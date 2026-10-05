# Architecture

This document summarizes the application structure and the role of each major Django app inside Kodehax Academy.

## Runtime model

Kodehax is organized as a single Django project with domain-based apps rather than a microservice layout. Requests flow through project-level URL routing, app views, templates, and shared services before reaching the database or external integrations.

## App responsibilities

- `accounts` — authentication, users, OTP and verification flows, and account-related services.
- `users` — shared user model and user-centric helpers and template tags.
- `student` — student dashboard, profile, classroom experience, and AI chat workflows.
- `teacher` — teacher dashboard, classroom management, notes, and assessment operations.
- `adminpanel` — admin oversight, maintenance mode, and platform settings.
- `skill_assessment` — challenge and assessment logic.
- `daily_challenges` — daily coding problem generation and scoring workflows.
- `chat` — chat-related service abstractions and model logic.
- `kodehax_academy` — project settings, middleware, shared URL routing, and deployment configuration.

## Data and runtime configuration

- Production uses MySQL through Django’s `django.db.backends.mysql` engine.
- The repository test configuration intentionally points to SQLite via `kodehax_academy.test_settings`.
- Static files are compiled with Tailwind and served with WhiteNoise in deployment.
- Production media storage uses a private S3-compatible backend with Backblaze B2 and signed/private URLs when appropriate.
- Media storage variables are configured through environment variables and intentionally fail closed in production when required values are missing.

## External integrations

- Groq is used for model-backed AI flows.
- Brevo provides API-backed transactional email and account communication.
- Render hosts the production deployment workflow.

## Operational notes

The app treats security and deployment assumptions as explicit runtime requirements rather than local defaults. For a production deployment, the environment must provide required credentials and database values before the app starts.
