# Security

This document covers the project’s operational security expectations and the configuration conventions used to keep secrets and production behavior safe.

## Secret handling

- Keep credentials in `.env` or deployment environment variables.
- Never commit real database credentials, API keys, or email secrets.
- Use `.env.example` as a safe template, not a real configuration file.

## Production assumptions

The Django settings intentionally reject unsafe defaults in production. Required keys such as `SECRET_KEY`, `ALLOWED_HOSTS`, database variables, and media storage credentials are treated as mandatory.

- `DEBUG` must be `False` in production.
- `PRODUCTION` must be set explicitly and used to gate operational behavior.
- Media storage variables are required before production media storage is enabled.
- Startup fails if required production variables are missing rather than silently falling back.

## External services

- Groq keys are expected through environment configuration.
- Brevo is the current transactional email provider through its HTTPS API integration.
- Production media storage uses a private S3-compatible backend with Backblaze B2, and signed/private URLs are used when appropriate.
- Database connection settings should use a reachable provider host and, when required, a verified TLS certificate chain.

## Security review

For additional project-specific review notes, see [../SECURITY_REVIEW.md](../SECURITY_REVIEW.md).
