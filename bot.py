import os
import asyncio
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import BufferedInputFile
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSIONS_FILE = "paid_sessions.txt"
GUIDE_PATH = "guide.pdf"

router = Router()

def get_paid_sessions():
    try:
        with open(SESSIONS_FILE, "r") as f:
            return set(line.strip() for line in f.readlines())
    except FileNotFoundError:
        return set()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    session_id = message.text.split(" ", 1)[1] if " " in message.text else ""
    paid_sessions = get_paid_sessions()

    if session_id in paid_sessions:
        await message.answer("✅ Спасибо за оплату! Вот твой гайд:")
        with open(GUIDE_PATH, "rb") as f:
            document = BufferedInputFile(f.read(), filename="guide.pdf")
            await message.answer_document(document)
        await message.answer("📘 Завтра ты получишь первое задание!")
    else:
        await message.answer("❌ Оплата не найдена. Попробуй позже или свяжись с поддержкой.")

async def main():
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
