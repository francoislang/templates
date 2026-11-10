# Veille des demandes — spec (07/11/2026)

## But
Repérer chaque jour le maximum de **demandes explicites** (quelqu'un cherche un prestataire) couvertes par les 4 pôles Kerr — site internet, automatisation, IA, développement sur mesure — et les pousser sur Telegram avec une réponse prête à copier. François répond lui-même.

## Contraintes (validées)
- **Aucune automatisation du compte LinkedIn** : pas de scraping, pas d'extension, pas de navigation pilotée. LinkedIn n'est lu qu'à travers ses propres e-mails d'alerte.
- **Sources gratuites uniquement** en v1 (Codeur.com 31,90 €/mois : plus tard si le volume manque).
- **Rien ne « fait IA »** : tri par règles (mots-clés), réponses = modèles fixes à trous remplis avec des faits de la demande. Aucun LLM dans `veille.py`.
- **Aucune maquette dans les réponses** (elles sont fictives) : lien vers la page du pôle sur kerr-studio.com.
- Tourne sur le Mac (launchd), comme `suivi_mails.py`.

## Sources v1
| Source | Accès | Identifiant de dédoublonnage |
|---|---|---|
| LinkedIn — 14 alertes emploi | E-mails `jobalerts-noreply@linkedin.com`, `jobs-noreply@linkedin.com` → libellé Gmail `veille/linkedin` | `job_id` (chiffres de `jobs/view/<id>`) |
| LinkedIn — posts | Pas de lecture auto : 17 liens de recherche « 24 h » envoyés sur Telegram à 8h00 | — |
| BOAMP | API Opendatasoft sans authentification + alertes boamp.fr (libellé `veille/boamp`) | `idweb` |
| Malt | E-mails « nouvelle demande » → libellé `veille/malt` | Message-ID |
| France Travail | API Offres d'emploi v2 (OAuth2 client credentials) | `id` de l'offre |

Hors v1 : Codeur.com, recherche Google de posts, Bark, boutons Telegram « fait / ignoré », CRM.

## Architecture
```
_scripts/
  veille.py            point d'entrée : collecte → tri → dédoublonnage → Telegram
  veille_sources.py    une fonction par source, chacune renvoie une liste de Demande
  li_alert.py          parseur des e-mails d'alerte LinkedIn (HTML + repli texte)
  poles.py             mots-clés : EXCLURE, DEMANDE, SITE, AUTO, IA, DEV + exceptions
  veille_modeles.py    modèles de réponse par (pôle, type de source)
  imap_gmail.py        connexion/recherche IMAP extraite de suivi_mails.py (réutilisée par les deux)
_scripts/launchd/com.francoislang.veille.plist
_scripts/run_veille.sh
```
- `Demande` (dataclass) : `source, ident, titre, entreprise, lieu, budget, date_limite, url, texte`.
- Les sources sont indépendantes : une source en panne est journalisée et signalée dans le bilan, les autres continuent.
- `suivi_mails.py` est modifié uniquement pour importer `imap_gmail.py` (aucun changement de comportement).

## Planification
- launchd : 8h00, 10h00, 12h30, 15h00, 18h00, 21h00.
- 8h00 : en plus, message Telegram des 17 liens de posts + bilan de la veille (nb reçu / retenu par source).

## Tri (`poles.py`)
1. Rejet si un terme de `EXCLURE` (CDI, temps plein, alternance, stage, ESN, régie, portage, senior, « nous recrutons », autopromotion : « je propose mes services », « #opentowork »…).
2. Score par pôle = nb de termes du pôle trouvés (mots entiers, sans accents, minuscules). Retenu si un pôle ≥ 2 (≥ 1 pour BOAMP, dont les objets sont courts).
3. Exceptions : « automatisation » + industriel/automate/PLC → rejet ; « make » seul ignoré (seul `make.com`) ; « ia » en mot entier.
4. Bonus d'affichage : Grand Est / Nancy / télétravail / freelance / mission → ⭐.
5. BOAMP : v1 limitée aux départements du Grand Est (54, 55, 57, 88, 67, 68, 51, 08, 10, 52), tous pôles confondus.

Les listes de départ sont en annexe A ; elles vivent dans `poles.py`, seul fichier à toucher pour ajuster.

## Données
Table `demandes` dans `_data/prospection.db` :
`source, ident, pole, score, titre, entreprise, lieu, budget, date_limite, url, recu_at, envoye_at, statut` — clé unique `(source, ident)`.
- URL LinkedIn stockée **propre** (`https://www.linkedin.com/jobs/view/<id>/`) : jamais l'URL brute (elle contient un `otpToken` de connexion).
- `statut` : `rejete` (avec raison) / `notifie`. Les rejets sont gardés pour régler les mots-clés.

## Telegram
Une carte par demande retenue :
```
🟦 SITE · LinkedIn · Nancy (54) ⭐
Refonte site WordPress — Menuiserie Dupont
Budget : — · Date limite : —
https://www.linkedin.com/jobs/view/4471940499/
Réponse :
`<modèle rempli, bloc copiable>`
```
Pastilles : 🟦 site, 🟩 automatisation, 🟪 IA, 🟧 sur mesure. BOAMP : pas de réponse, à la place date limite + lien DCE + rappel des pièces (DC1/DC2 ou DUME, attestation URSSAF, mémoire technique).
Plafond : 15 cartes par passage ; au-delà, un message récapitulatif avec les liens.

## Modèles de réponse (`veille_modeles.py`)
Règles : 4 à 6 lignes, « vous », 1re phrase = détail précis de la demande, lien = page du pôle, action simple, pas de « Je serais ravi », pas de compliment, pas d'emoji, pas de tiret long. Signature : `François Lang — Kerr, développeur web · 06 32 81 42 00`.

Liens par pôle : site → `kerr-studio.com/sites-internet/` · automatisation → `/automatisation/` · IA → `/intelligence-artificielle/` · sur mesure → `/developpement-sur-mesure/`.

Variables : `{sujet}` (titre nettoyé), `{entreprise}` (vide → tournure sans nom), `{techno}` (premier terme technique trouvé : WordPress, n8n, chatbot…), `{lieu}`.

Exemple (site × offre) :
> Bonjour,
> Vous cherchez quelqu'un pour {sujet}{ chez {entreprise}}. C'est ce que je fais pour des entreprises de votre taille, à Nancy et à distance.
> Ce que je propose et mes prix : kerr-studio.com/sites-internet/
> Dites-moi ce que vous avez aujourd'hui, je vous réponds avec une proposition chiffrée sous 24 h.
> François Lang — Kerr, développeur web · 06 32 81 42 00

Variantes à écrire et faire valider par François : 4 pôles × {offre, post (2 lignes), Malt} = 12 modèles.

## Mise en place manuelle (une fois, ~30 min)
`veille.py --installer` affiche la liste à suivre :
1. Ouvrir les 14 URLs d'alerte LinkedIn (annexe B), cliquer « Définir une alerte », fréquence quotidienne, e-mail.
2. Créer les filtres Gmail → libellés `veille/linkedin`, `veille/boamp`, `veille/malt` (ignorer la boîte de réception).
3. boamp.fr : créer les alertes « site internet », « application web », « logiciel », « chatbot ».
4. Malt : profil (« site internet TPE », « automatisation n8n », « Grand Est »).
5. francetravail.io : créer l'application, renseigner `FT_CLIENT_ID` / `FT_CLIENT_SECRET` dans `.env`.

## Erreurs
- IMAP injoignable / identifiants absents → source ignorée, ligne d'alerte dans le bilan.
- API en erreur ou délai > 20 s → idem, nouvel essai au passage suivant.
- E-mail d'alerte LinkedIn sans aucune offre lisible → journalisé avec son Message-ID (le format a peut-être changé) et signalé une fois par jour.
- Telegram en échec → la demande reste `statut=a_notifier` et repart au passage suivant.

## Tests
- `li_alert.py` : fixtures HTML et texte (FR) dans `_essais/fixtures/` → titre, entreprise, lieu, job_id ; à compléter avec 3 vrais e-mails anonymisés dès réception.
- `poles.py` : table de cas (≈ 30 phrases : vraies demandes, ESN, CDI, autopromotion, automatisme industriel, « Make », « IA ») → pôle attendu ou rejet.
- `veille_modeles.py` : chaque modèle rempli avec et sans entreprise, aucune variable non remplacée, longueur ≤ 6 lignes.
- `veille.py --apercu` : collecte + tri, n'écrit rien et n'envoie rien, affiche les cartes.

## Critère de succès (2 semaines après la mise en place)
Au moins 1 demande pertinente par jour ouvré en moyenne, moins de 30 % de cartes jugées hors sujet, et au moins 10 réponses envoyées. Sinon : ajuster `poles.py`, puis envisager Codeur.com.

---

## Annexe A — mots-clés de départ
- EXCLURE : cdi, temps plein, full-time, alternance, alternant, apprentissage, stage, stagiaire, internship, esn, ssii, régie, sur site client, portage salarial, pré-embauche, habilitation, salaire, k€/an, mutuelle, tickets restaurant, rtt, nous recrutons, rejoignez notre équipe, we're hiring, #hiring, senior, lead dev, automaticien, automatisme, plc, siemens, sap, salesforce, cobol, je propose mes services, disponible pour de nouvelles missions, #opentowork, je suis freelance, j'accompagne, offre spéciale, dm moi.
- DEMANDE (posts uniquement) : je cherche, nous cherchons, je recherche, nous recherchons, qui connaît, recommandez, des recommandations, besoin d'un, besoin d'aide, quelqu'un pour, un prestataire, un freelance, looking for, need a, devis.
- SITE : site vitrine, site internet, site web, refonte, wordpress, webflow, elementor, wix, shopify, woocommerce, prestashop, e-commerce, boutique en ligne, landing page, seo local, référencement, fiche google, google business profile, webdesign, webdesigner, intégrateur, nom de domaine, hébergement, website, responsive.
- AUTO : automatiser, automatisation, automation, zapier, make.com, integromat, n8n, power automate, workflow, no-code, low-code, airtable, notion, google sheets, excel, vba, apps script, macro, crm, hubspot, pipedrive, relance, facturation, devis automatique, synchroniser, emailing.
- IA : intelligence artificielle, ia, chatbot, agent ia, assistant ia, chatgpt, openai, gpt, llm, mistral, rag, ia générative, genai, traitement de documents, ocr, voicebot, ai agent.
- DEV : application web, outil interne, outil sur mesure, sur mesure, application métier, logiciel, extranet, intranet, back-office, dashboard, tableau de bord, api, full stack, fullstack, react, node, python, laravel, symfony, django, saas, mvp, base de données, portail client.

## Annexe B — alertes LinkedIn (filtres : C,T,P = contrat/intérim/temps partiel)
1. ("site vitrine" OR "site internet" OR "refonte") AND (freelance OR indépendant OR prestataire) NOT (stage OR alternance) — France, C/T/P
2. (WordPress OR Webflow OR Elementor) AND (freelance OR mission) NOT (stage OR alternance) — France, C/T/P, télétravail
3. (WooCommerce OR Shopify OR PrestaShop) AND (freelance OR mission) — France, C/T/P, télétravail
4. ("SEO local" OR "Google Business Profile" OR "référencement local") NOT (stage OR alternance) — France, C/T/P
5. (webmaster OR "développeur web" OR "intégrateur web" OR "chargé de site") — Nancy 50 km, C/T/P
6. (n8n OR Zapier OR "Make.com" OR "no-code" OR "low-code") AND (freelance OR mission OR consultant) — France, C/T/P, télétravail
7. ("automatisation des processus" OR "automatisation administrative" OR "automatisation marketing") NOT (automaticien OR automate OR industriel) — France, C/T/P
8. (VBA OR "Google Apps Script" OR "Power Automate" OR "Google Sheets") AND (freelance OR mission) — France, C/T/P, télétravail
9. (HubSpot OR Pipedrive OR Airtable OR Notion OR "intégration CRM") AND (freelance OR mission) — France, C/T/P, télétravail
10. (chatbot OR "agent IA" OR "assistant IA" OR "IA générative") AND (freelance OR mission OR consultant) — France, C/T/P, télétravail
11. ("API OpenAI" OR LLM OR RAG OR "intégration IA") AND (freelance OR mission) NOT (stage OR alternance OR thèse) — France, C/T/P, télétravail
12. ("développeur full stack" OR "développeur fullstack") AND (freelance OR indépendant) — France, C/T, télétravail
13. ("application métier" OR "outil interne" OR extranet OR "back-office") AND (freelance OR prestataire) — France, C/T/P
14. (freelance OR indépendant OR prestataire) AND (web OR digital OR automatisation OR IA OR développeur) — Nancy 50 km, sans filtre de contrat

URLs générées par `veille.py --installer` (paramètres `keywords`, `location`, `geoId=105015875` à vérifier, `f_JT`, `f_WT=2`, `distance=50`). Limite : 10 à 20 alertes selon le compte → créer 1 à 10 d'abord.

## Annexe C — recherches de posts (24 h, triées par date)
Format : `https://www.linkedin.com/search/results/content/?keywords=<requête>&datePosted=%22past-24h%22&sortBy=%22date_posted%22` (à vérifier une fois à la main).
- Site : "cherche un développeur web" OR "recherche un développeur web" · "besoin d'un site" OR "créer mon site" OR "refaire mon site" · "recommandez-moi" site internet · "qui connaît" (webdesigner OR "développeur web" OR "agence web") · "cherche un freelance" (WordPress OR Webflow OR Shopify) · "fiche Google" OR "référencement local" "cherche"
- Automatisation : "cherche un freelance" (automatisation OR n8n OR Make OR Zapier) · "automatiser" (devis OR factures OR relances) "quelqu'un" · "cherche quelqu'un" (Excel OR VBA OR "Google Sheets") · "cherche un prestataire" CRM
- IA : "cherche un freelance" (IA OR chatbot OR "agent IA") · "recherche un développeur IA" OR "cherche un expert IA"
- Sur mesure : "cherche un développeur" (application OR "outil interne" OR "sur mesure") · "recherche un prestataire" (logiciel OR "application métier" OR extranet)
- Tous : "qui connaît un" (développeur OR freelance OR dev) · "je recherche un freelance" OR "nous recherchons un freelance" · "des recommandations" (développeur OR freelance OR "agence web")

## Annexe D — accès API
- BOAMP : `GET https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records?where=<search(objet,"site internet") OR …> AND dateparution >= date'<J-2>'&order_by=dateparution desc&limit=100` — noms de champs (`idweb`, `objet`, `dateparution`, `datelimitereponse`, `code_departement`) à confirmer sur `/explore/dataset/boamp/api/` à l'implémentation.
- France Travail : token `POST https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire` (client_credentials, scope `api_offresdemploiv2`), puis `GET https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search?motsCles=<…>&minCreationDate=<…>` ; codes `typeContrat` à lire dans `/v2/referentiel/typesContrats`.
