# CATALOGADOR

Identifica estampas japonesas del Gestor de Taller del Prado desde su foto y prepara lo publicable
en la web: autor, título (construido si no lo hay), serie, editor, censor y fecha, y técnica, con
cómo se identificó cada dato, de qué fuente sale y con qué fiabilidad, y las obras vinculadas.

- Estado actual y cómo usarlo: `docs/05_version_depurada.md`.
- Integración con el Gestor (contrato de intercambio, servicio, contenedor, base propia): `docs/06_integracion_con_el_gestor.md`.
- Análisis crítico, fuentes y vínculos SKU: `docs/04_analisis_critico.md`.
- Historia: `docs/00` (estudio), `01` (piloto), `02` (v2 y decisiones P-11 a P-25), `03` (resultados v2).

## Puesta en marcha

Python 3.12 en `./.venv`:

```bash
py -3.12 -m venv .venv
```

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Copiar `.env.ejemplo` a `.env` y poner `ANTHROPIC_API_KEY`. El OCR de japonés antiguo
(NDL古典籍OCR-Lite) va aparte, en `C:\dev\ndlkotenocr-lite` con su propio `.venv` (o `TDP_NDL_OCR`).
Las bases de firmas y sellos se rehacen con `python firmas.py construir` y `python sellos.py construir`.
El Gestor y `Z:\IMAGENES` se abren en solo lectura; nada se escribe en la tienda.

## Órdenes

```bash
./.venv/Scripts/python.exe -m pytest pruebas -q
```

```bash
./.venv/Scripts/python.exe catalogador.py catalogar --en-seco
```

```bash
./.venv/Scripts/python.exe catalogador.py catalogar --lista piloto/sin_identificar.csv --hasta 13:00
```

```bash
./.venv/Scripts/python.exe catalogador.py exportar
```

```bash
./.venv/Scripts/python.exe revision.py
```

Como servicio auxiliar del Gestor (vigila `_intercambio/para_catalogador/cola.jsonl` y responde por ficheros):

```bash
./.venv/Scripts/python.exe servicio.py --intercambio "Z:\FOTO\_intercambio" --hasta 13:00
```

Una estampa suelta, con tus fotos (y, si la encontraste a mano en ukiyo-e.org, su enlace):

```bash
./.venv/Scripts/python.exe catalogador.py identificar hoja.jpg firma.jpg --medidas 35x24.4 --pista https://ukiyo-e.org/image/...
```

La búsqueda por imagen de ukiyo-e.org la hace una persona (su robots.txt la prohíbe a los
programas); el enlace del resultado se deja en `piloto/pistas.csv` (`referencia;url;nota`).
`resultados/` y `datos/` están fuera de git.
