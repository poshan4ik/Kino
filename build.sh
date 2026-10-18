#!/usr/bin/env bash
# Сборка для продакшена (Render/Railway/локально).
set -euo pipefail

python -m pip install --upgrade pip
pip install -r requirements.txt

python manage.py check --deploy --fail-level ERROR
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py ensure_admin || true
python manage.py seed_demo || true
