# CLAUDE.md — Contexte IA pour ce projet

## But du projet

Activité freelance de François (francois.lang54@gmail.com) : créer des **sites vitrines pour éleveurs canins** et les vendre comme démos personnalisées (~€2000/mois objectif).

Pipeline automatisé :
1. Un pipeline scrape chien.com quotidiennement (déclenché via Hermes Kanban, plus par crontab direct)
2. Il filtre les éleveurs déjà présents dans le CRM GitHub (Issues + Projects V2)
3. Génère un site HTML de démo (via IA — DeepSeek V4 Pro sur OpenRouter — ou template `universal.html.j2`)
4. Crée une Issue GitHub avec un pitch d'appel personnalisé et l'ajoute au board Projects
5. Notifie François via Telegram

## Répertoires clés

```
templates/                    ← RACINE DU REPO
├── CLAUDE.md                 ← ce fichier
├── README.md
├── SPEC_SITE_ELEVAGE.md
├── .env                      ← secrets locaux (ne pas commiter)
├── .env.example              ← modèle sans valeurs
├── cron_pipeline.py          ← pipeline auto-contenue lancée par le cron Hermes (no_agent)
├── kanban_cron_trigger.py    ← crée la tâche Kanban Hermes quotidienne
├── _close_crm.py             ← utilitaire ponctuel (nettoyage board CRM)
├── _scripts/                 ← pipeline Python
│   ├── pipeline.py           ← pipeline principal (scraper + IA + CRM GitHub + Telegram)
│   ├── agent.py              ← ancien point d'entrée manuel (encore fonctionnel)
│   ├── scraper.py            ← scraping chien.com
│   ├── crm.py                ← CRM GitHub Issues + Projects V2 (remplace Notion)
│   ├── generator.py          ← génération HTML depuis YAML + template Jinja2
│   ├── photos.py             ← recherche photos (Pexels / Unsplash / DuckDuckGo)
│   ├── cloudinary_check.py   ← mapping race → dossier de référence pour photos Cloudinary
│   ├── telegram.py           ← notifications
│   ├── notion.py             ← lecture Notion (legacy)
│   ├── relance_check.py      ← cron de relance J+7 sur le board CRM
│   ├── extract.py            ← extraire un YAML depuis une URL chien.com
│   ├── export_csv.py         ← export CSV des prospects scrapés
│   ├── migrate_to_github.py  ← one-shot Notion → GitHub (déjà exécuté)
│   └── config.py             ← chargement .env
├── _templates/               ← templates Jinja2 (aujourd'hui : `universal.html.j2` uniquement)
├── _data/                    ← configs YAML des anciens sites de référence
├── {slug}/index.html         ← sites générés (un dossier par élevage)
```

## Lancer le pipeline

Manuellement :
```bash
cd /Users/francoislang/Local/Perso/templates
python3 _scripts/pipeline.py       # pipeline actuel (IA + CRM GitHub)
python3 _scripts/agent.py          # ancien pipeline (fonctionne encore)
```

Automatique : le cron est **piloté par Hermes**, pas par crontab. `kanban_cron_trigger.py` insère une tâche dans la base Kanban Hermes (`~/.hermes/hermes-agent`) ; un dispatcher exécute ensuite `cron_pipeline.py` en mode `no_agent`. Rien à maintenir dans `crontab -l` local.

## Variables d'environnement (.env)

| Variable | Usage |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot `templateAnimalerieBot` |
| `TELEGRAM_CHAT_ID` | `5587588831` (François) |
| `GITHUB_TOKEN_PUSH_HERMES` | Token pour le CRM GitHub Issues + Projects |
| `GITHUB_REPO` | `francoislang/templates` |
| `ANTHROPIC_API_KEY` | Claude API |
| `CLOUDINARY_CLOUD_NAME` | `dhwukxhgc` |
| `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Upload d'images |
| `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `UNSPLASH_ACCESS_KEY` | Sources photos |
| `SITES_PER_DAY` | Nombre max de démos/jour (défaut : 3) |
| `PAGES_TO_SCRAPE` | Pages de listing à parcourir (défaut : 5) |
| `NOTION_SECRET`, `NOTION_DATABASE_ID` | **Legacy** — plus le CRM actif, gardé pour `migrate_to_github.py` |

## Stack technique

- **Python 3.9+** (le code a des annotations `list[str]` — vérifier la version d'exécution si erreurs)
- **Jinja2** : template unique `_templates/universal.html.j2`
- **YAML** : configs par client (`_data/*.yaml`) — flux legacy, encore utilisé par `generator.py`
- **GitHub Pages** : hébergement statique des démos (`francoislang/templates`)
- **GitHub Issues + Projects V2** : CRM (GraphQL API)
- **Cloudinary** : CDN photos (`res.cloudinary.com/dhwukxhgc`)
- **BeautifulSoup + requests** : scraping chien.com
- **DeepSeek V4 Pro via OpenRouter** : génération de sites dans `pipeline.py`
- **Hermes Kanban** : orchestration du cron (`~/.hermes/hermes-agent`)

## Templates et races

Il n'y a plus qu'un template Jinja2 : `_templates/universal.html.j2`. Le nouveau pipeline (`pipeline.py`) génère les sites via IA. L'ancien flow YAML → Jinja est encore là mais tous les templates spécifiques par race ont été retirés.

`BREED_TEMPLATE` dans `_scripts/cloudinary_check.py` mappe une race → **dossier d'un site de référence** (source des URLs Cloudinary déjà utilisées pour cette race). Ce n'est pas un mapping vers un fichier `.html.j2`.

⚠️ Plusieurs dossiers référencés dans `BREED_TEMPLATE` ont été supprimés du repo (`mas-andre`, `du-bois-de-chantalouette`, `du-domaine-du-quinquis`, `la-ferme-aredienne-des-salines`, `la-dolce-vita`, `joyaux-d-anubis`, `des-cotons-de-soie-d-or`, `mellan-schnauzers`). `get_photos_for_breed()` retourne `[]` pour ces races → à nettoyer ou à re-générer les sites de référence.

## Ajouter un client (flow legacy YAML)

1. Créer `_data/{slug}.yaml` (voir `_data/README.md`)
2. `template:` doit pointer vers un fichier `.html.j2` existant (aujourd'hui : `universal`)
3. Appeler `generator.generate_from_config()` — crée `{slug}/index.html` et stage dans git
4. Commit + push → disponible sur GitHub Pages

Pour un flow automatisé complet depuis une URL chien.com, utiliser `pipeline.py`.

## Courriels de prospection (Google Workspace)

`_scripts/envoi_mail.py` : quand un prospect de `pipeline_pro.py` a une adresse, le courriel devient le canal prioritaire (avant SMS et appel). Les messages sont traités **après** le push, quand la démo est en ligne.

- `MAIL_MODE=brouillon` (défaut) : dépôt dans les Brouillons Gmail via IMAP, François relit puis envoie.
- `MAIL_MODE=envoi` : envoi direct en SMTP (smtp.gmail.com:587). `off` : pitch uniquement sur Telegram.
- Garde-fous : plafond `MAILS_PAR_JOUR` (20 par défaut), une adresse n'est jamais écrite deux fois, `_data/desinscrits.txt` (STOP) est respecté, en-tête List-Unsubscribe.
- **Jamais de courriel à quelqu'un déjà démarché** (SMS, appel ou courriel) : comparaison par numéro ET par adresse avec prospection.db (fiches déjà traitées), annonces.db (éleveurs), le CRM GitHub (lu en début de tour) et `_data/deja_contactes.txt` (contacts faits à la main). Si le CRM est injoignable, aucun courriel ne part ce tour-là.
- Colonnes ajoutées à `prospects` : `mail_envoye_at`, `mail_statut`.
- Test : `.venv/bin/python _scripts/envoi_mail.py --verifier` puis `--test adresse@exemple.fr`.

### Bascule SMS → courriel (19/10/2026)

- `CANAL_PRO=mail` (défaut) : `pipeline_pro.py` ne prend que les prospects avec adresse, plus aucun pitch SMS/appel sur Telegram (seulement le bilan). Sans identifiants mail, le circuit se met en pause. `CANAL_PRO=tous` pour revenir en arrière.
- `relance_check.py` (board « A relancer ») : relances SMS/téléphone sur Telegram jusqu'au `RELANCES_SMS_JUSQUAU` (2026-10-25) inclus, puis plus rien. Les prospects contactés par courriel en sont exclus.
- `relance_mail.py` (lancé par `run_relances.sh`) : une seule relance par courriel à J+7, dans le même fil, sauf si le prospect a répondu, a dit STOP, ou si le premier courriel est resté en brouillon.

## Prospection multi-métiers (25/10/2026)

91 métiers joignables par courriel (bâtiment, bouche, beauté, restauration, hébergement, commerces, services, animaux…), déclarés dans **`_scripts/metiers.py`** — seul fichier à toucher pour ajouter un métier (étiquettes OSM, famille, 2 prestations, enseignes à exclure). Exclus volontairement : santé, pharmacie, vétérinaire, avocat, notaire, expert-comptable, banque/assurance.

1. `collecte_multi.py --tous --reprendre` : une requête Overpass par département pour tout le catalogue, uniquement les fiches avec courriel ou site. Enseignes écartées par `brand:wikidata`, par nom, puis par domaine partagé (≥3 fiches). `--stats` pour le vivier par métier. À lancer depuis le Mac.
2. `mails_sites.py --metier multi` : cherche l'adresse sur le site de ceux qui n'en ont pas (lancé automatiquement par `run_pro.sh`, `FOUILLE_MAILS_PRO`).
3. `pipeline_pro.py --metier tous` (`METIER_PRO=tous`) : rotation, `METIERS_PAR_TOUR` métiers par jour, le moins récemment servi d'abord. Site de démo depuis `_templates/artisan.html.j2` via `gabarit_generique.py` (sans IA ; `IA_METIERS=1` pour passer par le modèle). Mêmes garde-fous courriel (déjà contacté, désinscrits, plafond `MAILS_PAR_JOUR`).
- Aperçu d'un gabarit : `python3 _scripts/gabarit_generique.py coiffeur --sortie /tmp/a.html`.
- En mode courriel, un prospect sans téléphone est accepté (dédoublonnage par adresse).

### Gabarits par famille (28/10/2026)
- `_templates/familles/<famille>/` : `page.html.j2` + `metiers.json` (textes propres à chacun des 91 métiers) + `illus/<cle>.html` (illustration sur mesure) ou `illus/_famille.html` (secours). Contrat des variables : `_templates/familles/CONTRAT.md`.
- `gabarit_generique.remplir()` prend le gabarit de la famille du métier ; `artisan.html.j2` reste le secours si une famille n'a pas de `page.html.j2`.
- Designs validés : maquettes dans `_maquettes/` (A) et `_maquettes-b/` (B). Retenus : B pour services, loisirs, hébergement, animaux ; A pour les autres.

## Pièges connus

- Le scraper extrait la race depuis le **slug d'URL** (pas le HTML) — plus fiable
- `fetch_listing_page` utilise le regex `adresse/elevage-[^/]+/[^/]+-\d+\.php$` pour éviter de matcher les liens de pagination
- `BREED_TEMPLATE` pointe vers plusieurs dossiers de référence supprimés (voir section templates)
- `cron_pipeline.py` a des chemins hardcodés `/workspace/templates/…` → conçu pour tourner dans le container Hermes, pas en local
- `_scripts/crm.py` lit le token en re-parsant `.env` manuellement — pas via `config.py`
- Le CRM est un GitHub Project V2 (`PVT_kwHOBcibjc4BZSav`) — accès via GraphQL, pas REST
- `requirements.txt` n'existe plus dans le repo — les dépendances doivent être installées à la main ou via un `requirements.txt` externe
