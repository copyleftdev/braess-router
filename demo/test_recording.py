import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from recording import Recorder, verify


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'run'
        self.r = Recorder(self.path, scope='synthetic', metadata={})
        self.addCleanup(self.r.close)

    def queue(self, task='t'):
        self.r.append('task_queued', task, document_id='doc', family_id='family', modality='text')

    def test_concurrent_records_have_single_verified_order(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: self.queue(str(i)), range(100)))
        self.r.close()
        result = verify(self.path)
        self.assertEqual(result['summary']['incomplete'], 100)
        self.assertEqual([e['seq'] for e in result['events']], list(range(1, 101)))

    def test_tamper_reorder_and_torn_tail_fail(self):
        self.queue('a'); self.queue('b'); self.r.close()
        path = self.path / 'events.jsonl'
        data = path.read_bytes()
        for invalid in [data.replace(b'family', b'changed', 1), b'\n'.join(reversed(data.splitlines()))+b'\n', data[:-1], data.splitlines()[0]+b'\n']:
            path.write_bytes(invalid)
            with self.assertRaises(ValueError):
                verify(self.path)
        path.write_bytes(data)

    def test_incomplete_run_is_not_completed(self):
        self.queue()
        self.r.append('request_started', 't', input_sha256='a'*64)
        with self.assertRaises(ValueError):
            verify(self.path)
        result = verify(self.path, allow_unsealed=True)
        self.assertFalse(result['sealed'])
        self.assertEqual(result['summary']['incomplete'], 1)
        self.assertIsNone(result['summary']['total_cost_usd'])

    def test_invalid_transition_and_private_fields_rejected(self):
        with self.assertRaises(ValueError):
            self.r.append('task_completed', 't', outcome='handler_completed')
        self.queue()
        with self.assertRaises(ValueError):
            self.queue()
        with self.assertRaises(ValueError):
            self.r.append('request_started', 't', input_sha256='a'*64, prompt='private')

    def test_seal_does_not_imply_every_task_completed(self):
        self.queue(); self.r.close()
        self.assertEqual(verify(self.path)['summary']['incomplete'], 1)
        with self.assertRaises(FileExistsError):
            Recorder(self.path, scope='synthetic', metadata={})

    def test_decimal_cost_and_unknown_total(self):
        self.queue()
        self.r.append('request_started', 't', input_sha256='a'*64)
        self.r.append('response_received', 't', http_status=200, response_sha256='b'*64,
                      elapsed_ms=1, generation_cost_usd='0.0000019')
        self.r.append('task_completed', 't', outcome='handler_completed')
        self.r.close()
        result = verify(self.path)['summary']
        self.assertEqual(result['reported_generation_cost_usd'], '0.0000019')
        self.assertIsNone(result['total_cost_usd'])


if __name__ == '__main__':
    unittest.main()
