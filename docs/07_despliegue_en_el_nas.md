# CATALOGADOR en el NAS · contenedor propio · 09/10/2026

La casa, el 09/10/2026: CATALOGADOR arranca en el NAS, en un contenedor específico, con los
ficheros en el servidor. Va aparte del contenedor `tdp` del Gestor y comparte con él solo dos
carpetas: las imágenes (solo lectura) y `_intercambio`. Es el camino A del Gestor, sin SSH, desde
el Container Manager (`docs/manual/02_puesta_en_marcha.md` §5 del Gestor), y aquí se repite para
este programa.

## 1. Lo que hace falta en el NAS

| Qué | Dónde |
|---|---|
| La carpeta del código, clonada del repositorio | `…/CATALOGADOR/` (al lado de la del Gestor, por ejemplo `GESTOR_TDP_V2/CATALOGADOR/`) |
| El fichero `.env`, solo con rutas y el id del espacio de trabajo | `…/CATALOGADOR/.env` |
| La clave de la API de Anthropic, en un fichero de secreto, **nunca en `.env` ni en el compose** | `…/CATALOGADOR/secretos/anthropic_api_key` (fuera de git) |
| Las imágenes del Gestor | la misma carpeta que `TDP_ALMACEN_EN_EL_NAS` del Gestor, con `/originales` dentro |
| `_intercambio` | la misma carpeta que `TDP_INTERCAMBIO_EN_EL_NAS` del Gestor |

`.env` (las variables se llaman igual que en el Gestor para que apunten a las mismas carpetas):

```
TDP_IMAGENES_EN_EL_NAS=/volume1/…/IMAGENES
TDP_INTERCAMBIO_EN_EL_NAS=/volume1/…/FOTO/_intercambio
ANTHROPIC_WORKSPACE_ID=wrkspc_…
CATALOGADOR_HASTA=13:00
```

El fichero de secreto es una sola línea con la clave, sin comillas ni espacios. El contenedor la
lee de `/run/secrets/anthropic_api_key`; `agente.cliente()` la busca ahí si no hay variable.

## 2. Construir y arrancar, desde el Container Manager

1. **Proyecto nuevo** → carpeta `…/CATALOGADOR/` → `docker-compose.yml` el del repositorio. El Container Manager construye la imagen con el `Dockerfile`: Python 3.12, las dependencias, y el OCR de japonés antiguo de la Biblioteca Nacional de la Dieta clonado dentro con su propio entorno (sin la interfaz gráfica). La primera construcción tarda: descarga los modelos ONNX del OCR.
2. **Primer arranque.** El servicio estrena el volumen `catalogador_datos` y, la primera vez que el agente lo necesita, descarga las bases de firmas y sellos de ukiyoesig.net (dos páginas, una vez; quedan en el volumen). Ahí viven también la caché de ukiyo-e.org, la biblioteca propia, la memoria de series y el estado del servicio.
3. **Comprobar.** En el registro del contenedor debe salir `cola: /intercambio/para_catalogador/cola.jsonl · fotos: /imagenes` y, cada 15 segundos, nada más mientras la cola esté vacía. Para probarlo sin el Gestor: copiar a mano `contratos/intercambio/para_catalogador/cola.jsonl` a `_intercambio/para_catalogador/` con una referencia real y ver aparecer `de_catalogador/estado.jsonl` y `fichas.jsonl`.
4. **Horario.** `--hasta 13:00` deja «aplazada» cualquier petición que llegue más tarde y la retoma al día siguiente a partir de las 06:00 (el contenedor sigue vivo; la hora es la del NAS, que debe estar en Europe/Madrid).

## 3. Lo que no se hace

Montar las imágenes con escritura (van `:ro`). Poner la clave en `.env` o en el compose. Tocar la
base del Gestor: CATALOGADOR no la conoce. Lanzar la búsqueda por imagen de ukiyo-e.org desde el
servidor (la hace una persona en su navegador). Dos contenedores de CATALOGADOR a la vez sobre el
mismo `_intercambio`.

## 4. Lo que queda por probar en el NAS

- La construcción de la imagen (en el PC no hay Docker). Si el OCR no instala alguna dependencia en Linux, el registro lo dice en la construcción; se arregla en el `Dockerfile`.
- Cuánta CPU gasta el OCR en el NAS: en el PC son 9 s por foto. En el NAS será más; el agente lo espera.
- El tiempo de respuesta de ukiyo-e.org desde el NAS, que ya se consulta a 20–35 s por petición.

## 5. Mientras el contenedor no exista

Desde este PC, con las carpetas del NAS montadas en `Z:`:

```bash
./.venv/Scripts/python.exe servicio.py --intercambio "Z:\FOTO\_intercambio" --imagenes "Z:\IMAGENES" --hasta 13:00
```

El contrato es el mismo; el Gestor no nota la diferencia.
