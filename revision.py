"""Página de revisión local de una pasada: foto anotada, ficha del Gestor y del agente, justificación.

  python revision.py claude-sonnet-5-5_v3        escribe resultados/<carpeta>/revision.html
  python revision.py claude-sonnet-5-5_v3 piloto/sin_identificar.csv
                                                 solo las obras de esa lista -> revision_<lista>.html

Cada dato identificado lleva un color, el mismo en el recuadro sobre la foto y en la tabla:
título, serie, autor, censor y editor. Sirve las fichas antiguas (v2) también, sin recuadros.
Solo para este PC: las fotos van dentro de la página. El fichero queda en resultados/, fuera
de git, y no se sube a ningún sitio.
"""
from __future__ import annotations

import base64
import html
import json
import sys
from io import BytesIO
from pathlib import Path

import imagen
import piloto

ESTILO = """
:root{--papel:#f7f4ee;--tinta:#1d1b18;--gris:#6b665e;--linea:#d9d3c7;--ok:#2f6b3a;--mal:#9b2c1f;--aviso:#8a6a12}
@media (prefers-color-scheme:dark){:root{--papel:#171614;--tinta:#ece7dd;--gris:#a39d92;--linea:#3a3732;--ok:#7fc08b;--mal:#e58a7c;--aviso:#d9b55a}}
body{margin:0;background:var(--papel);color:var(--tinta);font:15px/1.45 system-ui,sans-serif}
main{max-width:1280px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:8px 0 6px}
article{display:grid;grid-template-columns:minmax(240px,420px) 1fr;gap:22px;padding:22px 0;border-top:1px solid var(--linea)}
@media (max-width:820px){article{grid-template-columns:1fr}}
img{width:100%;height:auto;border:1px solid var(--linea)}
h2{font-size:17px;margin:0 0 4px}
table{border-collapse:collapse;width:100%;font-size:14px}
td,th{border-bottom:1px solid var(--linea);padding:5px 6px;text-align:left;vertical-align:top}
th{color:var(--gris);font-weight:500}
.campo{white-space:nowrap;font-weight:600}
.muestra{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:-1px;border:2px solid}
.ok{color:var(--ok)}.mal{color:var(--mal)}.aviso{color:var(--aviso)}
.peq{color:var(--gris);font-size:13px}
.just{font-size:13px;color:var(--tinta);opacity:.85}
ul{margin:4px 0;padding-left:18px}
a{color:inherit}
.tienda{font-size:13px;margin:0 0 10px}
"""

CAMPOS = [  # clave en la ficha, clave de color, nombre
    ("titulo", "titulo", "Título"),
    ("serie", "serie", "Serie"),
    ("artista", "artista", "Autor"),
    ("censor", "censor", "Censor y fecha"),
    ("editor", "editor", "Editor"),
]


def e(valor) -> str:
    return html.escape(str(valor)) if valor not in (None, "", []) else '<span class="peq">—</span>'


def a_data(im) -> str:
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=84)
    return "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _cajas(dato) -> list:
    if not isinstance(dato, dict):
        return []
    cajas = dato.get("cajas") or ([dato["caja"]] if dato.get("caja") else [])
    return [c for c in cajas if isinstance(c, list) and len(c) == 4 and any(c)]


def marcas_de(f: dict) -> list[dict]:
    """Los recuadros a pintar: los de los campos principales y, si faltan, los de firma y sellos."""
    marcas = []
    for clave, color, nombre in CAMPOS:
        for caja in _cajas(f.get(clave)):
            marcas.append({"campo": color, "caja": caja, "etiqueta": nombre})
    if not any(m["campo"] == "artista" for m in marcas):
        for caja in _cajas(f.get("firma")):
            marcas.append({"campo": "artista", "caja": caja, "etiqueta": "Autor"})
    tipos = {"censor": "censor", "fecha": "censor", "censor y fecha": "censor", "editor": "editor"}
    ya = {(m["campo"], tuple(m["caja"])) for m in marcas}
    for s in f.get("sellos") or []:
        color = tipos.get((s.get("tipo") or "").lower(), "otro")
        for caja in _cajas(s):
            if (color, tuple(caja)) not in ya:
                marcas.append({"campo": color, "caja": caja, "etiqueta": s.get("tipo") or "sello"})
    return marcas


def enlaces(urls) -> str:
    if isinstance(urls, str):
        urls = urls.replace(";", " ").split()
    salida = []
    for u in urls or []:
        u = str(u)
        if u.startswith("http"):
            corto = "ukiyo-e.org" if "ukiyo-e.org" in u else u.split("/")[2].removeprefix("www.")
            salida.append(f'<a href="{html.escape(u)}" target="_blank" rel="noopener">{html.escape(corto)}</a>')
    return " · ".join(salida)


def comparacion(nombre: str, gestor, agente, coincide: bool | None) -> str:
    if coincide is None or not gestor:
        return f'<span class="peq">Gestor: {e(gestor)}</span>'
    clase, palabra = ("ok", "coincide con el Gestor") if coincide else ("mal", f"el Gestor dice {html.escape(str(gestor))}")
    return f'<span class="{clase}">{"✓" if coincide else "✗"} {palabra}</span>'


def obra(r: dict, v: dict, carpeta_img: Path) -> str:
    f = r.get("ficha") or {}
    c = piloto._campo
    foto = carpeta_img / v["imagenes"][0] if v["imagenes"] else None
    marcas = marcas_de(f)
    img = ""
    if foto and foto.exists():
        img = f'<img src="{a_data(imagen.anotar(foto, marcas))}" alt="{html.escape(r["referencia"])} con los elementos identificados">'

    def texto(clave):
        d = f.get(clave) or {}
        if clave == "artista":
            return d.get("nombre")
        if clave == "editor":
            return " · ".join(x for x in (d.get("nombre"), f"sello {d['sello_lectura']}" if d.get("sello_lectura") else None) if x)
        if clave == "censor":
            fecha = f.get("fecha") or {}
            rango = f"{fecha.get('desde') or ''}–{fecha.get('hasta') or ''}" if fecha.get("desde") or fecha.get("hasta") else ""
            return " · ".join(x for x in (d.get("lectura"), d.get("sellos"), rango) if x)
        return " · ".join(x for x in (d.get("japones"), d.get("romaji"), d.get("castellano")) if x)

    coincide = {
        "artista": piloto.mismo_artista(v["artista"], c(f, "artista", "nombre")),
        "editor": piloto.mismo_editor(v["editor_literal"], c(f, "editor", "nombre")),
        "censor": piloto.mismo_anio(piloto.rango_anio(v["anio"], v["anio_literal"]), (c(f, "fecha", "desde"), c(f, "fecha", "hasta"))),
    }
    gestor = {"titulo": v["titulo"], "serie": v["serie_literal"], "artista": v["artista"], "editor": v["editor_literal"],
              "censor": v["anio"] or v["anio_literal"]}
    filas = []
    for clave, color, nombre in CAMPOS:
        d = f.get(clave) if isinstance(f.get(clave), dict) else {}
        if clave == "censor" and not d:
            d = f.get("fecha") or {}
        tono = imagen.COLORES[color][0]
        just = d.get("justificacion") or d.get("metodo") or ""
        fuentes = d.get("fuentes") or d.get("fuente") or []
        filas.append(
            f'<tr><td class="campo"><span class="muestra" style="border-color:{tono}"></span>{nombre}</td>'
            f"<td>{e(texto(clave))}<div class='just'>{e(just)}</div>"
            f"<div class='peq'>{enlaces(fuentes)}</div></td>"
            f"<td class='peq'>{e(d.get('nivel'))}<br>{e(d.get('confianza'))}</td>"
            f"<td>{comparacion(nombre, gestor[clave], texto(clave), coincide.get(clave))}</td></tr>")

    sellos = "".join(f"<li><b>{e(s.get('tipo'))}</b>: {e(s.get('lectura'))} <span class='peq'>{e(s.get('descripcion'))} · "
                     f"{e(s.get('cotejo'))} · {e(s.get('confianza'))}</span></li>" for s in f.get("sellos") or [])
    textos = "".join(f"<li><b>{e(t.get('tipo'))}</b>: {e(t.get('transcripcion'))} <span class='peq'>{e(t.get('romaji'))} · "
                     f"{e(t.get('traduccion'))}{' · corrige al OCR: ' + html.escape(str(t['corrige_ocr'])) if t.get('corrige_ocr') else ''}</span></li>"
                     for t in f.get("textos") or [])
    firma = f.get("firma") or {}
    kabuki = f.get("kabuki") or {}
    actores = ", ".join(f"{a.get('actor')} como {a.get('papel')}" for a in kabuki.get("actores") or [] if isinstance(a, dict) and a.get("actor"))
    mayor = f.get("obra_mayor") or {}
    ue = f.get("ukiyoe") or {}
    ukiyoe = ""
    if ue:
        misma = ue.get("misma_estampa")
        ukiyoe = (f"<p><b>ukiyo-e.org</b>: {'<span class=ok>misma estampa</span> ' + enlaces([misma]) if misma else '<span class=aviso>no está la misma estampa</span>'}"
                  f"{' · otras láminas: ' + enlaces(ue.get('otras_laminas')) if ue.get('otras_laminas') else ''}"
                  f"<br><span class='peq'>consultas: {e(', '.join(ue.get('consultas') or []))}</span></p>")
    pendiente = "".join(f"<li>{e(p)}</li>" for p in f.get("pendiente") or [])
    t = v.get("tienda") or {}
    tienda = (f"<p class='tienda'>Tienda: id {e(t.get('id_woo'))} · SKU <code>{e(t.get('sku'))}</code>"
              f"{' · <span class=aviso>ficha creada como copia de otra</span>' if t.get('es_copia') else ''}"
              f"{' · <a href=' + chr(34) + html.escape(t['enlace']) + chr(34) + ' target=_blank rel=noopener>ver en la tienda</a>' if t.get('enlace') else ''}</p>")
    return f"""<article id="{r['referencia']}"><div>{img}<p class="peq">{e(v['alto_cm'])} × {e(v['ancho_cm'])} cm ·
{e(f.get('tipo_obra'))} · {r.get('coste_eur', 0):.2f} € · {r.get('duracion_s', '')} s</p></div><div>
<h2>{r['referencia']}</h2>{tienda}
<table><tr><th>Campo</th><th>Lo identificado, y por qué</th><th>Nivel</th><th>Gestor</th></tr>{''.join(filas)}</table>
<p><b>Firma</b>: {e(firma.get('transcripcion'))} <span class="peq">{e(firma.get('romaji'))} · {e(firma.get('cotejo'))}</span></p>
{ukiyoe}
{f"<p><b>Kabuki</b>: {e(kabuki.get('obra'))} · {e(kabuki.get('teatro'))} · {e(kabuki.get('fecha_representacion'))}<br>{e(actores)}</p>" if kabuki.get('obra') or actores else ''}
{f"<p><b>Forma parte de</b>: {e(mayor.get('tipo'))} · {e(mayor.get('titulo'))} · {e(mayor.get('posicion'))}</p>" if mayor.get('titulo') else ''}
<p><b>Sellos</b></p><ul>{sellos or '<li class="peq">ninguno</li>'}</ul>
<p><b>Textos leídos</b></p><ul>{textos or '<li class="peq">ninguno</li>'}</ul>
{f"<p><b>Pendiente</b></p><ul>{pendiente}</ul>" if pendiente else ''}
<p class="peq">{e(f.get('estado'))}</p>
</div></article>"""


def leyenda() -> str:
    return " ".join(f'<span class="peq"><span class="muestra" style="border-color:{imagen.COLORES[k][0]}"></span>{n}</span>'
                    for _, k, n in CAMPOS)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    piloto.cargar_env()
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    lista = Path(sys.argv[2]) if len(sys.argv) == 3 else None
    solo = {l.strip() for l in lista.read_text(encoding="utf-8").splitlines()[1:] if l.strip()} if lista else None
    carpeta = piloto.RESULTADOS / sys.argv[1]
    con = piloto.abrir_gestor()
    imagenes = piloto.carpeta_imagenes()
    partes = []
    for fichero in sorted(carpeta.glob("TDP-*.json")):
        if solo is not None and fichero.stem not in solo:
            continue
        r = json.loads(fichero.read_text(encoding="utf-8"))
        partes.append(obra(r, piloto.verdad(con, r["referencia"]), imagenes))
    pagina = (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
              f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión del catalogador</title>'
              f"<style>{ESTILO}</style></head><body><main><h1>Revisión · {html.escape(sys.argv[1])} · {len(partes)} obras</h1>"
              f"<p>{leyenda()}</p>{''.join(partes)}</main></body></html>")
    destino = carpeta / (f"revision_{lista.stem}.html" if lista else "revision.html")
    destino.write_text(pagina, encoding="utf-8")
    print(f"{len(partes)} obras -> {destino}")


if __name__ == "__main__":
    main()
