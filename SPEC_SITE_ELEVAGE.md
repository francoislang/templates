# Spec — Site vitrine élevage canin

## Contexte

Site vitrine statique pour un éleveur canin français. Le site sera utilisé comme démo commerciale à envoyer à des prospects (éleveurs avec des sites datés ou inexistants). Une fois vendu, seuls les textes, couleurs et photos changent.

## Objectif

Générer un fichier `index.html` unique (HTML + CSS + JS intégrés, pas de fichiers séparés) moderne, responsive, et optimisé SEO local. Le site doit être visuellement impressionnant comparé aux sites d'éleveurs typiques (souvent faits sur FrontPage ou Jimdo circa 2010).

## Stack technique

- **Un seul fichier** `index.html` (CSS et JS inline)
- Zéro dépendance externe (pas de framework, pas de npm)
- Google Fonts autorisé (via CDN)
- Compatible Netlify Drop (glisser-déposer pour mise en ligne)

## Design

- **Ambiance** : naturelle, chaleureuse, professionnelle — inspirée des élevages haut de gamme
- **Couleurs** : tons dorés / crème / vert forêt (adaptables via variables CSS en haut du fichier)
- **Typographie** : une font display élégante + une font body lisible (Google Fonts)
- **Responsive** : mobile-first, parfait sur téléphone
- **Animations** : légères, au scroll (fade-in) — rien de lourd

## Structure des sections (une seule page, navigation ancre)

1. **Hero** — grande photo plein écran, nom de l'élevage, accroche, bouton "Découvrir"
2. **À propos** — présentation de l'éleveur, histoire, valeurs, passion
3. **Nos chiens** — grid de cartes (photo + nom + description courte) pour les reproducteurs
4. **Chiots disponibles** — section avec badges "Disponible" / "Réservé"
5. **Galerie** — grille photos masonry simple
6. **Contact** — adresse, téléphone, email, formulaire simple (HTML only, pas de backend)
7. **Footer** — mentions légales, SIRET, réseaux sociaux

## SEO local

- Balises `<title>` et `<meta description>` optimisées
- Schema.org JSON-LD type `LocalBusiness` + `AnimalShelter`
- Open Graph pour partage Facebook/Instagram
- `sitemap.xml` et `robots.txt` à générer séparément
- Balises alt sur toutes les images

## Contenu placeholder

Utiliser du contenu fictif cohérent pour la démo :
- **Nom de l'élevage** : "Élevage du Val Doré"
- **Race** : Golden Retriever
- **Éleveur** : Marie Fontaine
- **Localisation** : Proche d'Avignon, Var (83)
- **Téléphone** : 06 XX XX XX XX
- **Email** : contact@elevage-val-dore.fr

Toutes les variables facilement modifiables doivent être **commentées dans le code** avec `<!-- MODIFIER : ... -->` pour que le développeur sache quoi changer à chaque nouveau client.

## Variables CSS à exposer en haut du fichier

```css
:root {
  --color-primary: /* ton doré */;
  --color-secondary: /* vert forêt */;
  --color-bg: /* crème clair */;
  --color-text: /* brun foncé */;
  --font-display: /* font titre */;
  --font-body: /* font texte */;
}
```

## Images

Utiliser des images placeholder via `https://picsum.photos` pour la démo. Commenter chaque image avec `<!-- REMPLACER : photo [description] -->`.

## Livrable

Un seul fichier : `index.html`

Le fichier doit pouvoir être glissé directement sur netlify.com/drop et être immédiatement en ligne sans aucune configuration supplémentaire.
