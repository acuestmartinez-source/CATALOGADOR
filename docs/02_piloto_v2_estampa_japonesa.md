# Piloto v2: especialización en estampa japonesa

Aprobado por la casa el 08/10/2026 («ADELANTE CON EL PROYECTO»). Amplía `01_diseno_piloto.md`.
El foco es solo estampa japonesa hasta que funcione bien; lo occidental espera.

## Qué cambió y por qué

La v1 acertó artista, serie y fecha en la primera obra (TDP-008194) pero no leyó los sellos
de censor ni de editor, ni el símbolo suelto sobre el cartucho de serie. La casa pidió:
identificar los cuadros de texto, leer los caracteres japoneses, distinguir los sellos de
censor y de editor, y tratar libros de kabuki y páginas de libro sin identificar.

| # | Decisión | Por qué |
|---|---|---|
| P-11 | Paso 0 local con **NDL古典籍OCR-Lite** (Biblioteca Nacional de la Dieta, CC BY 4.0, CPU, unos 9 s por foto). Su lectura va al agente como **pista**, con la caja de cada bloque. | Lee bien cartuchos y firma (葉うた虎之巻, 国周画 a la primera). No ve sellos redondos ni símbolos sueltos y a veces lee dibujo como texto: por eso es pista y no verdad. Está instalado aparte en `C:\dev\ndlkotenocr-lite` (`TDP_NDL_OCR`). |
| P-12 | **Lupa**: herramienta `ampliar` que devuelve un recorte ampliado de la foto. El prompt obliga a ampliar cada sello, símbolo, firma y cartucho antes de transcribirlo. Tope 16 por obra. | Un sello de 8 mm en una foto de 1.800 px no se lee sin ampliar. Con la lupa el agente pasó de 3 a 5 sellos inventariados en TDP-008194. |
| P-13 | **Base local de sellos de editor**: 4.020 sellos de 1.235 editores de la Ukiyo-e Publisher Seal Database de ukiyoesig.net (Alec Wood, sistema de formas de Marks). Herramienta `buscar_sello_editor`; `sellos.py construir` la rehace. | El agente leía 近久 pero no sabía que es Ōmiya Kyūjirō. La base lo dice, con fecha documentada, forma y la URL del ejemplar de museo para citar. Los datos quedan en `datos/`, fuera de git. |
| P-14 | El prompt trata kabuki (actores, papeles, mon, teatro, temporada), banzuke, páginas de libro (ehon, gōkan, libros de kabuki, folio 丁), dípticos y trípticos, obras sin texto y reediciones. La ficha gana `tipo_obra`, `obra_mayor`, `kabuki`, `textos` y `sellos` con posición. | Muchas estampas del taller son hojas de libros o de kabuki sin identificar. |
| P-15 | Tope de web **por obra** (12 búsquedas, 10 lecturas), no por petición. | El `max_uses` de la API cuenta por petición; con la lupa hay varias peticiones por obra y la primera prueba hizo 16 búsquedas. |
| P-16 | Cuatro obras en paralelo y llamada en streaming. | La v2 tarda unos 4 minutos por obra. |

## Cómo analiza una estampa, paso a paso

1. Del Gestor, en solo lectura: referencia, medidas y las dos primeras fotos de `Z:\IMAGENES`.
2. El OCR de la NDL lee la foto 1 en el PC y devuelve bloques de texto con su caja.
3. Claude Sonnet 5.5 recibe las fotos, la lectura del OCR y las medidas. No recibe artista ni título.
4. Hace inventario de todo lo escrito y sellado, amplía cada elemento con la lupa, transcribe y corrige al OCR.
5. Data por los sellos de censor y fecha (tabla 1790–1876 en el prompt) o, si no hay, por editor, firma, actor y estilo.
6. Consulta los caracteres de cada sello de editor en la base local.
7. Busca la obra en museos y marchantes serios; acepta un candidato solo si coinciden imagen, firma, editor y serie.
8. Devuelve la ficha con fuente por dato. Lo que no encuentra queda vacío y en «pendiente».

## Límites conocidos

- **Resolución**: las fotos de `Z:\IMAGENES` tienen 1.800 px de lado largo. Al ampliar un sello se ve borroso; en TDP-008194 el agente leyó el mismo sello como 近久 una vez y como 駒改 otra. Con fotos de detalle o el original de Capture One a más resolución, la lectura de sellos mejoraría mucho.
- **Variabilidad**: dos pasadas sobre la misma obra no dan exactamente la misma ficha.
- **Coste**: la v2 sale a unos 0,8–0,9 € por obra frente a 0,29 € de la v1. Hay que ver en el lote si la mejora lo justifica.

## Órdenes

- La pasada v2 completa: `./.venv/Scripts/python.exe piloto.py catalogar` → `resultados/claude-sonnet-5-5_v2/`
- La de referencia, sin OCR ni lupa: `… catalogar --sin-ocr --sin-lupa` → `resultados/claude-sonnet-5-5_v2_sin_ocr_sin_lupa/`
- Informe de una pasada: `… informe --modelo claude-sonnet-5-5_v2`
- Las dos, lado a lado: `… comparar claude-sonnet-5-5_v2_sin_ocr_sin_lupa claude-sonnet-5-5_v2`
- Consultar la base de sellos a mano: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe sellos.py buscar 近久`
