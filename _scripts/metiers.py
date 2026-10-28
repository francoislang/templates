#!/usr/bin/env python3
"""Catalogue des metiers prospectables par courriel.

Un seul endroit pour declarer un metier : la collecte (collecte_multi.py),
la generation du site (gabarit_generique.py) et le pitch (pipeline_pro.py)
lisent tous ce fichier. Ajouter un metier = ajouter une ligne M(...).

Chaque metier porte :
  - les etiquettes OpenStreetMap qui le designent (cle, valeur[, condition]) ;
  - sa famille, qui fixe la palette, l'icone, les etapes « preparer votre
    demande » et les choix du formulaire ;
  - deux grandes familles de prestations, formulees comme ce que fait
    HABITUELLEMENT le metier (jamais comme un fait sur l'entreprise : le bon
    de travail rappelle de les faire confirmer) ;
  - les enseignes de reseau propres au metier, en plus de la liste commune.

Volontairement absents : les professions dont la publicite est encadree
(sante, pharmacie, veterinaire, avocat, notaire, huissier, expert-comptable),
la banque et l'assurance (reseaux), et les metiers deja servis par leur
propre circuit (garage, menuisier, nautique, eleveurs).

    python3 _scripts/metiers.py            liste du catalogue
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# familles
# --------------------------------------------------------------------------

AUTRE = ("Le reste, de vive voix",
         "Ce qui n'entre dans aucune case se règle plus vite par un message "
         "qu'avec une liste qui promet tout.")

FAMILLES: dict[str, dict] = {
    "batiment": {
        "palettes": ["ciment", "acier", "signal"], "lieu": "l'entreprise",
        "nav": "Interventions", "cta": "Décrire mon besoin",
        "prep_titre": "Préparer votre demande",
        "etapes": [("Décrire", "Ce qui ne va pas, ou ce que vous voulez faire, en deux ou trois phrases."),
                   ("Photographier", "Une vue d'ensemble et une vue de près : elles évitent souvent un déplacement pour rien."),
                   ("Situer", "La commune du chantier et vos disponibilités pour une visite.")],
        "choix": ["Une demande de devis", "Un dépannage", "Une question", "Autre"],
        "icone": "M3 11 12 3l9 8M5 9.5V21h14V9.5M10 21v-6h4v6",
        "ouverture": "Vous décrivez votre besoin, vous parlez directement à la personne qui interviendra.",
    },
    "auto": {
        "palettes": ["acier", "signal", "bleu"], "lieu": "l'atelier",
        "nav": "Prestations", "cta": "Décrire mon besoin",
        "prep_titre": "Préparer votre demande",
        "etapes": [("Le véhicule", "Le modèle, l'année et le kilométrage approximatif."),
                   ("Le symptôme", "Ce que vous entendez, voyez ou sentez, et depuis quand."),
                   ("Vos disponibilités", "Les jours où vous pouvez déposer le véhicule.")],
        "choix": ["Entretien", "Réparation", "Une demande de devis", "Autre"],
        "icone": "M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z",
        "ouverture": "Vous expliquez ce qui se passe, vous parlez directement à la personne qui s'en occupera.",
    },
    "beaute": {
        "palettes": ["grenat", "actuelle", "atelier"], "lieu": "le salon",
        "nav": "Prestations", "cta": "Demander un rendez-vous",
        "prep_titre": "Avant de prendre rendez-vous",
        "etapes": [("La prestation", "Ce que vous souhaitez, même approximativement : on vous conseillera."),
                   ("Vos disponibilités", "Deux ou trois créneaux qui vous arrangent."),
                   ("Une précision", "Une sensibilité particulière, une envie, une photo d'inspiration.")],
        "choix": ["Une demande de rendez-vous", "Une question sur une prestation", "Autre"],
        "icone": "M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm0 12a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM8.1 7.9 20 20M8.1 16.1 20 4",
        "ouverture": "Vous dites ce que vous souhaitez, on vous répond pour trouver le bon créneau.",
    },
    "bouche": {
        "palettes": ["artisan", "grenat", "atelier"], "lieu": "la boutique",
        "nav": "La boutique", "cta": "Préparer une commande",
        "prep_titre": "Préparer une commande",
        "etapes": [("Ce qu'il vous faut", "Les produits, même approximativement : on vous conseillera."),
                   ("Pour quand", "Le jour et l'heure de retrait souhaités."),
                   ("Pour combien", "Le nombre de personnes, pour une commande ajustée.")],
        "choix": ["Une commande", "Une question", "Autre"],
        "icone": "M4 15c0-5 3.6-9 8-9s8 4 8 9v3H4zM8 11v3M12 10v4M16 11v3",
        "ouverture": "Vous passez, vous goûtez, vous demandez conseil à ceux qui fabriquent et choisissent.",
    },
    "restauration": {
        "palettes": ["grenat", "atelier", "artisan"], "lieu": "l'établissement",
        "nav": "La maison", "cta": "Demander une table",
        "prep_titre": "Avant de venir",
        "etapes": [("La date", "Le jour et l'heure qui vous conviennent."),
                   ("Le nombre de couverts", "Combien vous serez, enfants compris."),
                   ("Une précision", "Une allergie, un anniversaire, une chaise haute.")],
        "choix": ["Une demande de réservation", "Un groupe ou un événement", "Une question"],
        "icone": "M7 3v8m-2-8v5a2 2 0 0 0 4 0V3M7 11v10M17 3c-2 0-3 2.5-3 6h3v12",
        "ouverture": "Une table, une carte, et quelqu'un qui vous répond directement.",
    },
    "hebergement": {
        "palettes": ["artisan", "bleu", "grenat"], "lieu": "l'établissement",
        "nav": "Séjourner", "cta": "Demander une disponibilité",
        "prep_titre": "Avant de réserver",
        "etapes": [("Les dates", "Arrivée et départ, avec un peu de souplesse si possible."),
                   ("Combien vous serez", "Adultes, enfants, et animaux s'il y en a."),
                   ("Vos questions", "Accès, arrivée tardive, équipement : demandez avant de réserver.")],
        "choix": ["Une demande de disponibilité", "Une question", "Autre"],
        "icone": "M3 18V8m0 6h18v4M21 14v-2a3 3 0 0 0-3-3h-7v5M7 11.5a1.5 1.5 0 1 0 0-.01",
        "ouverture": "Vous demandez vos dates, vous échangez directement avec vos hôtes.",
    },
    "loisirs": {
        "palettes": ["bleu", "signal", "artisan"], "lieu": "la structure",
        "nav": "Activités", "cta": "Demander des renseignements",
        "prep_titre": "Avant de vous inscrire",
        "etapes": [("Votre niveau", "Débutant, confirmé, ou une reprise après une pause."),
                   ("Vos disponibilités", "Les jours et horaires qui vous arrangent."),
                   ("Vos questions", "Équipement, âge minimum, conditions d'accès.")],
        "choix": ["Des renseignements", "Une inscription", "Autre"],
        "icone": "M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z",
        "ouverture": "Vous posez vos questions, vous parlez directement à ceux qui encadrent.",
    },
    "commerce": {
        "palettes": ["actuelle", "bleu", "grenat"], "lieu": "la boutique",
        "nav": "La boutique", "cta": "Poser une question",
        "prep_titre": "Avant de passer",
        "etapes": [("Ce que vous cherchez", "Un article, une référence, ou simplement une idée."),
                   ("Une photo", "Elle vaut souvent mieux qu'une longue description."),
                   ("Pour quand", "Si c'est pour une date précise, dites-le.")],
        "choix": ["Une question", "Une commande ou une réservation", "Autre"],
        "icone": "M5 8h14l-1 13H6zM9 8V6a3 3 0 0 1 6 0v2",
        "ouverture": "Vous passez ou vous écrivez, quelqu'un vous répond et vous conseille.",
    },
    "services": {
        "palettes": ["bleu", "acier", "actuelle"], "lieu": "l'entreprise",
        "nav": "Services", "cta": "Décrire mon besoin",
        "prep_titre": "Préparer votre demande",
        "etapes": [("Décrire", "Votre besoin en quelques phrases, et l'échéance s'il y en a une."),
                   ("Joindre ce qui aide", "Une photo, un document, une référence."),
                   ("Vos disponibilités", "Pour un rappel ou un rendez-vous.")],
        "choix": ["Une demande de devis", "Un rendez-vous", "Une question"],
        "icone": "M4 8h16v11H4zM9 8V5h6v3M4 13h16",
        "ouverture": "Vous exposez votre besoin, vous avez un interlocuteur direct.",
    },
    "animaux": {
        "palettes": ["artisan", "bleu", "grenat"], "lieu": "l'établissement",
        "nav": "Prestations", "cta": "Demander un rendez-vous",
        "prep_titre": "Avant de venir",
        "etapes": [("Votre animal", "Espèce, race ou gabarit, âge, et son caractère."),
                   ("La prestation", "Ce que vous souhaitez, même approximativement."),
                   ("Vos disponibilités", "Deux ou trois créneaux qui vous arrangent.")],
        "choix": ["Une demande de rendez-vous", "Une question", "Autre"],
        "icone": "M8 7.5a1.5 2 0 1 0 0-.01M16 7.5a1.5 2 0 1 0 0-.01M4.5 12a1.5 2 0 1 0 0-.01M19.5 12a1.5 2 0 1 0 0-.01M12 12c-3 0-5 3.5-5 5.5S9 20 12 19c3 1 5 0 5-1.5S15 12 12 12z",
        "ouverture": "Vous présentez votre animal, vous parlez directement à la personne qui s'en occupera.",
        "animaux": True,
    },
    "artisanat": {
        "palettes": ["atelier", "grenat", "artisan"], "lieu": "l'atelier",
        "nav": "L'atelier", "cta": "Parler de mon projet",
        "prep_titre": "Préparer votre demande",
        "etapes": [("L'objet", "Ce que vous voulez créer, restaurer ou réparer."),
                   ("Une photo", "De l'objet, ou d'une inspiration."),
                   ("Votre idée", "Dimensions, matières, échéance : ce que vous savez déjà.")],
        "choix": ["Une création sur mesure", "Une restauration ou réparation", "Une question"],
        "icone": "M4 20l7-7M14 4l6 6-8 8-6-6zM9 9l6 6",
        "ouverture": "Vous montrez votre projet, vous parlez à la personne qui le réalisera.",
    },
}

# --------------------------------------------------------------------------
# enseignes communes a tous les metiers (comparaison par mots entiers)
# --------------------------------------------------------------------------

RESEAUX_COMMUNS = {
    "carrefour market", "carrefour city", "carrefour contact", "carrefour express",
    "e leclerc", "boutique orange", "orange store",
    # grande distribution et galeries
    "carrefour", "leclerc", "e leclerc", "intermarche", "super u", "hyper u",
    "auchan", "casino", "monoprix", "franprix", "lidl", "aldi", "netto",
    "grand frais", "picard", "biocoop", "naturalia", "la vie claire",
    "fnac", "darty", "boulanger", "cultura", "decathlon", "intersport",
    "go sport", "ikea", "conforama", "but", "leroy merlin", "castorama",
    "brico depot", "mr bricolage", "bricomarche", "weldom", "jardiland",
    "truffaut", "botanic", "gamm vert", "point vert", "maxi zoo", "animalis",
    "tom co", "tom&co", "la poste", "relay",
    # restauration en chaine
    "mcdonald s", "mcdonalds", "burger king", "kfc", "quick", "subway",
    "domino s", "dominos", "pizza hut", "five guys", "o tacos", "starbucks",
    "columbus cafe", "buffalo grill", "courtepaille", "hippopotamus",
    "del arte", "la pataterie", "flunch", "leon de bruxelles", "poivre rouge",
    "la boucherie", "au bureau", "o sullivans", "bistro regent", "big fernand",
    "pitaya", "sushi shop", "planet sushi", "paul", "brioche doree",
    "la mie caline", "marie blachere", "ange", "feuillette", "pomme de pain",
    "class croute", "memphis", "volfoni", "la criee", "speed burger",
    "le kiosque a pizzas", "la boite a pizza", "pizza cosy", "speed rabbit",
    "tablapizza", "bagelstein", "cojean", "exki", "prêt a manger", "pret a manger",
    "cora", "match", "spar", "vival", "proxi", "coccinelle",
    # banques, assurances, telephonie
    "orange", "sfr", "bouygues telecom", "free", "credit agricole", "bnp",
    "societe generale", "lcl", "caisse d epargne", "banque populaire",
    "credit mutuel", "cic", "axa", "maaf", "maif", "macif", "matmut", "mma",
    "groupama", "allianz", "generali",
}


# Enseignes dont le nom est aussi un mot, un prenom ou un patronyme courant :
# « Boulangerie Paul Martin », « Cafe du Carrefour », « Plombier a Orange ».
# Comparer le nom a ces mots ecarterait des independants. Ces chaines-la sont
# reperees autrement : par l'etiquette brand:wikidata qu'OpenStreetMap pose
# sur les enseignes, et par le domaine de courriel partage (reseaux_par_domaine).
TROP_COURANTS = {
    "paul", "ange", "orange", "free", "but", "match", "casino", "happy", "save",
    "moving", "vog", "era", "iad", "cer", "fresh", "louise", "the game", "envie",
    "troc", "greet", "comfort", "quality", "flower", "maeva", "action", "casa",
    "tous", "galeries", "lepage", "visual", "repro", "cellier", "o2", "shampoo",
    "spar", "proxi", "coccinelle", "cora", "relay", "castel", "nicolas", "andre",
    "besson", "chausson", "morgan", "mim", "bocage", "lacour", "bailly", "biard",
    "grospiron", "la mobiliere", "la laverie", "self laverie",
    "laverie libre service", "au bon marche", "agatha", "oya", "aquarelle",
    "le jardin des fleurs", "fleurs et nature", "agence de la gare",
    "4 immobilier", "momie", "le bon coin", "b m", "h m", "c a", "v b",
    "barber shop", "barbershop", "les barbiers", "l atelier du coiffeur",
    "nail bar", "ongle et beaute", "thai spa", "mamma mia", "jour de fete",
    "game over", "get out", "copy service", "la boutique du cadeau",
    "music store", "baobab", "jardinerie de", "france jardins", "velo station",
    "cordonnerie minute", "la boucherie", "au bureau", "quick", "la criee",
    "picard", "mma", "boulanger", "leclerc", "carrefour", "jules", "brice",
    "courir", "lacoste", "printemps", "lagrange", "the originals", "giant",
    "trek", "photo service", "mercure", "tom co", "envie", "secrets de pains",
    "la panetiere", "cellier des dauphins", "atol", "laforet",
}


def normaliser(t: str) -> str:
    """minuscules, sans accents, tout ce qui n'est ni lettre ni chiffre -> espace."""
    import unicodedata
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


@dataclass
class Metier:
    cle: str
    nom: str                 # « Plombier »
    cherche: str             # « un plombier » (pitch : « j'ai cherche un plombier a ... »)
    pluriel: str             # « plombiers »
    famille: str
    tags: list               # [(cle, valeur)] ou [(cle, valeur, {cond: val})]
    presta: list             # deux (titre, phrase) ; la troisieme est commune
    schema: str = "LocalBusiness"
    reseaux: set = field(default_factory=set)

    @property
    def fam(self) -> dict:
        return FAMILLES[self.famille]

    def prestations(self) -> list[tuple[str, str]]:
        return [*self.presta[:2], AUTRE]

    def palette(self, slug: str) -> str:
        choix = self.fam["palettes"]
        h = int(hashlib.md5(slug.encode("utf-8")).hexdigest(), 16)
        return choix[h % len(choix)]

    def enseignes(self) -> set[str]:
        return {normaliser(e) for e in (RESEAUX_COMMUNS | set(self.reseaux))} - TROP_COURANTS


def M(cle, nom, cherche, pluriel, famille, tags, presta, schema="LocalBusiness",
      reseaux=()):
    return Metier(cle, nom, cherche, pluriel, famille, list(tags), list(presta),
                  schema, set(reseaux))


# --------------------------------------------------------------------------
# le catalogue
# L'ORDRE COMPTE : un etablissement prend le premier metier dont une etiquette
# correspond. Les cas particuliers (barbier, creperie...) passent donc avant
# le cas general (coiffeur, restaurant...).
# --------------------------------------------------------------------------

_CUISINES = ["mobalpa", "schmidt", "cuisinella", "ixina", "arthur bonnet",
             "socooc", "cuisine plus", "aviva", "nolte", "hygena", "perene",
             "cuisines references", "lapeyre"]
_HOTELS = ["ibis", "ibis budget", "ibis styles", "campanile", "kyriad",
           "b b hotel", "b&b hotel", "premiere classe", "mercure", "novotel",
           "best western", "accor", "formule 1", "hotelf1", "hotel f1",
           "fasthotel", "balladins", "comfort", "quality", "holiday inn",
           "hampton", "radisson", "marriott", "hilton", "adagio", "appart city",
           "citadines", "odalys", "pierre vacances", "pierre & vacances",
           "residhome", "sofitel", "pullman", "ace hotel", "brit hotel",
           "the originals", "greet", "moxy", "okko", "zenitude", "nemea"]
_CAMPINGS = ["huttopia", "yelloh", "yelloh village", "sandaya", "capfun",
             "siblu", "flower", "flower campings", "camping paradis", "sunelia",
             "tohapi", "homair", "vacanceselect", "onlycamp", "ciela village",
             "campings maeva", "maeva", "airotel", "les castels", "village center"]
_OPTIQUE = ["optic 2000", "krys", "afflelou", "alain afflelou", "atol",
            "general d optique", "grand optical", "lissac", "optical center",
            "optique lafayette", "visual", "vision plus", "les opticiens mutualistes",
            "ecouter voir", "acuitis", "jimmy fairly", "sante vision"]
_IMMO = ["century 21", "orpi", "laforet", "foncia", "guy hoquet", "era",
         "stephane plaza", "nestenn", "square habitat", "citya", "nexity",
         "iad", "safti", "capifrance", "optimhome", "l adresse", "arthurimmo",
         "efficity", "sextant", "bsk", "4 immobilier", "proprietes privees",
         "agence de la gare", "immobilier.notaires", "cabinet bedin", "sergic",
         "oralia", "loiselet", "tagerim"]
_COIFFURE = ["franck provost", "jean louis david", "tchip", "dessange",
             "jacques dessange", "saint algue", "camille albane", "fabio salsa",
             "coiff co", "coiff&co", "intermede", "mod s hair", "biguine",
             "jean claude biguine", "self coiffure", "vog", "spoon coiffure",
             "l atelier du coiffeur", "pascal coste", "eric stipa", "toni guy",
             "provost", "shampoo", "beauty success"]
_BEAUTE = ["yves rocher", "sephora", "nocibe", "marionnaud", "body minute",
           "esthetic center", "beauty success", "l occitane", "kiko", "lush",
           "point soleil", "sun city", "the body shop", "passage bleu",
           "ongle et beaute", "nail bar"]
_VETEMENTS = ["zara", "h&m", "h m", "kiabi", "jules", "celio", "camaieu",
              "promod", "pimkie", "etam", "kookai", "naf naf", "bonobo", "cache cache",
              "la halle", "gemo", "c&a", "c a", "primark", "uniqlo", "mango",
              "devred", "brice", "armand thiery", "jennyfer", "okaidi", "obaibi",
              "vertbaudet", "sergent major", "du pareil au meme", "jacadi",
              "petit bateau", "tape a l oeil", "orchestra", "levi s", "lacoste",
              "sezane", "le temps des cerises", "ikks", "morgan", "jacqueline riu",
              "mim", "grain de malice", "bizzbee", "superdry", "galeries lafayette",
              "printemps", "intimissimi", "darjeeling", "princesse tam tam",
              "undiz", "eram", "andre", "besson", "chausson", "san marina", "minelli",
              "bocage", "jonak", "foot locker", "courir", "gemo", "la halle aux chaussures"]
_BIJOUX = ["histoire d or", "marc orian", "julien d orcel", "pandora", "cleor",
           "maty", "agatha", "swarovski", "thomas sabo", "tous", "edenly",
           "louis pion", "galeries", "lepage", "mauboussin"]
_FLEURS = ["monceau fleurs", "rapid flore", "au nom de la rose", "happy",
           "emova", "oya", "oya fleurs", "aquarelle", "le jardin des fleurs",
           "fleurs et nature", "carrement fleurs"]
_SPORT = ["basic fit", "fitness park", "keep cool", "l orange bleue", "on air",
          "neoness", "magic form", "cmg sports club", "club med gym",
          "vita liberte", "wellness sport club", "moving", "amazonia", "curves",
          "elancia", "gigagym", "les cercles de la forme", "freeness",
          "health city", "anytime fitness", "liberty gym", "episod", "keepcool",
          "fit lab", "fitness boutique"]
_FUNERAIRE = ["pfg", "pompes funebres generales", "roc eclerc", "le choix funeraire",
              "funecap", "pompes funebres de france", "simplifia", "lacour",
              "dignite funeraire", "pf de france"]
_DEMENAGEMENT = ["demeco", "les gentlemen du demenagement", "demepool",
                 "france demenagement", "bailly", "grospiron", "biard", "sirva",
                 "la mobiliere"]

CATALOGUE: list[Metier] = [
    # ---------------------------------------------------------- batiment
    M("plombier", "Plombier", "un plombier", "plombiers", "batiment",
      [("craft", "plumber")],
      [("Dépannage", "Fuite, canalisation bouchée, robinet ou chasse d'eau qui ne tient plus."),
       ("Installation", "Salle de bains, cuisine, chauffe-eau : des réseaux posés neufs ou refaits.")],
      "Plumber"),
    M("electricien", "Électricien", "un électricien", "électriciens", "batiment",
      [("craft", "electrician")],
      [("Dépannage", "Panne, disjoncteur qui saute, prise ou éclairage hors service."),
       ("Installation et rénovation", "Tableau, circuits, points lumineux : une installation créée ou remise à niveau.")],
      "Electrician"),
    M("chauffagiste", "Chauffagiste", "un chauffagiste", "chauffagistes", "batiment",
      [("craft", "hvac"), ("craft", "heating_engineer")],
      [("Chauffage", "Chaudière, pompe à chaleur, radiateurs : installation et remplacement."),
       ("Entretien et dépannage", "L'entretien annuel et les pannes, avant que l'hiver ne s'installe.")],
      "HVACBusiness"),
    M("couvreur", "Couvreur", "un couvreur", "couvreurs", "batiment",
      [("craft", "roofer")],
      [("Couverture", "Tuiles, ardoises, zinc : une toiture posée, refaite ou réparée."),
       ("Zinguerie et étanchéité", "Gouttières, faîtages, solins : ce qui fait que l'eau s'en va au bon endroit.")],
      "RoofingContractor"),
    M("macon", "Maçon", "un maçon", "maçons", "batiment",
      [("craft", "builder"), ("craft", "mason"), ("craft", "bricklayer")],
      [("Gros œuvre", "Fondations, murs, dalles : la structure, posée d'aplomb."),
       ("Rénovation et extension", "Ouvertures, agrandissements, reprises : la maison adaptée à ce qu'on en fait aujourd'hui.")],
      "GeneralContractor"),
    M("peintre", "Peintre en bâtiment", "un peintre en bâtiment", "peintres", "batiment",
      [("craft", "painter")],
      [("Peinture intérieure", "Murs, plafonds, boiseries : préparation des supports et finition soignée."),
       ("Façades et revêtements", "Ravalement, enduits, revêtements muraux et de sol.")],
      "HousePainter"),
    M("plaquiste", "Plaquiste, plâtrier", "un plaquiste", "plaquistes", "batiment",
      [("craft", "plasterer"), ("craft", "drywall")],
      [("Cloisons et doublages", "Plaques de plâtre, faux plafonds, doublages isolants."),
       ("Plâtrerie et finitions", "Enduits, bandes, reprises : des surfaces prêtes à peindre.")],
      "GeneralContractor"),
    M("carreleur", "Carreleur", "un carreleur", "carreleurs", "batiment",
      [("craft", "tiler")],
      [("Carrelage", "Sols et murs, intérieur ou terrasse."),
       ("Pièces d'eau", "Douche, crédence, salle de bains : les pièces humides refaites.")],
      "GeneralContractor"),
    M("serrurier", "Serrurier", "un serrurier", "serruriers", "batiment",
      [("craft", "locksmith"), ("shop", "locksmith")],
      [("Ouverture et dépannage", "Porte claquée, clé perdue, serrure bloquée."),
       ("Sécurisation", "Serrures, cylindres, renforcement de porte.")],
      "Locksmith", ["serrurerie minute", "mister minit", "minit"]),
    M("vitrier", "Vitrier, miroitier", "un vitrier", "vitriers", "batiment",
      [("craft", "glaziery")],
      [("Remplacement de vitrage", "Vitre cassée, double vitrage, miroirs et verre découpé."),
       ("Vitrines et verrières", "Vitrines de commerce, parois de douche, verrières.")],
      "HomeAndConstructionBusiness", ["france vitrage"]),
    M("metallier", "Métallier, ferronnier", "un métallier", "métalliers", "batiment",
      [("craft", "metal_construction"), ("craft", "blacksmith"), ("craft", "welder")],
      [("Métallerie", "Portails, garde-corps, escaliers, grilles : l'acier sur mesure."),
       ("Ferronnerie et soudure", "Pièces forgées, réparations, soudure à l'atelier ou sur place.")],
      "HomeAndConstructionBusiness"),
    M("paysagiste", "Paysagiste", "un paysagiste", "paysagistes", "batiment",
      [("craft", "gardener"), ("craft", "landscaper")],
      [("Création", "Plantations, pelouses, allées, terrasses : un jardin dessiné et posé."),
       ("Entretien", "Taille, tonte, débroussaillage : le jardin tenu au fil des saisons.")],
      "HomeAndConstructionBusiness", ["o2", "shiva", "adhap", "france jardins"]),
    M("isolation", "Isolation", "un artisan en isolation", "artisans de l'isolation", "batiment",
      [("craft", "insulation")],
      [("Isolation", "Combles, murs, planchers : les déperditions repérées et traitées."),
       ("Rénovation énergétique", "Le confort d'hiver et d'été, poste par poste.")],
      "HomeAndConstructionBusiness"),
    M("ramoneur", "Ramoneur", "un ramoneur", "ramoneurs", "batiment",
      [("craft", "chimney_sweeper")],
      [("Ramonage", "Conduits de cheminée, de poêle et de chaudière."),
       ("Entretien du conduit", "Débistrage, inspection, tubage.")],
      "HomeAndConstructionBusiness"),
    M("piscine", "Pisciniste", "un pisciniste", "piscinistes", "batiment",
      [("shop", "swimming_pool"), ("craft", "swimming_pool")],
      [("Construction et rénovation", "Bassins, liners, margelles, équipements."),
       ("Entretien et dépannage", "Mise en route, hivernage, filtration, réparations.")],
      "HomeAndConstructionBusiness", ["desjoyaux", "piscinelle", "diffazur",
                                      "everblue", "cash piscines", "hydro sud",
                                      "mondial piscine", "l esprit piscine",
                                      "aquilus", "magiline"]),
    M("cuisiniste", "Cuisiniste", "un cuisiniste", "cuisinistes", "batiment",
      [("shop", "kitchen")],
      [("Conception", "Plans, façades et équipements, à vos mesures."),
       ("Pose", "Montage, raccordements, finitions.")],
      "HomeAndConstructionBusiness", _CUISINES),
    M("tailleur-pierre", "Tailleur de pierre", "un tailleur de pierre", "tailleurs de pierre", "batiment",
      [("craft", "stonemason")],
      [("Taille et restauration", "Encadrements, appuis, murs et éléments en pierre."),
       ("Pierre sur mesure", "Pièces neuves, gravure, aménagements.")],
      "HomeAndConstructionBusiness"),
    M("nettoyage", "Entreprise de nettoyage", "une entreprise de nettoyage", "entreprises de nettoyage", "services",
      [("craft", "cleaning"), ("office", "cleaning")],
      [("Entretien régulier", "Bureaux, commerces, parties communes."),
       ("Remise en état", "Fin de chantier, vitres, nettoyages ponctuels.")],
      "HomeAndConstructionBusiness", ["o2", "shiva", "onet", "elior", "atalian",
                                      "samsic", "derichebourg", "anett", "anett hygiene"]),
    M("demenageur", "Déménageur", "un déménageur", "déménageurs", "services",
      [("office", "moving_company"), ("shop", "moving")],
      [("Déménagement", "Particuliers et professionnels, avec ou sans emballage."),
       ("Garde-meubles et manutention", "Stockage, monte-meubles, transports ponctuels.")],
      "MovingCompany", _DEMENAGEMENT),

    # ---------------------------------------------------------- auto, deux-roues
    M("moto", "Atelier moto", "un atelier moto", "ateliers moto", "auto",
      [("shop", "motorcycle_repair"), ("shop", "motorcycle")],
      [("Entretien et réparation", "Révisions, freins, pneus, transmission."),
       ("Équipement et accessoires", "Préparation pour la saison, accessoires, conseils.")],
      "MotorcycleRepair", ["dafy", "dafy moto", "moto axxe", "speedway", "cardy",
                           "harley davidson", "yamaha", "honda", "kawasaki",
                           "suzuki", "ktm", "triumph", "ducati", "bmw motorrad",
                           "piaggio", "vespa", "peugeot motocycles", "motoblouz"]),
    M("velo", "Magasin de vélos", "un magasin de vélos", "magasins de vélos", "auto",
      [("shop", "bicycle")],
      [("Réparation", "Crevaison, freins, dérailleur, révision complète."),
       ("Vente et conseil", "Vélos, électriques compris, et l'équipement qui va avec.")],
      "BikeStore", ["culture velo", "velo oxygen", "velo & oxygen", "cyclable",
                    "veloland", "giant", "trek", "mondovelo", "specialized",
                    "alltricks", "probikeshop", "cycles lapierre", "velo station"]),
    M("auto-ecole", "Auto-école", "une auto-école", "auto-écoles", "auto",
      [("amenity", "driving_school")],
      [("Permis B", "Code, leçons de conduite, accompagnement jusqu'à l'examen."),
       ("Autres formations", "Conduite accompagnée, perfectionnement, selon l'école.")],
      "LocalBusiness", ["ecf", "cer", "auto ecole cer", "stych", "ornikar",
                        "en voiture simone", "le permis libre", "lepermislibre",
                        "fun permis", "planete permis"]),

    # ---------------------------------------------------------- beaute
    M("barbier", "Barbier", "un barbier", "barbiers", "beaute",
      [("shop", "hairdresser", {"hairdresser": "barber"}),
       ("shop", "hairdresser", {"male": "yes", "female": "no"})],
      [("Coupe homme", "Coupe aux ciseaux ou à la tondeuse, dégradés, entretien."),
       ("Barbe", "Taille, contours, rasage.")],
      "HairSalon", _COIFFURE + ["barber shop", "the barber company", "barbershop", "les barbiers"]),
    M("coiffeur", "Coiffeur", "un coiffeur", "coiffeurs", "beaute",
      [("shop", "hairdresser")],
      [("Coupe et coiffage", "Coupe, brushing, coiffage, pour femmes, hommes ou enfants selon le salon."),
       ("Couleur et soins", "Coloration, mèches, balayage et soins du cheveu.")],
      "HairSalon", _COIFFURE),
    M("ongles", "Prothésiste ongulaire", "un salon d'ongles", "salons d'ongles", "beaute",
      [("shop", "beauty", {"beauty": "nails"}), ("shop", "nails")],
      [("Pose et entretien", "Gel, résine ou vernis semi-permanent."),
       ("Mains et pieds", "Manucure, beauté des pieds, décors.")],
      "NailSalon", _BEAUTE),
    M("estheticienne", "Institut de beauté", "un institut de beauté", "instituts de beauté", "beaute",
      [("shop", "beauty")],
      [("Soins du visage", "Nettoyage, soins adaptés au type de peau."),
       ("Épilation et soins du corps", "Épilations, gommages, modelages de bien-être.")],
      "BeautySalon", _BEAUTE),
    M("tatoueur", "Tatoueur", "un tatoueur", "tatoueurs", "beaute",
      [("shop", "tattoo")],
      [("Tatouage", "Projets sur mesure, du dessin à la séance."),
       ("Reprises et conseils", "Retouche d'un tatouage existant, conseils de cicatrisation.")],
      "TattooParlor"),
    M("massage", "Masseur bien-être", "un masseur bien-être", "praticiens de massage", "beaute",
      [("shop", "massage")],
      [("Massages bien-être", "Des séances de détente, sans visée médicale."),
       ("Séances et formules", "Durées et formules à voir directement avec le praticien.")],
      "HealthAndBeautyBusiness", ["l instant thai", "thai spa"]),

    # ---------------------------------------------------------- metiers de bouche
    M("boulangerie", "Boulangerie", "une boulangerie", "boulangeries", "bouche",
      [("shop", "bakery")],
      [("Pains", "Les pains du quotidien et les pains spéciaux."),
       ("Viennoiseries et pâtisseries", "Croissants, tartes, entremets, selon la saison.")],
      "Bakery", ["maison kayser", "eric kayser", "boulangerie louise", "louise",
                 "le fournil de pierre", "les delices du fournil", "boul pat",
                 "secrets de pains", "la panetiere", "boulangerie ange"]),
    M("patisserie", "Pâtisserie", "une pâtisserie", "pâtisseries", "bouche",
      [("shop", "pastry")],
      [("Pâtisseries", "Gâteaux individuels, entremets, tartes de saison."),
       ("Commandes", "Pièces pour un anniversaire ou un repas de fête.")],
      "Bakery", ["laduree", "pierre herme", "lenotre", "dalloyau"]),
    M("chocolatier", "Chocolatier", "un chocolatier", "chocolatiers", "bouche",
      [("shop", "chocolate")],
      [("Chocolats", "Bonbons, tablettes, créations de saison."),
       ("Coffrets", "Pour offrir, à composer ou déjà prêts.")],
      "Store", ["jeff de bruges", "leonidas", "de neuville", "monbana", "lindt",
                "la maison du chocolat", "pierre marcolini", "cacao et chocolat",
                "maxim s", "neuhaus", "chocolat de neuville", "puyricard",
                "réauté", "reaute chocolat", "chocolaterie de beussent"]),
    M("confiserie", "Confiserie", "une confiserie", "confiseries", "bouche",
      [("shop", "confectionery")],
      [("Confiseries", "Bonbons, nougats, caramels, spécialités."),
       ("Pour offrir", "Assortiments et coffrets.")],
      "Store", ["la cure gourmande", "cure gourmande", "le comptoir de mathilde",
                "comptoir de mathilde", "la maison du bonbon"]),
    M("boucherie", "Boucherie", "une boucherie", "boucheries", "bouche",
      [("shop", "butcher")],
      [("Viandes", "Bœuf, veau, agneau, porc et volailles, découpés à la demande."),
       ("Charcuterie et préparations", "Charcuterie, plats préparés, selon la maison.")],
      "Store", ["boucherie bernard", "boucherie nivernaise"]),
    M("fromagerie", "Fromagerie", "une fromagerie", "fromageries", "bouche",
      [("shop", "cheese")],
      [("Fromages", "Une sélection affinée, à goûter et à conseiller."),
       ("Crèmerie et plateaux", "Beurre, crème, et plateaux pour recevoir.")],
      "Store", ["androuet", "fromagerie androuet"]),
    M("caviste", "Caviste", "un caviste", "cavistes", "bouche",
      [("shop", "wine"), ("shop", "alcohol")],
      [("Vins", "Une sélection à goûter et à conseiller."),
       ("Spiritueux et bières", "Whiskies, rhums, bières artisanales, selon la cave.")],
      "LiquorStore", ["nicolas", "v and b", "v&b", "v b", "cavavin",
                      "le repaire de bacchus", "repaire de bacchus", "intercaves",
                      "lavinia", "la grande epicerie", "cellier", "cave de l hyper",
                      "les domaines qui montent", "la vignery"]),
    M("poissonnerie", "Poissonnerie", "une poissonnerie", "poissonneries", "bouche",
      [("shop", "seafood")],
      [("Poissons", "La pêche du jour, préparée à la demande."),
       ("Coquillages et crustacés", "Huîtres, moules, plateaux, selon les arrivages.")],
      "Store", ["la criee"]),
    M("primeur", "Primeur", "un primeur", "primeurs", "bouche",
      [("shop", "greengrocer")],
      [("Fruits et légumes", "De saison, choisis et conseillés."),
       ("Épicerie", "Ce qui accompagne, selon la boutique.")],
      "Store", ["o tera", "fresh", "au bon marche"]),
    M("traiteur", "Traiteur", "un traiteur", "traiteurs", "bouche",
      [("craft", "caterer"), ("shop", "caterer")],
      [("Plats et buffets", "Pour un repas de famille ou un événement."),
       ("Sur commande", "Menus à composer selon le nombre de convives.")],
      "FoodEstablishment"),
    M("epicerie-fine", "Épicerie fine", "une épicerie fine", "épiceries fines", "bouche",
      [("shop", "deli")],
      [("Épicerie fine", "Produits choisis, conserves, condiments, spécialités."),
       ("Pour offrir", "Paniers et coffrets gourmands.")],
      "Store", ["comptoir irlandais", "la grande epicerie", "fauchon", "hediard",
                "maison de la truffe", "ducs de gascogne", "kusmi tea",
                "mariage freres", "le palais des thes", "nysa"]),
    M("torrefacteur", "Torréfacteur", "un torréfacteur", "torréfacteurs", "bouche",
      [("shop", "coffee"), ("shop", "tea")],
      [("Cafés", "Torréfiés, moulus à la demande."),
       ("Thés et accessoires", "Thés, infusions, matériel.")],
      "Store", ["nespresso", "kusmi tea", "mariage freres", "le palais des thes",
                "comptoirs richard", "cafe coton", "dammann", "cafes richard"]),
    M("glacier", "Glacier", "un glacier", "glaciers", "bouche",
      [("shop", "ice_cream"), ("amenity", "ice_cream")],
      [("Glaces et sorbets", "Parfums de la maison, selon la saison."),
       ("À emporter", "Bacs, bûches et desserts glacés, selon le glacier.")],
      "IceCreamShop", ["amorino", "ben jerry s", "haagen dazs", "berthillon",
                       "la glace de pierre", "mövenpick", "movenpick"]),
    M("ferme", "Producteur en vente directe", "un producteur en vente directe",
      "producteurs", "bouche",
      [("shop", "farm")],
      [("Produits de la ferme", "Ce que l'exploitation produit, vendu sur place."),
       ("Vente directe", "Jours de vente, marchés, commandes : à voir avec le producteur.")],
      "Store", ["la ruche qui dit oui", "bienvenue a la ferme", "drive fermier"]),
    M("brasserie", "Brasserie artisanale", "une brasserie artisanale",
      "brasseries artisanales", "bouche",
      [("craft", "brewery")],
      [("Bières de la maison", "Les bières brassées sur place, selon les cuvées."),
       ("Vente et visites", "Boutique, dégustations : à voir avec la brasserie.")],
      "Brewery", ["heineken", "kronenbourg", "brasserie licorne"]),
    M("vigneron", "Domaine viticole", "un domaine viticole", "domaines", "bouche",
      [("craft", "winery"), ("shop", "winery")],
      [("Les vins du domaine", "Les cuvées produites sur l'exploitation."),
       ("Caveau", "Vente et dégustation, selon les horaires du domaine.")],
      "Winery", ["nicolas", "cellier des dauphins", "castel"]),

    # ---------------------------------------------------------- restauration
    M("creperie", "Crêperie", "une crêperie", "crêperies", "restauration",
      [("amenity", "restaurant", {"cuisine": "crepe"}),
       ("amenity", "restaurant", {"cuisine": "crepe;galette"}),
       ("amenity", "restaurant", {"cuisine": "galette"})],
      [("Galettes et crêpes", "Salées, sucrées, selon la carte de la maison."),
       ("Sur place ou à emporter", "Selon l'établissement.")],
      "Restaurant", ["creperie des arts", "la crepe a l emporte piece"]),
    M("pizzeria", "Pizzeria", "une pizzeria", "pizzerias", "restauration",
      [("amenity", "restaurant", {"cuisine": "pizza"}),
       ("amenity", "fast_food", {"cuisine": "pizza"})],
      [("Pizzas", "La carte de la maison, au four."),
       ("Sur place ou à emporter", "Selon l'établissement.")],
      "Restaurant", ["dominos", "pizza hut", "la boite a pizza",
                     "le kiosque a pizzas", "speed rabbit", "del arte",
                     "pizza cosy", "tablapizza", "pizza sprint", "papa john s",
                     "o pizz", "five pizza", "basilic co", "basilic & co",
                     "planet pizza", "la pizza de nico", "pizza time", "allo pizza",
                     "pizza paï", "pizza pai", "mamma mia"]),
    M("restaurant", "Restaurant", "un restaurant", "restaurants", "restauration",
      [("amenity", "restaurant")],
      [("La carte", "Les plats du moment, à découvrir sur place."),
       ("Groupes et événements", "Repas de famille, groupes, privatisation : selon la maison.")],
      "Restaurant"),
    M("cafe", "Café, bar", "un café", "cafés", "restauration",
      [("amenity", "cafe"), ("amenity", "bar"), ("amenity", "pub")],
      [("Au comptoir", "Cafés, boissons, et ce que la maison propose à grignoter."),
       ("Les rendez-vous", "Matchs, soirées, animations : selon l'établissement.")],
      "BarOrPub", ["starbucks", "columbus cafe", "costa coffee", "o sullivans",
                   "au bureau", "les 3 brasseurs", "3 brasseurs", "le brewberry",
                   "cafe marlette", "coffee shop company", "dunkin", "jour de fete"]),

    # ---------------------------------------------------------- hebergement
    M("chambres-hotes", "Chambres d'hôtes", "des chambres d'hôtes",
      "chambres d'hôtes", "hebergement",
      [("tourism", "guest_house")],
      [("Les chambres", "Des chambres chez l'habitant, petit-déjeuner selon la maison."),
       ("Réserver", "Disponibilités et tarifs donnés directement par vos hôtes.")],
      "BedAndBreakfast", ["airbnb", "abritel", "gites de france", "clevacances"]),
    M("gite", "Gîte, location de vacances", "un gîte", "gîtes", "hebergement",
      [("tourism", "chalet"), ("tourism", "apartment")],
      [("Le logement", "Un hébergement indépendant, équipé pour un séjour."),
       ("Réserver", "Disponibilités et conditions données directement par le propriétaire.")],
      "LodgingBusiness", ["airbnb", "abritel", "pierre vacances", "odalys",
                          "lagrange", "madame vacances", "belambra", "vvf",
                          "azureva", "nemea", "goelia", "appart city", "citadines",
                          "adagio", "residhome", "zenitude", "sejours affaires"]),
    M("hotel", "Hôtel indépendant", "un hôtel", "hôtels", "hebergement",
      [("tourism", "hotel")],
      [("Les chambres", "Chambres et équipements, selon l'établissement."),
       ("Réserver en direct", "Disponibilités et tarifs donnés directement par l'hôtel.")],
      "Hotel", _HOTELS),
    M("camping", "Camping", "un camping", "campings", "hebergement",
      [("tourism", "camp_site")],
      [("Emplacements et locations", "Tentes, camping-cars, hébergements, selon le terrain."),
       ("Sur place", "Services et équipements à voir directement avec le camping.")],
      "Campground", _CAMPINGS),

    # ---------------------------------------------------------- loisirs, sport, cours
    M("equitation", "Centre équestre", "un centre équestre", "centres équestres", "loisirs",
      [("leisure", "horse_riding"), ("sport", "equestrian")],
      [("Cours et balades", "Leçons, stages et balades, selon le niveau."),
       ("Pension et installations", "À voir directement avec le centre.")],
      "SportsActivityLocation"),
    M("danse", "École de danse", "une école de danse", "écoles de danse", "loisirs",
      [("amenity", "dancing_school"), ("leisure", "dance")],
      [("Cours", "Disciplines et niveaux, enfants et adultes, selon l'école."),
       ("Stages et spectacles", "Selon la saison.")],
      "LocalBusiness"),
    M("musique", "École de musique", "une école de musique", "écoles de musique", "loisirs",
      [("amenity", "music_school")],
      [("Cours d'instrument", "Instruments et niveaux, selon l'école."),
       ("Pratique collective", "Ateliers, groupes, auditions.")],
      "LocalBusiness"),
    M("yoga", "Studio de yoga", "un studio de yoga", "studios de yoga", "loisirs",
      [("leisure", "sports_centre", {"sport": "yoga"}),
       ("leisure", "fitness_centre", {"sport": "yoga"}), ("sport", "yoga")],
      [("Cours", "Styles et niveaux, selon le studio."),
       ("Ateliers", "Stages et séances particulières, selon le planning.")],
      "SportsActivityLocation"),
    M("salle-sport", "Salle de sport", "une salle de sport", "salles de sport", "loisirs",
      [("leisure", "fitness_centre")],
      [("Entraînement", "Plateau, cours collectifs, selon la salle."),
       ("Accompagnement", "Coaching et suivi, à voir directement avec l'équipe.")],
      "ExerciseGym", _SPORT),
    M("escape-game", "Escape game", "un escape game", "escape games", "loisirs",
      [("leisure", "escape_game")],
      [("Les salles", "Des scénarios à vivre en équipe."),
       ("Groupes", "Anniversaires, sorties d'équipe, selon l'établissement.")],
      "EntertainmentBusiness", ["lock academy", "the game", "escape hunt",
                                "team break", "get out", "game over"]),
    M("photographe", "Photographe", "un photographe", "photographes", "artisanat",
      [("craft", "photographer"), ("shop", "photo"), ("craft", "photographic_laboratory")],
      [("Séances photo", "Portraits, familles, événements, selon le photographe."),
       ("Tirages et identité", "Tirages, photos d'identité, selon le studio.")],
      "ProfessionalService", ["photomaton", "fujifilm", "photo service",
                              "photostation", "fnac", "kodak express", "cewe"]),

    # ---------------------------------------------------------- commerces
    M("fleuriste", "Fleuriste", "un fleuriste", "fleuristes", "commerce",
      [("shop", "florist")],
      [("Bouquets", "Composés à la demande, selon la saison."),
       ("Événements", "Mariages, deuils, décorations : sur commande.")],
      "Florist", _FLEURS),
    M("bijouterie", "Bijouterie", "une bijouterie", "bijouteries", "commerce",
      [("shop", "jewelry"), ("craft", "jeweller")],
      [("Bijoux", "Une sélection à voir en boutique."),
       ("Atelier", "Mise à taille, réparations, gravure, selon la bijouterie.")],
      "JewelryStore", _BIJOUX),
    M("horloger", "Horloger", "un horloger", "horlogers", "commerce",
      [("shop", "watches"), ("craft", "watchmaker"), ("craft", "clockmaker")],
      [("Réparation", "Piles, bracelets, révisions, restauration."),
       ("Montres", "Une sélection à voir en boutique.")],
      "Store", _BIJOUX),
    M("cordonnier", "Cordonnier", "un cordonnier", "cordonniers", "commerce",
      [("shop", "shoe_repair"), ("craft", "shoemaker")],
      [("Réparation de chaussures", "Talons, semelles, coutures, teintures."),
       ("Petits services", "Clés, maroquinerie, selon la boutique.")],
      "Store", ["mister minit", "minit", "cordonnerie minute", "talon minute",
                "cordo service"]),
    M("couture", "Couturière, retoucheur", "une couturière", "couturiers", "artisanat",
      [("craft", "tailor"), ("craft", "dressmaker"), ("shop", "tailor"),
       ("craft", "sewing")],
      [("Retouches", "Ourlets, ajustements, fermetures, réparations."),
       ("Sur mesure", "Création ou transformation, selon l'atelier.")],
      "Store", ["5 a sec", "cinq a sec"]),
    M("pressing", "Pressing", "un pressing", "pressings", "services",
      [("shop", "dry_cleaning"), ("shop", "laundry")],
      [("Nettoyage", "Vêtements, linge de maison, pièces délicates."),
       ("Repassage et retouches", "Selon le pressing.")],
      "DryCleaningOrLaundry", ["5 a sec", "cinq a sec", "pressing de france",
                               "speed queen", "lavomatic", "laverie libre service",
                               "self laverie", "wash n dry", "la laverie"]),
    M("librairie", "Librairie", "une librairie", "librairies", "commerce",
      [("shop", "books")],
      [("Livres", "Une sélection, et des conseils."),
       ("Commandes", "Un titre à commander, retiré en boutique.")],
      "BookStore", ["furet du nord", "decitre", "gibert", "gibert joseph",
                    "maison de la presse", "mag presse", "espace culturel",
                    "librairie gallimard", "france loisirs", "cultura", "fnac",
                    "boulinier", "momie", "le bon coin"]),
    M("antiquaire", "Antiquaire, brocante", "un antiquaire", "antiquaires", "commerce",
      [("shop", "antiques")],
      [("Objets et mobilier", "Ce qui est en boutique change souvent : venez voir."),
       ("Achat et estimation", "Selon l'antiquaire.")],
      "Store"),
    M("depot-vente", "Dépôt-vente", "un dépôt-vente", "dépôts-ventes", "commerce",
      [("shop", "second_hand"), ("shop", "charity")],
      [("En boutique", "Objets, mobilier, vêtements : un stock qui change souvent."),
       ("Dépôt", "Conditions de dépôt à voir avec la boutique.")],
      "Store", ["emmaus", "croix rouge", "cash express", "cash converters",
                "easy cash", "troc com", "troc", "le relais", "ding fring",
                "ressourcerie", "la recyclerie", "secours populaire",
                "secours catholique", "vinted", "abbe pierre", "envie",
                "label emmaus", "happy cash", "cash&co"]),
    M("encadreur", "Encadreur, galerie", "un encadreur", "encadreurs", "artisanat",
      [("shop", "frame"), ("shop", "art"), ("craft", "framing")],
      [("Encadrement sur mesure", "Baguettes, passe-partout, verres."),
       ("Œuvres", "Exposition et vente, selon la galerie.")],
      "Store", ["lezard creatif", "cultura", "le geant des beaux arts"]),
    M("tapissier", "Tapissier", "un tapissier", "tapissiers", "artisanat",
      [("craft", "upholsterer")],
      [("Réfection de sièges", "Garnissage, sanglage, recouverture."),
       ("Tissus et décoration", "Rideaux, coussins, tentures, selon l'atelier.")],
      "Store"),
    M("ceramiste", "Céramiste, potier", "un céramiste", "céramistes", "artisanat",
      [("craft", "pottery"), ("shop", "pottery")],
      [("Pièces de l'atelier", "Vaisselle, objets, pièces uniques."),
       ("Cours et commandes", "Selon l'atelier.")],
      "Store"),
    M("ebeniste-meuble", "Restaurateur de meubles", "un restaurateur de meubles",
      "restaurateurs de meubles", "artisanat",
      [("craft", "restoration"), ("shop", "furniture", {"second_hand": "only"})],
      [("Restauration", "Meubles anciens remis en état, dans le respect de la pièce."),
       ("Finitions", "Vernis, cire, teinte, selon l'atelier.")],
      "Store"),
    M("imprimerie", "Imprimerie", "une imprimerie", "imprimeries", "services",
      [("craft", "printer"), ("shop", "copyshop"), ("craft", "signmaker")],
      [("Impression", "Cartes, flyers, affiches, documents."),
       ("Signalétique", "Enseignes, adhésifs, marquage, selon l'imprimeur.")],
      "ProfessionalService", ["copytop", "bureau vallee", "top office",
                              "pixartprinting", "vistaprint", "exaprint",
                              "helloprint", "imprimerie nationale", "france enseigne",
                              "signarama", "repro", "copy service"]),
    M("informatique", "Dépannage informatique", "un dépanneur informatique",
      "dépanneurs informatiques", "services",
      [("shop", "computer"), ("craft", "computer"), ("shop", "electronics_repair"),
       ("craft", "electronics_repair")],
      [("Dépannage", "Ordinateur lent, panne, virus, récupération de données."),
       ("Installation et conseil", "Matériel, réseau, logiciels, selon le besoin.")],
      "ComputerStore", ["ldlc", "materiel net", "boulanger", "darty", "fnac",
                        "cash express", "easy cash", "micromania", "apple",
                        "rueducommerce", "top achat", "grosbill"]),
    M("telephone", "Réparation de téléphones", "un réparateur de téléphones",
      "réparateurs de téléphones", "services",
      [("shop", "mobile_phone")],
      [("Réparation", "Écran, batterie, connecteur, selon le modèle."),
       ("Accessoires", "Coques, protections, câbles.")],
      "MobilePhoneStore", ["orange", "sfr", "bouygues", "free", "phone house",
                           "the phone house", "point service mobiles", "save",
                           "wefix", "we fix", "cash express", "easy cash",
                           "samsung", "apple", "xiaomi", "huawei", "coriolis",
                           "nrj mobile", "la poste mobile", "sosh", "red by sfr"]),
    M("opticien", "Opticien indépendant", "un opticien", "opticiens", "commerce",
      [("shop", "optician")],
      [("Lunettes", "Montures et verres, conseil et ajustage."),
       ("Lentilles et entretien", "Selon l'opticien.")],
      "Optician", _OPTIQUE),
    M("vetements", "Boutique de vêtements", "une boutique de vêtements",
      "boutiques de vêtements", "commerce",
      [("shop", "clothes"), ("shop", "boutique"), ("shop", "fashion")],
      [("La collection", "Les pièces de la saison, à voir en boutique."),
       ("Conseil", "Tailles, retouches, mises de côté : selon la boutique.")],
      "ClothingStore", _VETEMENTS),
    M("chaussures", "Magasin de chaussures", "un magasin de chaussures",
      "magasins de chaussures", "commerce",
      [("shop", "shoes")],
      [("La collection", "Les modèles de la saison, à essayer en boutique."),
       ("Conseil", "Pointures, entretien, selon le magasin.")],
      "ShoeStore", _VETEMENTS),
    M("jouets", "Magasin de jouets", "un magasin de jouets", "magasins de jouets", "commerce",
      [("shop", "toys"), ("shop", "games")],
      [("Jouets et jeux", "Une sélection par âge, et des conseils."),
       ("Pour offrir", "Idées cadeaux et emballage, selon la boutique.")],
      "ToyStore", ["king jouet", "la grande recre", "joueclub", "toys r us",
                   "maxi toys", "oxybul", "picwic", "cultura", "fnac",
                   "micromania", "nature decouvertes", "nature & decouvertes",
                   "smyths", "lego"]),
    M("cadeaux", "Boutique déco et cadeaux", "une boutique de décoration",
      "boutiques de décoration", "commerce",
      [("shop", "gift"), ("shop", "interior_decoration")],
      [("Objets et décoration", "Une sélection qui change avec les saisons."),
       ("Pour offrir", "Idées et emballages cadeaux.")],
      "Store", ["nature decouvertes", "nature & decouvertes", "maisons du monde",
                "hema", "la chaise longue", "sostrene grene", "flying tiger",
                "casa", "zodio", "alinea", "action", "gifi", "la foir fouille",
                "stokomani", "centrakor", "b m", "b&m", "pylones", "gifi",
                "la boutique du cadeau", "bleu libellule", "comptoir de famille"]),
    M("musique-shop", "Magasin de musique", "un magasin de musique",
      "magasins de musique", "commerce",
      [("shop", "musical_instrument"), ("craft", "luthier")],
      [("Instruments", "Vente, conseil, essais en boutique."),
       ("Atelier", "Réglages et réparations, selon le magasin.")],
      "MusicStore", ["woodbrass", "thomann", "michenaud", "star s music",
                     "stars music", "music store"]),
    M("quincaillerie", "Quincaillerie", "une quincaillerie", "quincailleries", "commerce",
      [("shop", "hardware"), ("shop", "doityourself")],
      [("Quincaillerie", "Visserie, outillage, droguerie, au détail."),
       ("Services", "Clés, découpe, conseils, selon le magasin.")],
      "HardwareStore", ["brico pro", "tout faire", "bricorama", "brico leclerc",
                        "brico cash", "bricoman", "entrepot du bricolage",
                        "l entrepot du bricolage", "la plateforme du batiment",
                        "point p", "gedimat", "bigmat", "big mat", "samse",
                        "dispano", "chausson", "quincaillerie angles"]),
    M("pompes-funebres", "Pompes funèbres", "des pompes funèbres",
      "pompes funèbres", "services",
      [("shop", "funeral_directors"), ("amenity", "funeral_hall")],
      [("Organisation des obsèques", "Démarches, cérémonie, accompagnement des familles."),
       ("Prévoyance et marbrerie", "Selon l'entreprise.")],
      "LocalBusiness", _FUNERAIRE),
    M("immobilier", "Agence immobilière indépendante", "une agence immobilière",
      "agences immobilières", "services",
      [("office", "estate_agent"), ("shop", "estate_agent")],
      [("Vente et achat", "Estimation, mise en vente, accompagnement jusqu'à la signature."),
       ("Location et gestion", "Selon l'agence.")],
      "RealEstateAgent", _IMMO),
    M("architecte", "Architecte", "un architecte", "architectes", "services",
      [("office", "architect")],
      [("Conception", "Esquisse, plans, dossier de permis de construire."),
       ("Suivi", "Consultation des entreprises et suivi du chantier, selon la mission.")],
      "ProfessionalService"),
    M("geometre", "Géomètre-expert", "un géomètre", "géomètres", "services",
      [("office", "surveyor")],
      [("Bornage et division", "Limites de propriété, divisions, plans."),
       ("Topographie", "Relevés et plans, selon le cabinet.")],
      "ProfessionalService"),

    # ---------------------------------------------------------- animaux
    M("toiletteur", "Toiletteur", "un toiletteur", "toiletteurs", "animaux",
      [("shop", "pet_grooming"), ("craft", "pet_grooming")],
      [("Toilettage", "Bain, coupe, démêlage, adaptés à chaque pelage."),
       ("Soins", "Griffes, oreilles, et conseils d'entretien.")],
      "LocalBusiness", ["medor et compagnie", "médor et compagnie", "dog s & cat s",
                        "maxi zoo", "animalis", "tom co", "truffaut", "jardiland"]),
    M("pension-animaux", "Pension pour animaux", "une pension pour animaux",
      "pensions", "animaux",
      [("amenity", "animal_boarding")],
      [("Pension", "Garde pendant vos absences, selon les espèces accueillies."),
       ("Avant le séjour", "Visite, conditions d'accueil, à voir avec la pension.")],
      "LocalBusiness"),
    M("educateur-canin", "Éducateur canin", "un éducateur canin",
      "éducateurs canins", "animaux",
      [("amenity", "animal_training")],
      [("Éducation", "Séances pour le chiot comme pour l'adulte."),
       ("Comportement", "Conseils et accompagnement, selon l'éducateur.")],
      "LocalBusiness"),
    M("animalerie", "Animalerie", "une animalerie", "animaleries", "animaux",
      [("shop", "pet")],
      [("Alimentation et accessoires", "Pour chiens, chats, rongeurs, oiseaux, poissons."),
       ("Conseil", "Selon la boutique.")],
      "PetStore", ["maxi zoo", "animalis", "tom co", "tom&co", "truffaut",
                   "jardiland", "botanic", "gamm vert", "zoomalia", "medor et compagnie",
                   "point vert", "magasin vert", "terre de chiens", "inzoo"]),
    M("jardinerie", "Jardinerie, pépinière", "une pépinière", "pépinières", "commerce",
      [("shop", "garden_centre"), ("landuse", "plant_nursery")],
      [("Végétaux", "Plantes, arbustes, arbres, selon la saison."),
       ("Conseil", "Plantation, entretien, selon la pépinière.")],
      "GardenStore", ["jardiland", "truffaut", "botanic", "gamm vert", "point vert",
                      "villaverde", "delbard", "magasin vert", "baobab", "jardinerie de",
                      "leroy merlin", "castorama", "kiriel"]),
]

PAR_CLE: dict[str, Metier] = {m.cle: m for m in CATALOGUE}
assert len(PAR_CLE) == len(CATALOGUE), "cle de metier en double"


def classer(tags: dict) -> Metier | None:
    """Le premier metier du catalogue dont une etiquette correspond."""
    for m in CATALOGUE:
        for t in m.tags:
            k, v = t[0], t[1]
            cond = t[2] if len(t) > 2 else {}
            if tags.get(k) == v and all(tags.get(ck) == cv for ck, cv in cond.items()):
                return m
    return None


def cles_osm() -> dict[str, set[str]]:
    """{cle OSM: {valeurs}} pour construire la requete Overpass."""
    out: dict[str, set[str]] = {}
    for m in CATALOGUE:
        for t in m.tags:
            out.setdefault(t[0], set()).add(t[1])
    return out


def pour_pipeline() -> dict[str, dict]:
    """Les entrees au format de pipeline_pro.METIERS."""
    out = {}
    for m in CATALOGUE:
        out[m.cle] = {
            "metier": m.nom.lower(),
            "gabarit": None,              # gabarit generique
            "generique": True,
            "cherche": m.cherche,
            "pluriel": m.pluriel,
            "famille": m.famille,
            "animaux": bool(m.fam.get("animaux")),
            "devis": "Un formulaire de demande qui arrive directement chez vous, "
                     "même quand vous êtes occupé",
            "sections": ["Ouverture", "Bandeau de faits", "Prestations",
                         m.fam["prep_titre"], "Horaires et accès", "Contact"],
            "emoji": "✉️",
        }
    return out


if __name__ == "__main__":
    par_fam: dict[str, list[str]] = {}
    for m in CATALOGUE:
        par_fam.setdefault(m.famille, []).append(m.cle)
    for f, l in par_fam.items():
        print(f"{f:13} {len(l):>2}  {', '.join(l)}")
    print(f"\n{len(CATALOGUE)} metiers, {sum(len(v) for v in cles_osm().values())} "
          f"etiquettes OSM")
