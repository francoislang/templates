"""Chargement de la configuration depuis .env.

Pas de dependance externe : le .env est parse ici, comme le font deja
crm.py et relance_check.py. Une variable d'environnement existante
n'est jamais ecrasee par le .env.
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env(REPO_ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID")
NOTION_SECRET = _get("NOTION_SECRET")
NOTION_DATABASE_ID = _get("NOTION_DATABASE_ID")
CLOUDINARY_CLOUD_NAME = _get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = _get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = _get("CLOUDINARY_API_SECRET")
GITHUB_REPO = _get("GITHUB_REPO", "francoislang/template-elevage")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY")
PEXELS_API_KEY = _get("PEXELS_API_KEY")
PIXABAY_API_KEY = _get("PIXABAY_API_KEY")
UNSPLASH_ACCESS_KEY = _get("UNSPLASH_ACCESS_KEY")
UMAMI_WEBSITE_ID = _get("UMAMI_WEBSITE_ID")


def _int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)) or default)
    except ValueError:
        return default


SITES_PER_DAY = _int("SITES_PER_DAY", 3)
PAGES_TO_SCRAPE = _int("PAGES_TO_SCRAPE", 5)
