"""
Eden SMS Services – entry point
Run with:  python run.py
"""
import os
from flask import Flask
from flask_login import LoginManager
from config import Config
from models import db, User, init_default_settings

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure folders exist
    os.makedirs(os.path.join(app.root_path, "data"), exist_ok=True)
    os.makedirs(os.path.join(app.root_path, "uploads"), exist_ok=True)

    # Extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Blueprints
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.mod import mod_bp
    from routes.user import user_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(mod_bp)
    app.register_blueprint(user_bp)

    # Create tables + seed admin
    with app.app_context():
        db.create_all()
        _migrate_columns()
        _seed_admin(app)
        init_default_settings()

    # Start background pollers (works under both gunicorn and python run.py)
    _start_pollers(app)

    return app


_pollers_started = False


def _migrate_columns():
    """Add new columns to existing SQLite tables (no-op if they already exist)."""
    import sqlite3
    db_path = db.engine.url.database
    if not db_path:
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    migrations = [
        ("users", "binance_uid", "TEXT"),
        ("users", "payment_method", "TEXT DEFAULT 'usdt_bep20'"),
        ("withdrawals", "payment_method", "TEXT DEFAULT 'usdt_bep20'"),
    ]
    for table, col, col_type in migrations:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            print(f"[MIGRATE] Added {table}.{col}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()


def _start_pollers(app):
    """Start SMS pollers once (gunicorn may fork multiple workers)."""
    global _pollers_started
    if _pollers_started:
        return
    _pollers_started = True

    from sms_poller import SMSPoller
    poller = SMSPoller(app)
    poller.start()

    from numberpanel_poller import NumberPanelPoller
    np_poller = NumberPanelPoller(app)
    np_poller.start()

    from auto_revoke_worker import AutoRevokeWorker
    ar_worker = AutoRevokeWorker(app)
    ar_worker.start()


def _seed_admin(app):
    """Create or migrate the primary super-admin account."""
    target_uid = app.config["ADMIN_USER_ID"]  # "idledev"
    target_pwd = app.config["ADMIN_PASSWORD"]  # "isr999"

    # Check if the target admin already exists
    admin = User.query.filter_by(user_id=target_uid).first()
    if admin:
        # Ensure it's super_admin role
        if admin.role != "super_admin":
            admin.role = "super_admin"
            db.session.commit()
            print(f"[SEED] Promoted {target_uid} to super_admin")
        return

    # Migrate old admin (200715) to new ID if it exists
    old_admin = User.query.filter_by(user_id="200715", role="admin").first()
    if old_admin:
        old_admin.user_id = target_uid
        old_admin.role = "super_admin"
        old_admin.set_password(target_pwd)
        db.session.commit()
        print(f"[SEED] Migrated admin 200715 -> {target_uid} (super_admin)")
        return

    # Also check if any super_admin already exists
    existing_super = User.query.filter_by(role="super_admin").first()
    if existing_super:
        return

    # Fresh install – create super_admin
    admin = User(
        user_id=target_uid,
        role="super_admin",
    )
    admin.set_password(target_pwd)
    db.session.add(admin)
    db.session.commit()
    print(f"[SEED] Super-admin account created: {target_uid}")


# ──────────────────────────────────────────
if __name__ == "__main__":
    app = create_app()

    print("=" * 50)
    print("  EDEN SMS SERVICES")
    print("  http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
