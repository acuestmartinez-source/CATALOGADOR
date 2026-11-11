"""Fuentes abiertas, ejemplar de referencia, cuadros de texto, tirada, índice del taller y series juntas
(docs/11). Sin API ni red: las fuentes y el OCR son dobles."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agente  # noqa: E402
import censor  # noqa: E402
import ficha as F  # noqa: E402
import indice  # noqa: E402
import museos  # noqa: E402
import series  # noqa: E402
import servicio  # noqa: E402
import ukiyoe  # noqa: E402

# La ficha de una hoja de «Edo meishō zue» como la del NAS: sin sellos a la vista, fechada por una ficha.
SIN_SELLOS = {
    "tipo_obra": "estampa suelta",
    "autor": {"nombre": "Utagawa Hiroshige II", "firma": "広重画", "nivel": "lectura cotejada", "confianza": "alta",
              "cajas": [[80, 740, 190, 890]]},
    "titulo": {"castellano": "El templo Sensō-ji", "nivel": "museo misma estampa", "confianza": "media", "cajas": [[105, 110, 435, 225]]},
    "serie": {"castellano": "Vistas de lugares famosos de Edo", "japones": "江戸名勝圖會", "romaji": "Edo meishō zue",
              "nivel": "museo misma estampa", "confianza": "alta", "cajas": [[850, 85, 900, 262]]},
    "editor": {"nombre": "Fujiokaya Keijirō", "sello": "藤慶 (no visible en la foto)", "sello_visible": False,
               "nivel": "museo misma estampa", "confianza": "media", "cajas": []},
    "censor": {"sello": None, "lectura": None, "sello_visible": False, "fecha_desde": 1861, "fecha_hasta": 1862,
               "nivel": "museo misma estampa", "confianza": "media", "cajas": []},
    "tecnica": {"nombre": "Xilografía en color (nishiki-e)", "formato": "ōban tate-e", "confianza": "alta"},
    "textos": [{"tipo": "cartucho_serie", "lectura": "江戸名勝圖會", "romaji": "Edo meishō zue",
                "castellano": "Vistas de lugares famosos de Edo", "caja": [850, 85, 900, 262]},
               {"tipo": "firma", "lectura": "広重画", "romaji": "Hiroshige ga", "castellano": "pintado por Hiroshige",
                "caja": [80, 740, 190, 890]}],
    "edicion": {"estado": "edición de época", "indicios": ["la referencia lleva el sello de fecha en el margen izquierdo, que falta"],
                "referencia_comparada": "https://jpsearch.go.jp/item/arc_nishikie-X", "como": "Misma composición."},
    "vinculadas": [], "buscar_mas": [],
}


def _foto(ruta: Path, texto: str = "江戸", color=(200, 60, 50)) -> Path:
    """Una foto de mentira con un «cartucho» (un rectángulo de color con trazos negros) arriba a la derecha."""
    im = Image.new("RGB", (600, 800), (235, 225, 205))
    d = ImageDraw.Draw(im)
    d.rectangle((510, 68, 540, 210), fill=color)
    for i, _ in enumerate(texto * 3):
        d.line((515, 80 + i * 20, 535, 90 + i * 20), fill=(20, 20, 20), width=3)
        d.line((525, 78 + i * 20, 520, 95 + i * 20), fill=(20, 20, 20), width=2)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    im.save(ruta, quality=92)
    return ruta


# ---------------------------------------------------------------- censores

def test_la_pareja_de_censores_y_el_sello_solo_afinan_los_anos():
    assert censor.datar("dos_censores", None, None, ["村", "衣笠"])["anos"] == [1851, 1852]      # Murata + Kinugasa, 1851-53
    assert censor.datar("dos_censores", None, None, ["浜", "馬込"])["anos"] == [1849, 1850, 1851, 1852]
    assert censor.datar("dos_censores", None, None, ["濱", "衣笠"])["anos"] == [1847, 1848]      # 濱 es 浜
    assert censor.datar("dos_censores_fecha", "子", 5, ["米良", "渡辺"])["anos"] == [1852]
    assert censor.datar("un_censor", None, None, ["村田"])["anos"] == [1846]
    assert censor.datar("un_censor", None, None, ["村"])["anos"] == [1843, 1844, 1845]
    assert "Illing" in censor.datar("un_censor", None, None, ["村"])["nota"]
    # una pareja que no está en la tabla no afina, y dos que no caben en el tipo de sello lo dicen
    assert censor.datar("dos_censores", None, None, ["村松", "米良"])["anos"] == list(range(1847, 1853))
    assert "revisa la lectura" in censor.datar("un_censor", None, None, ["衣笠"])["nota"] or \
        censor.datar("un_censor", None, None, ["衣笠"])["anos"] == [1845, 1846]


def test_cuando_se_espera_sello_de_censura():
    assert censor.sello_esperado(1861, 1862) and censor.sello_esperado(None, 1800) and censor.sello_esperado(1870, 1880)
    assert not censor.sello_esperado(1880, 1890) and not censor.sello_esperado(1700, 1780)
    assert not censor.sello_esperado(None, None) and not censor.sello_esperado("1861", True)


# ---------------------------------------------------------------- cuadros de texto y tirada

def test_los_cuadros_de_texto_juntan_los_del_modelo_y_lo_que_el_ocr_leyo_de_mas():
    ocr = [{"caja": [105, 110, 435, 225], "texto": "浅草寺 宮戸川より", "confianza": 0.8},   # tapado por la caja del título
           {"caja": [852, 90, 898, 260], "texto": "江戸名勝圖會"},                          # tapado por el cartucho
           {"caja": [300, 600, 380, 700], "texto": "彫兼"},                                 # nadie lo recogió: entra
           {"caja": [1, 1, 20, 20], "texto": "□□□"}, {"caja": [5, 5, 3, 9], "texto": "国"}, {"caja": [1, 1, 9, 9], "texto": "abc"}]
    t = F.textos({**SIN_SELLOS, "textos": SIN_SELLOS["textos"] + [
        {"tipo": "magia", "lectura": "村", "caja": [10, 10, 30, 30]},                      # tipo desconocido: «otro»
        {"tipo": "firma", "lectura": "x", "caja": [0, 0, 5000, 3]}, {"tipo": "firma", "lectura": "", "caja": [1, 1, 5, 5]},
        "no soy un cuadro"]}, ocr)
    assert [x["n"] for x in t] == [1, 2, 3, 4]
    assert [(x["tipo"], x["origen"]) for x in t] == [("cartucho_serie", "modelo"), ("firma", "modelo"), ("otro", "modelo"), ("otro", "ocr")]
    assert t[3]["lectura"] == "彫兼" and t[0]["castellano"] == "Vistas de lugares famosos de Edo"
    assert F.textos(None) == [] and F.textos({"textos": "no"}, [{"caja": None}]) == []
    muchos = {"textos": [{"tipo": "poema", "lectura": "山" * 500, "caja": [i, i, i + 5, i + 5]} for i in range(0, 300, 10)]}
    assert len(F.textos(muchos)) == F.MAX_TEXTOS and len(F.textos(muchos)[0]["lectura"]) == 160
    assert F.textos({"textos": [{"tipo": "firma", "lectura": "国\x00貞‮", "caja": [1, 1, 9, 9]}]})[0]["lectura"] == "国貞"


def test_la_tirada_avisa_si_falta_el_sello_que_se_esperaba_y_no_depende_del_modelo():
    e = F.edicion(SIN_SELLOS)
    assert e["estado"] == "edición de época" and e["revisar"] and len(e["avisos"]) == 2
    assert "sello de censura" in e["avisos"][0] and "editor" in e["avisos"][1] and e["indicios"]
    assert F.resumen_edicion(e).startswith("AVISO de tirada: edición de época; no se ve el sello de censura")
    # con los sellos a la vista no hay aviso, diga lo que diga la fecha
    con = {**SIN_SELLOS, "censor": {**SIN_SELLOS["censor"], "sello_visible": True}, "editor": {**SIN_SELLOS["editor"], "sello_visible": True}}
    assert F.edicion(con)["avisos"] == [] and not F.edicion(con)["revisar"] and F.resumen_edicion(F.edicion(con)) is None
    # una página de libro o un surimono no pasaban por la censura; una estampa de 1890, tampoco
    assert F.edicion({**SIN_SELLOS, "tipo_obra": "página de libro"})["avisos"] == []
    tarde = {**SIN_SELLOS, "censor": {**SIN_SELLOS["censor"], "fecha_desde": 1885, "fecha_hasta": 1890}}
    assert F.edicion(tarde)["avisos"] == ["no se ve el sello del editor"]
    # sin fecha ni sello, se dice; un estado inventado no pasa; el del modelo «posterior» pide revisión aunque no haya aviso
    assert "ni fecha" in F.edicion({"tipo_obra": "estampa suelta", "editor": {"sello_visible": True}})["avisos"][0]
    assert F.edicion({"edicion": {"estado": "falsa", "indicios": "no"}})["estado"] == "sin determinar"
    assert F.edicion({**con, "edicion": {"estado": "reproducción moderna"}})["revisar"]
    # las fichas de antes no traen sello_visible: se deduce de la caja o de la lectura
    assert F.sello_visible({"censor": {"lectura": "改 丑二", "cajas": []}}, "censor")
    assert F.sello_visible({"censor": {"cajas": [[1, 1, 9, 9]]}}, "censor")
    assert not F.sello_visible({"censor": {"lectura": "sin sello visible", "cajas": []}}, "censor")
    assert not F.sello_visible({"editor": {"sello": "藤慶 · Fujikei (no visible en la foto)", "cajas": []}}, "editor")


def test_la_ficha_del_intercambio_lleva_los_cuadros_la_tirada_y_el_aviso_en_el_detalle_del_censor():
    r = {"ficha": SIN_SELLOS, "modelo": "doble", "fases": "A", "coste_eur": 0.2, "ocr": [{"caja": [300, 600, 380, 700], "texto": "彫兼"}]}
    linea = servicio.ficha_de_intercambio({"id_peticion": "idn-000001", "referencia": "TDP-008198"}, r)
    assert [t["n"] for t in linea["textos"]] == [1, 2, 3] and linea["textos"][2]["origen"] == "ocr"
    assert linea["edicion"]["revisar"] and linea["anotada_textos"] is None
    assert linea["datos"]["censor"]["detalle"].startswith("AVISO de tirada:") and linea["datos"]["censor"]["lectura"] is None
    assert len(linea["datos"]["censor"]["detalle"]) < 500  # el tope de un texto en el Gestor
    json.dumps(linea, ensure_ascii=True)
    # y la foto con los cuadros numerados
    carpeta = Path(servicio.RAIZ)  # no se escribe ahí: se da otra
    assert carpeta


def test_la_foto_de_los_cuadros_de_texto_se_dibuja(tmp_path):
    foto = _foto(tmp_path / "f.jpg")
    linea = servicio.ficha_de_intercambio({"id_peticion": "idn-000001", "referencia": "TDP-008198"}, {"ficha": SIN_SELLOS})
    ruta = servicio.anotar_textos(foto, linea, tmp_path / "anotadas")
    assert ruta == "anotadas/idn-000001_textos.jpg" and (tmp_path / ruta).read_bytes().startswith(b"\xff\xd8")
    assert servicio.anotar_textos(foto, {**linea, "textos": []}, tmp_path / "anotadas") is None


# ---------------------------------------------------------------- el índice del taller

def test_el_indice_guarda_los_cuadros_de_una_propuesta_y_los_encuentra_por_lo_que_dicen(tmp_path):
    foto = _foto(tmp_path / "a.jpg")
    linea = servicio.ficha_de_intercambio({"id_peticion": "idn-000001", "referencia": "TDP-008198"}, {"ficha": SIN_SELLOS})
    assert indice.desde_ficha(linea, foto) == 3      # firma, cartucho de serie y cartucho de título
    assert indice.desde_ficha(linea, foto) == 0      # repetir no duplica
    assert indice.resumen() == {"entradas": 3, "confirmadas": 0, "por_tipo": {"firma": 1, "cartucho_serie": 1, "cartucho_titulo": 1}, "obras": 1}
    # 圖會 y 図会 son lo mismo; se encuentra aunque falte un carácter
    (fila,) = indice.buscar("cartucho_serie", "江戸名勝図会")
    assert fila["dice_parecido"] == 1.0 and fila["hojas"] == 1 and not fila["confirmada"] and fila["nombre"] == "Edo meishô zue"
    assert indice.buscar("cartucho_serie", "江戸名□図会")[0]["dice_parecido"] >= 0.8
    assert indice.buscar("cartucho_serie", "東海道五拾三次") == [] and indice.buscar("firma", "") == []
    assert indice.buscar("sello_editor", "江戸名勝図会") == []       # un cartucho no se compara con un sello
    assert indice.buscar("cartucho_serie", "江戸名勝図会", sin_referencia="TDP-008198") == []  # no se encuentra a sí misma
    assert indice.buscar("magia", "江戸") == []


def test_lo_aceptado_confirma_lo_corregido_cambia_el_nombre_y_lo_rechazado_se_retira(tmp_path):
    foto = _foto(tmp_path / "a.jpg")
    linea = servicio.ficha_de_intercambio({"id_peticion": "idn-000007", "referencia": "TDP-008198"}, {"ficha": SIN_SELLOS})
    indice.desde_ficha(linea, foto)
    hecho = indice.desde_aceptada({"id_peticion": "idn-000007", "referencia": "TDP-008198", "campos": {
        "serie": {"estado": "corregido", "valor": "Edo meishô zue (48 vistas)"}, "autor": {"estado": "rechazado", "valor": None},
        "titulo": {"estado": "aceptado", "valor": "Sensō-ji"}}})
    assert hecho == 3
    assert indice.buscar("cartucho_serie", "江戸名勝圖會")[0] | {"forma_parecida": 0} == {
        "tipo": "cartucho_serie", "lectura": "江戸名勝圖會", "nombre": "Edo meishô zue (48 vistas)", "dice_parecido": 1.0,
        "forma_parecida": 0, "hojas": 1, "confirmada": True, "forma": "—"}
    assert indice.buscar("firma", "広重画") == [] and indice.resumen()["confirmadas"] == 2
    assert len(indice.leer(con_retiradas=True)) == 3
    assert indice.desde_aceptada({"id_peticion": "idn-999999", "campos": {"serie": {"estado": "aceptado"}}}) == 0


def test_la_forma_distingue_dos_cartuchos_iguales_de_uno_distinto(tmp_path):
    a = Image.open(_foto(tmp_path / "a.jpg")).crop((505, 60, 545, 215))
    b = Image.open(_foto(tmp_path / "b.jpg", color=(190, 70, 60))).crop((506, 62, 546, 214))   # el mismo, mal encuadrado
    c = Image.new("RGB", (40, 150), (200, 60, 50))
    ImageDraw.Draw(c).ellipse((5, 40, 35, 110), outline=(10, 10, 10), width=4)
    iguales, distintos = indice.forma_parecida(indice.describir(a), indice.describir(b)), indice.forma_parecida(indice.describir(a), indice.describir(c))
    assert iguales >= indice.FORMA_MUY_PARECIDA > distintos
    assert indice.describir(Image.new("RGB", (40, 150), (230, 220, 200))) is None   # un recorte liso no se describe
    assert indice.forma_parecida(indice.describir(a), None) == 0.0


def test_buscar_en_indice_no_dice_al_modelo_ninguna_referencia(tmp_path):
    foto = _foto(tmp_path / "a.jpg")
    linea = servicio.ficha_de_intercambio({"id_peticion": "idn-000001", "referencia": "TDP-008198"}, {"ficha": SIN_SELLOS})
    indice.desde_ficha(linea, foto)
    otra = _foto(tmp_path / "b.jpg")
    entrada = {"tipo": "cartucho_serie", "lectura": "江戸名勝圖會", "imagen": 1, "x0": 845, "y0": 80, "x1": 905, "y1": 268}
    salida = agente.ejecutar("buscar_en_indice", entrada, [otra], {"referencia": "TDP-008201"})
    visto = json.loads(salida)["ya_visto_en_el_taller"]
    assert visto[0]["nombre"] == "Edo meishô zue" and visto[0]["hojas"] == 1 and visto[0]["forma"] == "muy parecida"
    assert "TDP-" not in salida and "idn-" not in salida and "ind-" not in salida
    # la misma obra no se encuentra a sí misma, y una caja mala busca solo por lo que dice
    assert "nada parecido" in agente.ejecutar("buscar_en_indice", entrada, [otra], {"referencia": "TDP-008198"})
    assert "ya_visto" in agente.ejecutar("buscar_en_indice", {**entrada, "x1": 0}, [otra], {"referencia": "TDP-1"})


# ---------------------------------------------------------------- fuentes abiertas

JPS_BUSQUEDA = {"hit": 2, "list": [
    {"common": {"id": "arc_nishikie-BAMPFA_1919_0249", "title": "「江戸名勝図会」　「浅草寺」", "contributor": ["広重〈2〉", "藤岡屋　慶次郎"],
                "database": "arc_nishikie", "linkUrl": "https://www.dh-jac.net/db/nishikie/BAMPFA-1919.0249/portal/",
                "thumbnailUrl": ["https://www.arc.ritsumei.ac.jp/x.jpg", "https://data.ukiyo-e.org/japancoll/scaled/p300.jpg"], "temporal": ["1861"]}},
    {"common": {"id": "adeac-R1", "title": "江戸名勝図会 浅草寺花邸", "contributor": ["歌川広重（二代）/画"], "database": "adeac",
                "linkUrl": "https://adeac.jp/taito-lib/catalog/mp1", "thumbnailUrl": ["https://adeac.jp/items/t.jpg"], "temporal": ["1864"]}}]}
JPS_FICHA = {"common": {"id": "arc_nishikie-BAMPFA_1919_0249", "title": "「江戸名勝図会」", "database": "arc_nishikie", "contributor": ["広重〈2〉"]},
             "arc_nishikie-13-s": "藤けい 藤岡屋 慶次郎", "arc_nishikie-17-s": "広重画", "arc_nishikie-19-s": "彫兼",
             "arc_nishikie-20-s": "酉十二改", "arc_nishikie-71-s": "1919.249", "arc_nishikie-72-s": "© The Regents", "arc_nishikie-25-s": "・"}


def _fuente_de_mentira(monkeypatch, respuestas: dict):
    pedidas = []

    def pedir(url, sufijo=".json", tope_bytes=None):
        pedidas.append(url)
        for trozo, cuerpo in respuestas.items():
            if trozo in url:
                return cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
        raise AssertionError(f"petición no prevista: {url}")

    monkeypatch.setattr(museos, "_pedir", pedir)
    return pedidas


def test_japan_search_da_autor_editor_fecha_y_los_sellos_del_ejemplar_de_referencia(monkeypatch):
    pedidas = _fuente_de_mentira(monkeypatch, {"item/search/jps-cross": JPS_BUSQUEDA, "api/item/arc_nishikie": JPS_FICHA})
    filas = museos.buscar("japan_search", "江戸名勝図会  浅草寺")
    assert "keyword=%E6%B1%9F" in pedidas[0] and [f["base"] for f in filas] == ["arc_nishikie", "adeac"]
    # del ARC no se da su página (dh-jac.net no se abre) sino la de Japan Search, y de las miniaturas solo la permitida
    assert filas[0]["url"] == "https://jpsearch.go.jp/item/arc_nishikie-BAMPFA_1919_0249" and "dh-jac" not in json.dumps(filas)
    assert filas[0]["imagen"] == "https://data.ukiyo-e.org/japancoll/scaled/p300.jpg" and filas[0]["fecha"] == "1861"
    assert filas[1]["url"] == "https://adeac.jp/taito-lib/catalog/mp1"
    campos = museos.ficha("japan_search", "arc_nishikie-BAMPFA_1919_0249")["campos"]
    assert campos == {"editor": "藤けい 藤岡屋 慶次郎", "firma": "広重画", "grabador": "彫兼", "sello_de_censura": "酉十二改"}
    monkeypatch.setenv("TDP_JPS_SIN_ARC", "si")
    assert [f["base"] for f in museos.buscar("japan_search", "江戸名勝図会 浅草寺")] == ["adeac"]
    assert museos.buscar("japan_search", "   ") == []
    with pytest.raises(museos.NoPermitida):
        museos.ficha("japan_search", "../../etc/passwd")
    with pytest.raises(museos.NoPermitida):
        museos.buscar("google", "algo")


def test_los_museos_con_api_dan_solo_estampas_con_su_imagen(monkeypatch):
    _fuente_de_mentira(monkeypatch, {
        "api.artic.edu/api/v1/artworks/search": {"data": [
            {"id": 1, "title": "Head", "artist_title": "Edo", "classification_title": "sculpture", "image_id": "a"},
            {"id": 7688, "title": "Autumn Moon", "artist_title": "Utagawa Hiroshige II", "date_display": "c. 1859",
             "classification_title": "woodblock print", "image_id": "2ef4"}]},
        "api.artic.edu/api/v1/artworks/7688": {"data": {"id": 7688, "title": "Autumn Moon", "inscriptions": "Signature: Hiroshige ga",
                                                       "dimensions": "36 × 24 cm", "description": "<p>Una <b>vista</b></p>", "image_id": "2ef4"}},
        "clevelandart.org/api/artworks/?": {"data": [{"id": 111671, "title": "Woman", "creators": [{"description": "Utagawa Kunisada"}],
                                                      "creation_date": "c. 1820", "url": "https://clevelandart.org/art/1930.201",
                                                      "images": {"web": {"url": "https://openaccess-cdn.clevelandart.org/1930.201/w.jpg"}}}]}})
    (fila,) = museos.buscar("aic", "Hiroshige II Omi hakkei")
    assert fila["id"] == "7688" and fila["imagen"] == "https://www.artic.edu/iiif/2/2ef4/full/843,/0/default.jpg"
    f = museos.ficha("aic", "7688")
    assert f["inscripciones"] == "Signature: Hiroshige ga" and f["descripcion"] == "Una vista" and museos.imagen_permitida(f["imagen"])
    (c,) = museos.buscar("cleveland", "Kunisada")
    assert c["autor"] == "Utagawa Kunisada" and museos.imagen_permitida(c["imagen"])
    with pytest.raises(museos.NoPermitida):
        museos.ficha("aic", "7688/../x")


def test_solo_se_baja_una_imagen_de_las_fuentes_y_nunca_de_uploads():
    assert museos.imagen_permitida("https://data.ukiyo-e.org/mfa/scaled/sc190207.jpg")
    for mala in ("https://data.ukiyo-e.org/uploads/x.jpg", "http://data.ukiyo-e.org/mfa/scaled/a.jpg", "https://ejemplo.com/a.jpg",
                 "https://data.ukiyo-e.org.ejemplo.com/a.jpg", "https://usuario@data.ukiyo-e.org/a.jpg", "https://data.ukiyo-e.org:8443/a.jpg",
                 "file:///etc/passwd", "no es una url", "https://www.dh-jac.net/db/x.jpg"):
        assert not museos.imagen_permitida(mala), mala
        with pytest.raises(museos.NoPermitida):
            museos.imagen(mala)


def test_un_servidor_que_contesta_429_se_para_hasta_manana_y_no_se_le_vuelve_a_pedir(monkeypatch):
    veces = []

    def cae(pedido, timeout=60):
        veces.append(pedido.full_url)
        raise urllib.error.HTTPError(pedido.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))

    monkeypatch.setattr(museos.urllib.request, "urlopen", cae)
    with pytest.raises(museos.Parado):
        museos.buscar("aic", "Kunisada")
    with pytest.raises(museos.Parado):
        museos.buscar("aic", "Hiroshige")
    assert len(veces) == 1 and "429" in museos.estado()["servidores"]["api.artic.edu"]["parado"]
    assert "no se consulta más hoy" in agente.ejecutar("fuentes_buscar", {"fuente": "aic", "consulta": "Eisen"}, [])


def test_ver_referencia_trae_la_imagen_reducida_y_solo_de_las_fuentes(monkeypatch):
    grande = io.BytesIO()
    Image.new("RGB", (3000, 2000), (120, 90, 60)).save(grande, "JPEG", comment=b"TDP-777777")
    monkeypatch.setattr(museos, "_pedir", lambda url, sufijo=".json", tope_bytes=None: grande.getvalue())
    bloque, texto = agente.ejecutar("ver_referencia", {"url": "https://data.ukiyo-e.org/mfa/scaled/sc190207.jpg"}, [])
    import base64
    enviada = base64.standard_b64decode(bloque["source"]["data"])
    assert max(Image.open(io.BytesIO(enviada)).size) == agente.LADO_REFERENCIA and b"TDP-777777" not in enviada
    assert "edicion" in texto["text"] and "márgenes" in texto["text"]
    assert "No se puede traer" in agente.ejecutar("ver_referencia", {"url": "https://ejemplo.com/a.jpg"}, [])
    monkeypatch.setattr(museos, "_pedir", lambda *a, **k: b"esto no es una imagen")
    assert "No se pudo traer" in agente.ejecutar("ver_referencia", {"url": "https://data.ukiyo-e.org/mfa/scaled/x.jpg"}, [])


def test_la_ficha_de_ukiyoe_dice_donde_esta_su_imagen(monkeypatch):
    pagina = ('<div class="col-xs-12 col-md-6 imageholder"><a href="https://data.ukiyo-e.org/mfa/images/sc1.jpg"><img '
              'src="https://data.ukiyo-e.org/mfa/scaled/sc1.jpg" alt="Japanese Print &quot;Nezu&quot; by Hiroshige II"/></a></div>')
    monkeypatch.setattr(ukiyoe, "_pedir", lambda ruta: pagina)
    f = ukiyoe.ficha("mfa/sc1")
    assert f["imagen"] == "https://data.ukiyo-e.org/mfa/scaled/sc1.jpg" and museos.imagen_permitida(f["imagen"])
    monkeypatch.setattr(ukiyoe, "_pedir", lambda ruta: "<html></html>")
    assert ukiyoe.ficha("mfa/sc2")["imagen"] == ""


# ---------------------------------------------------------------- el OCR de la NDL en la lupa

def test_la_lupa_lee_con_el_ocr_cuando_se_le_pide_y_solo_unas_veces_por_obra(tmp_path, monkeypatch):
    import imagen

    foto = _foto(tmp_path / "a.jpg")
    llamadas = []
    monkeypatch.setattr(imagen, "ocr_carpeta", lambda carpeta: llamadas.append(sorted(p.name for p in carpeta.glob("*.jpg"))) or {
        "recorte": [{"texto": "江戸名勝圖會", "confianza": 0.91}, {"texto": "abc", "confianza": 0.2}]})
    entrada = {"imagen": 1, "x0": 845, "y0": 80, "x1": 905, "y1": 268, "mejora": "contraste", "ocr": True}
    contexto = {"referencia": "TDP-008198", "ocr_lupa": 0}
    bloque, texto = agente.ejecutar("ampliar", entrada, [foto], contexto)
    assert bloque["type"] == "image" and "江戸名勝圖會 (0.91)" in texto["text"] and "abc" not in texto["text"]
    assert llamadas == [["recorte.jpg"]] and contexto["ocr_lupa"] == 1
    assert len(agente.ejecutar("ampliar", {**entrada, "ocr": False}, [foto], contexto)) == 1     # sin pedirlo, solo el recorte
    for _ in range(agente.OCR_EN_LUPA - 1):
        agente.ejecutar("ampliar", entrada, [foto], contexto)
    assert "agotadas" in agente.ejecutar("ampliar", entrada, [foto], contexto)[1]["text"] and len(llamadas) == agente.OCR_EN_LUPA
    # si el OCR falla, la lupa sigue
    monkeypatch.setattr(imagen, "ocr_carpeta", lambda carpeta: (_ for _ in ()).throw(RuntimeError("sin OCR")))
    assert "no lee nada" in agente.ejecutar("ampliar", entrada, [foto], {"ocr_lupa": 0})[1]["text"]


def test_las_herramientas_nuevas_estan_en_las_dos_fases_con_su_tope_y_esquema_estricto():
    nombres = [h["name"] for h in agente.HERRAMIENTAS_A]
    assert nombres[-4:] == ["buscar_en_indice", "fuentes_buscar", "fuentes_ficha", "ver_referencia"]
    assert all(h["name"] in agente.TOPES and h["name"] in agente.TOPES_HERMANA for h in agente.HERRAMIENTAS_A)
    assert all(h.get("strict") and h["input_schema"]["additionalProperties"] is False
               and sorted(h["input_schema"]["required"]) == sorted(h["input_schema"]["properties"]) for h in agente.HERRAMIENTAS_A)
    assert [h for h in agente.HERRAMIENTAS_B if h.get("name") in nombres] == agente.HERRAMIENTAS_A
    assert agente.ORIGEN["fuentes_ficha"] == "abierta" and agente.ORIGEN["fuentes_buscar"] == "solo buscador"
    prompt = agente.PROMPT.read_text(encoding="utf-8")
    for palabra in ("buscar_en_indice", "fuentes_buscar", "ver_referencia", "sello_visible", '"edicion"', '"textos"', "reproducción moderna"):
        assert palabra in prompt, palabra


# ---------------------------------------------------------------- las series juntas

def _linea(ref, idp, serie_jp, autor, editor, fecha, censor_detalle, cajas_censor=(), valor="Edo meishô zue", lamina=""):
    return {"id_peticion": idp, "referencia": ref, "error": None, "para_web": {"serie_lamina": lamina}, "datos": {
        "titulo": {"valor": f"Vista {ref[-2:]}"}, "autor": {"valor": autor}, "editor": {"valor": editor},
        "serie": {"valor": valor, "detalle": serie_jp, "fiabilidad": "alta"},
        "censor": {"valor": fecha, "detalle": censor_detalle, "lectura": censor_detalle if cajas_censor else None, "cajas": list(cajas_censor)}}}


def test_las_hojas_de_una_serie_se_juntan_y_se_dice_cual_desentona():
    fichas = [
        _linea("TDP-008198", "idn-000029", "江戸名勝圖會", "Utagawa Hiroshige II (Shigenobu)", "Fujiokaya Keijirō (Fujikei)", "1861–1862", "改 酉十二", [[1, 1, 9, 9]], lamina="12"),
        _linea("TDP-008119", "idn-000018", "江戸名勝図会 · lámina 3", "Utagawa Hiroshige II", "Fujiokaya Keijirō", "1861", "改 酉六", [[1, 1, 9, 9]], valor="Vistas de lugares famosos de Edo"),
        _linea("TDP-008134", "idn-000021", "江戸名勝図会", "Utagawa Hiroshige", "Tsutaya Kichizō", "1832", "sin sello visible"),
        _linea("TDP-008134", "idn-000040", "江戸名勝図会", "Utagawa Hiroshige", "Fujiokaya Keijirō", "1861–1862", "sin sello visible"),  # la última manda
        _linea("TDP-007698", "idn-000020", "武勇魁図会", "Utagawa Kuniyoshi", None, "1847–1852", "村 衣笠", [[1, 1, 9, 9]], valor="Buyū sakigake zue"),
        {"id_peticion": "idn-000050", "referencia": "TDP-000001", "error": "sin fotos", "datos": {}},
    ]
    gestor = [{"referencia": "TDP-008201", "serie": "Edo meishô zue", "titulo": "Nezu", "artista": "Utagawa Hiroshige II", "anio": "1862"},
              {"referencia": "TDP-008198", "serie": "Edo meishô zue"},                 # ya identificada: no se repite
              {"referencia": "TDP-004000", "serie": "", "titulo": "Suelta"}]
    juntas = series.consolidar(fichas, gestor)
    edo = juntas[0]
    assert edo["clave"] == "江戸名勝図会" and [h["referencia"] for h in edo["hojas"]] == ["TDP-008119", "TDP-008198", "TDP-008134", "TDP-008201"]
    assert (edo["identificadas"], edo["pendientes"], edo["laminas"], edo["anios"]) == (3, 1, ["3", "12"], [1861, 1862])
    assert edo["autor"].startswith("Utagawa Hiroshige II") and edo["editor"].startswith("Fujiokaya Keijirō")
    assert edo["otros_nombres"] == ["Vistas de lugares famosos de Edo"]
    avisos = "\n".join(edo["avisos"])
    assert "TDP-008134: autor «Utagawa Hiroshige», y la serie dice «Utagawa Hiroshige II" in avisos   # Hiroshige no es Hiroshige II
    assert "TDP-008134: sin el sello de censura que llevan 2 de sus hermanas" in avisos
    assert "TDP-008198" not in avisos and "TDP-008119" not in avisos and "Tsutaya" not in avisos       # la propuesta vieja no cuenta
    assert [s["clave"] for s in juntas[1:]] == ["武勇魁図会"] and juntas[1]["avisos"] == []
    texto = series.informe(juntas)
    assert "1 series con dos hojas o más (4 hojas) y 1 series de las que solo hay una hoja" in texto
    assert "| TDP-008201 | — | Nezu | Utagawa Hiroshige II | — | 1862 | — | pendiente |" in texto and "Lo que desentona:" in texto


def test_una_serie_en_la_que_ninguna_hoja_ensena_sello_lo_dice_y_la_tirada_del_catalogador_tambien():
    fichas = [_linea(f"TDP-00810{i}", f"idn-00010{i}", "江戸名勝図会", "Utagawa Hiroshige II", "Fujiokaya Keijirō", "1861", "no visible") for i in range(3)]
    fichas[0]["edicion"] = {"estado": "reproducción moderna", "avisos": ["no se ve el sello de censura o de fecha"]}
    (s,) = series.consolidar(fichas)
    assert "ninguna de las 3 hojas identificadas enseña sello de censura" in s["avisos"][0]
    assert "TDP-008100: el catalogador la da por reproducción moderna" in s["avisos"]
    assert series.clave_de_serie("Tôkaidô gojûsan tsugi no uchi") == series.clave_de_serie("Tōkaidō gojūsan tsugi no uchi (actores)")
    assert series.clave_de_serie(None) == "" and series.consolidar([]) == []


def test_el_servicio_escribe_el_informe_de_series_solo_si_cambia(tmp_path):
    fichas = tmp_path / "fichas.jsonl"
    fichas.write_text("\n".join(json.dumps(x) for x in (
        {"formato": "fichas", "version": 1},
        _linea("TDP-008198", "idn-000029", "江戸名勝圖會", "Utagawa Hiroshige II", "Fujiokaya Keijirō", "1861", "no visible"),
        _linea("TDP-008119", "idn-000018", "江戸名勝図会", "Utagawa Hiroshige II", "Fujiokaya Keijirō", "1861", "no visible"))) + "\n", encoding="utf-8")
    salida = tmp_path / "resultados" / "series.md"
    assert series.publicar(fichas, salida) and not series.publicar(fichas, salida)
    assert "## Edo meishô zue · 江戸名勝圖會" in salida.read_text(encoding="utf-8")
