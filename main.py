# -*- coding: utf-8 -*-
import os
import json
import time
import uuid
import html
import asyncio
import logging
import tempfile
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
BACKUP_FILE = Path(os.environ.get("BACKUP_FILE", "database.json.bak"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", "8080"))

MAX_TEXT_LENGTH = 4000
DEFAULT_TTL = 7 * 24 * 60 * 60
CREATE_LIMIT = 20
CREATE_WINDOW = 60

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================================================
# 🔒 LOCKS & MEMORY
# =========================================================
DATA_LOCK = asyncio.Lock()
RATE_LIMIT_LOCK = asyncio.Lock()

CREATE_SESSIONS = {}
UNLOCK_SESSIONS = {}
INLINE_PENDING = {}
CREATE_HISTORY = defaultdict(deque)

(
    CREATE_TYPE, CREATE_TEXT, CREATE_MEDIA, CREATE_AUDIENCE,
    CREATE_RECIPIENTS, CREATE_ANONYMOUS, CREATE_PROTECTION,
    CREATE_PASSWORD, CREATE_QUESTION, CREATE_ANSWER,
    CREATE_ONETIME, CREATE_SELF_DESTRUCT, CREATE_TIME,
    CREATE_BUTTON, CREATE_CONFIRM,
) = range(15)

def now(): return int(time.time())
def escape(text): return html.escape(str(text))
def make_id(): return uuid.uuid4().hex[:16]

# =========================================================
# 🗄️ DATABASE 
# =========================================================
def empty_database():
    return {"whispers": {}}

async def load_database():
    if not DATA_FILE.exists(): return empty_database()
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return empty_database()

async def save_database(data):
    async with DATA_LOCK:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_path = DATA_FILE.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_path.replace(DATA_FILE)

async def rate_allowed(user_id):
    current = time.monotonic()
    async with RATE_LIMIT_LOCK:
        history = CREATE_HISTORY[user_id]
        while history and (current - history[0] > CREATE_WINDOW):
            history.popleft()
        if len(history) >= CREATE_LIMIT: return False
        history.append(current)
        return True

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    data = await load_database()
    changed = False
    current = now()
    for w_id in list(data["whispers"]):
        w = data["whispers"][w_id]
        if w.get("expires_at", 0) <= current:
            del data["whispers"][w_id]
            changed = True
    if changed:
        await save_database(data)
    for w_id in list(INLINE_PENDING):
        if current - INLINE_PENDING[w_id]["created_at"] > 3600:
            del INLINE_PENDING[w_id]

# =========================================================
# 🏠 START & HELP
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤫 <b>مرحبًا بك في بوت الهمسات!</b>\n\n"
        "لإنشاء همسة سريعة، اكتب يوزر البوت مسافة ثم رسالتك في أي محادثة.\n\n"
        "لإنشاء همسة بخيارات متقدمة (كلمة سر، وسائط..)، اضغط الزر بالأسفل."
    )
    keyboard = [[InlineKeyboardButton("🤫 إنشاء همسة متقدمة", callback_data="menu:create")]]
    if update.message:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# =========================================================
# 🤫 ADVANCED CREATE (Fixed Share Button)
# =========================================================
async def create_start(update, context):
    query = update.callback_query
    CREATE_SESSIONS[query.from_user.id] = {"sender_id": query.from_user.id}
    keyboard = [
        [InlineKeyboardButton("📝 نص", callback_data="ctype:text"), InlineKeyboardButton("🖼️ صورة", callback_data="ctype:photo")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="create:cancel")]
    ]
    await query.edit_message_text("اختر نوع الهمسة:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CREATE_TYPE

async def choose_content_type(update, context):
    query = update.callback_query
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    session["content_type"] = query.data.split(":")[1]
    if session["content_type"] == "text":
        await query.edit_message_text("📝 أرسل الآن نص الهمسة:")
        return CREATE_TEXT
    else:
        await query.edit_message_text("🖼️ أرسل الصورة:")
        return CREATE_MEDIA

async def receive_text(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    session["text"] = update.message.text.strip()
    return await confirm_whisper(update, context)

async def receive_media(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    if not update.message.photo: return CREATE_MEDIA
    session["file_id"] = update.message.photo[-1].file_id
    session["caption"] = update.message.caption or ""
    return await confirm_whisper(update, context)

async def confirm_whisper(update, context):
    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton("✅ حفظ وإنشاء", callback_data="create:save")]]
    await update.message.reply_text("هل أنت جاهز لإنشاء الهمسة؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return CREATE_CONFIRM

async def save_created_whisper(update, context):
    query = update.callback_query
    user = query.from_user
    session = CREATE_SESSIONS.get(user.id)
    if not session: return ConversationHandler.END

    data = await load_database()
    w_id = make_id()
    data["whispers"][w_id] = {
        "id": w_id, "sender_id": user.id, "sender_name": user.first_name,
        "content_type": session["content_type"], "text": session.get("text", ""),
        "file_id": session.get("file_id"), "caption": session.get("caption", ""),
        "audience": "first", "recipient_usernames": [], "password": None, 
        "self_destruct": 0, "expires_at": now() + DEFAULT_TTL,
        "button_text": "👁️ اضغط لقراءة الهمسة", "opened_by": []
    }
    await save_database(data)
    CREATE_SESSIONS.pop(user.id, None)

    # 🟢 الحل السحري لمشكلة زر المشاركة: استخدام switch_inline_query
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔗 مشاركة الهمسة", switch_inline_query=w_id)
    ]])
    await query.edit_message_text(
        "✅ <b>تم حفظ الهمسة بنجاح!</b>\n\nاضغط على زر المشاركة بالأسفل لإرسالها لأي شخص.", 
        reply_markup=keyboard, parse_mode="HTML"
    )
    return ConversationHandler.END

async def cancel_create(update, context):
    CREATE_SESSIONS.pop(update.callback_query.from_user.id, None)
    await update.callback_query.edit_message_text("تم الإلغاء.")
    return ConversationHandler.END

# =========================================================
# 📝 INLINE MODE (Fast & Advanced Sharing fixed)
# =========================================================
async def inline_query(update, context):
    query = update.inline_query
    text = (query.query or "").strip()
    if not text: return

    # 🟢 إذا كان المستخدم يحاول مشاركة همسة متقدمة (يتم التعرف عليها عبر المعرف المكون من 16 حرف)
    if len(text) == 16:
        data = await load_database()
        if text in data["whispers"]:
            w = data["whispers"][text]
            results = [
                InlineQueryResultArticle(
                    id=text,
                    title="🔗 إرسال همستك المتقدمة",
                    description="اضغط هنا لإرسال الهمسة للدردشة",
                    input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(w['sender_name'])})</b>", parse_mode="HTML"),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(w["button_text"], callback_data=f"open:{text}")]])
                )
            ]
            await query.answer(results, cache_time=0)
            return

    # 🟢 إذا كانت همسة سريعة (كتابة نص مباشر)
    recipient_usernames = []
    display_text = text
    if text.startswith("@") and " " in text:
        parts = text.split(" ", 1)
        target = parts[0].replace("@", "").lower()
        display_text = parts[1].strip()
        if display_text: recipient_usernames.append(target)
        
    if not display_text or not await rate_allowed(query.from_user.id): return

    w_id = make_id()
    INLINE_PENDING[w_id] = {
        "sender_id": query.from_user.id, "sender_name": query.from_user.first_name,
        "text": display_text, "recipient_usernames": recipient_usernames, "created_at": now()
    }

    results = []
    if recipient_usernames:
        results.append(
            InlineQueryResultArticle(
                id=f"{w_id}_single", title=f"👤 همسة لـ @{recipient_usernames[0]}", description=display_text,
                input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(query.from_user.first_name)}) إلى @{recipient_usernames[0]}</b>", parse_mode="HTML"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data=f"open:{w_id}_single")]])
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id=f"{w_id}_first", title="👁️ لأول شخص يفتحها", description=display_text,
                input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(query.from_user.first_name)}) لأول شخص يفتحها!</b>", parse_mode="HTML"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data=f"open:{w_id}_first")]])
            )
        )
    await query.answer(results, cache_time=0, is_personal=True)

# =========================================================
# 🔓 OPEN WHISPER (Fixed Alert Text)
# =========================================================
async def open_whisper(update, context):
    query = update.callback_query
    user = query.from_user
    data_parts = query.data.split(":", 1)[1].split("_")
    w_id = data_parts[0]

    data = await load_database()
    whisper = data["whispers"].get(w_id)

    if not whisper:
        pending = INLINE_PENDING.get(w_id)
        if not pending:
            await query.answer("❌ الهمسة غير موجودة أو انتهت صلاحيتها.", show_alert=True)
            return
        audience = data_parts[1] if len(data_parts) > 1 else "first"
        whisper = {
            "id": w_id, "sender_id": pending["sender_id"], "sender_name": pending["sender_name"],
            "content_type": "text", "text": pending["text"], "file_id": None, "caption": "",
            "audience": audience, "recipient_usernames": pending["recipient_usernames"],
            "self_destruct": 0, "expires_at": now() + DEFAULT_TTL, "opened_by": []
        }
        data["whispers"][w_id] = whisper
        INLINE_PENDING.pop(w_id, None)
        await save_database(data)

    opened_by = whisper["opened_by"]

    if user.id == whisper["sender_id"]:
        # 🟢 تنسيق جميل للراسل بدل ظهور النص فقط
        await query.answer(f"🤫 محتوى همستك:\n\n{whisper['text']}", show_alert=True)
        return

    allowed = False
    if whisper["audience"] == "first":
        if not opened_by or user.id in opened_by: allowed = True
    elif whisper["audience"] == "single":
        username = (user.username or "").lower().lstrip("@")
        if username in whisper["recipient_usernames"]: allowed = True

    if not allowed:
        await query.answer("🚫 هذه الهمسة ليست مخصصة لك، أو فتحها شخص قبلك!", show_alert=True)
        return

    if whisper["content_type"] == "text" and len(whisper["text"]) <= 190:
        if user.id not in opened_by:
            whisper["opened_by"].append(user.id)
            await save_database(data)
        
        # 🟢 تنسيق جميل للمستلم
        await query.answer(f"🤫 الهمسة:\n\n{whisper['text']}", show_alert=True)
    else:
        try:
            if whisper["content_type"] == "text":
                await context.bot.send_message(chat_id=user.id, text=f"🤫 <b>الهمسة:</b>\n\n{escape(whisper['text'])}", parse_mode="HTML")
            elif whisper["content_type"] == "photo":
                await context.bot.send_photo(chat_id=user.id, photo=whisper["file_id"], caption=whisper["caption"])
            
            if user.id not in opened_by:
                whisper["opened_by"].append(user.id)
                await save_database(data)
            await query.answer("تم إرسال الهمسة (المطولة/الوسائط) لك في الخاص!", show_alert=True)
        except Forbidden:
            await query.answer("❗ يجب أن تدخل للبوت وتضغط /start أولاً لتتمكن من استلام الوسائط.", show_alert=True)

# =========================================================
# 🚀 MAIN RUNNER
# =========================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_start, pattern=r"^menu:create$")],
        states={
            CREATE_TYPE: [CallbackQueryHandler(choose_content_type, pattern=r"^ctype:")],
            CREATE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
            CREATE_MEDIA: [MessageHandler(filters.PHOTO, receive_media)],
            CREATE_CONFIRM: [CallbackQueryHandler(save_created_whisper, pattern=r"^create:save$")]
        },
        fallbacks=[CallbackQueryHandler(cancel_create, pattern=r"^create:cancel$")],
        allow_reentry=True
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(CallbackQueryHandler(open_whisper, pattern=r"^open:"))

    if WEBHOOK_URL:
        clean_url = WEBHOOK_URL.replace("https://", "").replace("http://", "").rstrip("/")
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN, webhook_url=f"https://{clean_url}/{BOT_TOKEN}")
    else:
        app.run_polling()

if __name__ == "__main__":
    main()
