# Brief — une palette pour le gabarit « fiche d'accueil »

Le gabarit est figé : tu ne touches ni au HTML, ni à la mise en page, ni aux
effets. Tu ne produis **qu'un bloc CSS `:root`** qui remplace les couleurs.

## Le fichier que tu rends

Un seul fichier, `couleur-<ton-nom>.css`, contenant exactement un bloc
`:root{…}` avec ces quatorze jetons, tous en hexadécimal littéral (pas de
`var()`, pas de `color-mix`, pas de `hsl()` — le contrôleur lit les valeurs) :

```css
:root{
  --encre:#…;         /* l'aplat de marque : bandeau, ouverture, contact */
  --encre-2:#…;       /* le bandeau de faits, juste sous l'ouverture */
  --cuivre:#…;        /* l'accent, posé SUR les fonds sombres */
  --cuivre-sombre:#…; /* l'accent, posé SUR les fonds clairs */
  --txt-accent:#…;    /* le texte posé SUR l'accent (boutons pleins) */
  --brume:#…;         /* texte secondaire sur fond sombre */
  --brume-clair:#…;   /* texte courant sur fond sombre */
  --bord-fantome:#…;  /* bordure discrète sur fond sombre */
  --creme:#…;         /* le papier : fond des sections claires */
  --creme-2:#…;       /* seconde teinte claire : section horaires */
  --blanc:#…;         /* fond des cartes ; blanc pur sauf raison précise */
  --bord:#…;          /* filets et bordures sur fond clair */
  --texte:#…;         /* texte courant sur fond clair */
  --texte-2:#…;       /* texte discret sur fond clair */
}
```

Tu peux ajouter des commentaires. Tu ne peux ajouter **aucune autre règle**.

## Le contrôle de contraste, à lancer avant tout le reste

```
python3 verif_couleur.py couleur-<ton-nom>.css
```

Seize paires, tirées des surfaces réelles du gabarit. **Il faut les seize.**
Le piège habituel : un accent qui tient sur l'aplat de marque mais pas sur le
bandeau de faits, qui est plus clair. Ou un accent sombre qui passe sur le
blanc mais échoue sur la seconde teinte claire.

## Puis la page entière

```
python3 monter.py --couleur couleur-<ton-nom>.css --sortie page-<ton-nom>.html
./verifier.sh page-<ton-nom>.html
```

Le détecteur mesure la page rendue. **Zéro anti-pattern exigé.** Il connaît
plusieurs pièges de couleur : un vert ou un cyan saturé sur fond sombre est
classé « texte néon », un fond crème ou beige est classé palette de page
générée, une ombre colorée à décalage nul est une lueur. `verifier.sh` écrit
aussi une capture pleine page — **regarde-la** avec l'outil Read : une palette
peut passer les seize paires et être laide.

`couleur-actuelle.css` est la palette en place. Compare-toi à elle, et ne la
recopie pas.

## Ce qui est demandé

Une palette **crédible pour un garage automobile indépendant en France**, qui
ne ressemble ni à une marque de logiciel ni à une enseigne de réseau. Elle
doit tenir sur trois fonds différents (l'aplat de marque, le papier clair, la
seconde teinte claire) et garder de la force à petite dose : l'accent occupe
quelques pour cent de la surface, mais il porte tout.

## Ta réponse finale

Huit lignes maximum : l'idée de la palette en une phrase, d'où viennent les
deux couleurs principales, la marge la plus juste parmi les seize paires,
le résultat du détecteur, et ce que tu n'as pas réussi à obtenir.
