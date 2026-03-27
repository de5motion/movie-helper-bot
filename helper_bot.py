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
        logging.info(f"Movie saved: {code} - {title}")
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
                            {"text": "✅ ADD MOVIE", "callback_data": f"add_{message_id}"},
                            {"text": "❌ SKIP", "callback_data": f"skip_{message_id}"}
                        ],
                        [
                            {"text": "📋 VIEW DETAILS", "callback_data": f"view_{message_id}"}
                        ]
                    ]
                }
                
                send_message(
                    ADMIN_ID,
                    f"🎬 <b>NEW MOVIE DETECTED!</b>\n\n"
                    f"📝 <b>Title:</b> {title}\n"
                    f"📅 <b>Year:</b> {year if year else 'Unknown'}\n"
                    f"🆔 <b>Message ID:</b> <code>{message_id}</code>\n"
                    f"🔑 <b>Auto Code:</b> <code>{code}</code>\n\n"
                    f"📄 <b>Preview:</b>\n{content[:150]}...",
                    keyboard
                )
                logging.info(f"New movie detected: {message_id} - {title}")
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
                            [{"text": "🔍 GET MESSAGE INFO", "callback_data": "get_msg_info"}],
                            [{"text": "➕ ADD MANUAL", "callback_data": "add_manual"}]
                        ]
                    }
                    send_message(
                        chat_id,
                        "<b>🎬 MOVIE ID HELPER BOT</b>\n\n"
                        "<b>📌 Commands:</b>\n"
                        "/list - Show all movies\n"
                        "/pending - Show pending movies\n"
                        "/get MSG_ID - Get message info\n"
                        "/forward MSG_ID - Forward message to you\n"
                        "/add CODE MSG_ID TITLE YEAR - Add movie manually\n"
                        "/delete CODE - Delete movie\n\n"
                        f"<b>📢 Channel ID:</b> <code>{PRIVATE_CHANNEL}</code>\n\n"
                        "<i>When you send a movie to the channel, it will auto-detect!</i>",
                        keyboard
                    )
                
                elif text == "/list":
                    movies = get_all_movies()
                    if movies:
                        response = "<b>📋 ALL MOVIES IN DATABASE:</b>\n\n"
                        for code, msg_id, title, year, desc in movies:
                            response += f"• <b>{title}</b> ({year})\n"
                            response += f"  🔑 Code: <code>{code}</code> | 🆔 Msg ID: <code>{msg_id}</code>\n\n"
                        send_message(chat_id, response[:4000])
                    else:
                        send_message(chat_id, "📭 <b>No movies in database</b>\n\nAdd movies by sending them to your private channel!")
                
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
                            response += f"  📅 Year: {year if year else 'Unknown'}\n\n"
                        send_message(chat_id, response)
                    else:
                        send_message(chat_id, "✅ <b>No pending movies</b>\n\nAll movies have been processed!")
                
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
                                    f"📅 <b>Date:</b> {datetime.fromtimestamp(msg['date']).strftime('%Y-%m-%d %H:%M:%S')}\n"
                                    f"📄 <b>Content:</b>\n{content[:300]}\n\n"
                                    f"<b>✨ Use this in your main bot:</b>\n"
                                    f"<code>message_id = {msg['message_id']}</code>"
                                )
                                send_message(chat_id, response)
                            else:
                                send_message(chat_id, f"❌ <b>Message {msg_id} not found</b>\n\nMake sure the message exists in your private channel.")
                        except ValueError:
                            send_message(chat_id, "❌ <b>Invalid message ID</b>\n\nUse: /get 12345")
                    else:
                        send_message(chat_id, "❌ <b>Usage:</b> /get MESSAGE_ID\n\nExample: /get 12345")
                
                elif text.startswith("/forward"):
                    parts = text.split()
                    if len(parts) == 2:
                        try:
                            msg_id = int(parts[1])
                            result = forward_message(chat_id, PRIVATE_CHANNEL, msg_id)
                            if result and result.get("ok"):
                                send_message(chat_id, f"✅ <b>Message {msg_id} forwarded to you!</b>\n\nCheck your chat for the message.")
                            else:
                                send_message(chat_id, f"❌ <b>Failed to forward message {msg_id}</b>\n\nMake sure the message exists.")
                        except ValueError:
                            send_message(chat_id, "❌ <b>Invalid message ID</b>")
                    else:
                        send_message(chat_id, "❌ <b>Usage:</b> /forward MESSAGE_ID\n\nExample: /forward 12345")
                
                elif text.startswith("/add"):
                    parts = text.split(maxsplit=4)
                    if len(parts) >= 5:
                        _, code, msg_id, title, year = parts
                        try:
                            msg_id = int(msg_id)
                            year = int(year)
                            if save_movie(code, msg_id, title, year):
                                send_message(chat_id, f"✅ <b>Movie added successfully!</b>\n\n🔑 Code: <code>{code}</code>\n📝 Title: {title}\n🆔 Msg ID: <code>{msg_id}</code>")
                            else:
                                send_message(chat_id, "❌ <b>Failed to add movie</b>\n\nCheck the database.")
                        except ValueError:
                            send_message(chat_id, "❌ <b>Invalid message ID or year</b>\n\nMessage ID and year must be numbers.")
                    else:
                        send_message(chat_id, "❌ <b>Usage:</b> /add CODE MESSAGE_ID TITLE YEAR\n\nExample:\n/add INT001 12345 'Inception' 2010")
                
                elif text.startswith("/delete"):
                    parts = text.split()
                    if len(parts) == 2:
                        code = parts[1]
                        if delete_movie(code):
                            send_message(chat_id, f"✅ <b>Movie {code} deleted successfully!</b>")
                        else:
                            send_message(chat_id, f"❌ <b>Movie {code} not found</b>")
                    else:
                        send_message(chat_id, "❌ <b>Usage:</b> /delete CODE\n\nExample: /delete INT001")
                
                elif text.startswith("/"):
                    send_message(chat_id, "❌ <b>Unknown command</b>\n\nUse /start to see available commands.")
        
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
            
            if data.startswith("add_"):
                msg_id = int(data.split("_")[1])
                
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("SELECT title, year, description FROM pending_movies WHERE message_id = ?", (msg_id,))
                result = cursor.fetchone()
                
                if result:
                    title, year, desc = result
                    code = f"INT{msg_id}"
                    if save_movie(code, msg_id, title, year, desc):
                        cursor.execute("DELETE FROM pending_movies WHERE message_id = ?", (msg_id,))
                        conn.commit()
                        send_message(chat_id, f"✅ <b>Movie added to database!</b>\n\n🔑 Code: <code>{code}</code>\n📝 Title: {title}\n🆔 Msg ID: <code>{msg_id}</code>")
                    else:
                        send_message(chat_id, "❌ <b>Failed to add movie</b>")
                else:
                    send_message(chat_id, "❌ <b>Movie not found in pending</b>")
                conn.close()
            
            elif data.startswith("skip_"):
                msg_id = int(data.split("_")[1])
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("DELETE FROM pending_movies WHERE message_id = ?", (msg_id,))
                conn.commit()
                conn.close()
                send_message(chat_id, f"⏭️ <b>Skipped message {msg_id}</b>\n\nYou can always add it manually with /add")
            
            elif data == "list_all":
                movies = get_all_movies()
                if movies:
                    response = "<b>📋 MOVIES IN DATABASE:</b>\n\n"
                    for code, msg_id, title, year, desc in movies[:15]:
                        response += f"• {title} ({year}) - <code>{code}</code>\n"
                    if len(movies) > 15:
                        response += f"\n... and {len(movies)-15} more\nUse /list for full list"
                    send_message(chat_id, response)
                else:
                    send_message(chat_id, "📭 No movies in database")
            
            elif data == "list_pending":
                conn = sqlite3.connect('movies_helper.db')
                cursor = conn.cursor()
                cursor.execute("SELECT message_id, title, year FROM pending_movies ORDER BY date_received DESC")
                pending = cursor.fetchall()
                conn.close()
                
                if pending:
                    response = "<b>⏳ PENDING MOVIES:</b>\n\n"
                    for msg_id, title, year in pending:
                        response += f"• 🆔 <code>{msg_id}</code> - {title}"
                        if year:
                            response += f" ({year})"
                        response += "\n"
                    send_message(chat_id, response)
                else:
                    send_message(chat_id, "✅ No pending movies")
            
            elif data == "get_msg_info":
                send_message(chat_id, "🔍 <b>Get Message Info</b>\n\nSend: /get MESSAGE_ID\n\nExample: /get 12345")
            
            elif data == "add_manual":
                send_message(chat_id, "➕ <b>Add Movie Manually</b>\n\nUse command:\n<code>/add CODE MESSAGE_ID TITLE YEAR</code>\n\nExample:\n<code>/add INT001 12345 'Inception' 2010</code>")
    
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
    return "🎬 Movie ID Helper Bot is running!\n\nSend /start to the bot to begin."

@app.route('/health')
def health():
    """Health check"""
    try:
        conn = sqlite3.connect('movies_helper.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies")
        movie_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM pending_movies")
        pending_count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'bot': 'helper',
            'movies_count': movie_count,
            'pending_count': pending_count,
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
                logging.error(f"❌ HTTP error: {response.status_code}")
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