import logging
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

API_TOKEN = '8602756904:AAEI_n7qamsQGOx4zwkh89hj4d4uIw4tSkE'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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
        f"🌟 **أهلاً بك يا {message.from_user.full_name} في نظام LifeDesk الذكي** 🔐\n\n"
        "مكتبك الشخصي المتكامل جاهز الآن لإدارة مهامك وملاحظاتك بكل سهولة.\n"
        "👇 **اختر القسم المطلوب من الأزرار أدناه:**",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🏠 **القائمة الرئيسية لمكتبك الشخصي:**\n\n"
        "اختر أحد الأقسام التالية للإدارة:", 
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "menu_notes")
async def notes_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة ملاحظة جديدة", callback_data="add_note_start"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["notes"])
    text = f"📝 **قسم دفتر الملاحظات**\n\nلديك {count} ملاحظة محفوظة."
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_note_start")
async def add_note_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✍️ أرسل الآن نص الملاحظة الجديدة:")
    await state.set_state(LifeDeskStates.waiting_for_note)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_note)
async def save_note(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["notes"].append(message.text)
    data["points"] += 5
    await state.clear()
    await message.answer("✅ تم حفظ الملاحظة بنجاح!", reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "menu_tasks")
async def tasks_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة مهمة جديدة", callback_data="add_task_start"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["tasks"])
    text = f"✅ **قسم إدارة المهام**\n\nالمهام المسجلة: {count}"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_task_start")
async def add_task_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 أدخل عنوان المهمة الجديدة:")
    await state.set_state(LifeDeskStates.waiting_for_task)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_task)
async def save_task(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["tasks"].append(message.text)
    data["points"] += 10
    await state.clear()
    await message.answer("✅ تمت إضافة المهمة بنجاح!", reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "menu_files")
async def files_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["files"])
    text = f"📂 **خزنة الملفات الشخصية**\n\nالملفات المحفوظة: {count}\n💡 أرسل أي ملف أو صورة هنا ليتم حفظه تلقائياً."
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.message(F.document | F.photo)
async def handle_files(message: types.Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["files"].append("ملف مرسل")
    data["points"] += 15
    await message.answer("📂 تم حفظ الملف في خزنتك بنجاح!")

@dp.callback_query(F.data == "menu_links")
async def links_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة رابط جديد", callback_data="add_link_start"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["links"])
    text = f"🔗 **مدير الروابط**\n\nالروابط المحفوظة: {count}"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_link_start")
async def add_link_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🔗 أرسل رابط الموقع (URL):")
    await state.set_state(LifeDeskStates.waiting_for_link)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_link)
async def save_link(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["links"].append(message.text)
    await state.clear()
    await message.answer("🔗 تم حفظ الرابط بنجاح!", reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "menu_goals")
async def goals_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة هدف جديد", callback_data="add_goal_start"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["goals"])
    text = f"🎯 **متابع الأهداف**\n\nالأهداف الحالية: {count}"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_goal_start")
async def add_goal_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🎯 اكتب عنوان الهدف الجديد:")
    await state.set_state(LifeDeskStates.waiting_for_goal)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_goal)
async def save_goal(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["goals"].append(message.text)
    await state.clear()
    await message.answer("🎯 تم إضافة الهدف بنجاح!", reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "menu_stats")
async def stats_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    text = (
        "📊 **لوحة التحكم والإحصائيات الشخصية**\n\n"
        f"📝 الملاحظات: {len(data['notes'])}\n"
        f"✅ المهام: {len(data['tasks'])}\n"
        f"📂 الملفات: {len(data['files'])}\n"
        f"🔗 الروابط: {len(data['links'])}\n"
        f"🎯 الأهداف: {len(data['goals'])}\n\n"
        f"🏆 النقاط الإجمالية: {data['points']} نقطة\n"
        "🎖️ المستوى: منظم مبتدئ"
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("LifeDesk Bot is running...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
