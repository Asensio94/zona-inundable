"""From saved counts to the published figures: per municipality, per year and before/after 2016."""
from __future__ import annotations

import pandas as pd

from . import catastro, config, geo

ZONED = ["zfp", "t100", "t500"]


def key(code: str, m: dict) -> str:
    """INE code of a cadastral municipality, or «C» + its Catastro code when es-atlas lacks it."""
    return m.get("ine") or f"C{code}"


def _pretty(name: str) -> str:
    """«L ALQUERIA D ASNAR» → «l'Alqueria d'Asnar», for municipalities known only by their Catastro name."""
    words = name.title().split()
    out = []
    for w in words:
        if w in ("L", "D"):
            out.append(w.lower() + "'")
        elif w in ("De", "La", "El", "Les", "Els", "Del"):
            out.append(w.lower() + " ")
        else:
            out.append(w + " ")
    return "".join(out).strip()


def load() -> tuple[pd.DataFrame, dict]:
    """All saved counts with their INE code: one row per cadastral municipality, zone and year."""
    manifest = catastro.load_manifest()
    frames = []
    for code, m in manifest.items():
        path = config.COUNTS / m["office"] / f"{code}.csv"
        if not path.exists() or geo.PROVINCE_CCAA.get(m["office"]) not in config.REGIONS:
            continue
        frames.append(pd.read_csv(path).assign(code=code, ine=key(code, m)))
    cols = ["zone", "year", "n", "mixed", "res", "dwellings", "after_map", "code", "ine"]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
    return df, manifest


def data_year(manifest: dict) -> int:
    """Year of the Catastro extract: the latest update date of the municipalities counted."""
    years = [int(m["updated"][:4]) for m in manifest.values() if m.get("updated", "")[:4].isdigit()]
    return max(years) if years else pd.Timestamp.now().year


def windows(year: int) -> dict:
    post_end = year - config.PROVISIONAL_YEARS
    return {"pre": config.PRE_WINDOW, "post": (config.RD_YEAR + 1, post_end), "boom": config.BOOM_WINDOW,
            "provisional": (post_end + 1, year)}


def _in(df: pd.DataFrame, w: tuple[int, int]) -> pd.DataFrame:
    return df[(df.year >= w[0]) & (df.year <= w[1])]


def _span(w: tuple[int, int]) -> int:
    return w[1] - w[0] + 1


def period_stats(df: pd.DataFrame, w: dict) -> dict:
    """Buildings per year in flood zones before and after, and their share of all new buildings."""
    out = {}
    for k in ("boom", "pre", "post"):
        d = _in(df, w[k])
        z = d[d.zone.isin(ZONED)]
        r = d[d.zone.isin(["zfp", "t100"])]
        out[k] = {
            "years": list(w[k]),
            "zoned": int(z.n.sum()),
            "restricted": int(r.n.sum()),
            "all": int(d.n.sum()),
            "per_year": round(z.n.sum() / _span(w[k]), 1),
            "restricted_per_year": round(r.n.sum() / _span(w[k]), 1),
            "share": round(100 * z.n.sum() / d.n.sum(), 2) if d.n.sum() else None,
            "restricted_share": round(100 * r.n.sum() / d.n.sum(), 2) if d.n.sum() else None,
            # Same figures without the buildings whose units have different years (reform signal).
            "zoned_clean": int((z.n - z.mixed).sum()),
            "all_clean": int((d.n - d.mixed).sum()),
            "by_zone": {zz: int(d[d.zone == zz].n.sum()) for zz in ZONED},
        }
        o = out[k]
        o["share_clean"] = round(100 * o["zoned_clean"] / o["all_clean"], 2) if o["all_clean"] else None
    return out


def municipalities(df: pd.DataFrame, w: dict) -> pd.DataFrame:
    """One row per INE municipality with buildings in flood zones."""
    names = {key(c, m): _pretty(m["name"]) for c, m in catastro.load_manifest().items()}
    names.update({m.ine: m.name for m in geo.municipalities(tuple(config.REGIONS))})
    rows = []
    for ine, d in df.groupby("ine"):
        z = d[d.zone.isin(ZONED)]
        if z.n.sum() == 0:
            continue
        post_all = d[d.year > config.RD_YEAR]
        post = post_all[post_all.zone.isin(ZONED)]
        pre, pst = _in(d, w["pre"]), _in(d, w["post"])
        pre_z, pst_z = pre[pre.zone.isin(ZONED)], pst[pst.zone.isin(ZONED)]
        rows.append({
            "ine": ine, "name": names.get(ine, ine), "province": ine.lstrip("C")[:2],
            "province_name": geo.PROVINCE_NAMES.get(ine.lstrip("C")[:2], ""),
            "buildings": int(d.n.sum()),
            "zoned": int(z.n.sum()),
            **{f"zoned_{k}": int(z[z.zone == k].n.sum()) for k in ZONED},
            "post": int(post.n.sum()),
            **{f"post_{k}": int(post[post.zone == k].n.sum()) for k in ZONED},
            "post_mixed": int(post.mixed.sum()),
            "post_after_map": int(post.after_map.sum()),
            "post_dwellings": int(post.dwellings.sum()),
            "pre_per_year": round(pre_z.n.sum() / _span(w["pre"]), 2),
            "post_per_year": round(pst_z.n.sum() / _span(w["post"]), 2),
            "pre_share": round(100 * pre_z.n.sum() / pre.n.sum(), 1) if pre.n.sum() else None,
            "post_share": round(100 * pst_z.n.sum() / pst.n.sum(), 1) if pst.n.sum() else None,
            "unknown_year": int(z[z.year == 0].n.sum()),
        })
    cols = ["ine", "name", "province", "province_name", "buildings", "zoned", "post"]
    out = pd.DataFrame(rows)
    return out.sort_values(["post", "zoned"], ascending=False, ignore_index=True) if len(out) else pd.DataFrame(columns=cols)


def annual(df: pd.DataFrame) -> pd.DataFrame:
    """Buildings per year of construction and zone class, all counted municipalities together."""
    d = df[df.year >= config.CHART_FROM]
    t = d.pivot_table(index="year", columns="zone", values="n", aggfunc="sum", fill_value=0)
    m = d[d.zone.isin(ZONED)].groupby("year").mixed.sum()
    for z in ZONED + ["out"]:
        if z not in t:
            t[z] = 0
    return t[ZONED + ["out"]].assign(mixed=m).fillna(0).astype(int).reset_index()


def summary() -> dict:
    df, manifest = load()
    y = data_year(manifest)
    w = windows(y)
    z = df[df.zone.isin(ZONED)]
    post = z[z.year > config.RD_YEAR]
    munis = municipalities(df, w)
    counted = [m for m in manifest.values() if geo.PROVINCE_CCAA.get(m["office"]) in config.REGIONS]
    return {
        "data_year": y,
        "windows": w,
        "catastro_dates": sorted({m["updated"] for m in counted}),
        "cadastral_municipalities": len(counted),
        "zoned": int(z.n.sum()),
        "zoned_by_zone": {k: int(z[z.zone == k].n.sum()) for k in ZONED},
        "post": int(post.n.sum()),
        "post_by_zone": {k: int(post[post.zone == k].n.sum()) for k in ZONED},
        "post_mixed": int(post.mixed.sum()),
        "post_after_map": int(post.after_map.sum()),
        "post_dwellings": int(post.dwellings.sum()),
        "zoned_mixed": int(z.mixed.sum()),
        "unknown_year": int(z[z.year == 0].n.sum()),
        "municipalities_zoned": int((munis.zoned > 0).sum()) if len(munis) else 0,
        "municipalities_post": int((munis.post > 0).sum()) if len(munis) else 0,
        "periods": period_stats(df, w),
        "_df": df, "_munis": munis, "_annual": annual(df),
    }
