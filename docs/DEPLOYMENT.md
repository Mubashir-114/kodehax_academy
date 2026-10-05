# Deployment

This document summarizes the current deployment assumptions for Kodehax Academy.

## Platform

The project is designed for deployment on Render using Python, MySQL, and Gunicorn.

## Runtime configuration

- Render runtime target: Python 3.12.12
- Dependencies are installed from `requirements.txt`.
- Frontend assets are compiled via `npm ci --include=dev` and `npm run tailwind`.
- Static files are collected during the build or deploy pipeline with `build.sh`.

## Key commands

```bash
bash build.sh
python manage.py collectstatic --noinput
gunicorn kodehax_academy.wsgi --bind 0.0.0.0:$PORT
```

## Health check

The platform exposes `/health/` for liveness checks. This is intended for deployment monitoring and should remain lightweight.

## Database and storage

Production uses MySQL and private S3-compatible media storage via Backblaze B2. Signed/private media URLs are used where appropriate, and the app checks for required storage configuration before enabling production media behavior. The app also supports TLS configuration via environment variables when the provider requires it.

## Files to review

- `.env.example`
- `build.sh`
- `kodehax_academy/settings.py`
- `manage.py`
