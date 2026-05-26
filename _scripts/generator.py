import re
import subprocess
import unicodedata
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

import config
from cloudinary_check import BREED_TEMPLATE


# Mapping race → fichier template Jinja2
BREED_TEMPLATE_FILE = {
    "Berger Australien": "berger-australien.html.j2",
    # autres races à ajouter au fur et à mesure
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def generate_from_config(config_path: str) -> tuple[str, str] | None:
    """
    Génère un site HTML à partir d'un fichier YAML de configuration.
    Utilise le template Jinja2 correspondant à la race.
    Retourne (slug, github_pages_url) ou None si pas de template pour cette race.
    """
    with open(config_path) as f:
        data = yaml.safe_load(f)

    race = data["elevage"]["race"]
    template_file = BREED_TEMPLATE_FILE.get(race)
    if not template_file:
        return None

    env = Environment(
        loader=FileSystemLoader(str(config.REPO_ROOT / "_templates")),
        autoescape=False,
    )
    tmpl = env.get_template(template_file)
    html = tmpl.render(**data)

    slug = slugify(data["elevage"]["nom"])
    target = config.REPO_ROOT / slug
    target.mkdir(exist_ok=True)
    (target / "index.html").write_text(html, encoding="utf-8")

    subprocess.run(
        ["git", "-C", str(config.REPO_ROOT), "add", f"{slug}/index.html"],
        check=True,
        capture_output=True,
    )

    github_url = (
        f"https://{config.GITHUB_REPO.split('/')[0]}.github.io"
        f"/{config.GITHUB_REPO.split('/')[1]}/{slug}"
    )
    return slug, github_url


def generate_site(name: str, race: str, phone: str, city: str = "",
                  website: str = "") -> tuple[str, str] | None:
    """
    Compatibilité avec agent.py — copie le template de la race, met à jour le titre.
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
        github_url = (
            f"https://{config.GITHUB_REPO.split('/')[0]}.github.io"
            f"/{config.GITHUB_REPO.split('/')[1]}/{slug}"
        )
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
        check=True,
        capture_output=True,
    )

    github_url = (
        f"https://{config.GITHUB_REPO.split('/')[0]}.github.io"
        f"/{config.GITHUB_REPO.split('/')[1]}/{slug}"
    )
    return slug, github_url