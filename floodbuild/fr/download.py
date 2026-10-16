"""Downloads of the French sources into data/cache/fr, streamed to disk (the BDNB zips are hundreds of MB)."""
from __future__ import annotations

import io
import logging
import time
import zipfile
from pathlib import Path

import numpy as np
import requests
import shapefile
import shapely

from .. import config

log = logging.getLogger(__name__)
DIR = config.CACHE / "fr"
_HEADERS = {"User-Agent": config.USER_AGENT}


def fetch(url: str, name: str, max_age_days: float | None = 25) -> Path:
    """The file at url, cached as data/cache/fr/<name>; None as max_age_days keeps it forever."""
    path = DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (max_age_days is None or time.time() - path.stat().st_mtime < max_age_days * 86400):
        return path
    tmp = path.with_suffix(path.suffix + ".part")
    for attempt in range(4):
        try:
            with requests.get(url, headers=_HEADERS, timeout=600, stream=True) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
            tmp.replace(path)
            log.info("downloaded %s (%.0f MB)", name, path.stat().st_size / 1e6)
            return path
        except requests.RequestException:
            if attempt == 3:
                if path.exists():          # an old copy is better than nothing
                    log.warning("could not refresh %s, using the cached copy", name)
                    return path
                raise
            time.sleep(10 * (attempt + 1))
    raise AssertionError


def shapefile_in_zip(zf: zipfile.ZipFile, shp: str) -> shapefile.Reader:
    """A shapefile read from inside a zip, with the encoding its .cpg declares (latin-1 otherwise)."""
    stem = shp[:-4]
    names = {n.lower(): n for n in zf.namelist()}
    part = lambda ext: io.BytesIO(zf.read(names[(stem + ext).lower()]))  # noqa: E731
    enc = "latin-1"
    if (stem + ".cpg").lower() in names:
        cpg = zf.read(names[(stem + ".cpg").lower()]).decode("ascii", "ignore").strip().lower()
        enc = "utf-8" if "utf" in cpg else enc
    return shapefile.Reader(shp=part(".shp"), shx=part(".shx"), dbf=part(".dbf"), encoding=enc)


def polygon(shp: shapefile.Shape):
    """Polygon of a shapefile shape, rebuilt from its rings.

    pyshp's own GeoJSON conversion stops at degenerate rings, which the DDTM zonings have. Here
    zero-area rings are dropped, clockwise rings are shells and counter-clockwise ones holes (the
    shapefile rule), and each hole goes to the smallest shell that contains it. A hole inside no
    shell is dropped. Some shapes have fifteen thousand rings, hence the spatial index.
    """
    pts = np.asarray(shp.points, float)
    bounds = list(shp.parts) + [len(pts)]
    rings = [pts[a:b] for a, b in zip(bounds[:-1], bounds[1:]) if b - a >= 4]
    if not rings:
        return shapely.Polygon()
    lr = shapely.linearrings(np.concatenate(rings), indices=np.repeat(np.arange(len(rings)), [len(r) for r in rings]))
    area = shapely.area(shapely.polygons(lr))
    lr = lr[area > 1e-6]
    if not len(lr):
        return shapely.Polygon()
    ccw = shapely.is_ccw(lr)
    if ccw.all():                     # some writers ignore orientation: then every ring is a shell
        ccw[:] = False
    shells, holes = lr[~ccw], lr[ccw]
    shell_polys = shapely.make_valid(shapely.polygons(shells))
    owner = np.full(len(holes), -1)
    if len(holes):
        # Each shell, prepared, tests the holes' points at once (as in ZoneSet.hits): a spatial
        # query with a "within" predicate would test each point against an unprepared shell.
        xy = shapely.get_coordinates(shapely.point_on_surface(shapely.make_valid(shapely.polygons(holes))))
        for k in np.argsort(-shapely.area(shell_polys)):            # smallest shell written last wins
            shapely.prepare(shell_polys[k])
            owner[shapely.contains_xy(shell_polys[k], xy[:, 0], xy[:, 1])] = k
    parts = []
    for k, ring in enumerate(shells):
        hs = holes[owner == k]
        parts.append(shapely.make_valid(shapely.polygons(ring, holes=list(hs))) if len(hs) else shell_polys[k])
    # Gathered without a union, which takes minutes on the largest shapes. Shells can overlap, so
    # the result may be invalid as a whole; zones._zoneset splits it back into valid parts.
    flat = shapely.get_parts(np.array(parts, dtype=object))
    return shapely.multipolygons(flat[shapely.get_type_id(flat) == 3])
