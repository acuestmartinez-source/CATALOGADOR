"""La biblioteca propia: identidad estable, correcciones del Gestor y la instantánea publicada.
Sin API: el agente se sustituye por un doble (el `_montar` de test_servicio)."""
import itertools
import json
import pathlib
import random
import re
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agente  # noqa: E402
import biblioteca  # noqa: E402
import firmas  # noqa: E402
import imagen  # noqa: E402
import servicio  # noqa: E402
from test_servicio import CONTRATOS, _montar  # noqa: E402

FIRMA, SELLO = "bib-63e2dab61519", "bib-bfe4de1b0901"


def _correcciones(inter, *filas):
    """El Gestor reescribe el fichero entero, con su cabecera."""
    cabecera = {"formato": "biblioteca_correcciones", "version": 1, "escrito_por": "identificacion",
                "escrito_en": "2026-10-13T08:55:00Z", "filas": len(filas)}
    (inter / "para_catalogador" / "biblioteca_correcciones.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (cabecera, *filas)), encoding="utf-8")


def _c(n, entrada, accion, lectura=None, nombre=None):
    return {"id_correccion": f"bic-{n:06d}", "id_entrada": entrada, "accion": accion, "lectura": lectura,
            "nombre": nombre, "pedido_en": "2026-10-13T08:50:00Z"}


def _publicadas(inter):
    return servicio.leer_jsonl(inter / "de_catalogador" / "biblioteca.jsonl")


def _sin_buscar_fuera(monkeypatch):
    monkeypatch.setattr(firmas, "buscar", lambda consulta, limite=10: [])  # ni red ni bases ajenas


def test_la_identidad_es_estable_y_la_del_contrato(tmp_path, monkeypatch):
    firma = {"id_peticion": "idn-000001", "referencia": "TDP-008194", "caja": [868, 640, 905, 720]}
    assert biblioteca.identidad("firma", firma) == FIRMA
    assert biblioteca.identidad("sello", {**firma, "caja": [872, 598, 905, 642]}) == SELLO
    assert biblioteca.identidad("firma", {**firma, "caja": [868.0, 640, 905, 720], "lectura": "otra"}) == FIRMA
    assert biblioteca.identidad("sello", firma) != FIRMA and biblioteca.identidad("firma", {**firma, "caja": None}) != FIRMA
    # una fila vieja, sin id_entrada, lo deriva al leer; una línea rota se salta
    inter, imagenes = _montar(tmp_path, monkeypatch)
    biblioteca.TABLA["firma"].parent.mkdir(parents=True)
    vieja = {"referencia": "TDP-008194", "lectura": "國周画", "nombre": "Toyohara Kunichika", "caja": [868, 640, 905, 720],
             "confirmado_por": "belen", "confirmado_en": "2026-10-09T12:30:00Z", "id_peticion": "idn-000001", "recorte": None}
    repetida = {**vieja, "nombre": "Repetida", "confirmado_en": "2026-10-10T08:00:00Z"}  # de antes de la identidad
    biblioteca.TABLA["firma"].write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (vieja, repetida))
                                         + '{"referencia": "TDP-1", "lect', encoding="utf-8")
    biblioteca.CORRECCIONES.write_bytes(b'{"id_correccion": "bic-000009", "id_entrada": "bib-\xe5\x9c')
    leidas = biblioteca.leer("firma")
    assert [f["id_entrada"] for f in leidas] == [FIRMA] and leidas[0]["nombre"] == "Toyohara Kunichika"
    assert biblioteca.anotar("firma", "TDP-008194", "國周画", "Otra", [868, 640, 905, 720], None, "", "idn-000001")["nombre"] \
        == "Toyohara Kunichika"
    assert len(biblioteca.TABLA["firma"].read_text(encoding="utf-8").splitlines()) == 3
    # lo que se anota después de una línea a medias no se pega a ella
    biblioteca.anotar("firma", "TDP-008194", "國周画", "Nueva", [1, 2, 3, 4], None, "", "idn-000001")
    assert [f["nombre"] for f in biblioteca.leer("firma")] == ["Toyohara Kunichika", "Nueva"]


def test_anotar_no_duplica_ni_aunque_se_pierda_servicio_json(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    (tmp_path / "servicio.json").unlink()
    servicio.Servicio(inter, imagenes).vuelta()  # vuelve a leer las aceptadas desde cero
    biblioteca.anotar("firma", "TDP-008194", "國周画", "Otro nombre", [868, 640, 905, 720], None, "x", "idn-000001")
    for tipo, ide in (("firma", FIRMA), ("sello", SELLO)):
        filas = biblioteca.TABLA[tipo].read_text(encoding="utf-8").splitlines()
        assert len(filas) == 1 and json.loads(filas[0])["id_entrada"] == ide
    assert biblioteca.leer("firma")[0]["nombre"] == "Toyohara Kunichika"


def test_retirar_no_borra_y_restaurar_la_devuelve(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _sin_buscar_fuera(monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    tabla = biblioteca.TABLA["firma"].read_bytes()
    assert "TDP-008194" in agente.ejecutar("buscar_firma", {"consulta": "國周画"}, [])

    _correcciones(inter, _c(1, FIRMA, "retirar"))
    servicio.Servicio(inter, imagenes).vuelta()
    assert biblioteca.TABLA["firma"].read_bytes() == tabla  # la tabla no se toca
    assert biblioteca.buscar("firma", "國周画") == [] and biblioteca.leer("firma") == []
    assert "TDP-008194" not in agente.ejecutar("buscar_firma", {"consulta": "國周画"}, [])
    assert biblioteca.leer("firma", con_retiradas=True)[0]["estado"] == "retirada"
    assert biblioteca.resumen() == {"firmas": 0, "sellos": 1, "obras_adjudicadas": 1}
    firma = next(x for x in _publicadas(inter) if x["id_entrada"] == FIRMA)
    assert firma["estado"] == "retirada" and firma["correccion"] == "bic-000001" and firma["original"] is None

    _correcciones(inter, _c(1, FIRMA, "retirar"), _c(2, FIRMA, "restaurar"))
    servicio.Servicio(inter, imagenes).vuelta()
    assert biblioteca.buscar("firma", "國周画")[0]["id_entrada"] == FIRMA
    assert "TDP-008194" in agente.ejecutar("buscar_firma", {"consulta": "國周画"}, [])
    firma = next(x for x in _publicadas(inter) if x["id_entrada"] == FIRMA)
    assert firma["estado"] == "vigente" and firma["correccion"] == "bic-000002"


def test_corregir_lectura_y_nombre_conserva_el_prefijo_y_el_original(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    _correcciones(inter, _c(1, SELLO, "corregir", "越嘉板", "Echizen'ya Kajū"), _c(2, FIRMA, "corregir", None, "Toyohara Kunichika I"),
                  _c(3, FIRMA, "retirar"))
    servicio.Servicio(inter, imagenes).vuelta()
    sello = biblioteca.leer("sello")[0]
    assert sello["nombre"] == "editor: Echizen'ya Kajū" and sello["lectura"] == "越嘉板"
    assert biblioteca.buscar("sello", "板")[0]["id_entrada"] == SELLO  # busca con lo corregido
    publicadas = {x["id_entrada"]: x for x in _publicadas(inter)}
    assert publicadas[SELLO]["nombre"] == "Echizen'ya Kajū" and publicadas[SELLO]["tipo_sello"] == "editor"
    assert publicadas[SELLO]["original"] == {"lectura": "越嘉", "nombre": "Echizenya Kajū"}
    # corregir solo el nombre deja la lectura; retirar después no pierde lo corregido
    firma = publicadas[FIRMA]
    assert firma["lectura"] == "國周画" and firma["nombre"] == "Toyohara Kunichika I" and firma["estado"] == "retirada"
    assert firma["original"] == {"lectura": "國周画", "nombre": "Toyohara Kunichika"} and firma["correccion"] == "bic-000003"


def test_las_correcciones_son_idempotentes_y_una_desconocida_no_revienta(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    filas = [_c(1, FIRMA, "corregir", None, "A"), _c(2, FIRMA, "corregir", None, "B"),
             _c(3, "bib-000000000000", "retirar"),           # no se conoce
             _c(4, FIRMA, "borrar"),                         # acción que no existe
             _c(5, FIRMA, "corregir", "abc", None),          # lectura sin un carácter japonés
             _c(6, FIRMA, "corregir", "國" * 41, None),      # demasiado larga
             _c(7, FIRMA, "corregir", None, "x" * 121),
             _c(8, FIRMA, "corregir", None, None),           # no corrige nada
             _c(9, SELLO, "corregir", "□□", None)]           # □ vale: lo que no se lee
    _correcciones(inter, *filas)
    assert servicio.Servicio(inter, imagenes).corregir_biblioteca() == 3
    registro = biblioteca._jsonl(biblioteca.CORRECCIONES)
    assert [r["id_correccion"] for r in registro] == ["bic-000001", "bic-000002", "bic-000009"]
    assert servicio.leer_hecho()["correcciones"] == [f["id_correccion"] for f in filas]
    assert servicio.Servicio(inter, imagenes).corregir_biblioteca() == 0
    assert servicio.leer_hecho()["correcciones"] == [f["id_correccion"] for f in filas]
    (tmp_path / "servicio.json").unlink()  # aunque se pierda lo hecho, nada se aplica dos veces
    servicio.Servicio(inter, imagenes).vuelta()
    assert len(biblioteca._jsonl(biblioteca.CORRECCIONES)) == 3
    assert biblioteca.leer("firma")[0]["nombre"] == "B" and biblioteca.leer("sello")[0]["lectura"] == "□□"
    assert biblioteca.aplicar(filas[0]) is False and biblioteca.aplicar("basura") is False


def test_solo_se_publica_si_cambia(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    s = servicio.Servicio(inter, imagenes)
    s.vuelta()
    ruta = inter / "de_catalogador" / "biblioteca.jsonl"
    antes = ruta.read_bytes()
    assert s.publicar_biblioteca() is False and ruta.read_bytes() == antes
    cabecera = json.loads(antes.splitlines()[0])
    assert cabecera["formato"] == "biblioteca" and cabecera["escrito_por"] == "catalogador" and cabecera["filas"] == 2
    _correcciones(inter, _c(1, SELLO, "retirar"))
    s.corregir_biblioteca()
    assert s.publicar_biblioteca() is True and ruta.read_bytes() != antes
    assert s.publicar_biblioteca() is False
    ruta.unlink()
    assert s.publicar_biblioteca() is True and ruta.exists()


def test_el_recorte_se_escribe_antes_que_la_linea(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    orden = []
    de_verdad = pathlib.Path.replace

    def apuntando(self, destino):
        orden.append(Path(destino).name)
        return de_verdad(self, destino)

    monkeypatch.setattr(pathlib.Path, "replace", apuntando)
    servicio.Servicio(inter, imagenes).vuelta()
    publicadas = _publicadas(inter)
    assert {x["recorte"] for x in publicadas} == {f"biblioteca/{FIRMA}.jpg", f"biblioteca/{SELLO}.jpg"}
    for x in publicadas:
        assert orden.index(Path(x["recorte"]).name) < orden.index("biblioteca.jsonl")
        with Image.open(inter / "de_catalogador" / x["recorte"]) as im:
            assert im.format == "JPEG" and max(im.size) <= 480
    assert not list((inter / "de_catalogador").rglob("*.parcial"))


def test_la_miniatura_baja_la_calidad_hasta_caber(tmp_path):
    rnd = random.Random(7)
    ruido = Image.frombytes("RGB", (1200, 1200), rnd.randbytes(1200 * 1200 * 3))  # a calidad 85 pasa de 80 KB
    ruido.save(tmp_path / "ruido.png")
    datos = imagen.miniatura(tmp_path / "ruido.png")
    assert len(datos) < 80_000
    (tmp_path / "m.jpg").write_bytes(datos)
    with Image.open(tmp_path / "m.jpg") as im:
        assert im.format == "JPEG" and max(im.size) == 480


def test_lo_publicado_es_ascii_sin_quien_ni_rutas_propias(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    telefono = " ".join(("6" + "00", "0" + "00", "00" + "0"))  # armado a trozos: ni uno de verdad en el repositorio
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    aceptadas.write_text(aceptadas.read_text(encoding="utf-8").replace('"belen"', f'"ana@example.com {telefono}"'),
                         encoding="utf-8")
    _correcciones(inter, _c(1, FIRMA, "corregir", None, "Toyohara Kunichika I"))
    servicio.Servicio(inter, imagenes).vuelta()
    assert telefono in biblioteca.TABLA["firma"].read_text(encoding="utf-8")  # dentro sí está
    texto = (inter / "de_catalogador" / "biblioteca.jsonl").read_text(encoding="ascii")
    assert "confirmado_por" not in texto and "example" not in texto and "@" not in texto
    assert not re.search(r"(?<![\w-])\+?\d[\d ]{7,}\d(?![\w-])", texto)  # ni un teléfono

    def cadenas(v):
        if isinstance(v, dict):
            return [c for x in v.values() for c in cadenas(x)]
        if isinstance(v, list):
            return [c for x in v for c in cadenas(x)]
        return [v] if isinstance(v, str) else []

    for x in _publicadas(inter):
        assert all("datos" not in c and "\\" not in c and "recortes" not in c for c in cadenas(x)), x


def test_el_oro_queda_intacto_y_no_se_publica(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    oro = biblioteca.ORO.read_bytes()
    _correcciones(inter, _c(1, FIRMA, "corregir", "國周", "Otro"), _c(2, SELLO, "retirar"), _c(3, SELLO, "restaurar"))
    servicio.Servicio(inter, imagenes).vuelta()
    assert biblioteca.ORO.read_bytes() == oro
    assert not [p for p in (inter / "de_catalogador").rglob("*") if "oro" in p.name]
    assert "Cortesana" not in (inter / "de_catalogador" / "biblioteca.jsonl").read_text(encoding="ascii")


def test_con_las_aceptadas_del_contrato_sale_el_ejemplo(tmp_path, monkeypatch):
    """El ejemplo del contrato es la instantánea con la primera corrección del ejemplo ya aplicada."""
    inter, imagenes = _montar(tmp_path, monkeypatch)
    ejemplo_c = servicio.leer_jsonl(CONTRATOS / "para_catalogador" / "biblioteca_correcciones.jsonl")
    ejemplo = servicio.leer_jsonl(CONTRATOS / "de_catalogador" / "biblioteca.jsonl")
    _correcciones(inter, ejemplo_c[0])
    servicio.Servicio(inter, imagenes).vuelta()
    publicadas = _publicadas(inter)
    assert [list(x) for x in publicadas] == [list(x) for x in ejemplo]  # las mismas claves, en el mismo orden
    assert publicadas == ejemplo
    _correcciones(inter, *ejemplo_c)  # y la segunda retira el sello
    servicio.Servicio(inter, imagenes).vuelta()
    sello = next(x for x in _publicadas(inter) if x["id_entrada"] == SELLO)
    assert sello["estado"] == "retirada" and sello["correccion"] == "bic-000002"


def test_en_seco_ni_aprende_ni_corrige_ni_publica(tmp_path, monkeypatch, capsys):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _correcciones(inter, _c(1, FIRMA, "retirar"))
    servicio.Servicio(inter, imagenes, en_seco=True).vuelta()
    servicio.Servicio(inter, imagenes, hasta="00:00", en_seco=True).vuelta()  # fuera de hora: no se aplaza nada
    shutil.rmtree(imagenes / "originales" / "TDP-008133")
    servicio.Servicio(inter, imagenes, en_seco=True).vuelta()  # sin fotos: ni error ni petición por hecha
    assert not (tmp_path / "datos").exists() and not (tmp_path / "servicio.json").exists()
    assert not (tmp_path / "series.json").exists() and not (tmp_path / "resultados").exists()
    assert not [p for p in (inter / "de_catalogador").rglob("*") if p.is_file()]
    salida = capsys.readouterr().out
    assert "TDP-008194: se aplazaría" in salida and "TDP-008133: terminaría en error: sin fotos" in salida

    _correcciones(inter)
    servicio.Servicio(inter, imagenes).vuelta()
    foto = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    _correcciones(inter, _c(1, FIRMA, "retirar"))
    foto[inter / "para_catalogador" / "biblioteca_correcciones.jsonl"] = (
        inter / "para_catalogador" / "biblioteca_correcciones.jsonl").read_bytes()
    s = servicio.Servicio(inter, imagenes, en_seco=True)
    assert s.corregir_biblioteca() == 1 and s.publicar_biblioteca() is False
    s.vuelta()
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == foto


def test_la_regla_de_una_correccion_es_la_del_contrato():
    """D-1221: la lista común de ejemplos, la misma que recorre el Gestor con su propia regla."""
    ejemplos = json.loads((CONTRATOS / "lecturas_de_prueba.json").read_text(encoding="utf-8"))
    assert [x for x in ejemplos["lecturas_validas"] if not biblioteca.lectura_valida(x)] == []
    assert [x for x in ejemplos["lecturas_invalidas"] if biblioteca.lectura_valida(x)] == []
    assert [x for x in ejemplos["nombres_validos"] if not biblioteca.nombre_valido(x)] == []
    assert [x for x in ejemplos["nombres_invalidos"] if biblioteca.nombre_valido(x)] == []
    assert not biblioteca.lectura_valida(None) and not biblioteca.nombre_valido(["Kunichika"])


def _reloj(monkeypatch):
    """Cada escritura con su hora: así se ve si la instantánea se reescribió."""
    cuenta = itertools.count()
    monkeypatch.setattr(servicio, "_ahora", lambda: f"2026-10-13T10:00:00.{next(cuenta):06d}Z")


def _escrito_en(inter):
    return json.loads((inter / "de_catalogador" / "biblioteca.jsonl").read_text(encoding="ascii").splitlines()[0])["escrito_en"]


def test_un_recorte_roto_no_republica_en_cada_vuelta(tmp_path, monkeypatch, capsys):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _reloj(monkeypatch)
    s = servicio.Servicio(inter, imagenes)
    s.vuelta()
    (tmp_path / biblioteca.leer("firma")[0]["recorte"]).write_bytes(b"no es un jpeg")
    (inter / "de_catalogador" / "biblioteca" / f"{FIRMA}.jpg").unlink()
    escritos = []
    for _ in range(3):
        s.vuelta()
        escritos.append(_escrito_en(inter))
    assert len(set(escritos)) == 1, escritos  # la primera deja el recorte nulo; las otras dos no reescriben
    publicadas = {x["id_entrada"]: x for x in _publicadas(inter)}
    assert publicadas[FIRMA]["recorte"] is None and publicadas[SELLO]["recorte"] == f"biblioteca/{SELLO}.jpg"
    assert capsys.readouterr().out.count(f"{FIRMA} sin miniatura") == 1  # un aviso, no uno por vuelta


def test_una_miniatura_borrada_vuelve_en_la_siguiente_vuelta(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _reloj(monkeypatch)
    s = servicio.Servicio(inter, imagenes)
    s.vuelta()
    miniatura = inter / "de_catalogador" / "biblioteca" / f"{SELLO}.jpg"
    antes = (inter / "de_catalogador" / "biblioteca.jsonl").read_bytes()
    miniatura.unlink()
    s.vuelta()
    assert miniatura.exists()
    assert (inter / "de_catalogador" / "biblioteca.jsonl").read_bytes() == antes  # la línea ya la citaba


def test_una_tabla_que_no_se_puede_leer_no_es_una_tabla_vacia(tmp_path, monkeypatch, capsys):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    _correcciones(inter, _c(1, FIRMA, "retirar"))
    de_verdad = pathlib.Path.read_bytes

    def falla(self):
        if self.name == "firmas.jsonl":
            raise PermissionError(13, "simulado")
        return de_verdad(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", falla)
    capsys.readouterr()
    assert biblioteca.buscar("firma", "國周画") == []  # una pista que falta no tumba una obra a medio pagar
    assert capsys.readouterr().out == "biblioteca: una tabla no se pudo leer; la búsqueda sigue sin la biblioteca" + chr(10)
    with pytest.raises(OSError):
        servicio.Servicio(inter, imagenes).corregir_biblioteca()
    assert "bic-000001" not in servicio.leer_hecho().get("correcciones", [])  # no queda hecha
    assert not biblioteca.CORRECCIONES.exists()
    monkeypatch.setattr(pathlib.Path, "read_bytes", de_verdad)
    assert servicio.Servicio(inter, imagenes).corregir_biblioteca() == 1  # la vuelta siguiente la aplica
    assert biblioteca.leer("firma") == [] and biblioteca._jsonl(tmp_path / "no_existe.jsonl") == []


def test_lo_que_llega_en_aceptadas_sin_fiarse(tmp_path, monkeypatch, capsys):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    cabecera, buena = json.loads(aceptadas.read_text(encoding="utf-8").splitlines()[0]), servicio.leer_jsonl(aceptadas)[0]
    fuera = {**buena, "id_peticion": "idn-000002", "referencia": "../../fuera"}
    con_texto = {**buena, "id_peticion": "idn-000003", "firma_confirmada": {**buena["firma_confirmada"], "caja": ["x", 640, 905, 720]}}
    sello_raro = {**buena, "id_peticion": "idn-000004", "sellos_confirmados": [{**buena["sellos_confirmados"][0], "caja": [1, 2, 3]}]}
    aceptadas.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (cabecera, fuera, con_texto, sello_raro, buena)),
                         encoding="utf-8")
    servicio.Servicio(inter, imagenes).vuelta()
    # la referencia con «../» tira la línea; una caja con texto o de tres números no: la entrada va sin caja
    cajas = {(t, f["id_peticion"]): f["caja"] for t in ("firma", "sello") for f in biblioteca.leer(t)}
    assert set(cajas) == {(t, i) for t in ("firma", "sello") for i in ("idn-000001", "idn-000003", "idn-000004")}
    assert cajas[("firma", "idn-000003")] is None and cajas[("sello", "idn-000004")] is None
    assert cajas[("firma", "idn-000004")] == [868, 640, 905, 720]
    salida = capsys.readouterr().out
    assert salida.count("aceptadas: una línea fuera del contrato; se salta") == 1
    assert salida.count("aceptadas: una caja fuera del contrato; esa firma o ese sello van sin recorte") == 2
    assert "../" not in salida and "'x'" not in salida  # el aviso es fijo: no repite lo que llegó
    servicio.Servicio(inter, imagenes).vuelta()
    assert "se salta" not in capsys.readouterr().out  # y no se repite en cada vuelta
    # el recorte se llama por su id: una referencia con «../» no escribe fuera de recortes/
    foto = next(imagenes.rglob("*.jpg"))
    fila = biblioteca.anotar("firma", "../../fuera", "國周画", "x", [0, 0, 500, 500], foto, "", "idn-000009")
    assert (biblioteca.RECORTES / f"{fila['id_entrada']}.jpg").exists() and Path(fila["recorte"]).name == f"{fila['id_entrada']}.jpg"
    assert not list(tmp_path.rglob("*fuera*"))


def test_lo_que_ve_el_modelo_no_lleva_quien_confirmo(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    _sin_buscar_fuera(monkeypatch)
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    aceptadas.write_text(aceptadas.read_text(encoding="utf-8").replace('"belen"', '"ana@example.com"'), encoding="utf-8")
    servicio.Servicio(inter, imagenes).vuelta()
    texto = agente.ejecutar("buscar_firma", {"consulta": "國周画"}, [])
    propias = json.loads(texto)["confirmadas_por_el_taller"]
    assert propias and all(set(f) == {"referencia", "lectura", "nombre", "parecido"} for f in propias)
    assert "ana@example.com" not in texto
    assert all("confirmado_por" not in f for f in biblioteca.buscar("firma", "國周画"))


def test_dos_correcciones_seguidas_no_pisan_el_original(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    servicio.Servicio(inter, imagenes).vuelta()
    _correcciones(inter, _c(1, SELLO, "corregir", "越嘉板", "Primero"), _c(2, SELLO, "corregir", None, "Segundo"))
    servicio.Servicio(inter, imagenes).vuelta()
    sello = next(x for x in _publicadas(inter) if x["id_entrada"] == SELLO)
    assert sello["original"] == {"lectura": "越嘉", "nombre": "Echizenya Kajū"}  # el de antes de la primera
    assert (sello["lectura"], sello["nombre"], sello["correccion"]) == ("越嘉板", "Segundo", "bic-000002")
    assert biblioteca.leer("sello")[0]["nombre"] == "editor: Segundo"


def test_una_aceptada_mala_no_congela_la_biblioteca(tmp_path, monkeypatch, capsys):
    """Cajas al revés, degeneradas o fuera de 0-1000, una con decimales, una foto rota y `campos` raros:
    tres vueltas seguidas publican la biblioteca y aplican la corrección pendiente."""
    inter, imagenes = _montar(tmp_path, monkeypatch)
    rota = next((imagenes / "originales" / "TDP-008133").glob("*.jpg"))
    rota.write_bytes(b"\xff\xd8 no es un jpeg entero")  # la foto de idn-000002 no se deja leer
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    cabecera, buena = json.loads(aceptadas.read_text(encoding="utf-8").splitlines()[0]), servicio.leer_jsonl(aceptadas)[0]

    def con(idp, ref, caja_firma, caja_sello, **mas):
        return {**buena, "id_peticion": idp, "referencia": ref, "firma_confirmada": {**buena["firma_confirmada"], "caja": caja_firma},
                "sellos_confirmados": [{**buena["sellos_confirmados"][0], "caja": caja_sello}], **mas}

    lineas = [con("idn-000001", "TDP-008194", [868.0, 640.0, 905.0, 720.0], [900, 900, 100, 100]),  # decimales; al revés
              con("idn-000002", "TDP-008133", [868, 640, 905, 720], [10, 10, 10, 10]),             # foto rota; degenerada
              con("idn-000003", "TDP-000003", [5000, 5000, 6000, 6000], [-50, -50, -10, -10]),     # fuera de 0-1000
              con("idn-000004", "TDP-000004", [False, 0, 900, 900], [0, 0, float("nan"), 900]),    # booleano; no finito
              con("idn-000005", "TDP-000005", None, None, campos="texto"),                          # campos sin forma
              con("idn-000006", "TDP-000006", None, None, campos={"serie": ["x"]})]
    aceptadas.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (cabecera, *lineas)), encoding="utf-8")
    _correcciones(inter, _c(1, FIRMA, "retirar"))
    s = servicio.Servicio(inter, imagenes)
    for _ in range(3):
        s.vuelta()  # ninguna revienta
    publicadas = {(x["id_peticion"], x["tipo"]): x for x in _publicadas(inter)}
    assert set(publicadas) == {(i, t) for i in ("idn-000001", "idn-000002", "idn-000003", "idn-000004") for t in ("firma", "sello")}
    firma = publicadas[("idn-000001", "firma")]
    assert (firma["id_entrada"], firma["caja"], firma["estado"]) == (FIRMA, [868, 640, 905, 720], "retirada")
    assert firma["recorte"] == f"biblioteca/{FIRMA}.jpg"  # la caja con decimales no se pierde
    for clave in (("idn-000001", "sello"), ("idn-000002", "sello"), ("idn-000003", "firma"), ("idn-000003", "sello"),
                  ("idn-000004", "firma"), ("idn-000004", "sello")):
        assert publicadas[clave]["caja"] is None and publicadas[clave]["recorte"] is None, clave
    assert publicadas[("idn-000002", "firma")]["caja"] == [868, 640, 905, 720]
    assert publicadas[("idn-000002", "firma")]["recorte"] is None  # la foto rota: entra sin recorte
    oro = [json.loads(x)["id_peticion"] for x in biblioteca.ORO.read_text(encoding="utf-8").splitlines()]
    assert oro == ["idn-000001", "idn-000002", "idn-000003", "idn-000004"]  # los `campos` sin forma no dejan oro
    salida = capsys.readouterr().out
    assert "biblioteca: un recorte que no se pudo hacer" in salida and rota.name not in salida and "IMAGENES" not in salida


def test_una_linea_de_aceptadas_que_falla_no_tumba_la_vuelta(tmp_path, monkeypatch, capsys):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    clave = "idn-000001:2026-10-09T12:30:00Z"

    def falla(a, foto):
        raise ValueError("un dato raro en /ruta/secreta")

    monkeypatch.setattr(biblioteca, "desde_aceptada", falla)
    servicio.Servicio(inter, imagenes).vuelta()  # no revienta
    assert clave in servicio.leer_hecho()["aceptadas"]  # se da por hecha
    assert (inter / "de_catalogador" / "biblioteca.jsonl").exists()  # y la vuelta siguió hasta publicar
    salida = capsys.readouterr().out
    assert "aceptadas: una línea que no se pudo aprender (ValueError); se da por hecha" in salida and "secreta" not in salida
    # un OSError, en cambio, sube: la vuelta falla y la línea no queda hecha
    (tmp_path / "servicio.json").unlink()
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    cabecera, buena = json.loads(aceptadas.read_text(encoding="utf-8").splitlines()[0]), servicio.leer_jsonl(aceptadas)[0]
    segunda = {**buena, "id_peticion": "idn-000002", "referencia": "TDP-008133"}
    aceptadas.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (cabecera, buena, segunda)), encoding="utf-8")

    def no_se_lee(a, foto):
        if a["id_peticion"] == "idn-000002":
            raise PermissionError(13, "simulado")

    monkeypatch.setattr(biblioteca, "desde_aceptada", no_se_lee)
    with pytest.raises(OSError):
        servicio.Servicio(inter, imagenes).aprender()
    hechas = servicio.leer_hecho()["aceptadas"]
    assert clave in hechas and "idn-000002:2026-10-09T12:30:00Z" not in hechas  # lo de antes, apuntado; esta, no


def test_una_vuelta_que_falla_no_mata_el_servicio(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(servicio, "cargar_env", lambda: None)
    monkeypatch.setattr(servicio, "HECHO", tmp_path / "servicio.json")
    monkeypatch.setattr(servicio.time, "sleep", lambda segundos: None)
    llamadas = []

    def vuelta(self):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise ValueError("una vuelta mala")
        if len(llamadas) == 2:
            return 0
        raise KeyboardInterrupt  # para salir del bucle en la prueba

    monkeypatch.setattr(servicio.Servicio, "vuelta", vuelta)
    argumentos = ["--intercambio", str(tmp_path), "--imagenes", str(tmp_path)]
    with pytest.raises(KeyboardInterrupt):
        servicio.main(argumentos)
    assert len(llamadas) == 3  # tras la vuelta que falló vino otra
    assert capsys.readouterr().out.count("vuelta fallida (ValueError); se intenta otra vez en la siguiente") == 1
    llamadas.clear()
    with pytest.raises(SystemExit) as fin:  # con --una-vez no hay vuelta siguiente: sale con 1
        servicio.main([*argumentos, "--una-vez"])
    assert fin.value.code == 1


def test_la_cola_sin_fiarse(tmp_path, monkeypatch, capsys):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    cola = inter / "para_catalogador" / "cola.jsonl"
    cabecera, buena = json.loads(cola.read_text(encoding="utf-8").splitlines()[0]), servicio.leer_jsonl(cola)[0]
    Image.new("RGB", (300, 400), (230, 220, 200)).save(tmp_path / "secreta.jpg")
    malas = [{**buena, "id_peticion": "../../fuera-id"},
             {**buena, "id_peticion": "idn-000007", "referencia": "../../fuera-ref"},
             {**buena, "id_peticion": "idn-000008", "referencia": "TDP-000008", "imagenes": ["../secreta.jpg"]},
             {**buena, "id_peticion": "idn-000009", "referencia": "TDP-000009", "grupo": ["x"]}]
    cola.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (cabecera, *malas, buena)), encoding="utf-8")
    aceptadas = inter / "para_catalogador" / "aceptadas.jsonl"
    aceptada = servicio.leer_jsonl(aceptadas)[0]
    with aceptadas.open("a", encoding="utf-8") as f:  # lo aceptado de la petición con la imagen de fuera
        f.write(json.dumps({**aceptada, "id_peticion": "idn-000008", "referencia": "TDP-000008"}, ensure_ascii=False) + "\n")
    servicio.Servicio(inter, imagenes).vuelta()
    recortes = {f["id_peticion"]: f["recorte"] for f in biblioteca.leer("firma")}
    assert recortes["idn-000008"] is None and recortes["idn-000001"]  # no recorta una foto de fuera del almacén
    assert [f["id_peticion"] for f in servicio.leer_jsonl(inter / "de_catalogador" / "fichas.jsonl")] == ["idn-000001"]
    assert not list(tmp_path.rglob("*fuera*"))  # ni la foto anotada ni el resultado salen de su carpeta
    salida = capsys.readouterr().out
    assert salida.count("cola: una petición con el id, la referencia o una imagen fuera del contrato; se salta") == 4
    assert "../" not in salida and "secreta" not in salida  # el aviso es fijo
    assert {"../../fuera-id", "idn-000007", "idn-000008", "idn-000009"} <= set(servicio.leer_hecho()["peticiones"])
    servicio.Servicio(inter, imagenes).vuelta()
    assert "se salta" not in capsys.readouterr().out  # se dio por hecha: no se avisa en cada vuelta
