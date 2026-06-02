import re
from pathlib import Path
import config

# Mapping race → dossier du site de référence (contient les photos Cloudinary pour la race)
# Ajouter une entrée dès qu'un nouveau site de référence est généré pour une race.
BREED_TEMPLATE = {
    # Races avec banque photos Cloudinary — pointe vers le site de référence
    "Border Collie":              "mas-andre",
    "Berger Australien":          "du-bois-de-chantalouette",
    "Cavalier King Charles":      "du-domaine-du-quinquis",
    "Schnauzer":                  "mellan-schnauzers",
    "West Highland White Terrier":"la-ferme-aredienne-des-salines",
    "Lagotto Romagnolo":          "la-dolce-vita",
    "Carlin":                     "joyaux-d-anubis",
    "Loulou de Poméranie":        "des-cotons-de-soie-d-or",
    # Races sans banque photos pour l'instant — pas de photos Cloudinary injectées
    "Berger Polonais de Podhale": None,
    "Berger de Brie":             None,
    "Berger Americain Miniature": None,
    "Pomsky":                     None,
    "Berger Allemand":            None,
    "Bouledogue Francais":        None,
    "Golden Retriever":           None,
    "Shiba Inu":                  None,
    "Cane Corso":                 None,
    "Berger Blanc Suisse":        None,
    "Rhodesian Ridgeback":        None,
    "Vallhund Suédois":           None,
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
