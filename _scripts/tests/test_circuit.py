import sqlite3
import unittest
from unittest import mock

from tests import _base  # noqa: F401
import pipeline_pro as pp

URL = "https://francoislang.github.io/templates/boucherie-dupont/"
CAP = "https://res.cloudinary.com/x/image/upload/f_jpg,q_80,w_1072/mails/boucherie-dupont"


def base():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prospects (cle TEXT, nom TEXT, email TEXT, telephone TEXT, metier TEXT, "
              "mail_envoye_at TEXT, mail_statut TEXT, mail_message_id TEXT, mail_objet TEXT, "
              "mail_relance_at TEXT, mail_relance_statut TEXT, reponse_categorie TEXT, capture_url TEXT)")
    c.execute("INSERT INTO prospects (cle, nom, email, metier) VALUES ('k1','BOUCHERIE DUPONT','b@d.fr','boucherie')")
    c.commit()
    return c


P = dict(cle="k1", nom="BOUCHERIE DUPONT", email="b@d.fr", telephone="", metier="boucherie",
         site_statut="aucun", commune="Nancy")


class TestEcrire(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch.object(pp.envoi_mail, "actif", return_value=True),
            mock.patch.object(pp, "contacts_anterieurs", return_value=(set(), set())),
            mock.patch.object(pp, "_en_ligne", return_value=True),
            mock.patch.object(pp.mail_kerr, "assets", return_value={k: f"https://e.test/{k}" for k in pp.mail_kerr.IMAGES}),
            mock.patch.object(pp.telegram, "send"),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.exp = mock.patch.object(pp.envoi_mail, "expedier", return_value=("envoye", "<id@x>")).start()
        self.addCleanup(mock.patch.stopall)

    def test_capture_ok(self):
        c = base()
        with mock.patch.object(pp.plafond, "place_premiers", return_value=5), \
             mock.patch.object(pp.capture, "capturer", return_value=CAP):
            pp.ecrire(c, "boucherie", [(dict(P), URL)], set(), set())
        args, kw = self.exp.call_args
        self.assertIsNone(args[3])
        self.assertIn(CAP, kw["html"])
        self.assertEqual(c.execute("select capture_url from prospects").fetchone()[0], CAP)

    def test_capture_ratee_brouillon(self):
        c = base()
        with mock.patch.object(pp.plafond, "place_premiers", return_value=5), \
             mock.patch.object(pp.capture, "capturer", return_value=None):
            pp.ecrire(c, "boucherie", [(dict(P), URL)], set(), set())
        self.assertEqual(self.exp.call_args[0][3], "brouillon")
        self.assertTrue(any("capture" in str(a) for a in pp.telegram.send.call_args_list))

    def test_plafond_atteint(self):
        c = base()
        with mock.patch.object(pp.plafond, "place_premiers", return_value=0), \
             mock.patch.object(pp.capture, "capturer", return_value=CAP) as cap:
            pp.ecrire(c, "boucherie", [(dict(P), URL)], set(), set())
        self.exp.assert_not_called()
        cap.assert_not_called()


class TestRelance(unittest.TestCase):
    def test_relance_ancien_mail_sans_capture(self):
        import relance_mail
        with mock.patch.object(relance_mail.mail_kerr, "assets",
                               return_value={k: f"https://e.test/{k}" for k in relance_mail.mail_kerr.IMAGES}):
            m = relance_mail.relance_kerr(dict(P, site_genere=URL, mail_objet="Le site préparé pour X"), None)
        self.assertEqual(m.objet, "Re: Le site préparé pour X")
        self.assertIn(URL, m.html)
        c = base()
        with mock.patch.object(relance_mail.capture, "capturer", return_value=None):
            self.assertIsNone(relance_mail.capture_de(c, dict(P, site_genere=URL)))
        self.assertIsNone(relance_mail.capture_de(c, dict(P)))


if __name__ == "__main__":
    unittest.main()
