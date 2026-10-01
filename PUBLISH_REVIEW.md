# Publication review — 2026-10-01

Target: `Mubashir-114/kodehax_academy`, branch `cleanup/conservative-review-20261001`. Publication is authorized; no merge to main, deployment, forced push, database migration or live database operation is part of this work.

## Preservation and diagnosis

Repository root, current directory, branch, remotes, registered worktrees, reachable history/reflogs, stashes, relevant neighboring project folders, ignored/untracked source and unreachable Git objects were inspected. No applicable repository AGENTS.md was found in the workspace or accessible immediate parent. Unrelated personal folders were not searched. The Groq discrepancy is strongly explained by source rollback: every manifest-restored file matches its saved baseline and all six migration-only artifacts were absent. See [GROQ_MIGRATION.md](GROQ_MIGRATION.md) for evidence and limits.

Before edits, a binary tracked patch and copies/hashes of 23 existing changed or relevant untracked source files were preserved in an external temporary-directory snapshot. Backups and local runtime data remain on disk and are excluded from publication: `.migration-backup/`, `.migration-before.patch`, worktrees, verification helpers, virtual environments, credentials, local databases, uploads, generated static collection and node_modules. `.env.example` contains placeholders/empty secret fields and configured public model IDs only. No `.env` contents or key values were printed.

## Validation in this checkout

| Check | Result |
| --- | --- |
| Baseline full Django suite | 38 tests passed before repairs. |
| Baseline suite using real root URLconf | 38 tests passed. |
| Migrated full suite | 64 tests passed; 26 new migration/provider regressions supplement the baseline. |
| Migrated suite using real root URLconf | 64 tests passed after Gemini helpers were removed; 266 leaf routes and existing routes/names/callbacks retained. |
| Django checks | Passed. |
| Production `check --deploy` | Passed with safe dummy production settings and an unreachable dummy MySQL host; no DB connection. |
| Python requirements/dependencies | `pip install -r requirements.txt` and `pip check` passed in the existing isolated verification environment. |
| Frontend | `npm ci --include=dev` and `npm run tailwind` passed; outdated Browserslist notice remains. |
| Static collection | Passed; 132 existing collected assets unchanged. |
| Build/config syntax | Git Bash `bash -n build.sh`, Node syntax checks for Tailwind/PostCSS passed. Shell source contains LF only and `.gitattributes` enforces `eol=lf`. |
| Migration consistency | Pre-existing exit 1: two LectureNote index renames are proposed. No migrations generated/applied. |
| Templates | 84 of 86 tracked HTML templates compiled; same two legacy registration TemplateSyntaxErrors, no template changes. This scan excludes plain-text email templates. |
| Source preservation | Templates, other static sources, models, migrations and URL files match original tracked contents. Changed Python AST parsing passed. |
| Diff checks | Working and entire branch diff against `53de367` pass after correcting existing report trailing whitespace. |
| Credentials/artifacts | Changed-file credential-value scan found no local secret values; explicit publication exclusions verified. Intended files are staged individually. |
| Live Groq | Exact model IDs accessible; one complete synthetic workflow run and three total vision requests passed. One later text response was malformed and rejected. No vision 400 reproduced. |

The provider tests are mocked boundary tests covering model selection, image encoding, JSON/schema validation, incomplete output, missing keys, authentication, 429s, timeout and safe vision failures. Real-root journey tests cover grading math/snapshots, syntax override, failure scoring, quota response status, image response envelopes, and existing permissions/journeys. They do not represent live model calls. Synthetic smoke checks are separate evidence and did not use real students, submitted files or private course data. The prior claimed 61-test result was not reused: this checkout's observed counts are 38 baseline and 64 after repair.

## Remaining blockers and limits

The existing LectureNote index-name inconsistency and two legacy template compilation failures remain. Earlier cleanup findings concerning submitted-code isolation and HTML/script sanitization are documented in [CLEANUP_REVIEW.md](CLEANUP_REVIEW.md) and were not folded into this migration. The existing all-A scoring compatibility rule remains unchanged.

Live MySQL connectivity/schema/TLS, actual email delivery, durable production media, Render Linux runtime/startup, browser interactions, and external production services remain unverified. Email OTP and media deployment blockers remain in README. Validation ran on Windows Python 3.14.2 / Node 24.13.1; the documented Render runtime differs. Qwen vision is a preview model, and synthetic successes cannot establish production reliability.

## Commit structure and publication

Deployment preparation: `1078b51` — native Render/MySQL configuration, verified TLS, deployment tests/build and documentation. Cleanup: `943f4ba` — unused imports and real-route characterization tests. A separate Groq recovery commit contains the shared service, migrated consumers, schema validation, new tests, synthetic smoke command and updated reports. Final publication status and hashes are verified against GitHub and reported in the accompanying task result.
