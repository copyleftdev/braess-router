import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from evidence_bundle import build
from ocr_evidence import import_bundle

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, 'optional Pillow dependency required')
class EvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.native=self.root/'native.tiff'
        Image.new('RGB',(20,30),'white').save(self.native,save_all=True,
                                             append_images=[Image.new('RGB',(40,50),'black')])
        self.ocr=self.root/'ocr';self.ocr.mkdir()
        (self.ocr/'text.txt').write_text('Alpha café')
        self.mapping={'source_sha256':hashlib.sha256(self.native.read_bytes()).hexdigest(),
                      'text_sha256':hashlib.sha256('Alpha café'.encode()).hexdigest(),
                      'normalization':'ocr-tsv-word-join-v1',
                      'pages':{'1':{'width':20,'height':30},'2':{'width':40,'height':50}},
                      'words':[{'start_character':0,'end_character':5,'page':1,'box':[1,2,10,5],'confidence':90},
                               {'start_character':6,'end_character':10,'page':2,'box':[2,3,20,6],'confidence':60}]}
        self.bundle=self.root/'corpus'

    def prepare(self):
        (self.ocr/'mapping.json').write_text(json.dumps(self.mapping))
        import_bundle(self.native,self.ocr,self.bundle,document_id='3.1.A.1',family_id='3.1.A')

    def test_multiframe_pixels_geometry_text_and_hashes(self):
        self.prepare();out=self.root/'view'
        report=build(self.bundle/'manifest.json','3.1.A.1',out)
        self.assertEqual(report['words']['count'],2)
        self.assertFalse(report['publication_approved'])
        self.assertFalse(report['review_performed'])
        self.assertEqual((out/'text.txt').read_text(),'Alpha café')
        with Image.open(self.native) as original:
            for index,page in enumerate(report['pages']):
                original.seek(index)
                with Image.open(out/page['file']) as rendered:
                    self.assertEqual(rendered.size,original.size)
                    self.assertEqual(rendered.tobytes(),original.convert('RGBA').tobytes())
                self.assertEqual(hashlib.sha256((out/page['file']).read_bytes()).hexdigest(),page['sha256'])
        with self.assertRaises(FileExistsError):build(self.bundle/'manifest.json','3.1.A.1',out)

    def test_mapping_geometry_must_match_decoded_page(self):
        self.mapping['pages']['2']['width']=41
        self.prepare();out=self.root/'bad'
        with self.assertRaises(ValueError):build(self.bundle/'manifest.json','3.1.A.1',out)
        self.assertFalse((out/'manifest.json').exists())

    def test_mapping_page_count_must_match_decoder(self):
        self.mapping['pages']['3']={'width':10,'height':10}
        self.prepare();out=self.root/'bad'
        with self.assertRaises(ValueError):build(self.bundle/'manifest.json','3.1.A.1',out)
        self.assertFalse((out/'manifest.json').exists())


if __name__=='__main__':unittest.main()
