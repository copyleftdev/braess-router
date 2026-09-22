import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from media import identify, inventory, native_id
from ocr import parse_tsv


class MediaTests(unittest.TestCase):
    def test_signatures_override_filename_assumptions(self):
        self.assertEqual(identify(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')[1],'document_conversion')
        self.assertEqual(identify(b'RIFF0000WAVE')[0],'audio/wav')
        self.assertEqual(identify(b'RIFF0000WEBP')[0],'image/webp')
        self.assertEqual(identify(b'\x89PNG\r\n\x1a\n')[0],'image/png')
        self.assertEqual(identify(b'hello')[0],'text/plain')
        self.assertEqual(identify(b'\x00\xff')[1],'human_inspection')

    def test_native_ids_with_and_without_extensions(self):
        self.assertEqual(native_id('native/3.123.ABC.1.doc'),'3.123.ABC.1')
        self.assertEqual(native_id('native/3.123.ABC.1'),'3.123.ABC.1')
        self.assertIsNone(native_id('other.doc'))

    def test_prefix_inventory_keeps_complete_members_and_partial_scope(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);archive=root/'prefix';headers=root/'headers'
            with tarfile.open(archive,'w:bz2') as out:
                member=tarfile.TarInfo('native/3.1.A.1.doc');member.size=5
                out.addfile(member,io.BytesIO(b'hello'))
            size=archive.stat().st_size
            headers.write_text(f'HTTP/1.1 206 Partial Content\nContent-Range: bytes 0-{size-1}/{size+1000}\n')
            result=inventory(archive,headers,root/'out',source_url='https://fixture.invalid/archive')
            self.assertFalse(result['native_archive_complete'])
            self.assertEqual(result['complete_members'],1)
            self.assertEqual(result['members'][0]['signature_type'],'text/plain')
            self.assertFalse(result['members'][0]['decoder_validated'])
            headers.write_text('HTTP/1.1 200 OK\n')
            with self.assertRaises(ValueError):inventory(archive,headers,root/'bad',source_url='fixture')


class OCRTests(unittest.TestCase):
    def wire(self, box='10\t20\t30\t10', word='café'):
        return ('level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
                '1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t\n'
                f'5\t1\t1\t1\t1\t1\t{box}\t92\t{word}\n').encode()

    def test_word_offsets_and_pixel_box_preserved(self):
        text,mapping=parse_tsv(self.wire(),1)
        self.assertEqual(text,'café')
        self.assertEqual(mapping['words'][0]['end_character'],4)
        self.assertEqual(mapping['words'][0]['box'],[10,20,30,10])

    def test_missing_pages_and_outside_geometry_refused(self):
        with self.assertRaises(ValueError):parse_tsv(self.wire(),2)
        with self.assertRaises(ValueError):parse_tsv(self.wire(box='90\t20\t30\t10'),1)


if __name__=='__main__':unittest.main()
