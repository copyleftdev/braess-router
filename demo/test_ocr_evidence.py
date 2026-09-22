import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from corpus import locate
from ocr_evidence import import_bundle, location
from review import validate


class OCREvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.ocr=self.root/'ocr';self.ocr.mkdir()
        self.native=self.root/'native';self.native.write_bytes(b'synthetic image bytes, not decoder evidence')
        text='Alpha café';(self.ocr/'text.txt').write_text(text)
        self.mapping={'source_sha256':hashlib.sha256(self.native.read_bytes()).hexdigest(),
                      'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'normalization':'ocr-tsv-word-join-v1',
                      'pages':{'1':{'width':100,'height':100},'2':{'width':100,'height':100}},
                      'words':[{'start_character':0,'end_character':5,'page':1,'box':[1,2,30,10],'confidence':90},
                               {'start_character':6,'end_character':10,'page':2,'box':[5,7,20,10],'confidence':60}]}
        (self.ocr/'mapping.json').write_text(json.dumps(self.mapping))
        self.bundle=self.root/'bundle'
        self.document=import_bundle(self.native,self.ocr,self.bundle,document_id='3.1.A.1',family_id='3.1.A')['documents'][0]

    def test_finding_maps_to_native_page_and_pixels(self):
        result=locate(self.bundle,self.document,start=6,end=10,quote='café')
        self.assertEqual(result['representation'],'ocr_text')
        self.assertEqual(result['end_byte'],11)
        self.assertEqual(result['image_regions'][0]['page'],2)
        self.assertEqual(result['image_regions'][0]['box'],[5,7,20,10])

    def test_cross_page_quote_retains_both_locations(self):
        result=locate(self.bundle,self.document,start=0,end=10,quote='Alpha café')
        self.assertEqual([r['page'] for r in result['image_regions']],[1,2])

    def test_direct_location_rejects_invalid_ranges(self):
        for start,end in [(-1,5),(0,11),(True,5),(5,5)]:
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):
                location(self.bundle,self.document,start,end)

    def test_native_image_or_mapping_mutation_invalidates_review(self):
        path=self.bundle/'objects'/(self.document['native_source_sha256']+'.bin')
        path.write_bytes(b'changed')
        report={'schema_version':1,'document_id':self.document['document_id'],'source_sha256':self.document['source_sha256'],
                'responsiveness':'uncertain','findings':[]}
        with self.assertRaises(ValueError):validate(self.bundle,self.document,json.dumps(report).encode())

    def test_mapping_geometry_cannot_escape_page(self):
        self.mapping['words'][0]['box']=[90,2,30,10]
        (self.ocr/'mapping.json').write_text(json.dumps(self.mapping))
        with self.assertRaises(ValueError):import_bundle(self.native,self.ocr,self.root/'bad',document_id='3.1.A.1',family_id='3.1.A')
        self.assertFalse((self.root/'bad/manifest.json').exists())

    def test_mapping_gap_cannot_hide_unlocated_characters(self):
        self.mapping['words'][1]['start_character']=7
        (self.ocr/'mapping.json').write_text(json.dumps(self.mapping))
        with self.assertRaises(ValueError):import_bundle(self.native,self.ocr,self.root/'bad',document_id='3.1.A.1',family_id='3.1.A')


if __name__=='__main__':unittest.main()
