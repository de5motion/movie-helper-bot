import logging
import sqlite3
import re
from datetime import datetime
import requests
from flask import Flask, request, jsonify
import os

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAEGsV68gS860oepV0c1nAxPUkjvBiskWdY"
MAIN_BOT_API_URL = "https://movie-bot-7qmx.onrender.com/add_movie"
API_SECRET = "movie_bot_secret_2024_67890"
ADMIN_ID = 6777360306

# ===== FLASK APP =====
app = Flask(__name__)

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ===== DATABASE =====
def init_db():
    conn = sqlite3.connect('helper_movies.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            message_id INTEGER,
            title TEXT,
            year INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Database initialized")

init_db()

# ===== HELPER FUNCTIONS =====
def send_message(chat_id, text):
    """Send message to Telegram"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logging.error(f"Send error: {e}")

def extract_movie_info(text):
    """Extract title, year (optional), code, description"""
    lines = text.split('\n')
    title = None
    year = None
    code = None
    description = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Extract code
        code_match = re.search(r'(?:Code|Код):?\s*(\d+)', line, re.IGNORECASE)
        if code_match and not code:
            code = code_match.group(1)
            continue
        
        # Extract title with year (e.g., "Movie Title (2024)")
        match = re.match(r'^(.+?)\s*\((\d{4})\)$', line)
        if match and not title:
            title = match.group(1).strip()
            year = int(match.group(2))
            continue
        
        # Extract title without year
        if not title and not code_match and line and not line.startswith(('📝', 'Description', 'Plot')):
            title = line
        
        # Extract description
        if line.startswith(('📝', 'Description', 'Plot')) or (description and line):
            desc_match = re.sub(r'^[📝]*\s*', '', line)
            desc_match = re.sub(r'^(Description|Plot):\s*', '', desc_match, flags=re.IGNORECASE)
            if description:
                description += " " + desc_match
            else:
                description = desc_match
    
    return title, year, code, description[:500]

def add_movie_to_main_bot(code, message_id, title, year, description):
    """Send movie to main bot via API"""
    try:
        data = {
            'secret': API_SECRET,
            'code': code,
            'message_id': message_id,
            'title': title,
            'year': year if year else 0,
            'description': description
        }
        response = requests.post(MAIN_BOT_API_URL, json=data, timeout=30)
        return response.status_code == 200, response.text
    except Exception as e:
        logging.error(f"API error: {e}")
        return False, str(e)

# ===== WEBHOOK =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Handle Telegram webhook"""
    try:
        update = request.get_json()
        if not update:
            return jsonify({'status': 'ok'}), 200
        
        if 'message' in update:
            message = update['message']
            user_id = message['from']['id']
            
            # Check if admin
            if user_id != ADMIN_ID:
                return jsonify({'status': 'ok'}), 200
            
            chat_id = message['chat']['id']
            
            # Handle /start command
            if 'text' in message and message['text'] == '/start':
                send_message(chat_id,
                    "🎬 <b>Movie Helper Bot</b>\n\n"
                    "📌 <b>How to use:</b>\n"
                    "Forward a movie message to this bot\n\n"
                    "<b>Format:</b>\n"
                    "Title (optional year)\n"
                    "Code: 12345\n"
                    "Description (optional)\n\n"
                    "Year is optional - bot will work without it!")
                return jsonify({'status': 'ok'}), 200
            
            # Handle forwarded message
            if 'forward_from_chat' in message:
                original_msg_id = message.get('forward_from_message_id')
                text = message.get('text', '')
                
                if not text:
                    send_message(chat_id, "❌ Please forward a text message.")
                    return jsonify({'status': 'ok'}), 200
                
                # Extract info
                title, year, code, description = extract_movie_info(text)
                
                if not title or not code:
                    error_msg = "❌ Could not extract movie info.\n\n"
                    error_msg += "Make sure the message contains:\n"
                    error_msg += "• Title\n"
                    error_msg += "• Code: <code>12345</code>\n\n"
                    error_msg += f"Found:\nTitle: {title or 'Not found'}\n"
                    error_msg += f"Code: {code or 'Not found'}\n"
                    error_msg += f"Year: {year if year else 'Not found (optional)'}"
                    send_message(chat_id, error_msg)
                    return jsonify({'status': 'ok'}), 200
                
                # Show progress
                year_text = f" ({year})" if year else ""
                send_message(chat_id, f"📥 Processing: <b>{title}{year_text}</b>\n🔑 Code: <code>{code}</code>")
                
                # Save to local database
                conn = sqlite3.connect('helper_movies.db')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO movies (code, message_id, title, year, description)
                    VALUES (?, ?, ?, ?, ?)
                ''', (code, original_msg_id, title, year if year else 0, description))
                conn.commit()
                conn.close()
                
                # Send to main bot
                success, result = add_movie_to_main_bot(code, original_msg_id, title, year, description)
                
                if success:
                    send_message(chat_id,
                        f"✅ <b>Movie Added Successfully!</b>\n\n"
                        f"🎬 {title}{year_text}\n"
                        f"🔑 Code: <code>{code}</code>\n\n"
                        f"💾 Saved to main bot database")
                    logging.info(f"✅ Movie added: {code} - {title}")
                else:
                    send_message(chat_id,
                        f"⚠️ <b>Failed to add movie</b>\n\n"
                        f"Error: {result}\n\n"
                        f"Movie saved locally but not in main bot.")
        
        return jsonify({'status': 'ok'}), 200
        
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/')
def index():
    return "🎬 Helper Bot is running!"

@app.route('/health')
def health():
    """Health check"""
    try:
        conn = sqlite3.connect('helper_movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies")
        count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'movies_count': count,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    
    # Set webhook
    webhook_url = f"https://movie-helper-bot-1.onrender.com/{TOKEN}"
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}")
        logging.info(f"✅ Webhook set to {webhook_url}")
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    
    app.run(host='0.0.0.0', port=port)