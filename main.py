# -*- coding: utf-8 -*-
"""
=========================================================
🤫 WHISPER BOT - FIXED & FULL ADVANCED VERSION
=========================================================
Python: 3.9+
Library: python-telegram-bot==20.8
=========================================================
"""

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
from telegram.error import TelegramError, Forbidden, BadRequest
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
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()

try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0
try:
    PORT = int(os.environ.get("PORT", "8080"))
except ValueError:
    PORT = 8080

# =========================================================
# 🛡️ LIMITS
# =========================================================
MAX_TEXT_LENGTH = int(os.environ.get("MAX_TEXT_LENGTH", "4000"))
MAX_WHISPERS = int(os.environ.get("MAX_WHISPERS", "100000"))
MAX_RECIPIENTS = int(os.environ.get("MAX_RECIPIENTS", "10"))
DEFAULT_TTL = int(os.environ.get("DEFAULT_TTL", str(7 * 24 * 60 * 60)))
MAX_SELF_DESTRUCT = int(os.environ.get("MAX_SELF_DESTRUCT", "86400"))
CREATE_LIMIT = int(os.environ.get("CREATE_LIMIT", "20"))
CREATE_WINDOW = int(os.environ.get("CREATE_WINDOW", "60"))

# =========================================================
# 📝 LOGGING
# =========================================================
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
INLINE_PENDING = {}
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
def user_name(user): return escape(user.first_name or "مستخدم")
def is_admin(user_id): return (ADMIN_ID != 0 and user_id == ADMIN_ID)
def make_id(): return uuid.uuid4().hex[:16]
def format_time(ts):
    if not ts: return "غير محدد"
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def parse_seconds(text):
    text = text.strip().lower()
    if not text: return None
    try:
        if text.endswith("s"): return int(text[:-1])
        if text.endswith("m"): return int(text[:-1]) * 60
        if text.endswith("h"): return int(text[:-1]) * 3600
        if text.endswith("d"): return int(text[:-1]) * 86400
        return int(text)
    except ValueError:
        return None

# =========================================================
# 🗄️ DATABASE
# =========================================================
def empty_database():
    return {"version": 3, "whispers": {}}

def validate_database(data):
    if not isinstance(data, dict): return False
    if not isinstance(data.get("whispers"), dict): return False
    return True

def normalize_database(data):
    if not validate_database(data): raise ValueError("Invalid database structure")
    result = empty_database()
    for whisper_id, w in data["whispers"].items():
        if not isinstance(w, dict): continue
        if not isinstance(w.get("sender_id"), int): continue
        if w.get("content_type") not in ("text", "photo", "voice"): continue
        
        recipients = w.get("recipient_ids", [])
        recipients = [int(x) for x in recipients if isinstance(x, int)]
        
        opened_by = w.get("opened_by", [])
        opened_by = [int(x) for x in opened_by if isinstance(x, int)]
        
        result["whispers"][whisper_id] = {
            "id": whisper_id,
            "sender_id": w["sender_id"],
            "sender_name": str(w.get("sender_name", "مستخدم"))[:100],
            "content_type": w["content_type"],
            "text": str(w.get("text", ""))[:MAX_TEXT_LENGTH],
            "file_id": w.get("file_id"),
            "caption": str(w.get("caption", ""))[:1000],
            "audience": w.get("audience", "first"),
            "recipient_ids": recipients[:MAX_RECIPIENTS],
            "recipient_usernames": [str(x).lower().lstrip("@") for x in w.get("recipient_usernames", []) if isinstance(x, str)][:MAX_RECIPIENTS],
            "anonymous": bool(w.get("anonymous", False)),
            "password": w.get("password"),
            "question": w.get("question"),
            "answer": w.get("answer"),
            "one_time": bool(w.get("one_time", False)),
            "self_destruct": int(w.get("self_destruct", 0) or 0),
            "available_at": int(w.get("available_at", 0) or 0),
            "expires_at": int(w.get("expires_at", now() + DEFAULT_TTL)),
            "button_text": str(w.get("button_text", "👁️ اضغط لقراءة الهمسة"))[:100],
            "opened_by": opened_by,
            "created_at": int(w.get("created_at", now())),
            "deleted": bool(w.get("deleted", False)),
            "delivered_messages": w.get("delivered_messages", []),
        }
    return result

def load_database_sync():
    if not DATA_FILE.exists(): return empty_database()
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return normalize_database(data)
    except Exception as exc:
        logger.exception("Database read failed")
        raise RuntimeError("database.json is corrupted") from exc

async def load_database():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, load_database_sync)

def atomic_save_sync(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    fd, temp_name = tempfile.mkstemp(prefix="database_", suffix=".tmp", dir=str(DATA_FILE.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())
        if DATA_FILE.exists():
            with DATA_FILE.open("rb") as src:
                with BACKUP_FILE.open("wb") as dst:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk: break
                        dst.write(chunk)
        os.replace(temp_path, DATA_FILE)
    finally:
        if temp_path.exists():
            try: temp_path.unlink()
            except Exception: pass

async def save_database(data):
    if not validate_database(data): raise ValueError("Invalid database")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, atomic_save_sync, data)

# =========================================================
# 🚦 RATE LIMIT & CLEANUP
# =========================================================
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
    async with DATA_LOCK:
        try:
            data = await load_database()
            changed = False
            current = now()
            for whisper_id in list(data["whispers"]):
                whisper = data["whispers"][whisper_id]
                if whisper["expires_at"] and whisper["expires_at"] <= current:
                    del data["whispers"][whisper_id]
                    changed = True
                    continue
                delivered = whisper.get("delivered_messages", [])
                remaining = []
                for item in delivered:
                    destruct_at = item.get("destruct_at", 0)
                    if destruct_at and destruct_at <= current:
                        try:
                            await context.bot.delete_message(chat_id=item["chat_id"], message_id=item["message_id"])
                        except TelegramError: pass
                    else:
                        remaining.append(item)
                if len(remaining) != len(delivered):
                    whisper["delivered_messages"] = remaining
                    changed = True
            if changed:
                await save_database(data)
                
            # تنظيف الذاكرة المؤقتة
            for w_id in list(INLINE_PENDING):
                if current - INLINE_PENDING[w_id]["created_at"] > 3600:
                    del INLINE_PENDING[w_id]
        except Exception:
            logger.exception("Cleanup job failed")

# =========================================================
# 🏠 START & HELP
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤫 إنشاء همسة متقدمة", callback_data="menu:create")],
        [InlineKeyboardButton("📋 همساتي", callback_data="menu:my"), InlineKeyboardButton("📊 إحصائياتي", callback_data="menu:stats")],
        [InlineKeyboardButton("ℹ️ طريقة الاستخدام", callback_data="menu:help")]
    ]
    if is_admin(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("⚙️ الإدارة", callback_data="menu:admin")])
    await update.message.reply_text(
        "🤫 <b>مرحبًا بك في بوت الهمسات</b>\n\n"
        "أنشئ همسة سرية وأرسلها لأي شخص. للحصول على خيارات متقدمة اضغط على (إنشاء همسة متقدمة).\n\n"
        "أو استخدم البوت مباشرة في أي محادثة بكتابة يوزر البوت ثم نص الهمسة.",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )

async def show_help(update, context):
    query = update.callback_query
    await query.edit_message_text(
        "📖 <b>طريقة الاستخدام</b>\n\n1️⃣ للهمسات السريعة: أكتب يوزر البوت مسافة رسالتك.\n2️⃣ للهمسات المتقدمة: اضغط «إنشاء همسة» من القائمة واتبع الخطوات.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="menu:home")]])
    )

# =========================================================
# 🤫 ADVANCED CREATE (ConversationHandler)
# =========================================================
async def create_start(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    CREATE_SESSIONS[user_id] = {"sender_id": user_id}
    keyboard = [
        [InlineKeyboardButton("📝 نص", callback_data="ctype:text"), InlineKeyboardButton("🖼️ صورة", callback_data="ctype:photo")],
        [InlineKeyboardButton("🎤 صوت", callback_data="ctype:voice")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="create:cancel")]
    ]
    await query.edit_message_text("🤫 <b>إنشاء همسة جديدة</b>\n\nاختر نوع الهمسة:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_TYPE

async def choose_content_type(update, context):
    query = update.callback_query
    await query.answer()
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    ctype = query.data.split(":", 1)[1]
    session["content_type"] = ctype
    
    if ctype == "text":
        await query.edit_message_text("📝 أرسل الآن نص الهمسة:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="create:cancel")]]))
        return CREATE_TEXT
    elif ctype == "photo":
        await query.edit_message_text("🖼️ أرسل الصورة التي تريد جعلها همسة:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="create:cancel")]]))
        return CREATE_MEDIA
    elif ctype == "voice":
        await query.edit_message_text("🎤 أرسل البصمة الصوتية:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="create:cancel")]]))
        return CREATE_MEDIA

async def receive_text(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    if not session: return ConversationHandler.END
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("❌ النص فارغ.")
        return CREATE_TEXT
    if len(text) > MAX_TEXT_LENGTH:
        await update.message.reply_text(f"❌ الحد الأقصى {MAX_TEXT_LENGTH} حرف.")
        return CREATE_TEXT
    session["text"] = text
    return await ask_audience(update, context)

async def receive_media(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    if not session: return ConversationHandler.END
    if session["content_type"] == "photo":
        if not update.message.photo:
            await update.message.reply_text("❌ أرسل صورة فقط.")
            return CREATE_MEDIA
        session["file_id"] = update.message.photo[-1].file_id
        session["caption"] = (update.message.caption or "")[:1000]
    elif session["content_type"] == "voice":
        if not update.message.voice:
            await update.message.reply_text("❌ أرسل بصمة صوتية فقط.")
            return CREATE_MEDIA
        session["file_id"] = update.message.voice.file_id
    return await ask_audience(update, context)

async def ask_audience(update, context):
    keyboard = [
        [InlineKeyboardButton("👁️ أول شخص", callback_data="aud:first"), InlineKeyboardButton("👥 الجميع", callback_data="aud:all")],
        [InlineKeyboardButton("👤 شخص محدد", callback_data="aud:single"), InlineKeyboardButton("👥 عدة أشخاص", callback_data="aud:multi")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="create:cancel")]
    ]
    text = "🎯 <b>من يستطيع قراءة الهمسة؟</b>"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_AUDIENCE

async def choose_audience(update, context):
    query = update.callback_query
    await query.answer()
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    audience = query.data.split(":", 1)[1]
    session["audience"] = audience
    
    if audience == "single":
        await query.edit_message_text("👤 أرسل معرف الشخص (بدون مسافات):\n\n<code>@username</code>", parse_mode=ParseMode.HTML)
        return CREATE_RECIPIENTS
    if audience == "multi":
        await query.edit_message_text("👥 أرسل معرفات الأشخاص، كل معرف في سطر.", parse_mode=ParseMode.HTML)
        return CREATE_RECIPIENTS
    return await ask_anonymous_message(update, context)

async def receive_recipients(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    if not session: return ConversationHandler.END
    usernames = []
    for line in update.message.text.splitlines():
        username = line.strip().lower().lstrip("@")
        if username and username.replace("_", "").isalnum() and username not in usernames:
            usernames.append(username)
    if not usernames:
        await update.message.reply_text("❌ لم أجد معرفًا صحيحًا.")
        return CREATE_RECIPIENTS
    session["recipient_usernames"] = usernames[:MAX_RECIPIENTS]
    return await ask_anonymous_message(update, context)

async def ask_anonymous_message(update, context):
    keyboard = [[InlineKeyboardButton("👻 نعم، مجهولة", callback_data="anon:yes"), InlineKeyboardButton("👤 إظهار اسمي", callback_data="anon:no")]]
    text = "👻 <b>هل تريد إخفاء هويتك؟</b>"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_ANONYMOUS

async def choose_anonymous(update, context):
    query = update.callback_query
    await query.answer()
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    session["anonymous"] = (query.data == "anon:yes")
    
    keyboard = [
        [InlineKeyboardButton("🔓 بدون حماية", callback_data="protect:none")],
        [InlineKeyboardButton("🔐 كلمة مرور", callback_data="protect:password")],
        [InlineKeyboardButton("❓ سؤال وإجابة", callback_data="protect:quiz")]
    ]
    await query.edit_message_text("🛡️ <b>اختر حماية الهمسة:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_PROTECTION

async def choose_protection(update, context):
    query = update.callback_query
    await query.answer()
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    protection = query.data.split(":", 1)[1]
    session["protection"] = protection
    
    if protection == "password":
        await query.edit_message_text("🔐 أرسل كلمة المرور:")
        return CREATE_PASSWORD
    if protection == "quiz":
        await query.edit_message_text("❓ أرسل السؤال:")
        return CREATE_QUESTION
    return await ask_onetime(update, context)

async def receive_password(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    if not session: return ConversationHandler.END
    if not update.message.text: return CREATE_PASSWORD
    session["password"] = update.message.text.strip()[:200]
    return await ask_onetime(update, context)

async def receive_question(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    if not session: return ConversationHandler.END
    session["question"] = (update.message.text or "")[:500]
    await update.message.reply_text("✍️ الآن أرسل الإجابة الصحيحة:")
    return CREATE_ANSWER

async def receive_answer(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    if not session: return ConversationHandler.END
    session["answer"] = (update.message.text or "").strip()[:200]
    return await ask_onetime(update, context)

async def ask_onetime(update, context):
    keyboard = [[InlineKeyboardButton("☝️ نعم، مرة واحدة", callback_data="once:yes"), InlineKeyboardButton("🔁 يمكن إعادة القراءة", callback_data="once:no")]]
    text = "☝️ <b>هل تسمح بالقراءة مرة واحدة فقط؟</b>"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_ONETIME

async def choose_onetime(update, context):
    query = update.callback_query
    await query.answer()
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    session["one_time"] = (query.data == "once:yes")
    
    keyboard = [
        [InlineKeyboardButton("🚫 بدون تدمير ذاتي", callback_data="destroy:0")],
        [InlineKeyboardButton("💣 بعد 10 ثوانٍ", callback_data="destroy:10"), InlineKeyboardButton("💣 بعد دقيقة", callback_data="destroy:60")]
    ]
    await query.edit_message_text("💣 <b>التدمير الذاتي للوسائط</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_SELF_DESTRUCT

async def choose_self_destruct(update, context):
    query = update.callback_query
    await query.answer()
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    session["self_destruct"] = int(query.data.split(":", 1)[1])
    
    keyboard = [[InlineKeyboardButton("⚡ الآن", callback_data="time:now")]]
    await query.edit_message_text("⏰ <b>متى تصبح الهمسة قابلة للفتح؟</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_TIME

async def choose_time(update, context):
    query = update.callback_query
    await query.answer()
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    session["available_at"] = 0
    return await ask_button(update, context)

async def ask_button(update, context):
    keyboard = [[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data="button:default")]]
    text = "✏️ <b>نص الزر</b>\n\nأرسل النص الذي سيظهر على زر الهمسة، أو اضغط الافتراضي:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_BUTTON

async def choose_default_button(update, context):
    query = update.callback_query
    await query.answer()
    session = CREATE_SESSIONS.get(query.from_user.id)
    if not session: return ConversationHandler.END
    session["button_text"] = "👁️ اضغط لقراءة الهمسة"
    return await confirm_whisper(update, context)

async def receive_button(update, context):
    session = CREATE_SESSIONS.get(update.effective_user.id)
    if not session: return ConversationHandler.END
    session["button_text"] = (update.message.text or "👁️ اضغط لقراءة الهمسة")[:100]
    return await confirm_whisper(update, context)

async def confirm_whisper(update, context):
    user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    session = CREATE_SESSIONS.get(user_id)
    if not session: return ConversationHandler.END
    
    text = f"📋 <b>مراجعة الهمسة</b>\n\n🔘 الزر: {escape(session.get('button_text', ''))}\n\nجاهز للإنشاء؟"
    keyboard = [
        [InlineKeyboardButton("✅ إنشاء الهمسة", callback_data="create:save")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="create:cancel")]
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CREATE_CONFIRM

async def save_created_whisper(update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    session = CREATE_SESSIONS.get(user.id)
    if not session: return ConversationHandler.END
    if not await rate_allowed(user.id):
        await query.edit_message_text("🚫 وصلت إلى حد إنشاء الهمسات مؤقتًا.")
        return ConversationHandler.END

    async with DATA_LOCK:
        try:
            data = await load_database()
            whisper_id = make_id()
            whisper = {
                "id": whisper_id,
                "sender_id": user.id,
                "sender_name": user.first_name or "مستخدم",
                "content_type": session["content_type"],
                "text": session.get("text", ""),
                "file_id": session.get("file_id"),
                "caption": session.get("caption", ""),
                "audience": session.get("audience", "first"),
                "recipient_usernames": session.get("recipient_usernames", []),
                "anonymous": bool(session.get("anonymous", False)),
                "password": session.get("password"),
                "question": session.get("question"),
                "answer": session.get("answer"),
                "one_time": bool(session.get("one_time", False)),
                "self_destruct": int(session.get("self_destruct", 0)),
                "available_at": 0,
                "expires_at": now() + DEFAULT_TTL,
                "button_text": session.get("button_text", "👁️ اضغط لقراءة الهمسة"),
                "opened_by": [],
                "created_at": now(),
                "deleted": False,
                "delivered_messages": []
            }
            data["whispers"][whisper_id] = whisper
            await save_database(data)
        except Exception:
            logger.exception("Could not save whisper")
            await query.edit_message_text("❌ حدث خطأ.")
            return ConversationHandler.END

    CREATE_SESSIONS.pop(user.id, None)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(whisper["button_text"], callback_data=f"open:{whisper_id}")]])
    await query.edit_message_text("✅ <b>تم إنشاء الهمسة!</b>\n\nاستخدم زر المشاركة لإرسالها.", reply_markup=keyboard, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def cancel_create(update, context):
    query = update.callback_query
    await query.answer()
    CREATE_SESSIONS.pop(query.from_user.id, None)
    await query.edit_message_text("❌ تم إلغاء إنشاء الهمسة.")
    return ConversationHandler.END

# =========================================================
# 📝 INLINE MODE
# =========================================================
async def inline_query(update, context):
    query = update.inline_query
    text = (query.query or "").strip()
    if not text: return
    
    recipient_usernames = []
    if text.startswith("@") and " " in text:
        parts = text.split(" ", 1)
        target = parts[0].replace("@", "").lower()
        text = parts[1].strip()
        if text: recipient_usernames.append(target)
        
    if not text or not await rate_allowed(query.from_user.id): return

    w_id = make_id()
    INLINE_PENDING[w_id] = {
        "sender_id": query.from_user.id,
        "sender_name": query.from_user.first_name or "مستخدم",
        "text": text,
        "recipient_usernames": recipient_usernames,
        "created_at": now()
    }

    results = []
    if recipient_usernames:
        results.append(
            InlineQueryResultArticle(
                id=f"{w_id}_single", title=f"👤 همسة مخصصة لـ @{recipient_usernames[0]}", description=f"الرسالة: {text}",
                input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(query.from_user.first_name)}) إلى @{recipient_usernames[0]}</b>", parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data=f"open:{w_id}_single")]])
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id=f"{w_id}_first", title="👁️ لأول شخص يفتحها", description=f"الرسالة: {text}",
                input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(query.from_user.first_name)}) لأول شخص يفتحها!</b>", parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data=f"open:{w_id}_first")]])
            )
        )
        results.append(
            InlineQueryResultArticle(
                id=f"{w_id}_all", title="👥 للجميع", description=f"الرسالة: {text}",
                input_message_content=InputTextMessageContent(f"🔒 <b>همسة سرية من ({escape(query.from_user.first_name)}) للجميع.</b>", parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁️ اضغط لقراءة الهمسة", callback_data=f"open:{w_id}_all")]])
            )
        )

    await query.answer(results, cache_time=0, is_personal=True)

# =========================================================
# 🔓 OPEN WHISPER (FIXED)
# =========================================================
async def open_whisper(update, context):
    query = update.callback_query
    user = query.from_user
    
    # Callback data could be "open:{w_id}" (from advanced) or "open:{w_id}_{audience}" (from inline)
    data_parts = query.data.split(":", 1)[1].split("_")
    w_id = data_parts[0]

    async with DATA_LOCK:
        try:
            data = await load_database()
            whisper = data["whispers"].get(w_id)
            
            # --- إذا مش في قاعدة البيانات، استوردها من الإنلاين ---
            if not whisper:
                pending = INLINE_PENDING.get(w_id)
                if not pending:
                    await query.answer("❌ هذه الهمسة غير موجودة أو منتهية الصلاحية.", show_alert=True)
                    return
                
                audience = data_parts[1] if len(data_parts) > 1 else "first"
                whisper = {
                    "id": w_id, "sender_id": pending["sender_id"], "sender_name": pending["sender_name"],
                    "content_type": "text", "text": pending["text"], "file_id": None, "caption": "",
                    "audience": audience, "recipient_ids": [], "recipient_usernames": pending.get("recipient_usernames", []),
                    "anonymous": False, "password": None, "question": None, "answer": None,
                    "one_time": False, "self_destruct": 0, "available_at": 0, "expires_at": now() + DEFAULT_TTL,
                    "button_text": "👁️ اضغط لقراءة الهمسة", "opened_by": [], "created_at": pending["created_at"],
                    "deleted": False, "delivered_messages": []
                }
                data["whispers"][w_id] = whisper
                INLINE_PENDING.pop(w_id, None)
                await save_database(data)
            
            # --- جلب بيانات الهمسة المفتوحة ---
            opened_by = whisper["opened_by"]
            
            # الراسل يشوف همسته ديما
            if user.id == whisper["sender_id"]:
                if whisper["content_type"] == "text" and len(whisper["text"]) <= 190:
                    await query.answer(f"🤫 نص همستك:\n\n{whisper['text']}", show_alert=True)
                else:
                    await query.answer("🤫 همستك تحتوي على وسائط أو نص طويل (تجدها في الخاص).", show_alert=True)
                return
                
            # الصلاحيات
            allowed = False
            audience = whisper["audience"]
            if audience == "all": allowed = True
            elif audience == "first":
                if not opened_by or user.id in opened_by: allowed = True
            elif audience in ("single", "multi"):
                username = (user.username or "").lower().lstrip("@")
                if user.id in whisper.get("recipient_ids", []) or (username and username in whisper.get("recipient_usernames", [])):
                    allowed = True
                    
            if not allowed:
                await query.answer("🚫 هذه الهمسة ليست مخصصة لك، أو فتحها شخص آخر قبلك!", show_alert=True)
                return
                
            if whisper["one_time"] and user.id in opened_by:
                await query.answer("☝️ لقد قرأت هذه الهمسة مسبقًا ولا يمكن فتحها مرة أخرى.", show_alert=True)
                return

            # الحماية (كلمة السر)
            if whisper.get("password") or whisper.get("question"):
                mode = "password" if whisper.get("password") else "quiz"
                UNLOCK_SESSIONS[user.id] = {"whisper_id": w_id, "mode": mode}
                try:
                    if mode == "password":
                        await context.bot.send_message(chat_id=user.id, text=f"🔐 <b>الهمسة محمية بكلمة مرور.</b>\n\nأرسل:\n<code>/unlock كلمة_المرور</code>", parse_mode=ParseMode.HTML)
                    else:
                        await context.bot.send_message(chat_id=user.id, text=f"❓ <b>سؤال:</b>\n{escape(whisper['question'])}\n\nأرسل:\n<code>/answer إجابتك</code>", parse_mode=ParseMode.HTML)
                    await query.answer("🔐 الهمسة محمية، راجع الخاص!", show_alert=True)
                except Forbidden:
                    await query.answer("❗ يجب الدخول للخاص وارسال /start أولاً لتتمكن من فك القفل.", show_alert=True)
                return

            # --- التوصيل المباشر كـ Alert بدون الحاجة للخاص (للنصوص القصيرة) ---
            is_simple_text = (whisper["content_type"] == "text" and len(whisper["text"]) <= 190 and whisper["self_destruct"] == 0)

            if is_simple_text:
                if user.id not in opened_by:
                    opened_by.append(user.id)
                    whisper["opened_by"] = opened_by
                    await save_database(data)
                    # إشعار الراسل
                    try:
                        await context.bot.send_message(chat_id=whisper["sender_id"], text=f"🔔 <b>تم فتح همستك الآن!</b>\n\n👤 بواسطة: <a href=\"tg://user?id={user.id}\">{escape(user.first_name)}</a>", parse_mode=ParseMode.HTML)
                    except TelegramError: pass
                    
                await query.answer(f"🤫 الهمسة:\n\n{whisper['text']}", show_alert=True)
            else:
                # للوسائط والنصوص الطويلة والتدمير الذاتي (الخاص ضروري)
                try:
                    await deliver_whisper(context, whisper, user, data)
                    if user.id not in opened_by:
                        opened_by.append(user.id)
                        whisper["opened_by"] = opened_by
                        await save_database(data)
                    await query.answer("🤫 تم إرسال الهمسة لك في الخاص.", show_alert=True)
                except Forbidden:
                    await query.answer("❗ يجب أن تدخل للبوت وتضغط /start أولاً لتتمكن من استلام هذه الهمسة (وسائط/طويلة).", show_alert=True)

        except Exception:
            logger.exception("Open whisper failed")
            await query.answer("❌ حدث خطأ أثناء فتح الهمسة.", show_alert=True)

async def deliver_whisper(context, whisper, user, data):
    display_sender = "مجهول" if whisper["anonymous"] else whisper["sender_name"]
    header = f"🤫 <b>همسة سرية</b>\n\nمن: <b>{escape(display_sender)}</b>\n\n"
    ctype = whisper["content_type"]
    sent = None
    
    if ctype == "text":
        sent = await context.bot.send_message(chat_id=user.id, text=(header + escape(whisper["text"])), parse_mode=ParseMode.HTML)
    elif ctype == "photo":
        sent = await context.bot.send_photo(chat_id=user.id, photo=whisper["file_id"], caption=(header + escape(whisper.get("caption", ""))), parse_mode=ParseMode.HTML)
    elif ctype == "voice":
        sent = await context.bot.send_voice(chat_id=user.id, voice=whisper["file_id"], caption=header, parse_mode=ParseMode.HTML)

    if sent and whisper["self_destruct"] > 0:
        destruct_at = now() + whisper["self_destruct"]
        whisper["delivered_messages"].append({"user_id": user.id, "chat_id": sent.chat_id, "message_id": sent.message_id, "destruct_at": destruct_at})
        asyncio.create_task(destroy_message_later(context, sent.chat_id, sent.message_id, whisper["self_destruct"]))

    # إشعار الراسل
    if whisper["sender_id"] != user.id:
        try:
            await context.bot.send_message(chat_id=whisper["sender_id"], text=f"🔔 <b>تم فتح همستك الآن!</b>\n\n👤 بواسطة: <a href=\"tg://user?id={user.id}\">{escape(user.first_name)}</a>", parse_mode=ParseMode.HTML)
        except TelegramError: pass

async def destroy_message_later(context, chat_id, message_id, seconds):
    await asyncio.sleep(seconds)
    try: await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError: pass

async def unlock_command(update, context):
    user_id = update.effective_user.id
    session = UNLOCK_SESSIONS.get(user_id)
    if not session:
        await update.message.reply_text("❌ لا توجد همسة تنتظر الفتح.")
        return
    whisper_id = session["whisper_id"]
    supplied = " ".join(context.args).strip()
    
    async with DATA_LOCK:
        data = await load_database()
        whisper = data["whispers"].get(whisper_id)
        if not whisper:
            await update.message.reply_text("❌ الهمسة غير موجودة.")
            return
            
        if session["mode"] == "password" and supplied != whisper["password"]:
            await update.message.reply_text("❌ كلمة المرور خاطئة.")
            return
        elif session["mode"] == "quiz" and supplied.lower() != whisper["answer"].strip().lower():
            await update.message.reply_text("❌ إجابة خاطئة.")
            return
            
        await deliver_whisper(context, whisper, update.effective_user, data)
        if user_id not in whisper["opened_by"]:
            whisper["opened_by"].append(user_id)
            await save_database(data)
        UNLOCK_SESSIONS.pop(user_id, None)

# =========================================================
# 📋 ADMIN & STATS MENUS
# =========================================================
async def menu_callback(update, context):
    query = update.callback_query
    data = query.data
    if data == "menu:home": await start(update, context)
    elif data == "menu:create": await create_start(update, context)
    elif data == "menu:help": await show_help(update, context)
    elif data == "menu:admin":
        if is_admin(query.from_user.id):
            await query.edit_message_text(
                "⚙️ <b>لوحة الإدارة</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 تصدير", callback_data="admin:export")],
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="menu:home")]
                ]), parse_mode=ParseMode.HTML
            )
    elif data == "admin:export" and is_admin(query.from_user.id):
        if DATA_FILE.exists():
            await context.bot.send_document(chat_id=query.from_user.id, document=str(DATA_FILE), caption="📦 قاعدة البيانات.")
            await query.answer("تم الإرسال!")

async def import_document(update, context):
    if not is_admin(update.effective_user.id): return
    doc = update.message.document
    if doc.file_name.endswith(".json"):
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(DATA_FILE)
        await update.message.reply_text("✅ تم التحديث بنجاح!")

# =========================================================
# 🚀 MAIN RUNNER
# =========================================================
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_start, pattern=r"^menu:create$")],
        states={
            CREATE_TYPE: [CallbackQueryHandler(choose_content_type, pattern=r"^ctype:")],
            CREATE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
            CREATE_MEDIA: [MessageHandler(filters.PHOTO | filters.VOICE, receive_media)],
            CREATE_AUDIENCE: [CallbackQueryHandler(choose_audience, pattern=r"^aud:")],
            CREATE_RECIPIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_recipients)],
            CREATE_ANONYMOUS: [CallbackQueryHandler(choose_anonymous, pattern=r"^anon:")],
            CREATE_PROTECTION: [CallbackQueryHandler(choose_protection, pattern=r"^protect:")],
            CREATE_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
            CREATE_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)],
            CREATE_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_answer)],
            CREATE_ONETIME: [CallbackQueryHandler(choose_onetime, pattern=r"^once:")],
            CREATE_SELF_DESTRUCT: [CallbackQueryHandler(choose_self_destruct, pattern=r"^destroy:")],
            CREATE_TIME: [CallbackQueryHandler(choose_time, pattern=r"^time:")],
            CREATE_BUTTON: [CallbackQueryHandler(choose_default_button, pattern=r"^button:default$"), MessageHandler(filters.TEXT & ~filters.COMMAND, receive_button)],
            CREATE_CONFIRM: [CallbackQueryHandler(save_created_whisper, pattern=r"^create:save$"), CallbackQueryHandler(cancel_create, pattern=r"^create:cancel$")]
        },
        fallbacks=[CallbackQueryHandler(cancel_create, pattern=r"^create:cancel$"), CommandHandler("cancel", cancel_create)],
        allow_reentry=True
    )
    application.add_handler(conversation)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("unlock", unlock_command))
    application.add_handler(CommandHandler("answer", unlock_command))
    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(CallbackQueryHandler(open_whisper, pattern=r"^open:"))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^(menu|admin):"))
    application.add_handler(MessageHandler(filters.Document.ALL, import_document))

    application.job_queue.run_repeating(cleanup_job, interval=60, first=30)

    clean_url = WEBHOOK_URL.replace("https://", "").replace("http://", "").rstrip("/")
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN, webhook_url=f"https://{clean_url}/{BOT_TOKEN}")

if __name__ == "__main__":
    main()
