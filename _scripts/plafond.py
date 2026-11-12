#!/usr/bin/env python3
"""Plafond quotidien des courriels de prospection, relances comprises.

    MAILS_PAR_JOUR      si renseigne : plafond fixe, prioritaire sur tout le reste
    MAILS_DEPART        AAAA-MM-JJ, premier jour de la montee en charge (semaine 1)
    MAILS_PALIER        hausse par semaine (defaut 5)
    MAILS_PAR_JOUR_MAX  plafond final (defaut 30)

Semaine 1 = 5/jour, puis +MAILS_PALIER par semaine jusqu'au maximum. Une semaine
ne fait monter le palier que si la precedente a eu moins de 5 % de rebonds
(mail_statut='rejete' ou reponse classee 'rebond') : sinon on reste au palier
et Telegram previent (une fois par jour au plus, par l'appelant).

    .venv/bin/python _scripts/plafond.py      # affiche le plafond et la place du jour
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

DEPART_PALIER = 5
SEUIL_REBONDS = 0.05
JOURS_RELANCE = 7


def _int(nom: str, defaut: int | None) -> int | None:
    v = (os.environ.get(nom) or "").strip()
    try:
        return int(v) if v else defaut
    except ValueError:
        return defaut


def _depart() -> date | None:
    v = (os.environ.get("MAILS_DEPART") or "").strip()
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def taux_rebonds(conn, debut: date, fin: date) -> float:
    """Part des courriels partis entre debut (inclus) et fin (exclu) revenus en rebond."""
    n, r = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN mail_statut='rejete' OR "
        "COALESCE(reponse_categorie,'')='rebond' THEN 1 ELSE 0 END) "
        "FROM prospects WHERE mail_envoye_at IS NOT NULL AND "
        "date(mail_envoye_at,'localtime') >= ? AND date(mail_envoye_at,'localtime') < ?",
        (debut.isoformat(), fin.isoformat())).fetchone()
    return (r or 0) / n if n else 0.0


def palier_bloque(conn, aujourdhui: date | None = None) -> bool:
    """Vrai si la derniere semaine ecoulee a empeche la montee du palier."""
    aujourdhui = aujourdhui or date.today()
    d = _depart()
    if not d or (aujourdhui - d).days < 7:
        return False
    k = (aujourdhui - d).days // 7
    debut = d + timedelta(days=7 * (k - 1))
    return taux_rebonds(conn, debut, debut + timedelta(days=7)) >= SEUIL_REBONDS


def plafond_du_jour(conn, aujourdhui: date | None = None) -> int:
    fixe = _int("MAILS_PAR_JOUR", None)
    if fixe is not None:
        return max(0, fixe)
    aujourdhui = aujourdhui or date.today()
    maxi = _int("MAILS_PAR_JOUR_MAX", 30)
    pas = _int("MAILS_PALIER", 5)
    d = _depart()
    if not d or aujourdhui < d:
        return min(maxi, DEPART_PALIER)
    plafond = DEPART_PALIER
    for k in range(1, (aujourdhui - d).days // 7 + 1):
        debut = d + timedelta(days=7 * (k - 1))
        if taux_rebonds(conn, debut, debut + timedelta(days=7)) < SEUIL_REBONDS:
            plafond += pas
    return min(maxi, plafond)


def envois_du_jour(conn) -> int:
    """Premiers courriels + relances deposes ou envoyes aujourd'hui (heure locale)."""
    premiers = conn.execute(
        "SELECT COUNT(*) FROM prospects WHERE mail_envoye_at IS NOT NULL "
        "AND date(mail_envoye_at,'localtime') = date('now','localtime')").fetchone()[0]
    relances = conn.execute(
        "SELECT COUNT(*) FROM prospects WHERE mail_relance_at IS NOT NULL "
        "AND date(mail_relance_at,'localtime') = date('now','localtime')").fetchone()[0]
    return premiers + relances


def relances_prevues(conn, jours: int = JOURS_RELANCE) -> int:
    """Relances J+7 dues et pas encore parties (premier courriel bien envoye)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
    if "mail_relance_at" not in cols:
        return 0
    limite = (datetime.now(timezone.utc) - timedelta(days=jours)).isoformat()
    return conn.execute(
        "SELECT COUNT(*) FROM prospects WHERE mail_statut='envoye' "
        "AND mail_envoye_at <= ? AND mail_relance_at IS NULL "
        "AND COALESCE(mail_relance_statut,'') NOT IN ('a_repondu','stop','jamais_envoye')",
        (limite,)).fetchone()[0]


def place_relances(conn) -> int:
    return max(0, plafond_du_jour(conn) - envois_du_jour(conn))


def place_premiers(conn) -> int:
    """Les relances passent d'abord : on leur reserve leur place."""
    return max(0, place_relances(conn) - relances_prevues(conn))


if __name__ == "__main__":
    import sqlite3
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import config  # noqa: F401  (charge le .env)
    c = sqlite3.connect(str(Path(__file__).parent.parent / "_data" / "prospection.db"))
    print(f"plafond {plafond_du_jour(c)} · deja partis {envois_du_jour(c)} · "
          f"relances prevues {relances_prevues(c)} · place premiers {place_premiers(c)}"
          + (" · palier bloque (rebonds)" if palier_bloque(c) else ""))
