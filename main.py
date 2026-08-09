# -*- coding: utf-8 -*-

"""
=========================================================
                 🤫 WHISPER BOT
=========================================================

Python:
    3.9+

Library:
    python-telegram-bot==20.8

=========================================================
FEATURES
=========================================================

📝 Text whispers
🖼️ Photo whispers
🎤 Voice whispers

👁️ First person
👤 Specific user
👥 Multiple users
🌍 Everyone

👻 Anonymous mode
🔐 Password protection
❓ Quiz protection

☝️ One-time read
💣 Self destruct after reading
🔔 Read notification

⏰ Time capsule

✏️ Custom button text

📋 My whispers
🗑️ Delete whisper
📊 Statistics

📤 Export
📥 Import
💾 Automatic backup

🛡️ Atomic JSON writes
🛡️ Database validation
🚦 Rate limiting
🧹 Automatic cleanup

=========================================================
IMPORTANT
=========================================================

For advanced whispers use:

    /create

For quick text whispers use:

    @YourBot your message

Inline Mode must be enabled from BotFather.

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
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from telegram.constants import ParseMode

from telegram.error import (
    TelegramError,
    Forbidden,
    BadRequest,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)


# =========================================================
# ⚙️ CONFIG
# =========================================================

DATA_FILE = Path(
    os.environ.get(
        "DATA_FILE",
        "database.json"
    )
)

BACKUP_FILE = Path(
    os.environ.get(
        "BACKUP_FILE",
        "database.json.bak"
    )
)

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    ""
).strip()

WEBHOOK_URL = os.environ.get(
    "WEBHOOK_URL",
    ""
).strip()

WEBHOOK_SECRET = os.environ.get(
    "WEBHOOK_SECRET",
    ""
).strip()

try:
    ADMIN_ID = int(
        os.environ.get(
            "ADMIN_ID",
            "0"
        )
    )
except ValueError:
    ADMIN_ID = 0

try:
    PORT = int(
        os.environ.get(
            "PORT",
            "8080"
        )
    )
except ValueError:
    PORT = 8080


# =========================================================
# 🛡️ LIMITS
# =========================================================

MAX_TEXT_LENGTH = int(
    os.environ.get(
        "MAX_TEXT_LENGTH",
        "4000"
    )
)

MAX_WHISPERS = int(
    os.environ.get(
        "MAX_WHISPERS",
        "100000"
    )
)

MAX_RECIPIENTS = int(
    os.environ.get(
        "MAX_RECIPIENTS",
        "10"
    )
)

DEFAULT_TTL = int(
    os.environ.get(
        "DEFAULT_TTL",
        str(7 * 24 * 60 * 60)
    )
)

MAX_SELF_DESTRUCT = int(
    os.environ.get(
        "MAX_SELF_DESTRUCT",
        "86400"
    )
)

CREATE_LIMIT = int(
    os.environ.get(
        "CREATE_LIMIT",
        "20"
    )
)

CREATE_WINDOW = int(
    os.environ.get(
        "CREATE_WINDOW",
        "60"
    )
)


# =========================================================
# 📝 LOGGING
# =========================================================

logging.basicConfig(
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
    level=logging.INFO,
)

logger = logging.getLogger(
    "WhisperBot"
)


# =========================================================
# 🔒 LOCKS
# =========================================================

DATA_LOCK = asyncio.Lock()

RATE_LIMIT_LOCK = asyncio.Lock()


# =========================================================
# 🧠 MEMORY
# =========================================================

# إنشاء الهمسات المتقدمة
CREATE_SESSIONS = {}

# المستخدمون الذين ينتظرون كلمة سر / إجابة
UNLOCK_SESSIONS = {}

# Inline pending whispers
INLINE_PENDING = {}

# Rate limiter
CREATE_HISTORY = defaultdict(deque)


# =========================================================
# 🧩 CONVERSATION STATES
# =========================================================

(
    CREATE_TYPE,
    CREATE_TEXT,
    CREATE_MEDIA,
    CREATE_AUDIENCE,
    CREATE_RECIPIENTS,
    CREATE_ANONYMOUS,
    CREATE_PROTECTION,
    CREATE_PASSWORD,
    CREATE_QUESTION,
    CREATE_ANSWER,
    CREATE_ONETIME,
    CREATE_SELF_DESTRUCT,
    CREATE_TIME,
    CREATE_BUTTON,
    CREATE_CONFIRM,
) = range(15)


# =========================================================
# 🧰 HELPERS
# =========================================================

def now():
    return int(time.time())


def escape(text):
    return html.escape(
        str(text)
    )


def user_name(user):
    return escape(
        user.first_name
        or "مستخدم"
    )


def is_admin(user_id):
    return (
        ADMIN_ID != 0
        and user_id == ADMIN_ID
    )


def make_id():
    return uuid.uuid4().hex[:16]


def format_time(ts):
    if not ts:
        return "غير محدد"

    return datetime.fromtimestamp(
        ts,
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def parse_seconds(text):
    """
    10s
    10m
    2h
    3d
    """

    text = text.strip().lower()

    if not text:
        return None

    try:

        if text.endswith("s"):
            return int(
                text[:-1]
            )

        if text.endswith("m"):
            return int(
                text[:-1]
            ) * 60

        if text.endswith("h"):
            return int(
                text[:-1]
            ) * 3600

        if text.endswith("d"):
            return int(
                text[:-1]
            ) * 86400

        return int(text)

    except ValueError:
        return None


# =========================================================
# 🗄️ DATABASE
# =========================================================

def empty_database():
    return {
        "version": 3,
        "whispers": {}
    }


def validate_database(data):

    if not isinstance(
        data,
        dict
    ):
        return False

    if not isinstance(
        data.get("whispers"),
        dict
    ):
        return False

    return True


def normalize_database(data):

    if not validate_database(
        data
    ):
        raise ValueError(
            "Invalid database structure"
        )

    result = empty_database()

    for whisper_id, w in data[
        "whispers"
    ].items():

        if not isinstance(
            w,
            dict
        ):
            continue

        if not isinstance(
            w.get("sender_id"),
            int
        ):
            continue

        if w.get(
            "content_type"
        ) not in (
            "text",
            "photo",
            "voice"
        ):
            continue

        recipients = w.get(
            "recipient_ids",
            []
        )

        if not isinstance(
            recipients,
            list
        ):
            recipients = []

        recipients = [
            int(x)
            for x in recipients
            if isinstance(
                x,
                int
            )
        ]

        opened_by = w.get(
            "opened_by",
            []
        )

        if not isinstance(
            opened_by,
            list
        ):
            opened_by = []

        opened_by = [
            int(x)
            for x in opened_by
            if isinstance(
                x,
                int
            )
        ]

        result[
            "whispers"
        ][whisper_id] = {

            "id": whisper_id,

            "sender_id":
                w["sender_id"],

            "sender_name":
                str(
                    w.get(
                        "sender_name",
                        "مستخدم"
                    )
                )[:100],

            "content_type":
                w["content_type"],

            "text":
                str(
                    w.get(
                        "text",
                        ""
                    )
                )[:MAX_TEXT_LENGTH],

            "file_id":
                w.get(
                    "file_id"
                ),

            "caption":
                str(
                    w.get(
                        "caption",
                        ""
                    )
                )[:1000],

            "audience":
                w.get(
                    "audience",
                    "first"
                ),

            "recipient_ids":
                recipients[
                    :MAX_RECIPIENTS
                ],

            "recipient_usernames":
                [
                    str(x).lower().lstrip("@")
                    for x in w.get(
                        "recipient_usernames",
                        []
                    )
                    if isinstance(
                        x,
                        str
                    )
                ][:MAX_RECIPIENTS],

            "anonymous":
                bool(
                    w.get(
                        "anonymous",
                        False
                    )
                ),

            "password":
                w.get(
                    "password"
                ),

            "question":
                w.get(
                    "question"
                ),

            "answer":
                w.get(
                    "answer"
                ),

            "one_time":
                bool(
                    w.get(
                        "one_time",
                        False
                    )
                ),

            "self_destruct":
                int(
                    w.get(
                        "self_destruct",
                        0
                    ) or 0
                ),

            "available_at":
                int(
                    w.get(
                        "available_at",
                        0
                    ) or 0
                ),

            "expires_at":
                int(
                    w.get(
                        "expires_at",
                        now() + DEFAULT_TTL
                    )
                ),

            "button_text":
                str(
                    w.get(
                        "button_text",
                        "👁️ اضغط لقراءة الهمسة"
                    )
                )[:100],

            "opened_by":
                opened_by,

            "created_at":
                int(
                    w.get(
                        "created_at",
                        now()
                    )
                ),

            "deleted":
                bool(
                    w.get(
                        "deleted",
                        False
                    )
                ),

            "delivered_messages":
                w.get(
                    "delivered_messages",
                    []
                ),
        }

    return result


def load_database_sync():

    if not DATA_FILE.exists():
        return empty_database()

    try:

        with DATA_FILE.open(
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return normalize_database(
            data
        )

    except Exception as exc:

        logger.exception(
            "Database read failed"
        )

        raise RuntimeError(
            "database.json is corrupted"
        ) from exc


async def load_database():

    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        None,
        load_database_sync
    )


def atomic_save_sync(data):

    DATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    serialized = json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="database_",
        suffix=".tmp",
        dir=str(
            DATA_FILE.parent
        )
    )

    temp_path = Path(
        temp_name
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                serialized
            )

            f.flush()

            os.fsync(
                f.fileno()
            )

        # Backup
        if DATA_FILE.exists():

            with DATA_FILE.open(
                "rb"
            ) as src:

                with BACKUP_FILE.open(
                    "wb"
                ) as dst:

                    while True:

                        chunk = src.read(
                            1024 * 1024
                        )

                        if not chunk:
                            break

                        dst.write(
                            chunk
                        )

        os.replace(
            temp_path,
            DATA_FILE
        )

    finally:

        if temp_path.exists():

            try:
                temp_path.unlink()
            except Exception:
                pass


async def save_database(data):

    if not validate_database(
        data
    ):
        raise ValueError(
            "Invalid database"
        )

    loop = asyncio.get_running_loop()

    await loop.run_in_executor(
        None,
        atomic_save_sync,
        data
    )


# =========================================================
# 🚦 RATE LIMIT
# =========================================================

async def rate_allowed(
    user_id
):

    current = time.monotonic()

    async with RATE_LIMIT_LOCK:

        history = CREATE_HISTORY[
            user_id
        ]

        while history and (
            current - history[0]
            > CREATE_WINDOW
        ):
            history.popleft()

        if len(history) >= CREATE_LIMIT:
            return False

        history.append(
            current
        )

        return True


# =========================================================
# 🧹 CLEANUP
# =========================================================

async def cleanup_job(
    context: ContextTypes.DEFAULT_TYPE
):

    async with DATA_LOCK:

        try:

            data = await load_database()

            changed = False

            current = now()

            for whisper_id in list(
                data["whispers"]
            ):

                whisper = data[
                    "whispers"
                ][whisper_id]

                # انتهاء الهمسة
                if (
                    whisper[
                        "expires_at"
                    ]
                    and whisper[
                        "expires_at"
                    ] <= current
                ):

                    del data[
                        "whispers"
                    ][whisper_id]

                    changed = True

                    continue

                # حذف الرسائل التي انتهى وقتها
                delivered = whisper.get(
                    "delivered_messages",
                    []
                )

                remaining = []

                for item in delivered:

                    destruct_at = item.get(
                        "destruct_at",
                        0
                    )

                    if (
                        destruct_at
                        and destruct_at <= current
                    ):

                        try:

                            await context.bot.delete_message(
                                chat_id=item[
                                    "chat_id"
                                ],
                                message_id=item[
                                    "message_id"
                                ]
                            )

                        except TelegramError:
                            pass

                    else:

                        remaining.append(
                            item
                        )

                if (
                    len(remaining)
                    != len(delivered)
                ):

                    whisper[
                        "delivered_messages"
                    ] = remaining

                    changed = True

            if changed:

                await save_database(
                    data
                )

        except Exception:

            logger.exception(
                "Cleanup job failed"
            )


# =========================================================
# 🏠 START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [
        [
            InlineKeyboardButton(
                "🤫 إنشاء همسة",
                callback_data="menu:create"
            )
        ],
        [
            InlineKeyboardButton(
                "📋 همساتي",
                callback_data="menu:my"
            ),
            InlineKeyboardButton(
                "📊 إحصائياتي",
                callback_data="menu:stats"
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ طريقة الاستخدام",
                callback_data="menu:help"
            )
        ]
    ]

    if is_admin(
        update.effective_user.id
    ):

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⚙️ الإدارة",
                    callback_data="menu:admin"
                )
            ]
        )

    await update.message.reply_text(

        "🤫 <b>مرحبًا بك في بوت الهمسات</b>\n\n"

        "أنشئ همسة سرية وأرسلها لأي شخص.\n\n"

        "يمكنك تحديد:\n"
        "👤 المستلم\n"
        "👥 عدة مستلمين\n"
        "👻 مجهول\n"
        "🔐 كلمة سر\n"
        "❓ سؤال وإجابة\n"
        "☝️ قراءة مرة واحدة\n"
        "💣 تدمير ذاتي\n"
        "⏰ وقت فتح مستقبلي\n"
        "🖼️ صورة أو 🎤 صوت\n\n"

        "أو استخدم Inline Mode للهمسات النصية السريعة.",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode=ParseMode.HTML
    )


# =========================================================
# ℹ️ HELP
# =========================================================

async def show_help(
    update,
    context
):

    query = update.callback_query

    await query.edit_message_text(

        "📖 <b>طريقة الاستخدام</b>\n\n"

        "1️⃣ اضغط «إنشاء همسة».\n"
        "2️⃣ اختر نوع المحتوى.\n"
        "3️⃣ حدد المستلم.\n"
        "4️⃣ اختر الحماية.\n"
        "5️⃣ حدد مدة التدمير إن أردت.\n"
        "6️⃣ حدد وقت الفتح إن أردت.\n"
        "7️⃣ حدد نص الزر.\n"
        "8️⃣ شارك الهمسة.\n\n"

        "⚠️ ملاحظة مهمة:\n"
        "عند إرسال همسة لشخص محدد، يجب أن يكون "
        "المستلم قد بدأ البوت في الخاص إذا كانت "
        "الهمسة تحتوي على كلمة مرور أو اختبار.",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="menu:home"
                )
            ]
        ])
    )


# =========================================================
# 🤫 CREATE
# =========================================================

async def create_start(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    CREATE_SESSIONS[
        user_id
    ] = {
        "sender_id": user_id
    }

    keyboard = [
        [
            InlineKeyboardButton(
                "📝 نص",
                callback_data="ctype:text"
            ),
            InlineKeyboardButton(
                "🖼️ صورة",
                callback_data="ctype:photo"
            )
        ],
        [
            InlineKeyboardButton(
                "🎤 صوت",
                callback_data="ctype:voice"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ إلغاء",
                callback_data="create:cancel"
            )
        ]
    ]

    await query.edit_message_text(

        "🤫 <b>إنشاء همسة جديدة</b>\n\n"
        "اختر نوع الهمسة:",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode=ParseMode.HTML
    )

    return CREATE_TYPE


# =========================================================
# CONTENT TYPE
# =========================================================

async def choose_content_type(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    ctype = query.data.split(
        ":",
        1
    )[1]

    session[
        "content_type"
    ] = ctype

    if ctype == "text":

        await query.edit_message_text(
            "📝 أرسل الآن نص الهمسة:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data="create:cancel"
                    )
                ]
            ])
        )

        return CREATE_TEXT

    if ctype == "photo":

        await query.edit_message_text(
            "🖼️ أرسل الصورة التي تريد جعلها همسة:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data="create:cancel"
                    )
                ]
            ])
        )

        return CREATE_MEDIA

    if ctype == "voice":

        await query.edit_message_text(
            "🎤 أرسل البصمة الصوتية أو الملف الصوتي:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data="create:cancel"
                    )
                ]
            ])
        )

        return CREATE_MEDIA


# =========================================================
# TEXT
# =========================================================

async def receive_text(
    update,
    context
):

    user_id = update.effective_user.id

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    text = (
        update.message.text or ""
    ).strip()

    if not text:

        await update.message.reply_text(
            "❌ النص فارغ."
        )

        return CREATE_TEXT

    if len(text) > MAX_TEXT_LENGTH:

        await update.message.reply_text(
            f"❌ الحد الأقصى للنص "
            f"{MAX_TEXT_LENGTH} حرف."
        )

        return CREATE_TEXT

    session[
        "text"
    ] = text

    return await ask_audience(
        update,
        context
    )


# =========================================================
# MEDIA
# =========================================================

async def receive_media(
    update,
    context
):

    user_id = update.effective_user.id

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    if (
        session[
            "content_type"
        ]
        == "photo"
    ):

        if not update.message.photo:

            await update.message.reply_text(
                "❌ أرسل صورة فقط."
            )

            return CREATE_MEDIA

        photo = update.message.photo[-1]

        session[
            "file_id"
        ] = photo.file_id

        session[
            "caption"
        ] = (
            update.message.caption
            or ""
        )[:1000]

    elif (
        session[
            "content_type"
        ]
        == "voice"
    ):

        if not update.message.voice:

            await update.message.reply_text(
                "❌ أرسل بصمة صوتية فقط."
            )

            return CREATE_MEDIA

        session[
            "file_id"
        ] = update.message.voice.file_id

    else:

        await update.message.reply_text(
            "❌ نوع الوسائط غير صحيح."
        )

        return CREATE_MEDIA

    return await ask_audience(
        update,
        context
    )


# =========================================================
# AUDIENCE
# =========================================================

async def ask_audience(
    update,
    context
):

    keyboard = [
        [
            InlineKeyboardButton(
                "👁️ أول شخص",
                callback_data="aud:first"
            ),
            InlineKeyboardButton(
                "👥 الجميع",
                callback_data="aud:all"
            )
        ],
        [
            InlineKeyboardButton(
                "👤 شخص محدد",
                callback_data="aud:single"
            ),
            InlineKeyboardButton(
                "👥 عدة أشخاص",
                callback_data="aud:multi"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ إلغاء",
                callback_data="create:cancel"
            )
        ]
    ]

    if update.callback_query:

        await update.callback_query.edit_message_text(
            "🎯 <b>من يستطيع قراءة الهمسة؟</b>",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    else:

        await update.message.reply_text(
            "🎯 <b>من يستطيع قراءة الهمسة؟</b>",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    return CREATE_AUDIENCE


# =========================================================
# AUDIENCE CALLBACK
# =========================================================

async def choose_audience(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    audience = query.data.split(
        ":",
        1
    )[1]

    session[
        "audience"
    ] = audience

    if audience == "single":

        await query.edit_message_text(
            "👤 أرسل معرف الشخص:\n\n"
            "<code>@username</code>\n\n"
            "أو أرسل رقمه إذا كان البوت يعرفه.",
            parse_mode=ParseMode.HTML
        )

        return CREATE_RECIPIENTS

    if audience == "multi":

        await query.edit_message_text(
            "👥 أرسل معرفات الأشخاص، كل معرف في سطر:\n\n"
            "<code>@user1\n"
            "@user2\n"
            "@user3</code>",
            parse_mode=ParseMode.HTML
        )

        return CREATE_RECIPIENTS

    return await ask_anonymous(
        update,
        context
    )


# =========================================================
# RECIPIENTS
# =========================================================

async def receive_recipients(
    update,
    context
):

    user_id = update.effective_user.id

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    lines = (
        update.message.text
        .splitlines()
    )

    usernames = []

    for line in lines:

        username = (
            line.strip()
            .lower()
            .lstrip("@")
        )

        if not username:
            continue

        if (
            not username.replace(
                "_",
                ""
            ).isalnum()
        ):
            continue

        if username not in usernames:
            usernames.append(
                username
            )

    if not usernames:

        await update.message.reply_text(
            "❌ لم أجد معرفًا صحيحًا."
        )

        return CREATE_RECIPIENTS

    if len(usernames) > MAX_RECIPIENTS:

        await update.message.reply_text(
            f"❌ الحد الأقصى "
            f"{MAX_RECIPIENTS} أشخاص."
        )

        return CREATE_RECIPIENTS

    session[
        "recipient_usernames"
    ] = usernames

    return await ask_anonymous_message(
        update,
        context
    )


# =========================================================
# ANONYMOUS
# =========================================================

async def ask_anonymous(
    update,
    context
):

    user_id = update.effective_user.id

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    session[
        "recipient_usernames"
    ] = []

    return await ask_anonymous_message(
        update,
        context
    )


async def ask_anonymous_message(
    update,
    context
):

    keyboard = [
        [
            InlineKeyboardButton(
                "👻 نعم، مجهولة",
                callback_data="anon:yes"
            ),
            InlineKeyboardButton(
                "👤 إظهار اسمي",
                callback_data="anon:no"
            )
        ]
    ]

    if update.callback_query:

        await update.callback_query.edit_message_text(
            "👻 <b>هل تريد إخفاء هويتك؟</b>",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    else:

        await update.message.reply_text(
            "👻 <b>هل تريد إخفاء هويتك؟</b>",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    return CREATE_ANONYMOUS


async def choose_anonymous(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    session[
        "anonymous"
    ] = (
        query.data
        == "anon:yes"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔓 بدون حماية",
                callback_data="protect:none"
            )
        ],
        [
            InlineKeyboardButton(
                "🔐 كلمة مرور",
                callback_data="protect:password"
            )
        ],
        [
            InlineKeyboardButton(
                "❓ سؤال وإجابة",
                callback_data="protect:quiz"
            )
        ]
    ]

    await query.edit_message_text(
        "🛡️ <b>اختر حماية الهمسة:</b>",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode=ParseMode.HTML
    )

    return CREATE_PROTECTION


# =========================================================
# PROTECTION
# =========================================================

async def choose_protection(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    protection = query.data.split(
        ":",
        1
    )[1]

    session[
        "protection"
    ] = protection

    if protection == "password":

        await query.edit_message_text(
            "🔐 أرسل كلمة المرور التي يجب "
            "على المستلم إدخالها:"
        )

        return CREATE_PASSWORD

    if protection == "quiz":

        await query.edit_message_text(
            "❓ أرسل السؤال الذي يجب "
            "على المستلم الإجابة عنه:"
        )

        return CREATE_QUESTION

    return await ask_onetime(
        update,
        context
    )


async def receive_password(
    update,
    context
):

    session = CREATE_SESSIONS.get(
        update.effective_user.id
    )

    if not session:
        return ConversationHandler.END

    password = (
        update.message.text
        or ""
    ).strip()

    if not password:

        await update.message.reply_text(
            "❌ كلمة المرور فارغة."
        )

        return CREATE_PASSWORD

    session[
        "password"
    ] = password[:200]

    return await ask_onetime(
        update,
        context
    )


async def receive_question(
    update,
    context
):

    session = CREATE_SESSIONS.get(
        update.effective_user.id
    )

    if not session:
        return ConversationHandler.END

    session[
        "question"
    ] = (
        update.message.text
        or ""
    )[:500]

    await update.message.reply_text(
        "✍️ الآن أرسل الإجابة الصحيحة:"
    )

    return CREATE_ANSWER


async def receive_answer(
    update,
    context
):

    session = CREATE_SESSIONS.get(
        update.effective_user.id
    )

    if not session:
        return ConversationHandler.END

    session[
        "answer"
    ] = (
        update.message.text
        or ""
    ).strip()[:200]

    return await ask_onetime(
        update,
        context
    )


# =========================================================
# ONE TIME
# =========================================================

async def ask_onetime(
    update,
    context
):

    keyboard = [
        [
            InlineKeyboardButton(
                "☝️ نعم، مرة واحدة",
                callback_data="once:yes"
            ),
            InlineKeyboardButton(
                "🔁 يمكن إعادة القراءة",
                callback_data="once:no"
            )
        ]
    ]

    if update.callback_query:

        await update.callback_query.edit_message_text(
            "☝️ <b>هل تسمح بالقراءة مرة واحدة فقط؟</b>",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    else:

        await update.message.reply_text(
            "☝️ <b>هل تسمح بالقراءة مرة واحدة فقط؟</b>",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    return CREATE_ONETIME


async def choose_onetime(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    session = CREATE_SESSIONS.get(
        query.from_user.id
    )

    if not session:
        return ConversationHandler.END

    session[
        "one_time"
    ] = (
        query.data
        == "once:yes"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🚫 بدون تدمير ذاتي",
                callback_data="destroy:0"
            )
        ],
        [
            InlineKeyboardButton(
                "💣 بعد 10 ثوانٍ",
                callback_data="destroy:10"
            ),
            InlineKeyboardButton(
                "💣 بعد 30 ثانية",
                callback_data="destroy:30"
            )
        ],
        [
            InlineKeyboardButton(
                "💣 بعد دقيقة",
                callback_data="destroy:60"
            ),
            InlineKeyboardButton(
                "💣 بعد 5 دقائق",
                callback_data="destroy:300"
            )
        ]
    ]

    await query.edit_message_text(
        "💣 <b>التدمير الذاتي</b>\n\n"
        "ملاحظة: التدمير الذاتي يحذف "
        "الرسالة التي أرسلها البوت للمستلم.",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode=ParseMode.HTML
    )

    return CREATE_SELF_DESTRUCT


async def choose_self_destruct(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    session = CREATE_SESSIONS.get(
        query.from_user.id
    )

    if not session:
        return ConversationHandler.END

    seconds = int(
        query.data.split(
            ":",
            1
        )[1]
    )

    session[
        "self_destruct"
    ] = min(
        seconds,
        MAX_SELF_DESTRUCT
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "⚡ الآن",
                callback_data="time:now"
            )
        ],
        [
            InlineKeyboardButton(
                "⏰ بعد ساعة",
                callback_data="time:1h"
            ),
            InlineKeyboardButton(
                "⏰ بعد يوم",
                callback_data="time:1d"
            )
        ],
        [
            InlineKeyboardButton(
                "🕒 أدخل مدة مخصصة",
                callback_data="time:custom"
            )
        ]
    ]

    await query.edit_message_text(
        "⏰ <b>متى تصبح الهمسة قابلة للفتح؟</b>",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode=ParseMode.HTML
    )

    return CREATE_TIME


# =========================================================
# TIME
# =========================================================

async def choose_time(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    session = CREATE_SESSIONS.get(
        query.from_user.id
    )

    if not session:
        return ConversationHandler.END

    value = query.data.split(
        ":",
        1
    )[1]

    if value == "now":

        session[
            "available_at"
        ] = 0

        return await ask_button(
            update,
            context
        )

    if value == "1h":

        session[
            "available_at"
        ] = now() + 3600

        return await ask_button(
            update,
            context
        )

    if value == "1d":

        session[
            "available_at"
        ] = now() + 86400

        return await ask_button(
            update,
            context
        )

    await query.edit_message_text(
        "⏰ أرسل المدة بهذا الشكل:\n\n"
        "<code>30m</code>\n"
        "<code>2h</code>\n"
        "<code>3d</code>",
        parse_mode=ParseMode.HTML
    )

    return CREATE_TIME


async def receive_custom_time(
    update,
    context
):

    session = CREATE_SESSIONS.get(
        update.effective_user.id
    )

    if not session:
        return ConversationHandler.END

    seconds = parse_seconds(
        update.message.text
    )

    if seconds is None:

        await update.message.reply_text(
            "❌ صيغة غير صحيحة."
        )

        return CREATE_TIME

    if seconds < 0:

        await update.message.reply_text(
            "❌ المدة غير صحيحة."
        )

        return CREATE_TIME

    if seconds > 30 * 86400:

        await update.message.reply_text(
            "❌ الحد الأقصى 30 يومًا."
        )

        return CREATE_TIME

    session[
        "available_at"
    ] = now() + seconds

    return await ask_button(
        update,
        context
    )


# =========================================================
# BUTTON TEXT
# =========================================================

async def ask_button(
    update,
    context
):

    text = (
        "✏️ <b>نص الزر</b>\n\n"
        "أرسل النص الذي سيظهر على زر فتح الهمسة.\n\n"
        "مثال:\n"
        "<code>🔐 سر بيني وبينك</code>\n\n"
        "أو اضغط افتراضي:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "👁️ اضغط لقراءة الهمسة",
                callback_data="button:default"
            )
        ]
    ]

    if update.callback_query:

        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    else:

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    return CREATE_BUTTON


async def choose_default_button(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    session = CREATE_SESSIONS.get(
        query.from_user.id
    )

    if not session:
        return ConversationHandler.END

    session[
        "button_text"
    ] = "👁️ اضغط لقراءة الهمسة"

    return await confirm_whisper(
        update,
        context
    )


async def receive_button(
    update,
    context
):

    session = CREATE_SESSIONS.get(
        update.effective_user.id
    )

    if not session:
        return ConversationHandler.END

    text = (
        update.message.text
        or ""
    ).strip()

    if not text:

        await update.message.reply_text(
            "❌ نص الزر فارغ."
        )

        return CREATE_BUTTON

    session[
        "button_text"
    ] = text[:100]

    return await confirm_whisper(
        update,
        context
    )


# =========================================================
# CONFIRM
# =========================================================

async def confirm_whisper(
    update,
    context
):

    user_id = (
        update.effective_user.id
        if update.effective_user
        else update.callback_query.from_user.id
    )

    session = CREATE_SESSIONS.get(
        user_id
    )

    if not session:
        return ConversationHandler.END

    ctype = session.get(
        "content_type"
    )

    audience = session.get(
        "audience",
        "first"
    )

    protection = session.get(
        "protection",
        "none"
    )

    audience_name = {
        "first": "👁️ أول شخص",
        "all": "👥 الجميع",
        "single": "👤 شخص محدد",
        "multi": "👥 عدة أشخاص"
    }.get(
        audience,
        "غير معروف"
    )

    protection_name = {
        "none": "🔓 بدون حماية",
        "password": "🔐 كلمة مرور",
        "quiz": "❓ سؤال وإجابة"
    }.get(
        protection,
        "غير معروف"
    )

    content_name = {
        "text": "📝 نص",
        "photo": "🖼️ صورة",
        "voice": "🎤 صوت"
    }.get(
        ctype,
        "غير معروف"
    )

    text = (
        "📋 <b>مراجعة الهمسة</b>\n\n"
        f"المحتوى: {content_name}\n"
        f"المستلمون: {audience_name}\n"
        f"الحماية: {protection_name}\n"
        f"👻 مجهولة: "
        f"{'نعم' if session.get('anonymous') else 'لا'}\n"
        f"☝️ مرة واحدة: "
        f"{'نعم' if session.get('one_time') else 'لا'}\n"
        f"💣 التدمير الذاتي: "
        f"{session.get('self_destruct', 0)} ثانية\n"
        f"⏰ وقت الفتح: "
        f"{format_time(session.get('available_at'))}\n"
        f"🔘 الزر: "
        f"{escape(session.get('button_text', ''))}\n"
    )

    if ctype == "text":

        preview = session.get(
            "text",
            ""
        )

        text += (
            "\n<b>معاينة:</b>\n"
            f"{escape(preview[:500])}"
        )

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ إنشاء الهمسة",
                callback_data="create:save"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ إلغاء",
                callback_data="create:cancel"
            )
        ]
    ]

    if update.callback_query:

        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    else:

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )

    return CREATE_CONFIRM


# =========================================================
# SAVE WHISPER
# =========================================================

async def save_created_whisper(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    session = CREATE_SESSIONS.get(
        user.id
    )

    if not session:
        return ConversationHandler.END

    if not await rate_allowed(
        user.id
    ):

        await query.edit_message_text(
            "🚫 وصلت إلى حد إنشاء الهمسات مؤقتًا.\n\n"
            "حاول بعد قليل."
        )

        return ConversationHandler.END

    async with DATA_LOCK:

        try:

            data = await load_database()

            if (
                len(data["whispers"])
                >= MAX_WHISPERS
            ):

                await query.edit_message_text(
                    "❌ قاعدة البيانات ممتلئة حاليًا."
                )

                return ConversationHandler.END

            whisper_id = make_id()

            created = now()

            available_at = session.get(
                "available_at",
                0
            )

            # انتهاء افتراضي
            expires_at = (
                max(
                    created,
                    available_at
                )
                + DEFAULT_TTL
            )

            whisper = {

                "id":
                    whisper_id,

                "sender_id":
                    user.id,

                "sender_name":
                    user.first_name
                    or "مستخدم",

                "content_type":
                    session[
                        "content_type"
                    ],

                "text":
                    session.get(
                        "text",
                        ""
                    ),

                "file_id":
                    session.get(
                        "file_id"
                    ),

                "caption":
                    session.get(
                        "caption",
                        ""
                    ),

                "audience":
                    session.get(
                        "audience",
                        "first"
                    ),

                "recipient_ids":
                    session.get(
                        "recipient_ids",
                        []
                    ),

                "recipient_usernames":
                    session.get(
                        "recipient_usernames",
                        []
                    ),

                "anonymous":
                    bool(
                        session.get(
                            "anonymous",
                            False
                        )
                    ),

                "password":
                    session.get(
                        "password"
                    ),

                "question":
                    session.get(
                        "question"
                    ),

                "answer":
                    session.get(
                        "answer"
                    ),

                "one_time":
                    bool(
                        session.get(
                            "one_time",
                            False
                        )
                    ),

                "self_destruct":
                    int(
                        session.get(
                            "self_destruct",
                            0
                        )
                    ),

                "available_at":
                    available_at,

                "expires_at":
                    expires_at,

                "button_text":
                    session.get(
                        "button_text",
                        "👁️ اضغط لقراءة الهمسة"
                    ),

                "opened_by":
                    [],

                "created_at":
                    created,

                "deleted":
                    False,

                "delivered_messages":
                    []
            }

            data[
                "whispers"
            ][whisper_id] = whisper

            await save_database(
                data
            )

        except Exception:

            logger.exception(
                "Could not save whisper"
            )

            await query.edit_message_text(
                "❌ حدث خطأ أثناء إنشاء الهمسة."
            )

            return ConversationHandler.END

    # تنظيف الجلسة
    CREATE_SESSIONS.pop(
        user.id,
        None
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                whisper["button_text"],
                callback_data=f"open:{whisper_id}"
            )
        ]
    ])

    await query.edit_message_text(

        "✅ <b>تم إنشاء الهمسة!</b>\n\n"
        "اضغط الزر لمعاينتها، أو استخدم "
        "زر المشاركة الموجود في Telegram "
        "لإرسالها للشخص المطلوب.",

        reply_markup=keyboard,

        parse_mode=ParseMode.HTML
    )

    return ConversationHandler.END


# =========================================================
# CANCEL
# =========================================================

async def cancel_create(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    CREATE_SESSIONS.pop(
        query.from_user.id,
        None
    )

    await query.edit_message_text(
        "❌ تم إلغاء إنشاء الهمسة."
    )

    return ConversationHandler.END


# =========================================================
# 🔓 OPEN WHISPER
# =========================================================

async def open_whisper(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    whisper_id = query.data.split(
        ":",
        1
    )[1]

    async with DATA_LOCK:

        try:

            data = await load_database()

            whisper = data[
                "whispers"
            ].get(
                whisper_id
            )

            if not whisper:

                await query.answer(
                    "❌ هذه الهمسة غير موجودة.",
                    show_alert=True
                )

                return

            if whisper.get(
                "deleted"
            ):

                await query.answer(
                    "🗑️ تم حذف هذه الهمسة.",
                    show_alert=True
                )

                return

            current = now()

            # انتهاء الهمسة
            if (
                whisper[
                    "expires_at"
                ]
                <= current
            ):

                del data[
                    "whispers"
                ][whisper_id]

                await save_database(
                    data
                )

                await query.answer(
                    "⏰ انتهت صلاحية الهمسة.",
                    show_alert=True
                )

                return

            # الكبسولة الزمنية
            if (
                whisper[
                    "available_at"
                ]
                and current
                < whisper[
                    "available_at"
                ]
            ):

                remaining = (
                    whisper[
                        "available_at"
                    ]
                    - current
                )

                minutes = max(
                    1,
                    remaining // 60
                )

                await query.answer(
                    f"⏰ هذه الهمسة ستفتح بعد "
                    f"{minutes} دقيقة.",
                    show_alert=True
                )

                return

            # -------------------------------------------------
            # Authorization
            # -------------------------------------------------

            allowed = False

            audience = whisper[
                "audience"
            ]

            if audience == "all":
                allowed = True

            elif audience == "first":

                opened = whisper[
                    "opened_by"
                ]

                if not opened:
                    allowed = True

                elif user.id in opened:
                    allowed = True

            elif audience in (
                "single",
                "multi"
            ):

                if user.id in whisper[
                    "recipient_ids"
                ]:
                    allowed = True

                username = (
                    user.username
                    or ""
                ).lower()

                username = username.lstrip("@")

                if username and (
                    username in whisper[
                        "recipient_usernames"
                    ]
                ):
                    allowed = True

            if not allowed:

                await query.answer(
                    "🚫 هذه الهمسة ليست مخصصة لك.",
                    show_alert=True
                )

                return

            # -------------------------------------------------
            # One Time
            # -------------------------------------------------

            opened_by = whisper[
                "opened_by"
            ]

            if (
                whisper[
                    "one_time"
                ]
                and user.id in opened_by
            ):

                await query.answer(
                    "☝️ لقد قرأت هذه الهمسة مسبقًا "
                    "ولا يمكن فتحها مرة أخرى.",
                    show_alert=True
                )

                return

            # -------------------------------------------------
            # Password
            # -------------------------------------------------

            if whisper.get(
                "password"
            ):

                UNLOCK_SESSIONS[
                    user.id
                ] = {
                    "whisper_id":
                        whisper_id,

                    "mode":
                        "password"
                }

                try:

                    await context.bot.send_message(

                        chat_id=user.id,

                        text=(
                            "🔐 <b>هذه الهمسة محمية بكلمة مرور.</b>\n\n"
                            "أرسل كلمة المرور هنا باستخدام:\n"
                            "<code>/unlock كلمة_المرور</code>"
                        ),

                        parse_mode=ParseMode.HTML
                    )

                    await query.answer(
                        "🔐 أرسلت لك تعليمات الفتح في الخاص.",
                        show_alert=True
                    )

                except Forbidden:

                    await query.answer(
                        "❗ يجب أن تبدأ محادثة خاصة مع "
                        "البوت أولاً حتى أستطيع طلب كلمة المرور.",
                        show_alert=True
                    )

                return

            # -------------------------------------------------
            # Quiz
            # -------------------------------------------------

            if (
                whisper.get(
                    "question"
                )
                and whisper.get(
                    "answer"
                )
            ):

                UNLOCK_SESSIONS[
                    user.id
                ] = {
                    "whisper_id":
                        whisper_id,

                    "mode":
                        "quiz"
                }

                try:

                    await context.bot.send_message(

                        chat_id=user.id,

                        text=(
                            "❓ <b>اختبار الهمسة</b>\n\n"
                            f"{escape(whisper['question'])}\n\n"
                            "أرسل إجابتك باستخدام:\n"
                            "<code>/answer إجابتك</code>"
                        ),

                        parse_mode=ParseMode.HTML
                    )

                    await query.answer(
                        "❓ أرسلت السؤال إلى الخاص.",
                        show_alert=True
                    )

                except Forbidden:

                    await query.answer(
                        "❗ يجب أن تبدأ محادثة خاصة مع "
                        "البوت أولاً.",
                        show_alert=True
                    )

                return

            # -------------------------------------------------
            # Deliver
            # -------------------------------------------------

            await deliver_whisper(
                context,
                whisper,
                user,
                data
            )

            # سجل الفتح
            if user.id not in opened_by:

                opened_by.append(
                    user.id
                )

            whisper[
                "opened_by"
            ] = opened_by

            await save_database(
                data
            )

        except Exception:

            logger.exception(
                "Open whisper failed"
            )

            await query.answer(
                "❌ حدث خطأ أثناء فتح الهمسة.",
                show_alert=True
            )


# =========================================================
# 📤 DELIVER WHISPER
# =========================================================

async def deliver_whisper(
    context,
    whisper,
    user,
    data
):

    display_sender = (
        "مجهول"
        if whisper[
            "anonymous"
        ]
        else whisper[
            "sender_name"
        ]
    )

    header = (
        "🤫 <b>همسة سرية</b>\n\n"
        f"من: <b>{escape(display_sender)}</b>\n\n"
    )

    sent = None

    ctype = whisper[
        "content_type"
    ]

    try:

        # النص
        if ctype == "text":

            sent = await context.bot.send_message(

                chat_id=user.id,

                text=(
                    header
                    + escape(
                        whisper["text"]
                    )
                ),

                parse_mode=ParseMode.HTML
            )

        # صورة
        elif ctype == "photo":

            sent = await context.bot.send_photo(

                chat_id=user.id,

                photo=whisper[
                    "file_id"
                ],

                caption=(
                    header
                    + escape(
                        whisper.get(
                            "caption",
                            ""
                        )
                    )
                ),

                parse_mode=ParseMode.HTML
            )

        # صوت
        elif ctype == "voice":

            sent = await context.bot.send_voice(

                chat_id=user.id,

                voice=whisper[
                    "file_id"
                ],

                caption=header,

                parse_mode=ParseMode.HTML
            )

        else:

            raise ValueError(
                "Unknown content type"
            )

    except Forbidden:

        raise

    # -----------------------------------------------------
    # سجل الرسالة
    # -----------------------------------------------------

    if sent:

        destruct_at = 0

        if whisper[
            "self_destruct"
        ] > 0:

            destruct_at = (
                now()
                + whisper[
                    "self_destruct"
                ]
            )

        whisper[
            "delivered_messages"
        ].append({

            "user_id":
                user.id,

            "chat_id":
                sent.chat_id,

            "message_id":
                sent.message_id,

            "destruct_at":
                destruct_at
        })

        # -------------------------------------------------
        # Read notification
        # -------------------------------------------------

        try:

            if whisper[
                "sender_id"
            ] != user.id:

                await context.bot.send_message(

                    chat_id=whisper[
                        "sender_id"
                    ],

                    text=(
                        "🔔 <b>تم فتح همستك الآن!</b>\n\n"
                        f"👤 بواسطة: "
                        f"<a href=\"tg://user?id={user.id}\">"
                        f"{escape(user.first_name or 'مستخدم')}"
                        f"</a>"
                    ),

                    parse_mode=ParseMode.HTML
                )

        except TelegramError:

            logger.warning(
                "Could not send read notification"
            )

        # -------------------------------------------------
        # Schedule destruction
        # -------------------------------------------------

        if (
            whisper[
                "self_destruct"
            ] > 0
        ):

            asyncio.create_task(
                destroy_message_later(
                    context,
                    sent.chat_id,
                    sent.message_id,
                    whisper[
                        "self_destruct"
                    ]
                )
            )


# =========================================================
# 💣 SELF DESTRUCT
# =========================================================

async def destroy_message_later(
    context,
    chat_id,
    message_id,
    seconds
):

    await asyncio.sleep(
        seconds
    )

    try:

        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )

    except TelegramError:
        pass


# =========================================================
# 🔐 UNLOCK
# =========================================================

async def unlock_command(
    update,
    context
):

    user_id = update.effective_user.id

    session = UNLOCK_SESSIONS.get(
        user_id
    )

    if not session:

        await update.message.reply_text(
            "❌ لا توجد همسة تنتظر الفتح."
        )

        return

    whisper_id = session[
        "whisper_id"
    ]

    async with DATA_LOCK:

        try:

            data = await load_database()

            whisper = data[
                "whispers"
            ].get(
                whisper_id
            )

            if not whisper:

                await update.message.reply_text(
                    "❌ الهمسة غير موجودة."
                )

                UNLOCK_SESSIONS.pop(
                    user_id,
                    None
                )

                return

            if (
                whisper[
                    "expires_at"
                ]
                <= now()
            ):

                await update.message.reply_text(
                    "⏰ انتهت صلاحية الهمسة."
                )

                UNLOCK_SESSIONS.pop(
                    user_id,
                    None
                )

                return

            supplied = " ".join(
                context.args
            ).strip()

            if session[
                "mode"
            ] == "password":

                if supplied != whisper[
                    "password"
                ]:

                    await update.message.reply_text(
                        "❌ كلمة المرور خاطئة."
                    )

                    return

            else:

                correct = (
                    supplied.strip().lower()
                    ==
                    whisper[
                        "answer"
                    ].strip().lower()
                )

                if not correct:

                    await update.message.reply_text(
                        "❌ إجابة خاطئة."
                    )

                    return

            # One-time
            if (
                whisper[
                    "one_time"
                ]
                and user_id in whisper[
                    "opened_by"
                ]
            ):

                await update.message.reply_text(
                    "☝️ سبق لك قراءة هذه الهمسة."
                )

                UNLOCK_SESSIONS.pop(
                    user_id,
                    None
                )

                return

            await deliver_whisper(
                context,
                whisper,
                update.effective_user,
                data
            )

            if user_id not in whisper[
                "opened_by"
            ]:

                whisper[
                    "opened_by"
                ].append(
                    user_id
                )

            await save_database(
                data
            )

            UNLOCK_SESSIONS.pop(
                user_id,
                None
            )

            await update.message.reply_text(
                "✅ تم فتح الهمسة."
            )

        except Exception:

            logger.exception(
                "Unlock failed"
            )

            await update.message.reply_text(
                "❌ حدث خطأ أثناء فتح الهمسة."
            )


# =========================================================
# ❓ ANSWER
# =========================================================

async def answer_command(
    update,
    context
):

    # نفس unlock ولكن mode=quiz
    await unlock_command(
        update,
        context
    )


# =========================================================
# 📋 MY WHISPERS
# =========================================================

async def my_whispers(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    async with DATA_LOCK:

        try:

            data = await load_database()

            items = []

            for whisper in data[
                "whispers"
            ].values():

                if whisper[
                    "sender_id"
                ] == user_id:

                    items.append(
                        whisper
                    )

            if not items:

                await query.edit_message_text(
                    "📭 لا توجد لديك همسات نشطة.",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "🤫 إنشاء همسة",
                                callback_data="menu:create"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⬅️ رجوع",
                                callback_data="menu:home"
                            )
                        ]
                    ])
                )

                return

            items = items[
                -10:
            ]

            buttons = []

            for whisper in reversed(
                items
            ):

                status = (
                    "👁️ مفتوحة"
                    if whisper[
                        "opened_by"
                    ]
                    else "⏳ لم تفتح"
                )

                buttons.append([
                    InlineKeyboardButton(
                        f"🤫 {whisper['id']} • {status}",
                        callback_data=(
                            f"details:{whisper['id']}"
                        )
                    )
                ])

            buttons.append([
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="menu:home"
                )
            ])

            await query.edit_message_text(

                "📋 <b>همساتي</b>\n\n"
                "آخر 10 همسات:",

                reply_markup=InlineKeyboardMarkup(
                    buttons
                ),

                parse_mode=ParseMode.HTML
            )

        except Exception:

            logger.exception(
                "My whispers failed"
            )

            await query.edit_message_text(
                "❌ تعذر تحميل الهمسات."
            )


# =========================================================
# 📄 DETAILS
# =========================================================

async def whisper_details(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    whisper_id = query.data.split(
        ":",
        1
    )[1]

    async with DATA_LOCK:

        data = await load_database()

        whisper = data[
            "whispers"
        ].get(
            whisper_id
        )

        if not whisper:

            await query.edit_message_text(
                "❌ الهمسة غير موجودة."
            )

            return

        if whisper[
            "sender_id"
        ] != query.from_user.id:

            await query.answer(
                "🚫 ليست همستك.",
                show_alert=True
            )

            return

        text = (
            "🤫 <b>تفاصيل الهمسة</b>\n\n"
            f"🆔 <code>{whisper_id}</code>\n"
            f"📦 النوع: {whisper['content_type']}\n"
            f"🎯 الجمهور: {whisper['audience']}\n"
            f"👻 مجهولة: "
            f"{'نعم' if whisper['anonymous'] else 'لا'}\n"
            f"☝️ مرة واحدة: "
            f"{'نعم' if whisper['one_time'] else 'لا'}\n"
            f"💣 التدمير: "
            f"{whisper['self_destruct']} ثانية\n"
            f"⏰ الفتح: "
            f"{format_time(whisper['available_at'])}\n"
            f"⌛ الانتهاء: "
            f"{format_time(whisper['expires_at'])}\n"
            f"👁️ مرات الفتح: "
            f"{len(whisper['opened_by'])}"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🗑️ حذف الهمسة",
                    callback_data=(
                        f"delete:{whisper_id}"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="menu:my"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.HTML
        )


# =========================================================
# 🗑️ DELETE
# =========================================================

async def delete_whisper(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    whisper_id = query.data.split(
        ":",
        1
    )[1]

    async with DATA_LOCK:

        data = await load_database()

        whisper = data[
            "whispers"
        ].get(
            whisper_id
        )

        if not whisper:

            await query.edit_message_text(
                "❌ الهمسة غير موجودة."
            )

            return

        if whisper[
            "sender_id"
        ] != query.from_user.id:

            await query.answer(
                "🚫 لا يمكنك حذف هذه الهمسة.",
                show_alert=True
            )

            return

        del data[
            "whispers"
        ][whisper_id]

        await save_database(
            data
        )

    await query.edit_message_text(
        "🗑️ تم حذف الهمسة بنجاح."
    )


# =========================================================
# 📊 STATS
# =========================================================

async def stats(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    async with DATA_LOCK:

        data = await load_database()

        mine = [
            w
            for w in data[
                "whispers"
            ].values()
            if w[
                "sender_id"
            ] == user_id
        ]

        opened = sum(
            1
            for w in mine
            if w[
                "opened_by"
            ]
        )

        await query.edit_message_text(

            "📊 <b>إحصائياتك</b>\n\n"
            f"🤫 الهمسات: <b>{len(mine)}</b>\n"
            f"👁️ همسات تم فتحها: <b>{opened}</b>\n"
            f"⏳ لم تفتح بعد: "
            f"<b>{len(mine) - opened}</b>",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع",
                        callback_data="menu:home"
                    )
                ]
            ]),

            parse_mode=ParseMode.HTML
        )


# =========================================================
# ⚙️ ADMIN
# =========================================================

async def admin_menu(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    if not is_admin(
        query.from_user.id
    ):
        return

    await query.edit_message_text(

        "⚙️ <b>لوحة الإدارة</b>\n\n"
        "اختر العملية:",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📊 إحصائيات عامة",
                    callback_data="admin:stats"
                )
            ],
            [
                InlineKeyboardButton(
                    "🧹 تنظيف",
                    callback_data="admin:cleanup"
                )
            ],
            [
                InlineKeyboardButton(
                    "📤 تصدير",
                    callback_data="admin:export"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="menu:home"
                )
            ]
        ]),

        parse_mode=ParseMode.HTML
    )


async def admin_stats(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    if not is_admin(
        query.from_user.id
    ):
        return

    async with DATA_LOCK:

        data = await load_database()

        whispers = list(
            data[
                "whispers"
            ].values()
        )

        text_count = sum(
            1
            for w in whispers
            if w[
                "content_type"
            ] == "text"
        )

        photo_count = sum(
            1
            for w in whispers
            if w[
                "content_type"
            ] == "photo"
        )

        voice_count = sum(
            1
            for w in whispers
            if w[
                "content_type"
            ] == "voice"
        )

        await query.edit_message_text(

            "📊 <b>إحصائيات عامة</b>\n\n"
            f"🤫 إجمالي الهمسات: "
            f"<b>{len(whispers)}</b>\n"
            f"📝 نص: <b>{text_count}</b>\n"
            f"🖼️ صور: <b>{photo_count}</b>\n"
            f"🎤 صوت: <b>{voice_count}</b>",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع",
                        callback_data="menu:admin"
                    )
                ]
            ]),

            parse_mode=ParseMode.HTML
        )


async def admin_cleanup(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    if not is_admin(
        query.from_user.id
    ):
        return

    async with DATA_LOCK:

        data = await load_database()

        current = now()

        removed = 0

        for whisper_id in list(
            data[
                "whispers"
            ]
        ):

            if data[
                "whispers"
            ][
                whisper_id
            ][
                "expires_at"
            ] <= current:

                del data[
                    "whispers"
                ][whisper_id]

                removed += 1

        await save_database(
            data
        )

    await query.edit_message_text(
        f"🧹 تم التنظيف.\n\n"
        f"🗑️ تم حذف {removed} همسة."
    )


async def admin_export(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    if not is_admin(
        query.from_user.id
    ):
        return

    if not DATA_FILE.exists():

        await query.edit_message_text(
            "❌ لا توجد قاعدة بيانات."
        )

        return

    try:

        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=str(
                DATA_FILE
            ),
            caption=(
                "📦 نسخة قاعدة بيانات الهمسات."
            )
        )

        await query.edit_message_text(
            "✅ تم إرسال النسخة الاحتياطية إلى الخاص."
        )

    except TelegramError:

        await query.edit_message_text(
            "❌ فشل إرسال النسخة الاحتياطية."
        )


# =========================================================
# 📥 IMPORT DOCUMENT
# =========================================================

async def import_document(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):
        return

    document = update.message.document

    if not document:
        return

    filename = (
        document.file_name
        or ""
    ).lower()

    if not filename.endswith(
        ".json"
    ):

        await update.message.reply_text(
            "❌ أرسل ملف JSON فقط."
        )

        return

    if (
        document.file_size
        and document.file_size
        > 20 * 1024 * 1024
    ):

        await update.message.reply_text(
            "❌ الملف أكبر من 20MB."
        )

        return

    async with DATA_LOCK:

        temp_path = (
            DATA_FILE.parent
            / "import.tmp"
        )

        try:

            tg_file = await context.bot.get_file(
                document.file_id
            )

            await tg_file.download_to_drive(
                custom_path=str(
                    temp_path
                )
            )

            with temp_path.open(
                "r",
                encoding="utf-8"
            ) as f:

                raw = json.load(
                    f
                )

            data = normalize_database(
                raw
            )

            if len(
                data["whispers"]
            ) > MAX_WHISPERS:

                raise ValueError(
                    "Too many whispers"
                )

            await save_database(
                data
            )

            temp_path.unlink(
                missing_ok=True
            )

            await update.message.reply_text(
                "✅ تم استيراد قاعدة البيانات بنجاح.\n\n"
                f"عدد الهمسات: "
                f"{len(data['whispers'])}"
            )

        except Exception:

            logger.exception(
                "Import failed"
            )

            temp_path.unlink(
                missing_ok=True
            )

            await update.message.reply_text(
                "❌ الملف غير صالح أو تالف.\n"
                "لم يتم اعتماد النسخة."
            )


# =========================================================
# 📝 INLINE MODE
# =========================================================

async def inline_query(
    update,
    context
):

    query = update.inline_query

    text = (
        query.query
        or ""
    ).strip()

    if not text:

        await query.answer(
            [],
            cache_time=0,
            is_personal=True
        )

        return

    if len(text) > MAX_TEXT_LENGTH:

        await query.answer(
            [],
            cache_time=0,
            is_personal=True
        )

        return

    if not await rate_allowed(
        query.from_user.id
    ):

        await query.answer(
            [],
            cache_time=0,
            is_personal=True
        )

        return

    whisper_id = make_id()

    INLINE_PENDING[
        whisper_id
    ] = {
        "sender_id":
            query.from_user.id,

        "sender_name":
            query.from_user.first_name
            or "مستخدم",

        "text":
            text,

        "created_at":
            now()
    }

    result = InlineQueryResultArticle(

        id=whisper_id,

        title="🤫 إنشاء همسة",

        description=(
            "همسة نصية سرية"
        ),

        input_message_content=(
            InputTextMessageContent(
                message_text=(
                    "🤫 <b>همسة سرية</b>\n\n"
                    "اضغط الزر لفتحها."
                ),
                parse_mode=ParseMode.HTML
            )
        ),

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👁️ اضغط لقراءة الهمسة",
                    callback_data=(
                        f"openinline:{whisper_id}"
                    )
                )
            ]
        ])
    )

    await query.answer(
        [result],
        cache_time=0,
        is_personal=True
    )


# =========================================================
# INLINE OPEN
# =========================================================

async def open_inline(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    whisper_id = query.data.split(
        ":",
        1
    )[1]

    pending = INLINE_PENDING.get(
        whisper_id
    )

    if not pending:

        await query.answer(
            "❌ انتهت صلاحية الهمسة.",
            show_alert=True
        )

        return

    async with DATA_LOCK:

        data = await load_database()

        if len(
            data[
                "whispers"
            ]
        ) >= MAX_WHISPERS:

            await query.answer(
                "❌ قاعدة البيانات ممتلئة.",
                show_alert=True
            )

            return

        whisper = {

            "id":
                whisper_id,

            "sender_id":
                pending[
                    "sender_id"
                ],

            "sender_name":
                pending[
                    "sender_name"
                ],

            "content_type":
                "text",

            "text":
                pending[
                    "text"
                ],

            "file_id":
                None,

            "caption":
                "",

            "audience":
                "first",

            "recipient_ids":
                [],

            "recipient_usernames":
                [],

            "anonymous":
                False,

            "password":
                None,

            "question":
                None,

            "answer":
                None,

            "one_time":
                False,

            "self_destruct":
                0,

            "available_at":
                0,

            "expires_at":
                now() + DEFAULT_TTL,

            "button_text":
                "👁️ اضغط لقراءة الهمسة",

            "opened_by":
                [],

            "created_at":
                now(),

            "deleted":
                False,

            "delivered_messages":
                []
        }

        data[
            "whispers"
        ][
            whisper_id
        ] = whisper

        await save_database(
            data
        )

        INLINE_PENDING.pop(
            whisper_id,
            None
        )

    # نرسل المحتوى في الخاص
    try:

        await deliver_whisper(
            context,
            whisper,
            query.from_user,
            data
        )

        async with DATA_LOCK:

            data = await load_database()

            if whisper_id in data[
                "whispers"
            ]:

                data[
                    "whispers"
                ][
                    whisper_id
                ][
                    "opened_by"
                ].append(
                    query.from_user.id
                )

                await save_database(
                    data
                )

        await query.answer(
            "🤫 أرسلت لك الهمسة في الخاص.",
            show_alert=True
        )

    except Forbidden:

        await query.answer(
            "❗ ابدأ محادثة خاصة مع البوت أولاً.",
            show_alert=True
        )

    except Exception:

        logger.exception(
            "Inline open failed"
        )

        await query.answer(
            "❌ تعذر إرسال الهمسة.",
            show_alert=True
        )


# =========================================================
# 🏠 MENU CALLBACK
# =========================================================

async def menu_callback(
    update,
    context
):

    query = update.callback_query

    data = query.data

    if data == "menu:home":

        await query.answer()

        keyboard = [
            [
                InlineKeyboardButton(
                    "🤫 إنشاء همسة",
                    callback_data="menu:create"
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 همساتي",
                    callback_data="menu:my"
                ),
                InlineKeyboardButton(
                    "📊 إحصائياتي",
                    callback_data="menu:stats"
                )
            ],
            [
                InlineKeyboardButton(
                    "ℹ️ المساعدة",
                    callback_data="menu:help"
                )
            ]
        ]

        if is_admin(
            query.from_user.id
        ):

            keyboard.append([
                InlineKeyboardButton(
                    "⚙️ الإدارة",
                    callback_data="menu:admin"
                )
            ])

        await query.edit_message_text(

            "🤫 <b>القائمة الرئيسية</b>",

            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),

            parse_mode=ParseMode.HTML
        )

        return

    if data == "menu:create":

        await create_start(
            update,
            context
        )

        return

    if data == "menu:my":

        await my_whispers(
            update,
            context
        )

        return

    if data == "menu:stats":

        await stats(
            update,
            context
        )

        return

    if data == "menu:help":

        await show_help(
            update,
            context
        )

        return

    if data == "menu:admin":

        await admin_menu(
            update,
            context
        )

        return


# =========================================================
# ❌ UNKNOWN / ERROR
# =========================================================

async def error_handler(
    update,
    context
):

    logger.error(
        "Unhandled error: %s",
        context.error,
        exc_info=True
    )


# =========================================================
# 🚀 MAIN
# =========================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود."
        )

    if ADMIN_ID == 0:
        raise RuntimeError(
            "ADMIN_ID غير موجود."
        )

    if not WEBHOOK_URL:
        raise RuntimeError(
            "WEBHOOK_URL غير موجود."
        )

    # -----------------------------------------------------
    # Application
    # -----------------------------------------------------

    application = (
        Application
        .builder()
        .token(
            BOT_TOKEN
        )
        .build()
    )

    # -----------------------------------------------------
    # Conversation
    # -----------------------------------------------------

    conversation = ConversationHandler(

        entry_points=[

            CallbackQueryHandler(
                create_start,
                pattern=r"^menu:create$"
            )

        ],

        states={

            CREATE_TYPE: [

                CallbackQueryHandler(
                    choose_content_type,
                    pattern=r"^ctype:"
                )

            ],

            CREATE_TEXT: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_text
                )

            ],

            CREATE_MEDIA: [

                MessageHandler(
                    filters.PHOTO
                    | filters.VOICE,
                    receive_media
                )

            ],

            CREATE_AUDIENCE: [

                CallbackQueryHandler(
                    choose_audience,
                    pattern=r"^aud:"
                )

            ],

            CREATE_RECIPIENTS: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_recipients
                )

            ],

            CREATE_ANONYMOUS: [

                CallbackQueryHandler(
                    choose_anonymous,
                    pattern=r"^anon:"
                )

            ],

            CREATE_PROTECTION: [

                CallbackQueryHandler(
                    choose_protection,
                    pattern=r"^protect:"
                )

            ],

            CREATE_PASSWORD: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_password
                )

            ],

            CREATE_QUESTION: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_question
                )

            ],

            CREATE_ANSWER: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_answer
                )

            ],

            CREATE_ONETIME: [

                CallbackQueryHandler(
                    choose_onetime,
                    pattern=r"^once:"
                )

            ],

            CREATE_SELF_DESTRUCT: [

                CallbackQueryHandler(
                    choose_self_destruct,
                    pattern=r"^destroy:"
                )

            ],

            CREATE_TIME: [

                CallbackQueryHandler(
                    choose_time,
                    pattern=r"^time:"
                ),

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_custom_time
                )

            ],

            CREATE_BUTTON: [

                CallbackQueryHandler(
                    choose_default_button,
                    pattern=r"^button:default$"
                ),

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_button
                )

            ],

            CREATE_CONFIRM: [

                CallbackQueryHandler(
                    save_created_whisper,
                    pattern=r"^create:save$"
                ),

                CallbackQueryHandler(
                    cancel_create,
                    pattern=r"^create:cancel$"
                )

            ]

        },

        fallbacks=[

            CallbackQueryHandler(
                cancel_create,
                pattern=r"^create:cancel$"
            ),

            CommandHandler(
                "cancel",
                cancel_create
            )

        ],

        allow_reentry=True
    )

    application.add_handler(
        conversation
    )

    # -----------------------------------------------------
    # Commands
    # -----------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "unlock",
            unlock_command
        )
    )

    application.add_handler(
        CommandHandler(
            "answer",
            answer_command
        )
    )

    # -----------------------------------------------------
    # Inline
    # -----------------------------------------------------

    application.add_handler(
        InlineQueryHandler(
            inline_query
        )
    )

    # -----------------------------------------------------
    # Callback
    # -----------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            menu_callback,
            pattern=r"^menu:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            open_whisper,
            pattern=r"^open:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            open_inline,
            pattern=r"^openinline:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            whisper_details,
            pattern=r"^details:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            delete_whisper,
            pattern=r"^delete:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_stats,
            pattern=r"^admin:stats$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_cleanup,
            pattern=r"^admin:cleanup$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_export,
            pattern=r"^admin:export$"
        )
    )

    # -----------------------------------------------------
    # Import
    # -----------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            import_document
        )
    )

    # -----------------------------------------------------
    # Errors
    # -----------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    # -----------------------------------------------------
    # Cleanup job
    # -----------------------------------------------------

    application.job_queue.run_repeating(
        cleanup_job,
        interval=60,
        first=30
    )

    # -----------------------------------------------------
    # Webhook
    # -----------------------------------------------------

    clean_url = (
        WEBHOOK_URL
        .replace(
            "https://",
            ""
        )
        .replace(
            "http://",
            ""
        )
        .rstrip("/")
    )

    webhook_url = (
        f"https://{clean_url}/{BOT_TOKEN}"
    )

    kwargs = {

        "listen":
            "0.0.0.0",

        "port":
            PORT,

        "url_path":
            BOT_TOKEN,

        "webhook_url":
            webhook_url,

        "allowed_updates": [
            "message",
            "callback_query",
            "inline_query"
        ],

        "drop_pending_updates":
            False
    }

    if WEBHOOK_SECRET:

        kwargs[
            "secret_token"
        ] = WEBHOOK_SECRET

    logger.info(
        "Starting Whisper Bot..."
    )

    application.run_webhook(
        **kwargs
    )


# =========================================================
# ▶️ RUN
# =========================================================

if __name__ == "__main__":

    main()
