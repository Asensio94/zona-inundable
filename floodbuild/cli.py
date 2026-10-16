"""Command line: python -m floodbuild <command>."""
from __future__ import annotations

import argparse
import logging

from . import catastro, config, geo, snczi

log = logging.getLogger("floodbuild")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="floodbuild")
    p.add_argument("--region", action="append", choices=sorted(geo.PROVINCE_CCAA.values()),
                   help="INE community code (repeatable); the configured regions by default")
    sub = p.add_subparsers(dest="cmd", required=True)
    z = sub.add_parser("zones", help="download the SNCZI flood zones of the regions")
    z.add_argument("--force", action="store_true", help="download again even if the cache is recent")
    b = sub.add_parser("buildings", help="count Catastro buildings by flood zone and year")
    b.add_argument("--limit", type=int, help="count at most this many municipalities (the rest stay pending)")
    b.add_argument("--only", nargs="+", metavar="CODE", help="cadastral municipality codes")
    fz = sub.add_parser("fr-zones", help="download the French layers: GASPAR, PPR zoning, AZI and TRI")
    fz.add_argument("--dep", nargs="+", choices=sorted(config.FR_DEPARTMENTS), help="departments (all configured by default)")
    fb = sub.add_parser("fr-buildings", help="count BDNB buildings by French flood class and year")
    fb.add_argument("--dep", nargs="+", choices=sorted(config.FR_DEPARTMENTS), help="departments (all configured by default)")
    fb.add_argument("--force", action="store_true", help="recount even if the BDNB and the maps did not change")
    sub.add_parser("web", help="build docs/index.html, docs/fr/, the CSVs and docs/signals.json")
    sub.add_parser("all", help="zones, buildings and web, for Spain and France")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if a.region:
        config.REGIONS = {r: config.REGIONS.get(r, r) for r in a.region}
    provs = geo.provinces(tuple(config.REGIONS))

    if a.cmd in ("zones", "all"):
        snczi.update(provs, force=getattr(a, "force", False))
    if a.cmd in ("buildings", "all"):
        log.info(catastro.update(provs, limit=getattr(a, "limit", None),
                                 only=set(a.only) if getattr(a, "only", None) else None))
    if a.cmd in ("fr-zones", "fr-buildings", "all"):
        from .fr import bdnb, zones as frzones
        deps = getattr(a, "dep", None) or list(config.FR_DEPARTMENTS)
        if a.cmd == "fr-zones":
            for dep in deps:
                log.info("dep %s: %s", dep, frzones.zones(dep).report)
        else:
            log.info(bdnb.update(deps, force=getattr(a, "force", False)))
    if a.cmd in ("web", "all"):
        from . import signals, web
        from .fr import web as frweb
        web.build()
        frweb.build()
        signals.build()


if __name__ == "__main__":
    main()
