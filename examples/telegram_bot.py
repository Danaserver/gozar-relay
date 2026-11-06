"""
Minimal long-polling Telegram bot that runs on a server inside Iran and talks
to Telegram through Gozar. Needs only `requests`.

    pip install requests
    RELAY=https://relay.telo.ir RELAY_KEY=gz_xxx BOT_TOKEN=123:ABC python telegram_bot.py
"""

import os
import time

import requests

RELAY = os.environ.get("RELAY", "https://relay.telo.ir")
RELAY_KEY = os.environ["RELAY_KEY"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
API = "{}/{}/telegram/bot{}".format(RELAY, RELAY_KEY, BOT_TOKEN)


def call(method, **params):
    r = requests.post("{}/{}".format(API, method), json=params, timeout=40)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description"))
    return data["result"]


def main():
    me = call("getMe")
    print("Running as @{}".format(me["username"]))
    offset = None
    while True:
        try:
            updates = call("getUpdates", timeout=30, offset=offset)
        except Exception as exc:
            print("poll error:", exc)
            time.sleep(3)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            if "text" in msg:
                text = msg["text"]
                reply = "🏓 Pong!" if text == "/ping" else "📨 " + text
                call("sendMessage", chat_id=msg["chat"]["id"], text=reply)


if __name__ == "__main__":
    main()
