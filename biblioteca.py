"""La biblioteca propia del taller: firmas y sellos confirmados por una persona, con su recorte.

Es lo que hace que el sistema mejore con el uso. Cada vez que una persona acepta una firma o un
sello en el Gestor (`para_catalogador/aceptadas.jsonl`), aquí se guarda el recorte de la foto, la
lectura y el nombre confirmado. Las búsquedas del agente miran primero aquí y después en las bases
de ukiyoesig.net, y lo propio pesa más: son los sellos del taller fotografiados con su cámara.

  python biblioteca.py resumen
  python biblioteca.py buscar sello 越嘉
"""
from __future__ import annotations

import json
import sys
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CARPETA = RAIZ / "datos" / "biblioteca"
TABLA = {"firma": CARPETA / "firmas.jsonl", "sello": CARPETA / "sellos.jsonl"}
RECORTES = CARPETA / "recortes"
ORO = CARPETA / "oro.jsonl"  # las fichas adjudicadas por una persona: el conjunto con el que se mide
_cerrojo = threading.Lock()


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cjk(texto: str) -> set[str]:
    from sellos import ANTIGUAS

    texto = unicodedata.normalize("NFKC", texto or "").translate(ANTIGUAS)
    return {c for c in texto if unicodedata.category(c) == "Lo" and ord(c) > 0x2E80}


def leer(tipo: str) -> list[dict]:
    try:
        return [json.loads(l) for l in TABLA[tipo].read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return []


def anotar(tipo: str, referencia: str, lectura: str, nombre: str, caja: list[int] | None, foto: Path | None,
           quien: str = "", id_peticion: str = "") -> dict:
    """Guarda una firma o un sello confirmados. Si hay foto y caja, guarda también el recorte ampliado."""
    if tipo not in TABLA:
        raise ValueError(f"tipo: firma o sello, no {tipo}")
    fila = {"referencia": referencia, "lectura": lectura, "nombre": nombre, "caja": caja, "confirmado_por": quien,
            "confirmado_en": _ahora(), "id_peticion": id_peticion, "recorte": None}
    if foto and caja and foto.exists():
        import imagen

        RECORTES.mkdir(parents=True, exist_ok=True)
        destino = RECORTES / f"{referencia}_{tipo}_{'_'.join(str(v) for v in caja)}.jpg"
        imagen.ampliar_imagen(imagen.recortar(foto, tuple(caja)), 800).save(destino, quality=90)
        fila["recorte"] = str(destino.relative_to(RAIZ))
    with _cerrojo:
        TABLA[tipo].parent.mkdir(parents=True, exist_ok=True)
        with TABLA[tipo].open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return fila


def buscar(tipo: str, consulta: str, limite: int = 6) -> list[dict]:
    """Lo confirmado por el taller que comparte caracteres con la lectura, lo más parecido primero."""
    pedidos = _cjk(consulta) - {"画", "筆", "図", "□"}
    salida = []
    for fila in leer(tipo):
        propios = _cjk(fila["lectura"])
        if not pedidos or not propios:
            continue
        comunes = len(pedidos & propios)
        if comunes:
            salida.append((comunes / len(pedidos | propios), fila))
    salida.sort(key=lambda x: -x[0])
    vistos, unicas = set(), []
    for puntos, fila in salida:
        clave = (fila["lectura"], fila["nombre"])
        if clave not in vistos:
            vistos.add(clave)
            unicas.append({**fila, "parecido": round(puntos, 2), "origen": "biblioteca del taller"})
        if len(unicas) >= limite:
            break
    return unicas


def desde_aceptada(aceptada: dict, foto: Path | None) -> dict:
    """Lo que una persona aceptó en el Gestor pasa a la biblioteca y al conjunto de oro."""
    ref, quien, idp = aceptada["referencia"], aceptada.get("aceptado_por", ""), aceptada.get("id_peticion", "")
    hecho = {"firma": 0, "sellos": 0}
    firma = aceptada.get("firma_confirmada") or {}
    if firma.get("lectura") and firma.get("nombre"):
        anotar("firma", ref, firma["lectura"], firma["nombre"], firma.get("caja"), foto, quien, idp)
        hecho["firma"] = 1
    for s in aceptada.get("sellos_confirmados") or []:
        if s.get("lectura") and s.get("nombre"):
            anotar("sello", ref, s["lectura"], f"{s.get('tipo', 'sello')}: {s['nombre']}", s.get("caja"), foto, quien, idp)
            hecho["sellos"] += 1
    with _cerrojo:
        ORO.parent.mkdir(parents=True, exist_ok=True)
        with ORO.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"referencia": ref, "id_peticion": idp, "aceptado_por": quien,
                                "aceptado_en": aceptada.get("aceptado_en") or _ahora(),
                                "campos": aceptada.get("campos") or {}}, ensure_ascii=False) + "\n")
    return hecho


def resumen() -> dict:
    oro = [json.loads(l) for l in ORO.read_text(encoding="utf-8").splitlines() if l.strip()] if ORO.exists() else []
    return {"firmas": len(leer("firma")), "sellos": len(leer("sello")), "obras_adjudicadas": len({o["referencia"] for o in oro})}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 2 and sys.argv[1] == "resumen":
        print(json.dumps(resumen(), ensure_ascii=False))
    elif len(sys.argv) >= 4 and sys.argv[1] == "buscar":
        print(json.dumps(buscar(sys.argv[2], " ".join(sys.argv[3:])), ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)
