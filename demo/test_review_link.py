import json
from pathlib import Path
import tempfile
import unittest
from prepare_review import prepare
from recording import Recorder, canonical, digest
from review import validate
from review_link import link


class ReviewLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.corpus=self.root/'corpus';(self.corpus/'objects').mkdir(parents=True)
        text=b'An energy meeting.';sha=digest(text)
        self.doc={'document_id':'3.1.A','family_id':'3.1.A','source_sha256':sha,'modality':'text'}
        (self.corpus/'objects'/(sha+'.txt')).write_bytes(text)
        raw=canonical({'complete':True,'documents':[self.doc]});self.corpus_hash=digest(raw)
        (self.corpus/'manifest.json').write_bytes(raw)
        protocol=self.root/'protocol.json';protocol.write_bytes(canonical({'id':'test','version':'1','production_request':'Find energy meetings.','scope':'synthetic_protocol'}))
        self.prepared=prepare(self.corpus,protocol,self.root/'prepared');self.tasks=self.root/'prepared/tasks.json'
        self.task=self.prepared['tasks'][0];self.run=self.root/'run';(self.run/'private').mkdir(parents=True)
        self.report={'schema_version':1,'document_id':'3.1.A','source_sha256':sha,'responsiveness':'responsive',
                     'findings':[{'id':'one','kind':'issue_highlight','start':3,'end':9,'quote':'energy','note':'Synthetic test finding.'}]}
        answer=canonical(self.report)
        self.response=canonical({'route':'review_standard','handler_response':{'answer':answer.decode()}})
        self.review=canonical(validate(self.corpus,self.doc,answer))
        (self.run/'private'/(self.task['task_id']+'.response.json')).write_bytes(self.response)
        (self.run/'private'/(self.task['task_id']+'.review.json')).write_bytes(self.review)
        self.inputs={'tasks_sha256':digest(self.tasks.read_bytes()),'corpus_manifest_sha256':self.corpus_hash,
                     'protocol_sha256':self.prepared['protocol_sha256'],'protocol_scope':self.prepared['protocol_scope']}
        (self.run/'input-manifest.json').write_bytes(canonical(self.inputs))

    def record(self, *, uncertain=False, queued_id='3.1.A', input_hash=None, review_hash=None):
        r=Recorder(self.run/'recording',scope='synthetic',metadata={'corpus_manifest_sha256':self.corpus_hash})
        tid=self.task['task_id']
        r.append('task_queued',tid,document_id=queued_id,family_id='3.1.A',modality='text')
        r.append('request_started',tid,input_sha256=input_hash or digest(json.dumps({'request':self.task['request']}).encode()))
        r.append('response_received',tid,http_status=200,response_sha256=digest(self.response),elapsed_ms=1,route='review_standard')
        if uncertain:r.append('task_uncertain',tid,error='review_validation_failed')
        else:
            r.append('review_validated',tid,review_sha256=review_hash or digest(self.review),finding_count=1)
            r.append('task_completed',tid,outcome='review_validated')
        r.close()

    def check(self):return link(self.corpus,self.tasks,self.run,self.task['task_id'])

    def test_verified_link_preserves_scope_and_event_visibility(self):
        self.record();result=self.check()
        self.assertEqual(result['scope'],'synthetic')
        self.assertEqual(result['review']['findings'][0]['quote'],'energy')
        self.assertEqual(result['finding_visibility_after_elapsed_ns'],result['events'][3]['elapsed_ns'])
        self.assertFalse(result['publication_approved'])
        self.assertIsNone(result['inspector_manifest_sha256'])

    def test_response_artifact_tampering_refused(self):
        self.record();(self.run/'private'/(self.task['task_id']+'.response.json')).write_bytes(b'{}')
        with self.assertRaises(ValueError):self.check()

    def test_recorded_review_must_reproduce_from_response(self):
        changed=json.loads(self.review);changed['findings'][0]['quote']='invented'
        tampered=canonical(changed);(self.run/'private'/(self.task['task_id']+'.review.json')).write_bytes(tampered)
        self.record(review_hash=digest(tampered))
        with self.assertRaises(ValueError):self.check()

    def test_task_from_other_document_refused(self):
        self.record(queued_id='3.2.A')
        with self.assertRaises(ValueError):self.check()

    def test_request_from_other_run_refused(self):
        self.record(input_hash='a'*64)
        with self.assertRaises(ValueError):self.check()

    def test_uncertain_review_cannot_gain_source_link(self):
        self.record(uncertain=True)
        with self.assertRaises(ValueError):self.check()

    def test_prepared_task_mutation_refused(self):
        self.record();self.tasks.write_bytes(b'{}')
        with self.assertRaises(ValueError):self.check()


try:
    from PIL import Image
except ImportError:
    Image=None


@unittest.skipIf(Image is None,'optional Pillow required')
class OCRReviewLinkTests(ReviewLinkTests):
    def setUp(self):
        super().setUp()
        import io
        encoded=io.BytesIO();Image.new('RGB',(100,100),'white').save(encoded,format='TIFF')
        native=encoded.getvalue();native_sha=digest(native)
        mapping={'source_sha256':native_sha,'text_sha256':self.doc['source_sha256'],
                 'normalization':'ocr-tsv-word-join-v1','pages':{'1':{'width':100,'height':100}},
                 'words':[{'page':1,'start_character':0,'end_character':2,'box':[0,0,10,10],'confidence':90},
                          {'page':1,'start_character':3,'end_character':9,'box':[10,0,30,10],'confidence':80},
                          {'page':1,'start_character':10,'end_character':18,'box':[40,0,40,10],'confidence':70}]}
        mapping_raw=canonical(mapping)
        (self.corpus/'objects'/(native_sha+'.bin')).write_bytes(native)
        (self.corpus/'objects'/(digest(mapping_raw)+'.ocr.json')).write_bytes(mapping_raw)
        self.doc.update(modality='image',representation='ocr_text',normalization='ocr-tsv-word-join-v1',
                        native_source_sha256=native_sha,ocr_mapping_sha256=digest(mapping_raw))
        raw=canonical({'complete':True,'documents':[self.doc]});self.corpus_hash=digest(raw)
        (self.corpus/'manifest.json').write_bytes(raw)
        self.prepared=prepare(self.corpus,self.root/'protocol.json',self.root/'ocr-prepared')
        self.tasks=self.root/'ocr-prepared/tasks.json';self.task=self.prepared['tasks'][0]
        self.review=canonical(validate(self.corpus,self.doc,canonical(self.report)))
        (self.run/'private'/(self.task['task_id']+'.review.json')).write_bytes(self.review)
        self.inputs.update(tasks_sha256=digest(self.tasks.read_bytes()),corpus_manifest_sha256=self.corpus_hash)
        (self.run/'input-manifest.json').write_bytes(canonical(self.inputs))

    def record(self, **kwargs):
        # Base recorder uses text modality; generate then retain a valid image chain
        # through the same recorder API instead of modifying a sealed log.
        from unittest.mock import patch
        original=Recorder.append
        def append(recorder,kind,task_id,**data):
            if kind=='task_queued':data['modality']='image'
            return original(recorder,kind,task_id,**data)
        with patch.object(Recorder,'append',append):super().record(**kwargs)

    def test_inspector_assets_must_reproduce_from_native_source(self):
        from evidence_bundle import build
        self.record();inspector=self.root/'inspector'
        build(self.corpus/'manifest.json',self.doc['document_id'],inspector)
        result=link(self.corpus,self.tasks,self.run,self.task['task_id'],inspector=inspector)
        self.assertEqual(result['review']['findings'][0]['location']['image_regions'][0]['box'],[10,0,30,10])
        self.assertIsNotNone(result['inspector_manifest_sha256'])
        # Self-consistent forged manifest hashes must not legitimize different pixels.
        Image.new('RGBA',(100,100),'black').save(inspector/'page-1.png')
        manifest=json.loads((inspector/'manifest.json').read_bytes())
        raw=(inspector/'page-1.png').read_bytes();manifest['pages'][0].update(sha256=digest(raw),bytes=len(raw))
        (inspector/'manifest.json').write_bytes(canonical(manifest))
        with self.assertRaises(ValueError):link(self.corpus,self.tasks,self.run,self.task['task_id'],inspector=inspector)


if __name__=='__main__':unittest.main()
