"""
Database backups: consistent SQLite snapshots, delivery to a Telegram chat,
scheduling, and restore.

Settings (stored in the database, edited from the panel):
    backup_bot_token        Telegram bot token that sends the file
    backup_chat_id          chat / channel id that receives it
    backup_interval_hours   0 = automatic backups off
"""

import gzip
import json
import os
import shutil
import socket
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

from . import __version__, paths

REQUIRED_TABLES = {"settings", "services", "access_keys"}
CHECK_EVERY = 60
_lock = threading.Lock()


def snapshot(store):
    """Return (filename, gzip bytes) of a consistent copy of the database."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        dst = sqlite3.connect(tmp)
        store.db.backup(dst)
        dst.close()
        with open(tmp, "rb") as f:
            data = gzip.compress(f.read(), 9)
    finally:
        os.remove(tmp)
    host = (store.get("public_url") or socket.gethostname()).split("://")[-1].strip("/").replace("/", "_")
    name = "gozar-{}-{}.db.gz".format(host, time.strftime("%Y%m%d-%H%M"))
    return name, data


def send_telegram(token, chat_id, filename, data, caption=""):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", str(chat_id)), ("caption", caption)):
        parts.append('--{}\r\nContent-Disposition: form-data; name="{}"\r\n\r\n{}\r\n'.format(boundary, k, v).encode())
    parts.append('--{}\r\nContent-Disposition: form-data; name="document"; filename="{}"\r\n'
                 'Content-Type: application/gzip\r\n\r\n'.format(boundary, filename).encode())
    parts.append(data + b"\r\n--" + boundary.encode() + b"--\r\n")
    req = urllib.request.Request("https://api.telegram.org/bot{}/sendDocument".format(token), data=b"".join(parts))
    req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        res = json.loads(e.read().decode() or "{}")
    if not res.get("ok"):
        raise RuntimeError(res.get("description") or "Telegram rejected the file")
    return res


def run(store, reason="manual"):
    """Take a snapshot and send it. Records the outcome in settings. Returns (ok, message)."""
    token, chat = store.get("backup_bot_token") or "", store.get("backup_chat_id") or ""
    if not token or not chat:
        return False, "توکن ربات یا شناسهٔ چت تنظیم نشده است"
    with _lock:
        try:
            name, data = snapshot(store)
            stats = "{} کلید · {} سرویس".format(len(store.list_keys()), len(store.list_services()))
            caption = "🗄 بکاپ گذر v{} ({})\n{}\n{}".format(
                __version__, "خودکار" if reason == "auto" else "دستی", stats, time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()))
            send_telegram(token, chat, name, data, caption)
            msg = "ارسال شد: {} ({} KB)".format(name, max(1, len(data) // 1024))
            ok = True
        except Exception as exc:  # network, Telegram, disk
            msg, ok = "خطا: {}".format(exc), False
        store.set("backup_last_at", int(time.time()))
        store.set("backup_last_status", msg)
        return ok, msg


def due(store):
    hours = int(store.get("backup_interval_hours") or 0)
    if hours <= 0 or not store.get("backup_bot_token") or not store.get("backup_chat_id"):
        return False
    return time.time() - int(store.get("backup_last_at") or 0) >= hours * 3600


def maybe_run(store=None):
    if store is None:
        from .store import get_store
        store = get_store()
    if due(store):
        run(store, "auto")


def start_scheduler():
    """Background thread for the standalone server."""
    def loop():
        from .store import Store
        st = Store()
        while True:
            try:
                maybe_run(st)
            except Exception:
                pass
            time.sleep(CHECK_EVERY)
    threading.Thread(target=loop, name="gozar-backup", daemon=True).start()


def restore(src, db_path=None):
    """Replace the database with a backup (.db or .db.gz). Validates it first."""
    db_path = db_path or paths.db_path()
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=os.path.dirname(db_path))
    os.close(fd)
    try:
        opener = gzip.open if src.endswith(".gz") else open
        with opener(src, "rb") as fin, open(tmp, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        conn = sqlite3.connect(tmp)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("backup file is corrupt")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES <= tables:
                raise ValueError("not a Gozar database")
            keys = conn.execute("SELECT COUNT(*) FROM access_keys").fetchone()[0]
            services = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
        finally:
            conn.close()
        if os.path.exists(db_path):
            shutil.copy2(db_path, db_path + ".before-restore")
        os.replace(tmp, db_path)
        os.chmod(db_path, 0o600)
        return keys, services
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
