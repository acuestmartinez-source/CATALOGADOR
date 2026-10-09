"""La ficha esencial de una estampa y lo que de ella va a la web.

Seis datos: autor, título, serie, editor, censor (con la fecha) y técnica. Cada uno con su
`nivel`, `confianza`, `como`, `fuentes` y `cajas`. La fiabilidad que se publica la calcula el
código con reglas fijas, no el modelo.
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from pathlib import Path

ESENCIALES = ("autor", "titulo", "serie", "editor", "censor", "tecnica")

NIVELES = (  # de más a menos fiable; el prompt usa los mismos nombres
    "ukiyo-e.org misma estampa",
    "museo misma estampa",
    "lectura cotejada",
    "otra lámina documentada",
    "marchante",
    "lectura sin cotejar",
    "construido",
    "hipótesis",
)
_ANTIGUOS = {"museo otra lámina": "otra lámina documentada"}  # nombres de la v3
_CLAVES_V3 = {"autor": "artista"}  # las fichas antiguas llamaban «artista» al autor


def dato(ficha: dict | None, campo: str) -> dict:
    """El dato `campo` de una ficha, también de las fichas de la v2 y la v3."""
    ficha = ficha or {}
    d = ficha.get(campo)
    if not isinstance(d, dict) and campo in _CLAVES_V3:
        d = ficha.get(_CLAVES_V3[campo])
    if not isinstance(d, dict) and campo == "tecnica" and isinstance(ficha.get("tecnica"), str):
        d = {"nombre": ficha["tecnica"], "formato": (ficha.get("formato") or {}).get("nombre")}
    fecha = ficha.get("fecha")
    if campo == "censor" and isinstance(fecha, dict) and not (d or {}).get("fecha_desde"):
        # v2 y v3: la fecha iba aparte, con su propio nivel; lo que se publica es la fecha.
        d = {**(d or {}), "fecha_desde": fecha.get("desde"), "fecha_hasta": fecha.get("hasta"),
             "nivel": fecha.get("nivel") or (d or {}).get("nivel"), "confianza": fecha.get("confianza"),
             "metodo": fecha.get("metodo"), "como": (d or {}).get("justificacion") or fecha.get("justificacion")}
    return d if isinstance(d, dict) else {}


def valor(ficha: dict | None, campo: str) -> str:
    """El texto del dato tal como iría a la web, sin explicaciones."""
    d = dato(ficha, campo)
    if campo in ("autor", "editor", "tecnica"):
        return (d.get("nombre") or "").strip()
    if campo in ("titulo", "serie"):
        return (d.get("castellano") or d.get("romaji") or d.get("japones") or "").strip()
    if campo == "censor":
        desde, hasta = d.get("fecha_desde"), d.get("fecha_hasta")
        if desde is None and hasta is None:  # fichas antiguas: la fecha iba aparte
            fecha = (ficha or {}).get("fecha") or {}
            desde, hasta = fecha.get("desde"), fecha.get("hasta")
        if desde is None and hasta is None:
            return ""
        return str(desde or hasta) if desde in (None, hasta) or hasta is None else f"{desde}–{hasta}"
    return ""


def nivel(ficha: dict | None, campo: str) -> str:
    n = (dato(ficha, campo).get("nivel") or "").strip()
    return _ANTIGUOS.get(n, n)


def fiabilidad(ficha: dict | None, campo: str) -> str:
    """alta, media o baja; «—» si no hay dato.

    alta: la misma estampa documentada, o una lectura cotejada con confianza alta.
    media: lectura cotejada, otra lámina documentada o marchante.
    baja: lectura sin cotejar, título construido, hipótesis o nivel desconocido.
    La técnica se ve en la foto: su fiabilidad es la confianza que da el modelo.
    """
    if not valor(ficha, campo):
        return "—"
    d = dato(ficha, campo)
    if campo == "tecnica":
        return d.get("confianza") or "media"
    n, confianza = nivel(ficha, campo), d.get("confianza")
    if n in NIVELES[:2] or (n == "lectura cotejada" and confianza == "alta"):
        return "alta"
    if n in ("lectura cotejada", "otra lámina documentada", "marchante"):
        return "media"
    return "baja"


def para_web(ficha: dict | None) -> dict:
    """Lo que se puede publicar. Autor, serie y editor solo con fiabilidad alta o media: si no, van
    vacíos (un autor no identificable es un autor que no hay). El título va siempre, con la marca de
    construido si lo es. La fecha, con fiabilidad media o más."""
    salida = {}
    for campo in ESENCIALES:
        f = fiabilidad(ficha, campo)
        publicable = f in ("alta", "media") or campo in ("titulo", "tecnica")
        salida[campo] = valor(ficha, campo) if publicable else ""
        salida[f"{campo}_fiabilidad"] = f if salida[campo] else "—"
    salida["titulo_construido"] = bool(dato(ficha, "titulo").get("construido"))
    salida["formato"] = (dato(ficha, "tecnica").get("formato") or "") if ficha else ""
    salida["serie_lamina"] = str(dato(ficha, "serie").get("numero_lamina") or "")
    return salida


# ---------------------------------------------------------------- memoria de series y libros

_cerrojo = threading.Lock()
NIVELES_MEMORIA = NIVELES[:5]  # una serie se recuerda solo si salió de un documento o de un cotejo


def _cjk(texto: str) -> str:
    from sellos import ANTIGUAS

    texto = unicodedata.normalize("NFKC", texto or "").translate(ANTIGUAS)
    return "".join(c for c in texto if unicodedata.category(c) == "Lo" and ord(c) > 0x2E80)


def leer_memoria(ruta: Path) -> list[dict]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def recordar_serie(ruta: Path, ficha: dict | None, referencia: str) -> dict | None:
    """Guarda la serie (o el libro) de una ficha si está bien documentada, para sus hermanas."""
    serie = dato(ficha, "serie")
    clave = _cjk(serie.get("japones") or "")
    if len(clave) < 3 or serie.get("confianza") != "alta" or nivel(ficha, "serie") not in NIVELES_MEMORIA:
        return None
    entrada = {
        "clave": clave,
        "serie": {k: serie.get(k) for k in ("castellano", "japones", "romaji")},
        "autor": valor(ficha, "autor") if fiabilidad(ficha, "autor") in ("alta", "media") else "",
        "editor": valor(ficha, "editor") if fiabilidad(ficha, "editor") in ("alta", "media") else "",
        "editor_sello": dato(ficha, "editor").get("sello") or "",
        "fecha": valor(ficha, "censor"),
        "fuentes": sorted({*serie.get("fuentes", []), *dato(ficha, "editor").get("fuentes", [])})[:8],
        "vinculadas": [v for v in (ficha or {}).get("vinculadas") or []
                       if isinstance(v, dict) and v.get("relacion") != "misma estampa"][:8],
        "obras": [referencia],
    }
    with _cerrojo:
        memoria = leer_memoria(ruta)
        previa = next((m for m in memoria if m["clave"] == clave), None)
        if previa:
            previa["obras"] = sorted({*previa["obras"], referencia})
            for k in ("autor", "editor", "editor_sello", "fecha"):
                previa[k] = previa[k] or entrada[k]
            previa["fuentes"] = sorted({*previa["fuentes"], *entrada["fuentes"]})[:12]
        else:
            memoria.append(entrada)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(memoria, ensure_ascii=False, indent=1), encoding="utf-8")
    return entrada


def series_en_texto(memoria: list[dict], texto_ocr: str) -> list[dict]:
    """Las series conocidas cuyo título japonés aparece entero en lo que leyó el OCR."""
    leido = _cjk(texto_ocr)
    return [m for m in memoria if m["clave"] and m["clave"] in leido]


def texto_memoria(series: list[dict]) -> str:
    lineas = []
    for m in series:
        s = m["serie"]
        lineas.append(
            f"- {s.get('japones')} · {s.get('romaji')} · {s.get('castellano')}: autor {m['autor'] or '—'}, "
            f"editor {m['editor'] or '—'} (sello {m['editor_sello'] or '—'}), fecha {m['fecha'] or '—'}; "
            f"ya catalogada en {', '.join(m['obras'][:5])}; fuentes {' '.join(m['fuentes'][:5])}")
    return ("El taller ya ha documentado esta serie en otras obras. Compruébala en la estampa (cartucho, firma, "
            "sello de editor); si cuadra, usa estos datos con su nivel y no la vuelvas a buscar. El título de ESTA "
            "hoja sigue siendo tuyo:\n" + "\n".join(lineas))


def normalizar(texto: str | None) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", texto).strip()
