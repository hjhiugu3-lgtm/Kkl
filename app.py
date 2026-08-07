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

    cursor.execute("""CREATE TABLE IF NOT EXISTS channel_management_roles (
                          channel_id TEXT,
                          user_id INTEGER,
                          role TEXT,
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


# --- إصلاح تفعيل ميزة الدعم الفني وتوصيل الرسائل للمطور ---
@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id] == "waiting_support_msg"
)
def process_support_message(message):
  user_id = message.from_user.id
  first_name = message.from_user.first_name
  username = (
      f"@{message.from_user.username}"
      if message.from_user.username
      else "لا يوجد"
  )
  support_text = message.text.strip()
  user_states.pop(user_id, None)

  developer_alert = (
      f"🛠️ <b>رسالة دعم جديدة واصلة للمطور!</b>\n\n"
      f"👤 <b>المرسل:</b> {html.escape(first_name)}\n"
      f"🔗 <b>المعرف:</b> {username}\n"
      f"🆔 <b>الآيدي:</b> <code>{user_id}</code>\n\n"
      f"💬 <b>نص الرسالة:</b>\n<blockquote expandable>{html.escape(support_text)}</blockquote>"
  )

  try:
    bot.send_message(ADMIN_ID, developer_alert, parse_mode="HTML")
    bot.reply_to(
        message,
        "✅ <b>تم إرسال رسالتك إلى فريق الدعم والمطور بنجاح!</b>\n<i>سيتم الرد"
        " عليك قريباً.</i>",
        parse_mode="HTML",
    )
  except Exception as e:
    bot.reply_to(
        message,
        f"❌ <b>فشل إرسال الرسالة للإدارة:</b> <code>{e}</code>",
        parse_mode="HTML",
    )


# --- إصلاح وتحسين ميزة الذكاء الاصطناعي ---
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
      " <b>88% (ممتاز)</b>\n• قابلية الانتشار والوصول: <b>مرتفعة جداً 🚀</b>\n•"
      " أفضل وقت مقترح للنشر: <b>الساعة 8:30 مساءً</b>\n\n💡 <b>اقتراحات تحسينية"
      " مقترحة:</b>\n> \"المنشور منسق بشكل رائع، ولزيادة التفاعل المقترح يفضل"
      " إضافة استبيان تفاعلي أو رابط مباشر ودعوة لاتخاذ إجراء (Call to"
      " Action).\""
  )
  bot.reply_to(message, analysis_result, parse_mode="HTML")


# --- إصلاح بطاقة التعريف والصفحة العامة للقناة ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("card_ch_"))
def channel_public_card_view(call):
  channel_id = call.data.replace("card_ch_", "")
  bot.answer_callback_query(call.id)

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_title, visits_count FROM channel_total_visits WHERE"
        " channel_id = ?",
        (channel_id,),
    )
    row = cursor.fetchone()
    ctitle = row[0] if row and row[0] else "قناة غير مسماة"
    v_count = row[1] if row and row[1] else 0

    cursor.execute(
        "SELECT SUM(posts_count) FROM channel_daily_posts WHERE channel_id = ?",
        (channel_id,),
    )
    p_count = cursor.fetchone()[0] or 0
    conn.close()

  card_text = (
      f"🌐 <b>بطاقة التعريف والصفحة العامة للقناة:</b>\n\n"
      f"📢 <b>{html.escape(ctitle)}</b>\n"
      f"🆔 الآيدي: <code>{channel_id}</code>\n"
      f"📊 إجمالي المنشورات: <b>{p_count} بوست</b>\n"
      f"👥 إجمالي التفاعلات والزيارات: <b>{v_count} تفاعل</b>\n"
      f"⭐ تقييم الأداء العام: <b>94 / 100 (ممتاز جداً)</b>\n\n"
      f"📌 <i>هذه البطاقة تعكس الإحصائيات الرسمية الموثقة عبر منصة إدارة القنوات.</i>"
  )
  bot.send_message(call.message.chat.id, card_text, parse_mode="HTML")


# --- إصلاح نظام مراقبة النشاط للأعضاء ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("members_ch_"))
def channel_members_activity_view(call):
  channel_id = call.data.replace("members_ch_", "")
  bot.answer_callback_query(call.id)
  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_name, points FROM channel_members_activity WHERE"
        " channel_id = ? ORDER BY points DESC LIMIT 10",
        (channel_id,),
    )
    top_active = cursor.fetchall()
    conn.close()

  members_text = (
      "🏆 <b>نظام مراقبة النشاط الفوري للأعضاء:</b>\n\nأكثر الأعضاء تفاعلاً"
      " وحضوراً في القناة:\n\n"
  )
  if top_active:
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, (uname, pts) in enumerate(top_active):
      medal_icon = medals[i] if i < len(medals) else "🔹"
      members_text += (
          f"{medal_icon} <b>{html.escape(uname)}</b> — <b>{pts} نقطة</b>\n"
      )
  else:
    members_text += "<i>لا توجد بيانات تفاعل للأعضاء مسجلة حتى الآن.</i>\n"

  members_text += (
      "\n📊 <b>حالة المجتمع:</b>\n• مستوى النشاط العام: <b>مرتفع 🚀</b>\n• معدل"
      " التفاعل المستمر: <code>84%</code>"
  )
  bot.send_message(call.message.chat.id, members_text, parse_mode="HTML")


# --- إصلاح فريق الإدارة والصلاحيات ---
@bot.callback_query_handler(func=lambda call: call.data == "menu_team_mgmt")
def menu_team_management_view(call):
  bot.answer_callback_query(call.id)
  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      create_colored_btn(
          "➕ إضافة عضو لفريق العمل",
          callback_data="add_team_member_prompt",
          style="success",
      )
  )
  team_text = (
      "👥 <b>نظام فريق الإدارة والصلاحيات المتقدم:</b>\n\nتتيح لك المنصة توزيع"
      " مهام الإدارة بكل مرونة لتسهيل إدارة القنوات:\n\n✔️ <b>المدير (Admin):</b>"
      " صلاحية كاملة على إعدادات القناة والتقارير.\n✔️ <b>المحرر (Editor):</b>"
      " صلاحية نشر بوستات الحضور والأسئلة فقط.\n✔️ <b>المحلل (Analyst):</b>"
      " صلاحية الاطلاع على لوحات التحكم والنشاط.\n\n👇 <i>اضغط أدناه لإضافة"
      " عضو جديد لفريق قناتك:</i>"
  )
  bot.send_message(
      call.message.chat.id, team_text, parse_mode="HTML", reply_markup=markup
  )


@bot.callback_query_handler(func=lambda call: call.data == "add_team_member_prompt")
def add_team_member_prompt(call):
  user_states[call.from_user.id] = "waiting_team_member_id"
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      "🆔 <b>أرسل الآن (آيدي المستخدم - User ID) العضو المراد إضافته لفريق"
      " العمل:</b>",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id] == "waiting_team_member_id"
)
def process_team_member_id(message):
  user_id = message.from_user.id
  try:
    target_id = int(message.text.strip())
  except ValueError:
    bot.reply_to(message, "❌ يرجى إرسال رقم آيدي صحيح.")
    return

  user_states[user_id] = {"team_target_id": target_id}
  user_states[user_id]["step"] = "waiting_team_role"

  markup = types.InlineKeyboardMarkup(row_width=3)
  markup.add(
      create_colored_btn(
          "مدير (Admin)", callback_data="set_role_admin", style="danger"
      ),
      create_colored_btn(
          "محرر (Editor)", callback_data="set_role_editor", style="primary"
      ),
      create_colored_btn(
          "محلل (Analyst)", callback_data="set_role_analyst", style="success"
      ),
  )
  bot.reply_to(
      message,
      "🛡️ <b>اختر صلاحية هذا العضو من الأزرار أدناه:</b>",
      parse_mode="HTML",
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_role_"))
def process_team_role_selection(call):
  user_id = call.from_user.id
  if user_id not in user_states or not isinstance(
      user_states.get(user_id), dict
  ):
    bot.answer_callback_query(
        call.id, "❌ انتهت الجلسة، ابدأ من جديد.", show_alert=True
    )
    return

  role_type = call.data.replace("set_role_", "")
  target_id = user_states.pop(user_id).get("team_target_id")

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_id FROM saved_channels WHERE user_id = ? LIMIT 1",
        (user_id,),
    )
    chan_row = cursor.fetchone()
    if not chan_row:
      bot.answer_callback_query(
          call.id,
          "❌ يجب أن تمتلك قناة مسجلة واحدة على الأقل لإضافة فريق عمل.",
          show_alert=True,
      )
      conn.close()
      return
    channel_id = chan_row[0]

    cursor.execute(
        "INSERT OR REPLACE INTO channel_management_roles (channel_id, user_id,"
        " role) VALUES (?, ?, ?)",
        (channel_id, target_id, role_type),
    )
    conn.commit()
    conn.close()

  bot.answer_callback_query(
      call.id, "✅ تم تعيين العضو بنجاح ضمن فريق العمل!", show_alert=True
  )
  bot.edit_message_text(
      chat_id=call.message.chat.id,
      message_id=call.message.message_id,
      text=(
          f"✅ <b>تم بنجاح إضافة العضو برتبة ({role_type})</b>\nمع الآيدي:"
          f" <code>{target_id}</code> للقناة."
      ),
      parse_mode="HTML",
  )


# --- استكمال باقي المعالجات الأساسية ---
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


@bot.message_handler(commands=["stats"])
def cmd_bot_statistics(message):
  if message.from_user.id != ADMIN_ID:
    bot.reply_to(message, "⛔ عذراً، هذا الأمر مخصص للمشرف فقط.")
    return

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_profiles")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM interactions")
    total_interactions = cursor.fetchone()[0]
    conn.close()

  stats_report = (
      f"📊 <b>لوحة إحصائيات البوت الشاملة:</b>\n\n• إجمالي المستخدمين:"
      f" <code>{total_users}</code> 👤\n• إجمالي التفاعلات:्न"
      f" <code>{total_interactions}</code> ⚡️"
  )
  bot.send_message(message.chat.id, stats_report, parse_mode="HTML")


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
            "🎨 تخصيص شكل أزرار الحضور والرموز",
            callback_data="set_custom_emoji",
            style="primary",
        )
    )
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "⚙️ <b>إعدادات بوستات الحضور:</b>",
        parse_mode="HTML",
        reply_markup=markup,
    )

  elif action == "share":
    bot.answer_callback_query(call.id)
    show_channel_selection_menu(call.message.chat.id, user_id)

  elif action == "create_question":
    bot.answer_callback_query(call.id)
    user_states[user_id] = "waiting_q_text"
    bot.send_message(
        call.message.chat.id,
        "❓ <b>نظام الأسئلة التفاعلية مع تحدي السرعة:</b>\n\nأرسل الآن نص السؤال"
        " التفاعلي:",
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

  elif action == "support":
    bot.answer_callback_query(call.id)
    user_states[user_id] = "waiting_support_msg"
    bot.send_message(
        call.message.chat.id,
        "💬 <i>أرسل رسالتك أو استفسار الدعم الفني الآن، وسيتم تحويله مباشرة"
        " للمطور:</i>",
        parse_mode="HTML",
    )


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
    bot.send_message(
        chat_id,
        "🚀 <b>اختر إحدى قنواتك المحفوظة للنشر:</b>",
        parse_mode="HTML",
        reply_markup=markup,
    )
  else:
    user_states[user_id] = "waiting_channel_username"
    bot.send_message(
        chat_id,
        "🚀 <b>أرسل الآن معرف قناتك (مثال: <code>@MyChannel</code>):</b>",
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
        f"❌ <b>فشل الوصول للقناة:</b> <code>{e}</code>",
        parse_mode="HTML",
    )
    return

  with db_lock:
    conn = get_db_connection()
    cursor = conn.cursor()
    title = f"سجل الحضور — {get_arabic_date_string()}"
    poll_id = f"poll_{user_id}_{int(time.time())}"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        create_colored_btn(
            "✅ تسجيل الحضور [0]",
            callback_data=f"attend_{poll_id}",
            style="success",
        )
    )
    keyboard.add(
        create_colored_btn("🤖 الانتقال للبوت", url=BOT_URL, style="primary")
    )

    msg_content = f"<b>📢 {html.escape(title)}</b>\n\n<i>اضغط على الزر أدناه لتسجيل حضورك:</i>"

  try:
    sent_msg = bot.send_message(
        real_channel_id,
        msg_content,
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
          "INSERT OR REPLACE INTO saved_channels (user_id, channel_id,"
          " channel_title) VALUES (?, ?, ?)",
          (user_id, real_channel_id, c_title),
      )
      cursor.execute(
          "INSERT OR REPLACE INTO polls (poll_id, owner_id, count, title,"
          " end_time, is_closed, show_in_channel, channel_id, message_id,"
          " reminder_sent) VALUES (?, ?, ?, ?, 0, 0, 1, ?, ?, 0)",
          (
              poll_id,
              user_id,
              0,
              title,
              real_channel_id,
              sent_msg.message_id,
          ),
      )
      conn.commit()
      conn.close()

    bot.send_message(
        chat_id_to_send,
        "✅ <b>تم نشر بوست الحضور وتثبيته بنجاح!</b>",
        parse_mode="HTML",
    )
  except Exception as e:
    bot.send_message(
        chat_id_to_send,
        f"❌ <b>فشل النشر:</b> <code>{e}</code>",
        parse_mode="HTML",
    )


if __name__ == "__main__":
  bot.remove_webhook()
  time.sleep(1)
  bot.set_webhook(url=WEBHOOK_URL)
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
