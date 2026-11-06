"""
Built-in service templates.

auth_type controls how the relay injects an upstream credential when the
service has one stored ("managed" mode). With no stored credential the
service runs in "passthrough" mode and the client sends its own.

    none    nothing is injected
    bearer  Authorization: Bearer <key>
    header  <auth_name>: <key>
    query   ?<auth_name>=<key>
"""

PRESETS = [
    {
        "preset": "telegram",
        "slug": "telegram",
        "name": "Telegram Bot API",
        "upstream": "https://api.telegram.org",
        "auth_type": "none",
        "auth_name": "",
        "timeout": 95,
        "icon": "telegram",
        "docs": "https://core.telegram.org/bots/api",
        "hint": "توکن ربات در مسیر آدرس ارسال می‌شود (bot<TOKEN>/method).",
    },
    {
        "preset": "openrouter",
        "slug": "openrouter",
        "name": "OpenRouter",
        "upstream": "https://openrouter.ai",
        "auth_type": "bearer",
        "auth_name": "Authorization",
        "timeout": 300,
        "icon": "openrouter",
        "docs": "https://openrouter.ai/docs",
        "hint": "سازگار با OpenAI SDK. مسیر پایه: /api/v1",
        "variables": "SITE_URL=\nSITE_NAME=",
        "headers": "HTTP-Referer?: {{SITE_URL}}\nX-Title?: {{SITE_NAME}}",
    },
    {
        "preset": "gemini",
        "slug": "gemini",
        "name": "Google Gemini",
        "upstream": "https://generativelanguage.googleapis.com",
        "auth_type": "header",
        "auth_name": "x-goog-api-key",
        "timeout": 300,
        "icon": "gemini",
        "docs": "https://ai.google.dev/api",
        "hint": "مسیر پایه: /v1beta — کلید با هدر x-goog-api-key یا پارامتر key.",
    },
    {
        "preset": "openai",
        "slug": "openai",
        "name": "OpenAI",
        "upstream": "https://api.openai.com",
        "auth_type": "bearer",
        "auth_name": "Authorization",
        "timeout": 300,
        "icon": "openai",
        "docs": "https://platform.openai.com/docs/api-reference",
        "hint": "مسیر پایه: /v1",
    },
    {
        "preset": "anthropic",
        "slug": "anthropic",
        "name": "Anthropic Claude",
        "upstream": "https://api.anthropic.com",
        "auth_type": "header",
        "auth_name": "x-api-key",
        "timeout": 300,
        "icon": "anthropic",
        "docs": "https://docs.anthropic.com/en/api",
        "hint": "مسیر پایه: /v1",
        "headers": "anthropic-version?: 2023-06-01",
    },
    {
        "preset": "groq",
        "slug": "groq",
        "name": "Groq",
        "upstream": "https://api.groq.com",
        "auth_type": "bearer",
        "auth_name": "Authorization",
        "timeout": 120,
        "icon": "groq",
        "docs": "https://console.groq.com/docs",
        "hint": "سازگار با OpenAI SDK. مسیر پایه: /openai/v1",
    },
    {
        "preset": "deepseek",
        "slug": "deepseek",
        "name": "DeepSeek",
        "upstream": "https://api.deepseek.com",
        "auth_type": "bearer",
        "auth_name": "Authorization",
        "timeout": 300,
        "icon": "custom",
        "docs": "https://api-docs.deepseek.com",
        "hint": "سازگار با OpenAI SDK. مسیر پایه: /v1",
    },
    {
        "preset": "mistral",
        "slug": "mistral",
        "name": "Mistral",
        "upstream": "https://api.mistral.ai",
        "auth_type": "bearer",
        "auth_name": "Authorization",
        "timeout": 300,
        "icon": "custom",
        "docs": "https://docs.mistral.ai/api",
        "hint": "سازگار با OpenAI SDK. مسیر پایه: /v1",
    },
    {
        "preset": "cloudflare",
        "slug": "cloudflare-ai",
        "name": "Cloudflare Workers AI",
        "upstream": "https://api.cloudflare.com/client/v4/accounts/{{ACCOUNT_ID}}/ai",
        "auth_type": "bearer",
        "auth_name": "Authorization",
        "timeout": 300,
        "icon": "custom",
        "docs": "https://developers.cloudflare.com/workers-ai/",
        "hint": "متغیر ACCOUNT_ID را وارد کنید. مسیر سازگار با OpenAI: /v1",
        "variables": "ACCOUNT_ID=",
    },
    {
        "preset": "github",
        "slug": "github",
        "name": "GitHub API",
        "upstream": "https://api.github.com",
        "auth_type": "bearer",
        "auth_name": "Authorization",
        "timeout": 60,
        "icon": "github",
        "docs": "https://docs.github.com/rest",
        "hint": "",
    },
    {
        "preset": "custom",
        "slug": "",
        "name": "سرویس سفارشی",
        "upstream": "https://",
        "auth_type": "none",
        "auth_name": "",
        "timeout": 120,
        "icon": "custom",
        "docs": "",
        "hint": "هر API مبتنی بر HTTP/HTTPS.",
    },
]

PRESETS_BY_ID = {p["preset"]: p for p in PRESETS}

# Services created on first run.
DEFAULT_SERVICES = ("telegram", "openrouter", "gemini", "anthropic", "groq")

AUTH_TYPES = ("none", "bearer", "header", "query")


def get_preset(preset_id):
    return PRESETS_BY_ID.get(preset_id) or PRESETS_BY_ID["custom"]
