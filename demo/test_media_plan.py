import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from media import identify
from media_plan import plan


class MediaPlanTests(unittest.TestCase):
    def fixture(self, root):
        (root/'objects').mkdir()
        members = []
        for index, raw in enumerate([b'hello', b'II*\x00fixture', b'RIFF0000WAVE', b'\x00\xff']):
            sha = hashlib.sha256(raw).hexdigest()
            (root/'objects'/sha).write_bytes(raw)
            mime, capability = identify(raw)
            members.append({'document_id': str(index), 'sha256': sha, 'bytes': len(raw),
                            'signature_type': mime, 'candidate_capability': capability})
        inventory = {'schema_version': 1, 'members': members, 'native_archive_complete': False,
                     'range': 'bytes 0-99/1000', 'scan_ended': 'prefix_end_or_invalid_compressed_stream'}
        raw = json.dumps(inventory).encode()
        (root/'inventory.json').write_bytes(raw)
        probe = {'schema_version': 1, 'inventory_sha256': hashlib.sha256(raw).hexdigest(),
                 'images': [{'document_id': '1', 'source_sha256': members[1]['sha256'],
                             'decoded': True, 'width': 1, 'height': 1, 'frames': 1}]}
        (root/'probe.json').write_text(json.dumps(probe))
        return members, probe

    def run_plan(self, root):
        return plan(root/'inventory.json', root/'probe.json', root/'plan.json')

    def test_no_inference_or_silent_drop_of_small_image_or_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            report = self.run_plan(root)
            self.assertEqual([r['preparation_stage'] for r in report['members']],
                             ['prepare_text_review', 'prepare_ocr', 'needs_decoder', 'inspect_unknown'])
            self.assertFalse(report['native_archive_complete'])
            self.assertTrue(all(r['semantic_route'] is None and not r['dispatch_permitted']
                                for r in report['members']))
            with self.assertRaises(FileExistsError): self.run_plan(root)

    def test_receipts_and_source_bytes_are_bound(self):
        for tamper in ['source', 'inventory', 'missing', 'extra', 'geometry', 'conflict']:
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); members, probe = self.fixture(root)
                if tamper == 'source': (root/'objects'/members[0]['sha256']).write_bytes(b'other')
                if tamper == 'inventory': probe['inventory_sha256'] = '0'*64
                if tamper == 'missing': probe['images'] = []
                if tamper == 'extra': probe['images'].append({**probe['images'][0], 'document_id': 'other'})
                if tamper == 'geometry': probe['images'][0]['width'] = True
                if tamper == 'conflict': probe['images'].append({**probe['images'][0], 'decoded': False})
                (root/'probe.json').write_text(json.dumps(probe))
                with self.assertRaises(ValueError): self.run_plan(root)
                self.assertFalse((root/'plan.json').exists())

    def test_decoder_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, probe = self.fixture(root)
            probe['images'][0] = {**probe['images'][0], 'decoded': False, 'reason': 'deadline'}
            (root/'probe.json').write_text(json.dumps(probe))
            report = self.run_plan(root)
            self.assertEqual(report['members'][1]['preparation_stage'], 'inspect_failure')
            self.assertEqual(report['members'][1]['decoder_receipt']['reason'], 'deadline')


if __name__ == '__main__': unittest.main()
