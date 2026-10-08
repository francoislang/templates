#!/usr/bin/env python3
"""Retire d'une maquette publiee les coordonnees reelles du prospect.

La regle, depuis le 8 octobre : la base garde tout ce qu'il faut pour
contacter la personne, la page publique n'en garde rien de joignable. Le
nom, la commune et le metier restent — c'est ce qui donne sa force a la
demonstration — mais le telephone, le courriel, l'adresse precise, le SIREN
et les coordonnees GPS sont remplaces par des valeurs fictives.

Le numero de remplacement est tire des plages que l'ARCEP reserve a la
fiction (01 99 00, 02 61 91, 03 53 01, 04 65 71, 05 36 49 pour les fixes,
06 39 98 pour les mobiles). Il garde l'indicatif regional du vrai numero,
pour qu'un atelier du Doubs affiche toujours un 03. Ces numeros ne sont
attribues a personne : les afficher ne derange aucun abonne.

Deux fonctions, et l'ordre compte :

    html, faits = appliquer(html, prospect)   # remplace
    restes = verifier(html, prospect)         # controle qu'il ne reste rien

`verifier` est le garde-fou : il relit la page finie et renvoie la liste de
ce qu'il trouve encore. Un appelant qui obtient une liste non vide ne doit
pas publier.

Usage en ligne de commande, pour reprendre les maquettes deja en ligne :

    python3 _scripts/anonymiser.py --apercu            # ce qui serait change
    python3 _scripts/anonymiser.py --appliquer         # tout le depot
    python3 _scripts/anonymiser.py --appliquer <slug>  # une seule maquette
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Plages de fiction de l'ARCEP, par indicatif. Jamais attribuees.
PLAGES = {
    "01": "01 99 00", "02": "02 61 91", "03": "03 53 01",
    "04": "04 65 71", "05": "05 36 49", "09": "09 75 18",
    "06": "06 39 98", "07": "06 39 98",
}
PLAGE_DEFAUT = "01 99 00"
DOMAINE_FICTIF = "exemple-atelier.fr"


def _chiffres(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    if d.startswith("33") and len(d) == 11:
        d = "0" + d[2:]
    return d


def tel_fictif(tel_reel: str, graine: str) -> str:
    """Un numero stable : la meme fiche rend toujours le meme faux numero."""
    d = _chiffres(tel_reel)
    prefixe = PLAGES.get(d[:2], PLAGE_DEFAUT) if len(d) >= 2 else PLAGE_DEFAUT
    n = int(hashlib.sha256(graine.encode()).hexdigest()[:8], 16) % 10000
    return f"{prefixe} {n // 100:02d} {n % 100:02d}"


def _motif_tel(tel: str) -> re.Pattern | None:
    """Reconnait le numero quelle que soit sa mise en forme.

    Un meme numero s'ecrit « 03.81.44.12.00 », « 03 81 44 12 00 »,
    « 0381441200 », « +33 3 81 44 12 00 » ou « tel:+33381441200 » dans une
    seule et meme page. On construit donc le motif chiffre par chiffre.
    """
    d = _chiffres(tel)
    if len(d) != 10:
        return None
    sep = r"[\s.\-/ ‑–]*"
    corps = sep.join(d[1:])              # sans le 0 initial
    return re.compile(rf"(?:\+\s?33{sep}|00{sep}33{sep}|0)" + corps)


def appliquer(html: str, p: dict) -> tuple[str, list[str]]:
    """Remplace les coordonnees reelles. Renvoie la page et ce qui a change."""
    faits: list[str] = []
    graine = (p.get("cle") or p.get("source_url") or p.get("nom") or "x")

    # --- telephone -------------------------------------------------------
    reel = (p.get("telephone") or p.get("phone") or "").strip()
    faux = tel_fictif(reel, graine)
    motif = _motif_tel(reel)
    if motif:
        n = len(motif.findall(html))
        if n:
            html = motif.sub(lambda m: faux, html)
            faits.append(f"telephone remplace ({n} occurrence(s)) -> {faux}")
    # les href tel: gardent parfois une forme compactee
    compact = "+33" + _chiffres(faux)[1:]
    html = re.sub(r'(href=["\']tel:)[^"\']+(["\'])',
                  lambda m: m.group(1) + compact + m.group(2), html)

    # --- courriel --------------------------------------------------------
    mail = (p.get("email") or "").strip()
    if mail:
        n = html.lower().count(mail.lower())
        if n:
            html = re.sub(re.escape(mail), f"contact@{DOMAINE_FICTIF}", html,
                          flags=re.IGNORECASE)
            faits.append(f"courriel remplace ({n} occurrence(s))")

    # --- adresse postale precise ----------------------------------------
    # La commune reste (c'est l'ancrage local du pitch), le numero et la rue
    # partent : c'est ce qui mene au domicile quand l'atelier est chez lui.
    adresse = (p.get("adresse") or "").strip()
    if adresse:
        rue = re.sub(r"\s*\d{5}.*$", "", adresse).strip(" ,")
        if len(rue) > 6 and rue.lower() in html.lower():
            html = re.sub(re.escape(rue), "12 rue de l'Exemple", html,
                          flags=re.IGNORECASE)
            faits.append("adresse precise remplacee")

    # --- SIREN / SIRET ---------------------------------------------------
    for champ in ("siren", "siret"):
        v = (p.get(champ) or "").strip()
        if v and v in html:
            html = html.replace(v, "000 000 000")
            faits.append(f"{champ} retire")

    # --- coordonnees GPS -------------------------------------------------
    # Un couple lat/lon au dix-millieme designe le batiment. On tronque a
    # deux decimales : la carte reste sur la bonne commune, pas sur la porte.
    for champ in ("latitude", "longitude"):
        v = p.get(champ)
        if v in (None, ""):
            continue
        exact = f"{float(v)}"
        arrondi = f"{float(v):.2f}"
        if exact in html:
            html = html.replace(exact, arrondi)
            faits.append(f"{champ} arrondie")
        else:
            prefixe = f"{float(v):.4f}"[:7]
            motif_gps = re.compile(re.escape(prefixe) + r"\d*")
            if motif_gps.search(html):
                html = motif_gps.sub(arrondi, html)
                faits.append(f"{champ} arrondie")
    return html, faits


def fiche_publique(p: dict) -> dict:
    """La fiche telle qu'elle peut servir a fabriquer une page publique.

    C'est la version a donner au modele : il ne doit jamais voir les vraies
    coordonnees, sinon il les recopie quelque part ou le remplacement
    posterieur ne les rattrape pas (un attribut data-, un commentaire, un
    JSON-LD reformate). Le nom, la commune et le code postal restent : ce
    sont eux qui donnent son interet a la demonstration.

    Ce qui disparait : telephone reel, courriel, rue, SIREN, GPS precis.
    """
    graine = (p.get("cle") or p.get("source_url") or p.get("nom") or "x")
    public = dict(p)
    public["telephone"] = tel_fictif(p.get("telephone") or p.get("phone") or "", graine)
    public["phone"] = public["telephone"]
    public["email"] = ""
    public["adresse"] = ""
    public["siren"] = ""
    public["siret"] = ""
    for champ in ("latitude", "longitude"):
        v = p.get(champ)
        public[champ] = round(float(v), 2) if v not in (None, "") else v
    return public


def verifier(html: str, p: dict) -> list[str]:
    """Ce qui subsiste de reel dans la page. Vide = publiable."""
    restes: list[str] = []
    reel = (p.get("telephone") or p.get("phone") or "").strip()
    motif = _motif_tel(reel)
    if motif and motif.search(html):
        restes.append(f"telephone reel ({reel})")
    mail = (p.get("email") or "").strip()
    if mail and mail.lower() in html.lower():
        restes.append(f"courriel reel ({mail})")
    for champ in ("siren", "siret"):
        v = (p.get(champ) or "").strip()
        if v and len(v) >= 9 and v in html:
            restes.append(f"{champ} reel")
    adresse = (p.get("adresse") or "").strip()
    rue = re.sub(r"\s*\d{5}.*$", "", adresse).strip(" ,")
    if len(rue) > 6 and rue.lower() in html.lower():
        restes.append(f"adresse precise ({rue})")
    for champ in ("latitude", "longitude"):
        v = p.get(champ)
        if v in (None, ""):
            continue
        if f"{float(v):.4f}"[:7] in html:
            restes.append(f"{champ} au dix-millieme")
    return restes


# --------------------------------------------------------------------------
# reprise des maquettes deja publiees

def _prospects(db: Path) -> dict[str, dict]:
    """Les fiches des deux bases, indexees par slug de dossier."""
    par_slug: dict[str, dict] = {}
    for base, table, champs, slug_col in (
        ("prospection.db", "prospects",
         "nom, telephone, email, adresse, latitude, longitude, cle", "site_genere"),
        ("annonces.db", "annonces",
         "name, phone, email, '' , '' , '' , source_url", "site_slug"),
    ):
        chemin = db.parent / base
        if not chemin.exists():
            continue
        c = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        try:
            lignes = c.execute(
                f"SELECT {champs}, {slug_col} AS reperage FROM {table} "
                f"WHERE COALESCE({slug_col},'') <> ''").fetchall()
        except sqlite3.OperationalError:
            c.close()
            continue
        for r in lignes:
            cles = list(r.keys())
            slug = (r["reperage"] or "").rstrip("/").rsplit("/", 1)[-1]
            if not slug:
                continue
            par_slug[slug] = {
                "nom": r[cles[0]], "telephone": r[cles[1]], "email": r[cles[2]],
                "adresse": r[cles[3]], "latitude": r[cles[4]],
                "longitude": r[cles[5]], "cle": r[cles[6]],
                "siren": "",
            }
        c.close()
    return par_slug


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?", help="une seule maquette")
    ap.add_argument("--appliquer", action="store_true")
    ap.add_argument("--apercu", action="store_true")
    args = ap.parse_args()
    if not (args.appliquer or args.apercu):
        ap.error("choisis --apercu ou --appliquer")

    fiches = _prospects(REPO_ROOT / "_data" / "x")
    print(f"{len(fiches)} fiche(s) rattachees a une maquette\n")
    touches = intacts = sans_fiche = 0
    for dossier in sorted(REPO_ROOT.glob("*/index.html")):
        slug = dossier.parent.name
        if args.slug and slug != args.slug:
            continue
        if slug.startswith(("_", ".")):
            continue
        p = fiches.get(slug)
        if not p:
            sans_fiche += 1
            continue
        html = dossier.read_text(encoding="utf-8", errors="replace")
        neuf, faits = appliquer(html, p)
        if not faits:
            intacts += 1
            continue
        touches += 1
        print(f"  {slug}")
        for f in faits:
            print(f"      {f}")
        restes = verifier(neuf, p)
        if restes:
            print(f"      /!\\ il reste : {', '.join(restes)}")
        if args.appliquer:
            dossier.write_text(neuf, encoding="utf-8")

    print(f"\n{touches} maquette(s) a corriger, {intacts} deja propres, "
          f"{sans_fiche} sans fiche en base.")
    if args.apercu:
        print("Apercu : aucun fichier n'a ete modifie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
