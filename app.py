# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import csv
import html
import io
import os
import sqlite3
import threading
import time
from flask import Flask, request
import telebot
from telebot import types

TOKEN = "8602756904:AAEI_n7qamsQGOx4zwkh89hj4d4uIw4tSkE"
WEBHOOK_URL = f"https://eeeeeee-production.up.railway.app/{TOKEN}"
ADMIN_ID = 1250493517
BOT_URL = "https://t.me/DaftarHQBot"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

user_states = {}

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "", 200
    else:
        return "Forbidden", 403

def init_db():
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    
    tables = [
        """CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY, title TEXT, custom_message TEXT, duration INTEGER DEFAULT 0, show_in_channel INTEGER DEFAULT 1, show_on_leaderboard INTEGER DEFAULT 1)""",
        """CREATE TABLE IF NOT EXISTS user_profiles (user_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT, joined_timestamp REAL DEFAULT 0, streak_count INTEGER DEFAULT 0, last_attendance_date TEXT)""",
        """CREATE TABLE IF NOT EXISTS polls (poll_id TEXT PRIMARY KEY, owner_id INTEGER, count INTEGER, title TEXT, end_time REAL DEFAULT 0, is_closed INTEGER DEFAULT 0, show_in_channel INTEGER DEFAULT 1, channel_id TEXT, message_id INTEGER)""",
        """CREATE TABLE IF NOT EXISTS poll_votes (poll_id TEXT, user_id INTEGER, user_name TEXT, username TEXT, vote_timestamp REAL DEFAULT 0, PRIMARY KEY (poll_id, user_id))""",
        """CREATE TABLE IF NOT EXISTS channel_daily_attendance (user_id INTEGER, channel_id TEXT, date_str TEXT, count INTEGER DEFAULT 0, PRIMARY KEY (user_id, channel_id, date_str))""",
        """CREATE TABLE IF NOT EXISTS channel_daily_posts (channel_id TEXT, date_str TEXT, posts_count INTEGER DEFAULT 0, PRIMARY KEY (channel_id, date_str))""",
        """CREATE TABLE IF NOT EXISTS saved_channels (user_id INTEGER, channel_id TEXT, channel_title TEXT, show_on_leaderboard INTEGER DEFAULT 1, PRIMARY KEY (user_id, channel_id))""",
        """CREATE TABLE IF NOT EXISTS channel_total_visits (channel_id TEXT PRIMARY KEY, channel_title TEXT, visits_count INTEGER DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS authorized_question_creators (user_id INTEGER PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS interactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, timestamp REAL)""",
        """CREATE TABLE IF NOT EXISTS referrals (owner_id INTEGER PRIMARY KEY, visits_count INTEGER DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS user_referral_logs (owner_id INTEGER, visitor_id INTEGER, PRIMARY KEY (owner_id, visitor_id))""",
        """CREATE TABLE IF NOT EXISTS user_points (user_id INTEGER PRIMARY KEY, points INTEGER DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, points INTEGER, max_uses INTEGER, uses_count INTEGER DEFAULT 0, expires_at REAL, is_closed INTEGER DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS coupon_uses (code TEXT, user_id INTEGER, PRIMARY KEY (code, user_id))""",
        """CREATE TABLE IF NOT EXISTS questions (question_id TEXT PRIMARY KEY, owner_id INTEGER, question_text TEXT, opt_a TEXT, opt_b TEXT, opt_c TEXT, opt_d TEXT, correct_opt TEXT, channel_id TEXT, message_id INTEGER, is_closed INTEGER DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS question_answers (question_id TEXT, user_id INTEGER, selected_option TEXT, is_correct INTEGER, earned_points INTEGER, PRIMARY KEY (question_id, user_id))""",
        """CREATE TABLE IF NOT EXISTS user_badges (user_id INTEGER PRIMARY KEY, badge_name TEXT, badge_icon TEXT)""",
        """CREATE TABLE IF NOT EXISTS scheduled_posts (sched_id TEXT PRIMARY KEY, user_id INTEGER, channel_id TEXT, post_type TEXT, title TEXT, content_data TEXT, run_time REAL)""",
        """CREATE TABLE IF NOT EXISTS question_speed_race (question_id TEXT, user_id INTEGER, user_name TEXT, rank_pos INTEGER, PRIMARY KEY (question_id, user_id))""",
        """CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT)"""
    ]
    
    for table in tables:
        cursor.execute(table)
        
    # التحقق التلقائي من الأعمدة لتفادي أخطاء التحديث
    migrations = [
        ("user_settings", "ALTER TABLE user_settings ADD COLUMN show_on_leaderboard INTEGER DEFAULT 1"),
        ("user_profiles", "ALTER TABLE user_profiles ADD COLUMN streak_count INTEGER DEFAULT 0"),
        ("user_profiles", "ALTER TABLE user_profiles ADD COLUMN last_attendance_date TEXT"),
        ("saved_channels", "ALTER TABLE saved_channels ADD COLUMN show_on_leaderboard INTEGER DEFAULT 1")
    ]
    
    for table_name, query in migrations:
        try:
            cursor.execute(query)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

init_db()

def log_user_interaction(user_id, username, first_name):
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    now_ts = time.time()
    uname_str = f"@{username}" if username else "لا يوجد"

    cursor.execute("SELECT user_id FROM user_profiles WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    is_new = False

    if not exists:
        is_new = True
        cursor.execute(
            "INSERT INTO user_profiles (user_id, full_name, username, joined_timestamp, streak_count, last_attendance_date) VALUES (?, ?, ?, ?, 0, '')",
            (user_id, first_name, uname_str, now_ts),
        )
    else:
        cursor.execute(
            "UPDATE user_profiles SET full_name = ?, username = ? WHERE user_id = ?",
            (first_name, uname_str, user_id),
        )

    cursor.execute(
        "INSERT INTO interactions (user_id, timestamp) VALUES (?, ?)",
        (user_id, now_ts),
    )
    conn.commit()
    conn.close()
    return is_new

def get_arabic_date_string():
    days = {
        "Saturday": "السبت", "Sunday": "الأحد", "Monday": "الإثنين",
        "Tuesday": "الثلاثاء", "Wednesday": "الأربعاء", "Thursday": "الخميس", "Friday": "الجمعة"
    }
    months = {
        "1": "يناير", "2": "فبراير", "3": "مارس", "4": "أبريل", "5": "مايو", "6": "يونيو",
        "7": "يوليو", "8": "أغسطس", "9": "سبتمبر", "10": "أكتوبر", "11": "نوفمبر", "12": "ديسمبر"
    }
    now = datetime.now()
    d_name = days.get(now.strftime("%A"), "")
    m_name = months.get(str(now.month), "")
    return f"{d_name} {now.day} {m_name} {now.year}"

def get_user_badge(points):
    if points >= 500:
        return "💎 ماسي متقدم", "💎"
    elif points >= 250:
        return "🥇 ذهبي مميز", "🥇"
    elif points >= 100:
        return "🥈 فضي نشط", "🥈"
    elif points >= 30:
        return "🥉 برونزي تفاعلي", "🥉"
    else:
        return "🏅 عضو جديد", "🏅"

def create_colored_btn(text, callback_data=None, url=None, style="primary"):
    if url:
        btn = types.InlineKeyboardButton(text=text, url=url)
    else:
        btn = types.InlineKeyboardButton(text=text, callback_data=callback_data)
    return btn

def check_forced_subscription(user_id):
    if user_id == ADMIN_ID:
        return True
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'forced_channel'")
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        return True

    channel_username = row[0]
    try:
        member = bot.get_chat_member(channel_username, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        print(f"Subscription check error: {e}")
        return True
    return False

def send_subscription_required_message(chat_id):
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'forced_channel'")
    row = cursor.fetchone()
    conn.close()
    channel_username = row[0] if row else "@Channel"

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(create_colored_btn("📢 اشترك في القناة الآن", url=f"https://t.me/{channel_username.replace('@', '')}", style="primary"))
    markup.add(create_colored_btn("🔄 تحقق من الاشتراك", callback_data="check_sub", style="success"))

    msg = f"⛔ عذراً، يجب عليك الاشتراك في قناة البوت الرسمية أولاً لكي تتمكن من استخدامه.\n\n📌 قناة الاشتراك: <b>{channel_username}</b>\n\n<i>اضغط على زر الاشتراك ثم اضغط على (تحقق من الاشتراك).</i>"
    bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=markup)

def get_main_inline_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_settings = create_colored_btn("⚙️ إعدادات البوست", callback_data="menu_settings", style="primary")
    btn_share = create_colored_btn("🚀 نشر بوست جديد بالقناة", callback_data="menu_share", style="primary")
    markup.add(btn_settings, btn_share)

    btn_q_create = create_colored_btn("❓ طرح سؤال تفاعلي", callback_data="menu_create_question", style="success")
    btn_coupon_redeem = create_colored_btn("🎁 شحن كوبون هدية", callback_data="menu_redeem_prompt", style="success")
    markup.add(btn_q_create, btn_coupon_redeem)

    btn_sched = create_colored_btn("⏰ جدولة بوست/سؤال", callback_data="menu_schedule_prompt", style="primary")
    btn_stats = create_colored_btn("📊 إحصائيات التحليل المتقدم", callback_data="menu_stats", style="success")
    markup.add(btn_sched, btn_stats)

    btn_top = create_colored_btn("🏆 قائمة المتصدرين", callback_data="menu_leaderboard", style="success")
    btn_points = create_colored_btn("🌟 لوحة النقاط", callback_data="menu_points", style="success")
    markup.add(btn_top, btn_points)

    btn_profile = create_colored_btn("👤 الملف الشخصي (/profile)", callback_data="menu_profile", style="primary")
    btn_support = create_colored_btn("🛠️ الدعم والمساعدة", callback_data="menu_support", style="success")
    markup.add(btn_profile, btn_support)

    if user_id == ADMIN_ID:
        btn_admin = create_colored_btn("👑 لوحة تحكم المشرف", callback_data="menu_admin", style="danger")
        markup.add(btn_admin)

    return markup

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "لا يوجد"
    first_name = message.from_user.first_name

    is_new = log_user_interaction(user_id, username, first_name)

    if is_new and user_id != ADMIN_ID:
        admin_alert = f"🚨 <b>مستخدم جديد فتح البوت!</b>\n\n👤 <b>الاسم:</b> {html.escape(first_name)}\n🔗 <b>المعرف:</b> @{html.escape(username)}\n🆔 <b>الآيدي:</b> <code>{user_id}</code>\n⏰ <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            bot.send_message(ADMIN_ID, admin_alert, parse_mode="HTML")
        except Exception as e:
            print(f"فشل إرسال التنبيه للمطور: {e}")

    if not check_forced_subscription(user_id):
        send_subscription_required_message(message.chat.id)
        return

    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    args = message.text.split()
    if len(args) > 1 and message.text.startswith("/start"):
        try:
            owner_id = int(args[1])
            if owner_id != user_id:
                cursor.execute("SELECT * FROM user_referral_logs WHERE owner_id = ? AND visitor_id = ?", (owner_id, user_id))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO user_referral_logs (owner_id, visitor_id) VALUES (?, ?)", (owner_id, user_id))
                    cursor.execute("INSERT INTO referrals (owner_id, visits_count) VALUES (?, 1) ON CONFLICT(owner_id) DO UPDATE SET visits_count = visits_count + 1", (owner_id,))
                    conn.commit()
        except ValueError:
            pass

    cursor.execute("SELECT visits_count FROM referrals WHERE owner_id = ?", (user_id,))
    res = cursor.fetchone()
    total_visits = res[0] if res else 0
    cursor.execute("SELECT points FROM user_points WHERE user_id = ?", (user_id,))
    p_res = cursor.fetchone()
    user_points = p_res[0] if p_res else 0

    badge_name, badge_icon = get_user_badge(user_points)
    cursor.execute("INSERT OR REPLACE INTO user_badges (user_id, badge_name, badge_icon) VALUES (?, ?, ?)", (user_id, badge_name, badge_icon))
    conn.commit()
    conn.close()

    markup = get_main_inline_keyboard(user_id)
    bot_username = bot.get_me().username
    welcome_text = f"✨ <b>حيّاك الله أخي/أختي</b>\n\n<blockquote>📌 <i>أنشئ بوستات الحضور والأسئلة التفاعلية بكل احترافية، مع تحليلات ذكية ونظام الأوسمة وتحديات السرعة المتقدمة.</i></blockquote>\n\n🏅 <b>وسامك الحالي:</b> {badge_icon} <b>{badge_name}</b>\n\n⚠️ <b>تنبيه هام جداً:</b> ارفع البوت <b>مشرفاً (Admin)</b> في قناتك مع صلاحية (تعديل رسائل الآخرين وحذفها) لكي يعمل التحديث الفوري.\n\n🔗 <b>رابط دعوتك الشخصي:</b>\n<code>https://t.me/{bot_username}?start={user_id}</code>\n\n📊 <b>إجمالي زوار رابطك:</b> <code>{total_visits}</code> شخص\n🌟 <b>رصيدك من النقاط:</b> <code>{user_points}</code> نقطة\n\n👇 <b>اختر ما تحتاجه من الأزرار أدناه:</b>"
    bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=["stats"])
def cmd_bot_statistics(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ عذراً، هذا الأمر مخصص للمشرف فقط.")
        return

    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    today_start_ts = datetime.strptime(today_str, "%Y-%m-%d").timestamp()
    week_ago_ts = time.time() - (7 * 24 * 60 * 60)
    month_ago_ts = time.time() - (30 * 24 * 60 * 60)

    cursor.execute("SELECT COUNT(*) FROM user_profiles")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE joined_timestamp >= ?", (today_start_ts,))
    users_today = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE joined_timestamp >= ?", (week_ago_ts,))
    users_week = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE joined_timestamp >= ?", (month_ago_ts,))
    users_month = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM interactions")
    total_interactions = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM interactions WHERE timestamp >= ?", (today_start_ts,))
    interactions_today = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM interactions WHERE timestamp >= ?", (week_ago_ts,))
    interactions_week = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM interactions WHERE timestamp >= ?", (month_ago_ts,))
    interactions_month = cursor.fetchone()[0]

    conn.close()

    stats_report = f"📊 <b>لوحة تحكم وإحصائيات البوت الشاملة</b>\n\n👥 <b>إحصائيات المستخدمين الجدد:</b>\n• اليوم: <code>{users_today}</code> مستخدم\n• آخر 7 أيام: <code>{users_week}</code> مستخدم\n• آخر 30 يوماً: <code>{users_month}</code> مستخدم\n• <b>إجمالي المستخدمين:</b> <code>{total_users}</code> 👤\n\n📈 <b>إحصائيات التفاعلات والنشاط:</b>\n• تفاعلات اليوم: <code>{interactions_today}</code> تفاعل\n• تفاعلات الأسبوع: <code>{interactions_week}</code> تفاعل\n• تفاعلات الشهر: <code>{interactions_month}</code> تفاعل\n• <b>إجمالي التفاعلات:</b> <code>{total_interactions}</code> ⚡️\n\n🕒 <b>وقت التقرير:</b> <code>{now.strftime('%Y-%m-%d %H:%M')}</code>"
    bot.send_message(message.chat.id, stats_report, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_subscription(call):
    user_id = call.from_user.id
    if check_forced_subscription(user_id):
        bot.answer_callback_query(call.id, "✅ شكراً لاشتراكك! يمكنك استخدام البوت الآن.", show_alert=True)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT points FROM user_points WHERE user_id = ?", (user_id,))
        p_res = cursor.fetchone()
        user_points = p_res[0] if p_res else 0
        badge_name, badge_icon = get_user_badge(user_points)
        conn.close()

        markup = get_main_inline_keyboard(user_id)
        welcome_text = f"✨ <b>مرحباً بك مجدداً يا {html.escape(call.from_user.first_name)}</b>\n\n🏅 <b>وسامك الحالي:</b> {badge_icon} <b>{badge_name}</b>\n\n👇 <b>اختر ما تحتاجه من الأزرار أدناه:</b>"
        bot.send_message(call.message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)
    else:
        bot.answer_callback_query(call.id, "❌ لم تقم بالاشتراك في القناة بعد أو لم يتم رصد اشتراكك!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("attend_"))
def handle_attendance_click(call):
    user_id = call.from_user.id
    if not check_forced_subscription(user_id):
        bot.answer_callback_query(call.id, "يجب عليك الاشتراك في القناة أولاً ⛔", show_alert=True)
        send_subscription_required_message(call.message.chat.id)
        return

    poll_id = call.data.replace("attend_", "")
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT owner_id, count, title, end_time, is_closed, show_in_channel, channel_id, message_id FROM polls WHERE poll_id = ?", (poll_id,))
    poll = cursor.fetchone()
    if not poll:
        bot.answer_callback_query(call.id, "❌ عذراً، بوست الحضور غير موجود أو تم حذفه.", show_alert=True)
        conn.close()
        return

    owner_id, count, title, end_time, is_closed, show_in_channel, channel_id, message_id = poll

    if is_closed == 1 or (end_time > 0 and time.time() > end_time):
        cursor.execute("UPDATE polls SET is_closed = 1 WHERE poll_id = ?", (poll_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "⌛ عذراً، انتهى وقت تسجيل الحضور لهذا البوست!", show_alert=True)
        return

    cursor.execute("SELECT * FROM poll_votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
    if cursor.fetchone():
        bot.answer_callback_query(call.id, "⚠️ لقد قمت بتسجيل حضورك مسبقاً في هذا البوست!", show_alert=True)
        conn.close()
        return

    user_name = call.from_user.first_name
    username = f"@{call.from_user.username}" if call.from_user.username else "لا يوجد"
    now_ts = time.time()

    cursor.execute("INSERT INTO poll_votes (poll_id, user_id, user_name, username, vote_timestamp) VALUES (?, ?, ?, ?, ?)", (poll_id, user_id, user_name, username, now_ts))

    new_count = count + 1
    cursor.execute("UPDATE polls SET count = ? WHERE poll_id = ?", (new_count, poll_id))

    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO channel_daily_attendance (user_id, channel_id, date_str, count) VALUES (?, ?, ?, 1) ON CONFLICT(user_id, channel_id, date_str) DO UPDATE SET count = count + 1",
        (user_id, channel_id, today_str)
    )

    cursor.execute("SELECT streak_count, last_attendance_date FROM user_profiles WHERE user_id = ?", (user_id,))
    streak_row = cursor.fetchone()
    current_streak = 0
    last_date = ""
    if streak_row:
        current_streak = streak_row[0] or 0
        last_date = streak_row[1] or ""

    if last_date == today_str:
        streak_msg_extra = ""
    elif last_date == yesterday_str:
        current_streak += 1
        cursor.execute("UPDATE user_profiles SET streak_count = ?, last_attendance_date = ? WHERE user_id = ?", (current_streak, today_str, user_id))
        streak_msg_extra = f"\n🔥 سلسلة حضور متتالية: {current_streak} أيام!"
    else:
        current_streak = 1
        cursor.execute("UPDATE user_profiles SET streak_count = ?, last_attendance_date = ? WHERE user_id = ?", (current_streak, today_str, user_id))
        streak_msg_extra = "\n🔥 بدأت سلسلة حضور جديدة اليوم (1 أيام)."

    try:
        chat_info = bot.get_chat(channel_id)
        channel_title = chat_info.title or channel_id
    except Exception:
        channel_title = str(channel_id)

    cursor.execute(
        "INSERT INTO channel_total_visits (channel_id, channel_title, visits_count) VALUES (?, ?, 1) ON CONFLICT(channel_id) DO UPDATE SET visits_count = visits_count + 1, channel_title = ?",
        (str(channel_id), channel_title, channel_title)
    )

    points_earned = 10 + (min(current_streak, 5) * 2)
    cursor.execute("INSERT INTO user_points (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points = points + ?", (user_id, points_earned, points_earned))
    cursor.execute("SELECT points FROM user_points WHERE user_id = ?", (user_id,))
    user_pts = cursor.fetchone()[0]
    b_name, b_icon = get_user_badge(user_pts)
    cursor.execute("INSERT OR REPLACE INTO user_badges (user_id, badge_name, badge_icon) VALUES (?, ?, ?)", (user_id, b_name, b_icon))

    conn.commit()

    cursor.execute("SELECT user_name, username FROM poll_votes WHERE poll_id = ?", (poll_id,))
    all_votes = cursor.fetchall()
    conn.close()

    try:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(create_colored_btn(f"✅ تسجيل الحضور [{new_count}]", callback_data=f"attend_{poll_id}", style="success"))
        keyboard.add(create_colored_btn("🤖 الانتقال للبوت", url=BOT_URL, style="primary"))

        time_note = "\n<i>⏱️ البوست مفتوح طوال الوقت لتسجيل الحضور.</i>"
        msg_content = f"<b>📢 {html.escape(title)}</b>\n\n<i>اضغط على الزر الملون أدناه لتسجيل حضورك الرسمي فوراً:</i>{time_note}"

        if show_in_channel == 1:
            voters_lines = [f"{i+1}. <b>{html.escape(v[0])}</b> ({html.escape(v[1])})" for i, v in enumerate(all_votes)]
            voters_str = "\n".join(voters_lines) if voters_lines else "لا توجد تسجيلات حتى الآن."
            msg_content += f"\n\n<blockquote expandable><b>👥 قائمة الحضور المسجلين ({new_count}):</b>\n{voters_str}</blockquote>"

        bot.edit_message_text(chat_id=channel_id, message_id=message_id, text=msg_content, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)
    except Exception as e:
        print(f"Error updating channel message on attend: {e}")

    bot.answer_callback_query(call.id, f"✅ تم تسجيل حضورك بنجاح!\n➕ حصلت على {points_earned} نقاط ووسام: {b_icon} {b_name}{streak_msg_extra}", show_alert=True)

    try:
        owner_msg = f"🔔 <b>مستخدم جديد سجل حضوره في بوستك!</b>\n\n📌 <b>البوست:</b> {html.escape(title)}\n👤 <b>الاسم:</b> {html.escape(user_name)}\n🔗 <b>المعرف:</b> {username}\n📊 <b>إجمالي الحضور الآن:</b> {new_count}"
        bot.send_message(owner_id, owner_msg, parse_mode="HTML")
    except Exception:
        pass

@bot.message_handler(commands=["backup"])
def cmd_backup(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
        return
    if os.path.exists("roulette_bot.db"):
        with open("roulette_bot.db", "rb") as f:
            bot.send_document(message.chat.id, f, caption="📦 <b>نسخة احتياطية لقاعدة البيانات (Backup)</b>", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ ملف قاعدة البيانات غير موجود.")

@bot.message_handler(commands=["restore"])
def cmd_restore(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
        return
    user_states[ADMIN_ID] = "waiting_restore_file"
    bot.reply_to(message, "📥 <b>أرسل الآن ملف قاعدة البيانات (.db) لاستعادة النسخة الاحتياطية (Restore):</b>", parse_mode="HTML")

@bot.message_handler(content_types=["document"], func=lambda message: message.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID) == "waiting_restore_file")
def process_restore_file(message):
    user_states.pop(ADMIN_ID, None)
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("roulette_bot.db", "wb") as f:
            f.write(downloaded_file)
        init_db()
        bot.reply_to(message, "✅ <b>تم استعادة قاعدة البيانات (Restore) وتحديث الهيكلية بنجاح!</b>", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ <b>فشل استعادة قاعدة البيانات:</b> <code>{e}</code>", parse_mode="HTML")

@bot.message_handler(commands=["points", "رصيدي"])
def cmd_points(message):
    if not check_forced_subscription(message.from_user.id):
        send_subscription_required_message(message.chat.id)
        return
    user_id = message.from_user.id
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT points FROM user_points WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    pts = res[0] if res else 0
    b_name, b_icon = get_user_badge(pts)
    conn.close()
    bot.reply_to(message, f"🌟 <b>رصيدك الحالي:</b> <code>{pts}</code> نقطة\n🏅 <b>الوسام:</b> {b_icon} {b_name}", parse_mode="HTML")

@bot.message_handler(commands=["profile"])
def cmd_profile(message):
    if not check_forced_subscription(message.from_user.id):
        send_subscription_required_message(message.chat.id)
        return
    show_profile_data(message.chat.id, message.from_user.id)

def show_profile_data(chat_id, user_id):
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT points FROM user_points WHERE user_id = ?", (user_id,))
    p_res = cursor.fetchone()
    pts = p_res[0] if p_res else 0

    badge_name, badge_icon = get_user_badge(pts)
    cursor.execute("SELECT COUNT(*) FROM user_points WHERE points > ?", (pts,))
    higher_users = cursor.fetchone()[0]
    rank = higher_users + 1

    cursor.execute("SELECT streak_count FROM user_profiles WHERE user_id = ?", (user_id,))
    st_res = cursor.fetchone()
    streak_count = st_res[0] if st_res and st_res[0] else 0

    cursor.execute("SELECT COUNT(*), SUM(is_correct) FROM question_answers WHERE user_id = ?", (user_id,))
    q_res = cursor.fetchone()
    total_q = q_res[0] if q_res and q_res[0] else 0
    correct_q = q_res[1] if q_res and q_res[1] else 0
    accuracy = round((correct_q / total_q) * 100, 1) if total_q > 0 else 0.0

    cursor.execute("SELECT DISTINCT channel_title, channel_id FROM saved_channels WHERE user_id = ?", (user_id,))
    saved_channels = cursor.fetchall()

    cursor.execute("SELECT code FROM coupon_uses WHERE user_id = ?", (user_id,))
    used_coupons = [row[0] for row in cursor.fetchall()]
    conn.close()

    coupons_str = ", ".join(used_coupons) if used_coupons else "لا توجد"
    channels_str = ", ".join([f"{html.escape(c[0])} ({c[1]})" for c in saved_channels]) if saved_channels else "لا توجد قنوات مسجلة"

    profile_text = f"👤 <b>لوحة الملف الشخصي والإحصائيات الفردية:</b>\n\n🏅 <b>الوسام والرتبة:</b>\n<blockquote>• الوسام الحالي: {badge_icon} <b>{badge_name}</b>\n• رصيد النقاط: <code>{pts}</code> نقطة\n• الرتبة العالمية: المركز <code>{rank}</code>\n• 🔥 سلسلة الحضور: <code>{streak_count}</code> أيام</blockquote>\n\n📊 <b>سجل الإجابات:</b>\n<blockquote>• المشاركات: <code>{total_q}</code>\n• الصحيحة: <code>{correct_q}</code>\n• الدقة: <code>{accuracy}%</code></blockquote>\n\n🌐 <b>القنوات المسجلة:</b>\n<blockquote>{channels_str}</blockquote>\n\n🎁 <b>الكوبونات:</b>\n<blockquote>{coupons_str}</blockquote>"
    bot.send_message(chat_id, profile_text, parse_mode="HTML")

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
        return
    show_admin_panel(message.chat.id)

def show_admin_panel(chat_id):
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_profiles")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM polls")
    total_polls = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM coupons")
    total_coupons = cursor.fetchone()[0]
    cursor.execute("SELECT value FROM system_settings WHERE key = 'forced_channel'")
    f_row = cursor.fetchone()
    forced_channel_status = f_row[0] if f_row and f_row[0] else "غير مفعلة ❌"
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(create_colored_btn("📢 تعيين / تعديل قناة الاشتراك", callback_data="admin_set_forced_channel", style="primary"))
    markup.add(create_colored_btn("🎁 إدارة الكوبونات (إضافة/حذف)", callback_data="admin_manage_coupons", style="success"))
    markup.add(create_colored_btn("📊 إرسال التقرير الأسبوعي الفوري", callback_data="admin_send_weekly_report", style="success"))

    admin_panel = f"👑 <b>لوحة تحكم المشرف العامة:</b>\n\n<blockquote>• <b>إجمالي المستخدمين:</b> <code>{total_users}</code>\n• <b>إجمالي البوستات:</b> <code>{total_polls}</code>\n• <b>قناة الاشتراك:</b> <code>{forced_channel_status}</code>\n• <b>الكوبونات:</b> <code>{total_coupons}</code></blockquote>"
    bot.send_message(chat_id, admin_panel, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_coupons")
def admin_manage_coupons(call):
    if call.from_user.id != ADMIN_ID:
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        create_colored_btn("➕ إضافة كوبون", callback_data="admin_add_coupon", style="success"),
        create_colored_btn("🗑️ حذف كوبون", callback_data="admin_delete_coupon", style="danger")
    )
    bot.edit_message_text("🎁 <b>إدارة الكوبونات والهدايا:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_coupon")
def admin_add_coupon_start(call):
    user_states[ADMIN_ID] = {"step": "waiting_coupon_code"}
    bot.send_message(ADMIN_ID, "📝 أرسل الآن **كود الكوبون**:", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and isinstance(user_states.get(ADMIN_ID), dict) and user_states.get(ADMIN_ID).get("step") == "waiting_coupon_code")
def admin_add_coupon_code(message):
    user_states[ADMIN_ID]["code"] = message.text.strip()
    user_states[ADMIN_ID]["step"] = "waiting_coupon_points"
    bot.reply_to(message, "💰 كم عدد النقاط؟")

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and isinstance(user_states.get(ADMIN_ID), dict) and user_states.get(ADMIN_ID).get("step") == "waiting_coupon_points")
def admin_add_coupon_points(message):
    try:
        points = int(message.text.strip())
        user_states[ADMIN_ID]["points"] = points
        user_states[ADMIN_ID]["step"] = "waiting_coupon_uses"
        bot.reply_to(message, "👥 عدد مرات الاستخدام المسموحة؟")
    except ValueError:
        bot.reply_to(message, "❌ أرقام فقط.")

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and isinstance(user_states.get(ADMIN_ID), dict) and user_states.get(ADMIN_ID).get("step") == "waiting_coupon_uses")
def admin_add_coupon_uses(message):
    try:
        max_uses = int(message.text.strip())
        code = user_states[ADMIN_ID]["code"]
        points = user_states[ADMIN_ID]["points"]

        conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO coupons (code, points, max_uses, uses_count, is_closed) VALUES (?, ?, ?, 0, 0)", (code, points, max_uses))
        conn.commit()
        conn.close()

        user_states.pop(ADMIN_ID, None)
        bot.reply_to(message, f"✅ تم إضافة الكوبون <code>{code}</code> بنجاح!", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "❌ أرقام فقط.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_coupon")
def admin_delete_coupon_start(call):
    user_states[ADMIN_ID] = "waiting_delete_coupon_code"
    bot.send_message(ADMIN_ID, "🗑️ أرسل كود الكوبون للحذف:", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID) == "waiting_delete_coupon_code")
def admin_delete_coupon_execute(message):
    code = message.text.strip()
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM coupons WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    user_states.pop(ADMIN_ID, None)
    bot.reply_to(message, f"✅ تم حذف الكوبون <code>{code}</code>.", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_forced_channel")
def admin_set_forced_channel_prompt(call):
    if call.from_user.id != ADMIN_ID:
        return
    user_states[ADMIN_ID] = "waiting_forced_channel_input"
    bot.answer_callback_query(call.id)
    bot.send_message(ADMIN_ID, "📢 أرسل معرف قناة الاشتراك الإجباري (أو off للإلغاء):", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and user_states.get(ADMIN_ID) == "waiting_forced_channel_input")
def save_forced_channel_input(message):
    user_states.pop(ADMIN_ID, None)
    val = message.text.strip()
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    if val.lower() == "off":
        cursor.execute("DELETE FROM system_settings WHERE key = 'forced_channel'")
        bot.reply_to(message, "✅ تم إلغاء تفعيل الاشتراك الإجباري.")
    else:
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('forced_channel', ?)", (val,))
        bot.reply_to(message, f"✅ تم تعيين قناة الاشتراك: <code>{val}</code>", parse_mode="HTML")
    conn.commit()
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
def handle_menu_callbacks(call):
    user_id = call.from_user.id
    if not check_forced_subscription(user_id):
        bot.answer_callback_query(call.id, "يجب الاشتراك في القناة أولاً ⛔", show_alert=True)
        send_subscription_required_message(call.message.chat.id)
        return

    action = call.data.replace("menu_", "")

    if action == "settings":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            create_colored_btn("📝 اختيار العنوان", callback_data="wizard_title_type", style="primary"),
            create_colored_btn("⏱️ ضبط المدة", callback_data="set_duration", style="primary"),
            create_colored_btn("👁️ ضبط عرض القائمة", callback_data="set_display_mode", style="primary"),
            create_colored_btn("🔒 خصوصية المتصدرين", callback_data="set_privacy_leaderboard", style="primary")
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "⚙️ <b>إعدادات بوستات الحضور:</b>", parse_mode="HTML", reply_markup=markup)

    elif action == "share":
        bot.answer_callback_query(call.id)
        show_channel_selection_menu(call.message.chat.id, user_id)

    elif action == "schedule_prompt":
        bot.answer_callback_query(call.id)
        user_states[user_id] = "waiting_sched_input"
        bot.send_message(call.message.chat.id, "⏰ أرسل نص البوست المراد جدولته:", parse_mode="HTML")

    elif action == "create_question":
        bot.answer_callback_query(call.id)
        user_states[user_id] = "waiting_q_text"
        bot.send_message(call.message.chat.id, "❓ أرسل نص السؤال التفاعلي:", parse_mode="HTML")

    elif action == "redeem_prompt":
        bot.answer_callback_query(call.id)
        user_states[user_id] = "waiting_coupon_input"
        bot.send_message(call.message.chat.id, "🎁 أرسل كود الكوبون:", parse_mode="HTML")

    elif action == "profile":
        bot.answer_callback_query(call.id)
        show_profile_data(call.message.chat.id, user_id)

    elif action == "stats":
        bot.answer_callback_query(call.id)
        conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT poll_id, title, count FROM polls WHERE owner_id = ? ORDER BY rowid DESC", (user_id,))
        user_polls = cursor.fetchall()
        conn.close()

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(create_colored_btn("📑 تقرير أسبوعي", callback_data="report_weekly_supervisor", style="primary"))
        for pid, title, cnt in user_polls:
            short_title = title[:25] + "..." if len(title) > 25 else title
            markup.add(create_colored_btn(f"📌 {short_title} ({cnt})", callback_data=f"view_stats_{pid}", style="success"))
        bot.send_message(call.message.chat.id, "📊 <b>إحصائيات البوستات:</b>", parse_mode="HTML", reply_markup=markup)

    elif action == "leaderboard":
        bot.answer_callback_query(call.id)
        conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT tp.user_id, tp.points, p.full_name, b.badge_icon FROM user_points tp LEFT JOIN user_profiles p ON tp.user_id = p.user_id LEFT JOIN user_badges b ON tp.user_id = b.user_id ORDER BY tp.points DESC LIMIT 5")
        top_points = cursor.fetchall()
        conn.close()

        text = "🏆 <b>قائمة المتصدرين (النقاط):</b>\n"
        for i, (uid, pts, fname, b_icon) in enumerate(top_points):
            text += f"{i+1}. {b_icon or '🏅'} {html.escape(fname or 'مستخدم')} — <b>{pts}</b> نقطة\n"
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")

    elif action == "points":
        bot.answer_callback_query(call.id)
        conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT points FROM user_points WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        pts = res[0] if res else 0
        b_name, b_icon = get_user_badge(pts)
        conn.close()
        bot.send_message(call.message.chat.id, f"🌟 رصيدك: <b>{pts}</b> نقطة\nوسامك: {b_icon} {b_name}", parse_mode="HTML")

    elif action == "support":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "💬 تواصل مع المطور عبر @DaftarHQBot", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "set_privacy_leaderboard")
def callback_set_privacy_leaderboard(call):
    user_id = call.from_user.id
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT show_on_leaderboard FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    user_show = row[0] if row and row[0] is not None else 1
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(create_colored_btn(f"👤 الظهور بالمتصدرين: {'✅' if user_show == 1 else '🔒'}", callback_data="toggle_user_leaderboard_privacy", style="success" if user_show == 1 else "danger"))
    markup.add(create_colored_btn("🔙 عودة", callback_data="menu_settings", style="primary"))
    bot.edit_message_text("🔒 <b>إعدادات الخصوصية:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "toggle_user_leaderboard_privacy")
def toggle_user_leaderboard_privacy(call):
    user_id = call.from_user.id
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT show_on_leaderboard FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    current = row[0] if row and row[0] is not None else 1
    new_val = 0 if current == 1 else 1

    cursor.execute("INSERT OR IGNORE INTO user_settings (user_id, title, duration, show_in_channel, show_on_leaderboard) VALUES (?, '', 0, 1, ?)", (user_id, new_val))
    cursor.execute("UPDATE user_settings SET show_on_leaderboard = ? WHERE user_id = ?", (new_val, user_id))
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, "✅ تم التحديث!", show_alert=True)
    callback_set_privacy_leaderboard(call)

def show_channel_selection_menu(chat_id, user_id):
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_title, channel_id FROM saved_channels WHERE user_id = ?", (user_id,))
    saved = cursor.fetchall()
    conn.close()

    if saved:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c_title, c_id in saved:
            markup.add(create_colored_btn(f"📢 {html.escape(c_title)}", callback_data=f"select_chan_{c_id}", style="success"))
        markup.add(create_colored_btn("➕ قناة جديدة", callback_data="add_new_channel_prompt", style="primary"))
        bot.send_message(chat_id, "🚀 اختر القناة:", parse_mode="HTML", reply_markup=markup)
    else:
        user_states[user_id] = "waiting_channel_username"
        bot.send_message(chat_id, "🚀 أرسل معرف القناة (مثال: @MyChannel):", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "add_new_channel_prompt")
def add_new_channel_prompt(call):
    user_id = call.from_user.id
    user_states[user_id] = "waiting_channel_username"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🚀 أرسل معرف القناة الجديدة:", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_chan_"))
def select_saved_channel(call):
    user_id = call.from_user.id
    channel_id = call.data.replace("select_chan_", "")
    bot.answer_callback_query(call.id)
    publish_poll_to_channel(call.message, user_id, channel_id)

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "waiting_channel_username")
def process_channel_posting(message):
    user_id = message.from_user.id
    channel_input = message.text.strip()
    user_states.pop(user_id, None)
    publish_poll_to_channel(message, user_id, channel_input)

def publish_poll_to_channel(message_or_call_msg, user_id, channel_input):
    chat_id_to_send = message_or_call_msg.chat.id if hasattr(message_or_call_msg, "chat") else message_or_call_msg.message.chat.id
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()

    try:
        chat_info = bot.get_chat(channel_input)
        real_channel_id = str(chat_info.id)
        c_title = chat_info.title or real_channel_id
    except Exception as e:
        conn.close()
        bot.send_message(chat_id_to_send, f"❌ خطأ في الوصول للقناة: <code>{e}</code>", parse_mode="HTML")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT posts_count FROM channel_daily_posts WHERE channel_id = ? AND date_str = ?", (real_channel_id, today_str))
    p_row = cursor.fetchone()
    if p_row and p_row[0] >= 2:
        conn.close()
        bot.send_message(chat_id_to_send, "⚠️ عذراً، تم الوصول للحد الأقصى للبوستات اليومية (2).", parse_mode="HTML")
        return

    cursor.execute("SELECT title, duration, show_in_channel FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    title = row[0] if row and row[0] else f"سجل الحضور — {get_arabic_date_string()}"
    duration = row[1] if row and row[1] is not None else 0
    show_in_channel = row[2] if row and row[2] is not None else 1

    poll_id = f"poll_{user_id}_{int(time.time())}"
    end_time = (time.time() + (duration * 60)) if duration > 0 else 0

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(create_colored_btn("✅ تسجيل الحضور [0]", callback_data=f"attend_{poll_id}", style="success"))
    keyboard.add(create_colored_btn("🤖 الانتقال للبوت", url=BOT_URL, style="primary"))

    msg_content = f"<b>📢 {html.escape(title)}</b>\n\n<i>اضغط على الزر أدناه لتسجيل الحضور:</i>"
    if show_in_channel == 1:
        msg_content += "\n\n<blockquote expandable><b>👥 الحضور (0):</b>\nلا توجد تسجيلات.</blockquote>"

    try:
        sent_msg = bot.send_message(real_channel_id, msg_content, parse_mode="HTML", reply_markup=keyboard)
        cursor.execute("INSERT OR REPLACE INTO saved_channels (user_id, channel_id, channel_title) VALUES (?, ?, ?)", (user_id, real_channel_id, c_title))
        cursor.execute("INSERT INTO channel_daily_posts (channel_id, date_str, posts_count) VALUES (?, ?, 1) ON CONFLICT(channel_id, date_str) DO UPDATE SET posts_count = posts_count + 1", (real_channel_id, today_str))
        cursor.execute("INSERT OR REPLACE INTO polls (poll_id, owner_id, count, title, end_time, is_closed, show_in_channel, channel_id, message_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (poll_id, user_id, 0, title, end_time, 0, show_in_channel, real_channel_id, sent_msg.message_id))
        conn.commit()
        conn.close()
        bot.send_message(chat_id_to_send, "✅ تم النشر بنجاح!", parse_mode="HTML")
    except Exception as e:
        conn.close()
        bot.send_message(chat_id_to_send, f"❌ فشل النشر: <code>{e}</code>", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "waiting_coupon_input")
def process_coupon_text_input(message):
    user_id = message.from_user.id
    code = message.text.strip()
    user_states.pop(user_id, None)

    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT points, max_uses, uses_count, is_closed FROM coupons WHERE code = ?", (code,))
    c_row = cursor.fetchone()
    if not c_row:
        bot.reply_to(message, "❌ الكود غير صحيح.", parse_mode="HTML")
        conn.close()
        return
    pts, max_uses, uses_count, is_closed = c_row
    if is_closed == 1 or uses_count >= max_uses:
        bot.reply_to(message, "⌛ الكوبون منتهي.", parse_mode="HTML")
        conn.close()
        return
    cursor.execute("SELECT * FROM coupon_uses WHERE code = ? AND user_id = ?", (code, user_id))
    if cursor.fetchone():
        bot.reply_to(message, "⚠️ استخدمت هذا الكوبون مسبقاً.", parse_mode="HTML")
        conn.close()
        return

    cursor.execute("INSERT INTO coupon_uses (code, user_id) VALUES (?, ?)", (code, user_id))
    cursor.execute("UPDATE coupons SET uses_count = uses_count + 1 WHERE code = ?", (code,))
    cursor.execute("INSERT INTO user_points (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points = points + ?", (user_id, pts, pts))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"🎉 تم شحن الكوبون وإضافة <code>{pts}</code> نقطة!", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "waiting_q_text")
def q_step_text(message):
    user_id = message.from_user.id
    user_states[user_id] = {"q_text": message.text.strip(), "step": "waiting_opt_a"}
    bot.reply_to(message, "📌 أرسل الخيار الأول (أ):", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and isinstance(user_states[message.from_user.id], dict) and user_states[message.from_user.id].get("step") == "waiting_opt_a")
def q_step_opt_a(message):
    user_id = message.from_user.id
    user_states[user_id]["opt_a"] = message.text.strip()
    user_states[user_id]["step"] = "waiting_opt_b"
    bot.reply_to(message, "📌 أرسل الخيار الثاني (ب):", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and isinstance(user_states[message.from_user.id], dict) and user_states[message.from_user.id].get("step") == "waiting_opt_b")
def q_step_opt_b(message):
    user_id = message.from_user.id
    user_states[user_id]["opt_b"] = message.text.strip()
    user_states[user_id]["step"] = "waiting_opt_c"
    bot.reply_to(message, "📌 أرسل الخيار الثالث (ج):", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and isinstance(user_states[message.from_user.id], dict) and user_states[message.from_user.id].get("step") == "waiting_opt_c")
def q_step_opt_c(message):
    user_id = message.from_user.id
    user_states[user_id]["opt_c"] = message.text.strip()
    user_states[user_id]["step"] = "waiting_opt_d"
    bot.reply_to(message, "📌 أرسل الخيار الرابع (د):", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and isinstance(user_states[message.from_user.id], dict) and user_states[message.from_user.id].get("step") == "waiting_opt_d")
def q_step_opt_d(message):
    user_id = message.from_user.id
    user_states[user_id]["opt_d"] = message.text.strip()
    user_states[user_id]["step"] = "waiting_correct_opt"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        create_colored_btn("أ", callback_data="q_correct_A", style="success"),
        create_colored_btn("ب", callback_data="q_correct_B", style="success"),
        create_colored_btn("ج", callback_data="q_correct_C", style="success"),
        create_colored_btn("د", callback_data="q_correct_D", style="success")
    )
    bot.reply_to(message, "🎯 اختر الإجابة الصحيحة:", parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("q_correct_"))
def q_step_correct_chosen(call):
    user_id = call.from_user.id
    if user_id not in user_states or not isinstance(user_states[user_id], dict):
        bot.answer_callback_query(call.id, "❌ انتهت الجلسة.", show_alert=True)
        return
    correct_opt = call.data.replace("q_correct_", "")
    user_states[user_id]["correct_opt"] = correct_opt
    user_states[user_id]["step"] = "waiting_q_channel"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🚀 أرسل معرف القناة لنشر السؤال:", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.from_user.id in user_states and isinstance(user_states[message.from_user.id], dict) and user_states[message.from_user.id].get("step") == "waiting_q_channel")
def q_step_publish(message):
    user_id = message.from_user.id
    channel_input = message.text.strip()
    q_data = user_states.pop(user_id, None)

    question_id = f"q_{user_id}_{int(time.time())}"
    q_text = q_data["q_text"]
    oa, ob, oc, od = q_data["opt_a"], q_data["opt_b"], q_data["opt_c"], q_data["opt_d"]
    correct_opt = q_data["correct_opt"]

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        create_colored_btn(f"أ) {oa}", callback_data=f"ans_{question_id}_A", style="primary"),
        create_colored_btn(f"ب) {ob}", callback_data=f"ans_{question_id}_B", style="primary"),
        create_colored_btn(f"ج) {oc}", callback_data=f"ans_{question_id}_C", style="primary"),
        create_colored_btn(f"د) {od}", callback_data=f"ans_{question_id}_D", style="primary")
    )
    keyboard.add(create_colored_btn("🤖 بوت", url=BOT_URL, style="primary"))

    q_msg_content = f"💡 <b>سؤال تفاعلي:</b>\n\n📌 <b>{html.escape(q_text)}</b>\n\n🔹 أ) {html.escape(oa)}\n🔹 ب) {html.escape(ob)}\n🔹 ج) {html.escape(oc)}\n🔹 د) {html.escape(od)}"

    try:
        sent_msg = bot.send_message(channel_input, q_msg_content, parse_mode="HTML", reply_markup=keyboard)
        conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO questions (question_id, owner_id, question_text, opt_a, opt_b, opt_c, opt_d, correct_opt, channel_id, message_id, is_closed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                       (question_id, user_id, q_text, oa, ob, oc, od, correct_opt, str(sent_msg.chat.id), sent_msg.message_id))
        conn.commit()
        conn.close()
        bot.reply_to(message, "✅ تم نشر السؤال بنجاح!", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ فشل النشر: <code>{e}</code>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("ans_"))
def handle_question_answer(call):
    if not check_forced_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "يجب الاشتراك أولاً ⛔", show_alert=True)
        send_subscription_required_message(call.message.chat.id)
        return

    raw_data = call.data[4:]
    last_underscore_idx = raw_data.rfind("_")
    if last_underscore_idx == -1:
        return
    question_id = raw_data[:last_underscore_idx]
    chosen_opt = raw_data[last_underscore_idx + 1:]
    user = call.from_user

    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT correct_opt, is_closed FROM questions WHERE question_id = ?", (question_id,))
    q_row = cursor.fetchone()
    if not q_row or q_row[1] == 1:
        bot.answer_callback_query(call.id, "❌ السؤال غير موجود أو مغلق.", show_alert=True)
        conn.close()
        return
    correct_opt = q_row[0]

    cursor.execute("SELECT * FROM question_answers WHERE question_id = ? AND user_id = ?", (question_id, user.id))
    if cursor.fetchone():
        bot.answer_callback_query(call.id, "⚠️ لقد أجبت مسبقاً!", show_alert=True)
        conn.close()
        return

    is_correct = 1 if chosen_opt == correct_opt else 0
    earned_points = 5 if is_correct else 0

    cursor.execute("INSERT INTO question_answers (question_id, user_id, selected_option, is_correct, earned_points) VALUES (?, ?, ?, ?, ?)", (question_id, user.id, chosen_opt, is_correct, earned_points))
    if is_correct:
        cursor.execute("INSERT INTO user_points (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points = points + ?", (user.id, earned_points, earned_points))
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, "✅ إجابة صحيحة! +5 نقاط" if is_correct else "❌ إجابة خاطئة!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "wizard_title_type")
def wizard_title_type(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        create_colored_btn("✏️ اسم يدوي", callback_data="w_title_manual", style="primary"),
        create_colored_btn("📅 اسم تلقائي بالتاريخ", callback_data="w_title_auto", style="success")
    )
    bot.send_message(call.message.chat.id, "📌 اختر طريقة التسمية:", parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "w_title_auto")
def wizard_title_auto(call):
    user_id = call.from_user.id
    auto_title = f"سجل الحضور — {get_arabic_date_string()}"
    conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO user_settings (user_id, title, duration, show_in_channel) VALUES (?, ?, 0, 1)", (user_id, auto_title))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "✅ تم الاعتماد!")
    show_channel_selection_menu(call.message.chat.id, user_id)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
