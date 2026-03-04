#!/usr/bin/env python3
"""
Eden SMS Services – Telegram Support & Management Bot
=====================================================
• Admin  → full panel (manage mods, create accounts, allocate numbers, view stats)
• Mod    → mod panel (login to verify, create accounts, allocate numbers)
• User   → support chat (messages routed to a random available staff member)

Run standalone:  python bot.py
Or import and call run_bot(flask_app) from another entry point.
"""

import os
import sys
import random
import asyncio
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# ── Flask app context helper ──────────────────────
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

from run import create_app
from models import (
    db, User, Number, SMS, ActivityLog, Announcement,
    BotMod, SupportTicket, SupportMessage,
    get_setting,
)
from routes.admin import COUNTRY_FLAGS

# ── Config ────────────────────────────────────────
BOT_TOKEN = "8447151980:AAFyFM9FpDdQkt-YceZHrXgvCH6YciLbVw8"
ADMIN_TG_ID = 7648364004

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s – %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("eden_bot")

# ── Premium / decorative emoji (premium users see animated versions) ──
E = {
    "logo":    "⚡",
    "admin":   "👑",
    "mod":     "🛡️",
    "user":    "👤",
    "chat":    "💬",
    "phone":   "📱",
    "key":     "🔑",
    "check":   "✅",
    "cross":   "❌",
    "warn":    "⚠️",
    "stats":   "📊",
    "bell":    "🔔",
    "gear":    "⚙️",
    "star":    "⭐",
    "fire":    "🔥",
    "link":    "🔗",
    "ban":     "🚫",
    "globe":   "🌍",
    "rocket":  "🚀",
    "wave":    "👋",
    "inbox":   "📥",
    "send":    "📤",
    "people":  "👥",
    "pin":     "📌",
    "folder":  "📁",
    "tag":     "🏷️",
    "money":   "💰",
    "shield":  "🛡️",
}

# ── Conversation states ───────────────────────────
(
    MOD_LOGIN_USER,
    MOD_LOGIN_PASS,
    WAITING_SUPPORT_MSG,
    STAFF_REPLY,
    CREATE_ACC_USERID,
    CREATE_ACC_PASSWORD,
    ALLOC_COUNTRY,
    ALLOC_QUANTITY,
    ADD_MOD_ID,
    ADMIN_CREATE_ACC_USERID,
    ADMIN_CREATE_ACC_PASSWORD,
    ADMIN_ALLOC_USER,
    ADMIN_ALLOC_COUNTRY,
    ADMIN_ALLOC_QUANTITY,
) = range(14)

flask_app = create_app()


# ═══════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════
def get_staff_telegram_ids():
    """Return list of all staff (admin + verified mods) Telegram IDs."""
    with flask_app.app_context():
        mod_ids = [m.telegram_id for m in BotMod.query.filter(BotMod.site_user_id.isnot(None)).all()]
    return [ADMIN_TG_ID] + mod_ids


def is_admin(tg_id: int) -> bool:
    return tg_id == ADMIN_TG_ID


def is_mod(tg_id: int) -> bool:
    with flask_app.app_context():
        return BotMod.query.filter_by(telegram_id=tg_id).filter(BotMod.site_user_id.isnot(None)).first() is not None


def is_staff(tg_id: int) -> bool:
    return is_admin(tg_id) or is_mod(tg_id)


def get_mod_site_user(tg_id: int):
    """Return the site User object linked to this mod's Telegram ID."""
    with flask_app.app_context():
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        if bm and bm.site_user_id:
            return User.query.get(bm.site_user_id)
    return None


# ═══════════════════════════════════════════════════
#  /start  – role detection & welcome
# ═══════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    name = update.effective_user.first_name or "there"

    if is_admin(tg_id):
        await show_admin_panel(update, ctx, name)
    elif is_mod(tg_id):
        await show_mod_panel(update, ctx, name)
    else:
        # Check if this TG ID is registered as a mod but not yet verified
        with flask_app.app_context():
            bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        if bm and not bm.site_user_id:
            await update.message.reply_text(
                f"{E['shield']} <b>Mod Verification Required</b>\n\n"
                f"You've been added as a mod. Please verify your site account.\n"
                f"Enter your <b>site User ID</b>:",
                parse_mode=ParseMode.HTML,
            )
            return MOD_LOGIN_USER
        elif bm and bm.site_user_id:
            await show_mod_panel(update, ctx, name)
        else:
            await show_user_welcome(update, ctx, name)
            return WAITING_SUPPORT_MSG

    return ConversationHandler.END


# ═══════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════
async def show_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str = None):
    if not name:
        name = update.effective_user.first_name or "Admin"

    with flask_app.app_context():
        total_users = User.query.filter_by(role="user").count()
        total_mods = User.query.filter_by(role="mod").count()
        total_numbers = Number.query.count()
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_sms = SMS.query.filter(SMS.received_at >= today_start).count()
        open_tickets = SupportTicket.query.filter_by(is_open=True).count()

    text = (
        f"{E['logo']} <b>EDEN SMS – Admin Panel</b> {E['admin']}\n"
        f"{'━' * 30}\n\n"
        f"Welcome back, <b>{name}</b>!\n\n"
        f"{E['people']} Users: <b>{total_users}</b>\n"
        f"{E['shield']} Mods: <b>{total_mods}</b>\n"
        f"{E['phone']} Numbers: <b>{total_numbers}</b>\n"
        f"{E['stats']} Today's SMS: <b>{today_sms}</b>\n"
        f"{E['chat']} Open Tickets: <b>{open_tickets}</b>\n"
        f"{'━' * 30}"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"{E['people']} Create Account", callback_data="admin_create_acc"),
            InlineKeyboardButton(f"{E['phone']} Allocate Numbers", callback_data="admin_allocate"),
        ],
        [
            InlineKeyboardButton(f"{E['shield']} Add Mod", callback_data="admin_add_mod"),
            InlineKeyboardButton(f"{E['people']} View Mods", callback_data="admin_view_mods"),
        ],
        [
            InlineKeyboardButton(f"{E['stats']} Stats", callback_data="admin_stats"),
            InlineKeyboardButton(f"{E['chat']} Support Inbox", callback_data="admin_inbox"),
        ],
        [
            InlineKeyboardButton(f"{E['bell']} Announcements", callback_data="admin_announcements"),
            InlineKeyboardButton(f"{E['gear']} Settings", callback_data="admin_settings"),
        ],
    ]

    msg = update.message or update.callback_query.message
    if update.callback_query:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


# ── Admin: Add Mod ────────────────────────────────
async def admin_add_mod_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        f"{E['shield']} <b>Add New Mod</b>\n\n"
        f"Send the Telegram ID of the new mod.\n"
        f"They'll need to start the bot and verify their site account.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{E['cross']} Cancel", callback_data="admin_panel")]
        ]),
    )
    return ADD_MOD_ID


async def admin_add_mod_receive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        tg_id = int(text)
    except ValueError:
        await update.message.reply_text(f"{E['warn']} Invalid Telegram ID. Please send a number.")
        return ADD_MOD_ID

    with flask_app.app_context():
        existing = BotMod.query.filter_by(telegram_id=tg_id).first()
        if existing:
            await update.message.reply_text(f"{E['warn']} This Telegram ID is already a mod.")
            return ConversationHandler.END

        bm = BotMod(telegram_id=tg_id)
        db.session.add(bm)
        db.session.commit()

    await update.message.reply_text(
        f"{E['check']} <b>Mod added!</b>\n\n"
        f"Telegram ID: <code>{tg_id}</code>\n"
        f"They need to /start the bot and verify their site login.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── Admin: View Mods ──────────────────────────────
async def admin_view_mods(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with flask_app.app_context():
        mods = BotMod.query.all()

    if not mods:
        text = f"{E['shield']} <b>Mods</b>\n\nNo mods added yet."
        keyboard = [[InlineKeyboardButton(f"{E['shield']} Add Mod", callback_data="admin_add_mod")]]
    else:
        lines = []
        for m in mods:
            status = f"{E['check']} Verified" if m.site_user_id else f"{E['warn']} Pending"
            with flask_app.app_context():
                site_name = ""
                if m.site_user_id:
                    u = User.query.get(m.site_user_id)
                    site_name = f" → {u.user_id}" if u else ""
            lines.append(f"  <code>{m.telegram_id}</code> {status}{site_name}")

        text = f"{E['shield']} <b>Mods ({len(mods)})</b>\n\n" + "\n".join(lines)
        keyboard = [
            [InlineKeyboardButton(f"{E['shield']} Add Mod", callback_data="admin_add_mod")],
            [InlineKeyboardButton(f"◀️ Back", callback_data="admin_panel")],
        ]

    await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


# ── Admin: Create Account ─────────────────────────
async def admin_create_acc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        f"{E['people']} <b>Create New Account</b>\n\n"
        f"Enter the <b>User ID</b> for the new account:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{E['cross']} Cancel", callback_data="admin_panel")]
        ]),
    )
    return ADMIN_CREATE_ACC_USERID


async def admin_create_acc_userid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if not uid:
        await update.message.reply_text(f"{E['warn']} User ID cannot be empty. Try again:")
        return ADMIN_CREATE_ACC_USERID

    with flask_app.app_context():
        if User.query.filter_by(user_id=uid).first():
            await update.message.reply_text(f"{E['cross']} User ID <b>{uid}</b> already exists. Try another:", parse_mode=ParseMode.HTML)
            return ADMIN_CREATE_ACC_USERID

    ctx.user_data["new_user_id"] = uid
    await update.message.reply_text(
        f"{E['key']} Now enter the <b>password</b> for <b>{uid}</b>:",
        parse_mode=ParseMode.HTML,
    )
    return ADMIN_CREATE_ACC_PASSWORD


async def admin_create_acc_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    if not pwd:
        await update.message.reply_text(f"{E['warn']} Password cannot be empty. Try again:")
        return ADMIN_CREATE_ACC_PASSWORD

    uid = ctx.user_data.get("new_user_id")
    with flask_app.app_context():
        # Check again
        if User.query.filter_by(user_id=uid).first():
            await update.message.reply_text(f"{E['cross']} User ID already taken.")
            return ConversationHandler.END

        # Admin creates as admin's own user
        admin_user = User.query.filter_by(user_id="200715").first()
        u = User(user_id=uid, role="user", created_by_id=admin_user.id if admin_user else None)
        u.set_password(pwd)
        db.session.add(u)
        db.session.add(ActivityLog(
            user_id=admin_user.id if admin_user else None,
            action="create_user",
            details=f"Admin created user via bot: {uid}",
        ))
        db.session.commit()

    await update.message.reply_text(
        f"{E['check']} <b>Account Created!</b>\n\n"
        f"{E['user']} User ID: <code>{uid}</code>\n"
        f"{E['key']} Password: <code>{pwd}</code>\n\n"
        f"Use /start to return to the panel.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── Admin: Allocate Numbers ───────────────────────
async def admin_allocate_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with flask_app.app_context():
        users = User.query.filter(User.role.in_(["user", "mod"])).filter_by(is_banned=False).all()

    if not users:
        await query.message.edit_text(f"{E['warn']} No users available to allocate to.")
        return ConversationHandler.END

    keyboard = []
    row = []
    for u in users:
        row.append(InlineKeyboardButton(f"{u.user_id}", callback_data=f"aalloc_user_{u.id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(f"◀️ Cancel", callback_data="admin_panel")])

    await query.message.edit_text(
        f"{E['phone']} <b>Allocate Numbers</b>\n\n"
        f"Select the user to allocate numbers to:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADMIN_ALLOC_USER


async def admin_alloc_user_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[-1])
    ctx.user_data["alloc_target_id"] = user_id

    with flask_app.app_context():
        countries = db.session.query(Number.country).distinct().all()
        countries = sorted([c[0] for c in countries])
        country_avail = {}
        for c in countries:
            country_avail[c] = Number.query.filter_by(country=c, allocated_to_id=None, is_active=True).count()
        target = User.query.get(user_id)
        target_name = target.user_id if target else "?"

    if not countries:
        await query.message.edit_text(f"{E['warn']} No countries with available numbers.")
        return ConversationHandler.END

    keyboard = []
    row = []
    for c in countries:
        avail = country_avail.get(c, 0)
        flag = COUNTRY_FLAGS.get(c, "🏳️")
        btn_text = f"{flag} {c} ({avail})"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"aalloc_country_{c}"))
        if len(row) == 1:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(f"◀️ Cancel", callback_data="admin_panel")])

    ctx.user_data["alloc_target_name"] = target_name

    await query.message.edit_text(
        f"{E['phone']} <b>Allocate to {target_name}</b>\n\n"
        f"Select the country:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADMIN_ALLOC_COUNTRY


async def admin_alloc_country_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    country = query.data.replace("aalloc_country_", "")
    ctx.user_data["alloc_country"] = country

    with flask_app.app_context():
        avail = Number.query.filter_by(country=country, allocated_to_id=None, is_active=True).count()

    await query.message.edit_text(
        f"{E['phone']} <b>Allocate {country} numbers</b>\n"
        f"To: <b>{ctx.user_data.get('alloc_target_name', '?')}</b>\n"
        f"Available: <b>{avail}</b>\n\n"
        f"Enter the quantity to allocate:",
        parse_mode=ParseMode.HTML,
    )
    return ADMIN_ALLOC_QUANTITY


async def admin_alloc_quantity(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(f"{E['warn']} Enter a valid number.")
        return ADMIN_ALLOC_QUANTITY

    if qty <= 0:
        await update.message.reply_text(f"{E['warn']} Must be greater than 0.")
        return ADMIN_ALLOC_QUANTITY

    target_id = ctx.user_data.get("alloc_target_id")
    country = ctx.user_data.get("alloc_country")

    with flask_app.app_context():
        target = User.query.get(target_id)
        if not target:
            await update.message.reply_text(f"{E['cross']} User not found.")
            return ConversationHandler.END

        max_per_day = int(get_setting("max_numbers_per_user", "100"))
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        already_today = Number.query.filter(
            Number.allocated_to_id == target.id,
            Number.allocated_at >= today_start,
        ).count()
        remaining = max_per_day - already_today

        if qty > remaining:
            await update.message.reply_text(
                f"{E['warn']} Can only allocate {remaining} more today (limit: {max_per_day}/day)."
            )
            return ConversationHandler.END

        available = Number.query.filter_by(
            country=country, allocated_to_id=None, is_active=True
        ).limit(qty).all()

        now = datetime.utcnow()
        admin_user = User.query.filter_by(user_id="200715").first()
        for n in available:
            n.allocated_to_id = target.id
            n.allocated_by_id = admin_user.id if admin_user else None
            n.allocated_at = now

        db.session.add(ActivityLog(
            user_id=admin_user.id if admin_user else None,
            action="allocate_numbers",
            details=f"Admin allocated {len(available)} {country} numbers to {target.user_id} via bot",
        ))
        db.session.commit()
        allocated_count = len(available)

    await update.message.reply_text(
        f"{E['check']} <b>Allocated {allocated_count} {country} numbers</b>\n"
        f"To: <b>{ctx.user_data.get('alloc_target_name', '?')}</b>\n\n"
        f"Use /start to return to the panel.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── Admin: Stats ──────────────────────────────────
async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with flask_app.app_context():
        total_users = User.query.filter_by(role="user").count()
        total_mods = User.query.filter_by(role="mod").count()
        total_numbers = Number.query.count()
        allocated = Number.query.filter(Number.allocated_to_id.isnot(None)).count()
        available = total_numbers - allocated

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_sms = SMS.query.filter(SMS.received_at >= today_start).count()
        total_sms = SMS.query.count()

        # Top countries
        top_countries = db.session.query(
            Number.country, db.func.count(Number.id)
        ).group_by(Number.country).order_by(db.func.count(Number.id).desc()).limit(5).all()

    country_lines = ""
    for c, cnt in top_countries:
        flag = COUNTRY_FLAGS.get(c, "🏳️")
        country_lines += f"  {flag} {c}: <b>{cnt}</b>\n"

    text = (
        f"{E['stats']} <b>EDEN SMS – Statistics</b>\n"
        f"{'━' * 30}\n\n"
        f"{E['people']} Total Users: <b>{total_users}</b>\n"
        f"{E['shield']} Total Mods: <b>{total_mods}</b>\n"
        f"{E['phone']} Total Numbers: <b>{total_numbers}</b>\n"
        f"  {E['check']} Allocated: <b>{allocated}</b>\n"
        f"  {E['star']} Available: <b>{available}</b>\n\n"
        f"{E['chat']} SMS Today: <b>{today_sms}</b>\n"
        f"{E['chat']} Total SMS: <b>{total_sms}</b>\n\n"
        f"{E['globe']} <b>Top Countries:</b>\n{country_lines}"
        f"{'━' * 30}"
    )

    await query.message.edit_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"◀️ Back", callback_data="admin_panel")]
        ]),
    )


# ── Admin: Support Inbox ──────────────────────────
async def admin_inbox(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with flask_app.app_context():
        tickets = SupportTicket.query.filter_by(is_open=True).order_by(SupportTicket.created_at.desc()).limit(20).all()

    if not tickets:
        text = f"{E['inbox']} <b>Support Inbox</b>\n\nNo open tickets."
    else:
        lines = []
        for t in tickets:
            name = t.telegram_name or str(t.telegram_id)
            assigned = "Unassigned" if not t.assigned_to else f"Assigned"
            site = f" | {E['link']} {t.site_user.user_id}" if t.site_user_id else ""
            lines.append(f"  {E['chat']} <b>{name}</b> – {assigned}{site}")
        text = f"{E['inbox']} <b>Support Inbox ({len(tickets)} open)</b>\n\n" + "\n".join(lines)

    await query.message.edit_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"◀️ Back", callback_data="admin_panel")]
        ]),
    )


# ── Admin: Announcements ─────────────────────────
async def admin_announcements(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with flask_app.app_context():
        anns = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).limit(5).all()

    if not anns:
        text = f"{E['bell']} <b>Announcements</b>\n\nNo active announcements."
    else:
        lines = []
        for a in anns:
            lines.append(f"  {E['pin']} <b>{a.title}</b>\n     {a.body[:100]}{'...' if len(a.body) > 100 else ''}")
        text = f"{E['bell']} <b>Active Announcements</b>\n\n" + "\n\n".join(lines)

    await query.message.edit_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"◀️ Back", callback_data="admin_panel")]
        ]),
    )


# ── Admin: Settings ───────────────────────────────
async def admin_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with flask_app.app_context():
        otp_rate = get_setting("otp_rate", "0.005")
        min_wd = get_setting("min_withdrawal", "5")
        max_nums = get_setting("max_numbers_per_user", "100")
        wd_day = get_setting("withdrawal_day", "Tuesday")

    text = (
        f"{E['gear']} <b>Current Settings</b>\n"
        f"{'━' * 30}\n\n"
        f"  {E['money']} OTP Rate: <b>${otp_rate}</b>\n"
        f"  {E['money']} Min Withdrawal: <b>${min_wd}</b>\n"
        f"  {E['phone']} Max Numbers/User/Day: <b>{max_nums}</b>\n"
        f"  📅 Withdrawal Day: <b>{wd_day}</b>\n\n"
        f"<i>Edit these from the web panel.</i>"
    )

    await query.message.edit_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"◀️ Back", callback_data="admin_panel")]
        ]),
    )


# ── Admin: Back to panel callback ─────────────────
async def admin_panel_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_admin_panel(update, ctx)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════
#  MOD PANEL
# ═══════════════════════════════════════════════════
async def show_mod_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str = None):
    tg_id = update.effective_user.id
    if not name:
        name = update.effective_user.first_name or "Mod"

    with flask_app.app_context():
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        if not bm or not bm.site_user_id:
            msg = update.message or update.callback_query.message
            await msg.reply_text(f"{E['warn']} Your mod account is not verified yet. Use /start to verify.")
            return

        site_user = User.query.get(bm.site_user_id)
        if not site_user:
            msg = update.message or update.callback_query.message
            await msg.reply_text(f"{E['cross']} Site account not found.")
            return

        my_users = User.query.filter_by(created_by_id=site_user.id, role="user").count()
        my_numbers = Number.query.filter(
            Number.allocated_by_id == site_user.id
        ).count()

    text = (
        f"{E['shield']} <b>EDEN SMS – Mod Panel</b>\n"
        f"{'━' * 30}\n\n"
        f"Welcome, <b>{name}</b>!\n"
        f"Site Account: <b>{site_user.user_id}</b>\n\n"
        f"{E['people']} Your Users: <b>{my_users}</b>\n"
        f"{E['phone']} Numbers Allocated: <b>{my_numbers}</b>\n"
        f"{'━' * 30}"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"{E['people']} Create Account", callback_data="mod_create_acc"),
            InlineKeyboardButton(f"{E['phone']} Allocate Numbers", callback_data="mod_allocate"),
        ],
        [
            InlineKeyboardButton(f"{E['people']} My Users", callback_data="mod_my_users"),
            InlineKeyboardButton(f"{E['chat']} Support Inbox", callback_data="mod_inbox"),
        ],
    ]

    msg = update.message or update.callback_query.message
    if update.callback_query:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


# ── Mod: Login verification ───────────────────────
async def mod_login_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    ctx.user_data["mod_login_uid"] = uid
    await update.message.reply_text(
        f"{E['key']} Now enter your <b>password</b>:",
        parse_mode=ParseMode.HTML,
    )
    return MOD_LOGIN_PASS


async def mod_login_pass(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    uid = ctx.user_data.get("mod_login_uid", "")
    tg_id = update.effective_user.id

    with flask_app.app_context():
        user = User.query.filter_by(user_id=uid).first()
        if not user or not user.check_password(pwd):
            await update.message.reply_text(
                f"{E['cross']} <b>Invalid credentials.</b> Try /start again.",
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END

        if user.role != "mod":
            await update.message.reply_text(
                f"{E['cross']} This account is not a mod account.",
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END

        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        if bm:
            bm.site_user_id = user.id
            db.session.commit()

    await update.message.reply_text(
        f"{E['check']} <b>Verified successfully!</b>\n"
        f"Linked to site account: <b>{uid}</b>\n\n"
        f"Use /start to open your mod panel.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── Mod: Create Account ──────────────────────────
async def mod_create_acc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_staff(query.from_user.id):
        return ConversationHandler.END

    await query.message.edit_text(
        f"{E['people']} <b>Create New Account</b>\n\n"
        f"Enter the <b>User ID</b>:",
        parse_mode=ParseMode.HTML,
    )
    return CREATE_ACC_USERID


async def mod_create_acc_userid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if not uid:
        await update.message.reply_text(f"{E['warn']} User ID cannot be empty.")
        return CREATE_ACC_USERID

    with flask_app.app_context():
        if User.query.filter_by(user_id=uid).first():
            await update.message.reply_text(f"{E['cross']} User ID already exists. Try another:")
            return CREATE_ACC_USERID

    ctx.user_data["new_user_id"] = uid
    await update.message.reply_text(
        f"{E['key']} Enter the <b>password</b> for <b>{uid}</b>:",
        parse_mode=ParseMode.HTML,
    )
    return CREATE_ACC_PASSWORD


async def mod_create_acc_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    if not pwd:
        await update.message.reply_text(f"{E['warn']} Password cannot be empty.")
        return CREATE_ACC_PASSWORD

    uid = ctx.user_data.get("new_user_id")
    tg_id = update.effective_user.id

    with flask_app.app_context():
        if User.query.filter_by(user_id=uid).first():
            await update.message.reply_text(f"{E['cross']} User ID already taken.")
            return ConversationHandler.END

        # Get the mod's site user
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        creator_id = bm.site_user_id if bm else None

        u = User(user_id=uid, role="user", created_by_id=creator_id)
        u.set_password(pwd)
        db.session.add(u)
        db.session.add(ActivityLog(
            user_id=creator_id,
            action="create_user",
            details=f"Created user via bot: {uid}",
        ))
        db.session.commit()

    await update.message.reply_text(
        f"{E['check']} <b>Account Created!</b>\n\n"
        f"{E['user']} User ID: <code>{uid}</code>\n"
        f"{E['key']} Password: <code>{pwd}</code>\n\n"
        f"Use /start to return to the panel.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── Mod: Allocate Numbers ─────────────────────────
async def mod_allocate_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id

    with flask_app.app_context():
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        if not bm or not bm.site_user_id:
            await query.message.edit_text(f"{E['warn']} Not verified.")
            return ConversationHandler.END

        my_users = User.query.filter_by(created_by_id=bm.site_user_id, role="user", is_banned=False).all()

    if not my_users:
        await query.message.edit_text(
            f"{E['warn']} You have no users to allocate to.\nCreate an account first.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"◀️ Back", callback_data="mod_panel")]
            ]),
        )
        return ConversationHandler.END

    keyboard = []
    row = []
    for u in my_users:
        row.append(InlineKeyboardButton(f"{u.user_id}", callback_data=f"malloc_user_{u.id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(f"◀️ Cancel", callback_data="mod_panel")])

    await query.message.edit_text(
        f"{E['phone']} <b>Allocate Numbers</b>\n\n"
        f"Select the user:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ALLOC_COUNTRY


async def mod_alloc_user_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[-1])
    ctx.user_data["alloc_target_id"] = user_id

    with flask_app.app_context():
        countries = db.session.query(Number.country).distinct().all()
        countries = sorted([c[0] for c in countries])
        country_avail = {}
        for c in countries:
            country_avail[c] = Number.query.filter_by(country=c, allocated_to_id=None, is_active=True).count()
        target = User.query.get(user_id)
        target_name = target.user_id if target else "?"

    keyboard = []
    for c in countries:
        avail = country_avail.get(c, 0)
        flag = COUNTRY_FLAGS.get(c, "🏳️")
        keyboard.append([InlineKeyboardButton(f"{flag} {c} ({avail})", callback_data=f"malloc_country_{c}")])
    keyboard.append([InlineKeyboardButton(f"◀️ Cancel", callback_data="mod_panel")])

    ctx.user_data["alloc_target_name"] = target_name

    await query.message.edit_text(
        f"{E['phone']} <b>Allocate to {target_name}</b>\n\nSelect the country:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ALLOC_COUNTRY


async def mod_alloc_country_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    country = query.data.replace("malloc_country_", "")
    ctx.user_data["alloc_country"] = country

    with flask_app.app_context():
        avail = Number.query.filter_by(country=country, allocated_to_id=None, is_active=True).count()

    await query.message.edit_text(
        f"{E['phone']} <b>Allocate {country}</b>\n"
        f"To: <b>{ctx.user_data.get('alloc_target_name', '?')}</b>\n"
        f"Available: <b>{avail}</b>\n\n"
        f"Enter the quantity:",
        parse_mode=ParseMode.HTML,
    )
    return ALLOC_QUANTITY


async def mod_alloc_quantity(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(f"{E['warn']} Enter a valid number.")
        return ALLOC_QUANTITY

    if qty <= 0:
        await update.message.reply_text(f"{E['warn']} Must be > 0.")
        return ALLOC_QUANTITY

    target_id = ctx.user_data.get("alloc_target_id")
    country = ctx.user_data.get("alloc_country")
    tg_id = update.effective_user.id

    with flask_app.app_context():
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        mod_site_id = bm.site_user_id if bm else None

        target = User.query.get(target_id)
        if not target:
            await update.message.reply_text(f"{E['cross']} User not found.")
            return ConversationHandler.END

        max_per_day = int(get_setting("max_numbers_per_user", "100"))
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        already_today = Number.query.filter(
            Number.allocated_to_id == target.id,
            Number.allocated_at >= today_start,
        ).count()
        remaining = max_per_day - already_today

        if qty > remaining:
            await update.message.reply_text(f"{E['warn']} Can only allocate {remaining} more today.")
            return ConversationHandler.END

        available = Number.query.filter_by(
            country=country, allocated_to_id=None, is_active=True,
        ).limit(qty).all()

        now = datetime.utcnow()
        for n in available:
            n.allocated_to_id = target.id
            n.allocated_by_id = mod_site_id
            n.allocated_at = now

        db.session.add(ActivityLog(
            user_id=mod_site_id,
            action="allocate_numbers",
            details=f"Mod allocated {len(available)} {country} numbers to {target.user_id} via bot",
        ))
        db.session.commit()
        count = len(available)

    await update.message.reply_text(
        f"{E['check']} <b>Allocated {count} {country} numbers</b>\n"
        f"To: <b>{ctx.user_data.get('alloc_target_name', '?')}</b>\n\n"
        f"Use /start to return.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── Mod: My Users ─────────────────────────────────
async def mod_my_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id

    with flask_app.app_context():
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        if not bm or not bm.site_user_id:
            await query.message.edit_text(f"{E['warn']} Not verified.")
            return

        users = User.query.filter_by(created_by_id=bm.site_user_id, role="user").order_by(User.created_at.desc()).all()

    if not users:
        text = f"{E['people']} <b>My Users</b>\n\nNo users yet."
    else:
        lines = []
        for u in users:
            with flask_app.app_context():
                num_count = Number.query.filter_by(allocated_to_id=u.id).count()
            status = f"{E['ban']} Banned" if u.is_banned else f"{E['check']} Active"
            lines.append(f"  {E['user']} <b>{u.user_id}</b> – {num_count} numbers – {status}")
        text = f"{E['people']} <b>My Users ({len(users)})</b>\n\n" + "\n".join(lines)

    keyboard = []
    for u in users:
        keyboard.append([InlineKeyboardButton(f"{E['user']} {u.user_id}", callback_data=f"mod_user_detail_{u.id}")])
    keyboard.append([InlineKeyboardButton(f"◀️ Back", callback_data="mod_panel")])

    await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


# ── Mod: User Detail ──────────────────────────────
async def mod_user_detail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[-1])

    tg_id = query.from_user.id

    with flask_app.app_context():
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        user = User.query.get(uid)
        if not user:
            await query.message.edit_text(f"{E['cross']} User not found.")
            return

        is_owner = (bm and user.created_by_id == bm.site_user_id) or is_admin(tg_id)
        if not is_owner:
            await query.message.edit_text(f"{E['cross']} Not your user.")
            return

        num_count = Number.query.filter_by(allocated_to_id=user.id).count()
        sms_count = SMS.query.filter_by(user_id=user.id).count()

        # Get countries with allocations
        countries = db.session.query(Number.country, db.func.count(Number.id)).filter(
            Number.allocated_to_id == user.id
        ).group_by(Number.country).all()

    status = f"{E['ban']} Banned" if user.is_banned else f"{E['check']} Active"
    country_lines = ""
    for c, cnt in countries:
        flag = COUNTRY_FLAGS.get(c, "🏳️")
        country_lines += f"  {flag} {c}: {cnt}\n"

    text = (
        f"{E['user']} <b>User: {user.user_id}</b>\n"
        f"{'━' * 28}\n\n"
        f"Status: {status}\n"
        f"{E['phone']} Numbers: <b>{num_count}</b>\n"
        f"{E['chat']} SMS: <b>{sms_count}</b>\n"
        f"{E['money']} Balance: <b>${user.balance:.2f}</b>\n"
        f"📅 Joined: {user.created_at.strftime('%Y-%m-%d')}\n"
    )
    if country_lines:
        text += f"\n{E['globe']} <b>Numbers by Country:</b>\n{country_lines}"

    keyboard = [
        [
            InlineKeyboardButton(f"{E['phone']} Allocate", callback_data=f"quick_alloc_{user.id}"),
            InlineKeyboardButton(f"{E['cross']} Revoke All", callback_data=f"revoke_all_{user.id}"),
        ],
        [
            InlineKeyboardButton(
                f"{E['ban']} Unban" if user.is_banned else f"{E['ban']} Ban",
                callback_data=f"toggle_ban_{user.id}"
            ),
        ],
        [InlineKeyboardButton(f"◀️ Back", callback_data="mod_my_users" if not is_admin(tg_id) else "admin_panel")],
    ]

    await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


# ── Quick actions: Revoke All, Ban/Unban ──────────
async def revoke_all_numbers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[-1])
    tg_id = query.from_user.id

    with flask_app.app_context():
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        mod_site_id = bm.site_user_id if bm else None
        if is_admin(tg_id):
            admin_user = User.query.filter_by(user_id="200715").first()
            mod_site_id = admin_user.id if admin_user else None

        target = User.query.get(uid)
        if not target:
            await query.message.edit_text(f"{E['cross']} User not found.")
            return

        nums = Number.query.filter_by(allocated_to_id=uid).update(
            {"allocated_to_id": None, "allocated_by_id": None, "allocated_at": None}
        )
        db.session.add(ActivityLog(
            user_id=mod_site_id,
            action="revoke_numbers",
            details=f"Revoked all {nums} numbers from {target.user_id} via bot",
        ))
        db.session.commit()

    await query.message.edit_text(
        f"{E['check']} Revoked <b>{nums}</b> numbers from <b>{target.user_id}</b>.\n\nUse /start to return.",
        parse_mode=ParseMode.HTML,
    )


async def toggle_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[-1])
    tg_id = query.from_user.id

    with flask_app.app_context():
        bm = BotMod.query.filter_by(telegram_id=tg_id).first()
        mod_site_id = bm.site_user_id if bm else None
        if is_admin(tg_id):
            admin_user = User.query.filter_by(user_id="200715").first()
            mod_site_id = admin_user.id if admin_user else None

        user = User.query.get(uid)
        if not user:
            await query.message.edit_text(f"{E['cross']} User not found.")
            return

        user.is_banned = not user.is_banned
        action = "Banned" if user.is_banned else "Unbanned"
        db.session.add(ActivityLog(
            user_id=mod_site_id,
            action=f"{action.lower()}_user",
            details=f"{action} user {user.user_id} via bot",
        ))
        db.session.commit()
        status = user.is_banned

    emoji = E['ban'] if status else E['check']
    word = "banned" if status else "unbanned"
    await query.message.edit_text(
        f"{emoji} User <b>{user.user_id}</b> has been <b>{word}</b>.\n\nUse /start to return.",
        parse_mode=ParseMode.HTML,
    )


# ── Mod: Support Inbox ───────────────────────────
async def mod_inbox(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id

    with flask_app.app_context():
        tickets = SupportTicket.query.filter_by(
            assigned_to=tg_id, is_open=True
        ).order_by(SupportTicket.created_at.desc()).limit(20).all()

    if not tickets:
        text = f"{E['inbox']} <b>Support Inbox</b>\n\nNo assigned tickets."
    else:
        lines = []
        for t in tickets:
            name = t.telegram_name or str(t.telegram_id)
            site = f" | {E['link']} {t.site_user.user_id}" if t.site_user_id else ""
            lines.append(f"  {E['chat']} <b>{name}</b>{site}")
        text = f"{E['inbox']} <b>Your Tickets ({len(tickets)})</b>\n\n" + "\n".join(lines)

    kb = [[InlineKeyboardButton(f"◀️ Back",
        callback_data="mod_panel" if not is_admin(tg_id) else "admin_panel")]]

    await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))


# ── Mod panel callback ────────────────────────────
async def mod_panel_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_mod_panel(update, ctx)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════
#  USER SUPPORT CHAT
# ═══════════════════════════════════════════════════
async def show_user_welcome(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str):
    await update.message.reply_text(
        f"{E['wave']} <b>Welcome at Eden SMS</b>\n\n"
        f"Hi <b>{name}</b>! {E['chat']}\n\n"
        f"Type your message below and our support team will respond shortly after",
        parse_mode=ParseMode.HTML,
    )


async def handle_user_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle messages from regular users → route to staff."""
    tg_id = update.effective_user.id
    tg_name = update.effective_user.first_name or update.effective_user.username or str(tg_id)
    text = update.message.text

    if is_staff(tg_id):
        return  # Staff messages handled differently

    with flask_app.app_context():
        # Get or create ticket
        ticket = SupportTicket.query.filter_by(telegram_id=tg_id).first()

        if not ticket:
            # Assign to a random staff member
            staff_ids = get_staff_telegram_ids()
            if not staff_ids:
                await update.message.reply_text(f"{E['warn']} No support agents available. Try later.")
                return WAITING_SUPPORT_MSG

            assigned = random.choice(staff_ids)
            ticket = SupportTicket(
                telegram_id=tg_id,
                telegram_name=tg_name,
                assigned_to=assigned,
            )
            db.session.add(ticket)
            db.session.flush()

        # Save message
        msg = SupportMessage(
            ticket_id=ticket.id,
            sender_telegram_id=tg_id,
            text=text,
            is_from_staff=False,
        )
        db.session.add(msg)
        db.session.commit()

        assigned_to = ticket.assigned_to
        ticket_id = ticket.id
        site_user_id = ticket.site_user_id

    # Build inline buttons for the staff member
    buttons = []
    if site_user_id:
        # User has a linked account
        with flask_app.app_context():
            linked_user = User.query.get(site_user_id)
            if linked_user:
                buttons.append([InlineKeyboardButton(
                    f"{E['user']} {linked_user.user_id}",
                    callback_data=f"mod_user_detail_{linked_user.id}"
                )])
    else:
        buttons.append([InlineKeyboardButton(
            f"{E['people']} Create Account",
            callback_data=f"support_create_acc_{ticket_id}"
        )])

    buttons.append([InlineKeyboardButton(
        f"{E['send']} Reply",
        callback_data=f"support_reply_{ticket_id}"
    )])

    # Forward to assigned staff
    try:
        await ctx.bot.send_message(
            chat_id=assigned_to,
            text=(
                f"{E['inbox']} <b>New Support Message</b>\n"
                f"{'━' * 28}\n"
                f"From: <b>{tg_name}</b> (<code>{tg_id}</code>)\n\n"
                f"{E['chat']} {text}"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as e:
        logger.error(f"Failed to forward support msg to {assigned_to}: {e}")

    await update.message.reply_text(
        f"{E['check']} Message sent! Our team will respond shortly.",
        parse_mode=ParseMode.HTML,
    )
    return WAITING_SUPPORT_MSG


# ── Staff: Reply to support ticket ────────────────
async def support_reply_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split("_")[-1])
    ctx.user_data["reply_ticket_id"] = ticket_id

    with flask_app.app_context():
        ticket = SupportTicket.query.get(ticket_id)
        name = ticket.telegram_name if ticket else "User"

    await query.message.reply_text(
        f"{E['send']} <b>Reply to {name}</b>\n\nType your message:",
        parse_mode=ParseMode.HTML,
    )
    return STAFF_REPLY


async def support_reply_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    ticket_id = ctx.user_data.get("reply_ticket_id")
    tg_id = update.effective_user.id

    with flask_app.app_context():
        ticket = SupportTicket.query.get(ticket_id)
        if not ticket:
            await update.message.reply_text(f"{E['cross']} Ticket not found.")
            return ConversationHandler.END

        msg = SupportMessage(
            ticket_id=ticket.id,
            sender_telegram_id=tg_id,
            text=text,
            is_from_staff=True,
        )
        db.session.add(msg)
        db.session.commit()
        user_tg_id = ticket.telegram_id

    # Send to the user
    try:
        staff_name = "Support Team"
        await ctx.bot.send_message(
            chat_id=user_tg_id,
            text=(
                f"{E['shield']} <b>Eden SMS Support</b>\n"
                f"{'━' * 28}\n\n"
                f"{text}"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to send reply to user {user_tg_id}: {e}")
        await update.message.reply_text(f"{E['warn']} Failed to deliver message to user.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"{E['check']} Reply sent to <b>{ticket.telegram_name or 'user'}</b>!",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── Staff: Create account from support ────────────
async def support_create_acc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split("_")[-1])
    ctx.user_data["support_ticket_id"] = ticket_id

    await query.message.reply_text(
        f"{E['people']} <b>Create Account for Support User</b>\n\n"
        f"Enter the <b>User ID</b>:",
        parse_mode=ParseMode.HTML,
    )
    return CREATE_ACC_USERID


# ── After account created from support, link it ──
async def support_create_acc_password_finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    if not pwd:
        await update.message.reply_text(f"{E['warn']} Password cannot be empty.")
        return CREATE_ACC_PASSWORD

    uid = ctx.user_data.get("new_user_id")
    tg_id = update.effective_user.id
    ticket_id = ctx.user_data.get("support_ticket_id")

    with flask_app.app_context():
        if User.query.filter_by(user_id=uid).first():
            await update.message.reply_text(f"{E['cross']} User ID already taken.")
            return ConversationHandler.END

        # Determine creator
        if is_admin(tg_id):
            admin_user = User.query.filter_by(user_id="200715").first()
            creator_id = admin_user.id if admin_user else None
        else:
            bm = BotMod.query.filter_by(telegram_id=tg_id).first()
            creator_id = bm.site_user_id if bm else None

        u = User(user_id=uid, role="user", created_by_id=creator_id)
        u.set_password(pwd)
        db.session.add(u)
        db.session.flush()

        # Link ticket to new user if from support
        if ticket_id:
            ticket = SupportTicket.query.get(ticket_id)
            if ticket:
                ticket.site_user_id = u.id

        db.session.add(ActivityLog(
            user_id=creator_id,
            action="create_user",
            details=f"Created user via bot support: {uid}",
        ))
        db.session.commit()
        new_user_id = u.id

    await update.message.reply_text(
        f"{E['check']} <b>Account Created & Linked!</b>\n\n"
        f"{E['user']} User ID: <code>{uid}</code>\n"
        f"{E['key']} Password: <code>{pwd}</code>\n\n"
        f"This account is now linked to the support ticket.\n"
        f"Use /start to return.",
        parse_mode=ParseMode.HTML,
    )
    ctx.user_data.pop("support_ticket_id", None)
    return ConversationHandler.END


# ── Quick allocate from user detail ───────────────
async def quick_alloc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[-1])
    ctx.user_data["alloc_target_id"] = uid

    with flask_app.app_context():
        target = User.query.get(uid)
        ctx.user_data["alloc_target_name"] = target.user_id if target else "?"
        countries = db.session.query(Number.country).distinct().all()
        countries = sorted([c[0] for c in countries])
        country_avail = {}
        for c in countries:
            country_avail[c] = Number.query.filter_by(country=c, allocated_to_id=None, is_active=True).count()

    keyboard = []
    for c in countries:
        avail = country_avail.get(c, 0)
        flag = COUNTRY_FLAGS.get(c, "🏳️")
        # Use the right prefix based on who is calling
        tg_id = query.from_user.id
        prefix = "aalloc" if is_admin(tg_id) else "malloc"
        keyboard.append([InlineKeyboardButton(f"{flag} {c} ({avail})", callback_data=f"{prefix}_country_{c}")])
    keyboard.append([InlineKeyboardButton(f"◀️ Cancel", callback_data="mod_panel")])

    await query.message.edit_text(
        f"{E['phone']} <b>Allocate to {ctx.user_data.get('alloc_target_name')}</b>\n\nSelect country:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    # Return the right state
    tg_id = query.from_user.id
    if is_admin(tg_id):
        return ADMIN_ALLOC_COUNTRY
    return ALLOC_COUNTRY


# ═══════════════════════════════════════════════════
#  /help command
# ═══════════════════════════════════════════════════
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if is_admin(tg_id):
        text = (
            f"{E['admin']} <b>Admin Commands</b>\n\n"
            f"/start – Open admin panel\n"
            f"/help – Show this help\n"
            f"/id – Show your Telegram ID\n"
        )
    elif is_staff(tg_id):
        text = (
            f"{E['shield']} <b>Mod Commands</b>\n\n"
            f"/start – Open mod panel\n"
            f"/help – Show this help\n"
            f"/id – Show your Telegram ID\n"
        )
    else:
        text = (
            f"{E['chat']} <b>Support Commands</b>\n\n"
            f"/start – Start support chat\n"
            f"/help – Show this help\n"
            f"/id – Show your Telegram ID\n"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"{E['tag']} Your Telegram ID: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════
#  BUILD & RUN
# ═══════════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Conversation: /start (handles admin/mod/user routing) ──
    start_conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MOD_LOGIN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, mod_login_user)],
            MOD_LOGIN_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, mod_login_pass)],
            WAITING_SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )

    # ── Conversation: Admin add mod ──
    add_mod_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_mod_start, pattern="^admin_add_mod$")],
        states={
            ADD_MOD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_mod_receive)],
        },
        fallbacks=[
            CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

    # ── Conversation: Admin create account ──
    admin_create_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_create_acc_start, pattern="^admin_create_acc$")],
        states={
            ADMIN_CREATE_ACC_USERID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_acc_userid)],
            ADMIN_CREATE_ACC_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_acc_password)],
        },
        fallbacks=[
            CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

    # ── Conversation: Admin allocate numbers ──
    admin_alloc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_allocate_start, pattern="^admin_allocate$")],
        states={
            ADMIN_ALLOC_USER: [CallbackQueryHandler(admin_alloc_user_selected, pattern="^aalloc_user_")],
            ADMIN_ALLOC_COUNTRY: [CallbackQueryHandler(admin_alloc_country_selected, pattern="^aalloc_country_")],
            ADMIN_ALLOC_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_alloc_quantity)],
        },
        fallbacks=[
            CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

    # ── Conversation: Mod create account ──
    mod_create_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(mod_create_acc_start, pattern="^mod_create_acc$"),
            CallbackQueryHandler(support_create_acc_start, pattern="^support_create_acc_"),
        ],
        states={
            CREATE_ACC_USERID: [MessageHandler(filters.TEXT & ~filters.COMMAND, mod_create_acc_userid)],
            CREATE_ACC_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_create_acc_password_finish)],
        },
        fallbacks=[
            CallbackQueryHandler(mod_panel_callback, pattern="^mod_panel$"),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

    # ── Conversation: Mod allocate numbers ──
    mod_alloc_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(mod_allocate_start, pattern="^mod_allocate$"),
            CallbackQueryHandler(quick_alloc_start, pattern="^quick_alloc_"),
        ],
        states={
            ALLOC_COUNTRY: [CallbackQueryHandler(mod_alloc_country_selected, pattern="^malloc_country_")],
            ALLOC_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, mod_alloc_quantity)],
        },
        fallbacks=[
            CallbackQueryHandler(mod_panel_callback, pattern="^mod_panel$"),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
    )

    # ── Conversation: Support reply ──
    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(support_reply_start, pattern="^support_reply_")],
        states={
            STAFF_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_reply_send)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )

    # Register conversation handlers (order matters)
    app.add_handler(start_conv)
    app.add_handler(add_mod_conv)
    app.add_handler(admin_create_conv)
    app.add_handler(admin_alloc_conv)
    app.add_handler(mod_create_conv)
    app.add_handler(mod_alloc_conv)
    app.add_handler(reply_conv)

    # ── Standalone callback queries (not part of conversations) ──
    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_view_mods, pattern="^admin_view_mods$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_inbox, pattern="^admin_inbox$"))
    app.add_handler(CallbackQueryHandler(admin_announcements, pattern="^admin_announcements$"))
    app.add_handler(CallbackQueryHandler(admin_settings, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(mod_panel_callback, pattern="^mod_panel$"))
    app.add_handler(CallbackQueryHandler(mod_my_users, pattern="^mod_my_users$"))
    app.add_handler(CallbackQueryHandler(mod_inbox, pattern="^mod_inbox$"))
    app.add_handler(CallbackQueryHandler(mod_user_detail, pattern="^mod_user_detail_"))
    app.add_handler(CallbackQueryHandler(revoke_all_numbers, pattern="^revoke_all_"))
    app.add_handler(CallbackQueryHandler(toggle_ban, pattern="^toggle_ban_"))

    # ── Simple commands ──
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("id", cmd_id))

    # ── Catch-all for non-staff text (support messages) ──
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

    logger.info("🚀 Eden SMS Support Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
