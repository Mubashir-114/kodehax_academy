import logging
import re
from contextlib import contextmanager
from time import perf_counter

from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext


logger = logging.getLogger("post_auth.performance")

_QUOTED_VALUE_RE = re.compile(r"'(?:''|[^'])*'")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_WHITESPACE_RE = re.compile(r"\s+")


def _query_fingerprint(sql):
    """Collapse SQL values without putting user data or secrets in logs."""
    sql = _QUOTED_VALUE_RE.sub("?", sql)
    sql = _NUMBER_RE.sub("?", sql)
    return _WHITESPACE_RE.sub(" ", sql).strip()[:240]


@contextmanager
def post_auth_span(stage, *, capture_queries=False):
    """Opt-in timing for the login/OTP/dashboard critical path."""
    if not getattr(settings, "POST_AUTH_PERFORMANCE_LOGGING", False):
        yield
        return

    started_at = perf_counter()
    query_context = CaptureQueriesContext(connection) if capture_queries else None
    if query_context is not None:
        query_context.__enter__()
    try:
        yield
    finally:
        duration_ms = (perf_counter() - started_at) * 1000
        if query_context is None:
            logger.info("post_auth_perf stage=%s duration_ms=%.1f", stage, duration_ms)
        else:
            query_context.__exit__(None, None, None)
            queries = query_context.captured_queries
            db_ms = sum(float(query.get("time", 0)) for query in queries) * 1000
            fingerprints = {}
            for query in queries:
                fingerprint = _query_fingerprint(query.get("sql", ""))
                fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
            duplicates = sorted(
                ((count, fingerprint) for fingerprint, count in fingerprints.items() if count > 1),
                reverse=True,
            )[:5]
            slow_queries = sorted(
                (
                    (float(query.get("time", 0)) * 1000, _query_fingerprint(query.get("sql", "")))
                    for query in queries
                ),
                reverse=True,
            )[:5]
            logger.info(
                "post_auth_perf stage=%s duration_ms=%.1f query_count=%s db_ms=%.1f "
                "duplicate_queries=%s slow_queries=%s",
                stage,
                duration_ms,
                len(queries),
                db_ms,
                duplicates,
                slow_queries,
            )
