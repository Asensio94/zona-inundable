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

# === France ======================================================================================
# The same count for France: buildings of the BDNB inside the regulatory zoning of the flood risk
# prevention plans (PPRi), by commune and year. France is one more country of the same project; the
# Spanish settings above do not change. Codes are INSEE commune codes (5 characters, e.g. 2A004).
FR_WORK_CRS = "EPSG:2154"          # Lambert 93: every French source comes in it or is asked in it
FR_SITE_URL = SITE_URL + "fr/"

# Processed departments. The pilot is the Aude (the floods of 15 October 2018 in the Aude valley).
# Each one needs the DDTM's digital PPR zoning (a COVADIS-like shapefile published in the
# ministry's geo-ide ATOM service) and the hydrogeomorphological flood atlas (AZI) of its region.
FR_DEPARTMENTS = {
    "11": {
        "name": "Aude",
        "ppr_zoning": "https://atom.geo-ide.developpement-durable.gouv.fr/atomArchive/GetResource"
                      "?id=0c52b76b-401c-4051-9817-63fe9fb4b6e1&dataType=dataset",
        # AZI Languedoc-Roussillon (DREAL Occitanie), Picto-Occitanie data API, asked in Lambert 93.
        "azi": "https://catalogue.picto-occitanie.fr/api/data/837040f2-eb01-4944-818d-7f7431896148?srs=EPSG:2154",
    },
}

# --- Géorisques ---------------------------------------------------------------------------------
# GASPAR, the state's register of risk-prevention procedures: one row per procedure and commune,
# with prescription, approval and repeal dates. Bulk file, refreshed every week.
GASPAR_URL = "https://files.georisques.fr/GASPAR/gaspar.zip"
# Flood PPR models. A multi-risk PPR counts when one of its risks is flooding.
FR_FLOOD_MODELS = {"PPRN-I", "PPRN-L"}
FR_MULTI_MODEL = "PPRN-Multi"
FR_FLOOD_RISK = "Inondation"
# Floods Directive: maps of the territories at significant flood risk (TRI), 2020 cycle.
TRI_URL = "https://files.georisques.fr/di_2020/tri_2020_sig_di_{dep}.zip"
TRI_SCENARIOS = {"01": "for", "02": "moy", "03": "moy", "04": "fai"}   # frequent, medium (and its climate-change variant), extreme

# --- Zone classes -------------------------------------------------------------------------------
# Exclusive, the most restrictive wins. The PPR's regulatory zoning is the binding map; the AZI is
# a hazard atlas with no legal force, used only where a commune has no digital PPR zoning.
FR_ZONE_ORDER = ["ppr_red", "ppr_blue", "azi", "azi_exc"]
# COVADIS code of the regulation type of a PPR zone (TYPEREG) -> class.
# 03 interdiction, 04 strict interdiction, 08 "secteur non ou peu urbanisé" (inconstructible in the
# Aude's rules) -> red; 02 prescriptions -> blue. 01 ("autre") is blue only when the zone is subject
# to a hazard (SOUMISALEA); otherwise, and for any other code, the zone is left out and reported.
FR_TYPEREG = {"03": "ppr_red", "04": "ppr_red", "08": "ppr_red", "02": "ppr_blue"}
FR_TYPEREG_HAZARD = {"01": "ppr_blue"}
# AZI geomorphological units: the river beds a flood fills, and the exceptional major bed apart.
FR_AZI_UNITS = {"lit mineur": "azi", "lit moyen": "azi", "lit majeur": "azi", "lit majeur exceptionnel": "azi_exc"}
FR_ZONE_LABELS = {
    "ppr_red": "Zone rouge du PPRi (inconstructible)",
    "ppr_blue": "Zone bleue du PPRi (constructible sous conditions)",
    "azi": "Lit mineur, moyen ou majeur de l'atlas des zones inondables, sans PPRi numérique",
    "azi_exc": "Lit majeur exceptionnel de l'atlas des zones inondables, sans PPRi numérique",
    "out": "Hors zone inondable cartographiée",
}

# --- BDNB ---------------------------------------------------------------------------------------
# Base de données nationale des bâtiments (CSTB), open edition, one zip per department. The
# millesime in use is read from data.gouv.fr; this one is the fallback.
BDNB_DATASET_API = "https://www.data.gouv.fr/api/1/datasets/base-de-donnees-nationale-des-batiments/"
BDNB_MILLESIME = "2026-02-a"
BDNB_URL = ("https://open-data.s3.fr-par.scw.cloud/bdnb_millesime_{m}/millesime_{m}_dep{dep}/"
            "open_data_millesime_{m}_dep{dep}_csv.zip")

# --- Periods ------------------------------------------------------------------------------------
# The French milestone is each PPR's own approval date (Loi Barnier, 2 February 1995, created the
# PPR): a building counts as "after" when its year is later than the approval year of the PPR that
# zones it. The Spanish windows are kept as well, so both countries can be read side by side.
BARNIER_YEAR = 1995
# The year of construction comes from the Fichiers fonciers (DGFiP land tax files) of 1 January of
# the millesime's year: the year before it is the last one observed, and still incomplete (new
# buildings reach the tax files with the owner's declaration, months after completion).
FR_PROVISIONAL_YEARS = 1
# Sitadel (building permits) is complete from 2013 on in the BDNB. A building dated Y whose parcels
# had only extension or transformation permits filed in Y-3..Y, and no new-construction permit,
# is marked as an apparent reform.
SITADEL_FROM = 2013
SITADEL_LOOKBACK = 3
