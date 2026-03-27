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
ADMIN_ID = 6777360306  # Your Telegram ID

# ===== MAIN BOT API CONFIGURATION =====
MAIN_BOT_URL = "https://movie-bot-8-9cnw.onrender.com"  # Your main bot URL
API_SECRET = "movie_bot_secret_2024_67890"  # Must match the secret in main bot

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
        
        # Movies table with sync status
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                message_id INTEGER,
                title TEXT,
                year INTEGER,
                description TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                synced INTEGER DEFAULT 0,
                sync_error TEXT
            )
        ''')
        
        # Pending movies table (for failed syncs)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                chat_id INTEGER,
                title TEXT,
                year INTEGER,
                description TEXT,
                date_received TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_attempts INTEGER DEFAULT 0
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
    """Send message via Telegram"""
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
    """Get message info from channel"""
    url = f"https://api.telegram.org/bot{TOKEN}/getMessage"
    params = {"chat_id": chat_id, "message_id": message_id}
    try:
        response = requests.get(url, params=params, timeout=10)
        return response.json()
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

def forward_message(chat_id, from_chat_id, message_id):
    """Forward message to user"""
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
    """Extract title and year from text"""
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

def send_movie_to_main_bot(code, message_id, title, year, description=""):
    """Send movie to main bot via API"""
    try:
        url = f"{MAIN_BOT_URL}/add_movie"
        
        payload = {
            "code": code,
            "message_id": message_id,
            "title": title,
            "year": year,
            "description": description[:500],
            "secret": API_SECRET
        }
        
        logging.info(f"Sending to main bot: {url}")
        logging.info(f"Payload: code={code}, title={title}")
        
        response = requests.post(url, json=payload, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'success':
                logging.info(f"✅ Movie sent to main bot: {code}")
                return True, None
            else:
                error = result.get('error', 'Unknown error')
                logging.error(f"Main bot error: {error}")
                return False, error
        else:
            logging.error(f"HTTP error: {response.status_code} - {response.text}")
            return False, f"HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        logging.error("Timeout connecting to main bot")
        return False, "Timeout"
    except requests.exceptions.ConnectionError:
        logging.error("Cannot connect to main bot - check URL")
        return False, "Connection failed"
    except Exception as e:
        logging.error(f"Error sending to main bot: {e}")
        return False, str(e)

def save_movie_and_sync(code, message_id, title, year, description=""):
    """Save movie locally and sync to main bot"""
    try:
        # Save to local database first
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO movies (code, message_id, title, year, description, synced)
            VALUES (?, ?, ?, ?, ?, 0)
        ''', (code, message_id, title, year, description))
        conn.commit()
        conn.close()
        
        logging.info(f"Movie saved locally: {code} - {title}")
        
        # Try to sync with main bot
        success, error = send_movie_to_main_bot(code, message_id, title, year, description)
        
        if success:
            # Mark as synced
            conn = sqlite3.connect('movies_helper.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE movies SET synced = 1, sync_error = NULL WHERE code = ?", (code,))
            conn.commit()
            conn.close()
            return True, None
        else:
            # Mark as failed
            conn = sqlite3.connect('movies_helper.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE movies SET sync_error = ? WHERE code = ?", (error, code))
            conn.commit()
            conn.close()
            return False, error
            
    except Exception as e:
        logging.error(f"Error saving movie: {e}")
        return False, str(e)

def get_all_movies():
    """Get all movies from local database"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, message_id, title, year, description, synced, sync_error FROM movies ORDER BY year DESC")
        movies = cursor.fetchall()
        conn.close()
        return movies
    except Exception as e:
        logging.error(f"Error: {e}")
        return []

def get_pending_movies():
    """Get pending movies (failed syncs)"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, message_id, title, year, sync_error FROM movies WHERE synced = 0 ORDER BY added_date DESC")
        pending = cursor.fetchall()
        conn.close()
        return pending
    except Exception as e:
        logging.error(f"Error: {e}")
        return []

def delete_movie(code):
    """Delete movie from local database"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM movies WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error: {e}")
        return False

def sync_all_unsynced():
    """Sync all unsynced movies"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, message_id, title, year, description FROM movies WHERE synced = 0")
        unsynced = cursor.fetchall()
        
        synced_count = 0
        for code, msg_id, title, year, desc in unsynced:
            success, error = send_movie_to_main_bot(code, msg_id, title, year, desc)
            if success:
                cursor.execute("UPDATE movies SET synced = 1, sync_error = NULL WHERE code = ?", (code,))
                synced_count += 1
                logging.info(f"Synced: {code}")
            else:
                cursor.execute("UPDATE movies SET sync_error = ? WHERE code = ?", (error, code))
                logging.warning(f"Failed to sync: {code} - {error}")
        
        conn.commit()
        conn.close()
        return synced_count
    except Exception as e:
        logging.error(f"Sync error: {e}")
        return 0

# ===== PROCESS UPDATES =====
def process_update(update):
    """Process Telegram updates"""
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
                code = str(message_id)  # Use message_id as numeric code
                
                # Save and sync to main bot
                success, error = save_movie_and_sync(code, message_id, title, year, content[:500])
                
                if success:
                    # Notify admin that movie was added
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "📋 VIEW DETAILS", "callback_data": f"view_{message_id}"},
                                {"text": "🗑️ DELETE", "callback_data": f"delete_{code}"}
                            ]
                        ]
                    }
                    
                    send_message(
                        ADMIN_ID,
                        f"🎬 <b>MOVIE AUTO-ADDED TO MAIN BOT!</b>\n\n"
                        f"📝 <b>Title:</b> {title}\n"
                        f"📅 <b>Year:</b> {year if year else 'Unknown'}\n"
                        f"🆔 <b>Message ID:</b> <code>{message_id}</code>\n"
                        f"🔑 <b>Code:</b> <code>{code}</code>\n"
                        f"✅ <b>Status:</b> Synced to main bot\n\n"
                        f"📄 <b>Preview:</b>\n{content[:150]}...",
                        keyboard
                    )
                else:
                    # Notify admin that sync failed
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "🔄 RETRY SYNC", "callback_data": f"retry_{code}"},
                                {"text": "❌ DELETE", "callback_data": f"delete_{code}"}
                            ]
                        ]
                    }
                    
                    send_message(
                        ADMIN_ID,
                        f"⚠️ <b>MOVIE DETECTED - SYNC FAILED</b>\n\n"
                        f"📝 <b>Title:</b> {title}\n"
                        f"📅 <b>Year:</b> {year if year else 'Unknown'}\n"
                        f"🆔 <b>Message ID:</b> <code>{message_id}</code>\n"
                        f"🔑 <b>Code:</b> <code>{code}</code>\n"
                        f"❌ <b>Error:</b> {error}\n\n"
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
                    movies = get_all_movies()
                    synced_count = sum(1 for m in movies if m[5] == 1)
                    pending_count = len(movies) - synced_count
                    
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "📋 ALL MOVIES", "callback_data": "list_all"}],
                            [{"text": "⏳ PENDING SYNC", "callback_data": "list_pending"}],
                            [{"text": "🔄 SYNC NOW", "callback_data": "sync_now"}],
                            [{"text": "🔍 GET MESSAGE INFO", "callback_data": "get_msg_info"}],
                            [{"text": "➕ ADD MANUAL", "callback_data": "add_manual"}]
                        ]
                    }
                    
                    send_message(
                        chat_id,
                        f"<b>🎬 MOVIE ID HELPER BOT</b>\n\n"
                        f"<b>📊 Status:</b>\n"
                        f"• Total Movies: {len(movies)}\n"
                        f"• Synced: ✅ {synced_count}\n"
                        f"• Pending: ⏳ {pending_count}\n\n"
                        f"<b>📌 Commands:</b>\n"
                        f"/list - Show all movies\n"
                        f"/pending - Show pending sync\n"
                        f"/sync - Sync all unsynced\n"
                        f"/get MSG_ID - Get message info\n"
                        f"/forward MSG_ID - Forward message\n"
                        f"/add CODE MSG_ID TITLE YEAR - Add manually\n"
                        f"/delete CODE - Delete movie\n\n"
                        f"<b>📢 Channel:</b> <code>{PRIVATE_CHANNEL}</code>\n"
                        f"<b>🎯 Main Bot:</b> {MAIN_BOT_URL}",
                        keyboard
                    )
                
                elif text == "/list":
                    movies = get_all_movies()
                    if movies:
                        response = "<b>📋 ALL MOVIES:</b>\n\n"
                        for code, msg_id, title, year, desc, synced, error in movies:
                            status = "✅ Synced" if synced else f"⚠️ Pending: {error[:30] if error else 'Unknown'}"
                            response += f"• <b>{title}</b> ({year})\n"
                            response += f"  🔑 Code: <code>{code}</code> | 🆔 Msg: {msg_id}\n"
                            response += f"  📊 {status}\n\n"
                        send_message(chat_id, response[:4000])
                    else:
                        send_message(chat_id, "📭 No movies in database")
                
                elif text == "/pending":
                    pending = get_pending_movies()
                    if pending:
                        response = "<b>⏳ PENDING SYNC:</b>\n\n"
                        for code, msg_id, title, year, error in pending:
                            response += f"• <b>{title}</b> ({year})\n"
                            response += f"  🔑 Code: <code>{code}</code>\n"
                            response += f"  ❌ Error: {error}\n\n"
                        send_message(chat_id, response)
                    else:
                        send_message(chat_id, "✅ All movies synced!")
                
                elif text == "/sync":
                    send_message(chat_id, "🔄 Syncing movies to main bot...")
                    count = sync_all_unsynced()
                    send_message(chat_id, f"✅ Synced {count} movies to main bot!")
                
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
                                    f"🆔 Message ID: <code>{msg['message_id']}</code>\n"
                                    f"🔑 Code: <code>{msg['message_id']}</code>\n"
                                    f"📅 Date: {datetime.fromtimestamp(msg['date']).strftime('%Y-%m-%d %H:%M:%S')}\n"
                                    f"📄 Content:\n{content[:300]}\n\n"
                                    f"<b>✨ Use in main bot:</b>\n"
                                    f"<code>code = {msg['message_id']}</code>"
                                )
                                send_message(chat_id, response)
                            else:
                                send_message(chat_id, f"❌ Message {msg_id} not found")
                        except ValueError:
                            send_message(chat_id, "❌ Invalid message ID")
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
                                send_message(chat_id, f"❌ Failed to forward")
                        except ValueError:
                            send_message(chat_id, "❌ Invalid message ID")
                    else:
                        send_message(chat_id, "Usage: /forward MESSAGE_ID")
                
                elif text.startswith("/add"):
                    parts = text.split(maxsplit=4)
                    if len(parts) >= 5:
                        _, code, msg_id, title, year = parts
                        try:
                            msg_id = int(msg_id)
                            year = int(year)
                            if not code.isdigit():
                                send_message(chat_id, "❌ Code must be numeric!")
                                return
                            
                            success, error = save_movie_and_sync(code, msg_id, title, year)
                            if success:
                                send_message(chat_id, f"✅ Movie added and synced!\n\nCode: {code}\nTitle: {title}")
                            else:
                                send_message(chat_id, f"⚠️ Movie saved locally but sync failed: {error}")
                        except ValueError:
                            send_message(chat_id, "❌ Invalid message ID or year")
                    else:
                        send_message(chat_id, "Usage: /add CODE MESSAGE_ID TITLE YEAR\nExample: /add 12345 12345 'Inception' 2010")
                
                elif text.startswith("/delete"):
                    parts = text.split()
                    if len(parts) == 2:
                        if delete_movie(parts[1]):
                            send_message(chat_id, f"✅ Movie {parts[1]} deleted!")
                        else:
                            send_message(chat_id, f"❌ Movie not found")
                    else:
                        send_message(chat_id, "Usage: /delete CODE")
        
        # Handle callback queries
        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]
            
            # Answer callback
            try:
                url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
                requests.post(url, json={"callback_query_id": callback["id"]})
            except:
                pass
            
            if data.startswith("retry_"):
                code = data.split("_")[1]
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("SELECT message_id, title, year, description FROM movies WHERE code = ?", (code,))
                result = cursor.fetchone()
                if result:
                    msg_id, title, year, desc = result
                    success, error = send_movie_to_main_bot(code, msg_id, title, year, desc)
                    if success:
                        cursor.execute("UPDATE movies SET synced = 1, sync_error = NULL WHERE code = ?", (code,))
                        conn.commit()
                        send_message(chat_id, f"✅ Movie {code} synced successfully!")
                    else:
                        cursor.execute("UPDATE movies SET sync_error = ? WHERE code = ?", (error, code))
                        conn.commit()
                        send_message(chat_id, f"❌ Sync failed: {error}")
                conn.close()
            
            elif data.startswith("delete_"):
                code = data.split("_")[1]
                if delete_movie(code):
                    send_message(chat_id, f"✅ Movie {code} deleted!")
                else:
                    send_message(chat_id, f"❌ Movie not found")
            
            elif data == "list_all":
                movies = get_all_movies()
                if movies:
                    response = "<b>📋 MOVIES:</b>\n\n"
                    for code, msg_id, title, year, desc, synced, error in movies[:10]:
                        status = "✅" if synced else "⚠️"
                        response += f"{status} {title} ({year}) - <code>{code}</code>\n"
                    send_message(chat_id, response)
            
            elif data == "list_pending":
                pending = get_pending_movies()
                if pending:
                    response = "<b>⏳ PENDING:</b>\n\n"
                    for code, msg_id, title, year, error in pending[:10]:
                        response += f"• {title} - <code>{code}</code>\n"
                        response += f"  ❌ {error}\n\n"
                    send_message(chat_id, response)
                else:
                    send_message(chat_id, "✅ No pending movies")
            
            elif data == "sync_now":
                send_message(chat_id, "🔄 Syncing...")
                count = sync_all_unsynced()
                send_message(chat_id, f"✅ Synced {count} movies!")
            
            elif data == "get_msg_info":
                send_message(chat_id, "Send: /get MESSAGE_ID\n\nExample: /get 12345")
            
            elif data == "add_manual":
                send_message(chat_id, "➕ <b>Add Movie Manually</b>\n\nUse command:\n<code>/add CODE MESSAGE_ID TITLE YEAR</code>\n\nExample:\n<code>/add 12345 12345 'Inception' 2010</code>")
    
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
            logging.info(f"Helper received update: {update.get('update_id')}")
            process_update(update)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/')
def index():
    return "🎬 Movie ID Helper Bot is running!\n\nMovies are auto-synced to main bot!"

@app.route('/health')
def health():
    """Health check"""
    try:
        movies = get_all_movies()
        synced = sum(1 for m in movies if m[5] == 1)
        
        return jsonify({
            'status': 'healthy',
            'bot': 'helper',
            'total_movies': len(movies),
            'synced': synced,
            'pending': len(movies) - synced,
            'main_bot_url': MAIN_BOT_URL,
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