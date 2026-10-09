"""Comparar nombres y años con los del Gestor."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from medir import mismo_anio, mismo_artista, mismo_editor, rango_anio  # noqa: E402


def test_artista():
    assert mismo_artista("Utagawa Kunisada (Toyokuni III)", "Utagawa Kunisada")
    assert mismo_artista("Utagawa Kunisada (Toyokuni III)", "Utagawa Toyokuni III")
    assert mismo_artista("Kitagawa Utamaro (c. 1753–1806)", "Kitagawa Utamaro")
    assert mismo_artista("Ippōsai Teiichi-ga", "Ipposai Teiichi ga")
    assert not mismo_artista("Utagawa Hiroshige", "Utagawa Hiroshige II")
    assert not mismo_artista("Utagawa Kunisada (Toyokuni III)", "Utagawa Kuniyoshi")
    assert not mismo_artista("Utagawa Kunisada", None)


def test_editor():
    assert mismo_editor("Tsutaya Kichizō", "Tsutaya")
    assert mismo_editor("Kato Seibei", "Katōya Seibei (加藤屋清兵衛)")
    assert not mismo_editor("Iseya Ichibei", "Iseya Ichiemon (伊勢屋市右衛門)")
    assert not mismo_editor("", "Tenki")


def test_anios():
    assert rango_anio(1865, None) == (1865, 1865)
    assert rango_anio(None, "1850 circa") == (1847, 1853)
    assert rango_anio(None, "sin fecha") is None
    assert mismo_anio((1865, 1865), (1867, None))
    assert not mismo_anio((1865, 1865), (1850, 1855))
    assert not mismo_anio((1865, 1865), (None, None))
