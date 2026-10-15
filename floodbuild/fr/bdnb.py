"""Buildings of the BDNB (open edition), counted by flood-zone class, TRI scenario and year.

The unit is the BDNB "bâtiment groupe": a building, or several joined ones, with one record of the
land tax files (Fichiers fonciers, table ffo_bat) giving its year of construction, use and number
of dwellings. That is the closest thing to a Catastro building. A group gets the strictest class
of the points of its constructions (one interior point per footprint).

Privacy: the zip also carries owners (proprietaire, rel_batiment_groupe_proprietaire) and the
applicants of building permits (sitadel). Neither the owner tables nor the applicant columns are
ever read. What is saved and published is the number of buildings per commune, class and year.
"""
from __future__ import annotations

import json
import logging
import re
import zipfile

import numpy as np
import pandas as pd
import requests
import shapely

from .. import config
from . import download, zones as frzones

log = logging.getLogger(__name__)

VERSION = 1  # bump when the counting rules change, so every department is recounted
COUNTS = config.COUNTS / "fr"
MANIFEST = COUNTS / "manifest.json"
NEW = "nouvelle construction"


def millesime() -> str:
    """Latest BDNB millesime published on data.gouv.fr («2026-02-a»), or the configured one."""
    try:
        r = requests.get(config.BDNB_DATASET_API, timeout=60, headers={"User-Agent": config.USER_AGENT})
        r.raise_for_status()
        found = {m for res in r.json().get("resources", [])
                 for m in re.findall(r"millesime_(\d{4}-\d{2}-[a-z])", res.get("url", ""))}
        if found:
            return max(found)
    except (requests.RequestException, ValueError):
        log.warning("data.gouv.fr unreachable, using BDNB millesime %s", config.BDNB_MILLESIME)
    return config.BDNB_MILLESIME


def archive(dep: str, m: str):
    """The department's BDNB zip of millesime m. A millesime never changes, so it is kept until the next."""
    name = f"bdnb/{m}_dep{dep}.zip"
    for old in (download.DIR / "bdnb").glob(f"*_dep{dep}.zip"):
        if old.name != name.split("/")[-1]:
            old.unlink()
    return download.fetch(config.BDNB_URL.format(m=m, dep=dep), name, max_age_days=None)


def _read(zf: zipfile.ZipFile, table: str, cols: list[str]) -> pd.DataFrame:
    member = next(n for n in zf.namelist() if n.endswith(f"/{table}.csv") or n == f"{table}.csv")
    return pd.read_csv(zf.open(member), sep=";", usecols=cols, dtype=str, encoding="utf-8")


def ff_year(zf: zipfile.ZipFile, m: str) -> int:
    """Year of the Fichiers fonciers the millesime is built on (situation at 1 January)."""
    try:
        meta = _read(zf, "metadonnees_bdnb_version", ["millesime", "changelog_detaille"])
        text = str(meta.changelog_detaille.iloc[0])
        found = re.search(r"Fichiers Fonciers\][^|]*\|\s*(\d{4})", text, re.I)
        if found:
            return int(found.group(1))
    except (StopIteration, KeyError, ValueError):
        pass
    return int(m[:4]) - 1


# --- Classification -----------------------------------------------------------------------------

RANK = {z: i for i, z in enumerate(config.FR_ZONE_ORDER + ["out"])}
TRI_NAMES = {0: "", **{v: k for k, v in frzones.TRI_RANK.items()}}


def classify_points(xy: np.ndarray, insee: np.ndarray, fz: frzones.FrZones) -> pd.DataFrame:
    """Class, year of the zone and TRI scenario of each point.

    The AZI only counts in communes without a digital PPR zoning: where the PPR exists, it is the
    binding map, and a building outside its red and blue zones is outside the regulated flood zone.
    """
    pts = shapely.points(xy)
    zone = np.full(len(xy), "out", dtype=object)
    mapped = np.zeros(len(xy), int)
    covered = np.isin(insee, list(fz.ppr_communes))
    for z in reversed(config.FR_ZONE_ORDER):        # azi_exc, azi, then blue and red overwrite
        inside, first = fz.sets[z].hits(pts)
        if z.startswith("azi"):
            inside &= ~covered
        zone[inside] = z
        mapped[inside] = first[inside]
    inside, rank = fz.tri.hits(pts)
    return pd.DataFrame({"zone": zone, "mapped": mapped, "tri": np.where(inside, rank, 0)})


def per_group(pts: pd.DataFrame) -> pd.DataFrame:
    """One row per building group: its strictest class (and that zone's year) and its most frequent TRI scenario."""
    p = pts.assign(rank=pts.zone.map(RANK), mapped_key=pts.mapped.where(pts.mapped > 0, 9999))
    p = p.sort_values(["group", "rank", "mapped_key"])
    first = p.drop_duplicates("group")[["group", "zone", "mapped"]]
    t = pts[pts.tri > 0].groupby("group").tri.min()
    out = first.set_index("group").join(t).fillna({"tri": 0})
    out["tri"] = out.tri.astype(int).map(TRI_NAMES)
    return out.reset_index()


def apparent_reform(groups: pd.DataFrame, rel: pd.DataFrame, permits: pd.DataFrame) -> pd.Series:
    """Groups dated Y whose parcels had permits filed in Y-3..Y, none of them for a new building.

    rel: group -> parcel; permits: parcel, nature, year. Only years with a full Sitadel window.
    """
    g = groups[["group", "year"]]
    g = g[g.year >= config.SITADEL_FROM + config.SITADEL_LOOKBACK]
    j = g.merge(rel, on="group").merge(permits, on="parcel")
    j = j[(j.filed <= j.year) & (j.filed >= j.year - config.SITADEL_LOOKBACK)]
    if j.empty:
        return pd.Series(False, index=groups.index)
    agg = j.assign(new=j.nature == NEW).groupby("group").new.agg(["any", "size"])
    reform = set(agg.index[~agg["any"]])
    return groups.group.isin(reform)


def counts(b: pd.DataFrame) -> pd.DataFrame:
    """Buildings per commune, class, TRI scenario and year: the only thing that is kept."""
    after = (b.mapped > 0) & (b.year > b.mapped)
    b = b.assign(after_map=after, after_mixed=after & b.mixed, after_res=after & b.res,
                 after_dwellings=b.dwellings.where(after, 0))
    g = b.groupby(["insee", "zone", "tri", "year"])
    return pd.DataFrame({"n": g.size(), "mixed": g.mixed.sum(), "res": g.res.sum(),
                         "dwellings": g.dwellings.sum(), "after_map": g.after_map.sum(),
                         "after_mixed": g.after_mixed.sum(), "after_res": g.after_res.sum(),
                         "after_dwellings": g.after_dwellings.sum()}).reset_index()


def count_department(dep: str, zf: zipfile.ZipFile, fz: frzones.FrZones) -> tuple[pd.DataFrame, dict]:
    groups = _read(zf, "batiment_groupe", ["batiment_groupe_id", "code_commune_insee", "libelle_commune_insee"])
    groups = groups.rename(columns={"batiment_groupe_id": "group", "code_commune_insee": "insee"})
    cons = _read(zf, "batiment_construction", ["WKT", "batiment_groupe_id"])
    geoms = shapely.from_wkt(cons.WKT.to_numpy(), on_invalid="ignore")
    ok = ~shapely.is_missing(geoms) & ~shapely.is_empty(geoms)
    xy = shapely.get_coordinates(shapely.point_on_surface(shapely.make_valid(geoms[ok])))
    pts = pd.DataFrame({"group": cons.batiment_groupe_id.to_numpy()[ok]})
    pts = pts.merge(groups[["group", "insee"]], on="group", how="left")
    log.info("dep %s: %d groups, %d constructions", dep, len(groups), len(pts))
    pts = pd.concat([pts, classify_points(xy, pts.insee.fillna("").to_numpy(), fz)], axis=1)
    cls = per_group(pts)

    ffo = _read(zf, "batiment_groupe_ffo_bat", ["batiment_groupe_id", "annee_construction", "usage_niveau_1_txt", "nb_log"])
    ffo = ffo.rename(columns={"batiment_groupe_id": "group"})
    b = groups.merge(cls, on="group", how="left").fillna({"zone": "out", "mapped": 0, "tri": ""})
    with_ffo = b.group.isin(ffo.group)
    no_ffo = b[~with_ffo].zone.value_counts().to_dict()
    b = b[with_ffo].merge(ffo, on="group")
    b["year"] = pd.to_numeric(b.annee_construction, errors="coerce").fillna(0).astype(int)
    b["res"] = b.usage_niveau_1_txt.fillna("").str.startswith("Résidentiel")
    b["dwellings"] = pd.to_numeric(b.nb_log, errors="coerce").fillna(0).astype(int)
    b["mapped"] = b.mapped.astype(int)

    # Never read: sitadel's applicant columns (denomination_demandeur, siren, siret).
    sit = _read(zf, "sitadel", ["type_numero_dau", "nature_projet", "annee_depot_dau"])
    rel_p = _read(zf, "rel_parcelle_sitadel", ["type_numero_dau", "parcelle_id"])
    permits = sit.merge(rel_p, on="type_numero_dau").rename(columns={"parcelle_id": "parcel", "nature_projet": "nature"})
    permits["filed"] = pd.to_numeric(permits.annee_depot_dau, errors="coerce")
    rel = _read(zf, "rel_batiment_groupe_parcelle", ["batiment_groupe_id", "parcelle_id"])
    rel = rel.rename(columns={"batiment_groupe_id": "group", "parcelle_id": "parcel"})
    b["mixed"] = apparent_reform(b, rel, permits[["parcel", "nature", "filed"]].dropna()).to_numpy()

    names = groups.drop_duplicates("insee").set_index("insee").libelle_commune_insee.to_dict()
    meta = {"groups": int(len(groups)), "groups_with_year": int(len(b)),
            "unknown_year": int((b.year == 0).sum()),
            "no_tax_record_by_zone": {k: int(v) for k, v in no_ffo.items()},
            "names": {k: v for k, v in sorted(names.items()) if isinstance(k, str)}}
    return counts(b), meta


# --- Saved counts -------------------------------------------------------------------------------

def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}


def save_manifest(m: dict) -> None:
    COUNTS.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(dict(sorted(m.items())), ensure_ascii=False, indent=1), encoding="utf-8")


def update(deps: list[str] | None = None, force: bool = False) -> dict:
    """Recount every department whose BDNB millesime or flood maps changed since the last run."""
    deps = deps or list(config.FR_DEPARTMENTS)
    m = millesime()
    manifest = load_manifest()
    done = []
    for dep in deps:
        fz = frzones.zones(dep)
        ver = f"{VERSION}-{frzones.version(fz)}"
        old = manifest.get(dep, {})
        if not force and old.get("millesime") == m and old.get("zones") == ver:
            continue
        with zipfile.ZipFile(archive(dep, m)) as zf:
            c, meta = count_department(dep, zf, fz)
            year = ff_year(zf, m)
        COUNTS.mkdir(parents=True, exist_ok=True)
        c.sort_values(["insee", "zone", "tri", "year"]).to_csv(COUNTS / f"{dep}.csv", index=False)
        manifest[dep] = {"name": config.FR_DEPARTMENTS[dep]["name"], "millesime": m, "ff_year": year,
                         "zones": ver, "zones_summary": frzones.summary(fz), "zones_report": fz.report,
                         "ppr_communes": fz.communes, **meta}
        save_manifest(manifest)
        done.append(dep)
        log.info("dep %s: %d buildings with a year, %d in flood zones", dep, meta["groups_with_year"],
                 int(c[c.zone != "out"].n.sum()))
    return {"counted": done, "millesime": m}
