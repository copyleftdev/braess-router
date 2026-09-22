import json
import unittest
import test_review_link as fixtures
from adjudication import prepare,resolve
from recording import canonical,digest


class AdjudicationTests(unittest.TestCase):
    setUp=fixtures.ReviewLinkTests.setUp
    record=fixtures.ReviewLinkTests.record

    def prepare(self,uncertain=False):
        self.record(uncertain=uncertain);self.queue=self.root/'queue.json'
        return prepare(self.corpus,self.tasks,self.run,self.queue)

    def decision(self,queue,**changes):
        entry=queue['entries'][0]
        item={'task_id':entry['task_id'],'review_sha256':entry['review_sha256'],
              'outcome':'confirm_review','note':'Synthetic test assessment, not a real human judgment.'}
        item.update(changes)
        return {'queue_sha256':digest(self.queue.read_bytes()),'reviewer_id':'fixture-reviewer','decisions':[item]}

    def resolve(self,decisions):
        path=self.root/'decisions.json';path.write_bytes(canonical(decisions))
        return resolve(self.corpus,self.tasks,self.run,self.queue,path,self.root/'assessment.json')

    def test_pending_queue_never_invents_human_decisions(self):
        queue=self.prepare();self.assertEqual(queue['entries'][0]['status'],'awaiting_human')
        self.assertIsNone(queue['entries'][0]['decision'])
        self.assertEqual(queue['entries'][0]['review']['findings'][0]['quote'],'energy')
        self.assertEqual(self.queue.stat().st_mode & 0o777,0o600)

    def test_supplied_assessment_is_bound_and_not_redaction_approval(self):
        queue=self.prepare();before=(self.run/'recording/events.jsonl').read_bytes()
        result=self.resolve(self.decision(queue))
        self.assertEqual(result['assessed'],1);self.assertEqual(result['unresolved'],0)
        self.assertFalse(result['redactions_approved']);self.assertFalse(result['publication_approved'])
        self.assertFalse(result['reviewer_identity_authenticated'])
        self.assertEqual(before,(self.run/'recording/events.jsonl').read_bytes())
        with self.assertRaises(FileExistsError):self.resolve(self.decision(queue))

    def test_missing_review_remains_unresolved(self):
        queue=self.prepare(uncertain=True)
        with self.assertRaises(ValueError):self.resolve(self.decision(queue))
        result=self.resolve(self.decision(queue,outcome='needs_more_context'))
        self.assertEqual(result['unresolved'],1);self.assertEqual(result['assessed'],0)

    def test_wrong_queue_or_review_hash_rejected(self):
        queue=self.prepare()
        for changed in [dict(queue_sha256='a'*64),dict(decisions=[{**self.decision(queue)['decisions'][0],'review_sha256':'b'*64}])]:
            with self.assertRaises(ValueError):self.resolve({**self.decision(queue),**changed})
        self.assertFalse((self.root/'assessment.json').exists())

    def test_duplicate_and_unknown_tasks_rejected(self):
        queue=self.prepare();data=self.decision(queue)
        with self.assertRaises(ValueError):self.resolve({**data,'decisions':data['decisions']*2})
        with self.assertRaises(ValueError):self.resolve(self.decision(queue,task_id='unknown'))

    def test_tampered_queue_and_source_review_rejected(self):
        queue=self.prepare();decision=self.decision(queue)
        changed=json.loads(self.queue.read_bytes());changed['entries'][0]['review']['findings'][0]['quote']='invented'
        self.queue.write_bytes(canonical(changed));decision['queue_sha256']=digest(self.queue.read_bytes())
        with self.assertRaises(ValueError):self.resolve(decision)
        self.queue.write_bytes(canonical(queue)+b'\n')
        (self.run/'private'/(self.task['task_id']+'.review.json')).write_bytes(b'{}')
        with self.assertRaises(ValueError):self.resolve(self.decision(queue))
