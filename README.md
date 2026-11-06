<div align="center">

<img src="gozar/panel/static/logo.svg" width="84" alt="Gozar">

# گذر · Gozar Relay

**رلهٔ یکپارچه API برای سرورهای داخل ایران**
Telegram · OpenRouter · Gemini · OpenAI · Claude · Groq · GitHub · هر API دیگر

[![License: MIT](https://img.shields.io/badge/License-MIT-6366f1.svg)](LICENSE)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-22d3ee.svg)](https://www.python.org/)
![Zero dependencies](https://img.shields.io/badge/dependencies-0-10b981.svg)

[فارسی](#فارسی) · [English](#english)

</div>

---

<a name="فارسی"></a>

## گذر چیست؟

سرورهای داخل ایران به `api.telegram.org`، OpenRouter، Gemini و خیلی از APIهای دیگر دسترسی ندارند.
**گذر** را روی یک سرور خارج از ایران (VPS یا هاست cPanel) نصب می‌کنید و برنامه‌های داخل ایران به جای آدرس اصلی، درخواست‌ها را به گذر می‌فرستند. گذر کلید دسترسی را بررسی می‌کند و درخواست را **بدون تغییر و به صورت استریم** به مقصد می‌رساند.

```
 سرور ایران (ربات / وب‌سایت / حامی‌کار)
            │  https://relay.telo.ir/<KEY>/<service>/...
            ▼
 ┌──────────────────────────┐
 │        Gozar Relay       │  کلید دسترسی · محدودیت نرخ · لاگ · کلید API مدیریت‌شده
 └──────────────────────────┘
      │          │          │
  Telegram   OpenRouter   Gemini   …هر API دیگر
```

### امکانات

- **چندسرویسی:** هر تعداد سرویس با شناسهٔ دلخواه (`/telegram`، `/openrouter`، `/gemini`، …) و قالب آماده برای ۷ سرویس معروف + سرویس سفارشی.
- **کلید دسترسی برای هر برنامه:** فعال/غیرفعال، تعیین سرویس‌های مجاز، محدودیت درخواست در دقیقه، تاریخ انقضا و آمار مصرف.
- **کلید API مدیریت‌شده:** کلید OpenRouter/Gemini/… را فقط در رله ذخیره کنید؛ برنامه‌ها با کلید رله کار می‌کنند و کلید اصلی هرگز به سرور ایران نمی‌رسد. چند کلید = چرخش خودکار.
- **سازگار با همهٔ SDKها:** OpenAI SDK، google-genai، anthropic، python-telegram-bot، aiogram، telebot، PHP و cURL — فقط آدرس پایه عوض می‌شود.
- **استریم کامل:** پاسخ‌های SSE مدل‌های هوش مصنوعی، Long-Polling تلگرام و آپلود/دانلود فایل.
- **پنل مدیریت فارسی:** داشبورد ترافیک، وضعیت اتصال به سرویس‌ها، مدیریت سرویس‌ها و کلیدها، لاگ درخواست‌ها و کدهای آمادهٔ اتصال برای هر کلید.
- **امنیت:** ورود با کپچا و قفل ضد brute-force، نشست امضاشده، محافظت CSRF، حذف IP و کوکی کاربر از درخواست‌های خروجی، مخفی شدن توکن ربات در لاگ‌ها.
- **بدون وابستگی:** فقط کتابخانهٔ استاندارد پایتون ۳.۷+ (SQLite داخلی).
- **دو حالت اجرا:** سرور مستقل روی VPS (با systemd و Let's Encrypt) یا CGI روی هاست cPanel / LiteSpeed / Apache.
- **سازگار با نسخهٔ قبلی:** آدرس‌های قدیمی `/<KEY>/bot<TOKEN>/...` بدون تغییر کار می‌کنند و تنظیمات نسخهٔ ۱ خودکار منتقل می‌شوند.

---

## نصب

### ۱. روی VPS (اوبونتو، دبیان، CentOS، Alma، Rocky، Fedora، Alpine، Arch)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Danaserver/gozar-relay/main/install.sh)
```

اسکریپت دامنه و پورت‌ها را می‌پرسد، اگر پورت ۸۰/۴۴۳ اشغال باشد پورت جایگزین پیشنهاد می‌دهد، برای دامنه گواهی **Let's Encrypt** می‌گیرد (یا گواهی self-signed برای Cloudflare)، سرویس systemd می‌سازد و در پایان آدرس پنل، نام کاربری، رمز و اولین کلید دسترسی را نمایش می‌دهد.

نصب بدون پرسش:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Danaserver/gozar-relay/main/install.sh) --domain relay.example.com --port 80 --ssl-port 443 --yes
```

مدیریت:

```bash
gozar status            # وضعیت سرویس
gozar logs              # لاگ زنده
gozar restart
gozar update            # بروزرسانی به آخرین نسخه
gozar info              # خلاصهٔ سرویس‌ها و کلیدها
gozar reset-password    # رمز جدید برای پنل
gozar key add --name "ربات فروش" --services telegram
gozar uninstall
```

### ۲. روی هاست cPanel (مثلاً `relay.telo.ir`)

یک API Token در cPanel بسازید (Security » Manage API Tokens) و روی کامپیوتر خودتان اجرا کنید:

```bash
export CPANEL_TOKEN=xxxxxxxxxxxx
python3 deploy/cpanel_deploy.py --host my-cpanel-host.com --user cpuser --domain relay.telo.ir \
    --python /opt/alt/python311/bin/python3
```

اسکریپت سابدامین را می‌سازد، فایل‌ها را آپلود می‌کند، دیتابیس را **بیرون از پوشهٔ وب** (`~/.gozar/relay.telo.ir`) نگه می‌دارد، AutoSSL را فعال می‌کند و نام کاربری/رمز/کلید اولیه را چاپ می‌کند. برای بروزرسانی همین دستور را دوباره اجرا کنید (دیتابیس حفظ می‌شود).

> آپلود دستی: `relay.py` (مجوز 755)، `.htaccess` و پوشهٔ `gozar/` را در ریشهٔ سابدامین بگذارید، سپس با SSH دستور `python3 relay.py init` را اجرا کنید.

### ۳. اجرای دستی / توسعه

```bash
python3 relay.py init                 # ساخت مدیر، سرویس‌های پیش‌فرض و اولین کلید
python3 relay.py serve --port 8080    # پنل: http://localhost:8080
python3 -m unittest discover -s tests # تست‌ها
```

---

## اتصال برنامه‌ها

دو شکل آدرس (هر دو معادل‌اند):

```
https://relay.telo.ir/<ACCESS_KEY>/<service>/<path>          # کلید داخل آدرس
https://relay.telo.ir/<service>/<path>   +  X-Relay-Key: <ACCESS_KEY>
```

هر چیزی بعد از `<service>` عیناً به آدرس مقصد سرویس اضافه می‌شود. کدهای آماده برای هر کلید در پنل (بخش «راهنمای اتصال») ساخته می‌شوند.

### تلگرام

```python
# requests
API = f"https://relay.telo.ir/{RELAY_KEY}/telegram/bot{BOT_TOKEN}"
requests.post(f"{API}/sendMessage", json={"chat_id": 123, "text": "سلام"})

# python-telegram-bot v20+
app = (ApplicationBuilder().token(BOT_TOKEN)
       .base_url(f"https://relay.telo.ir/{RELAY_KEY}/telegram/bot")
       .base_file_url(f"https://relay.telo.ir/{RELAY_KEY}/telegram/file/bot").build())

# aiogram 3
session = AiohttpSession(api=TelegramAPIServer.from_base(f"https://relay.telo.ir/{RELAY_KEY}/telegram"))
```

### OpenRouter (یا OpenAI / Groq)

```python
from openai import OpenAI

# کلید OpenRouter در پنل ذخیره شده (مدیریت‌شده): کلید رله را به جای api_key بدهید
client = OpenAI(base_url="https://relay.telo.ir/openrouter/api/v1", api_key=RELAY_KEY)

# حالت عبوری: کلید رله در آدرس، کلید OpenRouter خودتان در api_key
client = OpenAI(base_url=f"https://relay.telo.ir/{RELAY_KEY}/openrouter/api/v1", api_key="sk-or-...")
```

### Gemini

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=RELAY_KEY,   # یا کلید Gemini خودتان در حالت عبوری
                      http_options=types.HttpOptions(base_url="https://relay.telo.ir/gemini"))
print(client.models.generate_content(model="gemini-2.5-flash", contents="سلام").text)
```

### هر API دیگر

در پنل «افزودن سرویس» → «سرویس سفارشی» را بزنید، شناسه (مثلاً `myapi`) و آدرس مقصد را وارد کنید:

```bash
curl https://relay.telo.ir/myapi/v1/items -H "X-Relay-Key: gz_xxx"
```

نمونه‌های کامل در پوشهٔ [`examples/`](examples).

### سازگار با رله‌های Cloudflare Worker

برنامه‌هایی که آدرس را به شکل `<relay>/<host>/<path>` می‌سازند و کلید را با هدر `X-Relay-Key` می‌فرستند (مثل حامی‌کار) بدون تغییر کار می‌کنند. فقط hostهایی که به عنوان سرویس تعریف شده‌اند عبور داده می‌شوند:

```bash
curl https://relay.telo.ir/openrouter.ai/api/v1/models -H "X-Relay-Key: gz_xxx"
```

### متغیرها، هدرها و پارامترهای اختصاصی

مثل Environment Variables در Cloudflare Worker، برای هر سرویس **و** هر کلید دسترسی می‌توانید داده تعریف کنید که همراه درخواست‌ها به مقصد برود:

| فیلد | قالب | نمونه |
|---|---|---|
| متغیرها | `NAME=value` | `SITE_NAME=Hamicar` |
| هدرهای اضافه | `Header: value` (با `?` = فقط اگر برنامه نفرستاده؛ مقدار خالی = حذف) | `X-Title?: {{SITE_NAME}}` |
| پارامترهای Query | `name=value` | `source={{KEY_NAME}}` |

- `{{NAME}}` در هدرها، پارامترها، مسیر آدرس مقصد و کلید API مدیریت‌شده قابل استفاده است (مثلاً `https://api.cloudflare.com/client/v4/accounts/{{ACCOUNT_ID}}/ai`).
- متغیرهای کلید روی متغیرهای سرویس اولویت دارند. اگر کلید API سرویس را `{{OPENROUTER_KEY}}` بگذارید، هر کلید دسترسی با کلید API خودش کار می‌کند.
- متغیرهای آماده: `{{KEY_NAME}}`، `{{KEY_ID}}`، `{{SERVICE}}`. مقدار متغیرهایی که نامشان KEY/SECRET/TOKEN/PASS دارد در پنل مخفی است.

---

## ساختار پروژه

```
relay.py                 نقطهٔ ورود (CGI یا CLI)
gozar/
├── app.py               مسیریابی اصلی
├── proxy.py             موتور رله: تشخیص سرویس و کلید، سیاست‌ها، استریم به مقصد
├── store.py             ذخیره‌سازی SQLite (تنظیمات، سرویس‌ها، کلیدها، لاگ)
├── security.py          هش رمز، نشست امضاشده، کپچا، پنهان‌سازی توکن‌ها
├── presets.py           قالب سرویس‌های آماده
├── http.py              Request / Response مستقل از سرور
├── runners.py           اجراکنندهٔ CGI و سرور مستقل چندنخی (HTTP/HTTPS)
├── cli.py               دستورات مدیریتی
└── panel/               پنل مدیریت (API + رابط کاربری تک‌صفحه‌ای بدون build)
deploy/cpanel_deploy.py  استقرار خودکار روی cPanel
install.sh               نصب‌کنندهٔ یک‌خطی VPS
tests/                   تست‌های end-to-end
```

## نکات امنیتی

- هر برنامه/ربات کلید جدا داشته باشد تا در صورت نشت، فقط همان را قطع کنید.
- برای سرویس‌های هوش مصنوعی حالت «مدیریت‌شده» را ترجیح دهید تا کلید اصلی فقط روی رله باشد.
- رله IP، کوکی و هدرهای `X-Forwarded-*` کاربر را به مقصد نمی‌فرستد.
- رمزها با PBKDF2-SHA256 (۲۰۰ هزار دور) ذخیره می‌شوند؛ تغییر رمز همهٔ نشست‌های قبلی را باطل می‌کند.

---

<a name="english"></a>

## English

**Gozar** is a zero-dependency, self-hosted API relay for servers on restricted networks. Deploy it on an unrestricted VPS or cPanel host and point your apps at it instead of `api.telegram.org`, `openrouter.ai`, `generativelanguage.googleapis.com` or any other HTTP API.

**Highlights**

- Unlimited services, each mounted at `/<slug>` with presets for Telegram, OpenRouter, Gemini, OpenAI, Anthropic, Groq and GitHub, plus custom upstreams.
- Per-app access keys with service allow-lists, per-minute rate limits, expiry dates and usage stats.
- *Managed* upstream credentials: store provider keys on the relay (with random rotation across several keys); clients authenticate with their Gozar key, which the relay swaps for the real one.
- Works with stock SDKs — only the base URL changes. Streaming (SSE), long polling and file transfer are passed through untouched.
- Persian RTL admin panel: traffic dashboard, upstream health, service & key management, request log and generated connection snippets.
- Captcha + lockout on login, signed sessions, CSRF protection, client IP/cookie stripping, bot-token redaction in logs.
- Runs as a standalone threaded HTTP/HTTPS server (systemd, Let's Encrypt) or as CGI on Apache/LiteSpeed.
- Backwards compatible with v1 URLs (`/<KEY>/bot<TOKEN>/<method>`) and auto-migrates v1 `config.json`.

**URL scheme**

```
https://relay.example.com/<ACCESS_KEY>/<service>/<upstream path>
https://relay.example.com/<service>/<upstream path>     (key via X-Relay-Key, Bearer token, or the service's own auth header)
```

**Install**

```bash
# VPS
bash <(curl -fsSL https://raw.githubusercontent.com/Danaserver/gozar-relay/main/install.sh)

# cPanel
CPANEL_TOKEN=... python3 deploy/cpanel_deploy.py --host HOST --user USER --domain relay.example.com

# Local
python3 relay.py init && python3 relay.py serve --port 8080
```

## License

[MIT](LICENSE)
