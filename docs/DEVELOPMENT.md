# Development

This document captures the practical local setup and validation workflow for the project.

## Local environment

```bash
git clone https://github.com/Mubashir-114/kodehax_academy.git
cd kodehax_academy
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
npm ci
cp .env.example .env
```

## Build and run

```bash
python manage.py migrate
npm run tailwind:build
python manage.py runserver
```

## Tests

Use the repo’s SQLite test configuration for the lightweight validation path:

```bash
python manage.py test --settings=kodehax_academy.test_settings
```

## Operational notes

- Keep `.env` local and private.
- Do not use the system Python for repo validation if the project’s virtual environment is the intended environment.
- Use the production configuration only for actual deployment contexts; keep local development isolated.
- Production media storage uses a private S3-compatible backend with Backblaze B2 and signed/private URLs where appropriate.
- Brevo is the current transactional email provider through the HTTPS API path.
