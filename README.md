# Construir en zona inundable

Cuántos edificios se han construido cada año dentro de las zonas inundables oficiales, municipio a municipio, y si el ritmo cambió cuando el Real Decreto 638/2016 limitó los usos en ellas. Cruza los mapas del Sistema Nacional de Cartografía de Zonas Inundables (SNCZI, Ministerio para la Transición Ecológica) con el año de construcción de los edificios del Catastro. Distingue la zona de flujo preferente, la de 100 años y la de 500 años. Piloto: Comunitat Valenciana. Web: <https://asensio94.github.io/zona-inundable/>

## Cómo funciona

1. Descarga del servicio WFS del SNCZI las tres capas (zona de flujo preferente, lámina de 100 años y lámina de 500 años), en ETRS89 / UTM 30N y limitadas a cada provincia. Las descargas en shapefile de la web del ministerio están tras un reto antibots; el WFS es la vía documentada para máquinas.
2. Lee el ATOM de edificios del Catastro INSPIRE por oficina territorial y se queda con los municipios cuyo recuadro toca algún polígono inundable.
3. Para cada uno de esos municipios descarga el fichero de edificios y lee de cada edificio la huella, la fecha de construcción (principio y fin), el uso y el número de viviendas. Los municipios al este del meridiano de Greenwich (la Marina Alta) vienen en el huso UTM 31 y se pasan al 30. No lee la referencia catastral ni nada que lleve al titular.
4. Cada edificio va a una sola clase, la más estricta en la que cae un punto interior de su huella: flujo preferente, luego 100 años, luego 500 años, luego fuera. También se apunta el año en que se aprobó el primer mapa que lo cubre.
5. Guarda solo los recuentos por clase y año de construcción en `data/counts/`. Un municipio se vuelve a contar únicamente cuando cambia su fichero del Catastro o cualquier mapa del SNCZI.
6. Asigna cada municipio catastral a su código INE, porque la numeración del Catastro no es la del INE (Paiporta es 46188 en uno y 46186 en el otro). Busca entre los municipios a menos de 3 km de sus edificios el que tiene el mismo nombre; no basta con mirar dónde caen, porque los límites de es-atlas están tan simplificados que la mayoría de los edificios de Mislata caen dentro del contorno de València.
7. Compara lo construido después de 2016 (de 2017 al año del extracto menos dos) con 2008-2016: edificios al año y parte de toda la obra nueva del municipio que cae en zona inundable. La parte corrige el ciclo de la construcción, que se hundió después de 2008. Los dos últimos años se muestran como provisionales porque el Catastro tarda en dar de alta la obra nueva.
8. Genera `docs/index.html`, los CSV abiertos y `docs/signals.json` para Estado de las IBA.

## Contraste

- **Paiporta**, en el centro de la zona arrasada por la DANA de octubre de 2024, se comprobó a mano contra el mapa que pinta el propio visor del SNCZI (servicio WMS). La zona de flujo preferente y la de 100 años del barranco del Poyo atraviesan el pueblo como una franja estrecha sobre el cauce; el casco queda en la de 500 años. El recuento da 1.212 edificios en zona inundable, todos en la de 500 años, y 54 con fecha de 2017 o posterior. El mapa oficial no es la inundación real: el agua de 2024 desbordó con mucho la lámina de 100 años.
- **Reforma u obra nueva.** De los 2.777 edificios en zona inundable fechados después de 2016, 863 (31 %) tienen partes de años distintos, señal de ampliación o reforma. Sin ellos, la parte de la obra nueva que cae en zona inundable pasa del 9,2 % (2008-2016) al 11,8 % (2017-2024); con ellos, del 8,0 % al 10,6 %. La subida se mantiene en los dos casos.
- **Georreferencia.** El Catastro sirve los municipios al este del meridiano de Greenwich (Dénia, Xàbia, Calp…) en el huso UTM 31. Leídos como si fueran del 30 caían 500 km al oeste y salían sin un solo edificio en zona inundable; ahora se reproyectan, y Dénia pasa de 0 a 2.097.
- **Códigos de municipio.** Los 447 municipios catastrales con zona inundable cercana se asignaron a 442 municipios INE sin repetir ninguno. Los 5 restantes no están en es-atlas y conservan su código del Catastro.

## Límites

- **El año del Catastro puede ser de una reforma.** Una reforma integral cuenta como fecha de construcción, porque para el Catastro equivale a un edificio nuevo. Cuando las partes de un edificio tienen años distintos se marca como «reforma aparente» y cada comparación se repite sin ellas. La reforma integral de un edificio de una sola unidad no se distingue: la cifra «construidos desde 2017» es un máximo.
- El mapa oficial no es la inundación real. Fuera de los tramos de río que estudió el SNCZI un edificio sale «fuera» aunque se inunde.
- Cada mapa tiene su fecha de aprobación. Un edificio de 2012 en un tramo cartografiado en 2020 se construyó antes de que existiera el mapa; el recuento guarda cuántos son posteriores al primer mapa que los cubre.
- Un edificio construido después de 2016 en zona inundable no es por sí una infracción: el Real Decreto es más estricto en suelo rural que en suelo ya urbanizado, donde permite construir con condiciones, y fuera de la zona de policía pone condiciones (sin sótanos, a cota segura), no prohibiciones.
- Cuenta edificios, no viviendas ni superficie. Un bloque de pisos y un almacén cuentan uno cada uno.
- Navarra y el País Vasco tienen catastro propio, fuera del servicio estatal.
- Un edificio a caballo entre dos clases cuenta donde cae su punto interior.
- Algunos municipios pequeños no están en es-atlas (en la Comunitat Valenciana, Rafal, Llocnou de la Corona o Geldo). Salen en la tabla con su código del Catastro precedido de «C» y no generan señal para Estado de las IBA, que pide el código INE.

## Pendiente

- Contrastar el año del Catastro con una fuente independiente (licencias de obra municipales, huella urbana por satélite como GHSL o el SIOSE) para medir cuántas «obras nuevas» son reformas integrales.
- Toda España: añadir comunidades en `config.REGIONS`. La capa nacional de flujo preferente pesa más de 1 GB en el WFS; habrá que bajarla por provincias en varias pasadas.
- Comparar con la capa provisional de dominio público hidráulico tras la DANA (`agua:zi_dana_dph_propuesto`).
- Que Estado de las IBA acepte el tipo de señal `flood_building` (se le ha propuesto aparte).

## Uso

```bash
pip install -r requirements.txt
python -m floodbuild zones               # capas del SNCZI de las comunidades configuradas
python -m floodbuild buildings           # recuento del Catastro (reanudable)
python -m floodbuild buildings --only 46188   # un municipio catastral
python -m floodbuild web                 # docs/index.html, CSV y signals.json
python -m floodbuild --region 10 all     # todo, para una comunidad
pytest
```

El flujo `mensual.yml` lo hace el día 3 de cada mes y guarda los cambios. Si se corta por tiempo, el siguiente sigue donde se quedó.

## Datos que se guardan

| Fichero | Contenido |
|---|---|
| `data/counts/{oficina}/{municipio}.csv` | Edificios por clase de zona y año de construcción: total, con reforma aparente, residenciales, viviendas y posteriores al primer mapa |
| `data/counts/manifest.json` | Por municipio catastral: nombre, código INE asignado, fecha del fichero del Catastro, edificios y huella de los mapas usados |
| `docs/edificios-municipios.csv` | Una fila por municipio INE con edificios en zona inundable: totales por clase, desde 2017, ritmos y partes antes y después |
| `docs/edificios-anuales.csv` | Por municipio INE, clase y año de construcción |
| `docs/summary.json` | Cifras de cabecera, periodos y resumen de los mapas |
| `docs/signals.json` | Señales para Estado de las IBA (contrato de `estado-iba/CONTRATO.md`, tipo `flood_building`, precisión `municipio`) |

No se guarda ningún edificio uno a uno, ni referencias catastrales, ni direcciones.

## Fuentes y licencias

- Zonas inundables: [SNCZI](https://www.miteco.gob.es/es/agua/temas/gestion-de-los-riesgos-de-inundacion/snczi.html), Ministerio para la Transición Ecológica y el Reto Demográfico, servicio WFS `gis.miteco.gob.es/geoserver/agua/wfs`. Reutilización libre citando la fuente.
- Edificios: [Catastro INSPIRE](https://www.catastro.hacienda.gob.es/webinspire/index.html), Dirección General del Catastro, servicio ATOM de edificios. Reutilización libre citando la fuente.
- Municipios: [es-atlas](https://github.com/martgnz/es-atlas), a partir de datos del Instituto Geográfico Nacional.
- El código de descarga del Catastro parte del de [observatorio-alegaciones](https://github.com/Asensio94/observatorio-alegaciones) (copiado, no importado).

Código bajo licencia MIT. Recuentos propios bajo CC BY 4.0.

Forma parte de un conjunto de proyectos hermanos: [Observatorio de alegaciones](https://asensio94.github.io/observatorio-alegaciones/), [Vigía de incendios](https://asensio94.github.io/vigia-incendios/), [Centinela Natura](https://asensio94.github.io/centinela-natura/), [Vigilancia de humedales](https://asensio94.github.io/vigilancia-humedales/), [Sub Nocte](https://asensio94.github.io/sub-nocte/), [Riesgo de tendidos para aves](https://asensio94.github.io/riesgo-tendidos-aves/), [Grafo de promotores](https://asensio94.github.io/grafo-promotores/), [Cartera de las cotizadas](https://asensio94.github.io/cartera-cotizadas/), [Cuaderno de campo](https://asensio94.github.io/cuaderno-campo/), [Caudal ecológico](https://asensio94.github.io/caudal-ecologico/), [Estado de las IBA](https://asensio94.github.io/estado-iba/) y [Barbechos y aves esteparias](https://asensio94.github.io/barbechos-esteparias/).
