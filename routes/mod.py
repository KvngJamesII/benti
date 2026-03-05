from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from models import (
    db, User, Number, SMS, ActivityLog, Announcement,
    TestNumber, TestSMS, get_setting, detect_country_from_phone,
)

mod_bp = Blueprint("mod", __name__, url_prefix="/mod")


def mod_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "mod":
            flash("Access denied.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════
@mod_bp.route("/dashboard")
@mod_required
def dashboard():
    my_users = User.query.filter_by(created_by_id=current_user.id, role="user").all()
    my_user_ids = [u.id for u in my_users]

    total_users = len(my_users)
    total_numbers_allocated = Number.query.filter(Number.allocated_to_id.in_(my_user_ids)).count() if my_user_ids else 0
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sms = SMS.query.filter(
        SMS.user_id.in_(my_user_ids),
        SMS.received_at >= today_start,
    ).count() if my_user_ids else 0

    return render_template("mod/dashboard.html",
        total_users=total_users,
        total_numbers_allocated=total_numbers_allocated,
        today_sms=today_sms,
        my_users=my_users,
        announcements=Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all(),
    )


# ═══════════════════════════════════════════
#  MY USERS
# ═══════════════════════════════════════════
@mod_bp.route("/users")
@mod_required
def my_users():
    users = User.query.filter_by(created_by_id=current_user.id, role="user").order_by(User.created_at.desc()).all()
    # For each user, get their number counts
    user_data = []
    for u in users:
        num_count = Number.query.filter_by(allocated_to_id=u.id).count()
        user_data.append({"user": u, "number_count": num_count})
    return render_template("mod/my_users.html", user_data=user_data)


# ═══════════════════════════════════════════
#  CREATE USER
# ═══════════════════════════════════════════
@mod_bp.route("/create-user", methods=["GET", "POST"])
@mod_required
def create_user():
    if request.method == "POST":
        uid = request.form.get("user_id", "").strip()
        pwd = request.form.get("password", "").strip()

        if not uid or not pwd:
            flash("User ID and Password are required.", "danger")
            return redirect(url_for("mod.create_user"))

        if User.query.filter_by(user_id=uid).first():
            flash("User ID already exists.", "danger")
            return redirect(url_for("mod.create_user"))

        u = User(user_id=uid, role="user", created_by_id=current_user.id)
        u.set_password(pwd)
        db.session.add(u)
        db.session.add(ActivityLog(
            user_id=current_user.id, action="create_user",
            details=f"Mod created user: {uid}",
        ))
        db.session.commit()
        flash(f"User '{uid}' created successfully!", "success")
        return redirect(url_for("mod.my_users"))

    return render_template("mod/create_user.html")


# ═══════════════════════════════════════════
#  ALLOCATE NUMBERS
# ═══════════════════════════════════════════
@mod_bp.route("/allocate-numbers", methods=["GET", "POST"])
@mod_required
def allocate_numbers():
    if request.method == "POST":
        target_user_id = request.form.get("user_id", type=int)
        country = request.form.get("country", "").strip()
        quantity = request.form.get("quantity", type=int, default=0)

        target_user = User.query.get(target_user_id) if target_user_id else None
        # Mods can only allocate to their own users
        if not target_user or target_user.created_by_id != current_user.id:
            flash("You can only allocate numbers to your own users.", "danger")
            return redirect(url_for("mod.allocate_numbers"))

        max_per_day = int(get_setting("max_numbers_per_user", "100"))
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        already_today = Number.query.filter(
            Number.allocated_to_id == target_user.id,
            Number.allocated_at >= today_start,
        ).count()

        remaining = max_per_day - already_today
        if quantity > remaining:
            flash(f"Can only allocate {remaining} more numbers today (limit: {max_per_day}/day).", "warning")
            return redirect(url_for("mod.allocate_numbers"))

        available = Number.query.filter_by(
            country=country, allocated_to_id=None, is_active=True,
        ).limit(quantity).all()

        if len(available) < quantity:
            flash(f"Only {len(available)} numbers available for {country}.", "warning")

        now = datetime.utcnow()
        for n in available:
            n.allocated_to_id = target_user.id
            n.allocated_by_id = current_user.id
            n.allocated_at = now

        db.session.add(ActivityLog(
            user_id=current_user.id, action="allocate_numbers",
            details=f"Mod allocated {len(available)} {country} numbers to {target_user.user_id}",
        ))
        db.session.commit()
        flash(f"Allocated {len(available)} {country} numbers to {target_user.user_id}.", "success")
        return redirect(url_for("mod.allocate_numbers"))

    my_users = User.query.filter_by(created_by_id=current_user.id, role="user", is_banned=False).all()
    countries = db.session.query(Number.country).distinct().all()
    countries = sorted([c[0] for c in countries])
    country_avail = {}
    for c in countries:
        country_avail[c] = Number.query.filter_by(country=c, allocated_to_id=None, is_active=True).count()

    from routes.admin import COUNTRY_FLAGS
    return render_template("mod/allocate_numbers.html",
        users=my_users, countries=countries,
        country_avail=country_avail, country_flags=COUNTRY_FLAGS,
    )


# ═══════════════════════════════════════════
#  REVOKE NUMBERS  (dedicated page)
# ═══════════════════════════════════════════
@mod_bp.route("/revoke-numbers")
@mod_required
def revoke_numbers_page():
    """Show all mod's users with per-country number breakdown for selective revocation."""
    users = User.query.filter_by(created_by_id=current_user.id, role="user").order_by(User.user_id).all()
    user_numbers = []
    for u in users:
        nums = Number.query.filter_by(allocated_to_id=u.id).all()
        if not nums:
            continue
        # Group by country
        by_country: dict[str, int] = {}
        for n in nums:
            by_country[n.country] = by_country.get(n.country, 0) + 1
        user_numbers.append({"user": u, "total": len(nums), "by_country": by_country})
    return render_template("mod/revoke_numbers.html", user_numbers=user_numbers)


@mod_bp.route("/revoke-numbers/<int:uid>", methods=["POST"])
@mod_required
def revoke_numbers(uid):
    target = User.query.get_or_404(uid)
    if target.created_by_id != current_user.id:
        flash("You can only manage your own users.", "danger")
        return redirect(url_for("mod.my_users"))

    country = request.form.get("country", "")
    if country:
        nums = Number.query.filter_by(allocated_to_id=uid, country=country).update(
            {"allocated_to_id": None, "allocated_by_id": None, "allocated_at": None}
        )
    else:
        nums = Number.query.filter_by(allocated_to_id=uid).update(
            {"allocated_to_id": None, "allocated_by_id": None, "allocated_at": None}
        )

    db.session.add(ActivityLog(
        user_id=current_user.id, action="revoke_numbers",
        details=f"Mod revoked {nums} numbers from {target.user_id}" + (f" ({country})" if country else ""),
    ))
    db.session.commit()
    flash(f"Revoked {nums} numbers from {target.user_id}.", "info")
    # Redirect back to the referring page, default to revoke page
    referrer = request.referrer or ""
    if "my_users" in referrer or "users" in referrer:
        return redirect(url_for("mod.my_users"))
    return redirect(url_for("mod.revoke_numbers_page"))


# ═══════════════════════════════════════════
#  TEST NUMBERS  (visible to mods)
# ═══════════════════════════════════════════
@mod_bp.route("/test-numbers")
@mod_required
def test_numbers():
    from datetime import datetime, timedelta
    from routes.admin import COUNTRY_FLAGS
    # Clean expired
    expired = TestNumber.query.filter(TestNumber.expires_at <= datetime.utcnow()).all()
    for tn in expired:
        TestSMS.query.filter_by(phone_number=tn.phone_number).delete()
        db.session.delete(tn)
    if expired:
        db.session.commit()

    numbers = TestNumber.query.order_by(TestNumber.country, TestNumber.phone_number).all()
    return render_template("mod/test_numbers.html",
        numbers=numbers, country_flags=COUNTRY_FLAGS,
    )


@mod_bp.route("/test-otps")
@mod_required
def test_otps():
    from datetime import datetime, timedelta
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
    return render_template("mod/test_otps.html", sms_list=sms_list, date_from=date_from, date_to=date_to)


# ═══════════════════════════════════════════
#  LIVE SMS  (all recent SMS with censored messages)
# ═══════════════════════════════════════════
@mod_bp.route("/live-sms")
@mod_required
def live_sms():
    from datetime import datetime, timedelta
    from routes.admin import COUNTRY_FLAGS
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
        country_flags=COUNTRY_FLAGS, role_prefix="mod",
    )
