import os
import sqlite3
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from tests import _base  # noqa: F401
import plafond

COLS = ("cle TEXT, mail_envoye_at TEXT, mail_statut TEXT, reponse_categorie TEXT, "
        "mail_relance_at TEXT, mail_relance_statut TEXT")


def base():
    c = sqlite3.connect(":memory:")
    c.execute(f"CREATE TABLE prospects ({COLS})")
    return c


def ajout(c, quand, statut="envoye", cat=None, relance=None):
    c.execute("INSERT INTO prospects VALUES (?,?,?,?,?,NULL)",
              ("x", quand, statut, cat, relance))


D0 = date(2026, 11, 16)
ENV = {"MAILS_DEPART": D0.isoformat(), "MAILS_PALIER": "5", "MAILS_PAR_JOUR_MAX": "30"}


class TestPlafond(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, ENV)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("MAILS_PAR_JOUR", None)

    def test_paliers(self):
        c = base()
        self.assertEqual(plafond.plafond_du_jour(c, D0), 5)
        self.assertEqual(plafond.plafond_du_jour(c, D0 + timedelta(days=7)), 10)
        self.assertEqual(plafond.plafond_du_jour(c, D0 + timedelta(days=35)), 30)
        self.assertEqual(plafond.plafond_du_jour(c, D0 + timedelta(days=70)), 30)

    def test_fixe_prioritaire(self):
        with mock.patch.dict(os.environ, {"MAILS_PAR_JOUR": "12"}):
            self.assertEqual(plafond.plafond_du_jour(base(), D0 + timedelta(days=70)), 12)

    def test_sans_depart(self):
        os.environ.pop("MAILS_DEPART")
        self.assertEqual(plafond.plafond_du_jour(base(), D0), 5)

    def test_frein_rebonds(self):
        c = base()
        for i in range(10):
            ajout(c, f"{D0.isoformat()}T10:00:00", "rejete" if i < 2 else "envoye")
        self.assertEqual(plafond.plafond_du_jour(c, D0 + timedelta(days=7)), 5)
        self.assertTrue(plafond.palier_bloque(c, D0 + timedelta(days=7)))

    def test_place_jamais_negative(self):
        c = base()
        now = datetime.now(timezone.utc).isoformat()
        for _ in range(25):
            ajout(c, now)
        with mock.patch.dict(os.environ, {"MAILS_PAR_JOUR": "5"}):
            self.assertEqual(plafond.place_premiers(c), 0)
            self.assertEqual(plafond.place_relances(c), 0)

    def test_relances_reservees(self):
        c = base()
        vieux = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        ajout(c, vieux)
        ajout(c, vieux)
        with mock.patch.dict(os.environ, {"MAILS_PAR_JOUR": "5"}):
            self.assertEqual(plafond.relances_prevues(c), 2)
            self.assertEqual(plafond.place_premiers(c), 3)
            self.assertEqual(plafond.place_relances(c), 5)

    def test_retard_de_relances_ne_bloque_pas(self):
        c = base()
        vieux = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
        for _ in range(42):
            ajout(c, vieux)
        with mock.patch.dict(os.environ, {"MAILS_PAR_JOUR": "5"}):
            self.assertEqual(plafond.place_premiers(c), 2)
            self.assertEqual(plafond.place_relances(c), 5)


if __name__ == "__main__":
    unittest.main()
