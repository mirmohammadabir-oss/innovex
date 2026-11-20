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

# Multiple admin IDs, separated by commas.
raw_admin_ids = os.environ.get(
    "ADMIN_IDS",
    os.environ.get("ADMIN_ID", ""),
)

ADMIN_IDS = {
    int(item.strip())
    for item in raw_admin_ids.split(",")
    if item.strip()
}

if not ADMIN_IDS:
    raise ValueError("Set ADMIN_IDS in Render Environment.")

BASE_URL = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
WEBHOOK_PATH = "innovex-telegram-webhook"
DB_PATH = os.environ.get("DB_PATH", "/tmp/innovex.db")


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS replies_map_v2 (
                admin_chat_id INTEGER NOT NULL,
                admin_message_id INTEGER NOT NULL,
                user_chat_id INTEGER NOT NULL,
                PRIMARY KEY (admin_chat_id, admin_message_id)
            )
        """)


def save_mapping(admin_id, admin_message_id, user_chat_id):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """
            INSERT OR REPLACE INTO replies_map_v2
            (admin_chat_id, admin_message_id, user_chat_id)
            VALUES (?, ?, ?)
            """,
            (admin_id, admin_message_id, user_chat_id),
        )


def get_user_chat(admin_id, admin_message_id):
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            """
            SELECT user_chat_id FROM replies_map_v2
            WHERE admin_chat_id = ? AND admin_message_id = ?
            """,
            (admin_id, admin_message_id),
        ).fetchone()

    return row[0] if row else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if user.id in ADMIN_IDS:
        await message.reply_text(
            "INNOVEX Admin is ready.\n"
            "Reply directly to a copied user message to respond."
        )
    else:
        await message.reply_text(
            "👋 Welcome to INNOVEX Support!\n\n"
            "আপনার মেসেজ লিখে পাঠান। আমাদের টিম উত্তর দেবে।"
        )


async def receive_user_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or user.id in ADMIN_IDS:
        return

    delivered = 0

    for admin_id in ADMIN_IDS:
        try:
            copied = await context.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )

            save_mapping(
                admin_id,
                copied.message_id,
                message.chat_id,
            )

            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    "📩 INNOVEX SUPPORT\n\n"
                    f"Name: {user.first_name}\n"
                    f"User ID: {user.id}\n"
                    "উপরের কপি করা মেসেজে Reply করে উত্তর দিন।"
                ),
            )
            delivered += 1

        except TelegramError:
            log.exception("Could not deliver to admin %s", admin_id)

    if delivered == 0:
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

    if not message or not user or user.id not in ADMIN_IDS:
        return

    if not message.reply_to_message:
        return

    user_chat_id = get_user_chat(
        message.chat_id,
        message.reply_to_message.message_id,
    )

    if user_chat_id is None:
        await message.reply_text(
            "⚠️ ইউজারের কপি করা মূল মেসেজে Reply করুন।"
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
