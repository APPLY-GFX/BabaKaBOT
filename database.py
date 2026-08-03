import sqlite3
from datetime import datetime, timedelta
from config import DATABASE_FILE, OWNER_IDS

class Database:
    def __init__(self):
        self.db_file = DATABASE_FILE
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_file, timeout=20)
    
    def init_db(self):
        conn = self.get_connection()
        c = conn.cursor()
        
        # USERS TABLE - Updated with more fields
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            subscription_end TEXT,
            tokens INTEGER DEFAULT 1,
            registration_date TEXT,
            total_requests INTEGER DEFAULT 0,
            last_daily_claim TEXT,
            last_token_reset TEXT,
            is_banned INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        )''')
        
        # REDEEM CODES TABLE
        c.execute('''CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            duration_days REAL,
            created_by INTEGER,
            created_at TEXT,
            used_by INTEGER,
            used_at TEXT,
            is_used INTEGER DEFAULT 0
        )''')
        
        # SEARCH HISTORY TABLE
        c.execute('''CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query TEXT,
            search_type TEXT,
            result_count INTEGER,
            timestamp TEXT
        )''')
        
        conn.commit()
        conn.close()
        print("✅ Database initialized")
    
    # ============ USER METHODS ============
    
    def get_user(self, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
        conn.close()
        return user
    
    def get_user_by_username(self, username):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        return user
    
    def create_user(self, user_id, username, first_name, last_name):
        conn = self.get_connection()
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""INSERT OR IGNORE INTO users 
                     (user_id, username, first_name, last_name, 
                      subscription_end, tokens, registration_date, 
                      last_token_reset)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (user_id, username, first_name, last_name,
                   now, 1, now, now))
        conn.commit()
        conn.close()
    
    def update_user(self, user_id, **kwargs):
        """Update user fields"""
        conn = self.get_connection()
        c = conn.cursor()
        for key, value in kwargs.items():
            c.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
        conn.commit()
        conn.close()
    
    def delete_user(self, user_id):
        """Delete user from database"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def get_all_users(self):
        """Get all users"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT user_id, username, first_name, last_name, subscription_end, tokens FROM users")
        users = c.fetchall()
        conn.close()
        return users
    
    def get_user_count(self):
        """Get total user count"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        count = c.fetchone()[0]
        conn.close()
        return count
    
    def get_premium_count(self):
        """Get premium user count"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')")
        count = c.fetchone()[0]
        conn.close()
        return count
    
    # ============ TOKEN METHODS ============
    
    def is_owner(self, user_id):
        """Check if user is owner"""
        return user_id in OWNER_IDS
    
    def is_premium(self, user_id):
        """Check premium status - Owner always premium"""
        if self.is_owner(user_id):
            return True
        
        user = self.get_user(user_id)
        if user and user[4]:
            try:
                sub_end = datetime.strptime(user[4], "%Y-%m-%d %H:%M:%S")
                return sub_end > datetime.now()
            except:
                pass
        return False
    
    def get_tokens(self, user_id):
        """Get tokens - Owner gets unlimited"""
        if self.is_owner(user_id):
            return 999999  # Unlimited for owner
        
        user = self.get_user(user_id)
        return user[5] if user else 0
    
    def update_tokens(self, user_id, tokens):
        """Update tokens"""
        if self.is_owner(user_id):
            return True  # Owner tokens can't be changed
        
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET tokens = ? WHERE user_id = ?", (tokens, user_id))
        conn.commit()
        conn.close()
    
    def deduct_token(self, user_id):
        """Deduct one token - Owner no deduction"""
        if self.is_owner(user_id):
            return True
        
        tokens = self.get_tokens(user_id)
        if tokens > 0:
            self.update_tokens(user_id, tokens - 1)
            return True
        return False
    
    def add_tokens(self, user_id, amount):
        """Add tokens to user"""
        if self.is_owner(user_id):
            return True
        
        tokens = self.get_tokens(user_id)
        self.update_tokens(user_id, tokens + amount)
        return True
    
    # ============ DAILY BONUS ============
    
    def claim_daily(self, user_id):
        """Claim daily bonus"""
        if self.is_owner(user_id):
            return True, "Owner - Unlimited"
        
        conn = self.get_connection()
        c = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        
        c.execute("SELECT last_daily_claim FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        
        if result and result[0]:
            last_claim = result[0].split()[0]
            if last_claim == today:
                conn.close()
                return False, "Already claimed today"
        
        c.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
        current = c.fetchone()[0]
        new_tokens = current + 1
        
        c.execute("UPDATE users SET tokens = ?, last_daily_claim = ? WHERE user_id = ?",
                  (new_tokens, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
        conn.commit()
        conn.close()
        return True, new_tokens
    
    # ============ SEARCH HISTORY ============
    
    def add_search_history(self, user_id, query, search_type, result_count):
        """Add search to history"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""INSERT INTO search_history 
                     (user_id, query, search_type, result_count, timestamp) 
                     VALUES (?, ?, ?, ?, ?)""",
                  (user_id, query, search_type, result_count, 
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
    
    def get_search_history(self, user_id, limit=10):
        """Get user search history"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""SELECT query, search_type, result_count, timestamp 
                     FROM search_history WHERE user_id = ? 
                     ORDER BY timestamp DESC LIMIT ?""",
                  (user_id, limit))
        history = c.fetchall()
        conn.close()
        return history
    
    def clear_search_history(self, user_id):
        """Clear user search history"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM search_history WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    # ============ REDEEM CODES ============
    
    def generate_code(self, duration, unit, created_by):
        """Generate redeem code"""
        import random, string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        conn = self.get_connection()
        c = conn.cursor()
        duration_days = duration if unit == 'days' else duration / 24
        c.execute("""INSERT INTO redeem_codes 
                     (code, duration_days, created_by, created_at) 
                     VALUES (?, ?, ?, ?)""",
                  (code, duration_days, created_by, 
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        return code
    
    def redeem_code(self, code, user_id):
        """Redeem a code"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM redeem_codes WHERE code = ? AND is_used = 0", (code,))
        redeem = c.fetchone()
        
        if redeem:
            duration_days = redeem[1]
            if duration_days < 1:
                hours = int(round(duration_days * 24))
                # Add subscription (implement as needed)
                display = f"{hours} hour(s)"
            else:
                days = int(duration_days)
                # Add subscription (implement as needed)
                display = f"{days} day(s)"
            
            c.execute("UPDATE redeem_codes SET used_by = ?, used_at = ?, is_used = 1 WHERE code = ?",
                      (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), code))
            conn.commit()
            conn.close()
            return True, display
        
        conn.close()
        return False, None
    
    def get_redeem_codes(self, created_by=None):
        """Get all redeem codes"""
        conn = self.get_connection()
        c = conn.cursor()
        if created_by:
            c.execute("SELECT * FROM redeem_codes WHERE created_by = ?", (created_by,))
        else:
            c.execute("SELECT * FROM redeem_codes")
        codes = c.fetchall()
        conn.close()
        return codes

# Global database instance
db = Database()