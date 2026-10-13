"""Flood zones of the SNCZI (MITECO): preferential-flow zone, 100-year and 500-year flood areas.

The layers come from the ministry's GeoServer WFS in ETRS89 / UTM 30N, paged and limited to the
bounding box of each processed province. Each zone class is kept as an array of polygons with
the year the map was approved, and queried with a spatial index; no union is built, so a
building can be traced to the earliest map that covered it.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
import requests
import shapely
from shapely.geometry import shape

from . import config, geo

log = logging.getLogger(__name__)
DIR = config.CACHE / "snczi"
MAX_AGE_DAYS = 25


def _get_json(params: dict) -> dict:
    for attempt in range(4):
        try:
            r = requests.get(config.SNCZI_WFS, params=params, timeout=600,
                             headers={"User-Agent": config.USER_AGENT})
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))
    raise AssertionError


def _bbox(province: str) -> tuple[float, float, float, float]:
    geoms = [m.geom for m in geo.municipalities(tuple(config.REGIONS)) if m.province == province]
    x0, y0, x1, y1 = shapely.total_bounds(np.array(geoms, dtype=object))
    return x0 - 1000, y0 - 1000, x1 + 1000, y1 + 1000  # es-atlas boundaries are simplified


def _approval_year(value: str | None) -> int | None:
    """«2011-10-31T23:00:00Z» is midnight of 1 November in Spain: read it in Madrid time."""
    if not value:
        return None
    t = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(t) else int(t.tz_convert("Europe/Madrid").year)


def download(zone: str, province: str) -> list[dict]:
    """Every feature of one zone class touching one province, as {id, year, wkb}."""
    layer, date_field = config.ZONES[zone]
    x0, y0, x1, y1 = _bbox(province)
    out, start = [], 0
    while True:
        fc = _get_json({
            "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": layer,
            "outputFormat": "application/json", "srsName": config.WORK_CRS, "sortBy": "id_zona",
            "count": config.WFS_PAGE, "startIndex": start,
            "bbox": f"{x0},{y0},{x1},{y1},urn:ogc:def:crs:EPSG::25830",
        })
        feats = fc.get("features") or []
        for f in feats:
            if not f.get("geometry"):
                continue
            p = f["properties"]
            g = shapely.make_valid(shape(f["geometry"]))
            out.append({"id": p.get("id_zona") or f.get("id"), "year": _approval_year(p.get(date_field)),
                        "updated": (p.get("fecha_lim") or "")[:10], "wkb": shapely.to_wkb(g, hex=True)})
        log.info("%s %s: %d features", zone, province, len(out))
        if len(feats) < config.WFS_PAGE:
            return out
        start += config.WFS_PAGE


def _cache_path(zone: str, province: str):
    return DIR / f"{zone}_{province}.json.gz"


def update(provinces: list[str], force: bool = False) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    for prov in provinces:
        for zone in config.ZONE_ORDER:
            path = _cache_path(zone, prov)
            if not force and path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_DAYS * 86400:
                continue
            feats = download(zone, prov)
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                json.dump(feats, fh)
            tmp.replace(path)


@dataclass
class ZoneSet:
    """All polygons of one zone class, with a spatial index and their approval years."""
    zone: str
    ids: np.ndarray
    years: np.ndarray        # approval year, 0 when unknown
    geoms: np.ndarray
    tree: shapely.STRtree

    def hits(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Mask of points inside any polygon, and the earliest approval year of those polygons."""
        inside = np.zeros(len(points), bool)
        first = np.full(len(points), 9999)
        if len(self.geoms) and len(points):
            # A layer polygon can be a whole river system with a million vertices. It is clipped to
            # the buildings' box and prepared, and the points are tested against it with
            # contains_xy. (STRtree.query(points, predicate) would prepare the points, not the
            # polygon, and take minutes per municipality.)
            x0, y0, x1, y1 = shapely.total_bounds(points)
            cand = self.tree.query(shapely.box(x0, y0, x1, y1), predicate="intersects")
            xy = shapely.get_coordinates(points)
            for gi in cand:
                piece = shapely.clip_by_rect(self.geoms[gi], x0 - 10, y0 - 10, x1 + 10, y1 + 10)
                if piece.is_empty:
                    continue
                px0, py0, px1, py1 = piece.bounds
                near = np.flatnonzero((xy[:, 0] >= px0) & (xy[:, 0] <= px1) & (xy[:, 1] >= py0) & (xy[:, 1] <= py1))
                if not len(near):
                    continue
                shapely.prepare(piece)
                hit = near[shapely.contains_xy(piece, xy[near, 0], xy[near, 1])]
                inside[hit] = True
                np.minimum.at(first, hit, self.years[gi] if self.years[gi] > 0 else 9999)
        first[first == 9999] = 0
        return inside, first


def _polygonal(g):
    """Polygon parts of a geometry. make_valid can leave a GeometryCollection with stray lines,
    and GEOS has no fast prepared point test for collections (minutes instead of milliseconds)."""
    if shapely.get_type_id(g) != 7:
        return g
    parts = shapely.get_parts(g)
    return shapely.multipolygons(shapely.get_parts(parts[np.isin(shapely.get_type_id(parts), (3, 6))]))


@lru_cache(maxsize=4)
def zones(provinces: tuple[str, ...]) -> dict[str, ZoneSet]:
    out = {}
    for zone in config.ZONE_ORDER:
        seen, ids, years, wkbs = set(), [], [], []
        for prov in provinces:
            with gzip.open(_cache_path(zone, prov), "rt", encoding="utf-8") as fh:
                for f in json.load(fh):
                    # Neighbouring provinces share river reaches; keep each feature once.
                    key = (f["id"], f["wkb"][:64], len(f["wkb"]))
                    if key in seen:
                        continue
                    seen.add(key)
                    ids.append(f["id"])
                    years.append(f["year"] or 0)
                    wkbs.append(f["wkb"])
        geoms = shapely.from_wkb(np.array(wkbs, dtype=object)) if wkbs else np.array([], dtype=object)
        geoms = np.array([_polygonal(g) for g in geoms], dtype=object)
        shapely.prepare(geoms)
        out[zone] = ZoneSet(zone, np.array(ids, dtype=object), np.array(years, int), geoms, shapely.STRtree(geoms))
    return out


def version(provinces: tuple[str, ...]) -> str:
    """Fingerprint of the zone layers: a change in any map forces the counts to be redone."""
    h = hashlib.sha256()
    for zone, zs in zones(provinces).items():
        h.update(zone.encode())
        for i, y, a in sorted(zip(zs.ids, zs.years, np.round(shapely.area(zs.geoms)).astype(int))):
            h.update(f"{i}|{y}|{a};".encode())
    return h.hexdigest()[:16]


def _union_area(zs: ZoneSet, tile: float = 10_000) -> float:
    """Area of the union of a zone class, in m², tile by tile.

    A single union_all over river systems of a million vertices runs for more than ten minutes.
    Unioned within 10 km tiles, each piece is small, and the tiles don't overlap, so their areas add up.
    """
    if not len(zs.geoms):
        return 0.0
    x0, y0, x1, y1 = shapely.total_bounds(zs.geoms)
    total = 0.0
    for tx in np.arange(x0, x1, tile):
        for ty in np.arange(y0, y1, tile):
            rect = (tx, ty, tx + tile, ty + tile)
            cand = zs.tree.query(shapely.box(*rect), predicate="intersects")
            if len(cand):
                total += shapely.area(shapely.union_all(shapely.clip_by_rect(zs.geoms[cand], *rect)))
    return float(total)


def summary(provinces: tuple[str, ...]) -> dict:
    """Polygons, area and approval years per zone class, for the method section."""
    # The union takes minutes; it is kept next to the counts and redone only when a map changes.
    path = config.COUNTS / "zones.json"
    ver = version(provinces)
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if saved.get("version") != ver:
        saved = {"version": ver, "km2": {z: round(_union_area(zs) / 1e6, 1) for z, zs in zones(provinces).items()}}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, indent=1), encoding="utf-8")
    out = {}
    for zone, zs in zones(provinces).items():
        yrs = zs.years[zs.years > 0]
        out[zone] = {"n": int(len(zs.geoms)),
                     "km2": saved["km2"][zone],
                     "first_year": int(yrs.min()) if len(yrs) else None,
                     "last_year": int(yrs.max()) if len(yrs) else None}
    return out
