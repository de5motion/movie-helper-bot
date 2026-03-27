import logging
import sqlite3
from datetime import datetime
import os
import re
from flask import Flask, request, jsonify
import requests
import traceback

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAGdM3sN3Sfi3zd8T0e_AOeFjhwAczQDyHw"
PRIVATE_CHANNEL = -1003800629563
ADMIN_ID = 123456789  # ЗАМЕНИТЕ НА ВАШ TELEGRAM ID

# ===== IMPORTANT: This bot uses a DIFFERENT webhook path =====
# It will NOT interfere with your main bot because Flask can handle multiple routes
# Your main bot uses: /{TOKEN}
# This helper uses: /helper/{TOKEN}

# ===== INITIALIZE FLASK =====
app = Flask(__name__)

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ===== DATABASE =====
def init_db():
    """Initialize helper database"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        
        # Movies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                message_id INTEGER,
                title TEXT,
                year INTEGER,
                description TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Pending movies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                chat_id INTEGER,
                title TEXT,
                year INTEGER,
                description TEXT,
                date_received TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("Helper database initialized")
    except Exception as e:
        logging.error(f"Database error: {e}")

init_db()

# ===== HELPER FUNCTIONS =====
def send_message(chat_id, text, reply_markup=None):
    """Send message"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logging.error(f"Error sending: {e}")
        return None

def get_message_info(chat_id, message_id):
    """Get message info"""
    url = f"https://api.telegram.org/bot{TOKEN}/getMessage"
    params = {"chat_id": chat_id, "message_id": message_id}
    try:
        response = requests.get(url, params=params, timeout=10)
        return response.json()
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

def forward_message(chat_id, from_chat_id, message_id):
    """Forward message"""
    url = f"https://api.telegram.org/bot{TOKEN}/forwardMessage"
    data = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

def extract_movie_info(text):
    """Extract title and year"""
    title = None
    year = None
    
    patterns = [
        r'(.+?)\s*[\(\-]\s*(\d{4})\s*[\)]',
        r'(.+?)\s+(\d{4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            if len(match.groups()) == 2:
                title = match.group(1).strip()
                year = int(match.group(2))
            break
    
    if not title:
        title = text[:50] if text else "Unknown"
    
    return title, year

def save_movie(code, message_id, title, year, description=""):
    """Save movie to database"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO movies (code, message_id, title, year, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (code.upper(), message_id, title, year, description))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error saving: {e}")
        return False

def get_all_movies():
    """Get all movies"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, message_id, title, year, description FROM movies ORDER BY year DESC")
        movies = cursor.fetchall()
        conn.close()
        return movies
    except Exception as e:
        logging.error(f"Error: {e}")
        return []

def delete_movie(code):
    """Delete movie"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM movies WHERE code = ?", (code.upper(),))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error: {e}")
        return False

# ===== PROCESS UPDATES =====
def process_update(update):
    """Process updates - only for helper bot"""
    try:
        # Handle channel posts
        if "channel_post" in update:
            post = update["channel_post"]
            chat_id = post["chat"]["id"]
            
            if chat_id == PRIVATE_CHANNEL:
                message_id = post["message_id"]
                caption = post.get("caption", "")
                text = post.get("text", "")
                content = caption or text
                
                title, year = extract_movie_info(content)
                code = f"INT{message_id}"
                
                # Save to pending
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO pending_movies (message_id, chat_id, title, year, description)
                    VALUES (?, ?, ?, ?, ?)
                ''', (message_id, chat_id, title, year, content[:500]))
                conn.commit()
                conn.close()
                
                # Notify admin
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ ADD", "callback_data": f"add_{message_id}"},
                            {"text": "❌ SKIP", "callback_data": f"skip_{message_id}"}
                        ],
                        [
                            {"text": "📋 VIEW", "callback_data": f"view_{message_id}"}
                        ]
                    ]
                }
                
                send_message(
                    ADMIN_ID,
                    f"🎬 <b>NEW MOVIE!</b>\n\n"
                    f"📝 Title: {title}\n"
                    f"📅 Year: {year if year else 'Unknown'}\n"
                    f"🆔 Message ID: <code>{message_id}</code>\n"
                    f"🔑 Code: <code>{code}</code>\n\n"
                    f"📄 Preview:\n{content[:150]}",
                    keyboard
                )
                return
        
        # Handle messages
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            
            # Only admin
            if user_id != ADMIN_ID:
                send_message(chat_id, "⛔ Admin only")
                return
            
            if "text" in message:
                text = message["text"].strip()
                
                if text == "/start":
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "📋 ALL MOVIES", "callback_data": "list_all"}],
                            [{"text": "⏳ PENDING", "callback_data": "list_pending"}],
                            [{"text": "🔍 GET MSG INFO", "callback_data": "get_msg_info"}]
                        ]
                    }
                    send_message(
                        chat_id,
                        "<b>🎬 MOVIE ID HELPER</b>\n\n"
                        "<b>Commands:</b>\n"
                        "/list - Show all movies\n"
                        "/pending - Show pending\n"
                        "/get MSG_ID - Get message info\n"
                        "/forward MSG_ID - Forward to you\n"
                        "/add CODE MSG_ID TITLE YEAR - Add movie\n"
                        "/delete CODE - Delete movie\n\n"
                        f"Channel: <code>{PRIVATE_CHANNEL}</code>",
                        keyboard
                    )
                
                elif text == "/list":
                    movies = get_all_movies()
                    if movies:
                        response = "<b>📋 ALL MOVIES:</b>\n\n"
                        for code, msg_id, title, year, desc in movies[:20]:
                            response += f"• <b>{title}</b> ({year})\n"
                            response += f"  Code: <code>{code}</code> | Msg ID: <code>{msg_id}</code>\n\n"
                        send_message(chat_id, response[:4000])
                    else:
                        send_message(chat_id, "No movies")
                
                elif text == "/pending":
                    conn = sqlite3.connect('movies_helper.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, message_id, title, year FROM pending_movies")
                    pending = cursor.fetchall()
                    conn.close()
                    
                    if pending:
                        response = "<b>⏳ PENDING:</b>\n\n"
                        for pid, msg_id, title, year in pending:
                            response += f"• Msg ID: <code>{msg_id}</code> - {title[:40]}\n"
                        send_message(chat_id, response)
                    else:
                        send_message(chat_id, "No pending")
                
                elif text.startswith("/get"):
                    parts = text.split()
                    if len(parts) == 2:
                        try:
                            msg_id = int(parts[1])
                            info = get_message_info(PRIVATE_CHANNEL, msg_id)
                            
                            if info and info.get("ok"):
                                msg = info["result"]
                                content = msg.get("text", msg.get("caption", "No text"))
                                
                                response = (
                                    f"<b>📝 MESSAGE INFO</b>\n\n"
                                    f"Message ID: <code>{msg['message_id']}</code>\n"
                                    f"Date: {datetime.fromtimestamp(msg['date'])}\n"
                                    f"Content: {content[:300]}\n\n"
                                    f"<b>Use in main bot:</b>\n"
                                    f"<code>message_id = {msg['message_id']}</code>"
                                )
                                send_message(chat_id, response)
                            else:
                                send_message(chat_id, f"❌ Message {msg_id} not found")
                        except ValueError:
                            send_message(chat_id, "❌ Invalid ID")
                    else:
                        send_message(chat_id, "Usage: /get MESSAGE_ID")
                
                elif text.startswith("/forward"):
                    parts = text.split()
                    if len(parts) == 2:
                        try:
                            msg_id = int(parts[1])
                            result = forward_message(chat_id, PRIVATE_CHANNEL, msg_id)
                            if result and result.get("ok"):
                                send_message(chat_id, f"✅ Message {msg_id} forwarded!")
                            else:
                                send_message(chat_id, f"❌ Failed")
                        except ValueError:
                            send_message(chat_id, "❌ Invalid ID")
                    else:
                        send_message(chat_id, "Usage: /forward MESSAGE_ID")
                
                elif text.startswith("/add"):
                    parts = text.split(maxsplit=4)
                    if len(parts) >= 5:
                        _, code, msg_id, title, year = parts
                        try:
                            msg_id = int(msg_id)
                            year = int(year)
                            if save_movie(code, msg_id, title, year):
                                send_message(chat_id, f"✅ Added!\nCode: {code}\nMsg ID: {msg_id}")
                            else:
                                send_message(chat_id, "❌ Failed")
                        except ValueError:
                            send_message(chat_id, "❌ Invalid ID or year")
                    else:
                        send_message(chat_id, "Format: /add CODE MESSAGE_ID TITLE YEAR")
                
                elif text.startswith("/delete"):
                    parts = text.split()
                    if len(parts) == 2:
                        if delete_movie(parts[1]):
                            send_message(chat_id, f"✅ Deleted {parts[1]}")
                        else:
                            send_message(chat_id, "❌ Not found")
                    else:
                        send_message(chat_id, "Format: /delete CODE")
        
        # Handle callbacks
        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]
            
            try:
                url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
                requests.post(url, json={"callback_query_id": callback["id"]})
            except:
                pass
            
            if data.startswith("add_"):
                msg_id = int(data.split("_")[1])
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("SELECT title, year, description FROM pending_movies WHERE message_id = ?", (msg_id,))
                result = cursor.fetchone()
                
                if result:
                    title, year, desc = result
                    code = f"INT{msg_id}"
                    save_movie(code, msg_id, title, year, desc)
                    cursor.execute("DELETE FROM pending_movies WHERE message_id = ?", (msg_id,))
                    conn.commit()
                    send_message(chat_id, f"✅ Added!\nCode: {code}\nTitle: {title}")
                conn.close()
            
            elif data.startswith("skip_"):
                msg_id = int(data.split("_")[1])
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("DELETE FROM pending_movies WHERE message_id = ?", (msg_id,))
                conn.commit()
                conn.close()
                send_message(chat_id, f"⏭️ Skipped {msg_id}")
            
            elif data == "list_all":
                movies = get_all_movies()
                if movies:
                    response = "<b>📋 MOVIES:</b>\n\n"
                    for code, msg_id, title, year, desc in movies[:10]:
                        response += f"• {title} ({year}) - <code>{code}</code>\n"
                    send_message(chat_id, response)
            
            elif data == "list_pending":
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("SELECT message_id, title FROM pending_movies")
                pending = cursor.fetchall()
                conn.close()
                if pending:
                    response = "<b>⏳ PENDING:</b>\n\n"
                    for msg_id, title in pending:
                        response += f"• Msg ID: <code>{msg_id}</code> - {title[:40]}\n"
                    send_message(chat_id, response)
            
            elif data == "get_msg_info":
                send_message(chat_id, "Send /get MESSAGE_ID")
    
    except Exception as e:
        logging.error(f"Error: {e}")
        logging.error(traceback.format_exc())

# ===== FLASK ROUTES - DIFFERENT PATH TO AVOID CONFLICT =====
@app.route('/helper', methods=['POST'])
def helper_webhook():
    """Helper bot webhook - different path from main bot"""
    try:
        update = request.get_json()
        if update:
            logging.info(f"Helper received update")
            process_update(update)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/')
def index():
    return "🎬 Movie ID Helper is running!"

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'bot': 'helper'})

# ===== SETUP =====
def setup_webhook():
    """Setup webhook for helper bot on different path"""
    try:
        app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
        if app_name:
            # Different path to avoid conflict with main bot
            webhook_url = f"https://{app_name}/helper"
            url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
            response = requests.post(url, json={"url": webhook_url}, timeout=10)
            
            if response.json().get("ok"):
                logging.info(f"✅ Helper webhook set: {webhook_url}")
                return True
            else:
                logging.error(f"❌ Failed: {response.text}")
                return False
        return False
    except Exception as e:
        logging.error(f"Error: {e}")
        return False

# ===== START =====
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    setup_webhook()
    app.run(host='0.0.0.0', port=port)
