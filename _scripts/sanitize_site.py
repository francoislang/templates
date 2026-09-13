#!/usr/bin/env python3
"""Nettoie un site genere par l'IA : supprime les URLs inventees.

Le modele deduit volontiers un nom de domaine plausible depuis le nom de
l'elevage (ex: www.delavalleecaid.fr) et le place dans <link rel=canonical>,
og:url, twitter:url et parfois dans des liens. Ces domaines n'existent pas.

Ce module reecrit toutes ces references vers l'URL reelle du site sur
GitHub Pages, et neutralise les liens sortants vers des hotes non autorises.

Usage:
    python3 _scripts/sanitize_site.py --check          # audit des 68 sites
    python3 _scripts/sanitize_site.py --apply          # corrige tous les sites
    python3 _scripts/sanitize_site.py --apply <slug>   # corrige un seul site
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PAGES_BASE = "https://francoislang.github.io/templates/"

# Hotes legitimes dans un site genere. Tout le reste est une invention.
ALLOWED_HOSTS = {
    "francoislang.github.io",
    "res.cloudinary.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "cdnjs.cloudflare.com",
    "cloud.umami.is",
    "schema.org",
    "www.w3.org",
    "www.google.com",       # iframe Maps eventuelle
    "maps.google.com",
}

_HOST_RE = re.compile(r"https?://([^/\"'\s>]+)")
_META_URL_RE = re.compile(
    r'(<meta\s+[^>]*(?:property|name)\s*=\s*["\'](?:og:url|twitter:url)["\'][^>]*content\s*=\s*["\'])([^"\']*)(["\'])',
    re.IGNORECASE)
_CANONICAL_RE = re.compile(
    r'(<link\s+[^>]*rel\s*=\s*["\']canonical["\'][^>]*href\s*=\s*["\'])([^"\']*)(["\'])',
    re.IGNORECASE)


def real_url(slug: str) -> str:
    return f"{PAGES_BASE}{slug}/"


def foreign_hosts(html: str) -> set[str]:
    return {h for h in _HOST_RE.findall(html)
            if h.lower().lstrip("www.") not in {a.lstrip("www.") for a in ALLOWED_HOSTS}
            and h.lower() not in ALLOWED_HOSTS}


def sanitize(html: str, slug: str) -> tuple[str, list[str]]:
    url = real_url(slug)
    changes: list[str] = []

    new, n = _CANONICAL_RE.subn(lambda m: m.group(1) + url + m.group(3), html)
    if n and new != html:
        changes.append(f"canonical -> {url}")
    html = new

    new, n = _META_URL_RE.subn(lambda m: m.group(1) + url + m.group(3), html)
    if n and new != html:
        changes.append(f"og:url / twitter:url -> {url} ({n})")
    html = new

    # Liens sortants vers un hote invente -> on ramene sur le site lui-meme
    for host in sorted(foreign_hosts(html)):
        pattern = re.compile(r'href\s*=\s*(["\'])https?://' + re.escape(host) + r'[^"\']*\1', re.IGNORECASE)
        html, n = pattern.subn(f'href="{url}"', html)
        if n:
            changes.append(f"lien vers {host} neutralise ({n})")

    return html, changes


def process(path: Path, apply: bool) -> list[str]:
    slug = path.parent.name
    html = path.read_text(encoding="utf-8")
    new, changes = sanitize(html, slug)
    if apply and new != html:
        path.write_text(new, encoding="utf-8")
    return changes


def main() -> None:
    args = [a for a in sys.argv[1:]]
    apply = "--apply" in args
    targets = [a for a in args if not a.startswith("--")]
    if targets:
        paths = [REPO_ROOT / t / "index.html" for t in targets]
    else:
        paths = sorted(p for p in REPO_ROOT.glob("*/index.html") if not p.parent.name.startswith("_"))

    touched = 0
    for p in paths:
        if not p.exists():
            print(f"  absent : {p}")
            continue
        changes = process(p, apply)
        if changes:
            touched += 1
            print(f"{p.parent.name}")
            for ch in changes:
                print(f"    - {ch}")
    verb = "corriges" if apply else "a corriger (mode audit)"
    print(f"\n{touched} site(s) {verb} sur {len(paths)}")


if __name__ == "__main__":
    main()
