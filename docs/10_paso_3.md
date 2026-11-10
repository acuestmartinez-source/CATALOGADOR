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
  sello, fecha, la referencia de la primera y hasta cinco fuentes;
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
