# Gabarits par famille — contrat

Chaque famille de `_scripts/metiers.py` a son dossier `_templates/familles/<famille>/` :

```
page.html.j2         la page complète (Jinja2, autoescape, trim_blocks, lstrip_blocks)
metiers.json         {"_defaut": {...}, "<cle_metier>": {...}, ...}  textes propres au métier
illus/<cle>.html     illustration du hero dessinée pour ce métier (facultatif)
illus/_famille.html  illustration neutre de la famille (obligatoire : secours)
```

`_scripts/gabarit_generique.py::remplir(fiche, metier, slug)` choisit `familles/<famille>/page.html.j2` s'il existe, sinon `artisan.html.j2`.
Aperçu : `python3 _scripts/gabarit_generique.py <cle_metier> --nom "…" --commune "…" --cp 54000 --horaires "Mo-Fr 08:30-12:00,14:00-18:30; Sa 09:00-12:00" --sortie /chemin/x.html`
(`--horaires ""` pour tester une fiche sans horaires).

## Variables disponibles dans page.html.j2

| Variable | Contenu |
|---|---|
| `N` | nom de l'entreprise (texte, échappé automatiquement) |
| `nom_js` | le nom en littéral JSON, à utiliser dans le JS (`const NOM = {{ nom_js }};`) |
| `m.cle`, `m.nom`, `m.cherche`, `m.pluriel`, `m.famille` | métier : `plombier`, `Plombier`, `un plombier`, `plombiers` |
| `m.prestations()` | 3 tuples `(titre, texte)` : 2 du métier + « Le reste, de vive voix » |
| `fam` | dict famille : `nav`, `cta`, `prep_titre`, `etapes` (3 tuples titre/texte), `choix` (options du formulaire), `ouverture` (phrase d'accroche), `lieu` (« le salon »), `icone` (path SVG 24×24) |
| `al` | « à Nancy » précédé d'une espace, ou chaîne vide |
| `lieu`, `a_lieu_etab` | « l'atelier », « à l'atelier » |
| `commune`, `court`, `cp`, `cpc` | commune, nom court du lieu (commune ou département), code postal, « 54000 Nancy » — chacun peut être vide |
| `itin` | URL Google Maps d'itinéraire (ou `#contact`) |
| `sem` | booléen : des horaires sont connus |
| `r` | si `sem` : `r.jours` (« Les lundi, mardi… »), `r.principal` (« 8 h 30–12 h · 14 h–18 h 30 »), `r.principal_et`, `r.exceptions`, `r.fermes` (« Fermé le dimanche et les jours fériés »), `r.court` (« Lun–sam »), `r.debut`, `r.fin` (minutes), `r.pause` |
| `semaine` | 7 dicts lundi→dimanche : `jour`, `court`, `ouvert`, `creneaux` [(début, fin) en minutes], `texte` |
| `data_h` | JSON pour le JS « ouvert maintenant » : 7 entrées **dimanche d'abord** (index = `Date.getDay()`), chacune `null` ou liste plate de minutes `[510,720,840,1110]` |
| `table_html` | lignes `<div><dt>Lundi</dt><dd>…</dd></div>` déjà prêtes (Markup), jours fermés en `class="hor--off"` |
| `a_tel`, `tel` | booléen + « 06 XX XX XX XX » |
| `ld_json` | balise `<script type="application/ld+json">` à placer dans `<head>` |
| `description` | meta description |
| `annee` | année en cours |
| `prof` | profil du métier = `metiers.json["_defaut"]` fusionné avec `metiers.json[m.cle]` |
| `illus` | HTML de l'illustration du hero (Markup), `illus_nom` = nom retenu (`couvreur`, `_famille`…) |

## Règles
- Aucun texte propre à un seul métier en dur dans `page.html.j2` : il vient de `m`, `fam` ou `prof`.
- Toujours prévoir `sem` faux (pas d'horaires : « Horaires sur demande ») et `a_tel` faux.
- Le JS ne contient jamais `{{` ni `{%` littéraux après rendu (le générateur refuse la page).
- Le JS doit tolérer une illustration différente (pas d'erreur si un élément animé est absent).
- Adresse toujours « XX rue de l'Exemple », téléphone masqué, aucun courriel, aucun avis, aucun tarif.
