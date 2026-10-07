# Agente de catalogación para Taller del Prado: viabilidad, fuentes, pipeline y coste por obra (foco: estampa japonesa)

> Estudio de partida del proyecto CATALOGADOR. Recibido el 07/10/2026. Las cifras y precios son los de esa fecha; véanse las reservas al final.

Sí: un agente que identifique estampas a partir de una foto y proponga una ficha catalográfica es viable hoy, y 2,5 €/obra es más que suficiente — el coste realista en modelos y APIs ronda 0,30–1,20 € por obra con un modelo de gama media, siempre que la búsqueda visual se haga contra un índice local de embeddings y contra ukiyo-e.org/ARC, y no a base de muchas llamadas a buscadores de pago. El cuello de botella no es el dinero, sino el acceso: casi ninguna de las fuentes clave para estampa japonesa ofrece una API de búsqueda por imagen, y la referencia de catálogo razonado (Hotei/Brown para Hasui, Marks para editores, etc.) está mayoritariamente en libros impresos, no en la web.

## TL;DR

- **Viable y barato**: con Claude (gama Sonnet) + índice CLIP/DINOv2/SigLIP local construido con colecciones abiertas (MFA Boston vía ukiyo-e.org como referencia, Met, AIC, Rijksmuseum, Library of Congress, Japan Search/ColBase), el coste por obra queda en torno a 0,3–1,2 €; 2,5 € permite incluso usar un modelo superior en los casos difíciles. Lo caro es el tiempo humano de revisión, no las llamadas.
- **Estampa japonesa = prioridad bien elegida**: ukiyo-e.org (Resig) agrega más de 200.000 estampas de más de 24 instituciones y busca por imagen, pero no tiene API pública documentada; el ARC de Ritsumeikan y Japan Search sí tienen búsqueda por imagen similar (web) y Japan Search tiene API/SPARQL. La datación se automatiza en parte leyendo sellos de censor/fecha (1790–1876) y sellos de editor (ukiyoesig.net, Marks).
- **Riesgo principal: referencias inventadas**. El agente nunca debe emitir un número de catálogo razonado que no venga de una fuente citada y verificable (URL o libro físico en el taller); toda ficha pasa por una cola de revisión humana con nivel de confianza.

## Key Findings

1. **No existe (que haya encontrado) un servicio comercial que catalogue automáticamente obra gráfica o estampa japonesa desde una foto.** Lo más cercano es ukiyo-e.org, un buscador por similitud de imagen construido sobre TinEye MatchEngine, más las funciones de "imagen similar" del ARC Ritsumeikan y de Japan Search. Smartify, Magnus o Google Arts & Culture están orientados a pintura/museos y no ofrecen API pública útil para esto.
2. **Bing Visual Search ya no existe**: Microsoft retiró las Bing Search APIs (incluida Visual Search) el 11 de agosto de 2025. Las alternativas programáticas reales son Google Cloud Vision *Web Detection* (3,50 $ por 1.000 imágenes tras las 1.000 gratuitas/mes) y la API de TinEye (desde 200 $ por 5.000 búsquedas, 0,04 $/búsqueda). Google Lens y Yandex no tienen API oficial.
3. **Las bases de precios (Artnet, Artprice, MutualArt, Askart, Invaluable/LiveAuctioneers) no son integrables legalmente por scraping**: son de suscripción, sin API pública general, y sus términos prohíben la extracción automatizada. Úsense como consulta manual del revisor, no como herramienta del agente.
4. **Las APIs abiertas de museos son la base del índice propio**: Rijksmuseum (nuevas APIs Linked Art/OAI-PMH sin clave), Library of Congress (API JSON de loc.gov y PPOC), Japan Search (API web y SPARQL), ColBase (imágenes de uso libre citando la fuente), más Met, AIC, Cleveland, Harvard y Smithsonian.
5. **La datación de ukiyo-e es en gran parte "algorítmica"**: entre 1790 y 1876 los sellos de censor y fecha permiten fechar muchas estampas con precisión de año o incluso mes; para shin-hanga de Watanabe, el tipo de sello de editor permite estimar la década de la tirada (clasificación de Hotei/Brown 2003).

## Details

### 1. Tabla comparativa de fuentes

| Fuente | Cobertura | Acceso / API | Búsqueda por imagen | Coste | Utilidad japonesa / occidental |
|---|---|---|---|---|---|
| **ukiyo-e.org** (John Resig) | Más de 200.000 estampas de más de 24 instituciones, subastas y marchantes; EN/JA | Web; sin API pública documentada; © Mongaku, LLC con Términos de Servicio propios | **Sí** (subida de imagen o URL) | Gratis | ★★★★★ / — |
| **ARC Ukiyo-e Portal Database** (Ritsumeikan) | Portal que agrega ukiyo-e publicado en la web + colecciones ARC (p. ej. Waseda Theatre Museum, Tobacco & Salt Museum); búsqueda por sello de censor, editor, grabador, actor, obra kabuki | Web (dh-jac.net); sin API pública documentada | **Sí** (Similar Image Search, web) | Gratis | ★★★★★ / — |
| **Japan Search** (NDL) | Agregador nacional (ColBase, NDL, ARC, etc.) | **API web JSON + SPARQL** | Sí (similar e "imagen AI" en web) | Gratis | ★★★★ / — |
| **ColBase** (Museos Nacionales de Japón: Tokio, Kioto, Nara, Kyushu) | Colecciones de los 4 museos nacionales | Web; imágenes de uso libre citando la fuente | No | Gratis | ★★★ / — |
| **MFA Boston** | Más de 50.000 estampas ukiyo-e según la nota de prensa del MFA de enero de 2025 ("among the largest and finest in the world"), digitalizadas; ~37.000 indexadas en ukiyo-e.org | Web; sin API pública abierta conocida | No (sí vía ukiyo-e.org) | Gratis | ★★★★★ / ★★★ |
| **Library of Congress** (Japanese prints, PPOC) | ca. 2.545 xilografías (en su mayoría en color) y ca. 265 dibujos japoneses, 1615–1912, según el registro PPOC de la serie FP 2 | **API JSON** (loc.gov y PPOC) | No | Gratis | ★★★ / ★★★ |
| **JAODB** (Ross Walker) | ~17.000 registros (muchos shin-hanga, de mercado) | Vía ukiyo-e.org | Sí (vía ukiyo-e.org) | Gratis | ★★★★ shin-hanga / — |
| **Ukiyo-e Signature Sample Database** (ukiyoesig.net) | Firmas 1680–1912 + base de sellos de editor (en curso) + sellos de coleccionista | Web abierta | No | Gratis | ★★★★★ firmas/sellos / — |
| **Viewing Japanese Prints / MIT date-seal pages** | Guías de lectura de sellos de censor y fecha | Web | No | Gratis | ★★★★ (referencia para el prompt) |
| **Scholten Japanese Art, artelino, Fuji Arts** | Archivos de ventas con fichas detalladas (sellos, estados, tiradas) | Web; sin API; consulta manual | No | Gratis | ★★★★ / — |
| **Rijksmuseum** | Colección total de un millón de objetos (1200–2000) según Wikipedia, con gran fondo de grabado europeo y japonés | **APIs abiertas sin clave** (Search Linked Art, OAI-PMH, IIIF) | No | Gratis | ★★★ / ★★★★★ |
| **Met / Art Institute of Chicago / Cleveland** | Grandes fondos de estampas europeas y japonesas | APIs abiertas (Met y AIC sin clave; datos e imágenes en dominio público CC0) | No | Gratis | ★★★ / ★★★★ |
| **Harvard Art Museums / Smithsonian** | Fondos amplios de grabado | API con clave gratuita | No | Gratis | ★★ / ★★★ |
| **British Museum Collection Online** | Uno de los mayores fondos de estampas del mundo, incluido ukiyo-e | Web; sin API pública actual | No | Gratis | ★★★★ / ★★★★★ (consulta manual) |
| **Europeana / Wikidata / Commons** | Agregación europea / datos enlazados | API (Europeana con clave gratuita), SPARQL (Wikidata, federable con Japan Search) | No | Gratis | ★★ / ★★★ |
| **Getty ULAN / Provenance Index** | Autoridades de artistas / procedencias | Linked Open Data / SPARQL | No | Gratis | ★★ normalización de nombres |
| **BNE (Biblioteca Digital Hispánica) / BnF Gallica** | Estampas españolas / francesas | Gallica: APIs SRU e IIIF; BNE: datos.bne.es | No | Gratis | — / ★★★★ |
| **Calcografía Nacional / RABASF** | Láminas de la Calcografía (Goya, etc.) y colecciones de estampas de la Academia | Catálogo digital web + catálogos de láminas en PDF por siglos | No | Gratis | — / ★★★★★ (obra española) |
| **Museo del Prado** | Pintura, dibujo y estampas (Goya) | Web; sin API pública | No | Gratis | — / ★★★ |
| **Artnet Price Database** | Resultados de subasta desde 1985 | Suscripción; sin API pública; uso según acuerdo de suscripción | No | Suscripción | ★★ / ★★★★ (valoración, manual) |
| **Artprice, MutualArt, Askart** | Resultados de subasta | Suscripción; sin API pública general; scraping no permitido | No | Suscripción | ★★ / ★★★ (manual) |
| **Invaluable / LiveAuctioneers** | Catálogos de subasta actuales e históricos | Web; sin API pública | No | Gratis (ver) | ★★★ / ★★★ (manual) |
| **Google Arts & Culture** | Selección de museos | Sin API pública | Sólo en app (no programático) | Gratis | ★ / ★★ |
| **Bridgeman Images** | Banco de imágenes con licencia | Licencia comercial | No (para este uso) | De pago | ★ / ★ |
| **Google Cloud Vision Web Detection** | Toda la web indexada por Google | **API** | **Sí** | 3,50 $/1.000 (1.000 gratis/mes) | ★★★ / ★★★★ |
| **TinEye API** | Índice web de copias casi exactas | **API** | **Sí** | Desde 200 $ / 5.000 búsquedas | ★★ / ★★★ |
| **Bing Visual Search** | — | **Retirada el 11/08/2025** | — | — | — |

Nota de honestidad: las filas de Artprice, MutualArt, Askart, Harvard, Smithsonian, Cleveland, Europeana, Getty, BNE, Gallica y Prado se basan en el conocimiento general del sector y no en verificación documental hecha en esta investigación; conviene confirmar condiciones antes de integrarlas.

### 2. Catálogos razonados y recursos de obra gráfica occidental

- **Cómo verificar una estampa occidental**: (1) identificar el autor por firma/monograma; (2) localizar la imagen idéntica en un museo con API (Rijksmuseum, Met, AIC) o en la Calcografía Nacional; (3) leer en la ficha del museo la referencia bibliográfica (los museos suelen citar el número de catálogo razonado: Bartsch, Hollstein, Delteil, Bloch, Cramer, Mourlot, Feldman-Schellmann, etc.); (4) cotejar medidas de plancha/mancha, estado y tirada.
- **Calcografía Nacional / RABASF**: catálogo digital de estampas (Calcografía + Archivo/Biblioteca de la Academia) y catálogos en PDF de láminas por siglos (XVI–XVII, XVIII, XIX, XX). Es la fuente primaria para Goya y obra gráfica española histórica, y es consulta abierta.
- **Catálogos razonados de artistas modernos (Picasso, Miró, Dalí, Chillida, Tàpies, Warhol, Hartung, Chagall)**: en su mayoría la obra gráfica sigue catalogada en libros impresos (p. ej. Bloch/Baer para Picasso, Cramer/Dupin para Miró, Feldman-Schellmann para Warhol, Mourlot/Sorlier para Chagall). Algunas fundaciones publican catálogos online, pero su alcance para obra gráfica es desigual; trátese como fuente de consulta manual y verifíquese caso por caso. La Catalogue Raisonné Scholars Association (CRSA) mantiene un directorio de catálogos razonados útil para saber cuál es la referencia estándar de cada autor.
- **Conclusión práctica**: para obra occidental moderna, el agente debe proponer "candidato a referencia X según ficha del museo Y (URL)", y el número definitivo lo confirma el revisor con el libro físico. Recomendación: que el taller compre los 10–15 catálogos razonados de los autores que más vende y los tenga indexados (índice de números y títulos) en el gestor interno.

### 3. Estampa japonesa en profundidad

**ukiyo-e.org (John Resig)**. Lanzado en diciembre de 2012; "currently contains over 200,000 prints from over 24 institutions", con búsqueda de texto, búsqueda por imagen subida y agrupación automática de copias de la misma estampa; según su propia página "About", gracias al sitio "Museums have been able to correct unattributed prints, finding the correct artist." Agrega, entre otros, MFA Boston (~37.000 registros), JAODB (~17.000), Ritsumeikan, Harvard y varios marchantes. Técnicamente, Resig usó TinEye MatchEngine, que en sus pruebas era mejor que imgSeek para encontrar coincidencias exactas ignorando diferencias de color y para encontrar estampas o fragmentos dentro de otras (p. ej. trípticos). No hay API pública documentada; el sitio está operado por Mongaku, LLC con términos de servicio propios. Recomendación: **escribir a admin@ukiyo-e.org** pidiendo permiso para un uso de bajo volumen (p. ej. <50 consultas/día) o acceso a un endpoint; mientras tanto, usarlo de forma semiautomática (el revisor sube la imagen y pega el permalink del resultado en la ficha). Existe código abierto relacionado (repos de jeresig: ukiyoe-web, ukiyoe-models, node-matchengine, fork de pastec), útil como referencia para montar algo propio.

**ARC Ukiyo-e Portal Database (Ritsumeikan)**. Portal que permite buscar ukiyo-e publicados en la web, incluida la colección del ARC; es especialmente valioso porque permite buscar por **sello de censor, editor, grabador, personajes, actores, obras y teatros kabuki**. Integra herramientas como ImageNote y **Similar Image Search**, y sigue creciendo (más de 2.600 estampas del Tobacco & Salt Museum en agosto de 2025; Waseda Theatre Museum en diciembre de 2025; OCR "miwo" para transcripción en 2024). Sin API pública documentada: uso manual o con permiso.

**Japan Search (NDL)**. Agregador nacional con **API web JSON** (p. ej. `https://jpsearch.go.jp/api/item/search/jps-cross?keyword=...`) y **endpoint SPARQL** (`https://jpsearch.go.jp/rdf/sparql/`), federable con Wikidata/Europeana. En web ofrece búsqueda de imagen similar y búsqueda por motivo ("imagen AI"). Es la mejor vía programática a fondos japoneses (ColBase, NDL, etc.).

**ColBase**. Base integrada de los museos nacionales de Tokio, Kioto, Nara y Kyushu; imágenes descargables de uso libre con cita de la fuente. Útil para ilustrar el índice local.

**MFA Boston**. Más de 50.000 estampas japonesas, toda la colección digitalizada entre 2005 y 2010; es probablemente la mejor colección de referencia para identificar ukiyo-e. Se consulta mejor a través de ukiyo-e.org.

**Library of Congress**. Según el registro PPOC de la serie "Japanese prints and drawings" (FP 2), unas 2.545 xilografías (sobre todo en color) y unos 265 dibujos japoneses fechados entre 1615 y 1912 (la mayoría de 1700–1890), con el escaneo de 1.100 estampas ukiyo-e financiado por Nichibunken, accesibles mediante la API JSON de loc.gov/PPOC: buena candidata para el índice local.

**Firmas y sellos**:
- **ukiyoesig.net (Alec Wood)**: base de muestras de firmas 1680–1912 organizada por *gagō*, más una base de **sellos de editor** en curso que sigue el sistema de formas de sello de Andreas Marks y documenta ~80% de los sellos que cataloga Marks (1.893 de 2.364).
- **artelino Ukiyo-e Signature Database**: firmas y sellos de miles de artistas.
- **Andreas Marks**, *Publishers of Japanese Woodblock Prints: A Compendium* (Brill, 2010): más de 1.100 editores y facsímiles de más de 2.300 sellos de editor (1650s–1990s); su ampliación *The Japanese Woodblock Prints Companion* perfila más de 1.900 editores y casi 900 grabadores/estampadores. Son libros: imprescindibles en la biblioteca del taller.
- **Censor y fecha**: las páginas de MIT (basadas en Self & Hirose, *Japanese Art Signatures*, 1987) y Viewing Japanese Prints explican las fases: *kiwame* (≈1790–1842), sellos de censores nominativos (1842–1853), *aratame* + fecha zodiacal (desde finales de 1853), sello oval de fecha solo (1858) y sello redondo combinado *aratame* + fecha (1859–1872); a partir de 1872 fechas en *nengō*; la censura formal termina en 1876.

**Shin-hanga (Watanabe, Hasui, Yoshida)**. Para Kawase Hasui la referencia estándar es *Kawase Hasui: The Complete Woodblock Prints* (Kendall H. Brown, Hotei/Brill, 2003, 2 vols.), que incluye el ensayo de Watanabe Shōichirō sobre los sellos de Watanabe; Scholten señala que Hotei renombró la clasificación de sellos de Patcher (1986), empezando por el sello redondo como "A". Según artelino, Hasui creó "more than six hundred woodblock print designs" (las cifras varían entre fuentes: Goodreads habla de más de 700 diseños), y el catálogo de Brown de 592 páginas reúne 617 ilustraciones en color y 131 en blanco y negro; el primer catálogo razonado fue el de Narazaki (1979). Las fichas de Scholten Japanese Art son un modelo excelente de cómo describir sellos (p. ej. "publisher's round Watanabe (Hotei 'A') seal… rectangular (Hotei 'B') seal on the left margin"). Para Yoshida (Hiroshi), la referencia habitual es el catálogo de su obra completa (Abe Publishing); verificar edición antes de citar.

#### Flujo de identificación de una estampa japonesa, paso a paso

1. **Medir y fotografiar**: hoja completa con margen, más recortes macro de firma, sellos (artista, editor, censor/fecha, grabador/estampador) y cartuchos de título. Medidas en mm → **formato** (ōban ≈ 39×26 cm; chūban ≈ 26×19 cm; hosoban, etc.) y orientación (tate-e / yoko-e).
2. **Clasificar época/escuela** por estilo y materiales (anilinas rojas tras ~1860s, papel, márgenes amplios en shin-hanga, sello de copyright en margen).
3. **Leer textos (OCR + VLM)**: firma (p. ej. "Hiroshige ga", "Kunisada ga"), título de serie en cartucho, número de lámina. El modelo propone transliteración; se cruza con ukiyoesig.net.
4. **Leer sellos de censor/fecha** → horquilla de fecha (tabla 1790–1876). Ej.: *aratame* + Buey + 2 en sello redondo combinado → 1865, 2.º mes.
5. **Identificar editor** por forma de sello (sistema Marks / ukiyoesig.net).
6. **Búsqueda visual**: índice local (top-20 candidatos) + ukiyo-e.org/ARC/Japan Search (similar image) + Google Web Detection si hace falta.
7. **Cruzar**: candidato aceptado sólo si coinciden imagen + firma + editor + serie; anotar diferencias de estado (sellos eliminados, colores, recortes) → posible reimpresión o *later edition*.
8. **Ficha propuesta** con título (JA/romaji/ES), serie, artista, editor, fecha (rango y método), formato, técnica (nishiki-e, xilografía en color), medidas, referencia(s) a ejemplares de museo (URL) y referencia de catálogo **sólo si aparece en fuente citada**.
9. **Revisión humana** y, para shin-hanga, dictamen sobre tirada por tipo de sello (lifetime vs. posterior).

### 4. Búsqueda inversa por imagen y visión por ordenador

- **Google Cloud Vision Web Detection**: 3,50 $ por 1.000 unidades (1.000/mes gratis); devuelve páginas con imágenes coincidentes y "entidades web". Útil para encontrar la estampa en webs de subastas o marchantes. Coste por obra: ~0,003 $.
- **TinEye API**: 200 $ por 5.000 búsquedas (0,04 $/búsqueda); bueno para copias casi idénticas en la web, débil para "otra impresión" con distinto color. **TinEye MatchEngine** (índice privado propio) cuesta desde 200 $/mes; no compensa frente a un índice local gratuito.
- **Bing Visual Search**: retirada el 11/08/2025. **Google Lens / Yandex**: sin API oficial (sólo intermediarios no oficiales de tipo SERP, con riesgo de términos de uso).
- **Índice propio (recomendado)**: descargar metadatos + imágenes de dominio público (Met, AIC, Rijksmuseum, Cleveland, LoC, Japan Search/ColBase, Harvard con clave) → embeddings con **DINOv2** (muy bueno para "misma imagen, otra impresión/recorte") y **SigLIP/CLIP** (búsqueda por texto↔imagen) → base vectorial local (FAISS, sqlite-vec o Qdrant) en el NAS. Un índice de 100.000–300.000 imágenes cabe holgadamente en un NAS; generarlo es un coste único de horas de GPU/CPU, y cada consulta luego es gratis. Para trípticos y recortes conviene indexar también recortes (o usar emparejamiento de puntos clave tipo SIFT/ORB como verificación geométrica — es lo que hace bien MatchEngine). Alternativa open source madura: VISE (Oxford VGG).
- **Smartify, Magnus, Google Arts & Culture**: apps de consumo orientadas a pintura y museos; no ofrecen API pública aprovechable para catalogar estampas.

### 5. Arquitectura del agente y coste por obra

**Pipeline propuesto** (orquestado desde el FastAPI del NAS; el agente es Claude con herramientas/MCP):

1. **Ingesta**: el gestor exporta JPG derivado del RAW (lado largo ~2.500 px) + 3–4 recortes (firma, sellos, cartucho, margen) + medidas + autor si se conoce.
2. **Visión local (gratis)**: consulta al índice de embeddings → top-20 candidatos con metadatos y URL.
3. **Análisis VLM (Claude)**: descripción, lectura de firma/sellos, formato, hipótesis de época; recibe los candidatos locales.
4. **Herramientas externas (3–6 fuentes)**: Japan Search API/SPARQL; APIs de Rijksmuseum/Met/AIC/LoC por título/artista; web fetch de las fichas de museo candidatas (MFA, BM, Scholten, ARC); Google Web Detection opcional; ukiyo-e.org sólo si hay permiso (si no, enlace para el revisor).
5. **Cruce y puntuación**: reglas explícitas (coincidencia visual ≥ umbral + firma + editor + serie) → confianza Alta/Media/Baja.
6. **Ficha JSON** con campos, nivel de confianza por campo y **citas (URL + fragmento)** por cada dato; los campos sin fuente quedan vacíos con "pendiente".
7. **Cola de revisión humana** en el gestor; al aprobar, se publica en WooCommerce (vía REST API) y la estampa verificada se añade al índice local, que va mejorando con el uso.

**Precios de referencia (documentación oficial de Anthropic, octubre 2026)**: Claude Sonnet 5.5 a 2 $/MTok de entrada y 10 $/MTok de salida; Claude Opus 5.5 a 4 $ / 20 $; Claude Haiku 4.5 a 1 $ / 5 $; lectura de caché a 0,1× del precio de entrada y Batch API con 50% de descuento. Una imagen cuesta ⌈ancho/28⌉ × ⌈alto/28⌉ tokens visuales, con tope de 4.784 tokens (lado largo 2.576 px) en el nivel de alta resolución. La búsqueda web del servidor cuesta 10 $ por 1.000 búsquedas; el web fetch no tiene recargo, sólo el coste de los tokens del contenido (~2.500 tokens una página media).

**Estimación por obra (Sonnet 5.5, agente de ~8–12 turnos)**:

| Concepto | Cantidad típica | Coste aprox. |
|---|---|---|
| 4–5 imágenes (completa + recortes) | ~15–20 k tokens | ~0,04 $ |
| Contexto acumulado del bucle agente (instrucciones, resultados de 6–10 fichas web/API) | 200–400 k tokens de entrada (parte en caché) | 0,25–0,70 $ |
| Salida (razonamiento + ficha JSON) | 10–20 k tokens | 0,10–0,20 $ |
| Búsquedas web del servidor | 5–10 | 0,05–0,10 $ |
| Google Web Detection | 1 | ~0,004 $ |
| Índice local y APIs de museos | — | 0 $ |
| **Total** | | **≈ 0,45–1,05 $ (≈ 0,40–0,95 €)** |

Con Opus 5.5 en todo el pipeline el total se duplica aproximadamente (≈ 0,9–2,1 $), aún dentro de 2,5 €. Con Batch API (procesado nocturno del lote de estampas sin catalogar) el coste de tokens se reduce a la mitad. **Conclusión: 2,5 €/obra es holgado**; la recomendación es presupuestar ~1 € como objetivo medio y reservar el resto para un "segundo pase" con modelo superior en las obras de confianza baja.

**Dónde ahorrar**: (a) búsqueda visual siempre primero en local; (b) pasar al modelo sólo los 5–10 candidatos mejores, no páginas completas (limitar `max_content_tokens`); (c) caché del prompt de sistema con las tablas de sellos y formatos; (d) Haiku para tareas mecánicas (normalizar medidas, traducir títulos) y Sonnet/Opus para el razonamiento de identificación.

**Riesgos**:
- **Alucinación de referencias** (el más grave): prohibir en el prompt cualquier número de catálogo sin cita; validar automáticamente que cada cita tenga URL accesible y que el texto citado aparezca en la página descargada; marcar como "requiere libro" las referencias de catálogos impresos.
- **Lectura errónea de sellos**: los VLM generales leen mal la escritura de sellos (tensho) y las variantes de caracteres; la lectura del sello debe tratarse como hipótesis y contrastarse visualmente con ukiyoesig.net.
- **Condiciones de uso**: no automatizar contra Artnet/Artprice/MutualArt/Askart ni contra ukiyo-e.org/ARC sin permiso; respetar límites de las APIs abiertas.
- **Derechos de imagen**: usar en la tienda sólo fotografías propias; las imágenes de museos (aunque CC0) sirven para el índice interno y la comparación; ColBase exige citar la fuente; la obra de artistas fallecidos hace menos de 70 años (gran parte del shin-hanga y sōsaku-hanga) puede seguir protegida en la UE, lo que afecta a la reproducción pública, no a la catalogación.

### 6. Servicios y proyectos existentes

- **ukiyo-e.org**: el sistema más cercano a lo que se busca (identificación por foto para estampa japonesa), sin API pública.
- **ARC Similar Image Search y Japan Search (similar / imagen AI)**: búsqueda visual institucional gratuita, vía web.
- **Proyectos académicos**: ARC Ukiyo-e Faces Dataset (ROIS-DS CODH, 11.103 entradas ARC con metadatos), trabajos de Ritsumeikan sobre identificación de la misma estampa entre bases de datos en distintos idiomas y sistemas de recomendación sobre ARC: útiles como datos y métodos, no como servicio.
- **Herramientas open source para montar el propio**: pastec, VISE, FAISS/Qdrant + DINOv2/SigLIP.
- No se ha encontrado ningún servicio comercial que entregue fichas catalográficas de obra gráfica automáticamente desde foto.

## Recommendations

**Lista priorizada de integración**:

1. **Índice local de embeddings** (DINOv2 + SigLIP en sqlite-vec/FAISS en el NAS) con imágenes de dominio público de Met, AIC, Rijksmuseum, LoC y Japan Search/ColBase, más las propias estampas ya catalogadas por el taller. Es la pieza que hace barato todo lo demás.
2. **Japan Search API/SPARQL**: única vía programática amplia a fondos japoneses.
3. **Contactar con ukiyo-e.org (admin@ukiyo-e.org) y con el ARC Ritsumeikan** pidiendo permiso de consulta automatizada de bajo volumen; mientras tanto, integrarlos como "enlace de verificación" para el revisor.
4. **Tablas de sellos en el prompt/caché**: censor/fecha (1790–1876), formatos, sellos Watanabe (clasificación Hotei); y ukiyoesig.net como herramienta de cotejo de firmas y sellos de editor.
5. **Google Cloud Vision Web Detection** como búsqueda web de respaldo (coste despreciable).
6. **APIs de Rijksmuseum, Met, AIC, LoC** para obra occidental y para estampa japonesa en colecciones occidentales.
7. **Biblioteca física indexada**: Marks (*Publishers*/*Companion*), Brown/Hotei (Hasui), catálogo de Yoshida, Self & Hirose; y para occidental, los catálogos razonados de los autores más vendidos. El agente propone; el revisor confirma número de catálogo con el libro.
8. **Consulta manual (no integrar)**: Artnet/Artprice/MutualArt/Invaluable para precio; British Museum y MFA para cotejo fino; Scholten/artelino como modelo de redacción de fichas.

**Plan de arranque**: piloto con 50 estampas japonesas ya catalogadas (para medir acierto) + 50 sin catalogar; objetivo: ≥70% de identificaciones correctas en el top-3 con confianza Alta, coste medio ≤1 €/obra, y tiempo de revisión humana ≤5 minutos por ficha.

## Caveats

- Los precios de los modelos proceden de la documentación oficial de Anthropic consultada en octubre de 2026; la propia página remite a claude.com/pricing como referencia más actual, y fuentes de terceros discrepan sobre si algunos precios de lanzamiento (p. ej. Sonnet 5) eran provisionales. Recalcular antes de presupuestar.
- La estimación de tokens del bucle agente es un rango razonado, no una medición; el piloto debe medir el coste real por obra.
- No se ha podido leer el texto íntegro de los Términos de Servicio de ukiyo-e.org; la recomendación de pedir permiso es prudencial.
- Varias filas de la tabla (fuentes de precios, algunos museos, catálogos razonados de artistas modernos) no se han verificado documentalmente en esta investigación y deben confirmarse antes de integrar.
- Los recuentos de ukiyo-e.org varían según la fuente (200.000–220.000+); el MFA da "más de 50.000" estampas japonesas, mientras otras fuentes citan "más de 30.000 ukiyo-e" de la donación Bigelow — no son contradictorios (cuentan cosas distintas).
