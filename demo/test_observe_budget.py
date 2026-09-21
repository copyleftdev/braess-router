from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from budget import Budget, BudgetError
from observe import observe
from recording import Recorder, verify


class ObserverBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recorder = Recorder(self.root/'recording', scope='live', metadata={})
        self.addCleanup(self.recorder.close)
        self.recorder.append('task_queued', 't', document_id='d', family_id='f', modality='text')

    def test_live_dispatch_without_budget_is_refused_before_network(self):
        with patch('observe.urllib.request.build_opener') as opener:
            with self.assertRaises(ValueError):
                observe(self.recorder, 't', 'http://127.0.0.1:1234/route', 'private')
            opener.assert_not_called()
        self.assertEqual(self.recorder.sequence, 1)

    def test_exhausted_budget_refuses_dispatch_without_network(self):
        budget = Budget.create(self.root/'budget', cap_usd='0.01', max_attempts=2, pricing_sha256='a'*64)
        budget.reserve('previous', request_sha256='b'*64, estimate_usd='0.01')
        with patch('observe.urllib.request.build_opener') as opener:
            with self.assertRaises(BudgetError):
                observe(self.recorder, 't', 'http://127.0.0.1:1234/route', 'private',
                        budget=budget, estimate_usd='0.01')
            opener.assert_not_called()
        self.assertEqual(budget.inspect()['attempts'], 1)

    def test_transport_failure_retains_reservation_and_trace_link(self):
        budget = Budget.create(self.root/'budget', cap_usd='0.01', max_attempts=2, pricing_sha256='a'*64)
        with patch('observe.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = OSError('private diagnostic')
            observe(self.recorder, 't', 'http://127.0.0.1:1234/route', 'private',
                    budget=budget, estimate_usd='0.01')
        self.recorder.close()
        result = verify(self.root/'recording')
        self.assertEqual(result['summary']['uncertain'], 1)
        self.assertEqual(result['events'][1]['data']['budget_attempt_id'], budget.inspect()['pending'][0]['attempt_id'])
        self.assertEqual(budget.inspect()['available_usd'], '0')
        self.assertNotIn('private', (self.root/'recording/events.jsonl').read_text())


if __name__ == '__main__':
    unittest.main()
