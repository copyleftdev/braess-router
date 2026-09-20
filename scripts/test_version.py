#!/usr/bin/env python3
"""Exercise version and release gates using disposable Git repositories."""
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name('check_version.py').resolve()


class VersionPolicy(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Version test')
        self.write('Cargo.toml', '[package]\nversion="0.1.0-alpha.1"\n')
        self.write('CHANGELOG.md', '# Changelog\n\n## 0.1.0-alpha.1\n')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', self.base)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True,
                                       stderr=subprocess.PIPE).strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')

    def check(self, *args, error=None):
        result = subprocess.run(['python3', str(SCRIPT), *args], cwd=self.root,
                                capture_output=True, text=True)
        if error:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stderr)
        else:
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_unchanged_runtime_and_inputs_require_bump(self):
        for path in ('src/lib.rs', 'config/example.json', 'eval/rubric.json'):
            with self.subTest(path=path):
                self.write(path, '{}\n')
                self.commit()
                self.check('--base', self.base, error='greater package version')

    def test_runtime_moved_to_docs_requires_bump(self):
        self.write('src/lib.rs', '// runtime code\n')
        self.commit()
        base = self.git('rev-parse', 'HEAD')
        self.git('mv', 'src/lib.rs', 'README.md')
        self.commit()
        self.check('--base', base, error='greater package version')

    def test_docs_only_needs_no_bump(self):
        self.write('README.md', 'Documentation\n')
        self.commit()
        self.check('--base', self.base)

    def test_backwards_version_rejected(self):
        self.write('Cargo.toml', '[package]\nversion="0.1.0-alpha.0"\n')
        self.commit()
        self.check('--base', self.base, error='greater package version')

    def test_missing_changelog_rejected(self):
        self.write('Cargo.toml', '[package]\nversion="0.1.0-alpha.2"\n')
        self.commit()
        self.check('--base', self.base, error='changelog entry')

    def test_greater_prerelease_and_stable_accepted(self):
        for value in ('0.1.0-alpha.2', '0.1.0-beta.1', '0.1.0-rc.1', '0.1.0'):
            with self.subTest(version=value):
                self.write('Cargo.toml', '[package]\nversion="' + value + '"\n')
                self.write('CHANGELOG.md', '## ' + value + '\n')
                self.commit()
                self.check('--base', self.base)

    def test_matching_main_tag_accepted(self):
        self.git('tag', 'v0.1.0-alpha.1')
        self.check('--tag', 'v0.1.0-alpha.1')

    def test_mismatched_tag_rejected(self):
        self.git('tag', 'v0.1.0')
        self.check('--tag', 'v0.1.0', error='Release tag must equal')

    def test_tag_on_another_commit_rejected(self):
        self.git('tag', 'v0.1.0-alpha.1')
        self.write('README.md', 'another commit\n')
        self.commit()
        self.check('--tag', 'v0.1.0-alpha.1', error='Checkout does not match')

    def test_unmerged_tag_rejected(self):
        self.write('README.md', 'unmerged commit\n')
        self.commit()
        self.git('tag', 'v0.1.0-alpha.1')
        self.check('--tag', 'v0.1.0-alpha.1', error='CalledProcessError')

    def test_missing_release_notes_rejected(self):
        self.write('CHANGELOG.md', '# No version entry\n')
        self.commit()
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git('tag', 'v0.1.0-alpha.1')
        self.check('--tag', 'v0.1.0-alpha.1', error='changelog heading')


if __name__ == '__main__':
    unittest.main()
