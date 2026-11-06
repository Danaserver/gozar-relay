"""Filesystem locations. Everything can be overridden with environment variables."""

import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PACKAGE_DIR)
STATIC_DIR = os.path.join(PACKAGE_DIR, "panel", "static")

DENY_ALL_HTACCESS = """<IfModule mod_authz_core.c>
    Require all denied
</IfModule>
<IfModule !mod_authz_core.c>
    Order Allow,Deny
    Deny from all
</IfModule>
"""


def data_dir():
    """Directory holding the database. Keep it outside the web root when possible."""
    path = os.environ.get("GOZAR_DATA_DIR") or os.path.join(APP_DIR, "data")
    if not os.path.isdir(path):
        os.makedirs(path, mode=0o700, exist_ok=True)
    guard = os.path.join(path, ".htaccess")
    if not os.path.exists(guard):
        try:
            with open(guard, "w") as f:
                f.write(DENY_ALL_HTACCESS)
        except OSError:
            pass
    return path


def db_path():
    return os.environ.get("GOZAR_DB") or os.path.join(data_dir(), "gozar.db")


def legacy_config_path():
    """config.json written by the old single-file Telegram relay (v1)."""
    return os.path.join(APP_DIR, "config.json")
