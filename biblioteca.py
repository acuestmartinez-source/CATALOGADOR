"""La biblioteca propia del taller: firmas y sellos confirmados por una persona, con su recorte.

Es lo que hace que el sistema mejore con el uso. Cada vez que una persona acepta una firma o un
sello en el Gestor (`para_catalogador/aceptadas.jsonl`), aquí se guarda el recorte de la foto, la
lectura y el nombre confirmado. Las búsquedas del agente miran primero aquí y después en las bases
de ukiyoesig.net, y lo propio pesa más: son los sellos del taller fotografiados con su cámara.

Las tablas solo crecen. Cada entrada tiene un `id_entrada` estable (`identidad`), y lo que una
persona pide en el Gestor (`para_catalogador/biblioteca_correcciones.jsonl`) se apunta en
`correcciones.jsonl` sin tocar las tablas: corregir cambia la lectura o el nombre, retirar la saca
de las búsquedas y restaurar la devuelve. `leer` pliega las dos cosas. `oro.jsonl` no se corrige.

  python biblioteca.py resumen
  python biblioteca.py buscar sello 越嘉
"""
from __future__ import annotations

import hashlib
import json
import re
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
CORRECCIONES = CARPETA / "correcciones.jsonl"  # lo aplicado de lo que pidió el Gestor; solo crece
ACCIONES = ("corregir", "retirar", "restaurar")
ID_CORRECCION, ID_ENTRADA = re.compile(r"bic-[0-9]{6}"), re.compile(r"bib-[0-9a-f]{12}")
LARGO_LECTURA, LARGO_NOMBRE = 40, 120
_cerrojo = threading.Lock()


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cjk(texto: str) -> set[str]:
    from sellos import ANTIGUAS

    texto = unicodedata.normalize("NFKC", texto or "").translate(ANTIGUAS)
    return {c for c in texto if unicodedata.category(c) == "Lo" and ord(c) > 0x2E80}


def _jsonl(ruta: Path) -> list[dict]:
    """Las filas de un fichero propio; una línea rota (a medio escribir) se salta. Un fichero que no
    existe no tiene filas, pero uno que no se puede leer no es un fichero vacío: ese error sube."""
    try:
        lineas = ruta.read_bytes().splitlines()
    except FileNotFoundError:
        return []
    filas = []
    for linea in lineas:
        try:
            fila = json.loads(linea)
        except (ValueError, RecursionError):  # también UnicodeDecodeError, y una línea anidada sin fondo
            continue
        if isinstance(fila, dict):
            filas.append(fila)
    return filas


def _anadir(ruta: Path, fila: dict) -> None:
    """Añade una línea entera. Si la última quedó a medias, empieza en otra para no perder esta pegada a ella."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a+b") as f:
        if f.seek(0, 2):
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write((json.dumps(fila, ensure_ascii=True) + "\n").encode("ascii"))  # ni un sustituto suelto la rompe


def identidad(tipo: str, fila: dict) -> str:
    """`bib-` y doce cifras del SHA-1 de `tipo|id_peticion|referencia|x0,y0,x1,y1` (el contrato)."""
    try:
        caja = ",".join(str(int(v)) for v in fila.get("caja") or [])
    except (TypeError, ValueError, OverflowError):  # una caja vieja que no son números cuenta como nula
        caja = ""
    clave = f"{tipo}|{fila.get('id_peticion') or ''}|{fila.get('referencia') or ''}|{caja}"
    return "bib-" + hashlib.sha1(clave.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def _filas(tipo: str) -> list[dict]:
    """La tabla tal cual, con `id_entrada` (las filas viejas lo derivan)."""
    return [{**f, "id_entrada": f.get("id_entrada") or identidad(tipo, f)} for f in _jsonl(TABLA[tipo])]


def _sin_prefijo(tipo: str, nombre: str | None) -> tuple[str | None, str | None]:
    """El sello se guarda como «editor: Nombre» (o «: Nombre» si no se sabe qué sello); devuelve («editor»,
    «Nombre») o («», «Nombre»)."""
    if tipo == "sello" and isinstance(nombre, str) and ": " in nombre:
        tipo_sello, nombre = nombre.split(": ", 1)
        return tipo_sello, nombre
    return None, nombre


def leer(tipo: str, con_retiradas: bool = False) -> list[dict]:
    """La tabla plegada con lo corregido: una fila por `id_entrada`, con su `estado`, la última
    `correccion` aplicada y el `original` si se corrigió. Por omisión, solo lo vigente."""
    registro: dict[str, list[dict]] = {}
    for c in _jsonl(CORRECCIONES):
        registro.setdefault(c.get("id_entrada"), []).append(c)
    plegadas: dict[str, dict] = {}
    for fila in _filas(tipo):
        if fila["id_entrada"] in plegadas:  # un duplicado de antes de la identidad: vale el primero
            continue
        fila.update(estado="vigente", correccion=None, original=None)
        for c in registro.get(fila["id_entrada"], []):  # en orden: manda la última de cada dato
            if c.get("accion") == "corregir":
                fila["original"] = fila["original"] or {"lectura": fila["lectura"], "nombre": fila["nombre"]}
                fila["lectura"] = c.get("lectura") or fila["lectura"]
                fila["nombre"] = c.get("nombre") or fila["nombre"]
            elif c.get("accion") in ("retirar", "restaurar"):
                fila["estado"] = "retirada" if c["accion"] == "retirar" else "vigente"
            fila["correccion"] = c.get("id_correccion")
        plegadas[fila["id_entrada"]] = fila
    return [f for f in plegadas.values() if con_retiradas or f["estado"] == "vigente"]


def anotar(tipo: str, referencia: str, lectura: str, nombre: str, caja: list[int] | None, foto: Path | None,
           quien: str = "", id_peticion: str = "", cuando: str = "") -> dict:
    """Guarda una firma o un sello confirmados. Si hay foto y caja, guarda también el recorte ampliado.
    Si la entrada ya está (el mismo `id_entrada`), no añade nada y devuelve la que había."""
    if tipo not in TABLA:
        raise ValueError(f"tipo: firma o sello, no {tipo}")
    fila = {"referencia": referencia, "lectura": lectura, "nombre": nombre, "caja": caja, "confirmado_por": quien,
            "confirmado_en": cuando or _ahora(), "id_peticion": id_peticion, "recorte": None}
    fila = {"id_entrada": identidad(tipo, fila), **fila}
    with _cerrojo:
        ya = next((f for f in _filas(tipo) if f["id_entrada"] == fila["id_entrada"]), None)
        if ya:
            return ya
        try:
            if foto and caja and foto.exists():
                import imagen

                RECORTES.mkdir(parents=True, exist_ok=True)
                destino = RECORTES / f"{fila['id_entrada']}.jpg"  # del id, nunca de lo que trae el Gestor
                imagen.ampliar_imagen(imagen.recortar(foto, tuple(caja)), 800).save(destino, quality=90)
                fila["recorte"] = str(destino.relative_to(RAIZ))
        except Exception as e:  # el recorte no es obligatorio: una foto rota no deja fuera la firma o el sello
            print(f"biblioteca: un recorte que no se pudo hacer ({type(e).__name__}); la entrada va sin recorte", flush=True)
        _anadir(TABLA[tipo], fila)
    return fila


def lectura_valida(texto) -> bool:
    """La regla de una corrección (D-1221, en el contrato): de 1 a 40 caracteres sin los espacios de los
    bordes, y al menos una letra `Lo` por encima de U+2E80 tras NFKC y la tabla de kanji antiguos, o «□»."""
    return isinstance(texto, str) and 0 < len(texto.strip()) <= LARGO_LECTURA and bool(_cjk(texto) or "□" in texto)


def nombre_valido(texto) -> bool:
    """La regla de una corrección (D-1221): de 1 a 120 caracteres sin los espacios de los bordes."""
    return isinstance(texto, str) and 0 < len(texto.strip()) <= LARGO_NOMBRE


def aplicar(correccion: dict) -> bool:
    """Apunta en `correcciones.jsonl` una corrección del Gestor. Devuelve False, sin apuntar nada, si
    no es válida, si su `id_entrada` no se conoce o si ya estaba aplicada."""
    c = correccion if isinstance(correccion, dict) else {}
    idc, ide, accion = c.get("id_correccion"), c.get("id_entrada"), c.get("accion")
    lectura, nombre = (c.get("lectura"), c.get("nombre")) if accion == "corregir" else (None, None)
    if not (isinstance(idc, str) and ID_CORRECCION.fullmatch(idc) and isinstance(ide, str) and ID_ENTRADA.fullmatch(ide)
            and accion in ACCIONES):
        print("biblioteca: una corrección sin forma válida; se ignora", flush=True)
        return False
    if accion == "corregir" and not ((lectura is not None or nombre is not None)
                                     and (lectura is None or lectura_valida(lectura))
                                     and (nombre is None or nombre_valido(nombre))):
        print(f"biblioteca: {idc} no trae una lectura o un nombre válidos; se ignora", flush=True)
        return False
    with _cerrojo:
        if any(r.get("id_correccion") == idc for r in _jsonl(CORRECCIONES)):
            return False
        tipo, fila = next(((t, f) for t in TABLA for f in _filas(t) if f["id_entrada"] == ide), (None, None))
        if fila is None:
            print(f"biblioteca: {idc} pide {accion} de {ide}, que no se conoce; se ignora", flush=True)
            return False
        lectura, nombre = lectura and lectura.strip(), nombre and nombre.strip()
        tipo_sello = _sin_prefijo(tipo, fila["nombre"])[0]
        if nombre and tipo_sello is not None:
            nombre = f"{tipo_sello}: {nombre}"
        _anadir(CORRECCIONES, {"id_correccion": idc, "id_entrada": ide, "accion": accion, "lectura": lectura,
                               "nombre": nombre, "aplicada_en": _ahora()})
    return True


def _recorte_propio(fila: dict) -> Path | None:
    ruta = RAIZ / fila["recorte"] if fila.get("recorte") else None
    return ruta if ruta and ruta.exists() else None


def recortes() -> dict[str, Path]:
    """El recorte propio de cada entrada que lo tiene, para hacer su miniatura."""
    return {f["id_entrada"]: r for t in TABLA for f in leer(t, con_retiradas=True) if (r := _recorte_propio(f))}


def entradas() -> list[dict]:
    """Lo que se publica en `de_catalogador/biblioteca.jsonl`: firmas y sellos, vigentes y retiradas,
    en la forma del contrato. Sin quién lo confirmó ni ninguna ruta propia."""
    salida = []
    for tipo in TABLA:
        for f in leer(tipo, con_retiradas=True):
            tipo_sello, nombre = _sin_prefijo(tipo, f["nombre"])
            original = f["original"] and {"lectura": f["original"]["lectura"],
                                          "nombre": _sin_prefijo(tipo, f["original"]["nombre"])[1]}
            salida.append({"id_entrada": f["id_entrada"], "tipo": tipo, "tipo_sello": tipo_sello or None,
                           "referencia": f.get("referencia"), "id_peticion": f.get("id_peticion") or None,
                           "lectura": f.get("lectura"), "nombre": nombre, "caja": f.get("caja"),
                           "recorte": f"biblioteca/{f['id_entrada']}.jpg" if _recorte_propio(f) else None,
                           "confirmado_en": f.get("confirmado_en"), "estado": f["estado"],
                           "correccion": f["correccion"], "original": original})
    return salida


def buscar(tipo: str, consulta: str, limite: int = 6) -> list[dict]:
    """Lo confirmado por el taller que comparte caracteres con la lectura, lo más parecido primero."""
    pedidos = _cjk(consulta) - {"画", "筆", "図", "□"}
    try:
        filas = leer(tipo)
    except OSError:  # una pista que falta no tumba una obra a medio pagar; corregir y publicar sí fallan
        print("biblioteca: una tabla no se pudo leer; la búsqueda sigue sin la biblioteca", flush=True)
        return []
    salida = []
    for fila in filas:
        if not (isinstance(fila.get("lectura"), str) and isinstance(fila.get("nombre"), str)):
            continue  # una fila vieja con una lectura o un nombre que no son texto no tumba la búsqueda
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
            unicas.append({**{k: v for k, v in fila.items() if k != "confirmado_por"},  # quién, nunca al modelo
                           "parecido": round(puntos, 2), "origen": "biblioteca del taller"})
        if len(unicas) >= limite:
            break
    return unicas


def desde_aceptada(aceptada: dict, foto: Path | None) -> dict:
    """Lo que una persona aceptó en el Gestor pasa a la biblioteca y al conjunto de oro."""
    ref, quien, idp = aceptada["referencia"], aceptada.get("aceptado_por", ""), aceptada.get("id_peticion", "")
    hecho = {"firma": 0, "sellos": 0}
    firma = aceptada.get("firma_confirmada") or {}
    if firma.get("lectura") and firma.get("nombre"):
        anotar("firma", ref, firma["lectura"], firma["nombre"], firma.get("caja"), foto, quien, idp, aceptada.get("aceptado_en") or "")
        hecho["firma"] = 1
    for s in aceptada.get("sellos_confirmados") or []:
        if s.get("lectura") and s.get("nombre"):
            tipo = s.get("tipo") if isinstance(s.get("tipo"), str) else ""  # sin tipo: se publica nulo
            anotar("sello", ref, s["lectura"], f"{tipo}: {s['nombre']}", s.get("caja"), foto, quien, idp,
                   aceptada.get("aceptado_en") or "")
            hecho["sellos"] += 1
    with _cerrojo:
        ORO.parent.mkdir(parents=True, exist_ok=True)
        with ORO.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"referencia": ref, "id_peticion": idp, "aceptado_por": quien,
                                "aceptado_en": aceptada.get("aceptado_en") or _ahora(),
                                "campos": aceptada.get("campos") or {}}, ensure_ascii=True) + "\n")
    return hecho


def resumen() -> dict:
    oro = _jsonl(ORO)
    return {"firmas": len(leer("firma")), "sellos": len(leer("sello")), "obras_adjudicadas": len({o["referencia"] for o in oro})}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 2 and sys.argv[1] == "resumen":
        print(json.dumps(resumen(), ensure_ascii=False))
    elif len(sys.argv) >= 4 and sys.argv[1] == "buscar":
        print(json.dumps(buscar(sys.argv[2], " ".join(sys.argv[3:])), ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)
