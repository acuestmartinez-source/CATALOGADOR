"""Página de revisión local: foto anotada, los seis datos con cómo se identificaron, y lo que iría a la web.

  python revision.py                       resultados/v4/revision.html
  python revision.py v4 piloto/lista.csv   solo las obras de esa lista -> revision_<lista>.html

Cada dato lleva un color, el mismo en el recuadro sobre la foto y en la tabla. Cada fuente lleva
una marca según cómo llegó a ella el agente. Sirve también las fichas de la v2 y la v3.
Solo para este PC: las fotos van dentro de la página, que queda en resultados/, fuera de git.
"""
from __future__ import annotations

import base64
import html
import json
import sys
from io import BytesIO
from pathlib import Path

import catalogador as C
import ficha as F
import imagen
import medir

ESTILO = """
:root{--papel:#f7f4ee;--tinta:#1d1b18;--gris:#6b665e;--linea:#d9d3c7;--ok:#2f6b3a;--mal:#9b2c1f;--aviso:#8a6a12}
@media (prefers-color-scheme:dark){:root{--papel:#171614;--tinta:#ece7dd;--gris:#a39d92;--linea:#3a3732;--ok:#7fc08b;--mal:#e58a7c;--aviso:#d9b55a}}
body{margin:0;background:var(--papel);color:var(--tinta);font:15px/1.45 system-ui,sans-serif}
main{max-width:1280px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:8px 0 6px}
article{display:grid;grid-template-columns:minmax(0,420px) minmax(0,1fr);gap:22px;padding:22px 0;border-top:1px solid var(--linea)}
@media (max-width:820px){article{grid-template-columns:minmax(0,1fr)}}
.campo{overflow-wrap:normal}
img{width:100%;height:auto;border:1px solid var(--linea)}
h2{font-size:17px;margin:0 0 4px}
table{border-collapse:collapse;width:100%;font-size:14px}
td,th{border-bottom:1px solid var(--linea);padding:5px 6px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{color:var(--gris);font-weight:500}
.campo{white-space:nowrap;font-weight:600}
.muestra{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:-1px;border:2px solid}
.ok{color:var(--ok)}.mal{color:var(--mal)}.aviso{color:var(--aviso)}
.peq{color:var(--gris);font-size:13px}
.como{font-size:13px;opacity:.85}
.web{border-left:3px solid var(--linea);padding:4px 10px;margin:10px 0;font-size:14px}
ul{margin:4px 0;padding-left:18px}
a{color:inherit}
"""

CAMPOS = [("titulo", "Título"), ("autor", "Autor"), ("serie", "Serie"), ("editor", "Editor"),
          ("censor", "Censor y fecha"), ("tecnica", "Técnica")]
COLOR = {"titulo": "titulo", "autor": "artista", "serie": "serie", "editor": "editor", "censor": "censor", "tecnica": "otro"}
MARCA_FUENTE = {
    "abierta": ("ok", "✓", "abierta y leída"),
    "base documentada": ("ok", "✓", "de la base de sellos o firmas"),
    "solo buscador": ("aviso", "⚠", "solo vista en el buscador, sin abrir"),
    "no comprobable": ("aviso", "?", "pasada antigua: no se puede comprobar"),
    "nunca vista": ("mal", "✗", "no salió de ninguna herramienta: no vale como fuente"),
}
MARCA_FIABILIDAD = {"alta": "ok", "media": "aviso", "baja": "mal"}


def e(valor) -> str:
    return html.escape(str(valor)) if valor not in (None, "", []) else '<span class="peq">—</span>'


def a_data(im) -> str:
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=84)
    return "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _cajas(d) -> list:
    if not isinstance(d, dict):
        return []
    cajas = d.get("cajas") or ([d["caja"]] if d.get("caja") else [])
    return [c for c in cajas if isinstance(c, list) and len(c) == 4 and any(c)]


def marcas_de(fi: dict) -> list[dict]:
    """Los recuadros: los de cada dato; en fichas antiguas, también los de la firma y los sellos."""
    marcas = [{"campo": COLOR[c], "caja": caja, "etiqueta": n} for c, n in CAMPOS for caja in _cajas(F.dato(fi, c))]
    if not any(m["campo"] == "artista" for m in marcas):
        marcas += [{"campo": "artista", "caja": caja, "etiqueta": "Autor"} for caja in _cajas(fi.get("firma"))]
    ya = {(m["campo"], tuple(m["caja"])) for m in marcas}
    tipos = {"censor": "censor", "fecha": "censor", "censor y fecha": "censor", "editor": "editor"}
    for s in fi.get("sellos") or []:
        color = tipos.get((s.get("tipo") or "").lower(), "otro")
        marcas += [{"campo": color, "caja": caja, "etiqueta": s.get("tipo") or "sello"}
                   for caja in _cajas(s) if (color, tuple(caja)) not in ya]
    return marcas


def enlaces(urls, verificadas: dict) -> str:
    salida = []
    for u in urls if isinstance(urls, list) else str(urls or "").replace(";", " ").split():
        u = str(u)
        if not u.startswith("http"):
            continue
        corto = "ukiyo-e.org" if "ukiyo-e.org" in u else u.split("/")[2].removeprefix("www.")
        clase, signo, ayuda = MARCA_FUENTE.get(verificadas.get(u, ""), ("peq", "", ""))
        salida.append(f'<a href="{html.escape(u)}" target="_blank" rel="noopener" title="{ayuda}">{html.escape(corto)}</a>'
                      + (f' <span class="{clase}" title="{ayuda}">{signo}</span>' if signo else ""))
    return " · ".join(salida)


def obra(r: dict, g: dict, carpeta_img: Path) -> str:
    fi = r.get("ficha") or {}
    verificadas = r.get("fuentes_verificadas") or {}
    foto = carpeta_img / g["imagenes"][0] if g["imagenes"] else None
    img = (f'<img src="{a_data(imagen.anotar(foto, marcas_de(fi)))}" alt="{html.escape(r["referencia"])} con los datos marcados">'
           if foto and foto.exists() else "")
    comp = medir.comparar(fi, g)
    gestor_de = {"titulo": g["titulo"], "autor": g["artista"], "serie": g["serie_literal"], "editor": g["editor_literal"],
                 "censor": g["anio"] or g["anio_literal"], "tecnica": g["tecnica_literal"]}
    comp_de = {"autor": comp["autor"], "serie": comp["serie"], "editor": comp["editor"], "censor": comp["fecha"]}
    filas = []
    for campo, nombre in CAMPOS:
        d = F.dato(fi, campo)
        extra = {"autor": d.get("firma"), "editor": d.get("sello") or d.get("sello_lectura"),
                 "censor": d.get("lectura") or d.get("sello"), "tecnica": d.get("formato"),
                 "titulo": "título construido a partir de la imagen" if d.get("construido") else None,
                 "serie": f"lámina {d['numero_lamina']}" if d.get("numero_lamina") else d.get("japones")}.get(campo)
        fiab = F.fiabilidad(fi, campo)
        c = comp_de.get(campo)
        gestor_txt = (f'<span class="ok">✓ coincide</span>' if c else f'<span class="mal">✗ {e(gestor_de[campo])}</span>'
                      if c is False else f'<span class="peq">{e(gestor_de[campo])}</span>')
        filas.append(
            f'<tr><td class="campo"><span class="muestra" style="border-color:{imagen.COLORES[COLOR[campo]][0]}"></span>{nombre}</td>'
            f"<td>{e(F.valor(fi, campo))}{f' <span class=peq>· {html.escape(str(extra))}</span>' if extra else ''}"
            f"<div class='como'>{e(d.get('como') or d.get('justificacion') or d.get('metodo'))}</div>"
            f"<div class='peq'>{enlaces(d.get('fuentes') or d.get('fuente'), verificadas)}</div></td>"
            f"<td><span class='{MARCA_FIABILIDAD.get(fiab, 'peq')}'>{e(fiab)}</span><br><span class='peq'>{e(F.nivel(fi, campo))}</span></td>"
            f"<td>{gestor_txt}</td></tr>")
    vinculadas = "".join(f"<li>{e(v.get('relacion'))}: {enlaces([v.get('url')], verificadas)} <span class='peq'>{e(v.get('descripcion'))}</span></li>"
                         for v in fi.get("vinculadas") or fi.get("ejemplares") or [] if isinstance(v, dict) and v.get("url"))
    web = r.get("para_web") or F.para_web(fi)
    publicable = " · ".join(f"<b>{n}</b>: {html.escape(str(web[c]))}" for c, n in CAMPOS if web.get(c))
    t = r.get("tienda") or g.get("tienda") or {}
    tienda = (f"<p class='peq'>Tienda: id {e(t.get('id_woo'))} · SKU <code>{e(t.get('sku'))}</code>"
              f"{' · <span class=aviso>ficha creada como copia de otra</span>' if t.get('es_copia') else ''}"
              + (f' · <a href="{html.escape(t["enlace"])}" target="_blank" rel="noopener">ver en la tienda</a>' if t.get("enlace") else "")
              + "</p>")
    return f"""<article id="{r['referencia']}"><div>{img}<p class="peq">{e(g['alto_cm'])} × {e(g['ancho_cm'])} cm ·
{e(fi.get('tipo_obra'))} · fases {e(r.get('fases', 'A+B'))} · {r.get('coste_eur', 0):.2f} € · {r.get('duracion_s', '')} s</p></div><div>
<h2>{r['referencia']}</h2>{tienda}
<table><tr><th>Dato</th><th>Lo identificado y cómo</th><th>Fiabilidad</th><th>Gestor</th></tr>{''.join(filas)}</table>
<div class="web"><b>Para la web</b><br>{publicable or '<span class="peq">nada publicable</span>'}</div>
{f"<p><b>Obras vinculadas</b></p><ul>{vinculadas}</ul>" if vinculadas else ''}
</div></article>"""


def leyenda() -> str:
    colores = " ".join(f'<span class="peq"><span class="muestra" style="border-color:{imagen.COLORES[COLOR[c]][0]}"></span>{n}</span>'
                       for c, n in CAMPOS)
    fuentes = " · ".join(f'<span class="{c}">{s}</span> <span class="peq">{a}</span>' for c, s, a in MARCA_FUENTE.values())
    return f"{colores}<br>{fuentes}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    C.cargar_env()
    nombre = sys.argv[1] if len(sys.argv) > 1 else C.CARPETA
    lista = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    carpeta = C.RESULTADOS / nombre
    con, fotos = C.abrir_gestor(), C.carpeta_imagenes()
    partes = [obra(r, C.gestor(con, r["referencia"]), fotos) for r in C.resultados(carpeta, lista)]
    pagina = (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
              f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión del catalogador</title>'
              f"<style>{ESTILO}</style></head><body><main><h1>Revisión · {html.escape(nombre)} · {len(partes)} obras</h1>"
              f"<p>{leyenda()}</p>{''.join(partes)}</main></body></html>")
    destino = carpeta / (f"revision_{lista.stem}.html" if lista else "revision.html")
    destino.write_text(pagina, encoding="utf-8")
    print(f"{len(partes)} obras -> {destino}")


if __name__ == "__main__":
    main()
