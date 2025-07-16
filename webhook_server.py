import os
import json
import stripe
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

app = Flask(__name__)
SESSIONS_FILE = "paid_sessions.txt"

THANKS_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Оплата подтверждена</title>
</head>
<body>
  <h1>Спасибо за оплату!</h1>
  <p>Нажмите кнопку ниже, чтобы перейти в Telegram-бот и получить доступ к курсу.</p>
  <a href="https://t.me/your_bot_username?start={{ session_id }}" 
     target="_blank" 
     style="display:inline-block;padding:15px 30px;background:#0088cc;color:#fff;text-decoration:none;border-radius:8px;font-size:18px;">
    Перейти в бот
  </a>
</body>
</html>
"""

def save_session(session_id: str):
    with open(SESSIONS_FILE, "a") as f:
        f.write(session_id + "\n")

def get_paid_sessions():
    try:
        with open(SESSIONS_FILE, "r") as f:
            return set(line.strip() for line in f.readlines())
    except FileNotFoundError:
        return set()

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except Exception as e:
        print("❌ Webhook error:", e)
        return jsonify(success=False), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session["id"]
        save_session(session_id)
        print(f"✅ Оплата прошла. Сохранён session_id: {session_id}")
    else:
        print(f"ℹ️ Получено событие {event['type']} (не обрабатывается)")

    return jsonify(success=True), 200

@app.route("/thanks")
def thanks():
    session_id = request.args.get("session_id", "")
    if not session_id:
        return "Ошибка: отсутствует session_id", 400
    return render_template_string(THANKS_PAGE_TEMPLATE, session_id=session_id)


if __name__ == "__main__":
    app.run(port=5000)
