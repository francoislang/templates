#!/usr/bin/env python3
"""Injecte (ou met a jour) le pixel de comptage dans tous les sites de demo.

Les sites sont servis par GitHub Pages, qui ne donne aucun journal d'acces.
Chaque page appelle donc un pixel transparent sur notre Worker Cloudflare
(_infra/compteur), qui tient les compteurs. Pas de service tiers, pas de
cookie, pas de JavaScript : une simple balise <img>, qui fonctionne meme
si le visiteur bloque les scripts.

Le slug transmis est celui du dossier du site, donc chaque demo est
comptee separement.

Idempotent : relancer le script remplace le bloc existant au lieu d'en
ajouter un second.

Usage:
    python3 _scripts/set_tracking.py <url-du-worker>   # injecte partout
    python3 _scripts/set_tracking.py --check           # etat des sites
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PLACEHOLDER = "URL_COMPTEUR_A_REMPLACER"

START = "<!-- tracking -->"
END = "<!-- /tracking -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)


def block(base_url: str, slug: str) -> str:
    """Le pixel de comptage pour un site donne."""
    base = (base_url or "").rstrip("/")
    return (
        f'{START}\n'
        f'  <img src="{base}/p?s={slug}" alt="" width="1" height="1" '
        f'style="position:absolute;left:-9999px" aria-hidden="true">\n'
        f'  {END}'
    )


def targets() -> list[Path]:
    files = sorted(p for p in REPO_ROOT.glob("*/index.html") if not p.parent.name.startswith("_"))
    tmpl = REPO_ROOT / "_templates" / "universal.html.j2"
    if tmpl.exists():
        files.append(tmpl)
    return files


def _slug(path: Path) -> str:
    """Slug du site : le nom de son dossier. Le template Jinja, lui,
    recoit une expression que le rendu remplacera par le vrai slug."""
    if path.name.endswith(".j2"):
        return "{{ elevage.slug }}"
    return path.parent.name


def apply(path: Path, base_url: str) -> str:
    html = path.read_text(encoding="utf-8")
    new_block = block(base_url, _slug(path))

    if BLOCK_RE.search(html):
        # Les anciens sites portaient le bloc dans <head>, ou une balise
        # <img> est invalide. On le retire et on le repose au bon endroit.
        html = BLOCK_RE.sub("", html)
        html = re.sub(r"\n[ \t]*\n[ \t]*\n", "\n\n", html)
        action = "maj"
    else:
        action = "ajout"

    if "</body>" in html:
        # Une balise <img> dans <head> est invalide : le navigateur la
        # deplace dans le corps. Autant l'y mettre nous-memes.
        updated = html.replace("</body>", f"  {new_block}\n</body>", 1)
    elif "</head>" in html:
        updated = html.replace("</head>", f"  {new_block}\n</head>", 1)
    else:
        return "SANS <body> ni <head> -- ignore"

    if updated != html:
        path.write_text(updated, encoding="utf-8")
    return action


def check() -> None:
    tracked = untracked = placeholder = 0
    for p in targets():
        html = p.read_text(encoding="utf-8")
        if PLACEHOLDER in html:
            placeholder += 1
        elif BLOCK_RE.search(html):
            tracked += 1
        else:
            untracked += 1
            print(f"  non traque : {p.relative_to(REPO_ROOT)}")
    print(f"\ntraques: {tracked} | placeholder a remplacer: {placeholder} | non traques: {untracked}")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "--check":
        check()
        return

    base_url = sys.argv[1].strip()
    counts: dict[str, int] = {}
    for p in targets():
        action = apply(p, base_url)
        counts[action] = counts.get(action, 0) + 1
    for action, n in sorted(counts.items()):
        print(f"  {action}: {n}")
    if base_url == PLACEHOLDER or not base_url.startswith("http"):
        print(f"\n/!\\ URL de placeholder posee. Relance avec l'URL du Worker quand il est deploye.")


if __name__ == "__main__":
    main()
