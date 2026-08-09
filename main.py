# -*- coding: utf-8 -*-
"""
=========================================================
🤫 WHISPER BOT - FIXED & OPTIMIZED VERSION
=========================================================
"""

import os
import json
import time
import uuid
import html
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, deque

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InlineQueryResultArticle, InputTextMessageContent,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, InlineQueryHandler, ContextTypes,
    ConversationHandler, filters,
)

# =========================================================
# ⚙️ CONFIG
# =========================================================
DATA_FILE = Path(os.environ.get("DATA_FILE", "database.json"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", "8080"))

MAX_TEXT_LENGTH = 4000
MAX_WHISPERS = 100000
DEFAULT_TTL = 7 * 24 * 60 * 60  # 7 Days
CREATE_LIMIT = 20
CREATE_WINDOW = 60

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("WhisperBot")

# =========================================================
# 🔒 LOCKS & MEMORY
# =========================================================
DATA_LOCK = asyncio.Lock()
RATE_LIMIT_LOCK = asyncio.Lock()

CREATE_SESSIONS = {}
UNLOCK_SESSIONS = {}
INLINE_CACHE = {}  # لتخزين الهمسات السريعة قبل أول ضغطة
CREATE_HISTORY = defaultdict(deque)

(
    CREATE_TYPE, CREATE_TEXT, CREATE_MEDIA, CREATE_AUDIENCE,
    CREATE_RECIPIENTS, CREATE_ANONYMOUS, CREATE_PROTECTION,
    CREATE_PASSWORD, CREATE_QUESTION, CREATE_ANSWER,
    CREATE_ONETIME, CREATE_SELF_DESTRUCT, CREATE_TIME,
    CREATE_BUTTON, CREATE_CONFIRM,
) = range(15)

# =========================================================
# 🧰 HELPERS
# =========================================================
def now(): return int(time.time())
def escape(text): return html.escape(str(text))
def make_id(): return uuid.uuid4().hex[:16]

# =========================================================
# 🗄️ DATABASE
# =========================================================
def empty_database():
    return {"whispers": {}}

async def load_database():
    async with DATA_LOCK:
        if not DATA_FILE.exists():
            return empty_database()
        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading DB: {e}")
            return empty_database()

async def save_database(data):
    async with DATA_LOCK:
        try:
            temp_file = DATA_FILE.with_suffix(".tmp")
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_file.replace(DATA_FILE)
        except Exception as e:
            logger.error(f"Error saving DB: {e}")

# =========================================================
# 🚦 RATE LIMIT
# =========================================================
async def rate_allowed(user_id):
    current = time.monotonic()
    async with RATE_LIMIT_LOCK:
        history = CREATE_HISTORY[user_id]
        while history and (current - history[0] > CREATE_WINDOW):
            history.popleft()
        if len(history) >= CREATE_LIMIT:
            return False
        history.append(current)
        return True

# =========================================================
# 🧹 CLEANUP JOB
# =========================================================
async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    # تنظيف قاعدة البيانات الرئيسية
    data = await load_database()
    changed = False
    current = now()
    
    for w_id in list(data["whispers"]):
        if data["whispers"][w_id].get("expires_at", 0) <= current:
            del data["whispers"][w_id]
            changed = True
            
    if changed:
        await save_database(data)

    # تنظيف الذاكرة المؤقتة (Inline Cache) للهمسات غير المفتوحة
    for w_id in list(INLINE_CACHE):
        if current - INLINE_CACHE[w_id]["created_at"] > 3600:  # مسح بعد ساعة
            del INLINE_CACHE[w_id]

# =========================================================
# 🏠 START & HELP
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤫 <b>مرحبًا بك في بوت الهمسات السري!</b>\n\n"
        "يمكنك استخدام البوت مباشرة في أي قروب بكتابة:\n"
        "<code>@{} نص الهمسة</code>\n"
        "أو\n"
        "<code>@{} @username نص الهمسة</code> (لشخص معين)\n\n"
        "أو اضغط على (إنشاء همسة) لخيارات متقدمة كالصور وكلمة المرور."
    ).format(context.bot.username, context.bot.username)
    
    keyboard = [
        [InlineKeyboardButton("🤫 إنشاء همسة متقدمة", callback_data="menu:create")],
        [InlineKeyboardButton("📋 همساتي", callback_data="menu:my"),
         InlineKeyboardButton("ℹ️ مساعدة", callback_data="menu:help")]
    ]
    if ADMIN_ID != 0 and update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ لوحة الإدارة", callback_data="menu:admin")])

    if update.message:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "📖 <b>طريقة الاستخدام</b>\n\nالهمسات السريعة عبر الـ Inline هي الأفضل للمحادثات، وتظهر كرسالة منبثقة (Alert) للمستلم لتوفير وقت الدخول للخاص.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="menu:home")]])
    )

# =========================================================
# 📝 INLINE MODE (FAST WHISPERS)
# =========================================================
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query: return
    
    user = update.inline_query.from_user
    w_id = make_id()
    
    audience = "first"
    target_username = ""
    
    # التحقق مما إذا كانت الهمسة موجهة لشخص معين
    if query.startswith("@") and " " in query:
        parts = query.split(" ", 1)
        target_username = parts[0].replace("@", "").lower()
        text = parts[1].strip()
        audience = "single"
    else:
        text = query
        
    if not text: return

    # حفظ الهمسة في الذاكرة المؤقتة (تنتقل لـ DB عند أول ضغطة)
    INLINE_CACHE[w_id] = {
        "sender_id": user.id,
        "sender_name": user.first_name,
        "text": text,
        "target": target_username,
        "created_at": now()
    }

    results = []
    if audience == "single":
        results.append(
            InlineQueryResultArticle(
                id=f"{w_id}_single",
                title=f"👤 همسة مخصصة لـ @{target_username}",
                description=f"الرسالة: {text}",
                input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(user.first_name)}) إلى @{target_username}</b>", parse_mode="HTML"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data=f"w:{w_id}_single")]])
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id=f"{w_id}_first",
                title="👁️ لأول شخص يفتحها",
                description=f"الرسالة: {text}",
                input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(user.first_name)}) لأول شخص يفتحها!</b>", parse_mode="HTML"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data=f"w:{w_id}_first")]])
            )
        )
        results.append(
            InlineQueryResultArticle(
                id=f"{w_id}_all",
                title="👥 للجميع",
                description=f"الرسالة: {text}",
                input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(user.first_name)}) للجميع.</b>", parse_mode="HTML"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data=f"w:{w_id}_all")]])
            )
        )

    await update.inline_query.answer(results, cache_time=0)

# =========================================================
# 🔓 OPEN ANY WHISPER (INLINE & ADVANCED)
# =========================================================
async def handle_open_whisper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data_parts = query.data.split(":")[1].split("_")
    w_id = data_parts[0]
    w_type = data_parts[1] if len(data_parts) > 1 else "advanced"

    data = await load_database()
    whisper = data["whispers"].get(w_id)

    # إذا لم تكن في قاعدة البيانات، ابحث في الذاكرة المؤقتة للإنلاين وانقلها
    if not whisper:
        if w_id in INLINE_CACHE:
            cached = INLINE_CACHE.pop(w_id)
            whisper = {
                "id": w_id,
                "sender_id": cached["sender_id"],
                "sender_name": cached["sender_name"],
                "content_type": "text",
                "text": cached["text"],
                "audience": w_type,
                "recipient_usernames": [cached["target"]] if cached["target"] else [],
                "opened_by": [],
                "expires_at": now() + DEFAULT_TTL
            }
            data["whispers"][w_id] = whisper
            await save_database(data)
        else:
            await query.answer("❌ الهمسة غير موجودة أو انتهت صلاحيتها.", show_alert=True)
            return

    # الراسل دائماً يرى همسته
    if user.id == whisper["sender_id"]:
        if whisper["content_type"] == "text" and len(whisper["text"]) <= 190:
            await query.answer(f"🤫 نص همستك:\n\n{whisper['text']}", show_alert=True)
        else:
            await query.answer("🤫 همستك تحتوي على وسائط أو نص طويل (موجودة في الخاص).", show_alert=True)
        return

    # التحقق من الصلاحيات بناءً على نوع الهمسة
    allowed = False
    audience = whisper.get("audience", "first")
    
    if audience == "all":
        allowed = True
    elif audience == "first":
        if not whisper["opened_by"] or user.id in whisper["opened_by"]:
            allowed = True
    elif audience == "single":
        username = (user.username or "").lower()
        if username and username in whisper.get("recipient_usernames", []):
            allowed = True

    if not allowed:
        await query.answer("🚫 هذه الهمسة ليست مخصصة لك، أو فتحها شخص آخر قبلك!", show_alert=True)
        return

    # تقديم الهمسة (Delivery)
    if whisper["content_type"] == "text":
        if len(whisper["text"]) <= 190:
            # نافذة منبثقة سريعة (أفضل تجربة مستخدم)
            await query.answer(f"🤫 الهمسة:\n\n{whisper['text']}", show_alert=True)
        else:
            # إرسال للخاص إذا كانت طويلة
            try:
                await context.bot.send_message(chat_id=user.id, text=f"🤫 <b>الهمسة:</b>\n\n{escape(whisper['text'])}", parse_mode="HTML")
                await query.answer("🤫 الهمسة طويلة جداً، أرسلتها لك في الخاص!", show_alert=True)
            except Forbidden:
                await query.answer("❗ الهمسة طويلة! يجب الدخول للبوت وإرسال /start أولاً لتتمكن من استلامها.", show_alert=True)
                return
    else:
        # إرسال الصور والصوت للخاص
        try:
            if whisper["content_type"] == "photo":
                await context.bot.send_photo(chat_id=user.id, photo=whisper["file_id"], caption=f"🤫 <b>الهمسة:</b>\n{whisper.get('caption','')}", parse_mode="HTML")
            elif whisper["content_type"] == "voice":
                await context.bot.send_voice(chat_id=user.id, voice=whisper["file_id"], caption="🤫 <b>همسة صوتية</b>", parse_mode="HTML")
            await query.answer("🤫 أرسلت لك الهمسة (الوسائط) في الخاص!", show_alert=True)
        except Forbidden:
            await query.answer("❗ يجب الدخول للبوت وإرسال /start أولاً لتتمكن من استلام الوسائط.", show_alert=True)
            return

    # تحديث قائمة من فتح الهمسة وإشعار الراسل
    if user.id not in whisper["opened_by"]:
        whisper["opened_by"].append(user.id)
        await save_database(data)
        
        # إشعار الفتح للراسل
        try:
            await context.bot.send_message(
                chat_id=whisper["sender_id"],
                text=f"🔔 <b>تم فتح همستك للتو!</b>\nبواسطة: <a href='tg://user?id={user.id}'>{escape(user.first_name)}</a>",
                parse_mode="HTML"
            )
        except Exception: pass

# =========================================================
# ⚙️ ADMIN MENU
# =========================================================
async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if DATA_FILE.exists():
        await update.callback_query.message.reply_document(document=open(DATA_FILE, "rb"), caption="📦 نسخة احتياطية من الهمسات.")
        await update.callback_query.answer("تم التصدير بنجاح.")

async def admin_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    doc = update.message.document
    if doc.file_name.endswith(".json"):
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(DATA_FILE)
        await update.message.reply_text("✅ تم استيراد وتحديث قاعدة البيانات بنجاح!")

# =========================================================
# 🚀 MENU ROUTER
# =========================================================
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "menu:home": await start(update, context)
    elif data == "menu:help": await show_help(update, context)
    elif data == "menu:admin" and update.effective_user.id == ADMIN_ID:
        await update.callback_query.edit_message_text(
            "⚙️ <b>لوحة الإدارة</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 تصدير البيانات (Export)", callback_data="admin:export")],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="menu:home")]
            ]), parse_mode="HTML"
        )
    elif data == "admin:export": await admin_export(update, context)

# =========================================================
# ▶️ MAIN RUNNER
# =========================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands & Callbacks
    app.add_handler(CommandHandler("start", start))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(CallbackQueryHandler(handle_open_whisper, pattern=r"^w:"))
    app.add_handler(CallbackQueryHandler(menu_router, pattern=r"^(menu|admin):"))
    
    # Import Document (Admin Only)
    app.add_handler(MessageHandler(filters.Document.ALL, admin_import))
    
    # Background Job
    app.job_queue.run_repeating(cleanup_job, interval=300, first=10) # ينظف كل 5 دقائق

    # Webhook Setup for Railway
    if WEBHOOK_URL:
        clean_url = WEBHOOK_URL.replace("https://", "").replace("http://", "").rstrip("/")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"https://{clean_url}/{BOT_TOKEN}"
        )
    else:
        app.run_polling()

if __name__ == "__main__":
    main()
