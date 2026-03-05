import os
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from functools import wraps
from models import (
    db, User, Number, NumberBatch, SMS, Withdrawal, Setting,
    ActivityLog, Announcement, TestNumber, TestSMS, get_setting, set_setting,
    AutoRevokeSchedule,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role not in ("admin", "super_admin"):
            flash("Access denied.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    """Only the primary super-admin (idledev) can access this."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "super_admin":
            flash("Only the primary admin can do this.", "danger")
            return redirect(url_for("admin.dashboard"))
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
    # Super admin sees all users including other admins; regular admin sees mods+users only
    if current_user.role == "super_admin":
        q = User.query.filter(User.id != current_user.id)  # hide self
    else:
        q = User.query.filter(User.role.notin_(["admin", "super_admin"]))
    if role_filter == "mod":
        q = q.filter_by(role="mod")
    elif role_filter == "user":
        q = q.filter_by(role="user")
    elif role_filter == "admin":
        q = q.filter_by(role="admin")
    all_users = q.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users, role_filter=role_filter,
        is_super_admin=current_user.role == "super_admin",
    )


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

        # Only super_admin can create admin accounts
        if role == "admin":
            if current_user.role != "super_admin":
                flash("Only the primary admin can create admin accounts.", "danger")
                return redirect(url_for("admin.create_account"))
        elif role not in ("user", "mod"):
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

    return render_template("admin/create_account.html",
        is_super_admin=current_user.role == "super_admin",
    )


@admin_bp.route("/ban-user/<int:uid>")
@admin_required
def ban_user(uid):
    u = User.query.get_or_404(uid)
    if u.role == "super_admin":
        flash("Cannot ban the primary admin.", "danger")
        return redirect(url_for("admin.users"))
    if u.role == "admin" and current_user.role != "super_admin":
        flash("Only the primary admin can ban other admins.", "danger")
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
    if u.role == "super_admin":
        flash("Cannot delete the primary admin.", "danger")
        return redirect(url_for("admin.users"))
    if u.role == "admin" and current_user.role != "super_admin":
        flash("Only the primary admin can delete other admins.", "danger")
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

    # Users with allocated numbers (for Users tab)
    allocated_users_raw = (
        db.session.query(
            User.id, User.user_id, User.role,
            db.func.count(Number.id).label("num_count"),
            db.func.min(Number.allocated_at).label("first_allocated"),
        )
        .join(Number, Number.allocated_to_id == User.id)
        .group_by(User.id)
        .order_by(db.func.count(Number.id).desc())
        .all()
    )
    allocated_users = []
    for row in allocated_users_raw:
        allocated_users.append({
            "id": row.id,
            "user_id": row.user_id,
            "role": row.role,
            "num_count": row.num_count,
            "first_allocated": row.first_allocated,
        })

    # Active auto-revoke schedule
    active_auto_revoke = AutoRevokeSchedule.query.filter_by(is_executed=False).order_by(
        AutoRevokeSchedule.revoke_at.asc()
    ).first()

    # All users with balance & number count (for All Users tab)
    all_users_raw = (
        db.session.query(
            User.id, User.user_id, User.role, User.balance, User.is_banned,
            User.created_at,
            db.func.count(Number.id).label("num_count"),
        )
        .outerjoin(Number, Number.allocated_to_id == User.id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
        .all()
    )
    all_users_list = []
    for row in all_users_raw:
        all_users_list.append({
            "id": row.id,
            "user_id": row.user_id,
            "role": row.role,
            "balance": row.balance or 0.0,
            "is_banned": row.is_banned,
            "created_at": row.created_at,
            "num_count": row.num_count,
        })

    return render_template("admin/number_pool.html",
        numbers=numbers, countries=countries,
        country_filter=country_filter, batches=batches,
        total=total, allocated=allocated, available=available,
        country_flags=COUNTRY_FLAGS,
        allocated_users=allocated_users,
        active_auto_revoke=active_auto_revoke,
        all_users_list=all_users_list,
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
    referrer = request.form.get("referrer", "")
    if referrer == "number_pool":
        return redirect(url_for("admin.number_pool"))
    return redirect(url_for("admin.users"))


@admin_bp.route("/revoke-numbers-bulk", methods=["POST"])
@admin_required
def revoke_numbers_bulk():
    """Revoke numbers from multiple selected users at once."""
    user_ids = request.form.getlist("user_ids")
    if not user_ids:
        flash("No users selected.", "warning")
        return redirect(url_for("admin.number_pool"))

    total_revoked = 0
    user_names = []
    for uid in user_ids:
        uid = int(uid)
        user = User.query.get(uid)
        if user:
            nums = Number.query.filter_by(allocated_to_id=uid).update(
                {"allocated_to_id": None, "allocated_by_id": None, "allocated_at": None}
            )
            total_revoked += nums
            user_names.append(user.user_id)

    db.session.add(ActivityLog(
        user_id=current_user.id, action="bulk_revoke_numbers",
        details=f"Revoked {total_revoked} numbers from {len(user_names)} users: {', '.join(user_names)}",
    ))
    db.session.commit()
    flash(f"Revoked {total_revoked} numbers from {len(user_names)} users.", "info")
    return redirect(url_for("admin.number_pool"))


@admin_bp.route("/set-auto-revoke", methods=["POST"])
@admin_required
def set_auto_revoke():
    """Schedule an auto-revoke for all users after N hours."""
    hours = request.form.get("hours", type=float)
    if not hours or hours <= 0:
        flash("Please enter a valid number of hours.", "danger")
        return redirect(url_for("admin.number_pool"))

    revoke_at = datetime.utcnow() + timedelta(hours=hours)

    # Cancel any existing pending auto-revoke
    AutoRevokeSchedule.query.filter_by(is_executed=False).delete()

    schedule = AutoRevokeSchedule(
        created_by_id=current_user.id,
        revoke_at=revoke_at,
    )
    db.session.add(schedule)
    db.session.add(ActivityLog(
        user_id=current_user.id, action="set_auto_revoke",
        details=f"Scheduled auto-revoke in {hours}h (fires at {revoke_at.strftime('%Y-%m-%d %H:%M UTC')})",
    ))
    db.session.commit()
    flash(f"Auto-revoke scheduled in {hours} hours.", "success")
    return redirect(url_for("admin.number_pool"))


@admin_bp.route("/cancel-auto-revoke", methods=["POST"])
@admin_required
def cancel_auto_revoke():
    """Cancel any pending auto-revoke schedule."""
    deleted = AutoRevokeSchedule.query.filter_by(is_executed=False).delete()
    db.session.add(ActivityLog(
        user_id=current_user.id, action="cancel_auto_revoke",
        details=f"Cancelled {deleted} pending auto-revoke schedule(s)",
    ))
    db.session.commit()
    flash("Auto-revoke cancelled.", "info")
    return redirect(url_for("admin.number_pool"))


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
        maintenance_mode=get_setting("maintenance_mode", "off"),
        maintenance_message=get_setting("maintenance_message", "We'll be back shortly."),
    )


@admin_bp.route("/toggle-maintenance", methods=["POST"])
@admin_required
def toggle_maintenance():
    """Toggle maintenance mode on/off with a custom banner message."""
    action = request.form.get("action", "off")  # "on" or "off"
    message = request.form.get("maintenance_message", "We'll be back shortly.").strip()

    if action == "on":
        set_setting("maintenance_mode", "on")
        set_setting("maintenance_message", message or "We'll be back shortly.")
        db.session.add(ActivityLog(
            user_id=current_user.id, action="maintenance_on",
            details=f"Enabled maintenance mode: {message}",
        ))
        db.session.commit()
        flash("Maintenance mode ENABLED. Users will see the maintenance page.", "warning")
    else:
        set_setting("maintenance_mode", "off")
        db.session.add(ActivityLog(
            user_id=current_user.id, action="maintenance_off",
            details="Disabled maintenance mode",
        ))
        db.session.commit()
        flash("Maintenance mode DISABLED. Site is back to normal.", "success")

    return redirect(url_for("admin.settings"))


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
def _load_api_tokens() -> list[dict]:
    """Load API tokens from settings as a JSON list of {name, token} dicts."""
    import json
    raw = get_setting("np_api_tokens", "")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    # Fallback: migrate single token if it exists
    single = get_setting("np_api_token", "")
    if single:
        return [{"name": "Default", "token": single}]
    cfg_token = current_app.config.get("NP_API_TOKEN", "")
    if cfg_token:
        return [{"name": "Default", "token": cfg_token}]
    return []


def _save_api_tokens(tokens: list[dict]):
    import json
    set_setting("np_api_tokens", json.dumps(tokens))


@admin_bp.route("/otp-fetcher", methods=["GET", "POST"])
@admin_required
def otp_fetcher():
    """Manage NumberPanel CR-API settings."""
    if request.method == "POST":
        np_api_url = request.form.get("np_api_url", "").strip()
        np_max_records = request.form.get("np_max_records", "10").strip()
        np_poll_interval = request.form.get("np_poll_interval", "10").strip()
        np_enabled = request.form.get("np_enabled", "off")

        set_setting("np_api_url", np_api_url)
        set_setting("np_max_records", np_max_records)
        set_setting("np_poll_interval", np_poll_interval)
        set_setting("np_enabled", "1" if np_enabled == "on" else "0")

        db.session.add(ActivityLog(
            user_id=current_user.id, action="update_np_settings",
            details=f"NumberPanel API: url={np_api_url}, records={np_max_records}, poll={np_poll_interval}s",
        ))
        db.session.commit()
        flash("NumberPanel API settings updated.", "success")
        return redirect(url_for("admin.otp_fetcher"))

    # GET: load current values from DB, fall back to config
    cfg = current_app.config
    return render_template("admin/otp_fetcher.html",
        np_api_url=get_setting("np_api_url", cfg.get("NP_API_URL", "")),
        np_api_tokens=_load_api_tokens(),
        np_max_records=get_setting("np_max_records", str(cfg.get("NP_MAX_RECORDS", 10))),
        np_poll_interval=get_setting("np_poll_interval", str(cfg.get("NP_POLL_INTERVAL", 10))),
        np_enabled=get_setting("np_enabled", "1"),
    )


@admin_bp.route("/otp-fetcher/add-token", methods=["POST"])
@admin_required
def otp_fetcher_add_token():
    """Add a new API token."""
    name = request.form.get("token_name", "").strip() or "Unnamed"
    token = request.form.get("token_value", "").strip()
    if not token:
        flash("Token cannot be empty.", "danger")
        return redirect(url_for("admin.otp_fetcher"))

    tokens = _load_api_tokens()
    tokens.append({"name": name, "token": token})
    _save_api_tokens(tokens)

    db.session.add(ActivityLog(
        user_id=current_user.id, action="add_api_token",
        details=f"Added API token: {name}",
    ))
    db.session.commit()
    flash(f"API token '{name}' added.", "success")
    return redirect(url_for("admin.otp_fetcher"))


@admin_bp.route("/otp-fetcher/remove-token/<int:idx>", methods=["POST"])
@admin_required
def otp_fetcher_remove_token(idx):
    """Remove an API token by index."""
    tokens = _load_api_tokens()
    if 0 <= idx < len(tokens):
        removed = tokens.pop(idx)
        _save_api_tokens(tokens)
        db.session.add(ActivityLog(
            user_id=current_user.id, action="remove_api_token",
            details=f"Removed API token: {removed.get('name', '?')}",
        ))
        db.session.commit()
        flash(f"Token '{removed.get('name', '?')}' removed.", "info")
    return redirect(url_for("admin.otp_fetcher"))


@admin_bp.route("/otp-fetcher/test", methods=["POST"])
@admin_required
def otp_fetcher_test():
    """One-shot test: call the CR-API with all tokens and show latest SMS."""
    import hashlib
    from datetime import datetime as _dt, timedelta, timezone
    import httpx
    from numberpanel_poller import detect_service

    cfg = current_app.config
    api_url = get_setting("np_api_url", cfg.get("NP_API_URL", ""))
    tokens = _load_api_tokens()
    max_records = int(get_setting("np_max_records", str(cfg.get("NP_MAX_RECORDS", 10))))

    result_msg = ""
    sms_rows = []

    if not tokens:
        result_msg = "No API tokens configured"
    else:
        total_fetched = 0
        errors = []
        for t in tokens:
            try:
                now = _dt.now(timezone.utc)
                dt2 = now.strftime("%Y-%m-%d %H:%M:%S")
                dt1 = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

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
                    errors.append(f"{t['name']}: unexpected response")
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
                    detected = detect_service(sms_text)
                    if detected == "Unknown":
                        detected = service
                    sms_rows.append({
                        "date": date_str,
                        "service": detected,
                        "number": phone,
                        "sms": sms_text,
                        "token_name": t["name"],
                    })
                total_fetched += len(data)

            except httpx.HTTPStatusError as e:
                errors.append(f"{t['name']}: HTTP {e.response.status_code}")
            except Exception as e:
                errors.append(f"{t['name']}: {e}")

        result_msg = f"API OK – fetched {len(sms_rows)} SMS from {len(tokens)} token(s)"
        if errors:
            result_msg += f" | Errors: {'; '.join(errors)}"

    db.session.add(ActivityLog(
        user_id=current_user.id, action="np_test_fetch",
        details=result_msg,
    ))
    db.session.commit()

    return render_template("admin/otp_fetcher.html",
        np_api_url=get_setting("np_api_url", cfg.get("NP_API_URL", "")),
        np_api_tokens=_load_api_tokens(),
        np_max_records=get_setting("np_max_records", str(cfg.get("NP_MAX_RECORDS", 10))),
        np_poll_interval=get_setting("np_poll_interval", str(cfg.get("NP_POLL_INTERVAL", 10))),
        np_enabled=get_setting("np_enabled", "1"),
        test_result=result_msg,
        test_sms=sms_rows,
    )

