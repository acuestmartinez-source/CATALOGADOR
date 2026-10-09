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
    imagenes = tmp_path / "IMAGENES"
    for p in servicio.leer_jsonl(inter / "para_catalogador" / "cola.jsonl"):
        for r in p["imagenes"]:
            (imagenes / r).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (300, 400), (230, 220, 200)).save(imagenes / r)
    monkeypatch.setattr(servicio, "HECHO", tmp_path / "servicio.json")
    monkeypatch.setattr(servicio, "MEMORIA", tmp_path / "series.json")
    monkeypatch.setattr(servicio, "RAIZ", tmp_path)
    monkeypatch.setattr(biblioteca, "CARPETA", tmp_path / "biblioteca")
    monkeypatch.setattr(biblioteca, "TABLA", {"firma": tmp_path / "biblioteca" / "firmas.jsonl", "sello": tmp_path / "biblioteca" / "sellos.jsonl"})
    monkeypatch.setattr(biblioteca, "RECORTES", tmp_path / "biblioteca" / "recortes")
    monkeypatch.setattr(biblioteca, "ORO", tmp_path / "biblioteca" / "oro.jsonl")
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
    # no repite
    assert servicio.Servicio(inter, imagenes).vuelta() == 0


def test_el_servicio_aprende_de_lo_aceptado(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    assert biblioteca.resumen() == {"firmas": 1, "sellos": 1, "obras_adjudicadas": 1}
    firma = biblioteca.leer("firma")[0]
    assert firma["nombre"] == "Toyohara Kunichika" and firma["recorte"] and (tmp_path / firma["recorte"]).exists()
    assert biblioteca.buscar("sello", "越□")[0]["nombre"] == "editor: Echizenya Kajū"
    assert biblioteca.buscar("firma", "国周画")[0]["referencia"] == "TDP-008194"  # 国 moderno casa con 國


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
    biblioteca.anotar("sello", "TDP-1", "越嘉", "editor: Echizenya Kajū", None, None)
    salida = json.loads(agente.ejecutar("buscar_sello_editor", {"consulta": "越嘉"}, []))
    assert salida["confirmadas_por_el_taller"][0]["referencia"] == "TDP-1"
    assert any(d["editor"] == "Echizenya Kajū" for d in salida["documentadas"])
    assert json.loads(agente.ejecutar("datar_censor", {"tipo": "combinado", "animal": "丑", "mes": 2, "censores": []}, []))["anos"] == [1865]
