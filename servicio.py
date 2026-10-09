"""El modo servicio: CATALOGADOR como programa auxiliar del Gestor, hablándose solo por ficheros (§7).

  python servicio.py [--intercambio RUTA] [--imagenes RUTA] [--hasta HH:MM] [--una-vez] [--en-seco]

Vigila `para_catalogador/cola.jsonl`; por cada petición nueva escribe su estado en
`de_catalogador/estado.jsonl` y, al terminar, la propuesta en `de_catalogador/fichas.jsonl`.
Lee `para_catalogador/aceptadas.jsonl` y pasa lo aceptado a la biblioteca propia, a la memoria
de series y al conjunto de oro. Es idempotente: lo hecho queda apuntado en `datos/servicio.json`
y no se repite. Las peticiones de un mismo grupo se hacen seguidas, para que la primera documente
la serie y las demás la aprovechen. Nunca escribe en el Gestor ni en la tienda.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

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
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def leer_hecho() -> dict:
    try:
        return json.loads(HECHO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"peticiones": [], "aceptadas": []}


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
                        "cajas": d.get("cajas") or []}
        if campo == "titulo":
            datos[campo]["construido"] = bool(d.get("construido"))
    return {"id_peticion": peticion["id_peticion"], "referencia": peticion["referencia"], "version_catalogador": "v4",
            "modelo": r.get("modelo"), "terminado_en": _ahora(), "coste_eur": r.get("coste_eur", 0.0),
            "fases": r.get("fases"), "tipo_obra": fi.get("tipo_obra"), "datos": datos,
            "para_web": r.get("para_web") or F.para_web(fi),
            "vinculadas": [v for v in fi.get("vinculadas") or [] if isinstance(v, dict)],
            "fuentes_verificadas": r.get("fuentes_verificadas") or {}, "error": None}


class Servicio:
    def __init__(self, intercambio: Path, imagenes: Path, hasta: str | None = None, en_seco: bool = False):
        self.cola = intercambio / "para_catalogador" / "cola.jsonl"
        self.aceptadas = intercambio / "para_catalogador" / "aceptadas.jsonl"
        self.estado = intercambio / "de_catalogador" / "estado.jsonl"
        self.fichas = intercambio / "de_catalogador" / "fichas.jsonl"
        self.imagenes, self.hasta, self.en_seco = imagenes, hasta, en_seco
        self.client = None
        self.hecho = leer_hecho()

    def estado_de(self, p: dict, estado: str, detalle: str = "") -> None:
        anadir(self.estado, {"id_peticion": p["id_peticion"], "referencia": p["referencia"], "estado": estado,
                             "en": _ahora(), "detalle": detalle}, "estado")

    def pendientes(self) -> list[list[dict]]:
        """Las peticiones no hechas, por grupos (las de un grupo seguidas, en el orden en que se pidieron)."""
        hechas = set(self.hecho["peticiones"])
        nuevas = [p for p in leer_jsonl(self.cola) if p.get("id_peticion") and p["id_peticion"] not in hechas]
        grupos: dict[str, list[dict]] = {}
        for p in nuevas:
            grupos.setdefault(p.get("grupo") or p["id_peticion"], []).append(p)
        return list(grupos.values())

    def una(self, p: dict) -> None:
        if fuera_de_hora(self.hasta):
            self.estado_de(p, "aplazada", f"pasada la hora límite {self.hasta}")
            return
        fotos = [self.imagenes / r for r in p.get("imagenes") or [] if (self.imagenes / r).exists()][:2]
        if not fotos:
            self.terminar(p, None, "sin fotos en el almacén")
            return
        if self.en_seco:
            print(f"{p['referencia']}: se haría con {len(fotos)} foto(s), grupo {p.get('grupo') or '—'}")
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
        except Exception as e:  # la petición queda en error con su motivo; el Gestor puede volver a pedirla
            self.terminar(p, None, f"{type(e).__name__}: {e}")
            return
        F.recordar_serie(MEMORIA, r.get("ficha"), p["referencia"])
        (RAIZ / "resultados" / "servicio").mkdir(parents=True, exist_ok=True)
        (RAIZ / "resultados" / "servicio" / f"{p['referencia']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        self.terminar(p, r, None)

    def terminar(self, p: dict, r: dict | None, error: str | None) -> None:
        if error:
            anadir(self.fichas, {"id_peticion": p["id_peticion"], "referencia": p["referencia"], "version_catalogador": "v4",
                                 "terminado_en": _ahora(), "datos": {}, "para_web": {}, "vinculadas": [], "error": error}, "fichas")
            self.estado_de(p, "error", error)
        else:
            anadir(self.fichas, ficha_de_intercambio(p, r), "fichas")
            self.estado_de(p, "lista", f"{r.get('coste_eur', 0):.2f} € · fases {r.get('fases')}")
        self.hecho["peticiones"].append(p["id_peticion"])
        guardar_hecho(self.hecho)
        print(f"{p['referencia']}: {'ERROR ' + error if error else 'lista'}", flush=True)

    def aprender(self) -> int:
        """Lo que una persona aceptó pasa a la biblioteca, a la memoria de series y al conjunto de oro."""
        hechas = set(self.hecho["aceptadas"])
        n = 0
        for a in leer_jsonl(self.aceptadas):
            clave = f"{a.get('id_peticion')}:{a.get('aceptado_en')}"
            if not a.get("referencia") or clave in hechas:
                continue
            foto = next((self.imagenes / r for r in (self.pedido(a.get("id_peticion")) or {}).get("imagenes") or []
                         if (self.imagenes / r).exists()), None)
            biblioteca.desde_aceptada(a, foto)
            campos = a.get("campos") or {}
            serie = campos.get("serie") or {}
            if serie.get("estado") in ("aceptado", "corregido") and serie.get("valor"):
                F.recordar_serie(MEMORIA, {"serie": {"japones": serie.get("valor"), "castellano": serie.get("valor"),
                                                     "nivel": "museo misma estampa", "confianza": "alta"}},
                                 a["referencia"])
            self.hecho["aceptadas"].append(clave)
            n += 1
        if n:
            guardar_hecho(self.hecho)
        return n

    def pedido(self, id_peticion: str | None) -> dict | None:
        return next((p for p in leer_jsonl(self.cola) if p.get("id_peticion") == id_peticion), None)

    def vuelta(self) -> int:
        grupos = self.pendientes()
        for grupo in grupos:
            for p in grupo:
                self.estado_de(p, "en_cola", f"grupo de {len(grupo)}") if not self.en_seco else None
        for grupo in grupos:
            for p in grupo:
                self.una(p)
        aprendidas = self.aprender()
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
        hechas = s.vuelta()
        if args.una_vez:
            print(f"{hechas} atendidas")
            return
        time.sleep(ESPERA_S)


if __name__ == "__main__":
    main()
