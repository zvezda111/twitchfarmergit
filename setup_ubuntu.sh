#!/usr/bin/env bash
# Установка Twitch Farmer на Ubuntu/Debian сервер (headless).
# Запуск:  bash setup_ubuntu.sh
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo "==> venv"
if [ ! -d venv ]; then
    "$PY" -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

echo "==> python зависимости"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> браузер для клейма веб-токенов (patchright/chromium) + системные зависимости"
# ставит apt-пакеты (libnss3, libatk, libgbm, libasound2 и т.д.)
if command -v sudo >/dev/null 2>&1; then
    sudo "$(which patchright)" install-deps || python -m patchright install-deps || true
else
    patchright install-deps || python -m patchright install-deps || true
fi
# сам браузер (Google Chrome-канал)
patchright install chrome || patchright install chromium || python -m patchright install chromium

echo "==> (опционально) Xvfb — виртуальный дисплей, если headless капризничает"
if command -v sudo >/dev/null 2>&1; then
    sudo apt-get install -y xvfb || true
fi

cat <<'EOF'

Готово.

Запуск:
    source venv/bin/activate
    python main.py

Если хочешь запускать браузер под виртуальным дисплеем (надёжнее для Kasada):
    xvfb-run -a python main.py

Переменные окружения (необязательно):
    BROWSER_CLAIM_CONCURRENCY=3   # сколько браузеров клеймят одновременно
    BROWSER_HEADLESS=true         # false — с окном (только с дисплеем/Xvfb)
    BROWSER_CHANNEL=chrome        # пусто -> bundled chromium
    CAMPAIGN_REFRESH_SECONDS=7200 # период обновления каталога кампаний

EOF
