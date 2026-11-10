# La biblioteca de firmas y sellos · 13/10/2026

El lado de CATALOGADOR de la biblioteca que el Gestor enseña y deja corregir (D-1205 del Gestor).
El contrato es `contratos/intercambio/LEEME.md`, con sus dos ejemplos: `de_catalogador/biblioteca.jsonl`
y `para_catalogador/biblioteca_correcciones.jsonl`.

## Qué hace

- **Cada entrada tiene un id estable.** `biblioteca.identidad` da `bib-` y doce cifras del SHA-1 de
  `tipo|id_peticion|referencia|x0,y0,x1,y1`. Las filas nuevas de `datos/biblioteca/firmas.jsonl` y
  `sellos.jsonl` lo guardan; las viejas lo derivan al leer. Anotar dos veces lo mismo no añade nada,
  aunque se pierda `datos/servicio.json`. El recorte propio se llama por su `id_entrada`, nunca por la
  referencia.
- **No se fía de lo que llega.** En `aceptadas.jsonl`, una línea cuya referencia no es `TDP-` y seis
  cifras, o cuya firma, sellos, `campos` o `campos.serie` no tienen su forma, se salta antes de
  escribir nada, con un aviso fijo, y queda hecha. Una caja que no son cuatro números con
  `0 <= x0 < x1 <= 1000` y `0 <= y0 < y1 <= 1000` no tira la línea: esa firma o ese sello entran sin
  caja ni recorte (una caja con decimales se redondea y vale). Si la foto no se deja recortar, la
  entrada entra sin recorte. Una línea que aun así falla se avisa y queda hecha. En `cola.jsonl`, una
  petición cuyo id no es `idn-` y seis cifras, cuya referencia no es `TDP-` y seis cifras o con una
  imagen fuera del almacén se salta con un aviso fijo y queda hecha; el Gestor no recibe noticia de
  ella. Una línea sin un id que case con su patrón (`idn-`, `bic-` y seis cifras) no se apunta como
  hecha: se salta con un aviso, uno por proceso. Un sello sin tipo se publica con `tipo_sello` nulo.
  El criterio es que **ninguna línea JSON tumba una vuelta** (anidada sin fondo, con sustitutos
  sueltos, números enormes, tipos cambiados o rutas largas), y lo vigila
  `pruebas/test_lineas_al_azar.py` con una semilla fija.
- **Aplica lo que pide el Gestor.** En cada vuelta, después de aprender de lo aceptado, el servicio
  lee `para_catalogador/biblioteca_correcciones.jsonl` y aplica cada `id_correccion` una sola vez y en
  orden (`corregir`, `retirar` o `restaurar`). Lo aplicado se apunta en
  `datos/biblioteca/correcciones.jsonl`, que solo crece. La regla de una corrección es la del contrato
  (D-1221), en `biblioteca.lectura_valida` y `biblioteca.nombre_valido`, y las pruebas recorren
  `contratos/intercambio/lecturas_de_prueba.json`. Una corrección que no la cumple, o de un
  `id_entrada` que no se conoce, se ignora, se dice en el registro del contenedor y no se vuelve a
  mirar.
- **Un error de lectura no es una tabla vacía.** Si una tabla propia no se puede leer en ese momento,
  la vuelta se corta ahí: lo que quedaba de ella (aprender, corregir o publicar) espera y la corrección
  no queda hecha. El servicio no se cae: deja en el registro «vuelta fallida (…); se intenta otra vez
  en la siguiente» y lo vuelve a intentar 15 s después, y así hasta que la tabla se lea. Con
  `--una-vez` no hay vuelta siguiente: la orden sale con 1. La búsqueda del agente, en cambio, sigue
  sin la biblioteca y lo dice en una línea del registro.
- **Busca con lo vigente.** `biblioteca.leer` pliega las tablas con lo aplicado: lo retirado deja de
  salir en `buscar_firma` y `buscar_sello_editor`, y lo corregido sale corregido. Al modelo le llegan la lectura,
  el nombre y el parecido; la referencia de la obra, no (D-1840).
- **Publica la biblioteca.** `de_catalogador/biblioteca.jsonl`, entera, con `.parcial` y renombrado,
  en ASCII y solo cuando algo cambia; antes, el recorte de cada entrada en
  `de_catalogador/biblioteca/<id_entrada>.jpg` (480 px como mucho y menos de 80 KB). Van vigentes y
  retiradas, con la última corrección y lo que había antes de la primera corrección. Una miniatura
  borrada se rehace en la vuelta siguiente; un recorte propio que no se deja leer sale con `recorte`
  nulo, con un aviso en el registro, y no hace reescribir la biblioteca en cada vuelta.

## Qué no hace

- **Retirar no borra.** Ni la fila de la tabla ni su recorte: la entrada sigue publicada como
  `retirada` y `restaurar` la devuelve.
- **Corregir no toca la obra del Gestor ni el oro.** Cambia solo lo que CATALOGADOR buscará desde
  entonces. `datos/biblioteca/oro.jsonl` no se corrige nunca y no se publica.
- No publica quién confirmó una entrada ni ninguna ruta de `datos/`.
- Con `--en-seco` no aprende, no corrige y no publica: solo dice lo que haría.

## Para estrenarlo en el NAS

Hay que **reconstruir la imagen** del proyecto `catalogador` en el Container Manager (el código va
dentro de la imagen) y recrear el contenedor. La primera vuelta publica la biblioteca entera; desde
entonces, solo cuando cambia.
