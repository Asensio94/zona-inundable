"""Parameters of the flood-zone building count. Every number that shapes a published figure lives here."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"            # downloads (zone layers, ATOM feeds, boundaries); not committed
COUNTS = DATA / "counts"          # aggregated counts per cadastral municipality; committed
DOCS = ROOT / "docs"

SITE_URL = "https://asensio94.github.io/zona-inundable/"
REPO_URL = "https://github.com/Asensio94/zona-inundable"
USER_AGENT = "zona-inundable/0.1 (proyecto abierto de datos; https://github.com/Asensio94/zona-inundable)"

WORK_CRS = "EPSG:25830"

# --- Regions ----------------------------------------------------------------------------------
# Processed regions, by INE autonomous-community code. The pilot is the Comunitat Valenciana
# (the DANA of 29 October 2024); the rest of Spain follows by adding codes here.
REGIONS = {"10": "Comunitat Valenciana"}

# --- SNCZI flood zones (MITECO) -----------------------------------------------------------------
# GeoServer WFS of the National Flood Zone Mapping System. The shapefile downloads of the
# ministry's page sit behind an anti-bot challenge; the WFS is the documented machine route.
SNCZI_WFS = "https://gis.miteco.gob.es/geoserver/agua/wfs"
# Zone class -> (WFS layer, field holding the approval date). Classes are exclusive and the most
# restrictive wins: a building inside the preferential-flow zone is not counted again in T100.
ZONES = {
    "zfp": ("agua:ZI_Laminas_ZFP", "fecha"),
    "t100": ("agua:Zi_laminas_q100", "fecha_apro"),
    "t500": ("agua:Zi_laminas_q500", "fecha_apro"),
}
ZONE_ORDER = ["zfp", "t100", "t500"]
ZONE_LABELS = {
    "zfp": "Zona de flujo preferente",
    "t100": "Inundable con periodo de retorno de 100 años",
    "t500": "Inundable con periodo de retorno de 500 años",
    "out": "Fuera de zona inundable cartografiada",
}
WFS_PAGE = 200

# --- Catastro INSPIRE buildings ---------------------------------------------------------------
CATASTRO_ATOM = "https://www.catastro.hacienda.gob.es/INSPIRE/Buildings/{office}/ES.SDGC.BU.atom_{office}.xml"
# Navarre and the Basque Country keep their own cadastres, outside the national service.
FORAL_OFFICES = {"01", "20", "31", "48"}

# --- Boundaries ---------------------------------------------------------------------------------
ES_ATLAS_URL = "https://unpkg.com/es-atlas@0.6.0/es/municipalities.json"
INE_SAMPLE = 2000   # building points used to map a cadastral municipality to its INE code

# --- Periods ------------------------------------------------------------------------------------
# Royal Decree 638/2016 (BOE 29-12-2016) added articles 9 bis to 9 quater and 14 bis to the
# Public Hydraulic Domain Regulation: limits on new building in the preferential-flow zone and in
# the 100-year flood zone. Buildings finished from 2017 on are "after".
RD_YEAR = 2016
PRE_WINDOW = (2008, 2016)     # same length of years as the post window, more or less
BOOM_WINDOW = (2000, 2007)    # shown as a reference: the housing boom before the crash
# Catastro registers a new building months or years after it is finished. The last
# PROVISIONAL_YEARS years before the data year are shown but left out of the rates.
PROVISIONAL_YEARS = 2
CHART_FROM = 1960

# --- Reform signal ------------------------------------------------------------------------------
# dateOfConstruction has a beginning and an end. Catastro fills them with the oldest and newest
# year of the building's units; when they differ by more than this, part of the building is
# newer than the rest (an extension or an integral refurbishment recorded as a new date).
MIXED_YEARS = 1
