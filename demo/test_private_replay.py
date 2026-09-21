import json
import unittest
from private_replay import assets, execution_assets
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

    def test_execution_only_profile_freezes_verified_metadata_without_source_links(self):
        self.record()
        result=execution_assets(self.run/'recording')
        self.assertEqual(set(result),{'replay.json'})
        replay=json.loads(result['replay.json'][0])
        self.assertEqual(replay['presentation']['profile'],'private_execution')
        self.assertIn('synthetic provider responses',replay['presentation']['description'])
        before=result['replay.json'][0]
        (self.run/'recording/events.jsonl').write_bytes(b'changed')
        self.assertEqual(result['replay.json'][0],before)
        with self.assertRaises(ValueError):execution_assets(self.run/'recording')


class OCRPrivateReplayTests(unittest.TestCase):
    def test_matching_inspector_is_bound_before_serving(self):
        from test_review_link import OCRReviewLinkTests
        from evidence_bundle import build
        if __import__('test_review_link').Image is None:self.skipTest('optional Pillow required')
        fixture=OCRReviewLinkTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.record();inspector=fixture.root/'inspector'
        build(fixture.corpus/'manifest.json',fixture.doc['document_id'],inspector)
        result=assets(fixture.corpus,fixture.tasks,fixture.run,inspector=inspector)
        links=json.loads(result['review-links.json'][0])
        self.assertIsNotNone(links['links'][0]['inspector_manifest_sha256'])


if __name__=='__main__':unittest.main()
