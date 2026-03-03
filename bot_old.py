# -*- coding: utf-8 -*-
import asyncio
import re
import html as html_lib
import httpx
from bs4 import BeautifulSoup
import time
import json
import os
from urllib.parse import urljoin
from datetime import datetime, timedelta, timezone
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = "8722526230:AAElK-moaq1hLmsk2wd9LGLvw4z0WQA4b54"
GROUP_ID = "-1003804984426"
ADMIN_ID = 7648364004

PANEL_CONFIG = {
    "login_url": "https://ivas.tempnum.qzz.io/login",
    "base_url": "https://ivas.tempnum.qzz.io",
    "sms_url": "https://ivas.tempnum.qzz.io/portal/sms/received/getsms",
    "username": "referboss0@gmail.com",
    "password": "12345678",
}

POLL_INTERVAL = 5
LOGIN_REFRESH = 600
PROCESSED_FILE = "processed_ids.json"
TEMPLATE_FILE = "template.json"

# ============================================
# LOOKUP DATA
# ============================================
COUNTRY_FLAGS = {
    "Afghanistan": "\U0001f1e6\U0001f1eb", "Albania": "\U0001f1e6\U0001f1f1", "Algeria": "\U0001f1e9\U0001f1ff",
    "Andorra": "\U0001f1e6\U0001f1e9", "Angola": "\U0001f1e6\U0001f1f4", "Argentina": "\U0001f1e6\U0001f1f7",
    "Armenia": "\U0001f1e6\U0001f1f2", "Australia": "\U0001f1e6\U0001f1fa", "Austria": "\U0001f1e6\U0001f1f9",
    "Azerbaijan": "\U0001f1e6\U0001f1ff", "Bahrain": "\U0001f1e7\U0001f1ed", "Bangladesh": "\U0001f1e7\U0001f1e9",
    "Belarus": "\U0001f1e7\U0001f1fe", "Belgium": "\U0001f1e7\U0001f1ea", "Benin": "\U0001f1e7\U0001f1ef",
    "Bhutan": "\U0001f1e7\U0001f1f9", "Bolivia": "\U0001f1e7\U0001f1f4", "Brazil": "\U0001f1e7\U0001f1f7",
    "Bulgaria": "\U0001f1e7\U0001f1ec", "Burkina Faso": "\U0001f1e7\U0001f1eb", "Cambodia": "\U0001f1f0\U0001f1ed",
    "Cameroon": "\U0001f1e8\U0001f1f2", "Canada": "\U0001f1e8\U0001f1e6", "Chad": "\U0001f1f9\U0001f1e9",
    "Chile": "\U0001f1e8\U0001f1f1", "China": "\U0001f1e8\U0001f1f3", "Colombia": "\U0001f1e8\U0001f1f4",
    "Congo": "\U0001f1e8\U0001f1ec", "Croatia": "\U0001f1ed\U0001f1f7", "Cuba": "\U0001f1e8\U0001f1fa",
    "Cyprus": "\U0001f1e8\U0001f1fe", "Czech Republic": "\U0001f1e8\U0001f1ff", "Denmark": "\U0001f1e9\U0001f1f0",
    "Egypt": "\U0001f1ea\U0001f1ec", "Estonia": "\U0001f1ea\U0001f1ea", "Ethiopia": "\U0001f1ea\U0001f1f9",
    "Finland": "\U0001f1eb\U0001f1ee", "France": "\U0001f1eb\U0001f1f7", "Gabon": "\U0001f1ec\U0001f1e6",
    "Gambia": "\U0001f1ec\U0001f1f2", "Georgia": "\U0001f1ec\U0001f1ea", "Germany": "\U0001f1e9\U0001f1ea",
    "Ghana": "\U0001f1ec\U0001f1ed", "Greece": "\U0001f1ec\U0001f1f7", "Guatemala": "\U0001f1ec\U0001f1f9",
    "Guinea": "\U0001f1ec\U0001f1f3", "Haiti": "\U0001f1ed\U0001f1f9", "Honduras": "\U0001f1ed\U0001f1f3",
    "Hong Kong": "\U0001f1ed\U0001f1f0", "Hungary": "\U0001f1ed\U0001f1fa", "Iceland": "\U0001f1ee\U0001f1f8",
    "India": "\U0001f1ee\U0001f1f3", "Indonesia": "\U0001f1ee\U0001f1e9", "Iran": "\U0001f1ee\U0001f1f7",
    "Iraq": "\U0001f1ee\U0001f1f6", "Ireland": "\U0001f1ee\U0001f1ea", "Israel": "\U0001f1ee\U0001f1f1",
    "Italy": "\U0001f1ee\U0001f1f9", "IVORY COAST": "\U0001f1e8\U0001f1ee", "Ivory Coast": "\U0001f1e8\U0001f1ee",
    "Jamaica": "\U0001f1ef\U0001f1f2", "Japan": "\U0001f1ef\U0001f1f5", "Jordan": "\U0001f1ef\U0001f1f4",
    "Kazakhstan": "\U0001f1f0\U0001f1ff", "Kenya": "\U0001f1f0\U0001f1ea", "Kuwait": "\U0001f1f0\U0001f1fc",
    "Kyrgyzstan": "\U0001f1f0\U0001f1ec", "Laos": "\U0001f1f1\U0001f1e6", "Latvia": "\U0001f1f1\U0001f1fb",
    "Lebanon": "\U0001f1f1\U0001f1e7", "Liberia": "\U0001f1f1\U0001f1f7", "Libya": "\U0001f1f1\U0001f1fe",
    "Lithuania": "\U0001f1f1\U0001f1f9", "Luxembourg": "\U0001f1f1\U0001f1fa", "Madagascar": "\U0001f1f2\U0001f1ec",
    "Malaysia": "\U0001f1f2\U0001f1fe", "Mali": "\U0001f1f2\U0001f1f1", "Malta": "\U0001f1f2\U0001f1f9",
    "Mexico": "\U0001f1f2\U0001f1fd", "Moldova": "\U0001f1f2\U0001f1e9", "Monaco": "\U0001f1f2\U0001f1e8",
    "Mongolia": "\U0001f1f2\U0001f1f3", "Montenegro": "\U0001f1f2\U0001f1ea", "Morocco": "\U0001f1f2\U0001f1e6",
    "Mozambique": "\U0001f1f2\U0001f1ff", "Myanmar": "\U0001f1f2\U0001f1f2", "Namibia": "\U0001f1f3\U0001f1e6",
    "Nepal": "\U0001f1f3\U0001f1f5", "Netherlands": "\U0001f1f3\U0001f1f1", "New Zealand": "\U0001f1f3\U0001f1ff",
    "Nicaragua": "\U0001f1f3\U0001f1ee", "Niger": "\U0001f1f3\U0001f1ea", "Nigeria": "\U0001f1f3\U0001f1ec",
    "North Korea": "\U0001f1f0\U0001f1f5", "North Macedonia": "\U0001f1f2\U0001f1f0", "Norway": "\U0001f1f3\U0001f1f4",
    "Oman": "\U0001f1f4\U0001f1f2", "Pakistan": "\U0001f1f5\U0001f1f0", "Panama": "\U0001f1f5\U0001f1e6",
    "Paraguay": "\U0001f1f5\U0001f1fe", "Peru": "\U0001f1f5\U0001f1ea", "Philippines": "\U0001f1f5\U0001f1ed",
    "Poland": "\U0001f1f5\U0001f1f1", "Portugal": "\U0001f1f5\U0001f1f9", "Qatar": "\U0001f1f6\U0001f1e6",
    "Romania": "\U0001f1f7\U0001f1f4", "Russia": "\U0001f1f7\U0001f1fa", "Rwanda": "\U0001f1f7\U0001f1fc",
    "Saudi Arabia": "\U0001f1f8\U0001f1e6", "Senegal": "\U0001f1f8\U0001f1f3", "Serbia": "\U0001f1f7\U0001f1f8",
    "Sierra Leone": "\U0001f1f8\U0001f1f1", "Singapore": "\U0001f1f8\U0001f1ec", "Slovakia": "\U0001f1f8\U0001f1f0",
    "Slovenia": "\U0001f1f8\U0001f1ee", "Somalia": "\U0001f1f8\U0001f1f4", "South Africa": "\U0001f1ff\U0001f1e6",
    "South Korea": "\U0001f1f0\U0001f1f7", "Spain": "\U0001f1ea\U0001f1f8", "Sri Lanka": "\U0001f1f1\U0001f1f0",
    "Sudan": "\U0001f1f8\U0001f1e9", "Sweden": "\U0001f1f8\U0001f1ea", "Switzerland": "\U0001f1e8\U0001f1ed",
    "Syria": "\U0001f1f8\U0001f1fe", "Taiwan": "\U0001f1f9\U0001f1fc", "Tajikistan": "\U0001f1f9\U0001f1ef",
    "Tanzania": "\U0001f1f9\U0001f1ff", "Thailand": "\U0001f1f9\U0001f1ed", "TOGO": "\U0001f1f9\U0001f1ec",
    "Tunisia": "\U0001f1f9\U0001f1f3", "Turkey": "\U0001f1f9\U0001f1f7", "Turkmenistan": "\U0001f1f9\U0001f1f2",
    "Uganda": "\U0001f1fa\U0001f1ec", "Ukraine": "\U0001f1fa\U0001f1e6", "United Arab Emirates": "\U0001f1e6\U0001f1ea",
    "United Kingdom": "\U0001f1ec\U0001f1e7", "United States": "\U0001f1fa\U0001f1f8", "Uruguay": "\U0001f1fa\U0001f1fe",
    "Uzbekistan": "\U0001f1fa\U0001f1ff", "Venezuela": "\U0001f1fb\U0001f1ea", "Vietnam": "\U0001f1fb\U0001f1f3",
    "Yemen": "\U0001f1fe\U0001f1ea", "Zambia": "\U0001f1ff\U0001f1f2", "Zimbabwe": "\U0001f1ff\U0001f1fc",
}

SERVICE_KEYWORDS = {
    "Facebook": ["facebook"], "Google": ["google", "gmail"], "WhatsApp": ["whatsapp"],
    "Telegram": ["telegram"], "Instagram": ["instagram"], "Amazon": ["amazon"],
    "Netflix": ["netflix"], "LinkedIn": ["linkedin"], "Microsoft": ["microsoft", "outlook", "live.com"],
    "Apple": ["apple", "icloud"], "Twitter": ["twitter"], "Snapchat": ["snapchat"],
    "TikTok": ["tiktok"], "Discord": ["discord"], "Signal": ["signal"],
    "Viber": ["viber"], "IMO": ["imo"], "PayPal": ["paypal"],
    "Binance": ["binance"], "Uber": ["uber"], "Bolt": ["bolt"],
    "Airbnb": ["airbnb"], "Yahoo": ["yahoo"], "Steam": ["steam"],
    "Spotify": ["spotify"], "Stripe": ["stripe"], "Coinbase": ["coinbase"],
}

SERVICE_EMOJIS = {
    "Telegram": "\U0001f4e9", "WhatsApp": "\U0001f7e2", "Facebook": "\U0001f4d8",
    "Instagram": "\U0001f4f8", "Google": "\U0001f50d", "Gmail": "\u2709\ufe0f",
    "Twitter": "\U0001f426", "TikTok": "\U0001f3b5", "Snapchat": "\U0001f47b",
    "Amazon": "\U0001f6d2", "Microsoft": "\U0001fa9f", "Netflix": "\U0001f3ac",
    "Spotify": "\U0001f3b6", "Apple": "\U0001f34f", "PayPal": "\U0001f4b0",
    "Binance": "\U0001fa99", "Discord": "\U0001f5e8\ufe0f", "Steam": "\U0001f3ae",
    "LinkedIn": "\U0001f4bc", "Uber": "\U0001f697", "Bolt": "\U0001f696",
    "Stripe": "\U0001f4b3", "Coinbase": "\U0001fa99", "Signal": "\U0001f510",
    "Viber": "\U0001f4de", "Yahoo": "\U0001f7e3", "Airbnb": "\U0001f3e0",
    "IMO": "\U0001f4ac", "Unknown": "\u2753",
}

# ============================================
# DEFAULT TEMPLATE (HTML mode)
# ============================================
DEFAULT_TEMPLATE = {
    "text": (
        "\U0001f4e8 <b>New OTP Received</b> {flag}\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\U0001f4cc <b>Service:</b> {service_emoji} {service}\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\U0001f4de <b>Number:</b> <code>{number}</code>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\U0001f513 <b>OTP:</b> <code>{otp}</code>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\U0001f4ac <b>Message:</b>\n"
        "<blockquote>{message}</blockquote>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "<i>OTP-King 2026</i>"
    ),
    "buttons": []
}

# ============================================
# STATE
# ============================================
_client = None
_csrf = None
_last_login = 0
_poll_count = 0
_otps_sent = 0
_start_time = time.time()
_processed_ids = set()

# ============================================
# HELPERS
# ============================================
def load_json_file(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default.copy() if isinstance(default, dict) else default

def save_json_file(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_processed_ids():
    global _processed_ids
    data = load_json_file(PROCESSED_FILE, [])
    _processed_ids = set(data)

def save_processed_ids():
    trimmed = list(_processed_ids)[-5000:]
    save_json_file(PROCESSED_FILE, trimmed)

def load_template():
    return load_json_file(TEMPLATE_FILE, DEFAULT_TEMPLATE)

def save_template(tpl):
    save_json_file(TEMPLATE_FILE, tpl)

def detect_service(sms_text):
    lower = sms_text.lower()
    for service, keywords in SERVICE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return service
    return "Unknown"

def extract_otp(sms_text):
    m = re.search(r"(\d{3}-\d{3})", sms_text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4,8})\b", sms_text)
    if m:
        return m.group(1)
    return "N/A"

def get_flag(country):
    return (
        COUNTRY_FLAGS.get(country)
        or COUNTRY_FLAGS.get(country.title())
        or COUNTRY_FLAGS.get(country.upper())
        or COUNTRY_FLAGS.get(country.capitalize())
        or "\U0001f3f3\ufe0f"
    )

def is_admin(user_id):
    return user_id == ADMIN_ID

def build_otp_message(msg_data):
    """Build the OTP message text and reply_markup from the template."""
    tpl = load_template()
    number = msg_data["number"]
    masked = f"+{number[:2]}***{number[-4:]}" if len(number) > 5 else number
    service = msg_data["service"]
    service_emoji = SERVICE_EMOJIS.get(service, "\u2753")

    text = tpl["text"]
    text = text.replace("{flag}", msg_data["flag"])
    text = text.replace("{service_emoji}", service_emoji)
    text = text.replace("{service}", html_lib.escape(service))
    text = text.replace("{number}", html_lib.escape(masked))
    text = text.replace("{otp}", html_lib.escape(msg_data["otp"]))
    text = text.replace("{message}", html_lib.escape(msg_data["sms"]))

    reply_markup = None
    if tpl.get("buttons"):
        keyboard = []
        for i in range(0, len(tpl["buttons"]), 2):
            row = [InlineKeyboardButton(tpl["buttons"][i]["text"], url=tpl["buttons"][i]["url"])]
            if i + 1 < len(tpl["buttons"]):
                row.append(InlineKeyboardButton(tpl["buttons"][i + 1]["text"], url=tpl["buttons"][i + 1]["url"]))
            keyboard.append(row)
        reply_markup = InlineKeyboardMarkup(keyboard)

    return text, reply_markup

# ============================================
# PANEL LOGIN
# ============================================
async def login_to_panel():
    global _client, _csrf, _last_login
    try:
        if _client:
            try:
                await _client.aclose()
            except Exception:
                pass

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Connection": "keep-alive",
        }
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        _client = httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers, limits=limits)

        print("\U0001f510 Logging into panel...")
        login_page = await _client.get(PANEL_CONFIG["login_url"])
        soup = BeautifulSoup(login_page.text, "html.parser")
        token_input = soup.find("input", {"name": "_token"})

        login_data = {"email": PANEL_CONFIG["username"], "password": PANEL_CONFIG["password"]}
        if token_input:
            login_data["_token"] = token_input["value"]

        login_res = await _client.post(PANEL_CONFIG["login_url"], data=login_data)

        if "login" in str(login_res.url):
            print("\u274c Login FAILED! Check credentials.")
            _csrf = None
            return False

        print("\u2705 Login SUCCESSFUL!")

        dash_soup = BeautifulSoup(login_res.text, "html.parser")
        csrf_meta = dash_soup.find("meta", {"name": "csrf-token"})
        if not csrf_meta:
            print("\u274c Could not find CSRF token.")
            _csrf = None
            return False

        _csrf = csrf_meta.get("content")
        _last_login = time.time()
        print(f"\U0001f510 CSRF token: {_csrf[:20]}...")
        return True

    except Exception as e:
        print(f"\u274c Login error: {e}")
        _csrf = None
        return False

# ============================================
# FETCH SMS
# ============================================
async def fetch_sms():
    messages = []
    base_url = PANEL_CONFIG["base_url"]
    sms_url = PANEL_CONFIG["sms_url"]

    try:
        today = datetime.now(timezone.utc)
        start_date = today - timedelta(days=1)
        from_str = start_date.strftime("%m/%d/%Y")
        to_str = today.strftime("%m/%d/%Y")

        payload = {"from": from_str, "to": to_str, "_token": _csrf}
        summary_res = await _client.post(sms_url, data=payload)
        summary_res.raise_for_status()

        soup = BeautifulSoup(summary_res.text, "html.parser")
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
                num_payload = {"start": from_str, "end": to_str, "range": group_id, "_token": _csrf}
                num_res = await _client.post(numbers_url, data=num_payload)
                num_soup = BeautifulSoup(num_res.text, "html.parser")
                number_divs = num_soup.select("div[onclick*='getDetialsNumber']")
                if not number_divs:
                    continue

                for num_div in number_divs:
                    phone = num_div.text.strip()
                    try:
                        sms_payload = {
                            "start": from_str, "end": to_str,
                            "Number": phone, "Range": group_id, "_token": _csrf,
                        }
                        sms_res = await _client.post(sms_detail_url, data=sms_payload)
                        sms_soup = BeautifulSoup(sms_res.text, "html.parser")
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
                                    "flag": get_flag(country),
                                })
                    except Exception as e:
                        print(f"  \u26a0\ufe0f Error fetching SMS for {phone}: {e}")
            except Exception as e:
                print(f"  \u26a0\ufe0f Error fetching group {group_id}: {e}")

        return messages
    except Exception as e:
        print(f"\u274c Error fetching SMS: {e}")
        return []

# ============================================
# SMS POLLING JOB
# ============================================
async def check_sms_job(context: ContextTypes.DEFAULT_TYPE):
    global _csrf, _last_login, _poll_count, _otps_sent

    try:
        now = time.time()

        # Login or re-login
        if _csrf is None or (now - _last_login) >= LOGIN_REFRESH:
            is_relogin = _csrf is not None
            if is_relogin:
                print("\U0001f504 Re-logging in (session refresh)...")

            success = await login_to_panel()
            if not success:
                return

            # Only send connection message on first login, not re-logins
            if not is_relogin:
                try:
                    await context.bot.send_message(
                        chat_id=GROUP_ID,
                        text=(
                            "\u2b50 <b>OTP KING CONNECTED AND RUNNING</b> \u2b50\n"
                            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                            "\U0001f7e2 Status: <b>Online</b>\n"
                            "\U0001f50d Monitoring for new OTPs.....\n"
                            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                            "<i>OTP-King 2026</i>"
                        ),
                        parse_mode="HTML",
                    )
                    print(f"\U0001f4e8 Connection message sent to group")
                except Exception as e:
                    print(f"\u274c Failed to send connection message: {e}")

        # Poll
        messages = await fetch_sms()
        new_count = 0

        for msg in messages:
            if msg["id"] not in _processed_ids:
                _processed_ids.add(msg["id"])
                text, reply_markup = build_otp_message(msg)
                try:
                    await context.bot.send_message(
                        chat_id=GROUP_ID,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                    new_count += 1
                    _otps_sent += 1
                except Exception as e:
                    print(f"\u274c Failed to send OTP: {e}")

        if new_count > 0:
            save_processed_ids()
            print(f"\u2705 Sent {new_count} new OTP(s)")

        _poll_count += 1
        if _poll_count % 60 == 0:
            print(f"\U0001f504 Still polling... ({_otps_sent} OTPs sent, {len(_processed_ids)} processed)")

    except httpx.RequestError as e:
        print(f"\u274c Network error: {e}. Will re-login next cycle.")
        _csrf = None
    except Exception as e:
        print(f"\u274c Poll error: {e}")
        import traceback
        traceback.print_exc()

# ============================================
# COMMANDS
# ============================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f451 <b>OTP King Bot</b>\n\n"
        "This bot monitors and forwards OTP messages.\n\n"
        "<b>Commands:</b>\n"
        "/alive - Check if bot is running\n"
        "/template - Edit OTP message template (admin)\n"
        "/stats - Bot statistics (admin)",
        parse_mode="HTML",
    )

async def alive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = int(time.time() - _start_time)
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)

    status = "\U0001f7e2 Connected" if _csrf else "\U0001f534 Disconnected"
    await update.message.reply_text(
        f"\U0001f451 <b>OTP King Status</b>\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4e1 Panel: {status}\n"
        f"\u23f1 Uptime: {hours}h {minutes}m {seconds}s\n"
        f"\U0001f4e8 OTPs Sent: {_otps_sent}\n"
        f"\U0001f504 Polls: {_poll_count}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"<i>OTP-King 2026</i>",
        parse_mode="HTML",
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uptime = int(time.time() - _start_time)
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    tpl = load_template()
    btn_count = len(tpl.get("buttons", []))
    await update.message.reply_text(
        f"\U0001f4ca <b>Bot Statistics</b>\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4e1 Panel: {'Connected' if _csrf else 'Disconnected'}\n"
        f"\u23f1 Uptime: {hours}h {minutes}m {seconds}s\n"
        f"\U0001f4e8 OTPs Sent: {_otps_sent}\n"
        f"\U0001f504 Total Polls: {_poll_count}\n"
        f"\U0001f4be Processed IDs: {len(_processed_ids)}\n"
        f"\U0001f4dd Template Buttons: {btn_count}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        parse_mode="HTML",
    )

# ============================================
# TEMPLATE MANAGEMENT
# ============================================
def get_template_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u270f\ufe0f Edit Template", callback_data="tpl_edit")],
        [
            InlineKeyboardButton("\u2795 Add Button", callback_data="tpl_add_btn"),
            InlineKeyboardButton("\U0001f5d1\ufe0f Clear Buttons", callback_data="tpl_clear_btn"),
        ],
        [
            InlineKeyboardButton("\U0001f441\ufe0f Preview", callback_data="tpl_preview"),
            InlineKeyboardButton("\U0001f9ea Live Test", callback_data="tpl_live_test"),
        ],
        [InlineKeyboardButton("\U0001f504 Reset Default", callback_data="tpl_reset")],
    ])

async def template_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    tpl = load_template()
    btn_info = "None" if not tpl.get("buttons") else ", ".join(b["text"] for b in tpl["buttons"])
    preview_text = tpl["text"][:300] + ("..." if len(tpl["text"]) > 300 else "")

    await update.message.reply_text(
        f"\U0001f4dd <b>OTP Message Template</b>\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"<b>Current Template:</b>\n"
        f"<code>{html_lib.escape(preview_text)}</code>\n\n"
        f"<b>Buttons:</b> {html_lib.escape(btn_info)}\n\n"
        f"<b>Placeholders:</b>\n"
        f"<code>{{flag}}</code> - Country flag\n"
        f"<code>{{service}}</code> - Service name\n"
        f"<code>{{service_emoji}}</code> - Service emoji\n"
        f"<code>{{number}}</code> - Masked number\n"
        f"<code>{{otp}}</code> - OTP code\n"
        f"<code>{{message}}</code> - Full SMS text\n\n"
        f"Use HTML formatting: <code>&lt;b&gt;bold&lt;/b&gt;</code>, <code>&lt;i&gt;italic&lt;/i&gt;</code>, "
        f"<code>&lt;code&gt;mono&lt;/code&gt;</code>, <code>&lt;blockquote&gt;quote&lt;/blockquote&gt;</code>",
        parse_mode="HTML",
        reply_markup=get_template_keyboard(),
    )

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data

    if data == "tpl_edit":
        context.user_data["state"] = "edit_template"
        await query.message.reply_text(
            "\u270f\ufe0f <b>Send your new template now.</b>\n\n"
            "Use HTML + placeholders. Example:\n\n"
            "<code>\U0001f4e8 &lt;b&gt;New OTP&lt;/b&gt; {flag}\n"
            "\U0001f4cc Service: {service_emoji} {service}\n"
            "\U0001f513 OTP: &lt;code&gt;{otp}&lt;/code&gt;\n"
            "&lt;blockquote&gt;{message}&lt;/blockquote&gt;</code>",
            parse_mode="HTML",
        )

    elif data == "tpl_add_btn":
        context.user_data["state"] = "add_button"
        await query.message.reply_text(
            "\u2795 <b>Add Inline Button</b>\n\n"
            "Send in this format:\n"
            "<code>Button Name | https://example.com</code>",
            parse_mode="HTML",
        )

    elif data == "tpl_clear_btn":
        tpl = load_template()
        tpl["buttons"] = []
        save_template(tpl)
        await query.message.edit_text(
            "\U0001f5d1\ufe0f All buttons cleared!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="tpl_back")]]),
        )

    elif data == "tpl_reset":
        save_template(DEFAULT_TEMPLATE.copy())
        await query.message.edit_text(
            "\U0001f504 Template reset to default!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="tpl_back")]]),
        )

    elif data == "tpl_preview":
        sample = {
            "number": "2290175xxxx",
            "country": "Benin",
            "sms": "Your verification code is 482916. Do not share this with anyone.",
            "service": "WhatsApp",
            "otp": "482916",
            "flag": "\U0001f1e7\U0001f1ef",
        }
        text, reply_markup = build_otp_message(sample)
        await query.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

    elif data == "tpl_live_test":
        await query.message.edit_text("\U0001f9ea Fetching a real OTP from the panel...")
        try:
            # Login if needed
            if _csrf is None:
                success = await login_to_panel()
                if not success:
                    await query.message.edit_text(
                        "\u274c Could not login to panel. Check credentials.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="tpl_back")]]),
                    )
                    return

            messages = await fetch_sms()
            if not messages:
                await query.message.edit_text(
                    "\u274c No OTPs found on the panel right now. Try again later.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="tpl_back")]]),
                )
                return

            # Pick the latest message and send to group
            msg_data = messages[-1]
            text, reply_markup = build_otp_message(msg_data)
            await context.bot.send_message(
                chat_id=GROUP_ID, text=text, parse_mode="HTML", reply_markup=reply_markup,
            )
            await query.message.edit_text(
                f"\u2705 Live test sent to group!\n\n"
                f"Service: {msg_data['service']}\n"
                f"Country: {msg_data['country']}",
                reply_markup=get_template_keyboard(),
            )
        except Exception as e:
            await query.message.edit_text(
                f"\u274c Live test failed: {e}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="tpl_back")]]),
            )

    elif data == "tpl_back":
        await template_command.__wrapped__(update, context) if hasattr(template_command, '__wrapped__') else None
        # Just re-show the template menu
        tpl = load_template()
        btn_info = "None" if not tpl.get("buttons") else ", ".join(b["text"] for b in tpl["buttons"])
        await query.message.edit_text(
            f"\U0001f4dd <b>OTP Message Template</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"<b>Buttons:</b> {html_lib.escape(btn_info)}\n\n"
            f"Use /template to see full details.",
            parse_mode="HTML",
            reply_markup=get_template_keyboard(),
        )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message or not update.message.text:
        return

    state = context.user_data.get("state")
    text = update.message.text

    if state == "edit_template":
        context.user_data["state"] = None
        tpl = load_template()
        tpl["text"] = text
        save_template(tpl)

        # Show preview
        sample = {
            "number": "2290175xxxx",
            "country": "Benin",
            "sms": "Your code is 123456.",
            "service": "Telegram",
            "otp": "123456",
            "flag": "\U0001f1e7\U0001f1ef",
        }
        preview_text, preview_markup = build_otp_message(sample)
        await update.message.reply_text("\u2705 Template saved! Preview:")
        await update.message.reply_text(preview_text, parse_mode="HTML", reply_markup=preview_markup)
        await update.message.reply_text(
            "\U0001f9ea Want to test with a real OTP from the panel?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f9ea Live Test", callback_data="tpl_live_test")],
                [InlineKeyboardButton("\u2705 Done", callback_data="tpl_back")],
            ]),
        )

    elif state == "add_button":
        context.user_data["state"] = None
        if "|" not in text:
            await update.message.reply_text("\u274c Wrong format. Use: <code>Name | URL</code>", parse_mode="HTML")
            return

        parts = text.split("|", 1)
        btn_text = parts[0].strip()
        btn_url = parts[1].strip()

        tpl = load_template()
        if len(tpl.get("buttons", [])) >= 6:
            await update.message.reply_text("\u274c Maximum 6 buttons allowed.")
            return

        tpl.setdefault("buttons", []).append({"text": btn_text, "url": btn_url})
        save_template(tpl)
        await update.message.reply_text(
            f"\u2705 Button added: <b>{html_lib.escape(btn_text)}</b>",
            parse_mode="HTML",
            reply_markup=get_template_keyboard(),
        )

# ============================================
# MAIN
# ============================================
def main():
    print("\U0001f680 OTP King Bot starting...")
    load_processed_ids()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("alive", alive_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("template", template_command))
    app.add_handler(CallbackQueryHandler(template_callback, pattern="^tpl_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.job_queue.run_repeating(check_sms_job, interval=POLL_INTERVAL, first=2)

    print(f"\U0001f451 Bot online! Polling every {POLL_INTERVAL}s")
    app.run_polling()

if __name__ == "__main__":
    main()
