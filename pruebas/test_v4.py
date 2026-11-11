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


def test_la_confianza_del_modelo_baja_la_fiabilidad_y_nunca_la_sube():
    """D-1842: el nivel pone el techo y la confianza que da el modelo solo puede bajarla."""
    def f(nivel, confianza=None):
        d = {"nombre": "X", "nivel": nivel}
        return F.fiabilidad({"autor": d if confianza is None else {**d, "confianza": confianza}}, "autor")

    assert f("ukiyo-e.org misma estampa", "alta") == "alta"
    assert f("ukiyo-e.org misma estampa", "media") == "media"   # TDP-008117, editor: «lectura probable»
    assert f("museo misma estampa", "baja") == "baja"
    assert f("lectura cotejada", "baja") == "baja"              # TDP-008154, fecha: el periodo del editor
    assert f("otra lámina documentada", "baja") == "baja"       # TDP-008114, editor: sin sello leído
    assert f("marchante", "alta") == "media"
    assert f("lectura sin cotejar", "alta") == "baja"           # TDP-007778, autor: la confianza no sube
    assert f("ukiyo-e.org misma estampa") == "media"            # sin confianza dicha, como mucho media
    assert f("ukiyo-e.org misma estampa", "altísima") == "media"
    sin_sello = {"editor": {"nombre": "Fujiokaya Keijirō", "nivel": "otra lámina documentada", "confianza": "baja"}}
    assert F.para_web(sin_sello)["editor"] == "" and F.para_web(sin_sello)["editor_fiabilidad"] == "—"
    # A las hermanas y a la memoria de series solo pasa lo que se publicaría: tampoco una fecha poco fiable.
    primera = {"serie": {"japones": "江戸名勝図会", "romaji": "Edo meisho zue", "nivel": "museo misma estampa", "confianza": "alta"},
               "autor": {"nombre": "Utagawa Hiroshige II", "nivel": "museo misma estampa", "confianza": "alta"},
               "censor": {"fecha_desde": 1862, "fecha_hasta": 1875, "nivel": "lectura cotejada", "confianza": "baja"}}
    assert F.hermana_de(primera, "TDP-1")["fecha"] == ""
    cotejada = {**primera, "censor": {**primera["censor"], "confianza": "media"}}
    assert F.hermana_de(cotejada, "TDP-1")["fecha"] == "1862–1875"


def test_para_web_no_publica_lo_poco_fiable_pero_si_el_titulo_construido():
    web = F.para_web(FICHA)
    assert web["autor"] == "Toyohara Kunichika" and web["autor_fiabilidad"] == "alta"
    assert web["editor"] == "" and web["editor_fiabilidad"] == "—"   # sin cotejar: no se publica
    assert web["titulo"] == "Cortesana con kamuro en una terraza" and web["titulo_construido"] is True
    assert web["serie"] == "Hauta tora no maki" and web["censor"] == "1862–1863"  # la serie, en rómaji (D-1784)
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


def test_exportar_y_la_revision_recalculan_lo_publicable():
    """D-1842: lo que se guardó al catalogar se calculó con la regla de entonces; lo que sale se calcula hoy."""
    import revision

    ficha = {"autor": {"nombre": "Utagawa Hiroshige II", "nivel": "ukiyo-e.org misma estampa", "confianza": "alta"},
             "editor": {"nombre": "Fujiokaya Keijirō, según JAODB", "nivel": "otra lámina documentada", "confianza": "baja"}}
    viejo = {**F.para_web(ficha), "editor": "Fujiokaya Keijirō, según JAODB", "editor_fiabilidad": "media"}
    r = {"referencia": "TDP-1", "ficha": ficha, "para_web": viejo}
    assert catalogador.fila_web(r)["editor"] == "" and catalogador.fila_web(r)["editor_fiabilidad"] == "—"
    g = {"imagenes": [], "titulo": None, "artista": None, "serie_literal": None, "editor_literal": None,
         "anio": None, "anio_literal": None, "tecnica_literal": None, "alto_cm": 36, "ancho_cm": 25}
    pagina = revision.obra(r, g, Path("."))
    assert "<b>Autor</b>" in pagina and "<b>Editor</b>" not in pagina


def test_texto_ocr_quita_la_basura():
    bloques = [{"caja": [0, 0, 1, 1], "texto": "□□□□□□", "confianza": 0.3}, {"caja": [0, 0, 1, 1], "texto": "TZLIN", "confianza": 0.6},
               {"caja": [1, 2, 3, 4], "texto": "葉うた虎之巻", "confianza": 0.7}]
    texto = agente.texto_ocr(bloques)
    assert "葉うた虎之巻" in texto and "TZLIN" not in texto and "□□□" not in texto


def test_extraer_json_coge_el_ultimo_bloque_valido():
    assert agente.extraer_json('x ```json\n{"a": 1}\n``` y ```json\n{"b": 2}\n```') == {"b": 2}
    assert agente.extraer_json("nada") is None
