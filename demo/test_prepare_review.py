import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from prepare_review import prepare


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.corpus=self.root/'corpus';(self.corpus/'objects').mkdir(parents=True)
        self.documents=[]
        for i,text in enumerate(['A short business note.','Long evidence. '*3000]):
            digest=hashlib.sha256(text.encode()).hexdigest()
            (self.corpus/'objects'/(digest+'.txt')).write_text(text)
            self.documents.append({'document_id':f'3.{i}.A','family_id':f'3.{i}.A','source_sha256':digest,
                                   'judgments':[{'assessment':1,'secret_gold_label':'not_for_model'}]})
        (self.corpus/'manifest.json').write_text(json.dumps({'complete':True,'documents':self.documents}))
        self.protocol=self.root/'protocol.json'
        self.protocol.write_text(json.dumps({'id':'exercise','version':'1','scope':'synthetic_protocol','production_request':'Identify business notes.'}))

    def test_preparation_keeps_oversized_exception_and_excludes_gold_labels(self):
        result=prepare(self.corpus,self.protocol,self.root/'tasks')
        self.assertEqual(len(result['tasks']),1)
        self.assertEqual(result['exceptions'],[{'document_id':'3.1.A','reason':'requires_chunking'}])
        self.assertNotIn('secret_gold_label',result['tasks'][0]['request'])
        self.assertEqual(result['provider_calls'],0)
        self.assertEqual(result['status'],'prepared_not_executed')

    def test_task_identity_is_stable_for_the_same_protocol(self):
        first=prepare(self.corpus,self.protocol,self.root/'a')
        second=prepare(self.corpus,self.protocol,self.root/'b')
        self.assertEqual(first['tasks'][0]['task_id'],second['tasks'][0]['task_id'])

    def test_modified_source_stops_preparation(self):
        digest=self.documents[0]['source_sha256']
        (self.corpus/'objects'/(digest+'.txt')).write_text('tampered')
        with self.assertRaises(ValueError):prepare(self.corpus,self.protocol,self.root/'tasks')
        self.assertFalse((self.root/'tasks/tasks.json').exists())


if __name__=='__main__':unittest.main()
