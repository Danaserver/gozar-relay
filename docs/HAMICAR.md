# اتصال حامی‌کار به رلهٔ گذر

حامی‌کار از قبل دو نوع رله را پشتیبانی می‌کند و **هر دو بدون تغییر کد با گذر کار می‌کنند**:

| بخش حامی‌کار | فرمت آدرسی که حامی‌کار می‌سازد | پشتیبانی گذر |
|---|---|---|
| ربات تلگرام، حالت «رله معمولی» | `<آدرس رله>/bot<TOKEN>/<method>` | مسیر `/<KEY>/telegram/...` |
| هوش مصنوعی، بخش «رله» (همان فرمت Cloudflare Worker) | `<آدرس رله>/<host>/<path>` + هدر `X-Relay-Key` | مسیریابی بر اساس host |

## ۱. در پنل گذر (https://relay.tello.ir)

1. **سرویس‌ها ← افزودن سرویس**: اگر از Groq یا Claude استفاده می‌کنید، «Groq» و «Anthropic Claude» را اضافه کنید. تلگرام، OpenRouter و Gemini از قبل هستند. برای هر host دیگری که حامی‌کار از رله رد می‌کند (مثل DeepSeek یا Mistral) هم یک سرویس بسازید.
2. **کلیدهای دسترسی ← کلید جدید**:
   - نام: `حامی‌کار`
   - سرویس‌های مجاز: تلگرام، OpenRouter، Gemini، Groq، Claude
   - محدودیت: مثلاً ۱۲۰ درخواست در دقیقه
   - متغیرها (اختیاری): `SITE_NAME=Hamicar` و `SITE_URL=https://<دامنهٔ حامی‌کار>`. سرویس OpenRouter این‌ها را به صورت هدرهای `X-Title` و `HTTP-Referer` می‌فرستد.
3. کلید ساخته‌شده (`gz_...`) را کپی کنید.

## ۲. در پنل حامی‌کار

**تنظیمات ← ربات‌ها ← تلگرام**

| فیلد | مقدار |
|---|---|
| حالت اتصال | رله معمولی (`relay`) |
| آدرس رله | `https://relay.tello.ir/<KEY>/telegram/bot` |

**تنظیمات ← هوش مصنوعی ← رله**

| فیلد | مقدار |
|---|---|
| آدرس رله (`ai_relay_url`) | `https://relay.tello.ir` |
| رمز رله (`ai_relay_key`) | `<KEY>` (همان کلید گذر) |
| سرویس‌های عبوری (`ai_relay_providers`) | Groq، OpenRouter، Gemini، Claude |

کلیدهای API خود سرویس‌ها (OpenRouter، Gemini و...) مثل قبل در حامی‌کار می‌مانند. اگر بخواهید فقط روی رله باشند، آن‌ها را در گذر در «کلید(های) API سرویس» وارد کنید. گذر کلید ذخیره‌شده را جایگزین می‌کند و فیلد کلید در حامی‌کار می‌تواند هر مقداری داشته باشد.

## ۳. تست

```bash
curl https://relay.tello.ir/openrouter.ai/api/v1/models -H "X-Relay-Key: <KEY>"
curl https://relay.tello.ir/<KEY>/telegram/bot<BOT_TOKEN>/getMe
```

در پنل گذر، بخش «گزارش درخواست‌ها» را با فیلتر کلید «حامی‌کار» ببینید.

## نکته‌ها

- رلهٔ Cloudflare Worker برای Groq و OpenRouter کار نمی‌کند، چون خود این دو سرویس پشت Cloudflare هستند. گذر روی VPS مستقل (هلند) اجرا می‌شود و این مشکل را ندارد.
- پیام خطای «کلید رله» در گذر این است: `[Gozar] Missing or invalid access key`. در این صورت `ai_relay_key` را دوباره کپی کنید.
- وبهوک تلگرام از طریق رله نیست. اگر سرور حامی‌کار از بیرون در دسترس نیست، از `hamicar:telegram-poll` استفاده کنید (long-polling از طریق گذر کار می‌کند).

---

## متن آماده برای پروژهٔ حامی‌کار (به Claude یا برنامه‌نویس بدهید)

```text
برای دسترسی به تلگرام و سرویس‌های هوش مصنوعی از رلهٔ «گذر» روی https://relay.tello.ir استفاده کن.
کد لازم نیست تغییر کند؛ فقط تنظیمات را این‌طور بگذار:

تلگرام (تنظیمات ← ربات‌ها):
  telegram_mode      = relay
  telegram_relay_url = https://relay.tello.ir/<KEY>/telegram/bot

هوش مصنوعی (تنظیمات ← هوش مصنوعی ← رله):
  ai_relay_url       = https://relay.tello.ir
  ai_relay_key       = <KEY>
  ai_relay_providers = ["groq","openrouter","gemini","claude"]

فرمت‌هایی که گذر می‌پذیرد:
  - هوش مصنوعی (سبک Cloudflare Worker): https://relay.tello.ir/<host>/<path> با هدر X-Relay-Key: <KEY>
    مثال: https://relay.tello.ir/openrouter.ai/api/v1/chat/completions
    hostهای مجاز: openrouter.ai، generativelanguage.googleapis.com، api.groq.com، api.anthropic.com
    (هر سرویسی که در پنل گذر تعریف شده باشد)
  - تلگرام: https://relay.tello.ir/<KEY>/telegram/bot<TOKEN>/<method> و برای فایل‌ها .../telegram/file/bot<TOKEN>/<path>
  - کلید را می‌شود به این شکل‌ها هم فرستاد: داخل مسیر، هدر X-Relay-Key، پارامتر ?relay_key=، یا Authorization: Bearer
  - هدر Authorization با کلید API خود سرویس، بدون تغییر به مقصد منتقل می‌شود.
    (مگر اینکه کلید سرویس در پنل گذر ذخیره شده باشد؛ در آن صورت گذر خودش آن را می‌گذارد.)
  - پاسخ‌های استریم (SSE) و long-polling پشتیبانی می‌شوند.
  - خطاهای خود رله با پیشوند [Gozar] برمی‌گردند (401 کلید نامعتبر، 403 سرویس مجاز نیست، 429 محدودیت نرخ، 502/504 خطای مقصد).

اگر یک host جدید (مثلاً api.deepseek.com) را از رله رد می‌کنی، باید در پنل گذر یک سرویس با همان آدرس اضافه شود.
```
