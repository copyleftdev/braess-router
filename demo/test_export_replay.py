import json
from pathlib import Path
import tempfile
import unittest
from export_replay import export, FLEET_TASKS, DISCOVERY_TASKS
from recording import Recorder


class ExportTests(unittest.TestCase):
    def bundle(self, root, *, scope='synthetic', error='review_validation_failed'):
        recorder=Recorder(root/'recording',scope=scope,metadata={})
        task=next(iter(FLEET_TASKS))
        recorder.append('task_queued',task,document_id=FLEET_TASKS[task],family_id=FLEET_TASKS[task],modality='text')
        recorder.append('request_started',task,input_sha256='a'*64)
        recorder.append('task_uncertain',task,error=error)
        recorder.close()
        return root/'recording'

    def test_fleet_metadata_retains_verified_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.bundle(root)
            export(source,root/'public.json',profile='fleet')
            data=json.loads((root/'public.json').read_bytes())
            self.assertEqual(data['presentation']['profile'],'fleet')
            self.assertEqual(data['events'][-1]['kind'],'task_uncertain')
            self.assertEqual(data['summary']['uncertain'],1)

    def test_arbitrary_error_content_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.bundle(root,error='private text embedded in metadata')
            with self.assertRaises(ValueError):export(source,root/'public.json',profile='fleet')
            self.assertFalse((root/'public.json').exists())

    def test_live_scope_is_refused_even_with_fixture_identifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.bundle(root,scope='live')
            with self.assertRaises(ValueError):export(source,root/'public.json',profile='fleet')

    def test_fleet_requires_explicit_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.bundle(root)
            with self.assertRaises(ValueError):export(source,root/'public.json')

    def test_discovery_fixture_identity_requires_discovery_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recorder=Recorder(root/'recording',scope='synthetic',metadata={})
            task=list(DISCOVERY_TASKS)[-1];document=DISCOVERY_TASKS[task]
            recorder.append('task_queued',task,document_id=document,family_id=document,modality='text')
            recorder.append('task_deferred',task,reason='budget_admission_refused');recorder.close()
            with self.assertRaises(ValueError):export(root/'recording',root/'wrong.json',profile='fleet')
            export(root/'recording',root/'public.json',profile='discovery')
            self.assertEqual(json.loads((root/'public.json').read_bytes())['summary']['deferred'],1)

    def test_discovery_model_labels_remain_allowlisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recorder=Recorder(root/'recording',scope='synthetic',metadata={})
            task=next(iter(DISCOVERY_TASKS));document=DISCOVERY_TASKS[task]
            recorder.append('task_queued',task,document_id=document,family_id=document,modality='text')
            recorder.append('request_started',task,input_sha256='a'*64)
            recorder.append('response_received',task,http_status=200,response_sha256='b'*64,elapsed_ms=1,
                            route='review_standard',generation_model='private-provider-label')
            recorder.append('task_uncertain',task,error='review_validation_failed');recorder.close()
            with self.assertRaises(ValueError):export(root/'recording',root/'public.json',profile='discovery')
            self.assertFalse((root/'public.json').exists())


if __name__=='__main__':unittest.main()
