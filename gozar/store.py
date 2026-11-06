"""SQLite-backed storage for settings, services, access keys and request logs."""

import json
import os
import secrets
import sqlite3
import threading
import time

from . import paths, presets, security

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS services (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    preset        TEXT NOT NULL DEFAULT 'custom',
    upstream      TEXT NOT NULL,
    auth_type     TEXT NOT NULL DEFAULT 'none',
    auth_name     TEXT NOT NULL DEFAULT '',
    upstream_keys TEXT NOT NULL DEFAULT '',
    timeout       INTEGER NOT NULL DEFAULT 120,
    enabled       INTEGER NOT NULL DEFAULT 1,
    cors          INTEGER NOT NULL DEFAULT 0,
    note          TEXT NOT NULL DEFAULT '',
    created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS access_keys (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    key           TEXT NOT NULL UNIQUE,
    services      TEXT NOT NULL DEFAULT '*',
    enabled       INTEGER NOT NULL DEFAULT 1,
    rate_limit    INTEGER NOT NULL DEFAULT 0,
    expires_at    INTEGER NOT NULL DEFAULT 0,
    note          TEXT NOT NULL DEFAULT '',
    created_at    INTEGER NOT NULL,
    last_used_at  INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS request_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    key_id      INTEGER,
    service     TEXT,
    method      TEXT,
    path        TEXT,
    status      INTEGER,
    duration_ms INTEGER,
    bytes_out   INTEGER,
    client_ip   TEXT,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_ts  ON request_log (ts);
CREATE INDEX IF NOT EXISTS idx_log_key ON request_log (key_id, ts);
CREATE TABLE IF NOT EXISTS login_attempts (
    ip TEXT NOT NULL,
    ts REAL NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "enabled": True,
    "admin_username": "admin",
    "admin_password_hash": "",
    "secret": "",
    "session_generation": 1,
    "log_retention": 5000,
    "trust_proxy": False,
    "public_url": "",
}

SERVICE_FIELDS = ("slug", "name", "preset", "upstream", "auth_type", "auth_name",
                  "upstream_keys", "timeout", "enabled", "cors", "note")
KEY_FIELDS = ("name", "key", "services", "enabled", "rate_limit", "expires_at", "note")


def _row(row):
    return dict(row) if row is not None else None


class Store:
    """Thin data-access layer. One SQLite connection per thread."""

    def __init__(self, path=None):
        self.path = path or paths.db_path()
        self._local = threading.local()
        self._init_lock = threading.Lock()
        with self._init_lock:
            db = self.db
            db.executescript(SCHEMA)
            db.commit()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @property
    def db(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 15000")
            self._local.conn = conn
        return conn

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ---------------------------------------------------------------- settings

    def get(self, key, default=None):
        row = self.db.execute("SELECT v FROM settings WHERE k = ?", (key,)).fetchone()
        if row is None:
            return DEFAULT_SETTINGS.get(key, default) if default is None else default
        return json.loads(row["v"])

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO settings (k, v) VALUES (?, ?)",
                        (key, json.dumps(value, ensure_ascii=False)))

    def settings(self):
        out = dict(DEFAULT_SETTINGS)
        for row in self.db.execute("SELECT k, v FROM settings"):
            out[row["k"]] = json.loads(row["v"])
        return out

    # --------------------------------------------------------------- bootstrap

    def is_initialized(self):
        return bool(self.get("admin_password_hash"))

    def initialize(self, username="admin", password=None, seed_services=True, first_key=True):
        """
        Create admin credentials, signing secret, default services and a first
        access key. Returns a dict with the generated plaintext secrets.
        """
        password = password or security.random_password()
        self.set("admin_username", username)
        self.set("admin_password_hash", security.hash_password(password))
        if not self.get("secret"):
            self.set("secret", secrets.token_hex(32))
        if self.get("installed_at", 0) == 0:
            self.set("installed_at", int(time.time()))
        result = {"username": username, "password": password, "key": None}

        if seed_services and not self.list_services():
            for preset_id in presets.DEFAULT_SERVICES:
                p = presets.get_preset(preset_id)
                self.add_service({k: p[k] for k in ("slug", "name", "preset", "upstream",
                                                    "auth_type", "auth_name", "timeout")})
        if first_key and not self.list_keys():
            result["key"] = self.add_key({"name": "کلید پیش‌فرض", "services": "*"})["key"]
        return result

    def import_legacy_config(self, path):
        """Migrate a v1 config.json (Telegram-only relay). Returns True on success."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            return False
        admin = cfg.get("admin") or {}
        if admin.get("password_hash"):
            self.set("admin_username", admin.get("username") or "admin")
            self.set("admin_password_hash", admin["password_hash"])
        self.set("enabled", bool(cfg.get("enabled", True)))
        if not self.get("secret"):
            self.set("secret", secrets.token_hex(32))
        self.initialize_services_only()
        existing = {k["key"] for k in self.list_keys()}
        for k in cfg.get("bot_keys") or []:
            if k.get("key") and k["key"] not in existing:
                self.add_key({"name": k.get("name") or "Legacy bot", "key": k["key"],
                              "services": "telegram", "enabled": bool(k.get("enabled", True)),
                              "note": "Imported from v1"})
        return True

    def import_bootstrap(self, path):
        """
        Apply a one-shot bootstrap file (used by the cPanel deployer, which cannot
        run commands on the host). The file is deleted afterwards.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                boot = json.load(f)
        except (OSError, ValueError):
            return False
        if boot.get("admin_password_hash"):
            self.set("admin_username", boot.get("admin_username") or "admin")
            self.set("admin_password_hash", boot["admin_password_hash"])
        if not self.get("secret"):
            self.set("secret", secrets.token_hex(32))
        if boot.get("public_url"):
            self.set("public_url", boot["public_url"])
        self.initialize_services_only()
        existing = {k["key"] for k in self.list_keys()}
        for k in boot.get("keys") or []:
            if k.get("key") and k["key"] not in existing:
                self.add_key(k)
        try:
            os.remove(path)
        except OSError:
            pass
        return True

    def initialize_services_only(self):
        if not self.list_services():
            for preset_id in presets.DEFAULT_SERVICES:
                p = presets.get_preset(preset_id)
                self.add_service({k: p[k] for k in ("slug", "name", "preset", "upstream",
                                                    "auth_type", "auth_name", "timeout")})
        if self.get("installed_at", 0) == 0:
            self.set("installed_at", int(time.time()))

    # ---------------------------------------------------------------- services

    def list_services(self):
        return [_row(r) for r in self.db.execute("SELECT * FROM services ORDER BY id")]

    def get_service(self, slug=None, service_id=None):
        if service_id is not None:
            return _row(self.db.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone())
        return _row(self.db.execute("SELECT * FROM services WHERE slug = ?", (slug,)).fetchone())

    def add_service(self, data):
        cols = [c for c in SERVICE_FIELDS if c in data]
        vals = [data[c] for c in cols]
        cur = self.db.execute(
            "INSERT INTO services ({}, created_at) VALUES ({}, ?)".format(
                ", ".join(cols), ", ".join("?" * len(cols))),
            vals + [int(time.time())])
        return self.get_service(service_id=cur.lastrowid)

    def update_service(self, service_id, data):
        cols = [c for c in SERVICE_FIELDS if c in data]
        if cols:
            self.db.execute(
                "UPDATE services SET {} WHERE id = ?".format(", ".join(c + " = ?" for c in cols)),
                [data[c] for c in cols] + [service_id])
        return self.get_service(service_id=service_id)

    def delete_service(self, service_id):
        self.db.execute("DELETE FROM services WHERE id = ?", (service_id,))

    # ------------------------------------------------------------- access keys

    def list_keys(self):
        return [_row(r) for r in self.db.execute("SELECT * FROM access_keys ORDER BY id")]

    def get_key(self, key=None, key_id=None):
        if key_id is not None:
            return _row(self.db.execute("SELECT * FROM access_keys WHERE id = ?", (key_id,)).fetchone())
        return _row(self.db.execute("SELECT * FROM access_keys WHERE key = ?", (key,)).fetchone())

    def add_key(self, data):
        data = dict(data)
        data.setdefault("key", security.new_access_key())
        cols = [c for c in KEY_FIELDS if c in data]
        cur = self.db.execute(
            "INSERT INTO access_keys ({}, created_at) VALUES ({}, ?)".format(
                ", ".join(cols), ", ".join("?" * len(cols))),
            [data[c] for c in cols] + [int(time.time())])
        return self.get_key(key_id=cur.lastrowid)

    def update_key(self, key_id, data):
        cols = [c for c in KEY_FIELDS if c in data]
        if cols:
            self.db.execute(
                "UPDATE access_keys SET {} WHERE id = ?".format(", ".join(c + " = ?" for c in cols)),
                [data[c] for c in cols] + [key_id])
        return self.get_key(key_id=key_id)

    def delete_key(self, key_id):
        self.db.execute("DELETE FROM access_keys WHERE id = ?", (key_id,))

    def requests_last_minute(self, key_id):
        row = self.db.execute("SELECT COUNT(*) AS n FROM request_log WHERE key_id = ? AND ts > ?",
                              (key_id, time.time() - 60)).fetchone()
        return row["n"]

    # ------------------------------------------------------------------ logging

    def log_request(self, entry):
        db = self.db
        db.execute(
            "INSERT INTO request_log (ts, key_id, service, method, path, status, duration_ms,"
            " bytes_out, client_ip, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry.get("ts", time.time()), entry.get("key_id"), entry.get("service"),
             entry.get("method"), (entry.get("path") or "")[:300], entry.get("status"),
             entry.get("duration_ms"), entry.get("bytes_out"), entry.get("client_ip"),
             (entry.get("error") or "")[:300] or None))
        if entry.get("key_id"):
            db.execute("UPDATE access_keys SET last_used_at = ?, request_count = request_count + 1"
                       " WHERE id = ?", (int(time.time()), entry["key_id"]))
        if secrets.randbelow(50) == 0:
            self.prune_logs()

    def prune_logs(self):
        keep = int(self.get("log_retention") or 5000)
        self.db.execute("DELETE FROM request_log WHERE id <= (SELECT MAX(id) FROM request_log) - ?", (keep,))
        self.db.execute("DELETE FROM login_attempts WHERE ts < ?", (time.time() - 86400,))

    def recent_logs(self, limit=100, service=None, key_id=None, errors_only=False):
        sql = ("SELECT l.*, k.name AS key_name FROM request_log l"
               " LEFT JOIN access_keys k ON k.id = l.key_id WHERE 1 = 1")
        args = []
        if service:
            sql += " AND l.service = ?"
            args.append(service)
        if key_id:
            sql += " AND l.key_id = ?"
            args.append(key_id)
        if errors_only:
            sql += " AND (l.status >= 400 OR l.status IS NULL)"
        sql += " ORDER BY l.id DESC LIMIT ?"
        args.append(min(int(limit), 500))
        return [_row(r) for r in self.db.execute(sql, args)]

    def clear_logs(self):
        self.db.execute("DELETE FROM request_log")

    def stats(self):
        now = time.time()
        day_ago = now - 86400
        db = self.db
        total = db.execute("SELECT COUNT(*) n, COALESCE(SUM(bytes_out),0) b FROM request_log WHERE ts > ?",
                           (day_ago,)).fetchone()
        errors = db.execute("SELECT COUNT(*) n FROM request_log WHERE ts > ? AND (status >= 400 OR status IS NULL)",
                            (day_ago,)).fetchone()["n"]
        avg = db.execute("SELECT AVG(duration_ms) a FROM request_log WHERE ts > ? AND status < 400",
                         (day_ago,)).fetchone()["a"]
        by_service = [_row(r) for r in db.execute(
            "SELECT service, COUNT(*) n, SUM(CASE WHEN status >= 400 OR status IS NULL THEN 1 ELSE 0 END) errors"
            " FROM request_log WHERE ts > ? GROUP BY service ORDER BY n DESC", (day_ago,))]
        hourly = {}
        for r in db.execute("SELECT CAST((ts - ?) / 3600 AS INTEGER) h, COUNT(*) n,"
                            " SUM(CASE WHEN status >= 400 OR status IS NULL THEN 1 ELSE 0 END) e"
                            " FROM request_log WHERE ts > ? GROUP BY h", (day_ago, day_ago)):
            hourly[r["h"]] = (r["n"], r["e"])
        return {
            "requests_24h": total["n"],
            "bytes_24h": total["b"],
            "errors_24h": errors,
            "avg_ms": int(avg or 0),
            "by_service": by_service,
            "hourly": [{"n": hourly.get(h, (0, 0))[0], "e": hourly.get(h, (0, 0))[1]} for h in range(24)],
            "hour_start": int(day_ago),
        }

    # ------------------------------------------------------------ login guard

    def failed_logins(self, ip, window=900):
        row = self.db.execute("SELECT COUNT(*) n FROM login_attempts WHERE ip = ? AND ts > ?",
                              (ip, time.time() - window)).fetchone()
        return row["n"]

    def record_failed_login(self, ip):
        self.db.execute("INSERT INTO login_attempts (ip, ts) VALUES (?, ?)", (ip, time.time()))

    def clear_failed_logins(self, ip):
        self.db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))


_store = None
_store_lock = threading.Lock()


def get_store():
    """Process-wide store, bootstrapped from legacy/bootstrap files on first use."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                st = Store()
                boot = os.path.join(paths.data_dir(), "bootstrap.json")
                if os.path.exists(boot):
                    st.import_bootstrap(boot)
                elif not st.is_initialized() and os.path.exists(paths.legacy_config_path()):
                    st.import_legacy_config(paths.legacy_config_path())
                _store = st
    return _store
