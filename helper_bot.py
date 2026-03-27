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
ADMIN_ID = 6777360306  # Your correct Telegram ID

# ===== MAIN BOT DATABASE PATH =====
# This assumes your main bot's database is in the same directory
# If your main bot is on a different server, you'll need to use API calls
MAIN_BOT_DB_PATH = "movies.db"  # Path to your main bot's database

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
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                synced INTEGER DEFAULT 0
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

# ===== MAIN BOT SYNC FUNCTIONS =====
def add_movie_to_main_bot(code, message_id, title, year, description=""):
    """Add movie to main bot's database"""
    try:
        # Connect to main bot's database
        conn = sqlite3.connect(MAIN_BOT_DB_PATH)
        cursor = conn.cursor()
        
        # Check if movies table exists in main bot
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
        if not cursor.fetchone():
            logging.error("Main bot movies table not found")
            return False
        
        # Add movie to main bot
        cursor.execute('''
            INSERT OR REPLACE INTO movies (code, message_id, title, year, description, added_date, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
        ''', (code, message_id, title, year, description, datetime.now()))
        
        conn.commit()
        conn.close()
        logging.info(f"Movie added to main bot: {code} - {title}")
        return True
    except Exception as e:
        logging.error(f"Error adding to main bot: {e}")
        return False

def sync_all_movies():
    """Sync all unsynced movies to main bot"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, message_id, title, year, description FROM movies WHERE synced = 0")
        unsynced = cursor.fetchall()
        
        synced_count = 0
        for code, msg_id, title, year, desc in unsynced:
            if add_movie_to_main_bot(code, msg_id, title, year, desc):
                cursor.execute("UPDATE movies SET synced = 1 WHERE code = ?", (code,))
                synced_count += 1
        
        conn.commit()
        conn.close()
        
        if synced_count > 0:
            logging.info(f"Synced {synced_count} movies to main bot")
        return synced_count
    except Exception as e:
        logging.error(f"Sync error: {e}")
        return 0

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
    """Save movie to helper database and sync to main bot"""
    try:
        # Save to helper database
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO movies (code, message_id, title, year, description, synced)
            VALUES (?, ?, ?, ?, ?, 0)
        ''', (code, message_id, title, year, description))
        conn.commit()
        conn.close()
        logging.info(f"Movie saved to helper: {code} - {title}")
        
        # Sync to main bot immediately
        if add_movie_to_main_bot(code, message_id, title, year, description):
            # Mark as synced
            conn = sqlite3.connect('movies_helper.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE movies SET synced = 1 WHERE code = ?", (code,))
            conn.commit()
            conn.close()
            return True
        else:
            return True  # Saved to helper but sync failed - will retry later
    except Exception as e:
        logging.error(f"Error saving movie: {e}")
        return False

def get_all_movies():
    """Get all movies from helper"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, message_id, title, year, description, synced FROM movies ORDER BY year DESC")
        movies = cursor.fetchall()
        conn.close()
        return movies
    except Exception as e:
        logging.error(f"Error: {e}")
        return []

def delete_movie(code):
    """Delete movie from both databases"""
    try:
        # Delete from helper
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM movies WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        
        # Delete from main bot
        try:
            conn = sqlite3.connect(MAIN_BOT_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM movies WHERE code = ?", (code,))
            conn.commit()
            conn.close()
        except:
            pass
        
        return True
    except Exception as e:
        logging.error(f"Error deleting: {e}")
        return False

# ===== PROCESS UPDATES =====
def process_update(update):
    """Process updates"""
    try:
        # Handle channel posts (auto-detect new movies)
        if "channel_post" in update:
            post = update["channel_post"]
            chat_id = post["chat"]["id"]
            
            if chat_id == PRIVATE_CHANNEL:
                message_id = post["message_id"]
                caption = post.get("caption", "")
                text = post.get("text", "")
                content = caption or text
                
                # Extract movie info
                title, year = extract_movie_info(content)
                # Use message_id as numeric code
                code = str(message_id)
                
                # AUTO-ADD to database immediately
                success = save_movie(code, message_id, title, year, content[:500])
                
                if success:
                    # Notify admin that movie was added
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "📋 VIEW MOVIE", "callback_data": f"view_{message_id}"},
                                {"text": "🗑️ DELETE", "callback_data": f"delete_{message_id}"}
                            ]
                        ]
                    }
                    
                    send_message(
                        ADMIN_ID,
                        f"🎬 <b>MOVIE AUTO-ADDED TO DATABASE!</b>\n\n"
                        f"📝 <b>Title:</b> {title}\n"
                        f"📅 <b>Year:</b> {year if year else 'Unknown'}\n"
                        f"🆔 <b>Message ID:</b> <code>{message_id}</code>\n"
                        f"🔑 <b>Code:</b> <code>{code}</code>\n"
                        f"✅ <b>Status:</b> Added to main bot\n\n"
                        f"📄 <b>Preview:</b>\n{content[:150]}...",
                        keyboard
                    )
                else:
                    # Save to pending if auto-add failed
                    conn = sqlite3.connect('movies_helper.db')
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO pending_movies (message_id, chat_id, title, year, description)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (message_id, chat_id, title, year, content[:500]))
                    conn.commit()
                    conn.close()
                    
                    # Notify admin for manual approval
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "✅ ADD MANUALLY", "callback_data": f"add_{message_id}"},
                                {"text": "❌ SKIP", "callback_data": f"skip_{message_id}"}
                            ]
                        ]
                    }
                    
                    send_message(
                        ADMIN_ID,
                        f"⚠️ <b>MOVIE DETECTED - NEEDS MANUAL ADD</b>\n\n"
                        f"📝 <b>Title:</b> {title}\n"
                        f"📅 <b>Year:</b> {year if year else 'Unknown'}\n"
                        f"🆔 <b>Message ID:</b> <code>{message_id}</code>\n"
                        f"🔑 <b>Auto Code:</b> <code>{code}</code>\n"
                        f"❌ <b>Auto-add failed</b> - Please add manually\n\n"
                        f"📄 <b>Preview:</b>\n{content[:150]}...",
                        keyboard
                    )
                
                logging.info(f"Movie processed: {message_id} - {title} - Code: {code}")
                return
        
        # Handle messages
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            
            # Only admin can use commands
            if user_id != ADMIN_ID:
                send_message(chat_id, "⛔ <b>Access Denied</b>\n\nThis bot is for admin use only.")
                return
            
            if "text" in message:
                text = message["text"].strip()
                
                if text == "/start":
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "📋 ALL MOVIES", "callback_data": "list_all"}],
                            [{"text": "⏳ PENDING MOVIES", "callback_data": "list_pending"}],
                            [{"text": "🔄 SYNC NOW", "callback_data": "sync_now"}],
                            [{"text": "🔍 GET MESSAGE INFO", "callback_data": "get_msg_info"}],
                            [{"text": "➕ ADD MANUAL", "callback_data": "add_manual"}]
                        ]
                    }
                    
                    # Check sync status
                    conn = sqlite3.connect('movies_helper.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM movies WHERE synced = 0")
                    unsynced = cursor.fetchone()[0]
                    conn.close()
                    
                    status = f"\n\n📊 <b>Sync Status:</b> {unsynced} unsynced movies"
                    
                    send_message(
                        chat_id,
                        "<b>🎬 MOVIE ID HELPER BOT</b>\n\n"
                        "<b>📌 Commands:</b>\n"
                        "/list - Show all movies\n"
                        "/pending - Show pending movies\n"
                        "/sync - Sync unsynced movies to main bot\n"
                        "/get MSG_ID - Get message info\n"
                        "/forward MSG_ID - Forward message to you\n"
                        "/add CODE MSG_ID TITLE YEAR - Add movie manually\n"
                        "/delete CODE - Delete movie\n\n"
                        f"<b>📢 Channel ID:</b> <code>{PRIVATE_CHANNEL}</code>\n"
                        f"<b>✅ Auto-add:</b> Enabled" + status,
                        keyboard
                    )
                
                elif text == "/list":
                    movies = get_all_movies()
                    if movies:
                        response = "<b>📋 ALL MOVIES IN DATABASE:</b>\n\n"
                        for code, msg_id, title, year, desc, synced in movies:
                            status = "✅ Synced" if synced else "⏳ Pending"
                            response += f"• <b>{title}</b> ({year})\n"
                            response += f"  🔑 Code: <code>{code}</code> | 🆔 Msg ID: <code>{msg_id}</code>\n"
                            response += f"  📊 Status: {status}\n\n"
                        send_message(chat_id, response[:4000])
                    else:
                        send_message(chat_id, "📭 <b>No movies in database</b>\n\nSend movies to your private channel to auto-add them!")
                
                elif text == "/pending":
                    conn = sqlite3.connect('movies_helper.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, message_id, title, year FROM pending_movies ORDER BY date_received DESC")
                    pending = cursor.fetchall()
                    conn.close()
                    
                    if pending:
                        response = "<b>⏳ PENDING MOVIES (Awaiting Approval):</b>\n\n"
                        for pid, msg_id, title, year in pending:
                            response += f"• 🆔 Msg ID: <code>{msg_id}</code>\n"
                            response += f"  📝 Title: {title}\n"
                            response += f"  📅 Year: {year if year else 'Unknown'}\n"
                            response += f"  🔑 Code: <code>{msg_id}</code>\n\n"
                        send_message(chat_id, response)
                    else:
                        send_message(chat_id, "✅ <b>No pending movies</b>\n\nAll movies have been auto-added!")
                
                elif text == "/sync":
                    count = sync_all_movies()
                    if count > 0:
                        send_message(chat_id, f"✅ <b>Synced {count} movies to main bot!</b>")
                    else:
                        send_message(chat_id, "✅ <b>All movies are already synced!</b>")
                
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
                                    f"<b>📝 MESSAGE INFORMATION</b>\n\n"
                                    f"🆔 <b>Message ID:</b> <code>{msg['message_id']}</code>\n"
                                    f"🔑 <b>Movie Code:</b> <code>{msg['message_id']}</code>\n"
                                    f"📅 <b>Date:</b> {datetime.fromtimestamp(msg['date']).strftime('%Y-%m-%d %H:%M:%S')}\n"
                                    f"📄 <b>Content:</b>\n{content[:300]}\n\n"
                                    f"<b>✨ Use this in your main bot:</b>\n"
                                    f"<code>code = {msg['message_id']}</code>\n"
                                    f"<code>message_id = {msg['message_id']}</code>"
                                )
                                send_message(chat_id, response)
                            else:
                                send_message(chat_id, f"❌ <b>Message {msg_id} not found</b>")
                        except ValueError:
                            send_message(chat_id, "❌ <b>Invalid message ID</b>")
                    else:
                        send_message(chat_id, "❌ <b>Usage:</b> /get MESSAGE_ID")
                
                elif text.startswith("/forward"):
                    parts = text.split()
                    if len(parts) == 2:
                        try:
                            msg_id = int(parts[1])
                            result = forward_message(chat_id, PRIVATE_CHANNEL, msg_id)
                            if result and result.get("ok"):
                                send_message(chat_id, f"✅ <b>Message {msg_id} forwarded to you!</b>")
                            else:
                                send_message(chat_id, f"❌ <b>Failed to forward message {msg_id}</b>")
                        except ValueError:
                            send_message(chat_id, "❌ <b>Invalid message ID</b>")
                    else:
                        send_message(chat_id, "❌ <b>Usage:</b> /forward MESSAGE_ID")
                
                elif text.startswith("/add"):
                    parts = text.split(maxsplit=4)
                    if len(parts) >= 5:
                        _, code, msg_id, title, year = parts
                        try:
                            msg_id = int(msg_id)
                            year = int(year)
                            if not code.isdigit():
                                send_message(chat_id, "❌ <b>Code must be numeric only!</b>")
                                return
                            if save_movie(code, msg_id, title, year):
                                send_message(chat_id, f"✅ <b>Movie added and synced!</b>\n\n🔑 Code: <code>{code}</code>\n📝 Title: {title}")
                            else:
                                send_message(chat_id, "❌ <b>Failed to add movie</b>")
                        except ValueError:
                            send_message(chat_id, "❌ <b>Invalid message ID or year</b>")
                    else:
                        send_message(chat_id, "❌ <b>Usage:</b> /add CODE MESSAGE_ID TITLE YEAR\n\nExample: /add 12345 12345 'Inception' 2010")
                
                elif text.startswith("/delete"):
                    parts = text.split()
                    if len(parts) == 2:
                        if delete_movie(parts[1]):
                            send_message(chat_id, f"✅ <b>Movie {parts[1]} deleted from both databases!</b>")
                        else:
                            send_message(chat_id, f"❌ <b>Movie {parts[1]} not found</b>")
                    else:
                        send_message(chat_id, "❌ <b>Usage:</b> /delete CODE")
        
        # Handle callback queries
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
                    code = str(msg_id)
                    if save_movie(code, msg_id, title, year, desc):
                        cursor.execute("DELETE FROM pending_movies WHERE message_id = ?", (msg_id,))
                        conn.commit()
                        send_message(chat_id, f"✅ <b>Movie added and synced!</b>\n\nCode: <code>{code}</code>\nTitle: {title}")
                conn.close()
            
            elif data.startswith("skip_"):
                msg_id = int(data.split("_")[1])
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("DELETE FROM pending_movies WHERE message_id = ?", (msg_id,))
                conn.commit()
                conn.close()
                send_message(chat_id, f"⏭️ <b>Skipped message {msg_id}</b>")
            
            elif data == "sync_now":
                count = sync_all_movies()
                send_message(chat_id, f"✅ <b>Synced {count} movies to main bot!</b>")
            
            elif data == "list_all":
                movies = get_all_movies()
                if movies:
                    response = "<b>📋 MOVIES IN DATABASE:</b>\n\n"
                    for code, msg_id, title, year, desc, synced in movies[:15]:
                        status = "✅" if synced else "⏳"
                        response += f"{status} {title} ({year}) - Code: <code>{code}</code>\n"
                    send_message(chat_id, response)
                else:
                    send_message(chat_id, "📭 No movies")
            
            elif data == "list_pending":
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("SELECT message_id, title, year FROM pending_movies")
                pending = cursor.fetchall()
                conn.close()
                
                if pending:
                    response = "<b>⏳ PENDING:</b>\n\n"
                    for msg_id, title, year in pending:
                        response += f"• <code>{msg_id}</code> - {title}\n"
                    send_message(chat_id, response)
                else:
                    send_message(chat_id, "✅ No pending")
            
            elif data == "get_msg_info":
                send_message(chat_id, "🔍 Send: /get MESSAGE_ID")
            
            elif data == "add_manual":
                send_message(chat_id, "➕ Use: /add CODE MESSAGE_ID TITLE YEAR\n\nExample: /add 12345 12345 'Inception' 2010")
    
    except Exception as e:
        logging.error(f"Error processing update: {e}")
        logging.error(traceback.format_exc())

# ===== FLASK ROUTES =====
@app.route('/helper', methods=['POST'])
def helper_webhook():
    """Helper bot webhook"""
    try:
        update = request.get_json()
        if update:
            logging.info(f"Helper received update")
            process_update(update)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/')
def index():
    return "🎬 Movie ID Helper Bot is running!\n\nMovies are auto-added to main bot database!"

@app.route('/health')
def health():
    """Health check"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies")
        movie_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM movies WHERE synced = 0")
        unsynced = cursor.fetchone()[0]
        conn.close()
        
        # Check if main bot database exists
        main_bot_exists = os.path.exists(MAIN_BOT_DB_PATH)
        
        return jsonify({
            'status': 'healthy',
            'bot': 'helper',
            'movies_count': movie_count,
            'unsynced_count': unsynced,
            'main_bot_db_exists': main_bot_exists,
            'admin_id': ADMIN_ID,
            'channel_id': PRIVATE_CHANNEL,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# ===== SETUP WEBHOOK =====
def setup_webhook():
    """Setup webhook for helper bot"""
    try:
        app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
        if app_name:
            webhook_url = f"https://{app_name}/helper"
            url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
            response = requests.post(url, json={"url": webhook_url}, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    logging.info(f"✅ Webhook set to: {webhook_url}")
                    return True
                else:
                    logging.error(f"❌ Failed: {result}")
                    return False
        else:
            logging.warning("⚠️ Running locally - webhook not set")
            return False
    except Exception as e:
        logging.error(f"❌ Webhook error: {e}")
        return False

# ===== START =====
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    
    # Setup webhook
    setup_webhook()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=port, debug=False)