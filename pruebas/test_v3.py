"""Lo nuevo de la v3: ukiyo-e.org con educación, firmas, mejoras de imagen y recuadros."""
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import firmas  # noqa: E402
import imagen  # noqa: E402
import revision  # noqa: E402
import ukiyoe  # noqa: E402

BUSQUEDA = '''<div class="img col-xs-6 col-sm-4 col-md-3"><a href="/image/etm/0189204030" class="img"><img src="x.jpg"
alt="Japanese Print &quot;How to Master &#x27;Hauta&#x27; Songs, No. 1&quot; by Toyohara Kunichika, 豊原国周 (TOYOHARA Kunichika)"/></a>
<div class="details"><div class="wrap"><a title="Toyohara Kunichika" href="/artist/toyohara-kunichika" class="artist">Kunichika</a>
<a title="Edo Tokyo Museum" href="/source/etm" class="source">ETM</a></div></div></div>'''

FICHA = '''<div class="col-xs-12 col-md-6 imageholder"><a href="x"><img src="y" alt="Japanese Print &quot;Courtesan&quot; by Toyohara Kunichika, 豊原国周 (Kunichika)"/></a></div>
<p class="row artist"><strong class="col-xs-3 right">Artist:</strong><span class="col-xs-9"><a href="/artist/k">Toyohara Kunichika</a></span></p>
<p class="row title"><strong class="col-xs-3 right">Title:</strong><span class="col-xs-9">Courtesan of the Sanotsuchiya</span></p>
<p class="row date"><strong class="col-xs-3 right">Date:</strong><span class="col-xs-9">1862</span></p>
<p class="row details"><strong class="col-xs-3 right">Details:</strong><span class="col-xs-9"><a href="https://collections.mfa.org/objects/190207">More</a></span></p>
<p class="row source"><strong class="col-xs-3 right">Source:</strong><span class="col-xs-9"><a href="m">Museum of Fine Arts</a><br/><small><a href="/source/mfa">Browse all 37,045 prints...</a></small></span></p>
<h2>Similar Prints</h2><div class="img col-xs-6 col-sm-4 col-md-3"><a href="/image/jaodb/abc" class="img"><img alt="Japanese Print &quot;Otra&quot; by K"/></a>
<div class="details"><div class="wrap"><span class="score">87% match</span></div></div></div>
<script>images:{id:"mfa/x",description:null},similar:{description:"no es esta"}</script>'''


def test_ukiyoe_lee_busqueda_y_ficha_sin_red(monkeypatch):
    monkeypatch.setattr(ukiyoe, "_pedir", lambda ruta: BUSQUEDA if ruta.startswith("/search") else FICHA)
    r = ukiyoe.buscar("Kunichika Hauta")
    assert r == [{"id": "etm/0189204030", "url": "https://ukiyo-e.org/image/etm/0189204030",
                  "titulo": "How to Master 'Hauta' Songs, No. 1",
                  "artista": "Toyohara Kunichika, 豊原国周 (TOYOHARA Kunichika)", "fuente": "ETM"}]
    f = ukiyoe.ficha("https://ukiyo-e.org/image/mfa/sc190207")
    assert (f["id"], f["titulo"], f["fecha"], f["fuente"]) == ("mfa/sc190207", "Courtesan of the Sanotsuchiya", "1862", "Museum of Fine Arts")
    assert f["ficha_original"] == "https://collections.mfa.org/objects/190207"
    assert f["descripcion"] == ""  # la de la parecida no se cuela
    assert f["parecidas"][0]["coincidencia_pct"] == 87


def test_ukiyoe_nunca_pide_upload():
    with pytest.raises(ValueError):
        ukiyoe._pedir("/upload/abc")


def test_ukiyoe_respeta_la_parada(monkeypatch, tmp_path):
    monkeypatch.setattr(ukiyoe, "CACHE", tmp_path)
    monkeypatch.setattr(ukiyoe, "ESTADO", tmp_path / "_estado.json")
    ukiyoe._guardar({"dia": ukiyoe.date.today().isoformat(), "peticiones": 3, "ultima": 0, "parado": "429"})
    with pytest.raises(ukiyoe.Parado):
        ukiyoe._pedir("/search?q=x")


def test_firmas_une_cada_firma_con_su_nombre_y_coteja_formas_antiguas(monkeypatch):
    pagina = '''<div class="name" id="n449"><h2 class="romaji-key">Kunisada</h2><div class="dates">fl. 1807-1865</div>
<div class="kanji-key">国貞</div></div><div class="signature" style="width: 1px">
<div>1831</div><div class="sig-img-container"><img src="x"><div class="sig-kanji">香蝶樓<br>　國貞画</div></div>
<div class="sig-romaji">Kōchōrō Kunisada ga</div><div class="sig-source"><a href="https://www.loc.gov/x">LOC</a></div></div>'''
    filas = firmas.analizar(pagina)
    assert filas[0]["nombre"] == "Kunisada" and filas[0]["fecha_firma"] == "1831"
    assert filas[0]["lectura"] == "Kōchōrō Kunisada ga" and filas[0]["fuente"] == "https://www.loc.gov/x"
    monkeypatch.setattr(firmas, "_tabla", lambda: filas)
    assert firmas.buscar("香蝶楼国貞画")[0]["nombre"] == "Kunisada"  # 楼 y 国 modernos casan con 樓 y 國


def test_mejoras_devuelven_rgb_del_mismo_tamano():
    im = Image.new("RGB", (60, 40), (230, 220, 200))
    for m in imagen.MEJORAS:
        salida = imagen.mejorar(im, m)
        assert salida.size == (60, 40) and salida.mode == "RGB"
    with pytest.raises(ValueError):
        imagen.mejorar(im, "magia")


def test_recuadros_salen_de_campos_firma_y_sellos():
    ficha = {"titulo": {"cajas": [[10, 10, 50, 50]]}, "firma": {"caja": [800, 600, 900, 800]},
             "sellos": [{"tipo": "editor", "caja": [700, 700, 760, 760]}, {"tipo": "grabador", "caja": [0, 0, 0, 0]}]}
    marcas = revision.marcas_de(ficha)
    assert [(m["campo"], m["caja"]) for m in marcas] == [
        ("titulo", [10, 10, 50, 50]), ("artista", [800, 600, 900, 800]), ("editor", [700, 700, 760, 760])]


def test_verificar_fuentes_dice_de_donde_sale_cada_url():
    import agente as piloto
    ficha = {"artista": {"fuentes": ["https://www.loc.gov/item/1/", "http://museo.org/a"]},
             "serie": {"fuentes": ["https://ukiyo-e.org/image/mfa/sc1"]},
             "editor": {"fuentes": ["https://inventada.org/x", "https://..."]}}
    vistas = {"https://loc.gov/item/1": "solo buscador", "https://www.loc.gov/item/1/": "abierta",
              "https://museo.org/a": "base documentada", "https://ukiyo-e.org/image/mfa/sc1": "abierta"}
    v = piloto.verificar_fuentes(ficha, vistas)
    assert v == {"http://museo.org/a": "base documentada", "https://inventada.org/x": "nunca vista",
                 "https://ukiyo-e.org/image/mfa/sc1": "abierta", "https://www.loc.gov/item/1/": "abierta"}


def test_turno_pasa_la_peticion_tal_cual_y_repite_un_corte(monkeypatch):
    import agente as piloto

    class Flujo:
        def __init__(self, fallar):
            self.fallar = fallar
        def __enter__(self):
            if self.fallar:
                raise RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)")
            return self
        def __exit__(self, *a):
            return False
        def get_final_message(self):
            return "respuesta"

    class Mensajes:
        def __init__(self):
            self.llamadas = []
        def stream(self, **peticion):
            self.llamadas.append(peticion)
            return Flujo(len(self.llamadas) == 1)

    class Cliente:
        messages = Mensajes()

    monkeypatch.setattr(piloto.time, "sleep", lambda s: None)
    cliente = Cliente()
    assert piloto.turno(cliente, model="claude-sonnet-5-5", max_tokens=10, messages=[]) == "respuesta"
    assert [l["model"] for l in cliente.messages.llamadas] == ["claude-sonnet-5-5", "claude-sonnet-5-5"]
