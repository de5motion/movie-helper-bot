import logging
import sqlite3
import re
from datetime import datetime
import requests
from flask import Flask, request, jsonify
import os
from PIL import Image, ImageDraw, ImageFont
import io

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAEGsV68gS860oepV0c1nAxPUkjvBiskWdY"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    return jsonify({'status': 'ok'}), 200
MAIN_BOT_API_URL = "https://movie-bot-7qmx.onrender.com/add_movie"
API_SECRET = "movie_bot_secret_2024_67890"
ADMIN_ID = 6777360306
PRIVATE_CHANNEL = -1003800629563

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
            channel_message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Database initialized")

init_db()

# ===== POSTER GENERATION =====
def generate_poster(title, year, code, description=""):
    try:
        img = Image.new('RGB', (800, 1200), color='#0f0f1a')
        draw = ImageDraw.Draw(img)
        
        for i in range(0, 1200, 50):
            color_value = 20 + int(i / 1200 * 40)
            draw.rectangle([0, i, 800, i+50], fill=f'#{color_value:02x}{color_value:02x}{30:02x}')
        
        draw.rectangle([10, 10, 790, 1190], outline='#ffd700', width=4)
        draw.rectangle([20, 20, 780, 1180], outline='#ffd700', width=1)
        
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 58)
            year_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
            code_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
            desc_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
            footer_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            title_font = ImageFont.load_default()
            year_font = ImageFont.load_default()
            code_font = ImageFont.load_default()
            desc_font = ImageFont.load_default()
            footer_font = ImageFont.load_default()
        
        title_lines = []
        words = title.split()
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            if len(test_line) <= 25:
                current_line = test_line
            else:
                if current_line:
                    title_lines.append(current_line)
                current_line = word
        if current_line:
            title_lines.append(current_line)
        
        y_offset = 200
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            x = (800 - (bbox[2] - bbox[0])) // 2
            draw.text((x, y_offset), line, fill='#ffffff', font=title_font)
            y_offset += 70
        
        year_y = y_offset + 20
        year_text = str(year) if year else "TBA"
        bbox = draw.textbbox((0, 0), year_text, font=year_font)
        x = (800 - (bbox[2] - bbox[0])) // 2
        draw.text((x, year_y), year_text, fill='#ffd700', font=year_font)
        
        sep_y = year_y + 60
        draw.line([250, sep_y, 550, sep_y], fill='#ffd700', width=3)
        
        code_y = sep_y + 50
        code_text = f"🔑 CODE: {code}"
        bbox = draw.textbbox((0, 0), code_text, font=code_font)
        x = (800 - (bbox[2] - bbox[0])) // 2
        draw.text((x, code_y), code_text, fill='#ff6666', font=code_font)
        
        if description:
            desc_y = code_y + 90
            desc_lines = []
            words = description.split()
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if len(test_line) <= 40:
                    current_line = test_line
                else:
                    if current_line:
                        desc_lines.append(current_line)
                    current_line = word
            if current_line:
                desc_lines.append(current_line)
            
            for line in desc_lines[:4]:
                bbox = draw.textbbox((0, 0), line, font=desc_font)
                x = (800 - (bbox[2] - bbox[0])) // 2
                draw.text((x, desc_y), line, fill='#cccccc', font=desc_font)
                desc_y += 45
        
        footer_text = "🎬 @englishmoviews"
        bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
        x = (800 - (bbox[2] - bbox[0])) // 2
        draw.text((x, 1150), footer_text, fill='#888888', font=footer_font)
        
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG', quality=95)
        img_bytes.seek(0)
        return img_bytes
        
    except Exception as e:
        logging.error(f"Poster error: {e}")
        return None

def generate_caption(title, year, code, description=""):
    caption = f"🎬 <b>{title}</b>\n\n"
    if year:
        caption += f"📅 <b>Year:</b> {year}\n"
    caption += f"🔑 <b>Movie Code:</b> <code>{code}</code>\n\n"
    if description:
        caption += f"📝 <b>Description:</b>\n<i>{description[:300]}</i>\n\n"
    caption += (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>How to watch:</b>\n"
        "1️⃣ Subscribe to @englishmoviews\n"
        "2️⃣ Send the code <code>{code}</code> to @englishmoviews_bot\n"
        "3️⃣ Enjoy the movie!\n\n"
        "✨ <b>Bot:</b> @englishmoviews_bot"
    ).format(code=code)
    return caption

def send_poster_to_channel(title, year, code, description=""):
    try:
        poster = generate_poster(title, year, code, description)
        if not poster:
            return None
        
        caption = generate_caption(title, year, code, description)
        
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        files = {'photo': ('poster.png', poster, 'image/png')}
        data = {
            'chat_id': PRIVATE_CHANNEL,
            'caption': caption,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, data=data, files=files, timeout=30)
        result = response.json()
        
        if result.get('ok'):
            return result['result']['message_id']
        else:
            logging.error(f"Failed: {result}")
            return None
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

def send_message(chat_id, text):
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
    lines = text.split('\n')
    title = None
    year = None
    code = None
    description = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        code_match = re.search(r'(?:Code|Код):?\s*(\d+)', line, re.IGNORECASE)
        if code_match and not code:
            code = code_match.group(1)
            continue
        
        match = re.match(r'^(.+?)\s*\((\d{4})\)$', line)
        if match and not title:
            title = match.group(1).strip()
            year = int(match.group(2))
            continue
        
        if not title and not code_match and line and not line.startswith(('📝', 'Description')):
            title = line
        
        if line.startswith(('📝', 'Description')) or (description and line):
            desc_match = re.sub(r'^[📝]*\s*', '', line)
            desc_match = re.sub(r'^(Description|Plot):\s*', '', desc_match, flags=re.IGNORECASE)
            if description:
                description += " " + desc_match
            else:
                description = desc_match
    
    return title, year, code, description[:500]

# ===== WEBHOOK =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if not update:
            return jsonify({'status': 'ok'}), 200
        
        if 'message' in update:
            message = update['message']
            user_id = message['from']['id']
            
            if user_id != ADMIN_ID:
                return jsonify({'status': 'ok'}), 200
            
            chat_id = message['chat']['id']
            
            if 'forward_from_chat' in message:
                original_msg_id = message.get('forward_from_message_id')
                text = message.get('text', '')
                
                if not text:
                    send_message(chat_id, "❌ Please forward a text message.")
                    return jsonify({'status': 'ok'}), 200
                
                title, year, code, description = extract_movie_info(text)
                
                if not title or not code:
                    send_message(chat_id,
                        "❌ Could not extract movie info.\n\n"
                        "Make sure the message contains:\n"
                        "• Title\n"
                        "• Code: <code>12345</code>")
                    return jsonify({'status': 'ok'}), 200
                
                send_message(chat_id, f"🎨 Generating poster for: <b>{title}</b>")
                
                channel_msg_id = send_poster_to_channel(title, year, code, description)
                
                if not channel_msg_id:
                    send_message(chat_id, "❌ Failed to generate poster.")
                    return jsonify({'status': 'ok'}), 200
                
                conn = sqlite3.connect('helper_movies.db')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO movies (code, message_id, title, year, description, channel_message_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (code, original_msg_id, title, year if year else 0, description, channel_msg_id))
                conn.commit()
                conn.close()
                
                data = {
                    'secret': API_SECRET,
                    'code': code,
                    'message_id': channel_msg_id,
                    'title': title,
                    'year': year if year else 0,
                    'description': description
                }
                
                try:
                    resp = requests.post(MAIN_BOT_API_URL, json=data, timeout=30)
                    if resp.status_code == 200:
                        year_text = f" ({year})" if year else ""
                        send_message(chat_id,
                            f"✅ <b>Movie Added!</b>\n\n"
                            f"🎬 {title}{year_text}\n"
                            f"🔑 Code: <code>{code}</code>\n\n"
                            f"📸 Poster sent to channel")
                    else:
                        send_message(chat_id, f"⚠️ Poster sent, but DB error")
                except Exception as e:
                    send_message(chat_id, f"⚠️ Poster sent, but API error")
            
            elif 'text' in message and message['text'] == '/start':
                send_message(chat_id,
                    "🎬 <b>Movie Poster Bot</b>\n\n"
                    "📌 Forward a movie message to this bot\n"
                    "Bot will generate poster + caption\n"
                    "and add to main bot database")
        
        return jsonify({'status': 'ok'}), 200
        
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/')
def index():
    return "🎬 Helper Bot is running with webhook!"

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    
    # Set webhook
    webhook_url = f"https://movie-helper-bot.onrender.com/{TOKEN}"
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}")
        logging.info(f"✅ Webhook set to {webhook_url}")
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    
    app.run(host='0.0.0.0', port=port)