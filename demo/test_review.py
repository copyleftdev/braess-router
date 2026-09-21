import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from review import prompt, redact, validate


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'objects').mkdir()
        self.text='A café memo. Secret account 123. Another 123.'
        digest=hashlib.sha256(self.text.encode()).hexdigest()
        self.document={'document_id':'3.1.A','source_sha256':digest}
        (self.root/'objects'/(digest+'.txt')).write_text(self.text)
        self.report={'schema_version':1,**self.document,'responsiveness':'responsive','findings':[
            {'id':'issue1','kind':'issue_highlight','start':2,'end':6,'quote':'café','note':'Relevant passage.'},
            {'id':'private1','kind':'privacy_candidate','start':28,'end':31,'quote':'123','note':'Account candidate.'}]}

    def wire(self):return json.dumps(self.report).encode()

    def test_valid_report_preserves_verified_source_offsets(self):
        result=validate(self.root,self.document,self.wire())
        self.assertEqual(result['findings'][0]['location']['end_byte'],7)
        self.assertFalse(result['publication_approved'])

    def test_wrong_source_and_hallucinated_quotes_rejected(self):
        self.report['findings'][0]['quote']='fake'
        with self.assertRaises(ValueError):validate(self.root,self.document,self.wire())
        self.report['source_sha256']='a'*64
        with self.assertRaises(ValueError):validate(self.root,self.document,self.wire())

    def test_unknown_fields_duplicate_keys_and_unjustified_responsiveness(self):
        original=self.wire()
        with self.assertRaises(ValueError):validate(self.root,self.document,original.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1'))
        self.report['execute']='send email'
        with self.assertRaises(ValueError):validate(self.root,self.document,self.wire())
        del self.report['execute'];self.report['findings']=[]
        with self.assertRaises(ValueError):validate(self.root,self.document,self.wire())

    def test_draft_removes_selected_span_preserves_original_flags_repeats(self):
        receipt=redact(self.root,self.document,self.wire(),self.root/'draft',approved_ids=['private1'])
        output=(self.root/'draft/redacted.txt').read_text()
        self.assertIn('account [REDACTED]',output)
        self.assertIn('Another 123.',output)
        self.assertEqual(receipt['residual_exact_quote_ids'],['private1'])
        self.assertEqual((self.root/'objects'/(self.document['source_sha256']+'.txt')).read_text(),self.text)
        self.assertFalse(receipt['publication_approved'])

    def test_redaction_requires_specific_candidate_approval(self):
        for ids in ([],['issue1'],['unknown'],['private1','private1']):
            with self.assertRaises(ValueError):redact(self.root,self.document,self.wire(),self.root/'draft',approved_ids=ids)
        self.assertFalse((self.root/'draft').exists())

    def test_overlaps_are_removed_once(self):
        self.report['findings'].append({'id':'private2','kind':'privacy_candidate','start':20,'end':31,'quote':'account 123','note':'Wider candidate.'})
        receipt=redact(self.root,self.document,self.wire(),self.root/'draft',approved_ids=['private1','private2'])
        self.assertEqual(receipt['removed_character_ranges'],[[20,31]])
        self.assertEqual((self.root/'draft/redacted.txt').read_text().count('[REDACTED]'),1)

    def test_prompt_is_bounded_and_source_identified(self):
        value=json.loads(prompt(self.root,self.document,production_request='Find discussions of café agreements.'))
        self.assertEqual(value['evidence_text'],self.text)
        self.assertEqual(value['source_sha256'],self.document['source_sha256'])


if __name__=='__main__':unittest.main()
