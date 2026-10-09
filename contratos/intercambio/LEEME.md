# El intercambio con el Gestor (§7 de ARQUITECTURA): solo ficheros, nadie llama a nadie

Carpeta: `ALMACEN\_intercambio\` del Gestor (`TDP_INTERCAMBIO`), la misma que usa FOTOS. Estos
ejemplos se copian **idénticos** en los dos repositorios y cada lado prueba que sabe leer los del
otro. Cada fichero `.jsonl` empieza con una línea de cabecera (`formato`, `version`, `escrito_por`,
`escrito_en`, `filas`) y sigue con una fila por línea. Las rutas de imagen son relativas a
`TDP_IMAGENES` (`Z:\IMAGENES`). Ningún fichero lleva datos de personas: `pedido_por` y
`aceptado_por` son el nombre de usuario del Gestor, como en el rastro.

| Fichero | Lo publica | Qué es |
|---|---|---|
| `para_catalogador/cola.jsonl` | IDENTIFICACION (Gestor) | Lo que una persona pidió identificar: una obra o un grupo. `grupo` y `serie_conocida` son opcionales; `pistas` son páginas encontradas a mano (la búsqueda por imagen de ukiyo-e.org). Se **añade** al final; `id_peticion` es único y no se repite. |
| `para_catalogador/aceptadas.jsonl` | IDENTIFICACION (Gestor) | Lo que una persona aceptó, corrigió o rechazó, campo a campo, y la firma y los sellos que confirmó con su recuadro. Es lo que alimenta la biblioteca propia y el conjunto de oro. |
| `de_catalogador/estado.jsonl` | CATALOGADOR | El estado de cada petición: `en_cola`, `leyendo`, `identificando`, `lista`, `error`, `aplazada` (pasada la hora límite). Se añade al final; vale la última línea de cada `id_peticion`. |
| `de_catalogador/fichas.jsonl` | CATALOGADOR | La propuesta: seis datos con valor, detalle, fiabilidad, nivel, cómo, fuentes y cajas (0–1000 sobre la primera imagen); `para_web`; `vinculadas`; `fuentes_verificadas`. Una línea por petición terminada, se añade al final. |

Los dos lados escriben con `.parcial` y renombrado atómico cuando reescriben, y en modo «añadir
una línea entera» cuando añaden. Un campo nuevo es opcional; ningún campo existente cambia de
significado sin fecha de retirada (§13).
