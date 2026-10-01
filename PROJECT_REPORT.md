# Kodehax Academy: Project and Render Deployment Report

**Inspection date:** 2026-10-01  
**Scope:** Native Python deployment configuration update; local credentials and database contents were not displayed.

Evidence labels used below:
- **Verified:** directly established by the checked-in source/configuration.
- **Inference/recommendation:** likely consequence or proposed deployment design; validate in the target Render workspace.
- **Unknown:** cannot be established from this repository snapshot.

## 1. Project Overview

Kodehax Academy is a single Django web application for coding education. Its intended users are students, teachers, and platform administrators. The implementation brings classroom, assignments, assessment, coding practice, and AI-assisted learning into one server-rendered application.

Verified implemented workflows include student registration and email verification; password login followed by an email OTP for non-admin users; invitation-based teacher creation; role-aware dashboards; class enrollment; file, quiz, and coding assignments; manual/AI grading; skill assessments; daily Python challenges; student chat and image analysis using Gemini; and admin management and maintenance mode. Relevant code is in `accounts/`, `users/`, `student/`, `teacher/`, `skill_assessment/`, `daily_challenges/`, and `adminpanel/`.

The README and semester summary describe these as finished product features, but that is not equivalent to end-to-end verification. Specific limitations found in the implementation:
- Public teacher registration is disabled; teachers enter through admin invitations (`accounts.views.teacher_register_disabled`, `teacher_invite_register`).
- Mobile templates exist, but `FORCE_DESKTOP_UI_ON_MOBILE` defaults to true in `kodehax_academy.mobile`; only an allowlist can select mobile alternatives by default. Mobile coverage is therefore partial, not uniformly enabled.
- Daily challenge generation has a management command, but no cron/worker is configured. Sets are also generated lazily when a student requests the challenge page.
- The `chat` app directory is an integration module rather than a configured Django app: `chat/models.py` is empty, `chat/urls.py` is empty, and the active chat routes are registered from `student` and the root URLconf.
- README claims about Cloudinary, CORS, Django REST Framework, JWT, and scheduled tasks are not reflected in active settings/code; see Technology Stack.

## Current runtime and deployment

Updated 2026-10-01: Django 5.2.5, PyMySQL 1.1.1, externally hosted MySQL, and Render native Python. build.sh installs dependencies, builds Tailwind, and collects static files. Start: `gunicorn kodehax_academy.wsgi --bind 0.0.0.0:$PORT`. Models, migrations, data, templates, features, and SQLite test settings are preserved.

Current deployment settings, environment variables, verified TLS, plan-specific migrations, and remaining email OTP / media blockers are maintained in [README](README.md#render-native-python-deployment) and [.env.example](.env.example). Health checks remain database-independent liveness.

## Validation

Pinned requirements installed successfully in an isolated Python 3.14.2 environment. `pip check`, ordinary Django checks, production `check --deploy`, npm clean install, Tailwind rebuild, and collectstatic passed (132 assets). All 21 SQLite tests passed (18 existing and 3 deployment regressions); deployment regression tests cover health/proxy behavior and TLS refusal before authentication. Offline checks confirmed Django 5.2.5 loads PyMySQL, verified TLS uses certificate and hostname validation, and invalid production settings are rejected.

No authorized reachable live MySQL connection was established. MySQL server checks, schema/migration status, queries, migration execution, and actual TLS negotiation were not verified. Render's Python 3.12.12 / Node 22.16.0 runtime and Linux Gunicorn startup were not executed locally; the host has Python 3.14.2 / Node 24.13.1 on Windows. Tailwind emitted an outdated Browserslist database notice; the build succeeded.

No deployment, push, or live database modification was performed.
