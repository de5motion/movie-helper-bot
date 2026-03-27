import logging
import sqlite3
import re
from datetime import datetime
import requests
from flask import Flask, request, jsonify
import os

TOKEN = "8660161351:AAEGsV68gS860oepV0c1nAxPUkjvBiskWdY"
MAIN_BOT_API_URL = "https://movie-bot-7qmx.onrender.com/add_movie"
API_SECRET = "movie_bot_secret_2024_67890"
ADMIN_ID = 6777360306

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect('helper_movies.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            message_id INTEGER,
            title TEXT,
            year INTEGER,
            description TEXT,
            channel_message_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
init_db()

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logging.error(f"Send error: {e}")

def answer_callback(callback_id):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})

def extract_movie_info(text):
    title = year = code = None
    for line in text.split('\n'):
        line = line.strip()
        match = re.search(r'(?:Code|Код):?\s*(\d+)', line, re.IGNORECASE)
        if match:
            code = match.group(1)
        match = re.match(r'^(.+?)\s*\((\d{4})\)$', line)
        if match:
            title = match.group(1).strip()
            year = int(match.group(2))
        elif not title and line and not line.startswith(('📝', 'Code', 'Код')):
            title = line
    return title, year, code

def save_pending_movie(code, message_id, title, year, description, channel_msg_id):
    conn = sqlite3.connect('helper_movies.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO pending_movies (code, message_id, title, year, description, channel_message_id, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    ''', (code, message_id, title, year or 0, description, channel_msg_id))
    conn.commit()
    conn.close()

def send_to_main_bot(code, message_id, title, year, description):
    data = {
        'secret': API_SECRET,
        'code': code,
        'message_id': message_id,
        'title': title,
        'year': year or 0,
        'description': description
    }
    try:
        resp = requests.post(MAIN_BOT_API_URL, json=data, timeout=30)
        return resp.status_code == 200, resp.text
    except Exception as e:
        return False, str(e)

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if not update:
            return 'ok', 200

        if 'message' in update:
            msg = update['message']
            user_id = msg['from']['id']
            if user_id != ADMIN_ID:
                return 'ok', 200
            chat_id = msg['chat']['id']

            # /start
            if 'text' in msg and msg['text'] == '/start':
                send_message(chat_id, "🎬 Forward a movie message.\nBot will ask for confirmation.")
                return 'ok', 200

            # forwarded
            if 'forward_from_chat' in msg and msg.get('text'):
                title, year, code = extract_movie_info(msg['text'])
                if not title or not code:
                    send_message(chat_id, "❌ Could not extract title or code.")
                    return 'ok', 200

                save_pending_movie(code, msg['forward_from_message_id'], title, year, msg['text'], msg['message_id'])

                keyboard = {
                    "inline_keyboard": [
                        [{"text": "✅ Add Movie", "callback_data": f"add_{code}"}],
                        [{"text": "❌ Cancel", "callback_data": f"cancel_{code}"}]
                    ]
                }
                send_message(chat_id,
                    f"📽 Movie Detected!\n\n🎬 {title}\n📅 Year: {year or 'N/A'}\n🔑 Code: <code>{code}</code>\n\nAdd to main bot?",
                    reply_markup=keyboard)

        elif 'callback_query' in update:
            q = update['callback_query']
            user_id = q['from']['id']
            if user_id != ADMIN_ID:
                answer_callback(q['id'])
                return 'ok', 200

            data = q['data']
            action, code = data.split('_')
            chat_id = q['message']['chat']['id']

            conn = sqlite3.connect('helper_movies.db')
            cursor = conn.cursor()
            cursor.execute("SELECT title, year, message_id, description FROM pending_movies WHERE code=? AND status='pending'", (code,))
            movie = cursor.fetchone()
            if not movie:
                send_message(chat_id, "❌ Movie not found.")
                answer_callback(q['id'])
                return 'ok', 200
            title, year, msg_id, desc = movie

            if action == 'add':
                ok, _ = send_to_main_bot(code, msg_id, title, year, desc)
                if ok:
                    cursor.execute("UPDATE pending_movies SET status='added' WHERE code=?", (code,))
                    send_message(chat_id, f"✅ {title} added to main bot.")
                else:
                    send_message(chat_id, f"❌ Failed to add {title}.")
            else:
                cursor.execute("UPDATE pending_movies SET status='cancelled' WHERE code=?", (code,))
                send_message(chat_id, f"❌ {title} cancelled.")

            conn.commit()
            conn.close()
            answer_callback(q['id'])

        return 'ok', 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return 'error', 500

@app.route('/')
def index():
    return "Helper Bot with buttons"

@app.route('/health')
def health():
    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    url = f"https://movie-helper-bot-1.onrender.com/{TOKEN}"
    requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}")
    app.run(host='0.0.0.0', port=port)