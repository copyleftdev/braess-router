import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from inspector_assets import load_bundle


class InspectorAssetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.manifest={'schema_version':1,'complete':True,'publication_approved':False,
                       'coordinate_unit':'source_page_pixels','pages':[]}
        for name,key,data in [('page-1.png','pages',b'fixture: browser checks PNG decoding'),('text.txt','text',b'Alpha'),('words.json','words',b'[]')]:
            (self.root/name).write_bytes(data)
            entry={'file':name,'sha256':hashlib.sha256(data).hexdigest()}
            if key=='pages':self.manifest[key].append({**entry,'page':1,'width':10,'height':10})
            else:self.manifest[key]=entry
        self.save()

    def save(self):
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))

    def test_only_explicit_verified_assets_are_frozen(self):
        assets=load_bundle(self.root)
        self.assertEqual(set(assets),{'evidence/manifest.json','evidence/page-1.png','evidence/text.txt','evidence/words.json'})
        (self.root/'text.txt').write_bytes(b'changed')
        self.assertEqual(assets['evidence/text.txt'][0],b'Alpha')
        with self.assertRaises(ValueError):load_bundle(self.root)

    def test_paths_and_symlinks_are_rejected(self):
        self.manifest['text']['file']='../text.txt';self.save()
        with self.assertRaises(ValueError):load_bundle(self.root)
        self.manifest['text']['file']='text.txt';self.save()
        (self.root/'text.txt').unlink();(self.root/'text.txt').symlink_to(self.root/'words.json')
        with self.assertRaises(ValueError):load_bundle(self.root)

    def test_incomplete_and_oversized_geometry_rejected(self):
        self.manifest['complete']=False;self.save()
        with self.assertRaises(ValueError):load_bundle(self.root)
        self.manifest['complete']=True;self.manifest['pages'][0]['width']=16_000_001;self.save()
        with self.assertRaises(ValueError):load_bundle(self.root)


if __name__=='__main__':unittest.main()
