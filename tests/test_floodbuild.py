import io

import numpy as np
import pandas as pd
import shapely

from floodbuild import analysis, catastro, config, geo, signals, snczi, web

GML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"
  xmlns:bu-core2d="http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0"
  xmlns:bu-ext2d="http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0"
  xmlns:base="urn:x-inspire:specification:gmlas:BaseTypes:3.2">
{}
</gml:FeatureCollection>"""

BUILDING = """<gml:featureMember><bu-ext2d:Building gml:id="ES.SDGC.BU.{ref}">
  <bu-core2d:dateOfConstruction><bu-core2d:DateOfEvent>
    <bu-core2d:beginning>{begin}</bu-core2d:beginning><bu-core2d:end>{end}</bu-core2d:end>
  </bu-core2d:DateOfEvent></bu-core2d:dateOfConstruction>
  <base:localId>{ref}</base:localId>
  <gml:posList srsDimension="2">{x0} 0 {x1} 0 {x1} 10 {x0} 10 {x0} 0</gml:posList>
  <bu-ext2d:currentUse>{use}</bu-ext2d:currentUse>
  <bu-ext2d:numberOfDwellings>{dw}</bu-ext2d:numberOfDwellings>
</bu-ext2d:Building></gml:featureMember>"""


def _gml(rows):
    body = "".join(BUILDING.format(ref=f"REF{i:010d}", x0=x, x1=x + 10, **r) for i, (x, r) in enumerate(rows))
    return io.BytesIO(GML.format(body).encode("iso-8859-1"))


def _zoneset(zone, boxes, years):
    geoms = np.array([shapely.box(*b) for b in boxes], dtype=object)
    return snczi.ZoneSet(zone, np.array([f"{zone}{i}" for i in range(len(boxes))], dtype=object),
                         np.array(years), geoms, shapely.STRtree(geoms))


def test_year_handles_unknown():
    assert catastro._year("1998-01-01T00:00:00") == 1998
    assert catastro._year("--01-01") == 0
    assert catastro._year(None) == 0


def test_parse_keeps_no_reference():
    df = catastro.parse_buildings(_gml([
        (0, dict(begin="1970-01-01", end="2019-01-01", use="1_residential", dw=4)),
        (100, dict(begin="--01-01", end="--01-01", use="3_industrial", dw=0)),
    ]))
    assert list(df.year) == [2019, 0]
    assert list(df.begin) == [1970, 0]
    assert list(df.res) == [True, False]
    assert list(df.dwellings) == [4, 0]
    assert not any("REF" in str(v) for v in df.to_numpy().ravel())


def test_parse_reprojects_utm31():
    # Ondara, in the Marina Alta, comes in UTM zone 31; in zone 30 it lies around x 762 km.
    x, y = 241018, 4301615
    building = (f'<gml:featureMember><bu-ext2d:Building gml:id="ES.SDGC.BU.X">'
                f'<gml:Surface srsName="urn:ogc:def:crs:EPSG::25831"><gml:posList srsDimension="2">'
                f'{x} {y} {x + 10} {y} {x + 10} {y + 10} {x} {y + 10} {x} {y}</gml:posList></gml:Surface>'
                f'</bu-ext2d:Building></gml:featureMember>')
    df = catastro.parse_buildings(io.BytesIO(GML.format(building).encode("iso-8859-1")))
    assert 755_000 < df.x[0] < 770_000 and 4_290_000 < df.y[0] < 4_320_000


def test_classes_are_exclusive_and_strictest_wins():
    zs = {"zfp": _zoneset("zfp", [(0, 0, 20, 20)], [2011]),
          "t100": _zoneset("t100", [(0, 0, 120, 20)], [2020]),
          "t500": _zoneset("t500", [(0, 0, 220, 20)], [0])}
    df = pd.DataFrame({"x": [5, 105, 205, 305], "y": [5] * 4, "begin": [2018] * 4, "year": [2018] * 4,
                       "res": [True] * 4, "dwellings": [1] * 4})
    out = catastro.classify(df, zs)
    assert list(out.zone) == ["zfp", "t100", "t500", "out"]
    assert list(out.mapped) == [2011, 2020, 0, 0]


def test_counts_flags_mixed_and_after_map():
    df = pd.DataFrame({"zone": ["t100", "t100", "out"], "year": [2019, 2019, 2019], "begin": [1960, 2019, 2019],
                       "res": [True, False, True], "dwellings": [3, 0, 1], "mapped": [2011, 2020, 0]})
    c = catastro.counts(df).set_index(["zone", "year"])
    assert c.loc[("t100", 2019)].tolist() == [2, 1, 1, 3, 1]


def test_windows_leave_provisional_years_out():
    w = analysis.windows(2026)
    assert w["post"] == (config.RD_YEAR + 1, 2024)
    assert w["provisional"] == (2025, 2026)


def test_period_stats_share():
    df = pd.DataFrame({"zone": ["t100", "out", "t500", "out"], "year": [2010, 2010, 2020, 2020],
                       "n": [9, 81, 2, 98], "mixed": [0, 0, 1, 0]})
    p = analysis.period_stats(df, analysis.windows(2026))
    assert p["pre"]["share"] == 10.0
    assert p["post"]["share"] == 2.0
    assert p["post"]["zoned_clean"] == 1


def test_signal_has_contract_fields():
    m = {"ine": "46186", "name": "Paiporta", "post": 54, "post_zfp": 0, "post_t100": 0, "post_t500": 54,
         "post_mixed": 3, "zoned": 1212, "pre_per_year": 5.0, "post_per_year": 6.75}
    s = signals._signal(m, "2026-08-21", analysis.windows(2026))
    for k in ("id", "kind", "date", "title", "url", "precision"):
        assert s[k]
    assert s["kind"] == "flood_building" and s["precision"] == "municipio"
    assert s["municipalities"] == ["46186"] and s["url"].endswith("#m-46186")


def test_spanish_numbers():
    assert web._es(1500) == "1.500"
    assert web._es(0.15, 2) == "0,15"


def test_ine_code_prefers_name_over_ground():
    # es-atlas outlines are simplified: most of Mislata's buildings fall inside València's polygon.
    big, small = shapely.box(0, 0, 1000, 1000), shapely.box(900, 0, 1100, 100)
    munis = [geo.Municipality("46250", "València", "46", big), geo.Municipality("46169", "Mislata", "46", small)]
    tree = shapely.STRtree([m.geom for m in munis])
    df = pd.DataFrame({"x": [950] * 8 + [1050] * 2, "y": [50] * 10})
    assert catastro.ine_code(df, "MISLATA", munis, tree) == "46169"
    assert catastro.ine_code(df, "RAFAL", munis, tree) is None
    assert catastro._tokens("l'Alqueria de la Comtessa") == catastro._tokens("L ALQUERIA DE LA COMTESSA")


def test_name_score_spellings():
    assert catastro.name_score("PU OL", "Puçol") == 1.0                  # letter lost by the Catastro
    assert catastro.name_score("BENLLOCH", "Benlloc") == 1.0
    assert catastro.name_score("MONTCADA MONCADA", "Moncada") == 1.0
    assert catastro.name_score("ALCOCER DE PLANES", "Planes") == 0.0     # every Catastro word needs a partner
    assert catastro.name_score("RAFAL", "el Ràfol d'Almúnia") < 0.75


def test_yearly_averages_are_whole_buildings():
    assert web._al_anio(1754.0) == "1.754"
    assert web._al_anio(969.8) == "970"
    assert web._al_anio(0.4) == "0,4"
    assert web._al_anio(None) == "—"


def test_signals_gap_is_explained():
    m = pd.DataFrame({"ine": ["46186", "C03109", "46001"], "name": ["Paiporta", "Rafal", "Ademuz"],
                      "post": [54, 13, 0]})
    t = web._senales(m)
    assert "suman 54 edificios y no 67" in t and "Rafal (13)" in t and "código INE" in t
    assert "y no" not in web._senales(m[m.ine != "C03109"])


def test_page_explains_classes_and_pilot():
    assert "periodo de retorno" in web.PLANTILLA and "(ZFP)" in web.PLANTILLA
    assert "En España es un piloto" in web.PLANTILLA
