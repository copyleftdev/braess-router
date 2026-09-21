import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from corpus import ingest, locate, seeds


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root/'input.tar.bz2'
        self.seed = self.root/'seed.csv'
        self.seed.write_text('3.1.A,200,1,3.1.A\n')

    def pack(self, members):
        with tarfile.open(self.archive,'w:bz2') as output:
            for name, data, kind in members:
                info=tarfile.TarInfo(name);info.size=len(data);info.type=kind
                if kind == tarfile.SYMTYPE:info.linkname='/etc/passwd'
                output.addfile(info,io.BytesIO(data) if kind==tarfile.REGTYPE else None)

    def test_exact_utf8_locations_and_native_scope(self):
        raw='A café agreement.'.encode()
        self.pack([('text/3.1.A.txt',raw,tarfile.REGTYPE)])
        result=ingest(self.archive,self.seed,self.root/'result',limit=1)
        doc=result['documents'][0]
        self.assertFalse(result['native_media_available'])
        self.assertEqual(doc['native_modality'],'unknown')
        self.assertEqual(doc['source_sha256'],hashlib.sha256(raw).hexdigest())
        span=locate(self.root/'result',doc,start=2,end=6,quote='café')
        self.assertEqual((span['start_byte'],span['end_byte']),(2,7))
        with self.assertRaises(ValueError):locate(self.root/'result',doc,start=2,end=6,quote='fake')
        with self.assertRaises(ValueError):locate(self.root/'result',doc,start=True,end=6,quote='café')

    def test_conflicting_and_unassessed_labels_are_preserved(self):
        self.seed.write_text('3.1.A,200,0,3.1.A\n3.1.A,200,1,3.1.A\n3.1.A,201,-1,3.1.A\n')
        record=seeds(self.seed)['3.1.A']
        self.assertEqual(record['judgment_conflicts'],[200])
        self.assertEqual([r['assessment'] for r in record['judgments']],[0,1,-1])
        self.assertEqual(record['judgments'][2]['status'],'not_assessed')

    def test_duplicate_content_keeps_distinct_document_ids(self):
        self.seed.write_text('3.1.A,200,1,3.1.A\n3.1.A_123,200,1,3.1.A.1\n')
        self.pack([('3.1.A.txt',b'same',tarfile.REGTYPE),('3.1.A.1.txt',b'same',tarfile.REGTYPE)])
        result=ingest(self.archive,self.seed,self.root/'result',limit=2)
        self.assertEqual(len(result['documents']),2)
        self.assertEqual(result['unique_content_hashes'],1)
        self.assertEqual(result['documents'][1]['family_id'],'3.1.A')

    def test_invalid_encoding_is_excluded_without_lossy_replacement(self):
        self.pack([('3.1.A.txt',b'bad\xff',tarfile.REGTYPE)])
        result=ingest(self.archive,self.seed,self.root/'result',limit=1)
        self.assertFalse(result['sample_limit_reached'])
        self.assertEqual(result['documents'],[])
        self.assertEqual(len(result['exclusions']),1)

    def test_unsafe_members_refused_without_extraction(self):
        for i,(name,kind) in enumerate([('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE)]):
            self.pack([(name,b'',kind)])
            with self.assertRaises(ValueError):ingest(self.archive,self.seed,self.root/f'result{i}',limit=1)
        self.assertFalse((self.root/'escape').exists())

    def test_changed_source_invalidates_finding(self):
        self.pack([('3.1.A.txt',b'original',tarfile.REGTYPE)])
        result=ingest(self.archive,self.seed,self.root/'result',limit=1)
        doc=result['documents'][0]
        (self.root/'result'/doc['object']).write_text('changed')
        with self.assertRaises(ValueError):locate(self.root/'result',doc,start=0,end=8,quote='original')


if __name__=='__main__':unittest.main()
