import logging
import os
import sqlite3

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
BASE_URL = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
WEBHOOK_PATH = "innovex-telegram-webhook"
DB_PATH = os.environ.get("DB_PATH", "/tmp/innovex.db")


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS replies_map (
                admin_message_id INTEGER PRIMARY KEY,
                user_chat_id INTEGER NOT NULL
            )
        """)


def save_mapping(admin_message_id, user_chat_id):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """INSERT OR REPLACE INTO replies_map
               (admin_message_id, user_chat_id)
               VALUES (?, ?)""",
            (admin_message_id, user_chat_id),
        )


def get_user_chat(admin_message_id):
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            """SELECT user_chat_id FROM replies_map
               WHERE admin_message_id = ?""",
            (admin_message_id,),
        ).fetchone()
    return row[0] if row else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id == ADMIN_ID:
        await update.effective_message.reply_text(
            "INNOVEX Admin is ready. User messages will arrive here."
        )
    else:
        await update.effective_message.reply_text(
            "👋 Welcome to INNOVEX Support!\n\n"
            "আপনার মেসেজ লিখে পাঠান। আমাদের টিম উত্তর দেবে।"
        )


async def receive_user_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or user.id == ADMIN_ID:
        return

    try:
        copied = await context.bot.copy_message(
            chat_id=ADMIN_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )

        save_mapping(copied.message_id, message.chat_id)

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "📩 INNOVEX SUPPORT\n\n"
                f"Name: {user.first_name}\n"
                f"User ID: {user.id}\n"
                "উপরের কপি করা মেসেজে Reply করে উত্তর দিন।"
            ),
        )

    except TelegramError:
        log.exception("Could not forward user message")
        try:
            await message.reply_text(
                "দুঃখিত, মেসেজ পাঠানো যায়নি। পরে আবার চেষ্টা করুন।"
            )
        except TelegramError:
            log.exception("Could not notify user")


async def admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if (
        not message
        or not user
        or user.id != ADMIN_ID
        or not message.reply_to_message
    ):
        return

    target_id = message.reply_to_message.message_id
    user_chat_id = get_user_chat(target_id)

    if not user_chat_id:
        await message.reply_text(
            "ইউজারের কপি করা মূল মেসেজে Reply করুন।"
        )
        return

    try:
        await context.bot.copy_message(
            chat_id=user_chat_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
        await message.reply_text("✅ উত্তর পাঠানো হয়েছে।")

    except TelegramError:
        log.exception("Could not send admin reply")
        await message.reply_text(
            "❌ উত্তর পাঠানো যায়নি। ইউজার বট Start করেছেন কি না দেখুন।"
        )


def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.REPLY
            & ~filters.COMMAND,
            admin_reply,
        ),
        group=0,
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            receive_user_message,
        ),
        group=1,
    )

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=f"{BASE_URL}/{WEBHOOK_PATH}",
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
