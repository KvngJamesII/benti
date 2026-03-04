from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


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
        return self.role == "admin"

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


# ═══════════════════════════════════════════
#  WITHDRAWAL
# ═══════════════════════════════════════════
class Withdrawal(db.Model):
    __tablename__ = "withdrawals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    wallet_address = db.Column(db.String(256))
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
