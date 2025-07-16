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

# 🔒 HTML-шаблон кастомной страницы после оплаты
THANKS_PAGE_TEMPLATE = """
<html>
  <head>
    <meta charset="utf-8">
    <title>Оплата успешна</title>
    <style>
      body {{ font-family: sans-serif; text-align: center; margin-top: 100px; }}
      .btn {{ background: #0088cc; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-size: 18px; }}
    </style>
  </head>
  <body>
    <h1>✅ Спасибо за оплату!</h1>
    <p>Нажмите на кнопку ниже, чтобы открыть Telegram и получить ваш гайд</p>
    <a class="btn" href="https://t.me/meta_course_bot?start={{session_id}}">Открыть Telegram</a>
  </body>
</html>
"""

# 🔄 Кастомная страница благодарности (если session_id передан через ?session_id=...)
@app.route("/thanks")
def thanks():
    session_id = request.args.get("session_id", "")
    if not session_id:
        return "Ошибка: отсутствует session_id", 400
    return render_template_string(THANKS_PAGE_TEMPLATE, session_id=session_id)

# 🎯 Альтернатива: /success/<session_id> — красиво и читаемо
@app.route("/success/<session_id>")
def success_page(session_id):
    return render_template_string(THANKS_PAGE_TEMPLATE, session_id=session_id)

# 💾 Запись session_id в файл
def save_session(session_id: str):
    with open(SESSIONS_FILE, "a") as f:
        f.write(session_id + "\n")

# 🔄 Webhook от Stripe
@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
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

# ✅ Локальный запуск — можно оставить для отладки
if __name__ == "__main__":
    app.run(port=5000)
