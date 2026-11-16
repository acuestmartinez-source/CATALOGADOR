"""CT-08: el corpus de los cuatro museos. Sin red: urlopen se sustituye por un doble que contesta por URL."""
import io
import json
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import museos  # noqa: E402


class _Red:
    """Doble de urllib.request.urlopen: `respuestas` es una lista de (trozo de URL, bytes o código de error)."""

    def __init__(self, respuestas):
        self.respuestas, self.pedidas = respuestas, []

    def __call__(self, pedido, timeout=None):
        self.pedidas.append(pedido)
        for trozo, resp in self.respuestas:
            if trozo in pedido.full_url:
                if isinstance(resp, int):
                    raise urllib.error.HTTPError(pedido.full_url, resp, "error", {}, io.BytesIO())
                return io.BytesIO(resp if isinstance(resp, bytes) else json.dumps(resp).encode())
        raise AssertionError(f"petición no esperada: {pedido.full_url}")


@pytest.fixture
def red(tmp_path, monkeypatch):
    monkeypatch.setattr(museos, "RAIZ", tmp_path)
    monkeypatch.setattr(museos, "DATOS", tmp_path / "datos" / "museos")
    monkeypatch.setattr(museos.time, "sleep", lambda s: None)

    def poner(respuestas):
        r = _Red(respuestas)
        monkeypatch.setattr(museos.urllib.request, "urlopen", r)
        return r
    return poner


AIC = {"pagination": {"total_pages": 1}, "data": [
    {"id": 1, "title": "Ola", "artist_title": "Hokusai", "date_display": "1831", "image_id": "abc", "is_public_domain": True},
    {"id": 2, "title": "Con derechos", "artist_title": "X", "date_display": "1950", "image_id": "def", "is_public_domain": False}]}


def test_aic_arma_la_consulta_y_filtra_lo_que_no_es_libre(red):
    r = red([("api.artic.edu", AIC)])
    assert museos.listar("aic") == 2
    url = urllib.parse.unquote_plus(r.pedidas[0].full_url)
    assert '"is_public_domain": true' in url and '"place_of_origin": "Japan"' in url and '"artwork_type_title": "Print"' in url
    assert r.pedidas[0].get_header("Aic-user-agent") == museos.AGENTE
    f1, f2 = museos.fichas("aic")
    assert f1["url_imagen"] == "https://www.artic.edu/iiif/2/abc/full/843,/0/default.jpg" and f1["licencia"] == "CC0"
    assert f2["url_imagen"] is None and f2["licencia"] == "no consta"


def test_met_usa_la_busqueda_nueva_y_mira_cada_ficha(red):
    r = red([("v1.1/search", {"total": 2, "objectIDs": [10, 11]}),
             ("objects/10", {"isPublicDomain": True, "primaryImageSmall": "https://images.metmuseum.org/web-large/a.jpg",
                             "title": "A", "artistDisplayName": "Kuniyoshi", "objectURL": "https://www.metmuseum.org/x/10"}),
             ("objects/11", {"isPublicDomain": False, "primaryImageSmall": "https://images.metmuseum.org/web-large/b.jpg"})])
    museos.listar("met")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r.pedidas[0].full_url).query)
    assert q["departmentId"] == ["6"] and q["geoLocation"] == ["Japan"] and q["q"] == ["Woodblock print"]
    assert [f["licencia"] for f in museos.fichas("met")] == ["CC0", "no consta"]
    assert museos.fichas("met")[1]["url_imagen"] is None
    # la segunda pasada no vuelve a pedir las fichas ya listadas
    r2 = red([("v1.1/search", {"total": 2, "objectIDs": [10, 11]})])
    assert museos.listar("met") == 0 and len(r2.pedidas) == 1


def _rijks_objeto(id_, licencia):
    return {"id": f"https://id.rijksmuseum.nl/{id_}", "identified_by": [
        {"type": "Name", "content": "Aap", "language": [{"id": "http://vocab.getty.edu/aat/300388256"}]},
        {"type": "Name", "content": "Monkey", "language": [{"id": "http://vocab.getty.edu/aat/300388277"}]}],
        "subject_of": [{"digitally_carried_by": [{"access_point": [{"id": "https://iiif.micr.io/zz/full/max/0/default.jpg"}],
                                                   "referred_to_by": [{"content": licencia}]}]}]}


def test_rijks_por_artista_y_solo_dominio_publico(red, monkeypatch):
    monkeypatch.setattr(museos, "ARTISTAS_RIJKS", ["Eisen"])
    r = red([("search/collection", {"orderedItems": [{"id": "https://id.rijksmuseum.nl/1"}, {"id": "https://id.rijksmuseum.nl/2"}]}),
             ("rijksmuseum.nl/1", _rijks_objeto(1, "https://creativecommons.org/publicdomain/mark/1.0/")),
             ("rijksmuseum.nl/2", _rijks_objeto(2, "https://creativecommons.org/licenses/by/4.0/"))])
    museos.listar("rijks")
    assert "creator=Eisen" in r.pedidas[0].full_url and "imageAvailable=true" in r.pedidas[0].full_url
    f1, f2 = museos.fichas("rijks")
    assert f1["titulo"] == "Monkey" and f1["url_imagen"] == "https://iiif.micr.io/zz/full/1000,/0/default.jpg"
    assert f2["url_imagen"] is None and f2["licencia"] == "no consta"


def test_cleveland_arma_la_consulta_y_filtra(red):
    web = {"web": {"url": "https://openaccess-cdn.clevelandart.org/a_web.jpg"}}
    r = red([("clevelandart.org/api", {"info": {"total": 2}, "data": [
        {"id": 5, "share_license_status": "CC0", "images": web, "creators": [{"description": "Hiroshige"}]},
        {"id": 6, "share_license_status": "Copyrighted", "images": web}]})])
    museos.listar("cleveland")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r.pedidas[0].full_url).query)
    assert q["department"] == ["Japanese Art"] and q["type"] == ["Print"] and q["cc0"] == ["1"] and q["has_image"] == ["1"]
    assert [f["url_imagen"] for f in museos.fichas("cleveland")] == ["https://openaccess-cdn.clevelandart.org/a_web.jpg", None]


def test_la_cache_no_pide_dos_veces_y_apunta_el_fichero(red):
    red([("api.artic.edu", AIC)])
    museos.listar("aic")
    r = red([("iiif/2/abc", b"JPEG1")])
    assert museos.descargar("aic") == 1 and len(r.pedidas) == 1
    assert museos.fichas("aic")[0]["fichero"] == "datos/museos/aic/img/1.jpg"
    assert (museos.DATOS / "aic" / "img" / "1.jpg").read_bytes() == b"JPEG1"
    r = red([])
    assert museos.descargar("aic") == 0 and r.pedidas == []


def test_un_429_para_la_fuente_y_no_reintenta(red):
    red([("api.artic.edu", AIC)])
    museos.listar("aic")
    r = red([("iiif/2/abc", 429)])
    with pytest.raises(museos.Parado):
        museos.descargar("aic")
    assert len(r.pedidas) == 1
    with pytest.raises(museos.Parado, match="429"):
        museos.descargar("aic")
    assert len(r.pedidas) == 1  # ni una más hasta mañana
    assert museos.estado()["aic"]["parado"]


def test_el_tope_diario_se_respeta(red, monkeypatch):
    monkeypatch.setattr(museos, "TOPE_DIA", 1)
    r = red([("api.artic.edu", AIC), ("iiif/2/abc", b"x")])
    museos.listar("aic")
    with pytest.raises(museos.Parado, match="tope"):
        museos.descargar("aic")
    assert len(r.pedidas) == 1


def test_el_tope_de_la_orden_se_respeta(red):
    datos = {"pagination": {"total_pages": 1}, "data": [
        {"id": i, "image_id": f"im{i}", "is_public_domain": True} for i in range(5)]}
    red([("api.artic.edu", datos)])
    museos.listar("aic")
    r = red([("iiif/2/", b"x")])
    assert museos.descargar("aic", tope=2) == 2 and len(r.pedidas) == 2


def test_el_agente_no_lleva_correo():
    assert "@" not in museos.AGENTE
