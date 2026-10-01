# Conservative cleanup review

Historical cleanup baseline, before the separate Groq migration. Current validation and publication are in [PUBLISH_REVIEW.md](PUBLISH_REVIEW.md).

Date: 2026-10-01. Branch: `cleanup/conservative-review-20261001`.

## Scope and preservation

The cleanup removes only 15 unused import bindings from seven application files and adds 17 characterization tests. No known product behavior was deliberately changed. No files, functions, dependencies, migrations, model fields, routes, templates, frontend interactions, AI prompts/settings, or environment/deployment settings were removed or changed by this pass. No performance or security refactor was attempted.

The 16 pre-existing modified/untracked/deleted paths were snapshotted before cleanup and verified byte-for-byte afterward, including the prior native Render/MySQL changes and PROJECT_REPORT.md. They remain uncommitted. This review's edits are separate from that earlier work. No commit, push, deployment, or live database operation was performed.

## Application connections inspected

Repository instruction discovery found no applicable AGENTS.md in the workspace or its accessible immediate parent. The review mapped 153 existing Python files, including migration dependencies and operations; 90 template/email files; 266 real URL leaf patterns (238 distinct names, including Django admin); build/configuration/dependency files; and inline frontend scripts, styles, selectors, forms, and literal links. Static scans and targeted source tracing support this review; they are not a formal proof of every execution path.

| Area | Connections retained |
| --- | --- |
| Project | WSGI/ASGI and settings register apps/middleware/context processors. Root URLs include accounts before users; student/teacher/admin APIs remain callable under their existing aliases. Device middleware and the mobile template map select existing templates. |
| Accounts/users | Custom User model -> registration forms -> verification tokens and email -> password login -> session OTP -> role redirects. Teacher invitation creation/redemption and password recovery remain unchanged. Users home/logout are active; legacy users auth helpers remain present. |
| Teacher/student | ClassRoom teacher ownership and student membership -> assignment types -> file/code submissions and quiz answers -> evaluation services -> PerformanceRecord snapshots -> analytics and template navigation/context. Course README permissions/rendering and lecture-note publication remain unchanged. |
| Skill assessment | Dynamic forms/default content -> self assessment, MCQ and subprocess coding evaluation -> weighted Decimal scoring -> StudentAssessment/StudentSkill -> student profiles and admin reset. Seed migrations remain intact. |
| Daily challenges | Approved parameter templates and CodingProblem content -> generation/history -> student/date sets -> hint/attempt/level rules -> subprocess execution -> scores, StudentPoints and session totals -> workspace/dashboard. Seed/assignment management commands remain intact. |
| Chat/AI | Student API aliases -> user-owned ChatSession/ChatMessage -> expiring memory -> Gemini client, prompts and vision processing -> normalized payloads -> existing inline chat UI. `chat` is an integration module even though it is not an installed app. |
| Admin | admin_required -> management routes and platform settings -> login signal and maintenance middleware. Superuser bypass, force-logout generation, maintenance HTTP 503/Retry-After, and health HTTP 200 remain unchanged. |
| Frontend/deployment | Django templates/inline JS and CSS -> Tailwind content discovery -> npm lockfile/build scripts -> collectstatic/WhiteNoise. External MySQL/PyMySQL and native Render Python/Gunicorn workflow remain unchanged. |

All literal template dependencies, named URL references, and mobile-map target templates resolve in the source inventory. Dynamic template selection, framework registration, template tags, decorators/signals, model hooks, management commands, string-based settings, and operational documentation were considered before choosing removals.

## Baseline issues (not introduced by cleanup)

| Check/finding | Baseline and final result |
| --- | --- |
| Migration consistency | `makemigrations --check --dry-run --settings=kodehax_academy.test_settings` exits 1: Django proposes two LectureNote index renames. Migration 0012 stores explicit names differing from current generated names. No migration was generated, and neither models nor migrations were edited. Review index naming separately. |
| Complete template compilation | 88 of 90 template/email files compile. `templates/user/register/std_register.html` and `teacher_register.html` put `{% load static %}` before `{% extends %}`, causing TemplateSyntaxError. The current registration URLs resolve to accounts views using different templates; these legacy files and helper views were retained. |
| Frontend build notice | Browserslist/caniuse-lite is outdated; baseline and final builds both succeed. No dependency upgrade or lockfile update was made to remove the notice. |
| Original test coverage | The 21-test suite passes but default test_settings uses a reduced URLconf with stub dashboards. Separate real-root-URLconf runs pass; new characterization tests explicitly override to the real URLconf. Passing stub routes was not counted as real dashboard verification. |

## Removal evidence

| File | Removed bindings |
| --- | --- |
| accounts/views.py | `render` |
| users/views.py | `render` |
| student/views.py | `render`, `settings` |
| adminpanel/views.py | `Sum`, `TruncDate`, `DailyChallenge`, `StudentChallengeAttempt`, `StudentPoints`, `CodeSubmission`, `QuizAnswer`, `Submission` |
| daily_challenges/services.py | `re` |
| teacher/services/evaluation.py | `settings` |
| teacher/services/performance.py | `Q` |

For every binding above, the original module's AST contains no load of that imported name. Repository-wide searches found no qualified consumers/re-exports of these bindings, relevant string references, wildcard import dependencies, module-namespace reflection, or framework registrations that need them. Templates render through render_for_device where render was unused. Model/query symbols remain imported by their actual consumers and registered by their existing apps/admin modules. The daily runner/template-expression strings do not use the removed `re` binding.

Each changed file's non-import AST is identical to its pre-cleanup source. Existing line endings were preserved rather than applying broad formatting. All 266 path/name/callback records match baseline, all 90 templates/email files are byte-identical, and model/migration/configuration/AI-module hashes remain unchanged.

No entire files or callable code were deleted. Legacy auth helpers/templates, compatibility/fallback logic, framework placeholders and package initializers, management commands, and the imported OTP constant were retained when their broader operational use was uncertain.

## Dependencies and performance

No Python or npm dependencies were removed or upgraded. The npm lockfile's direct dependency ranges match package.json. PyMySQL/RSA support, Gemini, Pillow, Markdown/Bleach, WhiteNoise, Gunicorn, Tailwind and the PostCSS configuration remain intact. Several optional storage, REST/JWT, CORS, scheduling, Sass/compression and HTTP helper packages have little or no direct active usage; static imports do not establish whether external scripts or deployment workflows rely on them. Review that inventory separately before pruning. No transitive lockfile entries were edited.

No query, caching, request, timeout, retry, or asynchronous behavior was changed. A disposable SQLite fixture measured get_classroom_performance_analytics at **96 queries for one student** and **253 for three students**, with no assignments/attempts. Repeated per-student skill/analytics computations are a concrete performance opportunity. These counts describe that fixture, not production latency or an achieved improvement. Defer batching until scoring, ordering, time windows, cohort filtering, and write side effects have stronger characterization coverage.

## Security findings requiring separate review

No security fixes were folded into import cleanup. The following existing problems would require accepted-input, rendering, or isolation changes and therefore need a separate focused patch under the requested preservation policy:

1. **Urgent: submitted-code restrictions can be bypassed.** In daily_challenges/services.py's RUNNER_SCRIPT, an allowed module exposes builtins through a from-import. A harmless local probe accessed the otherwise blocked evaluator and calculated `1 + 1` successfully. No file, credential, network, or destructive operation was attempted. Name/attribute AST checks are insufficient as a security boundary. Propose stronger namespace/import enforcement and a separately reviewed execution isolation design with resource limits. The current subprocess also inherits the process environment and has a wall-clock timeout but no configured memory/output quota; assess this boundary before allowing untrusted submissions.
2. **Unsafe README link fallback.** teacher/services/course_readme.py's _BasicHtmlSanitizer filters tag/attribute names and escapes values but does not restrict URL protocols. A mixed Markdown/HTML input selects the fallback and retains a `javascript:` link in returned HTML. Propose shared protocol-aware sanitization across all fallback/package paths, with tests for mixed content and malformed URLs.
3. **Inline chart JSON can terminate a script element.** student/views.py json.dumps assignment labels; templates/student/performance.html injects them using `|safe`. Offline template rendering confirmed that an assignment label containing a script-closing marker remains literal markup. Propose Django json_script plus client parsing, preserving chart data and appearance.
4. **Client Markdown fallback fails open if the sanitizer is unavailable.** README, lecture-note and some grading renderers use raw parsed HTML when DOMPurify is absent. This was confirmed from source, not by browser execution. Propose escaped-text fallback and tests simulating failed CDN loads.

Authentication/authorization, CSRF middleware, ORM queries, upload limits/type/image validation, configuration/secrets, HTML output, and code runners were reviewed without printing credential values. No raw SQL or csrf_exempt usage was found in the application scan. This is a scoped review, not a comprehensive security certification. Also review inactive/changed users during pending OTP, rate limiting, daemon-thread email reliability, and the all-A quiz compatibility heuristic in separate behavior/security passes. The existing all-A quiz rule awards full credit even for a wrong answer; a characterization test records it, and cleanup preserves it.

## Validation

| Check | Result |
| --- | --- |
| Original baseline suite | 21 tests passed before application edits. |
| Added real-route characterization tests | 17 passed against unchanged application code before cleanup; passed after cleanup. |
| Final default test suite | 38 tests passed. |
| Original suite with real root URLconf | 21 passed before import cleanup. |
| Final full suite with real root URLconf | 38 tests passed with ROOT_URLCONF=kodehax_academy.urls. |
| Django system checks | Passed before and after cleanup. |
| Production check --deploy | Passed with safe dummy environment, DEBUG=False, explicit hosts/origins and unreachable dummy MySQL hostname; no live database connection. |
| Python dependency check | pip check passed. |
| Frontend installation/build | npm ci --include=dev and npm run tailwind passed; outdated Browserslist notice remains. |
| Static collection | Passed; 132 collected assets are unchanged on the final run. |
| JavaScript configuration syntax | node --check passed for tailwind.config.js and postcss.config.js. |
| Render build script syntax | Git Bash `bash -n build.sh` passed. Full Linux build/runtime was not executed. |
| Migration consistency | Same pre-existing LectureNote index-name failure, exit 1. |
| Template scan | Same two legacy compile errors; no new missing literal template/URL references. |
| Diff and preservation | git diff --check passed; original 16 changed paths unchanged; non-import AST and route/template comparisons passed. |
| Configured lint/type checks | No configured lint/type-check commands or configuration were found; no lint rules/check exclusions were added. AST parsing covered all existing Python sources. |

## User-journey verification and limits

Automated real-route tests cover registration/inactive account creation and token verification (email dispatch mocked), portal login destinations and cross-role restrictions, admin dashboard rendering, classroom creation/enrollment/ownership, file-assignment creation and local storage readback, quiz scoring/performance snapshots, first-step skill assessment and weighted scoring, chat methods/payloads/session ownership, text-chat JSON validation and mocked AI response handling, mocked teacher note generation, maintenance/health, desktop/mobile home template selection, and logout. Existing OTP tests cover student/teacher/admin login, resend, invalid/expired codes and attempt limits; daily-challenge tests cover workspace/scoring/penalties and an actual safe-library runner invocation.

These are server-side automated tests, not manual browser verification. Local file readback does not prove production media HTTP retrieval or persistence. Browser interactions, layouts at viewport sizes, CDN/editor rendering, actual email delivery, Gemini responses/quota, end-to-end coding assessment, all assignment types/edge cases, large/concurrent challenge workloads, and provider-specific MySQL behavior remain unverified.

Only disposable SQLite test databases were created/migrated, plus temporary test uploads. Live MySQL queries/schema status/TLS negotiation and live migrations were not attempted. Tests ran on Windows with Python 3.14.2 and Node 24.13.1, not the documented Render Python 3.12.12/Node 22.16.0 Linux runtime. Production upload durability/serving and SMTP OTP deployment blockers from README remain unresolved. This pass does not establish production readiness.
