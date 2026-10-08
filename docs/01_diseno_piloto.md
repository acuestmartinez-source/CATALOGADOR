# Piloto: 50 estampas japonesas del Gestor, identificadas desde la foto

Aprobado por la casa el 08/10/2026 («ADELANTE»). Es la primera pieza del proyecto y sirve
para medir, no para producir fichas. Sale del estudio `00_viabilidad_agente_catalogacion.md`.

## Qué mide

Cuánto acierta un agente que recibe **solo la fotografía y las medidas** de una estampa, y
cuánto cuesta cada obra. La «verdad» es la ficha del Gestor, que también puede estar mal:
por eso el informe deja columnas para que una persona adjudique.

## Decisiones

| # | Decisión | Por qué |
|---|---|---|
| P-1 | Una llamada por obra a Claude con búsqueda y lectura web **del servidor**; sin herramientas propias ni índice local. | Mide la hipótesis del estudio con lo mínimo construido. El índice local llega después, si el piloto lo justifica. |
| P-2 | Entrada: foto principal (y la segunda si la hay) tal cual, a 1.800 px, más alto y ancho en cm. Sin artista. | Identificación pura. La pasada «con artista» se puede añadir con una bandera si hace falta. |
| P-3 | Modelo por defecto `claude-sonnet-5-5`, pensamiento adaptativo, esfuerzo alto; `--modelo` para repetir con `claude-opus-5-5`. | Es lo que recomienda el estudio; Opus queda para las obras de confianza baja. |
| P-4 | Tope de 8 búsquedas y 8 lecturas web por obra. | Acota el coste; el estudio estima 5–10. |
| P-5 | Regla dura en el prompt: ningún dato de catálogo sin URL citada. Lo que no se encuentra queda vacío. | El riesgo principal del estudio son las referencias inventadas. |
| P-6 | Muestra: 50 obras al azar con semilla fija entre las Moku-Hanga con editor, año y foto principal. Solo la referencia va a `piloto/muestra.csv`. | Repetible y sin copiar datos de producción al repositorio. |
| P-7 | El Gestor y `Z:\IMAGENES` se abren en **solo lectura**. CATALOGADOR no escribe nunca en el Gestor. | Regla de la casa. |
| P-8 | Un resultado guardado no se vuelve a pedir. | Repetible y no se paga dos veces. |
| P-9 | Comparación automática de artista, editor y año (nombres normalizados, año dentro del rango). Título y serie los adjudica una persona. | Los títulos vienen en tres lenguas y las fichas del Gestor no son fiables al 100 %. |
| P-10 | Las fuentes de pago (Artnet, Artprice…) y ukiyo-e.org/ARC quedan **bloqueadas** para el agente. | Condiciones de uso; el estudio pide permiso antes de automatizar contra ellas. |

## Piezas

- `piloto.py`: tres órdenes.
  - `muestra`: elige las 50 y escribe `piloto/muestra.csv`.
  - `catalogar [--modelo M] [--sin-web] [--en-seco] [--solo REF...]`: una ficha JSON por obra en
    `resultados/<modelo>/<REF>.json`, con el uso de tokens y búsquedas.
  - `informe [--modelo M]`: `resultados/<modelo>/informe.md` y `resumen.csv`.
- `piloto/prompt.md`: el prompt de sistema, con las tablas de sellos de censor y formatos.
- `pruebas/test_piloto.py`: la comparación de nombres y de años.
- `.env`: `ANTHROPIC_API_KEY`, `TDP_BASE` (ruta a la base del Gestor) y `TDP_IMAGENES` (`Z:\IMAGENES`).

## Qué sale

Por obra: artista, título (japonés, romaji, castellano), serie, editor, fecha con rango y
método de datación, formato, firma y sellos leídos, ejemplares de museo con URL, confianza
por campo, fuentes, tokens de entrada y salida, búsquedas, coste en euros.

En el informe: acierto en artista, editor y año; coste medio y total; las obras de
confianza baja; las columnas vacías para la adjudicación humana de título y serie.

## Objetivo del estudio para dar el piloto por bueno

Al menos el 70 % de aciertos en artista con confianza alta, coste medio por debajo de 1 €,
y menos de 5 minutos de revisión por ficha.
