import re
import subprocess
import unicodedata
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

import config
from cloudinary_check import BREED_TEMPLATE


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def generate_from_config(config_path: str):
    """
    Génère un site HTML à partir d'un fichier YAML de configuration.
    Utilise data["template"] pour choisir le fichier .html.j2.
    Retourne (slug, github_pages_url) ou None si le template est introuvable.
    """
    with open(config_path) as f:
        data = yaml.safe_load(f)

    template_name = data.get("template")
    if not template_name:
        return None
    template_file = f"{template_name}.html.j2"
    if not (config.REPO_ROOT / "_templates" / template_file).exists():
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
                  website: str = "", description: str = "",
                  siren: str = "", departement: str = "",
                  photo_url: str = "",
                  photos_race: list[str] = None) -> tuple | None:
    """Genere un site vitrine via Jinja2 avec les donnees du scraper."""
    template_folder = BREED_TEMPLATE.get(race)
    if not template_folder:
        return None

    template_file = f"{template_folder}.html.j2"
    if not (config.REPO_ROOT / "_templates" / template_file).exists():
        return None

    slug = slugify(name)
    target_dir = config.REPO_ROOT / slug
    target_dir.mkdir(exist_ok=True)
    target_file = target_dir / "index.html"

    if target_file.exists():
        github_url = f"https://{config.GITHUB_REPO.split('/')[0]}.github.io/{config.GITHUB_REPO.split('/')[1]}/{slug}"
        return slug, github_url

    ph = photos_race or []
    data = {
        "template": template_folder,
        "elevage": {
            "nom": name, "race": race,
            "departement": departement or city or "",
            "region": departement or city or "",
            "code_postal": "", "telephone": phone,
            "siren": siren or "", "url": website or "",
            "facebook": "", "facebook_label": "", "since": "",
            "description_seo": (description[:150] if description else f"Elevage {name} de {race}"),
            "description_hero": (description[:200] if description else f"Elevage {name} — {race}"),
            "description_about": description or "",
        },
        "couleurs": {"primaire": "#1B3A4B", "accent": "#D4622A", "fond": "#F7F4EF"},
        "photos": {
            "hero": photo_url or (ph[0] if ph else ""),
            "og": photo_url or (ph[0] if ph else ""),
            "about_1": ph[1] if len(ph) > 1 else (ph[0] if ph else ""),
            "about_2": ph[2] if len(ph) > 2 else "",
            "race": ph[3] if len(ph) > 3 else (ph[0] if ph else ""),
            "galerie": ph[4:] if len(ph) > 4 else [],
        },
        "reproducteurs": [], "temoignages": [],
    }

    # Rendre le template Jinja2
    from jinja2 import Environment, FileSystemLoader
    env = Environment(
        loader=FileSystemLoader(str(config.REPO_ROOT / "_templates")),
        autoescape=False,
    )
    tmpl = env.get_template(template_file)
    html = tmpl.render(**data)

    target_file.write_text(html, encoding="utf-8")

    # Stage dans git
    import subprocess
    subprocess.run(
        ["git", "-C", str(config.REPO_ROOT), "add", f"{slug}/index.html"],
        check=True, capture_output=True,
    )

    github_url = (
        f"https://{config.GITHUB_REPO.split('/')[0]}.github.io"
        f"/{config.GITHUB_REPO.split('/')[1]}/{slug}"
    )
    return slug, github_url