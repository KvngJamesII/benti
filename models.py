from datetime import datetime
from math import ceil
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ═══════════════════════════════════════════
#  SIMPLE PAGINATION HELPER  (for in-memory lists)
# ═══════════════════════════════════════════
class ListPagination:
    """Wraps a plain Python list into a pagination-like object."""
    def __init__(self, items, page, per_page):
        self.total = len(items)
        self.per_page = per_page
        self.page = max(1, min(page, self.pages or 1))
        start = (self.page - 1) * per_page
        self.items = items[start:start + per_page]
        self.has_prev = self.page > 1
        self.has_next = self.page < self.pages
        self.prev_num = self.page - 1
        self.next_num = self.page + 1

    @property
    def pages(self):
        return ceil(self.total / self.per_page) if self.total else 1

    def iter_pages(self, left_edge=1, left_current=1, right_current=2, right_edge=1):
        pages = []
        for p in range(1, self.pages + 1):
            if p <= left_edge or p > self.pages - right_edge or abs(p - self.page) <= max(left_current, right_current):
                pages.append(p)
            elif pages and pages[-1] is not None:
                pages.append(None)
        return pages


# ═══════════════════════════════════════════
#  USER
# ═══════════════════════════════════════════
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)  # login ID e.g. "200715"
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")  # admin | mod | user
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_banned = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Float, default=0.0)
    wallet_address = db.Column(db.String(256), nullable=True)
    binance_uid = db.Column(db.String(100), nullable=True)
    payment_method = db.Column(db.String(20), default="usdt_bep20")  # usdt_bep20 | binance_uid
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    created_by = db.relationship("User", remote_side=[id], backref="created_users")
    numbers = db.relationship("Number", foreign_keys="Number.allocated_to_id", backref="owner", lazy="dynamic")
    sms_messages = db.relationship("SMS", backref="owner", lazy="dynamic")
    withdrawals = db.relationship("Withdrawal", backref="owner", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role in ("admin", "super_admin")

    @property
    def is_super_admin(self):
        return self.role == "super_admin"

    @property
    def is_mod(self):
        return self.role == "mod"

    def __repr__(self):
        return f"<User {self.user_id} ({self.role})>"


# ═══════════════════════════════════════════
#  NUMBER BATCH  (one upload = one batch)
# ═══════════════════════════════════════════
class NumberBatch(db.Model):
    __tablename__ = "number_batches"

    id = db.Column(db.Integer, primary_key=True)
    country = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(256))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    total_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])
    numbers = db.relationship("Number", backref="batch", lazy="dynamic")


# ═══════════════════════════════════════════
#  NUMBER
# ═══════════════════════════════════════════
class Number(db.Model):
    __tablename__ = "numbers"

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(30), unique=True, nullable=False)
    country = db.Column(db.String(100), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("number_batches.id"), nullable=True)
    allocated_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    allocated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    allocated_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    allocated_by = db.relationship("User", foreign_keys=[allocated_by_id])


# ═══════════════════════════════════════════
#  SMS / OTP
# ═══════════════════════════════════════════
class SMS(db.Model):
    __tablename__ = "sms_messages"

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(300), unique=True, nullable=False)  # dedup key
    phone_number = db.Column(db.String(30), nullable=False)
    country = db.Column(db.String(100))
    service = db.Column(db.String(100))
    otp_code = db.Column(db.String(50))
    message = db.Column(db.Text)
    rate = db.Column(db.Float, default=0.005)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def censored_message(self):
        """Return the message with content replaced by asterisks."""
        if not self.message:
            return ""
        words = self.message.split()
        censored = []
        for w in words:
            if len(w) <= 2:
                censored.append("*" * len(w))
            else:
                censored.append(w[0] + "*" * (len(w) - 2) + w[-1])
        return " ".join(censored)


# ═══════════════════════════════════════════
#  PHONE COUNTRY CODE DETECTION
# ═══════════════════════════════════════════
PHONE_COUNTRY_CODES = {
    "93": "Afghanistan", "355": "Albania", "213": "Algeria", "376": "Andorra",
    "244": "Angola", "54": "Argentina", "374": "Armenia", "61": "Australia",
    "43": "Austria", "994": "Azerbaijan", "973": "Bahrain", "880": "Bangladesh",
    "375": "Belarus", "32": "Belgium", "229": "Benin", "975": "Bhutan",
    "591": "Bolivia", "55": "Brazil", "359": "Bulgaria", "226": "Burkina Faso",
    "855": "Cambodia", "237": "Cameroon", "1": "United States", "235": "Chad",
    "56": "Chile", "86": "China", "57": "Colombia", "242": "Congo",
    "506": "Costa Rica", "385": "Croatia", "53": "Cuba", "357": "Cyprus",
    "420": "Czech Republic", "45": "Denmark", "1809": "Dominican Republic",
    "1829": "Dominican Republic", "1849": "Dominican Republic",
    "593": "Ecuador", "20": "Egypt", "503": "El Salvador", "372": "Estonia",
    "251": "Ethiopia", "358": "Finland", "33": "France", "241": "Gabon",
    "220": "Gambia", "995": "Georgia", "49": "Germany", "233": "Ghana",
    "30": "Greece", "502": "Guatemala", "224": "Guinea", "509": "Haiti",
    "504": "Honduras", "852": "Hong Kong", "36": "Hungary", "354": "Iceland",
    "91": "India", "62": "Indonesia", "98": "Iran", "964": "Iraq",
    "353": "Ireland", "972": "Israel", "39": "Italy", "225": "Ivory Coast",
    "1876": "Jamaica", "81": "Japan", "962": "Jordan", "7": "Russia",
    "254": "Kenya", "965": "Kuwait", "996": "Kyrgyzstan", "856": "Laos",
    "371": "Latvia", "961": "Lebanon", "231": "Liberia", "218": "Libya",
    "370": "Lithuania", "352": "Luxembourg", "261": "Madagascar", "60": "Malaysia",
    "223": "Mali", "356": "Malta", "52": "Mexico", "373": "Moldova",
    "377": "Monaco", "976": "Mongolia", "382": "Montenegro", "212": "Morocco",
    "258": "Mozambique", "95": "Myanmar", "264": "Namibia", "977": "Nepal",
    "31": "Netherlands", "64": "New Zealand", "505": "Nicaragua", "227": "Niger",
    "234": "Nigeria", "850": "North Korea", "389": "North Macedonia", "47": "Norway",
    "968": "Oman", "92": "Pakistan", "507": "Panama", "595": "Paraguay",
    "51": "Peru", "63": "Philippines", "48": "Poland", "351": "Portugal",
    "974": "Qatar", "40": "Romania", "250": "Rwanda",
    "966": "Saudi Arabia", "221": "Senegal", "381": "Serbia",
    "232": "Sierra Leone", "65": "Singapore", "421": "Slovakia",
    "386": "Slovenia", "252": "Somalia", "27": "South Africa",
    "82": "South Korea", "34": "Spain", "94": "Sri Lanka", "249": "Sudan",
    "46": "Sweden", "41": "Switzerland", "963": "Syria", "886": "Taiwan",
    "992": "Tajikistan", "255": "Tanzania", "66": "Thailand", "228": "Togo",
    "216": "Tunisia", "90": "Turkey", "993": "Turkmenistan", "256": "Uganda",
    "380": "Ukraine", "971": "United Arab Emirates", "44": "United Kingdom",
    "598": "Uruguay", "998": "Uzbekistan",
    "58": "Venezuela", "84": "Vietnam", "967": "Yemen", "260": "Zambia",
    "263": "Zimbabwe",
}

# Pre-sort by prefix length descending so longer prefixes match first
_SORTED_PREFIXES = sorted(PHONE_COUNTRY_CODES.keys(), key=len, reverse=True)


def detect_country_from_phone(phone_number):
    """Detect country name from a phone number using country calling codes.
    Returns country name or None."""
    if not phone_number:
        return None
    clean = phone_number.replace(" ", "").replace("-", "").replace("+", "").replace("(", "").replace(")", "")
    for prefix in _SORTED_PREFIXES:
        if clean.startswith(prefix):
            return PHONE_COUNTRY_CODES[prefix]
    return None
# ═══════════════════════════════════════════
class Withdrawal(db.Model):
    __tablename__ = "withdrawals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    wallet_address = db.Column(db.String(256))
    payment_method = db.Column(db.String(20), default="usdt_bep20")
    status = db.Column(db.String(20), default="pending")  # pending | paid | rejected
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)


# ═══════════════════════════════════════════
#  SETTINGS  (key-value store)
# ═══════════════════════════════════════════
class Setting(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)


# ═══════════════════════════════════════════
#  ANNOUNCEMENT
# ═══════════════════════════════════════════
class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    variant = db.Column(db.String(20), default="info")  # info | warning | success | danger
    is_active = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = db.relationship("User", foreign_keys=[created_by_id])


# ═══════════════════════════════════════════
#  ACTIVITY LOG
# ═══════════════════════════════════════════
class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(200))
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])


# ═══════════════════════════════════════════
#  TEST NUMBER  (visible to all users/mods, expires after 23h)
# ═══════════════════════════════════════════
class TestNumber(db.Model):
    __tablename__ = "test_numbers"

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(30), unique=True, nullable=False)
    country = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(256), nullable=True)  # source file name
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])

    @property
    def is_expired(self):
        return datetime.utcnow() >= self.expires_at


# ═══════════════════════════════════════════
#  TEST SMS  (OTPs for test numbers – message is censored)
# ═══════════════════════════════════════════
class TestSMS(db.Model):
    __tablename__ = "test_sms_messages"

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(300), unique=True, nullable=False)
    phone_number = db.Column(db.String(30), nullable=False)
    country = db.Column(db.String(100))
    service = db.Column(db.String(100))
    otp_code = db.Column(db.String(50))
    message = db.Column(db.Text)  # stored full, displayed as asterisks
    rate = db.Column(db.Float, default=0.0)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def censored_message(self):
        """Return the message with content replaced by asterisks."""
        if not self.message:
            return ""
        # Keep first 5 chars, replace rest with asterisks
        words = self.message.split()
        censored = []
        for w in words:
            if len(w) <= 2:
                censored.append("*" * len(w))
            else:
                censored.append(w[0] + "*" * (len(w) - 2) + w[-1])
        return " ".join(censored)


# ═══════════════════════════════════════════
#  AUTO-REVOKE SCHEDULE
# ═══════════════════════════════════════════
class AutoRevokeSchedule(db.Model):
    __tablename__ = "auto_revoke_schedules"

    id = db.Column(db.Integer, primary_key=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    revoke_at = db.Column(db.DateTime, nullable=False)  # when to fire
    is_executed = db.Column(db.Boolean, default=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # NULL = all users
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    executed_at = db.Column(db.DateTime, nullable=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    target_user = db.relationship("User", foreign_keys=[target_user_id])


# ═══════════════════════════════════════════
#  BOT MOD  (Telegram IDs linked to site mods)
# ═══════════════════════════════════════════
class BotMod(db.Model):
    __tablename__ = "bot_mods"

    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    site_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    site_user = db.relationship("User", foreign_keys=[site_user_id])


# ═══════════════════════════════════════════
#  SUPPORT TICKET  (maps Telegram user → assigned staff)
# ═══════════════════════════════════════════
class SupportTicket(db.Model):
    __tablename__ = "support_tickets"

    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)  # the customer
    telegram_name = db.Column(db.String(256), nullable=True)
    assigned_to = db.Column(db.BigInteger, nullable=True)  # staff telegram_id
    site_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # linked site account
    is_open = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    site_user = db.relationship("User", foreign_keys=[site_user_id])


# ═══════════════════════════════════════════
#  SUPPORT MESSAGE
# ═══════════════════════════════════════════
class SupportMessage(db.Model):
    __tablename__ = "support_messages"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_tickets.id"), nullable=False)
    sender_telegram_id = db.Column(db.BigInteger, nullable=False)
    text = db.Column(db.Text, nullable=False)
    is_from_staff = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket = db.relationship("SupportTicket", backref="messages")


# ═══════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════
def get_setting(key, default=None):
    """Get a setting value by key, or return *default*."""
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default


def set_setting(key, value):
    """Create or update a setting."""
    s = Setting.query.filter_by(key=key).first()
    if s:
        s.value = str(value)
    else:
        s = Setting(key=key, value=str(value))
        db.session.add(s)
    db.session.commit()


def init_default_settings():
    """Seed default settings if they don't exist."""
    defaults = {
        "otp_rate": "0.005",
        "min_withdrawal": "5",
        "max_numbers_per_user": "100",
        "withdrawal_day": "Tuesday",
    }
    for k, v in defaults.items():
        if not Setting.query.filter_by(key=k).first():
            db.session.add(Setting(key=k, value=v))
    db.session.commit()
