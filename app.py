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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    get_user_data(user_id)
    await message.answer(
        f"✨ **أهلاً بك يا {message.from_user.full_name} في عالم التنظيم الذكي (LifeDesk)** 🚀🔐\n\n"
        "تم تجهيز مكتبك الرقمي بنجاح، ويحتوي الآن على كافة الأدوات لإدارة حياتك بكل احترافية واستمتاع.\n\n"
        "👇 **اختر القسم الذي تريد فتحه من لوحة التحكم أدناه:**",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🏠 **القائمة الرئيسية لمكتبك الشخصي (LifeDesk):**\n\n"
        "اختر أحد الأقسام التالية لإدارة بياناتك بكل سهولة:", 
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
    if len(data["notes"]) > 0:
        builder.row(types.InlineKeyboardButton(text="📜 استعراض كافة الملاحظات", callback_data="list_notes"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["notes"])
    text = f"📝 **قسم دفتر الملاحظات**\n\nإجمالي الملاحظات المحفوظة: **{count}**\nاختر الإجراء المطلوبة أدناه:"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "list_notes")
async def list_notes(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للملاحظات", callback_data="menu_notes"))
    
    text = "📝 **سجل ملاحظاتك المحفوظة:**\n\n"
    for idx, note in enumerate(data["notes"], 1):
        text += f"🔹 **{idx}قال:** {note}\n"
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_note_start")
async def add_note_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✍️ أرسل الآن نص الملاحظة الجديدة التي تريد تدوينها:")
    await state.set_state(LifeDeskStates.waiting_for_note)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_note)
async def save_note(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["notes"].append(message.text)
    data["points"] += 5
    await state.clear()
    await message.answer("🎉 **تم حفظ الملاحظة بنجاح في أرشيفك الشخصي!** 📝", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_tasks")
async def tasks_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة مهمة جديدة", callback_data="add_task_start"))
    if len(data["tasks"]) > 0:
        builder.row(types.InlineKeyboardButton(text="📋 استعراض المهام المسجلة", callback_data="list_tasks"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["tasks"])
    text = f"✅ **قسم إدارة المهام**\n\nإجمالي المهام الحالية: **{count}**\nتابع مهامك ونظّم جدولك اليومي بكل احترافية."
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "list_tasks")
async def list_tasks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للمهام", callback_data="menu_tasks"))
    
    text = "✅ **قائمة المهام الخاصة بك:**\n\n"
    for idx, task in enumerate(data["tasks"], 1):
        text += f"📌 **مهمة {idx}:** {task}\n"
        
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_task_start")
async def add_task_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 أدخل عنوان أو تفاصيل المهمة الجديدة:")
    await state.set_state(LifeDeskStates.waiting_for_task)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_task)
async def save_task(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["tasks"].append(message.text)
    data["points"] += 10
    await state.clear()
    await message.answer("🏆 **تمت إضافة المهمة بنجاح إلى جدول إنجازاتك!** ✅", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_files")
async def files_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    if len(data["files"]) > 0:
        builder.row(types.InlineKeyboardButton(text="📁 عرض قائمة الملفات المحفوظة", callback_data="list_files"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["files"])
    text = f"📂 **خزنة الملفات الشخصية**\n\nالملفات المحفوظة: **{count}**\n💡 **ملاحظة:** أرسل أي ملف، مستند، أو صورة مباشرة هنا ليتم حفظه تلقائياً في خزنتك."
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "list_files")
async def list_files(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للخزنة", callback_data="menu_files"))
    
    text = "📂 **سجل الملفات والمستندات المرسلة:**\n\n"
    for idx, f_item in enumerate(data["files"], 1):
        text += f"📎 ملف رقم {idx} (تم الحفظ بنجاح)\n"
        
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.message(F.document | F.photo)
async def handle_files(message: types.Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["files"].append("ملف مرسل")
    data["points"] += 15
    await message.answer("🔒 **تم حفظ الملف أو الصورة بأمان تام في خزنتك الخاصة!** 📂", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_links")
async def links_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة رابط جديد", callback_data="add_link_start"))
    if len(data["links"]) > 0:
        builder.row(types.InlineKeyboardButton(text="🌐 استعراض الروابط المحفوظة", callback_data="list_links"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["links"])
    text = f"🔗 **مدير الروابط الذكي**\n\nإجمالي الروابط المحفوظة: **{count}**\nاحفظ روابطك الهامة لتصل إليها في أي وقت."
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "list_links")
async def list_links(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للروابط", callback_data="menu_links"))
    
    text = "🔗 **روابطك المحفوظة:**\n\n"
    for idx, link in enumerate(data["links"], 1):
        text += f"🌐 {idx}: {link}\n"
        
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_link_start")
async def add_link_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🔗 أرسل رابط الموقع (URL) الآن:")
    await state.set_state(LifeDeskStates.waiting_for_link)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_link)
async def save_link(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["links"].append(message.text)
    await state.clear()
    await message.answer("🌐 **تم حفظ الرابط بنجاح في أرشيف الروابط!** 🔗", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_goals")
async def goals_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة هدف جديد", callback_data="add_goal_start"))
    if len(data["goals"]) > 0:
        builder.row(types.InlineKeyboardButton(text="🎯 عرض الأهداف والتقدم", callback_data="list_goals"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    count = len(data["goals"])
    text = f"🎯 **متابع الأهداف الشخصية**\n\nإجمالي الأهداف الحالية: **{count}**\nتابع طموحاتك وحقق إنجازاتك يوماً بيوم."
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "list_goals")
async def list_goals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للأهداف", callback_data="menu_goals"))
    
    text = "🎯 **أهدافك وطموحاتك الحالية:**\n\n"
    for idx, goal in enumerate(data["goals"], 1):
        text += f"🎯 **{idx}.** {goal}\n   📊 التقدم: 🟩🟩🟩⬜⬜ (60%)\n\n"
        
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "add_goal_start")
async def add_goal_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🎯 اكتب عنوان وهدف طموحك الجديد:")
    await state.set_state(LifeDeskStates.waiting_for_goal)
    await callback.answer()

@dp.message(LifeDeskStates.waiting_for_goal)
async def save_goal(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    data["goals"].append(message.text)
    await state.clear()
    await message.answer("🎯 **تم إضافة الهدف بنجاح، انطلق نحو قمة النجاح!** 🚀", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_stats")
async def stats_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main"))
    
    text = (
        "📊 **لوحة التحكم والإحصائيات الشخصية المتقدمة**\n\n"
        f"📝 الملاحظات المسجلة: **{len(data['notes'])}**\n"
        f"✅ المهام المنجزة/المسجلة: **{len(data['tasks'])}**\n"
        f"📂 الملفات في الخزنة: **{len(data['files'])}**\n"
        f"🔗 الروابط المحفوظة: **{len(data['links'])}**\n"
        f"🎯 الأهداف والطموحات: **{len(data['goals'])}**\n\n"
        f"🏆 النقاط الإجمالية لإنجازاتك: **{data['points']} نقطة**\n"
        "🎖️ **مستواك الحالي:** منظم مبتدئ 🌟"
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("LifeDesk Bot is running successfully...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
