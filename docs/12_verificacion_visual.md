# Paso 4 · la verificación visual · 12/11/2026 (catalogador-0.7.0)

La casa, el 12/11/2026: «La comparación visual de ukiyo-e es importante y construir los arreglos también»,
y después «ADELANTE, SIGUE Y CONSTRUYE». Lo que pidió: comparar nuestra foto con la de ukiyo-e.org para depender
menos del agente y acelerar la catalogación.

## D-1845 · Cada «misma estampa» de ukiyo-e.org se comprueba con la foto

`visual.py` compara nuestra foto con la imagen de cada ficha de ukiyo-e.org que el agente cita como
«ukiyo-e.org misma estampa». Usa OpenCV, que ya estaba en el contenedor: SIFT, la prueba del cociente y una
homografía con RANSAC. Cuenta los puntos del dibujo que encajan con una sola transformación. La misma xilografía
encaja aunque cambien la foto, los colores o la tirada; una hermana de serie no.

- **Misma** (150 puntos o más): el dato lleva `segunda_senal: "visual"`, la segunda señal independiente que pide
  ARQUITECTURA §8 r.2 para cualquier automatismo futuro.
- **Ninguna de las citadas encaja** (y se pudieron comprobar): el dato baja a «otra lámina documentada», con techo
  media (D-1842), y su `como` lo dice.
- **No se pudo comprobar** (ukiyo-e.org parado o tope del día, una ficha sin imagen): no se toca nada.
- El resultado de cada id va en `verificacion_visual` del resultado. El contrato `fichas.jsonl` no cambia: llega
  al Gestor por el nivel y la fiabilidad.
- **Hacia la API no sale nada nuevo:** se hace en local, después de la última respuesta del modelo. El prompt
  no cambia.
- **ukiyo-e.org:** una petición más por ficha citada que no esté en caché, la imagen de data.ukiyo-e.org, cuyo
  robots.txt solo cierra `/uploads/`. Va con el mismo freno, el mismo tope diario y la caché para siempre de
  `ukiyoe.py` (`ukiyoe.imagen`). La búsqueda por foto (`/upload/`) sigue sin automatizarse.

**Umbrales.** Salen de la etapa 0 (`scratchpad/visual_v0`, sin API): 15 fotos nuestras frente a 25 de
ukiyo-e.org, 26 pares que sí y 349 que no.
- Las mismas dieron de 212 a 452 puntos; ninguna distinta pasó de 120.
- Con 150, 20 aciertos de 26 y ningún falso «es la misma».
- Las 6 «mismas» que no encajaron eran citas dudosas del agente; una ya se sabía mal, la de TDP-008071 a la hoja
  de su hermana TDP-008060.
- Una pre-ficha (TDP-900377) da entre 50 y 90 puntos contra casi todo, por su fondo: por eso hay franja «dudosa».

**Sobre las fichas reales** (v4 y v3, las 8 con «misma estampa» en ukiyo-e.org):
- TDP-008071 se queda en alta: de sus dos citas, la buena encaja con 297 puntos y la de su hermana da 7.
- TDP-008117 baja su autor y su serie de alta a media: su única cita da 10 puntos. Que lo mire una persona.
- Las otras 6 encajan con 244 a 452 puntos.

**Descarta:**
- un modelo de imagen descargado (DINOv2 o CLIP): no hace falta para comparar pocas candidatas;
- automatizar la búsqueda por foto de ukiyo-e.org, que su robots.txt cierra;
- darle la comparación al agente como herramienta: queda para cuando haga falta.

Pruebas: 129 → 135 (`pruebas/test_visual.py`, con dibujos sintéticos y sin red).
