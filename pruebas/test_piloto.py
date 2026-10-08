"""La comparación con la ficha del Gestor: nombres normalizados y rangos de años."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from piloto import extraer_json, mismo_anio, mismo_artista, mismo_editor, rango_anio  # noqa: E402


def test_artista_igual_con_o_sin_parentesis_y_acentos():
    assert mismo_artista("Utagawa Kunisada (Toyokuni III)", "Utagawa Kunisada")
    assert mismo_artista("Utagawa Kunisada (Toyokuni III)", "Utagawa Toyokuni III")
    assert mismo_artista("Utagawa Hiroshige", "Hiroshige")
    assert mismo_artista("Kitagawa Utamaro (c. 1753–1806)", "Kitagawa Utamaro")
    assert mismo_artista("Tsukioka Yoshitoshi", "Yoshitoshi Tsukioka")
    assert mismo_artista("Ippōsai Teiichi-ga", "Ipposai Teiichi ga")


def test_artista_distinto_por_generacion_o_nombre():
    assert not mismo_artista("Utagawa Hiroshige", "Utagawa Hiroshige II")
    assert not mismo_artista("Utagawa Hiroshige II", "Utagawa Hiroshige")
    assert not mismo_artista("Utagawa Kunisada (Toyokuni III)", "Utagawa Kuniyoshi")
    assert not mismo_artista("Utagawa Kunisada", None)
    assert not mismo_artista(None, "Utagawa Kunisada")


def test_editor_contenido():
    assert mismo_editor("Tsutaya Kichizō", "Tsutaya")
    assert mismo_editor("Tenki", "Tenki (Yamamoto Heikichi)")
    assert not mismo_editor("Tenki", "Ebisuya")
    assert not mismo_editor("", "Tenki")


def test_rango_anio_del_gestor():
    assert rango_anio(1865, None) == (1865, 1865)
    assert rango_anio(None, "1820-1845") == (1820, 1845)
    assert rango_anio(None, "1850 circa") == (1847, 1853)
    assert rango_anio(None, "sin fecha") is None


def test_mismo_anio_con_tolerancia():
    assert mismo_anio((1865, 1865), (1865, 1865))
    assert mismo_anio((1865, 1865), (1867, None))
    assert mismo_anio((1820, 1845), (1830, 1831))
    assert not mismo_anio((1865, 1865), (1850, 1855))
    assert not mismo_anio(None, (1865, 1865))
    assert not mismo_anio((1865, 1865), (None, None))


def test_extraer_json_coge_el_ultimo_bloque_valido():
    texto = 'Pienso...\n```json\n{"a": 1}\n```\nY la ficha:\n```json\n{"artista": {"nombre": "X"}}\n```\n'
    assert extraer_json(texto) == {"artista": {"nombre": "X"}}
    assert extraer_json("sin bloque") is None
