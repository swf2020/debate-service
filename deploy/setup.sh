#!/bin/bash
set -e

# ============================================================
# One-time ECS setup script for debate-service
# Run as root on Alibaba Cloud ECS (CentOS/Alibaba Linux)
# ============================================================

APP_DIR="/opt/debate-service"
REPO="https://github.com/swf2020/debate-service.git"

echo "=== Installing system packages ==="
yum install -y python3 python3-pip git nginx redis

echo "=== Enabling and starting Redis ==="
systemctl enable redis
systemctl start redis

echo "=== Cloning repo ==="
if [ -d "$APP_DIR" ]; then
    echo "Directory $APP_DIR exists, skipping clone."
else
    git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR"

echo "=== Setting up Python venv ==="
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Create env file ==="
if [ ! -f /etc/default/debate-env ]; then
    cat > /etc/default/debate-env << 'EOF'
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
ADMIN_USERS=admin
DEBATE_DB_PATH=/opt/debate-service/debate.db
JWT_SECRET_KEY=change-me-to-a-random-secret
REDIS_URL=redis://localhost:6379/0
EOF
    chmod 600 /etc/default/debate-env
    echo "Created /etc/default/debate-env — edit with real key:"
    echo "  sudo vim /etc/default/debate-env"
else
    echo "/etc/default/debate-env already exists, skipping."
fi

echo "=== Installing systemd units ==="
cp deploy/debate.service /etc/systemd/system/
cp deploy/debate-deploy.service /etc/systemd/system/
cp deploy/debate-deploy.timer /etc/systemd/system/
chmod +x deploy/deploy.sh
systemctl daemon-reload

echo "=== Enabling services ==="
systemctl enable debate.service
systemctl enable --now debate-deploy.timer

echo "=== Starting debate service ==="
systemctl start debate.service

echo ""
echo "=== Setup complete ==="
echo "Check status:"
echo "  systemctl status debate.service"
echo "  systemctl status debate-deploy.timer"
echo "  journalctl -u debate.service -f"
echo "  journalctl -u debate-deploy.service -f"
