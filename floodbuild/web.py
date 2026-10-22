"""docs/index.html: buildings in flood zones by year and municipality, before and after RD 638/2016."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from . import analysis, config, snczi, geo
from .logo import LOGO_SVG, favicon_link
from .footer import footer_nav

COMMON_CSS = Path(__file__).with_name("common.css").read_text(encoding="utf-8").strip()
ACCENT, ACCENT_DARK = "#4a5d75", "#a7b8cc"


def _es(x: float, decimales: int = 0) -> str:
    """Número a la española: 1.500 y 0,15."""
    s = f"{x:,.{decimales}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _pct(x: float | None, decimales: int = 1) -> str:
    return "—" if x is None else f"{_es(x, decimales)} %"


def _span(w) -> str:
    return f"{w[0]}–{w[1]}"


# --- Page pieces -------------------------------------------------------------------------------

def _parametros(s: dict, zs: dict) -> str:
    w = s["windows"]
    corto = {"zfp": "Flujo preferente", "t100": "T100", "t500": "T500"}
    mapas = "; ".join(f"{corto[k]}: "
                      f"{_es(v['n'])} polígonos, {_es(v['km2'], 1)} km², aprobados entre {v['first_year']} y {v['last_year']}"
                      for k, v in zs.items() if v["n"])
    filas = [
        ("Zonas inundables", "SNCZI del Ministerio para la Transición Ecológica: zona de flujo preferente y "
                             "láminas de inundación de 100 y 500 años de periodo de retorno, servicio WFS"),
        ("Mapas leídos", mapas or "—"),
        ("Edificios", "Catastro INSPIRE, tema Edificios, un fichero por municipio; "
                      f"extracto de {', '.join(sorted({d[:7] for d in s['catastro_dates']})) or '—'}"),
        ("Año", "fin de la fecha de construcción del edificio (dateOfConstruction/end)"),
        ("Dentro o fuera", "un punto interior de la huella del edificio dentro del polígono"),
        ("Clase", "excluyente y de la más estricta a la menos: flujo preferente, luego T100, luego T500"),
        ("Antes", f"{_span(w['pre'])} ({w['pre'][1] - w['pre'][0] + 1} años)"),
        ("Después", f"{_span(w['post'])} ({w['post'][1] - w['post'][0] + 1} años)"),
        ("Provisionales", f"{_span(w['provisional'])}: el Catastro tarda en dar de alta la obra nueva; "
                          "se muestran pero no entran en las comparaciones"),
        ("Reforma aparente", f"el principio y el fin de la fecha de construcción se separan más de {config.MIXED_YEARS} año"),
        ("Municipio", "código INE (es-atlas, IGN) del municipio que tiene el mismo nombre a menos de 3 km de los edificios; si no está en es-atlas, «C» y el código del Catastro"),
    ]
    return '<table class="params">' + "".join(
        f"<tr><th>{escape(a)}</th><td>{escape(b)}</td></tr>" for a, b in filas) + "</table>"


def _periodos(p: dict) -> str:
    filas = []
    for k, nombre in (("boom", "Burbuja"), ("pre", "Antes"), ("post", "Después")):
        d = p[k]
        filas.append(
            f"<tr><th>{nombre} <span class='data'>{_span(d['years'])}</span></th>"
            f"<td class='num'>{_es(d['per_year'], 1)}</td><td class='num'>{_pct(d['share'], 2)}</td>"
            f"<td class='num'>{_es(d['restricted_per_year'], 1)}</td><td class='num'>{_pct(d['restricted_share'], 2)}</td>"
            f"<td class='num'>{_pct(d['share_clean'], 2)}</td></tr>")
    return ('<div class="tabla"><table class="params periodos"><tr><th>Periodo</th><th class="num">En zona inundable, al año</th>'
            '<th class="num">Parte de la obra nueva</th><th class="num">En flujo preferente o T100, al año</th>'
            '<th class="num">Parte de la obra nueva</th><th class="num">Parte, sin reformas aparentes</th></tr>'
            + "".join(filas) + "</table></div>")


def _cambio(a: float | None, b: float | None) -> str:
    if not a or b is None:
        return "—"
    v = 100 * (b / a - 1)
    return f"{'+' if v >= 0 else '−'}{_es(abs(v))} %"


def _reformas(s: dict) -> str:
    p = s["periods"]
    post = s["post"]
    m = s["post_mixed"]
    parte = 100 * m / post if post else 0
    return (f"<p>De los {_es(post)} edificios en zona inundable con fecha posterior a {config.RD_YEAR}, "
            f"<b>{_es(m)}</b> ({_pct(parte)}) tienen partes de años distintos: el principio y el fin de su fecha de "
            "construcción no coinciden. Son, casi seguro, ampliaciones o reformas de algo que ya estaba. Sin ellos, la "
            f"parte de la obra nueva que cae en zona inundable pasa del {_pct(p['pre']['share_clean'], 2)} antes al "
            f"{_pct(p['post']['share_clean'], 2)} después (con ellos, del {_pct(p['pre']['share'], 2)} al "
            f"{_pct(p['post']['share'], 2)}).</p>"
            "<p>Lo que esta medida no ve: una reforma integral de un edificio de una sola unidad cambia el principio y "
            "el fin a la vez, y queda como obra nueva. El Catastro lo hace así a propósito, porque para el valor del "
            "edificio una reforma integral equivale a construirlo de nuevo. Esa parte no se puede separar con estos "
            "datos; por eso la cifra «construidos desde 2017» es un máximo.</p>")


PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__FAVICON__
<title>Construir en zona inundable</title>
<meta name="description" content="Cuántos edificios se han construido cada año dentro de las zonas inundables del SNCZI, municipio a municipio, y si el ritmo cambió tras el Real Decreto 638/2016.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
__COMMON_CSS__
:root{--accent:__ACCENT__;--accent-dark:__ACCENT_DARK__}
:root{--zfp:#1d2c3f;--t100:#4a5d75;--t500:#a7b8cc;--prov:#dad2cb}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){--zfp:#dce5f0;--t100:#a7b8cc;--t500:#5a6b80;--prov:#362d28}
}
:root[data-theme="dark"]{--zfp:#dce5f0;--t100:#a7b8cc;--t500:#5a6b80;--prov:#362d28}
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
.grafica .cuota{fill:none;stroke:var(--ink);stroke-width:1.6}
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
.method p{margin:0 0 10px} .method ol{margin:0 0 10px;padding-left:1.4em} .method ol li{margin-bottom:8px}
.method > div > h3:first-child{margin-top:0}
.method table.params th{white-space:normal;width:30%}
.aviso{border-left:3px solid var(--accent);padding:2px 0 2px 12px}
.site-footer p{margin:0}
@media (max-width:900px){.dos,.method{grid-template-columns:minmax(0,1fr)}}
</style>
</head>
<body>
<header class="site-header">
  <div class="marca">
    <h1>__LOGO__Construir en <span>zona inundable</span></h1>
    <span class="label">__REGION__ · SNCZI y Catastro · se actualiza cada mes</span>
  </div>
  <p class="lede">Cuántos edificios se han levantado dentro de las zonas inundables oficiales, año a año y municipio a municipio, y si el ritmo cambió cuando el Real Decreto 638/2016 limitó lo que se puede construir en ellas. Con los mapas del Ministerio para la Transición Ecológica y el año de construcción del Catastro.</p>
  <div class="figures">
    <div><b>__ZONED__</b><span>edificios en zona inundable</span></div>
    <div><b>__POST__</b><span>con fecha de __POSTFROM__ o después</span></div>
    <div><b>__NPOST__</b><span>municipios con obra desde __POSTFROM__</span></div>
    <div><b>__SHARE__</b><span>de la obra nueva cae en zona inundable, __PRE__ → __POSTW__</span></div>
  </div>
</header>

<section class="bloque" id="anios">
  <h2>Año a año</h2>
  <div class="dos">
    <div>
      <div class="controles">
        <label>Desde <select id="f-desde"><option value="1960">1960</option><option value="1990">1990</option><option value="2000" selected>2000</option></select></label>
        <label><input type="checkbox" id="f-cuota"> Ver la parte de la obra nueva en zona inundable</label>
      </div>
      <figure class="grafica" style="margin:0"><div id="grafica"></div>
        <figcaption class="leyenda" id="leyenda"></figcaption></figure>
      <p class="note">Edificios por año de construcción según el Catastro, en los municipios que tienen zona inundable cartografiada. Los años __PROV__ salen más bajos porque el Catastro aún no ha dado de alta toda la obra terminada: son provisionales.</p>
    </div>
    <div>
      <h3 class="label">Antes y después del Real Decreto</h3>
      __PERIODOS__
      <p class="note">«Parte de la obra nueva»: edificios en zona inundable entre todos los construidos en esos años en los mismos municipios. Corrige el ciclo de la construcción, que se hundió después de 2008: si se construye menos en todas partes, la cifra al año baja aunque nada cambie en las zonas inundables.</p>
    </div>
  </div>
</section>

<section class="bloque" id="municipios">
  <h2>Por municipio</h2>
  <div class="dos">
    <div>
      <p>Municipios con más edificios en zona inundable fechados de __POSTFROM__ en adelante. Pulse un nombre para ver su fila.</p>
      <ol class="top" id="top"></ol>
    </div>
    <div>
      <p class="aviso">Un edificio construido después de 2016 en zona inundable no es por sí una infracción. El Real Decreto no prohíbe toda obra: es más estricto en suelo rural que en suelo ya urbanizado, donde deja construir con condiciones, y en la zona de 500 años pone condiciones, no prohibiciones. Y el año del Catastro puede ser el de una reforma. Son indicios para preguntar, no veredictos.</p>
    </div>
  </div>
  <div class="controles">
    <label>Buscar <input type="search" id="f-busca" placeholder="municipio"></label>
    <label>Provincia <select id="f-prov"><option value="">Todas</option></select></label>
    <span id="cuenta"></span>
  </div>
  <div class="tabla"><table class="munis" id="tabla"><thead><tr>
    <th data-k="name">Municipio</th>
    <th data-k="zoned" class="num">En zona inundable</th>
    <th data-k="zoned_zfp" class="num">Flujo preferente</th>
    <th data-k="zoned_t100" class="num">T100</th>
    <th data-k="zoned_t500" class="num">T500</th>
    <th data-k="post" class="num" aria-sort="descending">Desde __POSTFROM__</th>
    <th data-k="post_mixed" class="num">De ellos, reforma aparente</th>
    <th data-k="pre_per_year" class="num">Al año __PRE__</th>
    <th data-k="post_per_year" class="num">Al año __POSTW__</th>
    <th data-k="pre_share" class="num">Parte de la obra nueva __PRE__</th>
    <th data-k="post_share" class="num">Parte de la obra nueva __POSTW__</th>
  </tr></thead><tbody></tbody></table></div>
  <p class="note">Cifras de edificios, no de viviendas: un bloque de pisos cuenta uno. Fuera de zona inundable no se lista ningún municipio.</p>
</section>

<section class="method" id="metodo">
  <div>
    <h2>Cómo se calcula</h2>
    <ol>
      <li>Del Sistema Nacional de Cartografía de Zonas Inundables (SNCZI) se descargan tres capas: la zona de flujo preferente, por donde corre el agua con más fuerza y profundidad, y las zonas que se inundan con la avenida de 100 años y con la de 500 años de periodo de retorno.</li>
      <li>Del Catastro se descarga, municipio a municipio, el fichero de edificios. Cada edificio trae su huella y su fecha de construcción. Solo se leen la huella, la fecha, el uso y el número de viviendas; nunca la referencia catastral ni nada que lleve al titular. Los municipios al este del meridiano de Greenwich vienen en otro huso UTM y se pasan al común antes de cruzarlos con los mapas.</li>
      <li>Cada edificio va a una sola clase, la más estricta que le toca: flujo preferente; si no, zona de 100 años; si no, zona de 500 años; si no, fuera. Se mira un punto interior de la huella: un edificio a caballo cuenta donde cae ese punto.</li>
      <li>Se cuenta cuántos edificios hay en cada clase por año de construcción. Solo se guardan esos recuentos; los edificios uno a uno no se guardan.</li>
      <li>El Real Decreto 638/2016 entró en vigor a final de 2016. Se compara lo construido de __POSTFROM__ a __POSTEND__ con lo construido de __PRE__, al año y como parte de toda la obra nueva del municipio. Los años más recientes se dejan fuera porque el Catastro aún no ha recogido toda la obra terminada.</li>
      <li>El año del Catastro puede ser el de una reforma y no el de la obra. Cuando las partes de un edificio tienen fechas distintas se marca como reforma aparente, y cada comparación se repite sin ellas.</li>
    </ol>
    <h3>Parámetros</h3>
    __PARAMETROS__
  </div>
  <div>
    <h3>Reforma u obra nueva</h3>
    __REFORMAS__
    <h3>Contraste</h3>
    <p>Paiporta, en el centro de la zona arrasada por la DANA de octubre de 2024, se comprobó a mano contra el mapa del propio servicio (WMS del SNCZI, lo que pinta su visor). La zona de flujo preferente y la de 100 años del barranco del Poyo atraviesan el pueblo, pero como una franja estrecha sobre el cauce; el casco queda en la de 500 años. El recuento da __PAIPORTA__ El mapa oficial no es la inundación real: el agua de 2024 pasó muy por encima de la lámina de 100 años, y esta página cuenta solo contra el mapa oficial.</p>
    <p>Pendiente: contrastar el año del Catastro con una fuente independiente (licencias de obra o huella urbana por satélite) para medir cuántas «obras nuevas» son reformas integrales.</p>
    <h3>Lo que hay que saber antes de citarlo</h3>
    <p class="aviso">Las zonas inundables cubren los tramos de río estudiados por el SNCZI, no todos los cauces. Fuera de los tramos estudiados un edificio sale «fuera» aunque se inunde. Y cada mapa tiene su fecha: un edificio de 2010 en un tramo cartografiado en 2020 se construyó antes de que hubiera mapa.</p>
    <p class="aviso">Navarra y el País Vasco tienen catastro propio, fuera del servicio estatal; cuando el proyecto llegue a toda España, allí no habrá cifras.</p>
    <p>El Catastro numera los municipios de otra forma que el INE. Cada municipio catastral se identifica por su nombre entre los municipios cercanos a sus edificios. Los pocos que no están en el mapa municipal de es-atlas salen con su código del Catastro precedido de «C».</p>
    <h3>Datos abiertos</h3>
    <p><a href="edificios-municipios.csv">edificios-municipios.csv</a> (una fila por municipio) · <a href="edificios-anuales.csv">edificios-anuales.csv</a> (por municipio, clase y año) · <a href="signals.json">signals.json</a> · recuentos por municipio catastral en el <a href="__REPO__/tree/main/data/counts">repositorio</a> · <a href="__REPO__">código</a>. Generado el __GENERATED__.</p>
  </div>
</section>

<footer class="site-footer">
  <p class="principle">Datos públicos, reglas a la vista y cada cifra enlazada a su fuente. Indicios, no veredictos.</p>
  <p>Zonas inundables: <a href="https://www.miteco.gob.es/es/agua/temas/gestion-de-los-riesgos-de-inundacion/snczi.html">SNCZI</a>, Ministerio para la Transición Ecológica y el Reto Demográfico · Edificios: <a href="https://www.catastro.hacienda.gob.es/webinspire/index.html">Catastro INSPIRE</a>, Dirección General del Catastro · Municipios: es-atlas, a partir de datos del Instituto Geográfico Nacional · Código MIT, recuentos propios CC BY 4.0.</p>
  __FOOTER_NAV__
</footer>

<script>
const D = __DATOS__;
// Spanish grouping for every number, also four-digit ones (toLocaleString leaves 1500 ungrouped).
const num = (x,d=0) => {
  if (x == null) return "—";
  const [e, f] = Math.abs(x).toFixed(d).split(".");
  return (x < 0 ? "−" : "") + e.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + (f ? "," + f : "");
};
const Z = ["zfp","t100","t500"], ZN = {zfp:"Flujo preferente", t100:"T100", t500:"T500"};
const selD = document.getElementById("f-desde"), chkC = document.getElementById("f-cuota");

function grafica(){
  const desde = +selD.value, A = D.annual.filter(r => r.year >= desde && r.year <= D.data_year);
  const W = 760, H = 300, L = 52, R = 10, T = 26, B = 26;
  if (!A.length) return "";
  const cuota = chkC.checked;
  const val = r => cuota ? (r.zfp+r.t100+r.t500+r.out ? 100*(r.zfp+r.t100+r.t500)/(r.zfp+r.t100+r.t500+r.out) : 0) : r.zfp+r.t100+r.t500;
  const max = Math.max(1, ...A.map(val)) * 1.08;
  const bw = (W-L-R) / A.length, x = y => L + (y - A[0].year) * bw;
  const yy = v => T + (1 - v/max) * (H-T-B);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${cuota ? "Parte de la obra nueva en zona inundable por año" : "Edificios en zona inundable por año de construcción"}">`;
  for (const t of [0,.25,.5,.75,1]) { const v = max/1.08*t; s += `<line class="eje" x1="${L}" x2="${W-R}" y1="${yy(v)}" y2="${yy(v)}"/><text x="${L-5}" y="${yy(v)+4}" text-anchor="end">${cuota ? num(v,1)+" %" : num(v)}</text>`; }
  for (const r of A) {
    const prov = r.year >= D.windows.provisional[0];
    if (cuota) { s += `<rect x="${x(r.year)+1}" width="${Math.max(1,bw-2)}" y="${yy(val(r))}" height="${yy(0)-yy(val(r))}" fill="var(--t100)" opacity="${prov ? .35 : 1}"><title>${r.year}: ${num(val(r),2)} % de ${num(r.zfp+r.t100+r.t500+r.out)} edificios${prov ? " (provisional)" : ""}</title></rect>`; continue; }
    let base = 0;
    for (const z of Z) {
      const v = r[z]; if (!v) continue;
      s += `<rect x="${x(r.year)+1}" width="${Math.max(1,bw-2)}" y="${yy(base+v)}" height="${yy(base)-yy(base+v)}" fill="var(--${z})" opacity="${prov ? .35 : 1}"><title>${r.year} · ${ZN[z]}: ${num(v)} edificios${prov ? " (provisional)" : ""}</title></rect>`;
      base += v;
    }
  }
  const step = A.length > 40 ? 10 : 5;
  for (const r of A) if (r.year % step === 0) s += `<text x="${x(r.year)+bw/2}" y="${H-8}" text-anchor="middle">${r.year}</text>`;
  const xr = x(D.rd_year + 1);
  if (D.rd_year + 1 >= A[0].year) s += `<line class="rd" x1="${xr}" x2="${xr}" y1="${T-12}" y2="${H-B}"/><text class="rd-n" x="${xr+4}" y="${T-14}">RD 638/2016</text>`;
  return s + "</svg>";
}
function pintar(){
  document.getElementById("grafica").innerHTML = grafica();
  document.getElementById("leyenda").innerHTML = chkC.checked
    ? `<span><i style="background:var(--t100)"></i>Edificios en cualquier zona inundable entre todos los del año, en %</span><span><i style="background:var(--t100);opacity:.35"></i>provisional</span>`
    : Z.map(z => `<span><i style="background:var(--${z})"></i>${ZN[z]}</span>`).join("") + `<span><i style="background:var(--t500);opacity:.35"></i>provisional</span>`;
}

const M = D.munis;
document.getElementById("top").innerHTML = M.filter(m => m.post > 0).slice(0, 10).map((m,i) =>
  `<li><b>${i+1}</b><a href="#m-${m.ine}">${m.name}</a><span class="n">${num(m.post)} edif. · ${m.province_name}</span></li>`).join("")
  || "<li>Aún no hay municipios contados.</li>";
const selP = document.getElementById("f-prov");
for (const [p,n] of [...new Map(M.map(m => [m.province, m.province_name]))].sort((a,b) => a[1].localeCompare(b[1],"es"))) selP.add(new Option(n, p));
let orden = "post", asc = false;
const COLS = ["zoned","zoned_zfp","zoned_t100","zoned_t500","post","post_mixed","pre_per_year","post_per_year","pre_share","post_share"];
const DEC = {pre_per_year:1, post_per_year:1, pre_share:1, post_share:1};
function tabla(){
  const q = document.getElementById("f-busca").value.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"");
  const p = selP.value;
  const F = M.filter(m => (!p || m.province === p) && (!q || m.name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"").includes(q)));
  F.sort((a,b) => { const u = a[orden], v = b[orden]; const c = typeof u === "string" ? u.localeCompare(v,"es") : (u ?? -1) - (v ?? -1); return asc ? c : -c; });
  document.querySelector("#tabla tbody").innerHTML = F.map(m => `<tr id="m-${m.ine}"><td class="nom">${m.name} <span class="note">${m.province_name}</span></td>`
    + COLS.map(k => `<td class="num">${num(m[k], DEC[k] || 0)}${k.endsWith("share") && m[k] != null ? " %" : ""}</td>`).join("") + "</tr>").join("");
  document.getElementById("cuenta").textContent = `${num(F.length)} municipios`;
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
selP.addEventListener("change", tabla);
selD.addEventListener("change", pintar); chkC.addEventListener("change", pintar);
pintar(); tabla();
// Anchors (#m-46250) from the list and from other projects: the row must exist before scrolling.
if (location.hash) document.querySelector(location.hash)?.scrollIntoView({block:"center"});
</script>
</body>
</html>
"""


def _paiporta(munis) -> str:
    r = munis[munis.ine == "46186"] if len(munis) else munis
    if not len(r):
        return "pendiente de contar."
    r = r.iloc[0]
    return (f"{_es(r.zoned)} edificios en zona inundable: {_es(r.zoned_zfp)} en flujo preferente, {_es(r.zoned_t100)} en "
            f"la de 100 años y {_es(r.zoned_t500)} en la de 500 años.")


def build() -> Path:
    s = analysis.summary()
    df, munis, annual = s.pop("_df"), s.pop("_munis"), s.pop("_annual")
    zs = snczi.summary(tuple(geo.provinces(tuple(config.REGIONS))))
    w, p = s["windows"], s["periods"]
    now = datetime.now(timezone.utc)
    datos = {
        "data_year": s["data_year"], "rd_year": config.RD_YEAR, "windows": w,
        "annual": annual.to_dict("records"),
        "munis": munis.astype(object).where(munis.notna(), None).to_dict("records"),
    }
    share = f"{_pct(p['pre']['share'])} → {_pct(p['post']['share'])}"
    html = (PLANTILLA
            .replace("__LOGO__", LOGO_SVG)
            .replace("__FAVICON__", favicon_link(ACCENT, ACCENT_DARK))
            .replace("__COMMON_CSS__", COMMON_CSS)
            .replace("__ACCENT__", ACCENT).replace("__ACCENT_DARK__", ACCENT_DARK)
            .replace("__REGION__", " · ".join(config.REGIONS.values()))
            .replace("__ZONED__", _es(s["zoned"]))
            .replace("__POST__", _es(s["post"]))
            .replace("__NPOST__", _es(s["municipalities_post"]))
            .replace("__SHARE__", share)
            .replace("__POSTFROM__", str(config.RD_YEAR + 1))
            .replace("__POSTEND__", str(w["post"][1]))
            .replace("__PRE__", _span(w["pre"])).replace("__POSTW__", _span(w["post"]))
            .replace("__PROV__", " y ".join(map(str, range(w["provisional"][0], w["provisional"][1] + 1))))
            .replace("__PERIODOS__", _periodos(p))
            .replace("__PARAMETROS__", _parametros(s, zs))
            .replace("__REFORMAS__", _reformas(s))
            .replace("__PAIPORTA__", _paiporta(munis))
            .replace("__REPO__", config.REPO_URL)
            .replace("__FOOTER_NAV__", footer_nav("es"))
            .replace("__GENERATED__", now.strftime("%d/%m/%Y a las %H:%M UTC"))
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":"))))
    config.DOCS.mkdir(parents=True, exist_ok=True)
    out = config.DOCS / "index.html"
    out.write_text(html, encoding="utf-8")
    munis.to_csv(config.DOCS / "edificios-municipios.csv", index=False)
    (df.groupby(["ine", "zone", "year"], as_index=False)[["n", "mixed", "res", "dwellings", "after_map"]].sum()
       .sort_values(["ine", "zone", "year"]).to_csv(config.DOCS / "edificios-anuales.csv", index=False))
    (config.DOCS / "summary.json").write_text(json.dumps({**s, "zones": zs, "generated": now.isoformat(timespec="minutes")},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
    return out
