"""Versioned Python grading harness, run INSIDE a separately isolated worker.

AST/import checks below are defense in depth, not secure Python isolation.
This file is also used by the explicitly development-only local backend.
"""
import ast
import builtins
import contextlib
import importlib
import io
import json
import math
import sys
import time
import types

PROTOCOL = "kodehax-python-v1"
OUTPUT_BYTES = 128 * 1024
EXPORTS = {
    "math": {name for name in dir(math) if not name.startswith("_")},
    "collections": {"Counter", "deque", "defaultdict", "OrderedDict", "namedtuple", "ChainMap"},
    "itertools": {"accumulate", "chain", "combinations", "combinations_with_replacement", "compress",
                  "count", "cycle", "dropwhile", "filterfalse", "groupby", "islice", "pairwise",
                  "permutations", "product", "repeat", "starmap", "takewhile", "tee", "zip_longest"},
    "functools": {"reduce", "partial", "cmp_to_key", "lru_cache", "cache", "total_ordering"},
    "heapq": {"heappush", "heappop", "heapify", "heapreplace", "heappushpop", "nlargest", "nsmallest", "merge"},
    "bisect": {"bisect", "bisect_left", "bisect_right", "insort", "insort_left", "insort_right"},
    "string": {"ascii_letters", "ascii_lowercase", "ascii_uppercase", "digits", "hexdigits",
               "octdigits", "punctuation", "whitespace", "printable", "capwords"},
}
BLOCKED_CALLS = {"eval", "exec", "open", "__import__", "compile", "input", "globals", "locals", "vars"}


class OutputLimitExceeded(Exception):
    pass


class BoundedOutput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.size = 0

    def write(self, text):
        self.size += len(text.encode("utf-8"))
        if self.size > OUTPUT_BYTES:
            raise OutputLimitExceeded("Output limit exceeded.")
        # User stdout was never part of scoring/results; do not retain it.
        return len(text)


def validate_code(code):
    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Restricted name detected.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("Private/dunder attribute access is not allowed.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            raise ValueError("Restricted call detected.")
        if isinstance(node, ast.Import):
            if any(alias.name not in EXPORTS or (alias.asname or "").startswith("__") for alias in node.names):
                raise ValueError("Restricted import detected.")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in EXPORTS or any(
                alias.name not in EXPORTS[node.module] or (alias.asname or "").startswith("__") for alias in node.names
            ):
                raise ValueError("Restricted import detected.")
    return tree


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in EXPORTS or any(item not in EXPORTS[name] for item in (fromlist or ())):
        raise ImportError("Restricted import detected.")
    module = importlib.import_module(name)
    # Never return the original module's namespace (e.g. collections.__builtins__).
    return types.SimpleNamespace(**{key: getattr(module, key) for key in EXPORTS[name] if hasattr(module, key)})


def error_payload(exc, category):
    return {"category": category, "type": type(exc).__name__, "message": exception_message(exc),
            "line": getattr(exc, "lineno", None)}


def exception_message(exc):
    return (str(exc) or ("Memory limit exceeded." if isinstance(exc, MemoryError) else type(exc).__name__))[:2000]


def run(payload):
    captured = BoundedOutput()
    def safe_print(*args, **kwargs):
        kwargs["file"] = captured
        return builtins.print(*args, **kwargs)
    names = ("abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max",
             "min", "range", "reversed", "set", "sorted", "str", "sum", "tuple", "zip")
    allowed = {name: getattr(builtins, name) for name in names}
    allowed.update(print=safe_print, __import__=safe_import)
    namespace = {"__builtins__": allowed}
    started = time.perf_counter()
    try:
        tree = validate_code(payload["code"])
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            exec(compile(tree, "<student-code>", "exec"), namespace, namespace)
        target = namespace.get(payload["function_name"])
        if not callable(target):
            raise ValueError(f"Function '{payload['function_name']}' was not defined.")
    except Exception as exc:
        category = "compilation" if isinstance(exc, (SyntaxError, ValueError)) else "runtime"
        return {"results": [], "fatal_error": error_payload(exc, category), "execution_ms": 0}
    results = []
    for case in payload["test_cases"]:
        args, expected = case.get("input", []), case.get("expected")
        case_started = time.perf_counter()
        try:
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                actual = target(*args)
            # Ensure bounded JSON serializability before retaining a result.
            if len(json.dumps(actual, allow_nan=False).encode()) > OUTPUT_BYTES:
                raise OutputLimitExceeded("Result output limit exceeded.")
            results.append({"passed": actual == expected, "actual": actual, "expected": expected, "input": args,
                            "error_type": "", "error_category": "", "error": "",
                            "execution_ms": round((time.perf_counter() - case_started) * 1000, 2)})
        except Exception as exc:
            if payload["kind"] == "assessment":
                return {"results": [], "fatal_error": error_payload(exc, "runtime"), "execution_ms": 0}
            results.append({"passed": False, "actual": None, "expected": expected, "input": args,
                            "error_type": type(exc).__name__, "error_category": "runtime", "error": exception_message(exc),
                            "execution_ms": round((time.perf_counter() - case_started) * 1000, 2)})
    return {"results": results, "fatal_error": None, "execution_ms": round((time.perf_counter() - started) * 1000, 2)}


def apply_posix_limits(limits):
    import resource
    memory = limits["memory_bytes"]
    cpu = limits["cpu_seconds"]
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if hasattr(resource, "RLIMIT_NPROC"):
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))


if __name__ == "__main__":
    payload = json.loads(sys.stdin.buffer.read(512 * 1024 + 1))
    # Windows limits are attached by the parent BEFORE sending any submission.
    if sys.platform != "win32":
        apply_posix_limits(payload["limits"])
    result = run(payload)
    result.update(protocol=PROTOCOL, job_id=payload["job_id"], runner_sha256=payload["runner_sha256"])
    encoded = json.dumps(result, allow_nan=False).encode()
    if len(encoded) > OUTPUT_BYTES:
        result.update(results=[], fatal_error=error_payload(OutputLimitExceeded("Result output limit exceeded."), "runtime"))
        encoded = json.dumps(result).encode()
    sys.stdout.buffer.write(encoded)
