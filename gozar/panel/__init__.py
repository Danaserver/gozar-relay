"""Admin panel: login flow, static assets and the JSON API used by the SPA."""

import html
import mimetypes
import os
import re
import time

from .. import __version__, paths, presets, proxy, security
from ..http import Response, html_response, json_response, redirect

SESSION_COOKIE = "gozar_session"
MAX_FAILED_LOGINS = 8


def _template(name, **values):
    with open(os.path.join(paths.STATIC_DIR, name), "r", encoding="utf-8") as f:
        text = f.read()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def public_url(req, store):
    return (store.get("public_url") or "").rstrip("/") or req.base_url


# --------------------------------------------------------------------- session

def current_user(req, store):
    token = req.cookie(SESSION_COOKIE)
    if not token:
        return None, None
    user = security.verify_session(token, store.get("secret"), store.get("session_generation"))
    if user and user == store.get("admin_username"):
        return user, token
    return None, None


def start_session(resp, req, store, username):
    token = security.make_session(username, store.get("secret"), store.get("session_generation"))
    resp.set_cookie(SESSION_COOKIE, token, req, max_age=security.SESSION_MAX_AGE)


# ---------------------------------------------------------------------- pages

def login_page(req, store, error="", status=200):
    token, svg = security.new_captcha(store.get("secret"))
    err = '<div class="alert alert-error">{}</div>'.format(html.escape(error)) if error else ""
    page = _template("login.html", base=html.escape(req.base_path), captcha_token=token,
                     captcha_svg=svg, error=err, version=__version__, host=html.escape(req.host))
    return html_response(page, status)


def app_page(req, store, session_token):
    page = _template("app.html", base=html.escape(req.base_path), version=__version__,
                     csrf=security.csrf_token(session_token, store.get("secret")))
    return html_response(page)


def static_file(name):
    if not re.match(r"^[a-z0-9_\-]+\.(css|js|svg|png|ico|woff2)$", name):
        return Response(404, [], b"")
    path = os.path.join(paths.STATIC_DIR, name)
    if not os.path.isfile(path):
        return Response(404, [], b"")
    with open(path, "rb") as f:
        data = f.read()
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if ctype.startswith("text/") or name.endswith(".js"):
        ctype += "; charset=utf-8"
    return Response(200, [("Content-Type", ctype), ("Cache-Control", "public, max-age=3600")], data)


# --------------------------------------------------------------------- router

def handle(req, store):
    sub = req.path[len("/_panel"):] if req.path.startswith("/_panel") else req.path

    if sub.startswith("/static/"):
        return static_file(sub[len("/static/"):])

    if sub == "/login" and req.method == "POST":
        return do_login(req, store)

    if sub == "/captcha":
        token, svg = security.new_captcha(store.get("secret"))
        return json_response({"token": token, "svg": svg})

    user, token = current_user(req, store)

    if sub == "/logout" and req.method == "POST":
        resp = redirect(req.base_path + "/")
        resp.set_cookie(SESSION_COOKIE, "", req, max_age=0)
        return resp

    if sub in ("/", "", "/login"):
        if not store.is_initialized():
            return html_response(_template("setup.html", version=__version__), 503)
        return app_page(req, store, token) if user else login_page(req, store)

    if sub.startswith("/api/"):
        if not user:
            return json_response({"error": "unauthorized"}, 401)
        if req.method != "GET":
            expected = security.csrf_token(token, store.get("secret"))
            if req.headers.get("X-CSRF-Token") != expected:
                return json_response({"error": "csrf"}, 403)
        try:
            return api(req, store, sub[len("/api/"):])
        except ValueError as exc:
            return json_response({"error": str(exc)}, 400)

    return Response(404, [("Content-Type", "text/plain")], b"Not found")


def do_login(req, store):
    form = req.form()
    ip = req.client_ip or "?"
    if store.failed_logins(ip) >= MAX_FAILED_LOGINS:
        return login_page(req, store, "تعداد تلاش‌های ناموفق زیاد است. ۱۵ دقیقه دیگر دوباره امتحان کنید.", 429)
    if not security.verify_captcha(form.get("captcha", ""), form.get("captcha_token", ""), store.get("secret")):
        return login_page(req, store, "کد امنیتی اشتباه یا منقضی شده است.", 400)
    username = (form.get("username") or "").strip()
    if username != store.get("admin_username") or not security.verify_password(
            form.get("password") or "", store.get("admin_password_hash")):
        store.record_failed_login(ip)
        time.sleep(0.6)
        return login_page(req, store, "نام کاربری یا رمز عبور اشتباه است.", 401)
    store.clear_failed_logins(ip)
    resp = redirect(req.base_path + "/")
    start_session(resp, req, store, username)
    return resp


# ------------------------------------------------------------------------ API

def _service_view(s):
    out = dict(s)
    keys = [k for k in (s.get("upstream_keys") or "").splitlines() if k.strip()]
    out["upstream_keys"] = [security.mask_secret(k.strip()) for k in keys]
    out["managed"] = bool(keys)
    out["enabled"] = bool(s["enabled"])
    out["cors"] = bool(s["cors"])
    return out


def _key_view(k):
    out = dict(k)
    out["enabled"] = bool(k["enabled"])
    out["services"] = [s.strip() for s in (k["services"] or "*").split(",") if s.strip()]
    return out


def _int(value, default=0, lo=0, hi=10 ** 9):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _bool(value):
    return value in (True, 1, "1", "true", "on", "yes")


def api(req, store, action):
    data = req.form() if req.method != "GET" else {}

    if action == "state":
        settings = store.settings()
        return json_response({
            "version": __version__,
            "base_url": public_url(req, store),
            "settings": {k: settings.get(k) for k in ("enabled", "admin_username", "log_retention",
                                                       "trust_proxy", "public_url", "installed_at")},
            "services": [_service_view(s) for s in store.list_services()],
            "keys": [_key_view(k) for k in store.list_keys()],
            "presets": presets.PRESETS,
            "stats": store.stats(),
        })

    if action == "relay/toggle":
        store.set("enabled", not store.get("enabled"))
        return json_response({"enabled": store.get("enabled")})

    if action == "services/save":
        return json_response({"service": _service_view(save_service(store, data))})

    if action == "services/delete":
        store.delete_service(_int(data.get("id")))
        return json_response({"ok": True})

    if action == "services/test":
        svc = store.get_service(service_id=_int(data.get("id")))
        if not svc:
            raise ValueError("سرویس پیدا نشد")
        ok, detail, ms = proxy.probe(svc)
        return json_response({"ok": ok, "detail": detail, "ms": ms})

    if action == "keys/save":
        return json_response({"key": _key_view(save_key(store, data))})

    if action == "keys/rotate":
        kid = _int(data.get("id"))
        return json_response({"key": _key_view(store.update_key(kid, {"key": security.new_access_key()}))})

    if action == "keys/delete":
        store.delete_key(_int(data.get("id")))
        return json_response({"ok": True})

    if action == "logs":
        p = req.query_params()
        rows = store.recent_logs(limit=_int((p.get("limit") or [150])[0], 150, 1, 500),
                                 service=(p.get("service") or [None])[0] or None,
                                 key_id=_int((p.get("key_id") or [0])[0]) or None,
                                 errors_only=(p.get("errors") or ["0"])[0] == "1")
        return json_response({"logs": rows})

    if action == "logs/clear":
        store.clear_logs()
        return json_response({"ok": True})

    if action == "settings/save":
        store.set("trust_proxy", _bool(data.get("trust_proxy")))
        store.set("log_retention", _int(data.get("log_retention"), 5000, 100, 200000))
        url = (data.get("public_url") or "").strip().rstrip("/")
        if url and not re.match(r"^https?://[^\s/]+(/[^\s]*)?$", url):
            raise ValueError("آدرس عمومی نامعتبر است")
        store.set("public_url", url)
        return json_response({"ok": True})

    if action == "account":
        if not security.verify_password(data.get("current_password") or "", store.get("admin_password_hash")):
            raise ValueError("رمز عبور فعلی اشتباه است")
        username = (data.get("username") or "").strip()
        new_pass = data.get("new_password") or ""
        if not re.match(r"^[A-Za-z0-9_.\-@]{3,40}$", username):
            raise ValueError("نام کاربری نامعتبر است")
        if new_pass and len(new_pass) < 8:
            raise ValueError("رمز عبور جدید باید حداقل ۸ کاراکتر باشد")
        store.set("admin_username", username)
        if new_pass:
            store.set("admin_password_hash", security.hash_password(new_pass))
        store.set("session_generation", int(store.get("session_generation")) + 1)
        resp = json_response({"ok": True})
        start_session(resp, req, store, username)
        return resp

    return json_response({"error": "not found"}, 404)


def save_service(store, data):
    sid = _int(data.get("id"))
    current = store.get_service(service_id=sid) if sid else None
    preset = presets.get_preset(data.get("preset") or (current or {}).get("preset") or "custom")

    slug = (data.get("slug") or "").strip().lower()
    if not security.SLUG_PATTERN.match(slug):
        raise ValueError("شناسه (slug) باید با حرف انگلیسی شروع شود و فقط شامل a-z، 0-9 و - باشد (۲ تا ۳۲ کاراکتر)")
    other = store.get_service(slug=slug)
    if other and other["id"] != sid:
        raise ValueError("این شناسه قبلاً استفاده شده است")
    if store.get_key(key=slug):
        raise ValueError("این شناسه با یک کلید دسترسی تداخل دارد")

    upstream = (data.get("upstream") or "").strip().rstrip("/")
    if not re.match(r"^https?://[A-Za-z0-9.\-]+(:\d+)?(/[^\s?#]*)?$", upstream):
        raise ValueError("آدرس مقصد (Upstream) نامعتبر است")

    auth_type = data.get("auth_type") or preset["auth_type"]
    if auth_type not in presets.AUTH_TYPES:
        raise ValueError("نوع احراز هویت نامعتبر است")
    auth_name = (data.get("auth_name") or "").strip()
    if auth_type == "bearer":
        auth_name = "Authorization"
    if auth_type in ("header", "query") and not re.match(r"^[A-Za-z0-9_\-]{1,64}$", auth_name):
        raise ValueError("نام هدر/پارامتر احراز هویت نامعتبر است")

    record = {
        "slug": slug,
        "name": (data.get("name") or preset["name"]).strip()[:80],
        "preset": preset["preset"],
        "upstream": upstream,
        "auth_type": auth_type,
        "auth_name": auth_name if auth_type != "none" else "",
        "timeout": _int(data.get("timeout"), preset["timeout"], 5, 900),
        "enabled": 1 if _bool(data.get("enabled", True)) else 0,
        "cors": 1 if _bool(data.get("cors")) else 0,
        "note": (data.get("note") or "").strip()[:500],
    }
    # Upstream keys: only replaced when the admin typed new ones (the UI never sees them).
    if data.get("clear_upstream_keys"):
        record["upstream_keys"] = ""
    elif (data.get("upstream_keys") or "").strip():
        record["upstream_keys"] = "\n".join(
            k.strip() for k in data["upstream_keys"].splitlines() if k.strip())

    if current:
        if current["slug"] != slug:
            _rename_service_in_keys(store, current["slug"], slug)
        return store.update_service(sid, record)
    return store.add_service(record)


def _rename_service_in_keys(store, old, new):
    for k in store.list_keys():
        items = [s.strip() for s in k["services"].split(",")]
        if old in items:
            store.update_key(k["id"], {"services": ",".join(new if s == old else s for s in items)})


def save_key(store, data):
    kid = _int(data.get("id"))
    services = data.get("services")
    if isinstance(services, str):
        services = [s for s in services.split(",") if s.strip()]
    services = [s.strip() for s in (services or ["*"])]
    known = {s["slug"] for s in store.list_services()}
    if "*" in services:
        services = ["*"]
    elif not services or any(s not in known for s in services):
        raise ValueError("حداقل یک سرویس معتبر انتخاب کنید")

    record = {
        "name": (data.get("name") or "").strip()[:80] or "بدون نام",
        "services": ",".join(services),
        "enabled": 1 if _bool(data.get("enabled", True)) else 0,
        "rate_limit": _int(data.get("rate_limit"), 0, 0, 100000),
        "note": (data.get("note") or "").strip()[:500],
    }
    if "expires_at" in data:
        record["expires_at"] = _int(data.get("expires_at"), 0)

    custom = (data.get("key") or "").strip()
    if custom:
        if not security.KEY_PATTERN.match(custom) or len(custom) < 12:
            raise ValueError("کلید دلخواه باید حداقل ۱۲ کاراکتر و فقط شامل A-Z، a-z، 0-9، _ و - باشد")
        other = store.get_key(key=custom)
        if (other and other["id"] != kid) or store.get_service(slug=custom):
            raise ValueError("این کلید قابل استفاده نیست")
        record["key"] = custom

    if kid:
        if not store.get_key(key_id=kid):
            raise ValueError("کلید پیدا نشد")
        return store.update_key(kid, record)
    return store.add_key(record)

