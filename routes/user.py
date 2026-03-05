import io
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from functools import wraps
from models import (
    db, User, Number, SMS, Withdrawal, ActivityLog, Announcement,
    TestNumber, TestSMS, get_setting,
)

user_bp = Blueprint("user", __name__, url_prefix="/user")


def user_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "user":
            flash("Access denied.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════
@user_bp.route("/dashboard")
@user_required
def dashboard():
    total_numbers = Number.query.filter_by(allocated_to_id=current_user.id, is_active=True).count()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_otps = SMS.query.filter(
        SMS.user_id == current_user.id,
        SMS.received_at >= today_start,
    ).count()
    total_otps = SMS.query.filter_by(user_id=current_user.id).count()
    balance = current_user.balance or 0.0
    otp_rate = float(get_setting("otp_rate", "0.005"))

    # Countries summary
    from sqlalchemy import func
    country_counts = db.session.query(Number.country, func.count(Number.id)).filter(
        Number.allocated_to_id == current_user.id, Number.is_active == True
    ).group_by(Number.country).all()

    recent_otps = SMS.query.filter_by(user_id=current_user.id).order_by(SMS.received_at.desc()).limit(5).all()

    # Active announcements
    active_announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()

    return render_template("user/dashboard.html",
        total_numbers=total_numbers, today_otps=today_otps,
        total_otps=total_otps, balance=balance, otp_rate=otp_rate,
        country_counts=country_counts, recent_otps=recent_otps,
        announcements=active_announcements,
    )


# ═══════════════════════════════════════════
#  MY NUMBERS
# ═══════════════════════════════════════════
@user_bp.route("/my-numbers")
@user_required
def my_numbers():
    from sqlalchemy import func
    from routes.admin import COUNTRY_FLAGS

    country_counts = db.session.query(Number.country, func.count(Number.id)).filter(
        Number.allocated_to_id == current_user.id, Number.is_active == True
    ).group_by(Number.country).all()

    return render_template("user/my_numbers.html",
        country_counts=country_counts, country_flags=COUNTRY_FLAGS,
    )


@user_bp.route("/my-numbers/<country>")
@user_required
def number_detail(country):
    numbers = Number.query.filter_by(
        allocated_to_id=current_user.id, country=country, is_active=True
    ).order_by(Number.allocated_at.desc()).all()

    from routes.admin import COUNTRY_FLAGS
    return render_template("user/number_detail.html",
        numbers=numbers, country=country,
        flag=COUNTRY_FLAGS.get(country, "🏳️"),
    )


@user_bp.route("/download-numbers/<country>")
@user_required
def download_numbers(country):
    numbers = Number.query.filter_by(
        allocated_to_id=current_user.id, country=country, is_active=True
    ).all()
    content = "\n".join([n.phone_number for n in numbers])
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment;filename={country}_numbers.txt"},
    )


# ═══════════════════════════════════════════
#  MY OTPs
# ═══════════════════════════════════════════
@user_bp.route("/my-otps")
@user_required
def my_otps():
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    q = SMS.query.filter_by(user_id=current_user.id)

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(SMS.received_at >= dt_from)
        except ValueError:
            pass
    else:
        # Default: today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        q = q.filter(SMS.received_at >= today_start)

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(SMS.received_at < dt_to)
        except ValueError:
            pass

    sms_list = q.order_by(SMS.received_at.desc()).all()
    return render_template("user/my_otps.html", sms_list=sms_list, date_from=date_from, date_to=date_to)


# ═══════════════════════════════════════════
#  PAYMENT / EARNINGS
# ═══════════════════════════════════════════
@user_bp.route("/payment")
@user_required
def payment():
    balance = current_user.balance or 0.0
    otp_rate = float(get_setting("otp_rate", "0.005"))
    total_otps = SMS.query.filter_by(user_id=current_user.id).count()
    total_earned = total_otps * otp_rate

    # Daily earnings breakdown (last 7 days)
    from sqlalchemy import func
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    daily = db.session.query(
        func.date(SMS.received_at), func.count(SMS.id)
    ).filter(
        SMS.user_id == current_user.id,
        SMS.received_at >= seven_days_ago,
    ).group_by(func.date(SMS.received_at)).all()

    withdrawal_history = Withdrawal.query.filter_by(user_id=current_user.id).order_by(
        Withdrawal.requested_at.desc()
    ).all()

    return render_template("user/payment.html",
        balance=balance, otp_rate=otp_rate,
        total_otps=total_otps, total_earned=total_earned,
        daily=daily, withdrawal_history=withdrawal_history,
    )


# ═══════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════
@user_bp.route("/settings", methods=["GET", "POST"])
@user_required
def settings():
    if request.method == "POST":
        method = request.form.get("payment_method", "usdt_bep20").strip()
        if method not in ("usdt_bep20", "binance_uid"):
            method = "usdt_bep20"

        wallet = request.form.get("wallet_address", "").strip()
        binance_uid = request.form.get("binance_uid", "").strip()

        current_user.payment_method = method
        current_user.wallet_address = wallet
        current_user.binance_uid = binance_uid
        db.session.commit()
        flash("Payment settings saved.", "success")
        return redirect(url_for("user.settings"))

    otp_rate = float(get_setting("otp_rate", "0.005"))
    min_withdrawal = float(get_setting("min_withdrawal", "5"))
    withdrawal_day = get_setting("withdrawal_day", "Tuesday")

    return render_template("user/settings.html",
        otp_rate=otp_rate, min_withdrawal=min_withdrawal,
        withdrawal_day=withdrawal_day,
    )


# ═══════════════════════════════════════════
#  WITHDRAWAL
# ═══════════════════════════════════════════
@user_bp.route("/withdrawal", methods=["GET", "POST"])
@user_required
def withdrawal():
    min_wd = float(get_setting("min_withdrawal", "5"))
    withdrawal_day = get_setting("withdrawal_day", "Tuesday")
    balance = current_user.balance or 0.0

    if request.method == "POST":
        amount = request.form.get("amount", type=float, default=0)

        if amount <= 0:
            flash("Invalid amount.", "danger")
            return redirect(url_for("user.withdrawal"))

        if amount > balance:
            flash("Insufficient balance.", "danger")
            return redirect(url_for("user.withdrawal"))

        if amount < min_wd:
            flash(f"Minimum withdrawal is ${min_wd}.", "danger")
            return redirect(url_for("user.withdrawal"))

        # Validate payment destination
        if current_user.payment_method == "binance_uid":
            if not current_user.binance_uid:
                flash("Please set your Binance UID in Settings first.", "danger")
                return redirect(url_for("user.settings"))
        else:
            if not current_user.wallet_address:
                flash("Please set your USDT BEP-20 wallet address in Settings first.", "danger")
                return redirect(url_for("user.settings"))

        # Check if today is the withdrawal day
        today_name = datetime.utcnow().strftime("%A")
        if today_name != withdrawal_day:
            flash(f"Withdrawals are only available on {withdrawal_day}s.", "warning")
            return redirect(url_for("user.withdrawal"))

        # Check for pending withdrawal
        pending = Withdrawal.query.filter_by(user_id=current_user.id, status="pending").first()
        if pending:
            flash("You already have a pending withdrawal request.", "warning")
            return redirect(url_for("user.withdrawal"))

        pay_dest = current_user.binance_uid if current_user.payment_method == "binance_uid" else current_user.wallet_address
        wd = Withdrawal(
            user_id=current_user.id,
            amount=amount,
            wallet_address=pay_dest,
            payment_method=current_user.payment_method or "usdt_bep20",
            status="pending",
        )
        db.session.add(wd)
        db.session.add(ActivityLog(
            user_id=current_user.id, action="withdrawal_request",
            details=f"Withdrawal request: ${amount:.4f} via {current_user.payment_method} to {pay_dest}",
        ))
        db.session.commit()
        flash(f"Withdrawal request for ${amount:.4f} submitted!", "success")
        return redirect(url_for("user.withdrawal"))

    history = Withdrawal.query.filter_by(user_id=current_user.id).order_by(
        Withdrawal.requested_at.desc()
    ).all()

    return render_template("user/withdrawal.html",
        balance=balance, min_withdrawal=min_wd,
        withdrawal_day=withdrawal_day, history=history,
    )


# ═══════════════════════════════════════════
#  TEST NUMBERS  (visible to all users)
# ═══════════════════════════════════════════
@user_bp.route("/test-numbers")
@user_required
def test_numbers():
    from routes.admin import COUNTRY_FLAGS
    # Clean expired
    expired = TestNumber.query.filter(TestNumber.expires_at <= datetime.utcnow()).all()
    for tn in expired:
        TestSMS.query.filter_by(phone_number=tn.phone_number).delete()
        db.session.delete(tn)
    if expired:
        db.session.commit()

    numbers = TestNumber.query.order_by(TestNumber.country, TestNumber.phone_number).all()
    return render_template("user/test_numbers.html",
        numbers=numbers, country_flags=COUNTRY_FLAGS,
    )


# ═══════════════════════════════════════════
#  TEST OTPs  (censored messages for test numbers)
# ═══════════════════════════════════════════
@user_bp.route("/test-otps")
@user_required
def test_otps():
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    q = TestSMS.query

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(TestSMS.received_at >= dt_from)
        except ValueError:
            pass
    else:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        q = q.filter(TestSMS.received_at >= today_start)

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(TestSMS.received_at < dt_to)
        except ValueError:
            pass

    sms_list = q.order_by(TestSMS.received_at.desc()).all()
    return render_template("user/test_otps.html", sms_list=sms_list, date_from=date_from, date_to=date_to)


# ═══════════════════════════════════════════
#  LIVE SMS  (all recent SMS with censored messages)
# ═══════════════════════════════════════════
@user_bp.route("/live-sms")
@user_required
def live_sms():
    from routes.admin import COUNTRY_FLAGS
    from models import detect_country_from_phone
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    q = SMS.query

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(SMS.received_at >= dt_from)
        except ValueError:
            pass
    else:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        q = q.filter(SMS.received_at >= today_start)

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(SMS.received_at < dt_to)
        except ValueError:
            pass

    sms_list = q.order_by(SMS.received_at.desc()).limit(500).all()

    for sms in sms_list:
        if not sms.country:
            sms._detected_country = detect_country_from_phone(sms.phone_number)
        else:
            sms._detected_country = sms.country

    return render_template("live_sms.html",
        sms_list=sms_list, date_from=date_from, date_to=date_to,
        country_flags=COUNTRY_FLAGS, role_prefix="user",
    )
