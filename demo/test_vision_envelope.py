import base64
import json
import unittest
import test_review_link as fixtures
from evidence_bundle import build
from vision_envelope import prepare


@unittest.skipIf(fixtures.Image is None, 'optional Pillow required')
class VisionEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.OCRReviewLinkTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.bundle = self.fixture.root/'inspector'
        build(self.fixture.corpus/'manifest.json',self.fixture.doc['document_id'],self.bundle)
        self.output = self.fixture.root/'vision'

    def prepare(self, **overrides):
        options = dict(prompt='Describe page structure.',model='fixture/vision',provider='fixture',pages=[1])
        options.update(overrides)
        return prepare(self.bundle,self.output,**options)

    def test_private_image_bytes_survive_multipart_encoding(self):
        report = self.prepare()
        wire = json.loads((self.output/'provider-request.json').read_bytes())
        parts = wire['messages'][0]['content']
        self.assertEqual(parts[0]['type'],'text')
        encoded = parts[1]['image_url']['url'].removeprefix('data:image/png;base64,')
        self.assertEqual(base64.b64decode(encoded,validate=True),(self.bundle/'page-1.png').read_bytes())
        self.assertFalse(wire['provider']['allow_fallbacks'])
        self.assertFalse(report['dispatch_authorized'])
        self.assertFalse(report['provider_capability_verified'])
        self.assertNotIn('base64', (self.output/'reference.json').read_text())
        with self.assertRaises(FileExistsError): self.prepare()

    def test_invalid_pages_and_prompt_fail_before_output(self):
        for changes in [dict(pages=[]),dict(pages=[1,1]),dict(pages=[True]),dict(pages=[99]),
                        dict(prompt='x'*8193),dict(prompt=' '),dict(model='bad model')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.prepare(**changes)
            self.assertFalse(self.output.exists())

    def test_source_tampering_refused(self):
        (self.bundle/'page-1.png').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())


if __name__ == '__main__': unittest.main()
