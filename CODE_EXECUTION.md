# Code execution: isolation infrastructure required

The native Render Django service must not execute public student code locally. It now sends jobs to a separately administered HTTPS execution service. No Dockerfile, Docker dependency or deployment change is introduced in this repository.

**Current status:** application integration and development mitigations are implemented and tested. A real isolated execution service has not been provisioned, contacted or verified. Public code execution is **not certified safe** by this patch or by passing tests.

## Required production setup

Configure these privately in Render, after provisioning and reviewing the service:

```env
CODE_EXECUTION_BACKEND=remote
CODE_EXECUTION_URL=https://executor.example.invalid/v1/jobs
CODE_EXECUTION_TOKEN=<private-service-token>
```

The URL is an administrator-configured HTTPS endpoint, not a student-supplied URL. TLS certificate verification remains enabled; redirects are refused; proxy environment settings are not inherited. The bearer credential is sent only in the gateway request header and never inside a job/guest environment. Request bodies contain only code, function name, cases, grading kind, limits and protocol correlation fields. No application environment, database credentials, Groq key, usernames or uploaded files are sent.

Production rejects the development backend. A missing, unavailable or invalid remote executor produces a visible HTTP 503 in the existing daily workspace or assessment form, keeping entered code visible. It does not create a graded attempt, deduct points or finalize an assessment. There is no fallback to local execution. Existing grading formulas, quiz behavior and deterministic score calculations are unchanged. Other application features and health/build paths remain available. `check --deploy` warns when the remote URL/token are absent and errors if production selects the development backend.

After the service is provisioned, run the opt-in synthetic transport check:

```bash
python manage.py code_executor_check
```

This checks only authentication/transport, protocol binding and a synthetic `2 + 2` result. It does **not** attest that a gateway really uses secure isolation. Independent infrastructure review and containment tests remain necessary before public execution. Do not run exploit probes against existing user data, credentials or external targets.

## Selected isolation design: one Firecracker microVM per job

Provision a separate Linux host/service with KVM support and a maintained Firecracker installation. A protected gateway authenticates the Render application, queues jobs with strict concurrency bounds, and starts a fresh jailed microVM for each job. Render stays on its native Python runtime and talks to this gateway over HTTPS. Merely putting a second ordinary Python subprocess on another Render worker is insufficient isolation.

Firecracker uses a VM boundary with a separate guest kernel; its [design documentation](https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md) calls for the jailer in production and describes the required host containment and networking controls. The [production host setup](https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md) must be reviewed and applied. The gateway must implement the following before being considered suitable:

1. Start each VM through the jailer with a unique unprivileged identity, cgroup quotas, seccomp and constrained filesystem access. Keep host kernel/Firecracker/guest kernel patched. Native Render documentation does not establish access to these facilities; provision the execution host separately.
2. Use an immutable, minimal guest image containing Python and this repository's `code_execution/worker.py`. Transfer only the job through a controlled guest agent/vsock channel. Never expose gateway/API credentials, application mounts, database/upload directories, host sockets or metadata to the guest. Do not attach guest network devices; block host egress as an additional control.
3. Use a fresh guest/scratch filesystem per job, with no reuse of student-modified state. Destroy the whole VM and scratch data on success, error, timeout or gateway disconnect. Bound scratch space and writable files. A read-only base image is not a substitute for the VM boundary.
4. Enforce three seconds of submitted-code wall time, two CPU seconds, 256 MiB of code-process memory, one submitted-code process and 128 KiB of combined result/output. Also enforce independent host/VM CPU, memory, process/thread and disk quotas that account for VMM/kernel/agent overhead. A guest-only `rlimit` is not sufficient against a compromised guest kernel. The gateway must kill/destroy the VM at the deadline, not rely only on the harness to exit.
5. Limit job size/queue depth/concurrency, authenticate each request, rate limit the gateway and avoid logging source/case contents or secrets. Return bounded, schema-valid JSON only. Treat any setup failure, worker artifact mismatch, queue overload or inability to enforce isolation as HTTP 503, not a failed student test.
6. Review gateway/guest agent code and verify filesystem, network, cross-job and resource containment independently using harmless synthetic fixtures. Confirm no host/application data reaches a guest. Monitor failures and patch status. A declared engine name or matching worker digest is not proof of these controls.

Render's [native runtime documentation](https://render.com/docs/native-runtimes) and [web-service documentation](https://render.com/docs/web-services) describe its native application deployment. This integration needs outbound HTTPS, and does not assume nested virtualization, root privileges, a container daemon or a local sandbox on Render.

The gateway implementation, KVM host, guest image, TLS endpoint, authentication/rate-limit setup, independent containment review and production configuration are **manual infrastructure work still required**. No such infrastructure was deployed by this patch.

## Gateway protocol

Authenticated `POST` to the configured URL; content type `application/json`. The gateway should have an independent server-side maximum request size of 512 KiB and maximum code size of 64 KiB, with at most 100 test cases. Validate every field; do not accept submitted runner scripts, filenames, arbitrary commands or caller-supplied execution images. Whitelist the deployed worker artifact and protocol version. Limits are fixed application policy and must also be clamped/enforced by the gateway.

Request structure:

```json
{
  "protocol": "kodehax-python-v1",
  "job_id": "unique-application-generated-id",
  "runner_sha256": "sha256-of-deployed-worker.py",
  "kind": "daily",
  "code": "def synthetic_add(a, b):\n    return a + b",
  "function_name": "synthetic_add",
  "test_cases": [{"input": [2, 2], "expected": 4}],
  "limits": {"wall_seconds": 3, "cpu_seconds": 2, "memory_bytes": 268435456, "output_bytes": 131072, "processes": 1}
}
```

`kind` is `daily` or `assessment`. Run the trusted worker artifact inside the VM, pass the validated request on stdin and capture its bounded stdout response. The harness preserves daily per-case error results and assessment abort-on-error behavior. It exports only selected public standard-library symbols and rejects private imports, wildcard imports, relative imports and private/dunder name/attribute access. Those checks reduce known bypasses but are **not the isolation boundary**, and do not guarantee that an adversarial program cannot tamper with its interpreter/harness output. The external service must be treated as trusted grading infrastructure; independently verify it as well as its host isolation.

Response structure, for exactly one case per input (or zero results plus a fatal error):

```json
{
  "protocol": "kodehax-python-v1",
  "job_id": "same-request-id",
  "runner_sha256": "same-approved-worker-digest",
  "results": [{"passed": true, "actual": 4, "expected": 4, "input": [2, 2], "error_type": "", "error_category": "", "error": "", "execution_ms": 1}],
  "fatal_error": null,
  "execution_ms": 1
}
```

Fatal errors contain `category` (`compilation`, `runtime` or `timeout`), `type`, bounded `message` and nullable positive integer `line`. Transport/infrastructure failures must use non-200 HTTP status rather than a grading error. The application rejects malformed JSON, non-finite values, oversized responses, wrong protocol/job/artifact binding and missing case results. It takes expected values from its own cases and recomputes equality instead of trusting a worker's `passed` flag. This prevents a simple flag/expected-value mismatch, not all adversarial grading fraud.

The HTTP client uses connect/read timeouts of 3/5 seconds, a 10-second stream deadline checked between chunks and a 128 KiB response cap. An individual blocking read can extend that stream deadline by up to the five-second read timeout; infrastructure must separately enforce the submitted-code deadline. No automatic request retries or redirections occur.

## Local development only

Existing local development uses `CODE_EXECUTION_BACKEND=development` when `PRODUCTION=False`. If copying `.env.example`, explicitly change its remote backend to development only on a trusted local workstation. Keep it remote for any public service.

The development process uses an empty temporary working directory and only locale/SystemRoot/temp environment entries. Python runs with `-I -S -B`; no application credentials, PYTHONPATH or site packages are inherited. Windows Job Objects impose memory/CPU/one-process limits before submitting any code to stdin, and kill on job close. POSIX children set address-space, CPU, file/core, file-descriptor and process limits before executing code. The parent independently caps stdout/stderr, bounds wall time and kills the process group. User print output and returned JSON are also bounded.

These mitigations do **not** remove access to the host filesystem/network if Python restrictions are bypassed. Python AST checks, isolated mode and subprocesses are **not secure isolation**. Never accept untrusted public submissions through this backend. Windows quotas were exercised locally with synthetic probes; POSIX limit configuration was unit-tested with a stub and not exercised on a Linux host in this session. Remote transport tests use mocks, not a deployed microVM gateway.
