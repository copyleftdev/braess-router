import json
import unittest
from evidence_bundle import build
from recording import Recorder, canonical, digest
from vision_link import link
import test_review_link as fixtures


@unittest.skipIf(fixtures.Image is None,'optional Pillow required')
class VisionLinkTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.OCRReviewLinkTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.inspector=self.root/'inspector'
        build(self.fixture.corpus/'manifest.json',self.fixture.doc['document_id'],self.inspector)
        raw=(self.inspector/'manifest.json').read_bytes();m=json.loads(raw);p=m['pages'][0]
        self.reference={'schema_version':1,'kind':'vision_reference_v1','document_id':m['document_id'],
            'native_source_sha256':m['native_source_sha256'],'inspector_manifest_sha256':digest(raw),
            'prompt':'PRIVATE PROMPT','pages':[{k:p[k] for k in ('page','sha256','width','height')} |
                {'bytes':len((self.inspector/p['file']).read_bytes())}]}
        self.path=self.root/'reference.json';self.path.write_bytes(canonical(self.reference))

    def record(self, *, document=None, receipt=True):
        r=Recorder(self.root/'recording',scope='synthetic',metadata={})
        r.append('task_queued','task',document_id=document or self.reference['document_id'],family_id='fixture',modality='image')
        r.append('request_started','task',input_sha256='a'*64)
        extra={'generation_input_evidence':{'reference_sha256':digest(self.path.read_bytes()),
               'image_sha256':[p['sha256'] for p in self.reference['pages']]}} if receipt else {}
        r.append('response_received','task',http_status=200,response_sha256='b'*64,elapsed_ms=1,**extra)
        r.append('task_completed','task',outcome='handler_completed');r.close()

    def check(self):return link(self.root/'recording',self.path,self.inspector,'task')

    def test_binds_exact_receipt_and_pixels_without_prompt_or_quality_claim(self):
        self.record();result=self.check()
        self.assertEqual(result['pages'],self.reference['pages'])
        self.assertEqual(result['reference_sha256'],digest(self.path.read_bytes()))
        self.assertFalse(result['model_understanding_established'])
        self.assertFalse(result['publication_approved'])
        self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertGreater(result['input_visibility_after_elapsed_ns'],0)

    def test_even_whitespace_change_breaks_reference_binding(self):
        self.record();self.path.write_bytes(self.path.read_bytes()+b'\n')
        with self.assertRaises(ValueError):self.check()

    def test_wrong_task_document_cannot_gain_page_association(self):
        self.record(document='other')
        with self.assertRaises(ValueError):self.check()

    def test_legacy_missing_receipt_cannot_gain_page_association(self):
        self.record(receipt=False)
        with self.assertRaises(ValueError):self.check()

    def test_changed_page_refused(self):
        self.record();(self.inspector/'page-1.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.check()

    def test_incorrect_geometry_refused_even_with_matching_receipt(self):
        self.reference['pages'][0]['width']+=1;self.path.write_bytes(canonical(self.reference));self.record()
        with self.assertRaises(ValueError):self.check()

    def test_duplicate_selection_refused_even_with_matching_receipt(self):
        self.reference['pages']*=2;self.path.write_bytes(canonical(self.reference));self.record()
        with self.assertRaises(ValueError):self.check()
