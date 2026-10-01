"""An HTTPS isolation-service adapter and a bounded development-only runner.

The local backend has no filesystem/network isolation and must never serve
untrusted public submissions. Production requires an independently isolated
execution service; transport configuration is not proof of that isolation.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid

from django.conf import settings
import requests

PROTOCOL = "kodehax-python-v1"
WORKER = Path(__file__).with_name("worker.py")
LIMITS = {"wall_seconds": 3, "cpu_seconds": 2, "memory_bytes": 256 * 1024 * 1024,
          "output_bytes": 128 * 1024, "processes": 1}
REQUEST_BYTES = 512 * 1024


class ExecutionUnavailable(Exception):
    """An infrastructure failure, never a student's failed test or penalty."""
    def __init__(self):
        super().__init__("The isolated code execution service is unavailable. Your score and attempts have not changed. Please try again later.")


def fatal(category, name, message, elapsed=0):
    return {"results": [], "fatal_error": {"category": category, "type": name, "message": message, "line": None},
            "execution_ms": elapsed}


def _validate_response(raw, job):
    def reject_constant(value):
        raise ValueError("Non-finite JSON")
    data = json.loads(raw, parse_constant=reject_constant)
    if not isinstance(data, dict) or any(data.get(key) != job[key] for key in ("protocol", "job_id", "runner_sha256")):
        raise ValueError("Unbound worker response")
    results, error, elapsed = data.get("results"), data.get("fatal_error"), data.get("execution_ms")
    if not isinstance(results, list) or len(results) not in (0, len(job["test_cases"])):
        raise ValueError("Incomplete results")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not 0 <= elapsed <= 60_000:
        raise ValueError("Invalid elapsed time")
    if error is not None:
        if not isinstance(error, dict) or error.get("category") not in {"compilation", "runtime", "timeout"}:
            raise ValueError("Invalid worker error")
        if any(not isinstance(error.get(key), str) for key in ("type", "message")):
            raise ValueError("Invalid error fields")
        if error.get("line") is not None and (type(error["line"]) is not int or error["line"] < 1):
            raise ValueError("Invalid error line")
        error = {**error, "message": error["message"][:2000]}
    elif len(results) != len(job["test_cases"]):
        raise ValueError("Missing results")
    for result, case in zip(results, job["test_cases"]):
        if not isinstance(result, dict) or "actual" not in result or type(result.get("passed")) is not bool:
            raise ValueError("Invalid result")
        if not isinstance(result.get("error", ""), str) or result.get("error_category", "") not in {"", "runtime"}:
            raise ValueError("Invalid case error")
        # Expected answers and equality/scoring stay under application control.
        result.update(expected=case.get("expected"), input=case.get("input", []))
        result["passed"] = not (result.get("error") or result.get("error_category") or result.get("error_type")) and result["actual"] == case.get("expected")
    return {"results": results, "fatal_error": error, "execution_ms": elapsed}


def _remote(job, encoded):
    endpoint = settings.CODE_EXECUTION_URL
    token = settings.CODE_EXECUTION_TOKEN
    try:
        url = urlsplit(endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment or not token:
            raise ExecutionUnavailable()
        url.port
        with requests.Session() as session:
            # Do not inherit HTTP proxy credentials/settings from the web process.
            session.trust_env = False
            started = time.monotonic()
            with session.post(endpoint, data=encoded, headers={"Authorization": "Bearer " + token,
                              "Content-Type": "application/json"}, stream=True,
                              timeout=(3, 5), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ExecutionUnavailable()
                data = bytearray()
                for chunk in response.iter_content(4096):
                    if time.monotonic() - started > 10 or len(data) + len(chunk) > LIMITS["output_bytes"]:
                        raise ExecutionUnavailable()
                    data.extend(chunk)
        return _validate_response(data, job)
    except ExecutionUnavailable:
        raise
    except (requests.RequestException, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        # Never expose request headers, response bodies, or service credentials.
        raise ExecutionUnavailable() from None


def _stop(process):
    if os.name == "posix":
        # Kill the process group even if its leader exited but descendants hold pipes.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.kill()


def _development(job, encoded):
    if settings.PRODUCTION:
        raise ExecutionUnavailable()
    environment = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    if os.name == "nt":
        environment["SystemRoot"] = os.environ.get("SystemRoot", r"C:\Windows")
    quota = None
    process = None
    with tempfile.TemporaryDirectory(prefix="kodehax-code-") as directory:
        environment.update(TMP=directory, TEMP=directory, TMPDIR=directory)
        try:
            # Windows venv launchers spawn another process. The stdlib-only
            # harness uses the base interpreter so the one-process quota holds.
            interpreter = getattr(sys, "_base_executable", sys.executable)
            process = subprocess.Popen([interpreter, "-I", "-S", "-B", str(WORKER)],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       cwd=directory, env=environment, start_new_session=os.name == "posix")
            if os.name == "nt":
                from .windows_limits import Job
                quota = Job(process, LIMITS["memory_bytes"], LIMITS["cpu_seconds"])
            # Worker waits on stdin. No submission is sent before quotas attach.
            output, lock, exceeded = {"stdout": bytearray(), "stderr": bytearray()}, threading.Lock(), threading.Event()
            def drain(stream, name):
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        return
                    with lock:
                        if sum(len(value) for value in output.values()) + len(chunk) > LIMITS["output_bytes"]:
                            exceeded.set()
                            _stop(process)
                            return
                        output[name].extend(chunk)
            readers = [threading.Thread(target=drain, args=(process.stdout, "stdout"), daemon=True),
                       threading.Thread(target=drain, args=(process.stderr, "stderr"), daemon=True)]
            for reader in readers:
                reader.start()
            # Bound writes as well as execution when the child cannot consume stdin.
            def feed():
                try:
                    process.stdin.write(encoded)
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            writer = threading.Thread(target=feed, daemon=True)
            writer.start()
            try:
                process.wait(timeout=LIMITS["wall_seconds"])
            except subprocess.TimeoutExpired:
                _stop(process)
                process.wait(timeout=1)
                return fatal("timeout", "TimeoutExpired", "Execution timed out.", 3000)
            finally:
                if os.name == "posix":
                    _stop(process)
                for reader in readers:
                    reader.join(timeout=1)
                writer.join(timeout=1)
            if exceeded.is_set():
                return fatal("runtime", "OutputLimitExceeded", "Output limit exceeded.")
            if process.returncode:
                if os.name == "posix" and process.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
                    return fatal("timeout", "ResourceLimitExceeded", "Execution resource limit exceeded.", 3000)
                return fatal("runtime", "ResourceLimitExceeded", "Execution failed or exceeded its resource limits.")
            return _validate_response(output["stdout"], job)
        except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
            raise ExecutionUnavailable() from None
        finally:
            if process is not None:
                _stop(process)
                process.wait(timeout=1)
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
            if quota is not None:
                quota.close()


def execute(code, function_name, test_cases, *, kind):
    if kind not in {"daily", "assessment"}:
        raise ValueError("Unknown grading kind")
    if len(code.encode()) > 64 * 1024 or len(test_cases) > 100:
        return fatal("compilation", "InputLimitExceeded", "Submission exceeds the execution input limit.")
    job = {"protocol": PROTOCOL, "job_id": uuid.uuid4().hex,
           "runner_sha256": hashlib.sha256(WORKER.read_bytes()).hexdigest(),
           "kind": kind, "code": code, "function_name": function_name, "test_cases": test_cases,
           "limits": LIMITS.copy()}
    encoded = json.dumps(job, allow_nan=False).encode()
    if len(encoded) > REQUEST_BYTES:
        return fatal("compilation", "InputLimitExceeded", "Submission exceeds the execution input limit.")
    backend = settings.CODE_EXECUTION_BACKEND
    if backend == "remote":
        return _remote(job, encoded)
    if backend == "development":
        return _development(job, encoded)
    raise ExecutionUnavailable()
