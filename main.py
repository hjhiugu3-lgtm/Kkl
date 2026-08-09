
import os
import json
import logging
import asyncio
import secrets
import hashlib
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InlineQueryResultArticle, InputTextMessageContent,
    ForceReply, BotCommand
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, InlineQueryHandler,
    CallbackQueryHandler, MessageHandler, ContextTypes, filters
)

# =========================
# Configuration
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
PORT = int(os.getenv("PORT", "8080") or 8080)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
DATA_FILE = Path(os.getenv("DATA_FILE", "database.json"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is missing")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("whisper-bot")

DB_LOCK = asyncio.Lock()
BOT_USERNAME = ""


# =========================
# Database
# =========================
DEFAULT_DB = {"version": 2, "whispers": {}, "users": {}}


def load_db_sync():
    if not DATA_FILE.exists():
        return json.loads(json.dumps(DEFAULT_DB))
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("database root is not an object")
        data.setdefault("version", 2)
        data.setdefault("whispers", {})
        data.setdefault("users", {})
        return data
    except Exception:
        log.exception("Could not load database")
        # Do not overwrite a possibly recoverable broken file.
        broken = DATA_FILE.with_suffix(".broken.json")
        try:
            DATA_FILE.replace(broken)
        except Exception:
            pass
        return json.loads(json.dumps(DEFAULT_DB))


def save_db_sync(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, DATA_FILE)


async def db_update(mutator):
    async with DB_LOCK:
        db = load_db_sync()
        result = mutator(db)
        save_db_sync(db)
        return result


async def db_read():
    async with DB_LOCK:
        return load_db_sync()


def now_ts():
    return datetime.now(timezone.utc).timestamp()


def iso(ts):
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def new_id():
    return secrets.token_urlsafe(9).replace("-", "").replace("_", "")


def hash_password(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def valid_username(u):
    if not u:
        return None
    u = u.strip()
    if u.startswith("@"):
        u = u[1:]
    if not u or len(u) > 32:
        return None
    if not all(c.isalnum() or c == "_" for c in u):
        return None
    return u.lower()


# =========================
# Helpers
# =========================
def user_display(user):
    if user.username:
        return f"@{user.username}"
    return user.full_name or str(user.id)


def allowed_user(whisper, user):
    if user.id == whisper["sender_id"]:
        return True

    targets = whisper.get("targets", [])
    if not targets:
        return whisper.get("mode") in ("first", "all")

    username = (user.username or "").lower()
    return any(
        (t.get("username") or "").lower() == username or
        t.get("id") == user.id
        for t in targets
    )


def get_target_ids(whisper):
    return [t["id"] for t in whisper.get("targets", []) if t.get("id")]


def format_secret_text(whisper):
    text = whisper.get("text") or ""
    if whisper.get("anonymous"):
        return text
    return text


def public_caption(whisper):
    if whisper.get("anonymous"):
        return "🤫 همسة من مجهول"
    return f"🤫 همسة من {whisper.get('sender_name', 'مستخدم')}"


def build_button(whisper):
    label = whisper.get("button_text") or "👁️ اضغط لقراءة الهمسة"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label[:64], callback_data=f"w:{whisper['id']}")]
    ])


def parse_inline_options(query):
    """
    Supported:
      to:@user,@user message
      pass:1234 message
      ttl:10 message
      once message
      anon message
      btn:اضغط message
      at:2026-08-10T23:00:00+00:00 message

    Prefixes are removed from the secret itself.
    """
    q = query.strip()
    opts = {
        "mode": "first",
        "targets": [],
        "password": None,
        "quiz_question": None,
        "quiz_answer": None,
        "ttl": None,
        "once": False,
        "anonymous": False,
        "button_text": None,
        "unlock_at": None,
    }

    import re

    # to:@a,@b
    m = re.match(r"^\s*to:([^\s]+)\s+(.*)$", q, re.S | re.I)
    if m:
        names = m.group(1).split(",")
        for n in names:
            u = valid_username(n)
            if u:
                opts["targets"].append({"username": u, "id": None})
        opts["mode"] = "targeted"
        q = m.group(2).strip()

    # pass:value
    m = re.search(r"(?:^|\s)pass:([^\s]+)", q, re.I)
    if m:
        opts["password"] = m.group(1)
        q = (q[:m.start()] + q[m.end():]).strip()

    # quiz:السؤال|الإجابة
    m = re.search(r"(?:^|\s)quiz:(.*?)\|([^\n]+)", q, re.I | re.S)
    if m:
        question = m.group(1).strip()
        answer = m.group(2).strip()
        if question and answer:
            opts["quiz_question"] = question
            opts["quiz_answer"] = answer
            q = (q[:m.start()] + q[m.end():]).strip()

    # ttl:seconds
    m = re.search(r"(?:^|\s)ttl:(\d+)", q, re.I)
    if m:
        seconds = max(1, min(int(m.group(1)), 86400))
        opts["ttl"] = seconds
        q = (q[:m.start()] + q[m.end():]).strip()

    if re.search(r"(?:^|\s)once(?:\s|$)", q, re.I):
        opts["once"] = True
        q = re.sub(r"(?:^|\s)once(?=\s|$)", " ", q, flags=re.I).strip()

    if re.search(r"(?:^|\s)anon(?:\s|$)", q, re.I):
        opts["anonymous"] = True
        q = re.sub(r"(?:^|\s)anon(?=\s|$)", " ", q, flags=re.I).strip()

    m = re.search(r"(?:^|\s)btn:([^\s]+(?:\s+[^\s]+){0,4})", q, re.I)
    if m:
        opts["button_text"] = m.group(1).strip()
        q = (q[:m.start()] + q[m.end():]).strip()

    # ISO datetime after at:
    m = re.search(r"(?:^|\s)at:([^\s]+)", q, re.I)
    if m:
        raw = m.group(1)
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            opts["unlock_at"] = dt.timestamp()
        except ValueError:
            pass
        q = (q[:m.start()] + q[m.end():]).strip()

    # all mode can be requested explicitly
    if re.search(r"(?:^|\s)all(?:\s|$)", q, re.I):
        opts["mode"] = "all"
        q = re.sub(r"(?:^|\s)all(?=\s|$)", " ", q, flags=re.I).strip()

    return opts, q.strip()


async def create_whisper(
    sender,
    text="",
    mode="first",
    targets=None,
    password=None,
    quiz_question=None,
    quiz_answer=None,
    ttl=None,
    once=False,
    anonymous=False,
    button_text=None,
    unlock_at=None,
    media=None,
):
    wid = new_id()
    created = now_ts()
    expires_at = None
    if ttl:
        # ttl means from first successful read, handled separately.
        expires_at = None

    whisper = {
        "id": wid,
        "sender_id": sender.id,
        "sender_name": sender.full_name or sender.first_name or "مستخدم",
        "created_at": created,
        "mode": mode,
        "targets": targets or [],
        "text": text,
        "anonymous": bool(anonymous),
        "button_text": button_text or "👁️ اضغط لقراءة الهمسة",
        "password_hash": hash_password(password) if password else None,
        "quiz_question": quiz_question,
        "quiz_answer_hash": hash_password(quiz_answer) if quiz_answer else None,
        "once": bool(once),
        "ttl": int(ttl) if ttl else None,
        "unlock_at": unlock_at,
        "expires_at": expires_at,
        "opened_by": [],
        "read_count": 0,
        "deleted": False,
        "media": media,
        "pending_unlock": {},
    }

    def mut(db):
        db["whispers"][wid] = whisper
        db["users"].setdefault(str(sender.id), {"created": 0})
        db["users"][str(sender.id)]["created"] = db["users"][str(sender.id)].get("created", 0) + 1

    await db_update(mut)
    return whisper


# =========================
# /start and menus
# =========================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("unlock_"):
        wid = args[0][7:]
        await unlock_start(update, wid)
        return

    text = (
        "🤫 <b>بوت الهمسات السرية</b>\n\n"
        "أنشئ همسة واستخدمها داخل أي محادثة عبر الإنلاين.\n\n"
        "<b>مثال:</b>\n"
        "<code>@اسم_البوت سرٌّ بيننا</code>\n\n"
        "<b>خيارات متقدمة:</b>\n"
        "• <code>to:@username</code> — لشخص محدد\n"
        "• <code>pass:1234</code> — كلمة سر\n"
        "• <code>quiz:2+2؟|4</code> — سؤال وإجابة\n"
        "• <code>ttl:10</code> — حذف بعد 10 ثوانٍ من القراءة\n"
        "• <code>once</code> — قراءة واحدة\n"
        "• <code>anon</code> — مجهولة\n"
        "• <code>all</code> — للجميع\n"
        "• <code>at:2026-08-10T23:00:00+00:00</code> — كبسولة زمنية\n"
        "• <code>btn:اضغط للضرورة</code> — نص الزر\n\n"
        "📋 /my — إدارة همساتك\n"
        "🆕 /new — إنشاء همسة من الخاص\n"
        "📤 /export — نسخة احتياطية للمطور"
    )

    if user.id == ADMIN_ID:
        text += "\n\n⚙️ أنت المطور."

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def my_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = await db_read()
    items = [
        w for w in db["whispers"].values()
        if w.get("sender_id") == uid and not w.get("deleted")
    ]
    items.sort(key=lambda x: x.get("created_at", 0), reverse=True)

    if not items:
        await update.message.reply_text("📭 لا توجد لديك همسات نشطة.")
        return

    lines = ["📋 <b>همساتك النشطة</b>\n"]
    buttons = []
    for w in items[:20]:
        status = "مفتوحة" if w["opened_by"] else "لم تُفتح"
        lines.append(
            f"• <code>{w['id']}</code> — {status} — "
            f"{w.get('read_count', 0)} قراءة"
        )
        buttons.append([
            InlineKeyboardButton(
                f"🗑️ حذف {w['id']}",
                callback_data=f"d:{w['id']}"
            )
        ])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استخدم: /delete ID")
        return
    wid = context.args[0]
    uid = update.effective_user.id

    def mut(db):
        w = db["whispers"].get(wid)
        if not w or w.get("sender_id") != uid:
            return False
        w["deleted"] = True
        return True

    ok = await db_update(mut)
    await update.message.reply_text("✅ تم حذف الهمسة." if ok else "❌ الهمسة غير موجودة.")


# =========================
# Inline
# =========================
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    iq = update.inline_query
    query = iq.query.strip()

    if not query:
        await iq.answer([], cache_time=0, is_personal=True)
        return

    opts, text = parse_inline_options(query)
    if not text:
        await iq.answer([], cache_time=0, is_personal=True)
        return

    sender = iq.from_user

    # The inline query creates a whisper immediately.
    whisper = await create_whisper(
        sender=sender,
        text=text,
        mode=opts["mode"],
        targets=opts["targets"],
        password=opts["password"],
        quiz_question=opts["quiz_question"],
        quiz_answer=opts["quiz_answer"],
        ttl=opts["ttl"],
        once=opts["once"],
        anonymous=opts["anonymous"],
        button_text=opts["button_text"],
        unlock_at=opts["unlock_at"],
    )

    desc = []
    if opts["mode"] == "targeted":
        desc.append("🎯 مخصصة")
    elif opts["mode"] == "all":
        desc.append("👥 للجميع")
    else:
        desc.append("👁️ لأول شخص")

    if opts["password"]:
        desc.append("🔐 كلمة سر")
    if opts["quiz_question"]:
        desc.append("🧩 سؤال")
    if opts["once"]:
        desc.append("1️⃣ قراءة واحدة")
    if opts["ttl"]:
        desc.append(f"💣 {opts['ttl']}ث")
    if opts["unlock_at"]:
        desc.append("⏳ مؤجلة")
    if opts["anonymous"]:
        desc.append("🕵️ مجهولة")

    safe_title = " • ".join(desc)
    preview = text[:80].replace("\n", " ")

    results = [
        InlineQueryResultArticle(
            id=whisper["id"],
            title=safe_title,
            description=preview,
            input_message_content=InputTextMessageContent(
                public_caption(whisper),
                parse_mode=ParseMode.HTML
            ),
            reply_markup=build_button(whisper)
        )
    ]

    await iq.answer(
        results,
        cache_time=0,
        is_personal=True
    )


# =========================
# Reading / callbacks
# =========================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""

    if data.startswith("w:"):
        await open_whisper(q, context, data[2:])
    elif data.startswith("d:"):
        await dashboard_delete(q, data[2:])


async def open_whisper(q, context, wid):
    user = q.from_user
    db = await db_read()
    w = db["whispers"].get(wid)

    if not w or w.get("deleted"):
        await q.answer("❌ هذه الهمسة غير موجودة أو تم حذفها.", show_alert=True)
        return

    now = now_ts()

    if w.get("expires_at") and now >= w["expires_at"]:
        await q.answer("💨 انتهت صلاحية هذه الهمسة.", show_alert=True)
        return

    unlock_at = w.get("unlock_at")
    if unlock_at and now < unlock_at:
        await q.answer(
            f"⏳ هذه الهمسة ستفتح في:\n{iso(unlock_at)}",
            show_alert=True
        )
        return

    if not allowed_user(w, user):
        await q.answer("🚫 هذه الهمسة مخصصة لشخص آخر.", show_alert=True)
        return

    # Sender can inspect their own whisper without consuming it.
    is_sender = user.id == w["sender_id"]

    # Password is handled through private bot chat.
    if (w.get("password_hash") or w.get("quiz_answer_hash")) and not is_sender:
        token = secrets.token_urlsafe(8)

        def mut(db):
            ww = db["whispers"].get(wid)
            if ww:
                ww.setdefault("pending_unlock", {})[str(user.id)] = {
                    "token": token,
                    "created": now_ts()
                }

        await db_update(mut)

        url = f"https://t.me/{BOT_USERNAME}?start=unlock_{wid}"
        lock_text = "🧩 هذه الهمسة محمية بسؤال." if w.get("quiz_answer_hash") else "🔐 هذه الهمسة محمية بكلمة سر."
        await q.answer(
            lock_text + "\nافتح البوت الخاص للإجابة.",
            show_alert=True,
            url=url
        )
        return

    # Targeted users must have a username matching the configured target.
    if w.get("mode") == "targeted" and not is_sender:
        if not user.username:
            await q.answer(
                "🚫 يجب أن يكون لديك Username حتى يمكن التحقق من أنك المستلم.",
                show_alert=True
            )
            return

    # First-reader locking.
    if w.get("mode") == "first" and not is_sender:
        if w.get("opened_by") and user.id not in w["opened_by"]:
            await q.answer("🚫 شخص آخر فتح الهمسة قبلك.", show_alert=True)
            return

    # One-time read.
    if w.get("once") and not is_sender and user.id in w.get("opened_by", []):
        await q.answer("🚫 هذه الهمسة مخصصة للقراءة مرة واحدة فقط.", show_alert=True)
        return

    # Mark read.
    if not is_sender:
        def mut(db):
            ww = db["whispers"].get(wid)
            if not ww or ww.get("deleted"):
                return None

            if ww.get("mode") == "first" and ww.get("opened_by") and user.id not in ww["opened_by"]:
                return "taken"

            if ww.get("once") and user.id in ww.get("opened_by", []):
                return "once"

            if user.id not in ww.setdefault("opened_by", []):
                ww["opened_by"].append(user.id)
                ww["read_count"] = ww.get("read_count", 0) + 1

            if ww.get("ttl"):
                ww["expires_at"] = now_ts() + int(ww["ttl"])

            return "ok"

        result = await db_update(mut)

        if result == "taken":
            await q.answer("🚫 شخص آخر فتح الهمسة قبلك.", show_alert=True)
            return
        if result == "once":
            await q.answer("🚫 هذه الهمسة قُرئت مسبقاً.", show_alert=True)
            return

    # Notification.
    if not is_sender:
        try:
            await context.bot.send_message(
                chat_id=w["sender_id"],
                text=(
                    "🔔 <b>تم فتح همستك</b>\n\n"
                    f"👤 {user.full_name or 'مستخدم'}\n"
                    f"🆔 <code>{user.id}</code>\n"
                    f"🕒 {iso(now)}"
                ),
                parse_mode=ParseMode.HTML
            )
        except TelegramError:
            pass

    # Media cannot be displayed inside a callback alert.
    # Send it privately to the reader instead.
    media = w.get("media")
    if media and not is_sender:
        await send_media_private(context, user.id, w, media)
        await q.answer("✅ أرسلت لك الهمسة في الخاص.", show_alert=True)
        return

    # Text alert has a Telegram 200-char limit for callback answers.
    text = w.get("text") or "(همسة بدون نص)"
    if len(text) > 190:
        await q.answer("📩 الهمسة طويلة، أرسلتها لك في الخاص.", show_alert=True)
        try:
            sent = await context.bot.send_message(
                chat_id=user.id,
                text=f"🤫 <b>الهمسة:</b>\n\n{text}",
                parse_mode=ParseMode.HTML
            )
            if w.get("ttl"):
                schedule_delete(context, user.id, sent.message_id, w["ttl"])
        except TelegramError:
            pass
        return

    await q.answer(f"🤫 الهمسة:\n\n{text}", show_alert=True)


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data or {}
    try:
        await context.bot.delete_message(
            chat_id=data["chat_id"],
            message_id=data["message_id"],
        )
    except TelegramError:
        pass


def schedule_delete(context, chat_id, message_id, seconds):
    if not seconds:
        return
    jq = context.application.job_queue
    if jq is not None:
        jq.run_once(
            delete_message_job,
            when=max(1, int(seconds)),
            data={"chat_id": chat_id, "message_id": message_id},
        )


async def send_media_private(context, user_id, whisper, media):
    caption = "🤫 همسة سرية"
    if whisper.get("text"):
        caption += f"\n\n{whisper['text']}"

    try:
        typ = media.get("type")
        fid = media.get("file_id")

        if typ == "photo":
            sent = await context.bot.send_photo(user_id, fid, caption=caption)
        elif typ == "voice":
            sent = await context.bot.send_voice(user_id, fid, caption=caption)
        elif typ == "video":
            sent = await context.bot.send_video(user_id, fid, caption=caption)
        elif typ == "document":
            sent = await context.bot.send_document(user_id, fid, caption=caption)
        else:
            sent = await context.bot.send_message(user_id, caption)

        # Telegram cannot guarantee deletion of a file already downloaded
        # by the recipient. This only deletes the bot's sent message.
        if whisper.get("ttl"):
            schedule_delete(context, user_id, sent.message_id, whisper["ttl"])
    except TelegramError:
        log.exception("Failed to send secret media to %s", user_id)
        raise


# =========================
# Password unlock in private
# =========================
async def unlock_start(update, wid):
    user = update.effective_user
    db = await db_read()
    w = db["whispers"].get(wid)

    if not w or w.get("deleted"):
        await update.message.reply_text("❌ الهمسة غير موجودة.")
        return

    if not allowed_user(w, user):
        await update.message.reply_text("🚫 أنت لست المستلم المحدد لهذه الهمسة.")
        return

    if not (w.get("password_hash") or w.get("quiz_answer_hash")):
        await update.message.reply_text("هذه الهمسة لا تحتاج قفلاً.")
        return

    context_key = f"unlock:{wid}"
    context_data = context.user_data
    context_data["unlock_wid"] = wid

    prompt = w.get("quiz_question") if w.get("quiz_answer_hash") else "🔐 <b>أدخل كلمة السر للهمسة:</b>"
    await update.message.reply_text(
        prompt if w.get("quiz_answer_hash") else prompt,
        parse_mode=ParseMode.HTML,
        reply_markup=ForceReply(selective=True)
    )


async def private_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.reply_to_message:
        return

    if not context.user_data.get("unlock_wid"):
        return

    if not update.message.reply_to_message.from_user:
        return

    if update.message.reply_to_message.from_user.id != context.bot.id:
        return

    wid = context.user_data.pop("unlock_wid", None)
    if not wid:
        return

    password = update.message.text or ""
    user = update.effective_user
    db = await db_read()
    w = db["whispers"].get(wid)

    if not w or w.get("deleted"):
        await update.message.reply_text("❌ الهمسة غير موجودة.")
        return

    expected = w.get("quiz_answer_hash") or w.get("password_hash")
    if hash_password(password.strip()) != expected:
        await update.message.reply_text("❌ الإجابة/كلمة السر غير صحيحة.")
        return

    # Reuse normal read rules, except password already verified.
    await consume_after_password(update, context, w)


async def consume_after_password(update, context, w):
    user = update.effective_user
    now = now_ts()

    if w.get("unlock_at") and now < w["unlock_at"]:
        await update.message.reply_text(f"⏳ لم يحن وقت الهمسة بعد: {iso(w['unlock_at'])}")
        return

    if w.get("once") and user.id in w.get("opened_by", []):
        await update.message.reply_text("🚫 هذه الهمسة قُرئت مسبقاً.")
        return

    def mut(db):
        ww = db["whispers"].get(w["id"])
        if not ww or ww.get("deleted"):
            return False
        if user.id not in ww.setdefault("opened_by", []):
            ww["opened_by"].append(user.id)
            ww["read_count"] = ww.get("read_count", 0) + 1
        if ww.get("ttl"):
            ww["expires_at"] = now_ts() + int(ww["ttl"])
        return True

    ok = await db_update(mut)
    if not ok:
        await update.message.reply_text("❌ تعذر فتح الهمسة.")
        return

    media = w.get("media")
    if media:
        await send_media_private(context, user.id, w, media)
    else:
        sent = await update.message.reply_text(
            f"🤫 <b>الهمسة:</b>\n\n{w.get('text', '')}",
            parse_mode=ParseMode.HTML
        )
        if w.get("ttl"):
            schedule_delete(context, update.effective_chat.id, sent.message_id, w["ttl"])

    try:
        await context.bot.send_message(
            w["sender_id"],
            f"🔔 <b>{user.full_name or 'مستخدم'}</b> فتح همستك الآن!",
            parse_mode=ParseMode.HTML
        )
    except TelegramError:
        pass


# =========================
# /new media/text creator
# =========================
async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_mode"] = True
    await update.message.reply_text(
        "🆕 أرسل الآن نص الهمسة.\n\n"
        "أو استخدم الإنلاين إذا أردت الخيارات السريعة."
    )


async def new_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("new_mode"):
        return
    if not update.message or not update.message.text:
        return

    text = update.message.text
    context.user_data.clear()

    w = await create_whisper(update.effective_user, text=text)

    await update.message.reply_text(
        "✅ تم إنشاء الهمسة.\n\n"
        f"🆔 <code>{w['id']}</code>\n\n"
        f"استخدم داخل أي محادثة:\n"
        f"<code>@{BOT_USERNAME} share:{w['id']}</code>",
        parse_mode=ParseMode.HTML
    )


async def media_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["media_mode"] = True
    await update.message.reply_text(
        "🎙️ أرسل الآن الصورة أو البصمة أو الفيديو أو الملف الذي تريد جعله همسة."
    )


async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("media_mode"):
        return

    media = None
    if update.message.photo:
        media = {"type": "photo", "file_id": update.message.photo[-1].file_id}
    elif update.message.voice:
        media = {"type": "voice", "file_id": update.message.voice.file_id}
    elif update.message.video:
        media = {"type": "video", "file_id": update.message.video.file_id}
    elif update.message.document:
        media = {"type": "document", "file_id": update.message.document.file_id}

    if not media:
        return

    context.user_data.clear()
    w = await create_whisper(update.effective_user, media=media)

    await update.message.reply_text(
        "✅ تم حفظ الوسائط كهمسة.\n\n"
        f"🆔 <code>{w['id']}</code>\n\n"
        f"شاركها عبر:\n<code>@{BOT_USERNAME} share:{w['id']}</code>",
        parse_mode=ParseMode.HTML
    )


# =========================
# Inline share: share:ID
# =========================
async def inline_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    iq = update.inline_query
    q = iq.query.strip()

    if not q.lower().startswith("share:"):
        return False

    wid = q.split(":", 1)[1].strip()
    db = await db_read()
    w = db["whispers"].get(wid)

    if not w or w.get("deleted"):
        await iq.answer([], cache_time=0, is_personal=True)
        return True

    if w["sender_id"] != iq.from_user.id:
        await iq.answer([], cache_time=0, is_personal=True)
        return True

    await iq.answer(
        [
            InlineQueryResultArticle(
                id=f"share_{wid}",
                title="🤫 مشاركة الهمسة",
                description="أرسل هذه الهمسة إلى المحادثة",
                input_message_content=InputTextMessageContent(
                    public_caption(w),
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=build_button(w)
            )
        ],
        cache_time=0,
        is_personal=True
    )
    return True


# =========================
# Dashboard delete
# =========================
async def dashboard_delete(q, wid):
    uid = q.from_user.id

    def mut(db):
        w = db["whispers"].get(wid)
        if not w or w.get("sender_id") != uid:
            return False
        w["deleted"] = True
        return True

    ok = await db_update(mut)
    await q.answer("✅ حُذفت الهمسة." if ok else "❌ لم نجد الهمسة.", show_alert=True)


# =========================
# Export / Import
# =========================
async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not DATA_FILE.exists():
        await update.message.reply_text("❌ لا يوجد ملف بيانات.")
        return

    with DATA_FILE.open("rb") as f:
        await update.message.reply_document(
            document=f,
            filename="database.json",
            caption="📦 النسخة الاحتياطية لقاعدة بيانات الهمسات."
        )


async def import_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    doc = update.message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".json"):
        await update.message.reply_text("❌ أرسل database.json فقط.")
        return

    tg_file = await context.bot.get_file(doc.file_id)
    tmp = DATA_FILE.with_suffix(".import.json")
    await tg_file.download_to_drive(tmp)

    try:
        with tmp.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "whispers" not in data:
            raise ValueError("Invalid database structure")

        async with DB_LOCK:
            save_db_sync(data)

        await update.message.reply_text("✅ تم استيراد قاعدة البيانات بنجاح.")
    except Exception:
        log.exception("Import failed")
        await update.message.reply_text("❌ الملف غير صالح أو تالف.")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


# =========================
# Cleanup
# =========================
async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    now = now_ts()

    def mut(db):
        removed = 0
        for w in list(db["whispers"].values()):
            if w.get("deleted"):
                continue

            # TTL is based on first successful read.
            if w.get("expires_at") and now >= w["expires_at"]:
                w["deleted"] = True
                removed += 1

            # Old unopened capsule/whispers are not auto-deleted.
        return removed

    removed = await db_update(mut)
    if removed:
        log.info("Cleanup removed %s expired whispers", removed)


# =========================
# Error handler
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled exception", exc_info=context.error)


# =========================
# Main
# =========================
async def post_init(application):
    global BOT_USERNAME
    me = await application.bot.get_me()
    BOT_USERNAME = me.username or ""
    log.info("Bot started as @%s", BOT_USERNAME)

    commands = [
        BotCommand("start", "بدء البوت"),
        BotCommand("new", "إنشاء همسة"),
        BotCommand("media", "همسة وسائط"),
        BotCommand("my", "إدارة همساتي"),
        BotCommand("delete", "حذف همسة"),
        BotCommand("export", "نسخة احتياطية"),
    ]
    await application.bot.set_my_commands(commands)


def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("new", new_cmd))
    application.add_handler(CommandHandler("media", media_cmd))
    application.add_handler(CommandHandler("my", my_cmd))
    application.add_handler(CommandHandler("delete", delete_cmd))
    application.add_handler(CommandHandler("export", export_cmd))

    # Password replies and creator flows.
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.REPLY,
            private_password_handler
        ),
        group=0
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            new_text_handler
        ),
        group=1
    )
    application.add_handler(
        MessageHandler(
            filters.PHOTO | filters.VOICE | filters.VIDEO | filters.Document.ALL,
            media_handler
        ),
        group=2
    )

    application.add_handler(MessageHandler(filters.Document.ALL, import_handler), group=3)

    application.add_handler(CallbackQueryHandler(callback_handler))

    # Inline handler handles both normal and share: queries.
    async def inline_router(update, context):
        q = update.inline_query.query.strip()
        if q.lower().startswith("share:"):
            await inline_share_handler(update, context)
        else:
            await inline_query_handler(update, context)

    application.add_handler(InlineQueryHandler(inline_router))

    application.add_error_handler(error_handler)

    if application.job_queue is None:
        raise RuntimeError(
            "JobQueue unavailable. Install python-telegram-bot[job-queue,webhooks]==20.8"
        )

    application.job_queue.run_repeating(
        cleanup_job,
        interval=60,
        first=10,
        name="cleanup_job"
    )

    clean_url = WEBHOOK_URL.strip()
    clean_url = clean_url.replace("https://", "").replace("http://", "").rstrip("/")

    log.info("Starting webhook on port %s", PORT)

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"https://{clean_url}/{BOT_TOKEN}",
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
