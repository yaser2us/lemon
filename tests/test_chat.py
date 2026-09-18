import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lemon.__main__ import main, run_design
from lemon.chat import ChatViewer, load_chat
from lemon.events import replay


class ChatTests(unittest.TestCase):
    def test_live_observation_preserves_audit_and_matches_replay(self):
        observed = []

        def observer(event):
            observed.append(event.copy())
            event["hash"] = "observer cannot mutate the log"

        run = run_design("negotiated", 7, on_event=observer)
        baseline = run_design("negotiated", 7)
        self.assertEqual(run["events"], baseline["events"])
        self.assertEqual(observed, run["events"])
        self.assertEqual(replay(run["events"]), run["final_state"])

    def test_cards_show_challenges_revisions_and_outcome_without_ansi(self):
        stream = io.StringIO()
        viewer = ChatViewer(stream=stream, delay=0)
        viewer.start(live=True)
        run = run_design("negotiated", 7, on_event=viewer.event)
        viewer.finish(run)
        output = stream.getvalue()
        for expected in ("Product Agent", "UI Agent", "CHALLENGE", "STALE_REVISION", "approvals 4/4", "Outcome: agreed", "not been executed"):
            self.assertIn(expected, output)
        self.assertNotIn("\033", output)

    def test_saved_chat_is_verified_and_never_configures_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run.json"
            run = run_design("negotiated", 7)
            path.write_text(json.dumps(run))
            with patch("lemon.__main__.configured_reviewer", side_effect=AssertionError("No API")), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(["chat", str(path), "--delay", "0"]), 0)
                self.assertIn("VERIFIED REPLAY", output.getvalue())
            run["events"][0]["data"]["seed"] = 999
            path.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError, "Event chain mismatch"):
                load_chat(path)

    def test_terminal_control_sequences_in_agent_text_are_neutralized(self):
        stream = io.StringIO()
        viewer = ChatViewer(stream=stream, delay=0, details=True)
        viewer.card({"sender": "test-agent", "recipient": "world", "type": "ACCEPT", "id": "1",
                     "explanation": "hello\033[2J\rhidden\x08\u202eevil", "payload": {}}, 1)
        output = stream.getvalue()
        for control in ("\033", "\r", "\x08", "\u202e"):
            self.assertNotIn(control, output)

    def test_interrupted_chat_exits_cleanly(self):
        with patch("lemon.__main__.run_design", side_effect=KeyboardInterrupt), patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["chat", "--delay", "0"]), 130)

    def test_agent_failure_reports_the_error_code(self):
        stream = io.StringIO()
        viewer = ChatViewer(stream=stream, delay=0)
        viewer.event({"kind": "AGENT_FAILED", "data": {"message_id": "m1", "error_code": "INVALID_REVIEW"}})
        self.assertIn("AGENT_FAILED / m1 / INVALID_REVIEW", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
