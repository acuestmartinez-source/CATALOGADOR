"""El modo servicio: CATALOGADOR como programa auxiliar del Gestor, hablándose solo por ficheros (§7).

  python servicio.py [--intercambio RUTA] [--imagenes RUTA] [--hasta HH:MM] [--una-vez] [--en-seco]

Vigila `para_catalogador/cola.jsonl`; por cada petición nueva escribe su estado en
`de_catalogador/estado.jsonl` y, al terminar, la propuesta en `de_catalogador/fichas.jsonl`.
Lee `para_catalogador/aceptadas.jsonl` y pasa lo aceptado a la biblioteca propia, a la memoria
de series y al conjunto de oro. Aplica `para_catalogador/biblioteca_correcciones.jsonl` y publica
la biblioteca en `de_catalogador/biblioteca.jsonl` (con sus recortes en `de_catalogador/biblioteca/`)
cuando cambia. Es idempotente: lo hecho queda apuntado en `datos/servicio.json`
y no se repite. Las peticiones de un mismo grupo se hacen seguidas, para que la primera documente
la serie y las demás la aprovechen. Nunca escribe en el Gestor ni en la tienda.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePath

import agente
import biblioteca
import ficha as F
from catalogador import MEMORIA, cargar_env, fuera_de_hora

RAIZ = Path(__file__).resolve().parent
HECHO = RAIZ / "datos" / "servicio.json"
ESPERA_S = 15
_cerrojo = threading.Lock()


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leer_jsonl(ruta: Path) -> list[dict]:
    """Las filas de un fichero del intercambio, sin la cabecera. Un fichero a medio escribir no tumba nada."""
    if not ruta.exists():
        return []
    filas = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if isinstance(fila, dict) and "formato" not in fila:
            filas.append(fila)
    return filas


def anadir(ruta: Path, fila: dict, formato: str) -> None:
    """Añade una línea entera; si el fichero no existe, lo estrena con su cabecera."""
    with _cerrojo:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        nuevo = not ruta.exists()
        with ruta.open("a", encoding="utf-8") as f:
            if nuevo:
                f.write(json.dumps({"formato": formato, "version": 1, "escrito_por": "catalogador",
                                    "escrito_en": _ahora(), "filas": 0}, ensure_ascii=False) + "\n")
            # ASCII puro a propósito: el Gestor lee con UTF-8 estricto, y si lee justo cuando una línea
            # está a medio escribir, un corte dentro de un carácter de varios bytes rompería la lectura
            # entera. Con \\uXXXX cualquier corte deja bytes válidos y solo una línea rota, que tolera.
            f.write(json.dumps(fila, ensure_ascii=True) + "\n")
            f.flush()
            os.fsync(f.fileno())


def motivo_sin_detalles(e: Exception) -> str:
    """Lo que el Gestor puede enseñar de un fallo: la clase de problema, nunca el texto de la excepción."""
    nombre = type(e).__name__
    if isinstance(e, OSError):
        return "no se pudo leer la foto o escribir en el intercambio; mira el registro del contenedor catalogador"
    if "anthropic" in type(e).__module__ or nombre in ("APIConnectionError", "APIStatusError", "RateLimitError"):
        return "la API de identificación no respondió o rechazó la petición; mira el registro del contenedor catalogador"
    return f"fallo del catalogador ({nombre}); mira el registro del contenedor catalogador"


def leer_hecho() -> dict:
    try:
        return json.loads(HECHO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"peticiones": [], "aceptadas": [], "anunciadas": []}


def guardar_hecho(h: dict) -> None:
    with _cerrojo:
        HECHO.parent.mkdir(parents=True, exist_ok=True)
        parcial = HECHO.with_suffix(".parcial")
        parcial.write_text(json.dumps(h, ensure_ascii=False, indent=0), encoding="utf-8")
        parcial.replace(HECHO)


def ficha_de_intercambio(peticion: dict, r: dict) -> dict:
    """La propuesta en la forma del contrato `de_catalogador/fichas.jsonl`."""
    fi = r.get("ficha") or {}
    datos = {}
    for campo in F.ESENCIALES:
        d = F.dato(fi, campo)
        detalle = {"autor": d.get("firma"), "editor": d.get("sello"), "censor": d.get("lectura") or d.get("sello"),
                   "tecnica": d.get("formato"), "serie": " · ".join(x for x in (d.get("japones"),
                   f"lámina {d['numero_lamina']}" if d.get("numero_lamina") else None) if x) or None, "titulo": None}[campo]
        datos[campo] = {"valor": F.valor(fi, campo) or None, "detalle": detalle, "fiabilidad": F.fiabilidad(fi, campo),
                        "nivel": F.nivel(fi, campo) or None, "como": d.get("como"), "fuentes": d.get("fuentes") or [],
                        "cajas": d.get("cajas") or [],
                        "lectura": {"autor": d.get("firma"), "editor": d.get("sello"),
                                    "censor": d.get("lectura") or d.get("sello")}.get(campo)}
        if campo == "titulo":
            datos[campo]["construido"] = bool(d.get("construido"))
    return {"id_peticion": peticion["id_peticion"], "referencia": peticion["referencia"], "version_catalogador": "v4",
            "modelo": r.get("modelo"), "terminado_en": _ahora(), "coste_eur": r.get("coste_eur", 0.0),
            "fases": r.get("fases"), "tipo_obra": fi.get("tipo_obra"), "datos": datos,
            "para_web": r.get("para_web") or F.para_web(fi),
            "vinculadas": [v for v in fi.get("vinculadas") or [] if isinstance(v, dict)],
            "fuentes_verificadas": r.get("fuentes_verificadas") or {}, "anotada": None, "error": None}


REFERENCIA, PETICION = re.compile(r"TDP-[0-9]{6}"), re.compile(r"idn-[0-9]{6}")


def caja_limpia(caja) -> list[int] | None:
    """Una caja del Gestor, sin fiarse: cuatro números finitos que no sean booleanos, redondeados con `int()`,
    con 0 <= x0 < x1 <= 1000 y 0 <= y0 < y1 <= 1000. Si no cumple, nula: la entrada va sin recorte."""
    if not (isinstance(caja, list) and len(caja) == 4
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in caja)):
        return None
    x0, y0, x1, y1 = (int(v) for v in caja)
    return [x0, y0, x1, y1] if 0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000 else None


def aceptada_valida(a: dict) -> bool:
    """Lo que llega en `aceptadas.jsonl`, sin fiarse, antes de escribir nada: la referencia es `TDP-` y seis
    cifras, y la firma, los sellos, `campos` y `campos.serie` tienen su forma. Las cajas no tiran la línea:
    las limpia `caja_limpia`."""
    firma, sellos, campos = a.get("firma_confirmada") or {}, a.get("sellos_confirmados") or [], a.get("campos") or {}
    return (isinstance(a.get("referencia"), str) and REFERENCIA.fullmatch(a["referencia"]) is not None
            and isinstance(firma, dict) and isinstance(sellos, list) and all(isinstance(s, dict) for s in sellos)
            and isinstance(campos, dict) and isinstance(campos.get("serie") or {}, dict))


def peticion_valida(p: dict) -> bool:
    """Lo que llega en `cola.jsonl`, sin fiarse: el id es `idn-` y seis cifras y la referencia `TDP-` y seis
    cifras (van a nombres de fichero), el grupo es texto o nada, y cada imagen es una ruta relativa que no
    sale del almacén."""
    imagenes = p.get("imagenes") or []
    return (isinstance(p.get("id_peticion"), str) and PETICION.fullmatch(p["id_peticion"]) is not None
            and isinstance(p.get("referencia"), str) and REFERENCIA.fullmatch(p["referencia"]) is not None
            and isinstance(p.get("grupo"), (str, type(None))) and isinstance(imagenes, list)
            and all(isinstance(r, str) and not PurePath(r).anchor and ".." not in PurePath(r).parts for r in imagenes))


def _sin_fecha(texto: str) -> str | None:
    """Un fichero del intercambio salvo el `escrito_en` de su cabecera: lo que se compara para no
    reescribir lo mismo."""
    cabecera, _, cuerpo = texto.partition("\n")
    try:
        c = json.loads(cabecera)
    except ValueError:
        return None
    c.pop("escrito_en", None)
    return json.dumps(c, sort_keys=True) + "\n" + cuerpo


#: La palabra de cada dato en la foto anotada: la misma que pinta el Gestor en su tabla.
PALABRAS = {"autor": "Autor", "titulo": "Título", "serie": "Serie", "editor": "Editor", "censor": "Censor", "tecnica": "Técnica"}


def anotar(foto: Path, linea: dict, carpeta: Path) -> str | None:
    """La primera foto con un recuadro de color y su palabra por dato. Devuelve la ruta relativa a
    `de_catalogador/`, o None si no hay recuadros o no se pudo dibujar (la ficha sale igual)."""
    marcas = [{"campo": "artista" if c == "autor" else c, "caja": caja, "etiqueta": PALABRAS[c]}
              for c, d in linea["datos"].items() for caja in d.get("cajas") or []]
    if not marcas:
        return None
    try:
        from imagen import anotar as dibujar
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{linea['id_peticion']}.jpg"
        parcial = destino.with_suffix(".parcial")
        dibujar(foto, marcas).save(parcial, "JPEG", quality=85)
        parcial.replace(destino)
    except Exception as e:  # una foto que no se deja dibujar no tumba la propuesta
        print(f"{linea['referencia']}: sin foto anotada ({type(e).__name__})", flush=True)
        return None
    return f"{carpeta.name}/{destino.name}"


class Servicio:
    def __init__(self, intercambio: Path, imagenes: Path, hasta: str | None = None, en_seco: bool = False):
        self.cola = intercambio / "para_catalogador" / "cola.jsonl"
        self.aceptadas = intercambio / "para_catalogador" / "aceptadas.jsonl"
        self.estado = intercambio / "de_catalogador" / "estado.jsonl"
        self.fichas = intercambio / "de_catalogador" / "fichas.jsonl"
        self.anotadas = intercambio / "de_catalogador" / "anotadas"
        self.correcciones = intercambio / "para_catalogador" / "biblioteca_correcciones.jsonl"
        self.biblioteca = intercambio / "de_catalogador" / "biblioteca.jsonl"
        self.imagenes, self.hasta, self.en_seco = imagenes, hasta, en_seco
        self.client = None
        self.hecho = leer_hecho()
        self.sin_miniatura: set[str] = set()  # los recortes propios que no se dejaron leer: un aviso por proceso

    def estado_de(self, p: dict, estado: str, detalle: str = "") -> None:
        anadir(self.estado, {"id_peticion": p["id_peticion"], "referencia": p["referencia"], "estado": estado,
                             "en": _ahora(), "detalle": detalle}, "estado")

    def pendientes(self) -> list[list[dict]]:
        """Las peticiones no hechas, por grupos (las de un grupo seguidas, en el orden en que se pidieron)."""
        hechas = set(self.hecho["peticiones"])
        nuevas, saltadas = [], 0
        for p in leer_jsonl(self.cola):
            clave = str(p.get("id_peticion"))
            if clave in hechas:
                continue
            if not peticion_valida(p):  # el aviso es fijo: no repite lo que llegó
                print("cola: una petición con el id, la referencia o una imagen fuera del contrato; se salta", flush=True)
                if not self.en_seco:
                    self.hecho["peticiones"].append(clave)
                    hechas.add(clave)
                    saltadas += 1
                continue
            nuevas.append(p)
        if saltadas:
            guardar_hecho(self.hecho)
        grupos: dict[str, list[dict]] = {}
        for p in nuevas:
            grupos.setdefault(p.get("grupo") or p["id_peticion"], []).append(p)
        return list(grupos.values())

    def una(self, p: dict) -> None:
        aplazar = fuera_de_hora(self.hasta)
        fotos = [] if aplazar else [self.imagenes / r for r in p.get("imagenes") or [] if (self.imagenes / r).exists()][:2]
        if self.en_seco:  # en seco solo se dice lo que pasaría: ni estado, ni ficha, ni la petición por hecha
            print(f"{p['referencia']}: " + ("se aplazaría" if aplazar else "terminaría en error: sin fotos en el almacén"
                  if not fotos else f"se haría con {len(fotos)} foto(s), grupo {p.get('grupo') or '—'}"), flush=True)
            return
        if aplazar:
            self.estado_de(p, "aplazada", f"pasada la hora límite {self.hasta}")
            return
        if not fotos:
            self.terminar(p, None, "sin fotos en el almacén")
            return
        try:
            self.estado_de(p, "leyendo", "OCR local")
            ocr = " ".join(b["texto"] for b in agente.ocr_ndl(fotos[0]))
            series = F.series_en_texto(F.leer_memoria(MEMORIA), ocr)
            self.estado_de(p, "identificando", "fase A: lupa, firmas, sellos y ukiyo-e.org")
            if self.client is None:
                self.client = agente.cliente()
            r = agente.catalogar(self.client, {"referencia": p["referencia"], "alto_cm": p.get("alto_cm"), "ancho_cm": p.get("ancho_cm")},
                                 fotos, series=series, pistas=p.get("pistas") or None)
        except Exception as e:  # la petición queda en error; el Gestor puede volver a pedirla
            # Al intercambio va un motivo FIJO: el texto de una excepción puede llevar una ruta del NAS
            # o el cuerpo de un error de la API, y la ficha del Gestor lo pinta a cualquier cuenta.
            # El texto entero queda en el registro del contenedor y en resultados/servicio/.
            print(f"{p['referencia']}: {type(e).__name__}: {e}", flush=True)
            (RAIZ / "resultados" / "servicio").mkdir(parents=True, exist_ok=True)
            (RAIZ / "resultados" / "servicio" / f"{p['referencia']}.error.txt").write_text(f"{type(e).__name__}: {e}\n", encoding="utf-8")
            self.terminar(p, None, motivo_sin_detalles(e))
            return
        F.recordar_serie(MEMORIA, r.get("ficha"), p["referencia"])
        (RAIZ / "resultados" / "servicio").mkdir(parents=True, exist_ok=True)
        (RAIZ / "resultados" / "servicio" / f"{p['referencia']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        self.terminar(p, r, None, fotos[0])

    def terminar(self, p: dict, r: dict | None, error: str | None, foto: Path | None = None) -> None:
        if error:
            anadir(self.fichas, {"id_peticion": p["id_peticion"], "referencia": p["referencia"], "version_catalogador": "v4",
                                 "terminado_en": _ahora(), "datos": {}, "para_web": {}, "vinculadas": [], "error": error}, "fichas")
            self.estado_de(p, "error", error)
        else:
            linea = ficha_de_intercambio(p, r)
            if foto is not None:  # la imagen se escribe ANTES que la línea: quien lee la línea la encuentra
                linea["anotada"] = anotar(foto, linea, self.anotadas)
            anadir(self.fichas, linea, "fichas")
            self.estado_de(p, "lista", f"{r.get('coste_eur', 0):.2f} € · fases {r.get('fases')}")
        self.hecho["peticiones"].append(p["id_peticion"])
        guardar_hecho(self.hecho)
        print(f"{p['referencia']}: {'ERROR ' + error if error else 'lista'}", flush=True)

    def aprender(self) -> int:
        """Lo que una persona aceptó pasa a la biblioteca, a la memoria de series y al conjunto de oro."""
        hechas = set(self.hecho["aceptadas"])
        n = saltadas = 0
        try:
            for a in leer_jsonl(self.aceptadas):
                clave = f"{a.get('id_peticion')}:{a.get('aceptado_en')}"
                if clave in hechas:
                    continue
                if not aceptada_valida(a):  # el aviso es fijo: no repite lo que llegó
                    print("aceptadas: una línea fuera del contrato; se salta", flush=True)
                    if not self.en_seco:
                        self.hecho["aceptadas"].append(clave)
                        hechas.add(clave)
                        saltadas += 1
                    continue
                firma, sellos = a.get("firma_confirmada") or {}, a.get("sellos_confirmados") or []
                if any(x.get("caja") is not None and caja_limpia(x.get("caja")) is None for x in (firma, *sellos)):
                    print("aceptadas: una caja fuera del contrato; esa firma o ese sello van sin recorte", flush=True)
                a = {**a, "firma_confirmada": firma and {**firma, "caja": caja_limpia(firma.get("caja"))},
                     "sellos_confirmados": [{**s, "caja": caja_limpia(s.get("caja"))} for s in sellos]}
                if self.en_seco:
                    print(f"{a['referencia']}: se aprendería lo aceptado en {a.get('id_peticion')}", flush=True)
                    n += 1
                    continue
                try:
                    self._aprender_una(a)
                    n += 1
                except OSError:  # una tabla que no se lee: la vuelta falla y la siguiente lo repite
                    raise
                except Exception as e:  # una línea de datos no tumba la vuelta: se avisa y se da por hecha
                    print(f"aceptadas: una línea que no se pudo aprender ({type(e).__name__}); se da por hecha", flush=True)
                    saltadas += 1
                self.hecho["aceptadas"].append(clave)
                hechas.add(clave)
        finally:
            if (n or saltadas) and not self.en_seco:
                guardar_hecho(self.hecho)
        return n

    def _aprender_una(self, a: dict) -> None:
        p = self.pedido(a.get("id_peticion")) or {}
        foto = next((self.imagenes / r for r in (p.get("imagenes") if peticion_valida(p) else None) or []
                     if (self.imagenes / r).exists()), None)
        biblioteca.desde_aceptada(a, foto)
        serie = (a.get("campos") or {}).get("serie") or {}
        if serie.get("estado") in ("aceptado", "corregido") and serie.get("valor"):
            F.recordar_serie(MEMORIA, {"serie": {"japones": serie.get("valor"), "castellano": serie.get("valor"),
                                                 "nivel": "museo misma estampa", "confianza": "alta"}},
                             a["referencia"])

    def corregir_biblioteca(self) -> int:
        """Lo que una persona pidió en el Gestor con una entrada de la biblioteca: cada `id_correccion`
        una sola vez, en el orden del fichero. Devuelve cuántas se aplicaron (en seco, cuántas se harían)."""
        hechas = self.hecho.setdefault("correcciones", [])
        n = 0
        for c in leer_jsonl(self.correcciones):
            idc = c.get("id_correccion")
            if not isinstance(idc, str) or idc in hechas:
                continue
            if self.en_seco:
                print(f"biblioteca: se aplicaría {idc}", flush=True)
                n += 1
                continue
            # una inválida o de una entrada desconocida se ignora y queda hecha; si una tabla no se pudo
            # leer, aplicar lanza OSError, la vuelta falla y esta corrección no queda hecha
            n += biblioteca.aplicar(c)
            hechas.append(idc)
            guardar_hecho(self.hecho)
        return n

    def publicar_biblioteca(self) -> bool:
        """La instantánea de la biblioteca, entera, y solo si cambió o no existe. Antes se resuelven las
        miniaturas: se escriben las que falten (antes que la línea que las cita) y la que no se puede hacer
        queda con `recorte` nulo, el mismo en cada vuelta, así que no fuerza a reescribir nada."""
        lineas = biblioteca.entradas()
        if not self.en_seco:
            self._miniaturas(lineas)
        cabecera = {"formato": "biblioteca", "version": 1, "escrito_por": "catalogador", "escrito_en": _ahora(),
                    "filas": len(lineas)}
        texto = "".join(json.dumps(x, ensure_ascii=True) + "\n" for x in (cabecera, *lineas))
        try:
            antes = _sin_fecha(self.biblioteca.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            antes = None
        if antes is not None and antes == _sin_fecha(texto):
            return False
        if self.en_seco:
            print(f"biblioteca: se publicarían {len(lineas)} entradas", flush=True)
            return False
        self.biblioteca.parent.mkdir(parents=True, exist_ok=True)
        parcial = self.biblioteca.with_suffix(".parcial")
        parcial.write_text(texto, encoding="ascii")
        parcial.replace(self.biblioteca)
        return True

    def _miniaturas(self, lineas: list[dict]) -> None:
        """Escribe en `de_catalogador/biblioteca/` la miniatura que falte (también la que alguien borró)."""
        fuentes = None
        for x in lineas:
            destino = self.biblioteca.parent / x["recorte"] if x["recorte"] else None
            if destino is None or destino.exists():  # el recorte de un id no cambia nunca
                continue
            if fuentes is None:
                fuentes = biblioteca.recortes()
            try:
                from imagen import miniatura

                datos = miniatura(fuentes[x["id_entrada"]])
            except Exception as e:  # un recorte propio que no se deja leer no tumba la biblioteca
                if x["id_entrada"] not in self.sin_miniatura:
                    self.sin_miniatura.add(x["id_entrada"])
                    print(f"biblioteca: {x['id_entrada']} sin miniatura ({type(e).__name__})", flush=True)
                x["recorte"] = None
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            parcial = destino.with_suffix(".parcial")
            parcial.write_bytes(datos)
            parcial.replace(destino)

    def pedido(self, id_peticion: str | None) -> dict | None:
        return next((p for p in leer_jsonl(self.cola) if p.get("id_peticion") == id_peticion), None)

    def vuelta(self) -> int:
        grupos = self.pendientes()
        anunciadas = self.hecho.setdefault("anunciadas", [])
        for grupo in grupos:
            for p in grupo:
                # `en_cola` se escribe UNA vez por petición: repetirlo en cada vuelta rompía en el
                # Gestor la racha de «aplazada» y la ficha decía «hace un momento» toda la noche.
                if not self.en_seco and p["id_peticion"] not in anunciadas:
                    self.estado_de(p, "en_cola", f"grupo de {len(grupo)}")
                    anunciadas.append(p["id_peticion"])
        if grupos and not self.en_seco:
            guardar_hecho(self.hecho)
        for grupo in grupos:
            for p in grupo:
                self.una(p)
        aprendidas = self.aprender()
        self.corregir_biblioteca()
        self.publicar_biblioteca()
        return sum(len(g) for g in grupos) + aprendidas


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cargar_env()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--intercambio", type=Path, default=Path(os.environ.get("TDP_INTERCAMBIO", r"Z:\FOTO\_intercambio")))
    p.add_argument("--imagenes", type=Path, default=Path(os.environ.get("TDP_IMAGENES", r"Z:\IMAGENES")))
    p.add_argument("--hasta", metavar="HH:MM", help="no empezar peticiones nuevas a partir de esa hora")
    p.add_argument("--una-vez", action="store_true", help="atiende lo que haya y termina (para el programador de tareas)")
    p.add_argument("--en-seco", action="store_true")
    args = p.parse_args(argv)
    s = Servicio(args.intercambio, args.imagenes, args.hasta, args.en_seco)
    print(f"cola: {s.cola} · fotos: {args.imagenes}", flush=True)
    while True:
        try:
            hechas = s.vuelta()
        except Exception as e:  # una vuelta que falla no mata el servicio: la siguiente lo vuelve a intentar
            print(f"vuelta fallida ({type(e).__name__}); se intenta otra vez en la siguiente", flush=True)
            if args.una_vez:
                sys.exit(1)
        else:
            if args.una_vez:
                print(f"{hechas} atendidas")
                return
        time.sleep(ESPERA_S)


if __name__ == "__main__":
    main()
