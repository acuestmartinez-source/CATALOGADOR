"""CT-06: lo que se lee en la hoja manda.

Cada dato que trae su texto en caracteres (la firma, el título y la serie en japonés, el sello del editor,
la lectura del censor) se busca entre los bloques del OCR local. Si el OCR lee esos mismos caracteres en
la hoja, el dato lleva `leido_en_hoja` (lo que leyó el OCR) y su recuadro pasa a ser el del bloque: el
OCR mide dónde está el texto, el modelo lo estima. El recuadro del modelo se guarda en `cajas_modelo`.
Sin coincidencia, el dato queda como estaba, sin `leido_en_hoja`: sin comprobar.

Y ukiyo-e.org es un índice: `museos` da, para cada ficha suya ya en caché, la ficha del museo de detrás.
"""
from __future__ import annotations

import ficha as F
import ukiyoe

TEXTO = {"autor": ("firma",), "titulo": ("japones",), "serie": ("japones",), "editor": ("sello",),
         "censor": ("lectura", "sello")}
MINIMO = 2  # caracteres en común; uno solo (画, 版) casa con cualquier cosa


def _texto(d: dict, claves) -> str:
    # «廣重画 · Hiroshige ga»: solo cuentan los caracteres japoneses
    return "".join(F._cjk(str(d.get(k) or "")) for k in claves)


def bloque_de(texto: str, bloques: list[dict]) -> dict | None:
    """El bloque del OCR que más caracteres comparte con el texto, si comparte al menos MINIMO y la mitad."""
    letras = set(F._cjk(texto))
    if len(letras) < MINIMO:
        return None
    mejor, comun = None, 0
    for b in bloques or []:
        n = len(letras & set(F._cjk(b.get("texto"))))
        if n > comun:
            mejor, comun = b, n
    return mejor if comun >= max(MINIMO, len(letras) / 2) else None


def anclar(ficha: dict | None, bloques: list[dict]) -> dict | None:
    for campo, claves in TEXTO.items():
        d = (ficha or {}).get(campo)
        if not isinstance(d, dict):
            continue
        b = bloque_de(_texto(d, claves), bloques)
        if b is None:
            continue
        d["leido_en_hoja"] = b["texto"]
        if d.get("cajas") != [b["caja"]]:
            d["cajas_modelo"] = d.get("cajas") or []
            d["cajas"] = [b["caja"]]
    return ficha


def museos(ficha: dict | None) -> dict[str, str]:
    """{ficha de ukiyo-e.org: ficha del museo}, solo de lo que ya está en caché: no pide nada."""
    urls = {v.get("url") for v in (ficha or {}).get("vinculadas") or [] if isinstance(v, dict)}
    urls |= {u for c in F.ESENCIALES for u in F.dato(ficha, c).get("fuentes") or [] if isinstance(u, str)}
    salida = {}
    for u in sorted(x for x in urls if x and "ukiyo-e.org/image/" in x):
        if ukiyoe.en_cache(u):
            museo = ukiyoe.ficha(u).get("ficha_original") or ""
            if museo.startswith("http") and "ukiyo-e.org" not in museo:
                salida[u] = museo
    return salida
