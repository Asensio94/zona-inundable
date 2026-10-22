"""Interface strings and number formats, one dictionary per language.

Each country's page is written in that country's language: the Spanish one in Spanish, the
French one in French. Data files (CSV, summary.json, signals.json) stay in canonical,
language-independent values; only what a reader sees goes through here. Same pattern as
humedales/i18n.py in vigilancia-humedales.
"""
from __future__ import annotations

LANG_BY_COUNTRY = {"ES": "es", "FR": "fr"}

# French typography: a narrow no-break space as thousands separator and before «%», and a
# no-break space before «:», «;», «?» and «!».
_NNBSP = " "
_NBSP = " "


def lang_of(country: str) -> str:
    return LANG_BY_COUNTRY.get(country, "es")


def n(v: float, lang: str) -> str:
    """Integer with the thousands separator of the language: 46.709 / 46 709 (also 1.500 / 1 500)."""
    s = f"{abs(v):,.0f}".replace(",", "." if lang == "es" else _NNBSP)
    return ("−" if v < 0 else "") + s


def d(v: float, lang: str, nd: int = 1) -> str:
    """Decimal with comma and the thousands separator of the language: 1.234,5 / 1 234,5."""
    whole, _, frac = f"{abs(v):,.{nd}f}".partition(".")
    whole = whole.replace(",", "." if lang == "es" else _NNBSP)
    return ("−" if v < 0 else "") + whole + ("," + frac if frac else "")


def p(x: float | None, lang: str, nd: int = 1) -> str:
    """A percentage given in percent (12.5 → «12,5 %»); a dash when unknown."""
    if x is None:
        return "—"
    return f"{d(x, lang, nd)}{' ' if lang == 'es' else _NNBSP}%"


def colon(lang: str) -> str:
    """«:» with the space French puts before it."""
    return f"{_NBSP}:" if lang == "fr" else ":"


UI: dict[str, dict[str, str]] = {
    "es": {
        "lang_name": "Español",
        "other_country": "Francia (Aude)",
        "other_country_link": "Versión francesa: el Aude, con los PPRi",
        "unit_buildings": "edificios",
        "zone_ppr_red": "Zona roja del PPRi",
        "zone_ppr_blue": "Zona azul del PPRi",
        "zone_azi": "Atlas de zonas inundables",
        "zone_azi_exc": "Lecho mayor excepcional",
        "zone_out": "Fuera",
        "provisional": "provisional",
        "communes": "municipios",
    },
    "fr": {
        "lang_name": "Français",
        "other_country": "Espagne (Communauté valencienne)",
        "other_country_link": "Version espagnole : la Communauté valencienne, avec le SNCZI",
        "unit_buildings": "bâtiments",
        "zone_ppr_red": "Zone rouge du PPRi",
        "zone_ppr_blue": "Zone bleue du PPRi",
        "zone_azi": "Atlas des zones inondables",
        "zone_azi_exc": "Lit majeur exceptionnel",
        "zone_out": "Hors zone",
        "provisional": "provisoire",
        "communes": "communes",
    },
}


def t(lang: str, key: str) -> str:
    return UI.get(lang, UI["es"]).get(key) or UI["es"][key]
