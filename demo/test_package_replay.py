import json
from pathlib import Path
import unittest
from package_replay import build, verify
import test_review_link as fixtures


class PackageTests(unittest.TestCase):
    setUp = fixtures.ReviewLinkTests.setUp
    record = fixtures.ReviewLinkTests.record

    def package(self):
        self.record()
        self.output = self.root/'package'
        return build(self.corpus, self.tasks, self.run, self.output)

    def test_frozen_viewer_analysis_and_links_share_run(self):
        manifest = self.package()
        self.assertEqual(verify(self.output), manifest)
        self.assertFalse(manifest['publication_approved'])
        for name in ['index.html', 'app.js', 'assets/archivo-400.woff2', 'review-links.json', 'route-metrics.json']:
            self.assertIn(name, manifest['files'])
        self.assertEqual(json.loads((self.output/'route-metrics.json').read_bytes())['run_id'], manifest['run_id'])
        self.assertEqual(json.loads((self.output/'review-links.json').read_bytes())['run_id'], manifest['run_id'])
        self.assertFalse((self.output/'private').exists())
        with self.assertRaises(FileExistsError): build(self.corpus, self.tasks, self.run, self.output)

    def test_changed_or_extra_files_fail_verification(self):
        self.package()
        target = self.output/'app.js'; original = target.read_bytes()
        target.write_bytes(b'changed')
        with self.assertRaises(ValueError): verify(self.output)
        target.write_bytes(original)
        (self.output/'unexpected.txt').write_text('unexpected')
        with self.assertRaises(ValueError): verify(self.output)

    def test_manifest_traversal_and_symlink_are_rejected(self):
        self.package()
        path = self.output/'package.json'; original = path.read_bytes(); data = json.loads(original)
        data['files']['../outside'] = data['files'].pop('app.js')
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError): verify(self.output)
        path.write_bytes(original)
        target = self.output/'app.js'; raw = target.read_bytes(); target.unlink()
        outside = self.root/'outside'; outside.write_bytes(raw); target.symlink_to(outside)
        with self.assertRaises(ValueError): verify(self.output)

    def test_unverified_response_never_creates_package(self):
        self.record()
        (self.run/'private'/(self.task['task_id']+'.response.json')).write_bytes(b'{}')
        output = self.root/'package'
        with self.assertRaises(ValueError): build(self.corpus, self.tasks, self.run, output)
        self.assertFalse(output.exists())


@unittest.skipIf(fixtures.Image is None,'optional Pillow required')
class ImagePackageTests(unittest.TestCase):
    def setUp(self):
        import test_vision_link
        self.fixture=test_vision_link.VisionLinkTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.fixture.record()
        self.output=self.fixture.root/'package'

    def package(self):
        from package_replay import build_execution
        f=self.fixture
        return build_execution(f.root/'recording',f.path,f.inspector,'task',self.output)

    def test_relocated_package_keeps_page_binding_without_private_prompt(self):
        import shutil
        manifest=self.package()
        for name in ('image-link.json','evidence/page-1.png','evidence/manifest.json','route-metrics.json'):
            self.assertIn(name,manifest['files'])
        self.assertNotIn('review-links.json',manifest['files'])
        self.assertNotIn('reference.json',manifest['files'])
        for name in manifest['files']:
            self.assertNotIn(b'PRIVATE PROMPT',(self.output/name).read_bytes())
        moved=self.fixture.root/'relocated';shutil.move(self.output,moved)
        self.fixture.path.unlink()
        shutil.rmtree(self.fixture.inspector)
        shutil.rmtree(self.fixture.root/'recording')
        self.assertEqual(verify(moved),manifest)
        receipt=json.loads((moved/'replay.json').read_bytes())['events'][2]['data']['generation_input_evidence']
        association=json.loads((moved/'image-link.json').read_bytes())
        self.assertEqual(association['reference_sha256'],receipt['reference_sha256'])
        self.assertEqual([p['sha256'] for p in association['pages']],receipt['image_sha256'])

    def test_mismatched_reference_refused_before_output(self):
        self.fixture.path.write_bytes(self.fixture.path.read_bytes()+b'\n')
        with self.assertRaises(ValueError):self.package()
        self.assertFalse(self.output.exists())

    def test_changed_packaged_image_refused(self):
        self.package();(self.output/'evidence/page-1.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):verify(self.output)


if __name__ == '__main__': unittest.main()
