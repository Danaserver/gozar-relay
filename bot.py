import requests
import time
import json

# ===== تنظیمات =====
BOT_TOKEN = "TOKEN_خودت_را_اینجا_بذار"

# کد اختصاصی امنیتی این ربات (که از پنل https://robot.telo.ir/Relay دریافت می‌کنی)
RELAY_KEY = "telo_sec_8a2f4e"

# آدرس رله اختصاصی برای سرور ایران:
API_URL = f"https://robot.telo.ir/Relay/{RELAY_KEY}/bot{BOT_TOKEN}"

# ===== توابع اصلی =====

def get_updates(offset=None):
    """دریافت آپدیت‌های جدید از تلگرام"""
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        response = requests.get(f"{API_URL}/getUpdates", params=params, timeout=35)
        return response.json()
    except Exception as e:
        print(f"خطا در دریافت آپدیت: {e}")
        return None


def send_message(chat_id, text):
    """ارسال پیام به کاربر"""
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(f"{API_URL}/sendMessage", data=data)
        return response.json()
    except Exception as e:
        print(f"خطا در ارسال پیام: {e}")
        return None


def handle_message(message):
    """پردازش پیام دریافتی"""
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    username = message["from"].get("username", "کاربر")
    first_name = message["from"].get("first_name", "دوست")

    print(f"پیام از {first_name} (@{username}): {text}")

    # هندل کردن دستورات
    if text == "/start":
        reply = (
            f"سلام {first_name}! 👋\n\n"
            "ربات تست با موفقیت راه‌اندازی شد ✅\n\n"
            "دستورات موجود:\n"
            "/start - شروع\n"
            "/help - راهنما\n"
            "/ping - تست اتصال\n\n"
            "هر پیامی بفرستی برات echo میکنم 😊"
        )

    elif text == "/help":
        reply = (
            "📖 <b>راهنمای ربات</b>\n\n"
            "/start - پیام خوش‌آمدگویی\n"
            "/help - این راهنما\n"
            "/ping - تست اتصال و وضعیت سرور\n\n"
            "هر پیام دیگه‌ای بفرستی، اکوش میکنم."
        )

    elif text == "/ping":
        reply = "🏓 Pong! ربات آنلاین و سالمه ✅"

    elif text:
        # echo کردن پیام
        reply = f"📨 تو گفتی:\n{text}"

    else:
        reply = "نوع پیام پشتیبانی نمیشه!"

    send_message(chat_id, reply)


def main():
    """حلقه اصلی ربات"""
    print("ربات شروع به کار کرد...")
    offset = None

    while True:
        updates = get_updates(offset)

        if updates and updates.get("ok"):
            for update in updates.get("result", []):
                offset = update["update_id"] + 1

                if "message" in update:
                    handle_message(update["message"])

        time.sleep(1)


if __name__ == "__main__":
    main()
