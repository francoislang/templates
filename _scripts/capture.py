#!/usr/bin/env python3
"""Photographie une demo en ligne et met l'image sur Cloudinary (dossier mails/).

    capturer(url, slug) -> URL Cloudinary (f_jpg) ou None

Chromium sans fenetre (Playwright), format ordinateur 1280 x 800, on attend la
fin des animations. Images jamais supprimees : le mail et sa relance s'y referent.

Installation (une fois, sur le Mac) :
    .venv/bin/pip install playwright && .venv/bin/playwright install chromium
Essai :
    .venv/bin/python _scripts/capture.py https://francoislang.github.io/templates/<slug>/ <slug>
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

LARGEUR, HAUTEUR = 1280, 800
ATTENTE_MS = 5000
TRANSFO = "f_jpg,q_80,w_1072"


def photographier(url: str, chemin: Path) -> bool:
    """Capture PNG de la page ; False si Playwright manque ou si la page casse."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("   capture : Playwright absent (.venv/bin/pip install playwright)")
        return False
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch()
            try:
                page = nav.new_page(viewport={"width": LARGEUR, "height": HAUTEUR}, device_scale_factor=1)
                page.goto(url, wait_until="networkidle", timeout=60_000)
                page.wait_for_timeout(ATTENTE_MS)
                page.screenshot(path=str(chemin), clip={"x": 0, "y": 0, "width": LARGEUR, "height": HAUTEUR})
            finally:
                nav.close()
        return chemin.is_file() and chemin.stat().st_size > 5_000
    except Exception as e:
        print(f"   capture : {e}")
        return False


def capturer(url: str, slug: str) -> str | None:
    """Capture + envoi sur Cloudinary. Renvoie l'URL a mettre dans le mail, ou None."""
    if not url or not slug:
        return None
    with tempfile.TemporaryDirectory() as d:
        png = Path(d) / f"{slug}.png"
        if not photographier(url, png):
            return None
        import photos
        base = photos.upload_fichier(png, f"mails/{slug}")
    if not base or "/image/upload/" not in base:
        return None
    return base.replace("/image/upload/", f"/image/upload/{TRANSFO}/", 1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    import config  # noqa: F401  (charge le .env)
    print(capturer(sys.argv[1], sys.argv[2]) or "echec")
