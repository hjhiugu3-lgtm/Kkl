import logging
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# الإعدادات الأساسية
API_TOKEN = '8602756904:AAEI_n7qamsQGOx4zwkh89hj4d4uIw4tSkE'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()

# قاعدة بيانات مؤقتة لتخزين بيانات المستخدمين داخل الذاكرة
# Structure: {user_id: {"notes": [], "tasks": [], "files": [], "links": [], "goals": [], "points": 0}}
user_db = {}

def get_user_data(user_id):
    if user_id not in user_db:
        user_db[user_id] = {
            "notes": [],
            "tasks": [],
            "files": [],
            "links": [],
            "goals": [],
            "points": 0
        }
    return user_db[user_id]

# حالات المحادثة (FSM) للإدخال
class LifeDeskStates(StatesGroup):
    waiting_for_note = State()
    waiting_for_task = State()
    waiting_for_link = State()
    waiting_for_goal = State()

# --- القائمة الرئيسية ---
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

# --- أمر البداية ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    get_user_data(user_id) # تهيئة حساب المستخدم
    
    welcome_text = (
        f"أهلاً بك يا {user_name} في LifeDesk 🔐\n"
        "أنشأنا لك مكتبك الشخصي الخاص داخل تيليجرام.\n\n"
        "اختر القسم الذي تريد إدارته من القائمة أدناه:"
    )
    await message.answer(welcome_text, reply_markup=main_menu_keyboard())

# العودة للقائمة الرئيسية عبر الأزرار
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "القائمة الرئيسية لمكتبك الشخصي 🗂️:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

# --- 1) قسم الملاحظات ---
@dp.callback_query(F.data == "menu_notes")
async def notes_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة ملاحظة", callback_data="add_note_start"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    notes_count = len(data["notes"])
    notes_text = f"📝 **دفتر الملاحظات**\nلديك {notes_count} ملاحظة محفوظة.\n\n"
    if notes_count > 0:
        for i, n in enumerate(data["notes"][-5:], 1): # عرض آخر 5 ملاحظات
            notes_text += f"{i}. {n}\n"
            
    await callback.message.edit_text(notes_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_note_start")
async def add_note_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("أرسل الآن نص الملاحظة الجديدة:")
    await state.set_state(LifeDeskStates.waiting_for_note)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_note)
async def save_note(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["notes"].append(message.text)
    data["points"] += 5
    
    await state.clear()
    await message.answer("✅ تم حفظ الملاحظة بنجاح في دفتر ملاحظاتك!", reply_markup=main_menu_keyboard())

# --- 2) قسم المهام ---
@dp.callback_query(F.data == "menu_tasks")
async def tasks_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ مهمة جديدة", callback_data="add_task_start"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    tasks_count = len(data["tasks"])
    tasks_text = f"✅ **إدارة المهام**\nالمهام المسجلة: {tasks_count}\n\n"
    if tasks_count > 0:
        for i, t in enumerate(data["tasks"], 1):
            tasks_text += f"{i}. {t}\n"
            
    await callback.message.edit_text(tasks_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_task_start")
async def add_task_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("أدخل عنوان المهمة الجديدة:")
    await state.set_state(LifeDeskStates.waiting_for_task)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_task)
async def save_task(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["tasks"].append(message.text)
    data["points"] += 10 # نقاط إنجاز مهام
    
    await state.clear()
    await message.answer("✅ تمت إضافة المهمة بنجاح إلى جدولك!", reply_markup=main_menu_keyboard())

# --- 3) قسم الملفات (استقبال الملفات والصور) ---
@dp.callback_query(F.data == "menu_files")
async def files_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    files_count = len(data["files"])
    await callback.message.edit_text(
        f"📂 **خزنة الملفات**\nلديك {files_count} ملف محفوظ.\n\n"
        "💡 لاستفظار ملف جديد، قم بإرسال أي ملف أو صورة مباشرة هنا وسيقوم البوت بحفظه في خزنتك الخاصة.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(F.document | F.photo)
async def handle_files(message: types.Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["files"].append("ملف مرسل")
    data["points"] += 15
    await message.answer("📂 تم حفظ الملف في خزنتك الخاصة بنجاح!")

# --- 4) قسم الروابط ---
@dp.callback_query(F.data == "menu_links")
async def links_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة رابط", callback_data="add_link_start"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    links_count = len(data["links"])
    links_text = f"🔗 **مدير الروابط**\nالروابط المحفوظة: {links_count}\n\n"
    if links_count > 0:
        for i, l in enumerate(data["links"], 1):
            links_text += f"{i}. {l}\n"
            
    await callback.message.edit_text(links_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_link_start")
async def add_link_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("أرسل رابط الموقع (URL):")
    await state.set_state(LifeDeskStates.waiting_for_link)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_link)
async def save_link(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["links"].append(message.text)
    
    await state.clear()
    await message.answer("🔗 تم حفظ الرابط بنجاح!", reply_markup=main_menu_keyboard())

# --- 5) قسم الأهداف ---
@dp.callback_query(F.data == "menu_goals")
async def goals_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة هدف", callback_data="add_goal_start"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    goals_count = len(data["goals"])
    goals_text = f"🎯 **متابع الأهداف**\nالأهداف الحالية: {goals_count}\n\n"
    if goals_count > 0:
        for i, g in enumerate(data["goals"], 1):
            goals_text += f"{i}. {g} - التقدم: 🟩🟩⬜⬜⬜ (40%)\n"
            
    await callback.message.edit_text(goals_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_goal_start")
async def add_goal_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("اكتب عنوان الهدف الجديد:")
    await state.set_state(LifeDeskStates.waiting_for_goal)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_goal)
async def save_goal(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["goals"].append(message.text)
    
    await state.clear()
    await message.answer("🎯 تم إضافة الهدف بنجاح!", reply_markup=main_menu_keyboard())

# --- 6) لوحة التحكم والإحصائيات ---
@dp.callback_query(F.data == "menu_stats")
async def stats_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    stats_text = (
        "📊 **لوحة التحكم الشخصية**\n\n"
        f"📝 الملاحظات: {len(data['notes'])}\n"
        f"✅ المهام: {len(data['tasks'])}\n"
        f"📂 الملفات: {len(data['files'])}\n"
        f"🔗 الروابط: {len(data['links'])}\n"
        f"🎯 الأهداف: {len(data['goals'])}\n\n"
        f"🏆 النقاط الإجمالية: {data['points']} نقطة\n"
        "🎖️ المستوى الحالي: منظم مبتدئ"
    )
    await callback.message.edit_text(stats_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

# --- التشغيل الأساسي للمجدول والبوت ---
async def main():
    print("LifeDesk Bot is running...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
 
