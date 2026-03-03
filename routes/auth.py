from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, ActivityLog

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == "POST":
        uid = request.form.get("user_id", "").strip()
        pwd = request.form.get("password", "").strip()

        user = User.query.filter_by(user_id=uid).first()
        if user and user.check_password(pwd):
            if user.is_banned:
                flash("Your account has been suspended.", "danger")
                return redirect(url_for("auth.login"))

            login_user(user, remember=True)
            db.session.add(ActivityLog(user_id=user.id, action="login", details=f"Logged in"))
            db.session.commit()
            return _redirect_by_role(user)

        flash("Invalid User ID or Password.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    db.session.add(ActivityLog(user_id=current_user.id, action="logout", details="Logged out"))
    db.session.commit()
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))


def _redirect_by_role(user):
    if user.role == "admin":
        return redirect(url_for("admin.dashboard"))
    elif user.role == "mod":
        return redirect(url_for("mod.dashboard"))
    return redirect(url_for("user.dashboard"))
