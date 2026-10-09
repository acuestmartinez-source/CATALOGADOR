"""Comparar lo que propone el agente con la ficha del Gestor.

Lo que se mide es DESACUERDO con el Gestor, no error: el Gestor también se equivoca (TDP-007990,
las tres láminas de Hauta tora no maki). El error real sale de una persona que adjudica.
"""
from __future__ import annotations

import re

import ficha as F

GENERACION = {"ii", "iii", "iv", "2", "3", "4"}


def _alias(nombre: str) -> list[set[str]]:
    """'Utagawa Kunisada (Toyokuni III)' → [{utagawa,kunisada}, {toyokuni,iii}]."""
    parentesis = re.findall(r"\(([^)]*)\)", nombre or "")
    base = re.sub(r"\([^)]*\)", " ", nombre or "")
    return [set(F.normalizar(t).split()) for t in [base, *parentesis] if F.normalizar(t)]


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
    """Un nombre contiene al otro, sin espacios ni guiones; o el nombre comercial con o sin «ya» (Kato Seibei = Katōya Seibei)."""
    a, b = F.normalizar(gestor).replace(" ", ""), F.normalizar(agente).replace(" ", "")
    if a and b and (a in b or b in a):
        return True

    def palabras(texto):
        return {re.sub(r"ya$", "", w) for w in F.normalizar(texto).split() if len(w) >= 3}

    g, ag = palabras(gestor), palabras(agente)
    return len(g) >= 2 and g <= ag


def misma_serie(gestor: str | None, agente: str | None) -> bool:
    a, b = F.normalizar(gestor).replace(" ", ""), F.normalizar(agente).replace(" ", "")
    return bool(a and b) and (a[:10] in b or b[:10] in a)


def rango_anio(anio: int | None, literal: str | None) -> tuple[int, int] | None:
    if anio:
        return (int(anio), int(anio))
    numeros = [int(n) for n in re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", literal or "")]
    if not numeros:
        return None
    holgura = 3 if re.search(r"circa|ca\.|c\.|hacia|aprox", literal or "", re.I) else 0
    return (min(numeros) - holgura, max(numeros) + holgura)


def mismo_anio(gestor: tuple[int, int] | None, agente: tuple[int | None, int | None] | None, tolerancia: int = 2) -> bool:
    if not gestor or not agente or (agente[0] is None and agente[1] is None):
        return False
    desde = agente[0] if agente[0] is not None else agente[1]
    hasta = agente[1] if agente[1] is not None else agente[0]
    return desde - tolerancia <= gestor[1] and hasta + tolerancia >= gestor[0]


def fechas_agente(ficha: dict | None) -> tuple[int | None, int | None]:
    c = F.dato(ficha, "censor")
    if c.get("fecha_desde") is not None or c.get("fecha_hasta") is not None:
        return c.get("fecha_desde"), c.get("fecha_hasta")
    fecha = (ficha or {}).get("fecha") or {}  # fichas de la v2 y la v3
    return fecha.get("desde"), fecha.get("hasta")


def comparar(ficha: dict | None, gestor: dict) -> dict[str, bool | None]:
    """Por campo: True coincide, False discrepa, None no hay con qué comparar (el Gestor no lo tiene o el agente no lo da)."""
    def o_nada(g, a, prueba):
        return None if not g or not a else prueba(g, a)

    return {
        "autor": o_nada(gestor.get("artista"), F.valor(ficha, "autor"), mismo_artista),
        "serie": o_nada(gestor.get("serie_literal"), F.dato(ficha, "serie").get("romaji") or F.valor(ficha, "serie"), misma_serie),
        "editor": o_nada(gestor.get("editor_literal"), F.valor(ficha, "editor"), mismo_editor),
        "fecha": o_nada(rango_anio(gestor.get("anio"), gestor.get("anio_literal")), fechas_agente(ficha) if any(
            v is not None for v in fechas_agente(ficha)) else None, mismo_anio),
    }


def tasas(fichas_y_gestor: list[tuple[dict | None, dict]]) -> list[dict]:
    """Desacuerdo con el Gestor por campo y por fiabilidad, y cuántas veces el agente no da el dato."""
    filas = []
    for campo in ("autor", "serie", "editor", "fecha"):
        clave = "censor" if campo == "fecha" else campo
        por = {"todas": [0, 0], "alta": [0, 0], "media": [0, 0], "baja": [0, 0]}
        sin_dato = 0
        for ficha, gestor in fichas_y_gestor:
            r = comparar(ficha, gestor)[campo]
            if r is None:
                sin_dato += bool(gestor.get({"autor": "artista", "serie": "serie_literal", "editor": "editor_literal",
                                             "fecha": "anio"}[campo]) or (campo == "fecha" and gestor.get("anio_literal")))
                continue
            for grupo in ("todas", F.fiabilidad(ficha, clave)):
                if grupo in por:
                    por[grupo][0] += 1
                    por[grupo][1] += not r
        filas.append({"campo": campo, "sin_dato_del_agente": sin_dato,
                      **{g: (f"{d}/{n} ({100 * d / n:.0f} %)" if n else "—") for g, (n, d) in por.items()}})
    return filas
