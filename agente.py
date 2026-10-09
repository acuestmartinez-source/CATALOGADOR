"""El agente que identifica una estampa: herramientas, las dos fases, la verificación de fuentes y el coste.

Fase A, barata: lupa, bases de firmas y sellos, y ukiyo-e.org. Sin búsqueda web.
Fase B, solo si hace falta: la misma conversación con búsqueda y lectura web, y solo para lo que el
agente pidió en `buscar_mas`. Si en la fase A ya salió la misma estampa en ukiyo-e.org, no hay B.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path

import ficha as F

RAIZ = Path(__file__).resolve().parent
PROMPT = RAIZ / "piloto" / "prompt.md"
OCR_CACHE = RAIZ / "resultados" / "_ocr"
NDL_OCR = Path(os.environ.get("TDP_NDL_OCR", r"C:\dev\ndlkotenocr-lite"))

MODELO_POR_DEFECTO = "claude-sonnet-5-5"
ESFUERZO = "medium"
MAX_VUELTAS = 30          # peticiones a la API por obra, por si algo se enreda
MAX_REANUDACIONES = 5     # pause_turn del servidor
LADO_AMPLIACION = 1400
TOPES = {"ampliar": 10, "buscar_sello_editor": 6, "buscar_firma": 5, "datar_censor": 3, "ukiyoe_buscar": 3, "ukiyoe_ficha": 4}
WEB_POR_PETICION = 4      # max_uses de la API, que cuenta por petición
WEB_POR_OBRA = 8          # tope de búsquedas, y otro de lecturas, sumando la fase B entera

# USD por millón de tokens: entrada, salida, lectura de caché (octubre de 2026). Escribir en caché: 1,25 × entrada.
PRECIOS = {"claude-sonnet-5-5": (2.0, 10.0, 0.20), "claude-opus-5-5": (4.0, 20.0, 0.20), "claude-haiku-4-5": (1.0, 5.0, 0.10)}
USD_POR_BUSQUEDA = 0.01
EUR_POR_USD = 0.92  # ponytail: tipo fijo; los informes dicen que es aproximado

DOMINIOS_BLOQUEADOS = [
    "artnet.com", "artprice.com", "mutualart.com", "askart.com", "invaluable.com", "liveauctioneers.com",
    "dh-jac.net", "tallerdelprado.com",
    "ukiyo-e.org",  # sí se usa, pero SOLO por ukiyoe.py, que espera entre peticiones y respeta robots.txt
]


def cliente():
    """El cliente de la API. Una clave de organización necesita además ANTHROPIC_WORKSPACE_ID."""
    import anthropic

    secreto = Path(os.environ.get("ANTHROPIC_API_KEY_FILE", "/run/secrets/anthropic_api_key"))
    if not os.environ.get("ANTHROPIC_API_KEY") and secreto.exists():
        os.environ["ANTHROPIC_API_KEY"] = secreto.read_text(encoding="utf-8").strip()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Falta ANTHROPIC_API_KEY en .env (o el secreto de Docker).")
    cabeceras = {}
    if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        cabeceras["anthropic-workspace-id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
    return anthropic.Anthropic(default_headers=cabeceras)


# ---------------------------------------------------------------- herramientas

def _consulta(nombre: str, descripcion: str, campo: str, ayuda: str) -> dict:
    return {"name": nombre, "description": descripcion, "strict": True,
            "input_schema": {"type": "object", "properties": {campo: {"type": "string", "description": ayuda}},
                             "required": [campo], "additionalProperties": False}}


LUPA = {
    "name": "ampliar",
    "description": (
        "Recorte ampliado de una de las fotos, para leer firma, sellos y cartuchos. Coordenadas de 0 a 1000 "
        "(x de izquierda a derecha, y de arriba abajo). «mejora»: «contraste» para papel desvaído, «sin_rojo» si un "
        "sello pisa la tinta, «solo_rojo» para leer un sello rojo, «tinta» para manchas y foxing."),
    "input_schema": {
        "type": "object",
        "properties": {
            "imagen": {"type": "integer", "description": "1 o 2"},
            "x0": {"type": "integer"}, "y0": {"type": "integer"}, "x1": {"type": "integer"}, "y1": {"type": "integer"},
            "mejora": {"type": "string", "enum": ["ninguna", "contraste", "sin_rojo", "solo_rojo", "tinta"]},
        },
        "required": ["imagen", "x0", "y0", "x1", "y1", "mejora"],
        "additionalProperties": False,
    },
    "strict": True,
}
FIRMA = _consulta(
    "buscar_firma",
    "Coteja una firma con 3.456 firmas documentadas (ukiyoesig.net). Pásale lo leído en kanji (□ para lo ilegible) "
    "o un nombre en romaji. Devuelve artista, fechas, firma documentada, lectura, año y URL del ejemplar.",
    "consulta", "caracteres de la firma o nombre del artista")
SELLO = _consulta(
    "buscar_sello_editor",
    "Coteja un sello de editor con 4.020 sellos documentados (ukiyoesig.net). Pásale los caracteres leídos (□ para "
    "lo ilegible) o el nombre del editor. Devuelve editor, kanji, lugar, sello, lectura, fecha, forma y URL.",
    "consulta", "caracteres del sello o nombre del editor")
UKIYOE_BUSCAR = _consulta(
    "ukiyoe_buscar",
    "Búsqueda de texto en ukiyo-e.org (226.973 estampas), la fuente principal. En romaji sin macrones: artista y "
    "serie, o artista y actor. Devuelve id, título, artista y fuente de hasta 24 resultados. Lenta a propósito.",
    "consulta", "términos de búsqueda")
UKIYOE_FICHA = _consulta(
    "ukiyoe_ficha",
    "Abre una ficha de ukiyo-e.org por su id (p. ej. «mfa/sc190207»): título, artista con kanji, fecha, "
    "descripción, enlace al museo y estampas parecidas con su % de coincidencia visual.",
    "id", "id de la ficha")

CENSOR = {
    "name": "datar_censor",
    "description": (
        "Los años posibles según los sellos de censura: tipo (kiwame, un_censor, dos_censores, dos_censores_fecha, "
        "aratame_separado, fecha_sola, combinado, nengo), el animal del zodiaco si lo hay (carácter o nombre) y los "
        "censores nominativos leídos (p. ej. 村, 衣笠). Devuelve la lista de años, no la inventes."),
    "input_schema": {"type": "object", "properties": {
        "tipo": {"type": "string", "enum": ["kiwame", "un_censor", "dos_censores", "dos_censores_fecha", "aratame_separado",
                                           "fecha_sola", "combinado", "nengo"]},
        "animal": {"type": ["string", "null"]}, "mes": {"type": ["integer", "null"]},
        "censores": {"type": "array", "items": {"type": "string"}}},
        "required": ["tipo", "animal", "mes", "censores"], "additionalProperties": False},
    "strict": True,
}

HERRAMIENTAS_A = [LUPA, FIRMA, SELLO, CENSOR, UKIYOE_BUSCAR, UKIYOE_FICHA]
HERRAMIENTAS_B = HERRAMIENTAS_A + [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": WEB_POR_PETICION, "blocked_domains": DOMINIOS_BLOQUEADOS},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": WEB_POR_PETICION, "blocked_domains": DOMINIOS_BLOQUEADOS,
     "max_content_tokens": 6000},
]
ORIGEN = {"buscar_sello_editor": "base documentada", "buscar_firma": "base documentada",
          "ukiyoe_ficha": "abierta", "ukiyoe_buscar": "solo buscador"}


def ampliar(imagenes: list[Path], entrada: dict) -> list[dict]:
    """El recorte que pide el agente, ampliado y tratado; o un texto de error que el agente puede leer."""
    import imagen

    n = int(entrada.get("imagen", 1))
    if not 1 <= n <= len(imagenes):
        return [{"type": "text", "text": f"No hay imagen {n}; hay {len(imagenes)}."}]
    caja = tuple(max(0, min(1000, int(entrada[k]))) for k in ("x0", "y0", "x1", "y1"))
    if caja[2] - caja[0] < 5 or caja[3] - caja[1] < 5:
        return [{"type": "text", "text": "El recuadro es demasiado pequeño o está al revés: x1 > x0 e y1 > y0."}]
    recorte = imagen.ampliar_imagen(imagen.recortar(imagenes[n - 1], caja), LADO_AMPLIACION)
    return [imagen.a_bloque(imagen.mejorar(recorte, entrada.get("mejora") or "ninguna"))]


def ejecutar(nombre: str, entrada: dict, imagenes: list[Path]) -> list[dict] | str:
    """Una herramienta del taller. Devuelve el contenido del tool_result."""
    if nombre == "ampliar":
        return ampliar(imagenes, entrada)
    if nombre in ("buscar_sello_editor", "buscar_firma"):
        import biblioteca

        consulta = str(entrada.get("consulta", ""))
        propias = biblioteca.buscar("sello" if nombre == "buscar_sello_editor" else "firma", consulta)
        if nombre == "buscar_sello_editor":
            import sellos

            filas = sellos.buscar(consulta, limite=8)
            campos = ("editor", "editor_kanji", "lugar", "sello", "lectura", "fecha", "forma_nombre", "fuente")
            vacio = "Ningún sello documentado comparte caracteres con esa lectura."
        else:
            import firmas

            filas = firmas.buscar(consulta, limite=8)
            campos = ("nombre", "nombre_completo", "fechas_artista", "firma", "lectura", "fecha_firma", "fuente")
            vacio = "Ninguna firma documentada coincide: trata tu lectura como no cotejada."
        salida = {"confirmadas_por_el_taller": [{k: f[k] for k in ("referencia", "lectura", "nombre", "parecido")} for f in propias],
                  "documentadas": [{k: f[k] for k in campos} for f in filas]}
        return json.dumps(salida, ensure_ascii=False) if propias or filas else vacio
    if nombre == "datar_censor":
        import censor

        return json.dumps(censor.datar(str(entrada.get("tipo", "")), entrada.get("animal") or None,
                                       entrada.get("mes"), entrada.get("censores") or []), ensure_ascii=False)
    if nombre in ("ukiyoe_buscar", "ukiyoe_ficha"):
        import ukiyoe

        try:
            if nombre == "ukiyoe_buscar":
                filas = ukiyoe.buscar(str(entrada.get("consulta", "")), limite=15)
                return json.dumps(filas, ensure_ascii=False) if filas else "ukiyo-e.org no devuelve nada con esos términos."
            return json.dumps(ukiyoe.ficha(str(entrada.get("id", ""))), ensure_ascii=False)
        except ukiyoe.Parado as e:
            return f"ukiyo-e.org no se consulta más hoy ({e}). Sigue con lo que tienes."
        except Exception as e:  # una ficha que no existe o no se entiende no tumba la obra
            return f"No se pudo leer ukiyo-e.org: {type(e).__name__}: {e}"
    return f"Herramienta desconocida: {nombre}"


# ---------------------------------------------------------------- OCR

def ocr_ndl(foto: Path) -> list[dict]:
    """Bloques de texto leídos por NDL古典籍OCR-Lite, con caja en 0–1000. En caché por foto."""
    import subprocess

    cache = OCR_CACHE / f"{foto.parent.name}_{foto.stem}.json"
    if not cache.exists():
        python = NDL_OCR / ".venv" / "Scripts" / "python.exe"
        if not python.exists():
            raise RuntimeError(f"No encuentro el OCR de la NDL en {NDL_OCR}; pon TDP_NDL_OCR en .env")
        temporal = OCR_CACHE / "_trabajo" / foto.parent.name
        temporal.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(python), "ocr.py", "--sourceimg", str(foto.resolve()), "--output", str(temporal.resolve())],
                       cwd=NDL_OCR / "src", check=True, capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        crudo = json.loads((temporal / f"{foto.stem}.json").read_text(encoding="utf-8"))
        ancho, alto = crudo["imginfo"]["img_width"], crudo["imginfo"]["img_height"]
        bloques = []
        for b in (crudo["contents"][0] if crudo["contents"] else []):
            xs, ys = [q[0] for q in b["boundingBox"]], [q[1] for q in b["boundingBox"]]
            bloques.append({"caja": [min(xs) * 1000 // ancho, min(ys) * 1000 // alto, max(xs) * 1000 // ancho, max(ys) * 1000 // alto],
                            "texto": b.get("text", ""), "confianza": round(float(b.get("confidence", 0)), 2)})
        cache.write_text(json.dumps(bloques, ensure_ascii=False, indent=1), encoding="utf-8")
    return json.loads(cache.read_text(encoding="utf-8"))


def texto_ocr(bloques: list[dict]) -> str:
    # Los bloques de basura (cuadros □ o letras latinas sueltas) no aportan y cuestan tokens.
    utiles = [b for b in bloques if F._cjk(b["texto"]) and b["texto"].count("□") < len(b["texto"]) / 2]
    if not utiles:
        return "Lectura automática (OCR): ningún bloque de texto útil en la foto 1."
    return ("Lectura automática de la foto 1 (OCR de japonés antiguo, NDL古典籍OCR-Lite). Cajas en 0–1000. Es una pista "
            "con errores; no ve sellos ni símbolos sueltos:\n" + "\n".join(f"- {b['caja']} {b['texto']}" for b in utiles))


# ---------------------------------------------------------------- verificación y coste

URL = re.compile(r"https?://[^\s\"'<>;,)\]]+")


def _normal(url: str) -> str:
    return url.rstrip("/.").replace("http://", "https://").replace("://www.", "://")


def verificar_fuentes(ficha: dict | None, vistas: dict[str, str]) -> dict[str, str]:
    """Para cada URL citada en la ficha, cómo llegó a ella el agente: «abierta», «base documentada»,
    «solo buscador» (vista en un resultado y no abierta) o «nunca vista» (no salió de ninguna herramienta)."""
    orden = {"abierta": 0, "base documentada": 1, "solo buscador": 2}
    conocidas: dict[str, str] = {}
    for url, origen in vistas.items():
        clave = _normal(url)
        if clave not in conocidas or orden[origen] < orden[conocidas[clave]]:
            conocidas[clave] = origen
    citadas = {u for u in URL.findall(json.dumps(ficha or {}, ensure_ascii=False)) if "..." not in u}
    return {u: conocidas.get(_normal(u), "nunca vista") for u in sorted(citadas)}


def sumar_uso(total: dict, uso) -> None:
    total["entrada"] += uso.input_tokens or 0
    total["salida"] += uso.output_tokens or 0
    total["cache_escrita"] += getattr(uso, "cache_creation_input_tokens", 0) or 0
    total["cache_leida"] += getattr(uso, "cache_read_input_tokens", 0) or 0
    servidor = getattr(uso, "server_tool_use", None)
    if servidor is not None:
        total["busquedas"] += getattr(servidor, "web_search_requests", 0) or 0
        total["lecturas"] += getattr(servidor, "web_fetch_requests", 0) or 0


def coste_eur(modelo: str, uso: dict) -> float:
    entrada, salida, cache = PRECIOS.get(modelo, PRECIOS[MODELO_POR_DEFECTO])
    usd = (uso["entrada"] * entrada + uso["cache_escrita"] * entrada * 1.25 + uso["cache_leida"] * cache
           + uso["salida"] * salida) / 1_000_000 + uso["busquedas"] * USD_POR_BUSQUEDA
    return round(usd * EUR_POR_USD, 4)


def extraer_json(texto: str) -> dict | None:
    for candidato in reversed(re.findall(r"```json\s*(\{.*?\})\s*```", texto, flags=re.S)):
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            continue
    return None


def necesita_fase_b(ficha: dict | None) -> list[str]:
    """Lo que la fase B debe buscar en la web; vacío si no hay fase B.

    Solo lo que el agente pidió en `buscar_mas`, y nunca si ya salió la misma estampa documentada:
    entonces la web no añade nada que valga el gasto.
    """
    if not ficha:
        return []
    if any(F.nivel(ficha, c) in F.NIVELES[:2] for c in ("autor", "titulo", "serie")):
        return []
    return [str(x) for x in ficha.get("buscar_mas") or [] if str(x).strip()][:4]


# ---------------------------------------------------------------- la obra

def turno(client, intentos: int = 3, **peticion):
    """Una petición en streaming. Si la conexión se corta a mitad, se repite entera: el turno fallido no
    se ha añadido al historial, así que repetirlo no edita nada de lo anterior."""
    import anthropic

    for intento in range(intentos):
        try:
            with client.messages.stream(**peticion) as flujo:
                return flujo.get_final_message()
        except (anthropic.APIConnectionError, anthropic.InternalServerError):
            if intento == intentos - 1:
                raise
        except Exception as e:  # httpx corta el cuerpo a medias con su propio error
            if ("incomplete" not in str(e) and "closed connection" not in str(e)) or intento == intentos - 1:
                raise
        time.sleep(15 * (intento + 1))


def bloque_imagen(ruta: Path) -> dict:
    tipo = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[ruta.suffix.lower()]
    return {"type": "image", "source": {"type": "base64", "media_type": tipo,
                                        "data": base64.standard_b64encode(ruta.read_bytes()).decode("ascii")}}


def catalogar(client, obra: dict, imagenes: list[Path], modelo: str = MODELO_POR_DEFECTO, con_web: bool = True,
              series: list[dict] | None = None, pistas: list[dict] | None = None, esfuerzo: str = ESFUERZO) -> dict:
    """Identifica una obra. `obra` trae referencia y medidas; `series`, las conocidas que aparecen en su OCR;
    `pistas`, lo que una persona encontró a mano (p. ej. la búsqueda por imagen en ukiyo-e.org)."""
    sistema = [{"type": "text", "text": PROMPT.read_text(encoding="utf-8"), "cache_control": {"type": "ephemeral"}}]
    bloques = ocr_ndl(imagenes[0])
    contenido = [bloque_imagen(r) for r in imagenes] + [{"type": "text", "text": texto_ocr(bloques)}]
    if series:
        contenido.append({"type": "text", "text": F.texto_memoria(series)})
    if pistas:
        contenido.append({"type": "text", "text": "Una persona del taller encontró a mano estas páginas; ábrelas antes que "
                          "nada con la herramienta que corresponda (si son de ukiyo-e.org, `ukiyoe_ficha`):\n"
                          + "\n".join(f"- {p['url']} {p.get('nota', '')}" for p in pistas)})
    contenido.append({"type": "text", "text": f"Medidas de la hoja: {obra['alto_cm']} × {obra['ancho_cm']} cm (alto × ancho). "
                      "Identifica la obra siguiendo las reglas."})
    mensajes = [{"role": "user", "content": contenido}]

    uso = dict(entrada=0, salida=0, cache_escrita=0, cache_leida=0, busquedas=0, lecturas=0)
    usos = {k: 0 for k in TOPES}
    vistas: dict[str, str] = {}
    pasos: list[dict] = []
    fase, herramientas, pausas, avisado = "A", HERRAMIENTAS_A, 0, False
    buscar: list[str] = []
    inicio = time.time()
    respuesta = None
    for _ in range(MAX_VUELTAS):
        respuesta = turno(client, model=modelo, max_tokens=16000, system=sistema, thinking={"type": "adaptive"},
                          output_config={"effort": esfuerzo}, tools=herramientas, messages=mensajes)
        sumar_uso(uso, respuesta.usage)
        for b in respuesta.content:
            if b.type == "server_tool_use" and b.name == "web_fetch":
                vistas[b.input.get("url", "")] = "abierta"
                pasos.append({"fase": fase, "herramienta": "web_fetch", "entrada": b.input})
            elif b.type == "server_tool_use" and b.name == "web_search":
                pasos.append({"fase": fase, "herramienta": "web_search", "entrada": b.input})
            elif b.type == "web_search_tool_result" and isinstance(b.content, list):
                for res in b.content:
                    vistas.setdefault(getattr(res, "url", "") or "", "solo buscador")
        mensajes.append({"role": "assistant", "content": respuesta.content})
        if respuesta.stop_reason == "pause_turn" and pausas < MAX_REANUDACIONES:
            pausas += 1
            continue
        if respuesta.stop_reason != "tool_use":
            buscar = necesita_fase_b(extraer_json("\n".join(b.text for b in respuesta.content if b.type == "text")))
            if fase == "B" or not con_web or not buscar:
                break
            # Fase B: la misma conversación, con la web añadida y solo para lo que el agente pidió.
            fase, herramientas = "B", HERRAMIENTAS_B
            mensajes.append({"role": "user", "content": [{"type": "text", "text": (
                "Fase B. Ahora tienes búsqueda y lectura web, como mucho ocho búsquedas y ocho lecturas, SOLO para: "
                + "; ".join(buscar) + ". Prefiere fichas de museos (MFA, Met, Art Institute of Chicago, British Museum, "
                "Rijksmuseum, Library of Congress, Waseda, Biblioteca Nacional de la Dieta, Japan Search) y marchantes "
                "serios. Abre las páginas antes de citarlas. Devuelve la ficha completa otra vez, con `buscar_mas` vacío.")}]})
            continue
        resultados = []
        for b in respuesta.content:
            if b.type != "tool_use":
                continue
            if b.name in TOPES and usos[b.name] < TOPES[b.name]:
                usos[b.name] += 1
                pasos.append({"fase": fase, "herramienta": b.name, "entrada": b.input})
                salida = ejecutar(b.name, b.input, imagenes)
                if isinstance(salida, str) and b.name in ORIGEN:
                    for u in URL.findall(salida):
                        vistas.setdefault(u, ORIGEN[b.name])
                if b.name == "ukiyoe_ficha":
                    vistas[f"https://ukiyo-e.org/image/{str(b.input.get('id', '')).split('/image/')[-1]}"] = "abierta"
                resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": salida})
            else:
                resultados.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                   "content": "Agotado el tope de esta herramienta: sigue con lo que tienes."})
        if fase == "B" and not avisado and (uso["busquedas"] >= WEB_POR_OBRA or uso["lecturas"] >= WEB_POR_OBRA):
            avisado = True
            resultados.append({"type": "text", "text": "Agotado el presupuesto web de esta obra: termina la ficha."})
        mensajes.append({"role": "user", "content": resultados})

    texto = "\n".join(b.text for b in respuesta.content if b.type == "text")
    ficha = extraer_json(texto)
    return {
        "referencia": obra["referencia"],
        "version": "v4",
        "modelo": modelo,
        "esfuerzo": esfuerzo,
        "fases": "A+B" if fase == "B" else "A",
        "ficha": ficha,
        "para_web": F.para_web(ficha),
        "fuentes_verificadas": verificar_fuentes(ficha, vistas),
        "series_usadas": [m["clave"] for m in series or []],
        "parada": respuesta.stop_reason,
        "uso": uso,
        "usos": usos,
        "coste_eur": coste_eur(modelo, uso),
        "pasos": pasos,
        "ocr": bloques,
        "texto": texto,
        "duracion_s": round(time.time() - inicio, 1),
    }
