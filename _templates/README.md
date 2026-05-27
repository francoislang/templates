# _templates/

Templates Jinja2 pour la génération de sites vitrine. Un fichier `.html.j2` par design/race.

## Fonctionnement

Chaque template est un fichier HTML autonome (CSS + JS inline) rendu via Jinja2. Les variables viennent du fichier YAML correspondant dans `_data/`.

```
generator.py → lit _data/{slug}.yaml → rend _templates/{template}.html.j2 → écrit {slug}/index.html
```

## Templates existants

| Fichier | Race / Élevage de référence |
|---|---|
| `berger-australien.html.j2` | Berger Australien |
| `de-windy-stia.html.j2` | Loulou de Poméranie |
| `des-cotons-de-soie-d-or.html.j2` | Loulou de Poméranie (variante) |
| `domaine-du-quinquis.html.j2` | Cavalier King Charles |
| `elevage-border-collie-mas-andre.html.j2` | Border Collie |
| `ferme-aredienne-des-salines.html.j2` | West Highland White Terrier |
| `gaec-du-chateau-d-alboy.html.j2` | Berger Polonais de Podhale |
| `joyaux-d-anubis.html.j2` | Carlin |
| `la-dolce-vita.html.j2` | Lagotto Romagnolo |
| `marais-de-bremes.html.j2` | Cavalier King Charles (variante) |
| `mellan-schnauzers.html.j2` | Schnauzer |

## Variables Jinja2 standard

Les noms de variables viennent directement du YAML. Syntaxe : `{{ variable }}`.

### Élevage

```
{{ elevage.nom }}
{{ elevage.race }}
{{ elevage.departement }}
{{ elevage.region }}
{{ elevage.code_postal }}
{{ elevage.telephone }}
{{ elevage.url }}
{{ elevage.facebook }}
{{ elevage.facebook_label }}
{{ elevage.since }}
{{ elevage.description_seo }}
{{ elevage.description_hero }}
{{ elevage.description_about }}
```

### Couleurs (injectées dans le CSS via style tag)

```
{{ couleurs.primaire }}
{{ couleurs.accent }}
{{ couleurs.fond }}
```

*(Les noms de clés varient selon le template — certains utilisent des abréviations comme `bur`, `ros`, `crm`)*

### Photos

```
{{ photos.hero }}
{{ photos.og }}
{{ photos.about_1 }}
{{ photos.about_2 }}
{{ photos.race }}
{{ photos.galerie }}          ← liste (itérable avec {% for %})
```

### Portée (optionnel)

```
{{ portee.mere }}
{{ portee.pere }}
{{ portee.date_naissance }}
{{ portee.nb_chiots }}
{{ portee.disponibilite }}
{{ portee.coloris }}          ← liste de {swatch, nom, statut}
{{ portee.timeline }}         ← liste de {numero, date, description}
```

### Reproducteurs

```
{% for r in reproducteurs %}
  {{ r.prenom }}
  {{ r.sexe }}
  {{ r.role }}
  {{ r.photo }}
  {{ r.description }}
{% endfor %}
```

### Témoignages

```
{% for t in temoignages %}
  {{ t.texte }}
  {{ t.auteur }}
  {{ t.chiot }}
  {{ t.avatar }}
{% endfor %}
```

## Ajouter un nouveau template

1. Partir d'un `.html.j2` existant comme base
2. Remplacer toutes les valeurs en dur par des variables Jinja2
3. Nommer le fichier `{race-slug}.html.j2`
4. Ajouter l'entrée dans `BREED_TEMPLATE` dans `_scripts/cloudinary_check.py`
5. Créer un YAML de test dans `_data/` avec `template: {race-slug}`
6. Tester : `python3 _scripts/generator.py` (ou appel direct à `generate_from_config`)

## Règles

- Un seul fichier HTML (CSS et JS inline) — pas de fichiers séparés
- Zéro dépendance npm — Google Fonts via CDN autorisé
- Compatible GitHub Pages (pas de backend, pas de formulaire dynamique)
- Les images viennent de Cloudinary (`res.cloudinary.com/dhwukxhgc`)