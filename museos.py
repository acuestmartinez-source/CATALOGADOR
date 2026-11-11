"""Fuentes abiertas con API, para confirmar lo que se lee en la estampa: Japan Search, el Art Institute
of Chicago y el Cleveland Museum of Art. Y la imagen de referencia de una ficha, para comparar con la
foto del taller qué textos y qué sellos lleva cada ejemplar.

  python museos.py buscar japan_search "江戸名勝図会 浅草寺"
  python museos.py buscar aic "Utagawa Hiroshige II famous places Edo"
  python museos.py buscar cleveland "Kunisada"
  python museos.py ficha aic 4371
  python museos.py estado

Qué es cada una:
- **Japan Search** (jpsearch.go.jp, Biblioteca Nacional de la Dieta): el agregador nacional de Japón, con
  API pública. Junta la colección digital de la NDL, ColBase (museos nacionales), la Biblioteca
  Metropolitana de Tokio, ADEAC (bibliotecas municipales) y los metadatos del portal de nishiki-e del
  ARC. Se busca **en japonés** (título de la serie y de la lámina) y devuelve autor, editor y fecha.
- **Art Institute of Chicago** (api.artic.edu) y **Cleveland Museum of Art** (openaccess-api): API
  abierta, con ficha completa (inscripciones, medidas, serie) e imagen de dominio público.

Reglas, las mismas que `ukiyoe.py`:
- Solo las API públicas documentadas y las imágenes que esas API enseñan. Nunca se sube una foto.
- Una petición cada ESPERA_MIN a ESPERA_MAX segundos por servidor, con azar; tope diario por servidor.
- Caché en disco para siempre: lo que ya se pidió no se vuelve a pedir.
- Ante 403, 429 o 5xx ese servidor se para hasta el día siguiente; nunca se reintenta en bucle.
- De la base del ARC llegan solo los metadatos que Japan Search publica; sus páginas (dh-jac.net)
  no se abren. `TDP_JPS_SIN_ARC=si` deja fuera también esos metadatos.
"""
from __future__ import annotations

import hashlib
import json
import os
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
CACHE = RAIZ / "datos" / "museos_cache"
ESTADO = CACHE / "_estado.json"
ESPERA_MIN, ESPERA_MAX = 2.0, 4.0  # segundos entre peticiones al mismo servidor (son API, no páginas)
TOPE_DIA = 300                     # por servidor
MAX_IMAGEN = 8 * 1024 * 1024       # bytes: una imagen de referencia mayor no se baja
AGENTE = "CATALOGADOR/0.7 (Taller del Prado; consulta de catalogacion espaciada)"
FUENTES = ("japan_search", "aic", "cleveland")
#: Los únicos servidores de los que se baja una imagen de referencia: los de las fuentes de arriba y el
#: de ukiyo-e.org (su robots.txt solo prohíbe /uploads/). La URL la escribe el modelo: sin esta lista
#: sería una puerta a cualquier sitio.
SERVIDORES_DE_IMAGEN = ("data.ukiyo-e.org", "www.artic.edu", "openaccess-cdn.clevelandart.org",
                        "dl.ndl.go.jp", "adeac.jp", "colbase.nich.go.jp", "images.metmuseum.org")
_cerrojo = threading.Lock()


class Parado(Exception):
    """El servidor ha pedido que paremos, o se ha llegado al tope del día."""


class NoPermitida(ValueError):
    """Una dirección que no es de las fuentes."""


def _estado() -> dict:
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e = {}
    if e.get("dia") != date.today().isoformat():
        e = {"dia": date.today().isoformat(), "servidores": {}}
    return e


def _guardar(e: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e), encoding="utf-8")


def _pedir(url: str, sufijo: str = ".json", tope_bytes: int | None = None) -> bytes:
    """GET con caché, espera y tope por servidor. Lanza Parado si no se debe preguntar."""
    partes = urllib.parse.urlsplit(url)
    if partes.scheme != "https" or not partes.hostname:
        raise NoPermitida("solo direcciones https")
    servidor = partes.hostname
    fichero = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + sufijo)
    if fichero.exists():
        return fichero.read_bytes()
    with _cerrojo:  # una petición a la vez en todo el proceso
        e = _estado()
        s = e["servidores"].setdefault(servidor, {"peticiones": 0, "ultima": 0, "parado": None})
        if s.get("parado"):
            raise Parado(s["parado"])
        if s["peticiones"] >= TOPE_DIA:
            raise Parado(f"tope de {TOPE_DIA} peticiones de hoy a {servidor}")
        espera = s["ultima"] + random.uniform(ESPERA_MIN, ESPERA_MAX) - time.time()
        if espera > 0:
            time.sleep(espera)
        pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept-Language": "en"})
        try:
            with urllib.request.urlopen(pedido, timeout=60) as r:
                cuerpo = r.read((tope_bytes or 20 * 1024 * 1024) + 1)
        except urllib.error.HTTPError as err:
            if err.code in (403, 429) or err.code >= 500:
                s["parado"] = f"{servidor} contestó {err.code} el {date.today().isoformat()}: se para hasta mañana"
                raise Parado(s["parado"]) from err
            raise
        finally:
            s["peticiones"] += 1
            s["ultima"] = time.time()
            _guardar(e)
    if tope_bytes and len(cuerpo) > tope_bytes:
        raise NoPermitida("la imagen pesa demasiado")
    CACHE.mkdir(parents=True, exist_ok=True)
    fichero.write_bytes(cuerpo)
    return cuerpo


def _json(url: str) -> dict:
    return json.loads(_pedir(url).decode("utf-8", errors="replace"))


def _texto(v, largo: int = 400) -> str:
    """Un valor de una API, en una línea y con tope: lo que llega va a la conversación."""
    if isinstance(v, (list, tuple)):
        v = " · ".join(_texto(x, largo) for x in v if x)
    return " ".join(str(v or "").split())[:largo]


# ---------------------------------------------------------------- Japan Search

#: Los campos del portal de nishiki-e del ARC tal como los publica Japan Search (van numerados): los que
#: dicen qué textos y qué sellos lleva el ejemplar de referencia. Comprobado el 11/11/2026 con
#: arc_nishikie-BAMPFA_1919_0249 («Edo meishō zue», Sensō-ji).
ARC_CAMPOS = {"4": "titulo_lectura", "13": "editor", "15": "formato", "17": "firma", "18": "autor", "19": "grabador",
              "20": "sello_de_censura", "39": "genero", "49": "anio", "50": "era", "51": "mes", "53": "lugar",
              "55": "texto_en_la_imagen", "60": "serie"}

def _jps(consulta: str, limite: int) -> list[dict]:
    datos = _json("https://jpsearch.go.jp/api/item/search/jps-cross?"
                  + urllib.parse.urlencode({"keyword": consulta, "size": min(max(limite * 2, 10), 40)}))
    sin_arc = os.environ.get("TDP_JPS_SIN_ARC", "").lower() in ("si", "sí", "1", "true")
    salida = []
    for it in datos.get("list") or []:
        c = it.get("common") or {}
        base = c.get("database") or ""
        if sin_arc and base.startswith("arc_"):
            continue
        del_arc = base.startswith("arc_")
        miniaturas = [u for u in c.get("thumbnailUrl") or [] if isinstance(u, str)]
        salida.append({
            "fuente": "japan_search", "id": _texto(c.get("id") or it.get("id"), 120), "base": base,
            "titulo": _texto(c.get("title")), "autor_y_editor": _texto(c.get("contributor")),
            "fecha": _texto(c.get("temporal"), 80),
            # la página del ARC no se abre (dh-jac.net): de sus fichas vale lo que Japan Search publica
            "url": f"https://jpsearch.go.jp/item/{c.get('id')}" if del_arc else _texto(c.get("linkUrl"), 300),
            "imagen": next((u for u in miniaturas if imagen_permitida(u)), ""),
        })
        if len(salida) >= limite:
            break
    return salida


def _jps_ficha(id_: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{3,160}", id_):
        raise NoPermitida("id de Japan Search no válido")
    it = _json(f"https://jpsearch.go.jp/api/item/{id_}")
    c = it.get("common") or {}
    propios = {}
    del_arc = str(c.get("database") or "").startswith("arc_")
    for clave, v in it.items():  # los campos propios de cada base: sello de editor, censura, formato…
        if clave in ("common", "id", "rdfindex") or not isinstance(v, (str, list)):
            continue
        numero = clave.split("-")[-2] if clave.count("-") >= 2 else clave
        t = _texto(v, 300)
        if not t or t.startswith("http") or t in ("-", "・"):
            continue
        if del_arc:  # del portal de nishiki-e solo lo que sirve para cotejar; ni signaturas ni derechos
            if numero in ARC_CAMPOS:
                propios[ARC_CAMPOS[numero]] = t
        elif len(propios) < 20:
            propios[numero] = t
    return {"fuente": "japan_search", "id": id_, "base": c.get("database"), "titulo": _texto(c.get("title")),
            "autor_y_editor": _texto(c.get("contributor")), "fecha": _texto(c.get("temporal"), 80),
            "propietario": _texto(c.get("ownerOrg") or c.get("provider"), 120),
            "url": f"https://jpsearch.go.jp/item/{id_}", "campos": propios,
            "imagen": next((u for u in c.get("thumbnailUrl") or [] if isinstance(u, str) and imagen_permitida(u)), "")}


# ---------------------------------------------------------------- Art Institute of Chicago

_AIC_CAMPOS = ("id,title,alt_titles,artist_display,artist_title,date_display,date_start,date_end,medium_display,"
               "dimensions,inscriptions,publication_history,description,short_description,classification_title,"
               "image_id,is_public_domain,credit_line")


def _aic_imagen(image_id: str | None) -> str:
    return f"https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg" if image_id else ""


def _aic(consulta: str, limite: int) -> list[dict]:
    datos = _json("https://api.artic.edu/api/v1/artworks/search?" + urllib.parse.urlencode({
        "q": consulta, "limit": min(limite * 3, 30),
        "fields": "id,title,artist_title,date_display,image_id,classification_title"}))
    salida = []
    for a in datos.get("data") or []:
        if "print" not in (a.get("classification_title") or "").lower():
            continue  # la búsqueda es de toda la colección: solo estampas
        salida.append({"fuente": "aic", "id": str(a.get("id")), "titulo": _texto(a.get("title")),
                       "autor": _texto(a.get("artist_title"), 120), "fecha": _texto(a.get("date_display"), 80),
                       "url": f"https://www.artic.edu/artworks/{a.get('id')}", "imagen": _aic_imagen(a.get("image_id"))})
        if len(salida) >= limite:
            break
    return salida


def _aic_ficha(id_: str) -> dict:
    if not re.fullmatch(r"[0-9]{1,9}", id_):
        raise NoPermitida("id del Art Institute no válido")
    a = _json(f"https://api.artic.edu/api/v1/artworks/{id_}?fields={_AIC_CAMPOS}").get("data") or {}
    return {"fuente": "aic", "id": id_, "titulo": _texto(a.get("title")), "otros_titulos": _texto(a.get("alt_titles")),
            "autor": _texto(a.get("artist_display"), 200), "fecha": _texto(a.get("date_display"), 80),
            "tecnica": _texto(a.get("medium_display"), 200), "medidas": _texto(a.get("dimensions"), 200),
            "inscripciones": _texto(a.get("inscriptions"), 500),
            "descripcion": _texto(re.sub(r"<[^>]+>", " ", a.get("description") or a.get("short_description") or ""), 700),
            "url": f"https://www.artic.edu/artworks/{id_}", "imagen": _aic_imagen(a.get("image_id"))}


# ---------------------------------------------------------------- Cleveland Museum of Art

def _cma_fila(a: dict, completa: bool = False) -> dict:
    autores = _texto([c.get("description") for c in a.get("creators") or [] if isinstance(c, dict)], 200)
    fila = {"fuente": "cleveland", "id": str(a.get("id")), "titulo": _texto(a.get("title")), "autor": autores,
            "fecha": _texto(a.get("creation_date"), 80), "url": _texto(a.get("url"), 200),
            "imagen": _texto(((a.get("images") or {}).get("web") or {}).get("url"), 300)}
    if completa:
        fila.update(tecnica=_texto(a.get("technique"), 200), medidas=_texto(a.get("measurements"), 200),
                    inscripciones=_texto([i.get("inscription") for i in a.get("inscriptions") or [] if isinstance(i, dict)], 500),
                    descripcion=_texto(a.get("description") or a.get("tombstone"), 700))
    return fila


def _cma(consulta: str, limite: int) -> list[dict]:
    datos = _json("https://openaccess-api.clevelandart.org/api/artworks/?" + urllib.parse.urlencode({
        "q": consulta, "type": "Print", "limit": limite, "fields": "id,title,creators,creation_date,url,images"}))
    return [_cma_fila(a) for a in (datos.get("data") or [])[:limite]]


def _cma_ficha(id_: str) -> dict:
    if not re.fullmatch(r"[0-9]{1,9}", id_):
        raise NoPermitida("id de Cleveland no válido")
    return _cma_fila(_json(f"https://openaccess-api.clevelandart.org/api/artworks/{id_}").get("data") or {}, completa=True)


# ---------------------------------------------------------------- lo que usa el agente

def buscar(fuente: str, consulta: str, limite: int = 8) -> list[dict]:
    """Resultados de una fuente: id, título, autor (y editor, en Japan Search), fecha, URL e imagen."""
    consulta = " ".join(str(consulta or "").split())[:200]
    if not consulta:
        return []
    if fuente == "japan_search":
        return _jps(consulta, limite)
    if fuente == "aic":
        return _aic(consulta, limite)
    if fuente == "cleveland":
        return _cma(consulta, limite)
    raise NoPermitida(f"fuente desconocida: {fuente}. Son: {', '.join(FUENTES)}")


def ficha(fuente: str, id_: str) -> dict:
    """La ficha entera de un resultado: inscripciones, medidas, técnica y descripción, lo que haya."""
    id_ = str(id_ or "").strip()
    if fuente == "japan_search":
        return _jps_ficha(id_)
    if fuente == "aic":
        return _aic_ficha(id_)
    if fuente == "cleveland":
        return _cma_ficha(id_)
    raise NoPermitida(f"fuente desconocida: {fuente}. Son: {', '.join(FUENTES)}")


def imagen_permitida(url: str) -> bool:
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return (p.scheme == "https" and p.hostname in SERVIDORES_DE_IMAGEN and not p.username and p.port in (None, 443)
            and "/upload" not in p.path.lower())  # /uploads/ de data.ukiyo-e.org: prohibido por su robots.txt


def imagen(url: str) -> bytes:
    """Los bytes de una imagen de referencia, solo de los servidores de las fuentes. En caché."""
    if not imagen_permitida(url):
        raise NoPermitida("esa imagen no es de una de las fuentes: " + ", ".join(SERVIDORES_DE_IMAGEN))
    return _pedir(url, sufijo=".img", tope_bytes=MAX_IMAGEN)


def estado() -> dict:
    e = _estado()
    return {"dia": e["dia"], "tope": TOPE_DIA,
            "servidores": {s: {"peticiones_hoy": v["peticiones"], "parado": v.get("parado")} for s, v in e["servidores"].items()}}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 4 and sys.argv[1] == "buscar":
        print(json.dumps(buscar(sys.argv[2], " ".join(sys.argv[3:])), ensure_ascii=False, indent=1))
    elif len(sys.argv) == 4 and sys.argv[1] == "ficha":
        print(json.dumps(ficha(sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=1))
    elif len(sys.argv) == 2 and sys.argv[1] == "estado":
        print(json.dumps(estado(), ensure_ascii=False))
    else:
        sys.exit(__doc__)
