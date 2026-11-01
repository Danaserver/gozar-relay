#!/bin/bash
# این فایل رو داخل cPanel Cron Job هر ۵ دقیقه یه بار اجرا کن
# مثال: */5 * * * * /home/username/telegram-bot/run_bot.sh

BOT_DIR="/home/USERNAME/telegram-bot"   # <-- مسیر رو عوض کن
PID_FILE="$BOT_DIR/bot.pid"
LOG_FILE="$BOT_DIR/bot.log"
PYTHON="/usr/bin/python3"               # <-- مسیر پایتون cPanel ات

# چک کن ربات داره اجرا میشه یا نه
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "$(date): ربات داره اجرا میشه (PID: $PID)" >> "$LOG_FILE"
        exit 0
    fi
fi

# شروع ربات
echo "$(date): ربات شروع شد" >> "$LOG_FILE"
cd "$BOT_DIR"
nohup $PYTHON bot.py >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "$(date): PID ذخیره شد: $!" >> "$LOG_FILE"
