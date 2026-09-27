#!/usr/bin/env python3
"""Les dix identites visuelles des sites de demonstration garage.

Le probleme que ca resout : cent sites generes depuis un seul gabarit se
ressemblent tous, et un prospect qui recoit un lien voit immediatement que
c'est une chaine de montage. Dix identites tirees par hachage du nom du
garage suffisent a casser cet effet, tout en gardant une seule page a
maintenir.

Chaque variante n'est PAS un choix esthetique au hasard : les couleurs ont
ete cherchees par programme pour maximiser la vivacite de l'accent SOUS
contrainte de contraste, puis verifiees sur douze paires chacune. Le
critere qui compte et qu'on oublie toujours : une couleur de texte doit
tenir sur le fond des CARTES (encre2), pas seulement sur le fond de
section (encre) — sinon ca passe a l'oeil et echoue la ou on lit vraiment.

Ces douze controles ne suffisent pourtant pas : ils mesurent les jetons
declares, pas les pixels rendus. Le detecteur de controle_design.py, qui rend
la page, a trouve deux defauts qu'ils laissaient passer — « nuit-menthe »
(#289F7B sur bleu nuit) etait classee texte neon cyan sur fond sombre, la
signature couleur la plus reconnaissable d'une page generee, et l'accent de
« basalte-corail » tombait a 4,47:1 sur une surface translucide. La premiere
a ete remplacee par « nuit-sable », la seconde eclaircie.

    python3 _scripts/variantes.py --verifier      # rejoue les 120 controles
    python3 _scripts/variantes.py --lister
    python3 _scripts/variantes.py --css graphite-cuivre
"""
from __future__ import annotations

import argparse
import hashlib

VARIANTES: list[dict[str, str]] = [
    {"nom": "graphite-cuivre", "encre": "#111927", "encre2": "#1C273B", "accent": "#E76A23", "txt_accent": "#1A1002", "accent_clair": "#BF4B08", "brume": "#8491A9", "brume_clair": "#B7C1D1", "bord_fantome": "#506A95", "motif": "arcs", "police": "Manrope"},
    {"nom": "ardoise-safran", "encre": "#111E27", "encre2": "#1C2E3B", "accent": "#C7880A", "txt_accent": "#1A1002", "accent_clair": "#996600", "brume": "#8197A7", "brume_clair": "#B7C7D1", "bord_fantome": "#496E88", "motif": "grille", "police": "Archivo"},
    {"nom": "nuit-sable", "encre": "#111827", "encre2": "#1C253B", "accent": "#D9C08C", "txt_accent": "#1A1002", "accent_clair": "#7A6430", "brume": "#848FA9", "brume_clair": "#B4BCCF", "bord_fantome": "#526798", "motif": "pointille", "police": "Inter"},
    {"nom": "charbon-brique", "encre": "#271811", "encre2": "#3B261C", "accent": "#E7715F", "txt_accent": "#1A1002", "accent_clair": "#D52A10", "brume": "#A99084", "brume_clair": "#D1C0B7", "bord_fantome": "#8B604B", "motif": "diagonale", "police": "Figtree"},
    {"nom": "marine-ambre", "encre": "#111B27", "encre2": "#1C2A3B", "accent": "#D77B09", "txt_accent": "#1A1002", "accent_clair": "#A85D00", "brume": "#8193A7", "brume_clair": "#B7C3D1", "bord_fantome": "#4D6B8F", "motif": "arcs", "police": "Outfit"},
    {"nom": "foret-laiton", "encre": "#11271C", "encre2": "#1C3B2B", "accent": "#C39C28", "txt_accent": "#1A1002", "accent_clair": "#886A11", "brume": "#81A794", "brume_clair": "#C1D7CC", "bord_fantome": "#427B5E", "motif": "grille", "police": "Plus Jakarta Sans"},
    {"nom": "acier-cobalt", "encre": "#111C27", "encre2": "#1C2B3B", "accent": "#5097E7", "txt_accent": "#1A1002", "accent_clair": "#0E6CD8", "brume": "#8194A7", "brume_clair": "#B7C4D1", "bord_fantome": "#4D6E8F", "motif": "diagonale", "police": "Be Vietnam Pro"},
    {"nom": "basalte-corail", "encre": "#111127", "encre2": "#1C1C3B", "accent": "#ED6A5B", "txt_accent": "#1A1002", "accent_clair": "#DA200B", "brume": "#8787AB", "brume_clair": "#B4B4CF", "bord_fantome": "#5D5DA8", "motif": "pointille", "police": "Public Sans"},
    {"nom": "olive-ocre", "encre": "#1C2711", "encre2": "#2B3B1C", "accent": "#DA913E", "txt_accent": "#1A1002", "accent_clair": "#A15E12", "brume": "#94A781", "brume_clair": "#CCD7C1", "bord_fantome": "#5E7B42", "motif": "arcs", "police": "Sora"},
    {"nom": "prune-citron", "encre": "#201127", "encre2": "#311C3B", "accent": "#AE9A13", "txt_accent": "#1A1002", "accent_clair": "#7F6F05", "brume": "#9D84A9", "brume_clair": "#C9B7D1", "bord_fantome": "#84549C", "motif": "grille", "police": "Rubik"}
]

# Seuils WCAG : 4,5:1 pour du texte, 3:1 pour une bordure ou un contour.
PAIRES = [
    ("accent sur fond de section",  "accent",       "encre",      4.5),
    ("accent sur fond de carte",    "accent",       "encre2",     4.5),
    ("texte du bouton sur accent",  "txt_accent",   "accent",     4.5),
    ("accent clair sur blanc",      "accent_clair", "#FFFFFF",    4.5),
    ("accent clair sur papier",     "accent_clair", "#F6F8FB",    4.5),
    ("brume sur fond de section",   "brume",        "encre",      4.5),
    ("brume sur fond de carte",     "brume",        "encre2",     4.5),
    ("brume claire sur section",    "brume_clair",  "encre",      4.5),
    ("brume claire sur carte",      "brume_clair",  "encre2",     4.5),
    ("blanc sur fond de section",   "#FFFFFF",      "encre",      4.5),
    ("blanc sur fond de carte",     "#FFFFFF",      "encre2",     4.5),
    ("bordure fantome sur section", "bord_fantome", "encre",      3.0),
]

MOTIFS = {
    "arcs": """.hero__tread{background-image:repeating-radial-gradient(circle at 88% 6%,
    rgba(255,255,255,.09) 0 2px,transparent 2px 18px);
  mask-image:radial-gradient(62% 62% at 88% 6%,#000 55%,transparent 80%);
  -webkit-mask-image:radial-gradient(62% 62% at 88% 6%,#000 55%,transparent 80%)}""",
    "grille": """.hero__tread{background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px);background-size:46px 46px;
  mask-image:radial-gradient(115% 88% at 80% 10%,#000 22%,transparent 76%);
  -webkit-mask-image:radial-gradient(115% 88% at 80% 10%,#000 22%,transparent 76%)}""",
    "diagonale": """.hero__tread{background-image:repeating-linear-gradient(118deg,
    rgba(255,255,255,.055) 0 2px,transparent 2px 22px);
  mask-image:radial-gradient(110% 90% at 84% 8%,#000 25%,transparent 78%);
  -webkit-mask-image:radial-gradient(110% 90% at 84% 8%,#000 25%,transparent 78%)}""",
    "pointille": """.hero__tread{background-image:radial-gradient(rgba(255,255,255,.10) 1.4px,transparent 1.4px);
  background-size:26px 26px;
  mask-image:radial-gradient(105% 85% at 86% 8%,#000 20%,transparent 74%);
  -webkit-mask-image:radial-gradient(105% 85% at 86% 8%,#000 20%,transparent 74%)}""",
}


def _luminance(hexa: str) -> float:
    h = hexa.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def pour(slug: str) -> dict[str, str]:
    """Variante stable pour un garage : le meme slug donne toujours la meme.

    On hache plutot qu'on ne tire au sort : regenerer un site ne doit pas en
    changer l'apparence, sinon un prospect qui revient sur son lien decouvre
    un autre site.
    """
    n = int(hashlib.sha1(slug.encode("utf-8")).hexdigest()[:8], 16)
    return VARIANTES[n % len(VARIANTES)]


def verifier() -> int:
    """Rejoue tous les controles. Retourne le nombre d'echecs."""
    echecs = 0
    for v in VARIANTES:
        mauvais = []
        for libelle, a, b, seuil in PAIRES:
            ca = a if a.startswith("#") else v[a]
            cb = b if b.startswith("#") else v[b]
            r = contraste(ca, cb)
            if r < seuil:
                mauvais.append(f"{libelle} {r:.2f}:1 (seuil {seuil})")
        if v["motif"] not in MOTIFS:
            mauvais.append(f"motif inconnu : {v['motif']}")
        echecs += len(mauvais)
        etat = "OK   " if not mauvais else "ECHEC"
        print(f"  {etat} {v['nom']:18} {v['accent']}  {v['police']:18} {v['motif']}")
        for m in mauvais:
            print(f"        - {m}")
    total = len(VARIANTES) * len(PAIRES)
    print(f"\n{total - echecs}/{total} controles passes sur {len(VARIANTES)} variantes")
    return echecs


def css(v: dict[str, str]) -> str:
    """Le bloc a injecter dans la page pour appliquer la variante."""
    return f"""/* Identite « {v['nom']} » */
:root{{
  --encre:{v['encre']};
  --encre-2:{v['encre2']};
  --cuivre:{v['accent']};
  --cuivre-sombre:{v['accent_clair']};
  --txt-accent:{v['txt_accent']};
  --brume:{v['brume']};
  --brume-clair:{v['brume_clair']};
  --bord-fantome:{v['bord_fantome']};
}}
.btn--c{{background:var(--cuivre);color:{v['txt_accent']}}}
.saut{{background:var(--cuivre);color:{v['txt_accent']}}}
.band{{background:var(--cuivre);color:{v['txt_accent']}}}
{MOTIFS[v['motif']]}"""


def lien_police(v: dict[str, str]) -> str:
    fam = v["police"].replace(" ", "+")
    return (f'<link href="https://fonts.googleapis.com/css2?family={fam}'
            f':wght@400;500;600;700;800&display=swap" rel="stylesheet">')


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--verifier", action="store_true")
    p.add_argument("--lister", action="store_true")
    p.add_argument("--css", metavar="NOM")
    p.add_argument("--pour", metavar="SLUG", help="quelle variante pour ce slug")
    a = p.parse_args()
    if a.verifier:
        raise SystemExit(1 if verifier() else 0)
    if a.lister:
        for v in VARIANTES:
            print(f"  {v['nom']:18} {v['accent']}  {v['police']:18} {v['motif']}")
        return
    if a.pour:
        v = pour(a.pour)
        print(f"{a.pour} -> {v['nom']} ({v['accent']}, {v['police']}, {v['motif']})")
        return
    if a.css:
        v = next((x for x in VARIANTES if x["nom"] == a.css), None)
        if not v:
            raise SystemExit(f"Variante inconnue : {a.css}")
        print(css(v)); return
    p.print_help()


if __name__ == "__main__":
    main()
