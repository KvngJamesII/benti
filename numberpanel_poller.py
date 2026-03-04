# -*- coding: utf-8 -*-
"""
NumberPanel SMS Poller  (CR-API edition)
Polls SMS from the NumberPanel CR-API using a simple HTTP GET request.
No browser / Playwright needed – just token-based JSON API.
"""

import hashlib
import time
import threading
from datetime import datetime, timedelta, timezone

import httpx

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


class NumberPanelPoller:
    """Background service that polls the NumberPanel CR-API for SMS."""

    def __init__(self, app):
        self.app = app
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.poll_count = 0
        self.otps_fetched = 0

    # ── lifecycle ──────────────────────────
    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[NumberPanel] API poller thread started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)
        print("[NumberPanel] Stopped")

    # ── main loop ──────────────────────────
    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    self._poll_once()
            except Exception as e:
                print(f"[NumberPanel] Error: {e}")

            # Read poll interval from DB
            poll_wait = self.app.config.get("NP_POLL_INTERVAL", 10)
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

    # ── fetch SMS via CR-API ───────────────
    def _fetch_sms(self) -> list[dict]:
        """
        Call the CR-API viewstats endpoint and return parsed messages.
        API returns a JSON array of [service, phone, message, datetime].
        """
        from models import get_setting

        cfg = self.app.config
        api_url = get_setting("np_api_url", cfg.get("NP_API_URL", ""))
        max_records = int(get_setting("np_max_records", str(cfg.get("NP_MAX_RECORDS", 10))))

        # Load all API tokens (JSON list)
        import json as _json
        tokens: list[dict] = []
        raw = get_setting("np_api_tokens", "")
        if raw:
            try:
                tokens = _json.loads(raw)
            except Exception:
                pass
        if not tokens:
            # Fallback: single token from settings or config
            single = get_setting("np_api_token", cfg.get("NP_API_TOKEN", ""))
            if single:
                tokens = [{"name": "Default", "token": single}]

        if not api_url or not tokens:
            return []

        # Build date range (last 2 hours)
        now = datetime.now(timezone.utc)
        dt2 = now.strftime("%Y-%m-%d %H:%M:%S")
        dt1 = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

        messages: list[dict] = []
        seen_ids: set[str] = set()

        for t in tokens:
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.get(api_url, params={
                        "token": t["token"],
                        "dt1": dt1,
                        "dt2": dt2,
                        "records": max_records,
                    })
                    resp.raise_for_status()
                    data = resp.json()

                if not isinstance(data, list):
                    continue

                for record in data:
                    if not isinstance(record, list) or len(record) < 4:
                        continue

                    service = str(record[0] or "Unknown").strip()
                    phone = str(record[1] or "").strip()
                    sms_text = str(record[2] or "").strip().replace("\x00", "")
                    date_str = str(record[3] or "").strip()

                    if not phone or not sms_text:
                        continue

                    # Create unique ID from message data (same hash as api.js)
                    msg_data = f"{date_str}_{phone}_{service}_{sms_text}"
                    ext_id = "np-" + hashlib.md5(msg_data.encode()).hexdigest()

                    if ext_id in seen_ids:
                        continue
                    seen_ids.add(ext_id)

                    # Try to detect service from SMS content (more reliable)
                    detected = detect_service(sms_text)
                    if detected == "Unknown":
                        detected = service

                    # Extract country from phone prefix (basic)
                    country = "Unknown"
                    if phone.startswith("234"):
                        country = "Nigeria"
                    elif phone.startswith("1"):
                        country = "USA"
                    elif phone.startswith("44"):
                        country = "UK"
                    elif phone.startswith("91"):
                        country = "India"

                    messages.append({
                        "id": ext_id,
                        "number": phone,
                        "country": country,
                        "sms": sms_text,
                        "service": detected,
                        "date": date_str,
                    })

            except httpx.HTTPStatusError as e:
                print(f"[NumberPanel] API HTTP error ({t.get('name', '?')}): {e.response.status_code}")
            except Exception as e:
                print(f"[NumberPanel] API error ({t.get('name', '?')}): {e}")

        if messages:
            print(f"[NumberPanel] Fetched {len(messages)} SMS from {len(tokens)} token(s)")

        return messages
