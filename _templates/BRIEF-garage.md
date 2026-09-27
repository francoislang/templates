# Brief — site vitrine pour un garage automobile indépendant

Tu produis **une page HTML complète, autonome, en français**, qui sera montrée
au patron d'un vrai garage pour lui donner envie d'un site. Elle doit être
belle, pas seulement correcte.

## Les faits vérifiés — tu ne peux utiliser QUE ceux-là

- Nom : **Garage Patton**
- Activité : garage automobile indépendant (réparation et entretien)
- Adresse : **157 avenue du Général George S. Patton**, **35700 Rennes**
- Téléphone : **02 99 36 18 08** — lien `tel:+33299361808`
- Coordonnées : latitude 48.125452, longitude -1.6667021
- Horaires : lundi à jeudi **8h–12h et 14h–19h**, vendredi **8h–12h et
  14h–18h30**, fermé samedi, dimanche et jours fériés
- Pas d'adresse électronique publique connue
- **Aucun avis, aucune note** : la source n'en a pas
- Source : OpenStreetMap, nœud 567923341

## Règles absolues — un manquement invalide la page

1. **N'invente aucun fait.** Pas de tarif, pas de délai, pas de durée de
   garantie, pas d'année de création, pas de nombre de salariés, pas de
   véhicule de prêt, pas de marque, pas d'« toutes marques », pas de
   « devis gratuit », pas de « paiement par carte », pas d'accessibilité PMR,
   pas de témoignage. Le patron lira la page : tout ce qu'elle affirme doit
   être vrai.
2. **Une section sans données disparaît.** Pas d'avis ⇒ pas de section avis,
   et rien dans le menu ni le pied de page qui y renvoie, et pas de
   `aggregateRating` dans le JSON-LD. Jamais un bloc vide qui annonce qu'il
   se remplira : c'est ce qui fait qu'une page a l'air inachevée.
3. **La page s'adresse aux clients du garage**, jamais au garagiste. Aucun
   argumentaire de vente de site web sur la page.
4. **Pas de photographie.** Aucune image de banque d'images, aucun lien vers
   une image externe. Tout le visuel doit être fait en CSS et en SVG inline.
   C'est une contrainte, pas un handicap : c'est là que se joue la qualité.
5. Français correct, **avec les accents**, apostrophes typographiques
   bienvenues.

## Contrat technique — non négociable

- **Un seul fichier HTML**, tout en ligne : CSS dans un `<style>`, JS dans un
  `<script>`. Aucune dépendance externe sauf, si tu veux, une police Google
  Fonts (`fonts.googleapis.com`).
- **N'utilise PAS la police Inter** : un détecteur la signale comme la plus
  vue des pages générées. Choisis autre chose et charge-la.
- Tu dois définir ces variables CSS sur `:root`, avec ces noms exacts, parce
  qu'une identité visuelle est injectée par-dessus après coup :

  ```css
  --encre:#101A2E;        /* fond sombre principal */
  --encre-2:#182642;      /* fond des cartes sur sombre */
  --cuivre:#E67E3D;       /* accent, sur fond sombre */
  --cuivre-sombre:#9C4712;/* accent, sur fond clair */
  --txt-accent:#1A1002;   /* texte posé SUR l'accent */
  --brume:#93A1BC;        /* texte secondaire sur sombre */
  --brume-clair:#C9D3E6;  /* texte courant sur sombre */
  --bord-fantome:#526AA8; /* bordure discrète sur sombre */
  ```

  Les couleurs claires (papier, blanc, bordures, texte sur fond clair) sont
  libres, mais **toute couleur d'accent doit passer par `--cuivre` ou
  `--cuivre-sombre`**, jamais en dur. Un bouton plein d'accent porte la
  classe `.btn--c` et son texte est `var(--txt-accent)`.
- Téléphone cliquable, formulaire qui compose un SMS (pas d'adresse mail),
  balisage JSON-LD `AutoRepair`, métadonnées SEO avec la commune,
  `prefers-reduced-motion` respecté, cibles tactiles d'au moins 44 px.
- Mobile d'abord. **Aucun débordement horizontal de 320 à 1280 px.**

## Le garde-fou — tu dois t'en servir

Un détecteur déterministe mesure la page rendue dans un navigateur. Lance-le
et **corrige jusqu'à zéro défaut** :

```
./verifier.sh <ton-fichier>.html
```

Il affiche les anti-patterns trouvés, vérifie le débordement de 320 à 1280 px
et écrit une capture pleine page à côté du fichier. Les entrées marquées
« advisory » ne comptent pas comme des échecs, mais évite-les si tu peux.

Ce qu'il attrape le plus souvent, et qu'il vaut mieux ne pas écrire :
halo radial derrière un hero, tuile d'icône empilée au-dessus d'un titre,
surtitre en capitales espacées au-dessus d'un h2, ombre colorée à zéro
décalage, bordure épaisse sur un seul côté d'une carte, texte fonctionnel
sous 11 px, ligne de plus de 80 caractères, contraste sous 4,5:1, échelle
typographique plate (moins de 1,25× entre deux niveaux), texte gris foncé
laissé sur un fond sombre, capitales sur plus de 30 caractères.

**Regarde ta capture d'écran** avec l'outil Read avant de rendre. Une page
qui passe le détecteur peut être laide ; c'est ton jugement qui tranche.

## Le point de comparaison

`actuel-atelier.html` dans ce dossier est la version en production. Elle est
correcte et passe le détecteur à zéro. Ta page doit être **manifestement plus
belle**, pas juste différente. Lis-la, puis oublie-la : ne la recopie pas.

## Ce que tu rends

Ton fichier HTML à l'emplacement indiqué dans ta consigne, et dans ta réponse
finale, en dix lignes maximum : ta direction artistique en une phrase, les
partis pris de composition, le résultat du détecteur, et ce que tu changerais
avec plus de temps.
