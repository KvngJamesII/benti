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
        _seed_admin(app)
        init_default_settings()

    return app


def _seed_admin(app):
    """Create the admin user on first run."""
    admin = User.query.filter_by(user_id=app.config["ADMIN_USER_ID"]).first()
    if not admin:
        admin = User(
            user_id=app.config["ADMIN_USER_ID"],
            role="admin",
        )
        admin.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.commit()
        print(f"[SEED] Admin account created: {app.config['ADMIN_USER_ID']}")


# ──────────────────────────────────────────
if __name__ == "__main__":
    app = create_app()

    # Start SMS poller in background (IVAS)
    from sms_poller import SMSPoller
    poller = SMSPoller(app)
    poller.start()

    # Start NumberPanel poller in background
    from numberpanel_poller import NumberPanelPoller
    np_poller = NumberPanelPoller(app)
    np_poller.start()

    print("=" * 50)
    print("  EDEN SMS SERVICES")
    print("  http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
