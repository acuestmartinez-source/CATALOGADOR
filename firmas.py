"""Firmas de artistas de ukiyo-e: tabla local sacada de la Ukiyo-e Signature Sample Database (ukiyoesig.net).

  python firmas.py construir         descarga la página una vez y escribe datos/firmas_artista.json
  python firmas.py buscar 国貞        lo que vería el agente

Sirve para COTEJAR una lectura: el agente lee la firma con la lupa y comprueba que esa
secuencia de caracteres existe como firma documentada, con qué nombre de artista y en qué
años. Fuente: Alec Wood, Ukiyo-e Signature Sample Database, https://www.ukiyoesig.net/artistsigs.html
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

from sellos import _cjk, _plano

RAIZ = Path(__file__).resolve().parent
URL = "https://www.ukiyoesig.net/artistsigs.html"
PAGINA = RAIZ / "datos" / "ukiyoesig_artistsigs.html"
TABLA = RAIZ / "datos" / "firmas_artista.json"


def _limpio(trozo: str) -> str:
    return html.unescape(re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", trozo or ""))).replace("<br>", " ").strip()


def analizar(pagina: str) -> list[dict]:
    """Una fila por firma documentada, con el nombre (gagō) y las fechas del artista."""
    filas = []
    actual: dict = {}
    for trozo in re.split(r'(?=<div class="name" id="n\d+")|(?=<div class="signature")', pagina):
        if trozo.startswith('<div class="name"'):
            m = lambda patron: re.search(patron, trozo, re.S)  # noqa: E731
            romaji, kanji, completo_k, completo_r, fechas, ident = (
                m(r'<h2 class="romaji-key">(.*?)</h2>'), m(r'<div class="kanji-key">(.*?)</div>'),
                m(r'<div class="kanji-full">(.*?)</div>'), m(r'<div class="romaji-full">(.*?)</div>'),
                m(r'<div class="dates">(.*?)</div>'), m(r'id="(n\d+)"'))
            actual = {
                "id_nombre": ident.group(1) if ident else "",
                "nombre": _limpio(romaji.group(1)) if romaji else "",
                "nombre_kanji": _limpio(kanji.group(1)) if kanji else "",
                "nombre_completo": " · ".join(x for x in (_limpio(completo_r.group(1)) if completo_r else "",
                                                           _limpio(completo_k.group(1)) if completo_k else "") if x),
                "fechas_artista": _limpio(fechas.group(1)) if fechas else "",
            }
        elif trozo.startswith('<div class="signature"') and actual:
            fecha = re.search(r'<div class="signature"[^>]*>\s*<div>(.*?)</div>', trozo, re.S)
            kanji = re.search(r'<div class="sig-kanji">(.*?)</div>', trozo, re.S)
            romaji = re.search(r'<div class="sig-romaji">(.*?)</div>', trozo, re.S)
            fuente = re.search(r'<div class="sig-source"><a href="([^"]+)"', trozo)
            filas.append({
                **actual,
                "firma": _limpio(kanji.group(1)) if kanji else "",
                "lectura": _limpio(romaji.group(1)) if romaji else "",
                "fecha_firma": _limpio(fecha.group(1)) if fecha else "",
                "fuente": html.unescape(fuente.group(1)) if fuente else "",
            })
    return filas


def construir() -> None:
    if not PAGINA.exists():
        PAGINA.parent.mkdir(exist_ok=True)
        pedido = urllib.request.Request(URL, headers={"User-Agent": "CATALOGADOR (Taller del Prado; consulta interna)"})
        PAGINA.write_bytes(urllib.request.urlopen(pedido, timeout=120).read())
    filas = analizar(PAGINA.read_text(encoding="utf-8"))
    TABLA.write_text(json.dumps(filas, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(filas)} firmas de {len({f['id_nombre'] for f in filas})} nombres -> {TABLA}")


@lru_cache(maxsize=1)
def _tabla() -> list[dict]:
    if not TABLA.exists():
        construir()
    return json.loads(TABLA.read_text(encoding="utf-8"))


def buscar(consulta: str, limite: int = 10) -> list[dict]:
    """Firmas que comparten caracteres con lo leído, o nombres que coinciden en romaji.

    Puntúa más una firma cuyos caracteres están TODOS en lo leído (la lectura la contiene
    entera) y el nombre del artista en kanji. Una fila por nombre y firma distinta.
    """
    pedidos = _cjk(consulta) - {"画", "筆", "図", "□"}  # 画 y 筆 («pintado por») están en casi todas
    palabras = [p for p in re.split(r"[\s,;/]+", _plano(consulta)) if len(p) >= 3 and not _cjk(p)]
    puntuadas = []
    for f in _tabla():
        en_firma = _cjk(f["firma"]) - {"画", "筆", "図", "〇"}
        en_nombre = _cjk(f["nombre_kanji"])
        puntos = 0.0
        if pedidos:
            comunes = pedidos & (en_firma | en_nombre)
            puntos += 2 * len(comunes) / len(pedidos)
            if en_nombre and en_nombre <= pedidos:
                puntos += 1.5  # el nombre entero está en lo leído
            if en_firma and en_firma <= pedidos:
                puntos += 0.5
        for p in palabras:
            if p in _plano(f["nombre"]) or p in _plano(f["lectura"]) or p in _plano(f["nombre_completo"]):
                puntos += 1.5
        if puntos >= 1.5:
            puntuadas.append((puntos, f))
    puntuadas.sort(key=lambda x: -x[0])
    vistos, salida = set(), []
    for puntos, f in puntuadas:
        clave = (f["id_nombre"], f["firma"])
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append({**f, "puntos": round(puntos, 2)})
        if len(salida) >= limite:
            break
    return salida


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 2 and sys.argv[1] == "construir":
        construir()
    elif len(sys.argv) >= 3 and sys.argv[1] == "buscar":
        for fila in buscar(" ".join(sys.argv[2:])):
            print(json.dumps(fila, ensure_ascii=False))
    else:
        sys.exit(__doc__)
