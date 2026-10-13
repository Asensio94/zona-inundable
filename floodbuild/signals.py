"""docs/signals.json for estado-iba (CONTRATO.md): one signal per municipality with new buildings in flood zones."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import analysis, config


def _signal(m: dict, date: str, w: dict) -> dict:
    n = int(m["post"])
    return {
        "id": f"FB-{m['ine']}",
        "kind": "flood_building",
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


def build() -> Path:
    s = analysis.summary()
    munis, manifest = s["_munis"], analysis.load()[1]
    # The date of the fact is the Catastro extract the count comes from.
    date = max((v["updated"] for v in manifest.values() if v.get("updated")), default=None) \
        or datetime.now(timezone.utc).date().isoformat()
    # The contract asks for INE codes: municipalities missing from es-atlas get no signal.
    rows = munis[(munis.post > 0) & ~munis.ine.str.startswith("C")].to_dict("records") if len(munis) else []
    out = {
        "source": "zona-inundable",
        "version": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "coverage": {
            "label": " · ".join(config.REGIONS.values()),
            "sites": None,
            "note": "Edificios del Catastro con fecha de construcción posterior a 2016 dentro de las zonas "
                    "inundables del SNCZI (flujo preferente, T100 y T500). El año puede ser de una reforma.",
        },
        "signals": [_signal(m, date, s["windows"]) for m in rows],
    }
    config.DOCS.mkdir(parents=True, exist_ok=True)
    path = config.DOCS / "signals.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
