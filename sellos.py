"""Sellos de editor de ukiyo-e: tabla local sacada de la Ukiyo-e Signature Sample Database (ukiyoesig.net).

  python sellos.py construir          descarga la página una vez y escribe datos/sellos_editor.json
  python sellos.py buscar 近久         lo que el agente vería al consultar esos caracteres

Fuente: Alec Wood, Ukiyo-e Publisher Seal Database, https://www.ukiyoesig.net/pubseals.html
(sigue el sistema de formas de Andreas Marks). Uso interno de consulta; los datos quedan
en datos/, fuera de git.
"""
from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
import urllib.request
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
URL = "https://www.ukiyoesig.net/pubseals.html"
PAGINA = RAIZ / "datos" / "ukiyoesig_pubseals.html"
TABLA = RAIZ / "datos" / "sellos_editor.json"

FORMAS = {
    1: "una montaña", 2: "dos montañas", 3: "tres montañas", 4: "hoces cruzadas", 5: "otras montañas",
    6: "ángulo recto", 7: "rombo", 8: "círculo", 9: "hexágono u octógono", 10: "triángulo", 11: "abanico",
    12: "calabaza", 13: "gema (lágrima)", 14: "jarra", 15: "solo caracteres", 16: "cuadrado",
    17: "líneas en cuadrado", 18: "texto horizontal", 19: "texto horizontal con sello",
    20: "óvalo", 21: "sello con texto vertical (una línea)", 22: "sello con texto vertical (dos líneas)",
    23: "sello con texto vertical (tres líneas)", 24: "texto horizontal y luego vertical",
    25: "texto vertical (una línea)", 26: "texto vertical (dos líneas)", 27: "texto vertical (tres líneas)",
    28: "texto vertical (cuatro líneas)", 29: "texto vertical (cinco líneas)", 30: "varios",
}


def _limpio(trozo: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", trozo)).strip()


def analizar(pagina: str) -> list[dict]:
    """Una fila por sello, con su editor. La página va por bloques <div class="name">."""
    editores: dict[str, dict] = {}
    sellos = []
    for bloque in pagina.split('<div class="name"')[1:]:
        cabecera = re.search(r'id="n(\d+)"', bloque[:40])
        if cabecera:
            lugar = re.search(r'class="place-label">([^<]*)<', bloque)
            romaji = re.search(r'<h2 class="romaji-key">(.*?)</h2>', bloque, re.S)
            kanji = re.search(r'<div class="kanji-key">(.*?)</div>', bloque, re.S)
            editores[cabecera.group(1)] = {
                "editor": _limpio(romaji.group(1)) if romaji else "",
                "editor_kanji": _limpio(kanji.group(1)) if kanji else "",
                "lugar": _limpio(lugar.group(1)) if lugar else "",
            }
            continue
        firma = re.search(r'data-shape="(\d*)"[^>]*data-pub-id="(\d+)"', bloque)
        if not firma:
            continue
        textos = [_limpio(t) for t in re.findall(r'<div class="sig-romaji">(.*?)</div>', bloque, re.S)]
        fecha = re.search(r'<div class="dates">(.*?)</div>', bloque, re.S)
        fuente = re.search(r'<div class="sig-source"><a href="([^"]+)"', bloque)
        forma = int(firma.group(1)) if firma.group(1) else None
        sellos.append({
            **editores.get(firma.group(2), {"editor": "", "editor_kanji": "", "lugar": ""}),
            "id_editor": f"n{firma.group(2)}",
            "sello": textos[0] if textos else "",
            "lectura": textos[1] if len(textos) > 1 else "",
            "fecha": _limpio(fecha.group(1)) if fecha else "",
            "forma": forma,
            "forma_nombre": FORMAS.get(forma, ""),
            "fuente": html.unescape(fuente.group(1)) if fuente else "",
        })
    return sellos


def construir() -> None:
    if not PAGINA.exists():
        PAGINA.parent.mkdir(exist_ok=True)
        pedido = urllib.request.Request(URL, headers={"User-Agent": "CATALOGADOR (Taller del Prado; consulta interna)"})
        PAGINA.write_bytes(urllib.request.urlopen(pedido, timeout=60).read())
    sellos = analizar(PAGINA.read_text(encoding="utf-8"))
    TABLA.write_text(json.dumps(sellos, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(sellos)} sellos de {len({s['id_editor'] for s in sellos})} editores -> {TABLA}")


@lru_cache(maxsize=1)
def _tabla() -> list[dict]:
    if not TABLA.exists():
        construir()
    return json.loads(TABLA.read_text(encoding="utf-8"))


def _cjk(texto: str) -> set[str]:
    return {c for c in texto if unicodedata.category(c) == "Lo" and ord(c) > 0x2E80}


def _plano(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def buscar(consulta: str, limite: int = 12) -> list[dict]:
    """Sellos cuyo texto o cuyo editor comparte caracteres con la consulta, los más parecidos primero.

    Acepta kanji leídos en el sello (近久, 辻文…), el nombre del editor en kanji o en romaji.
    Los caracteres ilegibles («□», «?») se ignoran.
    """
    pedidos = _cjk(consulta)
    palabras = [p for p in re.split(r"[\s,;/]+", _plano(consulta)) if len(p) >= 3 and not _cjk(p)]
    puntuadas = []
    for s in _tabla():
        en_sello = _cjk(s["sello"])
        en_editor = _cjk(s["editor_kanji"])
        puntos = 0.0
        if pedidos:
            comunes = pedidos & en_sello
            puntos += 2 * len(comunes) / len(pedidos)
            if en_sello and comunes == en_sello:
                puntos += 1  # el sello entero está en lo leído
            puntos += 0.5 * len(pedidos & en_editor) / len(pedidos)
            if "".join(sorted(pedidos)) and consulta.strip() in s["sello"]:
                puntos += 1
        for p in palabras:
            if p in _plano(s["editor"]) or p in _plano(s["lectura"]):
                puntos += 1.5
        if puntos >= 1:
            puntuadas.append((puntos, s))
    puntuadas.sort(key=lambda x: -x[0])
    vistos, salida = set(), []
    for puntos, s in puntuadas:  # un mismo sello repetido en varias fuentes cuenta una vez
        clave = (s["id_editor"], s["sello"], s["forma"])
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append({**s, "puntos": round(puntos, 2)})
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
