import logging
import sqlite3
import re
from datetime import datetime
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import os

# ===== CONFIGURATION =====
TOKEN = "8616873829:AAF0BF9bx4R4wEcMzvhk24zD75Kl82Ieedo"  # Helper bot token
MAIN_BOT_API_URL = "https://movie-bot-8-9cnw.onrender.com/add_movie"
API_SECRET = "movie_bot_secret_2024_67890"
ADMIN_ID = 6777360306  # Your Telegram ID

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ===== DATABASE FOR HELPER BOT (stores pending movies) =====
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
    logging.info("Helper database initialized")

init_db()

# ===== HELPER FUNCTIONS =====
def extract_movie_info(text):
    """Extract movie information from forwarded message"""
    lines = text.split('\n')
    title = None
    year = None
    code = None
    
    for line in lines:
        line = line.strip()
        # Check for title and year like "Movie Title (2024)"
        match = re.match(r'^(.+?)\s*\((\d{4})\)$', line)
        if match and not title:
            title = match.group(1).strip()
            year = int(match.group(2))
        
        # Check for code like "Code: 12345" or "🔑 Code: 12345"
        code_match = re.search(r'(?:Code|Код):?\s*(\d+)', line, re.IGNORECASE)
        if code_match and not code:
            code = code_match.group(1)
    
    return title, year, code

def save_pending_movie(code, message_id, title, year, description, channel_msg_id):
    """Save pending movie to database"""
    try:
        conn = sqlite3.connect('helper_movies.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO pending_movies (code, message_id, title, year, description, channel_message_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ''', (code, message_id, title, year, description, channel_msg_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error saving pending movie: {e}")
        return False

def send_to_main_bot(code, message_id, title, year, description):
    """Send movie to main bot via API"""
    try:
        data = {
            'secret': API_SECRET,
            'code': code,
            'message_id': message_id,
            'title': title,
            'year': year,
            'description': description
        }
        
        response = requests.post(MAIN_BOT_API_URL, json=data, timeout=30)
        
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)

def is_admin(user_id):
    """Check if user is admin"""
    return user_id == ADMIN_ID

# ===== TELEGRAM HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
    
    await update.message.reply_text(
        "🎬 <b>Helper Bot for Movie Management</b>\n\n"
        "📌 <b>How to use:</b>\n"
        "1. Forward a movie message from your PRIVATE CHANNEL to this bot\n"
        "2. The bot will extract movie info (title, year, code)\n"
        "3. Confirm to add to main bot's database\n\n"
        "<b>Commands:</b>\n"
        "/pending - Show pending movies\n"
        "/stats - Show statistics\n"
        "/cancel - Cancel current operation",
        parse_mode="HTML"
    )

async def handle_forwarded_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded messages from private channel"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    message = update.message
    
    # Check if it's a forwarded message
    if not message.forward_from_chat:
        await update.message.reply_text("❌ Please forward a message from your private channel.")
        return
    
    # Get original message details
    original_msg_id = message.forward_from_message_id
    forwarded_from = message.forward_from_chat
    
    # Get the text of the forwarded message
    if not message.text:
        await update.message.reply_text("❌ Please forward a text message with movie info.")
        return
    
    # Extract movie info
    title, year, code = extract_movie_info(message.text)
    
    if not title or not year or not code:
        await update.message.reply_text(
            "❌ Could not extract movie information.\n\n"
            "Make sure the message contains:\n"
            "• Title with year in parentheses: <b>Movie Title (2024)</b>\n"
            "• Code: <code>12345</code>\n\n"
            f"<b>Extracted:</b>\n"
            f"Title: {title}\n"
            f"Year: {year}\n"
            f"Code: {code}",
            parse_mode="HTML"
        )
        return
    
    # Save to database
    save_pending_movie(code, original_msg_id, title, year, message.text, message.message_id)
    
    # Store in context for confirmation
    context.user_data['pending_movie'] = {
        'code': code,
        'message_id': original_msg_id,
        'title': title,
        'year': year,
        'description': message.text[:500],
        'channel_msg_id': message.message_id
    }
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Add Movie", callback_data="add_movie")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_movie")]
    ])
    
    await update.message.reply_text(
        f"📽 <b>Movie Detected!</b>\n\n"
        f"🎬 Title: <b>{title}</b>\n"
        f"📅 Year: {year}\n"
        f"🔑 Code: <code>{code}</code>\n\n"
        f"From Channel Message ID: {original_msg_id}\n\n"
        f"✅ Add this movie to main bot?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages (not forwarded)"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    await update.message.reply_text(
        "Please forward a movie message from your private channel.\n"
        "Use /start for help."
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.edit_message_text("❌ Unauthorized")
        return
    
    data = query.data
    pending = context.user_data.get('pending_movie')
    
    if not pending:
        await query.edit_message_text("❌ No pending movie. Please forward a new movie.")
        return
    
    if data == "add_movie":
        # Send to main bot
        success, result = send_to_main_bot(
            pending['code'],
            pending['message_id'],
            pending['title'],
            pending['year'],
            pending['description']
        )
        
        if success:
            # Update database status
            conn = sqlite3.connect('helper_movies.db')
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pending_movies SET status = 'added' WHERE code = ? AND channel_message_id = ?",
                (pending['code'], pending['channel_msg_id'])
            )
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ <b>Movie Added Successfully!</b>\n\n"
                f"🎬 {pending['title']} ({pending['year']})\n"
                f"🔑 Code: <code>{pending['code']}</code>\n\n"
                f"Movie is now available in the main bot.",
                parse_mode="HTML"
            )
            logging.info(f"Movie {pending['code']} added to main bot")
        else:
            await query.edit_message_text(
                f"❌ <b>Failed to add movie</b>\n\n"
                f"Error: {result}\n\n"
                f"Please check that the main bot is running and accessible.",
                parse_mode="HTML"
            )
        
        # Clear context
        context.user_data.pop('pending_movie', None)
    
    elif data == "cancel_movie":
        # Update database status
        conn = sqlite3.connect('helper_movies.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pending_movies SET status = 'cancelled' WHERE code = ? AND channel_message_id = ?",
            (pending['code'], pending['channel_msg_id'])
        )
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"❌ Cancelled.\n\nMovie {pending['title']} ({pending['year']}) was not added.",
            parse_mode="HTML"
        )
        context.user_data.pop('pending_movie', None)

async def pending_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending movies"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    conn = sqlite3.connect('helper_movies.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT code, title, year, created_at FROM pending_movies WHERE status = 'pending' ORDER BY created_at DESC"
    )
    movies = cursor.fetchall()
    conn.close()
    
    if not movies:
        await update.message.reply_text("📭 No pending movies.")
        return
    
    text = "📋 <b>Pending Movies:</b>\n\n"
    for code, title, year, created_at in movies:
        text += f"• <b>{title}</b> ({year}) - <code>{code}</code>\n"
        text += f"  Added: {created_at[:16]}\n\n"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show helper bot statistics"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    conn = sqlite3.connect('helper_movies.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM pending_movies WHERE status = 'pending'")
    pending = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pending_movies WHERE status = 'added'")
    added = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pending_movies WHERE status = 'cancelled'")
    cancelled = cursor.fetchone()[0]
    
    conn.close()
    
    await update.message.reply_text(
        f"📊 <b>Helper Bot Statistics</b>\n\n"
        f"⏳ Pending: {pending}\n"
        f"✅ Added: {added}\n"
        f"❌ Cancelled: {cancelled}\n"
        f"📦 Total Processed: {pending + added + cancelled}",
        parse_mode="HTML"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if context.user_data.get('pending_movie'):
        context.user_data.pop('pending_movie')
        await update.message.reply_text("✅ Current operation cancelled.")
    else:
        await update.message.reply_text("ℹ️ No pending operation.")

# ===== MAIN =====
def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pending", pending_movies))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED, handle_text))
    application.add_handler(MessageHandler(filters.FORWARDED, handle_forwarded_message))
    
    # Start bot
    print("🤖 Helper Bot started...")
    print(f"Main bot API URL: {MAIN_BOT_API_URL}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()