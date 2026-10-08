"""Piloto de catalogación: 50 estampas japonesas del Gestor, identificadas desde la foto.

Órdenes:
  python piloto.py muestra                       elige las 50 y escribe piloto/muestra.csv
  python piloto.py catalogar [--modelo M] [--sin-web] [--en-seco] [--solo REF ...]
  python piloto.py informe   [--modelo M]

El Gestor (TDP_BASE) y las imágenes (TDP_IMAGENES) se abren en SOLO LECTURA.
Diseño: docs/01_diseno_piloto.md.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import random
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MUESTRA = RAIZ / "piloto" / "muestra.csv"
PROMPT = RAIZ / "piloto" / "prompt.md"
RESULTADOS = RAIZ / "resultados"

MODELO_POR_DEFECTO = "claude-sonnet-5-5"
TAMANO_MUESTRA = 50
SEMILLA = 2026
MAX_BUSQUEDAS = 8
MAX_LECTURAS = 8
MAX_REANUDACIONES = 5  # pause_turn: el servidor para cada 10 iteraciones y se le dice que siga

# USD por millón de tokens: entrada, salida, lectura de caché. Precios de octubre de 2026.
PRECIOS = {
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}
USD_POR_BUSQUEDA = 0.01
EUR_POR_USD = 0.92  # ponytail: tipo fijo; el informe dice que es aproximado

# Fuera del piloto por condiciones de uso (decisión P-10 del diseño).
DOMINIOS_BLOQUEADOS = [
    "artnet.com", "artprice.com", "mutualart.com", "askart.com", "invaluable.com",
    "liveauctioneers.com", "ukiyo-e.org", "dh-jac.net", "tallerdelprado.com",
]


# ---------------------------------------------------------------- entorno y Gestor

def cargar_env() -> None:
    fichero = RAIZ / ".env"
    if not fichero.exists():
        return
    for linea in fichero.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def abrir_gestor() -> sqlite3.Connection:
    base = Path(os.environ.get("TDP_BASE", r"C:\dev\GESTOR_TDP\datos\tdp.sqlite"))
    if not base.exists():
        sys.exit(f"No encuentro la base del Gestor en {base}. Pon TDP_BASE en .env.")
    con = sqlite3.connect(f"{base.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def carpeta_imagenes() -> Path:
    carpeta = Path(os.environ.get("TDP_IMAGENES", r"Z:\IMAGENES"))
    if not carpeta.exists():
        sys.exit(f"No encuentro las imágenes en {carpeta}. Pon TDP_IMAGENES en .env.")
    return carpeta


def verdad(con: sqlite3.Connection, referencia: str) -> dict:
    """La ficha del Gestor, que es la verdad contra la que se mide (y que también puede estar mal)."""
    o = con.execute(
        """select o.referencia, o.titulo, o.serie_literal, o.editor_literal, o.anio, o.anio_literal,
                  o.alto_cm, o.ancho_cm, o.tecnica_literal, a.nombre_canonico as artista
           from nuc_obra o left join nuc_artista a on a.id = o.artista_id
           where o.referencia = ?""",
        (referencia,),
    ).fetchone()
    if o is None:
        sys.exit(f"{referencia} no está en el Gestor.")
    imagenes = [
        r["ruta_archivo"]
        for r in con.execute(
            "select ruta_archivo from nuc_imagen where referencia=? and retirada=0 and ruta_archivo is not null"
            " order by principal desc, nombre_fichero",
            (referencia,),
        )
    ]
    return {**dict(o), "imagenes": imagenes}


# ---------------------------------------------------------------- muestra

def orden_muestra(_args: argparse.Namespace) -> None:
    con = abrir_gestor()
    candidatas = [
        r[0]
        for r in con.execute(
            """select o.referencia from nuc_obra o
               where o.tecnica_literal like '%Moku%'
                 and coalesce(o.editor_literal,'') != ''
                 and (o.anio is not null or coalesce(o.anio_literal,'') != '')
                 and exists (select 1 from nuc_imagen i where i.referencia=o.referencia
                             and i.principal=1 and i.retirada=0 and i.ruta_archivo is not null)
               order by o.referencia"""
        )
    ]
    elegidas = sorted(random.Random(SEMILLA).sample(candidatas, TAMANO_MUESTRA))
    MUESTRA.parent.mkdir(exist_ok=True)
    with MUESTRA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["referencia"])
        w.writerows([r] for r in elegidas)
    print(f"{len(candidatas)} candidatas; {len(elegidas)} elegidas con semilla {SEMILLA} → {MUESTRA}")


def leer_muestra() -> list[str]:
    if not MUESTRA.exists():
        sys.exit("No hay muestra: ejecuta antes `python piloto.py muestra`.")
    with MUESTRA.open(encoding="utf-8") as f:
        return [fila["referencia"] for fila in csv.DictReader(f)]


# ---------------------------------------------------------------- catalogar

def cliente():
    """El cliente de la API. Una clave de organización necesita además ANTHROPIC_WORKSPACE_ID."""
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Falta ANTHROPIC_API_KEY en .env.")
    cabeceras = {}
    if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        cabeceras["anthropic-workspace-id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
    return anthropic.Anthropic(default_headers=cabeceras)


def bloque_imagen(ruta: Path) -> dict:
    tipo = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[ruta.suffix.lower()]
    datos = base64.standard_b64encode(ruta.read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": tipo, "data": datos}}


def herramientas(con_web: bool) -> list[dict]:
    if not con_web:
        return []
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_BUSQUEDAS,
         "blocked_domains": DOMINIOS_BLOQUEADOS},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": MAX_LECTURAS,
         "blocked_domains": DOMINIOS_BLOQUEADOS, "max_content_tokens": 8000},
    ]


def sumar_uso(total: dict, uso) -> None:
    total["entrada"] += uso.input_tokens or 0
    total["salida"] += uso.output_tokens or 0
    total["cache_escrita"] += getattr(uso, "cache_creation_input_tokens", 0) or 0
    total["cache_leida"] += getattr(uso, "cache_read_input_tokens", 0) or 0
    servidor = getattr(uso, "server_tool_use", None)
    if servidor is not None:
        total["busquedas"] += getattr(servidor, "web_search_requests", 0) or 0
        total["lecturas"] += getattr(servidor, "web_fetch_requests", 0) or 0


def coste_eur(modelo: str, uso: dict) -> float:
    entrada, salida, cache = PRECIOS.get(modelo, PRECIOS[MODELO_POR_DEFECTO])
    usd = (
        uso["entrada"] * entrada
        + uso["cache_escrita"] * entrada * 1.25
        + uso["cache_leida"] * cache
        + uso["salida"] * salida
    ) / 1_000_000 + uso["busquedas"] * USD_POR_BUSQUEDA
    return round(usd * EUR_POR_USD, 4)


def extraer_json(texto: str) -> dict | None:
    bloques = re.findall(r"```json\s*(\{.*?\})\s*```", texto, flags=re.S)
    for candidato in reversed(bloques):
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            continue
    return None


def catalogar_una(client, modelo: str, ficha: dict, imagenes: list[Path], con_web: bool) -> dict:
    import anthropic

    sistema = [{"type": "text", "text": PROMPT.read_text(encoding="utf-8"), "cache_control": {"type": "ephemeral"}}]
    medidas = f"Medidas de la hoja: {ficha['alto_cm']} cm de alto por {ficha['ancho_cm']} cm de ancho."
    contenido = [bloque_imagen(r) for r in imagenes] + [
        {"type": "text", "text": f"{medidas} Propón la ficha catalográfica de esta estampa siguiendo las reglas."}
    ]
    mensajes = [{"role": "user", "content": contenido}]
    uso = dict(entrada=0, salida=0, cache_escrita=0, cache_leida=0, busquedas=0, lecturas=0)
    consultas, lecturas = [], []
    inicio = time.time()
    respuesta = None
    for _ in range(MAX_REANUDACIONES + 1):
        respuesta = client.messages.create(
            model=modelo,
            max_tokens=16000,
            system=sistema,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            tools=herramientas(con_web),
            messages=mensajes,
        )
        sumar_uso(uso, respuesta.usage)
        for b in respuesta.content:
            if b.type == "server_tool_use":
                (consultas if b.name == "web_search" else lecturas).append(json.dumps(b.input, ensure_ascii=False))
        if respuesta.stop_reason != "pause_turn":
            break
        mensajes = mensajes[:1] + [{"role": "assistant", "content": respuesta.content}]
    texto = "\n".join(b.text for b in respuesta.content if b.type == "text")
    return {
        "referencia": ficha["referencia"],
        "modelo": modelo,
        "con_web": con_web,
        "ficha": extraer_json(texto),
        "texto": texto,
        "parada": respuesta.stop_reason,
        "uso": uso,
        "coste_eur": coste_eur(modelo, uso),
        "consultas": consultas,
        "lecturas": lecturas,
        "duracion_s": round(time.time() - inicio, 1),
    }


def orden_catalogar(args: argparse.Namespace) -> None:
    con = abrir_gestor()
    carpeta = carpeta_imagenes()
    referencias = args.solo or leer_muestra()
    salida = RESULTADOS / (args.modelo + ("" if not args.sin_web else "_sin_web"))
    salida.mkdir(parents=True, exist_ok=True)

    client = None if args.en_seco else cliente()

    total_eur, hechas, saltadas = 0.0, 0, 0
    for ref in referencias:
        destino = salida / f"{ref}.json"
        if destino.exists():
            saltadas += 1
            continue
        ficha = verdad(con, ref)
        imagenes = [carpeta / r for r in ficha["imagenes"][:2] if (carpeta / r).exists()]
        if not imagenes:
            print(f"{ref}: sin imagen en {carpeta}; se salta")
            continue
        if args.en_seco:
            print(f"{ref}: {len(imagenes)} imagen(es), {ficha['alto_cm']}x{ficha['ancho_cm']} cm → {destino.name}")
            continue
        try:
            resultado = catalogar_una(client, args.modelo, ficha, imagenes, not args.sin_web)
        except Exception as e:  # la obra que falla se apunta y se sigue con la siguiente
            resultado = {"referencia": ref, "modelo": args.modelo, "error": f"{type(e).__name__}: {e}", "coste_eur": 0.0}
        destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        total_eur += resultado["coste_eur"]
        hechas += 1
        estado = "ERROR " + resultado["error"] if "error" in resultado else (
            f"{resultado['coste_eur']:.2f} € · {resultado['uso']['busquedas']} búsq. · {resultado['duracion_s']} s"
            + ("" if resultado["ficha"] else " · SIN JSON"))
        print(f"{ref}: {estado}")
    print(f"\n{hechas} catalogadas, {saltadas} ya hechas, {total_eur:.2f} € esta pasada → {salida}")


# ---------------------------------------------------------------- identificar (fotos sueltas)

def orden_identificar(args: argparse.Namespace) -> None:
    """Una estampa cualquiera, con tus fotos: no toca el Gestor ni la muestra."""
    imagenes = [Path(r) for r in args.imagenes]
    for r in imagenes:
        if not r.exists():
            sys.exit(f"No encuentro {r}")
    alto, ancho = (float(x.replace(",", ".")) for x in args.medidas.lower().split("x"))
    ficha = {"referencia": args.nombre or imagenes[0].stem, "alto_cm": alto, "ancho_cm": ancho}
    salida = RESULTADOS / "sueltas"
    salida.mkdir(parents=True, exist_ok=True)
    resultado = catalogar_una(cliente(), args.modelo, ficha, imagenes, not args.sin_web)
    destino = salida / f"{ficha['referencia']}.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(resultado["texto"])
    print(f"\n{resultado['coste_eur']:.2f} € · {resultado['uso']['busquedas']} búsquedas · "
          f"{resultado['uso']['lecturas']} lecturas · {resultado['duracion_s']} s → {destino}")


# ---------------------------------------------------------------- informe

GENERACION = {"ii", "iii", "iv", "2", "3", "4"}


def normalizar(texto: str | None) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", texto).strip()


def _alias(nombre: str) -> list[set[str]]:
    """'Utagawa Kunisada (Toyokuni III)' → [{utagawa,kunisada}, {toyokuni,iii}]."""
    parentesis = re.findall(r"\(([^)]*)\)", nombre or "")
    base = re.sub(r"\([^)]*\)", " ", nombre or "")
    return [set(normalizar(t).split()) for t in [base, *parentesis] if normalizar(t)]


def _mismo_conjunto(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    chico, grande = (a, b) if len(a) < len(b) else (b, a)
    return chico <= grande and not (grande - chico) & GENERACION


def mismo_artista(gestor: str | None, agente: str | None) -> bool:
    return any(_mismo_conjunto(x, y) for x in _alias(gestor or "") for y in _alias(agente or ""))


def mismo_editor(gestor: str | None, agente: str | None) -> bool:
    a, b = normalizar(gestor), normalizar(agente)
    return bool(a and b) and (a in b or b in a)


def rango_anio(anio: int | None, literal: str | None) -> tuple[int, int] | None:
    if anio:
        return (int(anio), int(anio))
    numeros = [int(n) for n in re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", literal or "")]
    if not numeros:
        return None
    holgura = 3 if re.search(r"circa|ca\.|c\.|hacia|aprox", literal or "", re.I) else 0
    return (min(numeros) - holgura, max(numeros) + holgura)


def mismo_anio(gestor: tuple[int, int] | None, agente: tuple[int | None, int | None] | None, tolerancia: int = 2) -> bool:
    if not gestor or not agente or agente[0] is None and agente[1] is None:
        return False
    desde = agente[0] if agente[0] is not None else agente[1]
    hasta = agente[1] if agente[1] is not None else agente[0]
    return desde - tolerancia <= gestor[1] and hasta + tolerancia >= gestor[0]


def _campo(ficha: dict | None, *ruta, defecto=None):
    actual = ficha or {}
    for paso in ruta:
        if not isinstance(actual, dict):
            return defecto
        actual = actual.get(paso)
    return defecto if actual is None else actual


def orden_informe(args: argparse.Namespace) -> None:
    con = abrir_gestor()
    carpeta = RESULTADOS / args.modelo
    resultados = sorted(carpeta.glob("TDP-*.json"))
    if not resultados:
        sys.exit(f"No hay resultados en {carpeta}.")
    filas = []
    for fichero in resultados:
        r = json.loads(fichero.read_text(encoding="utf-8"))
        v = verdad(con, r["referencia"])
        f = r.get("ficha")
        fecha_agente = (_campo(f, "fecha", "desde"), _campo(f, "fecha", "hasta"))
        filas.append({
            "referencia": r["referencia"],
            "error": r.get("error", "" if f else "sin JSON"),
            "artista_gestor": v["artista"] or "",
            "artista_agente": _campo(f, "artista", "nombre", defecto="") or "",
            "conf_artista": _campo(f, "artista", "confianza", defecto="") or "",
            "acierto_artista": mismo_artista(v["artista"], _campo(f, "artista", "nombre")),
            "editor_gestor": v["editor_literal"] or "",
            "editor_agente": _campo(f, "editor", "nombre", defecto="") or "",
            "acierto_editor": mismo_editor(v["editor_literal"], _campo(f, "editor", "nombre")),
            "anio_gestor": v["anio"] or v["anio_literal"] or "",
            "fecha_agente": f"{fecha_agente[0] or ''}-{fecha_agente[1] or ''}" if f else "",
            "acierto_anio": mismo_anio(rango_anio(v["anio"], v["anio_literal"]), fecha_agente),
            "titulo_gestor": v["titulo"] or "",
            "titulo_agente": _campo(f, "titulo", "castellano", defecto="") or _campo(f, "titulo", "romaji", defecto="") or "",
            "adjudicacion_titulo": "",
            "serie_gestor": v["serie_literal"] or "",
            "serie_agente": _campo(f, "serie", "castellano", defecto="") or _campo(f, "serie", "romaji", defecto="") or "",
            "adjudicacion_serie": "",
            "ejemplares": len(_campo(f, "ejemplares", defecto=[]) or []),
            "busquedas": _campo(r, "uso", "busquedas", defecto=0),
            "coste_eur": r.get("coste_eur", 0.0),
            "duracion_s": r.get("duracion_s", ""),
        })

    with (carpeta / "resumen.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(filas)

    n = len(filas)
    validas = [x for x in filas if not x["error"]]
    coste = sum(x["coste_eur"] for x in filas)

    def tasa(clave, subconjunto=validas):
        return f"{sum(1 for x in subconjunto if x[clave])}/{len(subconjunto)}" if subconjunto else "0/0"

    altas = [x for x in validas if x["conf_artista"] == "alta"]
    bajas = [x["referencia"] for x in validas if x["conf_artista"] in ("baja", "")]
    lineas = [
        f"# Informe del piloto · modelo `{args.modelo}`",
        "",
        f"Obras: {n} · con ficha: {len(validas)} · con error o sin JSON: {n - len(validas)}",
        f"Coste: {coste:.2f} € en total, {coste / n:.2f} € por obra (a {EUR_POR_USD} €/USD, aproximado)",
        "",
        "| Campo | Acierto (automático) |",
        "|---|---|",
        f"| Artista | {tasa('acierto_artista')} |",
        f"| Artista, solo confianza alta | {tasa('acierto_artista', altas)} de {len(altas)} con confianza alta |",
        f"| Editor | {tasa('acierto_editor')} |",
        f"| Año (rango con ±2) | {tasa('acierto_anio')} |",
        "",
        "Título y serie no se comparan solos: rellena `adjudicacion_titulo` y `adjudicacion_serie` en `resumen.csv`.",
        "",
        f"Confianza baja o sin dar en artista ({len(bajas)}): {', '.join(bajas) or 'ninguna'}",
        "",
        "Errores: " + (", ".join(f"{x['referencia']} ({x['error']})" for x in filas if x["error"]) or "ninguno"),
        "",
        "Obras donde el agente discrepa del Gestor en artista (mirar quién tiene razón):",
    ]
    lineas += [f"- {x['referencia']}: Gestor «{x['artista_gestor']}» · agente «{x['artista_agente']}» ({x['conf_artista']})"
               for x in validas if not x["acierto_artista"]] or ["- ninguna"]
    (carpeta / "informe.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"\n→ {carpeta / 'informe.md'} y {carpeta / 'resumen.csv'}")


# ---------------------------------------------------------------- entrada

def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cargar_env()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="orden", required=True)
    sub.add_parser("muestra").set_defaults(f=orden_muestra)
    c = sub.add_parser("catalogar")
    c.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    c.add_argument("--sin-web", action="store_true", help="solo visión, sin búsqueda ni lectura web")
    c.add_argument("--en-seco", action="store_true", help="lista lo que haría sin llamar a la API")
    c.add_argument("--solo", nargs="*", metavar="REF", help="solo estas referencias")
    c.set_defaults(f=orden_catalogar)
    d = sub.add_parser("identificar", help="una estampa con tus propias fotos, fuera del Gestor")
    d.add_argument("imagenes", nargs="+", metavar="FOTO", help="una o varias fotos (la primera, la hoja entera)")
    d.add_argument("--medidas", required=True, metavar="ALTOxANCHO", help="en cm, p. ej. 35x24.4")
    d.add_argument("--nombre", help="nombre del resultado (por defecto, el de la primera foto)")
    d.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    d.add_argument("--sin-web", action="store_true")
    d.set_defaults(f=orden_identificar)
    i = sub.add_parser("informe")
    i.add_argument("--modelo", default=MODELO_POR_DEFECTO, help="carpeta de resultados (p. ej. claude-sonnet-5-5_sin_web)")
    i.set_defaults(f=orden_informe)
    args = p.parse_args(argv)
    args.f(args)


if __name__ == "__main__":
    main()
