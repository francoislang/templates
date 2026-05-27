# _scripts/

Pipeline Python d'automatisation de la prospection.

## Fichiers

### `agent.py` — Point d'entrée principal

Orchestre le pipeline complet. À lancer directement ou via cron.

```
1. Récupère les téléphones existants dans Notion
2. Scrape chien.com (N pages)
3. Filtre les nouveaux prospects (téléphone absent de Notion)
4. Pour chaque prospect :
   - Vérifie si des photos Cloudinary existent pour sa race
   - Génère le site HTML de démo
   - Ajoute dans Notion avec pitch d'appel
5. Commit + push Git si des sites ont été créés
6. Envoie un résumé sur Telegram
```

### `scraper.py` — Scraping chien.com

- `fetch_listing_page(page)` : récupère les URLs de profils sur une page de listing
- `fetch_profile(url)` : extrait nom, téléphone, ville, site web d'un profil
- `scrape(pages)` : boucle sur N pages, retourne les profils avec téléphone

**Important** : la race est extraite depuis le **slug d'URL** (`elevage-border-collie` → `"Border Collie"`), pas depuis le HTML (qui est peu fiable). Le dict `SLUG_TO_RACE` liste toutes les races connues.

Pattern URL profil : `adresse/elevage-{race}/{slug}-{id}.php`

### `generator.py` — Génération HTML

Deux fonctions :

- `generate_from_config(config_path)` : lit un YAML `_data/*.yaml`, rend le template Jinja2, écrit `{slug}/index.html`, stage dans git. **Méthode préférée.**
- `generate_site(name, race, phone, city)` : fallback rapide — copie le HTML existant du template de référence et met à jour le `<title>`.

### `notion.py` — Base de prospection

- `get_existing_phones()` : retourne l'ensemble des téléphones normalisés déjà dans la DB
- `add_entry(elevage, races, phone, demo_url, notes)` : ajoute un prospect avec statut "À contacter"

DB Notion : `3690be11a07480b9bb50c4d1ceaace89`

### `telegram.py` — Notifications

- `send(text)` : envoie un message Markdown au bot `templateAnimalerieBot` (chat `5587588831`)

### `cloudinary_check.py` — Photos par race

- `BREED_TEMPLATE` : dict `race → dossier` pointant vers un élevage de référence
- `get_photos_for_breed(race)` : extrait les URLs Cloudinary depuis le `index.html` de référence
- `has_photos_for_breed(race)` : booléen — utile pour avertir si des photos manquent
- `supported_breeds()` : liste des races avec template

### `config.py` — Configuration

Charge `.env` et expose toutes les variables. `REPO_ROOT` pointe vers la racine du repo (`templates/`).

## Variables d'environnement requises

```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
NOTION_SECRET
NOTION_DATABASE_ID
CLOUDINARY_CLOUD_NAME
CLOUDINARY_API_KEY
GITHUB_REPO          (défaut: francoislang/template-elevage)
SITES_PER_DAY        (défaut: 10)
```

## Cron

Configuré sur la machine de François :
```
0 8 * * * cd /Users/francoislang/Local/Perso/templates && python3 _scripts/agent.py >> /tmp/agent-elevage.log 2>&1
```

Logs : `tail -f /tmp/agent-elevage.log`

## Python 3.9

Ne pas utiliser les annotations de type génériques modernes :
- ❌ `list[str]`, `dict[str, int]`, `tuple[str, str] | None`
- ✓ `List[str]` (depuis `typing`), ou pas d'annotation du tout