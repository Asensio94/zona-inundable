"""Buildings of the Catastro INSPIRE service, counted by flood-zone class and year of construction.

The download, cache and ATOM helpers are copied from observatorio-alegaciones
(observatorio/footprint.py) and adapted to the Buildings theme; they are not imported, so each
repository stays self-contained.

Privacy: the GML carries each building's cadastral reference, which leads to its owners in the
Catastro's electronic office. The parser never reads it, nor any address or parcel. What is saved and published is the
number of buildings per municipality, zone class and year.
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from difflib import SequenceMatcher
from functools import lru_cache

import numpy as np
import pandas as pd
import requests
import shapely
from pyproj import Transformer

from . import config, geo, snczi

log = logging.getLogger(__name__)

DIR = config.CACHE / "catastro"
VERSION = 3  # bump when the counting rules change, so every municipality is recounted

_HEADERS = {"User-Agent": config.USER_AGENT}
_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# --- Copied from observatorio/footprint.py ---------------------------------------------------

def _get(url: str) -> bytes:
    for attempt in range(4):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=180)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError


def _cached(url: str, name: str, max_age_days: float = 25) -> bytes:
    DIR.mkdir(parents=True, exist_ok=True)
    f = DIR / name
    if f.exists() and time.time() - f.stat().st_mtime < max_age_days * 86400:
        return f.read_bytes()
    try:
        f.write_bytes(_get(url))
    except requests.RequestException:
        if not f.exists():
            raise
    return f.read_bytes()


# --- ATOM feeds -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _lonlat_to_work():
    return Transformer.from_crs("EPSG:4326", config.WORK_CRS, always_xy=True).transform


def municipalities(office: str) -> list[dict]:
    """Cadastral municipalities of one territorial office: code, name, zip, date and bounding box."""
    if office in config.FORAL_OFFICES:
        return []
    url = config.CATASTRO_ATOM.format(office=office)
    feed = ET.fromstring(_cached(url, f"bu_atom_{office}.xml"))
    out = []
    for e in feed.findall("a:entry", _ATOM_NS):
        link = e.find("a:link[@rel='enclosure']", _ATOM_NS)
        href = link.get("href", "") if link is not None else ""
        m = re.search(r"/(\d{5})-([^/]+)/", href)
        if not m:
            continue
        box = None
        poly = next((x for x in e.iter() if _ln(x.tag) == "polygon" and x.text), None)
        if poly is not None:
            v = np.array(poly.text.split(), float).reshape(-1, 2)  # lat lon pairs
            xs, ys = _lonlat_to_work()(v[:, 1], v[:, 0])
            box = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
        out.append({"code": m.group(1), "name": m.group(2).strip(), "office": office, "url": href,
                    "updated": (e.findtext("a:updated", "", _ATOM_NS) or "")[:10], "bbox": box})
    return out


def touches_zones(entry: dict, zs: dict[str, snczi.ZoneSet]) -> bool:
    """Whether any flood polygon reaches the municipality's bounding box (or the box is unknown)."""
    if not entry["bbox"]:
        return True
    box = shapely.box(*entry["bbox"])
    return any(len(z.tree.query(box, predicate="intersects")) for z in zs.values())


# --- Buildings --------------------------------------------------------------------------------

def _year(text: str | None) -> int:
    """Year of a Catastro date; 0 when the year is unknown («--01-01»)."""
    return int(text[:4]) if text and text[:4].isdigit() else 0


_WORK_EPSG = int(config.WORK_CRS.split(":")[-1])


def _epsg(srs: str | None) -> int:
    """EPSG code of a GML srsName («urn:ogc:def:crs:EPSG::25831»); the work CRS when absent."""
    m = re.search(r"(\d+)$", srs or "")
    return int(m.group(1)) if m else _WORK_EPSG


@lru_cache(maxsize=8)
def _to_work(epsg: int):
    return Transformer.from_crs(f"EPSG:{epsg}", config.WORK_CRS, always_xy=True).transform


def parse_buildings(gml: io.BufferedIOBase) -> pd.DataFrame:
    """One row per building: representative point, construction years, use and dwellings."""
    rows = []
    for _, el in ET.iterparse(gml):
        if _ln(el.tag) != "Building":
            continue
        begin = end = use = None
        dwellings = 0
        ring = srs = None
        for x in el.iter():
            t = _ln(x.tag)
            if srs is None and x.get("srsName"):
                srs = x.get("srsName")
            if t == "beginning":
                begin = x.text
            elif t == "end":
                end = x.text
            elif t == "posList" and ring is None:   # first exterior ring is enough for a point
                ring = x.text
            elif t == "currentUse":
                use = (x.text or "").strip()
            elif t == "numberOfDwellings" and x.text and x.text.strip().isdigit():
                dwellings = int(x.text)
        el.clear()
        if not ring:
            continue
        a = np.array(ring.split(), float).reshape(-1, 2)
        if len(a) < 4:
            continue
        rows.append((a, _year(begin), _year(end), (use or "").startswith("1_"), dwellings, _epsg(srs)))
    if not rows:
        return pd.DataFrame(columns=["x", "y", "begin", "year", "res", "dwellings"])
    rings = shapely.linearrings(np.concatenate([r[0] for r in rows]),
                                indices=np.repeat(np.arange(len(rows)), [len(r[0]) for r in rows]))
    polys = shapely.make_valid(shapely.polygons(rings))
    pts = shapely.point_on_surface(polys)
    xy = shapely.get_coordinates(pts)
    # Municipalities east of the Greenwich meridian (the Marina Alta) come in UTM zone 31.
    epsg = np.array([r[5] for r in rows])
    for code in set(epsg.tolist()) - {_WORK_EPSG}:
        sel = epsg == code
        xy[sel, 0], xy[sel, 1] = _to_work(code)(xy[sel, 0], xy[sel, 1])
    return pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1],
                         "begin": [r[1] for r in rows], "year": [r[2] for r in rows],
                         "res": [r[3] for r in rows], "dwellings": [r[4] for r in rows]})


def classify(df: pd.DataFrame, zs: dict[str, snczi.ZoneSet]) -> pd.DataFrame:
    """Exclusive zone class (most restrictive first) and the year that zone was first mapped."""
    pts = shapely.points(df[["x", "y"]].to_numpy())
    zone = np.full(len(df), "out", dtype=object)
    mapped = np.zeros(len(df), int)
    for z in reversed(config.ZONE_ORDER):          # t500, then t100, then zfp overwrite
        inside, first = zs[z].hits(pts)
        zone[inside] = z
        mapped[inside] = first[inside]
    return df.assign(zone=zone, mapped=mapped)


_STOP = {"EL", "LA", "LES", "ELS", "LOS", "LAS", "L", "D", "DE", "DEL", "DELS", "I", "Y", "EN", "NA"}


def _tokens(name: str) -> set[str]:
    """Words of a municipality name without accents or articles: «l'Alqueria de la Comtessa»
    and «L ALQUERIA DE LA COMTESSA» give the same set."""
    return set(re.findall(r"[A-Z0-9]+", _plain(name))) - _STOP


def _plain(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()


def _same(a: str, b: str) -> bool:
    """Two words of a name agree: equal, one cut short (the Catastro truncates at 30 characters),
    or spelt alike (Benlloch / Benlloc, Montcada / Moncada)."""
    return a == b or a.startswith(b) or b.startswith(a) or SequenceMatcher(None, a, b).ratio() >= 0.75


def name_score(catastro_name: str, ine_name: str) -> float:
    """How well a Catastro name matches an INE name, from 0 to 1.

    Every Catastro word must have a partner, so «Alcocer de Planes» does not match «Planes»; the
    score is the share of INE words matched («MONTCADA MONCADA» covers all of «Moncada»). When
    the Catastro lost a letter («PU OL» for Puçol) the whole names are compared instead.
    """
    want, have = _tokens(catastro_name), _tokens(ine_name)
    if not want or not have:
        return 0.0
    if all(any(_same(a, b) for b in have) for a in want):
        return sum(any(_same(a, b) for a in want) for b in have) / len(have)
    squash = lambda s: re.sub(r"[^A-Z0-9]", "", _plain(s))  # noqa: E731
    return 1.0 if SequenceMatcher(None, squash(catastro_name), squash(ine_name)).ratio() >= 0.85 else 0.0


def ine_code(df: pd.DataFrame, name: str, munis: list[geo.Municipality], tree: shapely.STRtree) -> str | None:
    """INE code of a cadastral municipality, or None when no INE municipality nearby has its name.

    Catastro and INE number municipalities differently (Paiporta is 46188 in Catastro and 46186
    in INE), and the es-atlas boundaries are too simplified to go by the ground alone: in l'Horta
    most of Mislata's buildings fall inside the outline of València. So the candidates are the
    municipalities within 3 km of the buildings, and the one whose name matches wins; the ground
    only breaks ties. A few small municipalities are missing from es-atlas (Rafal, Llocnou de la
    Corona…); they get None rather than a neighbour's code.
    """
    if df.empty:
        return None
    s = df.sample(min(len(df), config.INE_SAMPLE), random_state=0)
    pts = shapely.points(s[["x", "y"]].to_numpy())
    near = tree.query(shapely.box(*shapely.total_bounds(pts)).buffer(3000), predicate="intersects")
    _, mi = tree.query(pts, predicate="within")
    ground = np.bincount(mi, minlength=len(munis)) if len(mi) else np.zeros(len(munis), int)
    best, best_key = None, (0.0, 0)
    for i in near:
        score = name_score(name, munis[i].name)
        if score >= 0.75 and (score, ground[i]) > best_key:
            best, best_key = munis[i].ine, (score, int(ground[i]))
    return best


def counts(df: pd.DataFrame) -> pd.DataFrame:
    """Buildings per zone class and year of construction, the only thing that is kept."""
    df = df.assign(mixed=(df.year - df.begin).abs().gt(config.MIXED_YEARS) & (df.begin > 0) & (df.year > 0),
                   after_map=(df.mapped > 0) & (df.year > df.mapped))
    g = df.groupby(["zone", "year"])
    return pd.DataFrame({"n": g.size(), "mixed": g.mixed.sum(), "res": g.res.sum(),
                         "dwellings": g.dwellings.sum(), "after_map": g.after_map.sum()}).reset_index()


def count_municipality(entry: dict, zs: dict[str, snczi.ZoneSet],
                       munis: list[geo.Municipality], tree: shapely.STRtree) -> tuple[pd.DataFrame, dict]:
    raw = _get(entry["url"])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".building.gml"))
        with zf.open(name) as fh:
            df = parse_buildings(fh)
    df = classify(df, zs)
    meta = {"name": entry["name"], "office": entry["office"], "updated": entry["updated"],
            "ine": ine_code(df, entry["name"], munis, tree), "buildings": int(len(df)),
            "unknown_year": int((df.year == 0).sum()) if len(df) else 0}
    return counts(df), meta


# --- Saved counts -------------------------------------------------------------------------------

MANIFEST = config.COUNTS / "manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}


def save_manifest(m: dict) -> None:
    config.COUNTS.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(dict(sorted(m.items())), ensure_ascii=False, indent=1), encoding="utf-8")


def update(provinces: list[str], limit: int | None = None, only: set[str] | None = None) -> dict:
    """Recount every cadastral municipality whose buildings or flood maps changed since last run."""
    zs = snczi.zones(tuple(provinces))
    zver = f"{VERSION}-{snczi.version(tuple(provinces))}"
    munis = geo.municipalities(tuple(config.REGIONS))
    tree = shapely.STRtree([m.geom for m in munis])
    manifest = load_manifest()
    todo, skipped = [], 0
    for office in provinces:
        for e in municipalities(office):
            if only and e["code"] not in only:
                continue
            if not touches_zones(e, zs):
                skipped += 1
                manifest.pop(e["code"], None)
                continue
            m = manifest.get(e["code"])
            if m and m.get("updated") == e["updated"] and m.get("zones") == zver:
                continue
            todo.append(e)
    log.info("%d municipalities to count, %d without flood zones", len(todo), skipped)
    done = 0
    for e in todo[:limit]:
        t = time.time()
        try:
            c, meta = count_municipality(e, zs, munis, tree)
        except (requests.RequestException, zipfile.BadZipFile, StopIteration, ET.ParseError) as ex:
            log.warning("%s %s: %s", e["code"], e["name"], ex)
            continue
        path = config.COUNTS / e["office"] / f"{e['code']}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        c.to_csv(path, index=False)
        manifest[e["code"]] = {**meta, "zones": zver}
        done += 1
        if done % 10 == 0:
            save_manifest(manifest)
        log.info("[%d/%d] %s %s -> %s: %d buildings, %d in flood zones (%.0f s)", done, len(todo), e["code"],
                 e["name"], meta["ine"], meta["buildings"], int(c[c.zone != "out"].n.sum()), time.time() - t)
    save_manifest(manifest)
    return {"counted": done, "pending": len(todo) - done, "without_zones": skipped}
