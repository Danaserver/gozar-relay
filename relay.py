#!/opt/alt/python311/bin/python3
# -*- coding: utf-8 -*-
"""
Telegram Bot API Relay & Admin Control Panel
Universal Edition: Supports any Domain / Subdomain / Subpath + Standalone VPS Server Mode.
Runs seamlessly on:
 1. cPanel / Apache / LiteSpeed (via CGI)
 2. Linux VPS Raw Server (Ubuntu/Debian/CentOS) as a standalone threaded service
Zero external dependencies (uses Python standard library only).
"""

import sys
import os
import re
import ssl
import json
import time
import hmac
import random
import secrets
import hashlib
import argparse
import urllib.request
import urllib.error
import urllib.parse
from http import cookies
from http.client import responses as http_responses
import http.server
import socketserver

# Set binary streams for stdin and stdout in CGI mode
stdin_raw = sys.stdin.buffer
stdout_raw = sys.stdout.buffer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TELEGRAM_API_BASE = "https://api.telegram.org"
TIMEOUT_SECONDS = 95

HOP_BY_HOP_HEADERS = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'host'
}

# ----------------- CONFIG MANAGEMENT -----------------

def get_default_config():
    secret_key = secrets.token_hex(32)
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', b'Admin@Telo2026', salt.encode('utf-8'), 100000).hex()
    return {
        "enabled": True,
        "admin": {
            "username": "admin",
            "password_hash": f"{salt}:{hashed}"
        },
        "secret_jwt_key": secret_key,
        "bot_keys": [
            {
                "id": "key_default",
                "name": "ربات پیش‌فرض ۱",
                "key": f"telo_sec_{secrets.token_hex(4)}",
                "enabled": True,
                "created_at": time.strftime("%Y-%m-%d %H:%M")
            }
        ]
    }

def load_config():
    if not os.path.exists(CONFIG_FILE):
        cfg = get_default_config()
        save_config(cfg)
        return cfg
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return get_default_config()

def save_config(cfg):
    temp_file = f"{CONFIG_FILE}.tmp"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, CONFIG_FILE)

# ----------------- SECURITY & AUTH -----------------

def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{salt}:{hashed}"

def verify_password(password, stored_hash):
    if not stored_hash or ':' not in stored_hash:
        return False
    salt, hashed = stored_hash.split(':', 1)
    test_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return hmac.compare_digest(hashed, test_hash)

def make_session_token(username, secret_key):
    ts = int(time.time())
    msg = f"{username}:{ts}".encode('utf-8')
    sig = hmac.new(secret_key.encode('utf-8'), msg, hashlib.sha256).hexdigest()
    return f"{username}:{ts}:{sig}"

def verify_session_token(token, secret_key, max_age=86400):
    if not token or token.count(':') != 2:
        return None
    username, ts_str, sig = token.split(':', 2)
    try:
        ts = int(ts_str)
    except ValueError:
        return None
    if time.time() - ts > max_age:
        return None
    msg = f"{username}:{ts}".encode('utf-8')
    expected_sig = hmac.new(secret_key.encode('utf-8'), msg, hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected_sig):
        return username
    return None

def generate_captcha(secret_key):
    code = ''.join(random.choices('23456789ABCDEFGHJKLMNPQRSTUVWXYZ', k=4))
    ts = int(time.time())
    sig = hmac.new(secret_key.encode('utf-8'), f"{code.upper()}:{ts}".encode('utf-8'), hashlib.sha256).hexdigest()
    token = f"{ts}:{sig}"
    
    colors = ['#38bdf8', '#818cf8', '#34d399', '#f472b6', '#fbbf24']
    char_svgs = []
    for i, ch in enumerate(code):
        x = 18 + i * 28 + random.randint(-2, 2)
        y = 31 + random.randint(-2, 2)
        rot = random.randint(-14, 14)
        color = random.choice(colors)
        char_svgs.append(f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-weight="900" font-size="24" fill="{color}" transform="rotate({rot} {x} {y})">{ch}</text>')
    
    lines = []
    for _ in range(3):
        x1, y1 = random.randint(5, 40), random.randint(5, 38)
        x2, y2 = random.randint(80, 130), random.randint(5, 38)
        color = random.choice(['#475569', '#64748b'])
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.5"/>')
        
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="135" height="44" viewBox="0 0 135 44">
<rect width="135" height="44" fill="#0f172a" rx="8" stroke="#334155"/>
{''.join(lines)}
{''.join(char_svgs)}
</svg>'''
    return code, token, svg

def verify_captcha(entered_code, token, secret_key, max_age=300):
    if not token or ':' not in token or not entered_code:
        return False
    ts_str, sig = token.split(':', 1)
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    if time.time() - ts > max_age:
        return False
    expected_sig = hmac.new(secret_key.encode('utf-8'), f"{entered_code.strip().upper()}:{ts}".encode('utf-8'), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)

# ----------------- CONTEXT & URL UTILITIES -----------------

def get_request_context(env, custom_base_path=None):
    """
    Dynamically auto-detects protocol, domain/subdomain, and base path.
    Supports any subdomain, subfolder, reverse proxy, or standalone port.
    """
    proto = env.get('HTTP_X_FORWARDED_PROTO')
    if not proto:
        proto = 'https' if env.get('HTTPS') in ('on', '1') or env.get('SERVER_PORT') == '443' else 'http'
    
    host = env.get('HTTP_X_FORWARDED_HOST') or env.get('HTTP_HOST') or env.get('SERVER_NAME') or 'localhost'
    
    if custom_base_path is not None:
        base_path = custom_base_path.rstrip('/')
    else:
        script_name = env.get('SCRIPT_NAME', '').replace('\\', '/')
        dirname = os.path.dirname(script_name).replace('\\', '/')
        if dirname in ('/', '', '.'):
            base_path = ''
        else:
            base_path = dirname.rstrip('/')
        
    base_url = f"{proto}://{host}{base_path}"
    cookie_path = base_path if base_path else "/"
    
    return {
        "proto": proto,
        "host": host,
        "base_path": base_path,
        "base_url": base_url,
        "cookie_path": cookie_path
    }

def clean_req_path(req_uri, base_path):
    parsed = urllib.parse.urlsplit(req_uri)
    raw = parsed.path
    if base_path and raw.startswith(base_path):
        raw = raw[len(base_path):]
    raw = re.sub(r'^/?relay\.py/?', '/', raw)
    return raw.strip('/')

def parse_cookies(cookie_header):
    c = cookies.SimpleCookie()
    if cookie_header:
        try:
            c.load(cookie_header)
        except Exception:
            pass
    return c

def parse_query(req_uri):
    return urllib.parse.urlsplit(req_uri).query

def check_tg_connection():
    try:
        req = urllib.request.Request(TELEGRAM_API_BASE, headers={"User-Agent": "TelegramRelayCheck/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return True, f"Online (HTTP {resp.status})"
    except urllib.error.HTTPError as e:
        return True, f"Online (HTTP {e.code})"
    except Exception as e:
        return False, str(e)

# ----------------- ADMIN HTML VIEWS -----------------

def render_login_page(ctx, err_message=""):
    cfg = load_config()
    secret = cfg.get("secret_jwt_key", "default_secret")
    _, captcha_token, captcha_svg = generate_captcha(secret)
    
    base_path = ctx["base_path"]
    login_action = f"{base_path}/login"
    
    err_html = ""
    if err_message:
        err_html = f'''
        <div style="background: #ef444422; border: 1px solid #ef4444; color: #fca5a5; padding: 12px 16px; border-radius: 10px; margin-bottom: 20px; font-size: 14px; text-align: center;">
            ⚠️ {err_message}
        </div>
        '''

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ورود به پنل مدیریت رله تلگرام</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Tahoma, Arial, sans-serif; }}
        body {{
            background: #090d16;
            color: #f1f5f9;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .login-card {{
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 20px;
            max-width: 420px;
            width: 100%;
            padding: 36px 32px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
        }}
        .header {{
            text-align: center;
            margin-bottom: 28px;
        }}
        .logo-icon {{
            width: 60px;
            height: 60px;
            background: linear-gradient(135deg, #2563eb, #38bdf8);
            border-radius: 18px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            margin-bottom: 16px;
            box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.3);
        }}
        h1 {{ font-size: 20px; font-weight: 700; color: #fff; margin-bottom: 6px; }}
        p.subtitle {{ font-size: 13px; color: #9ca3af; }}
        .form-group {{
            margin-bottom: 18px;
        }}
        label {{
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: #d1d5db;
            margin-bottom: 8px;
        }}
        input[type="text"], input[type="password"] {{
            width: 100%;
            background: #1f2937;
            border: 1px solid #374151;
            border-radius: 10px;
            padding: 12px 14px;
            font-size: 14px;
            color: #fff;
            outline: none;
            transition: border-color 0.2s;
            direction: ltr;
        }}
        input[type="text"]:focus, input[type="password"]:focus {{
            border-color: #38bdf8;
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
        }}
        .captcha-row {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .captcha-box {{
            flex-shrink: 0;
            background: #0f172a;
            border-radius: 10px;
            overflow: hidden;
            display: flex;
            align-items: center;
            border: 1px solid #374151;
            height: 46px;
        }}
        .btn-submit {{
            width: 100%;
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #fff;
            border: none;
            padding: 13px;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            margin-top: 10px;
        }}
        .btn-submit:hover {{
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.3);
        }}
        .footer-note {{
            margin-top: 24px;
            text-align: center;
            font-size: 12px;
            color: #6b7280;
        }}
    </style>
</head>
<body>
    <div class="login-card">
        <div class="header">
            <div class="logo-icon">🔒</div>
            <h1>پنل مدیریت رله تلگرام</h1>
            <p class="subtitle">جهت دسترسی به تنظیمات و مشخصات، وارد شوید</p>
        </div>

        {err_html}

        <form method="POST" action="{login_action}">
            <input type="hidden" name="captcha_token" value="{captcha_token}">
            
            <div class="form-group">
                <label>نام کاربری</label>
                <input type="text" name="username" placeholder="admin" required autocomplete="username">
            </div>

            <div class="form-group">
                <label>رمز عبور</label>
                <input type="password" name="password" placeholder="••••••••" required autocomplete="current-password">
            </div>

            <div class="form-group">
                <label>کد امنیتی (کپچا)</label>
                <div class="captcha-row">
                    <input type="text" name="captcha_code" placeholder="کد ۴ رقمی" required maxlength="6" style="text-transform: uppercase;">
                    <div class="captcha-box" title="کد امنیتی">
                        {captcha_svg}
                    </div>
                </div>
            </div>

            <button type="submit" class="btn-submit">ورود به پنل</button>
        </form>

        <div class="footer-note">
            سرور: {ctx['host']}
        </div>
    </div>
</body>
</html>"""
    secure_flag = "; Secure" if ctx.get("proto") == "https" else ""
    cookie_header = f"relay_captcha={captcha_token}; Path={ctx['cookie_path']}; HttpOnly; SameSite=Lax{secure_flag}"
    return 200, [("Content-Type", "text/html; charset=utf-8"), ("Set-Cookie", cookie_header)], html.encode('utf-8')

def render_dashboard(ctx, cfg, notice=""):
    tg_ok, tg_status = check_tg_connection()
    is_enabled = cfg.get("enabled", True)
    bot_keys = cfg.get("bot_keys", [])
    base_url = ctx["base_url"]
    base_path = ctx["base_path"]

    notice_html = ""
    if notice:
        notice_html = f'''
        <div style="background: #04785722; border: 1px solid #10b981; color: #6ee7b7; padding: 12px 18px; border-radius: 12px; margin-bottom: 24px; font-size: 14px;">
            ✅ {notice}
        </div>
        '''

    rows_html = ""
    if not bot_keys:
        rows_html = '<tr><td colspan="5" style="text-align: center; color: #9ca3af; padding: 24px;">هیچ کد اختصاصی تعریف نشده است. از فرم زیر اضافه کنید.</td></tr>'
    else:
        for k in bot_keys:
            kid = k.get("id", "")
            name = k.get("name", "بدون نام")
            key_val = k.get("key", "")
            active = k.get("enabled", True)
            status_badge = '<span class="badge badge-success">فعال</span>' if active else '<span class="badge badge-error">غیرفعال</span>'
            toggle_label = 'غیرفعال‌سازی' if active else 'فعال‌سازی'
            toggle_class = 'btn-warning' if active else 'btn-success'
            
            example_url = f"{base_url}/{key_val}/bot"

            rows_html += f"""
            <tr>
                <td style="font-weight: 600; color: #fff;">{name}</td>
                <td>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <code class="code-pill">{key_val}</code>
                        <button type="button" class="btn-copy" onclick="copyText('{key_val}')">کپی</button>
                    </div>
                </td>
                <td style="direction: ltr; text-align: right;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <code class="code-pill" style="font-size: 11px;">{base_url}/{key_val}/bot...</code>
                        <button type="button" class="btn-copy" onclick="copyText('{example_url}')">کپی آدرس</button>
                    </div>
                </td>
                <td>{status_badge}</td>
                <td>
                    <div style="display: flex; gap: 6px;">
                        <form method="POST" action="{base_path}/api/toggle_key" style="display:inline;">
                            <input type="hidden" name="key_id" value="{kid}">
                            <button type="submit" class="btn-sm {toggle_class}">{toggle_label}</button>
                        </form>
                        <form method="POST" action="{base_path}/api/delete_key" onsubmit="return confirm('آیا از حذف این کد ربات مطمئن هستید؟');" style="display:inline;">
                            <input type="hidden" name="key_id" value="{kid}">
                            <button type="submit" class="btn-sm btn-danger">حذف</button>
                        </form>
                    </div>
                </td>
            </tr>
            """

    master_status_badge = '<span class="badge badge-success" style="font-size: 14px; padding: 6px 14px;">روشن و فعال است ✅</span>' if is_enabled else '<span class="badge badge-error" style="font-size: 14px; padding: 6px 14px;">خاموش و غیرفعال است ⛔</span>'
    master_toggle_text = '🔴 قطع و غیرفعال کردن رله' if is_enabled else '🟢 وصل و فعال کردن رله'
    master_toggle_btn = 'btn-danger' if is_enabled else 'btn-success'

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>داشبورد مدیریت رله تلگرام - {ctx['host']}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Tahoma, Arial, sans-serif; }}
        body {{
            background: #090d16;
            color: #f1f5f9;
            min-height: 100vh;
            padding: 24px 16px;
        }}
        .container {{
            max-width: 1050px;
            margin: 0 auto;
        }}
        .nav {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 16px;
            padding: 16px 24px;
            margin-bottom: 24px;
        }}
        .nav-brand {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .nav-logo {{
            width: 42px;
            height: 42px;
            background: linear-gradient(135deg, #2563eb, #38bdf8);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
        }}
        .card {{
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
        }}
        h2 {{ font-size: 17px; font-weight: 700; color: #fff; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
        .badge {{
            display: inline-block;
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-weight: 600;
        }}
        .badge-success {{ background: #065f46; color: #34d399; }}
        .badge-error {{ background: #991b1b; color: #f87171; }}
        .badge-warning {{ background: #78350f; color: #fcd34d; }}
        
        .master-box {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: {'#064e3b33' if is_enabled else '#7f1d1d33'};
            border: 1px solid {'#059669' if is_enabled else '#dc2626'};
            border-radius: 16px;
            padding: 20px 24px;
            margin-bottom: 24px;
        }}
        @media (max-width: 600px) {{
            .master-box {{ flex-direction: column; gap: 16px; text-align: center; }}
            .nav {{ flex-direction: column; gap: 14px; text-align: center; }}
        }}
        .btn {{
            padding: 10px 18px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn-primary {{ background: #2563eb; color: #fff; }}
        .btn-primary:hover {{ background: #1d4ed8; }}
        .btn-success {{ background: #059669; color: #fff; }}
        .btn-success:hover {{ background: #047857; }}
        .btn-danger {{ background: #dc2626; color: #fff; }}
        .btn-danger:hover {{ background: #b91c1c; }}
        .btn-warning {{ background: #d97706; color: #fff; }}
        .btn-warning:hover {{ background: #b45309; }}
        .btn-sm {{ padding: 6px 12px; font-size: 12px; border-radius: 8px; border: none; cursor: pointer; }}
        .btn-copy {{
            background: #1f2937;
            border: 1px solid #374151;
            color: #38bdf8;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            cursor: pointer;
        }}
        .btn-copy:hover {{ background: #374151; }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th, td {{
            padding: 12px 14px;
            text-align: right;
            border-bottom: 1px solid #1f2937;
        }}
        th {{ color: #9ca3af; font-weight: 600; text-transform: uppercase; font-size: 12px; }}
        .code-pill {{
            background: #0f172a;
            border: 1px solid #334155;
            padding: 3px 8px;
            border-radius: 6px;
            color: #38bdf8;
            font-family: monospace;
            font-size: 12px;
        }}
        input[type="text"], input[type="password"] {{
            width: 100%;
            background: #0f172a;
            border: 1px solid #374151;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 13px;
            color: #fff;
            outline: none;
            direction: ltr;
        }}
        input[type="text"].rtl-input {{ direction: rtl; }}
        input:focus {{ border-color: #38bdf8; }}
        pre {{
            background: #0f172a;
            border: 1px solid #1f2937;
            padding: 14px;
            border-radius: 10px;
            font-family: monospace;
            font-size: 12px;
            color: #e2e8f0;
            overflow-x: auto;
            white-space: pre-wrap;
            direction: ltr;
            text-align: left;
        }}
        .toast {{
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            background: #10b981;
            color: #fff;
            padding: 10px 20px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            display: none;
            z-index: 1000;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
        }}
    </style>
</head>
<body>
    <div id="toast" class="toast">کپی شد!</div>

    <div class="container">
        <!-- Navigation Header -->
        <div class="nav">
            <div class="nav-brand">
                <div class="nav-logo">⚡</div>
                <div>
                    <h1 style="font-size: 18px; font-weight: 700; color: #fff;">پنل مدیریت رله تلگرام</h1>
                    <span style="font-size: 12px; color: #9ca3af;">دامنه / آدرس فعال: <strong style="color: #38bdf8;">{base_url}</strong></span>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 13px; color: #9ca3af;">مدیر: <strong style="color: #fff;">{cfg.get("admin", {}).get("username", "admin")}</strong></span>
                <form method="POST" action="{base_path}/logout" style="display:inline;">
                    <button type="submit" class="btn btn-sm btn-danger">خروج از حساب</button>
                </form>
            </div>
        </div>

        {notice_html}

        <!-- 1. Master On/Off Switch -->
        <div class="master-box">
            <div>
                <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px;">وضعیت سراسری کل رله (Master Switch):</div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    {master_status_badge}
                    <span style="font-size: 13px; color: #cbd5e1;">(اتصال به api.telegram.org: <strong style="color: {'#34d399' if tg_ok else '#f87171'};">{tg_status}</strong>)</span>
                </div>
            </div>
            <div>
                <form method="POST" action="{base_path}/api/toggle_relay">
                    <button type="submit" class="btn {master_toggle_btn}" style="font-size: 15px; padding: 12px 24px;">
                        {master_toggle_text}
                    </button>
                </form>
            </div>
        </div>

        <!-- 2. Bot Access Keys Section -->
        <div class="card">
            <h2>🔑 مدیریت کدهای اختصاصی ربات‌ها (Bot Access Keys)</h2>
            <p style="font-size: 13px; color: #9ca3af; margin-bottom: 16px;">
                برای امنیت رله و جلوگیری از استفاده افراد ناشناس، هر ربات باید یک کد اختصاصی داشته باشد.
            </p>

            <div style="overflow-x: auto; margin-bottom: 24px;">
                <table>
                    <thead>
                        <tr>
                            <th>نام ربات</th>
                            <th>کد امنیتی (Key)</th>
                            <th>آدرس اختصاصی در سرور ایران</th>
                            <th>وضعیت</th>
                            <th>عملیات</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>

            <!-- Add New Key Form -->
            <div style="background: #0f172a; border: 1px solid #1f2937; border-radius: 12px; padding: 18px;">
                <h3 style="font-size: 14px; font-weight: 600; color: #38bdf8; margin-bottom: 12px;">➕ افزودن کد اختصاصی برای ربات جدید</h3>
                <form method="POST" action="{base_path}/api/add_key" style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end;">
                    <div>
                        <label style="font-size: 12px; color: #9ca3af; display: block; margin-bottom: 6px;">نام ربات (برای شناسایی شما)</label>
                        <input type="text" name="bot_name" class="rtl-input" placeholder="مثلاً: ربات پشتیبانی فروش" required>
                    </div>
                    <div>
                        <label style="font-size: 12px; color: #9ca3af; display: block; margin-bottom: 6px;">کد اختصاصی دلخواه (خالی بگذارید تا خودکار تولید شود)</label>
                        <input type="text" name="custom_key" placeholder="مثال: my_secret_998">
                    </div>
                    <button type="submit" class="btn btn-primary" style="height: 38px;">ایجاد کد اختصاصی</button>
                </form>
            </div>
        </div>

        <!-- 3. Usage & Integration Guide -->
        <div class="card">
            <h2>💻 راهنمای اتصال ربات‌ها در سرور ایران</h2>
            <p style="font-size: 13px; color: #9ca3af; margin-bottom: 12px;">
                در کدهای پایتون خود روی سرور ایران، کافیست آدرس رله با کد اختصاصی را جایگزین <code>https://api.telegram.org</code> کنید:
            </p>
            <pre># ۱. با کتابخانه requests:
BOT_TOKEN = "123456789:ABC..."
RELAY_KEY = "کد_اختصاصی_ربات"  # مثلا telo_sec_8a2f4e
API_URL = f"{base_url}/{{RELAY_KEY}}/bot{{BOT_TOKEN}}"

response = requests.post(f"{{API_URL}}/sendMessage", json={{"chat_id": 12345, "text": "سلام از سرور ایران!"}})

# ۲. با کتابخانه telebot (pyTelegramBotAPI):
import telebot
telebot.apihelper.API_URL = f"{base_url}/{{RELAY_KEY}}/bot{{0}}/{{1}}"
telebot.apihelper.FILE_URL = f"{base_url}/{{RELAY_KEY}}/file/bot{{0}}/{{1}}"
bot = telebot.TeleBot(BOT_TOKEN)

# ۳. با کتابخانه python-telegram-bot (v20+):
app = ApplicationBuilder().token(BOT_TOKEN).base_url(f"{base_url}/{{RELAY_KEY}}/bot").build()</pre>
        </div>

        <!-- 4. Security Settings (Change Password) -->
        <div class="card">
            <h2>🛡️ تنظیمات ورود به پنل (تغییر نام کاربری و رمز عبور)</h2>
            <form method="POST" action="{base_path}/api/change_password" style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end;">
                <div>
                    <label style="font-size: 12px; color: #9ca3af; display: block; margin-bottom: 6px;">نام کاربری جدید</label>
                    <input type="text" name="new_username" value="{cfg.get('admin', {}).get('username', 'admin')}" required>
                </div>
                <div>
                    <label style="font-size: 12px; color: #9ca3af; display: block; margin-bottom: 6px;">رمز عبور جدید</label>
                    <input type="password" name="new_password" placeholder="حداقل ۶ کاراکتر" required>
                </div>
                <button type="submit" class="btn btn-warning" style="height: 38px;">ذخیره تغییرات</button>
            </form>
        </div>
    </div>

    <script>
        function showToast() {{
            const toast = document.getElementById('toast');
            if (toast) {{
                toast.style.display = 'block';
                setTimeout(() => {{ toast.style.display = 'none'; }}, 2000);
            }}
        }}

        function fallbackCopy(str) {{
            const el = document.createElement('textarea');
            el.value = str;
            el.setAttribute('readonly', '');
            el.style.position = 'fixed';
            el.style.left = '-9999px';
            el.style.top = '0';
            document.body.appendChild(el);
            el.select();
            try {{
                const successful = document.execCommand('copy');
                if (successful) showToast();
            }} catch (err) {{
                prompt('کپی متن:', str);
            }}
            document.body.removeChild(el);
        }}

        function copyText(text) {{
            if (navigator.clipboard && window.isSecureContext) {{
                navigator.clipboard.writeText(text).then(showToast).catch(() => fallbackCopy(text));
            }} else {{
                fallbackCopy(text);
            }}
        }}
    </script>
</body>
</html>"""
    return 200, [("Content-Type", "text/html; charset=utf-8")], html.encode('utf-8')

# ----------------- UNIFIED REQUEST PROCESSOR -----------------

def parse_form_body(body_bytes):
    if not body_bytes:
        return {}
    parsed = urllib.parse.parse_qs(body_bytes.decode('utf-8', errors='replace'))
    return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

def is_admin_auth(cfg, cookie_header):
    c = parse_cookies(cookie_header)
    token = c.get("relay_session")
    if not token:
        return False
    secret = cfg.get("secret_jwt_key", "")
    username = verify_session_token(token.value, secret)
    if username and username == cfg.get("admin", {}).get("username"):
        return True
    return False

def process_http_request(method, req_uri, req_headers, body_bytes, env_dict, custom_base_path=None):
    """
    Central request router for both CGI and Standalone HTTP server modes.
    Returns: (status_code, response_headers_list, response_body_bytes)
    """
    cfg = load_config()
    ctx = get_request_context(env_dict, custom_base_path)
    base_path = ctx["base_path"]
    cookie_path = ctx["cookie_path"]
    secure_flag = "; Secure" if ctx.get("proto") == "https" else ""
    
    clean_path = clean_req_path(req_uri, base_path)
    query_string = parse_query(req_uri)
    cookie_hdr = req_headers.get("Cookie") or req_headers.get("cookie") or env_dict.get("HTTP_COOKIE", "")

    # Admin routes
    admin_routes = ('', 'login', 'logout', 'dashboard', 'admin', 'captcha.svg')
    is_admin = clean_path in admin_routes or clean_path.startswith('api/')

    if is_admin:
        # 1. Login submission
        if clean_path in ('login', 'login/') and method == 'POST':
            form = parse_form_body(body_bytes)
            uname = form.get("username", "").strip()
            pword = form.get("password", "").strip()
            c_code = form.get("captcha_code", "").strip()
            c_token = form.get("captcha_token", "")
            
            secret = cfg.get("secret_jwt_key", "")
            if not verify_captcha(c_code, c_token, secret):
                return render_login_page(ctx, "کد امنیتی (کپچا) نامعتبر یا منقضی شده است.")
            
            admin_cfg = cfg.get("admin", {})
            if uname == admin_cfg.get("username") and verify_password(pword, admin_cfg.get("password_hash")):
                sess_token = make_session_token(uname, secret)
                cookie_out = f"relay_session={sess_token}; Path={cookie_path}; HttpOnly; SameSite=Lax{secure_flag}"
                redirect_url = f"{base_path}/" if base_path else "/"
                return 303, [("Location", redirect_url), ("Set-Cookie", cookie_out)], b""
            else:
                return render_login_page(ctx, "نام کاربری یا رمز عبور اشتباه است.")

        # 2. Logout
        if clean_path in ('logout', 'logout/') and method == 'POST':
            cookie_out = f"relay_session=; Path={cookie_path}; Max-Age=0; HttpOnly; SameSite=Lax{secure_flag}"
            redirect_url = f"{base_path}/" if base_path else "/"
            return 303, [("Location", redirect_url), ("Set-Cookie", cookie_out)], b""

        # 3. Dynamic Captcha SVG
        if clean_path in ('captcha.svg',):
            secret = cfg.get("secret_jwt_key", "")
            _, c_token, c_svg = generate_captcha(secret)
            cookie_out = f"relay_captcha={c_token}; Path={cookie_path}; HttpOnly; SameSite=Lax{secure_flag}"
            return 200, [("Content-Type", "image/svg+xml"), ("Set-Cookie", cookie_out)], c_svg.encode('utf-8')

        # Authentication check
        if not is_admin_auth(cfg, cookie_hdr):
            if clean_path in ('', 'dashboard', 'admin'):
                return render_login_page(ctx)
            return 401, [("Content-Type", "application/json")], json.dumps({"error": "Unauthorized"}).encode()

        # Authenticated Admin Dashboard & API Actions
        if clean_path in ('', 'dashboard', 'admin'):
            notice = env_dict.get("HTTP_X_NOTICE", "")
            return render_dashboard(ctx, cfg, notice)

        if clean_path == 'api/toggle_relay' and method == 'POST':
            cfg['enabled'] = not cfg.get('enabled', True)
            save_config(cfg)
            status_text = "رله با موفقیت فعال شد." if cfg['enabled'] else "رله با موفقیت غیرفعال شد."
            return render_dashboard(ctx, cfg, notice=status_text)

        if clean_path == 'api/add_key' and method == 'POST':
            form = parse_form_body(body_bytes)
            bot_name = form.get("bot_name", "").strip() or "ربات بدون نام"
            custom_key = form.get("custom_key", "").strip()
            if not custom_key:
                custom_key = f"telo_sec_{secrets.token_hex(4)}"
            custom_key = re.sub(r'[^a-zA-Z0-9_\-]', '', custom_key)
            
            new_key = {
                "id": f"key_{secrets.token_hex(4)}",
                "name": bot_name,
                "key": custom_key,
                "enabled": True,
                "created_at": time.strftime("%Y-%m-%d %H:%M")
            }
            cfg.setdefault("bot_keys", []).append(new_key)
            save_config(cfg)
            return render_dashboard(ctx, cfg, notice=f"کد اختصاصی جدید برای '{bot_name}' با موفقیت ایجاد شد.")

        if clean_path == 'api/toggle_key' and method == 'POST':
            form = parse_form_body(body_bytes)
            kid = form.get("key_id", "")
            for k in cfg.get("bot_keys", []):
                if k.get("id") == kid:
                    k['enabled'] = not k.get('enabled', True)
                    break
            save_config(cfg)
            return render_dashboard(ctx, cfg, notice="وضعیت کلید ربات به‌روزرسانی شد.")

        if clean_path == 'api/delete_key' and method == 'POST':
            form = parse_form_body(body_bytes)
            kid = form.get("key_id", "")
            cfg['bot_keys'] = [k for k in cfg.get("bot_keys", []) if k.get("id") != kid]
            save_config(cfg)
            return render_dashboard(ctx, cfg, notice="کد ربات با موفقیت حذف شد.")

        if clean_path == 'api/change_password' and method == 'POST':
            form = parse_form_body(body_bytes)
            new_uname = form.get("new_username", "").strip()
            new_pass = form.get("new_password", "").strip()
            if new_uname and len(new_pass) >= 6:
                cfg['admin']['username'] = new_uname
                cfg['admin']['password_hash'] = hash_password(new_pass)
                cfg['secret_jwt_key'] = secrets.token_hex(32)
                save_config(cfg)
                new_token = make_session_token(new_uname, cfg['secret_jwt_key'])
                cookie_out = f"relay_session={new_token}; Path={cookie_path}; HttpOnly; SameSite=Lax{secure_flag}"
                status, headers, body = render_dashboard(ctx, cfg, notice="مشخصات ورود مدیر با موفقیت تغییر کرد.")
                headers.append(("Set-Cookie", cookie_out))
                return status, headers, body
            else:
                return render_dashboard(ctx, cfg, notice="رمز عبور باید حداقل ۶ کاراکتر باشد.")

    # ----------------- TELEGRAM FORWARDING -----------------
    if not cfg.get("enabled", True):
        payload = json.dumps({
            "ok": False,
            "error_code": 503,
            "description": "Relay service is currently disabled by administrator."
        }).encode('utf-8')
        return 503, [("Content-Type", "application/json; charset=utf-8")], payload

    bot_keys = {k.get("key"): k for k in cfg.get("bot_keys", []) if k.get("key")}
    matched_key = None
    target_tg_path = clean_path

    # Extract key from path: /<KEY>/bot<TOKEN>/...
    path_parts = clean_path.split('/', 1)
    if path_parts[0] in bot_keys:
        matched_key = bot_keys[path_parts[0]]
        target_tg_path = path_parts[1] if len(path_parts) > 1 else ""

    # Extract key from query param: ?relay_key=<KEY>
    if not matched_key and query_string:
        params = urllib.parse.parse_qs(query_string)
        if 'relay_key' in params:
            k_val = params['relay_key'][0]
            if k_val in bot_keys:
                matched_key = bot_keys[k_val]
                filtered = [pair for pair in query_string.split('&') if not pair.startswith('relay_key=')]
                query_string = '&'.join(filtered)

    # Extract key from header: X-Relay-Key: <KEY>
    if not matched_key:
        hdr_key = req_headers.get("X-Relay-Key") or req_headers.get("x-relay-key") or env_dict.get("HTTP_X_RELAY_KEY", "")
        if hdr_key in bot_keys:
            matched_key = bot_keys[hdr_key]

    if not matched_key:
        payload = json.dumps({
            "ok": False,
            "error_code": 403,
            "description": "Access denied: Missing or invalid Relay key. Please configure your bot's dedicated key."
        }).encode('utf-8')
        return 403, [("Content-Type", "application/json; charset=utf-8")], payload

    if not matched_key.get("enabled", True):
        payload = json.dumps({
            "ok": False,
            "error_code": 403,
            "description": f"Access denied: Key '{matched_key.get('name')}' is currently disabled."
        }).encode('utf-8')
        return 403, [("Content-Type", "application/json; charset=utf-8")], payload

    target_url = f"{TELEGRAM_API_BASE}/{target_tg_path}"
    if query_string:
        target_url = f"{target_url}?{query_string}"

    forward_headers = {}
    content_type = req_headers.get("Content-Type") or req_headers.get("content-type") or env_dict.get("CONTENT_TYPE")
    if content_type:
        forward_headers["Content-Type"] = content_type

    for k, v in req_headers.items():
        if k.lower() not in HOP_BY_HOP_HEADERS and k.lower() not in ('x-relay-key', 'host', 'content-length'):
            forward_headers[k] = v

    forward_headers["Host"] = "api.telegram.org"
    if "User-Agent" not in forward_headers and "user-agent" not in forward_headers:
        forward_headers["User-Agent"] = "TelegramRelayProxy/2.0"

    try:
        req = urllib.request.Request(
            url=target_url,
            data=body_bytes if body_bytes else None,
            headers=forward_headers,
            method=method
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            resp_headers = []
            for name, val in resp.getheaders():
                if name.lower() not in HOP_BY_HOP_HEADERS:
                    resp_headers.append((name, val))
            resp_body = resp.read()
            return resp.status, resp_headers, resp_body

    except urllib.error.HTTPError as e:
        resp_headers = []
        for name, val in e.headers.items():
            if name.lower() not in HOP_BY_HOP_HEADERS:
                resp_headers.append((name, val))
        err_body = e.read()
        return e.code, resp_headers, err_body

    except Exception as e:
        err_payload = json.dumps({
            "ok": False,
            "error_code": 502,
            "description": f"Relay Proxy Error: {str(e)}"
        }).encode('utf-8')
        return 502, [("Content-Type", "application/json; charset=utf-8")], err_payload

# ----------------- CGI RUNNER -----------------

def run_cgi():
    method = os.environ.get("REQUEST_METHOD", "GET").upper()
    req_uri = os.environ.get("REQUEST_URI", "/")
    content_length = os.environ.get("CONTENT_LENGTH")
    
    body_data = None
    if content_length and content_length.isdigit() and int(content_length) > 0:
        body_data = stdin_raw.read(int(content_length))
        
    req_headers = {}
    for k, v in os.environ.items():
        if k.startswith("HTTP_"):
            hdr_name = k[5:].replace("_", "-").title()
            req_headers[hdr_name] = v
    if os.environ.get("CONTENT_TYPE"):
        req_headers["Content-Type"] = os.environ["CONTENT_TYPE"]

    status_code, resp_headers, resp_body = process_http_request(
        method, req_uri, req_headers, body_data, os.environ
    )

    reason = http_responses.get(status_code, "OK")
    header_lines = [f"Status: {status_code} {reason}"]
    has_cl = False
    for k, v in resp_headers:
        if k.lower() == 'content-length':
            has_cl = True
        header_lines.append(f"{k}: {v}")
    if not has_cl and resp_body is not None:
        header_lines.append(f"Content-Length: {len(resp_body)}")

    header_text = "\r\n".join(header_lines) + "\r\n\r\n"
    stdout_raw.write(header_text.encode('utf-8'))
    if resp_body:
        stdout_raw.write(resp_body)
    stdout_raw.flush()

# ----------------- STANDALONE MULTI-THREADED SERVER -----------------

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class StandaloneHandler(http.server.BaseHTTPRequestHandler):
    custom_base_path = ""

    def handle_request_wrapper(self, method):
        length = 0
        cl_hdr = self.headers.get('Content-Length')
        if cl_hdr and cl_hdr.isdigit():
            length = int(cl_hdr)
        body = self.rfile.read(length) if length > 0 else b""

        env_dict = {
            'REQUEST_METHOD': method,
            'REQUEST_URI': self.path,
            'HTTP_HOST': self.headers.get('Host', 'localhost'),
            'HTTP_COOKIE': self.headers.get('Cookie', ''),
            'SERVER_PORT': str(self.server.server_port),
            'REMOTE_ADDR': self.client_address[0]
        }
        for k, v in self.headers.items():
            env_dict[f"HTTP_{k.upper().replace('-', '_')}"] = v

        req_headers = {k: v for k, v in self.headers.items()}

        status_code, resp_headers, resp_body = process_http_request(
            method, self.path, req_headers, body, env_dict, self.custom_base_path
        )

        self.send_response_only(status_code)
        has_cl = False
        for k, v in resp_headers:
            if k.lower() == 'content-length':
                has_cl = True
            self.send_header(k, v)
        if not has_cl and resp_body is not None:
            self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()

        if resp_body and method != 'HEAD':
            self.wfile.write(resp_body)

    def do_GET(self): self.handle_request_wrapper('GET')
    def do_POST(self): self.handle_request_wrapper('POST')
    def do_HEAD(self): self.handle_request_wrapper('HEAD')
    def do_OPTIONS(self): self.handle_request_wrapper('OPTIONS')
    def do_PUT(self): self.handle_request_wrapper('PUT')
    def do_DELETE(self): self.handle_request_wrapper('DELETE')

    def log_message(self, format, *args):
        # Clean logging
        sys.stderr.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {args[0]} {args[1]} -> {args[2]}\n")

def run_standalone(host="0.0.0.0", port=80, base_path="", ssl_cert=None, ssl_key=None, ssl_port=443):
    import threading
    StandaloneHandler.custom_base_path = base_path

    # Auto-detect default certificate files in application directory if not provided
    if not ssl_cert or not ssl_key:
        default_cert = os.path.join(BASE_DIR, "server.crt")
        default_key = os.path.join(BASE_DIR, "server.key")
        if os.path.exists(default_cert) and os.path.exists(default_key):
            ssl_cert, ssl_key = default_cert, default_key

    # 1. Initialize HTTP Server
    httpd = ThreadedHTTPServer((host, port), StandaloneHandler)

    print("=" * 60)
    print(f"⚡ Telegram Bot API Relay & Admin Panel (Standalone Mode)")
    print(f"🚀 HTTP Server listening on:  http://{host}:{port}{base_path}")

    # 2. Initialize HTTPS Server if SSL cert & key are available
    httpsd = None
    if ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        try:
            httpsd = ThreadedHTTPServer((host, ssl_port), StandaloneHandler)
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(certfile=ssl_cert, keyfile=ssl_key)
            httpsd.socket = ssl_ctx.wrap_socket(httpsd.socket, server_side=True)
            print(f"🔒 HTTPS Server listening on: https://{host}:{ssl_port}{base_path}")
        except Exception as e:
            print(f"⚠️ Could not start HTTPS on port {ssl_port}: {e}")
            httpsd = None

    print(f"⚙️ Configuration: {CONFIG_FILE}")
    print("=" * 60)

    if httpsd:
        t_https = threading.Thread(target=httpsd.serve_forever, daemon=True)
        t_https.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()
        if httpsd:
            httpsd.server_close()

# ----------------- MAIN DISPATCHER -----------------

def main():
    # If invoked by Apache / LiteSpeed CGI
    if "GATEWAY_INTERFACE" in os.environ or "REQUEST_METHOD" in os.environ:
        run_cgi()
        return

    # Otherwise, run Standalone CLI mode
    parser = argparse.ArgumentParser(description="Telegram Bot API Relay & Admin Panel Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=80, help="Port to listen on (default: 80)")
    parser.add_argument("--base-path", default="", help="Base URL path prefix (default: '')")
    parser.add_argument("--ssl-cert", default=None, help="Path to SSL certificate file (.crt or .pem)")
    parser.add_argument("--ssl-key", default=None, help="Path to SSL private key file (.key)")
    args = parser.parse_args()

    run_standalone(
        host=args.host,
        port=args.port,
        base_path=args.base_path,
        ssl_cert=args.ssl_cert,
        ssl_key=args.ssl_key
    )

if __name__ == "__main__":
    main()
