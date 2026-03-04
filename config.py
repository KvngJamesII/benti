import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "eden-sms-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "data", "eden.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

    # ── Admin defaults ──
    ADMIN_USER_ID = "200715"
    ADMIN_PASSWORD = "isr828u2"

    # ── SMS Panel (external OTP source) ──
    PANEL_LOGIN_URL = "https://ivas.tempnum.qzz.io/login"
    PANEL_BASE_URL = "https://ivas.tempnum.qzz.io"
    PANEL_SMS_URL = "https://ivas.tempnum.qzz.io/portal/sms/received/getsms"
    PANEL_USERNAME = "referboss0@gmail.com"
    PANEL_PASSWORD = "12345678"
    POLL_INTERVAL = 5  # seconds
    LOGIN_REFRESH = 600  # seconds

    # ── NumberPanel CR-API (second OTP source) ──
    NP_API_URL = "http://147.135.212.197/crapi/st/viewstats"
    NP_API_TOKEN = "RlZVRklBUzSAYplnanhsQoRyhWaAdI5mfGyFf2aAlWiAj4BkYGGNSQ=="
    NP_MAX_RECORDS = 10
    NP_POLL_INTERVAL = 10  # seconds

    # ── Default settings (stored in DB, editable by admin) ──
    DEFAULT_OTP_RATE = 0.005  # $ per OTP
    DEFAULT_MIN_WITHDRAWAL = 5.0  # $
    DEFAULT_MAX_NUMBERS_PER_USER = 100  # per 24 hrs
    WITHDRAWAL_DAY = "Tuesday"
