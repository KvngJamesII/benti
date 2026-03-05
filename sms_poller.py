# -*- coding: utf-8 -*-
"""
SMS Poller – adapted from bot_old.py
Runs in a background thread, fetches SMS from the external panel,
and routes them to the correct user in the Eden database.
"""

import re
import ssl
import time
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

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


def extract_otp(sms_text: str) -> str:
    m = re.search(r"(\d{3}-\d{3})", sms_text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4,8})\b", sms_text)
    if m:
        return m.group(1)
    return "N/A"


class SMSPoller:
    """Background service that polls the external panel for new SMS."""

    def __init__(self, app):
        self.app = app
        self.client: httpx.Client | None = None
        self.csrf: str | None = None
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
        print("[SMSPoller] Background thread started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        print("[SMSPoller] Stopped")

    # ── main loop ──────────────────────────
    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    self._poll_once()
            except (ssl.SSLError, httpx.ConnectError, httpx.ReadError) as e:
                print(f"[SMSPoller] SSL/connection error, forcing re-login: {e}")
                self.csrf = None
                self._close_client()
            except Exception as e:
                print(f"[SMSPoller] Error: {e}")
                self.csrf = None
            self._stop_event.wait(self.app.config.get("POLL_INTERVAL", 5))

    def _close_client(self):
        """Safely close the HTTP client."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    # ── single poll cycle ──────────────────
    def _poll_once(self):
        from models import db, SMS, Number, User, TestNumber, TestSMS, get_setting

        now = time.time()
        refresh = self.app.config.get("LOGIN_REFRESH", 600)

        # login / re-login
        if self.csrf is None or (now - self.last_login) >= refresh:
            if not self._login():
                return

        # Clean expired test numbers on each poll cycle
        expired_tests = TestNumber.query.filter(TestNumber.expires_at <= datetime.utcnow()).all()
        for tn in expired_tests:
            TestSMS.query.filter_by(phone_number=tn.phone_number).delete()
            db.session.delete(tn)
        if expired_tests:
            db.session.commit()
            print(f"[SMSPoller] Cleaned {len(expired_tests)} expired test numbers")

        messages = self._fetch_sms()
        new_count = 0
        test_count = 0

        otp_rate = float(get_setting("otp_rate", "0.005"))

        for msg in messages:
            ext_id = msg["id"]

            # Check if already processed in either table
            if SMS.query.filter_by(external_id=ext_id).first():
                continue
            if TestSMS.query.filter_by(external_id=ext_id).first():
                continue

            phone = msg["number"]

            # Check if this is a test number
            test_number = TestNumber.query.filter_by(phone_number=phone).first()
            if test_number and not test_number.is_expired:
                # Route to TestSMS (censored display)
                test_sms = TestSMS(
                    external_id=ext_id,
                    phone_number=phone,
                    country=msg["country"],
                    service=msg["service"],
                    otp_code=msg["otp"],
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
                # send to admin
                admin = User.query.filter_by(role="admin").first()
                if admin:
                    target_user_id = admin.id

            # ── OTP limit: max 10 per phone number ──
            otp_count = SMS.query.filter_by(phone_number=phone).count()
            if otp_count >= 10:
                continue

            sms_rec = SMS(
                external_id=ext_id,
                phone_number=phone,
                country=msg["country"],
                service=msg["service"],
                otp_code=msg["otp"],
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
                print(f"[SMSPoller] +{new_count} new OTP(s) stored")
            if test_count:
                print(f"[SMSPoller] +{test_count} test OTP(s) stored")

        self.poll_count += 1

    # ── login to external panel ────────────
    def _login(self) -> bool:
        try:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            }
            # Create SSL context that's more tolerant of connection issues
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
            ssl_ctx.check_hostname = True
            ssl_ctx.verify_mode = ssl.CERT_REQUIRED

            self.client = httpx.Client(
                timeout=30.0,
                follow_redirects=True,
                headers=headers,
                verify=ssl_ctx,
            )

            login_url = self.app.config["PANEL_LOGIN_URL"]
            page = self.client.get(login_url)
            soup = BeautifulSoup(page.text, "html.parser")
            token_input = soup.find("input", {"name": "_token"})

            data = {
                "email": self.app.config["PANEL_USERNAME"],
                "password": self.app.config["PANEL_PASSWORD"],
            }
            if token_input:
                data["_token"] = token_input["value"]

            resp = self.client.post(login_url, data=data)
            if "login" in str(resp.url):
                print("[SMSPoller] Login FAILED")
                self.csrf = None
                return False

            dash_soup = BeautifulSoup(resp.text, "html.parser")
            csrf_meta = dash_soup.find("meta", {"name": "csrf-token"})
            if not csrf_meta:
                print("[SMSPoller] No CSRF token found")
                self.csrf = None
                return False

            self.csrf = csrf_meta.get("content")
            self.last_login = time.time()
            print("[SMSPoller] Login OK")
            return True
        except Exception as e:
            print(f"[SMSPoller] Login error: {e}")
            self.csrf = None
            return False

    # ── fetch sms from external panel ──────
    def _fetch_sms(self) -> list[dict]:
        messages: list[dict] = []
        base_url = self.app.config["PANEL_BASE_URL"]
        sms_url = self.app.config["PANEL_SMS_URL"]

        try:
            today = datetime.now(timezone.utc)
            start_date = today - timedelta(days=1)
            from_str = start_date.strftime("%m/%d/%Y")
            to_str = today.strftime("%m/%d/%Y")

            payload = {"from": from_str, "to": to_str, "_token": self.csrf}
            resp = self._request_with_retry(sms_url, payload)
            if resp is None:
                return []
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            group_divs = soup.find_all("div", {"class": "pointer"})
            if not group_divs:
                return []

            group_ids = []
            for div in group_divs:
                match = re.search(r"getDetials\('(.+?)'\)", div.get("onclick", ""))
                if match:
                    group_ids.append(match.group(1))

            numbers_url = urljoin(base_url, "/portal/sms/received/getsms/number")
            sms_detail_url = urljoin(base_url, "/portal/sms/received/getsms/number/sms")

            for group_id in group_ids:
                try:
                    num_payload = {"start": from_str, "end": to_str, "range": group_id, "_token": self.csrf}
                    num_resp = self._request_with_retry(numbers_url, num_payload)
                    if num_resp is None:
                        continue
                    num_soup = BeautifulSoup(num_resp.text, "html.parser")
                    number_divs = num_soup.select("div[onclick*='getDetialsNumber']")
                    if not number_divs:
                        continue

                    for num_div in number_divs:
                        phone = num_div.text.strip()
                        try:
                            sms_payload = {
                                "start": from_str, "end": to_str,
                                "Number": phone, "Range": group_id, "_token": self.csrf,
                            }
                            sms_resp = self._request_with_retry(sms_detail_url, sms_payload)
                            if sms_resp is None:
                                continue
                            sms_soup = BeautifulSoup(sms_resp.text, "html.parser")
                            cards = sms_soup.find_all("div", class_="card-body")

                            for card in cards:
                                text_p = card.find("p", class_="mb-0")
                                if text_p:
                                    sms_text = text_p.get_text(separator="\n").strip()
                                    country_match = re.match(r"([a-zA-Z\s]+)", group_id)
                                    country = country_match.group(1).strip() if country_match else group_id.strip()
                                    messages.append({
                                        "id": f"{phone}-{sms_text}",
                                        "number": phone,
                                        "country": country,
                                        "sms": sms_text,
                                        "service": detect_service(sms_text),
                                        "otp": extract_otp(sms_text),
                                    })
                        except Exception as e:
                            print(f"[SMSPoller] SMS fetch error ({phone}): {e}")
                except Exception as e:
                    print(f"[SMSPoller] Group error ({group_id}): {e}")

            return messages
        except (ssl.SSLError, httpx.ConnectError, httpx.ReadError) as e:
            print(f"[SMSPoller] SSL/connection error during fetch, will re-login: {e}")
            self.csrf = None
            self._close_client()
            return []
        except Exception as e:
            print(f"[SMSPoller] Fetch error: {e}")
            return []

    def _request_with_retry(self, url: str, data: dict, retries: int = 2):
        """POST request with retry on SSL/timeout errors."""
        for attempt in range(retries + 1):
            try:
                return self.client.post(url, data=data)
            except (ssl.SSLError, httpx.ReadError, httpx.ConnectError) as e:
                if attempt < retries:
                    print(f"[SMSPoller] Retry {attempt+1}/{retries} for {url}: {e}")
                    time.sleep(1)
                    # Force re-create client on SSL error
                    self._close_client()
                    if not self._login():
                        return None
                else:
                    raise
        return None
