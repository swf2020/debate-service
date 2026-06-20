#!/bin/bash
set -e

APP_DIR="/opt/debate-service"
BRANCH="master"

cd "$APP_DIR"

# Fetch latest from remote
git fetch origin "$BRANCH"

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$(date)] No new commits."
    exit 0
fi

echo "[$(date)] New commits detected. Deploying..."

# Pull and install deps
git pull origin "$BRANCH"
source .venv/bin/activate
pip install -r requirements.txt --quiet

# Restart service
systemctl restart debate.service

# Health check
sleep 3
if curl -sf http://localhost:8080/api/debate/active > /dev/null 2>&1; then
    echo "[$(date)] Deploy OK — service healthy."
else
    echo "[$(date)] WARNING: service may have failed to start. Check: journalctl -u debate.service -n 20"
fi
