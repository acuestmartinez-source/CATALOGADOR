"""El modo servicio: lee el contrato, escribe el contrato, no repite y aprende de lo aceptado.
Sin API: el agente se sustituye por un doble."""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agente  # noqa: E402
import biblioteca  # noqa: E402
import censor  # noqa: E402
import servicio  # noqa: E402

CONTRATOS = Path(__file__).resolve().parents[1] / "contratos" / "intercambio"


def _montar(tmp_path, monkeypatch):
    inter = tmp_path / "_intercambio"
    shutil.copytree(CONTRATOS, inter)
    (inter / "de_catalogador").mkdir(exist_ok=True)
    for f in (inter / "de_catalogador").glob("*.jsonl"):
        f.unlink()
    (inter / "para_catalogador" / "biblioteca_correcciones.jsonl").unlink()  # cada prueba pone las suyas
    imagenes = tmp_path / "IMAGENES"
    for p in servicio.leer_jsonl(inter / "para_catalogador" / "cola.jsonl"):
        for r in p["imagenes"]:
            (imagenes / r).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (300, 400), (230, 220, 200)).save(imagenes / r)
    monkeypatch.setattr(servicio, "HECHO", tmp_path / "servicio.json")
    monkeypatch.setattr(servicio, "MEMORIA", tmp_path / "series.json")
    monkeypatch.setattr(servicio, "RAIZ", tmp_path)
    bib = tmp_path / "datos" / "biblioteca"
    monkeypatch.setattr(biblioteca, "CARPETA", bib)
    monkeypatch.setattr(biblioteca, "TABLA", {"firma": bib / "firmas.jsonl", "sello": bib / "sellos.jsonl"})
    monkeypatch.setattr(biblioteca, "RECORTES", bib / "recortes")
    monkeypatch.setattr(biblioteca, "ORO", bib / "oro.jsonl")
    monkeypatch.setattr(biblioteca, "CORRECCIONES", bib / "correcciones.jsonl")
    monkeypatch.setattr(biblioteca, "RAIZ", tmp_path)
    monkeypatch.setattr(agente, "ocr_ndl", lambda foto: [{"caja": [0, 0, 1, 1], "texto": "葉うた虎之巻", "confianza": 0.7}])
    monkeypatch.setattr(agente, "cliente", lambda: object())
    ejemplo = servicio.leer_jsonl(CONTRATOS / "de_catalogador" / "fichas.jsonl")[0]

    def falso_catalogar(client, obra, fotos, **kw):
        datos = ejemplo["datos"]
        return {"referencia": obra["referencia"], "modelo": "doble", "fases": "A", "coste_eur": 0.41,
                "ficha": {"tipo_obra": "estampa suelta",
                          "autor": {"nombre": datos["autor"]["valor"], "firma": "國周画", "nivel": "lectura cotejada", "confianza": "alta",
                                    "como": datos["autor"]["como"], "fuentes": datos["autor"]["fuentes"], "cajas": datos["autor"]["cajas"]},
                          "titulo": {"castellano": datos["titulo"]["valor"], "construido": True, "nivel": "construido", "confianza": "media", "como": "…"},
                          "serie": {"castellano": "Hauta tora no maki", "japones": "葉うた虎之巻", "romaji": "Hauta tora no maki",
                                    "nivel": "otra lámina documentada", "confianza": "alta", "fuentes": datos["serie"]["fuentes"]},
                          "editor": {"nombre": "Echizenya Kajū", "sello": "越嘉", "nivel": "lectura cotejada", "confianza": "media"},
                          "censor": {"fecha_desde": 1862, "fecha_hasta": 1863, "nivel": "otra lámina documentada", "confianza": "media"},
                          "tecnica": {"nombre": "Xilografía en color (nishiki-e)", "formato": "ōban tate-e", "confianza": "alta"},
                          "vinculadas": ejemplo["vinculadas"], "buscar_mas": []},
                "para_web": None, "fuentes_verificadas": ejemplo["fuentes_verificadas"], "series_usadas": [m["clave"] for m in kw.get("series") or []]}

    monkeypatch.setattr(agente, "catalogar", falso_catalogar)
    return inter, imagenes


def test_el_servicio_atiende_la_cola_del_contrato_y_escribe_el_contrato(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    s = servicio.Servicio(inter, imagenes)
    assert s.vuelta() == 3  # dos peticiones y una aceptada
    fichas = servicio.leer_jsonl(inter / "de_catalogador" / "fichas.jsonl")
    estados = servicio.leer_jsonl(inter / "de_catalogador" / "estado.jsonl")
    assert [f["id_peticion"] for f in fichas] == ["idn-000001", "idn-000002"]
    ejemplo = servicio.leer_jsonl(CONTRATOS / "de_catalogador" / "fichas.jsonl")[0]
    assert set(fichas[0]) == set(ejemplo)  # las mismas claves que el ejemplo del contrato
    assert set(fichas[0]["datos"]) == set(ejemplo["datos"])
    assert fichas[0]["datos"]["autor"]["fiabilidad"] == "alta" and fichas[0]["datos"]["titulo"]["construido"] is True
    assert fichas[0]["para_web"]["editor"] == "Echizenya Kajū" and fichas[0]["error"] is None
    assert [e["estado"] for e in estados if e["id_peticion"] == "idn-000001"] == ["en_cola", "leyendo", "identificando", "lista"]
    # la cabecera del contrato está
    primera = json.loads((inter / "de_catalogador" / "fichas.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert primera["formato"] == "fichas" and primera["escrito_por"] == "catalogador"
    # la segunda obra del grupo recibió la serie que documentó la primera
    guardado = json.loads((tmp_path / "resultados" / "servicio" / "TDP-008133.json").read_text(encoding="utf-8"))
    assert guardado["series_usadas"] == ["葉うた虎之巻"]
    # la foto anotada está ANTES que su línea, y la lectura de la firma y del sello va en su clave
    assert fichas[0]["anotada"] == "anotadas/idn-000001.jpg"
    with Image.open(inter / "de_catalogador" / fichas[0]["anotada"]) as im:
        assert max(im.size) <= 1100
    assert fichas[0]["datos"]["autor"]["lectura"] == "國周画" and fichas[0]["datos"]["editor"]["lectura"] == "越嘉"
    assert not list((inter / "de_catalogador" / "anotadas").glob("*.parcial"))
    # no repite
    assert servicio.Servicio(inter, imagenes).vuelta() == 0


def test_sin_cajas_no_hay_foto_anotada(tmp_path):
    linea = {"id_peticion": "idn-9", "referencia": "TDP-1", "datos": {"autor": {"cajas": []}}}
    assert servicio.anotar(tmp_path / "no_existe.jpg", linea, tmp_path / "anotadas") is None
    linea["datos"]["autor"]["cajas"] = [[0, 0, 10, 10]]
    assert servicio.anotar(tmp_path / "no_existe.jpg", linea, tmp_path / "anotadas") is None  # no tumba la ficha


def test_el_servicio_aprende_de_lo_aceptado(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    assert biblioteca.resumen() == {"firmas": 1, "sellos": 1, "obras_adjudicadas": 1}
    firma = biblioteca.leer("firma")[0]
    assert firma["nombre"] == "Toyohara Kunichika" and firma["recorte"] and (tmp_path / firma["recorte"]).exists()
    assert biblioteca.buscar("sello", "越□")[0]["nombre"] == "editor: Echizenya Kajū"
    assert biblioteca.buscar("firma", "国周画")[0]["referencia"] == "TDP-008194"  # 国 moderno casa con 國


def _propuesta_guardada(tmp_path, referencia, serie):
    carpeta = tmp_path / "resultados" / "servicio"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{referencia}.json").write_text(json.dumps({"ficha": {"serie": serie}}, ensure_ascii=False), encoding="utf-8")


def _aceptar_serie(inter, estado, valor):
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    cabecera, linea = aceptadas.read_text(encoding="utf-8").splitlines()
    a = json.loads(linea)
    a["campos"]["serie"] = {"estado": estado, "valor": valor}
    a["campos"]["censor"] = {"estado": "aceptado", "valor": "1862–1863"}
    aceptadas.write_text(f"{cabecera}\n{json.dumps(a, ensure_ascii=False)}\n", encoding="utf-8")


def test_la_serie_aceptada_en_romaji_se_aprende_con_sus_kanji_y_lo_que_confirmo_la_persona(tmp_path, monkeypatch):
    # La serie se acepta en rómaji y la memoria se busca por kanji: los kanji salen de la ficha que se propuso
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _propuesta_guardada(tmp_path, "TDP-008194", {"japones": "葉うた虎之巻", "romaji": "Hauta tora no maki",
                                                 "nivel": "construido", "confianza": "baja"})
    servicio.MEMORIA.write_text(json.dumps([{"clave": "葉うた虎之巻", "serie": {"japones": "葉うた虎之巻"}, "autor": "",
                                             "editor": "Ōmiya Kyūjirō", "editor_sello": "", "fecha": "", "fuentes": [],
                                             "vinculadas": [], "obras": ["TDP-008133"]}], ensure_ascii=False), encoding="utf-8")
    _aceptar_serie(inter, "aceptado", "Hauta tora no maki")
    servicio.Servicio(inter, imagenes).aprender()
    memoria = json.loads(servicio.MEMORIA.read_text(encoding="utf-8"))
    assert len(memoria) == 1
    e = memoria[0]
    assert e["serie"]["romaji"] == "Hauta tora no maki" and e["obras"] == ["TDP-008133", "TDP-008194"]
    # lo que confirmó una persona manda sobre lo que se aprendió de una máquina
    assert (e["autor"], e["editor"], e["fecha"]) == ("Toyohara Kunichika", "Echizenya Kajū", "1862–1863")


def test_una_serie_corregida_a_otra_no_se_guarda_con_los_kanji_de_la_propuesta(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _propuesta_guardada(tmp_path, "TDP-008194", {"japones": "葉うた虎之巻", "romaji": "Hauta tora no maki",
                                                 "nivel": "construido", "confianza": "baja"})
    _aceptar_serie(inter, "corregido", "Edo meishô zue")
    servicio.Servicio(inter, imagenes).aprender()
    assert not servicio.MEMORIA.exists() or "葉うた虎之巻" not in servicio.MEMORIA.read_text(encoding="utf-8")


def test_la_propuesta_guardada_de_otra_peticion_no_presta_sus_kanji(tmp_path, monkeypatch):
    # resultados/servicio/<ref>.json va por obra: si es de otra petición con otra serie, sus kanji no valen
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _propuesta_guardada(tmp_path, "TDP-008194", {"japones": "東海道五十三次", "romaji": "Tôkaidô gojûsan tsugi",
                                                 "nivel": "construido", "confianza": "baja"})
    _aceptar_serie(inter, "aceptado", "Hauta tora no maki")
    servicio.Servicio(inter, imagenes).aprender()
    assert not servicio.MEMORIA.exists() or "東海道" not in servicio.MEMORIA.read_text(encoding="utf-8")


def test_ninguna_referencia_vuelve_a_la_api_por_el_saneado():
    for sucio in ("véase TDP-123456", "tdp-123456", "Idn-000001", "TDP 123456", "TDP‑123456", "ＴＤＰ－１２３４５６"):
        assert servicio.texto_limpio(sucio, 120) is None, sucio
    assert servicio.texto_limpio("Toyohara Kunichika", 120)


def test_la_orden_catalogar_ya_no_lee_pistas():
    import catalogador
    assert not hasattr(catalogador, "leer_pistas") and not hasattr(catalogador, "PISTAS")


def test_hora_limite_aplaza_sin_gastar(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    s = servicio.Servicio(inter, imagenes, hasta="00:00")
    s.vuelta()
    estados = servicio.leer_jsonl(inter / "de_catalogador" / "estado.jsonl")
    assert {e["estado"] for e in estados if e["id_peticion"] == "idn-000001"} == {"en_cola", "aplazada"}
    assert not (inter / "de_catalogador" / "fichas.jsonl").exists()


def test_una_peticion_sin_fotos_termina_en_error_y_no_bloquea(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    shutil.rmtree(imagenes / "originales" / "TDP-008133")
    servicio.Servicio(inter, imagenes).vuelta()
    fichas = {f["id_peticion"]: f for f in servicio.leer_jsonl(inter / "de_catalogador" / "fichas.jsonl")}
    assert fichas["idn-000002"]["error"] == "sin fotos en el almacén" and fichas["idn-000001"]["error"] is None


def test_datar_censor():
    assert censor.datar("combinado", "丑")["anos"] == [1865]
    assert censor.datar("aratame_separado", "buey")["anos"] == [1853]
    assert censor.datar("kiwame")["anos"][0] == 1790 and censor.datar("kiwame")["anos"][-1] == 1842
    assert censor.datar("dos_censores", None, None, ["村", "衣笠"])["censores"] == ["Mura", "Kinugasa"]
    assert censor.datar("combinado", "戌")["anos"] == [1862]
    assert "error" in censor.datar("magia")
    assert "error" in censor.datar("combinado", "unicornio")


def test_la_herramienta_del_agente_junta_lo_propio_y_lo_documentado(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca, "TABLA", {"firma": tmp_path / "f.jsonl", "sello": tmp_path / "s.jsonl"})
    monkeypatch.setattr(biblioteca, "RECORTES", tmp_path / "r")
    monkeypatch.setattr(biblioteca, "CORRECCIONES", tmp_path / "c.jsonl")
    biblioteca.anotar("sello", "TDP-1", "越嘉", "editor: Echizenya Kajū", None, None)
    salida = json.loads(agente.ejecutar("buscar_sello_editor", {"consulta": "越嘉"}, []))
    assert salida["confirmadas_por_el_taller"][0]["nombre"] == "editor: Echizenya Kajū"
    assert any(d["editor"] == "Echizenya Kajū" for d in salida["documentadas"])
    assert json.loads(agente.ejecutar("datar_censor", {"tipo": "combinado", "animal": "丑", "mes": 2, "censores": []}, []))["anos"] == [1865]


def test_en_cola_se_escribe_una_vez_aunque_la_peticion_quede_aplazada_muchas_vueltas(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    s = servicio.Servicio(inter, imagenes, hasta="00:00")
    s.vuelta()
    s.vuelta()
    servicio.Servicio(inter, imagenes, hasta="00:00").vuelta()  # otro proceso, mismo estado en disco
    estados = [e["estado"] for e in servicio.leer_jsonl(inter / "de_catalogador" / "estado.jsonl") if e["id_peticion"] == "idn-000001"]
    # «aplazada», una vez por racha y proceso (D-1785): una del primero y otra del segundo
    assert estados.count("en_cola") == 1 and estados.count("aplazada") == 2


def test_un_fallo_no_saca_al_intercambio_rutas_ni_textos_de_la_excepcion(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)

    def revienta(client, obra, fotos, **kw):
        raise RuntimeError(r"Permission denied: \nas\TDP\_intercambio\cola.jsonl {'error': 'cuerpo de la API'}")

    monkeypatch.setattr(agente, "catalogar", revienta)
    servicio.Servicio(inter, imagenes).vuelta()
    texto = (inter / "de_catalogador" / "fichas.jsonl").read_text(encoding="utf-8") + (inter / "de_catalogador" / "estado.jsonl").read_text(encoding="utf-8")
    for prohibido in ("\\nas", "_intercambio", "cola.jsonl", "Permission", "cuerpo de la API"):
        assert prohibido not in texto
    assert "fallo del catalogador (RuntimeError)" in texto
    assert (tmp_path / "resultados" / "servicio" / "TDP-008194.error.txt").read_text(encoding="utf-8").startswith("RuntimeError: Permission denied")
    assert all(ord(c) < 128 for c in texto)  # ASCII puro en el intercambio


def test_motivo_sin_detalles():
    assert "intercambio" in servicio.motivo_sin_detalles(OSError(13, "Permission denied", r"\nas\x"))
    assert "API" in servicio.motivo_sin_detalles(type("APIConnectionError", (Exception,), {})())
    assert servicio.motivo_sin_detalles(ValueError("x")) == "fallo del catalogador (ValueError); mira el registro del contenedor catalogador"


def test_la_ficha_se_escribe_antes_que_su_lista_o_su_error(tmp_path, monkeypatch):
    """Es contrato (LEEME, D-1167 del Gestor): el Gestor no paga dos veces apoyándose en este orden."""
    inter, imagenes = _montar(tmp_path, monkeypatch)
    shutil.rmtree(imagenes / "originales" / "TDP-008133")  # una termina en error y la otra en lista
    orden = []
    de_verdad = servicio.anadir

    def apuntando(ruta, fila, formato):
        orden.append((formato, fila.get("id_peticion"), fila.get("estado")))
        de_verdad(ruta, fila, formato)

    monkeypatch.setattr(servicio, "anadir", apuntando)
    servicio.Servicio(inter, imagenes).vuelta()
    for idp in ("idn-000001", "idn-000002"):
        ficha = next(i for i, o in enumerate(orden) if o[:2] == ("fichas", idp))
        final = next(i for i, o in enumerate(orden) if o[0] == "estado" and o[1] == idp and o[2] in ("lista", "error"))
        assert ficha < final, (idp, orden)
