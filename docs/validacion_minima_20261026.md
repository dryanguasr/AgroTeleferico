# Validación mínima real de Gazebo y ROS

Ejecución del 26 de octubre de 2026 sobre `revised_supports`, después de la
[consolidación del modelo](consolidacion_modelo.md). El núcleo vigente tiene
un vano, dos carros y accionamiento `central_only`; los comandos ROS
ensayados pertenecen al piloto histórico AgroCableSystem.

## Qué queda verificado

| Comprobación | Resultado observado |
|---|---|
| Build nativo inicial | Colcon completó 1 paquete en 38,5 s, código 0 |
| Regresiones finales | 9/9 CTest en 2,15 s; incluye física histórica, núcleo, 21 pruebas del adaptador ROS y 8 pruebas del HUD |
| Ciclo de vida Gazebo | 19/19 comprobaciones: arranque pausado, 200 pasos a 4 s, pausa, 10 pasos a 4,2 s, reset, 50 pasos a 1 s, reanudación, nueva pausa y parada |
| Servicio de carga inicial | Ambos carros cargados: 15 kg en total antes del reset |
| Paridad nativa/CLI | Cinco CSV idénticos byte a byte: 86 filas globales y 172 en cada uno de los otros cuatro |
| Cierre Gazebo | Código 0; sin procesos propios restantes |
| ROS single y spider | Por caso: 53 filas de telemetría y 52 poses tipadas, sin valores inválidos ni retrocesos temporales |
| Comandos ROS | Objetivo válido aplicado; objetivo inválido incrementó rejected y conservó el destino anterior |
| Cierre ROS corregido | Launch, Gazebo, parameter_bridge, agro_telemetry_bridge e interfaz Python terminaron con código 0 en ambos casos; sin escalamiento |

**Verificado — alcance preciso.** El ensayo nativo de ciclo de vida usa
dt=0,001 s, actualización de forma de 0,01 s y calma. Sus primeros 4,2 s
corresponden a carga/parada, con q=0; no se presenta como viaje completo.
El tiempo terminal después del reset fue 1,32 s y el tiempo de pared,
14,622 s. Las capturas posteriores sí muestran desplazamiento y descarga.

Se registraron siete acuses de servicio, 56 publicaciones de estado y
75 estadísticas del mundo. El topic de estado lleva un desfase de publicación
de 0,08 s en los hitos de 4,0/4,2/1,0 s: publica cada 0,1 s y su primera
publicación se produce a 0,02 s. El reloj del mundo y el estado terminal
guardado confirman los pasos exactos. Por eso el ejecutor permite ese desfase
documentado, en lugar de exigir un mensaje exactamente en cada hito.

El cambio de objetivo ROS apareció a 1,021 s; el rechazo, a 1,041 s.
Se observó el objetivo anterior distinto antes de enviar cada orden válida.
Son efectos observados, no acuses correlacionados por identificador.

## Fallo conservado y corrección acotada

**Verificado.** El primer smoke real de single aplicó/rechazó comandos y
publicó telemetría correctamente, pero la interfaz Python acabó con código 1.
Después de SIGINT apareció un RuntimeError en `take_message`; Gazebo y
ambos puentes terminaron con código 0. No reapareció el doble shutdown.
El intento completo está conservado en
[ros_failed_before_signal_fix.zip](evidence/native_hud_20261026/ros_failed_before_signal_fix.zip).

**Inferido.** La secuencia sugiere una carrera entre la toma de mensajes y el
cierre asíncrono del contexto. El log no identifica la causa interna exacta de
la conversión de Python/C++; no se afirma haber demostrado esa causa.

La corrección desactiva el cierre automático por señales de rclpy. SIGINT y
SIGTERM marcan una solicitud; el bucle `spin_once`, con timeout solicitado
de 0,1 s, termina antes de destruir el nodo y cerrar el contexto. Se restauran
los handlers anteriores. RuntimeError y otras excepciones inesperadas siguen
propagándose; el código no convierte esos fallos en éxito.

**Verificado.** Pasaron 21 pruebas con dobles, incluida una señal durante la
lectura manteniendo el contexto válido, y luego pasaron single y spider reales.
La fuente, el script instalado y la procedencia del ensayo comparten el mismo
SHA-256. Esto verifica esos ensayos; no demuestra ausencia de toda carrera bajo
cualquier carga. El descubrimiento tardío como causa de problemas históricos
de comandos también permanece **inferido**, sin prueba nueva de causalidad.

## Capturas representativas

Son dos capturas nuevas de sensores Gazebo, con vista general y seguimiento
del carro 0. No son una reproducción de posiciones a partir de CSV.
Se detuvieron deliberadamente antes de completar el servicio.

| Escena | Cobertura simulada | Fotogramas por cámara | Duración a 20 fps / reproducción 4× | Contenido |
|---|---|---:|---:|---|
| Patio entre pisos | 0,04–70,00 s | 351 | 17,55 s | Carga 5/10 kg, desplazamiento, descarga entre 59,736 y 61,736 s |
| Ladera | 0,04–135,00 s | 676 | 33,80 s | Carga, viaje, descarga y ráfaga entre 118,368 y 128,368 s |

**Verificado.** Ambas cámaras tienen marcas temporales idénticas y separación
máxima de 0,20 s. Los vídeos fuente decodifican completos. Los cinco CSV
coinciden byte a byte con CLI hasta el tiempo real de parada del núcleo:
70,12 s en patio y 135,04 s en ladera. El cierre nativo fue 0 en ambas.
El pico registrado de viento de ladera fue 1,999921 m/s. El final nominal de
ráfaga fue 128,368 s; el evento `gust_end` se registró a 128,370 s por el paso
discreto de integración.

El HUD se superpone después sobre los fotogramas de esas mismas capturas.
Incluye etapa/objetivo, tiempo, velocidad, avance, mapa esquemático de ambos
carros, cargas, balanceo en grados, tensión por portante, fuerza/par/potencia,
trabajo positivo/absorbido, energía de carga y residuo. Los márgenes de bases
se rotulan como cribado analítico; la tensión límite no se presenta como
capacidad admisible y la energía absorbida no se llama electricidad almacenada.

| Vídeo final 1920×1080 | Vista previa |
|---|---|
| [Patio con HUD, 17,55 s](evidence/native_hud_20261026/patio_hud.mp4) | [Fotograma con carga](evidence/native_hud_20261026/patio_preview.png) |
| [Ladera con HUD, 33,80 s](evidence/native_hud_20261026/ladera_hud.mp4) | [Fotograma durante la ráfaga](evidence/native_hud_20261026/ladera_preview.png) |

**Verificado.** Los vídeos finales conservan 351 y 676 fotogramas, a 20 fps,
y decodifican completos. El HUD usa exclusivamente la última muestra anterior
o simultánea, sin interpolación; el desfase máximo observado fue 0,04 s para
cada uno de los cinco CSV. Se inspeccionaron fotogramas de inicio, viaje,
final y ráfaga para comprobar legibilidad. Las auditorías registran los hashes
de vídeos fuente, CSV, compositor y salida.

La primera composición falló al dibujar una barra de avance inferior a un
píxel. Se corrigió el ancho entero y el cierre de FFmpeg ante excepciones;
ocho pruebas locales aprobaron los bordes y la limpieza. No se alteraron las
capturas. El registro fallido se conserva como `hud_failed_before_fix.log`.

## Memoria, admisiones y procedencia

| Ejecución admitida | RAM libre mínima observada | RSS máximo del árbol |
|---|---:|---:|
| Ciclo de vida nativo | 9,898 GiB | 1,293 GiB |
| ROS single | 13,894 GiB | 0,428 GiB |
| ROS spider | 13,172 GiB | 1,030 GiB |
| Captura patio | 9,548 GiB | 2,643 GiB |
| Captura ladera | 9,489 GiB | 2,547 GiB |

**Verificado.** Antes de liberar memoria se rechazaron dos admisiones nativas
y dos de captura. No lanzaron Gazebo. Después, cada ejecución tuvo dos muestras
de admisión separadas 5 s: mínimo 9 GiB sin render o 10 GiB para capturas.
Se mantuvieron parada preventiva bajo 5 GiB y reserva de 4 GiB; ninguna
ejecución admitida activó esa parada. No se cerraron procesos ajenos.
Los intentos están en [admissions.json](evidence/native_hud_20261026/admissions.json).

Entorno comprobado: Ubuntu 24.04.4 en WSL, ROS 2 Jazzy, Gazebo Sim 8.11.0,
Python 3.12.3, rclpy 7.1.11 y FFmpeg 6.1.1. Las versiones completas están en
[environment.txt](evidence/native_hud_20261026/environment.txt).

Evidencia:

- [Ciclo de vida, trazas y paridad nativa](evidence/native_hud_20261026/native_smoke.zip).
- [ROS single/spider: órdenes, telemetría y códigos de salida](evidence/native_hud_20261026/ros_smoke.zip).
- [Log detallado de las nueve pruebas](evidence/native_hud_20261026/ctest_detailed.log).
- [Captura, CSV y configuración de patio](evidence/native_hud_20261026/patio_reproduction.zip).
- [Captura, CSV y configuración de ladera](evidence/native_hud_20261026/ladera_reproduction.zip).
- [Auditoría del HUD de patio](evidence/native_hud_20261026/patio_hud_audit.json) y
  [de ladera](evidence/native_hud_20261026/ladera_hud_audit.json).
- [Resumen clasificado y hashes de fuentes/artefactos](evidence/native_hud_20261026/manifest.json).

Los scripts vivos son pruebas explícitas, fuera de CTest:
`tests/test_ballasted_native.py` y `tests/test_ros_smoke.py`.
El supervisor Windows `scripts/windows/run_guarded_validation.ps1` administra
la admisión y el muestreo. No se repite la campaña completa para verificar estos
contratos. Para reproducir otra vez, elegir nombres de resultados nuevos.

Comandos usados desde la raíz del repositorio en PowerShell (ejecuciones
secuenciales; los nombres existentes se reservan como evidencia):

```powershell
./scripts/windows/run_guarded_validation.ps1 -Mode native -RunName model_consistency_native_03
./scripts/windows/run_guarded_validation.ps1 -Mode ros -RunName model_consistency_ros_02 -RosDomainId 74
./scripts/windows/run_guarded_loop.ps1 -RunName model_consistency_patio_capture_03 -Case capture -Scenario buitrago_patio -Variant revised_supports -NoGui -FollowCarrier -View overview -Until 70
./scripts/windows/run_guarded_loop.ps1 -RunName model_consistency_ladera_capture_01 -Case capture -Scenario ladera_agricola -Variant revised_supports -NoGui -FollowCarrier -View overview -Until 135
```

Después, dentro de WSL y desde la misma raíz, se ejecutaron
`scripts/verify_ballasted_excerpt.py` sobre cada captura y
`scripts/compose_telemetry_hud.py --capture <captura> --output <directorio-nuevo>`.
La revisión de código queda identificada por el commit base y hashes de las
fuentes modificadas, sin atribuir los resultados nuevos al commit sin cambios.

## Qué permanece pendiente

**Pendiente:** cierre físico completo cable–péndulo e impulsos, contacto
rueda–cable, dinámica de bases/líquidos, capacidad de losa/suelo, resistencia,
fatiga y tolerancias. No se ha ejecutado una nueva campaña completa de todas
las variantes ni una prueba exhaustiva de carreras o rendimiento.
La paridad valida integración del mismo núcleo, no física independiente.
