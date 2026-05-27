# Spec — Créer un nouveau template d'élevage

Guide de référence pour créer un nouveau template Jinja2 pour une race non encore couverte.

## Contexte

Chaque template est un fichier `.html.j2` dans `_templates/`. Il est rendu par Jinja2 à partir d'un fichier `_data/{slug}.yaml`. Le résultat est un `index.html` autonome (CSS + JS inline) hébergé sur GitHub Pages.

Voir `_templates/README.md` pour la liste des variables disponibles et `_data/README.md` pour le format YAML complet.

## Contraintes techniques

- **Un seul fichier** `index.html` — CSS et JS inline, pas de fichiers séparés
- Zéro dépendance npm — Google Fonts via CDN autorisé
- Compatible GitHub Pages (statique, pas de backend)
- Les images viennent de **Cloudinary** (`res.cloudinary.com/dhwukxhgc`)
- Python 3.9 — ne pas utiliser les annotations de type génériques modernes

## Structure des sections (une seule page, navigation ancre)

1. **Hero** — grande photo plein écran, `{{ elevage.nom }}`, `{{ elevage.description_hero }}`, CTA
2. **À propos** — `{{ elevage.description_about }}`, photos `about_1` et `about_2`
3. **La race** — photo `race`, description générique de la race (hardcodée dans le template)
4. **Reproducteurs** — `{% for r in reproducteurs %}` — photo, prénom, rôle, description
5. **Portée disponible** — `{% if portee %}` — dates, coloris, timeline (optionnel)
6. **Galerie** — `{% for url in photos.galerie %}` — grille photos
7. **Témoignages** — `{% for t in temoignages %}` — texte, auteur, race + ville
8. **Contact** — `{{ elevage.telephone }}`, `{{ elevage.url }}`, `{{ elevage.facebook }}`
9. **Footer** — `{{ elevage.siren }}`, mentions légales, réseaux sociaux

## SEO

Inclure dans le `<head>` :

```html
<title>Élevage {{ elevage.nom }} — {{ elevage.race }} | {{ elevage.departement }}</title>
<meta name="description" content="{{ elevage.description_seo }}">

<!-- Open Graph -->
<meta property="og:title" content="Élevage {{ elevage.nom }}">
<meta property="og:image" content="{{ photos.og }}">

<!-- Schema.org -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "{{ elevage.nom }}",
  "telephone": "{{ elevage.telephone }}"
}
</script>
```

## Couleurs

Injecter les couleurs du YAML dans des variables CSS :

```html
<style>
:root {
  --color-primary: {{ couleurs.primaire }};
  --color-accent: {{ couleurs.accent }};
  --color-bg: {{ couleurs.fond }};
}
</style>
```

## Design

- **Ambiance** : naturelle, chaleureuse, professionnelle
- **Typographie** : une font display distinctive + une font body lisible (Google Fonts) — éviter Inter, Roboto, Arial
- **Responsive** : mobile-first
- **Animations** : légères au scroll (fade-in) — rien de lourd
- Chaque template doit avoir une identité visuelle propre — ne pas tous les faire identiques

## Workflow pour ajouter une nouvelle race

1. Dupliquer un template existant proche visuellement : `cp _templates/berger-australien.html.j2 _templates/{nouvelle-race}.html.j2`
2. Adapter le contenu spécifique à la race (description générique, vocabulaire)
3. Créer un YAML de test dans `_data/test-{race}.yaml` avec `template: {nouvelle-race}`
4. Ajouter l'entrée dans `BREED_TEMPLATE` dans `_scripts/cloudinary_check.py`
5. Tester la génération :
   ```python
   from _scripts.generator import generate_from_config
   generate_from_config("_data/test-{race}.yaml")
   ```
6. Vérifier le rendu dans un navigateur
7. Supprimer le dossier de test, commiter le template

## Ajouter des photos Cloudinary pour une nouvelle race

Les photos sont uploadées sur Cloudinary (`dhwukxhgc`) et référencées dans le YAML.  
Format d'URL : `https://res.cloudinary.com/dhwukxhgc/image/upload/q_auto/f_auto/{public_id}.jpg`

Sans photos Cloudinary pour une race, l'agent le signale dans la notification Telegram
(`⚠️ photos {race} manquantes`) et François doit les uploader manuellement.