import os
import json
import logging
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, InlineQueryHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# إعداد السجلات (Logs)
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

DATA_FILE = "database.json"

# جلب متغيرات البيئة
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # آيدي حسابك في التليجرام
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # رابط Railway

# --- وظائف التعامل مع ملف البيانات ---
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"خطأ في قراءة الملف: {e}")
    return {"whispers": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- أوامر المطور (التصدير والاسترداد) ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = "أهلاً بك في بوت الهمسات السري! 🤫\n\nيمكنك استخدام البوت مباشرة في أي محادثة عبر كتابة معرف البوت ثم رسالتك."
    if user_id == ADMIN_ID:
        msg += "\n\n⚙️ **لوحة التحكم للمطور:**\n• `/export` : لجلب نسخة من ملف البيانات.\n• أرسل ملف `database.json` للبوت لاسترداد البيانات."
    await update.message.reply_text(msg, parse_mode="Markdown")

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال ملف البيانات للمطور"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if os.path.exists(DATA_FILE):
        await update.message.reply_document(
            document=open(DATA_FILE, "rb"),
            caption="📊 هذا هو ملف البيانات الحالي للهمسات."
        )
    else:
        await update.message.reply_text("❌ لا يوجد ملف بيانات حالياً.")

async def import_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استرداد الملف المرفوع من المطور"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    doc = update.message.document
    if doc.file_name.endswith(".json"):
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(DATA_FILE)
        await update.message.reply_text("✅ تم استرداد وتحديث ملف البيانات بنجاح!")
    else:
        await update.message.reply_text("⚠️ يرجى إرسال ملف بصيغة `.json` فقط.")

# --- نظام الـ Inline Query (إنشاء الهمسة) ---
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query:
        return

    results = []
    whisper_id = str(update.inline_query.id)
    sender = update.inline_query.from_user

    data = load_data()

    # خيار 1: همسة لأول شخص يفتحها
    data["whispers"][f"{whisper_id}_first"] = {
        "text": query,
        "sender_id": sender.id,
        "sender_name": sender.first_name,
        "type": "first",
        "opened_by": []
    }

    # خيار 2: همسة للجميع
    data["whispers"][f"{whisper_id}_all"] = {
        "text": query,
        "sender_id": sender.id,
        "sender_name": sender.first_name,
        "type": "all",
        "opened_by": []
    }

    save_data(data)

    results.append(
        InlineQueryResultArticle(
            id=f"{whisper_id}_first",
            title="👁️ همسة لأول شخص يفتحها فقط",
            description=f"الرسالة: {query}",
            input_message_content=InputTextMessageContent(
                f"🔒 **همسة سرية أرسلها ({sender.first_name}) لأول شخص يضغط عليها!**",
                parse_mode="Markdown"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👁️ إضغط لقراءة الهمسة", callback_data=f"w:{whisper_id}_first")]
            ])
        )
    )

    results.append(
        InlineQueryResultArticle(
            id=f"{whisper_id}_all",
            title="👥 همسة سرية للجميع",
            description=f"الرسالة: {query}",
            input_message_content=InputTextMessageContent(
                f"🔒 **همسة سرية من ({sender.first_name}) يمكن للجميع قراءتها.**",
                parse_mode="Markdown"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👁️ إضغط لقراءة الهمسة", callback_data=f"w:{whisper_id}_all")]
            ])
        )
    )

    await update.inline_query.answer(results, cache_time=1)

# --- تفاعل الضغط على زر الهمسة ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data_code = query.data

    if not data_code.startswith("w:"):
        return

    w_id = data_code.split("w:")[1]
    data = load_data()

    whisper = data["whispers"].get(w_id)

    if not whisper:
        await query.answer("❌ هذه الهمسة قديمة أو تم حذفها!", show_alert=True)
        return

    # الراسل دائماً يستطيع رؤية همسته
    if user.id == whisper["sender_id"]:
        await query.answer(f"🤫 نص همستك:\n\n{whisper['text']}", show_alert=True)
        return

    # همسة لأول شخص
    if whisper["type"] == "first":
        if len(whisper["opened_by"]) == 0:
            whisper["opened_by"].append(user.id)
            save_data(data)
            await query.answer(f"🤫 الهمسة لك فقط:\n\n{whisper['text']}", show_alert=True)
            
            # إشعار للراسل
            try:
                await context.bot.send_message(
                    chat_id=whisper["sender_id"],
                    text=f"🔔 المستخدم [{user.first_name}](tg://user?id={user.id}) قام بفتح همستك السرية!",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        elif user.id in whisper["opened_by"]:
            await query.answer(f"🤫 الهمسة لك:\n\n{whisper['text']}", show_alert=True)
        else:
            await query.answer("🚫 للأسف، قام شخص آخر بفتح هذه الهمسة قبلك!", show_alert=True)

    # همسة للجميع
    elif whisper["type"] == "all":
        if user.id not in whisper["opened_by"]:
            whisper["opened_by"].append(user.id)
            save_data(data)
        await query.answer(f"🤫 الهمسة:\n\n{whisper['text']}", show_alert=True)

# --- التشغيل الأساسي للبوت ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # الأوامر والإنلاين
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("export", export_data))
    app.add_handler(MessageHandler(filters.Document.ALL, import_data))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # التشغيل عبر Webhook لمنصة Railway
    clean_url = WEBHOOK_URL.replace("http://", "").replace("https://", "").rstrip("/")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"https://{clean_url}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
