# CATALOGADOR en el NAS: programa auxiliar del Gestor, en su propio contenedor (§7: solo ficheros).
# Sin probar en el PC (no hay Docker): se construye en el Container Manager del NAS, como el Gestor.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# El OCR de japonés antiguo de la Biblioteca Nacional de la Dieta, con su propio entorno (sin la interfaz gráfica).
RUN git clone --depth 1 https://github.com/ndl-lab/ndlkotenocr-lite.git /opt/ndlkotenocr-lite \
 && python -m venv /opt/ndlkotenocr-lite/.venv \
 && sed '/^flet/d' /opt/ndlkotenocr-lite/requirements.txt > /tmp/ocr-req.txt \
 && /opt/ndlkotenocr-lite/.venv/bin/python -m pip install --no-cache-dir -r /tmp/ocr-req.txt \
 && mkdir -p /opt/ndlkotenocr-lite/.venv/Scripts \
 && ln -s /opt/ndlkotenocr-lite/.venv/bin/python /opt/ndlkotenocr-lite/.venv/Scripts/python.exe

COPY . .
ENV TZ=Europe/Madrid \
    TDP_NDL_OCR=/opt/ndlkotenocr-lite \
    TDP_IMAGENES=/imagenes \
    TDP_INTERCAMBIO=/intercambio \
    PYTHONIOENCODING=utf-8

# Las bases de firmas y sellos y el estado del servicio viven en /app/datos, que es un volumen.
CMD ["python", "servicio.py", "--hasta", "13:00"]
