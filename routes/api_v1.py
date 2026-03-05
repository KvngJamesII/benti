"""
Eden SMS – Public REST API (v1)
Authenticated via ApiToken (X-API-Key header or api_key query param).
"""
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify
from models import db, ApiToken, SMS, Number, detect_country_from_phone

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


# ──────────────────────────────────────────
#  AUTH DECORATOR
# ──────────────────────────────────────────
def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not key:
            return jsonify(ok=False, error="Invalid or missing API key"), 401
        token = ApiToken.query.filter_by(token=key).first()
        if not token:
            return jsonify(ok=False, error="Invalid or missing API key"), 401
        if not token.is_active:
            return jsonify(ok=False, error="Token revoked"), 403
        if token.user.is_banned:
            return jsonify(ok=False, error="Account suspended"), 403
        # Update last-used timestamp
        token.last_used_at = datetime.utcnow()
        db.session.commit()
        # Attach user to kwargs
        kwargs["api_user"] = token.user
        return f(*args, **kwargs)
    return decorated


def _sms_to_dict(sms):
    detected = detect_country_from_phone(sms.phone_number)
    country = detected if detected else (sms.country or "Unknown")
    return {
        "id": sms.id,
        "service": sms.service,
        "phone": sms.phone_number,
        "country": country,
        "message": sms.message,
        "rate": round(sms.rate, 4) if sms.rate else 0,
        "received_at": sms.received_at.isoformat() if sms.received_at else None,
    }


# ──────────────────────────────────────────
#  GET /sms/latest
# ──────────────────────────────────────────
@api_v1_bp.route("/sms/latest")
@api_key_required
def sms_latest(api_user):
    q = SMS.query.filter_by(user_id=api_user.id)

    service = request.args.get("service")
    if service:
        q = q.filter(SMS.service.ilike(f"%{service}%"))

    phone = request.args.get("phone")
    if phone:
        q = q.filter(SMS.phone_number == phone)

    since = request.args.get("since", type=int)
    if since:
        q = q.filter(SMS.received_at >= datetime.utcfromtimestamp(since))

    sms = q.order_by(SMS.received_at.desc()).first()
    if not sms:
        return jsonify(ok=False, error="No SMS found"), 404

    return jsonify(ok=True, sms=_sms_to_dict(sms))


# ──────────────────────────────────────────
#  GET /sms/list
# ──────────────────────────────────────────
@api_v1_bp.route("/sms/list")
@api_key_required
def sms_list(api_user):
    q = SMS.query.filter_by(user_id=api_user.id)

    service = request.args.get("service")
    if service:
        q = q.filter(SMS.service.ilike(f"%{service}%"))

    phone = request.args.get("phone")
    if phone:
        q = q.filter(SMS.phone_number == phone)

    since = request.args.get("since", type=int)
    if since:
        q = q.filter(SMS.received_at >= datetime.utcfromtimestamp(since))

    limit = min(request.args.get("limit", 20, type=int), 100)
    page = request.args.get("page", 1, type=int)

    pg = q.order_by(SMS.received_at.desc()).paginate(
        page=page, per_page=limit, error_out=False
    )

    return jsonify(
        ok=True,
        page=pg.page,
        pages=pg.pages,
        total=pg.total,
        sms=[_sms_to_dict(s) for s in pg.items],
    )


# ──────────────────────────────────────────
#  GET /numbers
# ──────────────────────────────────────────
@api_v1_bp.route("/numbers")
@api_key_required
def numbers(api_user):
    nums = Number.query.filter_by(allocated_to_id=api_user.id).order_by(
        Number.allocated_at.desc()
    ).all()

    return jsonify(
        ok=True,
        total=len(nums),
        numbers=[
            {
                "phone": n.phone_number,
                "country": n.country,
                "service": n.service or "",
                "allocated_at": n.allocated_at.isoformat() if n.allocated_at else None,
            }
            for n in nums
        ],
    )


# ──────────────────────────────────────────
#  GET /balance
# ──────────────────────────────────────────
@api_v1_bp.route("/balance")
@api_key_required
def balance(api_user):
    return jsonify(
        ok=True,
        balance=round(api_user.balance, 4),
        user_id=api_user.user_id,
    )
