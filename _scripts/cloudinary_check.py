import re
from pathlib import Path
import config

# Mapping race → dossier template existant
BREED_TEMPLATE = {
    "Border Collie": "elevage-border-collie-mas-andre",
    "Berger Australien": "bois-de-chantalouette",
    "Cavalier King Charles": "domaine-du-quinquis",
    "Schnauzer": "mellan-schnauzers",
    "West Highland White Terrier": "ferme-aredienne-des-salines",
    "Lagotto Romagnolo": "la-dolce-vita",
    "Berger Polonais de Podhale": "gaec-du-chateau-d-alboy",
    "Carlin": "joyaux-d-anubis",
    "Loulou de Poméranie": "des-cotons-de-soie-d-or",
    "Berger de Brie": "bois-de-chantalouette",
    "Berger Americain Miniature": "coeur-de-clayton",  # réutilise berger australien comme fallback
}

_CLOUDINARY_RE = re.compile(
    r'https://res\.cloudinary\.com/[^/]+/image/upload/[^"\'>\s]+'
)


def get_photos_for_breed(race: str) -> list[str]:
    """Return Cloudinary URLs already used for this breed, extracted from the reference template."""
    folder = BREED_TEMPLATE.get(race)
    if not folder:
        return []
    html_path = config.REPO_ROOT / folder / "index.html"
    if not html_path.exists():
        return []
    content = html_path.read_text(encoding="utf-8")
    urls = list(dict.fromkeys(_CLOUDINARY_RE.findall(content)))
    return urls


def has_photos_for_breed(race: str) -> bool:
    return bool(get_photos_for_breed(race))


def supported_breeds() -> list[str]:
    return list(BREED_TEMPLATE.keys())
