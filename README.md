# CATALOGADOR

Agente de catalogación de obra gráfica para Taller del Prado, con foco inicial en estampa japonesa.

- Estudio de partida: `docs/00_viabilidad_agente_catalogacion.md`.
- Diseño del piloto: `docs/01_diseno_piloto.md`.
- Piloto v2, especializado en estampa japonesa (OCR, lupa, sellos de editor): `docs/02_piloto_v2_estampa_japonesa.md`.

## Órdenes del piloto

Python 3.12 en `./.venv` (`py -3.12 -m venv .venv` y `./.venv/Scripts/python.exe -m pip install -r requirements.txt`).
Copiar `.env.ejemplo` a `.env` y poner `ANTHROPIC_API_KEY`. El Gestor y `Z:\IMAGENES` se abren en solo lectura.

- Pruebas: `./.venv/Scripts/python.exe -m pytest pruebas -q`
- Elegir las 50: `./.venv/Scripts/python.exe piloto.py muestra` (ya hecha, `piloto/muestra.csv`)
- Ver qué haría sin gastar: `./.venv/Scripts/python.exe piloto.py catalogar --en-seco`
- Una sola obra, para probar: `./.venv/Scripts/python.exe piloto.py catalogar --solo TDP-008194`
- El lote entero (repetible, no repite las ya hechas): `./.venv/Scripts/python.exe piloto.py catalogar`
- Con Opus en las dudosas: `… catalogar --modelo claude-opus-5-5 --solo REF REF`
- Sin web, como línea base: `… catalogar --sin-web` (resultados en `resultados/claude-sonnet-5-5_sin_web/`)
- El informe: `./.venv/Scripts/python.exe piloto.py informe [--modelo <carpeta>]` → `resultados/<modelo>/informe.md` y `resumen.csv`
- La página de revisión, con foto, Gestor y agente lado a lado (local, fuera de git): `./.venv/Scripts/python.exe revision.py claude-sonnet-5-5_v2` → `resultados/claude-sonnet-5-5_v2/revision.html`
- Dos pasadas comparadas: `… piloto.py comparar <carpeta A> <carpeta B>`

`resultados/` está fuera de git.
