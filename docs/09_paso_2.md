# Paso 2 · arreglos de bajo riesgo y ahorro · 10/11/2026

ADELANTE de la casa del 10/11/2026 al «paso 2» del programa de identificación. Versión
`catalogador-0.5.0` (la etiqueta la pone el orquestador tras el ADELANTE). Punto de partida, medido
hoy con las 35 fichas reales del NAS: **0,244 € por obra, 29 de 35 con fase B**. Las pruebas, en
`pruebas/test_paso_2.py`, sin API ni web: el agente y el cliente son dobles.

## D-1784 · La serie, en la grafía de la web

**Qué.** El valor de la serie es el rómaji del modelo con las vocales largas en circunflejo (ā→â,
ī→î, ū→û, ē→ê, ō→ô, y sus mayúsculas; un macrón suelto, U+0304, también, porque antes se compone con
NFC). Sin rómaji, el castellano; sin castellano, el japonés. El `detalle` de la serie en
`fichas.jsonl` pasa a «japonés · castellano · lámina N», los que haya y sin repetir el valor. El
título no cambia: castellano primero.

**Por qué.** La web escribe «Edo meishô zue» y CATALOGADOR proponía «Vistas de lugares famosos de
Edo». Medido hoy en la base del NAS: de 176 series japonesas con vocal larga marcada, 129 van con
circunflejo y 47 con macrón.

**Dónde.** `ficha.valor` y `ficha.detalle_serie`. Lo usan `para_web`, `fichas.jsonl` (valor y
detalle), el CSV de `exportar` y `revision.py`. `medir.comparar` ya prefería el rómaji. La memoria de
series guarda castellano, japonés y rómaji, como antes.

**Pruebas.** Rómaji con macrón → circunflejo (las diez vocales y el macrón suelto); sin rómaji →
castellano; sin los dos → japonés; el detalle con las tres partes; `para_web`, `fichas.jsonl` y el
CSV. En `test_v4.py`, `para_web` ahora espera «Hauta tora no maki» y no el castellano.

## D-1785 · «aplazada», una vez por racha

**Qué.** El servicio no escribe «aplazada» si la última línea que **este proceso** escribió de esa
petición ya es «aplazada» (un diccionario en memoria). Tras reiniciar el contenedor se escribe una
vez más, y da igual: el Gestor la junta con la racha.

**Por qué.** Escribía una línea cada 15 s por petición fuera de hora: el `estado.jsonl` del NAS ya
tiene 74.125 líneas y 10 MB. El Gestor solo usa la primera línea de cada racha (`leer_estado` y
`_estado_segun` de su `modulos/identificacion/api.py`, D-1009 y D-1011 del Gestor), así que no le
cambia nada. Lo que ya hay en el fichero se queda: solo crece (contrato).

**Pruebas.** Cinco vueltas fuera de hora → una sola línea; al entrar en hora sigue con `leyendo`,
`identificando` y `lista` como siempre; otra línea en medio abre una racha nueva y vuelve a escribirla;
otro proceso escribe una más. En el flujo real una petición solo sale de «aplazada» para hacerse, así
que la racha nueva de verdad es la del reinicio. En `test_servicio.py` ahora son dos «aplazada» (una
por proceso), no tres.

## D-1786 · El horario de inicio

**Qué.** `--desde HH:MM` en `servicio.py` y en `catalogador.py catalogar`. Fuera de hora es antes de
`--desde` o de `--hasta` en adelante; si `--desde` va después de `--hasta`, la ventana cruza la
medianoche; sin `--desde`, como antes. Una hora que no es HH:MM no deja arrancar (lo dice argparse).
La línea «aplazada» dice el horario: «fuera del horario 06:00–13:00».

**Por qué.** Solo había hora tope: a las 00:00 volvía a trabajar (en el NAS intentó a las 23:00:26Z,
las 00:00 de Madrid). `docs/05` y `docs/07` prometían 06:00–13:00, por ukiyo-e.org y por el trabajo
del NAS de madrugada.

**Pruebas.** Bordes 05:59, 06:00, 12:59 y 13:00; las 00:00; una ventana 22:00–06:00; sin `--desde` y
solo con `--desde`; el servicio lanzado con `--desde` a las 05:00 deja «aplazada» con el horario; una
hora mala no arranca; `catalogar --desde` se lee.

## D-1787 · La serie conocida que manda el Gestor

**Qué.** `servicio.serie_conocida` la valida en la frontera: texto, con los espacios y saltos de
cualquier clase juntados en uno, de 1 a 200 caracteres y sin caracteres de control ni de formato
(categoría Unicode C). Si no vale, se ignora y la petición sigue. `agente.catalogar` la añade al primer
mensaje entre comillas de JSON, como **dato a comprobar** contra la estampa, no como instrucción: si no
cuadra, que lo diga; por sí sola no sube nivel ni confianza (la fiabilidad la sigue calculando el
código). La orden `catalogar` no la manda: las mediciones son ciegas.

**Por qué.** El Gestor ya la escribía en `cola.jsonl` y CATALOGADOR la ignoraba. D-991 del Gestor
permite que salga hacia la API la serie conocida si una persona la escribió.

**Pruebas.** El bloque sale, una vez y entre comillas, con una serie válida; no sale con nula, vacía,
solo espacios, un número, más de 200 caracteres, un carácter de control o sin la clave, y la petición
termina igual.

## D-1788 · La caché de la conversación

**Qué.** Antes de cada llamada, `cache_control: {"type": "ephemeral"}` en el último bloque del último
mensaje de usuario, y se quita del anterior. Con el del sistema son dos puntos de los cuatro que admite
la API. Solo en los mensajes de usuario, que son dicts nuestros; los del asistente son objetos del SDK
y no se tocan.

**Por qué.** Cada vuelta reenvía todo el historial (fotos, OCR, resultados de herramientas) y solo el
sistema iba en caché. Con el punto que avanza, lo anterior se lee de caché (0,10 × la entrada) y solo
lo nuevo se escribe (1,25 ×). El ahorro no está medido: se verá en `uso.cache_leida` y `coste_eur` de
`resultados/servicio/*.json` en la próxima tanda.

**Documentación** (context7, `/anthropics/anthropic-sdk-python`): `cache_control` crea un punto de
caché en el bloque que lo lleva («Create a cache control breakpoint at this content block»), y lo
admiten `TextBlockParam`, `ToolResultBlockParam`, las imágenes y las herramientas; `type: "ephemeral"`,
con `ttl` de 5 minutos por defecto. Hay también un `cache_control` de primer nivel en
`messages.create` que lo pone solo en el último bloque cacheable; no se usa, porque el encargo pide el
punto explícito y probado. Lo que context7 **no** confirmó: cuántos bloques mira la API hacia atrás
para encontrar el prefijo anterior. Si una vuelta añade muchos bloques y no lo encuentra, lo escribe
entero (techo apuntado con `ponytail:` en `agente.py`); si pasa, se deja también el punto anterior
(tres de cuatro). Al pasar a la fase B cambian las herramientas y esa vuelta escribe la caché de nuevo.

**Pruebas.** Con un cliente doble que guarda lo enviado: en cada una de las cuatro llamadas (herramienta,
pausa, herramienta, final) hay exactamente un `cache_control` en los mensajes, en el último bloque del
último mensaje de usuario, y uno en el sistema; en la última está en el resultado de la segunda herramienta.

## Lo que no se hace ahora

- **Un modelo más barato para las hojas hermanas**: se mide primero.
- **Reducir las fotos**: la API ya las reduce a 1.568 px de lado mayor.
- **Agrupar por parecido visual**: es el paso 3.
- **Precios**: paso 5.

## El contrato

No cambia el formato: las mismas claves en los ficheros del intercambio, y ninguna nueva. Cambian
dos textos: el valor y el detalle de la serie, y el detalle de «aplazada» («fuera del horario
06:00–13:00» en lugar de «pasada la hora límite 13:00»). `contratos/intercambio/LEEME.md` no se toca:
su «`aplazada` (pasada la hora límite)» se queda corto ahora que también se aplaza antes de las 06:00.
Si se cambia, en las dos copias a la vez y por el orquestador del Gestor.

## Cómo se despliega en el NAS

1. Una persona pone al día la carpeta del código de CATALOGADOR con `catalogador-0.5.0`.
2. En el `.env` de CATALOGADOR, si se quiere otra hora de inicio, la línea `CATALOGADOR_DESDE=06:00`
   (sin ella, el compose ya usa las 06:00). El `.env` lo edita la casa.
3. Container Manager → proyecto **catalogador-jap** → Detener → Construir (rehace la imagen con el
   código y el `docker-compose.yml` nuevos, que traen `--desde ${CATALOGADOR_DESDE:-06:00}`) → Iniciar.
   Los volúmenes `catalogador_datos` y `catalogador_resultados` **no se tocan**: ahí están la
   biblioteca, la memoria de series, `servicio.json` y la caché de ukiyo-e.org.
4. Comprobar en el registro la línea `cola: … · fotos: …`, y fuera de las 06:00–13:00 una sola línea
   «aplazada» por petición en `estado.jsonl`, con «fuera del horario 06:00–13:00», y no una cada 15 s.
