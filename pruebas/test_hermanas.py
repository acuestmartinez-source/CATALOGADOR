"""Paso 3 (D-1798 y D-1799): la pasada corta de las hermanas de un grupo. Sin API ni web: dobles."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agente  # noqa: E402
import ficha as F  # noqa: E402
import servicio  # noqa: E402
import ukiyoe  # noqa: E402
from test_paso_2 import CATALOGAR_DE_VERDAD, _Cliente, _con_serie, _pide_censor, _uso  # noqa: E402
from test_servicio import _montar  # noqa: E402

#: La primera hoja del grupo, como la devolvería el modelo: serie con confianza alta y nivel de documento.
PRIMERA = {"tipo_obra": "estampa suelta",
           "autor": {"nombre": "Toyohara Kunichika", "firma": "國周画", "nivel": "lectura cotejada", "confianza": "alta"},
           "titulo": {"castellano": "Mujer con abanico", "construido": True, "nivel": "construido", "confianza": "media"},
           "serie": {"castellano": "Hauta tora no maki", "japones": "葉うた虎之巻", "romaji": "Hauta tora no maki",
                     "numero_lamina": 3, "nivel": "otra lámina documentada", "confianza": "alta",
                     "fuentes": ["https://ukiyo-e.org/image/etm/0189204030"]},
           "editor": {"nombre": "Echizenya Kajū", "sello": "越嘉", "nivel": "lectura cotejada", "confianza": "media"},
           "censor": {"fecha_desde": 1862, "fecha_hasta": 1863, "nivel": "otra lámina documentada", "confianza": "media"},
           "vinculadas": [], "buscar_mas": []}
OBRA = {"referencia": "TDP-008133", "alto_cm": 35.2, "ancho_cm": 24.1}
CORTA = "Pasada corta"


def _final(ficha):
    texto = f"```json\n{json.dumps(ficha, ensure_ascii=False)}\n```" if ficha is not None else "No llego a una ficha."
    return SimpleNamespace(stop_reason="end_turn", usage=_uso(), content=[SimpleNamespace(type="text", text=texto)])


def _herramienta(id_, nombre, entrada):
    return SimpleNamespace(type="tool_use", id=id_, name=nombre, input=entrada)


CENSOR = {"tipo": "kiwame", "animal": None, "mes": None, "censores": []}


@pytest.fixture
def foto(tmp_path, monkeypatch):
    ruta = tmp_path / "01.jpg"
    Image.new("RGB", (60, 80), (230, 220, 200)).save(ruta)
    monkeypatch.setattr(agente, "ocr_ndl", lambda f: [])
    return ruta


# ---------------------------------------------------------------- el agente

def test_la_hermana_va_corta_sin_ukiyoe_ni_web_y_con_los_topes_reducidos(foto, monkeypatch):
    consultas = []
    monkeypatch.setattr(ukiyoe, "buscar", lambda *a, **k: consultas.append(a) or [])
    pide = SimpleNamespace(stop_reason="tool_use", usage=_uso(), content=[
        _herramienta("u1", "ukiyoe_buscar", {"consulta": "kunichika hauta"}),
        _herramienta("c1", "datar_censor", CENSOR), _herramienta("c2", "datar_censor", CENSOR)])
    con_b = _final({**PRIMERA, "buscar_mas": ["la fecha en la web"]})  # sin hermana, esto abre la fase B

    cliente = _Cliente([pide, con_b])
    r = agente.catalogar(cliente, OBRA, [foto], hermana=F.hermana_de(PRIMERA, "TDP-008194"))
    assert len(cliente.enviadas) == 2 and r["fases"] == "A corta" and consultas == []
    assert all(t.get("name") not in ("web_search", "web_fetch") for p in cliente.enviadas for t in p["tools"])
    respuestas = {b["tool_use_id"]: b for b in cliente.enviadas[1]["messages"][-1]["content"]}
    assert respuestas["u1"].get("is_error") and respuestas["c2"].get("is_error") and not respuestas["c1"].get("is_error")
    assert r["usos"]["datar_censor"] == 1 and r["usos"]["ukiyoe_buscar"] == 0
    # reescrita por especificación (docs/11): la hermana mira en el índice del taller y sigue sin salir fuera
    assert agente.TOPES_HERMANA == {"ampliar": 4, "buscar_sello_editor": 2, "buscar_firma": 2, "datar_censor": 1,
                                    "ukiyoe_buscar": 0, "ukiyoe_ficha": 0, "buscar_en_indice": 3,
                                    "fuentes_buscar": 0, "fuentes_ficha": 0, "ver_referencia": 0}
    bloque = [b["text"] for b in cliente.enviadas[0]["messages"][0]["content"] if CORTA in (b.get("text") or "")]
    assert len(bloque) == 1 and "Toyohara Kunichika" in bloque[0] and "葉うた虎之巻" in bloque[0]
    assert "no busques en ukiyo-e.org ni en la web" in bloque[0] and "ESTA hoja" in bloque[0]

    # la misma conversación sin hermana: ukiyo-e.org, dos censores y la fase B, como siempre
    cliente = _Cliente([pide, con_b])
    r = agente.catalogar(cliente, OBRA, [foto])
    assert len(cliente.enviadas) == 3 and r["fases"] == "A+B" and len(consultas) == 1 and r["usos"]["datar_censor"] == 2
    assert not any(CORTA in (b.get("text") or "") for b in cliente.enviadas[0]["messages"][0]["content"])


def test_la_pasada_corta_para_a_las_ocho_vueltas(foto):
    cliente = _Cliente([_pide_censor(i) for i in range(40)])
    r = agente.catalogar(cliente, OBRA, [foto], hermana=F.hermana_de(PRIMERA, "TDP-008194"))
    assert len(cliente.enviadas) == agente.MAX_VUELTAS_HERMANA == 8 and r["ficha"] is None


def test_el_mensaje_de_hermana_no_lleva_precio_ubicacion_procedencia_ni_personas(foto):
    # D-991 del Gestor: aunque la ficha de la primera trajera algo de eso, a la hermana no le llega.
    sucia = {**PRIMERA, "precio": "1.200 €", "ubicacion": "planero 3, cajón 2", "procedencia": "colección particular",
             "comprador": "Juan Pérez", "propietario": "CR",
             "autor": {**PRIMERA["autor"], "como": "lo dijo el cliente por teléfono"},
             "serie": {**PRIMERA["serie"], "como": "precio en la ficha de belen@taller.es", "importe": 900},
             "editor": {**PRIMERA["editor"], "como": "procedencia: subasta"},
             "vinculadas": [{"relacion": "otra lámina", "url": "https://www.mfa.org/x", "nota": "vendida a un cliente"}]}
    cliente = _Cliente()
    agente.catalogar(cliente, OBRA, [foto], hermana=F.hermana_de(sucia, "TDP-008194"))
    bloque = next(b["text"] for b in cliente.enviadas[0]["messages"][0]["content"] if CORTA in (b.get("text") or ""))
    for palabra in ("precio", "1.200", "€", "importe", "coste", "ubicaci", "planero", "cajón", "procedencia", "particular",
                    "subasta", "comprador", "juan", "cliente", "propietario", "teléfono", "@", "belen", "vendida"):
        assert palabra not in bloque.lower(), palabra


# ---------------------------------------------------------------- el servicio

def _servicio(tmp_path, monkeypatch, primera=PRIMERA, corta=PRIMERA):
    """El intercambio del contrato: dos hojas del grupo idn-g-000012, las dos con serie conocida. El agente
    doble apunta con qué hermana se le llama: la pasada completa devuelve `primera` y cuesta 0,41 €; la
    corta, `corta` y 0,10 €."""
    inter, imagenes = _montar(tmp_path, monkeypatch)
    llamadas = []

    def doble(client, obra, fotos, **kw):
        h = kw.get("hermana")
        llamadas.append((obra["referencia"], h))
        return {"referencia": obra["referencia"], "modelo": "doble", "fases": "A corta" if h else "A",
                "coste_eur": 0.10 if h else 0.41, "duracion_s": 1.0, "uso": {"corta": bool(h)}, "ficha": copy.deepcopy(corta if h else primera),
                "para_web": None, "fuentes_verificadas": {}}

    monkeypatch.setattr(agente, "catalogar", doble)
    return inter, imagenes, llamadas


def _ficha(inter, idp):
    return next(f for f in servicio.leer_jsonl(inter / "de_catalogador" / "fichas.jsonl") if f["id_peticion"] == idp)


SIN_JAPONES = {**PRIMERA, "serie": {**PRIMERA["serie"], "japones": None}}  # la memoria de series no la guardaría


@pytest.mark.parametrize("primera", [PRIMERA, SIN_JAPONES], ids=["con_japones", "sin_japones"])
def test_la_segunda_hoja_del_grupo_va_corta_con_la_memoria_de_la_primera(tmp_path, monkeypatch, primera):
    # el autor de la corta, con otras mayúsculas y espacios: normalizado es el mismo, no hay contradicción
    corta = {**primera, "autor": {**primera["autor"], "nombre": " toyohara  KUNICHIKA "}}
    inter, imagenes, llamadas = _servicio(tmp_path, monkeypatch, primera, corta)
    servicio.Servicio(inter, imagenes).vuelta()
    assert [ref for ref, _ in llamadas] == ["TDP-008194", "TDP-008133"]
    assert llamadas[0][1] is None
    h = llamadas[1][1]
    assert h["autor"] == "Toyohara Kunichika" and h["serie"]["romaji"] == "Hauta tora no maki" and h["obras"] == ["TDP-008194"]
    segunda = _ficha(inter, "idn-000002")
    assert segunda["fases"] == "A corta" and segunda["coste_eur"] == 0.10
    estados = [e for e in servicio.leer_jsonl(inter / "de_catalogador" / "estado.jsonl") if e["id_peticion"] == "idn-000002"]
    assert any(e["estado"] == "identificando" and "corta" in e["detalle"] for e in estados)


def _segunda(inter, **campos):
    cola = inter / "para_catalogador" / "cola.jsonl"
    lineas = [json.loads(x) for x in cola.read_text(encoding="utf-8").splitlines()]
    lineas[2].update(campos)
    cola.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lineas), encoding="utf-8")


#: El Gestor da grupo a cualquier petición de varias obras y, sin serie de grupo, cada una lleva la suya (su api.py).
CAMBIOS = {"otro_grupo": {"grupo": "idn-g-000099"}, "otra_serie": {"serie_conocida": "Betsu no soroimono"}}


@pytest.mark.parametrize("caso", ["sin_serie_conocida", "serie_no_alta", "serie_sin_cotejar", "sin_autor", "sin_json",
                                  "otro_grupo", "otra_serie"])
def test_sin_serie_conocida_o_sin_primera_documentada_va_completa(tmp_path, monkeypatch, caso):
    primera = {"serie_no_alta": {**PRIMERA, "serie": {**PRIMERA["serie"], "confianza": "media"}},
               "serie_sin_cotejar": {**PRIMERA, "serie": {**PRIMERA["serie"], "nivel": "lectura sin cotejar"}},
               "sin_autor": {**PRIMERA, "autor": {**PRIMERA["autor"], "nivel": "hipótesis"}},
               "sin_json": None}.get(caso, PRIMERA)
    inter, imagenes, llamadas = _servicio(tmp_path, monkeypatch, primera)
    if caso == "sin_serie_conocida":
        _con_serie(inter, ...)
    if caso in CAMBIOS:
        _segunda(inter, **CAMBIOS[caso])
    servicio.Servicio(inter, imagenes).vuelta()
    assert llamadas == [("TDP-008194", None), ("TDP-008133", None)]
    assert _ficha(inter, "idn-000002")["fases"] == "A"


def test_tras_reiniciar_a_medio_grupo_la_hermana_va_completa(tmp_path, monkeypatch):
    inter, imagenes, llamadas = _servicio(tmp_path, monkeypatch)
    s = servicio.Servicio(inter, imagenes)
    s.una(s.pendientes()[0][0])  # la primera hoja, y el proceso se para
    servicio.Servicio(inter, imagenes).vuelta()  # otro proceso: no sabe nada de la primera
    assert llamadas == [("TDP-008194", None), ("TDP-008133", None)]


CONTRADICCIONES = {
    "autor": {**PRIMERA, "autor": {**PRIMERA["autor"], "nombre": "Utagawa Kunisada"}},
    "serie": {**PRIMERA, "serie": {**PRIMERA["serie"], "confianza": "media"}},
    "buscar_mas": {**PRIMERA, "buscar_mas": ["el editor en la web"]},
    "sin JSON": None,
}


@pytest.mark.parametrize("motivo", list(CONTRADICCIONES))
def test_cada_contradiccion_repite_la_hoja_completa_y_suma_los_costes(tmp_path, monkeypatch, motivo):
    inter, imagenes, llamadas = _servicio(tmp_path, monkeypatch, corta=CONTRADICCIONES[motivo])
    servicio.Servicio(inter, imagenes).vuelta()
    assert [(ref, h is not None) for ref, h in llamadas] == [("TDP-008194", False), ("TDP-008133", True), ("TDP-008133", False)]
    segunda = _ficha(inter, "idn-000002")
    assert segunda["coste_eur"] == 0.51 and segunda["fases"] == "A"
    assert segunda["datos"]["autor"]["valor"] == "Toyohara Kunichika"  # la de la pasada completa
    guardado = json.loads((tmp_path / "resultados" / "servicio" / "TDP-008133.json").read_text(encoding="utf-8"))
    assert guardado["pasada_corta"] == {"motivo": motivo, "coste_eur": 0.10, "duracion_s": 1.0, "uso": {"corta": True}}
    # mientras corre la completa, el Gestor no sigue viendo «fase A corta»
    detalles = [e["detalle"] for e in servicio.leer_jsonl(inter / "de_catalogador" / "estado.jsonl")
                if e["id_peticion"] == "idn-000002" and e["estado"] == "identificando"]
    assert "corta" in detalles[0] and "corta" not in detalles[-1]


def test_la_hermana_llega_entera_a_la_api_y_sin_nada_de_la_persona_que_pidio(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    cliente = _Cliente([_final(PRIMERA), _final(PRIMERA)])
    monkeypatch.setattr(agente, "catalogar", CATALOGAR_DE_VERDAD)
    monkeypatch.setattr(agente, "cliente", lambda: cliente)
    servicio.Servicio(inter, imagenes).vuelta()
    assert len(cliente.enviadas) == 2
    assert [_ficha(inter, i)["fases"] for i in ("idn-000001", "idn-000002")] == ["A", "A corta"]
    primero, segundo = ("\n".join(b.get("text", "") for b in p["messages"][0]["content"]) for p in cliente.enviadas)
    assert CORTA not in primero and CORTA in segundo and "Toyohara Kunichika" in segundo
    assert "belen" not in primero + segundo  # `pedido_por` no sale del intercambio


@pytest.mark.parametrize("caso", [None, "otra_serie"])
def test_en_seco_dice_que_hermanas_irian_cortas_sin_llamar_a_la_api(tmp_path, monkeypatch, capsys, caso):
    inter, imagenes, llamadas = _servicio(tmp_path, monkeypatch)
    if caso:
        _segunda(inter, **CAMBIOS[caso])
    monkeypatch.setattr(agente, "cliente", lambda: pytest.fail("en seco no hay API"))
    s = servicio.Servicio(inter, imagenes, en_seco=True)
    s.vuelta()
    s.vuelta()  # sin --una-vez el bucle repite: la primera de cada grupo no pasa a «corta» en la segunda vuelta
    salida = capsys.readouterr().out
    assert "TDP-008194: se haría con 2 foto(s), corta" not in salida
    assert "TDP-008194: se haría con 2 foto(s)\n" in salida
    corta = ", corta si la primera del grupo sale documentada"
    assert f"TDP-008133: se haría con 1 foto(s){'' if caso else corta}\n" in salida
    assert llamadas == [] and not (inter / "de_catalogador" / "fichas.jsonl").exists()
