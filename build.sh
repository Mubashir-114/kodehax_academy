#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r requirements.txt
node --version
npm --version
npm ci --include=dev
npm run tailwind
python manage.py collectstatic --noinput
