import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from observe import observe
from recording import Recorder, digest, verify, validate_input_evidence
from run_metrics import metrics
from export_replay import export


class ImageReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.text = json.dumps({'schema_version':1,'kind':'vision_reference_v1',
                                'prompt':'PRIVATE PROMPT','pages':[{'sha256':'a'*64},{'sha256':'b'*64}]})
        self.evidence = {'reference_sha256':digest(self.text.encode()),'image_sha256':['a'*64,'b'*64]}

    def record(self, evidence):
        recorder = Recorder(self.root/'recording',scope='synthetic',metadata={})
        recorder.append('task_queued','task-0',document_id='fixture-0',family_id='fixture-0',modality='image')
        response = io.BytesIO(json.dumps({'route':'general','handler_response':{'execution':{
            'input_evidence':evidence},'answer':'PRIVATE ANSWER'}}).encode())
        response.status = 200
        with patch('observe.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            observe(recorder,'task-0','http://127.0.0.1:1234/route',self.text)
        recorder.close()
        return verify(self.root/'recording')

    def test_bound_image_metadata_survives_recording_and_analysis(self):
        result = self.record(self.evidence)
        self.assertEqual(result['events'][2]['data']['generation_input_evidence'],self.evidence)
        report = metrics(self.root/'recording',self.root/'metrics.json')
        self.assertEqual(report['tasks'][0]['generation_input_evidence'],self.evidence)
        self.assertNotIn('PRIVATE', (self.root/'recording/events.jsonl').read_text())
        self.assertNotIn('PRIVATE', (self.root/'metrics.json').read_text())
        with self.assertRaises(ValueError): export(self.root/'recording',self.root/'public.json')
        self.assertFalse((self.root/'public.json').exists())

    def test_mismatched_reference_becomes_uncertain(self):
        result = self.record({**self.evidence,'reference_sha256':'c'*64})
        self.assertEqual(result['summary']['uncertain'],1)
        self.assertFalse(any(e['kind']=='response_received' for e in result['events']))

    def test_reordered_images_become_uncertain(self):
        result = self.record({**self.evidence,'image_sha256':list(reversed(self.evidence['image_sha256']))})
        self.assertEqual(result['summary']['uncertain'],1)

    def test_missing_receipt_stays_unknown(self):
        self.record(None)
        report = metrics(self.root/'recording',self.root/'metrics.json')
        self.assertIsNone(report['tasks'][0]['generation_input_evidence'])

    def test_receipt_shape_cannot_carry_private_content(self):
        for value in [None,{}, {**self.evidence,'prompt':'PRIVATE'},
                      {**self.evidence,'image_sha256':[]}, {**self.evidence,'image_sha256':['a'*64]*9},
                      {**self.evidence,'image_sha256':['https://private.invalid']},
                      {**self.evidence,'reference_sha256':True}]:
            with self.subTest(value=value), self.assertRaises(ValueError): validate_input_evidence(value)


if __name__ == '__main__': unittest.main()
