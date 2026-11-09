#!/usr/bin/env bash
# ==============================================================================
#  Gozar — universal API relay · one-command installer for Linux VPS
#
#    bash <(curl -fsSL https://raw.githubusercontent.com/Danaserver/gozar-relay/main/install.sh)
#
#  Options (flags or environment variables):
#    --domain relay.example.com   DOMAIN=...     public hostname (enables Let's Encrypt)
#    --port 80                    PORT=...       HTTP port   (0 = disabled)
#    --ssl-port 443               SSL_PORT=...   HTTPS port  (0 = disabled)
#    --email you@example.com      EMAIL=...      Let's Encrypt account e-mail
#    --self-signed                               skip Let's Encrypt, use a self-signed cert
#    --listen 127.0.0.1           LISTEN=...     bind address (127.0.0.1 behind nginx/aaPanel)
#    --restore backup.db.gz       RESTORE=...    restore a Gozar backup before starting
#    --app-dir /path              GOZAR_APP_DIR  where the code lives (default /opt/gozar)
#    --yes                                       non-interactive, accept defaults
#    uninstall                                   remove Gozar (keeps the database)
#
#  Supports Ubuntu, Debian, CentOS/RHEL, AlmaLinux, Rocky, Fedora, Alpine, Arch.
# ==============================================================================
set -euo pipefail

REPO="${GOZAR_REPO:-Danaserver/gozar-relay}"
BRANCH="${GOZAR_BRANCH:-main}"
APP_DIR="${GOZAR_APP_DIR:-/opt/gozar}"
DATA_DIR="/var/lib/gozar"
SERVICE="gozar"
BIN="/usr/local/bin/gozar"

DOMAIN="${DOMAIN:-}"; PORT="${PORT:-}"; SSL_PORT="${SSL_PORT:-}"; EMAIL="${EMAIL:-}"
LISTEN="${LISTEN:-0.0.0.0}"; RESTORE="${RESTORE:-}"
SELF_SIGNED=0; ASSUME_YES=0; ACTION="install"

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --ssl-port) SSL_PORT="$2"; shift ;;
    --email) EMAIL="$2"; shift ;;
    --self-signed) SELF_SIGNED=1 ;;
    --listen) LISTEN="$2"; shift ;;
    --restore) RESTORE="$2"; shift ;;
    --app-dir) APP_DIR="${2%/}"; shift ;;
    -y|--yes) ASSUME_YES=1 ;;
    uninstall) ACTION="uninstall" ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

# ------------------------------------------------------------------- styling
if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[34m'; C=$'\033[36m'; W=$'\033[1m'; D=$'\033[2m'; N=$'\033[0m'
else
  R=; G=; Y=; B=; C=; W=; D=; N=
fi
step() { echo -e "\n${B}${W}▸ $*${N}"; }
ok()   { echo -e "  ${G}✓${N} $*"; }
warn() { echo -e "  ${Y}!${N} $*"; }
die()  { echo -e "\n${R}${W}✗ $*${N}\n"; exit 1; }
TTY=0; { [ "$ASSUME_YES" -eq 0 ] && [ -r /dev/tty ] && : </dev/tty; } 2>/dev/null && TTY=1
ask() { # ask VAR "question" default
  local __v="$1" __q="$2" __d="$3" __a=""
  if [ "$TTY" -eq 1 ]; then read -r -p "  $__q ${D}[$__d]${N}: " __a </dev/tty || true; fi
  printf -v "$__v" '%s' "${__a:-$__d}"
}

banner() {
  echo -e "${C}${W}"
  echo "   ██████   ██████  ███████  █████  ██████  "
  echo "  ██       ██    ██    ███  ██   ██ ██   ██ "
  echo "  ██   ███ ██    ██   ███   ███████ ██████  "
  echo "  ██    ██ ██    ██  ███    ██   ██ ██   ██ "
  echo "   ██████   ██████  ███████ ██   ██ ██   ██ "
  echo -e "${N}${D}   Universal API relay — Telegram · OpenRouter · Gemini · any HTTP API${N}"
}

[ "$(id -u)" -eq 0 ] || die "Please run as root:  sudo bash install.sh"
command -v systemctl >/dev/null 2>&1 || die "systemd is required."

# ----------------------------------------------------------------- uninstall
if [ "$ACTION" = "uninstall" ]; then
  systemctl disable --now "$SERVICE" 2>/dev/null || true
  rm -f "/etc/systemd/system/${SERVICE}.service" "$BIN"
  systemctl daemon-reload
  rm -rf "$APP_DIR"
  echo -e "${G}Gozar removed.${N} Database kept at ${DATA_DIR} (delete it manually if not needed)."
  exit 0
fi

banner

# -------------------------------------------------------------- dependencies
step "Installing dependencies"
PKGS="python3 curl openssl tar ca-certificates"
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null && apt-get install -y -qq $PKGS >/dev/null
elif command -v dnf >/dev/null 2>&1; then dnf install -y -q $PKGS >/dev/null
elif command -v yum >/dev/null 2>&1; then yum install -y -q $PKGS >/dev/null
elif command -v apk >/dev/null 2>&1; then apk add -q $PKGS bash >/dev/null
elif command -v pacman >/dev/null 2>&1; then pacman -Sy --noconfirm --needed python curl openssl tar >/dev/null
else warn "Unknown package manager — assuming dependencies are present"; fi
PY="$(command -v python3)" || die "python3 not found"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' || die "Python 3.7+ required ($("$PY" -V))"
ok "$("$PY" -V)"

# ------------------------------------------------------------------ download
step "Installing Gozar to ${APP_DIR}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
if [ -n "$SRC_DIR" ] && [ -f "$SRC_DIR/relay.py" ] && [ -d "$SRC_DIR/gozar" ]; then
  cp -r "$SRC_DIR/relay.py" "$SRC_DIR/gozar" "$STAGE/"
  ok "using local source ($SRC_DIR)"
else
  curl -fsSL "https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}" | tar -xz -C "$STAGE" --strip-components=1 \
    || die "Download failed from github.com/${REPO}"
  ok "downloaded ${REPO}@${BRANCH}"
fi
systemctl stop "$SERVICE" 2>/dev/null || true
mkdir -p "$APP_DIR" "$DATA_DIR"
chmod 700 "$DATA_DIR"
rm -rf "$APP_DIR/gozar"
cp -r "$STAGE/relay.py" "$STAGE/gozar" "$APP_DIR/"
chmod 755 "$APP_DIR/relay.py"

# Migrate the old single-file Telegram relay (v1) if present
if [ -f /opt/telegram-relay/config.json ] && [ ! -f "$DATA_DIR/gozar.db" ]; then
  cp /opt/telegram-relay/config.json "$APP_DIR/config.json"
  systemctl disable --now telegram-relay 2>/dev/null || true
  ok "migrating v1 settings from /opt/telegram-relay (admin login and bot keys are kept)"
fi
VERSION="$("$PY" -c "import sys; sys.path.insert(0,'$APP_DIR'); import gozar; print(gozar.__version__)")"
ok "Gozar v${VERSION}"

# --------------------------------------------------------------------- ports
port_busy() { "$PY" - "$1" <<'EOF' 2>/dev/null
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ignore TIME_WAIT/FIN_WAIT leftovers
try:
    s.bind(("0.0.0.0", int(sys.argv[1]))); sys.exit(1)
except OSError:
    sys.exit(0)
EOF
}
step "Network configuration"
SERVER_IP="$(curl -fs4 --max-time 4 https://api.ipify.org || curl -fs4 --max-time 4 https://ifconfig.me || hostname -I 2>/dev/null | awk '{print $1}')"
ok "public IP: ${SERVER_IP:-unknown}"

if [ -z "$DOMAIN" ]; then
  echo -e "  ${D}Point a domain/subdomain (A record) to ${SERVER_IP} for a trusted HTTPS certificate.${N}"
  ask DOMAIN "Domain (empty = use IP)" ""
fi
DOMAIN="$(echo "$DOMAIN" | sed -e 's#^[a-z]*://##' -e 's#/.*$##' | tr -d ' ')"

if [ -z "$PORT" ]; then
  D80=80; port_busy 80 && { warn "port 80 is in use"; D80=8080; }
  ask PORT "HTTP port (0 = off)" "$D80"
fi
if [ -z "$SSL_PORT" ]; then
  D443=443; port_busy 443 && { warn "port 443 is in use"; D443=8443; }
  ask SSL_PORT "HTTPS port (0 = off)" "$D443"
fi
PORT=$((PORT + 0)); SSL_PORT=$((SSL_PORT + 0))
[ "$PORT" -gt 0 ] || [ "$SSL_PORT" -gt 0 ] || die "At least one port must be enabled"
for p in $PORT $SSL_PORT; do
  [ "$p" -gt 0 ] || continue
  for _ in $(seq 1 20); do port_busy "$p" || break; sleep 1; done  # let the old process release it
  port_busy "$p" && die "port $p is already in use"
done
ok "HTTP: $([ $PORT -gt 0 ] && echo $PORT || echo off)   HTTPS: $([ $SSL_PORT -gt 0 ] && echo $SSL_PORT || echo off)"

# ----------------------------------------------------------------------- TLS
CERT=""; KEY=""
if [ "$SSL_PORT" -gt 0 ]; then
  step "TLS certificate"
  if [ -n "$DOMAIN" ] && [ "$SELF_SIGNED" -eq 0 ] && ! port_busy 80; then
    if ! command -v certbot >/dev/null 2>&1; then
      { command -v apt-get >/dev/null && apt-get install -y -qq certbot >/dev/null; } ||
      { command -v dnf >/dev/null && dnf install -y -q certbot >/dev/null; } ||
      { command -v yum >/dev/null && yum install -y -q certbot >/dev/null; } ||
      { command -v apk >/dev/null && apk add -q certbot >/dev/null; } || true
    fi
    if command -v certbot >/dev/null 2>&1; then
      EMAIL_ARG="--register-unsafely-without-email"; [ -n "$EMAIL" ] && EMAIL_ARG="-m $EMAIL"
      if certbot certonly --standalone -n --agree-tos $EMAIL_ARG -d "$DOMAIN" \
           --pre-hook "systemctl stop $SERVICE || true" --post-hook "systemctl start $SERVICE || true" >/dev/null 2>&1; then
        CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"; KEY="/etc/letsencrypt/live/$DOMAIN/privkey.pem"
        ok "Let's Encrypt certificate issued for $DOMAIN (auto-renews)"
      else
        warn "Let's Encrypt failed (is the A record pointing here?) — falling back to self-signed"
      fi
    fi
  fi
  if [ -z "$CERT" ]; then
    mkdir -p "$DATA_DIR/tls"
    CERT="$DATA_DIR/tls/fullchain.pem"; KEY="$DATA_DIR/tls/privkey.pem"
    if [ ! -f "$CERT" ]; then
      openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -keyout "$KEY" -out "$CERT" \
        -subj "/CN=${DOMAIN:-gozar}" >/dev/null 2>&1
      chmod 600 "$KEY"
    fi
    ok "self-signed certificate (fine behind Cloudflare 'Full' mode)"
  fi
fi

# ------------------------------------------------------------------- service
step "Configuring systemd service"
EXEC="$PY $APP_DIR/relay.py serve --host $LISTEN --port $PORT --ssl-port $SSL_PORT"
[ -n "$CERT" ] && EXEC="$EXEC --cert $CERT --key $KEY"
cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=Gozar universal API relay
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=GOZAR_DATA_DIR=${DATA_DIR}
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=${APP_DIR}
ExecStart=${EXEC}
Restart=always
RestartSec=2
LimitNOFILE=65535
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

cat > "$BIN" <<EOF
#!/usr/bin/env bash
# Gozar management helper
export GOZAR_DATA_DIR="${DATA_DIR}"
case "\${1:-}" in
  status)    systemctl status ${SERVICE} --no-pager ;;
  restart)   systemctl restart ${SERVICE} && echo "restarted" ;;
  stop)      systemctl stop ${SERVICE} ;;
  start)     systemctl start ${SERVICE} ;;
  logs)      journalctl -u ${SERVICE} -f -n 100 ;;
  update)    bash <(curl -fsSL https://raw.githubusercontent.com/${REPO}/${BRANCH}/install.sh) --yes --port ${PORT} --ssl-port ${SSL_PORT} --listen ${LISTEN} --app-dir ${APP_DIR} ${DOMAIN:+--domain $DOMAIN} ;;
  uninstall) bash <(curl -fsSL https://raw.githubusercontent.com/${REPO}/${BRANCH}/install.sh) uninstall ;;
  ""|-h|--help)
    echo "usage: gozar {status|restart|start|stop|logs|update|uninstall|info|reset-password|key ...}" ;;
  *)         exec ${PY} ${APP_DIR}/relay.py "\$@" ;;
esac
EOF
chmod 755 "$BIN"

export GOZAR_DATA_DIR="$DATA_DIR"
SCHEME=https; HPORT=$SSL_PORT; [ "$SSL_PORT" -gt 0 ] || { SCHEME=http; HPORT=$PORT; }
HOST="${DOMAIN:-$SERVER_IP}"
URL="${SCHEME}://${HOST}"
{ [ "$SCHEME" = https ] && [ "$HPORT" -eq 443 ]; } || { [ "$SCHEME" = http ] && [ "$HPORT" -eq 80 ]; } || URL="${URL}:${HPORT}"

if [ -n "$RESTORE" ]; then
  [ -f "$RESTORE" ] || die "Backup file not found: $RESTORE"
  "$PY" "$APP_DIR/relay.py" restore "$RESTORE" || die "Restore failed"
  ok "restored data from $RESTORE"
fi
INIT_JSON="$("$PY" "$APP_DIR/relay.py" init --json --public-url "$URL" 2>/dev/null || true)"
ADMIN_USER="$(echo "$INIT_JSON" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("username") or "admin")' 2>/dev/null || echo admin)"
ADMIN_PASS="$(echo "$INIT_JSON" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("password") or "")' 2>/dev/null || true)"
FIRST_KEY="$(echo "$INIT_JSON" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("key") or "")' 2>/dev/null || true)"
rm -f "$APP_DIR/config.json"

# Firewall (nothing to open when only listening on localhost behind a local web server)
for p in $PORT $SSL_PORT; do
  [ "$p" -gt 0 ] || continue
  case "$LISTEN" in 127.*|localhost|::1) continue ;; esac
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then ufw allow "$p/tcp" >/dev/null 2>&1 || true
  elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then firewall-cmd -q --permanent --add-port="$p/tcp" || true; fi
done
command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld && firewall-cmd -q --reload || true

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1
systemctl restart "$SERVICE"
sleep 1.5
systemctl is-active --quiet "$SERVICE" || { journalctl -u "$SERVICE" -n 30 --no-pager; die "Service failed to start"; }
ok "service '${SERVICE}' is running"

# ------------------------------------------------------------------- summary
echo -e "\n${G}${W}════════════════════════════════════════════════════════════════${N}"
echo -e "${G}${W}  Gozar v${VERSION} is installed and running${N}"
echo -e "${G}${W}════════════════════════════════════════════════════════════════${N}\n"
echo -e "${W}Admin panel${N}"
echo -e "${C}${URL}/${N}\n"
if [ -n "$ADMIN_PASS" ]; then
  echo -e "${W}Username${N}"; echo -e "${Y}${ADMIN_USER}${N}"
  echo -e "${W}Password${N}"; echo -e "${Y}${ADMIN_PASS}${N}\n"
else
  echo -e "${W}Login${N}  existing credentials were kept  ${D}(reset: gozar reset-password)${N}\n"
fi
if [ -n "$FIRST_KEY" ]; then
  echo -e "${W}Access key${N}"; echo -e "${C}${FIRST_KEY}${N}\n"
  echo -e "${W}Examples${N}"
  echo -e "  Telegram   ${C}${URL}/${FIRST_KEY}/telegram/bot<TOKEN>/getMe${N}"
  echo -e "  OpenRouter ${C}${URL}/${FIRST_KEY}/openrouter/api/v1${N}"
  echo -e "  Gemini     ${C}${URL}/${FIRST_KEY}/gemini/v1beta${N}\n"
fi
echo -e "${W}Manage${N}  gozar status | logs | restart | update | info | reset-password | uninstall"
echo -e "${D}Database: ${DATA_DIR}/gozar.db${N}\n"
