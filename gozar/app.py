"""Top-level dispatcher shared by every runner."""

import traceback

from . import __version__, panel, proxy
from .http import Response, json_response
from .store import get_store


def client_ip(req, store, peer):
    if store.get("trust_proxy"):
        for name in ("CF-Connecting-IP", "X-Real-IP"):
            if req.headers.get(name):
                return req.headers[name].strip()
        xff = req.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    return peer


def dispatch(req, store=None):
    store = store or get_store()
    req.client_ip = client_ip(req, store, req.client_ip)
    try:
        if req.path == "/" or req.path.startswith("/_panel"):
            return panel.handle(req, store)
        if req.path == "/_health":
            return json_response({"status": "ok", "enabled": bool(store.get("enabled")), "version": __version__})
        if req.path in ("/favicon.ico", "/robots.txt"):
            body = b"User-agent: *\nDisallow: /\n" if req.path == "/robots.txt" else b""
            return Response(200 if body else 204, [("Content-Type", "text/plain")], body)
        return proxy.handle(req, store)
    except Exception:
        traceback.print_exc()
        return json_response({"error": {"message": "[Gozar] Internal relay error", "type": "internal"}}, 500)
