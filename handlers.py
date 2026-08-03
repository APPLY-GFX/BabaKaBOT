# handlers.py - Updated for python-telegram-bot v20+

import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from api import search_api, extract_records
from formatter import Formatter
from utils import validate_phone, validate_email, validate_ip, detect_search_type, animate_search
from config import ADMIN_IDS, OWNER_IDS

# User modes
user_mode = {}

def get_main_keyboard(user_id=None):
    """Main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🔍 SEARCH", callback_data="search")],
        [InlineKeyboardButton("📋 INFO", callback_data="info")],
        [InlineKeyboardButton("🛍 SHOP", callback_data="shop")],
        [InlineKeyboardButton("🎁 DAILY", callback_data="daily")],
        [InlineKeyboardButton("💰 EARN", callback_data="earn")]
    ]
    
    if user_id and (user_id in ADMIN_IDS or user_id in OWNER_IDS):
        keyboard.append([InlineKeyboardButton("👑 ADMIN", callback_data="admin")])
    
    return InlineKeyboardMarkup(keyboard)

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query, search_type):
    """Execute search and send result"""
    user_id = update.effective_user.id
    message = update.message
    
    # Check premium/tokens
    is_premium = db.is_premium(user_id)
    
    if not is_premium:
        tokens = db.get_tokens(user_id)
        if tokens <= 0:
            await message.reply_text("""
NO CREDITS LEFT

/daily - Free credit
/earn - Earn credits
/shop - Premium plans
""", parse_mode='Markdown')
            return
        
        # Deduct token
        db.update_tokens(user_id, tokens - 1)
    
    # Animate search
    await animate_search(update, context, query)
    
    # Call API
    result = search_api(query)
    
    if result.get('error'):
        await message.reply_text(f"Error: {result['error']}")
        return
    
    # Extract records
    records = extract_records(result)
    
    # Save to history
    db.add_search_history(user_id, query, search_type, len(records))
    
    # Prepare token info
    tokens_info = {
        'is_premium': is_premium,
        'tokens': db.get_tokens(user_id) if not is_premium else None
    }
    
    # Format output
    formatted = Formatter.format_result(result, query, tokens_info)
    
    # Send response
    if len(formatted) > 4096:
        for i in range(0, len(formatted), 4096):
            await message.reply_text(formatted[i:i+4096], parse_mode='Markdown')
    else:
        await message.reply_text(formatted, parse_mode='Markdown')

# ============ COMMAND HANDLERS (Async) ============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start handler"""
    user = update.effective_user
    user_id = user.id
    
    # Create user if not exists
    if not db.get_user(user_id):
        db.create_user(user_id, user.username or "", user.first_name or "", user.last_name or "")
    
    welcome = """
HACKERS DB - OSINT TOOL

COMMANDS:
/num 91xxxxxxxxxx     Phone lookup
/email email@domain   Email lookup
/name Full Name       Name search
/ip 192.168.1.1       IP lookup
/location City, State  Location search
/aadhaar 12digits     Aadhaar lookup
/pan ABCDE1234F       PAN lookup

ACCOUNT:
/profile             Your info
/daily               Free credit
/earn                Earn credits
/redeem CODE         Redeem premium

PREMIUM:
/shop               View plans
/status             Check tokens

Support: @Rahul_Neoo
"""
    await update.message.reply_text(welcome, parse_mode='Markdown',
                                   reply_markup=get_main_keyboard(user_id))

async def num_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/num handler"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("""
INVALID FORMAT

Usage: /num 91xxxxxxxxxx
Example: /num 919834124648
""", parse_mode='Markdown')
        return
    
    query = args[0].strip()
    valid, processed = validate_phone(query)
    
    if not valid:
        await update.message.reply_text("""
INVALID NUMBER

Use: 91 + 10 digits
Example: /num 919834124648
""", parse_mode='Markdown')
        return
    
    await perform_search(update, context, processed, 'phone')

async def email_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/email handler"""
    args = context.args
    if not args:
        await update.message.reply_text("""
INVALID FORMAT

Usage: /email example@gmail.com
""", parse_mode='Markdown')
        return
    
    query = args[0].strip()
    if not validate_email(query):
        await update.message.reply_text("""
INVALID EMAIL

Enter valid email address
""", parse_mode='Markdown')
        return
    
    await perform_search(update, context, query, 'email')

async def name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/name handler"""
    args = ' '.join(context.args) if context.args else ''
    if not args or len(args) < 3:
        await update.message.reply_text("""
INVALID FORMAT

Usage: /name Full Name
Example: /name Amit Kumar
""", parse_mode='Markdown')
        return
    
    await perform_search(update, context, args, 'name')

async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ip handler"""
    from utils import validate_ip
    args = context.args
    if not args:
        await update.message.reply_text("""
INVALID FORMAT

Usage: /ip 192.168.1.1
""", parse_mode='Markdown')
        return
    
    query = args[0].strip()
    if not validate_ip(query):
        await update.message.reply_text("""
INVALID IP

Enter valid IPv4 address
""", parse_mode='Markdown')
        return
    
    await perform_search(update, context, query, 'ip')

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/profile handler"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user:
        await update.message.reply_text("Please /start first")
        return
    
    is_premium = db.is_premium(user_id)
    tokens = db.get_tokens(user_id)
    
    profile = f"""
ACCOUNT INFO
━━━━━━━━━━━━━━━━━━━━━━━━
ID: {user_id}
Name: {user[2] or 'Not set'} {user[3] or ''}
Username: @{update.effective_user.username or 'Not set'}

Status: {'Premium' if is_premium else 'Free'}
Credits: {'Unlimited' if is_premium else tokens}
Requests: {user[8] if user else 0}

Registered: {user[6] if user else 'Unknown'}
━━━━━━━━━━━━━━━━━━━━━━━━
/daily - Free credit
/shop - Premium plans
"""
    await update.message.reply_text(profile, parse_mode='Markdown')

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/daily handler"""
    user_id = update.effective_user.id
    
    if db.is_premium(user_id):
        await update.message.reply_text("""
PREMIUM USER

Unlimited access
No daily credit needed
""", parse_mode='Markdown')
        return
    
    success, result = db.claim_daily(user_id)
    
    if success:
        await update.message.reply_text(f"""
DAILY CREDIT CLAIMED

+1 Credit Added
Total: {result} credits

Next claim: Tomorrow
""", parse_mode='Markdown')
    else:
        await update.message.reply_text("""
ALREADY CLAIMED TODAY

Come back tomorrow
Or upgrade: /shop
""", parse_mode='Markdown')

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/redeem handler"""
    args = context.args
    if not args:
        await update.message.reply_text("""
INVALID FORMAT

Usage: /redeem CODE
Example: /redeem ABC123XYZ789
""", parse_mode='Markdown')
        return
    
    code = args[0].strip().upper()
    success, display = db.redeem_code(code, update.effective_user.id)
    
    if success:
        await update.message.reply_text(f"""
REDEEM SUCCESSFUL

Upgraded: {display}
Now: Unlimited searches
""", parse_mode='Markdown')
    else:
        await update.message.reply_text("""
INVALID CODE

Code not found or already used
Contact: @Rahul_Neoo
""", parse_mode='Markdown')

async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/shop handler"""
    shop = """
PREMIUM PLANS
━━━━━━━━━━━━━━━━━━━━━━━━
1 Hour      - ₹49
1 Day       - ₹249
15 Days     - ₹999
30 Days     - ₹1499

FEATURES:
• Unlimited searches
• All commands
• Priority support
• No daily limits

Contact: @Rahul_Neoo
Have code? /redeem CODE
"""
    await update.message.reply_text(shop, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status handler"""
    user_id = update.effective_user.id
    is_premium = db.is_premium(user_id)
    tokens = db.get_tokens(user_id)
    user = db.get_user(user_id)
    
    status = f"""
STATUS
━━━━━━━━━━━━━━━━━━━━━━━━
Type: {'Premium' if is_premium else 'Free'}
Credits: {'Unlimited' if is_premium else tokens}
Requests: {user[8] if user else 0}
━━━━━━━━━━━━━━━━━━━━━━━━
/daily - Free credit
/earn - Earn credits
/shop - Premium plans
"""
    await update.message.reply_text(status, parse_mode='Markdown')

async def earn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/earn handler"""
    user_id = update.effective_user.id
    user_mode[user_id] = 'earn'
    
    await update.message.reply_text("""
EARN FREE CREDITS

Send .txt file (1 word per line)
500 unique words = 1 credit

Click BACK TO MAIN to exit
""", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help handler"""
    await start_command(update, context)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Skip commands and buttons
    if text.startswith('/'):
        return
    
    # Skip button texts
    buttons = ["🔍 SEARCH", "📋 INFO", "🛍 SHOP", "🔮 REDEEM", "🎁 DAILY", "💰 EARN", "👑 ADMIN", "❌ CANCEL", "◀️ BACK TO MAIN"]
    if text in buttons:
        return
    
    # Check earn mode
    if user_mode.get(user_id) == 'earn':
        await update.message.reply_text("Send .txt file or click BACK TO MAIN")
        return
    
    # Auto-detect and search
    search_type, query = detect_search_type(text)
    await perform_search(update, context, query, search_type)

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads (for earn mode)"""
    user_id = update.effective_user.id
    document = update.message.document
    
    if not document or not document.file_name.endswith('.txt'):
        await update.message.reply_text("Send .txt file only")
        return
    
    if user_mode.get(user_id) != 'earn':
        await update.message.reply_text("Use /earn first")
        return
    
    # Process file (simplified)
    await update.message.reply_text(f"Processing {document.file_name}...")

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to main menu"""
    user_id = update.effective_user.id
    user_mode[user_id] = None
    await update.message.reply_text("Main Menu", reply_markup=get_main_keyboard(user_id))