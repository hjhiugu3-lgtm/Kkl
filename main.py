# -*- coding: utf-8 -*-

"""
بوت الهمسات السرية
------------------
Python: 3.9+
python-telegram-bot: 20.8

المميزات:
- Inline Mode
- همسة لأول شخص يفتحها
- همسة للجميع
- /export للنسخ الاحتياطي
- /import لاستعادة نسخة صحيحة من قاعدة البيانات
- كتابة ذرية للـ JSON
- نسخة احتياطية تلقائية database.json.bak
- حماية من Race Conditions داخل نفس نسخة البوت
- التحقق من صحة قاعدة البيانات
- انتهاء صلاحية الهمسات
- حد أقصى لطول الهمسة
- Rate Limit لإنشاء الهمسات
- تنظيف تلقائي للبيانات القديمة
- HTML بدل Markdown لتجنب مشاكل أسماء المستخدمين
- Webhook لـ Railway
- دعم WEBHOOK_SECRET اختياري
- معالجة أخطاء أفضل
"""

import os
import json
import uuid
import time
import asyncio
import logging
import tempfile
from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime, timezone

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChosenInlineResultHandler,
    ContextTypes,
    filters,
)


# ============================================================
# ⚙️ الإعدادات
# ============================================================

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


# ============================================================
# 🛡️ حدود الحماية
# ============================================================

# الحد الأقصى لطول الهمسة
MAX_WHISPER_LENGTH = int(
    os.environ.get("MAX_WHISPER_LENGTH", "2000")
)

# عمر الهمسة بالثواني
# الافتراضي: 7 أيام
WHISPER_TTL_SECONDS = int(
    os.environ.get("WHISPER_TTL_SECONDS", str(7 * 24 * 60 * 60))
)

# أقصى عدد للمستخدمين الذين نسجلهم في همسة "للجميع"
MAX_TRACKED_OPENERS = int(
    os.environ.get("MAX_TRACKED_OPENERS", "5000")
)

# عدد الهمسات التي يستطيع المستخدم إنشاءها
# خلال الفترة المحددة
CREATE_LIMIT = int(
    os.environ.get("CREATE_LIMIT", "20")
)

CREATE_WINDOW_SECONDS = int(
    os.environ.get("CREATE_WINDOW_SECONDS", "60")
)

# عدد الهمسات القصوى الموجودة في الملف
# يمنع تضخم قاعدة JSON بشكل غير محدود
MAX_TOTAL_WHISPERS = int(
    os.environ.get("MAX_TOTAL_WHISPERS", "100000")
)

# كل كم عملية إنشاء نقوم بتنظيف الهمسات القديمة
CLEANUP_EVERY = int(
    os.environ.get("CLEANUP_EVERY", "100")
)


# ============================================================
# 📝 Logging
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("WhisperBot")


# ============================================================
# 🔒 Locks
# ============================================================

# يمنع تعارض القراءة والكتابة داخل نفس instance
DATA_LOCK = asyncio.Lock()

# لحماية rate limiter
RATE_LIMIT_LOCK = asyncio.Lock()


# ============================================================
# 🧠 الذاكرة المؤقتة
# ============================================================

# النتيجة التي ظهرت في Inline Mode ولم يتم اختيارها بعد.
#
# لا نحفظ كل حرف يكتبه المستخدم في JSON.
# يتم وضع البيانات هنا مؤقتًا فقط.
#
# key:
#   result_id
#
# value:
#   {
#       "text": "...",
#       "sender_id": 123,
#       "sender_name": "..."
#   }
PENDING_WHISPERS = {}

# عدد الهمسات المنشأة منذ آخر تنظيف
CREATED_SINCE_CLEANUP = 0

# Rate limit:
# user_id -> deque(timestamp, timestamp, ...)
CREATE_HISTORY = defaultdict(deque)


# ============================================================
# 🧰 أدوات عامة
# ============================================================

def now_timestamp() -> int:
    """إرجاع الوقت الحالي Unix timestamp."""
    return int(time.time())


def utc_iso(timestamp: int) -> str:
    """تحويل timestamp إلى تاريخ ISO."""
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc
    ).isoformat()


def html_escape(text: str) -> str:
    """حماية النص من كسر HTML."""
    if not isinstance(text, str):
        text = str(text)

    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def safe_name(user) -> str:
    """اسم آمن للعرض."""
    name = user.first_name or "مستخدم"
    return html_escape(name[:100])


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID and ADMIN_ID != 0


# ============================================================
# 🔐 التحقق من متغيرات البيئة
# ============================================================

def validate_environment():
    """التأكد من وجود الإعدادات الأساسية."""

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود في Environment Variables."
        )

    if ADMIN_ID == 0:
        raise RuntimeError(
            "ADMIN_ID غير موجود أو غير صحيح."
        )

    if not WEBHOOK_URL:
        raise RuntimeError(
            "WEBHOOK_URL غير موجود في Environment Variables."
        )

    if PORT <= 0 or PORT > 65535:
        raise RuntimeError(
            "PORT غير صحيح."
        )

    if MAX_WHISPER_LENGTH < 1:
        raise RuntimeError(
            "MAX_WHISPER_LENGTH يجب أن يكون أكبر من صفر."
        )

    logger.info("Environment variables validated successfully.")


# ============================================================
# 🗄️ قاعدة البيانات JSON
# ============================================================

def empty_database():
    return {
        "version": 2,
        "whispers": {}
    }


def validate_database_structure(data):
    """
    التحقق من أن الملف المرفوع أو المقروء
    هو قاعدة بيانات تخص هذا البوت.
    """

    if not isinstance(data, dict):
        return False

    if not isinstance(data.get("whispers"), dict):
        return False

    # السماح بالنسخة القديمة أو الحالية
    version = data.get("version", 1)

    if not isinstance(version, int):
        return False

    return True


def normalize_database(data):
    """
    تنظيف البيانات وتحويلها إلى الشكل المتوقع.
    """

    if not validate_database_structure(data):
        raise ValueError("بنية قاعدة البيانات غير صحيحة.")

    normalized = empty_database()

    for whisper_id, whisper in data["whispers"].items():

        if not isinstance(whisper_id, str):
            continue

        if not isinstance(whisper, dict):
            continue

        text = whisper.get("text")
        sender_id = whisper.get("sender_id")
        sender_name = whisper.get("sender_name")
        whisper_type = whisper.get("type")

        if not isinstance(text, str):
            continue

        if not isinstance(sender_id, int):
            continue

        if whisper_type not in ("first", "all"):
            continue

        if not isinstance(sender_name, str):
            sender_name = "مستخدم"

        # تاريخ الإنشاء
        created_at = whisper.get("created_at")

        if not isinstance(created_at, int):
            created_at = now_timestamp()

        # تاريخ الانتهاء
        expires_at = whisper.get("expires_at")

        if not isinstance(expires_at, int):
            expires_at = created_at + WHISPER_TTL_SECONDS

        # المستخدمون الذين فتحوا الهمسة
        opened_by = whisper.get("opened_by", [])

        if not isinstance(opened_by, list):
            opened_by = []

        clean_opened_by = []

        for user_id in opened_by:
            if isinstance(user_id, int):
                if user_id not in clean_opened_by:
                    clean_opened_by.append(user_id)

        clean_opened_by = clean_opened_by[
            :MAX_TRACKED_OPENERS
        ]

        normalized["whispers"][whisper_id] = {
            "text": text[:MAX_WHISPER_LENGTH],
            "sender_id": sender_id,
            "sender_name": sender_name[:100],
            "type": whisper_type,
            "opened_by": clean_opened_by,
            "created_at": created_at,
            "expires_at": expires_at,
        }

    return normalized


def load_data_sync():
    """
    قراءة JSON بشكل متزامن.
    لا تستعمل هذه الدالة مباشرة من handlers
    إلا داخل executor أو أثناء الإقلاع.
    """

    if not DATA_FILE.exists():
        logger.warning(
            "database.json غير موجود. سيتم إنشاء قاعدة جديدة."
        )
        return empty_database()

    try:
        with DATA_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not validate_database_structure(data):
            raise ValueError(
                "بنية database.json غير صحيحة."
            )

        return normalize_database(data)

    except json.JSONDecodeError as exc:

        logger.critical(
            "database.json تالف JSON: %s",
            exc
        )

        # لا نرجع قاعدة فارغة هنا.
        # لأن ذلك قد يؤدي إلى الكتابة فوق البيانات التالفة.
        raise RuntimeError(
            "database.json تالف. "
            "استعمل database.json.bak أو /import لاستعادة نسخة صحيحة."
        ) from exc

    except Exception as exc:

        logger.exception(
            "فشل في قراءة قاعدة البيانات."
        )

        raise RuntimeError(
            "تعذر قراءة قاعدة البيانات."
        ) from exc


async def load_data():
    """قراءة قاعدة البيانات بدون تجميد event loop."""

    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        None,
        load_data_sync
    )


def write_json_atomic_sync(data):
    """
    كتابة ذرية وآمنة:

    1. إنشاء ملف مؤقت.
    2. كتابة البيانات بالكامل.
    3. عمل flush + fsync.
    4. نسخ النسخة القديمة إلى backup.
    5. استبدال الملف القديم بالملف الجديد.
    """

    DATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # تحويل البيانات إلى JSON قبل لمس الملف
    serialized = json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )

    temp_path = None

    try:

        # إنشاء ملف مؤقت في نفس المجلد
        # حتى يكون os.replace عملية آمنة قدر الإمكان.
        fd, temp_name = tempfile.mkstemp(
            prefix="database_",
            suffix=".tmp",
            dir=str(DATA_FILE.parent)
        )

        temp_path = Path(temp_name)

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(serialized)
            file.flush()
            os.fsync(file.fileno())

        # Backup للنسخة الحالية قبل استبدالها
        if DATA_FILE.exists():

            try:

                with DATA_FILE.open(
                    "rb"
                ) as source:

                    with BACKUP_FILE.open(
                        "wb"
                    ) as backup:

                        while True:

                            chunk = source.read(1024 * 1024)

                            if not chunk:
                                break

                            backup.write(chunk)

            except Exception:
                logger.exception(
                    "فشل إنشاء النسخة الاحتياطية."
                )

        # استبدال ذري
        os.replace(
            temp_path,
            DATA_FILE
        )

        temp_path = None

    finally:

        if temp_path is not None:
            try:
                temp_path.unlink(
                    missing_ok=True
                )
            except Exception:
                pass


async def save_data(data):
    """حفظ قاعدة البيانات بطريقة آمنة."""

    if not validate_database_structure(data):
        raise ValueError(
            "محاولة حفظ قاعدة بيانات غير صحيحة."
        )

    loop = asyncio.get_running_loop()

    await loop.run_in_executor(
        None,
        write_json_atomic_sync,
        data
    )


# ============================================================
# 🧹 تنظيف الهمسات القديمة
# ============================================================

def cleanup_expired_data_sync():
    """حذف الهمسات المنتهية."""

    if not DATA_FILE.exists():
        return 0

    data = load_data_sync()

    current = now_timestamp()
    removed = 0

    whisper_ids = list(
        data["whispers"].keys()
    )

    for whisper_id in whisper_ids:

        whisper = data["whispers"].get(
            whisper_id
        )

        if not whisper:
            continue

        expires_at = whisper.get(
            "expires_at",
            0
        )

        if expires_at <= current:

            del data["whispers"][
                whisper_id
            ]

            removed += 1

    if removed:
        write_json_atomic_sync(data)

    return removed


async def cleanup_expired_data():
    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        None,
        cleanup_expired_data_sync
    )


# ============================================================
# 🚦 Rate Limit
# ============================================================

async def can_create_whisper(user_id: int) -> bool:

    current = time.monotonic()

    async with RATE_LIMIT_LOCK:

        history = CREATE_HISTORY[user_id]

        # حذف العمليات القديمة
        while history and (
            current - history[0]
            > CREATE_WINDOW_SECONDS
        ):
            history.popleft()

        if len(history) >= CREATE_LIMIT:
            return False

        history.append(current)

        return True


# ============================================================
# 🧩 إنشاء همسة
# ============================================================

def make_whisper_id() -> str:
    """
    UUID قصير نسبيًا ومناسب لـ callback_data.
    """
    return uuid.uuid4().hex


def build_whisper_record(
    text,
    sender_id,
    sender_name,
    whisper_type
):
    created = now_timestamp()

    return {
        "text": text,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "type": whisper_type,
        "opened_by": [],
        "created_at": created,
        "expires_at": (
            created +
            WHISPER_TTL_SECONDS
        ),
    }


# ============================================================
# 🚀 /start
# ============================================================

async def start_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    user_id = update.effective_user.id

    text = (
        "🤫 <b>أهلاً بك في بوت الهمسات السرية</b>\n\n"
        "لاستخدام البوت:\n"
        "اكتب معرف البوت في أي محادثة، ثم اكتب "
        "الهمسة التي تريد إرسالها.\n\n"
        "سيظهر لك خياران:\n"
        "👁️ همسة لأول شخص يفتحها\n"
        "👥 همسة يمكن للجميع قراءتها"
    )

    if is_admin(user_id):

        text += (
            "\n\n"
            "⚙️ <b>لوحة المطور</b>\n\n"
            "• /export — أخذ نسخة احتياطية\n"
            "• /import — استعادة نسخة JSON\n"
            "• /stats — إحصائيات قاعدة البيانات\n"
            "• /cleanup — حذف الهمسات المنتهية"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML
    )


# ============================================================
# 📤 /export
# ============================================================

async def export_data(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if not is_admin(
        update.effective_user.id
    ):
        return

    async with DATA_LOCK:

        if not DATA_FILE.exists():

            await update.message.reply_text(
                "❌ لا توجد قاعدة بيانات حالياً."
            )

            return

        try:

            # التأكد من أن الملف صالح قبل تصديره
            data = await load_data()

            await update.message.reply_document(
                document=str(DATA_FILE),
                caption=(
                    "📦 نسخة احتياطية من قاعدة بيانات "
                    "الهمسات.\n\n"
                    f"عدد الهمسات: "
                    f"{len(data['whispers'])}"
                )
            )

            logger.info(
                "Database exported by admin %s",
                update.effective_user.id
            )

        except Exception as exc:

            logger.exception(
                "Export failed."
            )

            await update.message.reply_text(
                "❌ فشل تصدير قاعدة البيانات."
            )


# ============================================================
# 📥 /import
# ============================================================

async def import_data(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if not is_admin(
        update.effective_user.id
    ):
        return

    document = update.message.document

    if not document:
        return

    filename = (
        document.file_name or ""
    ).lower()

    if not filename.endswith(".json"):

        await update.message.reply_text(
            "⚠️ يجب إرسال ملف بصيغة JSON فقط."
        )

        return

    # حماية إضافية من الملفات الضخمة
    # Telegram يسمح للبوت بتنزيل ملفات حتى حدود معينة،
    # لكن لا نريد استهلاك الذاكرة بلا داعٍ.
    if document.file_size:
        if document.file_size > 20 * 1024 * 1024:

            await update.message.reply_text(
                "❌ حجم الملف أكبر من الحد المسموح."
            )

            return

    async with DATA_LOCK:

        temp_import = (
            DATA_FILE.parent /
            "database_import.tmp"
        )

        try:

            file = await context.bot.get_file(
                document.file_id
            )

            await file.download_to_drive(
                custom_path=str(temp_import)
            )

            # قراءة الملف المرفوع
            with temp_import.open(
                "r",
                encoding="utf-8"
            ) as imported_file:

                raw_data = json.load(
                    imported_file
                )

            # التحقق من البنية
            if not validate_database_structure(
                raw_data
            ):
                raise ValueError(
                    "بنية الملف غير صحيحة."
                )

            # Normalize + validation
            imported_data = normalize_database(
                raw_data
            )

            whisper_count = len(
                imported_data["whispers"]
            )

            if whisper_count > MAX_TOTAL_WHISPERS:

                raise ValueError(
                    f"عدد الهمسات يتجاوز الحد "
                    f"المسموح ({MAX_TOTAL_WHISPERS})."
                )

            # حفظ النسخة الحالية أولاً
            if DATA_FILE.exists():

                # النسخة الاحتياطية تتم داخل
                # write_json_atomic_sync
                pass

            await save_data(
                imported_data
            )

            # حذف الملف المؤقت
            temp_import.unlink(
                missing_ok=True
            )

            await update.message.reply_text(
                "✅ <b>تم استرداد قاعدة البيانات بنجاح.</b>\n\n"
                f"عدد الهمسات: <b>{whisper_count}</b>\n"
                "تم التحقق من بنية الملف قبل الاستبدال.",
                parse_mode=ParseMode.HTML
            )

            logger.warning(
                "Database imported by admin %s. "
                "Whispers: %s",
                update.effective_user.id,
                whisper_count
            )

        except json.JSONDecodeError:

            temp_import.unlink(
                missing_ok=True
            )

            await update.message.reply_text(
                "❌ الملف ليس JSON صالحًا."
            )

        except Exception as exc:

            logger.exception(
                "Import failed."
            )

            temp_import.unlink(
                missing_ok=True
            )

            await update.message.reply_text(
                "❌ فشل استرداد قاعدة البيانات.\n"
                "لم يتم اعتماد الملف المرفوع."
            )


# ============================================================
# 📊 /stats
# ============================================================

async def stats_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if not is_admin(
        update.effective_user.id
    ):
        return

    async with DATA_LOCK:

        try:

            data = await load_data()

            whispers = data["whispers"]

            first_count = 0
            all_count = 0

            current = now_timestamp()
            expired = 0

            for whisper in whispers.values():

                if whisper["type"] == "first":
                    first_count += 1
                else:
                    all_count += 1

                if whisper["expires_at"] <= current:
                    expired += 1

            text = (
                "📊 <b>إحصائيات البوت</b>\n\n"
                f"📦 إجمالي الهمسات: "
                f"<b>{len(whispers)}</b>\n"
                f"👁️ همسات لأول شخص: "
                f"<b>{first_count}</b>\n"
                f"👥 همسات للجميع: "
                f"<b>{all_count}</b>\n"
                f"⏰ منتهية وتنتظر التنظيف: "
                f"<b>{expired}</b>\n"
                f"💾 ملف البيانات: "
                f"<code>{DATA_FILE}</code>"
            )

            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML
            )

        except Exception:

            logger.exception(
                "Stats failed."
            )

            await update.message.reply_text(
                "❌ تعذر قراءة الإحصائيات."
            )


# ============================================================
# 🧹 /cleanup
# ============================================================

async def cleanup_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if not is_admin(
        update.effective_user.id
    ):
        return

    async with DATA_LOCK:

        try:

            removed = await cleanup_expired_data()

            await update.message.reply_text(
                "🧹 تم تنظيف قاعدة البيانات.\n\n"
                f"🗑️ تم حذف: {removed} همسة."
            )

            logger.info(
                "Manual cleanup removed %s whispers.",
                removed
            )

        except Exception:

            logger.exception(
                "Cleanup failed."
            )

            await update.message.reply_text(
                "❌ فشل تنظيف قاعدة البيانات."
            )


# ============================================================
# 🔎 Inline Query
# ============================================================

async def inline_query_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    inline_query = update.inline_query

    if not inline_query:
        return

    query_text = (
        inline_query.query.strip()
    )

    # لا نعرض نتائج فارغة
    if not query_text:

        await inline_query.answer(
            [],
            cache_time=0,
            is_personal=True
        )

        return

    # حماية من الرسائل الضخمة
    if len(query_text) > MAX_WHISPER_LENGTH:

        await inline_query.answer(
            [],
            cache_time=0,
            is_personal=True
        )

        return

    sender = inline_query.from_user

    # ID مختلف لكل نوع
    base_id = make_whisper_id()

    first_id = f"{base_id}f"
    all_id = f"{base_id}a"

    sender_name = (
        sender.first_name or "مستخدم"
    )

    # حفظ مؤقت فقط.
    # لا نكتب إلى JSON أثناء الكتابة.
    PENDING_WHISPERS[first_id] = {
        "text": query_text,
        "sender_id": sender.id,
        "sender_name": sender_name,
        "type": "first",
        "created_at": now_timestamp(),
    }

    PENDING_WHISPERS[all_id] = {
        "text": query_text,
        "sender_id": sender.id,
        "sender_name": sender_name,
        "type": "all",
        "created_at": now_timestamp(),
    }

    # حماية من نمو الذاكرة المؤقتة
    # نحذف العناصر الأقدم من 10 دقائق.
    cutoff = now_timestamp() - 600

    stale_ids = []

    for result_id, pending in PENDING_WHISPERS.items():

        if pending["created_at"] < cutoff:
            stale_ids.append(result_id)

    for result_id in stale_ids:
        PENDING_WHISPERS.pop(
            result_id,
            None
        )

    safe_sender_name = html_escape(
        sender_name[:100]
    )

    # لا نضع نص الهمسة نفسها في الرسالة المنشورة.
    # النص يظهر فقط عند الضغط على الزر.
    first_result = InlineQueryResultArticle(
        id=first_id,
        title="👁️ همسة لأول شخص يفتحها",
        description=(
            "ستظهر الهمسة لأول شخص يضغط على الزر."
        ),
        input_message_content=InputTextMessageContent(
            message_text=(
                "🔒 <b>همسة سرية</b>\n\n"
                f"أرسلها: <b>{safe_sender_name}</b>\n"
                "👁️ الهمسة متاحة لأول شخص يفتحها."
            ),
            parse_mode=ParseMode.HTML
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👁️ اضغط لقراءة الهمسة",
                    callback_data=f"w:{first_id}"
                )
            ]
        ])
    )

    all_result = InlineQueryResultArticle(
        id=all_id,
        title="👥 همسة للجميع",
        description=(
            "يمكن لكل شخص الضغط وقراءة الهمسة."
        ),
        input_message_content=InputTextMessageContent(
            message_text=(
                "🔒 <b>همسة سرية</b>\n\n"
                f"أرسلها: <b>{safe_sender_name}</b>\n"
                "👥 يمكن للجميع قراءة الهمسة."
            ),
            parse_mode=ParseMode.HTML
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👁️ اضغط لقراءة الهمسة",
                    callback_data=f"w:{all_id}"
                )
            ]
        ])
    )

    try:

        await inline_query.answer(
            [
                first_result,
                all_result
            ],
            cache_time=0,
            is_personal=True
        )

    except TelegramError:

        logger.exception(
            "Failed to answer inline query."
        )


# ============================================================
# 🧾 Chosen Inline Result
# ============================================================

async def chosen_inline_result_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    عندما يختار المستخدم نتيجة Inline،
    نحفظ الهمسة في JSON.

    ChosenInlineResult يوفر:
    - result_id
    - from_user
    - query
    """

    chosen = update.chosen_inline_result

    if not chosen:
        return

    result_id = chosen.result_id

    pending = PENDING_WHISPERS.get(
        result_id
    )

    if not pending:
        # لا نستطيع معرفة النوع إذا لم يكن
        # موجودًا في الذاكرة.
        #
        # نستخرج النوع من آخر حرف:
        if result_id.endswith("f"):
            whisper_type = "first"
        elif result_id.endswith("a"):
            whisper_type = "all"
        else:
            return

        text = (
            chosen.query or ""
        ).strip()

        if not text:
            return

        if len(text) > MAX_WHISPER_LENGTH:
            return

        pending = {
            "text": text,
            "sender_id": chosen.from_user.id,
            "sender_name": (
                chosen.from_user.first_name
                or "مستخدم"
            ),
            "type": whisper_type
        }

    # Rate limit يتم هنا، لأن الاختيار هو
    # عملية إنشاء فعلية وليس مجرد كتابة في Inline Mode.
    allowed = await can_create_whisper(
        chosen.from_user.id
    )

    if not allowed:

        logger.warning(
            "Rate limit reached for user %s",
            chosen.from_user.id
        )

        return

    global CREATED_SINCE_CLEANUP

    async with DATA_LOCK:

        try:

            data = await load_data()

            # حماية من تجاوز حجم قاعدة البيانات
            if (
                len(data["whispers"])
                >= MAX_TOTAL_WHISPERS
            ):

                logger.error(
                    "Maximum whisper database size reached."
                )

                return

            whisper_id = result_id

            # منع تكرار الإدخال
            if whisper_id in data["whispers"]:

                return

            record = build_whisper_record(
                text=pending["text"],
                sender_id=pending["sender_id"],
                sender_name=pending["sender_name"],
                whisper_type=pending["type"]
            )

            data["whispers"][whisper_id] = record

            await save_data(data)

            CREATED_SINCE_CLEANUP += 1

            logger.info(
                "Whisper created: %s | type=%s | sender=%s",
                whisper_id,
                pending["type"],
                pending["sender_id"]
            )

            # حذفها من الذاكرة
            PENDING_WHISPERS.pop(
                result_id,
                None
            )

            # تنظيف دوري
            if (
                CREATED_SINCE_CLEANUP
                >= CLEANUP_EVERY
            ):

                CREATED_SINCE_CLEANUP = 0

                # التنظيف داخل نفس lock
                removed = await cleanup_expired_data()

                if removed:
                    logger.info(
                        "Automatic cleanup removed %s "
                        "expired whispers.",
                        removed
                    )

        except Exception:

            logger.exception(
                "Failed to persist chosen inline result."
            )


# ============================================================
# 👁️ Callback Handler
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    callback = update.callback_query

    if not callback:
        return

    data_code = callback.data or ""

    if not data_code.startswith("w:"):

        await callback.answer()
        return

    whisper_id = data_code[2:].strip()

    if not whisper_id:

        await callback.answer(
            "❌ الهمسة غير صالحة.",
            show_alert=True
        )

        return

    user = callback.from_user

    async with DATA_LOCK:

        try:

            data = await load_data()

            whisper = data["whispers"].get(
                whisper_id
            )

            # ------------------------------------------------
            # إذا لم توجد في JSON:
            # نحاول إنشاؤها من الذاكرة المؤقتة.
            # ------------------------------------------------

            if not whisper:

                pending = PENDING_WHISPERS.get(
                    whisper_id
                )

                if pending:

                    if not await can_create_whisper(
                        pending["sender_id"]
                    ):
                        pending = None

                    else:

                        whisper = build_whisper_record(
                            text=pending["text"],
                            sender_id=pending["sender_id"],
                            sender_name=pending["sender_name"],
                            whisper_type=pending["type"]
                        )

                        data["whispers"][
                            whisper_id
                        ] = whisper

                        await save_data(data)

                        PENDING_WHISPERS.pop(
                            whisper_id,
                            None
                        )

            # ------------------------------------------------
            # لا توجد الهمسة
            # ------------------------------------------------

            if not whisper:

                await callback.answer(
                    "❌ هذه الهمسة غير موجودة أو انتهت صلاحيتها.",
                    show_alert=True
                )

                return

            # ------------------------------------------------
            # انتهاء الصلاحية
            # ------------------------------------------------

            if (
                whisper["expires_at"]
                <= now_timestamp()
            ):

                # حذفها فورًا
                del data["whispers"][
                    whisper_id
                ]

                await save_data(data)

                await callback.answer(
                    "⏰ انتهت صلاحية هذه الهمسة.",
                    show_alert=True
                )

                return

            # ------------------------------------------------
            # المرسل يستطيع رؤية همسته
            # ------------------------------------------------

            if (
                user.id
                == whisper["sender_id"]
            ):

                await callback.answer(
                    "🤫 نص همستك:\n\n"
                    + whisper["text"],
                    show_alert=True
                )

                return

            # ------------------------------------------------
            # همسة لأول شخص
            # ------------------------------------------------

            if whisper["type"] == "first":

                opened_by = whisper.get(
                    "opened_by",
                    []
                )

                # أول شخص
                if not opened_by:

                    whisper["opened_by"] = [
                        user.id
                    ]

                    await save_data(data)

                    await callback.answer(
                        "🤫 الهمسة لك فقط:\n\n"
                        + whisper["text"],
                        show_alert=True
                    )

                    # إشعار للمرسل
                    try:

                        safe_user_name = html_escape(
                            user.first_name
                            or "مستخدم"
                        )

                        await context.bot.send_message(
                            chat_id=whisper["sender_id"],
                            text=(
                                "🔔 <b>تم فتح همستك</b>\n\n"
                                f"👤 بواسطة: "
                                f"<a href=\"tg://user?id={user.id}\">"
                                f"{safe_user_name}"
                                f"</a>"
                            ),
                            parse_mode=ParseMode.HTML
                        )

                    except TelegramError as exc:

                        logger.warning(
                            "Could not notify sender %s: %s",
                            whisper["sender_id"],
                            exc
                        )

                    return

                # الشخص الذي فتحها سابقًا
                if user.id in opened_by:

                    await callback.answer(
                        "🤫 الهمسة لك:\n\n"
                        + whisper["text"],
                        show_alert=True
                    )

                    return

                # شخص آخر
                await callback.answer(
                    "🚫 للأسف، قام شخص آخر بفتح "
                    "هذه الهمسة قبلك.",
                    show_alert=True
                )

                return

            # ------------------------------------------------
            # همسة للجميع
            # ------------------------------------------------

            if whisper["type"] == "all":

                opened_by = whisper.get(
                    "opened_by",
                    []
                )

                # تسجيل المستخدم إن كان
                # ضمن الحد المسموح
                if (
                    user.id not in opened_by
                    and len(opened_by)
                    < MAX_TRACKED_OPENERS
                ):

                    opened_by.append(
                        user.id
                    )

                    whisper["opened_by"] = opened_by

                    await save_data(data)

                await callback.answer(
                    "🤫 الهمسة:\n\n"
                    + whisper["text"],
                    show_alert=True
                )

                return

            # ------------------------------------------------
            # نوع غير معروف
            # ------------------------------------------------

            await callback.answer(
                "❌ نوع الهمسة غير معروف.",
                show_alert=True
            )

        except Exception:

            logger.exception(
                "Callback handler failed."
            )

            try:

                await callback.answer(
                    "❌ حدث خطأ أثناء فتح الهمسة.",
                    show_alert=True
                )

            except Exception:
                pass


# ============================================================
# 📄 استقبال ملفات JSON من Admin
# ============================================================

async def document_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    # لا نتعامل مع الملف إلا إذا كان Admin
    if not is_admin(
        update.effective_user.id
    ):
        return

    document = update.message.document

    if not document:
        return

    filename = (
        document.file_name or ""
    ).lower()

    if filename.endswith(".json"):

        await import_data(
            update,
            context
        )


# ============================================================
# ❗ Error Handler
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Unhandled exception: %s",
        context.error,
        exc_info=(
            type(context.error),
            context.error,
            context.error.__traceback__
            if context.error
            else None
        )
    )


# ============================================================
# 🏁 Main
# ============================================================

def main():

    validate_environment()

    logger.info(
        "Starting Whisper Bot..."
    )

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # -----------------------------------------
    # Commands
    # -----------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "export",
            export_data
        )
    )

    app.add_handler(
        CommandHandler(
            "import",
            import_data
        )
    )

    app.add_handler(
        CommandHandler(
            "stats",
            stats_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "cleanup",
            cleanup_cmd
        )
    )

    # -----------------------------------------
    # Inline Mode
    # -----------------------------------------

    app.add_handler(
        InlineQueryHandler(
            inline_query_handler
        )
    )

    # مهم جدًا:
    # يحتاج تفعيل Inline Feedback من BotFather
    # للحصول على ChosenInlineResult.
    app.add_handler(
        ChosenInlineResultHandler(
            chosen_inline_result_handler
        )
    )

    # -----------------------------------------
    # Callback buttons
    # -----------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # -----------------------------------------
    # JSON import
    # -----------------------------------------

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            document_handler
        )
    )

    # -----------------------------------------
    # Error handler
    # -----------------------------------------

    app.add_error_handler(
        error_handler
    )

    # -----------------------------------------
    # Webhook
    # -----------------------------------------

    clean_url = (
        WEBHOOK_URL
        .replace("https://", "")
        .replace("http://", "")
        .rstrip("/")
    )

    webhook_url = (
        f"https://{clean_url}/{BOT_TOKEN}"
    )

    allowed_updates = [
        "message",
        "inline_query",
        "chosen_inline_result",
        "callback_query",
    ]

    logger.info(
        "Starting webhook on port %s",
        PORT
    )

    logger.info(
        "Webhook URL: https://%s/...",
        clean_url
    )

    # secret_token اختياري.
    # إذا وضعته في Railway سيتم استخدامه.
    webhook_kwargs = {
        "listen": "0.0.0.0",
        "port": PORT,
        "url_path": BOT_TOKEN,
        "webhook_url": webhook_url,
        "allowed_updates": allowed_updates,
        "drop_pending_updates": False,
    }

    if WEBHOOK_SECRET:

        webhook_kwargs[
            "secret_token"
        ] = WEBHOOK_SECRET

        logger.info(
            "Telegram webhook secret is enabled."
        )

    app.run_webhook(
        **webhook_kwargs
    )


# ============================================================
# ▶️ تشغيل
# ============================================================

if __name__ == "__main__":
    main()
