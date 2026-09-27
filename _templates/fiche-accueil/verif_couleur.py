#!/usr/bin/env python3
"""Controle les contrastes d'un bloc couleur, avant meme d'assembler la page.

    python3 verif_couleur.py couleur-xxx.css

Quinze paires, tirees des surfaces reelles du gabarit : l'aplat de marque
(--encre), le bandeau de faits (--encre-2), le papier (--creme), la seconde
teinte claire (--creme-2) et les cartes blanches. Une couleur d'accent doit
tenir sur TOUTES les surfaces ou elle est posee, pas seulement sur une.
"""
import re
import sys
from pathlib import Path

PAIRES = [
    ("accent sur l'aplat de marque",   "cuivre",         "encre",   4.5),
    ("accent sur le bandeau de faits", "cuivre",         "encre-2", 4.5),
    ("texte du bouton sur l'accent",   "txt-accent",     "cuivre",  4.5),
    ("accent sombre sur le papier",    "cuivre-sombre",  "creme",   4.5),
    ("accent sombre sur papier 2",     "cuivre-sombre",  "creme-2", 4.5),
    ("accent sombre sur le blanc",     "cuivre-sombre",  "blanc",   4.5),
    ("brume claire sur l'aplat",       "brume-clair",    "encre",   4.5),
    ("brume claire sur le bandeau",    "brume-clair",    "encre-2", 4.5),
    ("brume sur l'aplat",              "brume",          "encre",   4.5),
    ("blanc pur sur l'aplat",          "#FFFFFF",        "encre",   4.5),
    ("blanc pur sur le bandeau",       "#FFFFFF",        "encre-2", 4.5),
    ("texte courant sur le papier",    "texte",          "creme",   4.5),
    ("texte discret sur le papier",    "texte-2",        "creme",   4.5),
    ("texte discret sur le blanc",     "texte-2",        "blanc",   4.5),
    ("encre sur le papier",            "encre",          "creme",   4.5),
    ("bordure fantome sur l'aplat",    "bord-fantome",   "encre",   3.0),
]
OBLIGATOIRES = ["encre", "encre-2", "cuivre", "cuivre-sombre", "txt-accent",
                "brume", "brume-clair", "bord-fantome", "creme", "creme-2",
                "bord", "texte", "texte-2", "blanc"]


def lum(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)


def contraste(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


texte = Path(sys.argv[1]).read_text(encoding="utf-8")
jetons = dict(re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3,8})", texte))
absents = [j for j in OBLIGATOIRES if j not in jetons]
if absents:
    sys.exit("jetons absents ou non litteraux : " + ", ".join(absents))

echecs = 0
for lib, a, b, seuil in PAIRES:
    ca = a if a.startswith("#") else jetons[a]
    cb = b if b.startswith("#") else jetons[b]
    r = contraste(ca, cb)
    ok = r >= seuil
    echecs += not ok
    print(f"  {'OK   ' if ok else 'ECHEC'} {lib:32} {ca} sur {cb}  {r:.2f}:1 (seuil {seuil})")
print(f"\n{len(PAIRES) - echecs}/{len(PAIRES)} paires passees")
sys.exit(1 if echecs else 0)
