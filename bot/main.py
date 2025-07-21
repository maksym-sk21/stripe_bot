import os
import json
import asyncio
import stripe
import aiosqlite
from aiohttp import web
from dotenv import load_dotenv
import aiohttp_jinja2
import jinja2
from aiohttp_jinja2 import setup as jinja_setup
from jinja2 import FileSystemLoader
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "bot.db"
GUIDE_PATH = "guide.pdf"
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

stripe.api_key = STRIPE_SECRET_KEY
router = Router()

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(router)

app = web.Application()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

jinja_setup(app, loader=jinja2.FileSystemLoader(TEMPLATES_DIR))

# === Telegram UI ===
check_payment_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔑 Проверить оплату и получить гайд")]],
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
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                session_id TEXT PRIMARY KEY,
                is_paid INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()

# === Telegram handlers ===
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    session_id = message.text.split(" ", 1)[1] if " " in message.text else None
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    is_paid = 0

    async with aiosqlite.connect(DB_PATH) as db:
        # Проверим, была ли успешная оплата
        if session_id:
            async with db.execute("SELECT is_paid FROM payments WHERE session_id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == 1:
                    is_paid = 1

        # Проверим, что никто ещё не привязан к этой оплате
        async with db.execute("SELECT COUNT(*) FROM users WHERE session_id = ?", (session_id,)) as cursor:
            row = await cursor.fetchone()
            already_attached = row[0] > 0

        # Привязываем только если никто не привязан
        if session_id and not already_attached:
            await db.execute('''
                INSERT OR REPLACE INTO users (telegram_id, username, first_name, session_id, is_paid)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, session_id, is_paid))
            await db.commit()

        # Если пользователь уже в базе — не трогаем session_id
        else:
            await db.execute('''
                INSERT OR IGNORE INTO users (telegram_id, username, first_name, session_id, is_paid)
                VALUES (?, ?, ?, NULL, 0)
            ''', (user_id, username, first_name))
            await db.commit()

    await message.answer(
        "Привет! 👋 Я твой личный помощник.\n\nНажми кнопку ниже, чтобы проверить оплату и получить гайд.",
        reply_markup=check_payment_kb
    )

@router.message(lambda msg: msg.text == "🔑 Проверить оплату и получить гайд")
async def handle_payment_check(message: types.Message):
    user_id = message.from_user.id

    await message.answer("⏳ Проверяю оплату, подождите...")
    await asyncio.sleep(2)  # небольшая задержка

    async with aiosqlite.connect(DB_PATH) as db:
        # Получим текущие данные пользователя
        async with db.execute('SELECT session_id, is_paid FROM users WHERE telegram_id = ?', (user_id,)) as cursor:
            user_row = await cursor.fetchone()

        if not user_row:
            await message.answer("❌ Вы не зарегистрированы. Нажмите /start сначала.")
            return

        session_id, is_paid = user_row

        # Если уже оплачено — сразу даём доступ
        if is_paid == 1:
            await message.answer("✅ Оплата уже подтверждена. Вот твой гайд:")
        else:
            # Ищем первую НЕпривязанную session_id, у которой is_paid = 1
            async with db.execute('''
                SELECT session_id FROM payments
                WHERE is_paid = 1
                AND session_id NOT IN (SELECT session_id FROM users WHERE session_id IS NOT NULL)
                ORDER BY created_at ASC
                LIMIT 1
            ''') as cursor:
                new_session = await cursor.fetchone()

            if new_session:
                session_id = new_session[0]

                # Привязываем session_id и обновляем is_paid
                await db.execute('''
                    UPDATE users
                    SET session_id = ?, is_paid = 1
                    WHERE telegram_id = ?
                ''', (session_id, user_id))
                await db.commit()

                await message.answer("✅ Оплата найдена! Вот твой гайд:")
            else:
                await message.answer("❌ Оплата пока не найдена. Попробуй чуть позже.")
                return

        # Отправка гайда
        try:
            with open(GUIDE_PATH, "rb") as f:
                file = BufferedInputFile(f.read(), filename="guide.pdf")
                await message.answer_document(file)
            await message.answer("📘 Завтра ты получишь первое задание!")
        except FileNotFoundError:
            await message.answer("⚠️ Гайд не найден на сервере.")
# === Stripe webhook ===
async def stripe_webhook(request):
    payload = await request.read()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return web.Response(text=f"Webhook error: {e}", status=400)

    if event["type"] == "checkout.session.completed":
        session_id = event["data"]["object"].get("id")
        if session_id:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute('''
                    INSERT OR IGNORE INTO payments (session_id, is_paid)
                    VALUES (?, 1)
                ''', (session_id,))
                await db.commit()
            print(f"[Stripe] Оплата подтверждена, session_id: {session_id}")
    
    return web.Response(status=200)

# === Telegram webhook ===
async def telegram_handler(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response()

# === HTML pages ===
@aiohttp_jinja2.template("thanks.html")
async def thanks_page(request):
    session_id = request.query.get("session_id", "")
    return {"session_id": session_id}

@aiohttp_jinja2.template("admin.html")
async def admin_form(request):
    return {}

@aiohttp_jinja2.template("admin.html")
async def admin_login(request):
    data = await request.post()
    if data.get("password") == ADMIN_PASSWORD:
        response = web.HTTPFound("/dashboard")
        response.set_cookie("admin", "1")
        return response
    return {}

@aiohttp_jinja2.template("dashboard.html")
async def dashboard_page(request):
    if request.cookies.get("admin") != "1":
        return web.HTTPFound("/admin")
        
    async with aiosqlite.connect(DB_PATH) as db:
        users = await db.execute_fetchall("""
            SELECT telegram_id, username, first_name, session_id, is_paid
            FROM users
        """)
        
        sessions = await db.execute_fetchall("""
            SELECT session_id, is_paid, created_at
            FROM payments
            ORDER BY created_at DESC
        """)
        
    return aiohttp_jinja2.render_template("dashboard.html", request, {
        "users": users,
        "sessions": sessions,
    })

async def mark_paid_handler(request):
    if request.cookies.get("admin") != "1":
        return web.HTTPFound("/admin")
    user_id = int(request.match_info["user_id"])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_paid = 1 WHERE telegram_id = ?", (user_id,))
        await db.commit()
    return web.HTTPFound("/dashboard")


async def delete_user_handler(request):
    if request.cookies.get("admin") != "1":
        return web.HTTPFound("/admin")
    user_id = int(request.match_info["user_id"])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (user_id,))
        await db.commit()
    return web.HTTPFound("/dashboard")


async def bot_lifecycle(app):
    print("▶️ Startup")
    await init_db()

    task = asyncio.create_task(dp.start_polling(bot))
    
    app['bot_task'] = task
    yield

    print("⛔️ Shutting down bot polling...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app.cleanup_ctx.append(bot_lifecycle)

# === Роуты aiohttp ===
app.router.add_post("/webhook_stripe", stripe_webhook)
app.router.add_post("/webhook_bot", telegram_handler)
app.router.add_get("/thanks", thanks_page)
app.router.add_get("/admin", admin_form)
app.router.add_post("/admin", admin_login)
app.router.add_get("/dashboard", dashboard_page)
app.router.add_get("/mark_paid/{user_id}", mark_paid_handler)
app.router.add_get("/delete_user/{user_id}", delete_user_handler)


# === Запуск сервера ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[Run] Starting aiohttp server on port {port}")
    web.run_app(app, port=port)
