"""Corpus de referencia de estampas japonesas de dominio público / CC0 de cuatro museos (CT-08).

  python museos.py listar <fuente> [--tope N]      baja solo metadatos a datos/museos/<fuente>/fichas.jsonl
  python museos.py descargar <fuente> [--tope N]   baja las imágenes que faltan de esas fichas
  python museos.py estado

Fuentes: aic (Art Institute of Chicago), met (The Met), rijks (Rijksmuseum), cleveland (Cleveland Museum of Art).

Reglas, que no se tocan (las de ukiyoe.py):
- Una petición a la vez por fuente, con su pausa; la hora de la última se guarda en disco.
- Tope diario TOPE_DIA peticiones por fuente. Al llegar, no se pide más hasta el día siguiente.
- Caché para siempre: una imagen no se pide dos veces, una ficha ya listada tampoco; se reanuda donde se quedó.
- Ante 403, 429 o 5xx se para esa fuente hasta el día siguiente y se dice; nunca se reintenta en bucle.
- Solo dominio público / CC0: si la ficha no lo dice claro, se apunta sin imagen y no se baja.
- Nada de saltarse Cloudflare ni captchas. User-Agent genérico, sin correo ni nombres de personas.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "datos" / "museos"
TOPE_DIA = 3000
AGENTE = "CATALOGADOR/0.9 (Taller del Prado; indice privado de consulta, descargas espaciadas)"
PAUSA = {"aic": 1.0, "met": 1.0, "rijks": 1.5, "cleveland": 1.0}  # segundos entre peticiones
LIBRES = ("CC0", "Dominio público")
ARTISTAS_RIJKS = ["Hiroshige", "Kunisada", "Toyokuni", "Kuniyoshi", "Yoshitoshi", "Kunichika", "Chikanobu", "Eisen",
                  "Hokusai"]  # «Hiroshige» ya trae a Hiroshige II; Toyokuni III es Kunisada


class Parado(Exception):
    """El museo ha pedido que paremos, o se ha llegado al tope del día."""


def _carpeta(fuente: str) -> Path:
    if fuente not in PAUSA:
        raise ValueError(f"fuente desconocida: {fuente} (son {', '.join(PAUSA)})")
    return DATOS / fuente


def _estado(fuente: str) -> dict:
    try:
        e = json.loads((_carpeta(fuente) / "_estado.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e = {}
    if e.get("dia") != date.today().isoformat():
        e = {"dia": date.today().isoformat(), "peticiones": 0, "ultima": e.get("ultima", 0), "parado": None}
    return e


def _guardar(fuente: str, e: dict) -> None:
    _carpeta(fuente).mkdir(parents=True, exist_ok=True)
    (_carpeta(fuente) / "_estado.json").write_text(json.dumps(e), encoding="utf-8")


def _pedir(fuente: str, url: str) -> bytes:
    """GET con pausa, tope y freno. Lanza Parado si no se debe preguntar."""
    e = _estado(fuente)
    if e.get("parado"):
        raise Parado(e["parado"])
    if e["peticiones"] >= TOPE_DIA:
        raise Parado(f"{fuente}: tope de {TOPE_DIA} peticiones de hoy alcanzado")
    espera = e["ultima"] + PAUSA[fuente] - time.time()
    if espera > 0:
        time.sleep(espera)
    cabeceras = {"User-Agent": AGENTE}
    if fuente == "aic":
        cabeceras["AIC-User-Agent"] = AGENTE
    if fuente == "rijks":
        cabeceras["Accept"] = "application/ld+json"  # Linked Art en JSON; sin ella, id.rijksmuseum.nl da HTML
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=cabeceras), timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as err:
        if err.code in (403, 429) or err.code >= 500:
            e["parado"] = f"{fuente} contestó {err.code} el {date.today().isoformat()}: se para hasta mañana"
            raise Parado(e["parado"]) from err
        raise
    finally:
        e["peticiones"] += 1
        e["ultima"] = time.time()
        _guardar(fuente, e)


def _json(fuente: str, url: str) -> dict:
    return json.loads(_pedir(fuente, url).decode("utf-8"))


# --- Cada fuente: un generador de fichas. `conocidos` son los id ya listados, para no volver a pedirlos. ---

def _aic(conocidos: set) -> iter:
    # La búsqueda anónima no pasa de from+size=1000 (TooManyResultsException, un 403): se avanza por id,
    # ordenado, pidiendo siempre la primera página de «id mayor que el último visto».
    campos = "id,title,artist_title,date_display,image_id,is_public_domain"
    ultimo = 0
    while True:
        params = json.dumps({"query": {"bool": {"must": [
            {"term": {"is_public_domain": True}},
            {"match": {"place_of_origin": "Japan"}},
            {"match": {"artwork_type_title": "Print"}},
            {"range": {"id": {"gt": ultimo}}}]}}, "sort": [{"id": "asc"}]})
        d = _json("aic", "https://api.artic.edu/api/v1/artworks/search?" + urllib.parse.urlencode(
            {"params": params, "fields": campos, "limit": 100}))
        for o in d["data"]:
            libre = o.get("is_public_domain") is True and o.get("image_id")
            yield {"fuente": "aic", "id": str(o["id"]), "titulo": o.get("title"), "artista": o.get("artist_title"),
                   "fecha": o.get("date_display"), "url_ficha": f"https://www.artic.edu/artworks/{o['id']}",
                   "url_imagen": f"https://www.artic.edu/iiif/2/{o['image_id']}/full/843,/0/default.jpg" if libre else None,
                   "licencia": "CC0" if libre else "no consta"}
        if len(d["data"]) < 100:
            return
        ultimo = max(o["id"] for o in d["data"])


def _met(conocidos: set) -> iter:
    base = "https://collectionapi.metmuseum.org/public/collection"
    ids, desde = [], 0
    while True:  # la búsqueda v1.1 da páginas de hasta 500 (la de v1 se retiró el 01/10/2026)
        d = _json("met", f"{base}/v1.1/search?" + urllib.parse.urlencode(
            {"departmentId": 6, "q": "Woodblock print", "geoLocation": "Japan", "hasImages": "true",
             "limit": 500, "offset": desde}))
        ids += d.get("objectIDs") or []
        desde += 500
        if not d.get("objectIDs") or desde >= min(d.get("total", 0), 10000):
            break
    for i in dict.fromkeys(ids):
        if str(i) in conocidos:
            continue
        o = _json("met", f"{base}/v1/objects/{i}")
        libre = o.get("isPublicDomain") is True and o.get("primaryImageSmall")
        yield {"fuente": "met", "id": str(i), "titulo": o.get("title"), "artista": o.get("artistDisplayName"),
               "fecha": o.get("objectDate"), "url_ficha": o.get("objectURL"),
               "url_imagen": o["primaryImageSmall"] if libre else None, "licencia": "CC0" if libre else "no consta"}


def _en_ingles(lista: list) -> str | None:
    textos = [(x.get("content"), [l.get("id", "") for l in x.get("language", [])]) for x in lista or []]
    ingles = [t for t, l in textos if any(i.endswith("300388277") for i in l)]
    return (ingles or [t for t, _ in textos] or [None])[0]


def _rijks_ficha(o: dict) -> dict:
    imagen, licencia, web = None, "no consta", None
    for s in o.get("subject_of", []):
        for dig in s.get("digitally_carried_by", []):
            punto = (dig.get("access_point") or [{}])[0].get("id", "")
            lic = [r.get("content", "") for r in dig.get("referred_to_by", [])]
            if "iiif.micr.io" in punto and any("publicdomain" in x for x in lic):
                imagen, licencia = punto.replace("/full/max/", "/full/1000,/"), "Dominio público"
            elif dig.get("format") == "text/html":
                web = web or punto
    produccion = o.get("produced_by") or {}
    nombres = [x for x in o.get("identified_by", []) if x.get("type") == "Name"]
    id_ = o["id"].rsplit("/", 1)[-1]
    return {"fuente": "rijks", "id": id_, "titulo": _en_ingles(nombres),
            "artista": _en_ingles(produccion.get("referred_to_by")),
            "fecha": _en_ingles((produccion.get("timespan") or {}).get("identified_by")),
            "url_ficha": web or o["id"], "url_imagen": imagen, "licencia": licencia}


def _rijks(conocidos: set) -> iter:
    vistos = set(conocidos)
    for artista in ARTISTAS_RIJKS:
        url = "https://data.rijksmuseum.nl/search/collection?" + urllib.parse.urlencode(
            {"creator": artista, "imageAvailable": "true"})
        while url:
            d = _json("rijks", url)
            for item in d.get("orderedItems", []):
                id_ = item["id"].rsplit("/", 1)[-1]
                if id_ in vistos:
                    continue
                vistos.add(id_)
                yield _rijks_ficha(_json("rijks", item["id"]))
            url = (d.get("next") or {}).get("id")


def _cleveland(conocidos: set) -> iter:
    salto = 0
    while True:
        d = _json("cleveland", "https://openaccess-api.clevelandart.org/api/artworks/?" + urllib.parse.urlencode(
            {"department": "Japanese Art", "type": "Print", "has_image": 1, "cc0": 1, "limit": 100, "skip": salto,
             "fields": "id,title,creators,creation_date,url,share_license_status,images"}))
        for o in d["data"]:
            web = ((o.get("images") or {}).get("web") or {}).get("url")
            libre = o.get("share_license_status") == "CC0" and web
            yield {"fuente": "cleveland", "id": str(o["id"]), "titulo": o.get("title"),
                   "artista": ((o.get("creators") or [{}])[0]).get("description"), "fecha": o.get("creation_date"),
                   "url_ficha": o.get("url"), "url_imagen": web if libre else None,
                   "licencia": "CC0" if libre else "no consta"}
        salto += 100
        if not d["data"] or salto >= d["info"]["total"]:
            return


FUENTES = {"aic": _aic, "met": _met, "rijks": _rijks, "cleveland": _cleveland}


def fichas(fuente: str) -> list[dict]:
    try:
        texto = (_carpeta(fuente) / "fichas.jsonl").read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(l) for l in texto.splitlines() if l.strip()]


def listar(fuente: str, tope: int | None = None) -> int:
    """Añade a fichas.jsonl las que aún no estén. Devuelve cuántas nuevas."""
    conocidos = {f["id"] for f in fichas(fuente)}
    _carpeta(fuente).mkdir(parents=True, exist_ok=True)
    nuevas = 0
    with open(_carpeta(fuente) / "fichas.jsonl", "a", encoding="utf-8") as salida:
        for f in FUENTES[fuente](conocidos):
            if f["id"] in conocidos:
                continue
            conocidos.add(f["id"])
            salida.write(json.dumps({**f, "fichero": None}, ensure_ascii=False) + "\n")
            salida.flush()
            nuevas += 1
            if tope is not None and nuevas >= tope:
                break
    return nuevas


def _imagen(fuente: str, id_: str) -> Path:
    return _carpeta(fuente) / "img" / (re.sub(r"[^\w.-]", "_", id_) + ".jpg")


def descargar(fuente: str, tope: int | None = None) -> int:
    """Baja las imágenes libres que falten, tal como vienen. Devuelve cuántas nuevas."""
    todas, nuevas = fichas(fuente), 0
    try:
        for f in todas:
            fichero = _imagen(fuente, f["id"])
            if f.get("licencia") in LIBRES and f.get("url_imagen") and not fichero.exists():
                if tope is not None and nuevas >= tope:
                    break
                try:
                    datos = _pedir(fuente, f["url_imagen"])
                except urllib.error.HTTPError as err:
                    print(f"{fuente} {f['id']}: {err.code}, se salta", file=sys.stderr)
                    continue
                except OSError as err:  # red caída o tiempo agotado: se deja esta pasada, sin reintentar
                    print(f"{fuente} {f['id']}: {err}; se deja esta pasada", file=sys.stderr)
                    break
                fichero.parent.mkdir(parents=True, exist_ok=True)
                fichero.write_bytes(datos)
                nuevas += 1
    finally:  # que fichas.jsonl diga qué imagen hay, también si se para a medias
        for f in todas:
            fichero = _imagen(fuente, f["id"])
            f["fichero"] = fichero.relative_to(RAIZ).as_posix() if fichero.exists() else None
        if todas:
            (_carpeta(fuente) / "fichas.jsonl").write_text(
                "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in todas), encoding="utf-8")
    return nuevas


def estado() -> dict:
    salida = {}
    for fuente in FUENTES:
        todas, e = fichas(fuente), _estado(fuente)
        salida[fuente] = {"fichas": len(todas), "libres": sum(f.get("licencia") in LIBRES for f in todas),
                          "imagenes": sum(_imagen(fuente, f["id"]).exists() for f in todas),
                          "peticiones_hoy": e["peticiones"], "tope": TOPE_DIA, "parado": e.get("parado")}
    return salida


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    tope = None
    if "--tope" in args:
        i = args.index("--tope")
        tope = int(args[i + 1])
        del args[i:i + 2]
    try:
        if len(args) == 2 and args[0] in ("listar", "descargar") and args[1] in FUENTES:
            n = (listar if args[0] == "listar" else descargar)(args[1], tope)
            print(f"{args[1]}: {n} nuevas")
        elif args == ["estado"]:
            print(json.dumps(estado(), ensure_ascii=False, indent=1))
        else:
            sys.exit(__doc__)
    except Parado as p:
        sys.exit(f"PARADO: {p}")
    except OSError as err:  # red caída o tiempo agotado: lo hecho queda guardado; se reanuda en la próxima pasada
        sys.exit(f"CORTADO por la red: {err}")
