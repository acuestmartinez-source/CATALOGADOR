"""Tratamiento de imagen para leer caracteres en estampas: mejoras, OCR de recortes y anotación.

  python imagen.py variantes foto.jpg            guarda las variantes de mejora junto a la foto
  python imagen.py leer foto.jpg [x0 y0 x1 y1]   lee con el OCR de la NDL cada variante del recorte

Las mejoras son las de siempre para papel viejo, sin modelos: ampliar con interpolación,
igualar el contraste por zonas (CLAHE), quitar el rojo (para leer la tinta negra que pisa un
sello) o quedarse solo con el rojo (para leer el sello), y binarizar con umbral adaptativo
(para papel manchado o con foxing). El OCR es NDL古典籍OCR-Lite, en local.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

NDL_OCR = Path(os.environ.get("TDP_NDL_OCR", r"C:\dev\ndlkotenocr-lite"))
LADO_AMPLIACION = 1400
MEJORAS = ("ninguna", "contraste", "sin_rojo", "solo_rojo", "tinta")


def recortar(ruta: Path, caja: tuple[int, int, int, int] | None) -> Image.Image:
    """Recorte en coordenadas 0–1000 sobre la foto; sin caja, la foto entera."""
    with Image.open(ruta) as im:
        im = im.convert("RGB")
        if caja is None:
            return im.copy()
        w, h = im.size
        x0, y0, x1, y1 = (max(0, min(1000, int(v))) for v in caja)
        return im.crop((x0 * w // 1000, y0 * h // 1000, x1 * w // 1000, y1 * h // 1000))


def ampliar_imagen(im: Image.Image, lado: int = LADO_AMPLIACION) -> Image.Image:
    escala = lado / max(im.size)
    if escala > 1:  # solo se amplía; nunca se reduce lo que ya es grande
        im = im.resize((round(im.width * escala), round(im.height * escala)), Image.LANCZOS)
    return im


def mejorar(im: Image.Image, mejora: str) -> Image.Image:
    """Una de MEJORAS. Todas devuelven RGB para que el OCR y el modelo las lean igual."""
    if mejora == "ninguna":
        return im
    bgr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    if mejora == "contraste":
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(l)
        salida = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    elif mejora in ("sin_rojo", "solo_rojo"):
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        rojo = cv2.inRange(hsv, (0, 60, 60), (12, 255, 255)) | cv2.inRange(hsv, (160, 60, 60), (180, 255, 255))
        rojo = cv2.dilate(rojo, np.ones((3, 3), np.uint8))
        gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        if mejora == "sin_rojo":  # el sello rojo se vuelve papel y queda la tinta negra
            gris[rojo > 0] = 255
            gris = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris)
        else:  # solo el sello, en negro sobre blanco
            gris = np.where(rojo > 0, 0, 255).astype(np.uint8)
        salida = cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR)
    elif mejora == "tinta":
        gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gris = cv2.fastNlMeansDenoising(gris, h=12)
        binaria = cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
        salida = cv2.cvtColor(binaria, cv2.COLOR_GRAY2BGR)
    else:
        raise ValueError(f"Mejora desconocida: {mejora}. Son: {', '.join(MEJORAS)}")
    return Image.fromarray(cv2.cvtColor(salida, cv2.COLOR_BGR2RGB))


def a_bloque(im: Image.Image, calidad: int = 90) -> dict:
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=calidad)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode("ascii")}}


def ocr_carpeta(carpeta: Path) -> dict[str, list[dict]]:
    """NDL古典籍OCR-Lite sobre todas las imágenes de una carpeta, en un solo proceso."""
    python = NDL_OCR / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        raise RuntimeError(f"No encuentro el OCR de la NDL en {NDL_OCR}")
    salida = carpeta / "_ocr"
    salida.mkdir(exist_ok=True)
    subprocess.run([str(python), "ocr.py", "--sourcedir", str(carpeta.resolve()), "--output", str(salida.resolve())],
                   cwd=NDL_OCR / "src", check=True, capture_output=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    lecturas = {}
    for f in salida.glob("*.json"):
        crudo = json.loads(f.read_text(encoding="utf-8"))
        bloques = crudo["contents"][0] if crudo.get("contents") else []
        lecturas[f.stem] = [{"texto": b.get("text", ""), "confianza": round(float(b.get("confidence", 0)), 2)}
                            for b in bloques]
    return lecturas


def leer_variantes(im: Image.Image, mejoras=("ninguna", "contraste", "sin_rojo", "tinta")) -> dict[str, list[dict]]:
    """El mismo recorte, mejorado de varias formas y leído por el OCR. Lo que coincide entre variantes es más fiable."""
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp)
        base = ampliar_imagen(im, 1200)
        for m in mejoras:
            mejorar(base, m).save(carpeta / f"{m}.jpg", quality=92)
        return ocr_carpeta(carpeta)


# ---------------------------------------------------------------- anotación

COLORES = {  # el mismo color en la foto y en la tabla de la página de revisión
    "titulo": ("#1f5fbf", "Título"),
    "serie": ("#7b3fb5", "Serie"),
    "artista": ("#c0392b", "Autor / firma"),
    "censor": ("#1e8449", "Censor y fecha"),
    "editor": ("#d35400", "Editor"),
    "otro": ("#7f7f7f", "Otros"),
}


def anotar(ruta: Path, marcas: list[dict], lado: int = 1100) -> Image.Image:
    """La foto con un cuadro de color por cada elemento identificado. marcas: [{campo, caja, etiqueta}]."""
    with Image.open(ruta) as im:
        im = im.convert("RGB")
    im.thumbnail((lado, lado))
    w, h = im.size
    d = ImageDraw.Draw(im)
    try:
        letra = ImageFont.truetype("arial.ttf", max(12, w // 60))
    except OSError:
        letra = ImageFont.load_default()
    grosor = max(2, w // 300)
    for m in marcas:
        caja = m.get("caja")
        if not caja or len(caja) != 4:
            continue
        color = COLORES.get(m.get("campo"), COLORES["otro"])[0]
        x0, y0, x1, y1 = (int(v) for v in caja)
        if x1 <= x0 or y1 <= y0:
            continue
        r = (x0 * w // 1000, y0 * h // 1000, x1 * w // 1000, y1 * h // 1000)
        d.rectangle(r, outline=color, width=grosor)
        etiqueta = m.get("etiqueta") or COLORES.get(m.get("campo"), COLORES["otro"])[1]
        tx, ty = r[0], max(0, r[1] - letra.size - 4) if hasattr(letra, "size") else max(0, r[1] - 16)
        caja_txt = d.textbbox((tx, ty), etiqueta, font=letra)
        d.rectangle(caja_txt, fill=color)
        d.text((tx, ty), etiqueta, fill="white", font=letra)
    return im


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 3 and sys.argv[1] == "variantes":
        ruta = Path(sys.argv[2])
        for m in MEJORAS:
            mejorar(ampliar_imagen(recortar(ruta, None), 1200), m).save(ruta.with_name(f"{ruta.stem}_{m}.jpg"))
        print("hecho")
    elif len(sys.argv) >= 3 and sys.argv[1] == "leer":
        ruta = Path(sys.argv[2])
        caja = tuple(int(v) for v in sys.argv[3:7]) if len(sys.argv) >= 7 else None
        for m, bloques in leer_variantes(recortar(ruta, caja)).items():
            print(m, "→", " | ".join(f"{b['texto']} ({b['confianza']})" for b in bloques))
    else:
        sys.exit(__doc__)
