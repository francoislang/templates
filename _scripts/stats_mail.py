"""Les 3 chiffres du mail Kerr, choisis selon la famille du metier.

Chaque texte est repris mot a mot de sa source (verification du 07-10/11/2026).
Ne rien ajouter ici sans source primaire ouverte et datee.
"""
from __future__ import annotations

# cle: (titre, texte avec **gras**, source courte)
STATS = {
    "AVIS_ARTISAN": ("Vos avis, bien en vue",
                     "**9 Français sur 10** consultent les avis pour choisir un artisan.",
                     "Ifop, 2021"),
    "GOOGLE": ("Trouvé sur Google",
               "**87 %** des Français utilisent Google pour leurs recherches locales.",
               "Partoo, 2024"),
    "AVIS_CHOIX": ("Vos avis, en vitrine",
                   "**82 %** ont déjà choisi un établissement grâce à de très bons avis.",
                   "Ifop, 2026"),
    "PRIX": ("Vos prix défendus",
             "**54 %** paieraient plus cher un pro bien noté, avec beaucoup d'avis.",
             "Ifop, 2026"),
    "SITE_CONFIANCE": ("Un site qui rassure",
                       "Pour acheter en ligne, **67 %** se fient d'abord au site de l'entreprise.",
                       "Afnic, 2026"),
}

PAR_FAMILLE = {
    "batiment": ("AVIS_ARTISAN", "GOOGLE", "PRIX"),
    "auto": ("AVIS_ARTISAN", "GOOGLE", "PRIX"),
    "artisanat": ("GOOGLE", "PRIX", "SITE_CONFIANCE"),
    "bouche": ("GOOGLE", "AVIS_CHOIX", "SITE_CONFIANCE"),
    "commerce": ("GOOGLE", "AVIS_CHOIX", "SITE_CONFIANCE"),
    "hebergement": ("GOOGLE", "AVIS_CHOIX", "SITE_CONFIANCE"),
    "restauration": ("GOOGLE", "AVIS_CHOIX", "PRIX"),
    "loisirs": ("GOOGLE", "AVIS_CHOIX", "PRIX"),
    "beaute": ("GOOGLE", "AVIS_CHOIX", "PRIX"),
    "services": ("GOOGLE", "AVIS_CHOIX", "PRIX"),
    "animaux": ("GOOGLE", "AVIS_CHOIX", "PRIX"),
}
DEFAUT = ("GOOGLE", "AVIS_CHOIX", "PRIX")

# titres propres a une famille (le reste prend le titre par defaut)
TITRES = {
    ("hebergement", "GOOGLE"): "Trouvé quand on vous cherche",
    ("restauration", "GOOGLE"): "Trouvé quand on vous cherche",
    ("bouche", "GOOGLE"): "Vos horaires, bien en vue",
    ("commerce", "GOOGLE"): "Vos horaires, bien en vue",
    ("beaute", "AVIS_CHOIX"): "Vos avis, votre vitrine",
}


def pour(famille: str) -> list[tuple[str, str, str]]:
    """Les 3 (titre, texte, source) de la famille, dans l'ordre d'affichage."""
    f = (famille or "").lower()
    return [(TITRES.get((f, k), STATS[k][0]), STATS[k][1], STATS[k][2])
            for k in PAR_FAMILLE.get(f, DEFAUT)]
