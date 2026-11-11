"""El índice del taller: cada firma, sello y cartucho de cada estampa identificada, con su recorte, para
encontrar antes lo que ya se vio en otra obra y para que quien revisa lo tenga todo junto.

  python indice.py reconstruir --fichas RUTA/fichas.jsonl --cola RUTA/cola.jsonl --imagenes Z:\\IMAGENES
  python indice.py buscar cartucho_serie 江戸名勝圖會
  python indice.py galeria [--salida resultados/indice.html]
  python indice.py resumen

Qué añade a la biblioteca (`biblioteca.py`), que solo guarda la firma y los sellos que una persona
confirmó: aquí entran también los cartuchos de serie y de título, los sellos de censura y de fecha y
las marcas de grabador, y entra lo propuesto por el catalogador, marcado «sin confirmar», para que
sirva desde la primera tanda. Lo que una persona acepta, corrige o rechaza en el Gestor lo confirma,
lo corrige o lo retira.

Cómo busca. Primero por lo que DICE el cuadro: los caracteres en común con lo leído, con las formas
antiguas igualadas (國/国…). Y, para cartuchos y sellos, además por la FORMA de la tinta: el recorte se
binariza, se lleva a un lienzo fijo y se describe con un histograma de orientaciones (HOG, en CPU, sin
modelos ni red). La forma es una pista y no una prueba: medida con las 118 entradas del NAS del
11/11/2026, acierta con los sellos de editor (2 de 2) y con los cartuchos de serie (4 de 6, AUC 0,66), y
NO sirve para las firmas (AUC 0,45, como el azar: cada hoja se talla de nuevo), así que en las firmas
no se usa. El paso siguiente, si la casa lo quiere, es un modelo de imagen (DINOv2) que hay que bajar.

Solo crece: `entradas.jsonl` añade líneas y `estados.jsonl` apunta lo decidido después; `leer()` pliega
las dos cosas. De aquí solo sale hacia el agente qué es, qué dice, de quién es, si está confirmado y en
cuántas hojas; nunca una referencia de obra (D-1840).
"""
from __future__ import annotations

import hashlib
import html
import json
import sys
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import ficha as F

RAIZ = Path(__file__).resolve().parent
CARPETA = RAIZ / "datos" / "indice"
ENTRADAS, ESTADOS = CARPETA / "entradas.jsonl", CARPETA / "estados.jsonl"
RECORTES, DESCRIPTORES = CARPETA / "recortes", CARPETA / "descriptores"
#: Qué se compara con qué: una firma con firmas, un cartucho con cartuchos, un sello con sellos.
FAMILIA = {"firma": "firma", "sello_artista": "sello", "sello_editor": "sello", "sello_censor": "sello",
           "sello_fecha": "sello", "grabador": "sello", "estampador": "sello", "cartucho_serie": "cartucho",
           "cartucho_titulo": "cartucho"}
CON_FORMA = ("cartucho", "sello")  # las familias en las que la forma dice algo (medido; ver arriba)
#: El recuadro de cada dato de la ficha, como tipo de cuadro.
TIPO_DE_CAMPO = {"autor": "firma", "serie": "cartucho_serie", "titulo": "cartucho_titulo", "editor": "sello_editor",
                 "censor": "sello_censor"}
LIENZO = {"alto": (48, 144), "cuadrado": (96, 96), "ancho": (144, 48)}  # ancho x alto, por clase de forma
FORMA_PARECIDA, FORMA_MUY_PARECIDA = 0.52, 0.62  # por debajo no se dice nada (p95 y p99 de los distintos)
TEXTO_MINIMO = 0.34   # parte de los caracteres en común para decir «dice algo parecido»
_cerrojo = threading.Lock()


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jsonl(ruta: Path) -> list[dict]:
    try:
        lineas = ruta.read_bytes().splitlines()
    except FileNotFoundError:
        return []
    filas = []
    for linea in lineas:
        try:
            fila = json.loads(linea)
        except (ValueError, RecursionError):
            continue
        if isinstance(fila, dict):
            filas.append(fila)
    return filas


def _anadir(ruta: Path, fila: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a+b") as f:
        if f.seek(0, 2):
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write((json.dumps(fila, ensure_ascii=True) + "\n").encode("ascii"))


def identidad(tipo: str, id_peticion: str, referencia: str, caja: list[int]) -> str:
    clave = f"{tipo}|{id_peticion}|{referencia}|{','.join(str(int(v)) for v in caja)}"
    return "ind-" + hashlib.sha1(clave.encode("utf-8", "surrogatepass")).hexdigest()[:12]


# ---------------------------------------------------------------- la forma

def _hog(m: np.ndarray, celda: int = 8, cubos: int = 9) -> np.ndarray:
    """Histograma de orientaciones sin signo por celda, normalizado por bloques de 2 x 2 celdas. A mano:
    la versión sin interfaz de OpenCV 5 ya no trae `HOGDescriptor`."""
    m = m.astype(np.float32)
    gx, gy = cv2.Sobel(m, cv2.CV_32F, 1, 0, ksize=1), cv2.Sobel(m, cv2.CV_32F, 0, 1, ksize=1)
    fuerza = np.hypot(gx, gy)
    cubo = np.minimum((np.degrees(np.arctan2(gy, gx)) % 180.0 / (180.0 / cubos)).astype(np.int32), cubos - 1)
    alto, ancho = m.shape[0] // celda, m.shape[1] // celda
    ys, xs = np.mgrid[0:alto * celda, 0:ancho * celda]
    hist = np.zeros((alto, ancho, cubos), np.float32)
    np.add.at(hist, (ys // celda, xs // celda, cubo[:alto * celda, :ancho * celda]), fuerza[:alto * celda, :ancho * celda])
    bloques = [hist[y:y + 2, x:x + 2].reshape(-1) for y in range(alto - 1) for x in range(ancho - 1)]
    return np.concatenate([b / (np.linalg.norm(b) + 1e-6) for b in bloques]).astype(np.float32)


def describir(im: Image.Image) -> tuple[str, np.ndarray] | None:
    """La clase de forma (alto, cuadrado o ancho) y el descriptor de la tinta; None si no hay tinta."""
    valor = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2HSV)[:, :, 2]
    if min(valor.shape) < 8:
        return None
    _, tinta = cv2.threshold(cv2.GaussianBlur(valor, (3, 3), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if not 0.02 < float((tinta > 0).mean()) < 0.85:  # un recorte liso, o todo mancha
        return None
    razon = tinta.shape[0] / tinta.shape[1]
    clase = "alto" if razon > 1.6 else "ancho" if razon < 0.62 else "cuadrado"
    lienzo = cv2.GaussianBlur(cv2.resize(tinta, LIENZO[clase], interpolation=cv2.INTER_AREA), (5, 5), 0)
    d = _hog(lienzo)
    norma = float(np.linalg.norm(d))
    return (clase, d / norma) if norma else None


def forma_parecida(a: tuple[str, np.ndarray] | None, b: tuple[str, np.ndarray] | None) -> float:
    """De 0 a 1; 0 si no son de la misma clase de forma o falta alguno."""
    return round(max(0.0, float(a[1] @ b[1])), 3) if a and b and a[0] == b[0] else 0.0


# ---------------------------------------------------------------- guardar

def leer(con_retiradas: bool = False) -> list[dict]:
    """Las entradas plegadas con lo que se decidió después: `confirmada`, y el `nombre` corregido."""
    cambios: dict[str, list[dict]] = {}
    for c in _jsonl(ESTADOS):
        cambios.setdefault(c.get("id"), []).append(c)
    vistas, salida = set(), []
    for e in _jsonl(ENTRADAS):
        if e.get("id") in vistas or e.get("tipo") not in FAMILIA:
            continue
        vistas.add(e.get("id"))
        e = {**e, "confirmada": bool(e.get("confirmada")), "retirada": False}
        for c in cambios.get(e["id"], []):
            if c.get("estado") == "confirmada":
                e.update(confirmada=True, retirada=False, nombre=c.get("nombre") or e.get("nombre"))
            elif c.get("estado") == "retirada":
                e["retirada"] = True
        if con_retiradas or not e["retirada"]:
            salida.append(e)
    return salida


def anotar(tipo: str, lectura: str | None, nombre: str | None, caja, foto: Path, referencia: str = "",
           id_peticion: str = "", confirmada: bool = False) -> dict | None:
    """Guarda un cuadro con lo que se sabe de él y su recorte. Devuelve la entrada, la que ya había si es
    la misma, o None si el tipo no se guarda, la caja no vale o no se sabe ni qué dice ni de quién es."""
    caja = F.caja_valida(caja)
    lectura, nombre = F._linea(lectura, 160), F._linea(nombre, 200)
    if tipo not in FAMILIA or caja is None or not (lectura or nombre):
        return None
    ide = identidad(tipo, id_peticion, referencia, caja)
    with _cerrojo:
        ya = next((e for e in leer(con_retiradas=True) if e["id"] == ide), None)
        if ya:
            return ya
        con_recorte = False
        try:
            import imagen

            recorte = imagen.recortar(foto, tuple(caja))
            forma = describir(recorte)
            RECORTES.mkdir(parents=True, exist_ok=True)
            recorte.thumbnail((360, 360))
            recorte.save(RECORTES / f"{ide}.jpg", "JPEG", quality=88)
            con_recorte = True
            if forma:
                DESCRIPTORES.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(DESCRIPTORES / f"{ide}.npz", clase=forma[0], d=forma[1])
        except Exception as e:  # una foto rota no deja fuera el cuadro: entra sin recorte
            print(f"indice: un recorte que no se pudo guardar ({type(e).__name__})", flush=True)
        fila = {"id": ide, "tipo": tipo, "lectura": lectura, "nombre": nombre, "caja": caja, "referencia": referencia,
                "id_peticion": id_peticion, "confirmada": bool(confirmada), "recorte": con_recorte, "en": _ahora()}
        _anadir(ENTRADAS, fila)
        _formas.cache_clear()
    return fila


def desde_ficha(linea: dict, foto: Path) -> int:
    """Los cuadros de una propuesta (una línea de `fichas.jsonl`) pasan al índice como «sin confirmar»:
    el recuadro de cada dato y los cuadros de texto que identificó el modelo. Devuelve cuántos entraron."""
    ref, idp, n = linea.get("referencia") or "", linea.get("id_peticion") or "", 0
    datos = linea.get("datos") if isinstance(linea.get("datos"), dict) else {}
    hechas: list[list[int]] = []
    antes = {e["id"] for e in leer(con_retiradas=True)}

    def meter(tipo, lectura, nombre, caja) -> None:
        nonlocal n
        e = anotar(tipo, lectura, nombre, caja, foto, ref, idp)
        if e:
            hechas.append(caja)
            n += e["id"] not in antes

    for campo, tipo in TIPO_DE_CAMPO.items():
        d = datos.get(campo) if isinstance(datos.get(campo), dict) else {}
        for caja in d.get("cajas") or []:
            caja = F.caja_valida(caja)
            if caja:
                # lo que dice el cuadro: la lectura del sello o de la firma; en la serie, la parte japonesa del detalle
                partes = [x.strip() for x in str(d.get("detalle") or "").split("·")]
                meter(tipo, d.get("lectura") or next((x for x in partes if F._cjk(x)), None) or d.get("detalle"),
                      d.get("valor"), caja)
    for t in linea.get("textos") or []:
        if not isinstance(t, dict) or t.get("origen") != "modelo" or t.get("tipo") not in FAMILIA:
            continue
        caja = F.caja_valida(t.get("caja"))
        if caja is None or F._tapado(caja, hechas):
            continue  # el mismo cuadro ya entró como recuadro de un dato
        campo = F.CAMPO_DE_TIPO.get(t["tipo"])
        nombre = (datos.get(campo) or {}).get("valor") if campo else None
        meter(t["tipo"], t.get("lectura"), nombre or t.get("castellano") or t.get("romaji"), caja)
    return n


def desde_aceptada(aceptada: dict) -> int:
    """Lo que una persona decidió en el Gestor: las entradas de esa petición cuyo dato se aceptó o se
    corrigió quedan confirmadas (con el valor corregido); las del dato rechazado, retiradas."""
    idp = aceptada.get("id_peticion")
    campos = aceptada.get("campos") if isinstance(aceptada.get("campos"), dict) else {}
    n = 0
    for e in leer(con_retiradas=True):
        campo = F.CAMPO_DE_TIPO.get(e["tipo"])
        decision = campos.get(campo) if campo else None
        if not idp or e.get("id_peticion") != idp or not isinstance(decision, dict):
            continue
        estado = {"aceptado": "confirmada", "corregido": "confirmada", "rechazado": "retirada"}.get(decision.get("estado"))
        if estado:
            _anadir(ESTADOS, {"id": e["id"], "estado": estado, "nombre": F._linea(decision.get("valor"), 200), "en": _ahora()})
            n += 1
    return n


# ---------------------------------------------------------------- buscar

@lru_cache(maxsize=1)
def _formas() -> dict[str, tuple[str, np.ndarray]]:
    salida = {}
    for f in DESCRIPTORES.glob("*.npz") if DESCRIPTORES.exists() else []:
        try:
            with np.load(f) as z:
                salida[f.stem] = (str(z["clase"]), z["d"])
        except Exception:  # un fichero a medio escribir: esa entrada se busca solo por lo que dice
            continue
    return salida


def _dice_parecido(pedidos: set[str], entrada: dict) -> float:
    """Parte de los caracteres en común entre lo leído y la lectura guardada (0 a 1)."""
    propios = set(F._cjk(entrada.get("lectura") or "")) - set("画筆図")
    if not pedidos or not propios:
        return 0.0
    return len(pedidos & propios) / len(pedidos | propios)


def buscar(tipo: str, lectura: str = "", recorte: Image.Image | None = None, limite: int = 5,
           sin_referencia: str = "") -> list[dict]:
    """Lo que el taller ya vio y se parece: por lo que dice (`lectura`) y, en cartuchos y sellos, por la
    forma (`recorte`). Una fila por (tipo, de quién es): cuánto se parece lo que dice, cuánto la forma,
    en cuántas hojas está y si alguna está confirmada. `sin_referencia` deja fuera esa misma obra."""
    familia = FAMILIA.get(tipo)
    if familia is None:
        return []
    pedidos = set(F._cjk(lectura or "")) - set("画筆図")
    try:
        entradas = leer()
        formas = _formas() if recorte is not None and familia in CON_FORMA else {}
    except OSError:
        print("indice: no se pudo leer; la búsqueda sigue sin él", flush=True)
        return []
    consulta = describir(recorte) if formas else None
    grupos: dict[tuple, dict] = {}
    for e in entradas:
        if FAMILIA[e["tipo"]] != familia or (sin_referencia and e.get("referencia") == sin_referencia):
            continue
        dice = _dice_parecido(pedidos, e)
        forma = forma_parecida(consulta, formas.get(e["id"])) if consulta else 0.0
        if dice < TEXTO_MINIMO and forma < FORMA_PARECIDA:
            continue
        clave = (e["tipo"], F.normalizar(e.get("nombre") or "") or F._cjk(e.get("lectura") or ""))
        g = grupos.setdefault(clave, {"tipo": e["tipo"], "lectura": e.get("lectura"), "nombre": e.get("nombre"),
                                      "dice_parecido": 0.0, "forma_parecida": 0.0, "hojas": set(), "confirmada": False})
        g["hojas"].add(e.get("referencia") or e["id"])
        g["confirmada"] = g["confirmada"] or e["confirmada"]
        if (dice, forma) > (g["dice_parecido"], g["forma_parecida"]):
            g.update(dice_parecido=round(dice, 2), lectura=e.get("lectura") or g["lectura"])
        g["forma_parecida"] = max(g["forma_parecida"], forma)
    orden = sorted(grupos.values(), key=lambda g: (-g["confirmada"], -(g["dice_parecido"] + g["forma_parecida"])))
    return [{**g, "hojas": len(g["hojas"]),
             "forma": "muy parecida" if g["forma_parecida"] >= FORMA_MUY_PARECIDA
             else "parecida" if g["forma_parecida"] >= FORMA_PARECIDA else "—"} for g in orden[:limite]]


def resumen() -> dict:
    entradas = leer()
    por_tipo: dict[str, int] = {}
    for e in entradas:
        por_tipo[e["tipo"]] = por_tipo.get(e["tipo"], 0) + 1
    return {"entradas": len(entradas), "confirmadas": sum(e["confirmada"] for e in entradas), "por_tipo": por_tipo,
            "obras": len({e.get("referencia") for e in entradas})}


def reconstruir(fichas: Path, cola: Path, imagenes: Path) -> int:
    """Rehace el índice con las propuestas ya entregadas: cada línea de `fichas.jsonl`, con la primera
    foto de su petición en `cola.jsonl`. No repite lo que ya está."""
    fotos = {p["id_peticion"]: imagenes / p["imagenes"][0] for p in _jsonl(cola)
             if isinstance(p.get("id_peticion"), str) and p.get("imagenes")}
    n = 0
    for linea in _jsonl(fichas):
        foto = fotos.get(linea.get("id_peticion"))
        if linea.get("error") or foto is None or not foto.exists():
            continue
        n += desde_ficha(linea, foto)
    return n


# ---------------------------------------------------------------- la galería, para quien revisa

ROTULOS = {"firma": "Firmas", "sello_artista": "Sellos de artista", "cartucho_serie": "Cartuchos de serie",
           "cartucho_titulo": "Cartuchos de título", "sello_editor": "Sellos de editor", "sello_censor": "Sellos de censura",
           "sello_fecha": "Sellos de fecha", "grabador": "Marcas de grabador", "estampador": "Marcas de estampador"}


def galeria(salida: Path) -> int:
    """Una página con todos los recortes, por tipo y por de quién son, para verlos juntos: las firmas de
    un mismo autor, los sellos de un mismo editor, los cartuchos de una misma serie. Es local (lleva
    las referencias de las obras): no sale del NAS. Devuelve cuántos recortes enseña."""
    import base64

    grupos: dict[str, dict[str, list[dict]]] = {}
    for e in leer():
        if e.get("recorte") and (RECORTES / f"{e['id']}.jpg").exists():
            grupos.setdefault(e["tipo"], {}).setdefault(e.get("nombre") or "(sin atribuir)", []).append(e)
    partes, n = [], 0
    for tipo in ROTULOS:
        if tipo not in grupos:
            continue
        partes.append(f"<h2>{ROTULOS[tipo]} · {sum(len(v) for v in grupos[tipo].values())}</h2>")
        for nombre, entradas in sorted(grupos[tipo].items(), key=lambda kv: (-len(kv[1]), kv[0])):
            partes.append(f"<h3>{html.escape(nombre)} <small>{len(entradas)}</small></h3><div class='fila'>")
            for e in entradas:
                datos = base64.b64encode((RECORTES / f"{e['id']}.jpg").read_bytes()).decode("ascii")
                marca = "confirmada" if e["confirmada"] else "sin confirmar"
                partes.append(f"<figure class='{marca.replace(' ', '-')}'><img src='data:image/jpeg;base64,{datos}' alt=''>"
                              f"<figcaption>{html.escape(e.get('lectura') or '—')}<br>{html.escape(e.get('referencia') or '')}"
                              f"<br><i>{marca}</i></figcaption></figure>")
                n += 1
            partes.append("</div>")
    pagina = ("<!doctype html><html lang='es'><meta charset='utf-8'><title>Índice de firmas, sellos y cartuchos</title>"
              "<style>body{font:15px/1.4 system-ui,sans-serif;margin:24px;background:#faf8f4;color:#222}"
              "h2{border-bottom:2px solid #999;margin-top:36px}h3{margin:18px 0 6px}small{color:#777;font-weight:normal}"
              ".fila{display:flex;flex-wrap:wrap;gap:10px}figure{margin:0;width:150px;font-size:12px;text-align:center}"
              "figure img{max-width:150px;max-height:210px;border:1px solid #bbb;background:#fff}"
              "figure.confirmada img{border:3px solid #1e8449}i{color:#777}</style>"
              f"<h1>Índice de firmas, sellos y cartuchos del taller</h1><p>{n} recortes de {resumen()['obras']} obras. "
              "Con borde verde, lo confirmado por una persona en el Gestor; lo demás es propuesta del catalogador.</p>"
              + "".join(partes) + "</html>")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(pagina, encoding="utf-8")
    return n


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="orden", required=True)
    r = sub.add_parser("reconstruir")
    r.add_argument("--fichas", type=Path, required=True)
    r.add_argument("--cola", type=Path, required=True)
    r.add_argument("--imagenes", type=Path, required=True)
    b = sub.add_parser("buscar")
    b.add_argument("tipo", choices=sorted(FAMILIA))
    b.add_argument("lectura")
    g = sub.add_parser("galeria")
    g.add_argument("--salida", type=Path, default=RAIZ / "resultados" / "indice.html")
    sub.add_parser("resumen")
    a = p.parse_args()
    if a.orden == "reconstruir":
        print(f"{reconstruir(a.fichas, a.cola, a.imagenes)} cuadros nuevos; {json.dumps(resumen(), ensure_ascii=False)}")
    elif a.orden == "buscar":
        print(json.dumps(buscar(a.tipo, a.lectura), ensure_ascii=False, indent=1))
    elif a.orden == "galeria":
        print(f"{galeria(a.salida)} recortes en {a.salida}")
    else:
        print(json.dumps(resumen(), ensure_ascii=False))
