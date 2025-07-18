import os
import json
import asyncio
import stripe
import aiosqlite
from flask import Flask, request, render_template, redirect, url_for, session
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder="../templates")
app.secret_key = "supersecretkey"

DB_PATH = "bot.db"
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
admin_password = os.getenv("ADMIN_PASSWORD")

@app.route("/thanks")
def thanks():
    session_id = request.args.get("session_id")
    return render_template("thanks.html", session_id=session_id)

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        return f"Webhook error: {e}", 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        session_id = session_obj.get("id")

        if session_id:
            asyncio.run(save_paid_session(session_id))

    return {"success": True}

async def save_paid_session(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_paid = 1 WHERE session_id = ?", (session_id,))
        await db.commit()

# --- Admin login ---
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password")
        if password == admin_password:
            session["admin"] = True
            return redirect("/dashboard")
    return render_template("admin.html")

@app.route("/dashboard")
def dashboard():
    if not session.get("admin"):
        return redirect("/admin")
    users = asyncio.run(get_all_users())
    return render_template("dashboard.html", users=users)

@app.route("/mark_paid/<int:user_id>")
def mark_paid(user_id):
    asyncio.run(mark_user_paid(user_id))
    return redirect("/dashboard")

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT telegram_id, username, first_name, session_id, is_paid FROM users")
        return await cursor.fetchall()

async def mark_user_paid(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_paid = 1 WHERE telegram_id = ?", (user_id,))
        await db.commit()

if __name__ == "__main__":
    app.run(port=5000)
