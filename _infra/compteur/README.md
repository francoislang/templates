# Compteur de vues des démos

Les sites de démo sont servis par GitHub Pages, qui ne fournit aucun journal
d'accès. Chaque page appelle donc un pixel transparent hébergé sur un Worker
Cloudflare, qui incrémente un compteur dans KV.

Aucun service tiers, aucun cookie, aucune donnée personnelle : on ne stocke
qu'un slug de site, un nombre de vues et deux horodatages.

## Déploiement, une seule fois

```bash
npm install -g wrangler        # si besoin
cd _infra/compteur
wrangler login                 # ouvre le navigateur

# 1. créer le stockage, puis coller l'id renvoyé dans wrangler.toml
wrangler kv namespace create COMPTEUR

# 2. poser le jeton de lecture (invente une longue chaîne aléatoire)
wrangler secret put TOKEN

# 3. déployer
wrangler deploy
```

L'URL renvoyée ressemble à `https://compteur-demos.<toncompte>.workers.dev`.

## Puis, dans le dépôt

Renseigner `.env` :

```
COMPTEUR_URL=https://compteur-demos.<toncompte>.workers.dev
COMPTEUR_TOKEN=<le même jeton que ci-dessus>
```

Injecter le pixel dans les sites déjà générés :

```bash
python3 _scripts/set_tracking.py "$(grep COMPTEUR_URL .env | cut -d= -f2-)"
```

Les sites générés ensuite le reçoivent automatiquement.

## Vérifier

```bash
curl "https://compteur-demos.<toncompte>.workers.dev/p?s=test" -o /dev/null -w "%{http_code}\n"
python3 _scripts/vues_check.py --test
```

## Coût

Offre gratuite Cloudflare : 100 000 requêtes par jour et 1 Go de KV.
Avec 10 démos par jour, on est trois ordres de grandeur en dessous.
