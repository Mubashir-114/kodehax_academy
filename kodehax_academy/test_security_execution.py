"""Synthetic probes only. Passing these tests does not prove isolation."""
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from code_execution import service, worker
from daily_challenges.services import _run_code, _today, preview_solution, submit_solution_for_challenge
from daily_challenges.models import DailyChallenge, DailyChallengeSet, StudentChallengeAttempt, StudentPoints
from skill_assessment.services import run_code_against_test_cases, evaluate_coding_responses
from skill_assessment.models import CodingProblem, StudentAssessment
from users.models import User


PROBLEM = SimpleNamespace(function_name="solve", test_cases=[{"input": [], "expected": 2}])


@override_settings(PRODUCTION=False, CODE_EXECUTION_BACKEND="development")
class LocalMitigationTests(SimpleTestCase):
    def test_reported_import_builtins_bypass_is_blocked_in_both_features(self):
        probes = (
            'from collections import __builtins__ as b\ndef solve():\n    return b["eval"]("1 + 1")',
            'import collections\ndef solve():\n    return collections.__builtins__["eval"]("1 + 1")',
            'from collections import _sys\ndef solve():\n    return 2',
            'from math import *\ndef solve():\n    return 2',
            'def solve():\n    return __builtins__["eval"]("1 + 1")',
        )
        for code in probes:
            with self.subTest(code=code):
                results, error, _ = _run_code(PROBLEM, code)
                self.assertEqual(results, [])
                self.assertEqual(error["category"], "compilation")
                results, error = run_code_against_test_cases(PROBLEM, code)
                self.assertEqual(results, [])
                self.assertIsNotNone(error)

    def test_import_facade_has_only_approved_public_exports(self):
        facade = worker.safe_import("collections", fromlist=("Counter",))
        self.assertEqual(facade.Counter([1, 1])[1], 2)
        self.assertNotIn("__builtins__", vars(facade))
        self.assertNotIn("_sys", vars(facade))
        with self.assertRaises(ImportError):
            worker.safe_import("collections", fromlist=("__builtins__",))
        with self.assertRaises(ImportError):
            worker.safe_import("string", fromlist=("Formatter",))

    def test_safe_imports_and_exact_assessment_result_envelope(self):
        code = 'from math import floor\nfrom collections import Counter\ndef solve():\n    return floor(2.9) + Counter([1])[2]'
        daily, error, _ = _run_code(PROBLEM, code)
        self.assertIsNone(error)
        self.assertTrue(daily[0]["passed"])
        assessment, error = run_code_against_test_cases(PROBLEM, code)
        self.assertIsNone(error)
        self.assertEqual(assessment, [{"passed": True, "actual": 2, "expected": 2}])

    def test_subprocess_receives_no_application_environment_and_temporary_cwd(self):
        original = subprocess.Popen
        with patch.dict(os.environ, {"SYNTHETIC_SECRET": "synthetic-only-value", "PYTHONPATH": "synthetic-path"}):
            with patch("code_execution.service.subprocess.Popen", wraps=original) as start:
                result = service.execute("def solve():\n    return 2", "solve", PROBLEM.test_cases, kind="daily")
        self.assertTrue(result["results"][0]["passed"])
        environment = start.call_args.kwargs["env"]
        self.assertNotIn("SYNTHETIC_SECRET", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertLessEqual(set(environment), {"LANG", "LC_ALL", "SystemRoot", "TMP", "TEMP", "TMPDIR"})
        self.assertNotEqual(Path(start.call_args.kwargs["cwd"]), Path.cwd())
        self.assertFalse(Path(start.call_args.kwargs["cwd"]).exists())

    def test_wall_or_cpu_limit_stops_infinite_loop(self):
        started = time.monotonic()
        result = service.execute("def solve():\n    while True:\n        pass", "solve", PROBLEM.test_cases, kind="daily")
        self.assertLess(time.monotonic() - started, 6)
        self.assertIsNotNone(result["fatal_error"])
        self.assertIn(result["fatal_error"]["type"], {"TimeoutExpired", "ResourceLimitExceeded"})

    def test_memory_quota_rejects_synthetic_allocation(self):
        result = service.execute('def solve():\n    return "x" * (512 * 1024 * 1024)',
                                 "solve", PROBLEM.test_cases, kind="daily")
        self.assertTrue(result["fatal_error"] or result["results"][0]["error"])
        if result["results"]:
            self.assertFalse(result["results"][0]["passed"])
            self.assertEqual(result["results"][0]["error_type"], "MemoryError")

    def test_print_output_is_bounded(self):
        result = service.execute('def solve():\n    print("x" * (200 * 1024))\n    return 2',
                                 "solve", PROBLEM.test_cases, kind="daily")
        self.assertFalse(result["results"][0]["passed"])
        self.assertEqual(result["results"][0]["error_type"], "OutputLimitExceeded")

    def test_return_value_output_is_bounded(self):
        result = service.execute('def solve():\n    return "x" * (200 * 1024)',
                                 "solve", PROBLEM.test_cases, kind="daily")
        self.assertEqual(result["results"][0]["error_type"], "OutputLimitExceeded")

    def test_parent_bounds_raw_subprocess_output_independently_of_harness(self):
        original = subprocess.Popen
        def synthetic_writer(command, **kwargs):
            return original([command[0], "-I", "-S", "-c",
                'import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b"x" * (256 * 1024))'], **kwargs)
        with patch("code_execution.service.subprocess.Popen", side_effect=synthetic_writer):
            result = service.execute("def solve():\n    return 2", "solve", PROBLEM.test_cases, kind="daily")
        self.assertEqual(result["fatal_error"]["type"], "OutputLimitExceeded")

    def test_posix_quota_configuration_without_changing_parent_limits(self):
        fake = MagicMock()
        fake.RLIMIT_AS, fake.RLIMIT_CPU, fake.RLIMIT_FSIZE = 1, 2, 3
        fake.RLIMIT_CORE, fake.RLIMIT_NOFILE, fake.RLIMIT_NPROC = 4, 5, 6
        with patch.dict("sys.modules", {"resource": fake}):
            worker.apply_posix_limits(service.LIMITS)
        fake.setrlimit.assert_any_call(1, (256 * 1024 * 1024, 256 * 1024 * 1024))
        fake.setrlimit.assert_any_call(2, (2, 2))
        fake.setrlimit.assert_any_call(3, (0, 0))
        fake.setrlimit.assert_any_call(6, (1, 1))

    @override_settings(PRODUCTION=True)
    def test_production_never_starts_development_subprocess(self):
        with patch("code_execution.service.subprocess.Popen") as start:
            with self.assertRaises(service.ExecutionUnavailable):
                service.execute("def solve():\n    return 2", "solve", PROBLEM.test_cases, kind="daily")
        start.assert_not_called()

    def test_input_size_limit_does_not_start_process(self):
        with patch("code_execution.service.subprocess.Popen") as start:
            result = service.execute("#" * (64 * 1024 + 1), "solve", PROBLEM.test_cases, kind="daily")
        self.assertEqual(result["fatal_error"]["type"], "InputLimitExceeded")
        start.assert_not_called()

    def test_assessment_scoring_rules_still_award_full_credit(self):
        problem = SimpleNamespace(id=101, title="Synthetic", function_name="solve", test_cases=PROBLEM.test_cases)
        result = evaluate_coding_responses([problem], {"problem_101": "def solve():\n    return 2"})
        self.assertEqual(result["normalized_score"], 100)
        self.assertEqual(result["breakdown"]["101"]["status"], "passed")


@override_settings(PRODUCTION=True, CODE_EXECUTION_BACKEND="remote",
                   CODE_EXECUTION_URL="https://executor.example.invalid/v1/jobs", CODE_EXECUTION_TOKEN="synthetic-worker-token")
class RemoteExecutorTests(SimpleTestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.response = MagicMock()
        self.response.__enter__.return_value = self.response
        self.response.status_code = 200
        self.transform = lambda data: data
        def post(url, **kwargs):
            job = json.loads(kwargs["data"])
            response = {key: job[key] for key in ("protocol", "job_id", "runner_sha256")}
            response.update(results=[{"passed": True, "actual": 2, "expected": 999}], fatal_error=None, execution_ms=1)
            self.response.iter_content.return_value = [json.dumps(self.transform(response)).encode()]
            return self.response
        self.session.post.side_effect = post
        self.patcher = patch("code_execution.service.requests.Session", return_value=self.session)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def execute(self):
        return service.execute("def solve():\n    return 2", "solve", PROBLEM.test_cases, kind="daily")

    def test_remote_request_is_authenticated_bounded_and_contains_only_job_data(self):
        result = self.execute()
        self.assertTrue(result["results"][0]["passed"])
        self.assertEqual(result["results"][0]["expected"], 2)
        kwargs = self.session.post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer synthetic-worker-token")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (3, 5))
        self.assertFalse(self.session.trust_env)
        job = json.loads(kwargs["data"])
        self.assertEqual(job["limits"], service.LIMITS)
        self.assertEqual(set(job), {"protocol", "job_id", "runner_sha256", "kind", "code", "function_name", "test_cases", "limits"})

    def test_worker_passed_flag_cannot_override_application_equality(self):
        self.transform = lambda data: {**data, "results": [{"passed": True, "actual": 999}]}
        self.assertFalse(self.execute()["results"][0]["passed"])

    def test_error_statuses_do_not_fall_back_to_local_execution(self):
        for status in (302, 401, 403, 429, 500, 503):
            self.response.status_code = status
            with self.subTest(status=status), patch("code_execution.service.subprocess.Popen") as local:
                with self.assertRaises(service.ExecutionUnavailable) as caught:
                    self.execute()
                self.assertNotIn("synthetic-worker-token", str(caught.exception))
                local.assert_not_called()

    def test_missing_token_is_unavailable_without_network_request(self):
        with override_settings(CODE_EXECUTION_TOKEN=""), self.assertRaises(service.ExecutionUnavailable):
            self.execute()
        self.session.post.assert_not_called()

    def test_insecure_or_malformed_endpoint_is_rejected(self):
        for value in ("http://executor.example.invalid", "https://synthetic:placeholder@executor.example.invalid/",
                      "https://[broken", "https://executor.example.invalid/#fragment"):
            with self.subTest(value=value), override_settings(CODE_EXECUTION_URL=value):
                with self.assertRaises(service.ExecutionUnavailable):
                    self.execute()
        self.session.post.assert_not_called()

    def test_response_must_match_job_protocol_and_worker_digest(self):
        for key in ("protocol", "job_id", "runner_sha256"):
            self.transform = lambda data, key=key: {**data, key: "unbound-synthetic-value"}
            with self.subTest(key=key), self.assertRaises(service.ExecutionUnavailable):
                self.execute()

    def test_malformed_result_and_elapsed_types_are_rejected(self):
        for invalid in ({"results": {}}, {"results": []}, {"execution_ms": "slow"},
                        {"execution_ms": -1}, {"results": [{"actual": 2, "passed": "yes"}]}):
            self.transform = lambda data, invalid=invalid: {**data, **invalid}
            with self.subTest(invalid=invalid), self.assertRaises(service.ExecutionUnavailable):
                self.execute()

    def test_response_bytes_are_bounded(self):
        self.transform = lambda data: {**data, "extra": "x" * service.LIMITS["output_bytes"]}
        with self.assertRaises(service.ExecutionUnavailable):
            self.execute()

    def test_invalid_json_and_network_timeout_are_unavailable(self):
        self.session.post.side_effect = service.requests.Timeout("synthetic sensitive detail")
        with self.assertRaises(service.ExecutionUnavailable) as caught:
            self.execute()
        self.assertNotIn("sensitive", str(caught.exception))

    def test_invalid_json_response_is_unavailable(self):
        self.response.iter_content.side_effect = lambda size: iter([b"not-json"])
        with self.assertRaises(service.ExecutionUnavailable):
            self.execute()

    def test_stream_deadline_is_bounded(self):
        with patch("code_execution.service.time.monotonic", side_effect=[0, 11]):
            with self.assertRaises(service.ExecutionUnavailable):
                self.execute()

    def test_deployment_checks_make_missing_isolation_infrastructure_visible(self):
        from code_execution.checks import execution_configuration
        with override_settings(CODE_EXECUTION_TOKEN=""):
            self.assertEqual(execution_configuration(None)[0].id, "code_execution.W001")
        with override_settings(CODE_EXECUTION_BACKEND="development"):
            self.assertEqual(execution_configuration(None)[0].id, "code_execution.E001")


@override_settings(ROOT_URLCONF="kodehax_academy.urls", SECURE_SSL_REDIRECT=False)
class ExecutionOutageJourneyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.student = User.objects.create_user(username="synthetic_security_student", role="student")
        self.client.force_login(self.student)
        self.problem = CodingProblem.objects.create(title="Synthetic security problem", topic="loops", description="Synthetic",
            function_name="solve", starter_code="def solve():\n    return 2", test_cases=PROBLEM.test_cases)
        self.challenge_set = DailyChallengeSet.objects.create(student=self.student, date=_today())
        self.challenge = DailyChallenge.objects.create(challenge_set=self.challenge_set, student=self.student,
            problem=self.problem, date=_today(), title="Synthetic", description="Synthetic", topic="loops", function_name="solve",
            starter_code=self.problem.starter_code, test_cases=PROBLEM.test_cases, difficulty="easy", level=1, points=5)

    def test_daily_outage_does_not_deduct_points_or_consume_attempts(self):
        points, _ = StudentPoints.objects.get_or_create(student=self.student)
        initial = points.points_remaining
        with patch("daily_challenges.services._run_code", side_effect=service.ExecutionUnavailable()):
            for action in ("run", "submit"):
                response = self.client.post(reverse("daily_challenge_workspace", args=[self.challenge.pk]),
                                            {"action": action, "code": "def solve():\n    return 2"})
                self.assertEqual(response.status_code, 503)
                self.assertContains(response, "execution service is unavailable", status_code=503)
                self.assertContains(response, "return 2", status_code=503)
        self.challenge.refresh_from_db()
        points.refresh_from_db()
        self.assertEqual(self.challenge.attempts, 0)
        self.assertEqual(self.challenge.latest_code, "")
        self.assertEqual(points.points_remaining, initial)
        self.assertFalse(StudentChallengeAttempt.objects.filter(challenge=self.challenge).exists())

    def test_assessment_outage_preserves_form_code_and_does_not_finalize(self):
        CodingProblem.objects.exclude(pk=self.problem.pk).update(is_active=False)
        assessment = StudentAssessment.objects.create(student=self.student, current_step=3, coding_score=15)
        with patch("skill_assessment.views.ensure_default_assessment_content"):
            with patch("skill_assessment.views.evaluate_coding_responses", side_effect=service.ExecutionUnavailable()):
                response = self.client.post(reverse("skill_assessment_step", args=[3]),
                    {f"problem_{self.problem.pk}": "def solve():\n    return 2"})
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "execution service is unavailable", status_code=503)
        self.assertContains(response, "return 2", status_code=503)
        assessment.refresh_from_db()
        self.assertFalse(assessment.completed)
        self.assertEqual(assessment.coding_score, 15)
        self.assertEqual(assessment.current_step, 3)
