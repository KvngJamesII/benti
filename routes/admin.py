import os
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from functools import wraps
from models import (
    db, User, Number, NumberBatch, SMS, Withdrawal, Setting,
    ActivityLog, Announcement, TestNumber, TestSMS, get_setting, set_setting,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "admin":
            flash("Access denied.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ─── COUNTRY DATA ─────────────────────────
COUNTRY_FLAGS = {
    "Afghanistan": "🇦🇫", "Albania": "🇦🇱", "Algeria": "🇩🇿", "Andorra": "🇦🇩",
    "Angola": "🇦🇴", "Argentina": "🇦🇷", "Armenia": "🇦🇲", "Australia": "🇦🇺",
    "Austria": "🇦🇹", "Azerbaijan": "🇦🇿", "Bahrain": "🇧🇭", "Bangladesh": "🇧🇩",
    "Belarus": "🇧🇾", "Belgium": "🇧🇪", "Benin": "🇧🇯", "Bhutan": "🇧🇹",
    "Bolivia": "🇧🇴", "Brazil": "🇧🇷", "Bulgaria": "🇧🇬", "Burkina Faso": "🇧🇫",
    "Cambodia": "🇰🇭", "Cameroon": "🇨🇲", "Canada": "🇨🇦", "Chad": "🇹🇩",
    "Chile": "🇨🇱", "China": "🇨🇳", "Colombia": "🇨🇴", "Congo": "🇨🇬",
    "Costa Rica": "🇨🇷", "Croatia": "🇭🇷", "Cuba": "🇨🇺", "Cyprus": "🇨🇾",
    "Czech Republic": "🇨🇿", "Denmark": "🇩🇰", "Dominican Republic": "🇩🇴",
    "Ecuador": "🇪🇨", "Egypt": "🇪🇬", "El Salvador": "🇸🇻", "Estonia": "🇪🇪",
    "Ethiopia": "🇪🇹", "Finland": "🇫🇮", "France": "🇫🇷", "Gabon": "🇬🇦",
    "Gambia": "🇬🇲", "Georgia": "🇬🇪", "Germany": "🇩🇪", "Ghana": "🇬🇭",
    "Greece": "🇬🇷", "Guatemala": "🇬🇹", "Guinea": "🇬🇳", "Haiti": "🇭🇹",
    "Honduras": "🇭🇳", "Hong Kong": "🇭🇰", "Hungary": "🇭🇺", "Iceland": "🇮🇸",
    "India": "🇮🇳", "Indonesia": "🇮🇩", "Iran": "🇮🇷", "Iraq": "🇮🇶",
    "Ireland": "🇮🇪", "Israel": "🇮🇱", "Italy": "🇮🇹", "Ivory Coast": "🇨🇮",
    "Jamaica": "🇯🇲", "Japan": "🇯🇵", "Jordan": "🇯🇴", "Kazakhstan": "🇰🇿",
    "Kenya": "🇰🇪", "Kuwait": "🇰🇼", "Kyrgyzstan": "🇰🇬", "Laos": "🇱🇦",
    "Latvia": "🇱🇻", "Lebanon": "🇱🇧", "Liberia": "🇱🇷", "Libya": "🇱🇾",
    "Lithuania": "🇱🇹", "Luxembourg": "🇱🇺", "Madagascar": "🇲🇬", "Malaysia": "🇲🇾",
    "Mali": "🇲🇱", "Malta": "🇲🇹", "Mexico": "🇲🇽", "Moldova": "🇲🇩",
    "Monaco": "🇲🇨", "Mongolia": "🇲🇳", "Montenegro": "🇲🇪", "Morocco": "🇲🇦",
    "Mozambique": "🇲🇿", "Myanmar": "🇲🇲", "Namibia": "🇳🇦", "Nepal": "🇳🇵",
    "Netherlands": "🇳🇱", "New Zealand": "🇳🇿", "Nicaragua": "🇳🇮", "Niger": "🇳🇪",
    "Nigeria": "🇳🇬", "North Korea": "🇰🇵", "North Macedonia": "🇲🇰", "Norway": "🇳🇴",
    "Oman": "🇴🇲", "Pakistan": "🇵🇰", "Panama": "🇵🇦", "Paraguay": "🇵🇾",
    "Peru": "🇵🇪", "Philippines": "🇵🇭", "Poland": "🇵🇱", "Portugal": "🇵🇹",
    "Qatar": "🇶🇦", "Romania": "🇷🇴", "Russia": "🇷🇺", "Rwanda": "🇷🇼",
    "Saudi Arabia": "🇸🇦", "Senegal": "🇸🇳", "Serbia": "🇷🇸",
    "Sierra Leone": "🇸🇱", "Singapore": "🇸🇬", "Slovakia": "🇸🇰",
    "Slovenia": "🇸🇮", "Somalia": "🇸🇴", "South Africa": "🇿🇦",
    "South Korea": "🇰🇷", "Spain": "🇪🇸", "Sri Lanka": "🇱🇰", "Sudan": "🇸🇩",
    "Sweden": "🇸🇪", "Switzerland": "🇨🇭", "Syria": "🇸🇾", "Taiwan": "🇹🇼",
    "Tajikistan": "🇹🇯", "Tanzania": "🇹🇿", "Thailand": "🇹🇭", "Togo": "🇹🇬",
    "Tunisia": "🇹🇳", "Turkey": "🇹🇷", "Turkmenistan": "🇹🇲", "Uganda": "🇺🇬",
    "Ukraine": "🇺🇦", "United Arab Emirates": "🇦🇪", "United Kingdom": "🇬🇧",
    "United States": "🇺🇸", "Uruguay": "🇺🇾", "Uzbekistan": "🇺🇿",
    "Venezuela": "🇻🇪", "Vietnam": "🇻🇳", "Yemen": "🇾🇪", "Zambia": "🇿🇲",
    "Zimbabwe": "🇿🇼",
}


# ═══════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════
@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    total_users = User.query.filter_by(role="user").count()
    total_mods = User.query.filter_by(role="mod").count()
    total_numbers = Number.query.count()
    allocated_numbers = Number.query.filter(Number.allocated_to_id.isnot(None)).count()
    total_sms = SMS.query.count()
    today_sms = SMS.query.filter(SMS.received_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)).count()
    pending_withdrawals = Withdrawal.query.filter_by(status="pending").count()
    recent_sms = SMS.query.order_by(SMS.received_at.desc()).limit(10).all()
    recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()

    return render_template("admin/dashboard.html",
        total_users=total_users, total_mods=total_mods,
        total_numbers=total_numbers, allocated_numbers=allocated_numbers,
        total_sms=total_sms, today_sms=today_sms,
        pending_withdrawals=pending_withdrawals,
        recent_sms=recent_sms, recent_logs=recent_logs,
    )


# ═══════════════════════════════════════════
#  USERS MANAGEMENT
# ═══════════════════════════════════════════
@admin_bp.route("/users")
@admin_required
def users():
    role_filter = request.args.get("role", "all")
    q = User.query.filter(User.role != "admin")
    if role_filter == "mod":
        q = q.filter_by(role="mod")
    elif role_filter == "user":
        q = q.filter_by(role="user")
    all_users = q.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users, role_filter=role_filter)


@admin_bp.route("/create-account", methods=["GET", "POST"])
@admin_required
def create_account():
    if request.method == "POST":
        uid = request.form.get("user_id", "").strip()
        pwd = request.form.get("password", "").strip()
        role = request.form.get("role", "user")

        if not uid or not pwd:
            flash("User ID and Password are required.", "danger")
            return redirect(url_for("admin.create_account"))

        if role not in ("user", "mod"):
            flash("Invalid role.", "danger")
            return redirect(url_for("admin.create_account"))

        if User.query.filter_by(user_id=uid).first():
            flash("User ID already exists.", "danger")
            return redirect(url_for("admin.create_account"))

        u = User(user_id=uid, role=role, created_by_id=current_user.id)
        u.set_password(pwd)
        db.session.add(u)
        db.session.add(ActivityLog(
            user_id=current_user.id, action="create_account",
            details=f"Created {role} account: {uid}",
        ))
        db.session.commit()
        flash(f"{role.title()} account '{uid}' created successfully!", "success")
        return redirect(url_for("admin.users"))

    return render_template("admin/create_account.html")


@admin_bp.route("/ban-user/<int:uid>")
@admin_required
def ban_user(uid):
    u = User.query.get_or_404(uid)
    if u.role == "admin":
        flash("Cannot ban admin.", "danger")
        return redirect(url_for("admin.users"))
    u.is_banned = True
    db.session.add(ActivityLog(user_id=current_user.id, action="ban_user", details=f"Banned {u.user_id}"))
    db.session.commit()
    flash(f"User '{u.user_id}' has been banned.", "warning")
    return redirect(url_for("admin.users"))


@admin_bp.route("/unban-user/<int:uid>")
@admin_required
def unban_user(uid):
    u = User.query.get_or_404(uid)
    u.is_banned = False
    db.session.add(ActivityLog(user_id=current_user.id, action="unban_user", details=f"Unbanned {u.user_id}"))
    db.session.commit()
    flash(f"User '{u.user_id}' has been unbanned.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/delete-user/<int:uid>")
@admin_required
def delete_user(uid):
    u = User.query.get_or_404(uid)
    if u.role == "admin":
        flash("Cannot delete admin.", "danger")
        return redirect(url_for("admin.users"))
    # revoke all numbers
    Number.query.filter_by(allocated_to_id=u.id).update({"allocated_to_id": None, "allocated_by_id": None, "allocated_at": None})
    db.session.add(ActivityLog(user_id=current_user.id, action="delete_user", details=f"Deleted {u.user_id}"))
    db.session.delete(u)
    db.session.commit()
    flash(f"User '{u.user_id}' deleted.", "info")
    return redirect(url_for("admin.users"))


# ═══════════════════════════════════════════
#  NUMBER MANAGEMENT
# ═══════════════════════════════════════════
@admin_bp.route("/numbers")
@admin_required
def number_pool():
    country_filter = request.args.get("country", "all")
    q = Number.query
    if country_filter != "all":
        q = q.filter_by(country=country_filter)
    numbers = q.order_by(Number.created_at.desc()).limit(500).all()
    countries = db.session.query(Number.country).distinct().all()
    countries = sorted([c[0] for c in countries])
    batches = NumberBatch.query.order_by(NumberBatch.created_at.desc()).limit(20).all()

    # Stats
    total = Number.query.count()
    allocated = Number.query.filter(Number.allocated_to_id.isnot(None)).count()
    available = total - allocated

    return render_template("admin/number_pool.html",
        numbers=numbers, countries=countries,
        country_filter=country_filter, batches=batches,
        total=total, allocated=allocated, available=available,
        country_flags=COUNTRY_FLAGS,
    )


@admin_bp.route("/numbers/delete/<int:nid>", methods=["POST"])
@admin_required
def delete_number(nid):
    """Delete a single number from the pool and everywhere it's referenced."""
    number = Number.query.get_or_404(nid)
    phone = number.phone_number

    # Delete all SMS messages associated with this number
    SMS.query.filter_by(phone_number=phone).delete()

    # Remove the number itself
    db.session.delete(number)

    log = ActivityLog(
        user_id=current_user.id,
        action="Deleted number",
        details=f"Deleted {phone} and all associated SMS",
    )
    db.session.add(log)
    db.session.commit()

    flash(f"Number {phone} deleted successfully.", "success")
    return redirect(url_for("admin.number_pool"))


@admin_bp.route("/numbers/delete-bulk", methods=["POST"])
@admin_required
def delete_numbers_bulk():
    """Delete multiple selected numbers from the pool."""
    number_ids = request.form.getlist("number_ids")
    if not number_ids:
        flash("No numbers selected.", "warning")
        return redirect(url_for("admin.number_pool"))

    deleted = 0
    for nid in number_ids:
        number = Number.query.get(int(nid))
        if number:
            SMS.query.filter_by(phone_number=number.phone_number).delete()
            db.session.delete(number)
            deleted += 1

    db.session.commit()

    log = ActivityLog(
        user_id=current_user.id,
        action="Bulk deleted numbers",
        details=f"Deleted {deleted} numbers and their associated SMS",
    )
    db.session.add(log)
    db.session.commit()

    flash(f"Successfully deleted {deleted} numbers.", "success")
    return redirect(url_for("admin.number_pool"))


@admin_bp.route("/batch/delete/<int:bid>", methods=["POST"])
@admin_required
def delete_batch(bid):
    """Delete an uploaded batch – removes all its numbers and their SMS."""
    batch = NumberBatch.query.get_or_404(bid)
    fname = batch.filename or "(unknown)"
    country = batch.country

    # Delete SMS for every number in this batch
    numbers = Number.query.filter_by(batch_id=batch.id).all()
    deleted_nums = 0
    for n in numbers:
        SMS.query.filter_by(phone_number=n.phone_number).delete()
        db.session.delete(n)
        deleted_nums += 1

    db.session.delete(batch)
    db.session.add(ActivityLog(
        user_id=current_user.id,
        action="Deleted batch",
        details=f"Deleted batch '{fname}' ({country}) – {deleted_nums} numbers removed",
    ))
    db.session.commit()

    flash(f"Batch '{fname}' deleted – {deleted_nums} numbers removed.", "success")
    return redirect(url_for("admin.number_pool"))


@admin_bp.route("/upload-numbers", methods=["GET", "POST"])
@admin_required
def upload_numbers():
    if request.method == "POST":
        country = request.form.get("country", "").strip()
        file = request.files.get("file")

        if not country or not file:
            flash("Country and file are required.", "danger")
            return redirect(url_for("admin.upload_numbers"))

        # Read numbers from txt file
        content = file.read().decode("utf-8", errors="ignore")
        raw_numbers = [line.strip() for line in content.splitlines() if line.strip()]
        # remove duplicates
        raw_numbers = list(dict.fromkeys(raw_numbers))

        if not raw_numbers:
            flash("File is empty.", "danger")
            return redirect(url_for("admin.upload_numbers"))

        # Save batch
        batch = NumberBatch(
            country=country,
            filename=file.filename,
            uploaded_by_id=current_user.id,
            total_count=len(raw_numbers),
        )
        db.session.add(batch)
        db.session.flush()

        added = 0
        skipped = 0
        for num in raw_numbers:
            # clean the number
            clean = num.replace(" ", "").replace("-", "").replace("+", "")
            if not clean:
                continue
            if Number.query.filter_by(phone_number=clean).first():
                skipped += 1
                continue
            db.session.add(Number(phone_number=clean, country=country, batch_id=batch.id))
            added += 1

        db.session.add(ActivityLog(
            user_id=current_user.id, action="upload_numbers",
            details=f"Uploaded {added} numbers for {country} (skipped {skipped} duplicates)",
        ))
        db.session.commit()
        flash(f"Uploaded {added} numbers for {country}. {skipped} duplicates skipped.", "success")
        return redirect(url_for("admin.number_pool"))

    return render_template("admin/upload_numbers.html", countries=sorted(COUNTRY_FLAGS.keys()), country_flags=COUNTRY_FLAGS)


@admin_bp.route("/allocate-numbers", methods=["GET", "POST"])
@admin_required
def allocate_numbers():
    if request.method == "POST":
        target_user_id = request.form.get("user_id", type=int)
        country = request.form.get("country", "").strip()
        quantity = request.form.get("quantity", type=int, default=0)

        target_user = User.query.get(target_user_id) if target_user_id else None
        if not target_user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.allocate_numbers"))

        max_per_day = int(get_setting("max_numbers_per_user", "100"))

        # Check how many already allocated today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        already_today = Number.query.filter(
            Number.allocated_to_id == target_user.id,
            Number.allocated_at >= today_start,
        ).count()

        remaining = max_per_day - already_today
        if quantity > remaining:
            flash(f"Can only allocate {remaining} more numbers today (limit: {max_per_day}/day).", "warning")
            return redirect(url_for("admin.allocate_numbers"))

        # Get available numbers for the country
        available = Number.query.filter_by(
            country=country, allocated_to_id=None, is_active=True
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
            details=f"Allocated {len(available)} {country} numbers to {target_user.user_id}",
        ))
        db.session.commit()
        flash(f"Allocated {len(available)} {country} numbers to {target_user.user_id}.", "success")
        return redirect(url_for("admin.allocate_numbers"))

    users = User.query.filter(User.role.in_(["user", "mod"])).filter_by(is_banned=False).all()
    countries = db.session.query(Number.country).distinct().all()
    countries = sorted([c[0] for c in countries])
    # Count available per country
    country_avail = {}
    for c in countries:
        country_avail[c] = Number.query.filter_by(country=c, allocated_to_id=None, is_active=True).count()

    return render_template("admin/allocate_numbers.html",
        users=users, countries=countries,
        country_avail=country_avail, country_flags=COUNTRY_FLAGS,
    )


@admin_bp.route("/revoke-numbers/<int:uid>", methods=["POST"])
@admin_required
def revoke_numbers(uid):
    target = User.query.get_or_404(uid)
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
        details=f"Revoked {nums} numbers from {target.user_id}" + (f" ({country})" if country else ""),
    ))
    db.session.commit()
    flash(f"Revoked {nums} numbers from {target.user_id}.", "info")
    return redirect(url_for("admin.users"))


# ═══════════════════════════════════════════
#  SMS STATS
# ═══════════════════════════════════════════
@admin_bp.route("/sms-stats")
@admin_required
def sms_stats():
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    q = SMS.query
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(SMS.received_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(SMS.received_at < dt_to)
        except ValueError:
            pass
    sms_list = q.order_by(SMS.received_at.desc()).limit(500).all()

    # Stats
    total_all = SMS.query.count()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = SMS.query.filter(SMS.received_at >= today_start).count()

    # Per-service breakdown
    from sqlalchemy import func
    service_stats = db.session.query(SMS.service, func.count(SMS.id)).group_by(SMS.service).all()

    return render_template("admin/sms_stats.html",
        sms_list=sms_list, date_from=date_from, date_to=date_to,
        total_all=total_all, today_count=today_count,
        service_stats=service_stats,
    )


# ═══════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════
@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        otp_rate = request.form.get("otp_rate", "0.005")
        min_withdrawal = request.form.get("min_withdrawal", "5")
        max_numbers = request.form.get("max_numbers_per_user", "100")
        withdrawal_day = request.form.get("withdrawal_day", "Tuesday")

        set_setting("otp_rate", otp_rate)
        set_setting("min_withdrawal", min_withdrawal)
        set_setting("max_numbers_per_user", max_numbers)
        set_setting("withdrawal_day", withdrawal_day)

        db.session.add(ActivityLog(
            user_id=current_user.id, action="update_settings",
            details=f"OTP rate={otp_rate}, min withdrawal={min_withdrawal}, "
                    f"max numbers/user={max_numbers}, withdrawal day={withdrawal_day}",
        ))
        db.session.commit()
        flash("Settings updated.", "success")
        return redirect(url_for("admin.settings"))

    return render_template("admin/settings.html",
        otp_rate=get_setting("otp_rate", "0.005"),
        min_withdrawal=get_setting("min_withdrawal", "5"),
        max_numbers_per_user=get_setting("max_numbers_per_user", "100"),
        withdrawal_day=get_setting("withdrawal_day", "Tuesday"),
    )


# ═══════════════════════════════════════════
#  WITHDRAWALS
# ═══════════════════════════════════════════
@admin_bp.route("/withdrawals")
@admin_required
def withdrawals():
    status_filter = request.args.get("status", "pending")
    q = Withdrawal.query
    if status_filter != "all":
        q = q.filter_by(status=status_filter)
    wds = q.order_by(Withdrawal.requested_at.desc()).all()
    return render_template("admin/withdrawals.html", withdrawals=wds, status_filter=status_filter)


@admin_bp.route("/withdrawal-paid/<int:wid>")
@admin_required
def withdrawal_paid(wid):
    w = Withdrawal.query.get_or_404(wid)
    if w.status != "pending":
        flash("Withdrawal already processed.", "warning")
        return redirect(url_for("admin.withdrawals"))

    w.status = "paid"
    w.paid_at = datetime.utcnow()

    # Debit user balance
    user = User.query.get(w.user_id)
    if user:
        user.balance = max(0, (user.balance or 0) - w.amount)

    db.session.add(ActivityLog(
        user_id=current_user.id, action="mark_paid",
        details=f"Paid withdrawal #{w.id} (${w.amount:.4f}) to {user.user_id if user else '?'}",
    ))
    db.session.commit()
    flash(f"Withdrawal #{w.id} marked as paid.", "success")
    return redirect(url_for("admin.withdrawals"))


@admin_bp.route("/withdrawal-reject/<int:wid>")
@admin_required
def withdrawal_reject(wid):
    w = Withdrawal.query.get_or_404(wid)
    if w.status != "pending":
        flash("Withdrawal already processed.", "warning")
        return redirect(url_for("admin.withdrawals"))
    w.status = "rejected"
    db.session.add(ActivityLog(
        user_id=current_user.id, action="reject_withdrawal",
        details=f"Rejected withdrawal #{w.id}",
    ))
    db.session.commit()
    flash(f"Withdrawal #{w.id} rejected.", "info")
    return redirect(url_for("admin.withdrawals"))


# ═══════════════════════════════════════════
#  ANNOUNCEMENTS
# ═══════════════════════════════════════════
@admin_bp.route("/announcements")
@admin_required
def announcements():
    all_ann = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements.html", announcements=all_ann)


@admin_bp.route("/announcement/create", methods=["GET", "POST"])
@admin_required
def create_announcement():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        variant = request.form.get("variant", "info")
        if not title or not body:
            flash("Title and body are required.", "danger")
            return redirect(url_for("admin.create_announcement"))

        ann = Announcement(
            title=title, body=body, variant=variant,
            is_active=True, created_by_id=current_user.id,
        )
        db.session.add(ann)
        db.session.add(ActivityLog(
            user_id=current_user.id, action="create_announcement",
            details=f"Created announcement: {title}",
        ))
        db.session.commit()
        flash("Announcement created.", "success")
        return redirect(url_for("admin.announcements"))
    return render_template("admin/announcement_form.html", announcement=None)


@admin_bp.route("/announcement/edit/<int:aid>", methods=["GET", "POST"])
@admin_required
def edit_announcement(aid):
    ann = Announcement.query.get_or_404(aid)
    if request.method == "POST":
        ann.title = request.form.get("title", "").strip()
        ann.body = request.form.get("body", "").strip()
        ann.variant = request.form.get("variant", "info")
        ann.is_active = "is_active" in request.form
        if not ann.title or not ann.body:
            flash("Title and body are required.", "danger")
            return redirect(url_for("admin.edit_announcement", aid=aid))

        db.session.add(ActivityLog(
            user_id=current_user.id, action="edit_announcement",
            details=f"Edited announcement #{aid}: {ann.title}",
        ))
        db.session.commit()
        flash("Announcement updated.", "success")
        return redirect(url_for("admin.announcements"))
    return render_template("admin/announcement_form.html", announcement=ann)


@admin_bp.route("/announcement/delete/<int:aid>")
@admin_required
def delete_announcement(aid):
    ann = Announcement.query.get_or_404(aid)
    db.session.add(ActivityLog(
        user_id=current_user.id, action="delete_announcement",
        details=f"Deleted announcement: {ann.title}",
    ))
    db.session.delete(ann)
    db.session.commit()
    flash("Announcement deleted.", "success")
    return redirect(url_for("admin.announcements"))


@admin_bp.route("/announcement/toggle/<int:aid>")
@admin_required
def toggle_announcement(aid):
    ann = Announcement.query.get_or_404(aid)
    ann.is_active = not ann.is_active
    db.session.commit()
    status = "enabled" if ann.is_active else "disabled"
    flash(f"Announcement {status}.", "info")
    return redirect(url_for("admin.announcements"))


# ═══════════════════════════════════════════
#  TEST NUMBERS MANAGEMENT
# ═══════════════════════════════════════════
@admin_bp.route("/test-numbers")
@admin_required
def test_numbers():
    """View all test numbers, auto-clean expired ones."""
    # Clean expired test numbers first
    expired = TestNumber.query.filter(TestNumber.expires_at <= datetime.utcnow()).all()
    for tn in expired:
        # Also remove associated test SMS
        TestSMS.query.filter_by(phone_number=tn.phone_number).delete()
        db.session.delete(tn)
    if expired:
        db.session.commit()

    numbers = TestNumber.query.order_by(TestNumber.created_at.desc()).all()
    countries = sorted(set(n.country for n in numbers))
    return render_template("admin/test_numbers.html",
        numbers=numbers, countries=countries, country_flags=COUNTRY_FLAGS,
        now=datetime.utcnow(),
    )


@admin_bp.route("/test-numbers/add", methods=["POST"])
@admin_required
def add_test_numbers():
    """Add test numbers by pasting or uploading txt files."""
    country = request.form.get("country", "").strip()
    if not country:
        flash("Country is required.", "danger")
        return redirect(url_for("admin.test_numbers"))

    expires_at = datetime.utcnow() + timedelta(hours=23)
    added = 0
    skipped = 0

    # Handle pasted numbers
    pasted = request.form.get("pasted_numbers", "").strip()
    if pasted:
        raw = [line.strip() for line in pasted.splitlines() if line.strip()]
        raw = list(dict.fromkeys(raw))  # dedup
        for num in raw:
            clean = num.replace(" ", "").replace("-", "").replace("+", "")
            if not clean:
                continue
            if TestNumber.query.filter_by(phone_number=clean).first():
                skipped += 1
                continue
            tn = TestNumber(
                phone_number=clean, country=country,
                filename="pasted", uploaded_by_id=current_user.id,
                expires_at=expires_at,
            )
            db.session.add(tn)
            added += 1

    # Handle file uploads (multiple)
    files = request.files.getlist("files")
    for f in files:
        if not f or not f.filename:
            continue
        content = f.read().decode("utf-8", errors="ignore")
        raw = [line.strip() for line in content.splitlines() if line.strip()]
        raw = list(dict.fromkeys(raw))
        for num in raw:
            clean = num.replace(" ", "").replace("-", "").replace("+", "")
            if not clean:
                continue
            if TestNumber.query.filter_by(phone_number=clean).first():
                skipped += 1
                continue
            tn = TestNumber(
                phone_number=clean, country=country,
                filename=f.filename, uploaded_by_id=current_user.id,
                expires_at=expires_at,
            )
            db.session.add(tn)
            added += 1

    db.session.commit()

    db.session.add(ActivityLog(
        user_id=current_user.id, action="add_test_numbers",
        details=f"Added {added} test numbers for {country} (skipped {skipped} dupes)",
    ))
    db.session.commit()

    flash(f"Added {added} test numbers for {country}. Skipped {skipped} duplicates. They expire in 23 hours.", "success")
    return redirect(url_for("admin.test_numbers"))


@admin_bp.route("/test-numbers/delete/<int:tid>", methods=["POST"])
@admin_required
def delete_test_number(tid):
    tn = TestNumber.query.get_or_404(tid)
    phone = tn.phone_number
    TestSMS.query.filter_by(phone_number=phone).delete()
    db.session.delete(tn)
    db.session.add(ActivityLog(
        user_id=current_user.id, action="delete_test_number",
        details=f"Deleted test number {phone}",
    ))
    db.session.commit()
    flash(f"Test number {phone} deleted.", "success")
    return redirect(url_for("admin.test_numbers"))


@admin_bp.route("/test-numbers/delete-all", methods=["POST"])
@admin_required
def delete_all_test_numbers():
    count = TestNumber.query.count()
    TestSMS.query.delete()
    TestNumber.query.delete()
    db.session.add(ActivityLog(
        user_id=current_user.id, action="delete_all_test_numbers",
        details=f"Deleted all {count} test numbers and their SMS",
    ))
    db.session.commit()
    flash(f"Deleted all {count} test numbers.", "success")
    return redirect(url_for("admin.test_numbers"))


# ═══════════════════════════════════════════
#  ACTIVITY LOG
# ═══════════════════════════════════════════
@admin_bp.route("/activity-log")
@admin_required
def activity_log():
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    return render_template("admin/activity_log.html", logs=logs)


# ═══════════════════════════════════════════
#  OTP FETCHER  (NumberPanel settings + test)
# ═══════════════════════════════════════════
@admin_bp.route("/otp-fetcher", methods=["GET", "POST"])
@admin_required
def otp_fetcher():
    """Manage NumberPanel login credentials and test SMS fetching."""
    if request.method == "POST":
        np_username = request.form.get("np_username", "").strip()
        np_password = request.form.get("np_password", "").strip()
        np_login_url = request.form.get("np_login_url", "").strip()
        np_sms_url = request.form.get("np_sms_url", "").strip()
        np_poll_interval = request.form.get("np_poll_interval", "30").strip()
        np_enabled = request.form.get("np_enabled", "off")

        set_setting("np_username", np_username)
        set_setting("np_password", np_password)
        set_setting("np_login_url", np_login_url)
        set_setting("np_sms_url", np_sms_url)
        set_setting("np_poll_interval", np_poll_interval)
        set_setting("np_enabled", "1" if np_enabled == "on" else "0")

        db.session.add(ActivityLog(
            user_id=current_user.id, action="update_np_settings",
            details=f"NumberPanel: user={np_username}, login={np_login_url}, poll={np_poll_interval}s",
        ))
        db.session.commit()
        flash("NumberPanel settings updated.", "success")
        return redirect(url_for("admin.otp_fetcher"))

    # GET: load current values from DB, fall back to config
    cfg = current_app.config
    return render_template("admin/otp_fetcher.html",
        np_username=get_setting("np_username", cfg.get("NP_USERNAME", "")),
        np_password=get_setting("np_password", cfg.get("NP_PASSWORD", "")),
        np_login_url=get_setting("np_login_url", cfg.get("NP_LOGIN_URL", "")),
        np_sms_url=get_setting("np_sms_url", cfg.get("NP_SMS_URL", "")),
        np_poll_interval=get_setting("np_poll_interval", str(cfg.get("NP_POLL_INTERVAL", 30))),
        np_enabled=get_setting("np_enabled", "1"),
    )


@admin_bp.route("/otp-fetcher/test", methods=["POST"])
@admin_required
def otp_fetcher_test():
    """One-shot test: login to NumberPanel via headless browser and fetch latest SMS."""
    import re as _re
    from playwright.sync_api import sync_playwright
    from numberpanel_poller import solve_math_captcha, _strip_html

    cfg = current_app.config
    login_url = get_setting("np_login_url", cfg.get("NP_LOGIN_URL", ""))
    sms_url = get_setting("np_sms_url", cfg.get("NP_SMS_URL", ""))
    username = get_setting("np_username", cfg.get("NP_USERNAME", ""))
    password = get_setting("np_password", cfg.get("NP_PASSWORD", ""))

    result_msg = ""
    sms_rows = []

    pw = None
    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page()

        for attempt in range(5):
            try:
                page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                html = page.content()
                captcha_answer = solve_math_captcha(html)
                if not captcha_answer:
                    result_msg = f"Attempt {attempt+1}: Could not solve captcha"
                    continue

                page.fill('input[name="username"]', username)
                page.fill('input[name="password"]', password)
                page.fill('input[name="capt"]', captcha_answer)
                page.evaluate("document.querySelector('form').submit()")
                import time as _time; _time.sleep(10)

                if "/login" in page.url.lower().split("?")[0]:
                    result_msg = f"Attempt {attempt+1}: Login rejected"
                    import time; time.sleep(1)
                    continue

                # Logged in – intercept AJAX on SMS page
                ajax_data = {}

                def handle_response(response):
                    try:
                        if "data_smscdr" in response.url or "sesskey" in response.url:
                            if response.status == 200:
                                try:
                                    ajax_data["json"] = response.json()
                                except Exception:
                                    pass
                    except Exception:
                        pass

                page.on("response", handle_response)
                page.goto(sms_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                page.remove_listener("response", handle_response)

                rows = []
                if "json" in ajax_data:
                    rows = ajax_data["json"].get("aaData") or ajax_data["json"].get("data") or []
                else:
                    # Fallback: extract sAjaxSource and fetch via browser
                    html2 = page.content()
                    match = _re.search(r'"sAjaxSource"\s*:\s*"([^"]+)"', html2)
                    if match:
                        ajax_path = match.group(1)
                        base = sms_url.rsplit("/", 1)[0]
                        ajax_url = f"{base}/{ajax_path}"
                        resp = page.evaluate(f"""
                            async () => {{
                                const r = await fetch("{ajax_url}", {{
                                    headers: {{"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}}
                                }});
                                return await r.json();
                            }}
                        """)
                        rows = resp.get("aaData") or resp.get("data") or []

                for row in rows:
                    if not isinstance(row, list) or len(row) < 6:
                        continue
                    date_s = _strip_html(str(row[0])).strip()
                    if "," in date_s or "NAN" in date_s.upper() or "%" in date_s:
                        continue
                    sms_rows.append({
                        "date": date_s,
                        "country": _strip_html(str(row[1])).strip(),
                        "number": _strip_html(str(row[2])).strip(),
                        "cli": _strip_html(str(row[3])).strip(),
                        "sms": _strip_html(str(row[5])).strip(),
                    })

                result_msg = f"Login OK – fetched {len(sms_rows)} SMS messages"
                break

            except Exception as e:
                result_msg = f"Attempt {attempt+1}: {e}"
                import time; time.sleep(1)

    except Exception as e:
        result_msg = f"Browser error: {e}"
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass

    db.session.add(ActivityLog(
        user_id=current_user.id, action="np_test_fetch",
        details=result_msg,
    ))
    db.session.commit()

    return render_template("admin/otp_fetcher.html",
        np_username=get_setting("np_username", cfg.get("NP_USERNAME", "")),
        np_password=get_setting("np_password", cfg.get("NP_PASSWORD", "")),
        np_login_url=get_setting("np_login_url", cfg.get("NP_LOGIN_URL", "")),
        np_sms_url=get_setting("np_sms_url", cfg.get("NP_SMS_URL", "")),
        np_poll_interval=get_setting("np_poll_interval", str(cfg.get("NP_POLL_INTERVAL", 30))),
        np_enabled=get_setting("np_enabled", "1"),
        test_result=result_msg,
        test_sms=sms_rows,
    )
