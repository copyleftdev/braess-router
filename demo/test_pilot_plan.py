from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import unittest
import test_review_link as source_fixture
import test_pricing_quote as pricing_fixture
from pilot_plan import create,verify
from prepare_review import prepare
from recording import canonical,digest


class PilotPlanTests(unittest.TestCase):
    def setUp(self):
        source_fixture.ReviewLinkTests.setUp(self)
        manifest=json.loads((self.corpus/'manifest.json').read_bytes())
        manifest['documents'].append({**self.doc,'document_id':'3.2.A','family_id':'3.2.A'})
        (self.corpus/'manifest.json').write_bytes(canonical(manifest))
        prepare(self.corpus,self.root/'protocol.json',self.root/'two-tasks')
        self.tasks=self.root/'two-tasks/tasks.json'
        self.sources=self.root/'prices';self.sources.mkdir();self.now=datetime.now(timezone.utc)
        pricing_fixture.PricingTests.fixture(self,self.sources,self.now)
        self.rubric=Path(__file__).resolve().parent.parent/'eval/rubric.discovery.json'
        self.output=self.root/'plan'

    def make(self):return create(self.corpus,self.tasks,self.sources,self.rubric,self.output,now=self.now)

    def test_plan_binds_routes_and_limits_without_authorizing(self):
        result=self.make();self.assertEqual(verify(self.output,now=self.now),result)
        self.assertEqual(result['task_count'],2);self.assertIsNone(result['selected_allowance_usd'])
        adapter=json.loads((self.output/'adapter.json').read_bytes())
        self.assertEqual(adapter['max_calls'],2)
        self.assertEqual(adapter['routes']['review_standard']['provider'],'google-vertex/eu')
        self.assertEqual(adapter['routes']['review_deep']['max_tokens'],2048)
        self.assertFalse((self.output/'generation.jsonl').exists())
        self.assertFalse((self.output/'jev.budget').exists())

    def test_stale_quote_prevents_reuse(self):
        self.make()
        with self.assertRaises(ValueError):verify(self.output,now=self.now+timedelta(hours=25))

    def test_rehashed_config_still_must_match_priced_limits(self):
        self.make();path=self.output/'adapter.json';config=json.loads(path.read_bytes())
        config['routes']['review_deep']['provider']='other-provider';path.write_bytes(canonical(config))
        manifest=json.loads((self.output/'plan.json').read_bytes());manifest['files']['adapter.json']=digest(path.read_bytes())
        (self.output/'plan.json').write_bytes(canonical(manifest))
        with self.assertRaises(ValueError):verify(self.output,now=self.now)

    def test_source_change_is_detected(self):
        self.make();(self.corpus/'objects'/(self.doc['source_sha256']+'.txt')).write_bytes(b'changed')
        with self.assertRaises(ValueError):verify(self.output,now=self.now)

    def test_wrong_task_count_is_rejected_before_writing(self):
        tasks=json.loads(self.tasks.read_bytes());tasks['tasks']=tasks['tasks'][:1];self.tasks.write_bytes(canonical(tasks))
        with self.assertRaises(ValueError):self.make()
        self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
