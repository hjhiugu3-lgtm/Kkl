import logging
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

# الإعدادات الأساسية
API_TOKEN = '8602756904:AAEI_n7qamsQGOx4zwkh89hj4d4uIw4tSkE'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# قاعدة بيانات مؤقتة
user_db = {}

def get_user_data(user_id):
    if user_id not in user_db:
        user_db[user_id] = {
            "notes": [], "tasks": [], "files": [], 
            "links": [], "goals": [], "points": 0
        }
    return user_db[user_id]

class LifeDeskStates(StatesGroup):
    waiting_for_note = State()
    waiting_for_task = State()
    waiting_for_link = State()
    waiting_for_goal = State()

def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📝 الملاحظات", callback_data="menu_notes"),
        types.InlineKeyboardButton(text="✅ المهام", callback_data="menu_tasks")
    )
    builder.row(
        types.InlineKeyboardButton(text="📂 الملفات", callback_data="menu_files"),
        types.InlineKeyboardButton(text="🔗 الروابط", callback_data="menu_links")
    )
    builder.row(
        types.InlineKeyboardButton(text="🎯 الأهداف", callback_data="menu_goals"),
        types.InlineKeyboardButton(text="📊 لوحة التحكم", callback_data="menu_stats")
    )
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    get_user_data(user_id)
    await message.answer(
        f"أهلاً بك يا {message.from_user.full_name} في LifeDesk 🔐\n"
        "اختر القسم الذي تريد إدارته:",
        reply_markup=main_menu_keyboard()
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard())
    await callback.answer()

# [هنا تضع باقي دوال الـ handlers التي أرسلتها لك سابقاً للملاحظات والمهام...]
# (لقد اختصرت المساحة هنا، تأكد من إضافة الدوال السابقة الخاصة بالـ menus والـ states)

# --- التشغيل الأساسي ---
async def main():
    # هذا السطر هو الحل الجذري لمشكلة الـ Conflict التي ظهرت لك
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("LifeDesk Bot is running...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
 
