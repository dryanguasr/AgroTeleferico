# Ejecutar la demostración conceptual

Trabajar desde la rama del circuito, basada en `feat/gazebo-cable-pilot`, sin sobrescribir cambios locales. Usar carpetas de salida NUEVAS: los programas rechazan sobrescribir evidencia. No hacen falta descargas de modelos de Fuel.

## 1. Modelo reducido, sin ROS/Gazebo

Requisitos: C++17, CMake, Python 3, PyYAML y NumPy. Desde la raíz:

```bash
cmake -S . -B build-loop -DAGRO_LOOP_STANDALONE=ON -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-loop -j2
ctest --test-dir build-loop --output-on-failure
python3 scripts/run_loop_suite.py --binary build-loop/agro_loop_cli --output results/loop_check_01
python3 scripts/report_loop.py --summary results/loop_check_01/summary.json --output results/loop_check_01/report.md
```

La suite completa ejecuta cinco servicios: híbrido con viento, central con viento, híbrido sin viento, mitad de paso y doble frecuencia de actualización del cable. `--quick` ejecuta solamente el primero y no acredita las comparaciones restantes.

Para una ejecución individual o el estudio estático de apoyos:

```bash
python3 scripts/generate_loop.py --config config/loop.yaml --output results/loop_one_01
build-loop/agro_loop_cli --config results/loop_one_01/loop.params --output results/loop_one_01/core
build-loop/agro_loop_cli --config results/loop_one_01/loop.params --output results/supports_01 --screen-supports
```

`--until 10` sirve para diagnóstico parcial, nunca se cuenta como servicio completado. `--mode central_only` y `--no-wind` son opciones del CLI. No editar `loop.params` por separado: regenerarlo desde YAML.

## 2. Gazebo Harmonic + ROS 2 Jazzy en Linux/WSL

Esta ruta se entrega implementada, pero su compilación/ejecución queda pendiente de validación en el entorno de Codex. Conservar la instalación existente; no migrar de versión sin un motivo concreto. Preferir la carpeta Linux del repositorio.

```bash
source /opt/ros/jazzy/setup.bash
colcon build --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
ros2 launch agro_teleferico loop.launch.py output:=results/loop_gui_01
```

Parámetros: `gui:=false`, `mode:=central_only`, `gust:=false`, `config:=/ruta/loop.yaml`. En headless el plugin solicita terminar al completar el servicio; en GUI conserva la escena final hasta cerrar. El botón de pausa debe detener la integración. Reset crea un subdirectorio nuevo; no reutiliza ni borra el anterior.

Suite nativa, desde la raíz y con el entorno cargado:

```bash
python3 scripts/run_loop_suite.py --backend gazebo --plugin-dir "$(ros2 pkg prefix agro_teleferico)/lib" --output results/loop_gz_01
python3 scripts/report_loop.py --summary results/loop_gz_01/summary.json --output results/loop_gz_01/report.md
```

El mundo generado es autocontenido respecto de assets, pero contiene rutas absolutas de esa ejecución. Regenerarlo después de cambiar de máquina; no copiar el SDF aislado. Las dependencias del plugin se resuelven mediante el entorno de ROS/Gazebo.

Estado compacto por Gazebo Transport, no un topic ROS ya puenteado:

```bash
gz topic -e -t /agro_loop/status
```

La GUI muestra un título que identifica el modelo reducido. Hay palets/cajas, tractor naranja, portantes oscuros y flecha de viento durante la ráfaga. Usar la vista general para recorrer el terreno y acercarse a un palet para ver el balanceo. Los colores son ayudas conceptuales, no señales de seguridad certificadas.

## 3. Archivos y secuencia

`generated/` contiene YAML, parámetros, SDF, malla y metadatos. El backend produce `global.csv`, `carriers.csv`, `cables.csv` y `summary.json`. La suite conserva logs de proceso y devuelve error si falla un criterio. Un proceso que sale bien sin datos completos no cuenta como prueba aprobada.

Secuencia nominal: parada inicial y carga del carro 0; viaje hacia estación superior; parada global y descarga; retorno sin teletransportación, ráfaga suave y cierre tras completar el circuito. Tiempo nominal del modelo: aproximadamente 341 s. Los otros carros mantienen sus IDs y pueden atravesar las estaciones durante el recorrido.

## 4. Validación y capturas

Seguir `CODEX_LOOP_HANDOFF.md`. Obtener capturas/vídeo de Gazebo de vista general, estaciones, carga/descarga, flexión y ráfaga. No reemplazar capturas por imágenes generadas. Un vídeo de replay debe identificarse como replay.

Antes de reutilizar `scripts/capture_scene.py`, inspeccionar sus supuestos: pertenece al piloto y no se afirma compatible con el nuevo inventario de modelos. Ajustar el método de captura a WSLg disponible y registrar el comando real.

Si una ejecución falla, conservar su carpeta, leer `process.log`/`summary.json` y utilizar una nueva para repetir. No ocultar fallos borrando evidencias ni degradar automáticamente el modelo para forzar aprobación.
