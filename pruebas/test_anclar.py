import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anclar  # noqa: E402

# TDP-008062: el modelo puso la firma sobre el sello del grabador (彫竹); el OCR lee 豊国画 (con un error) al lado
OCR = [{"caja": [96, 734, 139, 841], "texto": "助豆国画"}, {"caja": [54, 786, 84, 846], "texto": "彫竹"},
       {"caja": [835, 123, 872, 235], "texto": "東海道五十"}]


def test_la_firma_va_al_bloque_que_la_lee_y_se_guarda_la_del_modelo():
    fi = {"autor": {"firma": "豊国画 · Toyokuni ga", "cajas": [[40, 700, 90, 880]]}}
    anclar.anclar(fi, OCR)
    assert fi["autor"]["cajas"] == [[96, 734, 139, 841]]
    assert fi["autor"]["cajas_modelo"] == [[40, 700, 90, 880]]
    assert fi["autor"]["leido_en_hoja"] == "助豆国画"


def test_sin_coincidencia_queda_como_estaba_y_sin_comprobar():
    fi = {"serie": {"japones": "江戸名所", "cajas": [[1, 2, 3, 4]]}, "editor": {"sello": "版", "cajas": []}}
    anclar.anclar(fi, OCR)
    assert fi["serie"] == {"japones": "江戸名所", "cajas": [[1, 2, 3, 4]]}
    assert "leido_en_hoja" not in fi["editor"]  # un carácter solo no basta


def test_la_serie_casa_con_mitad_de_sus_caracteres():
    fi = {"serie": {"japones": "東海道五十三次之内", "cajas": []}}
    anclar.anclar(fi, OCR)
    assert fi["serie"]["leido_en_hoja"] == "東海道五十" and fi["serie"]["cajas"] == [[835, 123, 872, 235]]


def test_museos_solo_mira_la_cache(monkeypatch):
    monkeypatch.setattr(anclar.ukiyoe, "en_cache", lambda u: u.endswith("mfa/sc1"))
    monkeypatch.setattr(anclar.ukiyoe, "ficha", lambda u: {"ficha_original": "https://collections.mfa.org/objects/1"})
    fi = {"vinculadas": [{"url": "https://ukiyo-e.org/image/mfa/sc1"}, {"url": "https://ukiyo-e.org/image/met/2"}]}
    assert anclar.museos(fi) == {"https://ukiyo-e.org/image/mfa/sc1": "https://collections.mfa.org/objects/1"}
