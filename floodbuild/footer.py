"""The common footer of the Terra Aperta projects: back to the hub, then the twelve siblings."""
from __future__ import annotations

SITE = "https://asensio94.github.io/"
CURRENT = "zona-inundable"

# Same order as the Terra Aperta menu. French pages link each sibling's French page when it has one.
PROJECTS = [
    ("sub-nocte", "Sub Nocte", "Sub Nocte", "sub-nocte/"),
    ("vigia-incendios", "Vigía de incendios", "Vigie des incendies", "vigia-incendios/fr/"),
    ("centinela-natura", "Centinela Natura", "Centinela Natura", "centinela-natura/fr/"),
    ("estado-iba", "Estado de las IBA", "État des IBA", "estado-iba/fr/"),
    ("riesgo-tendidos-aves", "Riesgo de tendidos para aves", "Risque des lignes pour les oiseaux",
     "riesgo-tendidos-aves/regions.fr.html"),
    ("observatorio-alegaciones", "Observatorio de alegaciones", "Observatoire des consultations",
     "observatorio-alegaciones/"),
    ("grafo-promotores", "Grafo de promotores", "Graphe des porteurs de projet", "grafo-promotores/"),
    ("vigilancia-humedales", "Vigilancia de humedales", "Veille des zones humides", "vigilancia-humedales/france.html"),
    ("caudal-ecologico", "Caudal ecológico", "Débit écologique", "caudal-ecologico/"),
    ("acuiferos-francia", "Acuíferos de Francia", "Nappes de France", "acuiferos-francia/"),
    ("depuracion-y-bano", "Depuración y baño", "Épuration et baignade", "depuracion-y-bano/fr/"),
    ("zona-inundable", "Construir en zona inundable", "Construire en zone inondable", "zona-inundable/"),
]

TEXT = {
    "es": ("← Terra Aperta: todos los proyectos", "terra-aperta/", "Proyectos hermanos"),
    "fr": ("← Terra Aperta : tous les projets", "terra-aperta/fr/", "Projets frères"),
}


def footer_nav(lang: str = "es") -> str:
    """The hub link and the sibling list; this project is plain text, marked as the current page."""
    hub, hub_path, label = TEXT[lang]
    colon = " :" if lang == "fr" else ":"  # French puts a no-break space before it
    items = []
    for slug, es, fr, fr_path in PROJECTS:
        name = fr if lang == "fr" else es
        if slug == CURRENT:
            items.append(f'    <li aria-current="page">{name}</li>')
        else:
            href = SITE + (fr_path if lang == "fr" else f"{slug}/")
            items.append(f'    <li><a href="{href}">{name}</a></li>')
    return (f'<p class="hub"><a href="{SITE}{hub_path}">{hub}</a></p>\n'
            f'  <nav aria-label="{label}">{label}{colon}<ul class="siblings">\n' + "\n".join(items) + "\n  </ul></nav>")
