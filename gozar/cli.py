"""Command-line interface: `python3 relay.py <command>`."""

import argparse
import json
import sys

from . import __version__, paths, security
from .store import get_store


def _print_creds(data, as_json):
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
        return
    print("Username : {}".format(data.get("username")))
    if data.get("password"):
        print("Password : {}".format(data["password"]))
    if data.get("key"):
        print("Access key: {}".format(data["key"]))


def cmd_serve(args):
    from .runners import run_standalone
    get_store()
    run_standalone(host=args.host, port=args.port, ssl_port=args.ssl_port,
                   cert=args.cert, key=args.key, base_path=args.base_path)


def cmd_init(args):
    st = get_store()
    if st.is_initialized() and not args.force:
        print("Already initialized (database: {}). Use --force to reset the admin password."
              .format(paths.db_path()), file=sys.stderr)
        if args.json:
            print(json.dumps({"username": st.get("admin_username"), "password": None, "key": None}))
        return 0
    result = st.initialize(username=args.username or st.get("admin_username") or "admin",
                           password=args.password)
    if args.public_url:
        st.set("public_url", args.public_url.rstrip("/"))
    _print_creds(result, args.json)
    return 0


def cmd_reset_password(args):
    st = get_store()
    password = args.password or security.random_password()
    if args.username:
        st.set("admin_username", args.username)
    st.set("admin_password_hash", security.hash_password(password))
    st.set("session_generation", int(st.get("session_generation")) + 1)
    if not st.get("secret"):
        st.initialize_services_only()
    _print_creds({"username": st.get("admin_username"), "password": password}, args.json)
    return 0


def cmd_key_add(args):
    st = get_store()
    k = st.add_key({"name": args.name, "services": args.services or "*",
                    "rate_limit": args.rate_limit or 0})
    print(json.dumps({"id": k["id"], "name": k["name"], "key": k["key"], "services": k["services"]},
                     ensure_ascii=False) if args.json else k["key"])
    return 0


def cmd_key_list(args):
    for k in get_store().list_keys():
        print("{:>3}  {:<8} {:<36} {:<24} {}".format(
            k["id"], "on" if k["enabled"] else "off", k["key"], k["services"], k["name"]))
    return 0


def cmd_info(args):
    st = get_store()
    print("Gozar v{}".format(__version__))
    print("Database : {}".format(paths.db_path()))
    print("Relay    : {}".format("enabled" if st.get("enabled") else "DISABLED"))
    print("Admin    : {}".format(st.get("admin_username")))
    print("Services :")
    for s in st.list_services():
        print("   /{:<14} -> {:<45} [{}{}]".format(
            s["slug"], s["upstream"], "on" if s["enabled"] else "off",
            ", managed key" if s["upstream_keys"].strip() else ""))
    print("Keys     : {}".format(len(st.list_keys())))
    return 0


def cmd_backup(args):
    from . import backup
    st = get_store()
    if args.send:
        ok, msg = backup.run(st)
        print(msg)
        return 0 if ok else 1
    name, data = backup.snapshot(st)
    out = args.out or name
    with open(out, "wb") as f:
        f.write(data)
    print(out)
    return 0


def cmd_restore(args):
    from . import backup
    keys, services = backup.restore(args.file)
    print("restored: {} keys, {} services -> {}".format(keys, services, paths.db_path()))
    print("restart the service to load it:  systemctl restart gozar")
    return 0


def cmd_bootstrap(args):
    """Write a bootstrap.json for hosts where commands cannot be run (cPanel)."""
    password = args.password or security.random_password()
    key = security.new_access_key()
    boot = {
        "admin_username": args.username,
        "admin_password_hash": security.hash_password(password),
        "public_url": (args.public_url or "").rstrip("/"),
        "keys": [{"name": "کلید پیش‌فرض", "key": key, "services": "*"}],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(boot, f, ensure_ascii=False, indent=2)
    _print_creds({"username": args.username, "password": password, "key": key}, args.json)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="relay.py", description="Gozar universal API relay v" + __version__)
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("serve", help="run the standalone HTTP(S) server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8080, help="HTTP port (0 disables)")
    s.add_argument("--ssl-port", type=int, default=0, help="HTTPS port (0 disables)")
    s.add_argument("--cert", help="TLS certificate (PEM, full chain)")
    s.add_argument("--key", help="TLS private key (PEM)")
    s.add_argument("--base-path", default="", help="serve under a URL prefix, e.g. /relay")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("init", help="create admin credentials, default services and a first key")
    s.add_argument("--username", default="admin")
    s.add_argument("--password")
    s.add_argument("--public-url")
    s.add_argument("--force", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("reset-password", help="set a new admin password (random if omitted)")
    s.add_argument("--username")
    s.add_argument("--password")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_reset_password)

    k = sub.add_parser("key", help="manage access keys").add_subparsers(dest="key_command")
    s = k.add_parser("add")
    s.add_argument("--name", required=True)
    s.add_argument("--services", default="*", help="comma separated slugs, or *")
    s.add_argument("--rate-limit", type=int, default=0, help="requests per minute (0 = unlimited)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_key_add)
    s = k.add_parser("list")
    s.set_defaults(func=cmd_key_list)

    s = sub.add_parser("info", help="show configuration summary")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("backup", help="write a gzip snapshot of the database, or --send it to Telegram")
    s.add_argument("--out", help="output file (default: gozar-<host>-<time>.db.gz)")
    s.add_argument("--send", action="store_true", help="send to the Telegram chat configured in the panel")
    s.set_defaults(func=cmd_backup)

    s = sub.add_parser("restore", help="replace the database with a backup (.db or .db.gz)")
    s.add_argument("file")
    s.set_defaults(func=cmd_restore)

    s = sub.add_parser("bootstrap", help="write a bootstrap.json for cPanel deployments")
    s.add_argument("--out", required=True)
    s.add_argument("--username", default="admin")
    s.add_argument("--password")
    s.add_argument("--public-url")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_bootstrap)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args) or 0

