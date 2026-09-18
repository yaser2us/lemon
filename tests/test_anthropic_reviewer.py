import io
import json
import tempfile
import unittest
import urllib.error
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from lemon.anthropic_reviewer import (AnthropicClient, AnthropicReviewer, NoRedirect,
                                      ReviewError, load_configuration, review_action)
from lemon.design import DesignWorld
from lemon.design_agents import BackendAgent, REQUIREMENTS, TestAgent
from lemon.design_evaluation import evaluate_design
from lemon.events import replay
from lemon.__main__ import main, run_design


def observation(revision=1):
    initial = {"revision": 0, "contract": None, "challenges": {}}
    contract = BackendAgent().decide({}, initial)[0].payload["contract"]
    return {"revision": revision, "requirements": deepcopy(REQUIREMENTS), "contract": contract, "cancellation": "OUT_OF_SCOPE"}


def provider_review(view):
    """Offline transport fixture; no real provider is used by automated tests."""
    action = TestAgent().decide({}, view)[0]
    return {"decision": action.kind, "revision": view["revision"], "issues": action.payload.get("issues", []),
            "questions": [], "test_cases": action.payload.get("artifact", {}).get("test_cases", []), "explanation": action.explanation}


def response(review, **patches):
    body = {"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "submit_review", "input": review}],
            "usage": {"input_tokens": 100, "output_tokens": 50}, **patches}
    return io.BytesIO(json.dumps(body).encode())


class FakeClient:
    model, max_requests, timeout = "test-model", 8, 30

    def __init__(self):
        self.requests, self.observations = 0, []

    def submit(self, view):
        self.requests += 1
        self.observations.append(deepcopy(view))
        return provider_review(view), {"attempts": 1, "latency_ms": 1, "input_tokens": 100, "output_tokens": 50}


class AnthropicTransportTests(unittest.TestCase):
    def test_reads_only_allowed_settings_without_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env.local"
            env.write_text("UNRELATED=$(echo should-not-run)\nANTHROPIC_API_KEY='secret-value' # comment\nANTHROPIC_MODEL=claude-test\n")
            self.assertEqual(load_configuration(env, environ={}), ("secret-value", "claude-test"))
            self.assertEqual(load_configuration(env, environ={"ANTHROPIC_MODEL": "claude-override"})[1], "claude-override")
            link = Path(tmp) / "link"
            link.symlink_to(env)
            with self.assertRaises(ReviewError):
                load_configuration(link, environ={})

    def test_missing_and_invalid_config_errors_never_echo_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env.local"
            env.write_text("ANTHROPIC_API_KEY='super-secret\nANTHROPIC_MODEL=claude-test")
            with self.assertRaises(ReviewError) as error:
                load_configuration(env, environ={})
            self.assertNotIn("super-secret", str(error.exception))
            env.unlink()
            with self.assertRaisesRegex(ReviewError, "MISSING_CONFIGURATION"):
                load_configuration(env, environ={})

    def test_request_uses_configured_model_and_sends_key_only_in_header(self):
        seen = []

        def opener(req, timeout):
            seen.append(req)
            self.assertEqual(timeout, 30)
            return response(provider_review(observation()))

        client = AnthropicClient("secret-key-not-for-output", "claude-configured", opener=opener)
        result, telemetry = client.submit(observation())
        req = seen[0]
        body = json.loads(req.data)
        self.assertEqual(body["model"], "claude-configured")
        self.assertEqual(req.get_header("X-api-key"), "secret-key-not-for-output")
        self.assertNotIn("secret-key-not-for-output", req.data.decode())
        self.assertEqual(body["tool_choice"], {"type": "tool", "name": "submit_review"})
        self.assertEqual(telemetry["input_tokens"], 100)
        self.assertEqual(result["revision"], 1)

    def test_http_error_is_redacted_and_auth_failure_not_retried(self):
        secret = "secret-body-value"

        def opener(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, secret, {}, io.BytesIO(secret.encode()))

        client = AnthropicClient("key", "model", opener=opener)
        with self.assertRaisesRegex(ReviewError, "HTTP_401") as error:
            client.submit(observation())
        self.assertNotIn(secret, str(error.exception))
        self.assertEqual(client.requests, 1)

    def test_retry_and_request_budget_are_bounded(self):
        calls = []

        def opener(req, timeout):
            calls.append(req)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "limited", {}, io.BytesIO(b""))
            return response(provider_review(observation()))

        client = AnthropicClient("secret-key", "model", opener=opener, sleep=lambda _: None, max_requests=2)
        _, telemetry = client.submit(observation())
        self.assertEqual(telemetry["attempts"], 2)
        with self.assertRaisesRegex(ReviewError, "REVIEW_BUDGET_EXHAUSTED"):
            client.submit(observation())
        self.assertEqual(len(calls), 2)

    def test_timeout_and_truncation_are_errors_not_approval(self):
        def timeout(req, timeout):
            raise TimeoutError("private transport details")
        client = AnthropicClient("secret-key", "model", opener=timeout)
        with self.assertRaisesRegex(ReviewError, "TIMEOUT"):
            client.submit(observation())
        client = AnthropicClient("secret-key", "model", opener=lambda *a, **k: response({}, stop_reason="max_tokens"))
        with self.assertRaisesRegex(ReviewError, "OUTPUT_LIMIT"):
            client.submit(observation())

    def test_rejects_unexpected_tools_and_refusals(self):
        for body in ({"stop_reason": "end_turn", "content": [{"type": "text", "text": "Cannot review"}]},
                     {"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "execute", "input": {}}]}):
            client = AnthropicClient("secret-key", "model", opener=lambda *a, **k: io.BytesIO(json.dumps(body).encode()))
            with self.assertRaisesRegex(ReviewError, "INVALID_RESPONSE"):
                client.submit(observation())
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))


class AnthropicReviewerTests(unittest.TestCase):
    def test_rejects_stale_mixed_and_malformed_model_actions(self):
        view = observation()
        good = provider_review(view)
        self.assertEqual(review_action(good, view).kind, "CHALLENGE")
        for patch_value in ({"revision": 99}, {"revision": True}, {"decision": "PROPOSE_CONTRACT"},
                            {"issues": ["DISABLE_AUTH"]}, {"issues": ["IDEMPOTENCY", "IDEMPOTENCY"]},
                            {"questions": ["Should I proceed?"]}, {"explanation": ""}, {"extra": "data"}):
            with self.subTest(patch=patch_value), self.assertRaises(ReviewError):
                review_action({**good, **patch_value}, view)

    def test_repeated_observation_uses_cached_action(self):
        client = FakeClient()
        reviewer = AnthropicReviewer(client)
        view = observation()
        a, b = reviewer.decide({}, view), reviewer.decide({}, view)
        self.assertEqual(a, b)
        self.assertEqual(client.requests, 1)
        self.assertNotIn("expected", client.observations[0])
        self.assertNotIn("scenario", client.observations[0])
        self.assertEqual(set(client.observations[0]), {"revision", "requirements", "contract", "cancellation"})

    def test_mock_provider_negotiates_and_replays_without_credentials(self):
        for variant in ("negotiated", "duplicate-delivery", "missing-decision", "silent-reviewer"):
            with self.subTest(variant=variant):
                client = FakeClient()
                run = run_design(variant, 7, AnthropicReviewer(client))
                self.assertTrue(run["quality"]["passed"], run["quality"]["checks"])
                self.assertEqual(run["final_state"], replay(run["events"]))
                if variant in {"missing-decision", "silent-reviewer"}:
                    self.assertEqual(client.requests, 0)
                else:
                    self.assertGreaterEqual(run["quality"]["metrics"]["api_requests"], 2)
                    self.assertEqual(run["quality"]["metrics"]["reported_input_tokens"], client.requests * 100)

    def test_provider_failure_is_visible_without_silent_fallback(self):
        class FailedClient(FakeClient):
            def submit(self, view):
                self.requests += 1
                raise ReviewError("HTTP_401")
        run = run_design("negotiated", 7, AnthropicReviewer(FailedClient()))
        self.assertEqual(run["final_state"]["status"], "needs_review")
        self.assertEqual(run["final_state"]["reason"], "HTTP_401")
        self.assertNotIn("test-agent", run["final_state"]["reviews"])
        self.assertFalse(run["quality"]["passed"])
        self.assertEqual(run["quality"]["metrics"]["model_reviews_without_usage"], 1)

    def test_review_budget_stops_extra_calls(self):
        client = FakeClient()
        reviewer = AnthropicReviewer(client, max_reviews=1)
        reviewer.decide({}, observation())
        with self.assertRaisesRegex(ReviewError, "REVIEW_BUDGET_EXHAUSTED"):
            reviewer.decide({}, observation(2))
        self.assertEqual(client.requests, 1)

    def test_comparison_cli_saves_both_sources_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp, patch("lemon.__main__.configured_reviewer", return_value=AnthropicReviewer(FakeClient())):
            self.assertEqual(main(["compare", "--output", tmp]), 0)
            summary = json.loads((Path(tmp) / "comparison-negotiated-seed-7.json").read_text())
            self.assertTrue(summary["same_final_contract"])
            self.assertEqual(summary["baseline"]["quality"]["metrics"]["api_requests"], 0)
            self.assertGreater(summary["anthropic"]["quality"]["metrics"]["api_requests"], 0)


if __name__ == "__main__":
    unittest.main()
