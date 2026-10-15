"""docs/fr/index.html: buildings in flood zones in France, by year and commune, before and after each PPRi.

The page is in French; the numbers go through i18n (narrow no-break space as thousands separator
and before «%»). The data files next to it (communes.csv, annual.csv, summary.json) are the same
for any language.
"""
from __future__ import annotations

import json

import pandas as pd
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .. import config, i18n
from ..logo import LOGO_SVG, favicon_link
from ..web import ACCENT, ACCENT_DARK, COMMON_CSS
from . import analysis

L = "fr"
OUT = config.DOCS / "fr"


def _n(v) -> str:
    return "—" if v is None else i18n.n(v, L)


def _d(v, nd: int = 1) -> str:
    return "—" if v is None else i18n.d(v, L, nd)


def _p(v, nd: int = 1) -> str:
    return i18n.p(v, L, nd)


def _span(w) -> str:
    return str(w[0]) if w[0] == w[1] else f"{w[0]}–{w[1]}"


def _years(ys: list[int]) -> str:
    return " et ".join(", ".join(map(str, ys[:-1])).split(" et ") + [str(ys[-1])]) if len(ys) > 1 else str(ys[0])


def _pl(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# --- Page pieces -------------------------------------------------------------------------------

def _parametres(s: dict) -> str:
    w = s["windows"]
    rows = []
    for dep, d in s["departments"].items():
        z, rep = d["zones"], d["zones_report"]
        rows += [
            (f"Zonage réglementaire ({d['name']})",
             f"PPR de la DDTM, {_n(rep['ppr_procedures'])} procédures, {_n(rep['ppr_features'])} zones ; "
             f"en vigueur et classées : {_n(z['ppr_red']['procedures'])} PPR avec zone rouge, "
             f"{_n(z['ppr_blue']['procedures'])} avec zone bleue, approuvés ou appliqués par anticipation de {z['ppr_red']['first_year']} à {z['ppr_red']['last_year']}"),
            ("Atlas des zones inondables", f"AZI Languedoc-Roussillon (DREAL), études de {z['azi']['first_year']} à "
                                           f"{z['azi']['last_year']} ; {_n(z['azi']['n'] + z['azi_exc']['n'])} polygones"),
            ("TRI", f"cartes de la directive Inondation, cycle 2020 : {', '.join(t.replace('FRD_TRI_', '').title() for t in z['tri']['tri'])}"),
            ("Bâtiments", f"BDNB, millésime {d['millesime']}, Fichiers fonciers {d['ff_year']} ; "
                          f"{_n(d['groups_with_year'])} bâtiments avec une fiche fiscale sur {_n(d['groups'])}"),
        ]
    rows += [
        ("Année", "année de construction des Fichiers fonciers (DGFiP), champ annee_construction de la BDNB"),
        ("Dedans ou dehors", "un point intérieur de chaque emprise ; un bâtiment de plusieurs emprises prend la classe la plus stricte"),
        ("Classe", "exclusive, de la plus stricte à la moins stricte : zone rouge, zone bleue, AZI (lit mineur, moyen, majeur), "
                   "AZI lit majeur exceptionnel ; l'AZI ne compte que dans les communes sans PPR numérique"),
        ("Rouge", "TYPEREG 03 (interdiction), 04 (interdiction stricte) et 08 (secteur non ou peu urbanisé, inconstructible)"),
        ("Bleue", "TYPEREG 02 (prescriptions), et 01 lorsque la zone est soumise à l'aléa"),
        ("Après le PPRi", "année du bâtiment postérieure à celle où le PPRi est devenu opposable : approbation, "
                          "ou application anticipée si elle a précédé"),
        ("Après le premier PPRi", "même zonage d'aujourd'hui, mais année postérieure au premier PPRi de la commune, "
                                  "même s'il a été abrogé et remplacé depuis par une révision"),
        ("Avant / après (comme en Espagne)", f"{_span(w['pre'])} et {_span(w['post'])}"),
        ("Provisoires", f"{_span(w['provisional'])} : la construction neuve entre dans les Fichiers fonciers avec "
                        "retard ; affichées, mais hors des comparaisons"),
        ("Réforme apparente", f"bâtiment daté Y dont les parcelles n'ont eu, de Y−{config.SITADEL_LOOKBACK} à Y, que des permis "
                              f"d'extension ou de transformation (Sitadel), à partir de {config.SITADEL_FROM + config.SITADEL_LOOKBACK}"),
        ("Commune", "code INSEE (5 caractères) de la commune du bâtiment dans la BDNB"),
    ]
    return '<table class="params">' + "".join(
        f"<tr><th>{escape(a)}</th><td>{escape(b.replace(' :', chr(0xa0) + ':').replace(' ;', chr(0xa0) + ';'))}</td></tr>"
        for a, b in rows) + "</table>"


def _periodes(p: dict) -> str:
    rows = []
    for k, name in (("boom", "Avant la crise"), ("pre", "Avant"), ("post", "Après")):
        d = p[k]
        rows.append(f"<tr><th>{name} <span class='data'>{_span(d['years'])}</span></th>"
                    f"<td class='num'>{_d(d['per_year'])}</td><td class='num'>{_p(d['share'], 2)}</td>"
                    f"<td class='num'>{_d(d['ppr_per_year'])}</td><td class='num'>{_p(d['ppr_share'], 2)}</td>"
                    f"<td class='num'>{_p(d['share_clean'], 2)}</td></tr>")
    return ('<div class="tabla"><table class="params periodos"><tr><th>Période</th><th class="num">En zone inondable, par an</th>'
            '<th class="num">Part de la construction neuve</th><th class="num">En zone rouge ou bleue, par an</th>'
            '<th class="num">Part de la construction neuve</th><th class="num">Part, sans réformes apparentes</th></tr>'
            + "".join(rows) + "</table></div>")


def _effet(s: dict) -> str:
    e = s["effect"]
    if not e.get("communes"):
        return "<p>Pas encore assez de communes avec un PPRi numérique ancien pour comparer.</p>"
    return (f"<p>Dans les <b>{_n(e['communes'])}</b> communes dont le PPRi numérique est opposable depuis au moins trois ans "
            f"complets (plans de {_years(e['years'])}), la part de la construction neuve qui s'est faite dans ce qui est "
            f"aujourd'hui zone rouge ou bleue passe de <b>{_p(e['before_share'], 2)}</b> pendant les "
            f"{analysis.EFFECT_YEARS + 1} années qui précèdent le plan à <b>{_p(e['after_share'], 2)}</b> après lui. "
            f"En nombre : {_n(e['before_ppr'])} bâtiments avant, {_n(e['after_ppr'])} après "
            f"({_d(e['before_per_year'])} et {_d(e['after_per_year'])} par an).</p>"
            "<p>Le zonage est celui d'aujourd'hui : avant le plan, ces terrains n'étaient pas encore réglementés. "
            "La comparaison dit combien on construisait là où le plan allait interdire ou encadrer, et combien on y "
            "construit depuis.</p>").replace(" :", " :")


def _contraste(munis, info: dict) -> str:
    out = []
    for insee in ("11397", "11425"):
        c = info.get(insee, {})
        r = munis[munis.insee == insee] if len(munis) else munis
        name = c.get("name") or insee
        if not len(r):
            out.append(f"<li><b>{escape(name)}</b> : pas de bâtiment en zone inondable cartographiée.</li>")
            continue
        r = r.iloc[0]
        first = (f"premier PPRi en {r.first_ppr_year}" if pd.notna(r.first_ppr_year) else "pas de PPRi avant la crue")
        now = (f"PPRi révisé {'appliqué par anticipation' if r.ppr_anticipated else 'approuvé'} en {r.ppr_year}"
               if pd.notna(r.ppr_year) else "aucun PPRi opposable")
        out.append(f"<li><b>{escape(name)}</b> ({first} ; {now}) : {_n(r.zoned)} bâtiments dans les zones rouge et bleue "
                   f"du plan actuel, dont {_n(r.zoned_ppr_red)} en rouge. <b>{_n(r.after_first_ppr)}</b> d'entre eux "
                   f"datent d'après le premier PPRi.</li>")
    return "<ul>" + "".join(out).replace(" :", " :").replace(" ;", " ;") + "</ul>"


def _hors(s: dict, info: dict) -> str:
    items = []
    for dep, d in s["departments"].items():
        rep = d["zones_report"]
        without = [info.get(i, {}).get("name") or i for i in rep["communes_without_digital"]]
        nf = sum(d["no_tax_record_by_zone"].get(z, 0) for z in analysis.ZONED)
        items += [
            f"<li><b>Plans sans zonage numérique.</b> {_n(len(without))} {_pl(len(without), 'commune', 'communes')} ont un plan "
            f"inondation opposable dont la DDTM ne publie pas le zonage en données : {_n(len(rep.get('communes_pss_only', [])))} "
            "n'ont qu'un plan des surfaces submersibles de 1948–1960 (il vaut PPR en droit, mais précède la loi Barnier), "
            "les autres un PPR sans couche publiée, comme le PPR littoral de Fitou. Ce sont " + escape(", ".join(sorted(without))) +
            ". Là, seul l'atlas compte, comme si le plan n'existait pas.</li>",
            f"<li><b>Plans pas encore opposables.</b> {_n(len(rep['ppr_not_in_force']))} procédures du fichier de zonage "
            f"({_n(rep['ppr_features_not_in_force'])} zones) sont seulement prescrites, ou absentes de GASPAR : elles ne "
            "réglementent encore rien et ne sont pas comptées.</li>",
            f"<li><b>Zones sans règle reconnue.</b> {_n(rep['ppr_features_unclassified'])} zones de type « autre » "
            "sans aléa ne sont ni rouges ni bleues.</li>",
            f"<li><b>Bâtiments sans fiche fiscale.</b> {_n(d['groups'] - d['groups_with_year'])} bâtiments de la BDNB "
            f"n'ont pas de ligne dans les Fichiers fonciers, dont {_n(nf)} en zone inondable : bâtiments publics non "
            "imposés, annexes, constructions trop récentes. Sans année, ils ne peuvent pas être datés.</li>",
        ]
    items.append("<li><b>Le TRI ne classe rien.</b> Les cartes des territoires à risque important (Carcassonne, Narbonne) "
                 "décrivent l'aléa sans réglementer ; elles servent de contraste (colonnes « TRI » du fichier des communes).</li>")
    return "<ul>" + "".join(items).replace(" :", " :") + "</ul>"


PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__FAVICON__
<title>Construire en zone inondable</title>
<meta name="description" content="Combien de bâtiments ont été construits chaque année dans les zones inondables réglementées par les PPRi, commune par commune, et combien après l'entrée en vigueur du plan.">
<link rel="alternate" hreflang="es" href="../">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
__COMMON_CSS__
:root{--accent:__ACCENT__;--accent-dark:__ACCENT_DARK__}
:root{--ppr_red:#a33a32;--ppr_blue:#3e6797;--azi:#a7b8cc;--azi_exc:#d5dde6;--prov:#dad2cb}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){--ppr_red:#e08a80;--ppr_blue:#8fb2dc;--azi:#5a6b80;--azi_exc:#3a4554;--prov:#362d28}
}
:root[data-theme="dark"]{--ppr_red:#e08a80;--ppr_blue:#8fb2dc;--azi:#5a6b80;--azi_exc:#3a4554;--prov:#362d28}
.marca{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.marca .label{color:var(--muted);font-size:14px}
.bloque{max-width:1440px;margin:0 auto;padding:24px 16px 0}
.bloque > h2{margin:0 0 8px;font:700 28px/1 var(--font-title);text-transform:uppercase;letter-spacing:.03em}
.bloque > p{max-width:72ch;margin:0 0 10px}
.dos{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:24px;align-items:start}
.controles{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:6px 0 10px;font-size:14px;color:var(--muted)}
.controles select,.controles input{font:14px var(--font-text);background:var(--paper);color:var(--ink);border:1px solid var(--line);padding:4px 6px}
.grafica svg{display:block;width:100%;height:auto;overflow:visible}
.grafica .eje{stroke:var(--line)} .grafica text{font:11px var(--font-data);fill:var(--muted)}
.grafica .rd{stroke:var(--ink);stroke-width:1.2;stroke-dasharray:3 3}
.grafica .rd-n{font:600 12px var(--font-title);fill:var(--ink);letter-spacing:.04em}
.leyenda{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--muted);align-items:center;margin-top:6px}
.leyenda i{display:inline-block;width:14px;height:10px;margin-right:4px;vertical-align:-1px}
ol.top{margin:0;padding:0;list-style:none;display:grid;gap:6px}
ol.top li{display:grid;grid-template-columns:1.6em 1fr auto;gap:8px;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:5px}
ol.top b{font-family:var(--font-data);color:var(--accent);font-variant-numeric:tabular-nums}
ol.top .n{color:var(--muted);font-family:var(--font-data);font-size:13px}
.tabla{overflow-x:auto;background:var(--paper);border:1px solid var(--line)}
table.munis{border-collapse:collapse;width:100%;font-size:14px}
table.munis th,table.munis td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
table.munis th{font:600 13px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.05em;cursor:pointer;position:sticky;top:0;background:var(--paper);vertical-align:bottom;white-space:normal;min-width:5em}
table.munis th[aria-sort]::after{content:" ↓";color:var(--accent)}
table.munis th[aria-sort="ascending"]::after{content:" ↑"}
table.munis td.num,table.munis th.num{text-align:right;font-family:var(--font-data);font-variant-numeric:tabular-nums}
table.munis tr:target td{background:color-mix(in srgb,var(--accent) 16%,var(--paper))}
table.munis td.nom{white-space:normal;min-width:10em}
table.periodos th{white-space:normal}
.method{border-top:1.5px solid var(--ink);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;margin-top:28px}
.method p{margin:0 0 10px} .method ol,.method ul{margin:0 0 10px;padding-left:1.4em} .method li{margin-bottom:8px}
.method > div > h3:first-child{margin-top:0}
.method table.params th{white-space:normal;width:30%}
table.compare{border-collapse:collapse;width:100%;font-size:14px;margin:0 0 12px}
table.compare th,table.compare td{border-bottom:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
table.compare thead th{font:600 13px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.05em}
.aviso{border-left:3px solid var(--accent);padding:2px 0 2px 12px}
.idioma{font-size:14px}
.site-footer p{margin:0}
@media (max-width:900px){.dos,.method{grid-template-columns:minmax(0,1fr)}}
</style>
</head>
<body>
<header class="site-header">
  <div class="marca">
    <h1>__LOGO__Construire en <span>zone inondable</span></h1>
    <span class="label">__REGION__ · PPRi, Géorisques et BDNB · mis à jour chaque mois</span>
    <a class="idioma" href="../" hreflang="es" lang="es">__OTHER__</a>
  </div>
  <p class="lede">Combien de bâtiments se sont construits dans les zones inondables réglementées, année après année et commune par commune, et combien après l'entrée en vigueur du plan de prévention du risque inondation (PPRi) qui les interdit ou les encadre. Avec le zonage des PPRi publié par l'État et l'année de construction des Fichiers fonciers.</p>
  <div class="figures">
    <div><b>__ZONED__</b><span>bâtiments en zone inondable</span></div>
    <div><b>__AFTER__</b><span>en zone rouge ou bleue, datés d'après leur PPRi</span></div>
    <div><b>__NAFTER__</b><span>communes concernées</span></div>
    <div><b>__EFFECT__</b><span>de la construction neuve en zone rouge ou bleue, avant → après le PPRi</span></div>
  </div>
</header>

<section class="bloque" id="annees">
  <h2>Année par année</h2>
  <div class="dos">
    <div>
      <div class="controles">
        <label>Depuis <select id="f-desde"><option value="1960">1960</option><option value="1990" selected>1990</option><option value="2000">2000</option></select></label>
        <label><input type="checkbox" id="f-cuota"> Voir la part de la construction neuve en zone inondable</label>
      </div>
      <figure class="grafica" style="margin:0"><div id="grafica"></div>
        <figcaption class="leyenda" id="leyenda"></figcaption></figure>
      <p class="note">Bâtiments par année de construction selon les Fichiers fonciers, dans les communes du département. L'année __PROV__ ressort plus basse parce que les constructions achevées n'ont pas encore toutes été déclarées : elle est provisoire. Les PPRi de l'Aude sont devenus opposables entre __PPRFIRST__ et __PPRLAST__, chacun à sa date.</p>
    </div>
    <div>
      <h3 class="label">Avant et après chaque PPRi</h3>
      __EFFET__
      <h3 class="label">Les mêmes périodes qu'en Espagne</h3>
      __PERIODES__
      <p class="note">« Part de la construction neuve » : bâtiments en zone inondable parmi tous ceux construits ces années-là dans les mêmes communes. Elle corrige le cycle de la construction, qui s'est effondrée après 2008.</p>
    </div>
  </div>
</section>

<section class="bloque" id="communes">
  <h2>Par commune</h2>
  <div class="dos">
    <div>
      <p>Communes qui comptent le plus de bâtiments en zone rouge ou bleue datés d'après l'entrée en vigueur de leur PPRi. Cliquez sur un nom pour voir sa ligne.</p>
      <ol class="top" id="top"></ol>
    </div>
    <div>
      <p class="aviso">Un bâtiment en zone rouge daté d'après le plan n'est pas en soi une infraction. Le règlement de chaque PPRi admet, même en zone rouge, des extensions limitées, des reconstructions, des bâtiments agricoles ou des équipements publics ; en zone bleue il fixe des conditions (premier plancher au-dessus des plus hautes eaux, par exemple), pas des interdictions. Et l'année des Fichiers fonciers peut être celle d'une transformation. Ce sont des indices pour poser des questions, pas des verdicts.</p>
    </div>
  </div>
  <div class="controles">
    <label>Chercher <input type="search" id="f-busca" placeholder="commune"></label>
    <label><input type="checkbox" id="f-ppr"> Seulement les communes avec PPRi numérique</label>
    <span id="cuenta"></span>
  </div>
  <div class="tabla"><table class="munis" id="tabla"><thead><tr>
    <th data-k="name">Commune</th>
    <th data-k="first_ppr_year" class="num">Premier PPRi</th>
    <th data-k="ppr_year" class="num">PPRi en vigueur depuis</th>
    <th data-k="zoned" class="num">En zone inondable</th>
    <th data-k="zoned_ppr_red" class="num">Zone rouge</th>
    <th data-k="zoned_ppr_blue" class="num">Zone bleue</th>
    <th data-k="zoned_azi_all" class="num">Atlas (sans PPRi numérique)</th>
    <th data-k="after_ppr" class="num" aria-sort="descending">Après le PPRi</th>
    <th data-k="after_ppr_red" class="num">dont zone rouge</th>
    <th data-k="after_ppr_mixed" class="num">dont réforme apparente</th>
    <th data-k="after_first_ppr" class="num">Après le premier PPRi</th>
    <th data-k="post" class="num">Depuis __POSTFROM__, toute zone</th>
    <th data-k="pre_share" class="num">Part de la construction neuve __PRE__</th>
    <th data-k="post_share" class="num">Part de la construction neuve __POSTW__</th>
  </tr></thead><tbody></tbody></table></div>
  <p class="note">Des bâtiments, pas des logements : un immeuble compte pour un. « a » après l'année : PPRi appliqué par anticipation, avant son approbation. « PSS » : seulement un plan des surfaces submersibles, antérieur à la loi Barnier. « * » : plan sans zonage numérique. Les communes sans bâtiment en zone inondable ne sont pas listées.</p>
</section>

<section class="method" id="methode">
  <div>
    <h2>Comment c'est calculé</h2>
    <ol>
      <li>De GASPAR, le registre des procédures de prévention des risques de l'État (Géorisques), on tire chaque PPR inondation (fluvial, littoral ou multirisque avec inondation), les communes qu'il couvre, son état et sa date : approbation, ou application anticipée quand le préfet l'a ordonnée avant (article L562-2 du Code de l'environnement). Seuls les plans opposables aujourd'hui comptent.</li>
      <li>La DDTM publie le zonage réglementaire de ses PPR en données géographiques. Chaque zone porte son type de règle (TYPEREG, standard COVADIS) : interdiction ou interdiction stricte → zone rouge ; prescriptions → zone bleue. Le lien avec GASPAR donne à chaque zone la date de son plan.</li>
      <li>Là où une commune n'a pas de PPR numérique, l'atlas des zones inondables (AZI, approche hydrogéomorphologique de la DREAL) indique où l'eau peut aller : lit mineur, moyen et majeur, et à part le lit majeur exceptionnel. L'atlas n'a pas de force réglementaire ; il remplace le plan là où le plan manque.</li>
      <li>De la BDNB (base nationale des bâtiments du CSTB), on lit l'emprise de chaque construction, la commune, et la fiche fiscale du bâtiment : année de construction, usage, nombre de logements. Jamais les propriétaires ni les demandeurs de permis.</li>
      <li>Chaque bâtiment va dans une seule classe, la plus stricte qui le touche : rouge, sinon bleue, sinon atlas, sinon dehors. Un bâtiment est « après le PPRi » quand son année est postérieure à celle où le plan qui le zone est devenu opposable.</li>
      <li>On compte les bâtiments par commune, classe, scénario TRI et année. Seuls ces comptes sont gardés.</li>
      <li>L'année fiscale peut être celle d'une transformation. Avec les permis de construire (Sitadel), un bâtiment dont les parcelles n'ont eu que des permis d'extension ou de transformation dans les années qui précèdent est marqué « réforme apparente ».</li>
    </ol>
    <h3>Ce qui change par rapport à l'Espagne</h3>
    <table class="compare"><thead><tr><th></th><th>Espagne : RD 638/2016</th><th>France : PPRi (loi Barnier, 1995)</th></tr></thead><tbody>
      <tr><th>La règle</th><td>Un décret national, le même pour tout le pays, qui modifie le règlement du domaine public hydraulique.</td><td>Un plan par commune ou par bassin, approuvé par le préfet, annexé au PLU comme servitude d'utilité publique. Chaque plan a son règlement.</td></tr>
      <tr><th>La carte</th><td>Les zones inondables du SNCZI (lit d'écoulement préférentiel, crues de 100 et 500 ans), faites par l'État.</td><td>Le zonage du PPRi, qui croise l'aléa (crue de référence : la plus forte connue, ou la centennale si elle est plus forte) et les enjeux.</td></tr>
      <tr><th>Ce qui est interdit</th><td>Dépend de la zone et du sol : plus strict en sol rural qu'en sol urbanisé ; dans la zone de 500 ans, des conditions seulement.</td><td>Zone rouge : inconstructible en principe, avec des exceptions écrites dans chaque règlement. Zone bleue : constructible sous conditions.</td></tr>
      <tr><th>La date</th><td>Une seule pour tous : fin 2016. On compare 2008–2016 et 2017 et après.</td><td>Une par plan : dans l'Aude, de __PPRFIRST__ à __PPRLAST__. « Après » se lit bâtiment par bâtiment.</td></tr>
      <tr><th>Avant</th><td>Des cartes sans effet direct sur le permis.</td><td>Les plans des surfaces submersibles (décret-loi de 1935 ; dans l'Aude, 1948–1960) et l'article R111-3 du Code de l'urbanisme.</td></tr>
      <tr><th>Les bâtiments</th><td>Catastro : chaque bâtiment, avec ses dates de début et de fin.</td><td>BDNB et Fichiers fonciers : un bâtiment, une année ; pas de début ni de fin.</td></tr>
    </tbody></table>
    <h3>Paramètres</h3>
    __PARAMETRES__
  </div>
  <div>
    <h3>Ce qui reste en dehors, et pourquoi</h3>
    __HORS__
    <h3>Contraste : les crues du 15 octobre 2018</h3>
    <p>Les crues de l'Orbiel et du Trapel ont fait quinze morts dans l'Aude. Trèbes et Villegailhenc, parmi les communes les plus touchées, avaient déjà un PPRi. Après la crue, l'État les a révisés ; les nouveaux plans s'appliquent par anticipation, avant leur approbation. Le décompte « après le PPRi » de cette page part du plan en vigueur, donc ici de 2023 et 2024 : il ne voit rien encore. Mesuré depuis le premier plan, le tableau change.</p>
    __CONTRASTE__
    <h3>Ce qu'il faut savoir avant de citer</h3>
    <p class="aviso">Le zonage est celui en vigueur aujourd'hui. Un plan révisé peut avoir élargi la zone rouge : un bâtiment construit après le premier plan mais avant la révision tombait peut-être alors en zone bleue ou blanche. Les dates retenues sont celles du plan actuel, ce qui donne moins de bâtiments « après », jamais plus. La colonne « Après le premier PPRi » donne l'autre borne : le zonage d'aujourd'hui, daté du premier plan de la commune. La vérité est entre les deux.</p>
    <p class="aviso">L'année vient de la déclaration fiscale du propriétaire. Elle manque pour les bâtiments non imposés et peut être celle d'une reconstruction. Les Fichiers fonciers décrivent la situation au 1er janvier __FFYEAR__ : l'année __LAST__ n'est pas complète.</p>
    <p class="aviso">L'atlas des zones inondables de l'ex-Languedoc-Roussillon est diffusé sans licence explicite ; la question est posée à la DREAL Occitanie. Il ne sert qu'à classer des bâtiments ; ses géométries ne sont pas republiées.</p>
    <h3>Données ouvertes</h3>
    <p><a href="communes.csv">communes.csv</a> (une ligne par commune) · <a href="annual.csv">annual.csv</a> (par commune, classe, scénario TRI et année) · <a href="summary.json">summary.json</a> · <a href="../signals.json">signals.json</a> · comptes par département dans le <a href="__REPO__/tree/main/data/counts/fr">dépôt</a> · <a href="__REPO__">code</a>. Généré le __GENERATED__.</p>
  </div>
</section>

<footer class="site-footer">
  <p class="principle">Des données publiques, des règles visibles et chaque chiffre relié à sa source. Des indices, pas des verdicts.</p>
  <p>PPR : <a href="https://www.georisques.gouv.fr/">GASPAR, Géorisques</a> (ministère de la Transition écologique) et zonage de la DDTM de l'Aude (geo-ide) · Atlas des zones inondables : DREAL Occitanie, via <a href="https://www.picto-occitanie.fr/">Picto-Occitanie</a> · TRI : directive Inondation, Géorisques · Bâtiments : <a href="https://bdnb.io/">BDNB</a>, CSTB, d'après les Fichiers fonciers (DGFiP, Cerema) et Sitadel · Code MIT, comptes CC BY 4.0.</p>
  <nav aria-label="Projets frères"><ul class="siblings">
    <li><a href="https://asensio94.github.io/observatorio-alegaciones/">Observatorio de alegaciones</a></li>
    <li><a href="https://asensio94.github.io/vigia-incendios/">Vigía de incendios</a></li>
    <li><a href="https://asensio94.github.io/centinela-natura/">Centinela Natura</a></li>
    <li><a href="https://asensio94.github.io/vigilancia-humedales/">Vigilancia de humedales</a></li>
    <li><a href="https://asensio94.github.io/sub-nocte/">Sub Nocte</a></li>
    <li><a href="https://asensio94.github.io/riesgo-tendidos-aves/">Riesgo de tendidos para aves</a></li>
    <li><a href="https://asensio94.github.io/grafo-promotores/">Grafo de promotores</a></li>
    <li><a href="https://asensio94.github.io/cartera-cotizadas/">Cartera de las cotizadas</a></li>
    <li><a href="https://asensio94.github.io/cuaderno-campo/">Cuaderno de campo</a></li>
    <li><a href="https://asensio94.github.io/caudal-ecologico/">Caudal ecológico</a></li>
    <li><a href="https://asensio94.github.io/estado-iba/">Estado de las IBA</a></li>
    <li><a href="https://asensio94.github.io/barbechos-esteparias/">Barbechos y aves esteparias</a></li>
    <li aria-current="page"><a href="https://asensio94.github.io/zona-inundable/">Construir en zona inundable</a></li>
  </ul></nav>
</footer>

<script>
const D = __DATOS__;
// French grouping: a narrow no-break space between thousands (also for four digits) and a decimal comma.
const NN = " ";
const num = (x,d=0) => {
  if (x == null) return "—";
  const [e, f] = Math.abs(x).toFixed(d).split(".");
  return (x < 0 ? "−" : "") + e.replace(/\B(?=(\d{3})+(?!\d))/g, NN) + (f ? "," + f : "");
};
const Z = ["ppr_red","ppr_blue","azi","azi_exc"], ZN = {ppr_red:"Zone rouge", ppr_blue:"Zone bleue", azi:"Atlas, lits mineur à majeur", azi_exc:"Atlas, lit majeur exceptionnel"};
const selD = document.getElementById("f-desde"), chkC = document.getElementById("f-cuota");
const tot = r => Z.reduce((a,z) => a + r[z], 0);

function grafica(){
  const desde = +selD.value, A = D.annual.filter(r => r.year >= desde && r.year <= D.windows.last);
  const W = 760, H = 300, L = 52, R = 10, T = 26, B = 26;
  if (!A.length) return "";
  const cuota = chkC.checked;
  const val = r => cuota ? (tot(r)+r.out ? 100*tot(r)/(tot(r)+r.out) : 0) : tot(r);
  const max = Math.max(1, ...A.map(val)) * 1.08;
  const bw = (W-L-R) / A.length, x = y => L + (y - A[0].year) * bw;
  const yy = v => T + (1 - v/max) * (H-T-B);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${cuota ? "Part de la construction neuve en zone inondable par année" : "Bâtiments en zone inondable par année de construction"}">`;
  for (const t of [0,.25,.5,.75,1]) { const v = max/1.08*t; s += `<line class="eje" x1="${L}" x2="${W-R}" y1="${yy(v)}" y2="${yy(v)}"/><text x="${L-5}" y="${yy(v)+4}" text-anchor="end">${cuota ? num(v,1)+NN+"%" : num(v)}</text>`; }
  for (const r of A) {
    const prov = r.year >= D.windows.provisional[0];
    if (cuota) { s += `<rect x="${x(r.year)+1}" width="${Math.max(1,bw-2)}" y="${yy(val(r))}" height="${yy(0)-yy(val(r))}" fill="var(--ppr_blue)" opacity="${prov ? .35 : 1}"><title>${r.year} : ${num(val(r),2)}${NN}% de ${num(tot(r)+r.out)} bâtiments${prov ? " (provisoire)" : ""}</title></rect>`; continue; }
    let base = 0;
    for (const z of Z) {
      const v = r[z]; if (!v) continue;
      s += `<rect x="${x(r.year)+1}" width="${Math.max(1,bw-2)}" y="${yy(base+v)}" height="${yy(base)-yy(base+v)}" fill="var(--${z})" opacity="${prov ? .35 : 1}"><title>${r.year} · ${ZN[z]} : ${num(v)} bâtiments${prov ? " (provisoire)" : ""}</title></rect>`;
      base += v;
    }
  }
  const step = A.length > 40 ? 10 : 5;
  for (const r of A) if (r.year % step === 0) s += `<text x="${x(r.year)+bw/2}" y="${H-8}" text-anchor="middle">${r.year}</text>`;
  const xb = x(D.barnier + 1);
  if (D.barnier + 1 >= A[0].year) s += `<line class="rd" x1="${xb}" x2="${xb}" y1="${T-12}" y2="${H-B}"/><text class="rd-n" x="${xb+4}" y="${T-14}">Loi Barnier</text>`;
  return s + "</svg>";
}
function pintar(){
  document.getElementById("grafica").innerHTML = grafica();
  document.getElementById("leyenda").innerHTML = chkC.checked
    ? `<span><i style="background:var(--ppr_blue)"></i>Bâtiments en zone inondable parmi tous ceux de l'année, en${NN}%</span><span><i style="background:var(--ppr_blue);opacity:.35"></i>provisoire</span>`
    : Z.map(z => `<span><i style="background:var(--${z})"></i>${ZN[z]}</span>`).join("") + `<span><i style="background:var(--azi);opacity:.35"></i>provisoire</span>`;
}

const M = D.munis.map(m => ({...m, zoned_azi_all: m.zoned_azi + m.zoned_azi_exc}));
document.getElementById("top").innerHTML = M.filter(m => m.after_ppr > 0).slice(0, 10).map((m,i) =>
  `<li><b>${i+1}</b><a href="#m-${m.insee}">${m.name}</a><span class="n">${num(m.after_ppr)} bât. · PPRi ${m.ppr_year}</span></li>`).join("")
  || "<li>Aucune commune comptée pour l'instant.</li>";
let orden = "after_ppr", asc = false;
const COLS = ["zoned","zoned_ppr_red","zoned_ppr_blue","zoned_azi_all","after_ppr","after_ppr_red","after_ppr_mixed","after_first_ppr","post","pre_share","post_share"];
const DEC = {pre_share:1, post_share:1};
const plain = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"");
function tabla(){
  const q = plain(document.getElementById("f-busca").value.trim());
  const solo = document.getElementById("f-ppr").checked;
  const F = M.filter(m => (!solo || m.ppr_digital) && (!q || plain(m.name).includes(q)));
  F.sort((a,b) => { const u = a[orden], v = b[orden]; const c = typeof u === "string" ? u.localeCompare(v,"fr") : (u ?? -1) - (v ?? -1); return asc ? c : -c; });
  document.querySelector("#tabla tbody").innerHTML = F.map(m => `<tr id="m-${m.insee}"><td class="nom">${m.name} <span class="note">${m.insee}</span></td>`
    + `<td class="num">${m.first_ppr_year ?? "—"}</td>`
    + `<td class="num">${m.ppr_year ? m.ppr_year + (m.ppr_anticipated ? " a" : "") + (m.ppr_digital ? "" : " *") : m.pss_year ? "PSS " + m.pss_year + " *" : "—"}</td>`
    + COLS.map(k => `<td class="num">${num(m[k], DEC[k] || 0)}${k.endsWith("share") && m[k] != null ? NN + "%" : ""}</td>`).join("") + "</tr>").join("");
  document.getElementById("cuenta").textContent = `${num(F.length)} communes · * PPRi sans zonage numérique`;
  for (const th of document.querySelectorAll("#tabla th")) {
    if (th.dataset.k === orden) th.setAttribute("aria-sort", asc ? "ascending" : "descending"); else th.removeAttribute("aria-sort");
  }
}
document.querySelector("#tabla thead").addEventListener("click", e => {
  const th = e.target.closest("th"); if (!th) return;
  if (orden === th.dataset.k) asc = !asc; else { orden = th.dataset.k; asc = orden === "name"; }
  tabla();
});
document.getElementById("f-busca").addEventListener("input", tabla);
document.getElementById("f-ppr").addEventListener("change", tabla);
selD.addEventListener("change", pintar); chkC.addEventListener("change", pintar);
pintar(); tabla();
// Anchors (#m-11397) from the list and from other projects: the row must exist before scrolling.
if (location.hash) document.querySelector(location.hash)?.scrollIntoView({block:"center"});
</script>
</body>
</html>
"""


def build() -> Path | None:
    s = analysis.summary()
    df, munis, annual, info = s.pop("_df"), s.pop("_munis"), s.pop("_annual"), s.pop("_info")
    if not s["departments"]:
        return None
    w, e = s["windows"], s["effect"]
    years = sorted(int(y) for y in s["ppr_years"])
    now = datetime.now(timezone.utc)
    data = {"barnier": config.BARNIER_YEAR, "windows": w,
            "annual": annual.to_dict("records"),
            "munis": munis.astype(object).where(munis.notna(), None).to_dict("records")}
    effect = f"{_p(e.get('before_share'), 1)} → {_p(e.get('after_share'), 1)}" if e.get("communes") else "—"
    html = (PAGE
            .replace("__LOGO__", LOGO_SVG)
            .replace("__FAVICON__", favicon_link(ACCENT, ACCENT_DARK))
            .replace("__COMMON_CSS__", COMMON_CSS)
            .replace("__ACCENT__", ACCENT).replace("__ACCENT_DARK__", ACCENT_DARK)
            .replace("__REGION__", " · ".join(d["name"] for d in s["departments"].values()))
            .replace("__OTHER__", escape(i18n.t(L, "other_country_link")))
            .replace("__ZONED__", _n(s["zoned"]))
            .replace("__AFTER__", _n(s["after_ppr"]))
            .replace("__NAFTER__", _n(s["communes_after_ppr"]))
            .replace("__EFFECT__", effect)
            .replace("__POSTFROM__", str(config.RD_YEAR + 1))
            .replace("__PRE__", _span(w["pre"])).replace("__POSTW__", _span(w["post"]))
            .replace("__PROV__", " et ".join(map(str, range(w["provisional"][0], w["provisional"][1] + 1))))
            .replace("__PPRFIRST__", str(years[0]) if years else "—").replace("__PPRLAST__", str(years[-1]) if years else "—")
            .replace("__FFYEAR__", str(s["data_year"])).replace("__LAST__", str(w["last"]))
            .replace("__EFFET__", _effet(s))
            .replace("__PERIODES__", _periodes(s["periods"]))
            .replace("__PARAMETRES__", _parametres(s))
            .replace("__HORS__", _hors(s, info))
            .replace("__CONTRASTE__", _contraste(munis, info))
            .replace("__REPO__", config.REPO_URL)
            .replace("__GENERATED__", now.strftime("%d/%m/%Y à %H:%M UTC"))
            .replace("__DATOS__", json.dumps(data, ensure_ascii=False, separators=(",", ":"))))
    # French typography in the fixed text: no-break space before the two-part punctuation marks.
    html = _french_spaces(html)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "index.html"
    out.write_text(html, encoding="utf-8")
    munis.to_csv(OUT / "communes.csv", index=False)
    (df.groupby(["insee", "zone", "tri", "year"], as_index=False)
       [["n", "mixed", "res", "dwellings", "after_map", "after_mixed", "after_res", "after_dwellings"]].sum()
       .assign(country="FR").sort_values(["insee", "zone", "tri", "year"])
       .to_csv(OUT / "annual.csv", index=False))
    (OUT / "summary.json").write_text(json.dumps({**s, "generated": now.isoformat(timespec="minutes")},
                                                 ensure_ascii=False, indent=1, default=int), encoding="utf-8")
    return out


def _french_spaces(html: str) -> str:
    """« : » and « ; » in the prose get a no-break space; scripts and styles are left alone."""
    import re
    parts = re.split(r"(<script>.*?</script>|<style>.*?</style>|<[^>]+>)", html, flags=re.S)
    for i, part in enumerate(parts):
        if part.startswith("<"):
            continue
        parts[i] = re.sub(r" ([:;?!])", " \\1", part)
        parts[i] = parts[i].replace("« ", "« ").replace(" »", " »")
    return "".join(parts)
