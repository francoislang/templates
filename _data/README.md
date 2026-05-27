# _data/

Fichiers de configuration YAML — un par élevage client. Ces fichiers sont la source de vérité pour la génération des sites.

## Nommage

`{slug-elevage}.yaml` — le slug devient le nom du dossier du site généré.

Exemple : `bois-de-chantalouette.yaml` → `bois-de-chantalouette/index.html`

## Format complet

```yaml
# Champ obligatoire — doit correspondre à un fichier dans _templates/
template: berger-australien

elevage:
  nom: "Du Bois de Chantalouette"
  race: "Berger Australien"
  departement: "Isère (38)"
  region: "Isère"
  code_postal: "38"
  telephone: "06 12 34 56 78"
  siren: ""                          # optionnel
  url: "https://www.example.fr/"     # site actuel de l'éleveur (si existant)
  facebook: "https://www.facebook.com/..."
  facebook_label: "Élevage du Bois de Chantalouette"
  since: "2024"                      # année de création
  description_seo: "Texte optimisé pour les moteurs de recherche (160 chars max)"
  description_hero: "Accroche courte affichée dans le hero"
  description_about: |
    Texte long multi-paragraphe pour la section "À propos".
    Peut contenir plusieurs paragraphes.

couleurs:
  primaire: "#1B3A4B"
  accent: "#D4622A"
  fond: "#F7F4EF"

photos:
  hero: "https://res.cloudinary.com/dhwukxhgc/image/upload/q_auto/f_auto/{id}.jpg"
  og: "https://res.cloudinary.com/..."    # image Open Graph (partage réseaux sociaux)
  about_1: "https://res.cloudinary.com/..."
  about_2: "https://res.cloudinary.com/..."
  race: "https://res.cloudinary.com/..."  # photo illustrant la race
  galerie:
    - "https://res.cloudinary.com/..."
    - "https://res.cloudinary.com/..."
    # ... autant que le template en supporte

# Optionnel — section portée disponible
portee:
  mere: "Arya"
  pere: "Yankee"
  date_naissance: "4 mars 2026"
  nb_chiots: 8
  nb_males: 4
  nb_femelles: 4
  disponibilite: "début mai 2026"
  disponibilite_court: "Mai"
  photo: "https://res.cloudinary.com/..."
  coloris:
    - swatch: "bm"           # code couleur (bm=bleu merle, rt=rouge tri, nt=noir tri...)
      nom: "Bleu merle"
      statut: "Disponible"   # ou "Réservé"
  timeline:
    - numero: "1"
      date: "4 mars 2026"
      description: "Naissance de la portée"

reproducteurs:
  - prenom: "Arya"
    sexe: "femelle"
    role: "Mère · Reproductrice"
    sexe_symbole: "♀"
    photo: "https://res.cloudinary.com/..."
    description: "Description du reproducteur..."
  - prenom: "Yankee"
    sexe: "male"
    role: "Père · Reproducteur"
    sexe_symbole: "♂"
    photo: "https://res.cloudinary.com/..."
    description: "Description du reproducteur..."

temoignages:
  - texte: "Témoignage client..."
    auteur: "Claire &amp; Romain D."
    chiot: "Berger Australien bleu merle · Grenoble"
    avatar: "https://picsum.photos/80/80?random=40"
```

## Champs obligatoires

- `template` — **doit exister** dans `_templates/` sous la forme `{valeur}.html.j2`
- `elevage.nom` — utilisé pour le slug du dossier généré
- `elevage.race` — affiché dans le titre de la page

## Notes

- Les photos viennent de Cloudinary (`dhwukxhgc`). URL format : `https://res.cloudinary.com/dhwukxhgc/image/upload/q_auto/f_auto/{public_id}.jpg`
- Les couleurs varient selon le template — certains utilisent des clés personnalisées (`bur`, `ros`, etc.) plutôt que `primaire`/`accent`/`fond`. Vérifier dans le `.html.j2` correspondant.
- Les champs `siren`, `url`, `facebook` peuvent être vides ou `null` si inconnus
- Le slug du dossier généré est calculé par `generator.slugify(elevage.nom)` : minuscules, accents supprimés, espaces → tirets
