"""La verificación visual (D-1845): nuestra foto frente a la imagen de la ficha de ukiyo-e.org que el agente
da por «misma estampa». Sin red: las imágenes son dibujos sintéticos y la descarga se sustituye por un doble."""
import random
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ficha as F  # noqa: E402
import ukiyoe  # noqa: E402
import visual  # noqa: E402


def _dibujo(semilla: int) -> np.ndarray:
    """Una «estampa» sintética: figuras y trazos al azar sobre papel, con bastante detalle para SIFT."""
    r = random.Random(semilla)
    im = np.full((900, 640, 3), (215, 225, 235), np.uint8)
    for _ in range(140):
        color = tuple(r.randrange(0, 200) for _ in range(3))
        x, y = r.randrange(0, 640), r.randrange(0, 900)
        if r.random() < 0.5:
            cv2.rectangle(im, (x, y), (x + r.randrange(8, 90), y + r.randrange(8, 90)), color, r.choice([-1, 2]))
        else:
            cv2.line(im, (x, y), (r.randrange(0, 640), r.randrange(0, 900)), color, r.randrange(1, 4))
    return im


def _jpeg(im: np.ndarray) -> bytes:
    return cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def _otra_foto_de(im: np.ndarray) -> np.ndarray:
    """La misma estampa fotografiada de otra manera: más pequeña, algo girada y con otros colores."""
    h, w = im.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 3, 0.75)
    girada = cv2.warpAffine(im, m, (w, h), borderValue=(240, 240, 240))
    return cv2.convertScaleAbs(girada, alpha=0.85, beta=25)


def test_la_misma_estampa_encaja_y_otra_no():
    a = _dibujo(1)
    misma = visual.coincidencia(_jpeg(a), _jpeg(_otra_foto_de(a)))
    otra = visual.coincidencia(_jpeg(a), _jpeg(_dibujo(2)))
    assert misma["veredicto"] == "misma" and misma["puntos"] >= visual.UMBRAL_MISMA, misma
    assert otra["veredicto"] == "no" and otra["puntos"] < visual.UMBRAL_DUDOSA, otra


def _ficha(id_):
    return {"autor": {"nombre": "Utagawa Hiroshige II", "nivel": "ukiyo-e.org misma estampa", "confianza": "alta",
                      "fuentes": [f"https://ukiyo-e.org/image/{id_}"]},
            "serie": {"romaji": "Edo meisho zue", "nivel": "ukiyo-e.org misma estampa", "confianza": "alta",
                      "fuentes": [f"https://ukiyo-e.org/image/{id_}", "https://www.mfa.org/x"]},
            "titulo": {"castellano": "Sekiya", "nivel": "museo misma estampa", "confianza": "alta"}}


def test_una_misma_estampa_que_no_encaja_baja_de_nivel(tmp_path, monkeypatch):
    nuestra = tmp_path / "foto.jpg"
    nuestra.write_bytes(_jpeg(_dibujo(1)))
    monkeypatch.setattr(visual, "imagen_ukiyoe", lambda id_: _jpeg(_dibujo(7)))  # otra hoja
    ficha, informe = visual.verificar(_ficha("mfa/sc1"), nuestra)
    assert informe == {"mfa/sc1": {"puntos": informe["mfa/sc1"]["puntos"], "veredicto": "no"}}
    assert F.nivel(ficha, "autor") == "otra lámina documentada" and F.nivel(ficha, "serie") == "otra lámina documentada"
    assert F.fiabilidad(ficha, "autor") == "media"
    assert "no encaja" in ficha["autor"]["como"]
    assert F.nivel(ficha, "titulo") == "museo misma estampa"  # sin imagen de ukiyo-e.org, no se puede comprobar


def test_una_misma_estampa_que_encaja_se_queda_y_lleva_su_segunda_senal(tmp_path, monkeypatch):
    a = _dibujo(1)
    nuestra = tmp_path / "foto.jpg"
    nuestra.write_bytes(_jpeg(a))
    monkeypatch.setattr(visual, "imagen_ukiyoe", lambda id_: _jpeg(_otra_foto_de(a)))
    ficha, informe = visual.verificar(_ficha("mfa/sc1"), nuestra)
    assert informe["mfa/sc1"]["veredicto"] == "misma"
    assert F.nivel(ficha, "autor") == "ukiyo-e.org misma estampa" and ficha["autor"]["segunda_senal"] == "visual"


def test_si_ukiyoe_no_contesta_no_se_toca_nada(tmp_path, monkeypatch):
    nuestra = tmp_path / "foto.jpg"
    nuestra.write_bytes(_jpeg(_dibujo(1)))

    def parado(id_):
        raise ukiyoe.Parado("tope del día")

    monkeypatch.setattr(visual, "imagen_ukiyoe", parado)
    original = _ficha("mfa/sc1")
    ficha, informe = visual.verificar(original, nuestra)
    assert informe["mfa/sc1"]["veredicto"] == "sin comprobar"
    assert F.nivel(ficha, "autor") == "ukiyo-e.org misma estampa" and "segunda_senal" not in ficha["autor"]


def test_sin_ficha_o_sin_foto_no_pasa_nada(tmp_path):
    assert visual.verificar(None, tmp_path / "no.jpg") == (None, {})
    ficha = {"autor": {"nombre": "X", "nivel": "lectura cotejada"}}
    assert visual.verificar(ficha, tmp_path / "no.jpg") == (ficha, {})


def test_catalogar_aplica_la_verificacion_antes_de_lo_publicable(tmp_path, monkeypatch):
    # de punta a punta con un doble de la API: lo que se publica ya lleva el nivel corregido
    import agente
    from test_hermanas import OBRA, _final
    from test_paso_2 import _Cliente

    foto = tmp_path / "01.jpg"
    foto.write_bytes(_jpeg(_dibujo(1)))
    monkeypatch.setattr(agente, "ocr_ndl", lambda f: [])
    monkeypatch.setattr(visual, "imagen_ukiyoe", lambda id_: _jpeg(_dibujo(7)))
    r = agente.catalogar(_Cliente([_final(_ficha("mfa/sc1"))]), OBRA, [foto])
    assert r["verificacion_visual"]["mfa/sc1"]["veredicto"] == "no"
    assert r["para_web"]["autor_fiabilidad"] == "media" and F.nivel(r["ficha"], "autor") == "otra lámina documentada"
