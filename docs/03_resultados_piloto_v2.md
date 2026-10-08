# Resultados del piloto v2 · 50 estampas japonesas · 08/10/2026

Muestra: 50 Moku-Hanga del Gestor con editor y año (semilla 2026, `piloto/muestra.csv`).
El agente recibe solo las fotos y las medidas. «Acierto» es coincidir con la ficha del Gestor,
que también tiene errores (ver abajo). Modelo: Claude Sonnet 5.5.

## Las dos pasadas

| Medida | Referencia (sin OCR ni lupa) | v2 (OCR + lupa + base de sellos) |
|---|---|---|
| Fichas completas | 50/50 | 50/50 |
| Artista | 48/50 | 47/50 |
| Artista con confianza alta | 30 de 31 | 39 de 40 |
| Editor | 27/50 | 33/50 |
| Editor con confianza alta o media | 19 de 24 | 31 de 40 |
| Año (±2) | 47/50 | 49/50 |
| Serie con confianza alta | 29/50 | 41/50 |
| Sellos inventariados por obra | 2,4 | 3,1 |
| Coste por obra | 0,24 € | 0,57 € |
| Coste del lote | 11,90 € | 28,25 € |
| Tiempo por obra | 158 s | 195 s |

Lectura:

- **La v2 se atreve más y acierta casi siempre que se atreve.** Da artista con confianza
  alta en 40 obras (frente a 31) y falla solo una. El editor lo da con confianza alta o media
  en 40 (frente a 24) y acierta 31.
- **Editor**: la v2 gana 12 obras y pierde 6. De las 6, dos son el sello 伊勢市, que la base
  de ukiyoesig.net atribuye a Iseya Ichiemon (1845–1848) y el Gestor a Iseya Ichibei; las
  otras cuatro son Fujiokaya Keijirō y Sanoya Kihei, cuyo sello no consiguió leer.
- **Serie**: 41 con confianza alta frente a 29. Es lo que más mejora el OCR.
- **Tipo de obra**: 46 sueltas, 2 hojas de díptico, 1 de tríptico, 1 álbum (TDP-007565,
  楳嶺花鳥画譜, Bairei kachō gafu). 20 reconocidas como kabuki.
- **Coste**: 0,57 € por obra, por debajo del euro de objetivo del estudio.

## El Gestor también se equivoca

- **TDP-007990**: el Gestor dice Shunkōsai Hokushū (Osaka, Wataya Kihei). La firma dice
  claramente 香蝶楼国貞画, Kōchōrō Kunisada ga, y el actor es 岩井粂三郎, Iwai Kumesaburō.
  El agente tiene razón (comprobado a ojo en la foto).

## Para adjudicar (una persona con la obra delante)

| Obra | Duda | Gestor | Agente |
|---|---|---|---|
| TDP-008194 | Dos sellos: uno redondo negro (越嘉) y otro en forma de pieza de shōgi (近久). | Ōmiya Kyūjirō | Echizenya Kajū, confianza media. Una pasada anterior leyó 近久, que es Ōmiya Kyūjirō. |
| TDP-008133, TDP-008183 | Misma serie que TDP-008194. | Ōmiya Kyūjirō | Echizenya Kajū |
| TDP-007798, TDP-007815 | Sello 伊勢市. | Iseya Ichibei | Iseya Ichiemon, según la base de sellos y la Library of Congress |
| TDP-007791 | Tríptico de Meiji: firma □寿園国利 y colofón Meiji 23. | Inoue Yasuji, 1888 | Utagawa Kunitoshi (?), 1890, confianza baja |
| TDP-007693, TDP-007700 | Sello 下谷 魚栄. | «Shitaya, Tōkei-han» y Tsutaya Kichizō | Uoya Eikichi |
| TDP-007706 | Sello 赤坂 吉. | «Akasaka Yoshi» | Iseya Kanekichi |
| TDP-007681 | Sello 海老林. | Ebirō | Ebiya Rinnosuke |

El listado completo, con columnas vacías para adjudicar título y serie, está en
`resultados/claude-sonnet-5-5_v2/resumen.csv` (fuera de git).

## Límites que quedan

- **Resolución de las fotos** (1.800 px): es lo que más frena la lectura de sellos.
- **Variabilidad** entre pasadas sobre la misma obra.
- **El tope de web por obra** se comprueba entre peticiones; una petición puede pasarse
  (hasta 16 búsquedas en una obra). No encarece mucho la media.
