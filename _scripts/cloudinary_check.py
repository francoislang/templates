import re
from pathlib import Path
import config

# Mapping race → dossier template existant
BREED_TEMPLATE = {
    "Border Collie": "universal",
    "Berger Australien": "universal",
    "Cavalier King Charles": "universal",
    "Schnauzer": "universal",
    "West Highland White Terrier": "universal",
    "Lagotto Romagnolo": "universal",
    "Berger Polonais de Podhale": "universal",
    "Carlin": "universal",
    "Loulou de Poméranie": "universal",
    "Berger de Brie": "universal",
    "Berger Americain Miniature": "universal",
    "Pomsky": "universal",
    "Berger Allemand": "universal",
    "Bouledogue Francais": "universal",
    "Golden Retriever": "universal",
    "Shiba Inu": "universal",
    "Cane Corso": "universal",
    "Berger Blanc Suisse": "universal",
    "Rhodesian Ridgeback": "universal",
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
