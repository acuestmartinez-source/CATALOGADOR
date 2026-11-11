"""Las series juntas: qué hojas de cada serie tiene el taller, qué dicen entre todas y cuál desentona.

  python series.py informe --fichas RUTA/fichas.jsonl [--gestor obras.csv] [--salida series.md]
  python series.py json --fichas RUTA/fichas.jsonl

Una hoja suelta se identifica peor que una serie entera. Las hojas de una serie comparten autor,
editor y casi siempre fecha; llevan el mismo cartucho; y sus sellos de censura caen en los mismos
años. Puestas juntas, lo que desentona se ve: un autor distinto, un editor distinto, una fecha fuera
del tramo de las demás o, lo más útil, **una hoja sin el sello de censura que sus hermanas sí llevan**,
que es la señal de un margen recortado, de una tirada posterior o de una reproducción.

Entra lo que CATALOGADOR ya propuso (`fichas.jsonl`; de cada obra vale su última propuesta) y, si se le
da, lo que dice el Gestor de las obras que aún no se han identificado (`--gestor`, un CSV con
`referencia;serie` y, si los hay, `titulo;artista;anio`): así la serie sale entera, con lo identificado y
lo pendiente. Solo lee. El informe lleva referencias de obra: es para la casa y no sale del NAS.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import ficha as F

MIN_HOJAS = 2  # desde cuántas hojas se habla de consenso y de quién desentona


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
        if isinstance(fila, dict) and "formato" not in fila:
            filas.append(fila)
    return filas


def _dato(linea: dict, campo: str) -> dict:
    d = (linea.get("datos") or {}).get(campo)
    return d if isinstance(d, dict) else {}


def clave_de_serie(valor: str | None, detalle: str | None = None) -> str:
    """Con qué se juntan las hojas de una serie: su título japonés si lo hay (con las formas antiguas
    igualadas: 圖/図, 會/会), y si no, el título escrito sin tildes, macrones ni mayúsculas."""
    for texto in (detalle, valor):
        for parte in str(texto or "").split("·"):
            if "lámina" in parte:
                continue
            japones = F._cjk(parte)
            if len(japones) >= 3:
                return japones
    plano = F.normalizar(str(valor or "").translate(F.CIRCUNFLEJO).split("(")[0])
    return " ".join(re.sub(r"(the|la|las|los|el|de|del|of)", " ", plano).split())


def _lamina(linea: dict) -> str:
    n = str((linea.get("para_web") or {}).get("serie_lamina") or "").strip()
    if not n:
        m = re.search(r"lámina\s+(\S+)", str(_dato(linea, "serie").get("detalle") or ""))
        n = m.group(1) if m else ""
    return n


def _anios(valor: str | None) -> tuple[int, int] | None:
    cifras = [int(x) for x in re.findall(r"\b(1[6-9]\d\d|20\d\d)\b", str(valor or ""))]
    return (min(cifras), max(cifras)) if cifras else None


def hoja_de(linea: dict) -> dict:
    """Lo que una propuesta dice de su hoja, en plano."""
    censor = _dato(linea, "censor")
    tirada = linea.get("edicion") if isinstance(linea.get("edicion"), dict) else None
    if tirada is None:  # propuestas de antes de `edicion`: se deduce de lo publicado
        sello = " ".join(str(censor.get(k) or "") for k in ("lectura", "detalle"))
        sin_sello = not censor.get("cajas") and (not F._cjk(sello) or F._SIN_SELLO.search(sello))
        tirada = {"estado": "sin determinar", "avisos": ["no se ve el sello de censura"] if sin_sello else []}
    return {"referencia": linea.get("referencia"), "id_peticion": linea.get("id_peticion"), "identificada": True,
            "titulo": _dato(linea, "titulo").get("valor"), "lamina": _lamina(linea),
            "autor": _dato(linea, "autor").get("valor"), "editor": _dato(linea, "editor").get("valor"),
            "fecha": censor.get("valor"), "serie": _dato(linea, "serie").get("valor"),
            "serie_fiabilidad": _dato(linea, "serie").get("fiabilidad"),
            "sello_censura": not any("censura" in a for a in tirada.get("avisos") or []),
            "tirada": tirada.get("estado") or "sin determinar"}


def _moda(valores: list[str | None]) -> tuple[str | None, int]:
    """El valor más repetido, comparando sin tildes ni mayúsculas ni lo que va entre paréntesis."""
    def llave(v):
        return " ".join(F.normalizar(re.sub(r"\(.*?\)", " ", v or "")).split()[:3])
    cuenta = Counter(llave(v) for v in valores if v)
    if not cuenta:
        return None, 0
    ganadora, veces = cuenta.most_common(1)[0]
    return next(v for v in valores if v and llave(v) == ganadora), veces


_GENERACION = {"i", "ii", "iii", "iv", "v", "2", "3", "4"}


def _desentona(valor: str | None, consenso: str | None) -> bool:
    """¿Es otro nombre? Se comparan sus tres primeras palabras sin tildes, mayúsculas ni lo que va entre
    paréntesis. Que uno sea el comienzo del otro vale («Fujiokaya Keijirō» y «Fujiokaya Keijirō Fujikei»),
    salvo que lo que sobre sea la generación: Kunisada no es Kunisada II."""
    if not valor or not consenso:
        return False
    a, b = (F.normalizar(re.sub(r"\(.*?\)", " ", x)).split()[:3] for x in (valor, consenso))
    if a == b:
        return False
    corto, largo = sorted((a, b), key=len)
    if corto and largo[:len(corto)] == corto:
        return bool(set(largo[len(corto):]) & _GENERACION)
    return True


def consolidar(fichas: list[dict], gestor: list[dict] | None = None) -> list[dict]:
    """Las series, de la que más hojas tiene a la que menos. Cada una con sus hojas, lo que dicen entre
    todas (autor, editor, años) y los `avisos` de las que desentonan."""
    ultima: dict[str, dict] = {}
    for linea in fichas:  # de cada obra, su última propuesta sin error
        if not linea.get("error") and isinstance(linea.get("referencia"), str):
            ultima[linea["referencia"]] = linea
    grupos: dict[str, dict] = {}
    for linea in ultima.values():
        serie = _dato(linea, "serie")
        clave = clave_de_serie(serie.get("valor"), serie.get("detalle"))
        if clave:
            g = grupos.setdefault(clave, {"clave": clave, "nombres": Counter(), "japones": Counter(), "hojas": []})
            g["hojas"].append(hoja_de(linea))
            g["nombres"][serie.get("valor")] += 1
            if F._cjk(clave):
                g["japones"][str(serie.get("detalle") or "").split("·")[0].strip()] += 1
    # lo que dice el Gestor de las obras aún sin identificar: se suman a su serie por el título escrito
    por_titulo = {F.normalizar(str(n).translate(F.CIRCUNFLEJO)): c for c, g in grupos.items() for n in g["nombres"] if n}
    # el puente: si una obra ya identificada lleva en el Gestor otro nombre de serie («Edo meishô zue» y el
    # catalogador «Vistas de lugares famosos de Edo · 江戸名勝圖會»), ese nombre del Gestor es esta misma serie
    puente: dict[str, Counter] = {}
    for fila in gestor or []:
        ref, serie = str(fila.get("referencia") or "").strip(), str(fila.get("serie") or "").strip()
        if serie and ref in ultima:
            d = _dato(ultima[ref], "serie")
            clave = clave_de_serie(d.get("valor"), d.get("detalle"))
            if clave:
                puente.setdefault(F.normalizar(serie.translate(F.CIRCUNFLEJO)), Counter())[clave] += 1
    for titulo, claves in puente.items():
        por_titulo[titulo] = claves.most_common(1)[0][0]
    for fila in gestor or []:
        ref, serie = str(fila.get("referencia") or "").strip(), str(fila.get("serie") or "").strip()
        if not ref or not serie or ref in ultima:
            continue
        clave = por_titulo.get(F.normalizar(serie.translate(F.CIRCUNFLEJO))) or clave_de_serie(serie)
        g = grupos.setdefault(clave, {"clave": clave, "nombres": Counter(), "japones": Counter(), "hojas": []})
        g["nombres"][serie] += 1
        por_titulo.setdefault(F.normalizar(serie.translate(F.CIRCUNFLEJO)), clave)
        g["hojas"].append({"referencia": ref, "id_peticion": None, "identificada": False, "titulo": fila.get("titulo") or None,
                           "lamina": "", "autor": fila.get("artista") or None, "editor": fila.get("editor") or None,
                           "fecha": fila.get("anio") or None, "serie": serie, "serie_fiabilidad": None,
                           "sello_censura": None, "tirada": None})
    salida = []
    for g in grupos.values():
        hojas = sorted(g["hojas"], key=lambda h: (not h["identificada"], h["lamina"].zfill(3) if h["lamina"] else "zzz", h["referencia"] or ""))
        vistas = [h for h in hojas if h["identificada"]]
        autor, _ = _moda([h["autor"] for h in hojas])
        editor, _ = _moda([h["editor"] for h in hojas])
        tramos = [t for t in (_anios(h["fecha"]) for h in vistas) if t]
        anios = (min(t[0] for t in tramos), max(t[1] for t in tramos)) if tramos else None
        con_sello = [h for h in vistas if h["sello_censura"]]
        avisos = []
        if len(hojas) >= MIN_HOJAS:
            for h in hojas:
                if _desentona(h["autor"], autor):
                    avisos.append(f"{h['referencia']}: autor «{h['autor']}», y la serie dice «{autor}»")
                if _desentona(h["editor"], editor):
                    avisos.append(f"{h['referencia']}: editor «{h['editor']}», y la serie dice «{editor}»")
            if len(tramos) >= 2:
                comun = Counter(a for d, h in tramos for a in range(d, h + 1)).most_common(1)[0]
                for h in vistas:
                    t = _anios(h["fecha"])
                    if t and comun[1] >= 2 and not (t[0] - 2 <= comun[0] <= t[1] + 2):
                        avisos.append(f"{h['referencia']}: fecha {h['fecha']}, lejos de la de sus hermanas (hacia {comun[0]})")
            if con_sello and len(con_sello) < len(vistas):
                for h in vistas:
                    if not h["sello_censura"]:
                        avisos.append(f"{h['referencia']}: sin el sello de censura que llevan {len(con_sello)} de sus hermanas: "
                                      "margen recortado, tirada posterior o reproducción")
            elif vistas and not con_sello and len(vistas) >= MIN_HOJAS:
                avisos.append(f"ninguna de las {len(vistas)} hojas identificadas enseña sello de censura: o lo llevaban "
                              "en un margen recortado en todas, o es una tirada sin sellos; conviene ver una a mano")
        for h in vistas:
            if h["tirada"] in ("edición posterior", "reproducción moderna"):
                avisos.append(f"{h['referencia']}: el catalogador la da por {h['tirada']}")
        nombre = g["nombres"].most_common(1)[0][0] if g["nombres"] else g["clave"]
        salida.append({"clave": g["clave"], "serie": nombre, "japones": g["japones"].most_common(1)[0][0] if g["japones"] else None,
                       "otros_nombres": [n for n in g["nombres"] if n and n != nombre], "hojas": hojas,
                       "identificadas": len(vistas), "pendientes": len(hojas) - len(vistas), "autor": autor, "editor": editor,
                       "anios": list(anios) if anios else None, "laminas": sorted({h["lamina"] for h in hojas if h["lamina"]}, key=lambda x: x.zfill(3)),
                       "avisos": avisos})
    return sorted(salida, key=lambda s: (-len(s["hojas"]), s["serie"] or ""))


def informe(series: list[dict], sueltas: int = 0) -> str:
    """El informe para la casa, en Markdown."""
    varias = [s for s in series if len(s["hojas"]) >= MIN_HOJAS]
    lineas = ["# Las series del taller, juntas", "",
              f"{len(varias)} series con dos hojas o más ({sum(len(s['hojas']) for s in varias)} hojas) y "
              f"{len(series) - len(varias)} series de las que solo hay una hoja.", ""]
    if varias:
        lineas += ["| Serie | Hojas | Identificadas | Autor | Editor | Años | Avisos |", "|---|---|---|---|---|---|---|"]
        for s in varias:
            lineas.append(f"| {s['serie']}{' · ' + s['japones'] if s['japones'] else ''} | {len(s['hojas'])} | {s['identificadas']} | "
                          f"{s['autor'] or '—'} | {s['editor'] or '—'} | {'–'.join(str(a) for a in s['anios']) if s['anios'] else '—'} | "
                          f"{len(s['avisos'])} |")
        lineas.append("")
    for s in varias:
        lineas += [f"## {s['serie']}" + (f" · {s['japones']}" if s["japones"] else ""), ""]
        if s["otros_nombres"]:
            lineas += ["También escrita: " + "; ".join(f"«{n}»" for n in s["otros_nombres"]) + ".", ""]
        lineas += [f"Autor: {s['autor'] or '—'} · editor: {s['editor'] or '—'} · años: "
                   f"{'–'.join(str(a) for a in s['anios']) if s['anios'] else '—'} · láminas con número: "
                   f"{', '.join(s['laminas']) or 'ninguna'}.", "",
                   "| Obra | Lámina | Título | Autor | Editor | Fecha | Sello de censura | Estado |", "|---|---|---|---|---|---|---|---|"]
        for h in s["hojas"]:
            sello = "—" if h["sello_censura"] is None else "sí" if h["sello_censura"] else "NO"
            lineas.append(f"| {h['referencia']} | {h['lamina'] or '—'} | {(h['titulo'] or '—')[:60]} | {h['autor'] or '—'} | "
                          f"{h['editor'] or '—'} | {h['fecha'] or '—'} | {sello} | {'identificada' if h['identificada'] else 'pendiente'} |")
        lineas.append("")
        if s["avisos"]:
            lineas += ["Lo que desentona:", ""] + [f"- {a}" for a in s["avisos"]] + [""]
    return "\n".join(lineas) + "\n"


def leer_gestor(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def publicar(fichas: Path, salida: Path) -> bool:
    """Reescribe el informe de series si cambió. Para el servicio: local, en `resultados/`."""
    texto = informe(consolidar(_jsonl(fichas)))
    try:
        if salida.read_text(encoding="utf-8") == texto:
            return False
    except OSError:
        pass
    salida.parent.mkdir(parents=True, exist_ok=True)
    parcial = salida.with_suffix(".parcial")
    parcial.write_text(texto, encoding="utf-8")
    parcial.replace(salida)
    return True


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("orden", choices=("informe", "json"))
    p.add_argument("--fichas", type=Path, required=True)
    p.add_argument("--gestor", type=Path)
    p.add_argument("--salida", type=Path)
    a = p.parse_args()
    juntas = consolidar(_jsonl(a.fichas), leer_gestor(a.gestor) if a.gestor else None)
    texto = informe(juntas) if a.orden == "informe" else json.dumps(juntas, ensure_ascii=False, indent=1)
    if a.salida:
        a.salida.write_text(texto, encoding="utf-8")
        print(f"{len(juntas)} series -> {a.salida}")
    else:
        print(texto)
