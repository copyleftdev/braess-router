from pathlib import Path
import tempfile
import unittest
from export_replay import export
from recording import Recorder


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def record(self, scope='synthetic', document='fixture-0'):
        recorder = Recorder(self.path / 'run', scope=scope, metadata={})
        recorder.append('task_queued', 'task-0', document_id=document,
                        family_id='fixture-0', modality='text')
        recorder.close()

    def test_live_export_requires_future_review_gate(self):
        self.record(scope='live')
        with self.assertRaises(ValueError):
            export(self.path/'run', self.path/'public.json')
        self.assertFalse((self.path/'public.json').exists())

    def test_unknown_source_id_cannot_enter_fixture_export(self):
        self.record(document='private-client-name')
        with self.assertRaises(ValueError):
            export(self.path/'run', self.path/'public.json')

    def test_unverified_event_cannot_be_exported(self):
        self.record()
        events = self.path/'run/events.jsonl'
        events.write_bytes(events.read_bytes().replace(b'fixture-0', b'fixture-1'))
        with self.assertRaises(ValueError):
            export(self.path/'run', self.path/'public.json')

    def test_verified_export_keeps_incomplete_count_and_scope(self):
        import json
        self.record()
        export(self.path/'run', self.path/'public.json')
        result=json.loads((self.path/'public.json').read_text())
        self.assertEqual(result['summary']['incomplete'], 1)
        self.assertEqual(result['run']['scope'], 'synthetic')
        self.assertEqual(result['presentation']['internal_decision_timing'], 'not_observed')


if __name__ == '__main__':
    unittest.main()
