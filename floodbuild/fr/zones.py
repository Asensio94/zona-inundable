"""French flood zones: the PPR regulatory zoning, the flood atlas (AZI) and the TRI maps.

The Géorisques API has no geometries, so each layer comes from where its owner publishes it: the
DDTM's digital PPR zoning (geo-ide ATOM), the regional AZI (Picto-Occitanie for the former
Languedoc-Roussillon) and the TRI maps of the Floods Directive (files.georisques.fr). GASPAR,
the register of procedures, gives each PPR its approval date and the communes it covers.

Every class is kept as a snczi.ZoneSet: the same spatial index and the same "earliest year of
the polygons that cover a point" as in Spain.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from .. import config
from ..snczi import ZoneSet, _polygonal
from . import download

log = logging.getLogger(__name__)

# --- GASPAR -------------------------------------------------------------------------------------

_GASPAR_COLS = ["CODE MODELE", "CODE PROCEDURE", "CODE INSEE DEPARTEMENT", "CODE INSEE COMMUNE",
                "NOM COMMUNE", "LIBELLE RISQUE 1", "LIBELLE RISQUE 2", "LIBELLE RISQUE 3",
                "APPLIC_ANTIC", "APPROBATION", "LIBELLE ETAT", "LIBELLE SOUS-ETAT"]


@lru_cache(maxsize=1)
def gaspar() -> pd.DataFrame:
    """Flood PPR procedures per commune: procedure, model, department, commune, approval year, state."""
    path = download.fetch(config.GASPAR_URL, "gaspar.zip", max_age_days=6)
    with zipfile.ZipFile(path) as zf:
        name = next(n for n in zf.namelist() if re.search(r"pprn_gaspar[^/]*\.csv$", n))
        g = pd.read_csv(zf.open(name), sep=";", dtype=str, encoding="utf-8", usecols=_GASPAR_COLS)
    return flood_procedures(g)


def flood_procedures(g: pd.DataFrame) -> pd.DataFrame:
    risks = g[["LIBELLE RISQUE 1", "LIBELLE RISQUE 2", "LIBELLE RISQUE 3"]].eq(config.FR_FLOOD_RISK).any(axis=1)
    flood = g["CODE MODELE"].isin(config.FR_FLOOD_MODELS) | ((g["CODE MODELE"] == config.FR_MULTI_MODEL) & risks)
    g = g[flood]
    approval = pd.to_numeric(g["APPROBATION"].str[:4], errors="coerce").fillna(0).astype(int)
    early = pd.to_numeric(g["APPLIC_ANTIC"].str[:4], errors="coerce").fillna(0).astype(int)
    # The year the plan first bound new building: its approval, or its anticipated application
    # (article L562-2 of the Environment Code) when the prefect ordered one before approval.
    binding = approval.where((early == 0) | ((approval > 0) & (approval <= early)), early)
    out = pd.DataFrame({"proc": g["CODE PROCEDURE"], "model": g["CODE MODELE"], "dep": g["CODE INSEE DEPARTEMENT"],
                        "insee": g["CODE INSEE COMMUNE"], "commune": g["NOM COMMUNE"], "approved": binding,
                        "anticipated": (early > 0) & ((approval == 0) | (early < approval)),
                        "state": g["LIBELLE ETAT"], "substate": g["LIBELLE SOUS-ETAT"]})
    # A procedure appears once per commune and risk; the risks are already folded in.
    return out.drop_duplicates(["proc", "insee"]).reset_index(drop=True)


def in_force(g: pd.DataFrame) -> pd.DataFrame:
    """Procedures that bind building today: opposable (not repealed, annulled or replaced), with
    an approval or an anticipated-application date. «approved» holds the first of the two."""
    return g[(g.state == "Opposable") & (g.approved > 0)]


# --- PPR zoning ---------------------------------------------------------------------------------

def ppr_class(typereg: str | None, hazard: str | None) -> str | None:
    """Class of a PPR zone from its COVADIS regulation type and whether it is subject to a hazard."""
    t = (typereg or "").strip().zfill(2) if (typereg or "").strip() else ""
    if t in config.FR_TYPEREG:
        return config.FR_TYPEREG[t]
    if t in config.FR_TYPEREG_HAZARD and (hazard or "").strip().lower() == "oui":
        return config.FR_TYPEREG_HAZARD[t]
    return None


def ppr_zoning(dep: str) -> pd.DataFrame:
    """Every zone of the department's digital PPR zoning: procedure, regulation type, hazard, geometry."""
    path = download.fetch(config.FR_DEPARTMENTS[dep]["ppr_zoning"], f"ppr_{dep}.zip")
    with zipfile.ZipFile(path) as zf:
        shp = next(n for n in zf.namelist() if re.search(r"REGL[^/]*_S_\d{3}\.shp$", n, re.I))
        r = download.shapefile_in_zip(zf, shp)
        names = [f[0] for f in r.fields[1:]]
        rows = []
        for sr in r.iterShapeRecords():
            if sr.shape.shapeType == 0:   # null shape
                continue
            a = dict(zip(names, sr.record))
            rows.append({"proc": (a.get("ID_GASPAR") or "").strip(), "typereg": a.get("TYPEREG"),
                         "hazard": a.get("SOUMISALEA"), "code": a.get("CODEZONE"),
                         "geom": _polygonal(download.polygon(sr.shape))})
    return pd.DataFrame(rows)


# --- AZI and TRI --------------------------------------------------------------------------------

def azi(dep: str) -> pd.DataFrame:
    """Polygons of the flood atlas in the classes counted, with the year each study was produced."""
    path = download.fetch(config.FR_DEPARTMENTS[dep]["azi"], f"azi_{dep}.json", max_age_days=90)
    fc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for f in fc["features"]:
        p, g = f["properties"], f.get("geometry")
        cls = config.FR_AZI_UNITS.get((p.get("t_type_uh") or "").strip().lower())
        if not g or not cls:
            continue
        year = int(p["d_produc"][:4]) if (p.get("d_produc") or "")[:4].isdigit() else 0
        rows.append({"cls": cls, "id": f"{p.get('gid')}", "year": year, "study": p.get("n_etude") or "",
                     "geom": _polygonal(shapely.make_valid(shape(g)))})
    return pd.DataFrame(rows)


TRI_RANK = {"for": 1, "moy": 2, "fai": 3}
TRI_LAYER = re.compile(r"n_tri_(\w+?)_inondable_\d{2}_(\d{2})[a-z]+_s_\d{3}\.shp$", re.I)


def tri(dep: str) -> pd.DataFrame:
    """Flooded area of each TRI scenario: frequent, medium, extreme. River and sea floods together.

    The layers are n_tri_<name>_inondable_<flood type>_<scenario>_s_<dep>.shp (01 river, 03 sea;
    01for, 02moy, 03mcc, 04fai). Not carte_inond: that one holds the extents of the map sheets.
    """
    path = download.fetch(config.TRI_URL.format(dep=dep), f"tri_{dep}.zip", max_age_days=180)
    rows = []
    with zipfile.ZipFile(path) as zf:
        for shp in zf.namelist():
            m = TRI_LAYER.search(shp)
            sc = config.TRI_SCENARIOS.get(m.group(2)) if m else None
            if not sc:
                continue
            r = download.shapefile_in_zip(zf, shp)
            names = [f[0] for f in r.fields[1:]]
            for sr in r.iterShapeRecords():
                if sr.shape.shapeType == 0:
                    continue
                a = dict(zip(names, sr.record))
                rows.append({"scenario": sc, "tri": a.get("id_tri") or m.group(1),
                             "geom": _polygonal(download.polygon(sr.shape))})
    return pd.DataFrame(rows)


# --- Zone sets ----------------------------------------------------------------------------------

def _zoneset(zone: str, ids, years, geoms) -> ZoneSet:
    """A ZoneSet with one entry per polygon part.

    The shells of a PPR zone can overlap one another, and GEOS's prepared point-in-polygon test
    counts ring crossings: a point inside two overlapping parts of one multipolygon reads as
    outside. Repairing the largest zones takes minutes; splitting them into parts, each valid on
    its own, does not, and hits() already looks for a point inside any part.
    """
    geoms = np.array(list(geoms), dtype=object)
    ids, years = np.array(list(ids), dtype=object), np.array(list(years), int)
    if len(geoms):
        parts, idx = shapely.get_parts(geoms, return_index=True)
        keep = shapely.get_type_id(parts) == 3
        geoms, ids, years = parts[keep], ids[idx[keep]], years[idx[keep]]
    shapely.prepare(geoms)
    return ZoneSet(zone, ids, years, geoms, shapely.STRtree(geoms))


@dataclass
class FrZones:
    """Zone classes of one department, the TRI scenarios, and which communes have a digital PPR."""
    sets: dict[str, ZoneSet]
    tri: ZoneSet                       # "years" hold the scenario rank: 1 frequent, 2 medium, 3 extreme
    ppr_communes: frozenset[str]       # communes covered by a digital PPR zoning in force
    communes: dict[str, dict] = field(default_factory=dict)   # every commune with a flood PPR in GASPAR
    report: dict = field(default_factory=dict)


def build(dep: str, g: pd.DataFrame, zoning: pd.DataFrame, atlas: pd.DataFrame, scen: pd.DataFrame) -> FrZones:
    """Zone classes from the raw layers; kept apart from the downloads so the tests can feed it."""
    force = in_force(g)
    approved = force.groupby("proc").approved.min().to_dict()
    zoning = zoning.assign(cls=[ppr_class(t, h) for t, h in zip(zoning.typereg, zoning.hazard)])
    known = zoning.proc.isin(approved)
    report = {
        "ppr_features": int(len(zoning)),
        "ppr_procedures": int(zoning.proc.nunique()),
        "ppr_not_in_force": sorted(set(zoning.proc[~known]) - {""}),
        "ppr_features_not_in_force": int((~known).sum()),
        "ppr_features_unclassified": int((known & zoning.cls.isna()).sum()),
        "ppr_unclassified_types": sorted({str(t) for t in zoning.typereg[known & zoning.cls.isna()]}),
    }
    z = zoning[known & zoning.cls.notna()]
    sets = {}
    for cls in ("ppr_red", "ppr_blue"):
        d = z[z.cls == cls]
        sets[cls] = _zoneset(cls, d.proc, d.proc.map(approved), d.geom)
    for cls in ("azi", "azi_exc"):
        d = atlas[atlas.cls == cls] if len(atlas) else atlas
        sets[cls] = _zoneset(cls, d.get("id", []), d.get("year", []), d.get("geom", []))
    t = _zoneset("tri", scen.get("tri", []), scen.scenario.map(TRI_RANK) if len(scen) else [], scen.get("geom", []))
    digital = set(z.proc)
    dep_g = g[g.dep == dep]
    ppr_communes = frozenset(force[force.proc.isin(digital)].insee)
    communes = {}
    for insee, d in dep_g.groupby("insee"):
        f = d[(d.state == "Opposable") & (d.approved > 0)]
        # Plans older than the Loi Barnier (the plans des surfaces submersibles of 1948-1960) are
        # worth a PPR in law, but they are not PPRi: the commune's PPRi year is the first after them.
        b, old = f[f.approved >= config.BARNIER_YEAR], f[f.approved < config.BARNIER_YEAR]
        communes[insee] = {
            "name": d.commune.dropna().iloc[0] if d.commune.notna().any() else None,
            "first_approval": int(b.approved.min()) if len(b) else None,
            "anticipated": bool(len(b)) and bool(b.sort_values("approved").anticipated.iloc[0]),
            "pss": int(old.approved.min()) if len(old) else None,
            # The first PPRi ever, counting plans since repealed and replaced by a revision.
            "first_ppr": int(e.approved.min()) if len(e := d[(d.approved >= config.BARNIER_YEAR)
                                                            & ((d.state == "Opposable") | (d.substate == "Abrogé"))]) else None,
            "digital": insee in ppr_communes,
            "procedures": sorted(f.proc),
            "prescribed": int(((d.state == "Prescrit") | ((d.state == "Opposable") & (d.approved == 0))).sum()),
        }
    report["communes_flood_ppr"] = sum(1 for c in communes.values() if c["first_approval"] or c["pss"])
    report["communes_pss_only"] = sorted(i for i, c in communes.items() if c["pss"] and not c["first_approval"])
    report["communes_digital"] = len(ppr_communes)
    report["communes_without_digital"] = sorted(i for i, c in communes.items() if (c["first_approval"] or c["pss"]) and not c["digital"])
    return FrZones(sets, t, ppr_communes, communes, report)


@lru_cache(maxsize=4)
def zones(dep: str) -> FrZones:
    return build(dep, gaspar(), ppr_zoning(dep), azi(dep), tri(dep))


def version(fz: FrZones) -> str:
    """Fingerprint of the zone layers and approval dates: any change forces a recount."""
    h = hashlib.sha256()
    for zs in [*fz.sets.values(), fz.tri]:
        h.update(zs.zone.encode())
        for i, y, a in sorted(zip(map(str, zs.ids), zs.years, np.round(shapely.area(zs.geoms)).astype(int))):
            h.update(f"{i}|{y}|{a};".encode())
    h.update(",".join(sorted(fz.ppr_communes)).encode())
    return h.hexdigest()[:16]


def summary(fz: FrZones) -> dict:
    """Polygons and years per class, for the method section."""
    out = {}
    for zone, zs in fz.sets.items():
        yrs = zs.years[zs.years > 0]
        out[zone] = {"n": int(len(zs.geoms)), "procedures": int(len(set(zs.ids))) if zone.startswith("ppr") else None,
                     "first_year": int(yrs.min()) if len(yrs) else None,
                     "last_year": int(yrs.max()) if len(yrs) else None}
    out["tri"] = {"n": int(len(fz.tri.geoms)), "tri": sorted(set(map(str, fz.tri.ids)))}
    return out
