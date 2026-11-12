"""D-1840: hacia la API no sale ninguna referencia (ni TDP-, ni idn-, ni el grupo idn-g-) ni nada más de la
petición. Sale la foto, las medidas y, si una persona la escribió, la serie conocida (D-991 del Gestor, que es
una excepción cerrada). Sin API: el cliente doble guarda todo lo que se le pasa a `messages.stream`."""
import base64
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agente  # noqa: E402
import biblioteca  # noqa: E402
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
#: Lo que la memoria tiene que seguir dando al modelo: el editor y la fuente de la primera hoja.
EDITOR, FUENTE = "Echizenya Kajū", "https://ukiyo-e.org/image/etm/0189204030"


def _con_metadatos(foto):
    """Una foto como las del almacén: con EXIF, XMP y comentario dentro (el segmento COM en un JPEG, el texto
    «comment» en un PNG), y en ellos una referencia."""
    exif = Image.Exif()
    exif[0x010E] = "TDP-123456"  # ImageDescription
    xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><dc:description>TDP-654321</dc:description></x:xmpmeta>'
    texto = PngImagePlugin.PngInfo()
    texto.add_text("comment", "TDP-777777")
    Image.new("RGB", (300, 400), (230, 220, 200)).save(foto, exif=exif, xmp=xmp, comment=b"TDP-777777", pnginfo=texto)


def _textos(cliente):
    return [b.get("text", "") for p in cliente.enviadas for b in p["messages"][0]["content"]]


def _sin_nada_de_la_peticion(cliente, inter=None):
    """Sobre TODO lo enviado (sistema, mensajes, herramientas, el resto de argumentos y los bytes de cada foto):
    ninguna referencia y, de la petición, ni la fecha, ni quién la pidió, ni los nombres de las fotos, ni las notas."""
    texto = json.dumps(cliente.enviadas, ensure_ascii=False, default=str)
    fotos = [base64.b64decode(d).decode("latin-1") for d in re.findall(r'"data": "([A-Za-z0-9+/=]+)"', texto)]
    assert fotos
    texto += "".join(fotos)
    prohibido = REFERENCIAS.findall(texto)
    for p in servicio.leer_jsonl(inter / "para_catalogador" / "cola.jsonl") if inter else []:
        prohibido += [x for x in (p["pedido_en"], p.get("pedido_por"), *(Path(r).name for r in p["imagenes"]),
                                  *(q.get("nota") or "" for q in p.get("pistas") or [])) if x and x in texto]
    assert cliente.enviadas and not prohibido, " | ".join(prohibido)


@pytest.mark.parametrize("corta, llamadas", [(PRIMERA, 2), (CONTRADICCIONES["autor"], 3)],
                         ids=["hermana_corta", "repetida_completa"])
def test_el_servicio_no_manda_referencias_ni_nada_de_la_peticion(tmp_path, monkeypatch, corta, llamadas):
    # (a) la primera, completa y con la memoria de series; (b) la hermana corta (D-1798); (c) la misma hermana
    # repetida completa tras una contradicción (D-1799), con la memoria que ya lleva la primera hoja.
    inter, imagenes = _montar(tmp_path, monkeypatch)
    for foto in imagenes.rglob("*.jpg"):
        _con_metadatos(foto)
    servicio.MEMORIA.write_text(json.dumps(MEMORIA, ensure_ascii=False), encoding="utf-8")
    cliente = _Cliente([_final(PRIMERA), _final(corta), _final(PRIMERA)])
    monkeypatch.setattr(agente, "catalogar", CATALOGAR_DE_VERDAD)
    monkeypatch.setattr(agente, "cliente", lambda: cliente)
    servicio.Servicio(inter, imagenes).vuelta()
    assert len(cliente.enviadas) == llamadas
    textos = _textos(cliente)
    assert sum("ya catalogada en" in t and EDITOR in t and FUENTE in t for t in textos) >= llamadas
    # la hermana corta lleva lo que el modelo necesita de la primera: el editor, su sello, la fecha y la fuente
    assert any(CORTA in t and EDITOR in t and "越嘉" in t and "1862" in t and FUENTE in t for t in textos)
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
    _con_metadatos(foto)
    cliente = _Cliente([_final(PRIMERA)])
    o = {"referencia": "TDP-008133", "destino": tmp_path / "TDP-008133.json", "fotos": [foto],
         "gestor": {"alto_cm": 35.2, "ancho_cm": 24.1, "tienda": {}}}
    args = SimpleNamespace(modelo=agente.MODELO_POR_DEFECTO, sin_web=False, esfuerzo=agente.ESFUERZO)
    assert catalogador.catalogar_una(cliente, o, args) > 0
    assert any("ya catalogada en" in t and EDITOR in t and FUENTE in t for t in _textos(cliente))
    _sin_nada_de_la_peticion(cliente)


def test_la_biblioteca_del_taller_no_devuelve_al_modelo_la_referencia(tmp_path, monkeypatch):
    # (e) lo que devuelven buscar_firma y buscar_sello_editor va entero a la API como tool_result
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()  # aprende la firma y el sello aceptados en TDP-008194
    for herramienta, consulta in (("buscar_firma", "國周画"), ("buscar_sello_editor", "越嘉")):
        salida = agente.ejecutar(herramienta, {"consulta": consulta}, [])
        assert json.loads(salida)["confirmadas_por_el_taller"] and not REFERENCIAS.search(salida), salida


def test_la_biblioteca_se_sanea_tambien_al_salir(tmp_path, monkeypatch):
    # D-1768: la lectura y el nombre salen hacia la API saneados, también lo que entró antes de la 0.6.1 o por una corrección
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    tabla = biblioteca.TABLA["firma"]
    tabla.write_text(tabla.read_text(encoding="utf-8").replace("Toyohara Kunichika", "Toyohara\\u0007Kunichika"), encoding="utf-8")
    salida = agente.ejecutar("buscar_firma", {"consulta": "國周画"}, [])
    assert "\u0007" not in salida and not json.loads(salida)["confirmadas_por_el_taller"], salida


def test_la_serie_aceptada_pasa_por_el_saneado_antes_de_la_memoria(tmp_path, monkeypatch):
    # lo que vuelve de la memoria va a la API: la serie aceptada en el Gestor se sanea como la serie_conocida (D-1787)
    inter, imagenes = _montar(tmp_path, monkeypatch)
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    aceptadas.write_text(aceptadas.read_text(encoding="utf-8").replace(
        '"valor": "Hauta tora no maki"', '"valor": "東海道五十三次\\u0007"'), encoding="utf-8")
    servicio.Servicio(inter, imagenes).vuelta()
    assert "東海道" not in servicio.MEMORIA.read_text(encoding="utf-8")


@pytest.mark.parametrize("nombre", ["foto.jpg", "foto.png"])
def test_ni_la_foto_entera_ni_la_lupa_llevan_el_comentario(tmp_path, nombre):
    # Pillow escribe al guardar el comentario que trae la imagen (im.info["comment"]): sale solo lo que se ve
    foto = tmp_path / nombre
    _con_metadatos(foto)
    with Image.open(foto) as im:
        assert im.info["comment"] in (b"TDP-777777", "TDP-777777")  # la foto de la prueba lo lleva
    lupa = agente.ampliar([foto], {"imagen": 1, "x0": 0, "y0": 0, "x1": 500, "y1": 500})
    for bloque in [agente.bloque_imagen(foto), *lupa]:
        assert b"TDP-" not in base64.b64decode(bloque["source"]["data"])


def test_las_medidas_que_no_son_un_numero_no_llegan_a_la_api(tmp_path, monkeypatch):
    # de la petición salen las medidas, y solo si son un número: un texto, un booleano o un NaN van como «—»
    inter, imagenes = _montar(tmp_path, monkeypatch)
    cola = inter / "para_catalogador" / "cola.jsonl"
    cola.write_text(cola.read_text(encoding="utf-8").replace('"alto_cm": 34.9, "ancho_cm": 23.9',
                                                            '"alto_cm": "TDP-777777", "ancho_cm": true')
                    .replace('"alto_cm": 35.2', '"alto_cm": NaN'), encoding="utf-8")
    cliente = _Cliente([_final(PRIMERA), _final(PRIMERA)])
    monkeypatch.setattr(agente, "catalogar", CATALOGAR_DE_VERDAD)
    monkeypatch.setattr(agente, "cliente", lambda: cliente)
    servicio.Servicio(inter, imagenes).vuelta()
    medidas = [t for t in _textos(cliente) if t.startswith("Medidas de la hoja")]
    assert [m.split(" cm")[0] for m in medidas] == ["Medidas de la hoja: — × —", "Medidas de la hoja: — × 24.1"]
    _sin_nada_de_la_peticion(cliente, inter)


def test_la_firma_y_los_sellos_aceptados_pasan_por_el_saneado_antes_de_la_biblioteca(tmp_path, monkeypatch):
    # la lectura y el nombre aprendidos vuelven a la API por buscar_firma y buscar_sello_editor (D-1787)
    inter, imagenes = _montar(tmp_path, monkeypatch)
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    cabecera, linea = aceptadas.read_text(encoding="utf-8").splitlines()
    a = json.loads(linea)
    a["firma_confirmada"]["lectura"] = "國周画\x07"
    sello = a["sellos_confirmados"][0]
    a["sellos_confirmados"] = [{**sello, "tipo": "editor\u202e", "nombre": " Echizenya \n Kajū "},
                               {**sello, "nombre": "x" * 121, "caja": None}]
    aceptadas.write_text(f"{cabecera}\n{json.dumps(a)}\n", encoding="utf-8")
    servicio.Servicio(inter, imagenes).vuelta()
    assert biblioteca.leer("firma") == []
    assert [f["nombre"] for f in biblioteca.leer("sello")] == [": Echizenya Kajū"]
