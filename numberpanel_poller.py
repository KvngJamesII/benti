# -*- coding: utf-8 -*-
"""
NumberPanel SMS Poller
Polls SMS from http://51.89.99.105/NumberPanel/ and routes them
into the Eden database exactly like sms_poller.py does for IVAS.
"""

import re
import time
import threading
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

# ── Service detection (same as sms_poller) ─────────
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


def solve_math_captcha(html: str) -> str | None:
    """Find and solve the math captcha from the login form label."""
    soup = BeautifulSoup(html, "html.parser")
    for label in soup.find_all("label"):
        text = label.get_text()
        if "what is" in text.lower():
            match = re.search(r"(\d+)\s*\+\s*(\d+)", text)
            if match:
                a, b = int(match.group(1)), int(match.group(2))
                print(f"[NumberPanel] Captcha: {a} + {b} = {a + b}")
                return str(a + b)
            match = re.search(r"(\d+)\s*-\s*(\d+)", text)
            if match:
                a, b = int(match.group(1)), int(match.group(2))
                print(f"[NumberPanel] Captcha: {a} - {b} = {a - b}")
                return str(a - b)
            match = re.search(r"(\d+)\s*[x\xd7\*]\s*(\d+)", text)
            if match:
                a, b = int(match.group(1)), int(match.group(2))
                print(f"[NumberPanel] Captcha: {a} * {b} = {a * b}")
                return str(a * b)
    return None


class NumberPanelPoller:
    """Background service that polls NumberPanel for new SMS."""

    def __init__(self, app):
        self.app = app
        self.client: httpx.Client | None = None
        self.logged_in = False
        self.last_login: float = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.poll_count = 0
        self.otps_fetched = 0

    # ── lifecycle ──────────────────────────
    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[NumberPanel] Background thread started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._close_client()
        print("[NumberPanel] Stopped")

    # ── main loop ──────────────────────────
    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    self._poll_once()
            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as e:
                print(f"[NumberPanel] Connection error, forcing re-login: {e}")
                self.logged_in = False
                self._close_client()
            except Exception as e:
                print(f"[NumberPanel] Error: {e}")
                self.logged_in = False
            # Read poll interval from DB settings (inside app context)
            poll_wait = self.app.config.get("NP_POLL_INTERVAL", 30)
            try:
                with self.app.app_context():
                    from models import get_setting
                    poll_wait = int(get_setting("np_poll_interval", str(poll_wait)))
            except Exception:
                pass
            self._stop_event.wait(poll_wait)

    def _close_client(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    # ── single poll cycle ──────────────────
    def _poll_once(self):
        from models import db, SMS, Number, User, TestNumber, TestSMS, get_setting

        # Check if poller is enabled via admin settings
        enabled = get_setting("np_enabled", "1")
        if enabled == "0":
            return

        now = time.time()
        refresh = self.app.config.get("NP_LOGIN_REFRESH", 600)

        # Read poll interval from DB settings
        try:
            poll_int = int(get_setting("np_poll_interval", str(self.app.config.get("NP_POLL_INTERVAL", 30))))
        except (TypeError, ValueError):
            poll_int = 30

        # login / re-login
        if not self.logged_in or (now - self.last_login) >= refresh:
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

            # Check if already processed
            if SMS.query.filter_by(external_id=ext_id).first():
                continue
            if TestSMS.query.filter_by(external_id=ext_id).first():
                continue

            phone = msg["number"]

            # Check if this is a test number
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

            # Normal flow: find the user who owns this number
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

            # credit user balance
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

    # ── login to NumberPanel ───────────────
    def _login(self) -> bool:
        """Login with retry (captcha is flaky server-side)."""
        from models import get_setting

        for attempt in range(5):
            try:
                self._close_client()

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
                self.client = httpx.Client(
                    timeout=30.0,
                    follow_redirects=True,
                    headers=headers,
                    verify=False,
                )

                # Read credentials from DB settings, fall back to config.py
                login_url = get_setting("np_login_url", self.app.config.get("NP_LOGIN_URL", ""))
                signin_url = login_url.rsplit("/", 1)[0] + "/signin"
                username = get_setting("np_username", self.app.config.get("NP_USERNAME", ""))
                password = get_setting("np_password", self.app.config.get("NP_PASSWORD", ""))

                page = self.client.get(login_url)

                # Solve math captcha from <label>
                captcha_answer = solve_math_captcha(page.text)
                if not captcha_answer:
                    print("[NumberPanel] Could not solve captcha")
                    continue

                data = {
                    "username": username,
                    "password": password,
                    "capt": captcha_answer,
                }

                # Grab any hidden fields
                soup = BeautifulSoup(page.text, "html.parser")
                form = soup.find("form")
                if form:
                    for inp in form.find_all("input", {"type": "hidden"}):
                        name = inp.get("name")
                        if name and name not in data:
                            data[name] = inp.get("value", "")

                resp = self.client.post(signin_url, data=data)

                # Check if login succeeded (should redirect away from login page)
                if "login" in str(resp.url).lower().split("?")[0].split("/")[-1]:
                    print(f"[NumberPanel] Login attempt {attempt+1} failed, retrying...")
                    time.sleep(2)
                    continue

                self.logged_in = True
                self.last_login = time.time()
                print("[NumberPanel] Login OK")
                return True

            except Exception as e:
                print(f"[NumberPanel] Login error (attempt {attempt+1}): {e}")
                time.sleep(2)

        print("[NumberPanel] Login FAILED after 5 attempts")
        self.logged_in = False
        return False

    # ── fetch SMS from NumberPanel ─────────
    def _fetch_sms(self) -> list[dict]:
        """
        The NumberPanel SMS CDR Reports page uses a server-side DataTable.
        We extract the sAjaxSource URL and call it to get JSON data.
        """
        messages: list[dict] = []
        from models import get_setting
        sms_url = get_setting("np_sms_url", self.app.config.get("NP_SMS_URL", ""))

        try:
            # Load the reports page to get the sAjaxSource
            resp = self.client.get(sms_url)

            # Check if session is still valid
            if "login" in str(resp.url).lower().split("/")[-1]:
                print("[NumberPanel] Session expired, forcing re-login")
                self.logged_in = False
                return []

            # Extract sAjaxSource from DataTable init
            match = re.search(r'"sAjaxSource"\s*:\s*"([^"]+)"', resp.text)
            if not match:
                print("[NumberPanel] No sAjaxSource found in page")
                return []

            ajax_path = match.group(1)
            # Build full URL (path is relative to /NumberPanel/agent/)
            base_url = sms_url.rsplit("/", 1)[0]
            ajax_url = f"{base_url}/{ajax_path}"

            # Fetch data from AJAX endpoint
            r = self.client.get(ajax_url, headers={
                "Referer": sms_url,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            })

            if r.status_code != 200:
                print(f"[NumberPanel] AJAX returned {r.status_code}")
                return []

            data = r.json()
            rows = data.get("aaData") or data.get("data") or []

            for row in rows:
                if not isinstance(row, list) or len(row) < 6:
                    continue

                # Columns: [0]=date, [1]=range/country, [2]=number, [3]=CLI, [4]=client, [5]=SMS
                date = self._strip_html(str(row[0])).strip()

                # Skip the totals/summary row (date field contains commas or "NAN")
                if "," in date or "NAN" in date.upper() or "%" in date:
                    continue
                country_raw = self._strip_html(str(row[1])).strip()
                destination = self._strip_html(str(row[2])).strip()
                source = self._strip_html(str(row[3])).strip()
                sms_text = self._strip_html(str(row[5])).strip().replace("\x00", "")

                if not sms_text or not destination:
                    continue

                # Extract country name from range string (e.g. "Nigeria-Smile-KM-2" -> "Nigeria")
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

        except Exception as e:
            print(f"[NumberPanel] Fetch error: {e}")
            return []

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text."""
        return re.sub(r"<[^>]+>", "", text)
