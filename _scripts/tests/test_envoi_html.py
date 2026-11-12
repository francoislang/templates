import unittest
from tests import _base  # noqa: F401
import envoi_mail


class TestEnvoiHtml(unittest.TestCase):
    def test_html_fourni(self):
        envoi_mail.ADRESSE = envoi_mail.ADRESSE or "francois-lang@kerr-studio.com"
        m = envoi_mail.construire("a@b.fr", "Objet", "corps texte", html="<p>x</p>")
        parts = {p.get_content_type(): p.get_content() for p in m.iter_parts()}
        self.assertEqual(parts["text/html"].strip(), "<p>x</p>")
        self.assertEqual(parts["text/plain"].strip(), "corps texte")


if __name__ == "__main__":
    unittest.main()
