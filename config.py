import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_URL = os.getenv('API_URL')
API_KEY = os.getenv('API_KEY')

# Owner & Admin IDs
OWNER_IDS = [8187995105]  # 👑 Owner (Full Control + Unlimited)
ADMIN_IDS = [8344394855]   # Admins (Limited Control)

# Wordlist System
WORDLIST_FOLDER = "collected_wordlists"
REQUIRED_UNIQUE = 500
CREDIT_REWARD = 1
COOLDOWN_SECONDS = 30
MAX_WORDS_PER_FILE = 5000

# Database
DATABASE_FILE = "osint_bot.db"