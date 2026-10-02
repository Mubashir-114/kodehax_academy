#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r requirements.txt
node --version
npm --version
npm ci --include=dev
npm run tailwind
# Render secret files are runtime-only; collectstatic does not access the database.
DB_SSL_CA="" python manage.py collectstatic --noinput
