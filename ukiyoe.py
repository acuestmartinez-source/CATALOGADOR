"""ukiyo-e.org, la fuente principal del taller, consultada con educación.

  python ukiyoe.py buscar "Kunichika Hauta tora"     resultados de la búsqueda de texto
  python ukiyoe.py ficha mfa/sc190207                la ficha de una estampa y sus parecidas
  python ukiyoe.py estado                            peticiones de hoy y última petición

Reglas, que no se tocan:
- Solo lo que su robots.txt permite: la búsqueda de texto (/search) y las fichas (/image/...).
  /upload/, la búsqueda por imagen, está prohibida en robots.txt y NO se automatiza: la hace
  una persona en el navegador y deja el enlace en piloto/pistas.csv.
- Una petición cada ESPERA_MIN a ESPERA_MAX segundos, con azar, también entre hilos y entre
  procesos (la hora de la última petición se guarda en disco).
- Tope diario TOPE_DIA. Al llegar, no se pregunta más hasta el día siguiente.
- Caché en disco para siempre: una ficha no se pide dos veces.
- Ante 429, 403 o 5xx, se para todo el día y se dice; nunca se reintenta en bucle.
"""
from __future__ import annotations

import hashlib
import html
import json
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CACHE = RAIZ / "datos" / "ukiyoe_cache"
ESTADO = CACHE / "_estado.json"
BASE = "https://ukiyo-e.org"
ESPERA_MIN, ESPERA_MAX = 20.0, 35.0  # segundos entre peticiones
TOPE_DIA = 400
AGENTE = "Mozilla/5.0 (compatible; CATALOGADOR/0.3; Taller del Prado; consulta de catalogacion espaciada)"
_cerrojo = threading.Lock()


class Parado(Exception):
    """ukiyo-e.org ha pedido que paremos, o se ha llegado al tope del día."""


def _estado() -> dict:
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e = {}
    if e.get("dia") != date.today().isoformat():
        e = {"dia": date.today().isoformat(), "peticiones": 0, "ultima": e.get("ultima", 0), "parado": None}
    return e


def _guardar(e: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e), encoding="utf-8")


def _pedir(ruta: str) -> str:
    """GET con caché, espera y tope. Lanza Parado si no se debe preguntar."""
    if ruta.startswith("/upload"):
        raise ValueError("/upload/ está prohibido por robots.txt de ukiyo-e.org")
    url = BASE + ruta
    fichero = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")
    if fichero.exists():
        return fichero.read_text(encoding="utf-8")
    with _cerrojo:  # una petición a la vez en todo el proceso
        e = _estado()
        if e.get("parado"):
            raise Parado(e["parado"])
        if e["peticiones"] >= TOPE_DIA:
            raise Parado(f"tope de {TOPE_DIA} peticiones de hoy alcanzado")
        espera = e["ultima"] + random.uniform(ESPERA_MIN, ESPERA_MAX) - time.time()
        if espera > 0:
            time.sleep(espera)
        pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept-Language": "en"})
        try:
            with urllib.request.urlopen(pedido, timeout=60) as r:
                texto = r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            e["ultima"] = time.time()
            if err.code in (403, 429) or err.code >= 500:
                e["parado"] = f"ukiyo-e.org contestó {err.code} el {date.today().isoformat()}: se para hasta mañana"
                _guardar(e)
                raise Parado(e["parado"]) from err
            _guardar(e)
            raise
        finally:
            e["peticiones"] += 1
            e["ultima"] = time.time()
            _guardar(e)
    fichero.write_text(texto, encoding="utf-8")
    return texto


def _limpio(trozo: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", trozo or "")).strip()


def buscar(consulta: str, limite: int = 24) -> list[dict]:
    """Búsqueda de texto. Devuelve id, título, artista y fuente de cada resultado."""
    texto = _pedir("/search?q=" + urllib.parse.quote_plus(consulta))
    total = re.search(r"([\d,]+)\s+(?:prints|results)", texto)
    salida = []
    for bloque in re.findall(r'<div class="img col-[^"]*">(.*?)</div></div></div>', texto, re.S):
        enlace = re.search(r'href="/image/([^"]+)"', bloque)
        alt = re.search(r'alt="([^"]*)"', bloque)
        fuente = re.search(r'class="source"[^>]*>([^<]*)<', bloque) or re.search(r'title="([^"]*)" href="/source', bloque)
        if not enlace:
            continue
        descripcion = html.unescape(alt.group(1)) if alt else ""
        m = re.match(r'Japanese Print "(.*)" by (.*)$', descripcion)
        salida.append({
            "id": enlace.group(1),
            "url": f"{BASE}/image/{enlace.group(1)}",
            "titulo": m.group(1) if m else descripcion,
            "artista": m.group(2) if m else "",
            "fuente": _limpio(fuente.group(1)) if fuente else "",
        })
        if len(salida) >= limite:
            break
    return salida


def ficha(id_: str) -> dict:
    """Una ficha: título, artista con kanji, fecha, enlace al museo, fuente y las estampas parecidas con su %."""
    id_ = id_.removeprefix(f"{BASE}/image/").removeprefix("/image/").strip("/")
    texto = _pedir(f"/image/{id_}")

    def campo(clase):
        m = re.search(rf'<p class="row {clase}"><strong[^>]*>[^<]*</strong><span[^>]*>(.*?)</span></p>', texto, re.S)
        return _limpio(m.group(1)) if m else ""

    detalles = re.search(r'<p class="row details">.*?href="([^"]+)"', texto, re.S)
    alt = re.search(r'<div class="col-xs-12 col-md-6 imageholder">.*?alt="([^"]*)"', texto, re.S)
    descripcion = re.search(r'description:(null|"(?:[^"\\]|\\.)*")', texto)  # la primera es la de esta estampa
    parecidas = []
    zona = texto.split("Similar Prints", 1)[1] if "Similar Prints" in texto else ""
    for bloque in re.findall(r'<div class="img col-[^"]*">(.*?)</div></div></div>', zona, re.S):
        enlace = re.search(r'href="/image/([^"]+)"', bloque)
        a = re.search(r'alt="([^"]*)"', bloque)
        pct = re.search(r'(\d+)% match', bloque)
        if enlace:
            parecidas.append({"id": enlace.group(1), "url": f"{BASE}/image/{enlace.group(1)}",
                              "descripcion": html.unescape(a.group(1)) if a else "",
                              "coincidencia_pct": int(pct.group(1)) if pct else None})
    return {
        "id": id_,
        "url": f"{BASE}/image/{id_}",
        "titulo": campo("title"),
        "artista": campo("artist"),
        "artista_completo": html.unescape(alt.group(1)).split(" by ", 1)[-1] if alt else "",
        "fecha": campo("date"),
        "descripcion": (json.loads(descripcion.group(1)) or "") if descripcion else "",
        "ficha_original": detalles.group(1) if detalles else "",
        "fuente": re.sub(r"\s*Browse all.*$", "", campo("source")).strip(),
        "parecidas": parecidas[:12],
    }


def estado() -> dict:
    e = _estado()
    return {"dia": e["dia"], "peticiones_hoy": e["peticiones"], "tope": TOPE_DIA,
            "segundos_desde_la_ultima": round(time.time() - e["ultima"]) if e.get("ultima") else None,
            "parado": e.get("parado")}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 3 and sys.argv[1] == "buscar":
        print(json.dumps(buscar(" ".join(sys.argv[2:])), ensure_ascii=False, indent=1))
    elif len(sys.argv) == 3 and sys.argv[1] == "ficha":
        print(json.dumps(ficha(sys.argv[2]), ensure_ascii=False, indent=1))
    elif len(sys.argv) == 2 and sys.argv[1] == "estado":
        print(json.dumps(estado(), ensure_ascii=False))
    else:
        sys.exit(__doc__)
