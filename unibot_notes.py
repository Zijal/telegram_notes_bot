import asyncio
import os
import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# -----------------------------
# 🔹 تنظیمات
# -----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.path.join(os.path.dirname(__file__), "notes_bot.db")


# -----------------------------
# 🧰 تابع کمکی برای دریافت message
# -----------------------------
def get_message(update: Update):
    """بازگرداندن message در هر نوع update (متن یا callback)."""
    return update.message or (update.callback_query.message if update.callback_query else None)


# -----------------------------
# 🗃️ ساخت دیتابیس
# -----------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER,
                title TEXT,
                file_id TEXT,
                file_type TEXT,
                FOREIGN KEY(lesson_id) REFERENCES lessons(id)
            )
        """)
        await db.commit()


# -----------------------------
# 🏁 دستور استارت
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📚 لیست درس‌ها", callback_data="list_lessons")],
        [InlineKeyboardButton("➕ افزودن درس جدید", callback_data="add_lesson")]
    ]

    text = (
        "سلام 👋\n"
        "به ربات جزوه‌دان دانشگاه خوش اومدی!\n"
        "از دکمه‌های زیر استفاده کن 👇"
    )

    message = get_message(update)
    if message:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# -----------------------------
# 📘 لیست درس‌ها
# -----------------------------
async def list_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        async with db.execute("SELECT id, name FROM lessons") as cursor:
            lessons = await cursor.fetchall()

    message = get_message(update)
    if not lessons:
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="home")]]
        await message.reply_text(
            "هنوز درسی اضافه نشده 😕\nاز منوی اصلی 'افزودن درس' رو بزن.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"📖 {name}", callback_data=f"lesson|{lesson_id}")]
        for lesson_id, name in lessons
    ]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])

    await message.reply_text("📚 درس‌های موجود:", reply_markup=InlineKeyboardMarkup(keyboard))


# -----------------------------
# ➕ افزودن درس جدید
# -----------------------------
async def add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = get_message(update)
    await message.reply_text("📝 نام درس جدید رو بنویس (مثلاً: ریاضی ۱):")
    context.user_data.clear()
    context.user_data["adding_lesson"] = True


# -----------------------------
# 📥 آپلود جزوه
# -----------------------------
async def upload_note(update: Update, context: ContextTypes.DEFAULT_TYPE, lesson_id):
    file = update.message.document or (update.message.photo[-1] if update.message.photo else None)
    message = get_message(update)

    if not file:
        await message.reply_text("❌ لطفاً فایل یا عکس ارسال کن.")
        return

    file_id = file.file_id
    file_type = "document" if update.message.document else "photo"
    title = context.user_data.get("note_title", "بدون عنوان")

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("INSERT INTO notes (lesson_id, title, file_id, file_type) VALUES (?, ?, ?, ?)",
            (lesson_id, title, file_id, file_type)
        )
        await db.commit()

    await message.reply_text("✅ جزوه با موفقیت ذخیره شد!")
    context.user_data.clear()


# -----------------------------
# 📂 نمایش جزوه‌های هر درس
# -----------------------------
async def show_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lesson_id = int(query.data.split("|")[1])

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        async with db.execute("SELECT name FROM lessons WHERE id=?", (lesson_id,)) as c:
            lesson = await c.fetchone()
        async with db.execute("SELECT id, title FROM notes WHERE lesson_id=?", (lesson_id,)) as c:
            notes = await c.fetchall()

    lesson_name = lesson[0] if lesson else "نامشخص"

    keyboard = [
        [InlineKeyboardButton(f"📄 {title}", callback_data=f"note|{note_id}")]
        for note_id, title in notes
    ]
    keyboard.append([InlineKeyboardButton("⬆️ بارگذاری جزوه جدید", callback_data=f"upload|{lesson_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="list_lessons")])

    await query.message.reply_text(
        f"📘 درس: {lesson_name}\nجزوه‌های موجود:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# -----------------------------
# 📄 نمایش جزوه خاص
# -----------------------------
async def show_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_id = int(update.callback_query.data.split("|")[1])
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        async with db.execute("SELECT file_id, file_type, title FROM notes WHERE id=?", (note_id,)) as c:
            note = await c.fetchone()

    if note:
        file_id, file_type, title = note
        if file_type == "document":
            await update.callback_query.message.reply_document(file_id, caption=f"📄 {title}")
        else:
            await update.callback_query.message.reply_photo(file_id, caption=f"🖼️ {title}")
    else:
        await update.callback_query.message.reply_text("❌ فایل پیدا نشد.")


# -----------------------------
# ⚙️ کال‌بک‌ها
# -----------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    context.user_data.pop("awaiting_title", None)
    context.user_data.pop("adding_lesson", None)

    try:
        if data == "list_lessons":
            await list_lessons(update, context)
        elif data == "add_lesson":
            await add_lesson(update, context)
        elif data.startswith("lesson|"):
            await show_lesson(update, context)
        elif data.startswith("note|"):
            await show_note(update, context)
        elif data.startswith("upload|"):
            lesson_id = int(data.split("|")[1])
            context.user_data.clear()
            context.user_data["uploading_to"] = lesson_id
            context.user_data["awaiting_title"] = True
            await update.callback_query.message.reply_text("📑 عنوان جزوه رو بنویس:")
        elif data == "home":
            await start(update, context)
    except Exception as e:
        await get_message(update).reply_text(f"⚠️ خطا رخ داد:\n{e}")


# -----------------------------
# 📨 پیام‌های متنی
# -----------------------------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if context.user_data.get("adding_lesson"):
        lesson_name = message.text.strip()
        async with aiosqlite.connect(DB_PATH, timeout=30) as db:
            await db.execute("INSERT OR IGNORE INTO lessons (name) VALUES (?)", (lesson_name,))
            await db.commit()
        context.user_data.clear()
        await message.reply_text(f"✅ درس '{lesson_name}' اضافه شد!")
        return

    if context.user_data.get("awaiting_title"):
        context.user_data["note_title"] = message.text.strip()
        context.user_data.pop("awaiting_title", None)
        await message.reply_text("📤 حالا فایل جزوه (PDF یا عکس) رو بفرست:")
        return

    await message.reply_text("❗ لطفاً از منوی اصلی استفاده کن.")


# -----------------------------
# 📎 فایل‌های ارسالی (PDF یا عکس)
# -----------------------------
async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lesson_id = context.user_data.get("uploading_to")
    if lesson_id:
        await upload_note(update, context, lesson_id)
    else:
        await update.message.reply_text("❗ اول باید مشخص کنی جزوه مربوط به کدوم درس هست.")


# -----------------------------
# 🚀 اجرای اصلی برنامه
# -----------------------------
async def main():
    await init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, file_handler))

    print("🤖 ربات جزوه‌دان بدون ارور آماده است! Ctrl+C برای خروج.")
    await app.run_polling()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())