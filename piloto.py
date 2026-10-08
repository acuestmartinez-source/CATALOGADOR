"""Piloto de catalogación: 50 estampas japonesas del Gestor, identificadas desde la foto.

Órdenes:
  python piloto.py muestra                       elige las 50 y escribe piloto/muestra.csv
  python piloto.py catalogar [--modelo M] [--sin-web] [--en-seco] [--solo REF ...]
  python piloto.py informe   [--modelo M]

El Gestor (TDP_BASE) y las imágenes (TDP_IMAGENES) se abren en SOLO LECTURA.
Diseño: docs/01_diseno_piloto.md.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import random
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MUESTRA = RAIZ / "piloto" / "muestra.csv"
PROMPT = RAIZ / "piloto" / "prompt.md"
RESULTADOS = RAIZ / "resultados"

MODELO_POR_DEFECTO = "claude-sonnet-5-5"
TAMANO_MUESTRA = 50
SEMILLA = 2026
MAX_BUSQUEDAS = 12  # por obra, sumando todas las peticiones
MAX_LECTURAS = 10
USOS_POR_PETICION = 6  # el max_uses de la API cuenta por petición, no por obra
MAX_CONSULTAS_SELLO = 10
MAX_REANUDACIONES = 5  # pause_turn: el servidor para cada 10 iteraciones y se le dice que siga
MAX_AMPLIACIONES = 16  # la lupa: recortes que puede pedir el agente por obra
MAX_VUELTAS = 40       # tope de peticiones a la API por obra, por si algo se enreda
LADO_AMPLIACION = 1400  # px del lado largo de cada recorte ampliado
NDL_OCR = Path(os.environ.get("TDP_NDL_OCR", r"C:\dev\ndlkotenocr-lite"))
OCR_CACHE = RESULTADOS / "_ocr"

# USD por millón de tokens: entrada, salida, lectura de caché. Precios de octubre de 2026.
PRECIOS = {
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}
USD_POR_BUSQUEDA = 0.01
EUR_POR_USD = 0.92  # ponytail: tipo fijo; el informe dice que es aproximado

# Fuera del piloto por condiciones de uso (decisión P-10 del diseño).
DOMINIOS_BLOQUEADOS = [
    "artnet.com", "artprice.com", "mutualart.com", "askart.com", "invaluable.com",
    "liveauctioneers.com", "dh-jac.net", "tallerdelprado.com",
    "ukiyo-e.org",  # sí se usa, pero SOLO por ukiyoe.py, que espera entre peticiones y respeta robots.txt
]
PISTAS = RAIZ / "piloto" / "pistas.csv"  # referencia;url;nota — lo que una persona encontró a mano (p. ej. en ukiyo-e.org)



# ---------------------------------------------------------------- entorno y Gestor

def cargar_env() -> None:
    fichero = RAIZ / ".env"
    if not fichero.exists():
        return
    for linea in fichero.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def abrir_gestor() -> sqlite3.Connection:
    base = Path(os.environ.get("TDP_BASE", r"C:\dev\GESTOR_TDP\datos\tdp.sqlite"))
    if not base.exists():
        sys.exit(f"No encuentro la base del Gestor en {base}. Pon TDP_BASE en .env.")
    con = sqlite3.connect(f"{base.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def carpeta_imagenes() -> Path:
    carpeta = Path(os.environ.get("TDP_IMAGENES", r"Z:\IMAGENES"))
    if not carpeta.exists():
        sys.exit(f"No encuentro las imágenes en {carpeta}. Pon TDP_IMAGENES en .env.")
    return carpeta


def verdad(con: sqlite3.Connection, referencia: str) -> dict:
    """La ficha del Gestor, que es la verdad contra la que se mide (y que también puede estar mal)."""
    o = con.execute(
        """select o.referencia, o.titulo, o.serie_literal, o.editor_literal, o.anio, o.anio_literal,
                  o.alto_cm, o.ancho_cm, o.tecnica_literal, a.nombre_canonico as artista
           from nuc_obra o left join nuc_artista a on a.id = o.artista_id
           where o.referencia = ?""",
        (referencia,),
    ).fetchone()
    if o is None:
        sys.exit(f"{referencia} no está en el Gestor.")
    imagenes = [
        r["ruta_archivo"]
        for r in con.execute(
            "select ruta_archivo from nuc_imagen where referencia=? and retirada=0 and ruta_archivo is not null"
            " order by principal desc, nombre_fichero",
            (referencia,),
        )
    ]
    tienda = {"id_woo": None, "sku": "", "enlace": "", "es_copia": False, "foto_publica": ""}
    fila = con.execute("select o.id_woo, e.json_wc from nuc_obra o left join web_espejo e on e.id_woo = o.id_woo "
                       "and e.tipo = 'producto' where o.referencia = ?", (referencia,)).fetchone()
    if fila and fila["json_wc"]:
        w = json.loads(fila["json_wc"])
        tienda = {"id_woo": fila["id_woo"], "sku": w.get("sku") or "", "enlace": w.get("permalink") or "",
                  "es_copia": (w.get("slug") or "").startswith("copia"),
                  "foto_publica": ((w.get("images") or [{}])[0] or {}).get("src", "")}
    elif fila:
        tienda["id_woo"] = fila["id_woo"]
    return {**dict(o), "imagenes": imagenes, "tienda": tienda}


# ---------------------------------------------------------------- muestra

def orden_muestra(_args: argparse.Namespace) -> None:
    con = abrir_gestor()
    candidatas = [
        r[0]
        for r in con.execute(
            """select o.referencia from nuc_obra o
               where o.tecnica_literal like '%Moku%'
                 and coalesce(o.editor_literal,'') != ''
                 and (o.anio is not null or coalesce(o.anio_literal,'') != '')
                 and exists (select 1 from nuc_imagen i where i.referencia=o.referencia
                             and i.principal=1 and i.retirada=0 and i.ruta_archivo is not null)
               order by o.referencia"""
        )
    ]
    elegidas = sorted(random.Random(SEMILLA).sample(candidatas, TAMANO_MUESTRA))
    MUESTRA.parent.mkdir(exist_ok=True)
    with MUESTRA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["referencia"])
        w.writerows([r] for r in elegidas)
    print(f"{len(candidatas)} candidatas; {len(elegidas)} elegidas con semilla {SEMILLA} → {MUESTRA}")


def leer_muestra() -> list[str]:
    if not MUESTRA.exists():
        sys.exit("No hay muestra: ejecuta antes `python piloto.py muestra`.")
    with MUESTRA.open(encoding="utf-8") as f:
        return [fila["referencia"] for fila in csv.DictReader(f)]


# ---------------------------------------------------------------- catalogar

def cliente():
    """El cliente de la API. Una clave de organización necesita además ANTHROPIC_WORKSPACE_ID."""
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Falta ANTHROPIC_API_KEY en .env.")
    cabeceras = {}
    if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        cabeceras["anthropic-workspace-id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
    return anthropic.Anthropic(default_headers=cabeceras)


def bloque_imagen(ruta: Path) -> dict:
    tipo = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[ruta.suffix.lower()]
    datos = base64.standard_b64encode(ruta.read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": tipo, "data": datos}}


LUPA = {
    "name": "ampliar",
    "description": (
        "Devuelve un recorte ampliado de una de las fotos. Úsalo para mirar de cerca cada sello (censor, fecha, "
        "editor, grabador, coleccionista), cada símbolo o emblema suelto, cada firma y cada cartucho de texto "
        "antes de transcribirlos. Coordenadas de 0 a 1000 sobre la foto: x de izquierda a derecha, y de arriba "
        "abajo. «mejora» trata la imagen para papel viejo o dañado: «contraste» iguala luces por zonas; "
        "«sin_rojo» borra el rojo para leer la tinta negra que pisa un sello; «solo_rojo» deja solo el sello rojo; "
        "«tinta» binariza para manchas, foxing o tinta desvaída. Ante una lectura dudosa, pide el mismo recorte con "
        "dos mejoras distintas y quédate con lo que coincide."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "imagen": {"type": "integer", "description": "1 para la primera foto, 2 para la segunda"},
            "x0": {"type": "integer"}, "y0": {"type": "integer"},
            "x1": {"type": "integer"}, "y1": {"type": "integer"},
            "mejora": {"type": "string", "enum": ["ninguna", "contraste", "sin_rojo", "solo_rojo", "tinta"]},
            "motivo": {"type": "string", "description": "qué quieres ver: sello de editor, firma, cartucho…"},
        },
        "required": ["imagen", "x0", "y0", "x1", "y1", "mejora", "motivo"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _consulta(nombre: str, descripcion: str, campo: str, ayuda: str) -> dict:
    return {"name": nombre, "description": descripcion, "strict": True,
            "input_schema": {"type": "object", "properties": {campo: {"type": "string", "description": ayuda}},
                             "required": [campo], "additionalProperties": False}}


SELLO_EDITOR = _consulta(
    "buscar_sello_editor",
    "Coteja un sello de editor contra 4.020 sellos documentados (Ukiyo-e Publisher Seal Database, ukiyoesig.net, "
    "formas de Marks). Pásale los caracteres que lees (marca lo ilegible con □) o el nombre del editor. Devuelve "
    "editor, kanji, lugar, texto del sello, lectura, fecha documentada, forma y la URL del ejemplar de museo.",
    "consulta", "caracteres leídos en el sello o nombre del editor")
FIRMA = _consulta(
    "buscar_firma",
    "Coteja una firma contra 3.456 firmas documentadas de 2.145 nombres de artista (Ukiyo-e Signature Sample "
    "Database, ukiyoesig.net). Pásale lo que lees en la firma, en kanji (p. ej. «香蝶楼国貞画»; □ para lo ilegible) "
    "o un nombre en romaji. Devuelve el nombre (gagō), el artista, sus fechas, la firma documentada, su lectura, "
    "el año del ejemplar y la URL del museo. Una lectura que no aparece en la base es una hipótesis.",
    "consulta", "caracteres leídos en la firma o nombre del artista")
UKIYOE_BUSCAR = _consulta(
    "ukiyoe_buscar",
    "Búsqueda de texto en ukiyo-e.org, la fuente principal del taller: 226.973 estampas de museos y marchantes. "
    "Busca en inglés o romaji, sin macrones: artista y serie, o artista y actor y papel (p. ej. «Kunichika Hauta "
    "tora», «Kunisada Kumesaburo Osato»). Devuelve hasta 24 resultados con id, título, artista y fuente. Es lenta "
    "a propósito (espera entre peticiones para no cargar el sitio): haz pocas consultas y bien pensadas.",
    "consulta", "términos de búsqueda")
UKIYOE_FICHA = _consulta(
    "ukiyoe_ficha",
    "Abre una ficha de ukiyo-e.org por su id (p. ej. «mfa/sc190207») y devuelve título, artista con kanji, fecha, "
    "descripción, enlace a la ficha original del museo, fuente y las estampas parecidas con su % de coincidencia "
    "visual. Úsala para confirmar que un resultado es la misma composición y para leer sus datos.",
    "id", "id de la ficha, como aparece en la búsqueda")

TOPES = {"ampliar": MAX_AMPLIACIONES, "buscar_sello_editor": MAX_CONSULTAS_SELLO, "buscar_firma": 8,
         "ukiyoe_buscar": 4, "ukiyoe_ficha": 6}


def herramientas(con_web: bool, con_lupa: bool) -> list[dict]:
    """Siempre las mismas en toda la obra: quitar una rompe la caché y deja huérfanas sus llamadas del historial."""
    lista = [LUPA, SELLO_EDITOR, FIRMA] if con_lupa else []
    if con_web:
        lista += [UKIYOE_BUSCAR, UKIYOE_FICHA,
                  {"type": "web_search_20260209", "name": "web_search", "max_uses": USOS_POR_PETICION,
                   "blocked_domains": DOMINIOS_BLOQUEADOS},
                  {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": USOS_POR_PETICION,
                   "blocked_domains": DOMINIOS_BLOQUEADOS, "max_content_tokens": 8000}]
    return lista


def ejecutar(nombre: str, entrada: dict, imagenes: list[Path]) -> list[dict] | str:
    """Una herramienta del lado del taller. Devuelve el contenido del tool_result."""
    if nombre == "ampliar":
        return ampliar(imagenes, entrada)
    if nombre == "buscar_sello_editor":
        import sellos

        filas = sellos.buscar(str(entrada.get("consulta", "")))
        campos = ("editor", "editor_kanji", "lugar", "sello", "lectura", "fecha", "forma_nombre", "fuente")
        return json.dumps([{k: f[k] for k in campos} for f in filas], ensure_ascii=False) if filas else \
            "Ningún sello de la base comparte caracteres con esa consulta."
    if nombre == "buscar_firma":
        import firmas

        filas = firmas.buscar(str(entrada.get("consulta", "")))
        campos = ("nombre", "nombre_kanji", "nombre_completo", "fechas_artista", "firma", "lectura", "fecha_firma", "fuente")
        return json.dumps([{k: f[k] for k in campos} for f in filas], ensure_ascii=False) if filas else \
            "Ninguna firma documentada coincide: trata tu lectura como hipótesis."
    if nombre in ("ukiyoe_buscar", "ukiyoe_ficha"):
        import ukiyoe

        try:
            if nombre == "ukiyoe_buscar":
                filas = ukiyoe.buscar(str(entrada.get("consulta", "")))
                return json.dumps(filas, ensure_ascii=False) if filas else "ukiyo-e.org no devuelve nada con esos términos."
            return json.dumps(ukiyoe.ficha(str(entrada.get("id", ""))), ensure_ascii=False)
        except ukiyoe.Parado as e:
            return f"ukiyo-e.org no se consulta más hoy ({e}). Sigue con otras fuentes y dilo en «notas»."
        except Exception as e:  # una ficha que no existe o no se entiende no tumba la obra
            return f"No se pudo leer ukiyo-e.org: {type(e).__name__}: {e}"
    return f"Herramienta desconocida: {nombre}"


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


def ocr_ndl(imagen: Path) -> list[dict]:
    """Bloques de texto leídos por NDL古典籍OCR-Lite, con caja en 0–1000. Se guarda en caché por foto."""
    import subprocess

    cache = OCR_CACHE / f"{imagen.parent.name}_{imagen.stem}.json"
    if not cache.exists():
        python = NDL_OCR / ".venv" / "Scripts" / "python.exe"
        if not python.exists():
            raise RuntimeError(f"No encuentro el OCR de la NDL en {NDL_OCR}; pon TDP_NDL_OCR o usa --sin-ocr")
        temporal = OCR_CACHE / "_trabajo" / imagen.parent.name
        temporal.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(python), "ocr.py", "--sourceimg", str(imagen.resolve()), "--output", str(temporal)],
                       cwd=NDL_OCR / "src", check=True, capture_output=True,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        crudo = json.loads((temporal / f"{imagen.stem}.json").read_text(encoding="utf-8"))
        ancho, alto = crudo["imginfo"]["img_width"], crudo["imginfo"]["img_height"]
        bloques = []
        for b in (crudo["contents"][0] if crudo["contents"] else []):
            xs = [q[0] for q in b["boundingBox"]]
            ys = [q[1] for q in b["boundingBox"]]
            bloques.append({
                "caja": [min(xs) * 1000 // ancho, min(ys) * 1000 // alto, max(xs) * 1000 // ancho, max(ys) * 1000 // alto],
                "texto": b.get("text", ""),
                "confianza": round(float(b.get("confidence", 0)), 2),
            })
        cache.write_text(json.dumps(bloques, ensure_ascii=False, indent=1), encoding="utf-8")
    return json.loads(cache.read_text(encoding="utf-8"))


def texto_ocr(bloques: list[dict]) -> str:
    if not bloques:
        return "Lectura automática (OCR): no ha encontrado ningún bloque de texto en la foto 1."
    lineas = [f"- caja {b['caja']} · confianza {b['confianza']}: {b['texto']}" for b in bloques]
    return ("Lectura automática de la foto 1 con NDL古典籍OCR-Lite (OCR de japonés antiguo). Cajas en 0–1000 "
            "(x0, y0, x1, y1). Es una PISTA con errores: a veces lee dibujo como texto, no ve los sellos redondos "
            "ni los símbolos sueltos, y confunde caracteres parecidos. Compruébala con la lupa antes de usarla:\n"
            + "\n".join(lineas))


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
    usd = (
        uso["entrada"] * entrada
        + uso["cache_escrita"] * entrada * 1.25
        + uso["cache_leida"] * cache
        + uso["salida"] * salida
    ) / 1_000_000 + uso["busquedas"] * USD_POR_BUSQUEDA
    return round(usd * EUR_POR_USD, 4)


def extraer_json(texto: str) -> dict | None:
    bloques = re.findall(r"```json\s*(\{.*?\})\s*```", texto, flags=re.S)
    for candidato in reversed(bloques):
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            continue
    return None


URL = re.compile(r"https?://[^\s\"'<>;,)\]]+")


def _normal(url: str) -> str:
    return url.rstrip("/.").replace("http://", "https://").replace("://www.", "://")


def verificar_fuentes(ficha: dict | None, vistas: dict[str, str]) -> dict[str, str]:
    """Para cada URL citada en la ficha, de dónde la sacó el agente.

    «abierta»: la leyó entera (lectura web o ficha de ukiyo-e.org) · «base documentada»: la devolvió
    la base de sellos o de firmas · «solo buscador»: solo la vio en un resultado de búsqueda, sin
    abrirla · «nunca vista»: no salió de ninguna herramienta; puede ser de memoria y no vale como fuente.
    """
    orden = {"abierta": 0, "base documentada": 1, "solo buscador": 2}
    conocidas = {}
    for url, origen in vistas.items():
        clave = _normal(url)
        if clave not in conocidas or orden[origen] < orden[conocidas[clave]]:
            conocidas[clave] = origen
    citadas = {u for u in URL.findall(json.dumps(ficha or {}, ensure_ascii=False)) if "..." not in u}
    return {u: conocidas.get(_normal(u), "nunca vista") for u in sorted(citadas)}


def fuentes_de(r: dict) -> dict[str, str]:
    """La verificación de fuentes de un resultado. Las pasadas anteriores a la verificación no la
    guardaron: se rehace con lo que sí guardaron (lecturas web y consultas a las bases locales, que
    se repiten sin red); lo que no se puede comprobar queda como «no comprobable»."""
    if "fuentes_verificadas" in r:
        return r["fuentes_verificadas"]
    vistas = {u: "abierta" for u in r.get("lecturas") or []}
    for paso in r.get("herramientas_locales") or []:
        nombre, entrada = paso.get("herramienta"), paso.get("entrada") or {}
        if nombre in ("buscar_sello_editor", "buscar_firma"):
            for u in URL.findall(str(ejecutar(nombre, entrada, []))):
                vistas.setdefault(u, "base documentada")
        elif nombre == "ukiyoe_ficha":
            vistas[f"https://ukiyo-e.org/image/{str(entrada.get('id', '')).split('/image/')[-1]}"] = "abierta"
    for consulta in r.get("sellos_consultados") or []:
        for u in URL.findall(str(ejecutar("buscar_sello_editor", {"consulta": consulta}, []))):
            vistas.setdefault(u, "base documentada")
    return {u: ("no comprobable" if o == "nunca vista" else o)
            for u, o in verificar_fuentes(r.get("ficha"), vistas).items()}


def leer_pistas() -> dict[str, list[dict]]:
    """Lo que una persona ha encontrado a mano para una obra: URL y nota, por referencia."""
    if not PISTAS.exists():
        return {}
    pistas: dict[str, list[dict]] = {}
    with PISTAS.open(encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f, delimiter=";"):
            if fila.get("referencia") and fila.get("url"):
                pistas.setdefault(fila["referencia"].strip(), []).append(
                    {"url": fila["url"].strip(), "nota": (fila.get("nota") or "").strip()})
    return pistas


def texto_pistas(pistas: list[dict]) -> str:
    lineas = [f"- {p['url']}" + (f" ({p['nota']})" if p["nota"] else "") for p in pistas]
    return ("Una persona del taller ha buscado esta obra a mano y te deja estas páginas. Léelas ANTES de buscar "
            "nada. Si una de ellas es de ukiyo-e.org e identifica la misma estampa, ese dato manda sobre cualquier "
            "otro: tómalo como fuente principal de artista, título, serie, editor y fecha.\n" + "\n".join(lineas))


def turno(client, intentos: int = 3, **peticion):
    """Una petición en streaming. Si la conexión se corta a mitad, se repite entera: el turno fallido
    no se ha añadido al historial, así que repetirlo no edita nada de lo anterior."""
    import anthropic

    for intento in range(intentos):
        try:
            with client.messages.stream(**peticion) as flujo:
                return flujo.get_final_message()
        except (anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            if intento == intentos - 1:
                raise
            time.sleep(15 * (intento + 1))
        except Exception as e:  # httpx corta el cuerpo a medias con su propio error
            if "incomplete" not in str(e) and "closed connection" not in str(e) or intento == intentos - 1:
                raise
            time.sleep(15 * (intento + 1))


def catalogar_una(client, modelo: str, ficha: dict, imagenes: list[Path], con_web: bool,
                  con_ocr: bool = True, con_lupa: bool = True, pistas: list[dict] | None = None) -> dict:
    sistema = [{"type": "text", "text": PROMPT.read_text(encoding="utf-8"), "cache_control": {"type": "ephemeral"}}]
    medidas = f"Medidas de la hoja: {ficha['alto_cm']} cm de alto por {ficha['ancho_cm']} cm de ancho."
    bloques = ocr_ndl(imagenes[0]) if con_ocr else []
    contenido = [bloque_imagen(r) for r in imagenes]
    if con_ocr:
        contenido.append({"type": "text", "text": texto_ocr(bloques)})
    if pistas and con_web:
        contenido.append({"type": "text", "text": texto_pistas(pistas)})
    pedido = f"{medidas} Propón la ficha catalográfica de esta obra siguiendo las reglas."
    if not con_lupa:
        pedido += " En esta pasada no tienes la herramienta de ampliar: trabaja con las fotos tal cual."
    contenido.append({"type": "text", "text": pedido})

    mensajes = [{"role": "user", "content": contenido}]
    uso = dict(entrada=0, salida=0, cache_escrita=0, cache_leida=0, busquedas=0, lecturas=0, ampliaciones=0,
               consultas_sello=0)
    usos = {k: 0 for k in TOPES}
    vistas: dict[str, str] = {}  # URL -> abierta | base documentada | solo buscador
    consultas, lecturas, ampliaciones, sellos_consultados, locales = [], [], [], [], []
    inicio = time.time()
    respuesta, pausas, avisado, recordado = None, 0, False, not con_web
    for _ in range(MAX_VUELTAS):
        respuesta = turno(client, modelo=modelo, max_tokens=32000, system=sistema, thinking={"type": "adaptive"},
                          output_config={"effort": "high"}, tools=herramientas(con_web, con_lupa), messages=mensajes)
        sumar_uso(uso, respuesta.usage)
        for b in respuesta.content:
            if b.type == "server_tool_use" and b.name == "web_search":
                consultas.append(b.input.get("query", ""))
            elif b.type == "server_tool_use" and b.name == "web_fetch":
                lecturas.append(b.input.get("url", ""))
                vistas[b.input.get("url", "")] = "abierta"
            elif b.type == "web_search_tool_result" and isinstance(b.content, list):
                for res in b.content:
                    vistas.setdefault(getattr(res, "url", "") or "", "solo buscador")
        mensajes.append({"role": "assistant", "content": respuesta.content})
        if respuesta.stop_reason == "pause_turn" and pausas < MAX_REANUDACIONES:
            pausas += 1
            continue
        if respuesta.stop_reason != "tool_use":
            if recordado or usos["ukiyoe_buscar"]:
                break
            # La fuente principal no se salta: si el agente terminó sin mirar ukiyo-e.org, se le pide una vez.
            recordado = True
            mensajes.append({"role": "user", "content": [{"type": "text", "text": (
                "No has consultado ukiyo-e.org, que es la fuente principal del taller. Búscala ahora con "
                "`ukiyoe_buscar` (artista y serie, o artista y actor), abre con `ukiyoe_ficha` los resultados que "
                "puedan ser la misma composición y corrige tu ficha si procede, citando la ficha de ukiyo-e.org. "
                "Termina otra vez con el bloque ```json completo.")}]})
            continue
        resultados = []
        for b in respuesta.content:
            if b.type != "tool_use":
                continue
            if b.name in TOPES and usos[b.name] < TOPES[b.name]:
                usos[b.name] += 1
                locales.append({"herramienta": b.name, "entrada": b.input})
                if b.name == "ampliar":
                    uso["ampliaciones"] += 1
                    ampliaciones.append(b.input)
                elif b.name == "buscar_sello_editor":
                    uso["consultas_sello"] += 1
                    sellos_consultados.append(b.input.get("consulta", ""))
                contenido_tool = ejecutar(b.name, b.input, imagenes)
                if isinstance(contenido_tool, str):
                    origen = {"buscar_sello_editor": "base documentada", "buscar_firma": "base documentada",
                              "ukiyoe_ficha": "abierta", "ukiyoe_buscar": "solo buscador"}.get(b.name)
                    for u in URL.findall(contenido_tool) if origen else []:
                        vistas.setdefault(u, origen)
                    if b.name == "ukiyoe_ficha":  # la ficha abierta y su original del museo, leído por ukiyo-e.org
                        vistas[f"https://ukiyo-e.org/image/{str(b.input.get('id', '')).split('/image/')[-1]}"] = "abierta"
                resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": contenido_tool})
            else:
                resultados.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                   "content": "Agotado el tope de esta herramienta: sigue con lo que tienes."})
        if con_web and not avisado and (uso["busquedas"] >= MAX_BUSQUEDAS or uso["lecturas"] >= MAX_LECTURAS):
            avisado = True
            resultados.append({"type": "text", "text": "Has agotado el presupuesto de búsquedas y lecturas web de "
                               "esta obra: no busques ni leas más en la web y termina la ficha con lo que tienes."})
        mensajes.append({"role": "user", "content": resultados})
    texto = "\n".join(b.text for b in respuesta.content if b.type == "text")
    ficha_agente = extraer_json(texto)
    return {
        "referencia": ficha["referencia"],
        "modelo": modelo,
        "con_web": con_web,
        "con_ocr": con_ocr,
        "con_lupa": con_lupa,
        "ficha": ficha_agente,
        "fuentes_verificadas": verificar_fuentes(ficha_agente, vistas),
        "texto": texto,
        "parada": respuesta.stop_reason,
        "uso": uso,
        "coste_eur": coste_eur(modelo, uso),
        "consultas": consultas,
        "lecturas": lecturas,
        "ampliaciones": ampliaciones,
        "sellos_consultados": sellos_consultados,
        "herramientas_locales": locales,
        "usos": usos,
        "ocr": bloques,
        "duracion_s": round(time.time() - inicio, 1),
    }


def nombre_pasada(modelo: str, sin_web: bool, sin_ocr: bool, sin_lupa: bool) -> str:
    """La carpeta de resultados dice cómo se hizo la pasada. Sin sufijos: la v2 completa."""
    return modelo + "_v3" + "_sin_web" * sin_web + "_sin_ocr" * sin_ocr + "_sin_lupa" * sin_lupa


def orden_catalogar(args: argparse.Namespace) -> None:
    from concurrent.futures import ThreadPoolExecutor

    con = abrir_gestor()
    carpeta = carpeta_imagenes()
    referencias = args.solo or leer_muestra()
    salida = RESULTADOS / nombre_pasada(args.modelo, args.sin_web, args.sin_ocr, args.sin_lupa)
    salida.mkdir(parents=True, exist_ok=True)
    client = None if args.en_seco else cliente()
    pistas = leer_pistas()

    trabajos, saltadas = [], 0
    for ref in referencias:
        destino = salida / f"{ref}.json"
        if destino.exists() and not args.repetir:
            saltadas += 1
            continue
        ficha = verdad(con, ref)
        imagenes = [carpeta / r for r in ficha["imagenes"][:2] if (carpeta / r).exists()]
        if not imagenes:
            print(f"{ref}: sin imagen en {carpeta}; se salta")
            continue
        if args.en_seco:
            print(f"{ref}: {len(imagenes)} imagen(es), {ficha['alto_cm']}x{ficha['ancho_cm']} cm -> {destino.name}")
            continue
        trabajos.append((ref, ficha, imagenes, destino))

    def una(trabajo) -> float:
        ref, ficha, imagenes, destino = trabajo
        for intento in range(3):
            try:
                r = catalogar_una(client, args.modelo, ficha, imagenes, not args.sin_web, not args.sin_ocr,
                                  not args.sin_lupa, pistas.get(ref))
                break
            except OSError as e:  # el NAS se corta a veces unos segundos: se espera y se repite
                if intento == 2:
                    print(f"{ref}: ERROR {type(e).__name__}: {e}", flush=True)
                    return 0.0
                print(f"{ref}: el NAS no responde ({e}); se repite en {60 * (intento + 1)} s", flush=True)
                time.sleep(60 * (intento + 1))
            except Exception as e:  # la obra que falla se apunta y se sigue; no se guarda y la próxima pasada la reintenta
                print(f"{ref}: ERROR {type(e).__name__}: {e}", flush=True)
                return 0.0
        destino.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{ref}: {r['coste_eur']:.2f} € · {r['uso']['busquedas']} búsq. · {r['uso']['ampliaciones']} ampl. · "
              f"{r['duracion_s']} s" + ("" if r["ficha"] else " · SIN JSON"), flush=True)
        return r["coste_eur"]

    with ThreadPoolExecutor(max_workers=args.paralelo) as hilos:
        total_eur = sum(hilos.map(una, trabajos))
    print(f"\n{len(trabajos)} intentadas, {saltadas} ya hechas, {total_eur:.2f} € esta pasada -> {salida}")


# ---------------------------------------------------------------- identificar (fotos sueltas)

def orden_identificar(args: argparse.Namespace) -> None:
    """Una estampa cualquiera, con tus fotos: no toca el Gestor ni la muestra."""
    imagenes = [Path(r) for r in args.imagenes]
    for r in imagenes:
        if not r.exists():
            sys.exit(f"No encuentro {r}")
    alto, ancho = (float(x.replace(",", ".")) for x in args.medidas.lower().split("x"))
    ficha = {"referencia": args.nombre or imagenes[0].stem, "alto_cm": alto, "ancho_cm": ancho}
    salida = RESULTADOS / "sueltas"
    salida.mkdir(parents=True, exist_ok=True)
    pistas = [{"url": u, "nota": ""} for u in (args.pista or [])]
    resultado = catalogar_una(cliente(), args.modelo, ficha, imagenes, not args.sin_web, not args.sin_ocr, True, pistas)
    destino = salida / f"{ficha['referencia']}.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(resultado["texto"])
    print(f"\n{resultado['coste_eur']:.2f} € · {resultado['uso']['busquedas']} búsquedas · "
          f"{resultado['uso']['lecturas']} lecturas · {resultado['duracion_s']} s → {destino}")


# ---------------------------------------------------------------- informe

GENERACION = {"ii", "iii", "iv", "2", "3", "4"}


def normalizar(texto: str | None) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", texto).strip()


def _alias(nombre: str) -> list[set[str]]:
    """'Utagawa Kunisada (Toyokuni III)' → [{utagawa,kunisada}, {toyokuni,iii}]."""
    parentesis = re.findall(r"\(([^)]*)\)", nombre or "")
    base = re.sub(r"\([^)]*\)", " ", nombre or "")
    return [set(normalizar(t).split()) for t in [base, *parentesis] if normalizar(t)]


def _mismo_conjunto(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    chico, grande = (a, b) if len(a) < len(b) else (b, a)
    return chico <= grande and not (grande - chico) & GENERACION


def mismo_artista(gestor: str | None, agente: str | None) -> bool:
    return any(_mismo_conjunto(x, y) for x in _alias(gestor or "") for y in _alias(agente or ""))


def mismo_editor(gestor: str | None, agente: str | None) -> bool:
    """Coincide si un nombre contiene al otro, sin espacios ni guiones (Tsuta-ya Kichizō = Tsutaya Kichizo)."""
    a, b = normalizar(gestor).replace(" ", ""), normalizar(agente).replace(" ", "")
    if a and b and (a in b or b in a):
        return True
    # Nombre comercial con o sin «ya» (Kato Seibei = Katōya Seibei): todas las palabras del Gestor en el agente.
    def palabras(texto):
        return {re.sub(r"ya$", "", w) for w in normalizar(texto).split() if len(w) >= 3}
    g, ag = palabras(gestor), palabras(agente)
    return len(g) >= 2 and g <= ag


def rango_anio(anio: int | None, literal: str | None) -> tuple[int, int] | None:
    if anio:
        return (int(anio), int(anio))
    numeros = [int(n) for n in re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", literal or "")]
    if not numeros:
        return None
    holgura = 3 if re.search(r"circa|ca\.|c\.|hacia|aprox", literal or "", re.I) else 0
    return (min(numeros) - holgura, max(numeros) + holgura)


def mismo_anio(gestor: tuple[int, int] | None, agente: tuple[int | None, int | None] | None, tolerancia: int = 2) -> bool:
    if not gestor or not agente or agente[0] is None and agente[1] is None:
        return False
    desde = agente[0] if agente[0] is not None else agente[1]
    hasta = agente[1] if agente[1] is not None else agente[0]
    return desde - tolerancia <= gestor[1] and hasta + tolerancia >= gestor[0]


def _campo(ficha: dict | None, *ruta, defecto=None):
    actual = ficha or {}
    for paso in ruta:
        if not isinstance(actual, dict):
            return defecto
        actual = actual.get(paso)
    return defecto if actual is None else actual


def filas_de(carpeta: Path, con: sqlite3.Connection) -> list[dict]:
    """Solo las obras de la muestra: las demás no tienen en el Gestor una ficha con la que medir."""
    muestra = set(leer_muestra())
    filas = []
    for fichero in sorted(carpeta.glob("TDP-*.json")):
        if fichero.stem not in muestra:
            continue
        r = json.loads(fichero.read_text(encoding="utf-8"))
        v = verdad(con, r["referencia"])
        f = r.get("ficha")
        fecha_agente = (_campo(f, "fecha", "desde"), _campo(f, "fecha", "hasta"))
        sellos_leidos = _campo(f, "sellos", defecto=[]) or []
        filas.append({
            "referencia": r["referencia"],
            "error": r.get("error", "" if f else "sin JSON"),
            "tipo_obra": _campo(f, "tipo_obra", defecto="") or "",
            "artista_gestor": v["artista"] or "",
            "artista_agente": _campo(f, "artista", "nombre", defecto="") or "",
            "conf_artista": _campo(f, "artista", "confianza", defecto="") or "",
            "acierto_artista": mismo_artista(v["artista"], _campo(f, "artista", "nombre")),
            "editor_gestor": v["editor_literal"] or "",
            "editor_agente": _campo(f, "editor", "nombre", defecto="") or "",
            "conf_editor": _campo(f, "editor", "confianza", defecto="") or "",
            "sello_editor_leido": (_campo(f, "editor", "sello_lectura", defecto="")
                                   or _campo(f, "editor", "sello_leido", defecto="") or ""),
            "acierto_editor": mismo_editor(v["editor_literal"], _campo(f, "editor", "nombre")),
            "anio_gestor": v["anio"] or v["anio_literal"] or "",
            "fecha_agente": f"{fecha_agente[0] or ''}-{fecha_agente[1] or ''}" if f else "",
            "metodo_fecha": _campo(f, "fecha", "metodo", defecto="") or "",
            "acierto_anio": mismo_anio(rango_anio(v["anio"], v["anio_literal"]), fecha_agente),
            "titulo_gestor": v["titulo"] or "",
            "titulo_agente": (_campo(f, "titulo", "castellano", defecto="")
                              or _campo(f, "titulo", "romaji", defecto="") or ""),
            "adjudicacion_titulo": "",
            "serie_gestor": v["serie_literal"] or "",
            "serie_agente": (_campo(f, "serie", "romaji", defecto="")
                             or _campo(f, "serie", "castellano", defecto="") or ""),
            "conf_serie": _campo(f, "serie", "confianza", defecto="") or "",
            "adjudicacion_serie": "",
            "sellos_leidos": len(sellos_leidos),
            "kabuki": bool(_campo(f, "kabuki", "obra") or _campo(f, "kabuki", "actores")),
            "obra_mayor": _campo(f, "obra_mayor", "titulo", defecto="") or "",
            "ejemplares": len(_campo(f, "ejemplares", defecto=[]) or []),
            "busquedas": _campo(r, "uso", "busquedas", defecto=0),
            "ampliaciones": _campo(r, "uso", "ampliaciones", defecto=0),
            "coste_eur": r.get("coste_eur", 0.0),
            "duracion_s": r.get("duracion_s", ""),
        })
    return filas


def metricas(filas: list[dict]) -> dict[str, str]:
    validas = [x for x in filas if not x["error"]]

    def tasa(clave, sub):
        return f"{sum(1 for x in sub if x[clave])}/{len(sub)}" if sub else "0/0"

    altas = [x for x in validas if x["conf_artista"] == "alta"]
    editor_alto = [x for x in validas if x["conf_editor"] in ("alta", "media")]
    coste = sum(x["coste_eur"] for x in filas)
    n = max(1, len(filas))
    return {
        "Obras con ficha": f"{len(validas)}/{len(filas)}",
        "Artista": tasa("acierto_artista", validas),
        "Artista, con confianza alta": tasa("acierto_artista", altas),
        "Editor": tasa("acierto_editor", validas),
        "Editor, con confianza alta o media": tasa("acierto_editor", editor_alto),
        "Año (±2)": tasa("acierto_anio", validas),
        "Serie dada con confianza alta": f"{sum(1 for x in validas if x['conf_serie'] == 'alta')}/{len(validas)}",
        "Sellos leídos por obra (media)": f"{sum(x['sellos_leidos'] for x in validas) / max(1, len(validas)):.1f}",
        "Coste por obra": f"{coste / n:.2f} €",
        "Coste total": f"{coste:.2f} €",
        "Duración media": f"{sum(float(x['duracion_s'] or 0) for x in filas) / n:.0f} s",
    }


def orden_informe(args: argparse.Namespace) -> None:
    con = abrir_gestor()
    carpeta = RESULTADOS / args.modelo
    filas = filas_de(carpeta, con)
    if not filas:
        sys.exit(f"No hay resultados en {carpeta}.")
    with (carpeta / "resumen.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(filas)

    validas = [x for x in filas if not x["error"]]
    lineas = [f"# Informe del piloto · `{args.modelo}`", "", "| Medida | Valor |", "|---|---|"]
    lineas += [f"| {k} | {v} |" for k, v in metricas(filas).items()]
    lineas += [
        "",
        f"Coste a {EUR_POR_USD} €/USD, aproximado. Título y serie no se comparan solos: "
        "rellena `adjudicacion_titulo` y `adjudicacion_serie` en `resumen.csv`.",
        "",
        "Errores: " + (", ".join(f"{x['referencia']} ({x['error']})" for x in filas if x["error"]) or "ninguno"),
        "",
        "## Discrepancias con el Gestor (mirar quién tiene razón)",
        "",
        "| Obra | Campo | Gestor | Agente | Confianza |",
        "|---|---|---|---|---|",
    ]
    for x in validas:
        if not x["acierto_artista"]:
            lineas.append(f"| {x['referencia']} | artista | {x['artista_gestor']} | {x['artista_agente']} | {x['conf_artista']} |")
        if not x["acierto_editor"]:
            lineas.append(f"| {x['referencia']} | editor | {x['editor_gestor']} | {x['editor_agente']} "
                          f"(sello {x['sello_editor_leido'] or '—'}) | {x['conf_editor']} |")
    texto = "\n".join(lineas) + "\n"
    (carpeta / "informe.md").write_text(texto, encoding="utf-8")
    print(texto)
    print(f"-> {carpeta / 'informe.md'} y {carpeta / 'resumen.csv'}")


def orden_comparar(args: argparse.Namespace) -> None:
    """Dos pasadas sobre las mismas obras, lado a lado."""
    con = abrir_gestor()
    a = filas_de(RESULTADOS / args.a, con)
    b = filas_de(RESULTADOS / args.b, con)
    comunes = {x["referencia"] for x in a} & {x["referencia"] for x in b}
    ma = metricas([x for x in a if x["referencia"] in comunes])
    mb = metricas([x for x in b if x["referencia"] in comunes])
    print(f"Sobre las {len(comunes)} obras que tienen las dos pasadas")
    print()
    print(f"| Medida | {args.a} | {args.b} |")
    print("|---|---|---|")
    for k in ma:
        print(f"| {k} | {ma[k]} | {mb[k]} |")


# ---------------------------------------------------------------- entrada

def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cargar_env()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="orden", required=True)
    sub.add_parser("muestra").set_defaults(f=orden_muestra)
    c = sub.add_parser("catalogar")
    c.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    c.add_argument("--sin-web", action="store_true", help="solo visión, sin búsqueda ni lectura web")
    c.add_argument("--en-seco", action="store_true", help="lista lo que haría sin llamar a la API")
    c.add_argument("--solo", nargs="*", metavar="REF", help="solo estas referencias")
    c.add_argument("--sin-ocr", action="store_true", help="sin la lectura previa del OCR de la NDL")
    c.add_argument("--sin-lupa", action="store_true", help="sin la herramienta de ampliar")
    c.add_argument("--paralelo", type=int, default=4, help="obras a la vez (por defecto 4)")
    c.add_argument("--repetir", action="store_true", help="vuelve a hacer las obras que ya tienen resultado")
    c.set_defaults(f=orden_catalogar)
    d = sub.add_parser("identificar", help="una estampa con tus propias fotos, fuera del Gestor")
    d.add_argument("imagenes", nargs="+", metavar="FOTO", help="una o varias fotos (la primera, la hoja entera)")
    d.add_argument("--medidas", required=True, metavar="ALTOxANCHO", help="en cm, p. ej. 35x24.4")
    d.add_argument("--nombre", help="nombre del resultado (por defecto, el de la primera foto)")
    d.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    d.add_argument("--sin-web", action="store_true")
    d.add_argument("--sin-ocr", action="store_true")
    d.add_argument("--pista", nargs="*", metavar="URL", help="páginas encontradas a mano (p. ej. el resultado de ukiyo-e.org)")
    d.set_defaults(f=orden_identificar)
    i = sub.add_parser("informe")
    i.add_argument("--modelo", default=MODELO_POR_DEFECTO + "_v3", help="carpeta de resultados (p. ej. claude-sonnet-5-5_v2)")
    i.set_defaults(f=orden_informe)
    k = sub.add_parser("comparar", help="dos carpetas de resultados lado a lado")
    k.add_argument("a")
    k.add_argument("b")
    k.set_defaults(f=orden_comparar)
    args = p.parse_args(argv)
    args.f(args)


if __name__ == "__main__":
    main()
