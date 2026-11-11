# Fuentes, ejemplar de referencia, cuadros de texto, tirada, índice del taller y series juntas · 11/11/2026

**Propuesta, sin desplegar y sin ADELANTE.** Rama `propuesta/fuentes-cuadros-series`, sobre `main`
(`b54a921`, la 0.6.1). La escribió la sesión del PC del taller a petición de la casa del 11/11/2026;
no la ha revisado nadie más. Las decisiones van como **P-1 a P-9**: el número D- lo pone el
orquestador si la casa da el ADELANTE. No toca `ficha.fiabilidad` (D-1842, en `parche/fiabilidad`).
Pruebas: de 121 a 142, sin API ni red (`pruebas/test_fuentes_cuadros_series.py` y `pruebas/conftest.py`).

## Lo que pidió la casa (11/11/2026)

> «El sistema de catalogación debe poder acceder a las estampas; que compare si tiene los mismos
> componentes de texto, los sellos de los censores, de los editores, de los autores. Revisa las fuentes y
> añade las que consideres: poder acceder a las fuentes es imprescindible para confirmar la información. El
> análisis en grupo de estampas de la misma serie es muy importante; consolidar series conjuntas y ver
> qué tenemos. Muchas veces, al no tener los sellos de los censores, son reediciones. Tener los cuadros de
> texto identificados ayuda a los revisores; y una base interna que compare firmas, sellos y cuadros. El
> OCR de la Biblioteca Nacional de Japón para caracteres antiguos hay que usarlo.»

## De dónde se parte: la ronda de 30 del 06/11

30 estampas japonesas al azar pedidas desde el Gestor: 30 fichas, ningún error, 7,26 € (0,24 € por obra).
Frente a lo que decía el Gestor: el autor coincide en 24, difiere en 2 y el catalogador no se atreve en 4.
Lo que esas fichas enseñan y motiva esta propuesta:

- En la ficha de TDP-008198 el modelo escribe «No he podido comparar su imagen con la foto»: abría la
  ficha de ukiyo-e.org, que es texto, y **nunca veía el ejemplar de referencia**.
- Las seis hojas de «Edo meishō zue» identificadas dicen «sin sello visible» y «editor no visible en la
  foto», y aun así salen fechadas en 1861–1862 con fiabilidad alta, por la ficha de un museo. El ejemplar
  de referencia sí los lleva (en Japan Search: censura `酉十二改`, editor `藤けい`, grabador `彫兼`). O a las
  del taller les falta el margen, o son otra tirada: **nadie lo decía**.
- El OCR de la NDL lee la foto entera una vez, y lo que lee no llega a quien revisa.
- Cada hoja se identifica sola; solo se juntan las que el Gestor manda en un grupo con serie conocida.

## P-1 · Fuentes abiertas con API (`museos.py`)

**Qué.** Tres fuentes nuevas, consultadas por su API pública, con caché en disco para siempre, una
petición cada 2–4 s por servidor, tope de 300 al día por servidor y parada hasta el día siguiente ante
403, 429 o 5xx (las reglas de `ukiyoe.py`):

| Fuente | Qué da | Cómo se busca |
|---|---|---|
| **Japan Search** (jpsearch.go.jp, NDL): colección digital de la NDL, ColBase, Biblioteca Metropolitana de Tokio, ADEAC y los metadatos del portal de nishiki-e | autor, **editor**, fecha con mes; en la ficha, **firma, grabador, sello de censura y el texto de la imagen** del ejemplar | en japonés, con el título de la serie y de la lámina tal como se leen en los cartuchos |
| **Art Institute of Chicago** (api.artic.edu) | título con serie, autor, fecha, inscripciones, medidas, imagen de dominio público | inglés o rómaji |
| **Cleveland Museum of Art** (openaccess-api) | lo mismo | inglés o rómaji |

Herramientas del agente: `fuentes_buscar` (4 por obra) y `fuentes_ficha` (3). Una ficha abierta cuenta
como fuente «abierta» en `fuentes_verificadas`; un resultado de búsqueda, como «solo buscador».

**Comprobado en vivo el 11/11/2026.** `japan_search "江戸名勝図会 浅草寺"` devuelve la misma lámina que
TDP-008198 con «広重〈2〉 · 藤岡屋 慶次郎 · 1861 · 文久01», y su ficha trae `firma: 広重画`, `grabador: 彫兼`,
`sello_de_censura: 酉十二改`. El Met queda fuera: su búsqueda nueva (v1.1) casi no encuentra estampas por
serie; se sigue llegando a él por la web de la fase B.

**La base del ARC.** Sus páginas (dh-jac.net) siguen sin abrirse (P-10 del piloto: sin permiso). Lo que
entra son los metadatos que el ARC entrega a Japan Search y que Japan Search publica por su API; el
enlace que se cita es el de Japan Search. Es la fuente que da editor, grabador y sello de censura.
**Decide la casa**: si no lo quiere, `TDP_JPS_SIN_ARC=si` en el `.env` los deja fuera (probado).

**Catálogos de un artista.** La fase B recomienda además los catálogos en línea con las series lámina a
lámina: hiroshige.org.uk, kuniyoshiproject.com, kunisada.de y yoshitoshi.net (en pie el 11/11/2026;
kunisada.de solo por http).

**Censores.** `censor.py` gana las fechas de cada nanushi solo (1842–1846) y de cada pareja (1847–1853),
de Illing (1980) tal como las publica la página del MIT: `datar_censor` con 村 y 衣笠 daba 1847–1852 y
ahora da 1851–1852. Si la pareja no cabe en el tipo de sello, lo dice.

## P-2 · El ejemplar de referencia (`ver_referencia`)

**Qué.** `ukiyoe_ficha` devuelve ahora la dirección de la imagen de la ficha; las fuentes nuevas, la suya.
`ver_referencia` (2 por obra) baja esa imagen, la reduce a 1.200 px y se la enseña al modelo junto a la
foto del taller, con el encargo de comparar composición, cartuchos, firma, sello de editor, sellos de
censura y de fecha, y márgenes. El prompt prohíbe decir «misma estampa» sin esa comparación.

**Qué se permite.** Solo imágenes de los servidores de las fuentes (lista cerrada en
`museos.SERVIDORES_DE_IMAGEN`), por https y sin `/uploads/`. `robots.txt` de ukiyo-e.org y de
data.ukiyo-e.org, leídos el 11/11/2026, solo prohíben `/upload/` y `/uploads/`. La foto del taller no se
sube a ningún sitio: la comparación la hace el modelo en la misma conversación de siempre.

## P-3 · La tirada: ¿de época, posterior o reproducción? (`ficha.edicion`)

**Qué.** El modelo devuelve `edicion` (`estado`, `indicios`, `referencia_comparada`, `como`) y dice en el
editor y en el censor si el sello **se ve** en la foto (`sello_visible`). El código, con reglas fijas y
sin fiarse del modelo, añade `avisos`:

- hoja de venta pública (suelta, díptico, tríptico) fechada entre 1790 y 1875 sin sello de censura a la
  vista: «margen recortado, tirada posterior o reproducción»;
- sin sello del editor a la vista;
- sin sello ni fecha: no se puede situar.

Una página de libro, un surimono o una estampa posterior a 1875 no avisan. El aviso va al final del
`detalle` del censor, que el Gestor ya enseña en su pantalla de revisión, así que **se ve desde el primer
día sin tocar el Gestor**; la `lectura` del sello no se toca.

**Lo que no hace.** No baja la fiabilidad de la fecha: esa regla es de D-1842 y de la casa. Con las
fichas ya entregadas (sin `sello_visible`) se deduce de la caja y de la lectura.

## P-4 · Los cuadros de texto, para quien revisa (`ficha.textos`)

**Qué.** El modelo devuelve la lista de cuadros de la foto: tipo (firma, sello de artista, cartucho de
serie, cartucho de título, sello de censura, sello de fecha, sello de editor, grabador, estampador, actor,
poema, inscripción), lectura en caracteres, rómaji, traducción y caja. El código los sanea, y **añade
detrás los bloques que leyó el OCR de la NDL y el modelo no recogió**, para que no se pierda ninguno.
Van numerados en `textos` y dibujados en `anotadas/<id>_textos.jpg`, cada uno con el color de su dato.

**El OCR de la NDL**, además: `ampliar` acepta `ocr: true` y devuelve, con el recorte, lo que NDL古典籍
OCR-Lite lee en él (4 recortes por obra: en el NAS cada lectura son segundos de CPU). Está pensado para
cartuchos, poemas e inscripciones; en sellos no lee.

## P-5 · El índice del taller (`indice.py`)

**Qué.** Cada firma, sello y cartucho de cada propuesta entra en `datos/indice/` con su recorte, marcado
«sin confirmar»; lo que una persona acepta o corrige en el Gestor lo confirma y lo rechazado se retira.
El agente pregunta primero ahí (`buscar_en_indice`, 6 por obra; 3 en la pasada corta de una hermana).
`python indice.py galeria` hace una página con todos los recortes por tipo y por autor, editor o serie.

**Cómo busca, y lo que se midió.** Por lo que dice el cuadro (caracteres en común, con las formas antiguas
igualadas) y, en cartuchos y sellos, por la forma de la tinta (HOG, en CPU, sin modelos). Con las 118
entradas reales del NAS:

| | pares iguales | pares distintos (p95) | ¿el más parecido es su hermana? |
|---|---|---|---|
| sellos de editor | 0,60 | 0,51 | 2 de 2 |
| cartuchos de serie | 0,62 | 0,51 | 4 de 6 (AUC 0,66) |
| firmas | 0,21 | 0,43 | 8 de 18 (AUC 0,45: como el azar) |

Se probó antes con puntos ORB y no casa nada: cada hoja se talla de nuevo y dos cartuchos de la misma
serie no son la misma imagen. **La forma es una pista para cartuchos y sellos y no se usa en firmas**; las
firmas se buscan por lo que dicen. Un modelo de imagen (DINOv2) lo haría mejor, pero hay que bajarlo
(unos 90 MB) y añadir onnxruntime al contenedor: **no se ha hecho, lo decide la casa**.

**D-1840.** `buscar_en_indice` devuelve qué es, qué dice, de quién es, en cuántas hojas y si está
confirmado. Nunca una referencia, un id de petición ni un id de entrada (probado). La referencia de la
obra que se cataloga se usa dentro, para que no se encuentre a sí misma, y no sale.

## P-6 · Las series juntas (`series.py`)

**Qué.** Junta las hojas de cada serie por su título japonés (圖會 y 図会 son lo mismo) o, si no lo hay,
por el título sin tildes ni macrones; de cada obra vale su última propuesta. Dice el autor, el editor y
los años que salen entre todas, y **lo que desentona**: otro autor (Kunisada no es Kunisada II), otro
editor, una fecha lejos de las hermanas, una hoja sin el sello de censura que las demás llevan, o que
ninguna lo enseña. Con `--gestor` (un CSV `referencia;serie;titulo;artista;anio;editor`) suma las obras
aún sin identificar, y si una obra identificada lleva en el Gestor otro nombre de serie, ese nombre hace
de puente. El servicio reescribe `resultados/series.md` cuando cambia algo.

**Con los datos de hoy** (524 estampas japonesas del Gestor y las 47 propuestas del NAS): «Edo meishō
zue», 54 hojas y 6 identificadas, ninguna con sello a la vista; «Tōkaidō gojūsan tsugi no uchi» de
Kunisada, 29 hojas con cuatro editores (es una serie de varios editores: el aviso es informativo);
«Kannon reigenki», una hoja atribuida a Kunisada y otra a Kunisada II; «Hauta tora no maki», el editor
del catalogador (Etsuka) no es el del Gestor (Ōmiya), que es la discrepancia de `docs/05`.

## P-7 · El contrato

Tres campos **opcionales** en la línea de `fichas.jsonl`: `textos`, `edicion` y `anotada_textos`; y un
fichero más, `anotadas/<id>_textos.jpg`. El Gestor de hoy los ignora (lee solo sus claves:
`modulos/identificacion/api.py`, `leer_fichas`), y la línea sigue muy por debajo de sus 200.000
caracteres. **Se ha tocado la copia del contrato de este repositorio** (`contratos/intercambio/LEEME.md`
y el ejemplo `de_catalogador/fichas.jsonl`), porque `test_servicio.py` exige las mismas claves que el
ejemplo: la copia del Gestor tiene que recibir lo mismo, y eso lo hace su orquestador. Cambia un texto:
el `detalle` del censor puede acabar en «AVISO de tirada: …».

## P-8 · Lo que sale hacia fuera (ARQUITECTURA §8 r.4, D-991, D-1840)

- **Hacia la API**: lo de antes y, nuevo, los resultados de las fuentes abiertas, la imagen del ejemplar
  de referencia y lo que devuelve el índice (lecturas y nombres que salieron del modelo o que una persona
  confirmó: como la biblioteca, D-1768). Ninguna referencia. La guardiana de D-1840 sigue en verde.
- **Hacia las fuentes**: las consultas que escribe el modelo (título de serie, artista), como ya pasa con
  ukiyo-e.org. Nunca una foto ni un dato de la casa.
- **Para el orquestador**: que quede escrito si los metadatos del ARC vía Japan Search y lo «sin
  confirmar» del índice entran en la excepción.

## P-9 · Pruebas reescritas por especificación

Una aserción de `test_hermanas.py` (los topes de la pasada corta, que eran un diccionario exacto): ahora
incluye las cuatro herramientas nuevas (índice 3; fuentes y referencia 0). El ejemplo del contrato gana
los tres campos. Las ratifica la casa con el ADELANTE.

## Coste

Sin medir: no se ha llamado a la API. Lo que añade por obra: hasta dos imágenes de referencia (unos
1.500 tokens de entrada cada una), la lista `textos` y `edicion` en la salida (unos 600–900 tokens), y
los resultados de las fuentes. Estimación: de 0,24 € a 0,27–0,30 € por obra completa. Lo que puede
ahorrar: el índice y Japan Search resuelven antes lo que hoy lleva a la fase B (29 de 35 la pedían).
**Se mide con una tanda de 10 antes de dar nada por bueno.**

## Lo que no se hace ahora

- Bajar un modelo de imagen para el índice (arriba).
- Que el Gestor enseñe `textos`, la foto numerada, la tirada y las series: es de IDENTIFICACION.
- Bajar la fiabilidad de una fecha sin sello a la vista: es de la casa.
- OCR de la segunda foto: es el reverso.

## Cómo se despliega (si hay ADELANTE)

Como la 0.6.1. No hay dependencias nuevas ni cambios en el `Dockerfile` ni en el compose. Los volúmenes
se conservan; `datos/indice/` y `datos/museos_cache/` nacen solos en `catalogador_datos`. Para estrenar el
índice con lo ya entregado, una vez, en la terminal del contenedor:

```bash
python indice.py reconstruir --fichas /intercambio/de_catalogador/fichas.jsonl --cola /intercambio/para_catalogador/cola.jsonl --imagenes /imagenes
```
