"""Para todas las pruebas: el índice del taller y la caché de las fuentes abiertas van a una carpeta
temporal. Sin esto, el servicio de las pruebas escribiría en `datos/` del repositorio, y una prueba
podría salir a internet."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import indice  # noqa: E402
import museos  # noqa: E402


@pytest.fixture(autouse=True)
def _datos_en_temporal(tmp_path, monkeypatch):
    carpeta = tmp_path / "datos_indice"
    monkeypatch.setattr(indice, "CARPETA", carpeta)
    monkeypatch.setattr(indice, "ENTRADAS", carpeta / "entradas.jsonl")
    monkeypatch.setattr(indice, "ESTADOS", carpeta / "estados.jsonl")
    monkeypatch.setattr(indice, "RECORTES", carpeta / "recortes")
    monkeypatch.setattr(indice, "DESCRIPTORES", carpeta / "descriptores")
    indice._formas.cache_clear()
    monkeypatch.setattr(museos, "CACHE", tmp_path / "museos_cache")
    monkeypatch.setattr(museos, "ESTADO", tmp_path / "museos_cache" / "_estado.json")
    monkeypatch.setattr(museos, "ESPERA_MIN", 0.0)
    monkeypatch.setattr(museos, "ESPERA_MAX", 0.0)

    def sin_red(*a, **kw):  # ninguna prueba sale a internet: la que lo necesite pone su doble
        raise AssertionError("una prueba ha intentado salir a internet por museos.py")

    monkeypatch.setattr(museos.urllib.request, "urlopen", sin_red)
    yield
    indice._formas.cache_clear()
