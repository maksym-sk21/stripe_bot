import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GUIDE_PATH = "guide.pdf"
DB_PATH = "bot.db"

router = Router()

# Кнопка
check_payment_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔑 Проверить оплату и получить гайд")]
    ],
    resize_keyboard=True
)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                session_id TEXT,
                is_paid INTEGER DEFAULT 0
            )
        ''')
        await db.commit()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    session_id = message.text.split(" ", 1)[1] if " " in message.text else None
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO users (telegram_id, username, first_name, session_id, is_paid)
            VALUES (?, ?, ?, ?, COALESCE((SELECT is_paid FROM users WHERE telegram_id = ?), 0))
        ''', (user_id, username, first_name, session_id, user_id))
        await db.commit()

    await message.answer(
        "Привет! 👋 Я твой личный помощник.\n\nНажми кнопку ниже, чтобы проверить оплату и получить гайд.",
        reply_markup=check_payment_kb
    )

@router.message(lambda msg: msg.text == "🔑 Проверить оплату и получить гайд")
async def handle_payment_check(message: types.Message):
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT is_paid FROM users WHERE telegram_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()

    if row and row[0] == 1:
        await message.answer("✅ Спасибо за оплату! Вот твой гайд:")
        with open(GUIDE_PATH, "rb") as f:
            file = BufferedInputFile(f.read(), filename="guide.pdf")
            await message.answer_document(file)
        await message.answer("📘 Завтра ты получишь первое задание!")
    else:
        await message.answer("❌ Оплата не найдена. Попробуй позже или свяжись с поддержкой.")

async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
