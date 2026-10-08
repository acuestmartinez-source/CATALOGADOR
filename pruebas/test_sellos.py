"""La tabla de sellos de editor: el analizador de la página y la búsqueda por caracteres."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sellos  # noqa: E402

PAGINA = '''
<div class="name" id="n96">
<div class="place edo"><span class="place-label">Edo/Tōkyō</span></div>
<h2 class="romaji-key">Ōmiya Kyūjirō</h2>
<div class="kanji-key">近江屋久次郎</div>
</div><div class="name"><div class="signature" style="width: 146px" data-shape="25" data-char-cnt="2" data-pub-id="96">
<div class="dates">1855</div>
<div class="sig-romaji">近久</div><div class="sig-romaji">Kinkyū</div>
<div class="sig-source"><a href="http://archive.waseda.jp/x?a=1&amp;b=2" target="_blank">Waseda</a></div>
</div></div>
<div class="name" id="n396">
<div class="place edo"><span class="place-label">Edo/Tōkyō</span></div>
<h2 class="romaji-key">Echizenya Kajū</h2>
<div class="kanji-key">越前屋嘉十</div>
</div><div class="name"><div class="signature" data-shape="21" data-char-cnt="2" data-pub-id="396">
<div class="dates">1860-1861</div>
<div class="sig-romaji">越嘉</div><div class="sig-romaji">Etsuka</div>
</div></div>
'''


def test_analizar_une_cada_sello_con_su_editor():
    filas = sellos.analizar(PAGINA)
    assert [(f["editor"], f["sello"], f["forma"]) for f in filas] == [
        ("Ōmiya Kyūjirō", "近久", 25), ("Echizenya Kajū", "越嘉", 21)]
    assert filas[0]["editor_kanji"] == "近江屋久次郎"
    assert filas[0]["fuente"] == "http://archive.waseda.jp/x?a=1&b=2"
    assert filas[0]["forma_nombre"] == "texto vertical (una línea)"


def test_buscar_por_caracteres_romaji_e_ilegibles(monkeypatch):
    monkeypatch.setattr(sellos, "_tabla", lambda: sellos.analizar(PAGINA))
    assert sellos.buscar("近久")[0]["editor"] == "Ōmiya Kyūjirō"
    assert sellos.buscar("越□")[0]["editor"] == "Echizenya Kajū"
    assert sellos.buscar("Echizenya")[0]["sello"] == "越嘉"
    assert sellos.buscar("丸清") == []
