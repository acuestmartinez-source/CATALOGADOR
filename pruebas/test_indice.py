import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import indice  # noqa: E402


def test_construir_salta_las_rotas_y_no_repite(tmp_path, monkeypatch):
    monkeypatch.setattr(indice, "RAIZ", tmp_path)
    monkeypatch.setattr(indice, "VECTORES", tmp_path / "v.npy")
    monkeypatch.setattr(indice, "FICHAS", tmp_path / "f.jsonl")
    monkeypatch.setattr(indice, "CARPETA", tmp_path)
    monkeypatch.setattr(indice, "vectores", lambda ims: np.ones((len(ims), 768), np.float32))
    img = tmp_path / "datos" / "museos" / "met" / "img"
    img.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(img / "1.jpg")
    (img / "2.jpg").write_bytes(b"rota")
    lineas = [json.dumps({"fuente": "met", "id": n, "fichero": f"datos/museos/met/img/{n}.jpg"}) for n in ("1", "2", "3")]
    (img.parent / "fichas.jsonl").write_text("\n".join(lineas), encoding="utf-8")  # la 3 no se bajó
    assert indice.construir() == 1
    assert indice.construir() == 0
    v, fichas = indice._cargar()
    assert len(v) == len(fichas) == 1


def test_buscar_pone_primero_la_misma_y_baja_las_dudosas_flojas(monkeypatch):
    v = np.eye(3, dtype=np.float32)
    fichas = [{"fichero": "a"}, {"fichero": "b"}, {"fichero": "c"}]
    monkeypatch.setattr(indice, "vectores", lambda ims: np.array([[0.9, 0.5, 0.1]], np.float32))
    monkeypatch.setattr(indice.Image, "open", lambda p: None)
    monkeypatch.setattr(Path, "read_bytes", lambda self: self.name.encode())
    puntos = {"a": 70, "b": 220, "c": 120}
    monkeypatch.setattr(indice.visual, "coincidencia", lambda n, s: {
        "puntos": puntos[s.decode()], "veredicto": indice.visual.veredicto(puntos[s.decode()])})
    r = indice.buscar(Path("foto.jpg"), k=3, indice=(v, fichas))
    assert [(x["fichero"], x["veredicto"]) for x in r] == [("b", "misma"), ("c", "dudosa"), ("a", "no")]


def test_parecidas_solo_da_misma_y_dudosa_y_nunca_tumba_la_obra(monkeypatch):
    monkeypatch.setattr(indice, "buscar", lambda f, k: [{"veredicto": "misma", "titulo": "A"}, {"veredicto": "no"}])
    assert [d["titulo"] for d in indice.parecidas(Path("x"))] == ["A"]
    monkeypatch.setattr(indice, "buscar", lambda f, k: 1 / 0)
    assert indice.parecidas(Path("x")) == []
