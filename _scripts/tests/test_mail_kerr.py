import re
import unittest
from unittest import mock

from tests import _base  # noqa: F401
import mail_kerr

DEMO = "https://francoislang.github.io/templates/boucherie-de-geneve/"
CAP = "https://res.cloudinary.com/dhwukxhgc/image/upload/f_jpg,q_80,w_1072/mails/boucherie-de-geneve"
FAUX_ASSETS = {k: f"https://exemple.test/{k}.jpg" for k in mail_kerr.IMAGES}


def prospect(nom="Boucherie Dupont", site=False, **k):
    p = dict(nom=nom, commune="Nancy", email="x@y.fr",
             site_statut="propre" if site else "aucun", site_web="https://a.fr" if site else "")
    p.update(k)
    return p


class TestMailKerr(unittest.TestCase):
    def setUp(self):
        pa = mock.patch.object(mail_kerr, "assets", return_value=FAUX_ASSETS)
        pa.start()
        self.addCleanup(pa.stop)

    def verifier(self, m, label):
        h = m.html
        self.assertNotRegex(h, r"\{\{|\{[a-z_]+\}", label)
        self.assertLessEqual(mail_kerr.mots_visibles(h), 130, label)
        self.assertLess(len(h.encode()), 100_000, label)
        for attendu in (DEMO, mail_kerr.lien_rdv(), "Ne plus recevoir", "293&nbsp;B", "SIRET"):
            self.assertIn(attendu, h, f"{label} : {attendu}")
        corps = h.split("<!--SIGNATURE-->")[0]
        self.assertNotIn("STOP", corps, label)
        self.assertNotIn("pas de site", corps.lower(), label)
        self.assertTrue(m.texte.strip(), label)
        self.assertIn(DEMO, m.texte, label)
        self.assertTrue(m.objet and len(m.objet) <= 70, label)

    def test_tous_les_metiers(self):
        for cle in mail_kerr.accroches():
            for site in (False, True):
                for mois in (1, 11):
                    m = mail_kerr.premier(prospect(site=site), cle, DEMO, CAP, mois)
                    self.verifier(m, f"{cle}/{'avec' if site else 'sans'}/{mois}")
                    self.assertIn(CAP, m.html)
                    self.assertIn("1&nbsp;200&nbsp;€", m.html)

    def test_metier_inconnu(self):
        m = mail_kerr.premier(prospect(), "inconnu", DEMO, CAP)
        self.verifier(m, "inconnu")
        self.assertIn("maquette de site à votre nom", m.html)

    def test_nom_majuscules_echappe(self):
        self.assertEqual(mail_kerr.nom_propre("BOUCHERIE DUPONT & FILS"), "Boucherie Dupont & Fils")
        self.assertEqual(mail_kerr.nom_propre("L'ATELIER DE LA GARE"), "L'Atelier de la Gare")
        self.assertEqual(mail_kerr.nom_propre("SARL MARTIN"), "SARL Martin")
        self.assertEqual(mail_kerr.nom_propre("Chez Léa"), "Chez Léa")
        m = mail_kerr.premier(prospect(nom='BOUCHERIE DUPONT & FILS <"LE BON">'), "boucherie", DEMO, CAP)
        self.assertIn("Dupont &amp; Fils", m.html)
        self.assertNotIn('<"', m.html)

    def test_pied_sans_commune_ni_source(self):
        m = mail_kerr.premier(dict(nom="Garage X", email="a@b.fr"), "garage", DEMO, CAP)
        self.verifier(m, "sans commune")
        self.assertIn("OpenStreetMap", m.html)

    def test_origine_site(self):
        p = prospect(mail_source="accueil", mail_cherche_at="2026-11-01", site_web="https://a.fr")
        self.assertIn("votre site", mail_kerr.origine_adresse(p))

    def test_relance(self):
        m = mail_kerr.relance(prospect(), "boucherie", DEMO, CAP, objet="Vos coffrets ?")
        self.verifier(m, "relance")
        self.assertEqual(m.objet, "Re: Vos coffrets ?")
        self.assertIn("une seule fois", m.html)
        self.assertIn("Je ne vous relancerai pas", m.html)
        self.assertNotIn("1&nbsp;200", m.html)
        self.assertLessEqual(mail_kerr.mots_visibles(m.html), 60)


if __name__ == "__main__":
    unittest.main()
