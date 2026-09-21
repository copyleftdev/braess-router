import json
import unittest
from private_replay import assets
import test_review_link as fixtures


class PrivateReplayTests(unittest.TestCase):
    setUp=fixtures.ReviewLinkTests.setUp
    record=fixtures.ReviewLinkTests.record

    def test_only_verified_run_and_links_served(self):
        self.record();result=assets(self.corpus,self.tasks,self.run)
        self.assertEqual(set(result),{'replay.json','review-links.json'})
        replay=json.loads(result['replay.json'][0]);links=json.loads(result['review-links.json'][0])
        self.assertEqual(replay['presentation']['profile'],'private_review')
        self.assertEqual(links['run_id'],replay['run']['run_id'])
        self.assertEqual(len(links['links']),1)
        self.assertFalse(links['publication_approved'])

    def test_rejected_review_has_no_finding_link(self):
        self.record(uncertain=True);result=assets(self.corpus,self.tasks,self.run)
        self.assertEqual(json.loads(result['review-links.json'][0])['links'],[])

    def test_changed_response_blocks_serving(self):
        self.record();(self.run/'private'/(self.task['task_id']+'.response.json')).write_bytes(b'{}')
        with self.assertRaises(ValueError):assets(self.corpus,self.tasks,self.run)


if __name__=='__main__':unittest.main()
