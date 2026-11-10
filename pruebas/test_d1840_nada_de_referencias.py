"""D-1840: hacia la API no sale ninguna referencia (ni TDP-, ni idn-, ni el grupo idn-g-) ni nada más de la
petición. Sale la foto, las medidas y, si una persona la escribió, la serie conocida (D-991 del Gestor, que es
una excepción cerrada). Sin API: el cliente doble guarda todo lo que se le pasa a `messages.stream`."""
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agente  # noqa: E402
import catalogador  # noqa: E402
import ficha as F  # noqa: E402
import servicio  # noqa: E402
from test_hermanas import CONTRADICCIONES, CORTA, PRIMERA, _final  # noqa: E402
from test_paso_2 import CATALOGAR_DE_VERDAD, _Cliente  # noqa: E402
from test_servicio import _montar  # noqa: E402

REFERENCIAS = re.compile(r"TDP-\d{6}|idn-\d{6}|idn-g-")
#: Una memoria de series como la del disco: la serie que lee el OCR doble, ya catalogada en dos obras.
MEMORIA = [{**F.hermana_de(PRIMERA, "TDP-007001"), "obras": ["TDP-007001", "TDP-007002"]}]
OCR = [{"caja": [0, 0, 1, 1], "texto": "葉うた虎之巻", "confianza": 0.7}]


def _sin_nada_de_la_peticion(cliente, inter=None):
    """Sobre TODO lo enviado (sistema, mensajes, herramientas y el resto de argumentos; la foto en base64 no
    tiene guiones): ninguna referencia y, de la petición, ni la fecha, ni los nombres de las fotos, ni las notas."""
    texto = json.dumps(cliente.enviadas, ensure_ascii=False, default=str)
    prohibido = REFERENCIAS.findall(texto)
    for p in servicio.leer_jsonl(inter / "para_catalogador" / "cola.jsonl") if inter else []:
        prohibido += [x for x in (p["pedido_en"], *(Path(r).name for r in p["imagenes"]),
                                  *(q.get("nota") or "" for q in p.get("pistas") or [])) if x and x in texto]
    assert cliente.enviadas and not prohibido, " | ".join(prohibido)


@pytest.mark.parametrize("corta, llamadas", [(PRIMERA, 2), (CONTRADICCIONES["autor"], 3)],
                         ids=["hermana_corta", "repetida_completa"])
def test_el_servicio_no_manda_referencias_ni_nada_de_la_peticion(tmp_path, monkeypatch, corta, llamadas):
    # (a) la primera, completa y con la memoria de series; (b) la hermana corta (D-1798); (c) la misma hermana
    # repetida completa tras una contradicción (D-1799), con la memoria que ya lleva la primera hoja.
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.MEMORIA.write_text(json.dumps(MEMORIA, ensure_ascii=False), encoding="utf-8")
    cliente = _Cliente([_final(PRIMERA), _final(corta), _final(PRIMERA)])
    monkeypatch.setattr(agente, "catalogar", CATALOGAR_DE_VERDAD)
    monkeypatch.setattr(agente, "cliente", lambda: cliente)
    servicio.Servicio(inter, imagenes).vuelta()
    assert len(cliente.enviadas) == llamadas
    textos = [b.get("text", "") for p in cliente.enviadas for b in p["messages"][0]["content"]]
    assert sum("ya catalogada en" in t for t in textos) >= llamadas and any(CORTA in t for t in textos)
    _sin_nada_de_la_peticion(cliente, inter)
    # la memoria del disco es local y no sale: sigue apuntando las obras
    assert {"TDP-007001", "TDP-008194"} <= set(json.loads(servicio.MEMORIA.read_text(encoding="utf-8"))[0]["obras"])


def test_la_orden_catalogar_tampoco_manda_las_obras_de_la_memoria(tmp_path, monkeypatch):
    # (d) la medición ciega: también usa series_en_texto y texto_memoria
    memoria = tmp_path / "series.json"
    memoria.write_text(json.dumps(MEMORIA, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(catalogador, "MEMORIA", memoria)
    monkeypatch.setattr(agente, "ocr_ndl", lambda foto: OCR)
    foto = tmp_path / "TDP-008133_01.jpg"
    Image.new("RGB", (60, 80), (230, 220, 200)).save(foto)
    cliente = _Cliente([_final(PRIMERA)])
    o = {"referencia": "TDP-008133", "destino": tmp_path / "TDP-008133.json", "fotos": [foto],
         "gestor": {"alto_cm": 35.2, "ancho_cm": 24.1, "tienda": {}}}
    args = SimpleNamespace(modelo=agente.MODELO_POR_DEFECTO, sin_web=False, esfuerzo=agente.ESFUERZO)
    assert catalogador.catalogar_una(cliente, o, args, {}) > 0
    assert "ya catalogada en" in json.dumps(cliente.enviadas, ensure_ascii=False, default=str)
    _sin_nada_de_la_peticion(cliente)
