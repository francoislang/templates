#!/usr/bin/env python3
"""Regenere avec les gabarits de famille les demos des prospects encore
« Nouveau » dans le CRM (metiers du catalogue metiers.py uniquement).

Meme chaine que pipeline_pro.generer_site (repli sans IA) : fiche publique,
gabarit, neutralisation, verification des coordonnees, pixel de comptage.
L'URL de la demo ne change pas : les brouillons Gmail restent valables.
Aucune operation git : relire, puis commiter et pousser soi-meme.

    python3 _scripts/regenerer_nouveau.py              liste, n'ecrit rien
    python3 _scripts/regenerer_nouveau.py --apercu     ecrit dans _data/tmp_apercu/regen/
    python3 _scripts/regenerer_nouveau.py --appliquer  remplace <slug>/index.html
    ... --slug le-bel --slug le-crin-blanc             sites precis (meme hors « Nouveau »)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import anonymiser            # noqa: E402
import crm                   # noqa: E402
import gabarit_fixe          # noqa: E402
import metiers               # noqa: E402
import pipeline as pl        # noqa: E402

REPO = Path(__file__).parent.parent
DB = REPO / "_data" / "prospection.db"
APERCU = REPO / "_data" / "tmp_apercu" / "regen"


def numeros_nouveau() -> set[int]:
    nums, cur = set(), None
    while True:
        after = f', after: "{cur}"' if cur else ""
        q = {"query": f'''{{ node(id: "{crm.PROJECT_ID}") {{ ... on ProjectV2 {{
          items(first: 100{after}) {{ pageInfo {{ hasNextPage endCursor }}
          nodes {{ fieldValues(first: 15) {{ nodes {{ ... on ProjectV2ItemFieldSingleSelectValue {{
            name field {{ ... on ProjectV2SingleSelectField {{ name }} }} }} }} }}
            content {{ ... on Issue {{ number }} }} }} }} }} }} }}'''}
        d = crm._graphql(q)["data"]["node"]["items"]
        for it in d["nodes"]:
            st = [fv.get("name") for fv in it["fieldValues"]["nodes"]
                  if fv and (fv.get("field") or {}).get("name") == "Status"]
            num = (it.get("content") or {}).get("number")
            if num and st and st[0] == "Nouveau":
                nums.add(num)
        if not d["pageInfo"]["hasNextPage"]:
            return nums
        cur = d["pageInfo"]["endCursor"]


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--apercu", action="store_true")
    a.add_argument("--appliquer", action="store_true")
    a.add_argument("--slug", action="append", default=[])
    x = a.parse_args()

    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    tous = list(c.execute("SELECT * FROM prospects WHERE COALESCE(site_genere,'') <> ''"))
    if x.slug:
        # --slug vise un site precis, quel que soit son statut dans le CRM
        lignes = [r for r in tous
                  if r["site_genere"].rstrip("/").rsplit("/", 1)[-1] in x.slug]
        print(f"{len(lignes)} site(s) demande(s) retrouve(s) dans prospection.db")
    else:
        nums = numeros_nouveau()
        lignes = [r for r in tous if (r["crm_issue"] or "") and
                  int(str(r["crm_issue"]).rstrip("/").rsplit("/", 1)[-1] or 0) in nums]
        print(f"{len(nums)} annonce(s) « Nouveau » dans le CRM, {len(lignes)} retrouvee(s) dans prospection.db")

    faits = 0
    for r in lignes:
        p = dict(r)
        slug = p["site_genere"].rstrip("/").rsplit("/", 1)[-1]
        if x.slug and slug not in x.slug:
            continue
        metier = p.get("metier") or ""
        if metier not in metiers.PAR_CLE:
            print(f"  - {slug:32} {metier:16} ignore (pas un metier du catalogue)")
            continue
        try:
            html = gabarit_fixe.remplir(anonymiser.fiche_publique(p), metier, slug)
        except Exception as e:
            print(f"  ! {slug:32} {metier:16} echec du gabarit : {e}")
            continue
        if not (x.apercu or x.appliquer):
            print(f"  · {slug:32} {metier:16} pret")
            continue
        cible = (REPO / slug / "index.html") if x.appliquer else (APERCU / slug / "index.html")
        cible.parent.mkdir(parents=True, exist_ok=True)
        ancien = cible.read_text(encoding="utf-8") if cible.exists() else None
        cible.write_text(html, encoding="utf-8")
        restes = pl.neutraliser_fichier(cible, p.get("cle") or p["nom"])
        restes += anonymiser.verifier(cible.read_text(encoding="utf-8"), p)
        if restes:
            if ancien is not None:
                cible.write_text(ancien, encoding="utf-8")
            print(f"  ! {slug:32} {metier:16} refuse : {', '.join(restes[:3])}")
            continue
        pl._inject_tracking(cible)
        faits += 1
        print(f"  ✓ {slug:32} {metier:16} -> {cible.relative_to(REPO)}")
    if x.appliquer and faits:
        print("\nA relire puis : git add <dossiers> && git commit && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
