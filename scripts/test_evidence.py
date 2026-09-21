#!/usr/bin/env python3
"""Negative tests for stale, missing, altered and unsafe validation evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from verify_evidence import STAGES, verify


class Evidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'bundle'
        (self.bundle / 'source').mkdir(parents=True)
        self.source = self.root / 'Cargo.toml'
        self.source.write_text('source fixture\n')
        (self.bundle / 'source/Cargo.toml').write_bytes(self.source.read_bytes())
        self.write('source-hashes.json', {'Cargo.toml': hashlib.sha256(self.source.read_bytes()).hexdigest()})
        self.write('result.json', {'passed': True, 'failure': None, 'stages_completed': len(STAGES)})
        self.write('stages.json', [{'name': name, 'returncode': 0, 'timed_out': False} for name in STAGES])
        self.seal()

    def write(self, name, value):
        (self.bundle / name).write_text(json.dumps(value))

    def seal(self):
        self.write('SHA256SUMS.json', {str(p.relative_to(self.bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.bundle.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.json'})

    def check(self):
        return verify(self.bundle, {'Cargo.toml': self.source})

    def test_matching_bundle_is_not_v1_approval(self):
        self.assertTrue(self.check()['evidence_valid'])
        self.assertFalse(self.check()['v1_accepted'])

    def test_altered_artifact(self):
        self.write('result.json', {'passed': True})
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.check()

    def test_stale_source(self):
        self.source.write_text('changed source\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.check()

    def test_missing_stage_even_with_resealed_summary(self):
        self.write('stages.json', [{'name': n, 'returncode': 0, 'timed_out': False} for n in STAGES[:-1]])
        self.seal()
        with self.assertRaisesRegex(ValueError, 'stages missing'):
            self.check()

    def test_failed_stage_even_with_passing_summary(self):
        rows = json.loads((self.bundle / 'stages.json').read_text())
        rows[3]['returncode'] = 1
        self.write('stages.json', rows)
        self.seal()
        with self.assertRaisesRegex(ValueError, 'stage failed'):
            self.check()

    def test_unlisted_file(self):
        (self.bundle / 'unlisted.log').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'exactly'):
            self.check()

    def test_escaped_symlink(self):
        copied = self.bundle / 'source/Cargo.toml'
        copied.unlink()
        copied.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.check()


if __name__ == '__main__':
    unittest.main()
