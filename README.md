# Telegram Bot API Relay & Admin Panel

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-brightgreen.svg)](https://www.python.org/)

[فارسی](#راهنمای-فارسی) | [English](#english-documentation)

---

<a name="راهنمای-فارسی"></a>
# راهنمای فارسی

یک رله (پروکسی معکوس شفاف) سبک و مستقل برای ارتباط ربات‌های تلگرام روی سرورهای داخل ایران با `api.telegram.org`، به همراه پنل مدیریت تحت وب محافظت‌شده با کپچا و سیستم احراز هویت اختصاصی برای هر ربات.

### چرا این پروژه؟
در سرورهای داخل ایران به دلیل فیلترینگ تلگرام، ارتباط مستقیم با `api.telegram.org` مسدود است. این ابزار روی یک سرور خارج از کشور (VPS لینوکس یا هاست cPanel) مستقر می‌شود و به عنوان پل ارتباطی امن عمل می‌کند.

### ویژگی‌های کلیدی
- **نصب با یک دستور روی سرور خام:** نصب خودکار تمام پیش‌نیازها روی اوبونتو، دبیان، سنت‌او‌اس، آلما‌لینوکس و ... حتی اگر پایتون از قبل نصب نباشد.
- **بدون نیاز به کتابخانه جانبی (Zero Dependencies):** نوشته شده با ماژول‌های استاندارد پایتون ۳ بدون نیاز به `pip install`.
- **پشتیبانی دوگانه (Dual-Mode):** قابلیت اجرا به عنوان وب‌سرور مستقل چندنخی (Multi-Threaded) روی VPS و یا به صورت اسکریپت CGI روی هاست‌های اشتراکی cPanel / LiteSpeed / Apache.
- **تشخیص خودکار دامنه و سابدامنه:** بدون نیاز به هاردکد کردن دامنه؛ سیستم آدرس پایه و پروتکل را پویا تشخیص می‌دهد.
- **کد امنیتی اختصاصی برای هر ربات:** امکان تعریف، فعال/غیرفعال کردن یا حذف کلید مجزا برای هر ربات جهت جلوگیری از سوءاستفاده دیگران.
- **پنل مدیریت تحت وب:** مشاهده وضعیت اتصال به تلگرام، سوییچ سراسری قطع/وصل (Master Switch)، مدیریت کلیدها و تغییر رمز عبور.
- **کپچای پویا (SVG):** کد امنیتی ضد ربات بدون وابستگی به کتابخانه‌های سنگین گرافیکی (Pillow).
- **پشتیبانی کامل از Long-Polling و آپلود فایل:** سازگار با متد `getUpdates` (بدون قطعی تایم‌اوت) و آپلود فایل‌های باینری چندبخشی (عکس، وویس، داکیومنت).

---

## ۱. نصب سریع روی سرور خام (VPS)

اگر یک سرور مجازی خارج با سیستم‌عامل اوبونتو، دبیان، سنت‌او‌اس یا آلما‌لینوکس دارید، با دسترسی `root` وارد ترمینال شوید و دستور زیر را اجرا کنید:

```bash
curl -sSL https://raw.githubusercontent.com/Danaserver/telegram-relay/main/install.sh | bash
```

> **نکته:** اگر اسکریپت را از قبل دانلود کرده‌اید، می‌توانید به صورت محلی نیز آن را اجرا کنید:
> ```bash
> sudo bash install.sh
> ```

### اجرای روی پورت دلخواه (اختیاری):
به صورت پیش‌فرض رله روی پورت ۸۰ اجرا می‌شود. برای تغییر پورت (مثلاً ۸۰۸۰):
```bash
PORT=8080 curl -sSL https://raw.githubusercontent.com/Danaserver/telegram-relay/main/install.sh | bash
```

اسکریپت پس از اتمام نصب، سرویس `telegram-relay` را در `systemd` ایجاد و فعال کرده و آدرس پنل، نام کاربری و رمز عبور تصادفی تولیدشده را نمایش می‌دهد.

---

## ۲. نصب روی هاست cPanel (روی هر سابدامنه یا پوشه)

اگر سرور اشتراکی cPanel با وب‌سرور LiteSpeed یا Apache دارید:
1. در پنل cPanel وارد مسیر سابدامنه مورد نظر یا یک پوشه دلخواه (مثلاً `public_html/Relay`) شوید.
2. این ۳ فایل را در آن پوشه آپلود کنید:
   - `relay.py` (پرمیشن `0755`)
   - `.htaccess` (پرمیشن `0644`)
   - `config.json` (پرمیشن `0600`)
3. رله فوراً فعال شده و آماده اتصال است.

---

## ۳. اتصال ربات‌ها در سرور ایران

تنها کاری که در کدهای ربات خود روی سرور ایران باید انجام دهید، تغییر آدرس پایه به آدرس رله و اضافه کردن کد اختصاصی ربات است:

```
https://YOUR_DOMAIN/<BOT_KEY>/bot<BOT_TOKEN>/<METHOD>
```

### نمونه کد با `requests` (پایتون)
```python
import requests

BOT_TOKEN = "123456789:AAFakeTokenExample"
RELAY_KEY = "telo_sec_8a2f4e"  # کلید اختصاصی دریافت شده از پنل
BASE_URL = f"https://your-domain.com/{RELAY_KEY}/bot{BOT_TOKEN}"

# دریافت آپدیت‌ها (Long Polling)
updates = requests.get(f"{BASE_URL}/getUpdates", params={"timeout": 30}).json()

# ارسال پیام
requests.post(f"{BASE_URL}/sendMessage", json={
    "chat_id": 12345678,
    "text": "پیام از سرور ایران از طریق رله اختصاصی"
})
```

### نمونه کد با `telebot` (`pyTelegramBotAPI`)
```python
import telebot

BOT_TOKEN = "123456789:AAFakeTokenExample"
RELAY_KEY = "telo_sec_8a2f4e"
SERVER = "https://your-domain.com"

telebot.apihelper.API_URL = f"{SERVER}/{RELAY_KEY}/bot{{0}}/{{1}}"
telebot.apihelper.FILE_URL = f"{SERVER}/{RELAY_KEY}/file/bot{{0}}/{{1}}"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def on_start(msg):
    bot.reply_to(msg, "سلام! ارتباط برقرار است.")

bot.infinity_polling()
```

### نمونه کد با `python-telegram-bot` (v20+)
```python
from telegram.ext import ApplicationBuilder

BOT_TOKEN = "123456789:AAFakeTokenExample"
RELAY_KEY = "telo_sec_8a2f4e"
SERVER = "https://your-domain.com"

app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .base_url(f"{SERVER}/{RELAY_KEY}/bot")
    .base_file_url(f"{SERVER}/{RELAY_KEY}/file/bot")
    .build()
)

app.run_polling()
```

### نمونه کد با `aiogram` (v3)
```python
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

RELAY_KEY = "telo_sec_8a2f4e"
session = AiohttpSession(
    api=TelegramAPIServer.from_base(f"https://your-domain.com/{RELAY_KEY}")
)

bot = Bot(token="YOUR_BOT_TOKEN", session=session)
dp = Dispatcher()
```

---

## ۴. مدیریت سرویس در لینوکس

```bash
# بررسی وضعیت سرویس
systemctl status telegram-relay

# ریستارت کردن سرویس
systemctl restart telegram-relay

# متوقف کردن سرویس
systemctl stop telegram-relay

# مشاهده لاگ زنده اتصالات
journalctl -u telegram-relay -f
```

---

<a name="english-documentation"></a>
# English Documentation

A lightweight, zero-dependency Telegram Bot API reverse proxy (relay) designed to bypass network restrictions and filtering. Includes a password-protected web dashboard, dynamic SVG captcha, and per-bot API key access control.

### Architecture
```
Bot Client (Iran / Filtered Server)
           │
           ▼  HTTPS Request (with bot key)
Telegram Relay Server (Unfiltered VPS or cPanel)
           │
           ▼  Forwarding Request
https://api.telegram.org
```

### Highlights
- **1-Command VPS Setup:** Installs Python 3, sets up `systemd`, configures firewall rules, and starts the service automatically.
- **Zero Third-Party Dependencies:** Built entirely with Python's standard library (`urllib`, `http.server`, `hmac`, `hashlib`, `ssl`).
- **Dual-Mode Engine:** Runs as a standalone multi-threaded HTTP server on Linux VPS or as a CGI script under cPanel / LiteSpeed / Apache.
- **Dynamic Host & Path Detection:** Automatically detects protocol (`http`/`https`), domain, subdomain, and URI path prefix.
- **Per-Bot Access Control:** Prevents unauthorized relay usage by requiring unique secret keys per bot.
- **Web Admin Dashboard:** Master switch (kill switch), live Telegram connection status check, bot key manager, and password updates.
- **SVG Captcha:** Fully client-side vector captcha without external imaging dependencies like Pillow.
- **Long-Polling & Multipart Support:** Fully transparent forwarding for `getUpdates` (timeout-safe) and file/media binary streaming.

---

## 1. Quick Installation (Linux VPS)

Run the following command as `root` on any fresh Ubuntu, Debian, CentOS, or AlmaLinux server:

```bash
curl -sSL https://raw.githubusercontent.com/Danaserver/telegram-relay/main/install.sh | bash
```

### Custom Port (Optional):
```bash
PORT=8080 curl -sSL https://raw.githubusercontent.com/Danaserver/telegram-relay/main/install.sh | bash
```

---

## 2. Shared Hosting / cPanel Setup

1. Create a subdomain or subfolder in your hosting panel (e.g. `public_html/Relay`).
2. Upload the following files:
   - `relay.py` (chmod `0755`)
   - `.htaccess` (chmod `0644`)
   - `config.json` (chmod `0600`)
3. Access the URL in your browser to log in to the management dashboard.

---

## 3. Usage & Routing Format

Requests are routed using the bot's secret key:
```
https://YOUR_DOMAIN/<BOT_KEY>/bot<TOKEN>/<METHOD>
```
Alternative authentication methods supported:
- Query parameter: `?relay_key=<BOT_KEY>`
- HTTP Header: `X-Relay-Key: <BOT_KEY>`

---

## 4. Service Commands (Systemd)

```bash
systemctl status telegram-relay    # Check service status
systemctl restart telegram-relay   # Restart service
systemctl stop telegram-relay      # Stop service
journalctl -u telegram-relay -f    # Live logs
```

---

## Security Model
- Admin passwords are encrypted using `PBKDF2-HMAC-SHA256` with random 16-byte cryptographic salts.
- Sessions are protected via HMAC-SHA256 cryptographically signed tokens.
- Direct web access to `config.json` is denied via `.htaccess`.
- Bot requests without a registered and enabled key are rejected with `403 Forbidden`.

## License
Distributed under the [MIT License](LICENSE).
