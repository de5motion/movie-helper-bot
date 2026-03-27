import logging
import sqlite3
import re
from datetime import datetime
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import os
from PIL import Image, ImageDraw, ImageFont
import io

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAEGsV68gS860oepV0c1nAxPUkjvBiskWdY"
MAIN_BOT_API_URL = "https://movie-bot-7qmx.onrender.com/add_movie"
API_SECRET = "movie_bot_secret_2024_67890"
ADMIN_ID = 6777360306
PRIVATE_CHANNEL = -1003800629563

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
        CREATE TABLE IF NOT EXISTS pending_movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            message_id INTEGER,
            title TEXT,
            year INTEGER,
            description TEXT,
            channel_message_id INTEGER,
            poster_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logging.info("Helper database initialized")

init_db()

# ===== POSTER GENERATION =====
def generate_poster(title, year, code, description=""):
    """Generate beautiful movie poster"""
    try:
        # Create image with gradient background
        img = Image.new('RGB', (800, 1200), color='#0f0f1a')
        draw = ImageDraw.Draw(img)
        
        # Draw gradient-like effect (simple rectangles)
        for i in range(0, 1200, 50):
            color_value = 20 + int(i / 1200 * 40)
            draw.rectangle([0, i, 800, i+50], fill=f'#{color_value:02x}{color_value:02x}{30:02x}')
        
        # Draw gold border
        draw.rectangle([10, 10, 790, 1190], outline='#ffd700', width=4)
        
        # Draw inner border
        draw.rectangle([20, 20, 780, 1180], outline='#ffd700', width=1)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 58)
            year_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
            code_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
            desc_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
            tagline_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            title_font = ImageFont.load_default()
            year_font = ImageFont.load_default()
            code_font = ImageFont.load_default()
            desc_font = ImageFont.load_default()
            tagline_font = ImageFont.load_default()
        
        # Draw title (centered, wrapped)
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
            text_width = bbox[2] - bbox[0]
            x = (800 - text_width) // 2
            draw.text((x, y_offset), line, fill='#ffffff', font=title_font)
            y_offset += 70
        
        # Draw year with background
        year_y = y_offset + 20
        year_text = str(year) if year else "TBA"
        bbox = draw.textbbox((0, 0), year_text, font=year_font)
        text_width = bbox[2] - bbox[0]
        x = (800 - text_width) // 2
        draw.text((x, year_y), year_text, fill='#ffd700', font=year_font)
        
        # Draw separator
        separator_y = year_y + 60
        draw.line([250, separator_y, 550, separator_y], fill='#ffd700', width=3)
        
        # Draw code with background
        code_y = separator_y + 50
        code_text = f"🔑 CODE: {code}"
        bbox = draw.textbbox((0, 0), code_text, font=code_font)
        text_width = bbox[2] - bbox[0]
        x = (800 - text_width) // 2
        draw.text((x, code_y), code_text, fill='#ff6666', font=code_font)
        
        # Draw description if exists
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
                text_width = bbox[2] - bbox[0]
                x = (800 - text_width) // 2
                draw.text((x, desc_y), line, fill='#cccccc', font=desc_font)
                desc_y += 45
        
        # Draw tagline/footer
        footer_y = 1150
        footer_text = "🎬 @englishmoviews"
        bbox = draw.textbbox((0, 0), footer_text, font=tagline_font)
        text_width = bbox[2] - bbox[0]
        x = (800 - text_width) // 2
        draw.text((x, footer_y), footer_text, fill='#888888', font=tagline_font)
        
        # Save to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG', quality=95)
        img_bytes.seek(0)
        
        return img_bytes
        
    except Exception as e:
        logging.error(f"Poster generation error: {e}")
        return None

def generate_caption(title, year, code, description=""):
    """Generate beautiful HTML caption for the movie"""
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
    """Generate poster and send to channel with beautiful caption"""
    try:
        # Generate poster
        poster = generate_poster(title, year, code, description)
        if not poster:
            return None
        
        # Generate caption
        caption = generate_caption(title, year, code, description)
        
        # Send to channel
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
            logging.error(f"Failed to send poster: {result}")
            return None
            
    except Exception as e:
        logging.error(f"Error sending poster: {e}")
        return None

def extract_movie_info(text):
    """Extract movie information from forwarded message"""
    lines = text.split('\n')
    title = None
    year = None
    code = None
    description = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for code
        code_match = re.search(r'(?:Code|Код):?\s*(\d+)', line, re.IGNORECASE)
        if code_match and not code:
            code = code_match.group(1)
            continue
        
        # Check for title with year
        match = re.match(r'^(.+?)\s*\((\d{4})\)$', line)
        if match and not title:
            title = match.group(1).strip()
            year = int(match.group(2))
            continue
        
        # Check for title without year
        if not title and not code_match and line and not line.startswith(('📝', 'Description', 'desc')):
            title = line
        
        # Collect description
        if line.startswith(('📝', 'Description', 'desc', 'Plot')) or (description and line and not code_match):
            desc_match = re.sub(r'^[📝]*\s*', '', line)
            desc_match = re.sub(r'^(Description|Plot):\s*', '', desc_match, flags=re.IGNORECASE)
            if description:
                description += " " + desc_match
            else:
                description = desc_match
    
    # Clean up description
    description = ' '.join(description.split())
    
    return title, year, code, description[:500]

def send_to_main_bot(code, message_id, title, year, description):
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
        
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)

def save_movie_to_db(code, message_id, title, year, description, channel_msg_id):
    """Save movie to database"""
    try:
        conn = sqlite3.connect('helper_movies.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO pending_movies (code, message_id, title, year, description, channel_message_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'added')
        ''', (code, message_id, title, year if year else 0, description, channel_msg_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error saving movie: {e}")
        return False

def is_admin(user_id):
    return user_id == ADMIN_ID

# ===== TELEGRAM HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    
    await update.message.reply_text(
        "🎬 <b>Movie Poster Bot v2.0</b>\n\n"
        "✨ <b>Features:</b>\n"
        "• 🎨 Beautiful movie posters\n"
        "• 📝 Rich HTML captions\n"
        "• 🔑 Auto-extract movie info\n"
        "• 💾 Auto-add to database\n"
        "• 📤 Send to private channel\n\n"
        "<b>📌 How to use:</b>\n"
        "1. Forward a movie message to this bot\n"
        "2. Bot extracts: Title, Year, Code, Description\n"
        "3. Generates poster + caption\n"
        "4. Sends to private channel\n"
        "5. Adds to main bot database\n\n"
        "<b>Commands:</b>\n"
        "/pending - Show recent movies\n"
        "/stats - Show statistics",
        parse_mode="HTML"
    )

async def handle_forwarded_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    message = update.message
    
    if not message.forward_from_chat:
        await update.message.reply_text("❌ Please forward a message from your private channel.")
        return
    
    original_msg_id = message.forward_from_message_id
    
    if not message.text:
        await update.message.reply_text("❌ Please forward a text message with movie info.")
        return
    
    # Show progress
    progress_msg = await update.message.reply_text("🎨 Processing movie info...")
    
    # Extract movie info
    title, year, code, description = extract_movie_info(message.text)
    
    if not title or not code:
        await progress_msg.edit_text(
            "❌ Could not extract movie information.\n\n"
            "Make sure the message contains:\n"
            "• Title (with or without year)\n"
            "• Code: <code>12345</code>\n\n"
            f"<b>Extracted:</b>\n"
            f"Title: {title if title else '❌ Not found'}\n"
            f"Year: {year if year else 'Not found (optional)'}\n"
            f"Code: {code if code else '❌ Not found'}",
            parse_mode="HTML"
        )
        return
    
    await progress_msg.edit_text(f"🎨 Generating poster for: <b>{title}</b>", parse_mode="HTML")
    
    # Generate and send poster to channel
    channel_msg_id = send_poster_to_channel(title, year, code, description)
    
    if not channel_msg_id:
        await progress_msg.edit_text("❌ Failed to generate poster. Please try again.")
        return
    
    await progress_msg.edit_text("✅ Poster sent to channel!\n📤 Adding to database...")
    
    # Save to database
    save_movie_to_db(code, original_msg_id, title, year, description, channel_msg_id)
    
    # Send to main bot
    success, result = send_to_main_bot(code, channel_msg_id, title, year, description)
    
    if success:
        year_text = f" ({year})" if year else ""
        await progress_msg.edit_text(
            f"✅ <b>Movie Added Successfully!</b>\n\n"
            f"🎬 {title}{year_text}\n"
            f"🔑 Code: <code>{code}</code>\n\n"
            f"📸 <b>Poster & caption sent to channel</b>\n"
            f"💾 <b>Added to main bot database</b>\n\n"
            f"✨ Movie is now available for users!",
            parse_mode="HTML"
        )
        logging.info(f"✅ Movie added: {code} - {title}")
    else:
        await progress_msg.edit_text(
            f"⚠️ <b>Poster sent but database error</b>\n\n"
            f"Error: {result}\n\n"
            f"Poster is in channel, but movie not added to database.\n"
            f"Please try again or add manually.",
            parse_mode="HTML"
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    await update.message.reply_text(
        "📌 Please forward a movie message from your private channel.\n"
        "Use /start for help."
    )

async def pending_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    conn = sqlite3.connect('helper_movies.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT code, title, year, created_at FROM pending_movies WHERE status = 'added' ORDER BY created_at DESC LIMIT 20"
    )
    movies = cursor.fetchall()
    conn.close()
    
    if not movies:
        await update.message.reply_text("📭 No movies added yet.")
        return
    
    text = "📋 <b>Recently Added Movies:</b>\n\n"
    for code, title, year, created_at in movies:
        year_text = f" ({year})" if year and year != 0 else ""
        text += f"• <b>{title}</b>{year_text} - <code>{code}</code>\n"
        text += f"  Added: {created_at[:16]}\n\n"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    conn = sqlite3.connect('helper_movies.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM pending_movies WHERE status = 'added'")
    added = cursor.fetchone()[0]
    
    conn.close()
    
    await update.message.reply_text(
        f"📊 <b>Movie Poster Bot Statistics</b>\n\n"
        f"✅ Movies added: {added}\n"
        f"🎬 Posters generated: {added}\n"
        f"📝 Captions generated: {added}\n\n"
        f"✨ All movies have:\n"
        f"• Beautiful poster\n"
        f"• Rich HTML caption\n"
        f"• Auto-added to database",
        parse_mode="HTML"
    )

# ===== MAIN =====
def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pending", pending_movies))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED, handle_text))
    application.add_handler(MessageHandler(filters.FORWARDED, handle_forwarded_message))
    
    print("🤖 Movie Poster Bot v2.0 started...")
    print(f"✅ Main bot API: {MAIN_BOT_API_URL}")
    print(f"✅ Private channel: {PRIVATE_CHANNEL}")
    print("✨ Features: Beautiful posters + Rich captions")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()