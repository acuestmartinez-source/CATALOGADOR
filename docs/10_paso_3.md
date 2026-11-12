# Paso 3 · la pasada corta de las hermanas de un grupo · 10/11/2026

ADELANTE de la casa del 10/11/2026 al «paso 3»: «CATALOGADOR identifica a fondo la primera hoja y las
demás con una pasada corta». Ese mismo día la casa pidió también consumo mínimo. Versión
`catalogador-0.6.0` (la etiqueta la pone el orquestador tras el ADELANTE). Las pruebas están en
`pruebas/test_hermanas.py`, sin API ni web: el agente y el cliente son dobles. Pasan de 92 a 112.

El punto de partida es el de `docs/09_paso_2.md`, medido con las 35 fichas reales del NAS:
**0,244 € por obra y 29 de 35 con fase B**. Hasta ahora, en un grupo no se hacía nada especial entre
la primera hoja y las demás:

- cada hoja era una conversación propia, con la fase A completa y, si la pedía, la B;
- la memoria de series solo ayudaba si el OCR leía entero el título japonés de la serie;
- una serie sin título japonés no se guardaba nunca.

## D-1798 · La pasada corta

**Cuándo.** Una hoja va corta solo si se cumplen las dos condiciones:

1. su petición trae `serie_conocida` válida (D-1787);
2. **este proceso** ya documentó otra hoja del mismo `grupo` **y con la misma `serie_conocida`**.
   Hace falta la pareja, no basta el grupo: el Gestor da un `grupo` a cualquier petición de más de
   una obra, también a las marcadas a la vez en la rejilla, y si no se le da una serie para todo el
   grupo, cada línea lleva la `serie_literal` de su propia obra (su `modulos/identificacion/api.py`).
   Un grupo puede mezclar series, y una obra de otra serie del mismo grupo va completa.
   Documentada quiere decir:
   - serie con confianza alta y nivel entre los cinco primeros, la misma selección de la memoria de
     series pero sin exigir los caracteres japoneses (`ficha.hermana_de`);
   - y autor publicable (fiabilidad alta o media). Sin autor no hay nada que confirmar, y una pasada
     sin ukiyo-e.org ni web dejaría el autor sin buscar.

Se guarda la primera hoja que cumple de cada pareja (grupo, `serie_conocida`); las siguientes no la
sustituyen. Vive solo en memoria (`Servicio.primeras`). Si el servicio se reinicia a medio grupo, las hojas que faltan van completas:
es seguro, solo que no ahorra.

**Qué se le pasa.** Va en un solo bloque del primer mensaje:

- `texto_memoria` de la primera hoja: serie en japonés, rómaji y castellano, autor, editor y su
  sello, fecha, «ya catalogada en N hojas de esta serie» (sin sus referencias desde la 0.6.1, D-1840)
  y hasta cinco fuentes;
- la frase de la pasada corta: confirma en la estampa autor, serie, editor y sello; no busques en
  ukiyo-e.org ni en la web; identifica el título y el número de lámina de ESTA hoja; si algo no
  cuadra, dilo en el `como` y deja la confianza en media o baja.

Todo sale de lo que el modelo devolvió en la primera hoja. No lleva precios, ubicaciones, procedencia
ni personas (D-991 del Gestor). `hermana_de` copia solo campos con nombre, y la prueba lo comprueba
con una ficha manchada a propósito. El prompt del sistema no cambia, así que su caché sigue valiendo.

**Qué se salta.**

| | Completa | Corta |
|---|---|---|
| Fase B (web) | si la pide | nunca (`con_web=False`) |
| `ukiyoe_buscar` / `ukiyoe_ficha` | 3 / 4 | 0 / 0 |
| `ampliar` | 10 | 4 |
| `buscar_firma` / `buscar_sello_editor` | 5 / 6 | 2 / 2 |
| `datar_censor` | 3 | 1 |
| Vueltas (peticiones a la API) | 30 | 8 |

Las herramientas de ukiyo-e.org siguen en la lista, con tope 0: si el modelo las pide, recibe
«agotado el tope». Así la lista de herramientas es la misma que en la primera hoja, y las
herramientas y el sistema se leen de caché. El resultado lleva `fases: "A corta"`. El modelo no
cambia: sigue siendo el de siempre.

**Por qué.** Lo caro de una hoja es la fase B (29 de 35 la pidieron) y las vueltas de búsqueda. Las
hermanas comparten autor, serie, editor y casi siempre fecha. Saltarse ukiyo-e.org en ellas ayuda
también con su límite real: 400 peticiones al día y entre 20 y 35 s por petición (`docs/05`), unas
80 obras al día. Nada se aplica solo: la persona sigue revisando la propuesta en IDENTIFICACION.

**Dónde.**

- `ficha.hermana_de`, que también usa ahora `recordar_serie` (esa sí exige el título japonés);
- `agente.catalogar(..., hermana=...)`, con `TOPES_HERMANA` y `MAX_VUELTAS_HERMANA`;
- `servicio.Servicio.una` y `Servicio.primeras`.

En seco (`--en-seco`), el servicio dice qué hermanas irían cortas (véase «Cómo medir el ahorro»).
La orden `catalogar` (las mediciones ciegas) no cambia.

**Pruebas.**

- La segunda hoja de un grupo con serie conocida y primera documentada (con y sin título japonés) va
  corta: lleva la memoria de la primera y cuesta solo la corta. Un autor que solo cambia en
  mayúsculas o espacios no es contradicción.
- En el agente, con la misma conversación: con hermana no hay fase B, ukiyo-e.org no se llama y el
  segundo censor se rechaza; sin hermana hay B, ukiyo-e.org y dos censores. La pasada corta para a
  las 8 vueltas.
- Va completa en cada uno de estos casos:
  - sin serie conocida;
  - serie de la primera no alta;
  - serie de nivel bajo;
  - primera sin autor publicable;
  - primera sin JSON;
  - hoja de otro grupo;
  - hoja del mismo grupo con otra `serie_conocida` (también en seco);
  - tras reiniciar el servicio.
- El bloque de la hermana no lleva precio, importe, ubicación, planero, cajón, procedencia,
  comprador, cliente, propietario, teléfono ni correo, aunque la ficha de la primera los trajera.
  `pedido_por` no llega a la API.
- De punta a punta, con el `catalogar` de verdad y un cliente doble: «A» en la primera y «A corta» en
  la segunda.

## D-1799 · La vuelta a la pasada completa

**Qué.** Tras la pasada corta, `ficha.contradice` hace una comprobación fija, sin volver a preguntar
al modelo. La hoja se repite completa (sin hermana, con todo lo demás igual) si pasa cualquiera de
estas cosas:

- no hay JSON;
- el autor no coincide con el de la primera, comparando los dos normalizados: sin acentos, en
  minúsculas y con los espacios juntados;
- la serie no tiene confianza alta;
- `buscar_mas` trae algo.

Al repetirla:

- `coste_eur` suma las dos pasadas, también en `fichas.jsonl`, porque las dos se pagaron;
- `fases` es el de la completa;
- `estado.jsonl` lleva otro «identificando», el de la pasada completa, para que el Gestor no siga
  viendo «fase A corta» mientras corre;
- `resultados/servicio/<ref>.json` guarda la corta en `pasada_corta`, con `motivo`, `coste_eur`,
  `duracion_s` y `uso` (sus tokens). Ese campo no pasa al intercambio.

**Por qué.** Una hermana que no cuadra no debe quedarse con una ficha a medias. Una regla fija es
barata, se prueba y no depende de otra llamada. El editor y la fecha no se comparan: si no cuadran,
el modelo lo dice en el `como` y baja la confianza, y la fiabilidad la calcula el código como siempre.

**Pruebas.** Cada motivo (autor, serie, `buscar_mas`, sin JSON) hace:

- tres llamadas: la primera hoja, la hermana corta y la misma hermana completa;
- 0,41 + 0,10 = 0,51 € en la ficha;
- la ficha de la pasada completa;
- `pasada_corta` con su motivo y su `uso`;
- un último «identificando» sin «corta».

## Cómo medir el ahorro

**Sin gastar nada.**

1. En seco, sobre la cola que se vaya a lanzar:

   ```bash
   ./.venv/Scripts/python.exe servicio.py --intercambio <carpeta> --en-seco --una-vez
   ```

   Cada hermana que iría corta lo dice: «se haría con N foto(s), corta si la primera del grupo sale
   documentada». En seco no hay API, así que da por documentada la primera de cada grupo y serie. La cifra
   es, por tanto, el techo del ahorro, no el ahorro.
2. Lo ya pagado: los `resultados/servicio/*.json` del volumen `catalogador_resultados`, que se leen
   en su sitio. Cada uno dice cuánto costó la obra (`coste_eur`), si hubo fase B (`fases`), cuántas
   veces se usó cada herramienta (`usos`) y cuántos tokens (`uso`).
3. Multiplicando el número de hermanas por lo que una completa gastó en fase B y en ukiyo-e.org sale
   una estimación. No es una medida.

**La medida de verdad, con gasto y con un tope que tiene que autorizar la casa.**

- **Muestra.** Un grupo real de 3 a 5 hojas de una serie ya documentada por la web o por una persona,
  con su `serie_conocida`. El orquestador escribe la cola en una carpeta de intercambio de prueba,
  nunca a partir de una copia de la base. Las fotos se leen de `Z:\IMAGENES` en solo lectura.
- **Dos brazos**, cada uno con su propia copia del código y su `datos/` vacía, para no compartir
  `servicio.json` ni la memoria de series, y con el mismo modelo:
  - (a) `catalogador-0.5.0`: todo completo;
  - (b) `catalogador-0.6.0`: la primera completa y las demás cortas.
- **Qué se compara, hoja a hoja:**
  - `coste_eur` y `duracion_s`;
  - cuántas se repitieron, y por qué (`pasada_corta.motivo`);
  - autor, serie, editor y fecha de (b) frente a (a) y frente a la web;
  - las fuentes en «nunca vista» (véase abajo).
- **Tope propuesto: 4 €.** Es una estimación, no una medida. A 0,244 € por obra, el brazo (a) con 5
  hojas sale hacia 1,2 €, y el (b) debería salir por menos; los 4 € dejan margen para las fases B y
  las repeticiones. No se lanza nada hasta que la casa lo autorice.

## Lo que no se hace ahora

- **Haiku en las hermanas.** Irá después, solo con el ahorro medido y con la contradicción como red.
  Antes hay que mirar en la documentación si Haiku admite `thinking: adaptive` y
  `output_config.effort`.
- **Guardar la primera en disco.** Tras un reinicio la hermana va completa: cuesta lo de antes y no
  rompe nada.
- **Las fuentes heredadas.** Las fuentes que la hermana copie de la primera no salieron de ninguna
  herramienta en su propia conversación, así que `verificar_fuentes` las marca «nunca vista». Pasa
  igual con la memoria de series de siempre. Se mira en la medida antes de decidir nada.
- **Comparar el editor o la fecha en la contradicción.** El motivo está en D-1799.

## El contrato

No cambia el formato: ni una clave nueva en el intercambio. Cambian tres textos:

- `fases` puede ser «A corta». El Gestor lo guarda como texto (`fases: str | None` en su
  `modulos/identificacion/api.py`);
- el detalle de «identificando» de una hermana: «fase A corta: lupa, firmas y sellos de la hermana»;
- el de «lista»: «… € · fases A corta».

Si la hoja se repitió, `coste_eur` incluye las dos pasadas. `contratos/intercambio/LEEME.md` no se
toca.

## Cómo se despliega en el NAS

1. Una persona pone al día la carpeta del código de CATALOGADOR con `catalogador-0.6.0`.
2. En Container Manager, proyecto **catalogador-jap**: Detener, Construir e Iniciar. Los volúmenes
   `catalogador_datos` y `catalogador_resultados` **no se tocan**, y el `.env` tampoco.
3. Comprobar en `estado.jsonl`, con el siguiente grupo de serie conocida, que la segunda hoja dice
   «fase A corta: …» y luego «… € · fases A corta», o la suma si se repitió.

## D-1840 · Hacia la API no sale ninguna referencia (catalogador-0.6.1)

**Por qué.** El orquestador del Gestor, el 10/11/2026: la nota D-991 de ARQUITECTURA §8 regla 4 es
una excepción cerrada. Hacia la API sale la fotografía, las medidas y, si una persona la escribió, la
serie conocida, y nada más. `ficha.texto_memoria` escribía «ya catalogada en TDP-…, TDP-…» con las
referencias de las obras donde se documentó la serie. Ese texto llegaba a la API por tres caminos: la
memoria de series de siempre (`agente.catalogar(series=…)`), la pasada corta de una hermana
(`hermana=…`, D-1798) y la orden `catalogar`. Una referencia no está en la lista.

**Qué cambia.**

- `texto_memoria` dice «ya catalogada en 1 hoja de esta serie» o «en N hojas de esta serie». El
  número no es una referencia, y al modelo le basta. Dice «1 hoja» y no «otra hoja» porque, si el
  Gestor vuelve a pedir una obra que ya está en la memoria, esa hoja es la misma.
- La memoria del disco (`datos/series_conocidas.json` y su lista `obras`) no cambia: es local y no
  sale. `ficha.hermana_de` tampoco: su `obras` se queda en el proceso.
- `buscar_firma` y `buscar_sello_editor` devuelven de la biblioteca del taller
  (`confirmadas_por_el_taller`) la lectura, el nombre y el parecido, y ya no la `referencia` de la
  obra en la que una persona confirmó esa firma o ese sello (`agente.ejecutar`, línea 170). Lo que
  devuelve una herramienta va entero a la API como `tool_result`.
- Las fotos se vuelven a codificar antes de salir (`agente.bloque_imagen`, con `imagen.recortar` e
  `imagen.a_bloque`, lo mismo que ya hacía la lupa): salen solo los píxeles, en JPEG de calidad 90,
  sin EXIF, XMP ni IPTC. Tampoco el comentario (el segmento COM de un JPEG o el texto «comment» de un
  PNG): Pillow lo copia en `im.info` al abrir, lo conserva al recortar y lo escribe al guardar, así que
  `a_bloque` guarda una imagen nueva hecha solo de los píxeles (`Image.frombytes`), para la foto entera
  y para la lupa (ronda 3). Antes salían los bytes del fichero tal cual, y con ellos lo que se apuntó
  dentro: titulares con pinta de título, descripciones con el artista, palabras clave, autor y
  derechos, números de serie de la cámara e historial de edición (muestreo de solo lectura de la
  revisión: 74 de 80 fotos de `Z:\IMAGENES\originales` llevan metadatos; ninguna, una referencia).
  Los tokens de imagen no cambian, porque dependen de los píxeles. En otras 80 fotos del almacén
  ninguna lleva orientación EXIF, así que la foto entera y los recortes de la lupa siguen en el
  mismo marco. Pesa algo más: en la muestra, de 0,08–0,52 MB a 0,10–0,72 MB, lejos del tope de la API.
- El servicio deja de mandar las `pistas` de la petición (la URL y la nota que escribió una persona),
  que tampoco están en la lista. Hoy el Gestor las manda siempre vacías (`"pistas": []` en su
  `modulos/identificacion/api.py`), así que en la práctica no cambia nada. El contrato no se toca: el
  campo se sigue leyendo sin error. Las pistas de `piloto/pistas.csv` y de `--pista`, en las órdenes
  `catalogar` e `identificar`, siguen igual: son ficheros y argumentos de quien mide en este PC, no
  una petición del Gestor.
- La serie aceptada o corregida en `aceptadas.jsonl` pasa por el saneado de la `serie_conocida`
  (D-1787: de 1 a 200 caracteres y sin caracteres de control) antes de entrar en la memoria de
  series, porque de ahí vuelve a la API cuando el OCR de otra hoja casa con ella.
- Por lo mismo, al aprender `aceptadas.jsonl` la `lectura` (hasta 40 caracteres), el `nombre` (hasta
  120) y el `tipo` del sello (hasta 40) de `firma_confirmada` y `sellos_confirmados` pasan por ese
  saneado (`servicio.texto_limpio`, el que usa `serie_conocida`), porque vuelven a la API por
  `buscar_firma` y `buscar_sello_editor`. Si la lectura o el nombre no valen, esa firma o ese sello no
  entran en la biblioteca (`desde_aceptada` pide los dos); si no vale el tipo, el sello entra sin tipo
  (ronda 3).
- Las medidas solo salen si son un número: un entero o un flotante finito que no sea booleano
  (`agente.medida`, en `agente.catalogar`, así que vale para el servicio, `catalogar` e `identificar`).
  Si no, «—», lo que ya escribe el código para «sin dato». Antes, un texto que el Gestor pusiera en
  `alto_cm` llegaba tal cual (ronda 3).
- `piloto/prompt.md` y las herramientas no se tocan, así que la caché del sistema sigue valiendo. El
  cambio está en el primer mensaje, que ya cambiaba en cada obra, y en los `tool_result`.

**Lo que se miró.** Cada texto que `agente.py`, `servicio.py` y `catalogador.py` meten en la
conversación:

- `agente.catalogar` (líneas 334 a 353): el sistema, las fotos (sin el nombre del fichero y, desde
  la 0.6.1, sin sus metadatos), el OCR de la foto, la memoria de series, las pistas, la serie
  conocida, el bloque de la hermana y las medidas;
- la fase B (395 a 399), que solo lleva lo que el modelo pidió en `buscar_mas`;
- los resultados de las herramientas (401 a 421): la lupa (recortes vueltos a codificar), la
  biblioteca y las bases públicas de firmas y sellos, `datar_censor` (un cálculo local) y ukiyo-e.org
  (la consulta que escribe el modelo);
- `servicio.Servicio.una` (323 a 332): de la petición pasan las fotos, las medidas y la serie
  conocida. La referencia va en `obra` pero no entra en la conversación; `id_peticion`, `grupo`,
  `pedido_por` y `pedido_en` no salen del servicio;
- `catalogador.catalogar_una` (149 a 152) y `orden_identificar` (229 a 231): la referencia o el
  nombre, solo en `obra` y en el fichero de resultado.

**Lo que quedaba para el orquestador, y cómo quedó (11/11/2026).**

- La biblioteca sigue mandando la `lectura` (hasta 40 caracteres) y el `nombre` (hasta 120) que
  confirmó o corrigió una persona en el Gestor. **Resuelto: la casa lo firmó** («Firmo: la biblioteca
  sale»), y quedó como nota aditiva **D-1768** en ARQUITECTURA §8 regla 4, detrás de D-1789. Además
  de la foto, las medidas y la serie conocida, sale lo que sabe la biblioteca de firmas y sellos: la
  lectura y el nombre del artista o del editor, saneados como en D-1787. Nunca la referencia, ni
  quién confirmó. Queda una cosa por hacer en el próximo parche, para que se cumpla del todo: «saneados
  como en D-1787» hoy solo vale para lo que entra por `aceptadas.jsonl` desde la ronda 3. Las
  correcciones de `biblioteca_correcciones.jsonl` siguen con la regla de D-1221 del contrato, que mira
  el largo pero no los caracteres de control. Y lo que ya estaba en la biblioteca antes de la 0.6.1 no
  se ha vuelto a sanear. Lo más corto es sanear al salir, en `agente.ejecutar`.
- La orden `catalogar` sigue mandando la `nota` libre de `piloto/pistas.csv`. Ese fichero no existe
  hoy ni en `C:/dev/CATALOGADOR` ni en la rama, y es de quien mide, no del Gestor; pero es texto de
  una persona hacia la API. **El orquestador, el 10/11/2026: se cierra**, en el próximo parche y con
  su PARADA.
- La `serie_conocida` que manda el Gestor (`serie_conocida or obra.serie_literal`) cuenta como
  «escrita por una persona» en el sentido de D-991. Es la interpretación **D-1841** (orquestador, 10/11/2026):
  la serie de una ficha la teclea una persona, viene del catálogo de la casa, del gestor antiguo o de
  la tienda (escritos por personas), o la acepta una persona campo a campo y con rastro. Nunca la
  pone una máquina sola.

**Pruebas reescritas por especificación.** Seis aserciones de cuatro pruebas existentes pedían la
`referencia` en `confirmadas_por_el_taller`: `test_biblioteca.py`, líneas 91, 97 y 106
(`test_retirar_no_borra_y_restaurar_la_devuelve`, que buscaba `TDP-008194` en la salida de
`buscar_firma` como señal de que la firma salía o no), 388 (los campos que ve el modelo) y 567, y
`test_servicio.py`, línea 143. Con D-1840 piden lo mismo con el `nombre` («Toyohara Kunichika»,
«editor: Echizenya Kajū») y el conjunto de campos sin `referencia`. Como la de `test_biblioteca.py`
en la 0.5.0, las ratifica la casa con el ADELANTE.

**Prueba.** `pruebas/test_d1840_nada_de_referencias.py`. El cliente doble de `test_paso_2.py` guarda
todo lo que se le pasa a `messages.stream`: modelo, sistema, mensajes, herramientas y el resto de
argumentos. Sobre el `json.dumps` de todo eso, y sobre los bytes de cada foto enviada (el base64
decodificado), la prueba exige que no haya ningún `TDP-` con seis cifras, ningún `idn-` con seis
cifras ni ningún `idn-g-`. De la petición, además, ni `pedido_en`, ni `pedido_por`, ni el nombre de
sus fotos, ni la nota de sus pistas. Las fotos de la prueba llevan una referencia en el EXIF y otra en
el XMP. Los caminos que recorre, con una memoria de series que lleva dos obras TDP:

- el servicio con la primera hoja completa y la hermana corta (D-1798), que además tiene que llevar el
  sello del editor y la fecha de la primera;
- el servicio con la hermana repetida completa tras una contradicción (D-1799);
- `catalogador.catalogar_una`, la medición ciega;
- `buscar_firma` y `buscar_sello_editor` con la biblioteca aprendida de `aceptadas.jsonl`;
- que una serie aceptada con un carácter de control no entra en la memoria;
- la foto entera y la lupa, con un JPEG y un PNG que llevan el comentario `TDP-777777`;
- unas medidas que no son un número («TDP-777777», `true` y `NaN`), que salen como «—», y una buena
  que sale tal cual;
- y una firma y un sello aceptados con un carácter de control en la lectura, otro de formato en el
  tipo, saltos en el nombre y un nombre de 121 caracteres: la firma y el sello largo no entran, y el
  otro entra limpio y sin tipo.

La memoria de series y la hermana corta tienen que llevar, en el mismo texto, el editor («Echizenya
Kajū») y la URL de la fuente de la primera hoja: si se quitan de `ficha.texto_memoria`, tres pruebas
se ponen en rojo (comprobado quitándolos).

Comprueba también que la memoria del disco sigue con sus obras. En la ronda 1, con el código de la
0.6.0, las tres primeras fallaban con `TDP-007001`, `TDP-007002`, `TDP-008194` y la nota de la pista de
la petición. En la ronda 2, con el código de la ronda 1, fallaban las cinco: `TDP-123456` y
`TDP-654321` en los bytes de las fotos, `TDP-008194` en la salida de `buscar_firma` y la serie con el
carácter de control en la memoria. En la ronda 3, con el código de la ronda 2, fallaban siete: el
comentario `TDP-777777` en los bytes de las fotos (las tres de antes y la foto entera y la lupa, en
JPEG y en PNG), las medidas («TDP-777777 × True» y «nan × 24.1») y la lectura con el carácter de
control en la biblioteca. Las pruebas pasan de 112 a 117 en la ronda 2 y a 121 en la ronda 3.

**Despliegue.** Igual que la 0.6.0 (arriba), con `catalogador-0.6.1`. Los volúmenes no se tocan:
la memoria de series que ya hay sirve tal cual.

## D-1843 · La memoria de series aprende lo que confirma una persona (catalogador-0.6.3, 12/11/2026)

La serie se acepta en el Gestor en rómaji («Hauta tora no maki») y la memoria de series se busca por los kanji
del cartucho que lee el OCR. Por eso, hasta ahora, una serie confirmada por una persona no se guardaba nunca
(tenía menos de tres caracteres CJK), y la que se guardaba llevaba el autor, el editor y la fecha vacíos.
Desde la 0.6.3, `servicio._aprender_una`:
- toma los kanji de la ficha que se propuso (`resultados/servicio/<referencia>.json`), pero solo si la persona
  aceptó la serie tal cual o la corrigió a lo mismo; si la corrigió a otra serie, se guarda como antes;
- guarda con la serie el autor, el editor y la fecha que la persona aceptó o corrigió;
- y lo que confirmó una persona pisa lo que la memoria había aprendido de una máquina
  (`ficha.recordar_serie(..., pisar=True)`); lo de la máquina sigue rellenando solo huecos.
Descarta: pedir al Gestor que mande los kanji (cambiaría el contrato `aceptadas.jsonl`).
Ronda 2 de la revisión (NO APTO): el fichero de la propuesta va por obra y puede ser de otra petición; ahora
los kanji solo se toman si lo aceptado dice lo mismo que lo propuesto (normalizado y no vacío), también cuando
la persona «aceptó». El castellano bueno de la memoria ya no se pisa con el rómaji. Lo que vuelve a la API sigue
D-1768 (el nombre del artista y del editor confirmados, saneados); **la fecha confirmada (años) que se guarda con
la serie no está en la lista de D-1768: la casa decide con el ADELANTE si sale** (es inocua: solo años).
Y el saneado (`biblioteca.texto_limpio`) rechaza ahora cualquier texto con una referencia `TDP-` o `idn-`,
para todos los que lo usan.

## D-1844 · Lo que queda de D-991: la biblioteca se sanea al salir y la orden catalogar ya no lee pistas

- `biblioteca.buscar` sanea la lectura y el nombre al salir (D-1768: el saneado de D-1787, que ahora vive en
  `biblioteca.texto_limpio` y usa también el servicio). Así sale limpio también lo que entró antes de la 0.6.1
  y lo corregido; una fila que no vale no sale.
- La orden `catalogar` ya no lee `piloto/pistas.csv` ni manda pistas (orquestador, 10/11: «pistas.csv se
  cierra en el próximo parche»). `identificar`, con las fotos de una persona y fuera del Gestor, sigue
  aceptando `--pista`.
- Reescritas por especificación, para que las ratifique la casa con el ADELANTE: tres llamadas de las pruebas
  a `catalogar_una` que pasaban unas pistas vacías (`test_paso_2.py` 275 y 297, `test_d1840_nada_de_referencias.py` 96)
  y el doble que sustituía a `leer_pistas` (`test_paso_2.py` 274), que ya no existe.

Pruebas: 123 → 129.
