import logging
import asyncio
import os
from datetime import datetime
import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==========================================
# ⚙️ الإعدادات الأساسية
# ==========================================
API_TOKEN = '8602756904:AAEI_n7qamsQGOx4zwkh89hj4d4uIw4tSkE'
DB_FILE = 'lifedesk.db'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()

# ==========================================
# 💾 إعداد قاعدة البيانات (SQLite)
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # جدول المستخدمين
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (user_id INTEGER PRIMARY KEY, name TEXT, points INTEGER DEFAULT 0, join_date TEXT)''')
        # جدول الملاحظات
        await db.execute('''CREATE TABLE IF NOT EXISTS notes 
                            (id INTEGER KEY AUTOINCREMENT, user_id INTEGER, content TEXT, category TEXT, date TEXT)''')
        # جدول المهام
        await db.execute('''CREATE TABLE IF NOT EXISTS tasks 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, priority TEXT, due_date TEXT, status TEXT)''')
        # جدول الملفات
        await db.execute('''CREATE TABLE IF NOT EXISTS files 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, file_id TEXT, file_name TEXT, type TEXT, category TEXT)''')
        # جدول الروابط
        await db.execute('''CREATE TABLE IF NOT EXISTS links 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, url TEXT, title TEXT)''')
        # جدول الأهداف
        await db.execute('''CREATE TABLE IF NOT EXISTS goals 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, progress INTEGER DEFAULT 0)''')
        await db.commit()

async def get_or_create_user(user_id, name):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user:
            await db.execute("INSERT INTO users (user_id, name, points, join_date) VALUES (?, ?, ?, ?)",
                             (user_id, name, 0, datetime.now().strftime("%Y-%m-%d")))
            await db.commit()
            return 0
        return user[0]

async def add_points(user_id, points):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
        await db.commit()

# ==========================================
# 🚦 حالات الإدخال (FSM)
# ==========================================
class NoteState(StatesGroup):
    waiting_for_content = State()
    waiting_for_category = State()

class TaskState(StatesGroup):
    waiting_for_title = State()
    waiting_for_priority = State()
    waiting_for_date = State()

class FileState(StatesGroup):
    waiting_for_file = State()
    waiting_for_name = State()
    waiting_for_category = State()

class LinkState(StatesGroup):
    waiting_for_url = State()
    waiting_for_title = State()

class GoalState(StatesGroup):
    waiting_for_title = State()

# ==========================================
# 🎛️ لوحات المفاتيح والأزرار
# ==========================================
def main_menu():
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
        types.InlineKeyboardButton(text="📊 الإحصائيات", callback_data="menu_stats")
    )
    return builder.as_markup()

def back_btn(target="main"):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"menu_{target}"))
    return b.as_markup()

# ==========================================
# 🚀 القائمة الرئيسية
# ==========================================
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await get_or_create_user(message.from_user.id, message.from_user.full_name)
    
    text = (f"✨ **أهلاً بك {message.from_user.full_name} في LifeDesk V2.0** 🚀\n\n"
            "مكتبك الرقمي المتكامل. تم تفعيل نظام التخزين السحابي الآمن (SQLite).\n"
            "👇 **اختر القسم الذي تريد إدارته:**")
    await message.answer(text, reply_markup=main_menu(), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_main")
async def back_main_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏠 **القائمة الرئيسية لمكتبك الشخصي:**", reply_markup=main_menu(), parse_mode="Markdown")

# ==========================================
# 📝 1. الملاحظات المتطورة
# ==========================================
@dp.callback_query(F.data == "menu_notes")
async def notes_menu(callback: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="➕ إضافة ملاحظة", callback_data="note_add"))
    b.row(types.InlineKeyboardButton(text="📜 عرض الملاحظات", callback_data="note_list"))
    b.row(types.InlineKeyboardButton(text="🔙 الرئيسية", callback_data="menu_main"))
    await callback.message.edit_text("📝 **إدارة الملاحظات:**", reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "note_add")
async def note_add_1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ أرسل نص الملاحظة الآن:")
    await state.set_state(NoteState.waiting_for_content)

@dp.message(NoteState.waiting_for_content)
async def note_add_2(message: types.Message, state: FSMContext):
    await state.update_data(content=message.text)
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="💡 أفكار", callback_data="catnote_Idea"),
          types.InlineKeyboardButton(text="💼 عمل", callback_data="catnote_Work"))
    b.row(types.InlineKeyboardButton(text="📚 دراسة", callback_data="catnote_Study"),
          types.InlineKeyboardButton(text="📌 عام", callback_data="catnote_General"))
    await message.answer("اختر تصنيف الملاحظة:", reply_markup=b.as_markup())
    await state.set_state(NoteState.waiting_for_category)

@dp.callback_query(NoteState.waiting_for_category, F.data.startswith("catnote_"))
async def note_save(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = callback.data.split("_")[1]
    date_now = datetime.now().strftime("%Y-%m-%d")
    
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO notes (user_id, content, category, date) VALUES (?, ?, ?, ?)",
                         (callback.from_user.id, data['content'], category, date_now))
        await db.commit()
    
    await add_points(callback.from_user.id, 5)
    await state.clear()
    await callback.message.edit_text(f"✅ تم حفظ الملاحظة في قسم [{category}] بنجاح!", reply_markup=back_btn("notes"))

@dp.callback_query(F.data == "note_list")
async def note_list(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT rowid, content, category, date FROM notes WHERE user_id = ?", (callback.from_user.id,))
        notes = await cursor.fetchall()
    
    if not notes:
        return await callback.message.edit_text("لا توجد ملاحظات مسجلة.", reply_markup=back_btn("notes"))
    
    b = InlineKeyboardBuilder()
    text = "📝 **ملاحظاتك:**\n\n"
    for idx, (nid, content, cat, date) in enumerate(notes, 1):
        text += f"*{idx}.* [{cat}] {date}\n{content}\n\n"
        b.row(types.InlineKeyboardButton(text=f"❌ حذف رقم {idx}", callback_data=f"del_note_{nid}"))
    
    b.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_notes"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("del_note_"))
async def del_note(callback: types.CallbackQuery):
    nid = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM notes WHERE rowid = ? AND user_id = ?", (nid, callback.from_user.id))
        await db.commit()
    await callback.answer("تم الحذف 🗑️", show_alert=True)
    await note_list(callback)

# ==========================================
# ✅ 2. إدارة المهام (أولوية + تاريخ)
# ==========================================
@dp.callback_query(F.data == "menu_tasks")
async def tasks_menu(callback: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="➕ مهمة جديدة", callback_data="task_add"))
    b.row(types.InlineKeyboardButton(text="📋 المهام النشطة", callback_data="task_list"))
    b.row(types.InlineKeyboardButton(text="🔙 الرئيسية", callback_data="menu_main"))
    await callback.message.edit_text("✅ **إدارة المهام:**", reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "task_add")
async def task_add_1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 اكتب عنوان المهمة:")
    await state.set_state(TaskState.waiting_for_title)

@dp.message(TaskState.waiting_for_title)
async def task_add_2(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🔴 عالية", callback_data="prio_High"),
          types.InlineKeyboardButton(text="🟡 متوسطة", callback_data="prio_Med"),
          types.InlineKeyboardButton(text="🟢 عادية", callback_data="prio_Low"))
    await message.answer("اختر أولوية المهمة:", reply_markup=b.as_markup())
    await state.set_state(TaskState.waiting_for_priority)

@dp.callback_query(TaskState.waiting_for_priority, F.data.startswith("prio_"))
async def task_add_3(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(priority=callback.data.split("_")[1])
    await callback.message.edit_text("📅 أرسل موعد التسليم (مثال: اليوم، غداً، أو تاريخ 2026-08-10):")
    await state.set_state(TaskState.waiting_for_date)

@dp.message(TaskState.waiting_for_date)
async def task_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO tasks (user_id, title, priority, due_date, status) VALUES (?, ?, ?, ?, ?)",
                         (message.from_user.id, data['title'], data['priority'], message.text, 'Pending'))
        await db.commit()
    
    await add_points(message.from_user.id, 10)
    await state.clear()
    await message.answer("✅ تمت إضافة المهمة بنجاح!", reply_markup=back_btn("tasks"))

@dp.callback_query(F.data == "task_list")
async def task_list(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT id, title, priority, due_date FROM tasks WHERE user_id = ? AND status = 'Pending'", (callback.from_user.id,))
        tasks = await cursor.fetchall()
    
    if not tasks:
        return await callback.message.edit_text("لا توجد مهام قيد الانتظار 🎉", reply_markup=back_btn("tasks"))
    
    b = InlineKeyboardBuilder()
    text = "📋 **مهامك الحالية:**\n\n"
    for tid, title, prio, date in tasks:
        p_icon = "🔴" if prio=="High" else "🟡" if prio=="Med" else "🟢"
        text += f"{p_icon} **{title}**\n   📅 الموعد: {date}\n\n"
        b.row(
            types.InlineKeyboardButton(text=f"✅ إنجاز: {title[:10]}", callback_data=f"done_task_{tid}"),
            types.InlineKeyboardButton(text="🗑️", callback_data=f"del_task_{tid}")
        )
    
    b.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_tasks"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("done_task_"))
async def done_task(callback: types.CallbackQuery):
    tid = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE tasks SET status = 'Completed' WHERE id = ? AND user_id = ?", (tid, callback.from_user.id))
        await db.commit()
    await add_points(callback.from_user.id, 15)
    await callback.answer("🏆 تم إنجاز المهمة! (+15 نقطة)", show_alert=True)
    await task_list(callback)

@dp.callback_query(F.data.startswith("del_task_"))
async def del_task(callback: types.CallbackQuery):
    tid = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (tid, callback.from_user.id))
        await db.commit()
    await callback.answer("تم حذف المهمة", show_alert=True)
    await task_list(callback)

# ==========================================
# 📂 3. خزنة الملفات الذكية
# ==========================================
@dp.callback_query(F.data == "menu_files")
async def files_menu(callback: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="📥 استعراض الخزنة", callback_data="file_list"))
    b.row(types.InlineKeyboardButton(text="🔙 الرئيسية", callback_data="menu_main"))
    await callback.message.edit_text("📂 **خزنة الملفات:**\nلإضافة ملف جديد، فقط قم بإرساله لي في المحادثة مباشرة.", reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.message(F.document | F.photo)
async def catch_file(message: types.Message, state: FSMContext):
    file_id = message.document.file_id if message.document else message.photo[-1].file_id
    f_type = "document" if message.document else "photo"
    
    await state.update_data(file_id=file_id, type=f_type)
    await message.answer("📁 تم استلام الملف. اكتب اسماً مميزاً لحفظه به:")
    await state.set_state(FileState.waiting_for_name)

@dp.message(FileState.waiting_for_name)
async def file_save_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO files (user_id, file_id, file_name, type, category) VALUES (?, ?, ?, ?, ?)",
                         (message.from_user.id, data['file_id'], message.text, data['type'], 'عام'))
        await db.commit()
    await add_points(message.from_user.id, 20)
    await state.clear()
    await message.answer(f"🔒 تم تشفير وحفظ الملف ({message.text}) بنجاح!", reply_markup=back_btn("files"))

@dp.callback_query(F.data == "file_list")
async def file_list(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT id, file_name FROM files WHERE user_id = ?", (callback.from_user.id,))
        files = await cursor.fetchall()
    
    if not files:
        return await callback.message.edit_text("الخزنة فارغة.", reply_markup=back_btn("files"))
    
    b = InlineKeyboardBuilder()
    for fid, name in files:
        b.row(
            types.InlineKeyboardButton(text=f"📥 {name}", callback_data=f"get_file_{fid}"),
            types.InlineKeyboardButton(text="🗑️", callback_data=f"del_file_{fid}")
        )
    b.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_files"))
    await callback.message.edit_text("📂 **اختر ملفاً لاسترجاعه:**", reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("get_file_"))
async def retrieve_file(callback: types.CallbackQuery):
    fid = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT file_id, type FROM files WHERE id = ? AND user_id = ?", (fid, callback.from_user.id))
        file_data = await cursor.fetchone()
    
    if file_data:
        file_id, f_type = file_data
        await callback.answer("جاري الإرسال...")
        if f_type == "document": await bot.send_document(callback.from_user.id, file_id)
        else: await bot.send_photo(callback.from_user.id, file_id)

@dp.callback_query(F.data.startswith("del_file_"))
async def delete_file(callback: types.CallbackQuery):
    fid = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM files WHERE id = ? AND user_id = ?", (fid, callback.from_user.id))
        await db.commit()
    await callback.answer("تم حذف الملف 🗑️")
    await file_list(callback)

# ==========================================
# 🔗 4. الروابط والأهداف
# ==========================================
# الروابط
@dp.callback_query(F.data == "menu_links")
async def links_menu(callback: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="➕ حفظ رابط", callback_data="link_add"))
    b.row(types.InlineKeyboardButton(text="🌐 عرض الروابط", callback_data="link_list"))
    b.row(types.InlineKeyboardButton(text="🔙 الرئيسية", callback_data="menu_main"))
    await callback.message.edit_text("🔗 **إدارة الروابط:**", reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "link_add")
async def link_add_1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("أرسل الرابط (URL):")
    await state.set_state(LinkState.waiting_for_url)

@dp.message(LinkState.waiting_for_url)
async def link_add_2(message: types.Message, state: FSMContext):
    await state.update_data(url=message.text)
    await message.answer("اكتب عنواناً أو وصفاً لهذا الرابط:")
    await state.set_state(LinkState.waiting_for_title)

@dp.message(LinkState.waiting_for_title)
async def link_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO links (user_id, url, title) VALUES (?, ?, ?)", (message.from_user.id, data['url'], message.text))
        await db.commit()
    await state.clear()
    await message.answer("✅ تم حفظ الرابط!", reply_markup=back_btn("links"))

@dp.callback_query(F.data == "link_list")
async def link_list(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT id, title, url FROM links WHERE user_id = ?", (callback.from_user.id,))
        links = await cursor.fetchall()
    
    if not links: return await callback.message.edit_text("لا توجد روابط.", reply_markup=back_btn("links"))
    
    text = "🌐 **الروابط:**\n\n"
    b = InlineKeyboardBuilder()
    for idx, (lid, title, url) in enumerate(links, 1):
        text += f"🔹 **{title}**\n{url}\n\n"
        b.row(types.InlineKeyboardButton(text=f"🗑️ حذف {title[:10]}", callback_data=f"del_link_{lid}"))
    b.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_links"))
    await callback.message.edit_text(text, disable_web_page_preview=True, reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("del_link_"))
async def delete_link(callback: types.CallbackQuery):
    lid = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM links WHERE id = ? AND user_id = ?", (lid, callback.from_user.id))
        await db.commit()
    await callback.answer("تم الحذف")
    await link_list(callback)

# الأهداف
@dp.callback_query(F.data == "menu_goals")
async def goals_menu(callback: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="➕ إضافة هدف جديد", callback_data="goal_add"))
    b.row(types.InlineKeyboardButton(text="🎯 متابعة التقدم", callback_data="goal_list"))
    b.row(types.InlineKeyboardButton(text="🔙 الرئيسية", callback_data="menu_main"))
    await callback.message.edit_text("🎯 **إدارة الأهداف الشخصية:**", reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "goal_add")
async def goal_add_1(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("اكتب عنوان الهدف العظيم الذي تسعى لتحقيقه:")
    await state.set_state(GoalState.waiting_for_title)

@dp.message(GoalState.waiting_for_title)
async def goal_save(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO goals (user_id, title, progress) VALUES (?, ?, 0)", (message.from_user.id, message.text))
        await db.commit()
    await state.clear()
    await message.answer("🎯 تم تسجيل الهدف! الانطلاق يبدأ بخطوة.", reply_markup=back_btn("goals"))

@dp.callback_query(F.data == "goal_list")
async def goal_list(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT id, title, progress FROM goals WHERE user_id = ? AND progress < 100", (callback.from_user.id,))
        goals = await cursor.fetchall()
    
    if not goals: return await callback.message.edit_text("لا توجد أهداف نشطة حالياً.", reply_markup=back_btn("goals"))
    
    text = "🎯 **أهدافك ومستوى تقدمك:**\n\n"
    b = InlineKeyboardBuilder()
    for gid, title, prog in goals:
        bar = "🟩" * (prog // 10) + "⬜" * (10 - (prog // 10))
        text += f"🏆 **{title}**\n   {bar} {prog}%\n\n"
        b.row(
            types.InlineKeyboardButton(text=f"➕ 10% لـ {title[:10]}", callback_data=f"prog_goal_{gid}"),
            types.InlineKeyboardButton(text="🗑️", callback_data=f"del_goal_{gid}")
        )
    b.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_goals"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("prog_goal_"))
async def update_goal_progress(callback: types.CallbackQuery):
    gid = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE goals SET progress = progress + 10 WHERE id = ? AND user_id = ?", (gid, callback.from_user.id))
        await db.commit()
    await callback.answer("تم تحديث التقدم 💪")
    await goal_list(callback)

@dp.callback_query(F.data.startswith("del_goal_"))
async def delete_goal(callback: types.CallbackQuery):
    gid = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (gid, callback.from_user.id))
        await db.commit()
    await callback.answer("تم حذف الهدف")
    await goal_list(callback)

# ==========================================
# 📊 5. لوحة الإحصائيات الشاملة
# ==========================================
@dp.callback_query(F.data == "menu_stats")
async def stats_menu(callback: types.CallbackQuery):
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_FILE) as db:
        c = await db.execute("SELECT points FROM users WHERE user_id = ?", (uid,))
        pts = (await c.fetchone())[0]
        
        c = await db.execute("SELECT COUNT(*) FROM notes WHERE user_id = ?", (uid,))
        n_cnt = (await c.fetchone())[0]
        
        c = await db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'Pending'", (uid,))
        t_cnt = (await c.fetchone())[0]
        
        c = await db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'Completed'", (uid,))
        tc_cnt = (await c.fetchone())[0]
        
        c = await db.execute("SELECT COUNT(*) FROM files WHERE user_id = ?", (uid,))
        f_cnt = (await c.fetchone())[0]

    if pts < 100: level = "مبتدئ 🌱"
    elif pts < 300: level = "منظم 💼"
    else: level = "أسطورة التنظيم 👑"

    text = (
        "📊 **تقرير مكتبك (LifeDesk):**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📝 الملاحظات: **{n_cnt}**\n"
        f"✅ مهام بانتظارك: **{t_cnt}**\n"
        f"🏆 مهام أنجزتها: **{tc_cnt}**\n"
        f"📂 ملفات بالخزنة: **{f_cnt}**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔥 إجمالي نقاطك: **{pts}** نقطة\n"
        f"🎖️ مستواك الحالي: **{level}**"
    )
    await callback.message.edit_text(text, reply_markup=back_btn(), parse_mode="Markdown")

# ==========================================
# ⏰ 6. نظام التذكيرات التلقائي (Scheduler)
# ==========================================
async def check_deadlines():
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT user_id, title FROM tasks WHERE due_date = ? AND status = 'Pending'", (today,))
        tasks = await cursor.fetchall()
        
    for user_id, title in tasks:
        try:
            await bot.send_message(user_id, f"⚠️ **تذكير تلقائي:**\nلديك مهمة يجب إنجازها اليوم:\n📌 *{title}*", parse_mode="Markdown")
        except Exception:
            pass # تخطي إذا قام المستخدم بحظر البوت

# ==========================================
# ⚙️ التشغيل الأساسي
# ==========================================
async def main():
    await init_db()
    
    # تشغيل نظام التذكيرات ليفحص المهام كل يوم الساعة 9 صباحاً
    # (للأغراض التجريبية، جعلته يعمل كل ساعة، يمكنك تغييره)
    scheduler.add_job(check_deadlines, "interval", hours=1)
    scheduler.start()

    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 LifeDesk V2.0 (Pro Version) is running...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
