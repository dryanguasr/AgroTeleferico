# Assets del piloto para la propuesta

La [publicación del piloto de demanda](https://github.com/dryanguasr/AgroTeleferico/releases/tag/piloto-demanda-20261029) ofrece descargas directas de los cuatro vídeos y un paquete de evidencia. Los archivos originales también se conservan en este repositorio.

Los cuatro vídeos muestran la misma demanda (semilla 26, 24 pedidos/h, predominio alternado), durante los minutos simulados 10–20. Cada vídeo dura 150 s, en 1080p, 20 fps y reproducción 4×. Las imágenes proceden de sensores Gazebo y el HUD se compone con telemetría sincronizada.

| Política | Vídeo descargable | Vista previa |
|---|---|---|
| A: inmediato, sin buffers | [A_inmediato.mp4](https://github.com/dryanguasr/AgroTeleferico/releases/download/piloto-demanda-20261029/A_inmediato.mp4) | [Miniatura A](evidence/demand_pilot_20261026/A_preview.png) |
| B: coordinado, sin buffers | [B_coordinado.mp4](https://github.com/dryanguasr/AgroTeleferico/releases/download/piloto-demanda-20261029/B_coordinado.mp4) | [Miniatura B](evidence/demand_pilot_20261026/B_preview.png) |
| C: inmediato, con buffers | [C_inmediato_buffers.mp4](https://github.com/dryanguasr/AgroTeleferico/releases/download/piloto-demanda-20261029/C_inmediato_buffers.mp4) | [Miniatura C](evidence/demand_pilot_20261026/C_preview.png) |
| D: coordinado, con buffers | [D_coordinado_buffers.mp4](https://github.com/dryanguasr/AgroTeleferico/releases/download/piloto-demanda-20261029/D_coordinado_buffers.mp4) | [Miniatura D](evidence/demand_pilot_20261026/D_preview.png) |

Para incorporar resultados a la propuesta:

- [Figura comparativa PNG](evidence/demand_pilot_20261026/comparacion_nominal.png) y [SVG editable](evidence/demand_pilot_20261026/comparacion_nominal.svg).
- [Informe completo](resultados_demanda.md), con supuestos, intervalos pareados y sensibilidad eléctrica.
- [Paquete de evidencia sin vídeos](https://github.com/dryanguasr/AgroTeleferico/releases/download/piloto-demanda-20261029/evidencia_demanda_sin_videos.zip), con tablas, eventos, procedencia, fuentes archivadas, miniaturas e informe.
- [Manifiesto SHA-256 de la evidencia](evidence/demand_pilot_20261026/manifest.json). Los archivos del paquete conservan sus nombres y bytes originales.

**Verificado:** 720 ejecuciones comparables auditadas; cuatro casos representativos con seis CSV idénticos entre CLI y Gazebo; cuatro vídeos sincronizados. La semilla representativa se eligió mediante una regla fija de proximidad a la mediana del trabajo de A.

**Inferido:** las diferencias estadísticas describen las demandas sintéticas ensayadas. La electricidad del HUD es una estimación con eficiencias y auxiliares supuestos; no es una medición eléctrica.

**Pendiente:** validación experimental del consumo y del equipo físico. Estos assets no certifican contacto, resistencia estructural ni seguridad.

Los registros científicos conservan como base `6a824b4` y sus hashes de fuentes y binarios: se generaron antes del commit de publicación. El tag de esta publicación identifica el código y los assets ahora versionados, sin alterar aquellos registros.
