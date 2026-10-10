# El intercambio con el Gestor (§7 de ARQUITECTURA): solo ficheros, nadie llama a nadie

Carpeta: `ALMACEN\_intercambio\` del Gestor (`TDP_INTERCAMBIO`), la misma que usa FOTOS. Estos
ejemplos se copian **idénticos** en los dos repositorios y cada lado prueba que sabe leer los del
otro. Cada fichero `.jsonl` empieza con una línea de cabecera (`formato`, `version`, `escrito_por`,
`escrito_en`, `filas`) y sigue con una fila por línea. Las rutas de imagen son relativas a
`TDP_IMAGENES` (`Z:\IMAGENES`). Ningún fichero lleva datos de personas: `pedido_por` y
`aceptado_por` son el nombre de usuario del Gestor, como en el rastro.

| Fichero | Lo publica | Qué es |
|---|---|---|
| `para_catalogador/cola.jsonl` | IDENTIFICACION (Gestor) | Lo que una persona pidió identificar: una obra o un grupo. `grupo` y `serie_conocida` son opcionales; `pistas` son páginas encontradas a mano (la búsqueda por imagen de ukiyo-e.org). `id_peticion` es único y no se repite. **IDENTIFICACION lo reescribe entero** (con `.parcial` y renombrado, y `filas` al día, D-1003); CATALOGADOR lo lee entero en cada vuelta y salta los ids que ya atendió, así que da igual que crezca o que se reescriba. |
| `para_catalogador/aceptadas.jsonl` | IDENTIFICACION (Gestor) | Lo que una persona aceptó, corrigió o rechazó, campo a campo, y la firma y los sellos que confirmó con su recuadro. Es lo que alimenta la biblioteca propia y el conjunto de oro. |
| `de_catalogador/estado.jsonl` | CATALOGADOR | El estado de cada petición: `en_cola`, `leyendo`, `identificando`, `lista`, `error`, `aplazada` (pasada la hora límite). Se añade al final; vale la última línea de cada `id_peticion`. |
| `de_catalogador/fichas.jsonl` | CATALOGADOR | La propuesta: seis datos con valor, detalle, fiabilidad, nivel, cómo, fuentes, cajas (0–1000 sobre la primera imagen) y `lectura` (lo que dice la firma, el sello de editor o el de censor, en sus caracteres; nulo en los demás); `para_web`; `vinculadas`; `fuentes_verificadas`; `anotada`. Una línea por petición terminada, se añade al final. |
| `de_catalogador/anotadas/<id_peticion>.jpg` | CATALOGADOR | La primera imagen, a 1.100 px de lado mayor, con un recuadro de color y la palabra del dato (Autor, Título, Serie, Editor, Censor) por cada caja. `anotada` en la ficha es su ruta relativa a `de_catalogador/`, o nulo si no hay cajas. Se escribe con `.parcial` y renombrado **antes** que la línea de la ficha. Los colores son de CATALOGADOR; la palabra es la que pinta el Gestor en su tabla. |

Los dos lados escriben con `.parcial` y renombrado atómico cuando reescriben, y en modo «añadir
una línea entera» cuando añaden. Los dos ficheros que publica CATALOGADOR (`estado`, `fichas`) solo
crecen: su cabecera lleva `filas: 0` desde que se estrena y el lector no se fía de esa cifra. Las
líneas van en ASCII puro (secuencias de escape para lo que no sea ASCII), para que una lectura a
medio escribir nunca rompa el UTF-8. El `detalle` de un estado `error` es un motivo fijo, sin texto
de excepción ni ruta. Un campo nuevo es opcional; ningún campo existente cambia de
significado sin fecha de retirada (§13).
