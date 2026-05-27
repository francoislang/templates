# template-elevage

Sites vitrines pour éleveurs canins — démos personnalisées générées automatiquement.

## Objectif business

Créer des sites HTML de démo pour des éleveurs de chiens prospectés sur chien.com, puis les appeler avec un pitch personnalisé. Objectif : €2000/mois en freelance.

## Architecture

```
templates/
├── _scripts/        → Pipeline d'automatisation Python
├── _templates/      → Templates Jinja2 par race (*.html.j2)
├── _data/           → Configs YAML par client (un fichier = un élevage)
├── {slug}/          → Sites générés (un dossier par élevage)
├── .env             → Secrets (Telegram, Notion, Cloudinary)
└── requirements.txt
```

## Pipeline automatisé

Le cron tourne à **8h chaque matin** :

```
scraping chien.com
    → filtre Notion (doublons)
    → génération site HTML
    → ajout Notion + pitch d'appel
    → notification Telegram
```

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env   # puis remplir les valeurs
```

## Lancer manuellement

```bash
python3 _scripts/agent.py
```

## Ajouter un client manuellement

1. Créer `_data/{slug}.yaml` (voir `_data/README.md`)
2. Choisir un template existant dans `_templates/`
3. Générer le site :

```python
from _scripts.generator import generate_from_config
generate_from_config("_data/{slug}.yaml")
```

4. Commit + push → en ligne sur GitHub Pages

## Sites en ligne

`https://francoislang.github.io/template-elevage/{slug}`

## Races avec template

Border Collie · Berger Australien · Cavalier King Charles · Schnauzer ·
West Highland White Terrier · Lagotto Romagnolo · Berger Polonais de Podhale ·
Carlin · Loulou de Poméranie

Voir `_scripts/cloudinary_check.py` pour la liste complète et les mappings.