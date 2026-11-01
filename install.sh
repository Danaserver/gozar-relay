#!/usr/bin/env bash
# ==============================================================================
# Telegram Bot API Relay & Admin Panel - Auto Installer
# Supports: Ubuntu, Debian, CentOS, AlmaLinux, RockyLinux, Fedora, Alpine, Arch
# Works on fresh/raw servers or alongside existing web servers (Nginx/Apache).
# ==============================================================================

set -e

# Default GitHub Repo (Override via: GITHUB_REPO="user/repo" bash install.sh)
GITHUB_REPO="${GITHUB_REPO:-"Danaserver/telegram-relay"}"
GITHUB_BRANCH="${GITHUB_BRANCH:-"main"}"
RAW_BASE="https://raw.githubusercontent.com/${GITHUB_REPO}/${GITHUB_BRANCH}"

# Parse optional arguments: bash install.sh [PORT] [SSL_PORT] [DOMAIN]
CLI_PORT="$1"
CLI_SSL_PORT="$2"
CLI_DOMAIN="$3"

PORT="${CLI_PORT:-${PORT:-""}}"
SSL_PORT="${CLI_SSL_PORT:-${SSL_PORT:-""}}"
DOMAIN="${CLI_DOMAIN:-${DOMAIN:-""}}"

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
echo "    Telegram Bot API Relay & Admin Panel - Auto Installer       "
echo "================================================================"
echo -e "${NC}"

# 1. Check Root Privileges
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[!] Error: Please run this installer with root privileges:${NC}"
    echo "    sudo bash $0"
    exit 1
fi

# 2. Detect OS & Install Python 3 and dependencies
echo -e "${BLUE}[*] Detecting operating system and installing dependencies (Python 3, curl, openssl)...${NC}"

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
    echo -e "${YELLOW}[!] Warning: Unknown OS distribution, attempting to use existing Python...${NC}"
fi

# Verify Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] Python 3 installation failed. Please install Python 3 manually.${NC}"
    exit 1
fi

PYTHON_BIN=$(command -v python3)
PYTHON_VER=$($PYTHON_BIN --version 2>&1)
echo -e "${GREEN}[✓] Python is ready: ${PYTHON_VER}${NC}"

# 3. Setup Installation Directory & Server IP
SERVER_IP=$(curl -s4 --max-time 3 https://api.ipify.org || curl -s4 --max-time 3 https://ifconfig.me || hostname -I | awk '{print $1}')
INSTALL_DIR="/opt/telegram-relay"
echo -e "${BLUE}[*] Preparing installation directory at ${INSTALL_DIR}...${NC}"
mkdir -p "$INSTALL_DIR"

# Temporarily stop existing telegram-relay service to accurately detect third-party port conflicts
systemctl stop telegram-relay 2>/dev/null || true

# 4. Port Conflict Detection & Custom Ports Configuration
check_port_in_use() {
    local p=$1
    if [ -z "$p" ] || [ "$p" -le 0 ] 2>/dev/null; then
        return 1
    fi
    $PYTHON_BIN -c "import socket, sys
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('0.0.0.0', int(sys.argv[1])))
    s.close()
    sys.exit(1)
except Exception:
    sys.exit(0)
" "$p" 2>/dev/null
}

get_port_process() {
    local p=$1
    if command -v ss >/dev/null 2>&1; then
        ss -tlpn "sport = :$p" 2>/dev/null | grep -o 'users:(("[^"]*"' | head -n1 | sed -e 's/users:(("//' -e 's/"//'
    elif command -v lsof >/dev/null 2>&1; then
        lsof -i :"$p" -sTCP:LISTEN -F c 2>/dev/null | grep '^c' | head -n1 | sed 's/^c//'
    else
        echo ""
    fi
}

PORT_80_BUSY=0
PROC_80=""
if check_port_in_use 80; then
    PORT_80_BUSY=1
    PROC_80=$(get_port_process 80)
    [ -z "$PROC_80" ] && PROC_80="existing service"
fi

PORT_443_BUSY=0
PROC_443=""
if check_port_in_use 443; then
    PORT_443_BUSY=1
    PROC_443=$(get_port_process 443)
    [ -z "$PROC_443" ] && PROC_443="existing service"
fi

# Interactive Port Configuration (if not passed via ENV or CLI arguments)
if [ -z "$PORT" ] || [ -z "$SSL_PORT" ]; then
    if [ -e /dev/tty ]; then
        echo -e "\n${YELLOW}----------------------------------------------------------------${NC}"
        echo -e "${BOLD}[ Port Configuration ]${NC}"
        echo -e "You can assign custom ports if another web server (Nginx/Apache/etc.) is running."
        echo -e "Tip: Entering 0 disables that protocol completely."
        echo -e "${YELLOW}----------------------------------------------------------------${NC}"

        # HTTP Port Prompt
        if [ -z "$PORT" ]; then
            if [ "$PORT_80_BUSY" -eq 1 ]; then
                echo -e "${RED}[!] Notice: Port 80 is currently in use by (${PROC_80}).${NC}"
                DEFAULT_HTTP=8080
            else
                DEFAULT_HTTP=80
            fi
            read -r -p "HTTP Port [Default: ${DEFAULT_HTTP}]: " INPUT_PORT </dev/tty || true
            PORT="${INPUT_PORT:-$DEFAULT_HTTP}"
        fi

        # SSL Port Prompt
        if [ -z "$SSL_PORT" ]; then
            if [ "$PORT_443_BUSY" -eq 1 ]; then
                echo -e "${RED}[!] Notice: Port 443 is currently in use by (${PROC_443}).${NC}"
                DEFAULT_SSL=8443
            else
                DEFAULT_SSL=443
            fi
            echo -e "Cloudflare HTTPS supported ports: ${CYAN}443, 8443, 2053, 2083, 2087, 2096${NC}"
            read -r -p "HTTPS / SSL Port [Default: ${DEFAULT_SSL}]: " INPUT_SSL_PORT </dev/tty || true
            SSL_PORT="${INPUT_SSL_PORT:-$DEFAULT_SSL}"
        fi
        echo -e "${YELLOW}----------------------------------------------------------------${NC}\n"
    else
        # Non-interactive fallback
        if [ -z "$PORT" ]; then
            [ "$PORT_80_BUSY" -eq 1 ] && PORT=8080 || PORT=80
        fi
        if [ -z "$SSL_PORT" ]; then
            [ "$PORT_443_BUSY" -eq 1 ] && SSL_PORT=8443 || SSL_PORT=443
        fi
    fi
fi

# Ensure integer values
PORT=$((PORT + 0))
SSL_PORT=$((SSL_PORT + 0))

if [ "$PORT" -le 0 ] && [ "$SSL_PORT" -le 0 ]; then
    echo -e "${RED}[ERROR] At least one port (HTTP or HTTPS) must be enabled (greater than 0).${NC}"
    exit 1
fi

echo -e "${GREEN}[✓] HTTP Port:${NC}  $([ "$PORT" -gt 0 ] && echo "$PORT" || echo "Disabled (0)")"
echo -e "${GREEN}[✓] HTTPS Port:${NC} $([ "$SSL_PORT" -gt 0 ] && echo "$SSL_PORT" || echo "Disabled (0)")"

# 5. Domain / Subdomain Setup (Interactive Prompt)
if [ -z "$DOMAIN" ]; then
    if [ -e /dev/tty ]; then
        echo -e "\n${YELLOW}----------------------------------------------------------------${NC}"
        echo -e "${BOLD}[ Domain / Subdomain Setup (Optional) ]${NC}"
        echo -e "If you pointed a domain or subdomain (e.g. ${CYAN}relay.yourdomain.com${NC}) to"
        echo -e "this server's IP (${GREEN}${SERVER_IP}${NC}), enter it below."
        echo -e "Otherwise, press ${BOLD}Enter${NC} to use the server IP address directly."
        read -r -p "Domain or Subdomain (Leave blank for IP): " INPUT_DOMAIN </dev/tty || true
        DOMAIN=$(echo "$INPUT_DOMAIN" | tr -d ' ' | sed -e 's/^https\?:\/\///' -e 's/\/.*$//')
        echo -e "${YELLOW}----------------------------------------------------------------${NC}\n"
    fi
fi

SSL_CN="telegram-relay"
if [ -n "$DOMAIN" ]; then
    SSL_CN="$DOMAIN"
    echo -e "${GREEN}[✓] Domain selected: ${DOMAIN}${NC}"
else
    echo -e "${BLUE}[*] Using server IP address: ${SERVER_IP}${NC}"
fi

# 6. Obtain relay.py (Local > GitHub Raw)
CURRENT_SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
TARGET_RELAY="$INSTALL_DIR/relay.py"

if [ -f "./relay.py" ] && [ "$(pwd)/relay.py" != "$TARGET_RELAY" ]; then
    cp -f ./relay.py "$TARGET_RELAY"
elif [ -n "$CURRENT_SCRIPT_DIR" ] && [ -f "$CURRENT_SCRIPT_DIR/relay.py" ] && [ "$CURRENT_SCRIPT_DIR/relay.py" != "$TARGET_RELAY" ]; then
    cp -f "$CURRENT_SCRIPT_DIR/relay.py" "$TARGET_RELAY"
elif [ ! -f "$TARGET_RELAY" ]; then
    echo -e "${BLUE}[*] Downloading latest relay.py...${NC}"
    curl -sSL "${RAW_BASE}/relay.py" -o "$TARGET_RELAY" || {
        echo -e "${RED}[ERROR] Failed to download relay.py.${NC}"
        exit 1
    }
fi

chmod +x "$TARGET_RELAY"

# 7. Initialize Config with Random Password & Keys if not exists
CONFIG_FILE="$INSTALL_DIR/config.json"
ADMIN_USER="admin"

# Generate random secure admin password if not explicitly supplied
if [ -z "$ADMIN_PASS" ]; then
    ADMIN_PASS=$($PYTHON_BIN -c "import secrets; print(secrets.token_urlsafe(12))")
fi

# Generate random bot key (e.g. key_a1b2c3d4e5f6)
DEFAULT_BOT_KEY="key_$($PYTHON_BIN -c "import secrets; print(secrets.token_hex(6))")"

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${BLUE}[*] Generating initial configuration and credentials...${NC}"
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
    echo -e "${GREEN}[✓] Configuration generated successfully.${NC}"
else
    echo -e "${YELLOW}[i] Preserving existing configuration file: ${CONFIG_FILE}${NC}"
fi

# 8. Configure Systemd Service
SERVICE_FILE="/etc/systemd/system/telegram-relay.service"
echo -e "${BLUE}[*] Configuring systemd service...${NC}"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Telegram Bot API Relay & Admin Panel Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${PYTHON_BIN} ${INSTALL_DIR}/relay.py --host 0.0.0.0 --port ${PORT} --ssl-port ${SSL_PORT}
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# 9. SSL Certificate & Firewall Configuration
if [ "$SSL_PORT" -gt 0 ]; then
    if [ ! -f "$INSTALL_DIR/server.crt" ]; then
        echo -e "${BLUE}[*] Generating self-signed SSL certificate for ${SSL_CN} on port ${SSL_PORT}...${NC}"
        openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
          -keyout "$INSTALL_DIR/server.key" \
          -out "$INSTALL_DIR/server.crt" \
          -subj "/CN=${SSL_CN}" >/dev/null 2>&1 || true
        chmod 600 "$INSTALL_DIR/server.key" "$INSTALL_DIR/server.crt" 2>/dev/null || true
    fi
fi

# Firewall ports
ALLOW_PORTS=()
[ "$PORT" -gt 0 ] && ALLOW_PORTS+=("$PORT")
[ "$SSL_PORT" -gt 0 ] && ALLOW_PORTS+=("$SSL_PORT")

for p in "${ALLOW_PORTS[@]}"; do
    if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
        echo -e "${BLUE}[*] Allowing port ${p} in UFW firewall...${NC}"
        ufw allow "${p}/tcp" >/dev/null 2>&1 || true
    elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
        echo -e "${BLUE}[*] Allowing port ${p} in firewalld...${NC}"
        firewall-cmd --add-port="${p}/tcp" --permanent >/dev/null 2>&1 || true
    fi
done
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
    firewall-cmd --reload >/dev/null 2>&1 || true
fi

# 10. Start & Enable Service
systemctl daemon-reload
systemctl enable telegram-relay >/dev/null 2>&1
systemctl restart telegram-relay

sleep 1

# Check if running
if systemctl is-active --quiet telegram-relay; then
    echo -e "${GREEN}[✓] Service successfully started and active!${NC}"
else
    echo -e "${RED}[ERROR] Service failed to start. Journal log:${NC}"
    journalctl -u telegram-relay -n 20 --no-pager
    exit 1
fi

# 11. URL Formatting Helper
format_url() {
    local scheme=$1
    local host=$2
    local port=$3
    if [ -z "$port" ] || [ "$port" -le 0 ] 2>/dev/null; then
        echo ""
    elif [ "$scheme" = "http" ] && [ "$port" -eq 80 ]; then
        echo "http://${host}"
    elif [ "$scheme" = "https" ] && [ "$port" -eq 443 ]; then
        echo "https://${host}"
    else
        echo "${scheme}://${host}:${port}"
    fi
}

TARGET_HOST="${DOMAIN:-$SERVER_IP}"
PRIMARY_URL=""
if [ "$SSL_PORT" -gt 0 ]; then
    PRIMARY_URL=$(format_url "https" "$TARGET_HOST" "$SSL_PORT")
elif [ "$PORT" -gt 0 ]; then
    PRIMARY_URL=$(format_url "http" "$TARGET_HOST" "$PORT")
fi

IP_HTTP=$(format_url "http" "$SERVER_IP" "$PORT")
IP_HTTPS=$(format_url "https" "$SERVER_IP" "$SSL_PORT")

# 12. Final Clean Summary (Each detail on its own line for easy double-click copying)
echo -e "\n${GREEN}${BOLD}================================================================${NC}"
echo -e "${GREEN}${BOLD}   Telegram Bot API Relay & Admin Panel - Installed Successfully!${NC}"
echo -e "${GREEN}${BOLD}================================================================${NC}"
echo -e ""
echo -e "${BOLD}[ Web Panel URL ]${NC}"
echo -e "${CYAN}${PRIMARY_URL}/${NC}"
echo -e ""

if [ -n "$DOMAIN" ]; then
    if [ -n "$IP_HTTPS" ]; then
        echo -e "${BOLD}[ Direct IP Access (SSL) ]${NC}"
        echo -e "${CYAN}${IP_HTTPS}/${NC}"
        echo -e ""
    fi
    if [ -n "$IP_HTTP" ]; then
        echo -e "${BOLD}[ Direct IP Access (HTTP) ]${NC}"
        echo -e "${CYAN}${IP_HTTP}/${NC}"
        echo -e ""
    fi
else
    if [ -n "$IP_HTTPS" ] && [ "$SSL_PORT" -gt 0 ]; then
        echo -e "${BOLD}[ Direct IP Access (SSL) ]${NC}"
        echo -e "${CYAN}${IP_HTTPS}/${NC}"
        echo -e ""
    fi
fi

echo -e "${BOLD}[ Admin Login Credentials ]${NC}"
echo -e "Username:"
echo -e "${YELLOW}${ADMIN_USER}${NC}"
echo -e "Password:"
echo -e "${YELLOW}${ADMIN_PASS}${NC}"
echo -e ""

echo -e "${BOLD}[ Default Bot Access Key ]${NC}"
echo -e "${CYAN}${DEFAULT_BOT_KEY}${NC}"
echo -e ""

echo -e "${BOLD}[ Telegram Bot API Base URL (for scripts in Iran) ]${NC}"
echo -e "${CYAN}${PRIMARY_URL}/${DEFAULT_BOT_KEY}/bot<TOKEN>${NC}"
echo -e ""

if [ "$PORT_80_BUSY" -eq 1 ] || [ "$PORT_443_BUSY" -eq 1 ]; then
echo -e "----------------------------------------------------------------"
echo -e "${BOLD}[ Nginx Reverse Proxy Example (Optional) ]${NC}"
echo -e "server {"
echo -e "    listen 80;"
echo -e "    server_name ${DOMAIN:-"relay.yourdomain.com"};"
echo -e "    location / {"
echo -e "        proxy_pass http://127.0.0.1:$([ "$PORT" -gt 0 ] && echo "$PORT" || echo "8080");"
echo -e "        proxy_set_header Host \$host;"
echo -e "        proxy_set_header X-Real-IP \$remote_addr;"
echo -e "        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;"
echo -e "        proxy_set_header X-Forwarded-Proto \$scheme;"
echo -e "    }"
echo -e "}"
echo -e "----------------------------------------------------------------"
echo -e ""
fi

echo -e "${BOLD}[ Service Management Commands ]${NC}"
echo -e "Check Status: systemctl status telegram-relay"
echo -e "Restart:      systemctl restart telegram-relay"
echo -e "Stop:         systemctl stop telegram-relay"
echo -e "Live Logs:    journalctl -u telegram-relay -f"
echo -e "${GREEN}${BOLD}================================================================${NC}\n"
