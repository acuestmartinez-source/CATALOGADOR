"""CATALOGADOR: identifica estampas japonesas del Gestor desde su foto y prepara los datos para la web.

Órdenes:
  python catalogador.py catalogar [--lista F.csv | --solo REF ...] [--hasta HH:MM] [--en-seco] [--repetir]
  python catalogador.py identificar FOTO [FOTO ...] --medidas 35x24 [--pista URL ...]
  python catalogador.py informe   [--carpeta C] [--lista F.csv]
  python catalogador.py exportar  [--carpeta C] [--lista F.csv]         CSV con lo publicable
  python catalogador.py comparar  CARPETA_A CARPETA_B
  python catalogador.py muestra                                         la muestra fija de 50 (semilla 2026)

El Gestor (TDP_BASE) y las fotos (TDP_IMAGENES) se abren en SOLO LECTURA. Nada se escribe en la
tienda: `exportar` deja un CSV para que el Gestor lo cargue por su puerta.
Diseño y decisiones: docs/05_version_depurada.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import agente
import ficha as F
import medir

RAIZ = Path(__file__).resolve().parent
RESULTADOS = RAIZ / "resultados"
CARPETA = "v4"  # resultados/v4/<REF>.json
MUESTRA = RAIZ / "piloto" / "muestra.csv"
PISTAS = RAIZ / "piloto" / "pistas.csv"
MEMORIA = RAIZ / "datos" / "series_conocidas.json"
SEMILLA, TAMANO_MUESTRA = 2026, 50


# ---------------------------------------------------------------- entorno y Gestor

def cargar_env() -> None:
    fichero = RAIZ / ".env"
    if not fichero.exists():
        return
    for linea in fichero.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def abrir_gestor() -> sqlite3.Connection:
    base = Path(os.environ.get("TDP_BASE", r"C:\dev\GESTOR_TDP\datos\tdp.sqlite"))
    if not base.exists():
        sys.exit(f"No encuentro la base del Gestor en {base}. Pon TDP_BASE en .env.")
    con = sqlite3.connect(f"{base.as_uri()}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def carpeta_imagenes() -> Path:
    carpeta = Path(os.environ.get("TDP_IMAGENES", r"Z:\IMAGENES"))
    if not carpeta.exists():
        sys.exit(f"No encuentro las imágenes en {carpeta}. Pon TDP_IMAGENES en .env.")
    return carpeta


def gestor(con: sqlite3.Connection, referencia: str) -> dict:
    """Lo que el Gestor sabe de la obra (también puede estar mal), sus fotos y su ficha en la tienda."""
    o = con.execute(
        """select o.referencia, o.titulo, o.serie_literal, o.editor_literal, o.anio, o.anio_literal,
                  o.alto_cm, o.ancho_cm, o.tecnica_literal, o.id_woo, a.nombre_canonico as artista
           from nuc_obra o left join nuc_artista a on a.id = o.artista_id where o.referencia = ?""",
        (referencia,)).fetchone()
    if o is None:
        raise SystemExit(f"{referencia} no está en el Gestor.")
    fotos = [r["ruta_archivo"] for r in con.execute(
        "select ruta_archivo from nuc_imagen where referencia=? and retirada=0 and ruta_archivo is not null"
        " order by principal desc, nombre_fichero", (referencia,))]
    tienda = {"id_woo": o["id_woo"], "sku": "", "enlace": "", "es_copia": False}
    e = con.execute("select json_wc from web_espejo where id_woo=? and tipo='producto'", (o["id_woo"],)).fetchone()
    if e and e["json_wc"]:
        w = json.loads(e["json_wc"])
        tienda.update(sku=w.get("sku") or "", enlace=w.get("permalink") or "",
                      es_copia=(w.get("slug") or "").startswith("copia"))
    return {**dict(o), "imagenes": fotos, "tienda": tienda}


def leer_lista(ruta: Path) -> list[str]:
    with ruta.open(encoding="utf-8-sig") as f:
        return [fila["referencia"].strip() for fila in csv.DictReader(f) if fila.get("referencia", "").strip()]


def leer_pistas() -> dict[str, list[dict]]:
    """referencia;url;nota — lo que una persona encontró a mano (la búsqueda por imagen de ukiyo-e.org)."""
    if not PISTAS.exists():
        return {}
    pistas: dict[str, list[dict]] = {}
    with PISTAS.open(encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f, delimiter=";"):
            if fila.get("referencia") and fila.get("url"):
                pistas.setdefault(fila["referencia"].strip(), []).append(
                    {"url": fila["url"].strip(), "nota": (fila.get("nota") or "").strip()})
    return pistas


# ---------------------------------------------------------------- catalogar

def agrupar(obras: list[dict]) -> list[list[dict]]:
    """Las obras de la misma serie (según el Gestor) van juntas y en orden: la primera documenta la serie
    y las demás la reutilizan. Las que no tienen serie van cada una sola."""
    grupos: dict[str, list[dict]] = {}
    sueltas = []
    for o in obras:
        clave = F.normalizar(o["gestor"].get("serie_literal")).replace(" ", "")
        (grupos.setdefault(clave, []) if clave else sueltas).append(o)
    return sorted(grupos.values(), key=len, reverse=True) + [[o] for o in sueltas]


def fuera_de_hora(hasta: str | None, ahora: datetime | None = None) -> bool:
    """True si ya ha pasado la hora límite (HH:MM, hora del PC) para EMPEZAR obras nuevas."""
    if not hasta:
        return False
    ahora = ahora or datetime.now()
    h, m = (int(x) for x in hasta.split(":"))
    return (ahora.hour, ahora.minute) >= (h, m)


def catalogar_una(client, o: dict, args, pistas: dict) -> float:
    """Una obra con sus reintentos. Devuelve el coste, o 0 si falló (no se guarda y se reintenta otro día)."""
    ref, destino = o["referencia"], o["destino"]
    for intento in range(3):
        try:
            series = F.series_en_texto(F.leer_memoria(MEMORIA), " ".join(b["texto"] for b in agente.ocr_ndl(o["fotos"][0])))
            r = agente.catalogar(client, {"referencia": ref, "alto_cm": o["gestor"]["alto_cm"], "ancho_cm": o["gestor"]["ancho_cm"]},
                                 o["fotos"], modelo=args.modelo, con_web=not args.sin_web, series=series,
                                 pistas=pistas.get(ref), esfuerzo=args.esfuerzo)
            break
        except OSError as e:  # el NAS se corta a veces unos segundos
            if intento == 2:
                print(f"{ref}: ERROR {type(e).__name__}: {e}", flush=True)
                return 0.0
            print(f"{ref}: el NAS no responde; se repite en {60 * (intento + 1)} s", flush=True)
            time.sleep(60 * (intento + 1))
        except Exception as e:
            # La API a veces deja a medias el código con que filtra sus propias búsquedas: el historial ya no
            # vale y no se edita; se repite la obra una vez.
            if "without a corresponding" in str(e) and intento == 0:
                print(f"{ref}: la API dejó una búsqueda a medias; se repite la obra", flush=True)
                continue
            print(f"{ref}: ERROR {type(e).__name__}: {e}", flush=True)
            return 0.0
    r["tienda"] = o["gestor"]["tienda"]
    destino.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    F.recordar_serie(MEMORIA, r["ficha"], ref)
    web = r["para_web"]
    print(f"{ref}: {r['coste_eur']:.2f} € · fases {r['fases']} · {web['autor'] or 'sin autor'} · "
          f"«{web['titulo'][:50]}» · {r['duracion_s']} s" + ("" if r["ficha"] else " · SIN FICHA"), flush=True)
    return r["coste_eur"]


def orden_catalogar(args) -> None:
    from concurrent.futures import ThreadPoolExecutor

    con, carpeta = abrir_gestor(), carpeta_imagenes()
    referencias = args.solo or (leer_lista(args.lista) if args.lista else leer_lista(MUESTRA))
    salida = RESULTADOS / CARPETA
    salida.mkdir(parents=True, exist_ok=True)
    obras, hechas = [], 0
    for ref in referencias:
        destino = salida / f"{ref}.json"
        if destino.exists() and not args.repetir:
            hechas += 1
            continue
        g = gestor(con, ref)
        fotos = [carpeta / r for r in g["imagenes"][:2] if (carpeta / r).exists()]
        if not fotos:
            print(f"{ref}: sin foto en {carpeta}; se salta")
            continue
        obras.append({"referencia": ref, "gestor": g, "fotos": fotos, "destino": destino})
    grupos = agrupar(obras)
    if args.en_seco:
        for grupo in grupos:
            serie = grupo[0]["gestor"].get("serie_literal") or "sin serie"
            print(f"{len(grupo):>3} · {serie[:50]}: {' '.join(o['referencia'] for o in grupo)}")
        print(f"\n{len(obras)} por hacer en {len(grupos)} grupos, {hechas} ya hechas. "
              f"Estimado: {0.30 * len(obras):.0f}–{0.55 * len(obras):.0f} € y {len(obras) * 4 // max(1, args.paralelo)} "
              f"min (ukiyo-e.org va despacio a propósito).")
        return
    client, pistas = agente.cliente(), leer_pistas()

    def un_grupo(grupo: list[dict]) -> float:
        total = 0.0
        for o in grupo:
            if fuera_de_hora(args.hasta):
                print(f"{o['referencia']}: pasada la hora límite {args.hasta}; queda para otro día", flush=True)
                continue
            total += catalogar_una(client, o, args, pistas)
        return total

    with ThreadPoolExecutor(max_workers=args.paralelo) as hilos:
        total = sum(hilos.map(un_grupo, grupos))
    print(f"\n{len(obras)} intentadas en {len(grupos)} grupos, {hechas} ya hechas, {total:.2f} € -> {salida}")


def orden_identificar(args) -> None:
    """Una estampa cualquiera con tus fotos: no toca el Gestor."""
    fotos = [Path(r) for r in args.fotos]
    for r in fotos:
        if not r.exists():
            sys.exit(f"No encuentro {r}")
    alto, ancho = (float(x.replace(",", ".")) for x in args.medidas.lower().split("x"))
    nombre = args.nombre or fotos[0].stem
    series = F.series_en_texto(F.leer_memoria(MEMORIA), " ".join(b["texto"] for b in agente.ocr_ndl(fotos[0])))
    r = agente.catalogar(agente.cliente(), {"referencia": nombre, "alto_cm": alto, "ancho_cm": ancho}, fotos,
                         modelo=args.modelo, series=series, pistas=[{"url": u} for u in args.pista or []], esfuerzo=args.esfuerzo)
    destino = RESULTADOS / "sueltas" / f"{nombre}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(r["para_web"], ensure_ascii=False, indent=1))
    print(f"\n{r['coste_eur']:.2f} € · fases {r['fases']} · {r['duracion_s']} s -> {destino}")


# ---------------------------------------------------------------- informe, exportar, comparar

def resultados(carpeta: Path, lista: Path | None = None) -> list[dict]:
    solo = set(leer_lista(lista)) if lista else None
    salida = []
    for f in sorted(carpeta.glob("TDP-*.json")):
        if solo is None or f.stem in solo:
            salida.append(json.loads(f.read_text(encoding="utf-8")))
    return salida


def orden_informe(args) -> None:
    con, carpeta = abrir_gestor(), RESULTADOS / args.carpeta
    rs = resultados(carpeta, args.lista)
    if not rs:
        sys.exit(f"No hay resultados en {carpeta}.")
    pares = [(r.get("ficha"), gestor(con, r["referencia"])) for r in rs]
    coste = sum(r.get("coste_eur", 0) for r in rs)
    fuentes: dict[str, int] = {}
    for r in rs:
        for origen in (r.get("fuentes_verificadas") or {}).values():
            fuentes[origen] = fuentes.get(origen, 0) + 1
    lineas = [f"# Informe · `{args.carpeta}` · {len(rs)} obras", "",
              "Desacuerdo con el Gestor (no es error: el Gestor también se equivoca), por fiabilidad del dato:", "",
              "| Campo | Todas | Fiabilidad alta | Media | Baja | El agente no lo da |", "|---|---|---|---|---|---|"]
    lineas += [f"| {t['campo']} | {t['todas']} | {t['alta']} | {t['media']} | {t['baja']} | {t['sin_dato_del_agente']} |"
               for t in medir.tasas(pares)]
    con_b = sum(1 for r in rs if r.get("fases") == "A+B")
    lineas += ["", f"Coste: {coste:.2f} € ({coste / len(rs):.2f} € por obra, a {agente.EUR_POR_USD} €/USD). "
               f"Fase B en {con_b} de {len(rs)} obras.",
               "Fuentes citadas: " + (", ".join(f"{k} {v}" for k, v in sorted(fuentes.items())) or "ninguna"), "",
               "## Discrepancias (mirar quién tiene razón)", "", "| Obra | Campo | Gestor | Agente | Fiabilidad |", "|---|---|---|---|---|"]
    for (fi, g), r in zip(pares, rs):
        comp = medir.comparar(fi, g)
        for campo, clave, g_val in (("autor", "autor", g["artista"]), ("editor", "editor", g["editor_literal"])):
            if comp[campo] is False:
                lineas.append(f"| {r['referencia']} | {campo} | {g_val} | {F.valor(fi, clave)} | {F.fiabilidad(fi, clave)} |")
    texto = "\n".join(lineas) + "\n"
    (carpeta / "informe.md").write_text(texto, encoding="utf-8")
    print(texto)


COLUMNAS_WEB = ["referencia", "id_tienda", "sku", "titulo", "titulo_construido", "titulo_fiabilidad", "autor",
                "autor_fiabilidad", "serie", "serie_lamina", "serie_fiabilidad", "editor", "editor_fiabilidad",
                "censor", "censor_fiabilidad", "tecnica", "formato", "como", "fuentes", "vinculadas"]


def fila_web(r: dict) -> dict:
    fi, web = r.get("ficha") or {}, r.get("para_web") or F.para_web(r.get("ficha"))
    verificadas = r.get("fuentes_verificadas") or {}
    buenas = [u for u, o in verificadas.items() if o in ("abierta", "base documentada")]
    def explicacion(c):
        d = F.dato(fi, c)
        return d.get("como") or d.get("justificacion") or ""  # «justificacion» en las fichas de la v3

    como = " ".join(f"{c.capitalize()}: {explicacion(c)}" for c in ("autor", "titulo", "serie", "editor", "censor")
                    if explicacion(c) and web.get(c))
    return {"referencia": r["referencia"], "id_tienda": (r.get("tienda") or {}).get("id_woo") or "",
            "sku": (r.get("tienda") or {}).get("sku") or "", **{k: web.get(k, "") for k in COLUMNAS_WEB if k in web},
            "como": como, "fuentes": " ".join(buenas),
            "vinculadas": " ".join(v.get("url", "") for v in fi.get("vinculadas") or [] if isinstance(v, dict))}


def orden_exportar(args) -> None:
    carpeta, con = RESULTADOS / args.carpeta, abrir_gestor()
    rs = [r for r in resultados(carpeta, args.lista) if r.get("ficha")]
    for r in rs:  # las pasadas anteriores a la v4 no guardaban la ficha de la tienda
        r.setdefault("tienda", gestor(con, r["referencia"])["tienda"])
    destino = carpeta / "para_web.csv"
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_WEB, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(fila_web(r) for r in rs)
    print(f"{len(rs)} obras -> {destino}")


def orden_comparar(args) -> None:
    con = abrir_gestor()
    a, b = resultados(RESULTADOS / args.a), resultados(RESULTADOS / args.b)
    comunes = {r["referencia"] for r in a} & {r["referencia"] for r in b}
    print(f"Sobre las {len(comunes)} obras que tienen las dos pasadas\n")
    for nombre, rs in ((args.a, a), (args.b, b)):
        rs = [r for r in rs if r["referencia"] in comunes]
        coste = sum(r.get("coste_eur", 0) for r in rs) / max(1, len(rs))
        print(f"## {nombre} · {coste:.2f} € por obra")
        for t in medir.tasas([(r.get("ficha"), gestor(con, r["referencia"])) for r in rs]):
            print(f"  {t['campo']:<7} desacuerdo {t['todas']:<14} con fiabilidad alta {t['alta']:<14} sin dato {t['sin_dato_del_agente']}")


def orden_muestra(_args) -> None:
    con = abrir_gestor()
    candidatas = [r[0] for r in con.execute(
        """select o.referencia from nuc_obra o where o.tecnica_literal like '%Moku%'
             and coalesce(o.editor_literal,'') != '' and (o.anio is not null or coalesce(o.anio_literal,'') != '')
             and exists (select 1 from nuc_imagen i where i.referencia=o.referencia and i.principal=1
                         and i.retirada=0 and i.ruta_archivo is not null) order by o.referencia""")]
    elegidas = sorted(random.Random(SEMILLA).sample(candidatas, TAMANO_MUESTRA))
    MUESTRA.write_text("referencia\n" + "\n".join(elegidas) + "\n", encoding="utf-8")
    print(f"{len(candidatas)} candidatas; {len(elegidas)} elegidas con semilla {SEMILLA} -> {MUESTRA}")


# ---------------------------------------------------------------- entrada

def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cargar_env()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="orden", required=True)

    c = sub.add_parser("catalogar", help="identifica obras del Gestor")
    grupo = c.add_mutually_exclusive_group()
    grupo.add_argument("--solo", nargs="*", metavar="REF")
    grupo.add_argument("--lista", type=Path, metavar="F.csv", help="CSV con columna «referencia» (por defecto, la muestra)")
    c.add_argument("--hasta", metavar="HH:MM", help="no empezar obras nuevas a partir de esa hora")
    c.add_argument("--en-seco", action="store_true", help="dice qué haría, en qué grupos y cuánto costaría; no llama a la API")
    c.add_argument("--repetir", action="store_true", help="vuelve a hacer las que ya tienen resultado")
    c.add_argument("--paralelo", type=int, default=3)
    c.add_argument("--sin-web", action="store_true", help="solo la fase A")
    c.add_argument("--modelo", default=agente.MODELO_POR_DEFECTO)
    c.add_argument("--esfuerzo", default=agente.ESFUERZO, choices=["low", "medium", "high"])
    c.set_defaults(f=orden_catalogar)

    d = sub.add_parser("identificar", help="una estampa con tus fotos, fuera del Gestor")
    d.add_argument("fotos", nargs="+", metavar="FOTO")
    d.add_argument("--medidas", required=True, metavar="ALTOxANCHO")
    d.add_argument("--nombre")
    d.add_argument("--pista", nargs="*", metavar="URL", help="p. ej. el resultado de la búsqueda por imagen en ukiyo-e.org")
    d.add_argument("--modelo", default=agente.MODELO_POR_DEFECTO)
    d.add_argument("--esfuerzo", default=agente.ESFUERZO, choices=["low", "medium", "high"])
    d.set_defaults(f=orden_identificar)

    for nombre, funcion, ayuda in (("informe", orden_informe, "desacuerdo con el Gestor, coste y fuentes"),
                                   ("exportar", orden_exportar, "CSV con lo publicable en la web")):
        o = sub.add_parser(nombre, help=ayuda)
        o.add_argument("--carpeta", default=CARPETA)
        o.add_argument("--lista", type=Path)
        o.set_defaults(f=funcion)

    k = sub.add_parser("comparar", help="dos carpetas de resultados lado a lado")
    k.add_argument("a")
    k.add_argument("b")
    k.set_defaults(f=orden_comparar)
    sub.add_parser("muestra").set_defaults(f=orden_muestra)
    args = p.parse_args(argv)
    args.f(args)


if __name__ == "__main__":
    main()
