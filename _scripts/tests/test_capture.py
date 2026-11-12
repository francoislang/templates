import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _base  # noqa: F401
import capture

PLAYWRIGHT = importlib.util.find_spec("playwright") is not None


class TestCapture(unittest.TestCase):
    @unittest.skipUnless(PLAYWRIGHT, "Playwright absent")
    def test_photographier_page_locale(self):
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "page.html"
            page.write_text("<html><body style='background:linear-gradient(red,blue)'>"
                            + "<h1>Essai</h1>" * 40 + "</body></html>")
            png = Path(d) / "x.png"
            with mock.patch.object(capture, "ATTENTE_MS", 100):
                self.assertTrue(capture.photographier(page.as_uri(), png))
            self.assertGreater(png.stat().st_size, 5_000)

    def test_capturer_url_cloudinary(self):
        base = "https://res.cloudinary.com/dhwukxhgc/image/upload/v1/mails/abc.png"
        with mock.patch.object(capture, "photographier", return_value=True), \
             mock.patch("photos.upload_fichier", return_value=base):
            url = capture.capturer("https://exemple.test/", "abc")
        self.assertEqual(url, "https://res.cloudinary.com/dhwukxhgc/image/upload/f_jpg,q_80,w_1072/v1/mails/abc.png")

    def test_capturer_echec(self):
        with mock.patch.object(capture, "photographier", return_value=False):
            self.assertIsNone(capture.capturer("https://exemple.test/", "abc"))
        self.assertIsNone(capture.capturer("", "abc"))

    def test_sans_playwright(self):
        with mock.patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            with tempfile.TemporaryDirectory() as d:
                self.assertFalse(capture.photographier("https://exemple.test/", Path(d) / "x.png"))


if __name__ == "__main__":
    unittest.main()
