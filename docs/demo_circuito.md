# Ejecutar la demostración conceptual

Para la revisión actual de nueve postes en T, jaulas tipo garrucha y vídeo
con recuadro de seguimiento, ver [revision_garruchas.md](revision_garruchas.md).
Las recetas generales de este documento también permiten conservar las vistas
estáticas y repetir configuraciones históricas mediante su YAML archivado.

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

La compilación nativa y los cinco servicios se han ejecutado con Harmonic 8.11.0 y Jazzy, con paridad CLI/plugin aprobada. El [informe nativo](informe_nativo_circuito.md) resume resultados; [validacion_nativa_circuito.md](validacion_nativa_circuito.md) conserva la bitácora de fallos y pendientes. La grabación de 341 s y su revisión visual están documentadas en el informe; no sustituyen una validación de contacto físico. Conservar la instalación existente; no migrar de versión sin un motivo concreto. Preferir la carpeta Linux del repositorio.

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

El circuito dispone de un grabador propio de cámara Gazebo en vivo. Requiere
Pillow (`python3-pil`) y `ffmpeg`; no reproduce los CSV:

```bash
python3 scripts/capture_loop.py --output results/loop_capture_new --view overview --gui --video --until 341 --timeout 1800
```

Las vistas disponibles son `overview`, `lower` y `upper`. Los PNG conservan
instantes de carga, descarga y ráfaga; `frame_times.csv` permite revisar cobertura
y pérdidas. El vídeo recibe 5 imágenes por segundo simulado y reproduce a
20 fps (4× nominal). Un intento parcial no acredita cobertura del servicio.
`--all-views` captura las tres cámaras en un solo mundo y graba vídeo de la
vista seleccionada. La GUI utiliza Qt xcb y libX11 (incluida en el entorno
Ubuntu/WSLg); su cierre normal se limita al PID de esa instancia, sin cerrar
ventanas de otras aplicaciones. Se registran por separado las salidas del
servidor y de la GUI y la confirmación del servicio de parada.

Después de una captura completa con las tres vistas, verificar tiempos,
integridad del vídeo, salidas y reserva de RAM (no sustituye la revisión visual):

```bash
python3 scripts/verify_loop_capture.py --capture results/loop_capture_new/capture --output results/loop_capture_new/verification.json
```

La ruta anterior corresponde al supervisor PowerShell; si se ejecuta el
grabador directamente, usar su directorio `--output` como `--capture`.

En este PC compartido, ejecutar desde PowerShell 7 mediante el supervisor incluido
en el repositorio (no ejecutar estos ejemplos simultáneamente):

```powershell
./scripts/windows/run_guarded_loop.ps1 -RunName loop_guarded_new -Case hybrid_gust
./scripts/windows/run_guarded_loop.ps1 -RunName loop_capture_new -Case capture -View overview -Until 341
```

El lanzador localiza el repositorio, convierte la ruta con `wslpath` y usa
Ubuntu-24.04 por defecto (`-Distribution` permite indicar otra instalación
compatible ya preparada). La compilación y `install/setup.bash` deben existir.
Solo se debe ejecutar un lanzador a la vez; no coordina automáticamente otros
proyectos ni constituye un límite duro de memoria del sistema operativo.
Conserva las dos muestras de admisión, logs y código de salida del supervisor.

Ejecuta los scripts Linux
con `--host-memory` alimentado por muestras reales: al menos 9 GiB libres para
headless y 14 GiB para render con GUI (pico observado 8.42 GiB), dos mediciones separadas, cierre preventivo bajo
5 GiB para preservar la reserva humana de 4 GiB. La opción sin monitor anterior
es una referencia de uso en una máquina dedicada, no el procedimiento vigente
en este PC. No solapar render con otra carga pesada de GPU.

Para representar un caso completo ya verificado:

```bash
python3 scripts/plot_loop_native.py --case results/loop_guarded_01/hybrid_gust --output results/loop_plots_new
```

`compare_loop_backends.py` verifica todos los campos CSV y eventos contra CLI;
`collect_loop_native.py` recibe cinco argumentos `--case nombre=directorio`,
`--cli directorio_suite_cli` y `--output directorio_nuevo`. Exige los cinco
casos completos y los cierres de los supervisores. Aplica los mismos umbrales
comparativos de la suite sin favorecer el controlador híbrido.

Si una ejecución falla, conservar su carpeta, leer `process.log`/`summary.json` y utilizar una nueva para repetir. No ocultar fallos borrando evidencias ni degradar automáticamente el modelo para forzar aprobación.
