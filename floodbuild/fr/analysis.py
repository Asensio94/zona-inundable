"""From the French counts to the published figures: per commune, per year, and before/after each PPR.

Two readings. The French one: buildings in the red and blue zones of a PPRi dated after the year
that PPRi first bound new building (approval, or anticipated application). The Spanish one, for
reading both countries side by side: the same windows as Spain (2008–2016 against 2017 on).
"""
from __future__ import annotations

import pandas as pd

from .. import config
from . import bdnb

ZONED = list(config.FR_ZONE_ORDER)
PPR = ["ppr_red", "ppr_blue"]
AZI = ["azi", "azi_exc"]
EFFECT_YEARS = 10   # years before a PPR compared with the years after it


def load() -> tuple[pd.DataFrame, dict]:
    """All saved counts: one row per commune, class, TRI scenario and year."""
    manifest = bdnb.load_manifest()
    frames = []
    for dep in manifest:
        path = bdnb.COUNTS / f"{dep}.csv"
        if dep in config.FR_DEPARTMENTS and path.exists():
            frames.append(pd.read_csv(path, dtype={"insee": str, "tri": str}).assign(dep=dep))
    cols = ["insee", "zone", "tri", "year", "n", "mixed", "res", "dwellings", "after_map",
            "after_mixed", "after_res", "after_dwellings", "dep"]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
    df["tri"] = df.tri.fillna("")
    return df, {k: v for k, v in manifest.items() if k in config.FR_DEPARTMENTS}


def data_year(manifest: dict) -> int:
    """Year of the Fichiers fonciers: the tax files describe 1 January of that year."""
    years = [m["ff_year"] for m in manifest.values() if m.get("ff_year")]
    return max(years) if years else pd.Timestamp.now().year - 1


def windows(year: int) -> dict:
    last = year - 1                                  # the last year the tax files can show
    post_end = last - config.FR_PROVISIONAL_YEARS
    return {"pre": config.PRE_WINDOW, "post": (config.RD_YEAR + 1, post_end), "boom": config.BOOM_WINDOW,
            "provisional": (post_end + 1, last), "last": last}


def _in(df: pd.DataFrame, w) -> pd.DataFrame:
    return df[(df.year >= w[0]) & (df.year <= w[1])]


def _span(w) -> int:
    return w[1] - w[0] + 1


def _share(a: float, b: float) -> float | None:
    return round(100 * a / b, 2) if b else None


def communes_info(manifest: dict) -> dict[str, dict]:
    """PPR facts and name of every commune, from GASPAR (saved in the manifest) and the BDNB."""
    out = {}
    for m in manifest.values():
        for insee, name in m.get("names", {}).items():
            out.setdefault(insee, {"name": name})
        for insee, c in m.get("ppr_communes", {}).items():
            out.setdefault(insee, {}).update({**c, "name": out.get(insee, {}).get("name") or c.get("name")})
    return out


def period_stats(df: pd.DataFrame, w: dict) -> dict:
    """Buildings per year in flood zones and in PPR zones, and their share of all new buildings."""
    out = {}
    for k in ("boom", "pre", "post"):
        d = _in(df, w[k])
        z, r = d[d.zone.isin(ZONED)], d[d.zone.isin(PPR)]
        out[k] = {
            "years": list(w[k]), "zoned": int(z.n.sum()), "ppr": int(r.n.sum()), "all": int(d.n.sum()),
            "per_year": round(z.n.sum() / _span(w[k]), 1), "ppr_per_year": round(r.n.sum() / _span(w[k]), 1),
            "share": _share(z.n.sum(), d.n.sum()), "ppr_share": _share(r.n.sum(), d.n.sum()),
            "share_clean": _share((z.n - z.mixed).sum(), (d.n - d.mixed).sum()),
            "by_zone": {zz: int(d[d.zone == zz].n.sum()) for zz in ZONED},
        }
    return out


def ppr_effect(df: pd.DataFrame, info: dict, w: dict) -> dict:
    """Share of each commune's new buildings that went into today's red and blue zones, in the
    EFFECT_YEARS years up to its first PPR and in the years after it (up to the last complete one).

    Only communes whose PPR is digital and bound building at least three complete years before
    the end of the data, so that "after" is not a single year.
    """
    rows = []
    for insee, d in df.groupby("insee"):
        c = info.get(insee, {})
        a = c.get("first_approval")
        if not c.get("digital") or not a or a > w["post"][1] - 3:
            continue
        before, after = _in(d, (a - EFFECT_YEARS, a)), _in(d, (a + 1, w["post"][1]))
        rows.append({"insee": insee, "year": a,
                     "before_ppr": int(before[before.zone.isin(PPR)].n.sum()), "before_all": int(before.n.sum()),
                     "after_ppr": int(after[after.zone.isin(PPR)].n.sum()), "after_all": int(after.n.sum()),
                     "before_years": EFFECT_YEARS + 1, "after_years": w["post"][1] - a})
    e = pd.DataFrame(rows)
    if e.empty:
        return {"communes": 0}
    return {"communes": int(len(e)),
            "before_share": _share(e.before_ppr.sum(), e.before_all.sum()),
            "after_share": _share(e.after_ppr.sum(), e.after_all.sum()),
            "before_ppr": int(e.before_ppr.sum()), "after_ppr": int(e.after_ppr.sum()),
            "before_per_year": round(float((e.before_ppr / e.before_years).sum()), 1),
            "after_per_year": round(float((e.after_ppr / e.after_years).sum()), 1),
            "years": sorted(map(int, e.year.unique()))}


def municipalities(df: pd.DataFrame, w: dict, info: dict) -> pd.DataFrame:
    """One row per commune with buildings in a flood zone."""
    rows = []
    for insee, d in df.groupby("insee"):
        z = d[d.zone.isin(ZONED)]
        if z.n.sum() == 0:
            continue
        c = info.get(insee, {})
        ppr = z[z.zone.isin(PPR)]
        post = z[z.year > config.RD_YEAR]
        pre, pst = _in(d, w["pre"]), _in(d, w["post"])
        pre_z, pst_z = pre[pre.zone.isin(ZONED)], pst[pst.zone.isin(ZONED)]
        rows.append({
            "country": "FR", "insee": insee, "name": c.get("name") or insee, "dep": insee[:2],
            "ppr_year": c.get("first_approval"), "ppr_anticipated": bool(c.get("anticipated")),
            "pss_year": c.get("pss"), "first_ppr_year": c.get("first_ppr"),
            "ppr_digital": bool(c.get("digital")),
            "buildings": int(d.n.sum()), "zoned": int(z.n.sum()),
            **{f"zoned_{k}": int(z[z.zone == k].n.sum()) for k in ZONED},
            "after_ppr": int(ppr.after_map.sum()),
            "after_ppr_red": int(ppr[ppr.zone == "ppr_red"].after_map.sum()),
            "after_ppr_blue": int(ppr[ppr.zone == "ppr_blue"].after_map.sum()),
            "after_ppr_mixed": int(ppr.after_mixed.sum()),
            "after_ppr_dwellings": int(ppr.after_dwellings.sum()),
            # Today's red and blue zones, built after the commune's first PPRi (even a repealed one).
            "after_first_ppr": int(ppr[ppr.year > c["first_ppr"]].n.sum()) if c.get("first_ppr") else 0,
            "post": int(post.n.sum()),
            **{f"post_{k}": int(post[post.zone == k].n.sum()) for k in ZONED},
            "post_mixed": int(post.mixed.sum()), "post_dwellings": int(post.dwellings.sum()),
            "pre_per_year": round(pre_z.n.sum() / _span(w["pre"]), 2),
            "post_per_year": round(pst_z.n.sum() / _span(w["post"]), 2),
            "pre_share": round(100 * pre_z.n.sum() / pre.n.sum(), 1) if pre.n.sum() else None,
            "post_share": round(100 * pst_z.n.sum() / pst.n.sum(), 1) if pst.n.sum() else None,
            **{f"tri_{s}": int(d[d.tri == s].n.sum()) for s in ("for", "moy", "fai")},
            "unknown_year": int(z[z.year == 0].n.sum()),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["country", "insee", "name", "zoned", "after_ppr", "post"])
    out[["ppr_year", "pss_year", "first_ppr_year"]] = out[["ppr_year", "pss_year", "first_ppr_year"]].astype("Int64")
    return out.sort_values(["after_ppr", "post", "zoned"], ascending=False, ignore_index=True)


def annual(df: pd.DataFrame) -> pd.DataFrame:
    """Buildings per year of construction and class, all communes together."""
    d = df[df.year >= config.CHART_FROM]
    t = d.pivot_table(index="year", columns="zone", values="n", aggfunc="sum", fill_value=0)
    for z in ZONED + ["out"]:
        if z not in t:
            t[z] = 0
    a = d[d.zone.isin(PPR)].groupby("year").after_map.sum()
    return t[ZONED + ["out"]].assign(after_ppr=a).fillna(0).astype(int).reset_index()


def summary() -> dict:
    df, manifest = load()
    y = data_year(manifest)
    w = windows(y)
    info = communes_info(manifest)
    z = df[df.zone.isin(ZONED)]
    ppr = z[z.zone.isin(PPR)]
    post = z[z.year > config.RD_YEAR]
    munis = municipalities(df, w, info)
    flood_ppr = {k: c for k, c in info.items() if c.get("first_approval")}
    return {
        "country": "FR",
        "data_year": y, "windows": w,
        "departments": {k: {"name": m["name"], "millesime": m["millesime"], "ff_year": m["ff_year"],
                            "groups": m["groups"], "groups_with_year": m["groups_with_year"],
                            "no_tax_record_by_zone": m["no_tax_record_by_zone"],
                            "zones": m["zones_summary"], "zones_report": m["zones_report"]}
                        for k, m in manifest.items()},
        "buildings": int(df.n.sum()),
        "zoned": int(z.n.sum()),
        "zoned_by_zone": {k: int(z[z.zone == k].n.sum()) for k in ZONED},
        "after_ppr": int(ppr.after_map.sum()),
        "after_ppr_by_zone": {k: int(ppr[ppr.zone == k].after_map.sum()) for k in PPR},
        "after_ppr_res": int(ppr.after_res.sum()),
        "after_ppr_mixed": int(ppr.after_mixed.sum()),
        "after_ppr_dwellings": int(ppr.after_dwellings.sum()),
        "post": int(post.n.sum()),
        "post_by_zone": {k: int(post[post.zone == k].n.sum()) for k in ZONED},
        "post_mixed": int(post.mixed.sum()),
        "unknown_year": int(z[z.year == 0].n.sum()),
        "tri": {s: int(df[df.tri == s].n.sum()) for s in ("for", "moy", "fai")},
        "communes": len(info),
        "communes_flood_ppr": len(flood_ppr),
        "communes_digital": sum(1 for c in flood_ppr.values() if c.get("digital")),
        "communes_anticipated": sum(1 for c in flood_ppr.values() if c.get("anticipated")),
        "after_first_ppr": int(munis.after_first_ppr.sum()) if len(munis) else 0,
        "communes_revised": sum(1 for c in flood_ppr.values() if c.get("first_ppr") and c["first_ppr"] < c["first_approval"]),
        "communes_pss_only": sum(1 for c in info.values() if c.get("pss") and not c.get("first_approval")),
        "communes_zoned": int((munis.zoned > 0).sum()) if len(munis) else 0,
        "communes_after_ppr": int((munis.after_ppr > 0).sum()) if len(munis) else 0,
        "ppr_years": pd.Series([c["first_approval"] for c in flood_ppr.values()]).value_counts().sort_index()
                       .astype(int).to_dict() if flood_ppr else {},
        "periods": period_stats(df, w),
        "effect": ppr_effect(df, info, w),
        "_df": df, "_munis": munis, "_annual": annual(df), "_info": info,
    }
