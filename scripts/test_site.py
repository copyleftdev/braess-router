#!/usr/bin/env python3
"""Negative discovery checks use disposable copies, never alter the site."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import check_site


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / 'site'
        shutil.copytree(check_site.SITE, self.site)
        self.mock = patch.object(check_site, 'SITE', self.site)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def change(self, name, old, new):
        p = self.site / name
        text = p.read_text()
        self.assertIn(old, text)
        p.write_text(text.replace(old, new))

    def test_valid_site(self):
        check_site.validate()

    def test_canonical_drift(self):
        self.change('index.html', 'rel="canonical" href="https://copyleftdev.github.io/braess-router/"', 'rel="canonical" href="https://example.com/"')
        with self.assertRaisesRegex(ValueError, 'Canonical'):
            check_site.validate()

    def test_subpath_asset_error(self):
        self.change('index.html', 'href="style.css"', 'href="/style.css"')
        with self.assertRaisesRegex(ValueError, 'escaped project'):
            check_site.validate()

    def test_wrong_schema_repository(self):
        self.change('index.html', '"codeRepository": "https://github.com/copyleftdev/braess-router"', '"codeRepository": "https://example.com"')
        with self.assertRaisesRegex(ValueError, 'Incorrect source'):
            check_site.validate()

    def test_wrong_sitemap(self):
        self.change('sitemap.xml', 'https://copyleftdev.github.io/braess-router/', 'https://example.com/')
        with self.assertRaisesRegex(ValueError, 'Sitemap'):
            check_site.validate()

    def test_wrong_social_image(self):
        (self.site / 'assets/social-card.png').write_bytes(b'not a PNG')
        with self.assertRaisesRegex(ValueError, 'Social preview'):
            check_site.validate()

    def test_missing_agent_guide(self):
        (self.site / 'llms.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing or unsafe'):
            check_site.validate()

    def test_symlink_asset(self):
        p = self.site / 'assets/mark.svg'
        p.unlink()
        p.symlink_to(self.site / 'index.html')
        with self.assertRaisesRegex(ValueError, 'Missing or unsafe'):
            check_site.validate()


if __name__ == '__main__':
    unittest.main()
