import re
import subprocess
import unicodedata
from pathlib import Path
import config
from cloudinary_check import BREED_TEMPLATE


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def generate_site(name: str, race: str, phone: str, city: str = "",
                  website: str = "") -> tuple[str, str] | None:
    """
    Copie le template de la race, met à jour le titre, crée le dossier.
    Retourne (slug, github_pages_url) ou None si pas de template pour cette race.
    """
    template_folder = BREED_TEMPLATE.get(race)
    if not template_folder:
        return None

    template_path = config.REPO_ROOT / template_folder / "index.html"
    if not template_path.exists():
        return None

    slug = slugify(name)
    target_dir = config.REPO_ROOT / slug
    target_dir.mkdir(exist_ok=True)
    target_file = target_dir / "index.html"

    # Ne pas écraser si le site existe déjà
    if target_file.exists():
        github_url = f"https://{config.GITHUB_REPO.split('/')[0]}.github.io/{config.GITHUB_REPO.split('/')[1]}/{slug}"
        return slug, github_url

    content = template_path.read_text(encoding="utf-8")

    # Mise à jour minimale : titre de la page
    content = re.sub(
        r"<title>[^<]+</title>",
        f"<title>Élevage {name} — {race}</title>",
        content,
        count=1,
    )

    target_file.write_text(content, encoding="utf-8")

    # Stage dans git (le commit/push est fait par l'agent après tous les sites)
    subprocess.run(
        ["git", "-C", str(config.REPO_ROOT), "add", f"{slug}/index.html"],
        check=True, capture_output=True
    )

    github_url = (
        f"https://{config.GITHUB_REPO.split('/')[0]}.github.io"
        f"/{config.GITHUB_REPO.split('/')[1]}/{slug}"
    )
    return slug, github_url
