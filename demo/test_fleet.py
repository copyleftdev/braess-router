import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fleet import run
from budget import Budget
from recording import canonical, digest


class FleetPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.corpus=self.root/'corpus';self.corpus.mkdir()
        self.budget=Budget.create(self.root/'budget',cap_usd='0.01',max_attempts=1,pricing_sha256='d'*64)
        self.manifest={'complete':True,'documents':[{'document_id':'doc','source_sha256':'a'*64}]}
        raw=canonical(self.manifest);(self.corpus/'manifest.json').write_bytes(raw)
        self.task={'task_id':'b'*64,'document_id':'doc','source_sha256':'a'*64,'family_id':'f',
                   'request':'request','request_sha256':digest(b'request')}
        self.prepared={'corpus_manifest_sha256':digest(raw),'status':'prepared_not_executed','tasks':[self.task],
                       'protocol_sha256':'c'*64,'protocol_scope':'synthetic_protocol','exceptions':[]}

    def attempt(self):
        path=self.root/'tasks.json';path.write_bytes(canonical(self.prepared))
        with patch('fleet.observe') as observer:
            with self.assertRaises(ValueError):
                run(self.corpus,path,self.root/'out',gateway_url='http://127.0.0.1:1234/route',
                    budget=self.budget,estimate_usd='0.01',scope='synthetic')
            observer.assert_not_called()
        self.assertFalse((self.root/'out').exists())

    def test_request_mutation_refused_before_dispatch(self):
        self.task['request']='mutated';self.attempt()

    def test_path_like_task_id_refused_before_file_access(self):
        self.task['task_id']='../../outside';self.attempt()

    def test_duplicate_tasks_refused(self):
        self.prepared['tasks'].append(dict(self.task));self.attempt()

    def test_corpus_mutation_refused(self):
        (self.corpus/'manifest.json').write_text('{}');self.attempt()


if __name__=='__main__':unittest.main()
