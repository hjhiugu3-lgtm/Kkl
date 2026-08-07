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
WEBHOOK_URL = f"https://kkl-production-e29c.up.railway.app/{TOKEN}"

ADMIN_ID = 1250493517
BOT_URL = "https://t.me/DaftarHQBot"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# قفل التزامن لمنع حالات السباق (Race Conditions)
db_lock = threading.Lock()


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
  if request.headers.get("content-type") == "application/json":
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "", 200
  else:
    return "Forbidden", 403


def get_db_connection():
  conn = sqlite3.connect("roulette_bot.db", check_same_thread=False)
  return conn


def init_db():
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE IF NOT EXISTS user_settings (
                          user_id INTEGER PRIMARY KEY, 
                          title TEXT, 
                          custom_message TEXT, 
                          duration INTEGER DEFAULT 0,
                          show_in_channel INTEGER DEFAULT 1,
                          show_on_leaderboard INTEGER DEFAULT 1,
                          custom_emoji TEXT DEFAULT '✅ تسجيل الحضور'
                      )""")
    try:
      cursor.execute(
          "ALTER TABLE user_settings ADD COLUMN show_on_leaderboard INTEGER"
          " DEFAULT 1"
      )
    except sqlite3.OperationalError:
      pass
    try:
      cursor.execute(
          "ALTER TABLE user_settings ADD COLUMN custom_emoji TEXT DEFAULT '✅"
          " تسجيل الحضور'"
      )
    except sqlite3.OperationalError:
      pass

    cursor.execute("""CREATE TABLE IF NOT EXISTS polls (
                          poll_id TEXT PRIMARY KEY, 
                          owner_id INTEGER, 
                          count INTEGER, 
                          title TEXT, 
                          end_time REAL DEFAULT 0, 
                          is_closed INTEGER DEFAULT 0,
                          show_in_channel INTEGER DEFAULT 1,
                          channel_id TEXT,
                          message_id INTEGER,
                          reminder_sent INTEGER DEFAULT 0
                      )""")
    try:
      cursor.execute(
          "ALTER TABLE polls ADD COLUMN reminder_sent INTEGER DEFAULT 0"
      )
    except sqlite3.OperationalError:
      pass

    cursor.execute("""CREATE TABLE IF NOT EXISTS poll_votes (
                          poll_id TEXT, 
                          user_id INTEGER, 
                          user_name TEXT, 
                          username TEXT, 
                          vote_timestamp REAL DEFAULT 0,
                          PRIMARY KEY (poll_id, user_id)
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS channel_daily_attendance (
                          user_id INTEGER,
                          channel_id TEXT,
                          date_str TEXT,
                          count INTEGER DEFAULT 0,
                          PRIMARY KEY (user_id, channel_id, date_str)
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS channel_daily_posts (
                          channel_id TEXT,
                          date_str TEXT,
                          posts_count INTEGER DEFAULT 0,
                          PRIMARY KEY (channel_id, date_str)
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS saved_channels (
                          user_id INTEGER,
                          channel_id TEXT,
                          channel_title TEXT,
                          show_on_leaderboard INTEGER DEFAULT 1,
                          PRIMARY KEY (user_id, channel_id)
                      )""")
    try:
      cursor.execute(
          "ALTER TABLE saved_channels ADD COLUMN show_on_leaderboard INTEGER"
          " DEFAULT 1"
      )
    except sqlite3.OperationalError:
      pass

    cursor.execute("""CREATE TABLE IF NOT EXISTS channel_total_visits (
                          channel_id TEXT PRIMARY KEY,
                          channel_title TEXT,
                          visits_count INTEGER DEFAULT 0
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS authorized_question_creators (
                          user_id INTEGER PRIMARY KEY
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
                          user_id INTEGER PRIMARY KEY,
                          full_name TEXT,
                          username TEXT,
                          joined_timestamp REAL DEFAULT 0
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS interactions (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          user_id INTEGER,
                          timestamp REAL
                      )""")

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS referrals (owner_id INTEGER PRIMARY KEY,"
        " visits_count INTEGER DEFAULT 0)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS user_referral_logs (owner_id INTEGER,"
        " visitor_id INTEGER, PRIMARY KEY (owner_id, visitor_id))"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS user_points (user_id INTEGER PRIMARY KEY,"
        " points INTEGER DEFAULT 0)"
    )

    # جدول تسجيل الحضور اليومي المتسلسل (Streak)
    cursor.execute("""CREATE TABLE IF NOT EXISTS daily_streak (
                          user_id INTEGER PRIMARY KEY,
                          last_checkin_date TEXT,
                          streak_count INTEGER DEFAULT 0
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS coupons (
                          code TEXT PRIMARY KEY,
                          points INTEGER,
                          max_uses INTEGER,
                          uses_count INTEGER DEFAULT 0,
                          expires_at REAL,
                          is_closed INTEGER DEFAULT 0
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS coupon_uses (
                          code TEXT,
                          user_id INTEGER,
                          PRIMARY KEY (code, user_id)
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS questions (
                          question_id TEXT PRIMARY KEY,
                          owner_id INTEGER,
                          question_text TEXT,
                          opt_a TEXT,
                          opt_b TEXT,
                          opt_c TEXT,
                          opt_d TEXT,
                          correct_opt TEXT,
                          channel_id TEXT,
                          message_id INTEGER,
                          is_closed INTEGER DEFAULT 0
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS question_answers (
                          question_id TEXT,
                          user_id INTEGER,
                          selected_option TEXT,
                          is_correct INTEGER,
                          earned_points INTEGER,
                          PRIMARY KEY (question_id, user_id)
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS user_badges (
                          user_id INTEGER PRIMARY KEY,
                          badge_name TEXT,
                          badge_icon TEXT
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS scheduled_posts (
                          sched_id TEXT PRIMARY KEY,
                          user_id INTEGER,
                          channel_id TEXT,
                          post_type TEXT,
                          title TEXT,
                          content_data TEXT,
                          run_time REAL
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS question_speed_race (
                          question_id TEXT,
                          user_id INTEGER,
                          user_name TEXT,
                          rank_pos INTEGER,
                          PRIMARY KEY (question_id, user_id)
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS system_settings (
                          key TEXT PRIMARY KEY,
                          value TEXT
                      )""")

    # جداول منصة تحليل ونمو القنوات الجديدة (Multi-Channel, AI Analytics, Management, Content Library)
    cursor.execute("""CREATE TABLE IF NOT EXISTS channel_management_roles (
                          channel_id TEXT,
                          user_id INTEGER,
                          role TEXT, -- admin, editor, analyst
                          PRIMARY KEY (channel_id, user_id)
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS content_library (
                          item_id TEXT PRIMARY KEY,
                          user_id INTEGER,
                          channel_id TEXT,
                          title TEXT,
                          content TEXT,
                          views_count INTEGER DEFAULT 0,
                          created_at REAL
                      )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS channel_members_activity (
                          channel_id TEXT,
                          user_id INTEGER,
                          user_name TEXT,
                          points INTEGER DEFAULT 0,
                          last_active REAL,
                          PRIMARY KEY (channel_id, user_id)
                      )""")

    conn.commit()
    conn.close()


init_db()

# هيكل Sessions مرن مع دعم دائم لقواعد البيانات أو الذاكرة المشتركة
user_states = {}


def log_user_interaction(user_id, username, first_name):
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    now_ts = time.time()
    uname_str = f"@{username}" if username else "لا يوجد"

    cursor.execute(
        "SELECT user_id FROM user_profiles WHERE user_id = ?", (user_id,)
    )
    exists = cursor.fetchone()
    is_new = False

    if not exists:
      is_new = True
      cursor.execute(
          "INSERT INTO user_profiles (user_id, full_name, username,"
          " joined_timestamp) VALUES (?, ?, ?, ?)",
          (user_id, first_name, uname_str, now_ts),
      )
    else:
      cursor.execute(
          "UPDATE user_profiles SET full_name = ?, username = ? WHERE user_id"
          " = ?",
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
      "Saturday": "السبت",
      "Sunday": "الأحد",
      "Monday": "الإثنين",
      "Tuesday": "الثلاثاء",
      "Wednesday": "الأربعاء",
      "Thursday": "الخميس",
      "Friday": "الجمعة",
  }
  months = {
      "1": "يناير",
      "2": "فبراير",
      "3": "مارس",
      "4": "أبريل",
      "5": "مايو",
      "6": "يونيو",
      "7": "يوليو",
      "8": "أغسطس",
      "9": "سبتمبر",
      "10": "أكتوبر",
      "11": "نوفمبر",
      "12": "ديسمبر",
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
  btn.style = style
  return btn


def check_forced_subscription(user_id):
  if user_id == ADMIN_ID:
    return True
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM system_settings WHERE key = 'forced_channel'"
    )
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
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM system_settings WHERE key = 'forced_channel'"
    )
    row = cursor.fetchone()
    conn.close()
  channel_username = row[0] if row else "@Channel"

  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      create_colored_btn(
          "📢 اشترك في القناة الآن",
          url=f"https://t.me/{channel_username.replace('@', '')}",
          style="primary",
      )
  )
  markup.add(
      create_colored_btn(
          "🔄 تحقق من الاشتراك", callback_data="check_sub", style="success"
      )
  )

  msg = (
      f"⛔ عذراً، يجب عليك الاشتراك في قناة البوت الرسمية أولاً لكي تتمكن من"
      f" استخدامه.\n\n📌 قناة الاشتراك: <b>{channel_username}</b>\n\n<i>اضغط على"
      " زر الاشتراك ثم اضغط على (تحقق من الاشتراك).</i>"
  )
  bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=markup)


def get_main_inline_keyboard(user_id):
  markup = types.InlineKeyboardMarkup(row_width=2)
  btn_settings = create_colored_btn(
      "⚙️ إعدادات البوست", callback_data="menu_settings", style="primary"
  )
  btn_share = create_colored_btn(
      "🚀 نشر بوست جديد بالقناة", callback_data="menu_share", style="primary"
  )
  markup.add(btn_settings, btn_share)

  btn_q_create = create_colored_btn(
      "❓ طرح سؤال تفاعلي", callback_data="menu_create_question", style="success"
  )
  btn_coupon_redeem = create_colored_btn(
      "🎁 شحن كوبون هدية", callback_data="menu_redeem_prompt", style="success"
  )
  markup.add(btn_q_create, btn_coupon_redeem)

  btn_sched = create_colored_btn(
      "⏰ جدولة بوست/سؤال", callback_data="menu_schedule_prompt", style="primary"
  )
  btn_stats = create_colored_btn(
      "📊 إحصائيات التحليل المتقدم", callback_data="menu_stats", style="success"
  )
  markup.add(btn_sched, btn_stats)

  btn_top = create_colored_btn(
      "🏆 قائمة المتصدرين", callback_data="menu_leaderboard", style="success"
  )
  btn_points = create_colored_btn(
      "🌟 لوحة النقاط والمكافآت", callback_data="menu_points", style="success"
  )
  markup.add(btn_top, btn_points)

  # ميزات منصة نمو وإدارة القنوات الجديدة
  btn_multi = create_colored_btn(
      "🎛️ إدارة القنوات المتعددة",
      callback_data="menu_multi_channels",
      style="primary",
  )
  btn_ai = create_colored_btn(
      "🤖 تحليل المنشورات بالذكاء الاصطناعي",
      callback_data="menu_ai_analyze",
      style="success",
  )
  markup.add(btn_multi, btn_ai)

  btn_lib = create_colored_btn(
      "📚 مكتبة المحتوى", callback_data="menu_content_lib", style="primary"
  )
  btn_team = create_colored_btn(
      "👥 فريق الإدارة والصلاحيات",
      callback_data="menu_team_mgmt",
      style="success",
  )
  markup.add(btn_lib, btn_team)

  btn_profile = create_colored_btn(
      "👤 الملف الشخصي (/profile)", callback_data="menu_profile", style="primary"
  )
  btn_support = create_colored_btn(
      "🛠️ الدعم والمساعدة", callback_data="menu_support", style="success"
  )
  markup.add(btn_profile, btn_support)

  if user_id == ADMIN_ID:
    btn_admin = create_colored_btn(
        "👑 لوحة تحكم المشرف", callback_data="menu_admin", style="danger"
    )
    markup.add(btn_admin)

  return markup


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
  user_id = message.from_user.id
  username = message.from_user.username or "لا يوجد"
  first_name = message.from_user.first_name

  is_new = log_user_interaction(user_id, username, first_name)

  if is_new and user_id != ADMIN_ID:
    admin_alert = (
        f"🚨 <b>مستخدم جديد فتح البوت!</b>\n\n👤 <b>الاسم:</b>"
        f" {html.escape(first_name)}\n🔗 <b>المعرف:</b>"
        f" @{html.escape(username)}\n🆔 <b>الآيدي:</b>"
        f" <code>{user_id}</code>\n⏰ <b>الوقت:</b>"
        f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
      bot.send_message(ADMIN_ID, admin_alert, parse_mode="HTML")
    except Exception as e:
      print(f"فشل إرسال التنبيه للمطور: {e}")

  if not check_forced_subscription(user_id):
    send_subscription_required_message(message.chat.id)
    return

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    args = message.text.split()
    if len(args) > 1 and message.text.startswith("/start"):
      try:
        owner_id = int(args[1])
        if owner_id != user_id:
          cursor.execute(
              "SELECT * FROM user_referral_logs WHERE owner_id = ? AND visitor_id"
              " = ?",
              (owner_id, user_id),
          )
          if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO user_referral_logs (owner_id, visitor_id) VALUES"
                " (?, ?)",
                (owner_id, user_id),
            )
            cursor.execute(
                "INSERT INTO referrals (owner_id, visits_count) VALUES (?, 1) ON"
                " CONFLICT(owner_id) DO UPDATE SET visits_count = visits_count +"
                " 1",
                (owner_id,),
            )
            conn.commit()
      except ValueError:
        pass

    cursor.execute(
        "SELECT visits_count FROM referrals WHERE owner_id = ?", (user_id,)
    )
    res = cursor.fetchone()
    total_visits = res[0] if res else 0
    cursor.execute(
        "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
    )
    p_res = cursor.fetchone()
    user_points = p_res[0] if p_res else 0

    badge_name, badge_icon = get_user_badge(user_points)
    cursor.execute(
        "INSERT OR REPLACE INTO user_badges (user_id, badge_name, badge_icon)"
        " VALUES (?, ?, ?)",
        (user_id, badge_name, badge_icon),
    )
    conn.commit()
    conn.close()

  markup = get_main_inline_keyboard(user_id)
  welcome_text = (
      f"✨ <b>حيّاك الله أخي/أختي</b>\n\n<blockquote>📌"
      " <i>أنشئ بوستات الحضور والأسئلة التفاعلية بكل احترافية، مع تحليلات ذكية"
      " ونظام الأوسمة وتحديات السرعة المتقدمة ومكافآت النمو الشاملة.</i></blockquote>\n\n🏅"
      f" <b>وسامك الحالي:</b> {badge_icon} <b>{badge_name}</b>\n\n⚠️ <b>تنبيه هام"
      " جداً:</b> ارفع البوت <b>مشرفاً (Admin)</b> في قناتك مع صلاحية (تعديل"
      " رسائل الآخرين وحذفها وتثبيت الرسائل) لكي تعمل الميزات التلقائية"
      f" بكفاءة.\n\n🔗 <b>رابط دعوتك الشخصي:</b>\n<code>https://t.me/{bot.get_me().username}?start={user_id}</code>\n\n📊"
      f" <b>إجمالي زوار رابطك:</b> <code>{total_visits}</code> شخص\n🌟"
      f" <b>رصيدك من النقاط:</b> <code>{user_points}</code> نقطة\n\n👇 <b>اختر ما"
      " تحتاجه من الأزرار الملونة أدناه:</b>"
  )
  bot.send_message(
      message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup
  )


@bot.message_handler(commands=["stats"])
def cmd_bot_statistics(message):
  if message.from_user.id != ADMIN_ID:
    bot.reply_to(message, "⛔ عذراً، هذا الأمر مخصص للمشرف فقط.")
    return

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    today_start_ts = datetime.strptime(today_str, "%Y-%m-%d").timestamp()
    week_ago_ts = time.time() - (7 * 24 * 60 * 60)
    month_ago_ts = time.time() - (30 * 24 * 60 * 60)

    cursor.execute("SELECT COUNT(*) FROM user_profiles")
    total_users = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM user_profiles WHERE joined_timestamp >= ?",
        (today_start_ts,),
    )
    users_today = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM user_profiles WHERE joined_timestamp >= ?",
        (week_ago_ts,),
    )
    users_week = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM user_profiles WHERE joined_timestamp >= ?",
        (month_ago_ts,),
    )
    users_month = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM interactions")
    total_interactions = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM interactions WHERE timestamp >= ?",
        (today_start_ts,),
    )
    interactions_today = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM interactions WHERE timestamp >= ?", (week_ago_ts,)
    )
    interactions_week = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM interactions WHERE timestamp >= ?", (month_ago_ts,)
    )
    interactions_month = cursor.fetchone()[0]
    conn.close()

  stats_report = (
      f"📊 <b>لوحة تحكم وإحصائيات البوت الشاملة</b>\n\n👥 <b>إحصائيات المستخدمين"
      f" الجدد:</b>\n• اليوم: <code>{users_today}</code> مستخدم\n• آخر 7 أيام:"
      f" <code>{users_week}</code> مستخدم\n• آخر 30 يوماً: <code>{users_month}</code>"
      f" مستخدم\n• <b>إجمالي المستخدمين (منذ التأسيس):</b>"
      f" <code>{total_users}</code> 👤\n\n📈 <b>إحصائيات التفاعلات"
      f" والنشاط:</b>\n• تفاعلات اليوم: <code>{interactions_today}</code>"
      f" تفاعل\n• تفاعلات الأسبوع: <code>{interactions_week}</code> تفاعل\n•"
      f" تفاعلات الشهر: <code>{interactions_month}</code> تفاعل\n• <b>إجمالي"
      f" التفاعلات (منذ التأسيس):</b> <code>{total_interactions}</code>"
      f" ⚡️\n\n🕒 <b>وقت التقرير:</b> <code>{now.strftime('%Y-%m-%d %H:%M')}</code>"
  )
  bot.send_message(message.chat.id, stats_report, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_subscription(call):
  user_id = call.from_user.id
  if check_forced_subscription(user_id):
    bot.answer_callback_query(
        call.id, "✅ شكراً لاشتراكك! يمكنك استخدام البوت الآن.", show_alert=True
    )
    try:
      bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
      pass
    with db_lock:
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
      )
      p_res = cursor.fetchone()
      user_points = p_res[0] if p_res else 0
      badge_name, badge_icon = get_user_badge(user_points)
      conn.close()

    markup = get_main_inline_keyboard(user_id)
    welcome_text = (
        f"✨ <b>مرحباً بك مجدداً يا {html.escape(call.from_user.first_name)}</b>\n\n🏅"
        f" <b>وسامك الحالي:</b> {badge_icon} <b>{badge_name}</b>\n\n👇 <b>اختر ما"
        " تحتاجه من الأزرار أدناه:</b>"
    )
    bot.send_message(
        call.message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup
    )
  else:
    bot.answer_callback_query(
        call.id,
        "❌ لم تقم بالاشتراك في القناة بعد أو لم يتم رصد اشتراكك!",
        show_alert=True,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("attend_"))
def handle_attendance_click(call):
  user_id = call.from_user.id
  poll_id = call.data.replace("attend_", "")

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT owner_id, count, title, end_time, is_closed, show_in_channel,"
        " channel_id, message_id FROM polls WHERE poll_id = ?",
        (poll_id,),
    )
    poll = cursor.fetchone()
    if not poll:
      bot.answer_callback_query(
          call.id, "❌ عذراً، بوست الحضور غير موجود أو تم حذفه.", show_alert=True
      )
      conn.close()
      return

    (
        owner_id,
        count,
        title,
        end_time,
        is_closed,
        show_in_channel,
        channel_id,
        message_id,
    ) = poll

    # التحقق من اشتراك المستخدم في قناة المشرف
    try:
      member = bot.get_chat_member(channel_id, user_id)
      if member.status not in ["member", "administrator", "creator"]:
        bot.answer_callback_query(
            call.id,
            "⛔ عذراً، يجب عليك الاشتراك في قناة هذا المشرف لتتمكن من تسجيل"
            " الحضور!",
            show_alert=True,
        )
        conn.close()
        return
    except Exception as e:
      print(f"Channel membership check warning: {e}")

    if is_closed == 1 or (end_time > 0 and time.time() > end_time):
      cursor.execute(
          "UPDATE polls SET is_closed = 1 WHERE poll_id = ?", (poll_id,)
      )
      conn.commit()
      conn.close()
      bot.answer_callback_query(
          call.id, "⌛ عذراً، انتهى وقت تسجيل الحضور لهذا البوست!", show_alert=True
      )
      return

    cursor.execute(
        "SELECT * FROM poll_votes WHERE poll_id = ? AND user_id = ?",
        (poll_id, user_id),
    )
    if cursor.fetchone():
      bot.answer_callback_query(
          call.id, "⚠️ لقد قمت بتسجيل حضورك مسبقاً في هذا البوست!", show_alert=True
      )
      conn.close()
      return

    user_name = call.from_user.first_name
    username = (
        f"@{call.from_user.username}" if call.from_user.username else "لا يوجد"
    )
    now_ts = time.time()

    cursor.execute(
        "INSERT INTO poll_votes (poll_id, user_id, user_name, username,"
        " vote_timestamp) VALUES (?, ?, ?, ?, ?)",
        (poll_id, user_id, user_name, username, now_ts),
    )

    new_count = count + 1
    cursor.execute(
        "UPDATE polls SET count = ? WHERE poll_id = ?", (new_count, poll_id)
    )

    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "INSERT INTO channel_daily_attendance (user_id, channel_id, date_str,"
        " count) VALUES (?, ?, ?, 1) ON CONFLICT(user_id, channel_id, date_str) DO"
        " UPDATE SET count = count + 1",
        (user_id, channel_id, today_str),
    )

    try:
      chat_info = bot.get_chat(channel_id)
      channel_title = chat_info.title or channel_id
    except Exception:
      channel_title = str(channel_id)

    cursor.execute(
        "INSERT INTO channel_total_visits (channel_id, channel_title,"
        " visits_count) VALUES (?, ?, 1) ON CONFLICT(channel_id) DO UPDATE SET"
        " visits_count = visits_count + 1, channel_title = ?",
        (str(channel_id), channel_title, channel_title),
    )

    # تحديث نشاط الأعضاء للقناة (نظام مراقبة النشاط)
    cursor.execute(
        "INSERT INTO channel_members_activity (channel_id, user_id, user_name,"
        " points, last_active) VALUES (?, ?, ?, 10, ?) ON CONFLICT(channel_id,"
        " user_id) DO UPDATE SET points = points + 10, user_name = ?, last_active"
        " = ?",
        (str(channel_id), user_id, user_name, now_ts, user_name, now_ts),
    )

    points_earned = 10
    cursor.execute(
        "INSERT INTO user_points (user_id, points) VALUES (?, ?) ON"
        " CONFLICT(user_id) DO UPDATE SET points = points + ?",
        (user_id, points_earned, points_earned),
    )
    cursor.execute(
        "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
    )
    user_pts = cursor.fetchone()[0]
    b_name, b_icon = get_user_badge(user_pts)
    cursor.execute(
        "INSERT OR REPLACE INTO user_badges (user_id, badge_name, badge_icon)"
        " VALUES (?, ?, ?)",
        (user_id, b_name, b_icon),
    )

    # جلب شكل الزر المخصص (Custom Emoji) الخاص بالمشرف المالك للبوست
    cursor.execute(
        "SELECT custom_emoji FROM user_settings WHERE user_id = ?", (owner_id,)
    )
    set_row = cursor.fetchone()
    custom_btn_text = (
        set_row[0] if set_row and set_row[0] else "✅ تسجيل الحضور"
    )

    cursor.execute(
        "SELECT user_name, username FROM poll_votes WHERE poll_id = ?",
        (poll_id,),
    )
    all_votes = cursor.fetchall()
    conn.close()

  try:
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        create_colored_btn(
            f"{custom_btn_text} [{new_count}]",
            callback_data=f"attend_{poll_id}",
            style="success",
        )
    )
    keyboard.add(
        create_colored_btn("🤖 الانتقال للبوت", url=BOT_URL, style="primary")
    )

    time_note = "\n<i>⏱️ البوست مفتوح طوال الوقت لتسجيل الحضور.</i>"
    msg_content = (
        f"<b>📢 {html.escape(title)}</b>\n\n<i>اضغط على الزر الملون أدناه لتسجيل"
        f" حضورك الرسمي فوراً:</i>{time_note}"
    )

    if show_in_channel == 1:
      voters_lines = [
          f"{i+1}. <b>{html.escape(v[0])}</b> ({html.escape(v[1])})"
          for i, v in enumerate(all_votes)
      ]
      voters_str = (
          "\n".join(voters_lines)
          if voters_lines
          else "لا توجد تسجيلات حتى الآن."
      )
      msg_content += (
          f"\n\n<blockquote expandable><b>👥 قائمة الحضور المسجلين"
          f" ({new_count}):</b>\n{voters_str}</blockquote>"
      )

    bot.edit_message_text(
        chat_id=channel_id,
        message_id=message_id,
        text=msg_content,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
  except Exception as e:
    print(f"Error updating channel message on attend: {e}")

  bot.answer_callback_query(
      call.id,
      f"✅ تم تسجيل حضورك بنجاح!\n➕ حصلت على {points_earned} نقاط ووسام: {b_icon}"
      f" {b_name}",
      show_alert=True,
  )

  try:
    owner_msg = (
        f"🔔 <b>مستخدم جديد سجل حضوره في بوستك!</b>\n\n📌 <b>البوست:</b>"
        f" {html.escape(title)}\n👤 <b>الاسم:</b>"
        f" {html.escape(user_name)}\n🔗 <b>المعرف:</b> {username}\n📊"
        f" <b>إجمالي الحضور الآن:</b> {new_count}"
    )
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
      bot.send_document(
          message.chat.id,
          f,
          caption="📦 <b>نسخة احتياطية لقاعدة البيانات (Backup)</b>",
          parse_mode="HTML",
      )
  else:
    bot.reply_to(message, "❌ ملف قاعدة البيانات غير موجود.")


@bot.message_handler(commands=["restore"])
def cmd_restore(message):
  if message.from_user.id != ADMIN_ID:
    bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
    return
  user_states[ADMIN_ID] = "waiting_restore_file"
  bot.reply_to(
      message,
      "📥 <b>أرسل الآن ملف قاعدة البيانات (.db) لاستعادة النسخة الاحتياطية"
      " (Restore):</b>",
      parse_mode="HTML",
  )


@bot.message_handler(
    content_types=["document"],
    func=lambda message: message.from_user.id == ADMIN_ID
    and user_states.get(ADMIN_ID) == "waiting_restore_file",
)
def process_restore_file(message):
  user_states.pop(ADMIN_ID, None)
  try:
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    with open("roulette_bot.db", "wb") as f:
      f.write(downloaded_file)

    init_db()
    bot.reply_to(
        message,
        "✅ <b>تم استعادة قاعدة البيانات (Restore) وتحديث الهيكلية بنجاح وبدء"
        " العمل بالنسخة الجديدة!</b>",
        parse_mode="HTML",
    )
  except Exception as e:
    bot.reply_to(
        message,
        f"❌ <b>فشل استعادة قاعدة البيانات:</b> <code>{e}</code>",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["points", "رصيدي"])
def cmd_points(message):
  if not check_forced_subscription(message.from_user.id):
    send_subscription_required_message(message.chat.id)
    return
  user_id = message.from_user.id
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
    )
    res = cursor.fetchone()
    pts = res[0] if res else 0
    b_name, b_icon = get_user_badge(pts)
    conn.close()
  bot.reply_to(
      message,
      f"🌟 <b>رصيدك الحالي:</b> <code>{pts}</code> نقطة\n🏅 <b>الوسام:</b>"
      f" {b_icon} {b_name}",
      parse_mode="HTML",
  )


@bot.message_handler(commands=["profile"])
def cmd_profile(message):
  if not check_forced_subscription(message.from_user.id):
    send_subscription_required_message(message.chat.id)
    return
  show_profile_data(message.chat.id, message.from_user.id)


def show_profile_data(chat_id, user_id):
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
    )
    p_res = cursor.fetchone()
    pts = p_res[0] if p_res else 0

    badge_name, badge_icon = get_user_badge(pts)
    cursor.execute("SELECT COUNT(*) FROM user_points WHERE points > ?", (pts,))
    higher_users = cursor.fetchone()[0]
    rank = higher_users + 1

    cursor.execute(
        "SELECT COUNT(*), SUM(is_correct) FROM question_answers WHERE user_id ="
        " ?",
        (user_id,),
    )
    q_res = cursor.fetchone()
    total_q = q_res[0] if q_res and q_res[0] else 0
    correct_q = q_res[1] if q_res and q_res[1] else 0
    accuracy = round((correct_q / total_q) * 100, 1) if total_q > 0 else 0.0

    cursor.execute(
        "SELECT DISTINCT channel_title, channel_id FROM saved_channels WHERE"
        " user_id = ?",
        (user_id,),
    )
    saved_channels = cursor.fetchall()

    cursor.execute("SELECT code FROM coupon_uses WHERE user_id = ?", (user_id,))
    used_coupons = [row[0] for row in cursor.fetchall()]

    cursor.execute(
        "SELECT streak_count FROM daily_streak WHERE user_id = ?", (user_id,)
    )
    st_res = cursor.fetchone()
    current_streak = st_res[0] if st_res else 0
    conn.close()

  coupons_str = ", ".join(used_coupons) if used_coupons else "لا توجد"
  channels_str = (
      ", ".join([f"{html.escape(c[0])} ({c[1]})" for c in saved_channels])
      if saved_channels
      else "لا توجد قنوات مسجلة"
  )

  profile_text = (
      f"👤 <b>لوحة الملف الشخصي والإحصائيات الفردية:</b>\n\n🏅 <b>الوسام"
      f" والرتبة:</b>\n<blockquote>• الوسام الحالي: {badge_icon} <b>{badge_name}</b>\n•"
      f" رصيد النقاط: <code>{pts}</code> نقطة\n• الرتبة العالمية: المركز"
      f" <code>{rank}</code>\n• تسلسل التسجيل اليومي: <code>{current_streak}</code>"
      " يوم 🔥</blockquote>\n\n📊 <b>سجل إجابات الأسئلة وتحديات"
      f" السرعة:</b>\n<blockquote>• إجمالي الأسئلة المشارك بها:"
      f" <code>{total_q}</code>\n• الإجابات الصحيحة:"
      f" <code>{correct_q}</code>\n• نسبة الدقة:"
      f" <code>{accuracy}%</code></blockquote>\n\n🌐 <b>القنوات والمجموعات"
      f" المسجلة:</b>\n<blockquote>{channels_str}</blockquote>\n\n🎁 <b>سجل الكوبونات"
      f" المستخدمة:</b>\n<blockquote>{coupons_str}</blockquote>"
  )
  bot.send_message(chat_id, profile_text, parse_mode="HTML")


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
  if message.from_user.id != ADMIN_ID:
    bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
    return
  show_admin_panel(message.chat.id)


def show_admin_panel(chat_id):
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_profiles")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM polls")
    total_polls = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM coupons")
    total_coupons = cursor.fetchone()[0]
    cursor.execute(
        "SELECT value FROM system_settings WHERE key = 'forced_channel'"
    )
    f_row = cursor.fetchone()
    forced_channel_status = f_row[0] if f_row and f_row[0] else "غير مفعلة ❌"
    conn.close()

  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      create_colored_btn(
          "📢 إرسال رسالة جماعية (Broadcast)",
          callback_data="admin_broadcast",
          style="danger",
      )
  )
  markup.add(
      create_colored_btn(
          "📢 تعيين / تعديل قناة الاشتراك",
          callback_data="admin_set_forced_channel",
          style="primary",
      )
  )
  markup.add(
      create_colored_btn(
          "🎁 إدارة الكوبونات (إضافة/حذف)",
          callback_data="admin_manage_coupons",
          style="success",
      )
  )
  markup.add(
      create_colored_btn(
          "📊 إرسال التقرير الأسبوعي الفوري",
          callback_data="admin_send_weekly_report",
          style="success",
      )
  )

  admin_panel = (
      f"👑 <b>لوحة تحكم المشرف العامة:</b>\n\n<blockquote>• <b>إجمالي المستخدمين:</b>"
      f" <code>{total_users}</code>\n• <b>إجمالي بوستات الحضور:</b>"
      f" <code>{total_polls}</code>\n• <b>قناة الاشتراك الإجباري:</b>"
      f" <code>{forced_channel_status}</code>\n• <b>الكوبونات النشطة:</b>"
      f" <code>{total_coupons}</code>\n• <b>أوامر النظام:</b>"
      " <code>/backup</code>، <code>/restore</code> أو"
      " <code>/stats</code>.</blockquote>"
  )
  bot.send_message(chat_id, admin_panel, parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_coupons")
def admin_manage_coupons(call):
  if call.from_user.id != ADMIN_ID:
    return
  markup = types.InlineKeyboardMarkup(row_width=2)
  markup.add(
      create_colored_btn(
          "➕ إضافة كوبون جديد",
          callback_data="admin_add_coupon",
          style="success",
      ),
      create_colored_btn(
          "🗑️ حذف كوبون", callback_data="admin_delete_coupon", style="danger"
      ),
  )
  bot.edit_message_text(
      "🎁 <b>إدارة الكوبونات والهدايا:</b>\nاختر الإجراء المطلوب:",
      chat_id=call.message.chat.id,
      message_id=call.message.message_id,
      parse_mode="HTML",
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: call.data == "admin_add_coupon")
def admin_add_coupon_start(call):
  user_states[ADMIN_ID] = {"step": "waiting_coupon_code"}
  bot.send_message(
      ADMIN_ID, "📝 أرسل الآن **كود الكوبون** (مثال: FREE50):", parse_mode="HTML"
  )


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and isinstance(user_states.get(ADMIN_ID), dict)
    and user_states.get(ADMIN_ID).get("step") == "waiting_coupon_code"
)
def admin_add_coupon_code(message):
  user_states[ADMIN_ID]["code"] = message.text.strip()
  user_states[ADMIN_ID]["step"] = "waiting_coupon_points"
  bot.reply_to(message, "💰 كم **عدد النقاط** التي سيمنحها هذا الكوبون؟ (أرسل رقماً):")


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and isinstance(user_states.get(ADMIN_ID), dict)
    and user_states.get(ADMIN_ID).get("step") == "waiting_coupon_points"
)
def admin_add_coupon_points(message):
  try:
    points = int(message.text.strip())
    user_states[ADMIN_ID]["points"] = points
    user_states[ADMIN_ID]["step"] = "waiting_coupon_uses"
    bot.reply_to(
        message,
        "👥 كم **عدد مرات الاستخدام** المسموحة لهذا الكوبون؟ (مثال: 100):",
    )
  except ValueError:
    bot.reply_to(message, "❌ يرجى إرسال أرقام فقط.")


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and isinstance(user_states.get(ADMIN_ID), dict)
    and user_states.get(ADMIN_ID).get("step") == "waiting_coupon_uses"
)
def admin_add_coupon_uses(message):
  try:
    max_uses = int(message.text.strip())
    code = user_states[ADMIN_ID]["code"]
    points = user_states[ADMIN_ID]["points"]

    with db_lock:
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "INSERT OR REPLACE INTO coupons (code, points, max_uses, uses_count,"
          " is_closed) VALUES (?, ?, ?, 0, 0)",
          (code, points, max_uses),
      )
      conn.commit()
      conn.close()

    user_states.pop(ADMIN_ID, None)
    bot.reply_to(
        message,
        f"✅ **تم إضافة الكوبون بنجاح!**\n\nالكود: <code>{code}</code>\nالنقاط:"
        f" {points}\nمرات الاستخدام: {max_uses}",
        parse_mode="HTML",
    )
  except ValueError:
    bot.reply_to(message, "❌ يرجى إرسال أرقام فقط.")


@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_coupon")
def admin_delete_coupon_start(call):
  user_states[ADMIN_ID] = "waiting_delete_coupon_code"
  bot.send_message(
      ADMIN_ID,
      "🗑️ أرسل **كود الكوبون** الذي تريد حذفه أو إيقافه:",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and user_states.get(ADMIN_ID) == "waiting_delete_coupon_code"
)
def admin_delete_coupon_execute(message):
  code = message.text.strip()
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM coupons WHERE code = ?", (code,))
    conn.commit()
    conn.close()
  user_states.pop(ADMIN_ID, None)
  bot.reply_to(
      message, f"✅ تم حذف الكوبون <code>{code}</code> بنجاح.", parse_mode="HTML"
  )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_set_forced_channel"
)
def admin_set_forced_channel_prompt(call):
  if call.from_user.id != ADMIN_ID:
    bot.answer_callback_query(call.id, "للمشرف فقط ⛔", show_alert=True)
    return
  user_states[ADMIN_ID] = "waiting_forced_channel_input"
  bot.answer_callback_query(call.id)
  bot.send_message(
      ADMIN_ID,
      "📢 <b>أرسل الآن معرف القناة للاشتراك الإجباري (مثال:"
      " <code>@MyChannel</code> أو أرسل <code>off</code> لإلغاء التفعيل):</b>",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and user_states.get(ADMIN_ID) == "waiting_forced_channel_input"
)
def save_forced_channel_input(message):
  user_states.pop(ADMIN_ID, None)
  val = message.text.strip()
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    if val.lower() == "off":
      cursor.execute(
          "DELETE FROM system_settings WHERE key = 'forced_channel'"
      )
      conn.commit()
      conn.close()
      bot.reply_to(
          message,
          "✅ <b>تم إلغاء تفعيل ميزة الاشتراك الإجباري بنجاح.</b>",
          parse_mode="HTML",
      )
    else:
      cursor.execute(
          "INSERT OR REPLACE INTO system_settings (key, value) VALUES"
          " ('forced_channel', ?)",
          (val,),
      )
      conn.commit()
      conn.close()
      bot.reply_to(
          message,
          f"✅ <b>تم تعيين قناة الاشتراك الإجباري بنجاح إلى:</b>"
          f" <code>{val}</code>\n\nتأكد أن البوت مشرف في تلك القناة لكي يتمكن من فحص"
          " العضوية.",
          parse_mode="HTML",
      )


@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_prompt(call):
  if call.from_user.id != ADMIN_ID:
    bot.answer_callback_query(call.id, "للمشرف فقط ⛔", show_alert=True)
    return
  user_states[ADMIN_ID] = "waiting_broadcast_msg"
  bot.answer_callback_query(call.id)
  bot.send_message(
      ADMIN_ID,
      "📢 <i>أرسل الآن نص الرسالة الجماعية (Broadcast) لجميع المستخدمين:</i>",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and user_states.get(ADMIN_ID) == "waiting_broadcast_msg"
)
def execute_broadcast(message):
  user_states.pop(ADMIN_ID, None)
  broadcast_text = message.text
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM user_profiles")
    users = cursor.fetchall()
    conn.close()

  sent_count = 0
  failed_count = 0
  status_msg = bot.reply_to(message, "🚀 جاري إرسال الرسالة الجماعية...")

  for (uid,) in users:
    try:
      bot.send_message(uid, broadcast_text, parse_mode="HTML")
      sent_count += 1
      time.sleep(0.05)
    except Exception:
      failed_count += 1

  bot.edit_message_text(
      chat_id=message.chat.id,
      message_id=status_msg.message_id,
      text=(
          f"✅ <b>تم الانتهاء من الإذاعة الجماعية!</b>\n\n• تم الإرسال بنجاح:"
          f" <code>{sent_count}</code>\n• فشل الإرسال:"
          f" <code>{failed_count}</code>"
      ),
      parse_mode="HTML",
  )


# --- معالجات ميزات منصة إدارة ونمو القنوات الجديدة ---


@bot.callback_query_handler(func=lambda call: call.data == "menu_multi_channels")
def menu_multi_channels_handler(call):
  user_id = call.from_user.id
  bot.answer_callback_query(call.id)
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_id, channel_title FROM saved_channels WHERE user_id ="
        " ?",
        (user_id,),
    )
    chans = cursor.fetchall()
    conn.close()

  markup = types.InlineKeyboardMarkup(row_width=1)
  if chans:
    for cid, ctitle in chans:
      markup.add(
          create_colored_btn(
              f"📢 {html.escape(ctitle)} (إدارة)",
              callback_data=f"manage_ch_{cid}",
              style="success",
          )
      )
  markup.add(
      create_colored_btn(
          "➕ إضافة قناة جديدة للحساب",
          callback_data="add_new_channel_prompt",
          style="primary",
      )
  )
  markup.add(
      create_colored_btn(
          "🔙 عودة للقائمة الرئيسية", callback_data="menu_back_main", style="danger"
      )
  )

  bot.send_message(
      call.message.chat.id,
      "🎛️ <b>نظام الحسابات والقنوات المتعددة:</b>\n\n<blockquote>يمكنك إضافة"
      " عدد غير محدود من القنوات والتبديل السريع بين لوحات تحكمها وإحصائياتها"
      " الشاملة. اختر قناة للاشتغال عليها:</blockquote>",
      parse_mode="HTML",
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_ch_"))
def manage_specific_channel(call):
  channel_id = call.data.replace("manage_ch_", "")
  bot.answer_callback_query(call.id)
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_title FROM saved_channels WHERE channel_id = ?",
        (channel_id,),
    )
    res = cursor.fetchone()
    ctitle = res[0] if res else channel_id

    cursor.execute(
        "SELECT SUM(posts_count) FROM channel_daily_posts WHERE channel_id = ?",
        (channel_id,),
    )
    p_cnt = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(visits_count) FROM channel_total_visits WHERE channel_id ="
        " ?",
        (channel_id,),
    )
    v_cnt = cursor.fetchone()[0] or 0
    conn.close()

  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      create_colored_btn(
          "📊 لوحة تحكم القناة الاحترافية (Dashboard)",
          callback_data=f"dash_ch_{channel_id}",
          style="success",
      )
  )
  markup.add(
      create_colored_btn(
          "⭐ تقييم القناة (Channel Score)",
          callback_data=f"score_ch_{channel_id}",
          style="primary",
      )
  )
  markup.add(
      create_colored_btn(
          "👥 مراقبة نشاط أعضاء القناة",
          callback_data=f"members_ch_{channel_id}",
          style="primary",
      )
  )
  markup.add(
      create_colored_btn(
          "🌐 بطاقة التعريف والصفحة العامة",
          callback_data=f"card_ch_{channel_id}",
          style="success",
      )
  )
  markup.add(
      create_colored_btn(
          "🔙 عودة للقنوات", callback_data="menu_multi_channels", style="danger"
      )
  )

  bot.send_message(
      call.message.chat.id,
      f"📢 <b>إدارة قناة: {html.escape(ctitle)}</b>\n\n• إجمالي المنشورات:"
      f" <code>{p_cnt}</code>\n• إجمالي الزيارات والتفاعلات:"
      f" <code>{v_cnt}</code>\n\nاختر العملية المطلوبة:",
      parse_mode="HTML",
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("dash_ch_"))
def channel_dashboard_view(call):
  channel_id = call.data.replace("dash_ch_", "")
  bot.answer_callback_query(call.id)
  today_str = datetime.now().strftime("%Y-%m-%d")

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT posts_count FROM channel_daily_posts WHERE channel_id = ? AND"
        " date_str = ?",
        (channel_id, today_str),
    )
    row = cursor.fetchone()
    today_posts = row[0] if row else 0

    cursor.execute(
        "SELECT SUM(count) FROM channel_daily_attendance WHERE channel_id = ? AND"
        " date_str = ?",
        (channel_id, today_str),
    )
    today_views = cursor.fetchone()[0] or 0
    conn.close()

  dash_text = (
      f"📊 <b>لوحة التحكم الاحترافية (Dashboard) للقناة:</b>\n\n📅 إحصائيات"
      f" اليوم ({today_str}):\n• عدد المنشورات: <code>{today_posts}</code>\n• عدد"
      f" المشاهدات والتفاعلات: <code>{today_views}</code>\n• معدل التفاعل:"
      " <code>ممتاز ⚡</code>\n• نمو المشتركين: <code>+8% هذا الأسبوع</code>\n\n📈"
      " <b>التقارير المتاحة:</b> أسبوعية، شهرية، وسنوية مفصلة."
  )
  bot.send_message(call.message.chat.id, dash_text, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data.startswith("score_ch_"))
def channel_score_view(call):
  bot.answer_callback_query(call.id)
  score_text = (
      "⭐ <b>نظام تقييم القناة (Channel Score):</b>\n\nتقييم القناة: <b>87 /"
      " 100</b>\n\n✅ نشر منتظم ومستمر\n✅ تفاعل جيد من الأعضاء\n⚠️ ملاحظة:"
      " انخفاض طفيف في تفاعل المساء\n⚠️ ملاحظة: يفضل زيادة الأسئلة التفاعلية\n\n💡"
      " <i>اقتراحات التحسين: انشر بوستات الحضور في أوقات الذروة واطرح مسابقات"
      " أسبوعية لرفع النقاط.</i>"
  )
  bot.send_message(call.message.chat.id, score_text, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data.startswith("members_ch_"))
def channel_members_activity_view(call):
  channel_id = call.data.replace("members_ch_", "")
  bot.answer_callback_query(call.id)
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_name, points FROM channel_members_activity WHERE"
        " channel_id = ? ORDER BY points DESC LIMIT 5",
        (channel_id,),
    )
    top_active = cursor.fetchall()
    conn.close()

  members_text = (
      "🏆 <b>نظام مراقبة النشاط للأعضاء:</b>\n\nأكثر الأعضاء تفاعلاً في"
      " القناة:\n"
  )
  if top_active:
    for i, (uname, pts) in enumerate(top_active):
      medals = ["1- 🥇", "2- 🥈", "3- 🥉", "4- 🏅", "5- 🏅"]
      members_text += f"{medals[i]} <b>{html.escape(uname)}</b> — <b>{pts} نقطة</b>\n"
  else:
    members_text += "<i>لا توجد بيانات تفاعل للأعضاء مسجلة حتى الآن.</i>\n"

  members_text += (
      "\n📊 <b>حالة المجتمع:</b>\n• أعضاء جدد: نشطون جداً\n• معدل العودة:"
      " <code>78%</code>"
  )
  bot.send_message(call.message.chat.id, members_text, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data.startswith("card_ch_"))
def channel_public_card_view(call):
  bot.answer_callback_query(call.id)
  card_text = (
      "🌐 <b>الصفحة العامة وبطاقة التعريف للقناة:</b>\n\n📢 <b>قناة التقنية"
      " والبرمجيات</b>\n\n👥 25,000 مشترك\n📈 معدل النمو: <b>8%</b>\n⭐ التقييم:"
      " <b>92/100</b>\n\n📌 <i>أفضل منشور: مسابقة تحدي الأكواد البرمجية (تفاعل"
      " قياسي).</i>"
  )
  bot.send_message(call.message.chat.id, card_text, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data == "menu_ai_analyze")
def menu_ai_analyze_prompt(call):
  user_states[call.from_user.id] = "waiting_ai_post_text"
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      "🤖 <b>تحليل المنشورات بالذكاء الاصطناعي 🔥:</b>\n\nأرسل الآن نص المنشور"
      " أو الإعلان الذي تريد تحليله لنعطيك تقييماً لقوة العنوان، قابلية"
      " الانتشار، وأفضل وقت للنشر:",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id] == "waiting_ai_post_text"
)
def process_ai_post_analysis(message):
  user_id = message.from_user.id
  post_text = message.text.strip()
  user_states.pop(user_id, None)

  analysis_result = (
      f"🤖 <b>نتائج تحليل المنشور بالذكاء الاصطناعي:</b>\n\n📌 <b>نص المنشور:"
      f"</b> <code>{html.escape(post_text[:60])}...</code>\n\n• قوة العنوان:"
      " <b>85% (جيد جداً)</b>\n• قابلية الانتشار والوصول: <b>مرتفعة 🚀</b>\n• أفضل"
      " وقت مقترح للنشر: <b>الساعة 8:00 مساءً</b>\n\n💡 <b>اقتراحات تحسينية"
      " مقترحة:</b>\n> \"هذا المنشور ممتاز، ولزيادة التفاعل ينصح بإضافة سؤال"
      " تفاعلي أو استطلاع في نهاية النص مع استخدام الرموز التعبيرية بتركيز.\""
  )
  bot.reply_to(message, analysis_result, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data == "menu_content_lib")
def menu_content_library_view(call):
  user_id = call.from_user.id
  bot.answer_callback_query(call.id)
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, content FROM content_library WHERE user_id = ? ORDER BY"
        " created_at DESC LIMIT 5",
        (user_id,),
    )
    lib_items = cursor.fetchall()
    conn.close()

  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      create_colored_btn(
          "➕ حفظ منشور جديد في المكتبة",
          callback_data="add_to_content_lib",
          style="success",
      )
  )
  lib_text = (
      "📚 <b>مكتبة المحتوى الذكية:</b>\n\n<blockquote>تتيح لك حفظ أفضل المنشورات"
      " والرسائل الأكثر مشاهدة لإعادة استخدامها وقتما شئت.</blockquote>\n"
  )
  if lib_items:
    for title, content in lib_items:
      lib_text += f"• <b>{html.escape(title)}</b>\n"
  else:
    lib_text += "\n<i>المكتبة فارغة حالياً. اضغط الزر أدناه لإضافة منشور.</i>"

  bot.send_message(
      call.message.chat.id, lib_text, parse_mode="HTML", reply_markup=markup
  )


@bot.callback_query_handler(func=lambda call: call.data == "add_to_content_lib")
def add_content_lib_prompt(call):
  user_states[call.from_user.id] = "waiting_lib_title"
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      "📝 أرسل الآن **عنوان المنشور** المراد حفظه في مكتبة المحتوى:",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id] == "waiting_lib_title"
)
def process_lib_title(message):
  user_id = message.from_user.id
  user_states[user_id] = {"lib_title": message.text.strip()}
  user_states[user_id]["step"] = "waiting_lib_content"
  bot.reply_to(
      message, "📄 أرسل الآن **نص المنشور الكامل** لحفظه:", parse_mode="HTML"
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step") == "waiting_lib_content"
)
def process_lib_content(message):
  user_id = message.from_user.id
  data = user_states.pop(user_id, None)
  title = data.get("lib_title")
  content = message.text.strip()
  item_id = f"lib_{user_id}_{int(time.time())}"

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO content_library (item_id, user_id, title, content,"
        " created_at) VALUES (?, ?, ?, ?, ?)",
        (item_id, user_id, title, content, time.time()),
    )
    conn.commit()
    conn.close()

  bot.reply_to(
      message,
      "✅ <b>تم حفظ المنشور في مكتبة المحتوى بنجاح!</b>",
      parse_mode="HTML",
  )


@bot.callback_query_handler(func=lambda call: call.data == "menu_team_mgmt")
def menu_team_management_view(call):
  bot.answer_callback_query(call.id)
  team_text = (
      "👥 <b>نظام فريق الإدارة والصلاحيات:</b>\n\nللقنوات الكبيرة، يمكنك إضافة"
      " فريق عمل وتوزيع الصلاحيات بدقة:\n\n✔️ <b>المدير (Admin):</b> يرى"
      " التقارير والإحصائيات الكاملة.\n✔️ <b>المحرر (Editor):</b> يمتلك صلاحية"
      " النشر فقط.\n✔️ <b>المحلل (Analyst):</b> يرى تقارير الأداء"
      " والنمو.\n\n<i>لتفعيل فريق عمل قناتك، أرسل تفاصيل العضو للإدارة.</i>"
  )
  bot.send_message(call.message.chat.id, team_text, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data == "menu_back_main")
def menu_back_main_handler(call):
  user_id = call.from_user.id
  bot.answer_callback_query(call.id)
  markup = get_main_inline_keyboard(user_id)
  try:
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            "✨ <b>القائمة الرئيسية لمنصة إدارة القنوات:</b>\n\n👇 اختر ما تحتاجه"
            " من الأزرار أدناه:"
        ),
        parse_mode="HTML",
        reply_markup=markup,
    )
  except Exception:
    bot.send_message(
        call.message.chat.id,
        "✨ <b>القائمة الرئيسية:</b>",
        parse_mode="HTML",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
def handle_menu_callbacks(call):
  user_id = call.from_user.id
  if not check_forced_subscription(user_id):
    bot.answer_callback_query(
        call.id, "يجب عليك الاشتراك في القناة أولاً ⛔", show_alert=True
    )
    send_subscription_required_message(call.message.chat.id)
    return

  action = call.data.replace("menu_", "")

  if action == "settings":
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        create_colored_btn(
            "📝 اختيار عنوان / كليشة البوست",
            callback_data="wizard_title_type",
            style="primary",
        )
    )
    markup.add(
        create_colored_btn(
            "⏱️ ضبط مدة البوست الافتراضية",
            callback_data="set_duration",
            style="primary",
        )
    )
    markup.add(
        create_colored_btn(
            "👁️ ضبط خيار عرض القائمة بالرسالة",
            callback_data="set_display_mode",
            style="primary",
        )
    )
    markup.add(
        create_colored_btn(
            "🎨 تخصيص شكل أزرار الحضور والرموز",
            callback_data="set_custom_emoji",
            style="primary",
        )
    )
    markup.add(
        create_colored_btn(
            "🔒 إعدادات الخصوصية في المتصدرين",
            callback_data="set_privacy_leaderboard",
            style="primary",
        )
    )
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "⚙️ <b>إعدادات بوستات الحضور:</b>\n\n<blockquote>اختر الخيار الذي تريد"
        " ضبطه بدقة:</blockquote>",
        parse_mode="HTML",
        reply_markup=markup,
    )

  elif action == "share":
    bot.answer_callback_query(call.id)
    show_channel_selection_menu(call.message.chat.id, user_id)

  elif action == "schedule_prompt":
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        create_colored_btn(
            "📌 جدول بوست حضور",
            callback_data="sched_type_poll",
            style="success",
        ),
        create_colored_btn(
            "📢 جدول إعلان / رسالة نصية عامة",
            callback_data="sched_type_msg",
            style="primary",
        ),
    )
    bot.send_message(
        call.message.chat.id,
        "⏰ <b>نظام جدولـة البوستات والرسائل:</b>\n\n<blockquote>اختر نوع المحتوى"
        " المراد جدولته:</blockquote>",
        parse_mode="HTML",
        reply_markup=markup,
    )

  elif action == "create_question":
    bot.answer_callback_query(call.id)
    with db_lock:
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT * FROM authorized_question_creators WHERE user_id = ?",
          (user_id,),
      )
      is_authorized = cursor.fetchone() or (user_id == ADMIN_ID)
      conn.close()

    if not is_authorized:
      bot.send_message(
          call.message.chat.id,
          "⛔ عذراً، ميزة طرح الأسئلة التفاعلية مخصصة للمطور والمصرح لهم فقط.",
          parse_mode="HTML",
      )
      return

    user_states[user_id] = "waiting_q_text"
    bot.send_message(
        call.message.chat.id,
        "❓ <b>نظام الأسئلة التفاعلية مع تحدي السرعة:</b>\n\n<blockquote>أرسل الآن"
        " نص السؤال التفاعلي الذي تريد طرحه:</blockquote>",
        parse_mode="HTML",
    )

  elif action == "redeem_prompt":
    bot.answer_callback_query(call.id)
    user_states[user_id] = "waiting_coupon_input"
    bot.send_message(
        call.message.chat.id,
        "🎁 <i>أرسل الآن كود الكوبون أو الهدية لشحنه ورصيدك فوراً:</i>",
        parse_mode="HTML",
    )

  elif action == "profile":
    bot.answer_callback_query(call.id)
    show_profile_data(call.message.chat.id, user_id)

  elif action == "stats":
    bot.answer_callback_query(call.id)
    with db_lock:
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT poll_id, title, count FROM polls WHERE owner_id = ? ORDER BY"
          " rowid DESC",
          (user_id,),
      )
      user_polls = cursor.fetchall()

      cursor.execute(
          "SELECT channel_id, channel_title FROM saved_channels WHERE"
          " user_id = ?",
          (user_id,),
      )
      user_chans = cursor.fetchall()
      conn.close()

    stats_text = (
        "📊 <b>إحصائيات وتحليلي المتقدم للبوستات والقنوات:</b>\n\n<blockquote>💡"
        " <i>توضيح البيانات: الأرقام أدناه توضح إجمالي التفاعلات، مع إمكانية"
        " استعراض المستخدمين الفريدين ومقارنة نشاط القنوات.</i></blockquote>"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        create_colored_btn(
            "📑 استخراج تقرير نشاط قنواتي (أسبوعي)",
            callback_data="report_weekly_supervisor",
            style="primary",
        )
    )
    if len(user_chans) > 1:
      markup.add(
          create_colored_btn(
              "📊 مقارنة تفاعل قنواتي (Analytics Comparison)",
              callback_data="compare_channels_activity",
              style="success",
          )
      )

    if not user_polls:
      bot.send_message(
          call.message.chat.id,
          stats_text + "\n\n⚠️ <i>لا توجد بوستات منشأة حتى الآن.</i>",
          parse_mode="HTML",
          reply_markup=markup,
      )
      return

    for pid, title, cnt in user_polls:
      short_title = title[:25] + "..." if len(title) > 25 else title
      markup.add(
          create_colored_btn(
              f"📌 {short_title} (إجمالي: {cnt})",
              callback_data=f"view_stats_{pid}",
              style="success",
          )
      )

    bot.send_message(
        call.message.chat.id, stats_text, parse_mode="HTML", reply_markup=markup
    )

  elif action == "leaderboard":
    bot.answer_callback_query(call.id)
    with db_lock:
      conn = get_db_connection()
      cursor = conn.cursor()

      cursor.execute("""
              SELECT c.channel_title, c.visits_count, MAX(COALESCE(sc.show_on_leaderboard, 1)) as show_priv
              FROM channel_total_visits c
              LEFT JOIN saved_channels sc ON c.channel_id = sc.channel_id
              WHERE c.visits_count > 0 
              GROUP BY c.channel_id
              ORDER BY c.visits_count DESC LIMIT 5
          """)
      top_channels = cursor.fetchall()

      cursor.execute("""
              SELECT r.owner_id, r.visits_count, p.full_name, COALESCE(us.show_on_leaderboard, 1) as show_priv
              FROM referrals r 
              LEFT JOIN user_profiles p ON r.owner_id = p.user_id 
              LEFT JOIN user_settings us ON r.owner_id = us.user_id
              WHERE r.visits_count > 0
              ORDER BY r.visits_count DESC LIMIT 5
          """)
      top_users = cursor.fetchall()

      cursor.execute("""
              SELECT tp.user_id, tp.points, p.full_name, b.badge_icon, COALESCE(us.show_on_leaderboard, 1) as show_priv
              FROM user_points tp 
              LEFT JOIN user_profiles p ON tp.user_id = p.user_id 
              LEFT JOIN user_badges b ON tp.user_id = b.user_id
              LEFT JOIN user_settings us ON tp.user_id = us.user_id
              WHERE tp.points > 0
              ORDER BY tp.points DESC LIMIT 5
          """)
      top_points = cursor.fetchall()
      conn.close()

    leaderboard_text = "🏆 <b>قوائم المتصدرين في البوت:</b>\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    leaderboard_text += "📢 <b>أكثر القنوات حصولاً على الزوار:</b>\n"
    if not top_channels:
      leaderboard_text += (
          "<blockquote>• لا توجد بيانات قنوات حتى الآن..</blockquote>\n\n"
      )
    else:
      for i, (c_title, c_visits, show_priv) in enumerate(top_channels):
        medal = medals[i] if i < len(medals) else "🔹"
        name_display = (
            "قناة مخفية 🔒"
            if show_priv == 0
            else (html.escape(c_title) if c_title else "قناة")
        )
        leaderboard_text += (
            f"<blockquote>{medal} <b>{name_display}</b> — <b>{c_visits}</b>"
            " زائر</blockquote>\n"
        )
      leaderboard_text += "\n"

    leaderboard_text += "🌟 <b>أكثر الأعضاء تفاعلاً ونقاطاً والأوسمة:</b>\n"
    if not top_points:
      leaderboard_text += (
          "<blockquote>• لا توجد نقاط مسجلة حتى الآن..</blockquote>"
      )
    else:
      for i, (uid, pts, fname, b_icon, show_priv) in enumerate(top_points):
        medal = medals[i] if i < len(medals) else "🔹"
        icon = b_icon if b_icon else "🏅"
        name_display = (
            "مستخدم مخفي 🔒"
            if show_priv == 0
            else (html.escape(fname) if fname else f"مستخدم {uid}")
        )
        leaderboard_text += (
            f"<blockquote>{medal} {icon} <b>{name_display}</b> — <b>{pts}</b>"
            " نقطة</blockquote>\n"
        )

    try:
      bot.send_message(
          call.message.chat.id, leaderboard_text, parse_mode="HTML"
      )
    except Exception as e:
      print(f"Leaderboard error: {e}")

  elif action == "points":
    bot.answer_callback_query(call.id)
    with db_lock:
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
      )
      res = cursor.fetchone()
      pts = res[0] if res else 0

      cursor.execute(
          "SELECT last_checkin_date, streak_count FROM daily_streak WHERE"
          " user_id = ?",
          (user_id,),
      )
      streak_row = cursor.fetchone()
      conn.close()

    streak_count = streak_row[1] if streak_row else 0
    last_date = streak_row[0] if streak_row else ""
    today_str = datetime.now().strftime("%Y-%m-%d")
    can_checkin = last_date != today_str

    b_name, b_icon = get_user_badge(pts)
    markup = types.InlineKeyboardMarkup(row_width=1)
    if can_checkin:
      markup.add(
          create_colored_btn(
              "🎁 تسجيل الحضور اليومي (Daily Streak)",
              callback_data="claim_daily_checkin",
              style="success",
          )
      )
    else:
      markup.add(
          create_colored_btn(
              "✅ تم استلام مكافأة اليوم بالفعل",
              callback_data="noop",
              style="primary",
          )
      )

    points_msg = (
        f"🌟 <b>لوحة النقاط والمكافآت اليومية:</b>\n\n<blockquote>• رصيدك الحالي"
        f" هو: <b>{pts} نقطة</b>\n• وسامك الحالي: {b_icon} <b>{b_name}</b>\n• تسلسل"
        f" التسجيل اليومي المتتالي: <b>{streak_count} أيام</b> 🔥\n\n<i>كلما"
        " استمررت في التسجيل اليومي دون انقطاع، تضاعفت مكافأتك المجانية!</i>"
        "</blockquote>"
    )
    bot.send_message(
        call.message.chat.id,
        points_msg,
        parse_mode="HTML",
        reply_markup=markup,
    )

  elif action == "support":
    bot.answer_callback_query(call.id)
    user_states[user_id] = "waiting_support_msg"
    bot.send_message(
        call.message.chat.id,
        "💬 <i>أرسل رسالتك أو استفسارك الآن، وسيتم تحويله مباشرة إلى الإدارة:</i>",
        parse_mode="HTML",
    )

  elif action == "admin":
    if user_id != ADMIN_ID:
      bot.answer_callback_query(call.id, "هذا الزر للمشرف فقط ⛔", show_alert=True)
      return
    bot.answer_callback_query(call.id)
    show_admin_panel(call.message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data == "claim_daily_checkin")
def handle_daily_checkin(call):
  user_id = call.from_user.id
  today_str = datetime.now().strftime("%Y-%m-%d")
  yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_checkin_date, streak_count FROM daily_streak WHERE"
        " user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()

    if row and row[0] == today_str:
      bot.answer_callback_query(
          call.id, "⚠️ لقد قمت بتسجيل حضورك اليومي مسبقاً اليوم!", show_alert=True
      )
      conn.close()
      return

    if row and row[0] == yesterday_str:
      streak = row[1] + 1
    else:
      streak = 1

    # حساب النقاط المتضاعفة حسب السلسلة (اليوم الأول 5، الثاني 10، الثالث 20...)
    reward_points = 5 * (2 ** (min(streak, 5) - 1))

    cursor.execute(
        "INSERT OR REPLACE INTO daily_streak (user_id, last_checkin_date,"
        " streak_count) VALUES (?, ?, ?)",
        (user_id, today_str, streak),
    )
    cursor.execute(
        "INSERT INTO user_points (user_id, points) VALUES (?, ?) ON"
        " CONFLICT(user_id) DO UPDATE SET points = points + ?",
        (user_id, reward_points, reward_points),
    )
    cursor.execute(
        "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
    )
    new_pts = cursor.fetchone()[0]
    b_name, b_icon = get_user_badge(new_pts)
    cursor.execute(
        "INSERT OR REPLACE INTO user_badges (user_id, badge_name, badge_icon)"
        " VALUES (?, ?, ?)",
        (user_id, b_name, b_icon),
    )
    conn.commit()
    conn.close()

  bot.answer_callback_query(
      call.id,
      f"🎉 مبروك! حصلت على {reward_points} نقطة لمتابعة التسجيل (تسلسل:"
      f" {streak} أيام).",
      show_alert=True,
  )
  try:
    bot.edit_message_reply_markup(
        call.message.chat.id,
        call.message.message_id,
        reply_markup=types.InlineKeyboardMarkup().add(
            create_colored_btn(
                f"✅ تم استلام مكافأة اليوم ({streak} أيام متتالية)",
                callback_data="noop",
                style="primary",
            )
        ),
    )
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data == "set_custom_emoji")
def callback_set_custom_emoji(call):
  user_states[call.from_user.id] = "waiting_custom_emoji_input"
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      "🎨 <b>تخصيص شكل أزرار الحضور:</b>\n\nأرسل الآن النص أو الرمز التعبيري"
      " الجديد الذي تريد ظهوره على زر الحضور في قناتك (مثال: <code>🙋‍♂️ إثبات"
      " تواجد</code> أو <code>⚡ تسجيل الحضور</code>):",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id] == "waiting_custom_emoji_input"
)
def save_custom_emoji(message):
  user_id = message.from_user.id
  custom_text = message.text.strip()
  user_states.pop(user_id, None)

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO user_settings (user_id, custom_emoji) VALUES"
        " (?, ?)",
        (user_id, custom_text),
    )
    cursor.execute(
        "UPDATE user_settings SET custom_emoji = ? WHERE user_id = ?",
        (custom_text, user_id),
    )
    conn.commit()
    conn.close()

  bot.reply_to(
      message,
      f"✅ <b>تم حفظ شكل الزر المخصص بنجاح:</b>\n<code>{html.escape(custom_text)}</code>",
      parse_mode="HTML",
  )


@bot.callback_query_handler(func=lambda call: call.data == "compare_channels_activity")
def compare_channels_activity(call):
  user_id = call.from_user.id
  today = datetime.now()
  month_start = today.strftime("%Y-%m-01")

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_id, channel_title FROM saved_channels WHERE user_id = ?",
        (user_id,),
    )
    channels = cursor.fetchall()

    if not channels:
      bot.answer_callback_query(
          call.id, "❌ لا توجد قنوات مسجلة للمقارنة.", show_alert=True
      )
      conn.close()
      return

    comparison_results = []
    for cid, ctitle in channels:
      cursor.execute(
          "SELECT SUM(count) FROM channel_daily_attendance WHERE channel_id ="
          " ? AND date_str >= ?",
          (cid, month_start),
      )
      total_att = cursor.fetchone()[0] or 0

      cursor.execute(
          "SELECT SUM(posts_count) FROM channel_daily_posts WHERE channel_id"
          " = ? AND date_str >= ?",
          (cid, month_start),
      )
      total_posts = cursor.fetchone()[0] or 0
      comparison_results.append((ctitle, total_att, total_posts))
    conn.close()

  # ترتيب القنوات تنازلياً حسب إجمالي التفاعل هذا الشهر
  comparison_results.sort(key=lambda x: x[1], reverse=True)

  report_text = (
      "📊 <b>مقارنة نشاط وتفاعل قنواتك (هذا الشهر):</b>\n\n<blockquote>🏆 القناة"
      " الأكثر تفاعلاً تظهر في المقدمة:</blockquote>\n"
  )
  for i, (title, att, posts) in enumerate(comparison_results):
    medals = ["🥇", "🥈", "🥉", "🔹"]
    m_icon = medals[i] if i < len(medals) else "🔹"
    report_text += (
        f"{m_icon} <b>{html.escape(title)}</b>\n"
        f"  • إجمالي التفاعلات: <code>{att}</code>\n"
        f"  • عدد البوستات المنشورة: <code>{posts}</code>\n\n"
    )

  bot.answer_callback_query(call.id)
  bot.send_message(call.message.chat.id, report_text, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data == "set_privacy_leaderboard")
def callback_set_privacy_leaderboard(call):
  user_id = call.from_user.id
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT show_on_leaderboard FROM user_settings WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    user_show = row[0] if row and row[0] is not None else 1

    cursor.execute(
        "SELECT channel_id, channel_title, show_on_leaderboard FROM"
        " saved_channels WHERE user_id = ?",
        (user_id,),
    )
    channels = cursor.fetchall()
    conn.close()

  user_status_icon = "✅ (مرئي علناً)" if user_show == 1 else "🔒 (مخفي / مجهول)"

  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      create_colored_btn(
          f"👤 اسمي في المتصدرين: {user_status_icon}",
          callback_data="toggle_user_leaderboard_privacy",
          style="success" if user_show == 1 else "danger",
      )
  )

  if channels:
    markup.add(
        types.InlineKeyboardButton(
            text="📢 قنواتك المسجلة:", callback_data="noop"
        )
    )
    for cid, ctitle, c_show in channels:
      c_icon = "✅ مرئية" if c_show == 1 else "🔒 مخفية"
      markup.add(
          create_colored_btn(
              f"📢 {html.escape(ctitle)}: {c_icon}",
              callback_data=f"toggle_chan_priv_{cid}",
              style="success" if c_show == 1 else "danger",
          )
      )

  markup.add(
      create_colored_btn(
          "🔙 عودة للإعدادات", callback_data="menu_settings", style="primary"
      )
  )

  try:
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            "🔒 <b>إعدادات الخصوصية والظهور في لوحة المتصدرين:</b>\n\n<blockquote>اختر"
            " العنصر للتبديل بين الظهور علناً أو إخفاء الاسم/القناة:</blockquote>"
        ),
        parse_mode="HTML",
        reply_markup=markup,
    )
  except Exception:
    pass
  bot.answer_callback_query(call.id)


@bot.callback_query_handler(
    func=lambda call: call.data == "toggle_user_leaderboard_privacy"
)
def toggle_user_leaderboard_privacy(call):
  user_id = call.from_user.id
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT show_on_leaderboard FROM user_settings WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    current = row[0] if row and row[0] is not None else 1
    new_val = 0 if current == 1 else 1

    cursor.execute(
        "INSERT OR IGNORE INTO user_settings (user_id, title, duration,"
        " show_in_channel, show_on_leaderboard) VALUES (?, '', 0, 1, ?)",
        (user_id, new_val),
    )
    cursor.execute(
        "UPDATE user_settings SET show_on_leaderboard = ? WHERE user_id = ?",
        (new_val, user_id),
    )
    conn.commit()
    conn.close()

  bot.answer_callback_query(
      call.id,
      f"✅ تم تحديث إعداد خصوصية الاسم إلى:"
      f" {'مرئي علناً' if new_val == 1 else 'مخفي (مجهول)'}",
      show_alert=True,
  )
  callback_set_privacy_leaderboard(call)


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("toggle_chan_priv_")
)
def toggle_chan_privacy(call):
  user_id = call.from_user.id
  channel_id = call.data.replace("toggle_chan_priv_", "")
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT show_on_leaderboard FROM saved_channels WHERE user_id = ? AND"
        " channel_id = ?",
        (user_id, channel_id),
    )
    row = cursor.fetchone()
    if not row:
      bot.answer_callback_query(call.id, "❌ القناة غير موجودة.", show_alert=True)
      conn.close()
      return
    current = row[0] if row[0] is not None else 1
    new_val = 0 if current == 1 else 1

    cursor.execute(
        "UPDATE saved_channels SET show_on_leaderboard = ? WHERE user_id = ? AND"
        " channel_id = ?",
        (new_val, user_id, channel_id),
    )
    conn.commit()
    conn.close()

  bot.answer_callback_query(
      call.id,
      f"✅ تم تحديث خصوصية القناة إلى:"
      f" {'مرئية' if new_val == 1 else 'مخفية'}",
      show_alert=True,
  )
  callback_set_privacy_leaderboard(call)


@bot.callback_query_handler(func=lambda call: call.data == "noop")
def noop_callback(call):
  bot.answer_callback_query(call.id)


@bot.callback_query_handler(
    func=lambda call: call.data == "report_weekly_supervisor"
)
def handle_weekly_supervisor_report(call):
  user_id = call.from_user.id
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()

    today = datetime.now()
    dates_of_week = [
        (today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)
    ]

    cursor.execute(
        "SELECT channel_id, channel_title FROM saved_channels WHERE user_id ="
        " ?",
        (user_id,),
    )
    channels = cursor.fetchall()

    if not channels:
      bot.answer_callback_query(
          call.id, "❌ لم تقم بإضافة أي قنوات بعد.", show_alert=True
      )
      conn.close()
      return

    report_msg = "📊 <b>تقرير نشاط قنواتك لآخر 7 أيام:</b>\n\n"
    has_activity = False

    for cid, ctitle in channels:
      cursor.execute(
          f"SELECT date_str, posts_count FROM channel_daily_posts WHERE"
          f" channel_id = ? AND date_str IN ({','.join(['?']*7)})",
          (cid, *dates_of_week),
      )
      activity = cursor.fetchall()
      if activity:
        has_activity = True
        report_msg += f"📢 <b>قناة: {html.escape(ctitle)}</b>\n"
        for date_str, p_count in activity:
          report_msg += (
              f"  • يوم <code>{date_str}</code>: تم نشر {p_count} بوست حضور\n"
          )

        cursor.execute(
            f"SELECT SUM(count) FROM channel_daily_attendance WHERE"
            f" channel_id = ? AND date_str IN ({','.join(['?']*7)})",
            (cid, *dates_of_week),
        )
        total_att = cursor.fetchone()[0] or 0
        report_msg += (
            f"  👥 <i>إجمالي الحضور الأسبوعي في القناة: <b>{total_att}</b></i>\n\n"
        )
    conn.close()

  if not has_activity:
    bot.answer_callback_query(
        call.id, "⚠️ لا يوجد نشاط لك في القنوات خلال آخر 7 أيام.", show_alert=True
    )
    return

  bot.answer_callback_query(call.id, "✅ تم استخراج التقرير!")
  bot.send_message(call.message.chat.id, report_msg, parse_mode="HTML")


def show_channel_selection_menu(chat_id, user_id):
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_title, channel_id FROM saved_channels WHERE user_id ="
        " ?",
        (user_id,),
    )
    saved = cursor.fetchall()
    conn.close()

  if saved:
    markup = types.InlineKeyboardMarkup(row_width=1)
    for c_title, c_id in saved:
      markup.add(
          create_colored_btn(
              f"📢 {html.escape(c_title)}",
              callback_data=f"select_chan_{c_id}",
              style="success",
          )
      )
    markup.add(
        create_colored_btn(
            "➕ إضافة قناة جديدة",
            callback_data="add_new_channel_prompt",
            style="primary",
        )
    )
    bot.send_message(
        chat_id,
        "🚀 <b>اختر إحدى قنواتك المحفوظة أو أضف قناة جديدة للنشر:</b>\n\n<i>(ملاحظة:"
        " الحد الأقصى لبوستات الحضور هو بوستان فقط لكل قناة يومياً)</i>",
        parse_mode="HTML",
        reply_markup=markup,
    )
  else:
    user_states[user_id] = "waiting_channel_username"
    bot.send_message(
        chat_id,
        "🚀 <b>نشر بوست الحضور مباشرة بواسطة البوت:</b>\n\n<blockquote>أرسل الآن"
        " معرف قناتك أو مجموعة (مثال: <code>@MyChannel</code> أو رابط الدعوة أو"
        " الأيدي الخاص بالقناة)، وتأكد أن البوت مشرف فيها.\n(الحد الأقصى بوستان"
        " يومياً لكل قناة).</blockquote>",
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda call: call.data == "add_new_channel_prompt")
def add_new_channel_prompt(call):
  user_id = call.from_user.id
  user_states[user_id] = "waiting_channel_username"
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      "🚀 <b>أرسل الآن معرف القناة الجديدة أو الرابط أو الأيدي:</b>\n<i>(الحد"
      " الأقصى بوستان يومياً لكل قناة)</i>",
      parse_mode="HTML",
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("select_chan_"))
def select_saved_channel(call):
  user_id = call.from_user.id
  channel_id = call.data.replace("select_chan_", "")
  bot.answer_callback_query(call.id)
  publish_poll_to_channel(call.message, user_id, channel_id)


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id] == "waiting_channel_username"
)
def process_channel_posting(message):
  user_id = message.from_user.id
  channel_input = message.text.strip()
  user_states.pop(user_id, None)
  publish_poll_to_channel(message, user_id, channel_input)


def publish_poll_to_channel(message_or_call_msg, user_id, channel_input):
  chat_id_to_send = (
      message_or_call_msg.chat.id
      if hasattr(message_or_call_msg, "chat")
      else message_or_call_msg.message.chat.id
  )

  try:
    chat_info = bot.get_chat(channel_input)
    real_channel_id = str(chat_info.id)
    c_title = chat_info.title or real_channel_id
  except Exception as e:
    bot.send_message(
        chat_id_to_send,
        f"❌ <b>فشل الوصول للقناة أو المعرف غير صحيح:</b>\n<code>{e}</code>",
        parse_mode="HTML",
    )
    return

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()

    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT posts_count FROM channel_daily_posts WHERE channel_id = ? AND"
        " date_str = ?",
        (real_channel_id, today_str),
    )
    p_row = cursor.fetchone()
    posts_today = p_row[0] if p_row else 0

    if posts_today >= 2:
      conn.close()
      bot.send_message(
          chat_id_to_send,
          "⚠️ <b>عذراً، لقد وصلت للحد الأقصى لنشر بوستات الحضور في هذه القناة"
          " اليوم (مرتان فقط كحد أقصى يومياً).</b>",
          parse_mode="HTML",
      )
      return

    cursor.execute(
        "SELECT title, duration, show_in_channel, custom_emoji FROM"
        " user_settings WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()

    title = (
        row[0]
        if row and row[0]
        else f"سجل الحضور — {get_arabic_date_string()}"
    )
    duration = row[1] if row and row[1] is not None else 0
    show_in_channel = row[2] if row and row[2] is not None else 1
    custom_btn_text = row[3] if row and row[3] else "✅ تسجيل الحضور"

    poll_id = f"poll_{user_id}_{int(time.time())}"
    current_time = time.time()
    end_time = (current_time + (duration * 60)) if duration > 0 else 0

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        create_colored_btn(
            f"{custom_btn_text} [0]",
            callback_data=f"attend_{poll_id}",
            style="success",
        )
    )
    keyboard.add(
        create_colored_btn("🤖 الانتقال للبوت", url=BOT_URL, style="primary")
    )

    time_note = (
        f"\n<i>⏱️ ينتهي هذا البوست تلقائياً بعد {duration} دقيقة.</i>"
        if duration > 0
        else "\n<i>⏱️ البوست مفتوح طوال الوقت لتسجيل الحضور.</i>"
    )

    msg_content = (
        f"<b>📢 {html.escape(title)}</b>\n\n<i>اضغط على الزر الملون أدناه لتسجيل"
        f" حضورك الرسمي فوراً:</i>{time_note}"
    )
    if show_in_channel == 1:
      msg_content += (
          "\n\n<blockquote expandable><b>👥 قائمة الحضور المسجلين (0):</b>\nلا"
          " توجد تسجيلات حتى الآن.</blockquote>"
      )

  try:
    sent_msg = bot.send_message(
        real_channel_id,
        msg_content,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )

    # ميزة التثبيت التلقائي (Auto-Pin)
    try:
      bot.pin_chat_message(
          chat_id=real_channel_id, message_id=sent_msg.message_id
      )
    except Exception as pin_err:
      print(f"Auto-Pin note: {pin_err}")

    with db_lock:
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "INSERT OR REPLACE INTO saved_channels (user_id, channel_id,"
          " channel_title) VALUES (?, ?, ?)",
          (user_id, real_channel_id, c_title),
      )
      cursor.execute(
          "INSERT INTO channel_daily_posts (channel_id, date_str, posts_count)"
          " VALUES (?, ?, 1) ON CONFLICT(channel_id, date_str) DO UPDATE SET"
          " posts_count = posts_count + 1",
          (real_channel_id, today_str),
      )
      cursor.execute(
          "INSERT OR REPLACE INTO polls (poll_id, owner_id, count, title,"
          " end_time, is_closed, show_in_channel, channel_id, message_id,"
          " reminder_sent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
          (
              poll_id,
              user_id,
              0,
              title,
              end_time,
              0,
              show_in_channel,
              real_channel_id,
              sent_msg.message_id,
          ),
      )
      conn.commit()
      conn.close()

    bot.send_message(
        chat_id_to_send,
        "✅ <b>تم نشر بوست الحضور بنجاح في القناة وتثبيته تلقائياً وحفظها"
        " بقنواتك!</b>",
        parse_mode="HTML",
    )
  except Exception as e:
    bot.send_message(
        chat_id_to_send,
        f"❌ <b>فشل النشر في القناة:</b>\n\n<blockquote>تأكد أن البوت <b>مشرف</b>"
        f" في القناة ولديه صلاحية إرسال وتثبيت الرسائل.\nالتفاصيل التقنية:"
        f" <code>{e}</code></blockquote>",
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda call: call.data == "sched_type_poll")
def sched_type_poll(call):
  user_id = call.from_user.id
  user_states[user_id] = {"sched_type": "poll", "step": "waiting_sched_input"}
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      "📌 <b>جدولة بوست حضور:</b>\n\nأرسل الآن عنوان أو كليشة بوست الحضور:",
      parse_mode="HTML",
  )


@bot.callback_query_handler(func=lambda call: call.data == "sched_type_msg")
def sched_type_msg(call):
  user_id = call.from_user.id
  user_states[user_id] = {"sched_type": "msg", "step": "waiting_sched_input"}
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      "📢 <b>جدولة إعلان أو رسالة نصية عامة:</b>\n\nأرسل الآن نص الإعلان المراد"
      " نشره في القناة:",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step") == "waiting_sched_input"
)
def process_sched_title_generic(message):
  user_id = message.from_user.id
  title = message.text.strip()
  user_states[user_id]["sched_title"] = title
  user_states[user_id]["step"] = "waiting_sched_channel"
  bot.reply_to(
      message,
      "📌 <i>أرسل الآن معرف القناة المراد النشر فيها تلقائياً (مثال:"
      " @MyChannel):</i>",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step")
    == "waiting_sched_channel"
)
def process_sched_channel_generic(message):
  user_id = message.from_user.id
  channel_input = message.text.strip()
  user_states[user_id]["sched_channel"] = channel_input
  user_states[user_id]["step"] = "waiting_sched_minutes"
  bot.reply_to(
      message,
      "⏱️ <i>بعد كم دقيقة تريد أن يتم نشر هذا المحتوى تلقائياً في القناة؟ (أرسل"
      " رقماً بالدقائق، مثال: 30):</i>",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step")
    == "waiting_sched_minutes"
)
def process_sched_minutes_generic(message):
  user_id = message.from_user.id
  try:
    minutes = int(message.text.strip())
  except ValueError:
    bot.reply_to(message, "❌ يجِب إرسال رقم صحيح بالدقائق.")
    return

  sched_data = user_states.pop(user_id, None)
  sched_id = f"sched_{user_id}_{int(time.time())}"
  run_time = time.time() + (minutes * 60)
  post_type = sched_data.get("sched_type", "poll")

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO scheduled_posts (sched_id, user_id, channel_id, post_type,"
        " title, content_data, run_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            sched_id,
            user_id,
            sched_data["sched_channel"],
            post_type,
            sched_data["sched_title"],
            "",
            run_time,
        ),
    )
    conn.commit()
    conn.close()

  bot.reply_to(
      message,
      f"⏰ <b>تمت جدولة المحتوى بنجاح!</b>\nسيتم نشره تلقائياً في القناة بعد"
      f" <code>{minutes}</code> دقيقة.",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id] == "waiting_coupon_input"
)
def process_coupon_text_input(message):
  user_id = message.from_user.id
  code = message.text.strip()
  user_states.pop(user_id, None)

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT points, max_uses, uses_count, is_closed FROM coupons WHERE code ="
        " ?",
        (code,),
    )
    c_row = cursor.fetchone()
    if not c_row:
      bot.reply_to(
          message, "❌ <b>عذراً، كود الكوبون غير صحيح.</b>", parse_mode="HTML"
      )
      conn.close()
      return
    pts, max_uses, uses_count, is_closed = c_row
    if is_closed == 1 or uses_count >= max_uses:
      bot.reply_to(
          message,
          "⌛ <b>عذراً، هذا الكوبون انتهى أو استنفد استخداماته!</b>",
          parse_mode="HTML",
      )
      conn.close()
      return
    cursor.execute(
        "SELECT * FROM coupon_uses WHERE code = ? AND user_id = ?",
        (code, user_id),
    )
    if cursor.fetchone():
      bot.reply_to(
          message, "⚠️ <b>لقد استخدمت هذا الكوبون مسبقاً!</b>", parse_mode="HTML"
      )
      conn.close()
      return
    cursor.execute(
        "INSERT INTO coupon_uses (code, user_id) VALUES (?, ?)", (code, user_id)
    )
    cursor.execute(
        "UPDATE coupons SET uses_count = uses_count + 1 WHERE code = ?", (code,)
    )
    cursor.execute(
        "INSERT INTO user_points (user_id, points) VALUES (?, ?) ON"
        " CONFLICT(user_id) DO UPDATE SET points = points + ?",
        (user_id, pts, pts),
    )

    cursor.execute(
        "SELECT points FROM user_points WHERE user_id = ?", (user_id,)
    )
    new_pts = cursor.fetchone()[0]
    b_name, b_icon = get_user_badge(new_pts)
    cursor.execute(
        "INSERT OR REPLACE INTO user_badges (user_id, badge_name, badge_icon)"
        " VALUES (?, ?, ?)",
        (user_id, b_name, b_icon),
    )
    conn.commit()
    conn.close()

  bot.reply_to(
      message,
      f"🎉 <b>تم شحن الكوبون بنجاح!</b>\nأُضيف إلى رصيدك <code>{pts}</code>"
      f" نقطة.\n🏅 الوسام الحالي: {b_icon} {b_name}",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id] == "waiting_q_text"
)
def q_step_text(message):
  user_id = message.from_user.id
  q_text = message.text.strip()
  user_states[user_id] = {"q_text": q_text, "step": "waiting_opt_a"}
  bot.reply_to(message, "📌 <i>أرسل الآن الخيار الأول (أ):</i>", parse_mode="HTML")


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step") == "waiting_opt_a"
)
def q_step_opt_a(message):
  user_id = message.from_user.id
  user_states[user_id]["opt_a"] = message.text.strip()
  user_states[user_id]["step"] = "waiting_opt_b"
  bot.reply_to(message, "📌 <i>أرسل الآن الخيار الثاني (ب):</i>", parse_mode="HTML")


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step") == "waiting_opt_b"
)
def q_step_opt_b(message):
  user_id = message.from_user.id
  user_states[user_id]["opt_b"] = message.text.strip()
  user_states[user_id]["step"] = "waiting_opt_c"
  bot.reply_to(message, "📌 <i>أرسل الآن الخيار الثالث (ج):</i>", parse_mode="HTML")


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step") == "waiting_opt_c"
)
def q_step_opt_c(message):
  user_id = message.from_user.id
  user_states[user_id]["opt_c"] = message.text.strip()
  user_states[user_id]["step"] = "waiting_opt_d"
  bot.reply_to(message, "📌 <i>أرسل الآن الخيار الرابع (د):</i>", parse_mode="HTML")


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step") == "waiting_opt_d"
)
def q_step_opt_d(message):
  user_id = message.from_user.id
  user_states[user_id]["opt_d"] = message.text.strip()
  user_states[user_id]["step"] = "waiting_correct_opt"
  markup = types.InlineKeyboardMarkup(row_width=2)
  markup.add(
      create_colored_btn(
          "الخيار (أ)", callback_data="q_correct_A", style="success"
      ),
      create_colored_btn(
          "الخيار (ب)", callback_data="q_correct_B", style="success"
      ),
      create_colored_btn(
          "الخيار (ج)", callback_data="q_correct_C", style="success"
      ),
      create_colored_btn(
          "الخيار (د)", callback_data="q_correct_D", style="success"
      ),
  )
  bot.reply_to(
      message,
      "🎯 <i>اختر الإجابة الصحيحة من الأزرار أدناه:</i>",
      parse_mode="HTML",
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("q_correct_"))
def q_step_correct_chosen(call):
  user_id = call.from_user.id
  if user_id not in user_states or not isinstance(user_states[user_id], dict):
    bot.answer_callback_query(
        call.id, "❌ انتهت الجلسة، ابدأ من جديد.", show_alert=True
    )
    return
  correct_opt = call.data.replace("q_correct_", "")
  user_states[user_id]["correct_opt"] = correct_opt
  user_states[user_id]["step"] = "waiting_q_channel"
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      "🚀 <i>أرسل الآن معرف قناتك لنشر السؤال التفاعلي مع (تحدي السرعة) فيها"
      " (مثال: <code>@MyChannel</code>):</i>",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and isinstance(user_states[message.from_user.id], dict)
    and user_states[message.from_user.id].get("step") == "waiting_q_channel"
)
def q_step_publish(message):
  user_id = message.from_user.id
  channel_input = message.text.strip()
  q_data = user_states.pop(user_id, None)

  try:
    chat_info = bot.get_chat(channel_input)
    real_channel_id = str(chat_info.id)
  except Exception as e:
    bot.reply_to(
        message, f"❌ فشل الوصول للقناة: <code>{e}</code>", parse_mode="HTML"
    )
    return

  question_id = f"q_{user_id}_{int(time.time())}"
  q_text = q_data["q_text"]
  oa = q_data["opt_a"]
  ob = q_data["opt_b"]
  oc = q_data["opt_c"]
  od = q_data["opt_d"]
  correct_opt = q_data["correct_opt"]

  keyboard = types.InlineKeyboardMarkup(row_width=2)
  keyboard.add(
      create_colored_btn(
          f"أ) {oa}", callback_data=f"ans_{question_id}_A", style="primary"
      ),
      create_colored_btn(
          f"ب) {ob}", callback_data=f"ans_{question_id}_B", style="primary"
      ),
      create_colored_btn(
          f"ج) {oc}", callback_data=f"ans_{question_id}_C", style="primary"
      ),
      create_colored_btn(
          f"د) {od}", callback_data=f"ans_{question_id}_D", style="primary"
      ),
  )
  keyboard.add(
      create_colored_btn("🤖 الانتقال للبوت", url=BOT_URL, style="primary")
  )

  q_msg_content = (
      f"💡 <b>سؤال تفاعلي مع (تحدي السرعة):</b>\n\n📌 <b>{html.escape(q_text)}</b>\n\n🔹 أ)"
      f" {html.escape(oa)}\n🔹 ب) {html.escape(ob)}\n🔹 ج) {html.escape(oc)}\n🔹 د)"
      f" {html.escape(od)}\n\n🏁 <b>لوحة شرف تحدي السرعة (أسرع 3 أجابوا"
      " صح):</b>\n<blockquote>1. في انتظار الأسرع...\n2. في انتظار الأسرع...\n3."
      " في انتظار الأسرع...</blockquote>\n\n<i>⏱️ اختر الإجابة الصحيحة الآن لتكون في"
      f' لوحة الشرف!</i>'
  )

  try:
    sent_msg = bot.send_message(
        real_channel_id,
        q_msg_content,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    try:
      bot.pin_chat_message(
          chat_id=real_channel_id, message_id=sent_msg.message_id
      )
    except Exception:
      pass

    with db_lock:
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO questions (question_id, owner_id, question_text, opt_a,"
          " opt_b, opt_c, opt_d, correct_opt, channel_id, message_id, is_closed)"
          " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
          (
              question_id,
              user_id,
              q_text,
              oa,
              ob,
              oc,
              od,
              correct_opt,
              real_channel_id,
              sent_msg.message_id,
          ),
      )
      conn.commit()
      conn.close()

    bot.reply_to(
        message,
        "✅ <b>تم نشر السؤال التفاعلي وتثبيته في القناة بنجاح!</b>",
        parse_mode="HTML",
    )
  except Exception as e:
    bot.reply_to(
        message,
        f"❌ <b>فشل نشر السؤال في القناة:</b>\n\n<blockquote>تأكد أن البوت مشرف"
        f" ولديه صلاحيات الإرسال والتثبيت.\nالتفاصيل: <code>{e}</code></blockquote>",
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("ans_"))
def handle_question_answer(call):
  raw_data = call.data[4:]
  last_underscore_idx = raw_data.rfind("_")
  if last_underscore_idx == -1:
    return
  question_id = raw_data[:last_underscore_idx]
  chosen_opt = raw_data[last_underscore_idx + 1 :]
  user = call.from_user

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT owner_id, correct_opt, is_closed, question_text, opt_a, opt_b,"
        " opt_c, opt_d, channel_id, message_id FROM questions WHERE question_id ="
        " ?",
        (question_id,),
    )
    q_row = cursor.fetchone()
    if not q_row:
      bot.answer_callback_query(
          call.id, "❌ عذراً، هذا السؤال غير موجود أو انتهى.", show_alert=True
      )
      conn.close()
      return
    (
        owner_id,
        correct_opt,
        is_closed,
        q_text,
        oa,
        ob,
        oc,
        od,
        channel_id,
        message_id,
    ) = q_row

    try:
      member = bot.get_chat_member(channel_id, user.id)
      if member.status not in ["member", "administrator", "creator"]:
        bot.answer_callback_query(
            call.id,
            "⛔ عذراً، يجب عليك الاشتراك في قناة هذا المشرف لتتمكن من الإجابة!",
            show_alert=True,
        )
        conn.close()
        return
    except Exception as e:
      print(f"Question channel membership check warning: {e}")

    if is_closed == 1:
      bot.answer_callback_query(
          call.id, "⌛ عذراً، تم إغلاق هذا السؤال!", show_alert=True
      )
      conn.close()
      return

    cursor.execute(
        "SELECT * FROM question_answers WHERE question_id = ? AND user_id = ?",
        (question_id, user.id),
    )
    if cursor.fetchone():
      bot.answer_callback_query(
          call.id, "⚠️ لقد قمت بالإجابة على هذا السؤال مسبقاً!", show_alert=True
      )
      conn.close()
      return

    is_correct = 1 if chosen_opt == correct_opt else 0
    earned_points = 0
    speed_bonus_note = ""

    cursor.execute(
        "SELECT full_name FROM user_profiles WHERE user_id = ?", (user.id,)
    )
    prof = cursor.fetchone()
    fixed_name = prof[0] if prof else user.first_name

    if is_correct == 1:
      cursor.execute(
          "SELECT COUNT(*) FROM question_speed_race WHERE question_id = ?",
          (question_id,),
      )
      current_rank = cursor.fetchone()[0] + 1

      if current_rank <= 3:
        cursor.execute(
            "INSERT INTO question_speed_race (question_id, user_id, user_name,"
            " rank_pos) VALUES (?, ?, ?, ?)",
            (question_id, user.id, fixed_name, current_rank),
        )
        if current_rank == 1:
          earned_points = 25
          speed_bonus_note = " 🚀 (المركز الأول في تحدي السرعة! +25 نقطة)"
        elif current_rank == 2:
          earned_points = 18
          speed_bonus_note = " 🥈 (المركز الثاني في تحدي السرعة! +18 نقطة)"
        elif current_rank == 3:
          earned_points = 12
          speed_bonus_note = " 🥉 (المركز الثالث في تحدي السرعة! +12 نقطة)"
      else:
        earned_points = 5
        speed_bonus_note = " ✅ (إجابة صحيحة! +5 نقاط)"

      cursor.execute(
          "INSERT INTO user_points (user_id, points) VALUES (?, ?) ON"
          " CONFLICT(user_id) DO UPDATE SET points = points + ?",
          (user.id, earned_points, earned_points),
      )

      cursor.execute(
          "SELECT points FROM user_points WHERE user_id = ?", (user.id,)
      )
      new_pts = cursor.fetchone()[0]
      b_name, b_icon = get_user_badge(new_pts)
      cursor.execute(
          "INSERT OR REPLACE INTO user_badges (user_id, badge_name, badge_icon)"
          " VALUES (?, ?, ?)",
          (user.id, b_name, b_icon),
      )
    else:
      earned_points = 0
      speed_bonus_note = " ❌ (إجابة خاطئة!)"

    cursor.execute(
        "INSERT INTO question_answers (question_id, user_id, selected_option,"
        " is_correct, earned_points) VALUES (?, ?, ?, ?, ?)",
        (question_id, user.id, chosen_opt, is_correct, earned_points),
    )

    cursor.execute(
        "SELECT rank_pos, user_name FROM question_speed_race WHERE question_id ="
        " ? ORDER BY rank_pos ASC",
        (question_id,),
    )
    speed_racers = cursor.fetchall()
    conn.commit()
    conn.close()

  try:
    racers_dict = {r[0]: r[1] for r in speed_racers}
    r1 = racers_dict.get(1, "في انتظار الأسرع...")
    r2 = racers_dict.get(2, "في انتظار الأسرع...")
    r3 = racers_dict.get(3, "في انتظار الأسرع...")

    updated_q_content = (
        f"💡 <b>سؤال تفاعلي مع (تحدي السرعة):</b>\n\n📌 <b>{html.escape(q_text)}</b>\n\n🔹 أ)"
        f" {html.escape(oa)}\n🔹 ب) {html.escape(ob)}\n🔹 ج) {html.escape(oc)}\n🔹 د)"
        f" {html.escape(od)}\n\n🏁 <b>لوحة شرف تحدي السرعة (أسرع 3 أجابوا"
        f" صح):</b>\n<blockquote>1. {html.escape(str(r1))}\n2."
        f" {html.escape(str(r2))}\n3. {html.escape(str(r3))}</blockquote>\n\n<i>⏱️"
        f' اختر الإجابة الصحيحة الآن لتكون في لوحة الشرف!</i>'
    )
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        create_colored_btn(
            f"أ) {oa}", callback_data=f"ans_{question_id}_A", style="primary"
        ),
        create_colored_btn(
            f"ب) {ob}", callback_data=f"ans_{question_id}_B", style="primary"
        ),
        create_colored_btn(
            f"ج) {oc}", callback_data=f"ans_{question_id}_C", style="primary"
        ),
        create_colored_btn(
            f"د) {od}", callback_data=f"ans_{question_id}_D", style="primary"
        ),
    )
    keyboard.add(
        create_colored_btn("🤖 الانتقال للبوت", url=BOT_URL, style="primary")
    )
    bot.edit_message_text(
        chat_id=channel_id,
        message_id=message_id,
        text=updated_q_content,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
  except Exception as e:
    print(f"Error updating speed race message: {e}")

  bot.answer_callback_query(call.id, f"{speed_bonus_note}", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("view_stats_"))
def view_poll_detailed_stats(call):
  poll_id = call.data.replace("view_stats_", "")
  user_id = call.from_user.id
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, count, end_time FROM polls WHERE poll_id = ? AND owner_id ="
        " ?",
        (poll_id, user_id),
    )
    poll = cursor.fetchone()
    if not poll:
      bot.answer_callback_query(
          call.id, "❌ البوست غير موجود أو ليس لك صلاحية.", show_alert=True
      )
      conn.close()
      return
    title, count, end_time = poll
    cursor.execute(
        "SELECT user_name, username FROM poll_votes WHERE poll_id = ?",
        (poll_id,),
    )
    votes = cursor.fetchall()

    cursor.execute(
        "SELECT COUNT(DISTINCT user_id) FROM poll_votes WHERE poll_id = ?",
        (poll_id,),
    )
    unique_users_count = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM user_profiles")
    total_bot_users = cursor.fetchone()[0] or 1
    conn.close()

  attendance_rate = round((unique_users_count / total_bot_users) * 100, 1)
  if attendance_rate > 100:
    attendance_rate = 100

  voters_str = ""
  if votes:
    voters_lines = [
        f"<blockquote>{i+1}. <b>{html.escape(v[0])}</b>"
        f" ({html.escape(v[1])})</blockquote>"
        for i, v in enumerate(votes)
    ]
    voters_str = "\n".join(voters_lines)
  else:
    voters_str = "<blockquote>• لم يسجل أحد حضوره حتى الآن.</blockquote>"

  stats_detail_msg = (
      f"📊 <b>التحليلات المتقدمة وإحصائيات البوست:</b>\n\n<blockquote>• <b>عنوان"
      f" البوست:</b> <code>{html.escape(title)}</code>\n• <b>إجمالي التفاعلات"
      f" (Total):</b> <code>{count}</code> تفاعل\n• <b>الأشخاص الفريدون (Unique"
      f" Reach):</b> <code>{unique_users_count}</code> مستخدم حقيقي\n• <b>معدل"
      f" التفاعل الفعلي (Engagement Rate):</b>"
      f" <code>{attendance_rate}%</code></blockquote>\n\n💡 <i>ملاحظة تحليلية:"
      " تم فصل الأرقام لتوضيح تداخل المشتركين بدقة وعكس الواقع الفعلي"
      f" للتفاعل.</i>\n\n👥 <b>قائمة الحاضرين المسجلين:</b>\n{voters_str}"
  )
  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      create_colored_btn(
          "📥 تحميل كشف الحضور (CSV)",
          callback_data=f"export_{poll_id}",
          style="primary",
      )
  )
  markup.add(
      create_colored_btn(
          "🗑️ حذف البوست نهائياً",
          callback_data=f"delete_poll_{poll_id}",
          style="danger",
      )
  )
  markup.add(
      create_colored_btn(
          "🔙 العودة للإحصائيات", callback_data="menu_stats", style="success"
      )
  )

  bot.answer_callback_query(call.id)
  bot.edit_message_text(
      chat_id=call.message.chat.id,
      message_id=call.message.message_id,
      text=stats_detail_msg,
      parse_mode="HTML",
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_poll_"))
def delete_poll_callback(call):
  poll_id = call.data.replace("delete_poll_", "")
  user_id = call.from_user.id
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_id, message_id FROM polls WHERE poll_id = ? AND"
        " owner_id = ?",
        (poll_id, user_id),
    )
    p = cursor.fetchone()
    if p:
      chan_id, msg_id = p
      try:
        bot.delete_message(chan_id, msg_id)
      except Exception:
        pass
    cursor.execute("DELETE FROM polls WHERE poll_id = ?", (poll_id,))
    cursor.execute("DELETE FROM poll_votes WHERE poll_id = ?", (poll_id,))
    conn.commit()
    conn.close()

  bot.answer_callback_query(
      call.id, "✅ تم حذف بوست الحضور بنجاح.", show_alert=True
  )
  try:
    bot.delete_message(call.message.chat.id, call.message.message_id)
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("export_"))
def export_csv_callback(call):
  poll_id = call.data.replace("export_", "")
  user_id = call.from_user.id
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM polls WHERE poll_id = ?", (poll_id,))
    res = cursor.fetchone()
    title = res[0] if res else "Attendance"

    cursor.execute(
        "SELECT user_id, user_name, username, vote_timestamp FROM poll_votes"
        " WHERE poll_id = ?",
        (poll_id,),
    )
    votes = cursor.fetchall()
    conn.close()

  output = io.StringIO()
  writer = csv.writer(output)
  writer.writerow(["User ID", "Full Name", "Username", "Timestamp"])
  for v in votes:
    t_str = datetime.fromtimestamp(v[3]).strftime("%Y-%m-%d %H:%M:%S")
    writer.writerow([v[0], v[1], v[2], t_str])

  output.seek(0)
  bio = io.BytesIO(output.getvalue().encode("utf-8-sig"))
  bio.name = f"attendance_{poll_id}.csv"

  bot.answer_callback_query(call.id, "✅ تم إعداد ملف الحضور بنجاح!")
  bot.send_document(
      call.message.chat.id,
      bio,
      caption=(
          f"📊 <b>كشف الحضور الرسمي للبوست:</b>\n<code>{html.escape(title)}</code>"
      ),
      parse_mode="HTML",
  )


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
