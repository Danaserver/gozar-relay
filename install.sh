#!/usr/bin/env bash
# ==============================================================================
# Telegram Bot API Relay & Admin Panel - One-Command Auto Installer
# Supports: Ubuntu, Debian, CentOS, AlmaLinux, RockyLinux, Fedora, Alpine
# Works on fresh/raw servers without Python pre-installed.
# ==============================================================================

set -e

# Default GitHub Repo (User can override via: GITHUB_REPO="user/repo" bash install.sh)
GITHUB_REPO="${GITHUB_REPO:-"Danaserver/telegram-relay"}"
GITHUB_BRANCH="${GITHUB_BRANCH:-"main"}"
RAW_BASE="https://raw.githubusercontent.com/${GITHUB_REPO}/${GITHUB_BRANCH}"

# Terminal colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}"
echo "================================================================"
echo "   ⚡ Telegram Bot API Relay & Admin Panel - Auto Installer   "
echo "        نصب خودکار رله تلگرام و پنل مدیریت روی سرور خام       "
echo "================================================================"
echo -e "${NC}"

# 1. Check Root Privileges
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[!] لطفا این اسکریپت را با دسترسی روت (root) اجرا کنید:${NC}"
    echo "    sudo bash $0"
    exit 1
fi

# 2. Port Configuration
PORT=${PORT:-80}
if [ -n "$1" ]; then
    PORT=$1
fi

# 3. Detect OS & Install Python 3 and dependencies
echo -e "${BLUE}[*] در حال شناسایی سیستم‌عامل و نصب پیش‌نیازها (Python 3, curl, openssl)...${NC}"

if [ -f /etc/debian_version ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y -q
    apt-get install -y -q python3 python3-pip curl openssl
elif [ -f /etc/redhat-release ] || [ -f /etc/almalinux-release ] || [ -f /etc/rocky-release ]; then
    if command -v dnf >/dev/null 2>&1; then
        dnf install -y python3 curl openssl
    else
        yum install -y python3 curl openssl
    fi
elif [ -f /etc/alpine-release ]; then
    apk update
    apk add python3 curl openssl bash
elif [ -f /etc/arch-release ]; then
    pacman -Sy --noconfirm python curl openssl
else
    echo -e "${YELLOW}[!] سیستم‌عامل شناسایی نشد، تلاش برای استفاده از پایتون موجود...${NC}"
fi

# Verify Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] نصب پایتون ۳ با خطا مواجه شد. لطفاً ابتدا پایتون را به صورت دستی نصب کنید.${NC}"
    exit 1
fi

PYTHON_BIN=$(command -v python3)
PYTHON_VER=$($PYTHON_BIN --version 2>&1)
echo -e "${GREEN}[✓] پایتون آماده است: ${PYTHON_VER}${NC}"

# 4. Setup Installation Directory
INSTALL_DIR="/opt/telegram-relay"
echo -e "${BLUE}[*] در حال آماده‌سازی دایرکتوری نصب در ${INSTALL_DIR}...${NC}"
mkdir -p "$INSTALL_DIR"

# 5. Obtain relay.py (Local > GitHub Raw > Mirror)
if [ -f "./relay.py" ]; then
    cp ./relay.py "$INSTALL_DIR/relay.py"
elif [ -f "$(dirname "$0")/relay.py" ]; then
    cp "$(dirname "$0")/relay.py" "$INSTALL_DIR/relay.py"
else
    echo -e "${BLUE}[*] در حال دریافت آخرین نسخه relay.py...${NC}"
    curl -sSL "${RAW_BASE}/relay.py" -o "$INSTALL_DIR/relay.py" || \
    curl -sSL "https://robot.telo.ir/Relay/relay.py" -o "$INSTALL_DIR/relay.py" || {
        echo -e "${RED}[ERROR] دریافت فایل relay.py ناموفق بود.${NC}"
        exit 1
    }
fi

chmod +x "$INSTALL_DIR/relay.py"

# 6. Initialize Config if not exists
CONFIG_FILE="$INSTALL_DIR/config.json"
ADMIN_USER="admin"
ADMIN_PASS=${ADMIN_PASS:-"Admin@Telo2026"}
DEFAULT_BOT_KEY="telo_sec_$(openssl rand -hex 3)"

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${BLUE}[*] در حال تولید رمز عبور و پیکربندی اولیه...${NC}"
    $PYTHON_BIN -c "
import hashlib, secrets, json, time

salt = secrets.token_hex(16)
pw = '${ADMIN_PASS}'.encode('utf-8')
hashed = hashlib.pbkdf2_hmac('sha256', pw, salt.encode('utf-8'), 100000).hex()
jwt_key = secrets.token_hex(32)

cfg = {
    'enabled': True,
    'admin': {
        'username': '${ADMIN_USER}',
        'password_hash': f'{salt}:{hashed}'
    },
    'secret_jwt_key': jwt_key,
    'bot_keys': [
        {
            'id': 'key_default',
            'name': 'Default Bot',
            'key': '${DEFAULT_BOT_KEY}',
            'enabled': True,
            'created_at': time.strftime('%Y-%m-%d %H:%M')
        }
    ]
}

with open('${CONFIG_FILE}', 'w', encoding='utf-8') as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
"
    chmod 600 "$CONFIG_FILE"
    echo -e "${GREEN}[✓] تنظیمات با موفقیت ذخیره شد.${NC}"
else
    echo -e "${YELLOW}[i] فایل تنظیمات موجود حفظ شد: ${CONFIG_FILE}${NC}"
fi

# 7. Configure Systemd Service
SERVICE_FILE="/etc/systemd/system/telegram-relay.service"
echo -e "${BLUE}[*] در حال پیکربندی سرویس خودکار systemd روی پورت ${PORT}...${NC}"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Telegram Bot API Relay & Admin Panel Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${PYTHON_BIN} ${INSTALL_DIR}/relay.py --host 0.0.0.0 --port ${PORT}
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# 8. Firewall Configuration
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    echo -e "${BLUE}[*] باز کردن پورت ${PORT} در فایروال UFW...${NC}"
    ufw allow ${PORT}/tcp >/dev/null 2>&1 || true
elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
    echo -e "${BLUE}[*] باز کردن پورت ${PORT} در فایروal firewalld...${NC}"
    firewall-cmd --add-port=${PORT}/tcp --permanent >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
fi

# 9. Start & Enable Service
systemctl daemon-reload
systemctl enable telegram-relay >/dev/null 2>&1
systemctl restart telegram-relay

sleep 1

# Check if running
if systemctl is-active --quiet telegram-relay; then
    echo -e "${GREEN}[✓] سرویس با موفقیت فعال و اجرا شد!${NC}"
else
    echo -e "${RED}[ERROR] سرویس اجرا نشد. بررسی لاگ:${NC}"
    journalctl -u telegram-relay -n 20 --no-pager
    exit 1
fi

# 10. Detect Server IP
SERVER_IP=$(curl -s4 --max-time 3 https://api.ipify.org || curl -s4 --max-time 3 https://ifconfig.me || hostname -I | awk '{print $1}')
SERVER_URL="http://${SERVER_IP}"
if [ "$PORT" != "80" ]; then
    SERVER_URL="http://${SERVER_IP}:${PORT}"
fi

# 11. Final Summary
echo -e "\n${GREEN}${BOLD}================================================================${NC}"
echo -e "${GREEN}${BOLD}      🎉 رله تلگرام با موفقیت روی سرور نصب و فعال شد!          ${NC}"
echo -e "${GREEN}${BOLD}================================================================${NC}"
echo -e ""
echo -e "  🌐 ${BOLD}آدرس پنل مدیریت:${NC}      ${CYAN}${SERVER_URL}/${NC}"
echo -e "  👤 ${BOLD}نام کاربری مدیر:${NC}      ${YELLOW}${ADMIN_USER}${NC}"
if [ -n "$ADMIN_PASS" ]; then
echo -e "  🔑 ${BOLD}رمز عبور مدیر:${NC}        ${YELLOW}${ADMIN_PASS}${NC}"
fi
echo -e "  🤖 ${BOLD}کد اختصاصی ربات:${NC}      ${CYAN}${DEFAULT_BOT_KEY}${NC}"
echo -e ""
echo -e "----------------------------------------------------------------"
echo -e "  🚀 ${BOLD}نحوه استفاده در کدهای ربات (روی سرور ایران):${NC}"
echo -e "     API_URL = \"${SERVER_URL}/${DEFAULT_BOT_KEY}/bot<TOKEN>\""
echo -e "----------------------------------------------------------------"
echo -e "  🛠 ${BOLD}دستورات مدیریت سرویس:${NC}"
echo -e "     بررسی وضعیت:  systemctl status telegram-relay"
echo -e "     ریستارت:      systemctl restart telegram-relay"
echo -e "     توقف:         systemctl stop telegram-relay"
echo -e "     لاگ زنده:     journalctl -u telegram-relay -f"
echo -e "================================================================\n"
