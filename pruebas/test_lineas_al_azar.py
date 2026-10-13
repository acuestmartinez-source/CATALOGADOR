"""El criterio, fijado: ninguna línea JSON de lo que llega del Gestor tumba una vuelta.

Con una semilla fija, cientos de líneas al azar en `cola.jsonl`, `aceptadas.jsonl` y
`biblioteca_correcciones.jsonl` (anidamiento hondo, sustitutos sueltos, números enormes, tipos cambiados
y rutas largas) entre las líneas buenas del contrato: tres vueltas seguidas no fallan, lo bueno se
atiende, la biblioteca se publica y nada de lo guardado se pierde. Sin API: el agente es el doble de
test_servicio."""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agente  # noqa: E402
import biblioteca  # noqa: E402
import firmas  # noqa: E402
import servicio  # noqa: E402
from test_biblioteca import FIRMA, SELLO, _c  # noqa: E402
from test_servicio import _montar  # noqa: E402

SEMILLA, LINEAS = 1205, 150
CRUDAS = ["[" * 100000 + "]" * 100000,  # anidamiento hondo: RecursionError al leer
          '{"id_peticion": ' + "[" * 3000,  # anidado y roto
          "1" * 5000,  # más cifras de las que json.loads admite
          "NaN", "Infinity", "null", "[]", '"texto"', "{", ""]
RAROS = [None, True, False, 0, -1, 10**400, 1e308, float("nan"), float("inf"), "", " ", "\ud800", "a\udfffb",
         "idn-00000\ud800", "TDP-00000\ud800", "bic-00000\ud800", "a" * 300, "/".join(["b" * 300] * 2), "../" * 40,
         "C:\\x.jpg", "\\\\servidor\\c\\x.jpg", "\x00", "x" * 5000, ["越"], {"x": 1}, [[[[]]]], [0, 0, 10**400, 900],
         [900, 900, 100, 100], [1, 2, 3], ["a", 1, 2, 3], "國周画", "□", "idn-000099", "TDP-000099", "bic-000099",
         "bib-000000000000", "corregir", "retirar", "restaurar", "editor", 12.5, [None], {"serie": ["x"]},
         {"serie": {"estado": "aceptado", "valor": "葉うた虎之巻\ud800"}}]


def _raro(rnd):
    return rnd.choice(RAROS)


def _mutada(rnd, buena: dict) -> dict:
    """Una línea buena con de una a tres claves cambiadas por algo raro (también dentro de firma y sellos)."""
    linea = json.loads(json.dumps(buena))
    for _ in range(rnd.randint(1, 3)):
        clave = rnd.choice([*linea, "firma_confirmada", "sellos_confirmados", "otra"])
        if clave == "firma_confirmada" and isinstance(linea.get(clave), dict) and rnd.random() < 0.7:
            linea[clave][rnd.choice(["lectura", "nombre", "caja", "tipo"])] = _raro(rnd)
        elif clave == "sellos_confirmados" and isinstance(linea.get(clave), list) and linea[clave] and rnd.random() < 0.7:
            linea[clave][0][rnd.choice(["lectura", "nombre", "caja", "tipo"])] = _raro(rnd)
        else:
            linea[clave] = _raro(rnd)
    return linea


def _nueva(rnd, buena: dict, i: int) -> dict:
    """La línea buena con ids nuevos, para que llegue hasta el fondo y no se salte por repetida."""
    linea = json.loads(json.dumps(buena))
    if "id_correccion" in linea:  # nunca sobre FIRMA: la buena la retira y así se comprueba que llegó
        return {**linea, "id_correccion": f"bic-{900000 + i:06d}", "id_entrada": rnd.choice([SELLO, "bib-0123456789ab"]),
                "accion": rnd.choice(["corregir", "retirar", "restaurar"]), "lectura": rnd.choice([None, "越嘉板", "□", "越\ud800"]),
                "nombre": rnd.choice([None, "Otro", "Kaj: Nuevo", "Otro\udfff"])}
    linea.update(id_peticion=f"idn-{900000 + i:06d}", referencia=f"TDP-{900000 + i:06d}")
    if "aceptado_en" in linea:
        linea["aceptado_en"] = f"2026-10-13T10:{i // 60:02d}:{i % 60:02d}Z"
    return linea


def _al_azar(rnd, buena: dict, i: int) -> str:
    tirada = rnd.random()
    if tirada < 0.10:
        return rnd.choice(CRUDAS)
    if tirada < 0.20:
        return json.dumps(_raro(rnd))
    if tirada < 0.30:
        return json.dumps({k: _raro(rnd) for k in rnd.sample(sorted(buena), rnd.randint(1, len(buena)))})
    if tirada < 0.45:
        return json.dumps(_nueva(rnd, buena, i))  # una buena más
    return json.dumps(_mutada(rnd, _nueva(rnd, buena, i)))  # ASCII puro, como el Gestor: los sustitutos van escapados


def test_ninguna_linea_al_azar_tumba_una_vuelta(tmp_path, monkeypatch):
    inter, imagenes = _montar(tmp_path, monkeypatch)
    monkeypatch.setattr(servicio.os, "fsync", lambda fd: None)  # rápida: el disco no es lo que se prueba
    monkeypatch.setattr(firmas, "buscar", lambda consulta, limite=10: [])  # ni red ni bases ajenas
    rnd = random.Random(SEMILLA)
    correcciones = inter / "para_catalogador" / "biblioteca_correcciones.jsonl"
    cabecera_c = {"formato": "biblioteca_correcciones", "version": 1, "escrito_por": "identificacion",
                  "escrito_en": "2026-10-13T08:55:00Z", "filas": 1}
    correcciones.write_text(json.dumps(cabecera_c) + "\n" + json.dumps(_c(1, FIRMA, "retirar")) + "\n", encoding="utf-8")
    buena_aceptada = servicio.leer_jsonl(inter / "para_catalogador" / "aceptadas.jsonl")[0]
    for nombre in ("cola", "aceptadas", "biblioteca_correcciones"):
        ruta = inter / "para_catalogador" / f"{nombre}.jsonl"
        texto = ruta.read_text(encoding="utf-8")
        buena = servicio.leer_jsonl(ruta)[0]
        ruta.write_text(texto + "".join(_al_azar(rnd, buena, i) + "\n" for i in range(LINEAS)), encoding="utf-8")
    with (inter / "para_catalogador" / "aceptadas.jsonl").open("a", encoding="utf-8") as f:  # una serie nueva con un sustituto
        f.write(json.dumps({**_nueva(rnd, buena_aceptada, LINEAS),
                            "campos": {"serie": {"estado": "aceptado", "valor": "広重國周画\ud800"}}}) + "\n")

    s = servicio.Servicio(inter, imagenes)
    for _ in range(2):
        s.vuelta()  # ninguna falla
    servicio.Servicio(inter, imagenes).vuelta()  # tampoco otro proceso con lo guardado en disco

    atendidas = {f["id_peticion"] for f in servicio.leer_jsonl(inter / "de_catalogador" / "fichas.jsonl")}
    assert {"idn-000001", "idn-000002"} <= atendidas  # las buenas se atienden
    texto = (inter / "de_catalogador" / "biblioteca.jsonl").read_text(encoding="ascii")
    lineas = [json.loads(x) for x in texto.splitlines()]
    assert lineas[0]["filas"] == len(lineas) - 1
    assert next(x for x in lineas[1:] if x["id_entrada"] == FIRMA)["estado"] == "retirada"  # la biblioteca se publica
    hecho = (tmp_path / "servicio.json").read_text(encoding="utf-8")
    assert hecho.isascii()
    hecho = json.loads(hecho)
    assert all(servicio.PETICION.fullmatch(x) for x in hecho["peticiones"])
    assert all(servicio.ACEPTADA.fullmatch(x) for x in hecho["aceptadas"])
    assert all(servicio.CORRECCION.fullmatch(x) for x in hecho["correcciones"])
    memoria = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))  # la memoria de series no se pierde
    assert any("葉うた虎之巻" == (m["serie"].get("japones") or "") for m in memoria)
    assert biblioteca.resumen()["firmas"] >= 1 and biblioteca.buscar("sello", "越嘉")
    assert json.loads(agente.ejecutar("buscar_firma", {"consulta": "國周画"}, []))["confirmadas_por_el_taller"]  # el agente busca
