from types import SimpleNamespace

import numpy as np
import pandas as pd
import shapely

from floodbuild import config, i18n, signals
from floodbuild.fr import analysis as fra, bdnb, download, zones as frzones


def _gaspar(rows):
    cols = ["CODE MODELE", "CODE PROCEDURE", "CODE INSEE DEPARTEMENT", "CODE INSEE COMMUNE", "NOM COMMUNE",
            "LIBELLE RISQUE 1", "LIBELLE RISQUE 2", "LIBELLE RISQUE 3", "APPLIC_ANTIC", "APPROBATION",
            "LIBELLE ETAT", "LIBELLE SOUS-ETAT"]
    return pd.DataFrame(rows, columns=cols)


G = _gaspar([
    # approved PPRi
    ["PPRN-I", "P1", "11", "11001", "Alpha", "Inondation", None, None, None, "2005-03-01", "Opposable", "Approuvé"],
    # applied by anticipation before approval
    ["PPRN-I", "P2", "11", "11002", "Beta", "Inondation", None, None, "2023-08-31", None, "Opposable", "Anticipé"],
    # multirisk with flood, and one without
    ["PPRN-Multi", "P3", "11", "11003", "Gamma", "Mouvement de terrain", "Inondation", None, None, "2010-01-01", "Opposable", "Approuvé"],
    ["PPRN-Multi", "P4", "11", "11004", "Delta", "Séisme", None, None, None, "2010-01-01", "Opposable", "Approuvé"],
    # a plan des surfaces submersibles, and a first PPRi repealed by a revision
    ["PPRN-I", "P5", "11", "11005", "Epsilon", "Inondation", None, None, None, "1949-06-01", "Opposable", "Approuvé"],
    ["PPRN-I", "P6", "11", "11002", "Beta", "Inondation", None, None, "2001-02-01", "2004-01-01", "Caduque", "Abrogé"],
    # prescribed only
    ["PPRN-I", "P7", "11", "11006", "Zeta", "Inondation", None, None, None, None, "Prescrit", "Prescrit"],
])


def _square(x, y, s=10):
    return shapely.box(x, y, x + s, y + s)


def _fz():
    g = frzones.flood_procedures(G)
    zoning = pd.DataFrame({"proc": ["P1", "P1", "P2", "PX"], "typereg": ["03", "02", "04", "03"],
                           "hazard": ["oui", "oui", "oui", "oui"],
                           "geom": [_square(0, 0), _square(20, 0), _square(100, 0), _square(200, 0)]})
    atlas = pd.DataFrame({"cls": ["azi", "azi"], "id": ["a1", "a2"], "year": [2010, 2010],
                          "geom": [_square(0, 0, 40), _square(300, 0)]})
    scen = pd.DataFrame({"scenario": ["for", "fai"], "tri": ["T", "T"], "geom": [_square(0, 0, 5), _square(0, 0, 40)]})
    return frzones.build("11", g, zoning, atlas, scen)


def test_flood_procedures_and_anticipation():
    g = frzones.flood_procedures(G)
    assert set(g.proc) == {"P1", "P2", "P3", "P5", "P6", "P7"}       # P4 has no flood risk
    p2 = g[(g.proc == "P2")].iloc[0]
    assert p2.approved == 2023 and p2.anticipated
    assert g[g.proc == "P6"].iloc[0].approved == 2001                    # anticipated before approval
    assert g[g.proc == "P1"].iloc[0].approved == 2005 and not g[g.proc == "P1"].iloc[0].anticipated
    assert set(frzones.in_force(g).proc) == {"P1", "P2", "P3", "P5"}


def test_ppr_class():
    assert frzones.ppr_class("03", None) == "ppr_red"
    assert frzones.ppr_class("4", "non") == "ppr_red"
    assert frzones.ppr_class("02", None) == "ppr_blue"
    assert frzones.ppr_class("01", "oui") == "ppr_blue"
    assert frzones.ppr_class("01", "non") is None
    assert frzones.ppr_class(None, None) is None


def test_build_communes_and_report():
    fz = _fz()
    assert fz.report["ppr_not_in_force"] == ["PX"]
    assert fz.ppr_communes == {"11001", "11002"}
    beta = fz.communes["11002"]
    assert beta["first_approval"] == 2023 and beta["anticipated"] and beta["first_ppr"] == 2001
    eps = fz.communes["11005"]
    assert eps["first_approval"] is None and eps["pss"] == 1949 and not eps["digital"]
    assert "11005" in fz.report["communes_without_digital"]
    assert fz.communes["11006"]["prescribed"] == 1


def test_classify_points_azi_only_without_digital_ppr():
    fz = _fz()
    xy = np.array([[2, 2], [25, 5], [35, 5], [35, 5], [105, 5], [305, 5], [500, 5]], float)
    insee = np.array(["11001", "11001", "11001", "11009", "11002", "11009", "11009"])
    c = bdnb.classify_points(xy, insee, fz)
    # red; blue; AZI gated off in a commune with a digital PPR; AZI elsewhere; red (anticipated); AZI; out
    assert list(c.zone) == ["ppr_red", "ppr_blue", "out", "azi", "ppr_red", "azi", "out"]
    assert list(c.mapped[:2]) == [2005, 2005] and c.mapped[4] == 2023
    assert list(c.tri[:3]) == [1, 3, 3] and c.tri[6] == 0


def test_per_group_strictest_and_most_frequent_scenario():
    pts = pd.DataFrame({"group": ["g", "g", "h"], "zone": ["ppr_blue", "ppr_red", "out"],
                        "mapped": [2005, 2010, 0], "tri": [1, 3, 0]})
    out = bdnb.per_group(pts).set_index("group")
    assert out.loc["g", "zone"] == "ppr_red" and out.loc["g", "mapped"] == 2010 and out.loc["g", "tri"] == "for"
    assert out.loc["h", "zone"] == "out" and out.loc["h", "tri"] == ""


def test_apparent_reform():
    groups = pd.DataFrame({"group": ["a", "b", "c", "d"], "year": [2018, 2018, 2018, 2010]})
    rel = pd.DataFrame({"group": ["a", "b", "c", "d"], "parcel": ["p1", "p2", "p3", "p4"]})
    permits = pd.DataFrame({"parcel": ["p1", "p2", "p2", "p4"],
                            "nature": ["extension de surface sans transformation", "extension de surface sans transformation",
                                       bdnb.NEW, "extension de surface sans transformation"],
                            "filed": [2016, 2017, 2017, 2009]})
    # a: only an extension; b: also a new building; c: no permit; d: before Sitadel is complete
    assert list(bdnb.apparent_reform(groups, rel, permits)) == [True, False, False, False]


def test_counts_after_map():
    b = pd.DataFrame({"insee": ["1"] * 3, "zone": ["ppr_red"] * 3, "tri": [""] * 3, "year": [2004, 2006, 2006],
                      "mapped": [2005] * 3, "mixed": [False, True, False], "res": [True, True, False], "dwellings": [1, 2, 0]})
    c = bdnb.counts(b).set_index("year")
    assert c.loc[2006, "n"] == 2 and c.loc[2006, "after_map"] == 2 and c.loc[2004, "after_map"] == 0
    assert c.loc[2006, "after_mixed"] == 1 and c.loc[2006, "after_dwellings"] == 2


def test_polygon_rings_overlap_and_holes():
    outer = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]           # clockwise: shell
    hole = [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)]                # counter-clockwise: hole
    other = [(5, 5), (5, 15), (15, 15), (15, 5), (5, 5)]           # overlapping shell
    tiny = [(50, 50), (50, 50), (50, 50), (50, 50)]                # degenerate ring
    shp = SimpleNamespace(points=outer + hole + other + tiny, parts=[0, 5, 10, 15])   # what polygon() reads
    g = download.polygon(shp)
    zs = frzones._zoneset("ppr_red", ["P"], [2005], [g])
    assert len(zs.geoms) == 2 and all(shapely.is_valid(zs.geoms))
    inside, first = zs.hits(shapely.points([[3, 3], [7, 7], [12, 12], [50, 50]]))
    # the hole is outside; the overlap of both shells is inside (it would not be in the invalid whole)
    assert list(inside) == [False, True, True, False] and first[1] == 2005


def test_french_typography():
    assert i18n.n(46709, "fr") == "46 709" and i18n.n(1500, "fr") == "1 500"
    assert i18n.n(46709, "es") == "46.709"
    assert i18n.p(12.5, "fr") == "12,5 %" and i18n.p(None, "fr") == "—"
    assert i18n.d(1234.5, "fr") == "1 234,5"
    assert i18n.colon("fr") == " :" and i18n.colon("es") == ":"


def test_french_windows():
    w = fra.windows(2025)
    assert w["last"] == 2024 and w["provisional"] == (2024, 2024) and w["post"] == (config.RD_YEAR + 1, 2023)


def test_french_signal():
    m = {"insee": "2A004", "name": "Ajaccio", "after_ppr": 1500, "after_ppr_red": 500, "after_ppr_blue": 1000,
         "after_ppr_mixed": 3, "ppr_year": 2011, "ppr_anticipated": False, "first_ppr_year": pd.NA,
         "after_first_ppr": 0, "zoned": 4000, "post": 200, "pre_per_year": 1.5, "post_per_year": 2.0}
    s = signals._signal_fr(m, "2025-01-01", fra.windows(2025))
    assert s["country"] == "FR" and s["id"] == "FB-FR-2A004" and s["municipalities"] == ["2A004"]
    assert s["title"].startswith("Ajaccio : 1 500 bâtiments")
    assert s["url"].endswith("/fr/#m-2A004") and s["details"]["anio_primer_ppr"] is None
