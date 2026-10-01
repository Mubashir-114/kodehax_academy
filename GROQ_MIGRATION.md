# Groq migration recovery — 2026-10-01

## Why the previous report did not match Git

At inspection, HEAD was `53de367` on `cleanup/conservative-review-20261001`. Requirements and all active AI consumers still used Gemini. The expected shared service, schema/tests, vision helper, smoke command and migration report were absent, rather than ignored. No migration commit existed in reachable branch history. The registered detached worktree and neighboring Academy source folder also contained Gemini, with no recoverable Groq implementation/report.

The local rollback manifest records the six migration-only artifacts and hashes of their expected finished contents. **All 12 restored files matched its pre-migration snapshot hashes**, and all six artifacts it would remove were absent. This is strong evidence of an applied rollback, rather than a completed migration in this checkout. The retained Groq SDK and credential are consistent with source rollback leaving the environment intact. The available evidence does not identify the actor or execution time. Unreachable Git blobs/trees contained neither matching finished-file hashes nor migration artifact paths. The original report itself was not recoverable; this report describes newly completed work, not restoration of its claimed implementation.

The rollback helper was inspected and never executed. Existing native Render/MySQL preparation, cleanup edits/tests, and other changed source files were snapshotted outside the repository before repair.

## Implementation

All active consumers now use `chat/ai_service.py`: student text chat and session chat, student image queries, teacher quiz/notes/coding-assignment authoring, file grading, code rubric grading, and admin service status. `chat/schemas.py` validates JSON objects, field types, nested quiz entries, string lists and finite rubric values. No routes, permission checks, models/migrations, templates or UI source were changed by the migration. Existing response envelopes and normalization remain. Deterministic quiz rules, rubric scaling/clamping, Python syntax override and performance snapshots remain, including the existing all-A quiz compatibility behavior.

Gemini helpers were removed only after migrated consumers passed tests. `requirements.txt` replaces `google-genai` with the locally exercised `groq==1.7.0`; unrelated dependencies remain. The local verification environment can still contain obsolete installed packages; it was not destructively pruned.

Set these only in the server environment:

```env
GROQ_API_KEY=<private-key>
GROQ_TEXT_MODEL=openai/gpt-oss-20b
GROQ_VISION_MODEL=qwen/qwen3.8-27b
```

No models are substituted automatically. API keys are never returned to the browser. The admin status reports key presence and recent normalized issues; it explicitly does not claim a live account check.

The provider boundary uses a 30-second timeout and zero SDK retries. Authentication/permission failures, 429s, unavailable connections/timeouts, request HTTP 400s, empty/truncated output and invalid JSON produce safe messages, with normalized issue metadata available to admin status. Successful completion clears the prior issue. Provider exception bodies are not logged by the migrated authoring helpers.

Images retain JPG/PNG validation and the 5 MiB upload limit. Validated RGB pixels are re-encoded as JPEG and sent as a base64 data URL, without filenames/EXIF or public upload URLs. A 10 MiB encoded-image cap keeps the base64 request below the documented vision request ceiling. Vision uses JSON mode and Qwen instruct reasoning (`none`), and rejects invalid response schemas. It does not retry another model on failure.

## Model and account verification

Checked current [Groq model documentation](https://console.groq.com/docs/models), [vision documentation](https://console.groq.com/docs/vision), and [structured-output documentation](https://console.groq.com/docs/structured-outputs) on 2026-10-01. GPT-OSS 20B is listed as a production model; Qwen 3.8 27B is a **preview** vision model. Keep that lifecycle limitation in deployment decisions. Both exact configured IDs were returned by this account's models endpoint. Synthetic completion checks also established access, rather than relying only on model listing.

Live checks used synthetic educational prompts and an in-memory `2 + 2` image only. One complete run passed text-chat JSON, quiz, notes, assignment generation, grading-rubric JSON and vision. Two further isolated vision runs passed: **three successful vision requests**, with no HTTP 400 reproduced. An intervening combined probe failed text JSON validation before reaching vision. Earlier completion probes also failed without an HTTP response; these do not establish a vision failure. Malformed text output was rejected safely. External model output remains nondeterministic, and these probes do not prove reliability under production load.

The earlier intermittent vision HTTP 400 had no retained request/error evidence to identify its cause. Current Groq documentation describes a request-size limit and the multimodal data-URL format. Correct encoding, bounded size and avoiding model fallback address concrete request risks; no claim is made that the historical 400 was fixed or diagnosed conclusively.

Reproduce opt-in synthetic checks (credentials must be available privately):

```bash
python manage.py groq_smoke --vision --studio --settings=kodehax_academy.test_settings
python manage.py groq_smoke --vision-only --settings=kodehax_academy.test_settings
```

The command prints model IDs and validation outcomes, never keys or provider bodies. It uses the test settings to avoid live database work. See [PUBLISH_REVIEW.md](PUBLISH_REVIEW.md) for checkout validation and remaining blockers.
