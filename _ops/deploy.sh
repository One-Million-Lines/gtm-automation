#!/usr/bin/env bash
# Production deployment script for GTM Automation.
# Assumes:
#   - Repo cloned at /opt/gtm-automation
#   - Python 3.13 installed
#   - Node 20+ installed
#   - nginx + systemd available
#   - /opt/gtm-automation/backend/.env populated (see backend/.env.example)
set -euo pipefail

ROOT="${ROOT:-/opt/gtm-automation}"
WEBROOT="${WEBROOT:-/var/www/gtm-automation/dist}"
SERVICE="${SERVICE:-gtm-api.service}"
BRANCH="${BRANCH:-main}"

echo "[deploy] pulling latest from $BRANCH"
cd "$ROOT"
git fetch --all --prune
git checkout "$BRANCH"
git pull --ff-only

echo "[deploy] backend deps"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
    python3.13 -m venv .venv
fi
. .venv/bin/activate
pip install -r pip_requirements.txt
python setup_database.py
deactivate

echo "[deploy] frontend build"
cd "$ROOT/frontend"
npm ci
VITE_API_BASE="${VITE_API_BASE:-/api}" npm run build

echo "[deploy] publishing frontend → $WEBROOT"
sudo mkdir -p "$WEBROOT"
sudo rsync -a --delete dist/ "$WEBROOT/"

echo "[deploy] restarting service"
sudo systemctl restart "$SERVICE"
sudo systemctl reload nginx || true

echo "[deploy] OK"
