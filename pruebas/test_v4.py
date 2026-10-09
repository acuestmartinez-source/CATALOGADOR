"""La versión depurada: qué se publica, con qué fiabilidad, cuándo hay fase B, la memoria de series,
la agrupación, la hora límite y la medición contra el Gestor."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agente  # noqa: E402
import catalogador  # noqa: E402
import ficha as F  # noqa: E402
import medir  # noqa: E402

FICHA = {
    "autor": {"nombre": "Toyohara Kunichika", "nivel": "lectura cotejada", "confianza": "alta"},
    "titulo": {"castellano": "Cortesana con kamuro en una terraza", "construido": True, "nivel": "construido", "confianza": "media"},
    "serie": {"castellano": "Manual de canciones hauta", "japones": "葉うた虎之巻", "romaji": "Hauta tora no maki",
              "numero_lamina": None, "nivel": "otra lámina documentada", "confianza": "alta",
              "fuentes": ["https://ukiyo-e.org/image/etm/0189204030"]},
    "editor": {"nombre": "Echizenya Kajū", "sello": "越嘉", "nivel": "lectura sin cotejar", "confianza": "media"},
    "censor": {"sello": "redondo", "fecha_desde": 1862, "fecha_hasta": 1863, "nivel": "otra lámina documentada", "confianza": "media"},
    "tecnica": {"nombre": "Xilografía en color (nishiki-e)", "formato": "ōban tate-e", "confianza": "alta"},
    "vinculadas": [{"url": "https://ukiyo-e.org/image/etm/0189204030", "relacion": "otra lámina de la serie"}],
    "buscar_mas": [],
}


def test_fiabilidad_por_nivel_y_confianza():
    assert F.fiabilidad(FICHA, "autor") == "alta"      # lectura cotejada con confianza alta
    assert F.fiabilidad(FICHA, "serie") == "media"     # otra lámina documentada
    assert F.fiabilidad(FICHA, "editor") == "baja"     # lectura sin cotejar
    assert F.fiabilidad(FICHA, "titulo") == "baja"     # construido
    assert F.fiabilidad({"autor": {"nombre": None}}, "autor") == "—"
    assert F.fiabilidad({"autor": {"nombre": "X", "nivel": "ukiyo-e.org misma estampa", "confianza": "baja"}}, "autor") == "alta"


def test_para_web_no_publica_lo_poco_fiable_pero_si_el_titulo_construido():
    web = F.para_web(FICHA)
    assert web["autor"] == "Toyohara Kunichika" and web["autor_fiabilidad"] == "alta"
    assert web["editor"] == "" and web["editor_fiabilidad"] == "—"   # sin cotejar: no se publica
    assert web["titulo"] == "Cortesana con kamuro en una terraza" and web["titulo_construido"] is True
    assert web["serie"] == "Manual de canciones hauta" and web["censor"] == "1862–1863"
    assert web["tecnica"] == "Xilografía en color (nishiki-e)" and web["formato"] == "ōban tate-e"
    assert F.para_web(None)["titulo"] == ""


def test_lee_tambien_las_fichas_antiguas():
    vieja = {"artista": {"nombre": "Utagawa Kunisada", "nivel": "museo otra lámina", "confianza": "alta"},
             "fecha": {"desde": 1847, "hasta": 1852}, "tecnica": "xilografía en color", "formato": {"nombre": "ōban"}}
    assert F.valor(vieja, "autor") == "Utagawa Kunisada"
    assert F.nivel(vieja, "autor") == "otra lámina documentada"
    assert F.valor(vieja, "censor") == "1847–1852"
    assert F.valor(vieja, "tecnica") == "xilografía en color"
    assert F.valor({"censor": {"fecha_desde": 1865, "fecha_hasta": 1865}}, "censor") == "1865"


def test_fase_b_solo_si_el_agente_la_pide_y_no_hay_misma_estampa():
    assert agente.necesita_fase_b(FICHA) == []
    pide = {**FICHA, "buscar_mas": ["editor: confirmar el sello 越嘉 en una ficha de museo"]}
    assert agente.necesita_fase_b(pide) == ["editor: confirmar el sello 越嘉 en una ficha de museo"]
    resuelta = {**pide, "titulo": {"castellano": "X", "nivel": "ukiyo-e.org misma estampa"}}
    assert agente.necesita_fase_b(resuelta) == []
    assert agente.necesita_fase_b(None) == []


def test_memoria_de_series_recuerda_lo_documentado_y_lo_reconoce_en_el_ocr(tmp_path):
    ruta = tmp_path / "series.json"
    assert F.recordar_serie(ruta, FICHA, "TDP-008194")["clave"] == "葉うた虎之巻"
    F.recordar_serie(ruta, FICHA, "TDP-008133")
    memoria = F.leer_memoria(ruta)
    assert len(memoria) == 1 and memoria[0]["obras"] == ["TDP-008133", "TDP-008194"]
    assert memoria[0]["autor"] == "Toyohara Kunichika" and memoria[0]["editor"] == ""  # editor sin cotejar: no se recuerda
    assert F.series_en_texto(memoria, "えこた 葉うた虎之巻 〽はききやらなかに") == memoria
    assert F.series_en_texto(memoria, "国周画") == []
    floja = {**FICHA, "serie": {**FICHA["serie"], "nivel": "lectura sin cotejar"}}
    assert F.recordar_serie(ruta, floja, "TDP-000001") is None


def test_agrupar_pone_juntas_las_de_la_misma_serie():
    def o(ref, serie):
        return {"referencia": ref, "gestor": {"serie_literal": serie}}
    grupos = catalogador.agrupar([o("A", "Hauta tora no maki"), o("B", ""), o("C", "Hauta Tora no Maki"), o("D", "Edo meisho zue")])
    assert [[x["referencia"] for x in g] for g in grupos] == [["A", "C"], ["D"], ["B"]]


def test_hora_limite():
    assert not catalogador.fuera_de_hora(None)
    assert not catalogador.fuera_de_hora("13:00", datetime(2026, 10, 9, 12, 59))
    assert catalogador.fuera_de_hora("13:00", datetime(2026, 10, 9, 13, 0))


def test_medir_desacuerdo_por_campo_y_fiabilidad():
    gestor = {"artista": "Toyohara Kunichika", "serie_literal": "Hauta tora no maki", "editor_literal": "Omiya Kyūjirō",
              "anio": 1863, "anio_literal": "1863"}
    assert medir.comparar(FICHA, gestor) == {"autor": True, "serie": True, "editor": False, "fecha": True}
    t = {x["campo"]: x for x in medir.tasas([(FICHA, gestor), ({}, gestor)])}
    assert t["autor"]["todas"] == "0/1 (0 %)" and t["autor"]["sin_dato_del_agente"] == 1
    assert t["editor"]["baja"] == "1/1 (100 %)"


def test_fila_web_solo_cita_fuentes_verificadas():
    r = {"referencia": "TDP-1", "ficha": FICHA, "tienda": {"id_woo": 81141, "sku": "TDP-toyohara-kunichika-81141"},
         "fuentes_verificadas": {"https://ukiyo-e.org/image/etm/0189204030": "abierta", "https://x.org/a": "nunca vista"}}
    fila = catalogador.fila_web(r)
    assert fila["sku"] == "TDP-toyohara-kunichika-81141" and fila["id_tienda"] == 81141
    assert fila["fuentes"] == "https://ukiyo-e.org/image/etm/0189204030"
    assert fila["editor"] == "" and fila["autor"] == "Toyohara Kunichika"


def test_texto_ocr_quita_la_basura():
    bloques = [{"caja": [0, 0, 1, 1], "texto": "□□□□□□", "confianza": 0.3}, {"caja": [0, 0, 1, 1], "texto": "TZLIN", "confianza": 0.6},
               {"caja": [1, 2, 3, 4], "texto": "葉うた虎之巻", "confianza": 0.7}]
    texto = agente.texto_ocr(bloques)
    assert "葉うた虎之巻" in texto and "TZLIN" not in texto and "□□□" not in texto


def test_extraer_json_coge_el_ultimo_bloque_valido():
    assert agente.extraer_json('x ```json\n{"a": 1}\n``` y ```json\n{"b": 2}\n```') == {"b": 2}
    assert agente.extraer_json("nada") is None
