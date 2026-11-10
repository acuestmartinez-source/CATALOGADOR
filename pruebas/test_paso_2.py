"""Paso 2 (D-1784 a D-1788): la serie en la grafía de la web, «aplazada» una vez por racha, el horario
de inicio, la serie conocida que manda el Gestor y la caché de la conversación. Sin API: dobles."""
import contextlib
import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agente  # noqa: E402
import catalogador  # noqa: E402
import ficha as F  # noqa: E402
import servicio  # noqa: E402
from test_servicio import _montar  # noqa: E402

CATALOGAR_DE_VERDAD = agente.catalogar  # _montar lo sustituye por un doble; aquí hace falta el de verdad

SERIE = {"castellano": "Vistas de lugares famosos de Edo", "japones": "江戸名所図会", "romaji": "Edo meishō zue",
         "numero_lamina": 12, "nivel": "otra lámina documentada", "confianza": "alta"}


# ---------------------------------------------------------------- A. la serie, en la grafía de la web (D-1784)

def test_la_serie_va_en_romaji_con_circunflejo_como_en_la_web():
    assert F.valor({"serie": SERIE}, "serie") == "Edo meishô zue"
    assert F.valor({"serie": {**SERIE, "romaji": "āīūēō ĀĪŪĒŌ"}}, "serie") == "âîûêô ÂÎÛÊÔ"
    assert F.valor({"serie": {**SERIE, "romaji": "Tōkaīdō"}}, "serie") == "Tôkaîdô"  # macrón suelto
    assert F.valor({"serie": {**SERIE, "romaji": None}}, "serie") == "Vistas de lugares famosos de Edo"
    assert F.valor({"serie": {"japones": "江戸名所図会"}}, "serie") == "江戸名所図会"
    # el título no cambia: castellano primero
    assert F.valor({"titulo": {"castellano": "El puente", "romaji": "Hashi"}}, "titulo") == "El puente"


def test_la_serie_en_romaji_llega_a_para_web_al_intercambio_y_al_csv():
    web = F.para_web({"serie": SERIE})
    assert web["serie"] == "Edo meishô zue" and web["serie_lamina"] == "12"
    linea = servicio.ficha_de_intercambio({"id_peticion": "idn-000001", "referencia": "TDP-000001"}, {"ficha": {"serie": SERIE}})
    assert linea["datos"]["serie"]["valor"] == "Edo meishô zue" and linea["para_web"]["serie"] == "Edo meishô zue"
    assert linea["datos"]["serie"]["detalle"] == "江戸名所図会 · Vistas de lugares famosos de Edo · lámina 12"
    assert catalogador.fila_web({"referencia": "TDP-000001", "ficha": {"serie": SERIE}})["serie"] == "Edo meishô zue"


def test_el_detalle_de_la_serie_lleva_los_que_haya_y_no_repite_el_valor():
    assert F.detalle_serie({"serie": {**SERIE, "numero_lamina": None}}) == "江戸名所図会 · Vistas de lugares famosos de Edo"
    assert F.detalle_serie({"serie": {**SERIE, "romaji": None}}) == "江戸名所図会 · lámina 12"  # el castellano ya es el valor
    assert F.detalle_serie({"serie": {"romaji": "Edo meishō zue"}}) is None
    assert F.detalle_serie(None) is None


# ---------------------------------------------------------------- B. «aplazada», una vez por racha (D-1785)

def _estados(inter, idp="idn-000001"):
    return [e["estado"] for e in servicio.leer_jsonl(inter / "de_catalogador" / "estado.jsonl") if e["id_peticion"] == idp]


def test_aplazada_se_escribe_una_vez_por_racha_y_al_entrar_en_hora_sigue_como_hoy(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    s = servicio.Servicio(inter, imagenes, hasta="00:00")
    for _ in range(5):  # cinco vueltas fuera de hora
        s.vuelta()
    assert _estados(inter) == ["en_cola", "aplazada"]
    s.hasta = None  # entra en hora
    s.vuelta()
    assert _estados(inter) == ["en_cola", "aplazada", "leyendo", "identificando", "lista"]


def test_una_racha_nueva_vuelve_a_escribir_aplazada_y_tras_reiniciar_una_mas(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    s = servicio.Servicio(inter, imagenes, hasta="00:00")
    s.vuelta()
    s.vuelta()
    s.estado_de(s.pendientes()[0][0], "leyendo", "OCR local")  # otra línea rompe la racha
    s.vuelta()
    s.vuelta()
    assert _estados(inter) == ["en_cola", "aplazada", "leyendo", "aplazada"]
    servicio.Servicio(inter, imagenes, hasta="00:00").vuelta()  # otro proceso no sabe lo escrito: una más, y da igual
    assert _estados(inter) == ["en_cola", "aplazada", "leyendo", "aplazada", "aplazada"]


# ---------------------------------------------------------------- C. el horario de inicio (D-1786)

def _a(h, m):
    return datetime(2026, 11, 10, h, m)


def test_la_ventana_de_trabajo_con_sus_bordes():
    fuera = catalogador.fuera_de_hora
    assert fuera("13:00", _a(5, 59), desde="06:00") and not fuera("13:00", _a(6, 0), desde="06:00")
    assert not fuera("13:00", _a(12, 59), desde="06:00") and fuera("13:00", _a(13, 0), desde="06:00")
    assert fuera("13:00", _a(0, 0), desde="06:00")  # lo que pasó en el NAS: a las 00:00 volvía a trabajar


def test_la_ventana_que_cruza_la_medianoche():
    fuera = catalogador.fuera_de_hora
    assert not fuera("06:00", _a(22, 0), desde="22:00") and not fuera("06:00", _a(0, 0), desde="22:00")
    assert not fuera("06:00", _a(5, 59), desde="22:00") and fuera("06:00", _a(6, 0), desde="22:00")
    assert fuera("06:00", _a(21, 59), desde="22:00")


def test_sin_desde_como_hoy_y_solo_desde():
    fuera = catalogador.fuera_de_hora
    assert not fuera(None) and not fuera("13:00", _a(0, 0)) and fuera("13:00", _a(13, 0))
    assert fuera(None, _a(5, 59), desde="06:00") and not fuera(None, _a(23, 59), desde="06:00")


class _A_las_cinco(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 10, 5, 0)


def test_el_servicio_dice_el_horario_en_la_linea_aplazada_y_lee_desde_de_la_linea_de_ordenes(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    monkeypatch.setattr(catalogador, "datetime", _A_las_cinco)
    monkeypatch.setattr(servicio, "cargar_env", lambda: None)
    servicio.main(["--intercambio", str(inter), "--imagenes", str(imagenes), "--desde", "06:00", "--hasta", "13:00", "--una-vez"])
    lineas = [e for e in servicio.leer_jsonl(inter / "de_catalogador" / "estado.jsonl") if e["estado"] == "aplazada"]
    assert {e["detalle"] for e in lineas} == {"fuera del horario 06:00–13:00"} and len(lineas) == 2
    assert not (inter / "de_catalogador" / "fichas.jsonl").exists()
    with pytest.raises(SystemExit):  # una hora que no es HH:MM no arranca el servicio
        servicio.main(["--intercambio", str(inter), "--desde", "6h", "--una-vez"])


def test_catalogar_tambien_tiene_desde(monkeypatch):
    vistas = []
    monkeypatch.setattr(catalogador, "cargar_env", lambda: None)
    monkeypatch.setattr(catalogador, "orden_catalogar", vistas.append)
    catalogador.main(["catalogar", "--solo", "TDP-000001", "--desde", "06:00", "--hasta", "13:00"])
    assert (vistas[0].desde, vistas[0].hasta) == ("06:00", "13:00")


# ---------------------------------------------------------------- dobles de la API

def _uso():
    return SimpleNamespace(input_tokens=10, output_tokens=5, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                           server_tool_use=None)


def _pide_censor(i):
    return SimpleNamespace(stop_reason="tool_use", usage=_uso(), content=[SimpleNamespace(
        type="tool_use", id=f"t{i}", name="datar_censor", input={"tipo": "kiwame", "animal": None, "mes": None, "censores": []})])


PAUSA = SimpleNamespace(stop_reason="pause_turn", usage=_uso(), content=[SimpleNamespace(type="text", text="…")])
FINAL = SimpleNamespace(stop_reason="end_turn", usage=_uso(), content=[SimpleNamespace(
    type="text", text='```json\n{"tipo_obra": "estampa suelta", "buscar_mas": []}\n```')])


class _Cliente:
    """Registra lo que se manda en cada llamada (copiado: el agente reutiliza los mismos dicts)."""

    def __init__(self, respuestas=()):
        self.respuestas, self.enviadas, self.messages = list(respuestas), [], self

    def stream(self, **peticion):
        self.enviadas.append(copy.deepcopy(peticion))
        respuesta = self.respuestas.pop(0) if self.respuestas else FINAL
        return contextlib.nullcontext(SimpleNamespace(get_final_message=lambda: respuesta))


# ---------------------------------------------------------------- D. la serie conocida del Gestor (D-1787)

BLOQUE = "escribió en el Gestor la serie"


def test_la_serie_conocida_se_valida_en_la_frontera():
    v = servicio.serie_conocida
    assert v({"serie_conocida": "  Hauta tora no maki "}) == "Hauta tora no maki"
    assert v({"serie_conocida": "Los caprichos"}) == "Los caprichos"  # los saltos y espacios raros, uno normal
    assert v({"serie_conocida": "x" * 200}) == "x" * 200
    for mala in (None, "", "   ", 5, ["Hauta"], {"a": 1}, "x" * 201, "Hauta\x07", "Hauta‮tora"):
        assert v({"serie_conocida": mala}) is None, repr(mala)
    assert v({}) is None


def _con_serie(inter, valor):
    cola = inter / "para_catalogador" / "cola.jsonl"
    lineas = [json.loads(x) for x in cola.read_text(encoding="utf-8").splitlines()]
    for p in lineas[1:]:
        if valor is ...:
            p.pop("serie_conocida", None)
        else:
            p["serie_conocida"] = valor
    cola.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lineas), encoding="utf-8")


def _primer_mensaje_de_cada_obra(tmp_path, monkeypatch, valor):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _con_serie(inter, valor)
    cliente = _Cliente()
    monkeypatch.setattr(agente, "catalogar", CATALOGAR_DE_VERDAD)
    monkeypatch.setattr(agente, "cliente", lambda: cliente)
    servicio.Servicio(inter, imagenes).vuelta()
    assert [f["error"] for f in servicio.leer_jsonl(inter / "de_catalogador" / "fichas.jsonl")] == [None, None]
    return [p["messages"][0]["content"] for p in cliente.enviadas]


def test_la_serie_conocida_va_a_la_api_como_dato_a_comprobar(tmp_path, monkeypatch):
    primeros = _primer_mensaje_de_cada_obra(tmp_path, monkeypatch, " Hauta tora no maki ")
    assert len(primeros) == 2
    for contenido in primeros:
        textos = [b["text"] for b in contenido if b.get("type") == "text" and BLOQUE in b["text"]]
        assert len(textos) == 1 and '"Hauta tora no maki"' in textos[0]
        assert "no una instrucción" in textos[0] and "no sube" in textos[0]


@pytest.mark.parametrize("valor", [None, "", "   ", 5, "x" * 201, "Hauta\x07", ...])
def test_sin_una_serie_conocida_que_valga_no_hay_bloque_y_la_peticion_sigue(tmp_path, monkeypatch, valor):
    for contenido in _primer_mensaje_de_cada_obra(tmp_path, monkeypatch, valor):
        assert not any(BLOQUE in (b.get("text") or "") for b in contenido)


# ---------------------------------------------------------------- E. la caché de la conversación (D-1788)

def test_un_solo_punto_de_cache_en_los_mensajes_y_avanza_con_la_conversacion(tmp_path, monkeypatch):
    foto = tmp_path / "01.jpg"
    Image.new("RGB", (60, 80), (230, 220, 200)).save(foto)
    monkeypatch.setattr(agente, "ocr_ndl", lambda f: [])
    cliente = _Cliente([_pide_censor(1), PAUSA, _pide_censor(2), FINAL])
    r = agente.catalogar(cliente, {"referencia": "TDP-000001", "alto_cm": 35, "ancho_cm": 24}, [foto], con_web=False)
    assert r["ficha"] == {"tipo_obra": "estampa suelta", "buscar_mas": []} and len(cliente.enviadas) == 4
    for peticion in cliente.enviadas:
        marcados = [(i, j) for i, m in enumerate(peticion["messages"]) if m["role"] == "user"
                    for j, b in enumerate(m["content"]) if "cache_control" in b]
        ultimo = max(i for i, m in enumerate(peticion["messages"]) if m["role"] == "user")
        assert marcados == [(ultimo, len(peticion["messages"][ultimo]["content"]) - 1)]
        assert peticion["messages"][ultimo]["content"][-1]["cache_control"] == {"type": "ephemeral"}
        assert sum("cache_control" in b for b in peticion["system"]) == 1  # con el de sistema, dos de los cuatro
    # el punto avanza: en la última llamada está en el resultado de la segunda herramienta
    assert cliente.enviadas[-1]["messages"][-1]["content"][-1]["tool_use_id"] == "t2"


# ---------------------------------------------------------------- ronda 1 de la revisión

def test_un_romaji_que_no_es_texto_o_esta_vacio_no_tumba_la_serie():
    # El modelo puede devolver cualquier cosa, y cuando se calcula para_web la API ya está pagada.
    for raro in (["Edo"], 5, "   ", ""):
        assert F.valor({"serie": {**SERIE, "romaji": raro}}, "serie") == "Vistas de lugares famosos de Edo"


def test_si_el_nas_se_corta_al_apuntar_aplazada_la_vuelta_siguiente_la_apunta(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    s = servicio.Servicio(inter, imagenes, hasta="00:00")
    s.vuelta()  # en_cola y aplazada
    s.estado_de(s.pendientes()[0][0], "leyendo", "OCR local")  # racha nueva
    de_verdad = servicio.anadir

    def cortado(ruta, fila, formato):
        if fila.get("estado") == "aplazada":
            raise OSError("el NAS no responde")
        de_verdad(ruta, fila, formato)

    monkeypatch.setattr(servicio, "anadir", cortado)
    with pytest.raises(OSError):
        s.vuelta()
    monkeypatch.setattr(servicio, "anadir", de_verdad)
    s.vuelta()
    assert _estados(inter) == ["en_cola", "aplazada", "leyendo", "aplazada"]


def _orden_catalogar_a_las_cinco(tmp_path, monkeypatch, desde):
    hechas = []
    (tmp_path / "foto.jpg").write_bytes(b"x")
    monkeypatch.setattr(catalogador, "datetime", _A_las_cinco)
    monkeypatch.setattr(catalogador, "RESULTADOS", tmp_path / "resultados")
    monkeypatch.setattr(catalogador, "abrir_gestor", lambda: None)
    monkeypatch.setattr(catalogador, "carpeta_imagenes", lambda: tmp_path)
    monkeypatch.setattr(catalogador, "gestor", lambda con, ref: {"imagenes": ["foto.jpg"], "serie_literal": ""})
    monkeypatch.setattr(catalogador, "leer_pistas", dict)
    monkeypatch.setattr(agente, "cliente", lambda: None)
    monkeypatch.setattr(catalogador, "catalogar_una", lambda client, o, args, pistas: hechas.append(o["referencia"]) or 0.0)
    args = SimpleNamespace(solo=["TDP-000001"], lista=None, repetir=False, en_seco=False, paralelo=1,
                           desde=desde, hasta="13:00")
    catalogador.orden_catalogar(args)
    return hechas


def test_catalogar_respeta_desde(tmp_path, monkeypatch):
    assert _orden_catalogar_a_las_cinco(tmp_path, monkeypatch, "06:00") == []
    assert _orden_catalogar_a_las_cinco(tmp_path, monkeypatch, None) == ["TDP-000001"]


def test_catalogar_por_linea_de_ordenes_no_manda_la_serie_conocida(tmp_path, monkeypatch):
    # Las mediciones son ciegas: la orden «catalogar» no manda ninguna serie a la API.
    llamadas = []
    monkeypatch.setattr(catalogador, "MEMORIA", tmp_path / "series.json")
    monkeypatch.setattr(agente, "ocr_ndl", lambda foto: [])
    monkeypatch.setattr(agente, "catalogar", lambda *a, **k: llamadas.append(k) or {
        "ficha": {}, "para_web": F.para_web({}), "coste_eur": 0.0, "fases": "A", "duracion_s": 0})
    o = {"referencia": "TDP-000001", "destino": tmp_path / "TDP-000001.json", "fotos": [tmp_path / "foto.jpg"],
         "gestor": {"alto_cm": 35, "ancho_cm": 24, "serie_literal": "Edo meishô zue", "tienda": {}}}
    args = SimpleNamespace(modelo="m", sin_web=True, esfuerzo="low")
    catalogador.catalogar_una(None, o, args, {})
    assert llamadas and "serie_conocida" not in llamadas[0] and llamadas[0]["series"] == []
