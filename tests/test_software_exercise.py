import unittest
from unittest.mock import patch

from lemon.events import replay
from lemon.software_exercise import HttpDemo, run_exercise, valid_body


class SoftwareExerciseTests(unittest.TestCase):
    def test_only_loopback_origins_and_no_arbitrary_path(self):
        for url in ('https://127.0.0.1:3001', 'http://example.com', 'http://user:pass@localhost',
                    'http://localhost/other', 'http://localhost?x=1', 'file:///etc/passwd'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                HttpDemo(url)
        HttpDemo('http://127.0.0.1:3301')

    def test_request_contract_does_not_coerce_types(self):
        self.assertEqual(valid_body('{"scenario":"normal"}'), {'scenario': 'normal'})
        for body in ('{"scenario":["normal"]}', '{"scenario":[]}', '{"scenario":null}',
                     '{"scenario":{"value":"normal"}}', '{"scenario":12}', 'null', '[]',
                     '{"scenario":"normal","amount":100}', '{"scenario":"other"}', '{'):
            with self.subTest(body=body):
                self.assertIsNone(valid_body(body))

    def test_checker_detects_bad_software_without_trusting_its_own_checks(self):
        class BadApi:
            def __init__(self, *args): pass
            def send(self, method, path, body=None):
                if path == '/api/health':
                    return {'status': 200, 'body': {'status': 'ok', 'service': 'lemonade-api'}}
                return {'status': 201 if method == 'PUT' else 200, 'body': {'status': 'completed', 'checks': {'passed': True}}}
        actions = [{'operation': 'submit', 'slot': 'primary', 'body_json': '{"scenario":["normal"]}', 'reason': 'Probe strict type validation.'}]
        with patch('lemon.software_exercise.HttpDemo', BadApi):
            run = run_exercise('http://127.0.0.1', actions=actions)
        self.assertFalse(run['quality']['passed'])
        self.assertEqual(run['quality']['failures'], [0])
        self.assertFalse(run['final_state']['history'][0]['checks']['invalid_input_did_not_create_transfer'])
        self.assertEqual(replay(run['events']), run['final_state'])

    def test_actor_cannot_choose_a_path_or_an_unowned_identity(self):
        class Api:
            def __init__(self, *args): pass
            def send(self, method, path, body=None):
                assert path == '/api/health'
                return {'status': 200, 'body': {'status': 'ok', 'service': 'lemonade-api'}}
        with patch('lemon.software_exercise.HttpDemo', Api):
            run = run_exercise('http://127.0.0.1', actions=[{
                'operation': 'recover', 'slot': '../../other', 'body_json': '', 'reason': 'Invalid identity.'}])
        self.assertFalse(run['quality']['passed'])
        self.assertEqual(run['error'], 'Invalid replay action')
        self.assertEqual(run['replay_actions'], [])

    def test_changed_receipt_is_detected_despite_successful_http_responses(self):
        class ChangingReceipt:
            def __init__(self, *args): self.count = 0
            def send(self, method, path, body=None):
                if path == '/api/health':
                    return {'status': 200, 'body': {'status': 'ok', 'service': 'lemonade-api'}}
                self.count += 1
                identity = path.split('/')[3]
                return {'status': 201 if method == 'PUT' else 200, 'body': {
                    'id': identity, 'amountSen': 10000, 'status': 'completed',
                    'receipt': {'id': str(self.count), 'transferId': identity, 'amountSen': 10000, 'outcome': 'completed'}}}
        actions = [{'operation': 'submit', 'slot': 'primary', 'body_json': '{"scenario":"normal"}', 'reason': 'Submit.'},
                   {'operation': 'recover', 'slot': 'primary', 'body_json': '', 'reason': 'Recover.'}]
        with patch('lemon.software_exercise.HttpDemo', ChangingReceipt):
            run = run_exercise('http://127.0.0.1', actions=actions)
        self.assertEqual(run['quality']['failures'], [1])
        checks = run['final_state']['history'][1]['checks']
        self.assertTrue(checks['http_contract'])
        self.assertFalse(checks['stable_receipt'])


if __name__ == '__main__':
    unittest.main()
