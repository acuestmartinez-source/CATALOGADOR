"""Página de revisión local de una pasada: foto, ficha del Gestor y ficha del agente, lado a lado.

  python revision.py claude-sonnet-5-5_v2        escribe resultados/<carpeta>/revision.html
  python revision.py claude-sonnet-5-5_v2 piloto/sin_identificar.csv
                                                 solo las obras de esa lista -> revision_<lista>.html

Solo para este PC: las fotos se enlazan desde Z:\\IMAGENES con file://, no se copian ni se suben.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import piloto

ESTILO = """
:root{--papel:#f7f4ee;--tinta:#1d1b18;--gris:#6b665e;--linea:#d9d3c7;--ok:#2f6b3a;--mal:#9b2c1f;--duda:#8a6a12}
@media (prefers-color-scheme:dark){:root{--papel:#171614;--tinta:#ece7dd;--gris:#a39d92;--linea:#3a3732;--ok:#7fc08b;--mal:#e58a7c;--duda:#d9b55a}}
body{margin:0;background:var(--papel);color:var(--tinta);font:15px/1.45 system-ui,sans-serif}
main{max-width:1200px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:8px 0 16px}
article{display:grid;grid-template-columns:minmax(220px,340px) 1fr;gap:20px;padding:20px 0;border-top:1px solid var(--linea)}
@media (max-width:760px){article{grid-template-columns:1fr}}
img{width:100%;height:auto;border:1px solid var(--linea)}
h2{font-size:17px;margin:0 0 8px}
table{border-collapse:collapse;width:100%;font-size:14px}
td,th{border-bottom:1px solid var(--linea);padding:4px 6px;text-align:left;vertical-align:top}
th{color:var(--gris);font-weight:500;width:12%}
.ok{color:var(--ok)}.mal{color:var(--mal)}.duda{color:var(--duda)}
.peq{color:var(--gris);font-size:13px}
ul{margin:4px 0;padding-left:18px}
a{color:inherit}
"""


def miniatura(ruta: Path, lado: int = 700) -> str:
    import base64
    from io import BytesIO
    from PIL import Image

    with Image.open(ruta) as im:
        im = im.convert("RGB")
        im.thumbnail((lado, lado))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode("ascii")


def marca(acierto: bool | None, confianza: str) -> str:
    if acierto is None:
        return f'<span class="peq">{html.escape(confianza or "")}</span>'
    clase, palabra = ("ok", "✓ coincide") if acierto else ("mal", "✗ distinto")
    return f'<span class="{clase}">{palabra}</span> <span class="peq">{html.escape(confianza or "")}</span>'


def e(valor) -> str:
    return html.escape(str(valor)) if valor not in (None, "") else '<span class="peq">—</span>'


def enlaces(texto: str) -> str:
    partes = []
    for trozo in str(texto or "").replace(";", " ").split():
        if trozo.startswith("http"):
            partes.append(f'<a href="{html.escape(trozo)}" target="_blank" rel="noopener">fuente</a>')
    return " ".join(partes)


def obra(r: dict, v: dict, carpeta_img: Path) -> str:
    f = r.get("ficha") or {}
    c = piloto._campo
    foto = carpeta_img / v["imagenes"][0] if v["imagenes"] else None
    tiene_verdad = bool(v["editor_literal"] or v["serie_literal"])

    def fila(nombre, gestor, agente, acierto, confianza, fuente=""):
        return (f"<tr><th>{nombre}</th><td>{e(gestor)}</td><td>{e(agente)} {enlaces(fuente)}</td>"
                f"<td>{marca(acierto if tiene_verdad or nombre == 'Artista' else None, confianza)}</td></tr>")

    fecha = f"{c(f, 'fecha', 'desde') or ''}–{c(f, 'fecha', 'hasta') or ''}"
    serie = " · ".join(x for x in (c(f, "serie", "japones"), c(f, "serie", "romaji"), c(f, "serie", "castellano")) if x)
    titulo = " · ".join(x for x in (c(f, "titulo", "japones"), c(f, "titulo", "romaji"), c(f, "titulo", "castellano")) if x)
    filas = [
        fila("Artista", v["artista"], c(f, "artista", "nombre"),
             piloto.mismo_artista(v["artista"], c(f, "artista", "nombre")), c(f, "artista", "confianza"), c(f, "artista", "fuente")),
        fila("Título", v["titulo"], titulo, None, c(f, "titulo", "confianza"), c(f, "titulo", "fuente")),
        fila("Serie", v["serie_literal"], serie, None, c(f, "serie", "confianza"), c(f, "serie", "fuente")),
        fila("Editor", v["editor_literal"], f"{c(f, 'editor', 'nombre') or ''} (sello {c(f, 'editor', 'sello_lectura') or '—'})",
             piloto.mismo_editor(v["editor_literal"], c(f, "editor", "nombre")), c(f, "editor", "confianza"), c(f, "editor", "fuente")),
        fila("Fecha", v["anio"] or v["anio_literal"], f"{fecha} · {c(f, 'fecha', 'metodo') or ''}",
             piloto.mismo_anio(piloto.rango_anio(v["anio"], v["anio_literal"]), (c(f, "fecha", "desde"), c(f, "fecha", "hasta"))),
             c(f, "fecha", "confianza")),
    ]
    sellos = "".join(f"<li><b>{e(s.get('tipo'))}</b> · {e(s.get('posicion'))}: {e(s.get('lectura'))} "
                     f"<span class='peq'>{e(s.get('descripcion'))} · {e(s.get('confianza'))}</span></li>"
                     for s in c(f, "sellos", defecto=[]) or [])
    textos = "".join(f"<li><b>{e(t.get('tipo'))}</b>: {e(t.get('transcripcion'))} <span class='peq'>{e(t.get('romaji'))} · "
                     f"{e(t.get('traduccion'))}</span></li>" for t in c(f, "textos", defecto=[]) or [])
    kabuki = c(f, "kabuki", defecto={}) or {}
    actores = ", ".join(f"{a.get('actor')} como {a.get('papel')}" for a in kabuki.get("actores") or [] if a.get("actor"))
    mayor = c(f, "obra_mayor", defecto={}) or {}
    ejemplares = "".join(f'<li><a href="{html.escape(x.get("url") or "")}" target="_blank" rel="noopener">{e(x.get("institucion"))}</a> '
                         f'<span class="peq">{"misma composición" if x.get("misma_composicion") else "otra lámina"}</span></li>'
                         for x in c(f, "ejemplares", defecto=[]) or [])
    pendiente = "".join(f"<li>{e(p)}</li>" for p in c(f, "pendiente", defecto=[]) or [])
    img = f'<img src="{miniatura(foto)}" alt="{html.escape(r["referencia"])}">' if foto and foto.exists() else ""
    return f"""<article id="{r['referencia']}"><div>{img}<p class="peq">{e(v['alto_cm'])} × {e(v['ancho_cm'])} cm ·
{e(c(f, 'tipo_obra'))} · {r.get('coste_eur', 0):.2f} € · {r.get('duracion_s', '')} s</p></div><div>
<h2>{r['referencia']}</h2>
<table><tr><th></th><th>Gestor</th><th>Agente</th><th></th></tr>{''.join(filas)}</table>
{f"<p><b>Kabuki</b>: {e(kabuki.get('obra'))} · {e(kabuki.get('teatro'))} · {e(kabuki.get('fecha_representacion'))}<br>{e(actores)}</p>" if kabuki.get('obra') or actores else ''}
{f"<p><b>Forma parte de</b>: {e(mayor.get('tipo'))} · {e(mayor.get('titulo'))} · {e(mayor.get('posicion'))}</p>" if mayor.get('titulo') else ''}
<p><b>Sellos</b></p><ul>{sellos or '<li class="peq">ninguno</li>'}</ul>
<p><b>Textos leídos</b></p><ul>{textos or '<li class="peq">ninguno</li>'}</ul>
{f"<p><b>Ejemplares</b></p><ul>{ejemplares}</ul>" if ejemplares else ''}
{f"<p><b>Pendiente</b></p><ul>{pendiente}</ul>" if pendiente else ''}
<p class="peq">{e(c(f, 'estado'))}</p>
</div></article>"""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    piloto.cargar_env()
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    lista = Path(sys.argv[2]) if len(sys.argv) == 3 else None
    solo = None
    if lista:
        solo = {l.strip() for l in lista.read_text(encoding="utf-8").splitlines()[1:] if l.strip()}
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
              f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión del piloto</title>'
              f"<style>{ESTILO}</style></head><body><main><h1>Revisión · {html.escape(sys.argv[1])} · {len(partes)} obras</h1>"
              f"{''.join(partes)}</main></body></html>")
    destino = carpeta / (f"revision_{lista.stem}.html" if lista else "revision.html")
    destino.write_text(pagina, encoding="utf-8")
    print(f"{len(partes)} obras -> {destino}")


if __name__ == "__main__":
    main()
