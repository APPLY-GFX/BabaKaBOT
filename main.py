#!/usr/bin/env python3
"""
HACKERS DB - OSINT BOT v3.0
Professional OSINT Telegram Bot with All Features
"""

import logging
import telebot
from telebot import types
from config import BOT_TOKEN, ADMIN_IDS, OWNER_IDS
from database import db
from api import search_api, extract_records
from formatter import Formatter
from utils import validate_phone, validate_email, validate_ip, detect_search_type
import re
import time
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

# ============ CONFIGURATION ============

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN)
user_mode = {}
db_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=5)

# ============ SMART LINE FUNCTION ============

def make_line(text=None, char="─"):
    """Smart line - sirf text ke hisaab se"""
    if text:
        length = len(text) + 4
    else:
        length = 30
    return char * length

# ============ SPAM PROTECTION ============

RATE_LIMIT = {
    'max_requests': 10,
    'time_window': 60,
    'cooldown': 30,
}

user_requests = {}
user_cooldown = {}

def is_rate_limited(user_id):
    current_time = time.time()
    
    if user_id in user_cooldown:
        if current_time < user_cooldown[user_id]:
            return True, int(user_cooldown[user_id] - current_time)
        else:
            del user_cooldown[user_id]
    
    if user_id not in user_requests:
        user_requests[user_id] = []
    
    cutoff = current_time - RATE_LIMIT['time_window']
    user_requests[user_id] = [t for t in user_requests[user_id] if t > cutoff]
    
    if len(user_requests[user_id]) >= RATE_LIMIT['max_requests']:
        user_cooldown[user_id] = current_time + RATE_LIMIT['cooldown']
        return True, RATE_LIMIT['cooldown']
    
    user_requests[user_id].append(current_time)
    return False, 0

def rate_limited_handler(func):
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        limited, wait_time = is_rate_limited(user_id)
        if limited:
            bot.reply_to(message, f"⏰ Please wait {wait_time} seconds")
            return
        return func(message, *args, **kwargs)
    return wrapper

# ============ SET MENU COMMANDS ============

def set_commands():
    commands = [
        types.BotCommand("start", "🚀 Start"),
        types.BotCommand("help", "📖 Help"),
        types.BotCommand("profile", "👤 Profile"),
        types.BotCommand("num", "📱 Phone lookup"),
        types.BotCommand("name", "👤 Name search"),
        types.BotCommand("location", "📍 Location"),
        types.BotCommand("ip", "🌐 IP lookup"),
        types.BotCommand("aadhaar", "🆔 Aadhaar"),
        types.BotCommand("daily", "🎁 Free credit"),
        types.BotCommand("earn", "💰 Earn credits"),
        types.BotCommand("redeem", "🔮 Redeem"),
        types.BotCommand("shop", "🛍 Plans"),
        types.BotCommand("status", "📊 Status"),
        types.BotCommand("history", "📜 History"),
        types.BotCommand("osint", "🔍 OSINT menu"),
    ]
    bot.set_my_commands(commands)
    logger.info("✅ Commands menu set!")

set_commands()

# ============ KEYBOARDS ============

def get_main_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        types.KeyboardButton("🔍 SEARCH"),
        types.KeyboardButton("📋 OSINT MENU"),
        types.KeyboardButton("👤 PROFILE"),
        types.KeyboardButton("🛍 SHOP"),
        types.KeyboardButton("🎁 DAILY"),
        types.KeyboardButton("💰 EARN"),
        types.KeyboardButton("📜 HISTORY"),
    ]
    if user_id and (user_id in ADMIN_IDS or user_id in OWNER_IDS):
        buttons.append(types.KeyboardButton("👑 ADMIN"))
    markup.add(*buttons)
    return markup

def get_osint_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        types.KeyboardButton("📱 PHONE"),
        types.KeyboardButton("👤 NAME"),
        types.KeyboardButton("📍 LOCATION"),
        types.KeyboardButton("🌐 IP"),
        types.KeyboardButton("🆔 AADHAAR"),
        types.KeyboardButton("◀️ BACK"),
    ]
    markup.add(*buttons)
    return markup

def get_earn_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    markup.add(types.KeyboardButton("◀️ BACK"))
    return markup

# ============ SEARCH FUNCTION ============

def perform_search(message, query, search_type):
    user_id = message.from_user.id
    logger.info(f"🔍 Search: {query} | Type: {search_type} | User: {user_id}")
    
    try:
        with db_lock:
            user = db.get_user(user_id)
            if not user:
                db.create_user(user_id, "", "", "")
            
            is_premium = db.is_premium(user_id)
            tokens = db.get_tokens(user_id)
        
        if not is_premium:
            if tokens <= 0:
                bot.reply_to(message, "❌ No credits! Use /daily")
                return
            with db_lock:
                db.update_tokens(user_id, tokens - 1)
        
        animate_search(message, query)
        result = search_api(query)
        
        if result.get('error'):
            bot.reply_to(message, f"❌ Error: {result['error']}")
            return
        
        records = extract_records(result)
        
        with db_lock:
            db.add_search_history(user_id, query, search_type, len(records))
        
        tokens_info = {
            'is_premium': is_premium,
            'tokens': db.get_tokens(user_id) if not is_premium else None
        }
        
        formatted = Formatter.format_result(result, query, tokens_info)
        
        if len(formatted) > 4096:
            for i in range(0, len(formatted), 4096):
                bot.send_message(message.chat.id, formatted[i:i+4096], parse_mode='Markdown')
        else:
            bot.reply_to(message, formatted, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"❌ Search error: {e}")
        bot.reply_to(message, "❌ Error occurred. Try again.")

def animate_search(message, query):
    try:
        frames = ["⏳ Searching.", "⏳ Searching..", "⏳ Searching..."]
        msg = bot.reply_to(message, f"{frames[0]} `{query}`", parse_mode='Markdown')
        for frame in frames[1:]:
            time.sleep(0.1)
            try:
                bot.edit_message_text(f"{frame} `{query}`", 
                                    msg.chat.id, msg.message_id, 
                                    parse_mode='Markdown')
            except:
                pass
    except:
        pass

# ============ START COMMAND ============

@bot.message_handler(commands=['start'])
def start_command(message):
    try:
        user = message.from_user
        user_id = user.id
        
        with db_lock:
            if not db.get_user(user_id):
                db.create_user(user_id, user.username or "", user.first_name or "", user.last_name or "")
        
        welcome = f"""
🚀 HACKERS DB - OSINT TOOL v3.0
{make_line("HACKERS DB - OSINT TOOL v3.0")}

📌 WORKING COMMANDS

📱 /num 91xxxxxxxxxx     Phone lookup
👤 /name Full Name       Name search
📍 /location City, State Location search
🌐 /ip 192.168.1.1       IP lookup
🆔 /aadhaar 12digits     Aadhaar lookup

👤 ACCOUNT
/profile                 Your info
/daily                   Free credit
/earn                    Earn credits
/redeem CODE             Redeem premium
/history                 Search history

🛍 PREMIUM
/shop                    View plans
/status                  Check tokens

💡 Click 📋 OSINT MENU for all options
📞 Support: @TorProtest
"""
        bot.reply_to(message, welcome, parse_mode='Markdown',
                    reply_markup=get_main_keyboard(user_id))
        logger.info(f"✅ Start command: {user_id}")
    except Exception as e:
        logger.error(f"❌ Start error: {e}")
        bot.reply_to(message, "❌ Error starting bot.")

# ============ HELP COMMAND ============

@bot.message_handler(commands=['help'])
def help_command(message):
    try:
        help_text = f"""
📖 HELP - HACKERS DB OSINT TOOL
{make_line("HELP - HACKERS DB OSINT TOOL")}

🔍 SEARCH COMMANDS

📱 /num 91xxxxxxxxxx     Phone lookup
👤 /name Full Name       Name search
📍 /location City, State Location search
🌐 /ip 192.168.1.1       IP lookup
🆔 /aadhaar 12digits     Aadhaar lookup

👤 ACCOUNT COMMANDS
/profile                 Your info
/daily                   Free credit
/earn                    Earn credits
/redeem CODE             Redeem premium
/history                 Search history

🛍 PREMIUM COMMANDS
/shop                    View plans
/status                  Check tokens

💡 Use /osint for menu
📞 Support: @TorProtest
"""
        bot.reply_to(message, help_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Help error: {e}")
        bot.reply_to(message, "❌ Error showing help.")

# ============ OSINT MENU ============

@bot.message_handler(commands=['osint'])
def osint_command(message):
    try:
        menu = f"""
🔍 OSINT SEARCH MENU
{make_line("OSINT SEARCH MENU")}

📱 PHONE       - Phone number lookup
👤 NAME        - Person name search
📍 LOCATION    - Location search
🌐 IP          - IP address lookup
🆔 AADHAAR     - Aadhaar number lookup

💡 Select an option below
"""
        bot.reply_to(message, menu, parse_mode='Markdown',
                    reply_markup=get_osint_keyboard())
    except Exception as e:
        logger.error(f"❌ OSINT menu error: {e}")
        bot.reply_to(message, "❌ Error loading menu.")

@bot.message_handler(func=lambda message: message.text == "📋 OSINT MENU")
def osint_menu_handler(message):
    osint_command(message)

@bot.message_handler(func=lambda message: message.text == "◀️ BACK")
def back_to_main(message):
    user_id = message.from_user.id
    user_mode[user_id] = None
    bot.reply_to(message, "🏠 Main Menu", reply_markup=get_main_keyboard(user_id))

@bot.message_handler(func=lambda message: message.text == "📱 PHONE")
def phone_menu_handler(message):
    bot.reply_to(message, "📱 Enter phone number:\n91xxxxxxxxxx or xxxxxxxxxx")

@bot.message_handler(func=lambda message: message.text == "👤 NAME")
def name_menu_handler(message):
    bot.reply_to(message, "👤 Enter full name:\nExample: Amit Kumar")

@bot.message_handler(func=lambda message: message.text == "📍 LOCATION")
def location_menu_handler(message):
    bot.reply_to(message, "📍 Enter location:\nExample: Mumbai, Maharashtra")

@bot.message_handler(func=lambda message: message.text == "🌐 IP")
def ip_menu_handler(message):
    bot.reply_to(message, "🌐 Enter IP address:\nExample: 192.168.1.1")

@bot.message_handler(func=lambda message: message.text == "🆔 AADHAAR")
def aadhaar_menu_handler(message):
    bot.reply_to(message, "🆔 Enter Aadhaar number:\n12 digits only\nExample: 424964825085")

# ============ COMMAND HANDLERS ============

@bot.message_handler(commands=['num', 'phone'])
@rate_limited_handler
def num_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "📱 Use: /num 91xxxxxxxxxx")
        return
    
    query = args[1].strip()
    if not re.fullmatch(r'91\d{10}', query):
        bot.reply_to(message, "❌ Invalid! Use: 91 + 10 digits")
        return
    
    executor.submit(perform_search, message, query, 'phone')

@bot.message_handler(commands=['name'])
@rate_limited_handler
def name_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "👤 Use: /name Full Name")
        return
    
    query = args[1].strip()
    if len(query) < 3 or not re.match(r'^[a-zA-Z\s\.]+$', query):
        bot.reply_to(message, "❌ Invalid name! Use letters only, min 3 chars")
        return
    
    executor.submit(perform_search, message, query, 'name')

@bot.message_handler(commands=['location', 'loc'])
@rate_limited_handler
def location_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "📍 Use: /location City, State")
        return
    
    query = args[1].strip()
    if len(query) < 3:
        bot.reply_to(message, "❌ Location too short!")
        return
    
    executor.submit(perform_search, message, query, 'location')

@bot.message_handler(commands=['ip'])
@rate_limited_handler
def ip_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "🌐 Use: /ip 192.168.1.1")
        return
    
    query = args[1].strip()
    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', query):
        bot.reply_to(message, "❌ Invalid IP!")
        return
    
    parts = query.split('.')
    if not all(0 <= int(p) <= 255 for p in parts):
        bot.reply_to(message, "❌ Invalid IP!")
        return
    
    executor.submit(perform_search, message, query, 'ip')

@bot.message_handler(commands=['aadhaar', 'uid'])
@rate_limited_handler
def aadhaar_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "🆔 Use: /aadhaar 12digits")
        return
    
    query = args[1].strip().replace(' ', '')
    if not re.fullmatch(r'\d{12}', query):
        bot.reply_to(message, "❌ Invalid Aadhaar! Use 12 digits")
        return
    
    executor.submit(perform_search, message, query, 'aadhaar')

# ============ ACCOUNT COMMANDS ============

@bot.message_handler(commands=['profile'])
def profile_command(message):
    try:
        user_id = message.from_user.id
        
        with db_lock:
            user = db.get_user(user_id)
            if not user:
                bot.reply_to(message, "❌ Please /start first")
                return
            
            is_premium = db.is_premium(user_id)
            is_owner = db.is_owner(user_id)
            tokens = db.get_tokens(user_id)
        
        status = "👑 OWNER" if is_owner else "💎 PREMIUM" if is_premium else "📄 FREE"
        credits = "♾️ Unlimited" if is_owner or is_premium else str(tokens)
        
        profile = f"""
👤 PROFILE
{make_line("PROFILE")}

ID: `{user_id}`
Name: {user[2] or 'Not set'}
Username: @{message.from_user.username or 'Not set'}

Status: {status}
Credits: {credits}
Searches: {user[8] if user else 0}
"""
        bot.reply_to(message, profile, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Profile error: {e}")
        bot.reply_to(message, "❌ Error loading profile.")

@bot.message_handler(commands=['daily'])
def daily_command(message):
    user_id = message.from_user.id
    
    with db_lock:
        if db.is_premium(user_id):
            bot.reply_to(message, "💎 Premium - Unlimited!")
            return
        
        success, result = db.claim_daily(user_id)
    
    if success:
        bot.reply_to(message, f"✅ +1 Credit! Total: {result}")
    else:
        bot.reply_to(message, "⏰ Already claimed today!")

@bot.message_handler(commands=['redeem'])
def redeem_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "🔮 Use: /redeem CODE")
        return
    
    code = args[1].strip().upper()
    
    with db_lock:
        success, display = db.redeem_code(code, message.from_user.id)
    
    if success:
        bot.reply_to(message, f"✅ Redeemed! {display}")
    else:
        bot.reply_to(message, "❌ Invalid code!")

@bot.message_handler(commands=['shop'])
def shop_command(message):
    shop = f"""
🛍 PREMIUM PLANS
{make_line("PREMIUM PLANS")}

⏱️ 1 Hour      - ₹49
📅 1 Day       - ₹249
📆 15 Days     - ₹999
🗓️ 30 Days     - ₹1499

✨ FEATURES
• Unlimited searches
• All commands available
• Priority support
• No daily limits

📞 Contact: @TorProtest
Have code? /redeem CODE
"""
    bot.reply_to(message, shop, parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def status_command(message):
    user_id = message.from_user.id
    
    with db_lock:
        is_premium = db.is_premium(user_id)
        tokens = db.get_tokens(user_id)
        user = db.get_user(user_id)
    
    status = f"""
📊 STATUS
{make_line("STATUS")}

Type: {'💎 Premium' if is_premium else '📄 Free'}
Credits: {'♾️ Unlimited' if is_premium else tokens}
Searches: {user[8] if user else 0}
"""
    bot.reply_to(message, status, parse_mode='Markdown')

@bot.message_handler(commands=['earn'])
def earn_command(message):
    user_id = message.from_user.id
    user_mode[user_id] = 'earn'
    bot.reply_to(message, "💰 Send .txt file (1 word/line)", reply_markup=get_earn_keyboard())

@bot.message_handler(commands=['history'])
def history_command(message):
    user_id = message.from_user.id
    
    with db_lock:
        history = db.get_search_history(user_id, 10)
    
    if not history:
        bot.reply_to(message, "📭 No search history")
        return
    
    msg = f"📜 SEARCH HISTORY\n{make_line('SEARCH HISTORY')}\n\n"
    for idx, (query, search_type, count, timestamp) in enumerate(history, 1):
        msg += f"{idx}. `{query}` ({search_type}) - {count} results\n"
        msg += f"   📅 {timestamp}\n\n"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

# ============ BUTTON HANDLERS ============

@bot.message_handler(func=lambda message: message.text == "🔍 SEARCH")
def search_button_handler(message):
    bot.reply_to(message, "📱 Send: 91 + 10 digits or use /num")

@bot.message_handler(func=lambda message: message.text == "👤 PROFILE")
def profile_button_handler(message):
    profile_command(message)

@bot.message_handler(func=lambda message: message.text == "🛍 SHOP")
def shop_button_handler(message):
    shop_command(message)

@bot.message_handler(func=lambda message: message.text == "🎁 DAILY")
def daily_button_handler(message):
    daily_command(message)

@bot.message_handler(func=lambda message: message.text == "💰 EARN")
def earn_button_handler(message):
    earn_command(message)

@bot.message_handler(func=lambda message: message.text == "📜 HISTORY")
def history_button_handler(message):
    history_command(message)

@bot.message_handler(func=lambda message: message.text == "👑 ADMIN")
def admin_button_handler(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS and user_id not in OWNER_IDS:
        bot.reply_to(message, "❌ Access Denied!")
        return
    
    admin_msg = f"""
👑 ADMIN PANEL
{make_line("ADMIN PANEL")}

📊 /stats     - Statistics
👥 /users     - All users
🎫 /gen       - Generate code
💎 /addtokens - Add tokens
🚫 /ban       - Ban user
✅ /unban     - Unban user

📌 Usage
/gen 1day
/addtokens USER_ID AMOUNT
/ban USER_ID
"""
    bot.reply_to(message, admin_msg, parse_mode='Markdown')

# ============ ADMIN COMMANDS ============

@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS and user_id not in OWNER_IDS:
        bot.reply_to(message, "❌ Access Denied!")
        return
    
    admin_msg = f"""
👑 ADMIN PANEL
{make_line("ADMIN PANEL")}

📊 /stats     - Statistics
👥 /users     - All users
🎫 /gen       - Generate code
💎 /addtokens - Add tokens
🚫 /ban       - Ban user
✅ /unban     - Unban user
"""
    bot.reply_to(message, admin_msg, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def stats_command(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS and user_id not in OWNER_IDS:
        bot.reply_to(message, "❌ Access Denied!")
        return
    
    with db_lock:
        total_users = db.get_user_count()
        premium_users = db.get_premium_count()
        
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT SUM(total_requests) FROM users")
        total_requests = c.fetchone()[0] or 0
        conn.close()
    
    stats = f"""
📊 BOT STATISTICS
{make_line("BOT STATISTICS")}

👥 Total Users: {total_users}
💎 Premium: {premium_users}
📄 Free: {total_users - premium_users}
🔍 Total Searches: {total_requests}
"""
    bot.reply_to(message, stats, parse_mode='Markdown')

@bot.message_handler(commands=['users'])
def users_command(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS and user_id not in OWNER_IDS:
        bot.reply_to(message, "❌ Access Denied!")
        return
    
    with db_lock:
        users = db.get_all_users()
    
    if not users:
        bot.reply_to(message, "No users found!")
        return
    
    msg = f"👥 USERS LIST\n{make_line('USERS LIST')}\n\n"
    
    for idx, (uid, username, fname, lname, sub_end, tokens) in enumerate(users[:20], 1):
        try:
            is_premium = sub_end and sub_end > datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status = "💎" if is_premium else "📄"
            msg += f"{idx}. {status} `{uid}` - @{username or 'N/A'}\n"
            msg += f"   Tokens: {tokens}\n\n"
        except:
            pass
    
    if len(users) > 20:
        msg += f"... and {len(users) - 20} more"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['addtokens'])
def add_tokens_command(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS and user_id not in OWNER_IDS:
        bot.reply_to(message, "❌ Access Denied!")
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "Usage: /addtokens USER_ID AMOUNT")
        return
    
    try:
        target_id = int(args[1])
        amount = int(args[2])
        
        with db_lock:
            if not db.get_user(target_id):
                bot.reply_to(message, f"❌ User {target_id} not found!")
                return
            
            db.add_tokens(target_id, amount)
            new_tokens = db.get_tokens(target_id)
        
        bot.reply_to(message, f"""
✅ TOKENS ADDED!
{make_line("TOKENS ADDED")}

User: `{target_id}`
Added: +{amount} tokens
Total: {new_tokens} tokens
""", parse_mode='Markdown')
        
    except ValueError:
        bot.reply_to(message, "❌ Invalid USER_ID or AMOUNT!")

@bot.message_handler(commands=['gen'])
def gen_code_command(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS and user_id not in OWNER_IDS:
        bot.reply_to(message, "❌ Access Denied!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: /gen 1hour|1day|15day|30day")
        return
    
    plan = args[1].lower()
    plans = {
        '1hour': (1, 'hours'),
        '1day': (1, 'days'),
        '15day': (15, 'days'),
        '30day': (30, 'days')
    }
    
    if plan not in plans:
        bot.reply_to(message, "❌ Invalid plan!")
        return
    
    duration, unit = plans[plan]
    
    with db_lock:
        code = db.generate_code(duration, unit, user_id)
    
    bot.reply_to(message, f"""
🎫 CODE GENERATED!
{make_line("CODE GENERATED")}

Code: `{code}`
Duration: {duration} {unit}

Send: /redeem {code}
""", parse_mode='Markdown')

@bot.message_handler(commands=['ban'])
def ban_command(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS and user_id not in OWNER_IDS:
        bot.reply_to(message, "❌ Access Denied!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: /ban USER_ID")
        return
    
    try:
        target_id = int(args[1])
        with db_lock:
            db.update_user(target_id, is_banned=1)
        bot.reply_to(message, f"✅ User {target_id} banned!")
    except:
        bot.reply_to(message, "❌ Invalid USER_ID!")

@bot.message_handler(commands=['unban'])
def unban_command(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS and user_id not in OWNER_IDS:
        bot.reply_to(message, "❌ Access Denied!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: /unban USER_ID")
        return
    
    try:
        target_id = int(args[1])
        with db_lock:
            db.update_user(target_id, is_banned=0)
        bot.reply_to(message, f"✅ User {target_id} unbanned!")
    except:
        bot.reply_to(message, "❌ Invalid USER_ID!")

# ============ TEXT HANDLER ============

@bot.message_handler(func=lambda message: True, content_types=['text'])
@rate_limited_handler
def handle_text(message):
    try:
        user_id = message.from_user.id
        text = message.text.strip()
        
        if text.startswith('/'):
            return
        
        buttons = ["🔍 SEARCH", "📋 OSINT MENU", "👤 PROFILE", "🛍 SHOP", 
                   "🎁 DAILY", "💰 EARN", "📜 HISTORY", "👑 ADMIN", "◀️ BACK",
                   "📱 PHONE", "👤 NAME", "📍 LOCATION", "🌐 IP", "🆔 AADHAAR"]
        if text in buttons:
            return
        
        if user_mode.get(user_id) == 'earn':
            bot.reply_to(message, "📄 Send .txt file")
            return
        
        search_type, query = detect_search_type(text)
        
        if search_type == 'unknown':
            bot.reply_to(message, f"""
❌ INVALID INPUT
{make_line("INVALID INPUT")}

📱 Phone: 91xxxxxxxxxx or xxxxxxxxxx
👤 Name: 3+ characters (A-Z only)
📍 Location: City, State
🌐 IP: 192.168.1.1
🆔 Aadhaar: 12 digits

Use /help for commands
""", parse_mode='Markdown')
            return
        
        executor.submit(perform_search, message, query, search_type)
        
    except Exception as e:
        logger.error(f"❌ Text handler error: {e}")

# ============ FILE HANDLER ============

@bot.message_handler(content_types=['document'])
def handle_file(message):
    try:
        user_id = message.from_user.id
        
        if user_mode.get(user_id) != 'earn':
            bot.reply_to(message, "❌ Use /earn first")
            return
        
        document = message.document
        if not document or not document.file_name.endswith('.txt'):
            bot.reply_to(message, "❌ Send .txt file only")
            return
        
        bot.reply_to(message, f"📄 Processing {document.file_name}...")
        
    except Exception as e:
        logger.error(f"❌ File handler error: {e}")
        bot.reply_to(message, "❌ Error processing file.")

# ============ START ============

def main():
    try:
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN not set!")
            return
        
        print("=" * 50)
        print("🔥 HACKERS DB - OSINT BOT v3.0")
        print(f"👑 Owner: {OWNER_IDS}")
        print(f"👥 Admins: {ADMIN_IDS}")
        print("=" * 50)
        print("✅ Bot started successfully!")
        print("🚀 Ready to handle requests...")
        print("🛡️ Spam Protection: ON")
        print("⚠️ Press Ctrl+C to stop")
        
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
        
    except KeyboardInterrupt:
        print("\n⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()