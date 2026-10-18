#!/usr/bin/env python3
"""Envoie a TOI un vrai mail de prospection, pour voir le rendu.

Prend un prospect de _data/prospection.db (non traite, avec adresse), construit
exactement l'objet et le texte que le pipeline lui enverrait, mais l'adresse a
l'adresse donnee. La base n'est ni modifiee ni marquee : le prospect reste a
traiter. Le lien de demo pointe vers l'adresse qu'aurait sa demo.

Usage :
    .venv/bin/python _scripts/essai_pitch.py francois.lang54@gmail.com
    .venv/bin/python _scripts/essai_pitch.py francois.lang54@gmail.com --metier menuisier --site
    .venv/bin/python _scripts/essai_pitch.py francois.lang54@gmail.com --mode envoi
    .venv/bin/python _scripts/essai_pitch.py francois.lang54@gmail.com --relance
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import envoi_mail          # noqa: E402
import pipeline_pro as pp  # noqa: E402
import relance_mail        # noqa: E402


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("destinataire")
    a.add_argument("--metier", default="garage", choices=sorted(pp.METIERS))
    a.add_argument("--site", action="store_true",
                   help="prendre un prospect qui a deja un site (version refonte)")
    a.add_argument("--mode", choices=["brouillon", "envoi"], default="envoi",
                   help="envoi (defaut) : arrive directement dans ta boite")
    a.add_argument("--relance", action="store_true",
                   help="envoyer aussi la relance J+7, dans le meme fil")
    x = a.parse_args()

    c = sqlite3.connect(f"file:{pp.DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    # De preference un prospect dont la demo existe deja, pour un lien qui
    # marche ; sinon un prospect non traite (lien de demo pas encore en ligne).
    statut_site = "propre" if x.site else "aucun"
    r = c.execute(
        "SELECT * FROM prospects WHERE metier=? AND COALESCE(email,'')<>'' "
        "AND site_statut=? AND COALESCE(site_genere,'')<>'' "
        "ORDER BY CAST(COALESCE(avis,0) AS INTEGER) DESC LIMIT 1",
        (x.metier, statut_site)).fetchone() or c.execute(
        "SELECT * FROM prospects WHERE metier=? AND COALESCE(email,'')<>'' "
        "AND site_statut=? ORDER BY CAST(COALESCE(avis,0) AS INTEGER) DESC LIMIT 1",
        (x.metier, statut_site)).fetchone()
    if not r:
        sys.exit("Aucun prospect correspondant dans la base.")
    p = dict(r)
    demo = p.get("site_genere") or f"{pp.PAGES}/{pp.pl.slugify(p['nom'])}/"
    objet = pp.objet_mail(p)
    corps = pp.pitch(p, x.metier, demo)

    print(f"Prospect pris pour l'essai : {p['nom']} ({p.get('commune') or '?'})")
    print(f"Objet : [ESSAI] {objet}\n\n{corps}\n")
    statut, mid = envoi_mail.expedier(x.destinataire, f"[ESSAI] {objet}", corps, x.mode)
    print(f"-> {statut} vers {x.destinataire}")

    if x.relance:
        p["site_genere"] = demo
        statut, _ = envoi_mail.expedier(
            x.destinataire, f"Re: [ESSAI] {objet}", relance_mail.corps_relance(p),
            x.mode, entetes={"In-Reply-To": mid, "References": mid})
        print(f"-> relance {statut} vers {x.destinataire}")


if __name__ == "__main__":
    main()
