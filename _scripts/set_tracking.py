#!/usr/bin/env python3
"""Injecte (ou met a jour) le snippet de tracking Umami dans tous les sites de demo.

Idempotent : relancer le script remplace le snippet existant au lieu d'en ajouter un second.

Usage:
    python3 _scripts/set_tracking.py <website-id>   # injecte l'ID Umami partout
    python3 _scripts/set_tracking.py --check        # liste les sites traques / non traques
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PLACEHOLDER = "UMAMI_ID_A_REMPLACER"
SCRIPT_SRC = "https://cloud.umami.is/script.js"

START = "<!-- tracking -->"
END = "<!-- /tracking -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)


def block(website_id: str) -> str:
    return (
        f'{START}\n'
        f'  <script defer src="{SCRIPT_SRC}" data-website-id="{website_id}"></script>\n'
        f'  {END}'
    )


def targets() -> list[Path]:
    files = sorted(p for p in REPO_ROOT.glob("*/index.html") if not p.parent.name.startswith("_"))
    tmpl = REPO_ROOT / "_templates" / "universal.html.j2"
    if tmpl.exists():
        files.append(tmpl)
    return files


def apply(path: Path, website_id: str) -> str:
    html = path.read_text(encoding="utf-8")
    new_block = block(website_id)

    if BLOCK_RE.search(html):
        updated = BLOCK_RE.sub(new_block, html)
        action = "maj"
    elif "</head>" in html:
        updated = html.replace("</head>", f"  {new_block}\n</head>", 1)
        action = "ajout"
    else:
        return "SANS <head> -- ignore"

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

    website_id = sys.argv[1].strip()
    counts: dict[str, int] = {}
    for p in targets():
        action = apply(p, website_id)
        counts[action] = counts.get(action, 0) + 1
    for action, n in sorted(counts.items()):
        print(f"  {action}: {n}")
    if website_id == PLACEHOLDER:
        print(f"\n/!\\ ID placeholder pose. Relance avec le vrai ID Umami quand tu l'as.")


if __name__ == "__main__":
    main()
