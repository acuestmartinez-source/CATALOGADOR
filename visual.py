"""La verificación visual (D-1845): ¿es nuestra foto la misma estampa que la ficha de ukiyo-e.org que cita el agente?

Comparación geométrica con OpenCV (SIFT, prueba del cociente y homografía con RANSAC): cuenta los puntos del dibujo
que encajan con una sola transformación. La misma xilografía encaja aunque cambien la foto, los colores o la tirada;
una hermana de serie no. Sin modelos descargados y en local: hacia la API no sale nada nuevo.

Umbrales de la etapa 0 (12/11/2026, 15 obras, 26 pares que sí y 349 que no): las mismas dieron de 212 a 452
puntos y ninguna distinta pasó de 120.
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

import ficha as F
import ukiyoe

UMBRAL_MISMA, UMBRAL_DUDOSA = 150, 60
LADO = 1000
UKIYOE = re.compile(r"ukiyo-e\.org/image/([A-Za-z0-9_./-]+)")
_SIFT = cv2.SIFT_create(nfeatures=4000)


def imagen_ukiyoe(id_: str) -> bytes:
    return ukiyoe.imagen(id_)


def _rasgos(datos: bytes):
    im = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise ValueError("no es una imagen")
    f = LADO / max(im.shape)
    if f < 1:
        im = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return _SIFT.detectAndCompute(cv2.createCLAHE(2.0, (8, 8)).apply(im), None)


def _puntos(a, b) -> int:
    (ka, da), (kb, db) = a, b
    if da is None or db is None or len(ka) < 8 or len(kb) < 8:
        return 0
    buenos = [m for m, n in (p for p in cv2.BFMatcher().knnMatch(da, db, k=2) if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(buenos) < 8:
        return 0
    _, mascara = cv2.findHomography(np.float32([ka[m.queryIdx].pt for m in buenos]),
                                    np.float32([kb[m.trainIdx].pt for m in buenos]), cv2.RANSAC, 8.0)
    return int(mascara.sum()) if mascara is not None else 0


def veredicto(puntos: int) -> str:
    return "misma" if puntos >= UMBRAL_MISMA else "dudosa" if puntos >= UMBRAL_DUDOSA else "no"


def coincidencia(nuestra: bytes, suya: bytes) -> dict:
    p = _puntos(_rasgos(nuestra), _rasgos(suya))
    return {"puntos": p, "veredicto": veredicto(p)}


def verificar(ficha: dict | None, foto: Path) -> tuple[dict | None, dict]:
    """Comprueba con la foto cada «ukiyo-e.org misma estampa» de la ficha. Si alguna de sus fichas encaja, el dato
    lleva `segunda_senal: "visual"`; si se pudo comprobar y ninguna encaja, baja a «otra lámina documentada» (techo
    media, D-1842) y lo dice en su `como`. Si no se pudo comprobar (ukiyo-e.org parado, sin imagen), no se toca."""
    datos = {c: F.dato(ficha, c) for c in F.ESENCIALES} if ficha else {}
    citadas = {c: [m.group(1).strip("/") for u in d.get("fuentes") or [] if (m := UKIYOE.search(str(u)))]
               for c, d in datos.items() if F.nivel(ficha, c) == "ukiyo-e.org misma estampa"}
    ids = sorted({i for v in citadas.values() for i in v})
    if not ids or not foto.exists():
        return ficha, {}
    nuestra = _rasgos(foto.read_bytes())
    informe = {}
    for id_ in ids:
        try:
            p = _puntos(nuestra, _rasgos(imagen_ukiyoe(id_)))
            informe[id_] = {"puntos": p, "veredicto": veredicto(p)}
        except (ukiyoe.Parado, OSError, ValueError):
            informe[id_] = {"puntos": None, "veredicto": "sin comprobar"}
    for campo, suyas in citadas.items():
        vistos = [informe[i]["veredicto"] for i in suyas]
        d = ficha[campo] if isinstance(ficha.get(campo), dict) else None
        if d is None or not vistos:
            continue
        if "misma" in vistos:
            d["segunda_senal"] = "visual"
        elif "sin comprobar" not in vistos:
            d["nivel"] = "otra lámina documentada"
            d["como"] = (f"{d.get('como') or ''} La ficha de ukiyo-e.org que se cita como la misma estampa no encaja "
                         f"con la foto (verificación visual, D-1845).").strip()
    return ficha, informe
