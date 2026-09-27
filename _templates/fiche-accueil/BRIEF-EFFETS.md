# Brief — un jeu d'effets pour le gabarit « fiche d'accueil »

Le gabarit est figé : tu ne touches ni au HTML, ni à la mise en page, ni aux
couleurs. Tu produis **un bloc CSS** et, si nécessaire, **un petit script**,
tous deux injectés en fin de page, donc capables de surcharger la base.

## Les fichiers que tu rends

- `effets-<ton-nom>.css` — obligatoire
- `effets-<ton-nom>.js` — facultatif, sans dépendance externe

## Ce que tu as le droit de toucher

`animation`, `transition`, `transform`, `opacity`, `filter`, `will-change`,
les `@keyframes`, les pseudo-éléments décoratifs que tu crées toi-même, et
en JavaScript : `IntersectionObserver`, les écouteurs d'événements, l'ajout
et le retrait de classes.

**Interdit** : changer une couleur, une taille de police, une marge, un
padding, une largeur, une structure de grille. Si un effet exige un
pseudo-élément, il doit être purement décoratif et `aria-hidden` par nature.

## Ce qu'il y a déjà, et que tu remplaces

La base porte un jeu d'effets repris d'un site de référence : la fiche
d'accueil arrive en tampon (`@keyframes pose`) et se redresse au survol, la
pastille d'état respire par un anneau qui s'écarte (`@keyframes souffle`),
les lignes du registre se soulèvent avec une ombre portée franche et leur
mention de droite se pose en même temps, les boutons se décalent de deux
pixels. Neutralise ce que tu remplaces plutôt que de l'empiler.

Les crochets utiles dans le HTML : `.hdr`, `.ouv`, `.ouv h1`, `.fiche`,
`.fiche dl > div`, `.faits__g > div`, `.puces li`, `.reg li`, `.reg__i`,
`.reg__q`, `.pan`, `.hor > div`, `.ctc__tel`, `.btn`, `.etat`, `.pastille`.

## Les règles

1. **`prefers-reduced-motion: reduce` doit tout désarmer.** La base contient
   déjà une règle générale ; si ton effet a besoin d'un état final explicite
   (une opacité remise à 1, par exemple), écris-le toi-même.
2. **Rien ne doit rester invisible sans JavaScript.** Un bloc à `opacity:0`
   révélé par un observateur est un contenu perdu si le script ne tourne pas :
   conditionne-le à une classe posée par le script, jamais l'inverse.
3. Pas de défilement détourné, pas de parallaxe qui déplace du texte, pas de
   curseur personnalisé, pas de compteur qui s'anime sur un chiffre — les
   chiffres de cette page sont des horaires et une adresse, ils doivent être
   lisibles à l'instant où la page s'affiche.
4. Une animation d'entrée dure moins de 600 ms. Une transition de survol,
   moins de 250 ms.
5. Les cibles tactiles restent à 44 px minimum, et rien ne doit bouger sous
   le doigt au moment du tap.

## Les contrôles

```
python3 monter.py --effets effets-<ton-nom>.css [--js effets-<ton-nom>.js] \
                  --sortie page-<ton-nom>.html
./verifier.sh page-<ton-nom>.html
```

**Zéro anti-pattern exigé.** Le détecteur connaît les tics d'animation :
rebond élastique, lueur colorée pulsée, ombre teintée à décalage nul.

Attention : `:hover` ne se simule pas de façon fiable dans le navigateur sans
fenêtre du bac de test. Pour vérifier un effet de survol, ajoute
temporairement une classe qui rejoue les mêmes déclarations, capture, puis
retire-la. **Regarde tes captures** avec l'outil Read : au repos, en cours
d'entrée, et dans l'état survolé simulé.

## Ta réponse finale

Huit lignes maximum : l'intention en une phrase, la liste des effets avec
leur durée et leur courbe, ce que tu as neutralisé de la base, le résultat du
détecteur, et l'effet que tu as essayé puis abandonné.
