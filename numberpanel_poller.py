# -*- coding: utf-8 -*-
"""
NumberPanel SMS Poller  (Playwright headless browser edition)
Polls SMS from http://51.89.99.105/NumberPanel/ using a real
headless Chromium browser – same approach as bot.js but in Python.
"""

import re
import time
import json
import threading
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ── Service detection ──────────────────────
SERVICE_KEYWORDS = {
    "Facebook": ["facebook"], "Google": ["google", "gmail"], "WhatsApp": ["whatsapp"],
    "Telegram": ["telegram"], "Instagram": ["instagram"], "Amazon": ["amazon"],
    "Netflix": ["netflix"], "LinkedIn": ["linkedin"], "Microsoft": ["microsoft", "outlook", "live.com"],
    "Apple": ["apple", "icloud"], "Twitter": ["twitter", "x.com"], "Snapchat": ["snapchat"],
    "TikTok": ["tiktok"], "Discord": ["discord"], "Signal": ["signal"],
    "Viber": ["viber"], "IMO": ["imo"], "PayPal": ["paypal"],
    "Binance": ["binance"], "Uber": ["uber"], "Bolt": ["bolt"],
    "Airbnb": ["airbnb"], "Yahoo": ["yahoo"], "Steam": ["steam"],
    "Spotify": ["spotify"], "Stripe": ["stripe"], "Coinbase": ["coinbase"],
}


def detect_service(sms_text: str) -> str:
    lower = sms_text.lower()
    for service, keywords in SERVICE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return service
    return "Unknown"


def solve_math_captcha(page_content: str) -> str | None:
    """Solve the math captcha from a label like 'What is 5 + 6 = ?'"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_content, "html.parser")
    for label in soup.find_all("label"):
        text = label.get_text()
        if "what is" in text.lower():
            m = re.search(r"(\d+)\s*\+\s*(\d+)", text)
            if m:
                return str(int(m.group(1)) + int(m.group(2)))
            m = re.search(r"(\d+)\s*-\s*(\d+)", text)
            if m:
                return str(int(m.group(1)) - int(m.group(2)))
            m = re.search(r"(\d+)\s*[x\xd7\*]\s*(\d+)", text)
            if m:
                return str(int(m.group(1)) * int(m.group(2)))
    return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


class NumberPanelPoller:
    """Background service that polls NumberPanel using a headless browser."""

    def __init__(self, app):
        self.app = app
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.poll_count = 0
        self.otps_fetched = 0
        # Playwright objects (created inside the thread)
        self._pw = None
        self._browser = None
        self._page = None
        self._logged_in = False
        self._last_login: float = 0

    # ── lifecycle ──────────────────────────
    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[NumberPanel] Playwright poller thread started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)
        self._cleanup_browser()
        print("[NumberPanel] Stopped")

    def _cleanup_browser(self):
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._pw = None
        self._logged_in = False

    # ── main loop ──────────────────────────
    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    self._poll_once()
            except Exception as e:
                print(f"[NumberPanel] Error: {e}")
                self._logged_in = False
                self._cleanup_browser()

            # Read poll interval from DB
            poll_wait = self.app.config.get("NP_POLL_INTERVAL", 30)
            try:
                with self.app.app_context():
                    from models import get_setting
                    poll_wait = int(get_setting("np_poll_interval", str(poll_wait)))
            except Exception:
                pass
            self._stop_event.wait(poll_wait)

    # ── single poll cycle ──────────────────
    def _poll_once(self):
        from models import db, SMS, Number, User, TestNumber, TestSMS, get_setting

        # Check if poller is enabled
        enabled = get_setting("np_enabled", "1")
        if enabled == "0":
            return

        now = time.time()
        refresh = self.app.config.get("NP_LOGIN_REFRESH", 600)

        # Login / re-login
        if not self._logged_in or (now - self._last_login) >= refresh:
            if not self._login():
                return

        # Clean expired test numbers
        expired_tests = TestNumber.query.filter(TestNumber.expires_at <= datetime.utcnow()).all()
        for tn in expired_tests:
            TestSMS.query.filter_by(phone_number=tn.phone_number).delete()
            db.session.delete(tn)
        if expired_tests:
            db.session.commit()
            print(f"[NumberPanel] Cleaned {len(expired_tests)} expired test numbers")

        messages = self._fetch_sms()
        new_count = 0
        test_count = 0
        otp_rate = float(get_setting("otp_rate", "0.005"))

        for msg in messages:
            ext_id = msg["id"]

            if SMS.query.filter_by(external_id=ext_id).first():
                continue
            if TestSMS.query.filter_by(external_id=ext_id).first():
                continue

            phone = msg["number"]

            # Test number?
            test_number = TestNumber.query.filter_by(phone_number=phone).first()
            if test_number and not test_number.is_expired:
                test_sms = TestSMS(
                    external_id=ext_id,
                    phone_number=phone,
                    country=msg["country"],
                    service=msg["service"],
                    message=msg["sms"],
                    rate=0.0,
                    received_at=datetime.utcnow(),
                )
                db.session.add(test_sms)
                test_count += 1
                continue

            # Normal flow
            number_rec = Number.query.filter_by(phone_number=phone, is_active=True).first()
            target_user_id = None
            if number_rec and number_rec.allocated_to_id:
                target_user_id = number_rec.allocated_to_id
            else:
                admin = User.query.filter_by(role="admin").first()
                if admin:
                    target_user_id = admin.id

            sms_rec = SMS(
                external_id=ext_id,
                phone_number=phone,
                country=msg["country"],
                service=msg["service"],
                message=msg["sms"],
                rate=otp_rate,
                user_id=target_user_id,
                received_at=datetime.utcnow(),
            )
            db.session.add(sms_rec)

            # Credit user balance
            if target_user_id and number_rec and number_rec.allocated_to_id:
                user = User.query.get(target_user_id)
                if user:
                    user.balance = (user.balance or 0) + otp_rate

            new_count += 1

        if new_count or test_count:
            db.session.commit()
            self.otps_fetched += new_count
            if new_count:
                print(f"[NumberPanel] +{new_count} new OTP(s) stored")
            if test_count:
                print(f"[NumberPanel] +{test_count} test OTP(s) stored")

        self.poll_count += 1

    # ── login via headless browser ─────────
    def _login(self) -> bool:
        from models import get_setting

        cfg = self.app.config
        login_url = get_setting("np_login_url", cfg.get("NP_LOGIN_URL", ""))
        username = get_setting("np_username", cfg.get("NP_USERNAME", ""))
        password = get_setting("np_password", cfg.get("NP_PASSWORD", ""))

        for attempt in range(5):
            try:
                # Fresh browser each login attempt
                self._cleanup_browser()
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                self._page = self._browser.new_page()
                self._page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })

                # Navigate to login
                print(f"[NumberPanel] Login attempt {attempt + 1} – navigating to {login_url}")
                self._page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

                # Solve captcha from page HTML
                html = self._page.content()
                captcha_answer = solve_math_captcha(html)
                if not captcha_answer:
                    print("[NumberPanel] Could not solve captcha, retrying...")
                    time.sleep(2)
                    continue

                print(f"[NumberPanel] Captcha answer: {captcha_answer}")

                # Fill in the form (character-by-character for reliability)
                self._page.evaluate("document.querySelector('input[name=\"username\"]').value = ''")
                self._page.type('input[name="username"]', username, delay=50)
                self._page.evaluate("document.querySelector('input[name=\"password\"]').value = ''")
                self._page.type('input[name="password"]', password, delay=50)
                self._page.evaluate("document.querySelector('input[name=\"capt\"]').value = ''")
                self._page.type('input[name="capt"]', str(captcha_answer), delay=50)

                # Submit the form via JS (most reliable across environments)
                self._page.evaluate("document.querySelector('form').submit()")
                time.sleep(10)

                # Check if login succeeded by looking at page CONTENT
                # (form.submit() via JS may not update the URL bar)
                body_text = self._page.inner_text("body").lower()
                if "welcome back" in body_text or "dashboard" in body_text or "sms module" in body_text:
                    self._logged_in = True
                    self._last_login = time.time()
                    print(f"[NumberPanel] Login OK")
                    return True

                print(f"[NumberPanel] Login attempt {attempt + 1} – page has no dashboard content, retrying...")
                time.sleep(2)
                continue

            except PwTimeout:
                print(f"[NumberPanel] Login timeout (attempt {attempt + 1})")
                time.sleep(2)
            except Exception as e:
                print(f"[NumberPanel] Login error (attempt {attempt + 1}): {e}")
                time.sleep(2)

        print("[NumberPanel] Login FAILED after 5 attempts")
        self._logged_in = False
        self._cleanup_browser()
        return False

    # ── fetch SMS via the browser ──────────
    def _fetch_sms(self) -> list[dict]:
        """
        Navigate to the SMS CDR Reports page with the headless browser,
        intercept the DataTable AJAX call, and parse the JSON response.
        """
        from models import get_setting
        messages: list[dict] = []
        sms_url = get_setting("np_sms_url", self.app.config.get("NP_SMS_URL", ""))

        if not self._page:
            print("[NumberPanel] No browser page, skipping fetch")
            self._logged_in = False
            return []

        try:
            # We'll intercept the AJAX response from the DataTable
            ajax_data = {}

            def handle_response(response):
                """Capture the DataTable AJAX JSON response."""
                try:
                    url = response.url
                    if "data_smscdr" in url or "sAjaxSource" in url or "sesskey" in url:
                        if response.status == 200:
                            try:
                                ajax_data["json"] = response.json()
                            except Exception:
                                pass
                except Exception:
                    pass

            self._page.on("response", handle_response)

            # Navigate to SMS reports page
            self._page.goto(sms_url, wait_until="domcontentloaded", timeout=60000)

            # Check if session expired (redirected to login)
            if "/login" in self._page.url.lower().split("?")[0]:
                print("[NumberPanel] Session expired, forcing re-login")
                self._logged_in = False
                return []

            # Wait for AJAX to complete
            self._page.wait_for_timeout(5000)

            # Remove the response listener
            self._page.remove_listener("response", handle_response)

            # If we captured AJAX data, parse it
            if "json" in ajax_data:
                rows = ajax_data["json"].get("aaData") or ajax_data["json"].get("data") or []
            else:
                # Fallback: extract sAjaxSource from the page and fetch it manually
                print("[NumberPanel] No intercepted AJAX, trying manual extraction...")
                html = self._page.content()
                match = re.search(r'"sAjaxSource"\s*:\s*"([^"]+)"', html)
                if not match:
                    print("[NumberPanel] No sAjaxSource found")
                    return []

                ajax_path = match.group(1)
                base = sms_url.rsplit("/", 1)[0]
                ajax_url = f"{base}/{ajax_path}"

                # Use the browser to fetch the AJAX URL (cookies included automatically)
                resp = self._page.evaluate(f"""
                    async () => {{
                        const r = await fetch("{ajax_url}", {{
                            headers: {{
                                "X-Requested-With": "XMLHttpRequest",
                                "Accept": "application/json"
                            }}
                        }});
                        return await r.json();
                    }}
                """)
                rows = resp.get("aaData") or resp.get("data") or []

            for row in rows:
                if not isinstance(row, list) or len(row) < 6:
                    continue

                date = _strip_html(str(row[0])).strip()

                # Skip totals/summary row
                if "," in date or "NAN" in date.upper() or "%" in date:
                    continue

                country_raw = _strip_html(str(row[1])).strip()
                destination = _strip_html(str(row[2])).strip()
                source = _strip_html(str(row[3])).strip()
                sms_text = _strip_html(str(row[5])).strip().replace("\x00", "")

                if not sms_text or not destination:
                    continue

                # Extract country from range string
                country_match = re.match(r"([A-Za-z]+)", country_raw)
                country = country_match.group(1) if country_match else country_raw

                ext_id = f"np-{date}-{destination}-{source}-{sms_text[:50]}"

                messages.append({
                    "id": ext_id,
                    "number": destination,
                    "country": country,
                    "sms": sms_text,
                    "service": detect_service(sms_text),
                })

            if messages:
                print(f"[NumberPanel] Fetched {len(messages)} SMS messages")

            return messages

        except PwTimeout:
            print("[NumberPanel] Timeout loading SMS page")
            self._logged_in = False
            return []
        except Exception as e:
            print(f"[NumberPanel] Fetch error: {e}")
            return []
