import logging
import asyncio
import json
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================================
# ⚙️ الإعدادات الأساسية
# ==========================================
API_TOKEN = '8602756904:AAEI_n7qamsQGOx4zwkh89hj4d4uIw4tSkE'
DB_FILE = 'lifedesk_database.json'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# 💾 نظام قاعدة البيانات (حفظ دائم)
# ==========================================
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

user_db = load_db()

def save_db():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_db, f, ensure_ascii=False, indent=4)

def get_user_data(user_id):
    user_id = str(user_id) # JSON requires string keys
    if user_id not in user_db:
        user_db[user_id] = {
            "notes": [], "tasks": [], "files": [], 
            "links": [], "goals": [], "points": 0
        }
        save_db()
    return user_db[user_id]

def update_points(user_id, points):
    user_id = str(user_id)
    user_db[user_id]["points"] += points
    save_db()

# ==========================================
# 🚦 حالات الإدخال (FSM)
# ==========================================
class LifeDeskStates(StatesGroup):
    waiting_for_note = State()
    waiting_for_task = State()
    waiting_for_link = State()
    waiting_for_goal = State()

# ==========================================
# 🎛️ لوحات المفاتيح (Keyboards)
# ==========================================
def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📝 دفتر الملاحظات", callback_data="menu_notes"),
        types.InlineKeyboardButton(text="✅ إدارة المهام", callback_data="menu_tasks")
    )
    builder.row(
        types.InlineKeyboardButton(text="📂 خزنة الملفات", callback_data="menu_files"),
        types.InlineKeyboardButton(text="🔗 مدير الروابط", callback_data="menu_links")
    )
    builder.row(
        types.InlineKeyboardButton(text="🎯 متابعة الأهداف", callback_data="menu_goals"),
        types.InlineKeyboardButton(text="📊 لوحة التحكم", callback_data="menu_stats")
    )
    return builder.as_markup()

def back_button(target_menu="back_to_main"):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=target_menu))
    return builder.as_markup()

# ==========================================
# 🚀 أوامر البداية والتنقل الأساسي
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    get_user_data(user_id)
    await message.answer(
        f"✨ **أهلاً بك يا {message.from_user.full_name} في (LifeDesk)** 🚀\n\n"
        "مكتبك الرقمي الذي يحفظ بياناتك بشكل **دائم وآمن**. تم تجهيز كل أدواتك بنجاح.\n\n"
        "👇 **اختر القسم الذي تريد فتحه:**",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🏠 **القائمة الرئيسية لمكتبك الشخصي:**\n\n"
        "اختر أحد الأقسام التالية لإدارة بياناتك:", 
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

# ==========================================
# 📝 1. قسم دفتر الملاحظات
# ==========================================
@dp.callback_query(F.data == "menu_notes")
async def notes_menu(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة ملاحظة", callback_data="add_note_start"))
    if data["notes"]:
        builder.row(types.InlineKeyboardButton(text="📜 عرض الملاحظات", callback_data="list_notes"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        f"📝 **دفتر الملاحظات**\n\nإجمالي الملاحظات: **{len(data['notes'])}**\nماذا تريد أن تفعل؟", 
        reply_markup=builder.as_markup(), parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "list_notes")
async def list_notes(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    text = "📝 **ملاحظاتك المحفوظة:**\n\n"
    for idx, note in enumerate(data["notes"], 1):
        text += f"🔹 {idx}. {note}\n\n"
    await callback.message.edit_text(text, reply_markup=back_button("menu_notes"), parse_mode="Markdown")

@dp.callback_query(F.data == "add_note_start")
async def add_note_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ **أرسل الآن نص الملاحظة الجديدة:**", parse_mode="Markdown")
    await state.set_state(LifeDeskStates.waiting_for_note)

@dp.message(LifeDeskStates.waiting_for_note)
async def save_note(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    user_db[user_id]["notes"].append(message.text)
    save_db()
    update_points(user_id, 5)
    await state.clear()
    await message.answer("🎉 **تم حفظ الملاحظة بنجاح!** (+5 نقاط)", reply_markup=back_button("menu_notes"), parse_mode="Markdown")

# ==========================================
# ✅ 2. قسم إدارة المهام
# ==========================================
@dp.callback_query(F.data == "menu_tasks")
async def tasks_menu(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة مهمة", callback_data="add_task_start"))
    if data["tasks"]:
        builder.row(types.InlineKeyboardButton(text="📋 عرض المهام الحالية", callback_data="list_tasks"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        f"✅ **إدارة المهام**\n\nالمهام قيد الانتظار: **{len(data['tasks'])}**\nاختر الإجراء المطلوب:", 
        reply_markup=builder.as_markup(), parse_mode="Markdown"
    )

@dp.callback_query(F.data == "list_tasks")
async def list_tasks(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    text = "✅ **مهامك الحالية (اضغط على المهمة لإنجازها):**\n\n"
    
    for idx, task in enumerate(data["tasks"]):
        text += f"📌 {task}\n"
        builder.row(types.InlineKeyboardButton(text=f"إنجاز: {task[:15]}...", callback_data=f"done_task_{idx}"))
        
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_tasks"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("done_task_"))
async def complete_task(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    task_idx = int(callback.data.split("_")[2])
    
    if task_idx < len(user_db[user_id]["tasks"]):
        completed_task = user_db[user_id]["tasks"].pop(task_idx)
        save_db()
        update_points(user_id, 10)
        await callback.answer(f"أنجزت: {completed_task} (+10 نقاط) 🏆", show_alert=True)
        # Refresh the list
        await list_tasks(callback)
    else:
        await callback.answer("حدث خطأ، المهمة غير موجودة.", show_alert=True)

@dp.callback_query(F.data == "add_task_start")
async def add_task_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 **أرسل عنوان المهمة الجديدة:**", parse_mode="Markdown")
    await state.set_state(LifeDeskStates.waiting_for_task)

@dp.message(LifeDeskStates.waiting_for_task)
async def save_task(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    user_db[user_id]["tasks"].append(message.text)
    save_db()
    await state.clear()
    await message.answer("✅ **تمت إضافة المهمة بنجاح!**", reply_markup=back_button("menu_tasks"), parse_mode="Markdown")

# ==========================================
# 📂 3. قسم خزنة الملفات
# ==========================================
@dp.callback_query(F.data == "menu_files")
async def files_menu(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    if data["files"]:
        builder.row(types.InlineKeyboardButton(text="📁 استعراض الملفات", callback_data="list_files"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        f"📂 **خزنة الملفات**\n\nالملفات المحفوظة: **{len(data['files'])}**\n\n💡 *لإضافة ملف جديد، قم بإرسال أي مستند أو صورة مباشرة إلى هذه المحادثة.*", 
        reply_markup=builder.as_markup(), parse_mode="Markdown"
    )

@dp.callback_query(F.data == "list_files")
async def list_files(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    
    text = "📂 **ملفاتك المحفوظة (اضغط للاسترجاع):**\n\n"
    for idx, f_item in enumerate(data["files"]):
        file_name = f_item.get('name', f'ملف {idx+1}')
        builder.row(types.InlineKeyboardButton(text=f"📥 {file_name}", callback_data=f"get_file_{idx}"))
        
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_files"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("get_file_"))
async def retrieve_file(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    file_idx = int(callback.data.split("_")[2])
    
    if file_idx < len(user_db[user_id]["files"]):
        file_info = user_db[user_id]["files"][file_idx]
        file_id = file_info["file_id"]
        file_type = file_info["type"]
        
        await callback.answer("جاري إرسال الملف... ⏳")
        if file_type == "document":
            await bot.send_document(chat_id=callback.from_user.id, document=file_id)
        elif file_type == "photo":
            await bot.send_photo(chat_id=callback.from_user.id, photo=file_id)
    else:
        await callback.answer("الملف غير موجود.", show_alert=True)

@dp.message(F.document | F.photo)
async def handle_files(message: types.Message):
    user_id = str(message.from_user.id)
    get_user_data(user_id) # Ensure user exists
    
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        f_type = "document"
    else:
        file_id = message.photo[-1].file_id
        file_name = "صورة محفوظة 🖼️"
        f_type = "photo"

    user_db[user_id]["files"].append({"file_id": file_id, "name": file_name, "type": f_type})
    save_db()
    update_points(user_id, 15)
    
    await message.answer(f"🔒 **تم حفظ الملف ({file_name}) بنجاح!** (+15 نقطة)", reply_markup=back_button("menu_files"), parse_mode="Markdown")

# ==========================================
# 🔗 4. قسم مدير الروابط
# ==========================================
@dp.callback_query(F.data == "menu_links")
async def links_menu(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ حفظ رابط", callback_data="add_link_start"))
    if data["links"]:
        builder.row(types.InlineKeyboardButton(text="🌐 عرض الروابط", callback_data="list_links"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        f"🔗 **مدير الروابط**\n\nالروابط المحفوظة: **{len(data['links'])}**", 
        reply_markup=builder.as_markup(), parse_mode="Markdown"
    )

@dp.callback_query(F.data == "list_links")
async def list_links(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    text = "🔗 **روابطك المحفوظة:**\n\n"
    for idx, link in enumerate(data["links"], 1):
        text += f"🌐 {idx}: {link}\n\n"
    await callback.message.edit_text(text, reply_markup=back_button("menu_links"), parse_mode="Markdown")

@dp.callback_query(F.data == "add_link_start")
async def add_link_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔗 **أرسل الرابط (URL) الآن:**", parse_mode="Markdown")
    await state.set_state(LifeDeskStates.waiting_for_link)

@dp.message(LifeDeskStates.waiting_for_link)
async def save_link(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    user_db[user_id]["links"].append(message.text)
    save_db()
    update_points(user_id, 2)
    await state.clear()
    await message.answer("🌐 **تم حفظ الرابط بنجاح!**", reply_markup=back_button("menu_links"), parse_mode="Markdown")

# ==========================================
# 🎯 5. قسم الأهداف
# ==========================================
@dp.callback_query(F.data == "menu_goals")
async def goals_menu(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة هدف", callback_data="add_goal_start"))
    if data["goals"]:
        builder.row(types.InlineKeyboardButton(text="🎯 عرض الأهداف", callback_data="list_goals"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        f"🎯 **متابع الأهداف**\n\nالأهداف الحالية: **{len(data['goals'])}**", 
        reply_markup=builder.as_markup(), parse_mode="Markdown"
    )

@dp.callback_query(F.data == "list_goals")
async def list_goals(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    text = "🎯 **أهدافك وطموحاتك:**\n\n"
    for idx, goal in enumerate(data["goals"], 1):
        text += f"🏆 **{idx}.** {goal}\n   📈 حالة الإنجاز مستمرة...\n\n"
    await callback.message.edit_text(text, reply_markup=back_button("menu_goals"), parse_mode="Markdown")

@dp.callback_query(F.data == "add_goal_start")
async def add_goal_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎯 **اكتب عنوان هدفك الجديد:**", parse_mode="Markdown")
    await state.set_state(LifeDeskStates.waiting_for_goal)

@dp.message(LifeDeskStates.waiting_for_goal)
async def save_goal(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    user_db[user_id]["goals"].append(message.text)
    save_db()
    update_points(user_id, 20)
    await state.clear()
    await message.answer("🎯 **تمت إضافة الهدف! لنعمل على تحقيقه 💪**", reply_markup=back_button("menu_goals"), parse_mode="Markdown")

# ==========================================
# 📊 6. لوحة التحكم والإحصائيات
# ==========================================
@dp.callback_query(F.data == "menu_stats")
async def stats_menu(callback: types.CallbackQuery):
    data = get_user_data(callback.from_user.id)
    
    # حساب المستوى
    pts = data['points']
    if pts < 50: level = "مبتدئ 🌱"
    elif pts < 200: level = "منظم جيد 💼"
    elif pts < 500: level = "محترف تنظيم 🎖️"
    else: level = "أسطورة التنظيم 👑"

    text = (
        "📊 **لوحة التحكم والإحصائيات الشاملة**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📝 **الملاحظات:** {len(data['notes'])}\n"
        f"✅ **المهام الحالية:** {len(data['tasks'])}\n"
        f"📂 **الملفات المحفوظة:** {len(data['files'])}\n"
        f"🔗 **الروابط:** {len(data['links'])}\n"
        f"🎯 **الأهداف:** {len(data['goals'])}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **النقاط الإجمالية:** {pts} نقطة\n"
        f"🎖️ **مستواك الحالي:** {level}"
    )
    await callback.message.edit_text(text, reply_markup=back_button(), parse_mode="Markdown")

# ==========================================
# ⚙️ التشغيل الأساسي
# ==========================================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 LifeDesk Bot is running successfully with Persistent Storage...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
 
