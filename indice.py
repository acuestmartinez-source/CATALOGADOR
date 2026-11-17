"""CT-08: búsqueda por imagen propia, contra las estampas de dominio público bajadas por museos.py.

  python indice.py construir          añade al índice las imágenes nuevas de datos/museos/
  python indice.py buscar <foto>      las más parecidas, con la comprobación geométrica de visual.py

DINOv2-small (ONNX, CPU) da un vector por imagen y el coseno ordena; luego SIFT + RANSAC (D-1845) dice
«misma», «dudosa» o «no» con los mismos umbrales que ya usa el catalogador. Nada sale de este PC.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import visual

RAIZ = Path(os.environ.get("TDP_INDICE") or Path(__file__).resolve().parent)  # en el NAS, la carpeta montada
MODELO = RAIZ / "datos" / "modelos" / "dinov2-small" / "model.onnx"
CARPETA = RAIZ / "datos" / "indice"
VECTORES, FICHAS = CARPETA / "vectores.npy", CARPETA / "fichas.jsonl"
MEDIA, DESV = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)
UMBRAL_DUDOSA = 100  # medido el 17/11: las estampas distintas de los museos llegan a 87 puntos, las mismas pasan de 200
_sesion = None


def _modelo():
    global _sesion
    if _sesion is None:
        import onnxruntime
        _sesion = onnxruntime.InferenceSession(str(MODELO), providers=["CPUExecutionProvider"])
    return _sesion


def _pixeles(im: Image.Image) -> np.ndarray:
    # la estampa entera, sin recortar el centro: una hoja vertical perdería la firma y el cartucho
    a = np.asarray(im.convert("RGB").resize((224, 224), Image.BICUBIC), np.float32) / 255
    return ((a - MEDIA) / DESV).transpose(2, 0, 1)


def vectores(imagenes: list[Image.Image]) -> np.ndarray:
    """CLS y media de los parches, juntos y normalizados: el coseno es el producto escalar."""
    h = _modelo().run(None, {"pixel_values": np.stack([_pixeles(i) for i in imagenes])})[0]
    v = np.concatenate([h[:, 0], h[:, 1:].mean(1)], axis=1)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _cargar() -> tuple[np.ndarray, list[dict]]:
    if not VECTORES.exists():
        return np.zeros((0, 768), np.float32), []
    fichas = [json.loads(x) for x in FICHAS.read_text(encoding="utf-8").splitlines() if x.strip()]
    return np.load(VECTORES), fichas


def construir(lote: int = 32) -> int:
    v, fichas = _cargar()
    ya = {f["fichero"] for f in fichas}
    nuevas = []
    for f in sorted((RAIZ / "datos" / "museos").glob("*/fichas.jsonl")):
        for linea in f.read_text(encoding="utf-8").splitlines():
            d = json.loads(linea) if linea.strip() else {}
            if d.get("fichero") and d["fichero"] not in ya and (RAIZ / d["fichero"]).exists():
                nuevas.append({k: d.get(k) for k in ("fuente", "id", "titulo", "artista", "fecha", "url_ficha", "licencia", "fichero")})
                ya.add(d["fichero"])
    partes, buenas = [v], []
    for i in range(0, len(nuevas), lote):
        trozo, ims = [], []
        for d in nuevas[i:i + lote]:
            try:
                ims.append(Image.open(RAIZ / d["fichero"]))
                trozo.append(d)
            except OSError:  # una imagen rota no para el índice
                continue
        if ims:
            partes.append(vectores(ims))
            buenas += trozo
        print(f"{min(i + lote, len(nuevas))}/{len(nuevas)}", flush=True)
    CARPETA.mkdir(parents=True, exist_ok=True)
    np.save(VECTORES, np.concatenate(partes).astype(np.float32))
    FICHAS.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in fichas + buenas), encoding="utf-8")
    return len(buenas)


def buscar(foto: Path, k: int = 5, indice=None) -> list[dict]:
    """Las k más parecidas, de mejor a peor veredicto y luego por parecido."""
    v, fichas = indice or _cargar()
    if not len(fichas):
        return []
    q = vectores([Image.open(foto)])[0]
    parecido = v @ q
    nuestra = Path(foto).read_bytes()
    salida = []
    for i in np.argsort(-parecido)[:k]:
        d = dict(fichas[i], parecido=round(float(parecido[i]), 3))
        d.update(visual.coincidencia(nuestra, (RAIZ / d["fichero"]).read_bytes()))
        if d["veredicto"] == "dudosa" and d["puntos"] < UMBRAL_DUDOSA:
            d["veredicto"] = "no"
        salida.append(d)
    orden = {"misma": 0, "dudosa": 1, "no": 2}
    return sorted(salida, key=lambda d: (orden[d["veredicto"]], -d["parecido"]))


def parecidas(foto: Path, k: int = 5) -> list[dict]:
    """Para la salida de cada obra: solo «misma» y «dudosa». Sin índice o con un fallo, nada: no tumba la obra."""
    try:
        return [{c: d.get(c) for c in ("fuente", "titulo", "artista", "fecha", "url_ficha", "licencia", "veredicto",
                                       "puntos", "parecido")} for d in buscar(foto, k) if d["veredicto"] != "no"]
    except Exception:  # noqa: BLE001
        return []


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["construir"]:
        print(construir(), "imágenes nuevas en el índice")
    elif len(sys.argv) == 3 and sys.argv[1] == "buscar":
        print(json.dumps(buscar(Path(sys.argv[2])), ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)
