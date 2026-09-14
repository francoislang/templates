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


# Marqueurs de double encodage UTF-8 (texte UTF-8 relu en latin-1).
_MOJIBAKE = ("Ã©", "Ã¨", "Ã ", "Ã§", "Ã´", "Ãª", "â€™", "â€œ", "Ã‰", "Ã€")


def fix_double_encoding(html: str) -> tuple[str, bool]:
    """Repare un texte UTF-8 qui a ete decode en latin-1 puis re-encode.

    Ne touche a rien si le round-trip n'est pas exactement reversible : mieux
    vaut laisser le texte tel quel que le degrader davantage.
    """
    if not any(m in html for m in _MOJIBAKE):
        return html, False
    try:
        repare = html.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return html, False
    return repare, True


def sanitize(html: str, slug: str, contact: dict = None) -> tuple[str, list[str]]:
    url = real_url(slug)
    changes: list[str] = []

    html, repare = fix_double_encoding(html)
    if repare:
        changes.append("double encodage des accents repare")

    new, n = _CANONICAL_RE.subn(lambda m: m.group(1) + url + m.group(3), html)
    if n and new != html:
        changes.append(f"canonical -> {url}")
    html = new

    new, n = _META_URL_RE.subn(lambda m: m.group(1) + url + m.group(3), html)
    if n and new != html:
        changes.append(f"og:url / twitter:url -> {url} ({n})")
    html = new

    # Toute URL absolue vers un hote invente -> on ramene sur le site lui-meme.
    # Les domaines legitimes sont dans ALLOWED_HOSTS, donc tout le reste est une
    # invention du modele : liens, canonical deja traite, mais aussi les champs
    # "url" du JSON-LD, ou une simple reecriture de href ne suffisait pas.
    inventes = sorted(foreign_hosts(html))
    for host in inventes:
        pattern = re.compile(r'https?://' + re.escape(host) + r'[^"\'\s<>)]*', re.IGNORECASE)
        html, n = pattern.subn(url.rstrip("/") + "/", html)
        if n:
            changes.append(f"{n} URL(s) vers le domaine invente {host} corrigee(s)")

    html, changes_mail = _fix_mailto(html, contact or {}, inventes)
    changes.extend(changes_mail)

    return html, changes


_ANCRE_MAILTO = re.compile(
    r'<a\b[^>]*href\s*=\s*["\']mailto:([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL)


def _fix_mailto(html: str, contact: dict, inventes: list) -> tuple[str, list[str]]:
    """Neutralise les adresses email fabriquees par le modele.

    Une adresse n'est consideree comme inventee que si son domaine fait partie
    des domaines inventes deja reperes dans CE document. Sans cette contrainte
    on detruit les exemples legitimes comme placeholder="votre@email.fr".
    """
    vrai_email = (contact.get("email") or "").strip()
    tel = (contact.get("phone") or "").strip()
    suspects = {h.lower().lstrip("www.") for h in inventes}
    changes: list[str] = []
    if not suspects:
        return html, changes

    def est_invente(adresse):
        return adresse.split("@")[-1].lower().lstrip("www.") in suspects

    def remplace(m):
        adresse, texte = m.group(1), m.group(2)
        if not est_invente(adresse):
            return m.group(0)
        if vrai_email:
            changes.append(f"email invente {adresse} -> {vrai_email}")
            return f'<a href="mailto:{vrai_email}">{vrai_email}</a>'
        if tel:
            changes.append(f"email invente {adresse} -> telephone {tel}")
            return f'<a href="tel:{re.sub(r"[^0-9+]", "", tel)}">{tel}</a>'
        changes.append(f"email invente {adresse} retire")
        return texte

    html = _ANCRE_MAILTO.sub(remplace, html)

    # adresses en clair (hors attributs) sur un domaine invente
    for adresse in set(re.findall(r'[\w.+-]+@[\w.-]+\.[a-z]{2,}', html, re.IGNORECASE)):
        if not est_invente(adresse):
            continue
        remplacement = vrai_email or tel or ""
        avant = html
        html = html.replace(adresse, remplacement)
        if html != avant:
            changes.append(f"adresse en clair {adresse} -> {remplacement or 'retiree'}")
    return html, changes


def process(path: Path, apply: bool, contact: dict = None) -> list[str]:
    slug = path.parent.name
    html = path.read_text(encoding="utf-8")
    new, changes = sanitize(html, slug, contact)
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
