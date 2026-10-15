"""docs/signals.json for estado-iba (CONTRATO.md): one signal per municipality with new buildings in flood zones.

Every signal carries its country. Spanish municipalities go by their INE code and keep their ids
(FB-46250); French communes go by their INSEE code, and their ids carry the country (FB-FR-11397)
because both codes have five characters and can coincide.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import analysis, config, i18n


def _signal(m: dict, date: str, w: dict) -> dict:
    n = int(m["post"])
    return {
        "id": f"FB-{m['ine']}",
        "kind": "flood_building",
        "country": "ES",
        "date": date,
        "title": f"{m['name']}: {n:,} edificio{'s' if n != 1 else ''} en zona inundable con fecha de "
                 f"{config.RD_YEAR + 1} o posterior".replace(",", "."),
        "url": f"{config.SITE_URL}#m-{m['ine']}",
        "municipalities": [m["ine"]],
        "precision": "municipio",
        "status": "provisional",
        "value": {"amount": n, "unit": "edificios"},
        "details": {
            "zfp": int(m["post_zfp"]), "t100": int(m["post_t100"]), "t500": int(m["post_t500"]),
            "reforma_aparente": int(m["post_mixed"]),
            "en_zona_total": int(m["zoned"]),
            "al_anio_antes": m["pre_per_year"], "al_anio_despues": m["post_per_year"],
            "periodo_antes": list(w["pre"]), "periodo_despues": list(w["post"]),
        },
    }


def _signal_fr(m: dict, date: str, w: dict) -> dict:
    """A French commune: buildings in the red or blue zone of a PPRi dated after the PPRi bound them."""
    n = int(m["after_ppr"])
    when = "appliqué par anticipation" if m["ppr_anticipated"] else "approuvé"
    return {
        "id": f"FB-FR-{m['insee']}",
        "kind": "flood_building",
        "country": "FR",
        "date": date,
        "title": f"{m['name']}{i18n.colon('fr')} {i18n.n(n, 'fr')} bâtiment{'s' if n != 1 else ''} en zone rouge ou "
                 f"bleue du PPRi datés d'après le plan ({when} en {m['ppr_year']})",
        "url": f"{config.FR_SITE_URL}#m-{m['insee']}",
        "municipalities": [m["insee"]],
        "precision": "municipio",
        "status": "provisional",
        "value": {"amount": n, "unit": "edificios"},
        "details": {
            "ppr_rouge": int(m["after_ppr_red"]), "ppr_bleue": int(m["after_ppr_blue"]),
            "reforma_aparente": int(m["after_ppr_mixed"]),
            "anio_ppr": int(m["ppr_year"]), "ppr_anticipado": bool(m["ppr_anticipated"]),
            # Today's red and blue zones dated after the commune's first PPRi, even one since revised.
            "anio_primer_ppr": None if pd.isna(m.get("first_ppr_year")) else int(m["first_ppr_year"]),
            "tras_primer_ppr": int(m.get("after_first_ppr") or 0),
            "en_zona_total": int(m["zoned"]),
            "desde_2017": int(m["post"]),
            "al_anio_antes": m["pre_per_year"], "al_anio_despues": m["post_per_year"],
            "periodo_antes": list(w["pre"]), "periodo_despues": list(w["post"]),
        },
    }


def _french() -> tuple[list[dict], str | None]:
    from .fr import analysis as fra
    s = fra.summary()
    munis = s["_munis"]
    if not len(munis):
        return [], None
    # The date of the fact is the Fichiers fonciers' situation: 1 January of their year.
    date = f"{s['data_year']}-01-01"
    rows = munis[munis.after_ppr > 0].to_dict("records")
    label = " · ".join(f"{d['name']} ({k})" for k, d in s["departments"].items())
    return [_signal_fr(m, date, s["windows"]) for m in rows], label


def build() -> Path:
    s = analysis.summary()
    munis, manifest = s["_munis"], analysis.load()[1]
    # The date of the fact is the Catastro extract the count comes from.
    date = max((v["updated"] for v in manifest.values() if v.get("updated")), default=None) \
        or datetime.now(timezone.utc).date().isoformat()
    # The contract asks for INE codes: municipalities missing from es-atlas get no signal.
    rows = munis[(munis.post > 0) & ~munis.ine.str.startswith("C")].to_dict("records") if len(munis) else []
    fr_signals, fr_label = _french()
    out = {
        "source": "zona-inundable",
        "version": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "coverage": {
            "label": " · ".join([*config.REGIONS.values(), *([fr_label] if fr_label else [])]),
            "sites": None,
            "note": "Edificios del Catastro con fecha de construcción posterior a 2016 dentro de las zonas "
                    "inundables del SNCZI (flujo preferente, T100 y T500). El año puede ser de una reforma."
                    + (" Francia: edificios de la BDNB en zona roja o azul de un PPRi con año posterior al del "
                       "PPRi (aprobación o aplicación anticipada)." if fr_signals else ""),
        },
        "signals": [_signal(m, date, s["windows"]) for m in rows] + fr_signals,
    }
    config.DOCS.mkdir(parents=True, exist_ok=True)
    path = config.DOCS / "signals.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
