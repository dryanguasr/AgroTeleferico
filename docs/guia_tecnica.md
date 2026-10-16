# Guía técnica de AgroTeleferico

Proyecto para diseñar y validar un prototipo de robot agrícola suspendido por cables para apoyar labores agrícolas en laderas.

Piloto agrícola de dinámica y control en **Gazebo Harmonic + ROS 2 Jazzy**.

**[Ver los vídeos representativos](videos.md):** circuito completo, vista
general con recuadro de seguimiento y detalle de la garrucha. El índice distingue
el servicio completo de las capturas parciales de la última revisión.

| Escenario | Mecánica | Control |
|---|---|---|
| `single` | Carro sobre un portante flexible con flecha | Posición longitudinal, tracción limitada y balanceo |
| `double` | Carro sobre dos portantes paralelos | Posición longitudinal, carga simétrica y rigidez lateral |
| `spider` | Plataforma rígida con ocho cabrestantes | Posición y orientación con tensiones positivas |

El doble portante es una propuesta agrícola, no una reproducción mecánica de Monserrate. Todos los parámetros iniciales son supuestos de demostración.

## Ejecución en Ubuntu 24.04 / WSL

Requisitos: ROS 2 Jazzy, `ros-jazzy-ros-gz`, bibliotecas de desarrollo Gazebo Sim 8, Eigen3, colcon, NumPy, PyYAML y Matplotlib. `ffmpeg` sólo se necesita para exportar videos. Ejecutar dentro de Ubuntu WSL; WSLg permite abrir la GUI.

```bash
git clone https://github.com/dryanguasr/AgroTeleferico.git
cd AgroTeleferico
source /opt/ros/jazzy/setup.bash
colcon build --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
ros2 launch agro_teleferico pilot.launch.py scenario:=single
```

Cambiar a `scenario:=double` o `scenario:=spider`. Usar `gui:=false`, `config:=/ruta/parametros.yaml` u `output:=/ruta/telemetry.csv` según necesidad. Cerrar con Ctrl+C. Ejecutar una simulación interactiva por partición Gazebo/dominio ROS.

## Pruebas

```bash
colcon test --event-handlers console_direct+
colcon test-result --verbose
python3 scripts/run_suite.py --quick  # Tres escenarios nominales, 120 s
python3 scripts/run_suite.py          # 18 nominales + 3 perturbaciones
```

La suite ejecuta Gazebo y conserva CSV, SDF, log, gráficos y métricas JSON en `results/suite/`. Compara pasos de 1 y 0,5 ms, cargas útiles de 0/5/10 kg y perturbación lateral. Devuelve error si los criterios fallan. Los resultados generados no se versionan automáticamente.

Trayectorias: los carros recorren de x=1 a x=19 m, frenan al llegar y comienzan el regreso en t=60 s; la referencia adapta su avance a la pendiente y conserva margen de velocidad. La plataforma barre con cambios de los tres ángulos. Los ensayos terminan a 120 s; la ejecución interactiva queda abierta y corre en tiempo real por defecto.

## Comandos ROS 2

Un objetivo externo válido sustituye la demostración hasta reiniciar el escenario.

```bash
ros2 topic pub --once /agro/goal_x std_msgs/msg/Float64 '{data: 12.0}'
ros2 topic pub --once /agro/target_pose geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: world}, pose: {position: {x: 10.0, y: 0.0, z: 7.68}, orientation: {w: 1.0}}}'
ros2 topic echo /agro/pose
ros2 topic echo /agro/tensions
ros2 topic echo /agro/feasible
```

`goal_x` es posición horizontal en [1,19] m. Se publican `/agro/pose` (`PoseStamped`), `/agro/velocity` (`TwistStamped`), `/agro/tensions` y `/agro/lengths` (`Float64MultiArray`), `/agro/feasible` (`Bool`) y `/agro/telemetry` (fila CSV completa). El encabezado CSV define el orden; cada cable ocupa tensión, longitud y velocidad de cabrestante. Entradas no usadas de carros contienen cero. Todas las poses usan `world` y tiempo simulado.

## Alcance

- Carros: dinámica reducida con restricción guiada, catenaria elástica cuasiestática a 50 Hz, tracción y péndulo de balanceo. Gazebo representa la pose calculada; no se resuelve contacto rueda–cable.
- Doble cable: reparto simétrico de carga y rigidez lateral equivalente, sin transferencia de carga lateral detallada.
- Plataforma: dinámica de cuerpo rígido integrada por Gazebo y fuerzas de ocho cables elásticos amortiguados que sólo tiran. Sin masa distribuida ni colisiones entre cables.
- Las líneas renderizadas usan segmentos de longitud visual fija; no determinan las fuerzas físicas.
- El límite de tensión acota el comando; una perturbación puede producir sobretensión física, registrada sin recorte artificial.

Ver [resultados medidos y escenas](resultados.md), [modelo](modelo.md), [referencias](referencias.md) y [validación](validacion.md). Código nuevo bajo MIT; no se ha incorporado código externo de las referencias.

## Nuevo: circuito conceptual de seis carros

La configuración actual incorpora **9 postes en T**, vanos de 6 m horizontales
y carros con jaula inspirada en garruchas. El vídeo añade un recuadro que sigue
al carro 0. Ver [cambios, pruebas y reproducción](revision_garruchas.md).
La evidencia nativa enlazada a continuación conserva la variante anterior de
13 apoyos; no debe confundirse con los resultados de esta revisión.

Extensión independiente; no cambia la configuración ni el código físico de los tres escenarios anteriores. Dos carriles, cuatro portantes, tractor separado, terreno irregular, palets, paradas globales, ajuste local y viento. **Cinco servicios nativos Harmonic/Jazzy, paridad CLI/plugin y grabación completa aprobados.** No es validación física ni contacto rueda–cable. Ver el [informe nativo](informe_nativo_circuito.md) y los [CSV y gráficos empaquetados](evidence/loop/native/manifest.json).

```bash
cmake -S . -B build-loop -DAGRO_LOOP_STANDALONE=ON -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-loop -j2
ctest --test-dir build-loop --output-on-failure
python3 scripts/run_loop_suite.py --binary build-loop/agro_loop_cli --output results/loop_check_01
python3 scripts/report_loop.py --summary results/loop_check_01/summary.json --output results/loop_check_01/report.md
```

Tras compilar con colcon y cargar `install/setup.bash`:

```bash
ros2 launch agro_teleferico loop.launch.py output:=results/loop_gui_01
# Alternativa sin GUI; usar otra carpeta:
ros2 launch agro_teleferico loop.launch.py gui:=false output:=results/loop_headless_01
```

Cada ejecución exige una carpeta nueva. Ver [instrucciones completas y captura](demo_circuito.md), [arquitectura y límites](concepto_circuito.md), [resultados reducidos](informe_exploratorio_circuito.md) y [trabajo restante para Codex](CODEX_LOOP_HANDOFF.md). El [goal original](goals/loop_six_carriers.md) permanece como referencia, no como afirmación de cumplimiento total.

Captura en este PC desde PowerShell 7, con vigilancia de RAM Windows y dos
vistas simultáneas: general y seguimiento (requiere el entorno ya compilado):

```powershell
./scripts/windows/run_guarded_loop.ps1 -RunName loop_capture_new -Case capture -View overview -Until 341 -NoGui -FollowCarrier
```

El vídeo corresponde al sensor Gazebo en vivo, a 1280×800 y 4× de velocidad
nominal; los CSV de tiempos permiten comprobar la cobertura real. El supervisor
exige una carpeta nueva y conserva también intentos incompletos. El servicio
headless histórico de 13 apoyos midió un factor de tiempo real de 0,5046; el rendimiento
gráfico se registra aparte. El control híbrido aumentó un 4,55 % el RMS
longitudinal frente al central en el caso nominal con ráfaga: no se demuestra
una mejora del control local.

