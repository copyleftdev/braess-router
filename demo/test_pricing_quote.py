from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from pricing_quote import endpoint_quote, plan


def snapshot(model='google/gemini-2.5-flash', **changes):
    endpoint={'tag':'google-vertex/eu','status':0,'context_length':100,
              'max_completion_tokens':20,'supported_parameters':['max_tokens'],
              'pricing':{'prompt':'0.0000003','completion':'0.0000025','internal_reasoning':'0.0000025','discount':0}}
    endpoint.update(changes)
    return json.dumps({'data':{'id':model,'architecture':{'input_modalities':['text'],'output_modalities':['text']},
                              'endpoints':[endpoint]}}).encode()


class PricingTests(unittest.TestCase):
    def test_full_capacity_scenario_keeps_reasoning_separate(self):
        q=endpoint_quote(snapshot(),model='google/gemini-2.5-flash',provider='google-vertex/eu',max_tokens=10)
        self.assertEqual(q['capacity_scenario_usd'],'0.0001300')
        self.assertEqual(q['components_usd']['reasoning'],'0.0000500')
        self.assertEqual(q['requested_max_tokens'],10)
        self.assertEqual(q['completion_capacity'],20)

    def test_base_provider_cannot_pick_the_cheapest_variant(self):
        with self.assertRaises(ValueError):endpoint_quote(snapshot(),model='google/gemini-2.5-flash',provider='google-vertex',max_tokens=10)

    def test_unavailable_or_unknown_charge_refuses_quote(self):
        for changes in [{'status':-5},{'supported_parameters':[]},{'max_completion_tokens':None},
                        {'pricing':{'prompt':'0.1','completion':'0.2','surprise_fee':'0.3'}},
                        {'pricing':{'prompt':0.1,'completion':'0.2'}},
                        {'pricing':{'prompt':'NaN','completion':'0.2'}}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                endpoint_quote(snapshot(**changes),model='google/gemini-2.5-flash',provider='google-vertex/eu',max_tokens=10)

    def fixture(self,root,now):
        sources={'observed_at':now.isoformat(),'files':{},'decision':{'model':'jev-1.13.0',
            'source_url':'https://docs.typesafe.ai/models','source_sha256':hashlib.sha256(b'fixture documentation').hexdigest(),
            'max_input_tokens':64000,'input_usd_per_token':'0.000000042','output_usd_per_token':'0'}}
        (root/'typesafe-models.html').write_bytes(b'fixture documentation')
        for filename,model in [('flash-lite.json','google/gemini-2.5-flash-lite'),('flash.json','google/gemini-2.5-flash')]:
            raw=snapshot(model,context_length=10000,max_completion_tokens=4000)
            (root/filename).write_bytes(raw)
            sources['files'][filename]={'url':'https://openrouter.ai/api/v1/models/'+model+'/endpoints',
                                       'sha256':hashlib.sha256(raw).hexdigest()}
        (root/'sources.json').write_text(json.dumps(sources))

    def test_stale_source_or_changed_snapshot_refuses_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=datetime.now(timezone.utc);self.fixture(root,now)
            q=plan(root,now=now)
            self.assertEqual(q['per_task_reservation_usd'],'0.03211')
            self.assertFalse(q['invoice_ceiling_guaranteed'])
            with self.assertRaises(ValueError):plan(root,now=now+timedelta(hours=25))
            with self.assertRaises(ValueError):plan(root,now=now-timedelta(seconds=1))
            (root/'flash.json').write_bytes(snapshot())
            with self.assertRaises(ValueError):plan(root,now=now)


if __name__=='__main__':unittest.main()
