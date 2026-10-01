# Security patch verification — 2026-10-01

Baseline: `6e8de0b` on `cleanup/conservative-review-20261001`. PR #5 remains a draft. No deployment or merge is part of this patch.

| Issue | Status | Result |
| --- | --- | --- |
| README link protocols | Fixed | Shared conservative URL policy across Bleach, basic HTML, fallback Markdown and browser rendering. Recursive entity/percent encodings, unsafe schemes, controls and malformed authorities are rejected; legitimate formatting/links remain. |
| Chart JSON injection | Fixed | Native chart arrays use Django `json_script` and client `JSON.parse(textContent)`. Chart configuration and values are preserved. |
| Client Markdown fallback | Fixed | All ten affected controllers use the shared local helper. Missing parser/sanitizer or thrown errors render through `textContent`; normal rendering uses DOMPurify with URL filtering. |
| Submitted-code execution | Partially mitigated | Both runners share a restricted harness and bounded development process. Known import/builtins bypasses are blocked. Production uses authenticated HTTPS execution transport without a local fallback. Actual isolation infrastructure remains unprovisioned and unverified. |

## Checks performed in this checkout

- Before editing: complete existing suite, **64 tests passed**, using the real root URLconf.
- After changes: **35 focused Python security tests passed**; complete suite **99 tests passed** with `kodehax_academy.real_url_test_settings` (real root URLconf, no silenced checks).
- **76 offline JavaScript probes passed**, covering all ten controllers, missing CDN/parser, sanitizer exceptions, normal rendering and a shared URL corpus. These use DOM/parser/sanitizer stubs; they are not a live browser/CDN integration test.
- Synthetic local probes exercised both runners, approved imports, Windows memory/CPU/process quotas, bounded time/output, minimal environment and temporary working directory. Mocked remote probes covered authentication, malformed/oversized responses, correlation, status failures and timeouts. Real-route outage tests verified attempts, points, entered form code and completion remain unchanged.
- Django checks, `pip check`, `npm ci`, Tailwind build, JavaScript configuration syntax, `bash -n build.sh`, static collection and Git diff checks passed. Production deployment checks emitted `code_execution.W001`: missing external executor URL/token. This warning is a real readiness blocker for coding execution.
- Migration consistency still exits **1** for the pre-existing two `LectureNote` index renames. They are intentionally outside this patch. Two existing legacy templates fail standalone compilation; affected templates compile. Neither problem is suppressed or repaired here.

Test reproduction:

```bash
python manage.py test kodehax_academy.test_security_rendering kodehax_academy.test_security_execution --settings=kodehax_academy.real_url_test_settings --noinput
python manage.py test --settings=kodehax_academy.real_url_test_settings --noinput
node tests/security_markdown.test.cjs
```

## Required infrastructure and limitations

[CODE_EXECUTION.md](CODE_EXECUTION.md) specifies the application protocol and a separate, jailed Firecracker microVM per job. Provision and review the gateway, KVM host, guest image, TLS/authentication, quotas, network/filesystem containment and lifecycle cleanup; then configure `CODE_EXECUTION_BACKEND=remote`, `CODE_EXECUTION_URL` and `CODE_EXECUTION_TOKEN` privately in Render. Run the opt-in synthetic transport check only after provisioning, followed by independent containment verification.

Until then, production coding requests explicitly return HTTP 503 in the existing interfaces without charging attempts or changing scores. Other features remain available. Local development remains available only outside production. AST restrictions, Python `-I`, subprocesses, matching worker digests and passing tests do **not** prove secure isolation or prevent every possible grading-harness attack.

The gateway itself and execution infrastructure are not implemented/deployed by this application patch. POSIX quota configuration was mocked, not exercised on Linux; no live remote executor, Groq, MySQL, email or Render deployment was tested in this security session. Exploit probes used harmless synthetic fixtures only.

MySQL/native Render deployment files, Groq integration, routes, permissions, migrations, legacy templates and deterministic scoring formulas remain outside the implementation changes. The shared runner preserves daily per-case errors and assessment abort-on-error semantics. No credentials, backups, local databases, uploads or temporary tooling are intended for this commit.
