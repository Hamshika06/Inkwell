import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OrbitCopyTests(unittest.TestCase):
    def test_extension_uses_the_same_orbit(self):
        """The extension can't import from the website, so it carries a copy of web/orbit.js. Keep them identical."""
        web = (ROOT / "web" / "orbit.js").read_bytes().replace(b"\r\n", b"\n")
        ext = (ROOT / "extension" / "orbit.js").read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(web, ext, "extension/orbit.js differs from web/orbit.js: copy web/orbit.js over it")


if __name__ == "__main__":
    unittest.main()
