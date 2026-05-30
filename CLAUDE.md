# CLAUDE.md — Contexte IA pour ce projet

## But du projet

Activité freelance de François (francois.lang54@gmail.com) : créer des **sites vitrines pour éleveurs canins** et les vendre comme démos personnalisées (~€2000/mois objectif).

Pipeline automatisé :
1. Un cron scrape chien.com tous les jours à 8h
2. Il filtre les éleveurs déjà dans Notion (évite les doublons)
3. Génère un site HTML de démo personnalisé par race
4. Ajoute le prospect dans Notion avec un pitch d'appel
5. Notifie François via Telegram

## Répertoires clés

```
templates/               ← RACINE DU REPO (pas template-elevage/)
├── CLAUDE.md            ← ce fichier
├── README.md
├── .env                 ← secrets locaux (ne pas commiter)
├── .env.example         ← modèle sans valeurs
├── requirements.txt
├── _scripts/            ← pipeline Python
│   ├── agent.py         ← point d'entrée principal
│   ├── scraper.py       ← scraping chien.com
│   ├── generator.py     ← génération HTML depuis template
│   ← notion.py         ← lecture/écriture base Notion
│   ├── telegram.py      ← notifications
│   ├── cloudinary_check.py ← mapping race → photos Cloudinary
│   └── config.py        ← chargement .env
├── _templates/          ← templates Jinja2 (*.html.j2)
├── _data/               ← configs YAML par élevage (un fichier = un client)
├── {slug}/index.html    ← sites générés (un dossier par élevage)
```

**Important** : il existe deux dossiers similaires sur la machine :
- `/Users/francoislang/Local/Perso/templates/` → **repo actif**, tout le code est ici
- `/Users/francoislang/Local/Perso/template-elevage/` → dossier vide lié au remote GitHub Pages

## Lancer l'agent

```bash
cd /Users/francoislang/Local/Perso/templates
python3 _scripts/agent.py
```

Cron configuré (tourne automatiquement à 8h chaque jour) :
```
0 8 * * * cd /Users/francoislang/Local/Perso/templates && python3 _scripts/agent.py >> /tmp/agent-elevage.log 2>&1
```

Logs : `tail -f /tmp/agent-elevage.log`

## Variables d'environnement (.env)

| Variable | Usage |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot `templateAnimalerieBot` |
| `TELEGRAM_CHAT_ID` | `5587588831` (François) |
| `NOTION_SECRET` | Token d'intégration Notion |
| `NOTION_DATABASE_ID` | `3690be11a07480b9bb50c4d1ceaace89` (base Prospection) |
| `CLOUDINARY_CLOUD_NAME` | `dhwukxhgc` |
| `GITHUB_REPO` | `francoislang/templates` |
| `SITES_PER_DAY` | Nombre max de demos/jour (defaut : 10) |
| `PAGES_TO_SCRAPE` | Pages de listing a parcourir (defaut : 5) |

## Stack technique

- **Python 3.9** (important : pas de `list[str]` en annotation, pas de `X | Y` union types)
- **Jinja2** : templates HTML paramétrés (`_templates/*.html.j2`)
- **YAML** : configs par client (`_data/*.yaml`)
- **GitHub Pages** : hébergement statique des démos (`francoislang/templates`)
- **Cloudinary** : CDN photos (`res.cloudinary.com/dhwukxhgc`)
- **Notion API** : base de prospection
- **BeautifulSoup + requests** : scraping chien.com

## Races supportées (templates existants)

| Race | Template / Dossier |
|---|---|
| Border Collie | `elevage-border-collie-mas-andre` |
| Berger Australien | `bois-de-chantalouette` |
| Cavalier King Charles | `domaine-du-quinquis` |
| Schnauzer | `mellan-schnauzers` |
| West Highland White Terrier | `ferme-aredienne-des-salines` |
| Lagotto Romagnolo | `la-dolce-vita` |
| Berger Polonais de Podhale | `gaec-du-chateau-d-alboy` |
| Carlin | `joyaux-d-anubis` |
| Loulou de Poméranie | `des-cotons-de-soie-d-or` |

Pour ajouter une race : créer `_templates/{race}.html.j2` + l'entrée dans `BREED_TEMPLATE` dans `cloudinary_check.py`.

## Ajouter un nouveau client (workflow manuel)

1. Créer `_data/{slug}.yaml` (voir `_data/README.md` pour le format)
2. Vérifier que `template:` pointe vers un fichier `.html.j2` existant dans `_templates/`
3. Lancer : `python3 _scripts/generator.py` (ou via `generate_from_config`)
4. Le dossier `{slug}/index.html` est créé et stagé dans git
5. Commit + push → disponible sur GitHub Pages

## Pièges connus

- Le scraper extrait la race depuis le **slug d'URL** (pas le HTML) — plus fiable
- `fetch_listing_page` utilise le regex `adresse/elevage-[^/]+/[^/]+-\d+\.php$` pour éviter de matcher les liens de pagination
- Python 3.9 : ne pas utiliser les type hints génériques (`list[str]`, `tuple[x,y] | None`)
- Le Notion database ID réel est `3690be11a07480b9bb50c4d1ceaace89` (pas celui dans l'URL de la page)
- Les dossiers `du-bois-de-chantalouette/`, `from-love-of-fairypoms/`, `des-marais-de-bremes/`, `mellan-schnauzers/` dans la racine sont des **tests non commités** — à nettoyer si nécessaire
