# Validación nativa del circuito — en curso

## Primer servicio nativo completo y continuidad autorizada

El usuario indicó después: «Continúa, te avisaré desde el otro chat cuando
necesite recursos». Se continúa secuencialmente, con vigilancia y sin solapar
simulaciones propias. Los avisos posteriores de recursos tienen prioridad.

`results/loop_guarded_01/hybrid_gust/guard_summary.json` acredita un servicio
completo de **340,802587245 s**, cierre con código **0**, todos los criterios
numéricos aprobados y ninguna parada de la guarda. Pico RSS sumado del árbol:
**3,474724 GiB**; mínimo libre del host Windows: **7,299744 GiB**. Tiempo del
supervisor: 688,31 s; RTF medido por el plugin: **0,5046**. Estas cifras incluyen
la carga compartida del equipo de esta ejecución, no una prueba de rendimiento
aislada.

`results/loop_guarded_01/cli_parity.json` verifica **igualdad exacta de todos los
campos de los tres CSV y de los eventos**, a la precisión registrada, frente al
CLI con la misma configuración. Esto comprueba que separar el paso de escena
(10 ms) del integrador (2 ms) conserva la trayectoria en este caso; no acredita
todavía las otras cuatro comparaciones ni validez física del modelo.

Siguiente caso en marcha: `results/loop_guarded_02/central_gust`, con las mismas
guardas. No se repite el servicio híbrido ya completado.

## Relevo limitado tras la pausa

Uchuvas autorizó explícitamente **un único servicio headless**, sin GUI,
render ni otras suites concurrentes. Se admitió un presupuesto provisional
adicional de 4 GiB con reserva global de 2 GiB. La comprobación local previa
midió 15,66 GiB libres en Windows; las primeras muestras del árbol propio
registraron 3,475 GiB RSS y unos 12,9 GiB libres en el host.
`outputs/run_one_headless.ps1` (en el workspace) actualiza la medida Windows
cada 2 s; `scripts/run_loop_guarded.py` mide el árbol cada segundo y cierra
Gazebo si supera 4 GiB, si Windows baja de 3 GiB (margen de cierre antes de
la reserva de 2 GiB), o si la medida del host caduca. Este RSS suma procesos
y puede contar páginas compartidas más de una vez; no equivale a memoria
privada ni atribuye todos los cambios de RAM del host al teleférico.
Evidencia: `results/loop_guarded_01/hybrid_gust`. No autoriza todavía render
ni nuevos arranques adicionales.

Durante esta ejecución se reconstruyó, sin lanzar simulaciones, el informe
`results/pilot_native_full_01/recovered_summary.json`: los **21 CSV completos**
y las **9 comparaciones de convergencia** aprueban los criterios numéricos.
Los valores recalculados coinciden con los 20 informes individuales existentes.
Se conserva la limitación de no haber registrado el código de salida ni el
tiempo de pared del último proceso; no se presenta el supervisor interrumpido
como ejecución agregada terminada normalmente.

## Pausa autorizada para priorizar uchuvas

El 14 de octubre de 2026 el usuario autorizó «Go» en el chat
`01a0fe9f-042c-7e62-9d72-60074358ef5a`, después de recomendar pausar el
teleférico para liberar RAM. Se verificó ese intercambio antes de actuar.
**No relanzar simulaciones, grabaciones ni suites hasta nueva autorización.**
Código, resultados y registros se conservan; no hay cambios publicados ni
fusión a main. El objetivo queda pausado, no completado.

Se detuvieron los supervisores PID 1779 (regresión) y 2035 (suite del circuito),
así como los Gazebo propios 2057 y 2133 (servidor/GUI 2134/2135). El último
caso del piloto, PID 3491, ya había terminado al intentar cerrarlo. El grabador
2092 y FFmpeg 2132 finalizaron; la verificación posterior no encontró ningún
proceso propio pesado. No se detuvo WSL ni procesos de otros proyectos.

- Suite nativa `loop_gazebo_native_03`: primer caso parcial hasta aproximadamente
  303,8 s; sin resumen final y con última fila truncada. **No aprobado**. Los
  CSV originales se conservan sin editarlos. No hay checkpoint reiniciable del
  integrador; el caso incompleto requerirá una ejecución nueva al reanudar.
- Vídeo `loop_capture_overview_01/gazebo.mp4`: 1355 fotogramas, hasta 270,8 s
  simulados, incluye carga, descarga y ráfaga. Gazebo salió con código 0 y su
  resumen marca `interrupted`. La captura es parcial y conserva el terreno
  blanco previo a la última corrección; no sustituye el vídeo final corregido.
- Regresión `pilot_native_full_01`: 21 carpetas conservadas; el lanzador fue
  interrumpido antes del informe agregado. Hay 20 archivos `metrics.json`,
  los 20 con `passed=true`. Inspeccionar el último caso y las métricas individuales
  y completar lo que falte, sin declarar aprobación global por contar carpetas.
- Integración ROS (`single`, `spider`) y saturación finalizaron con código 0.
- Ciclo de vida `loop_lifecycle_03`: ocho comprobaciones aprobadas, incluido
  cierre limpio y archivos separados tras reset.

Al reanudar: inspeccionar primero Git y procesos; no asumir que siguen vivos
los handles de esta sesión. Reinstalar scripts actualizados con colcon antes
de probar launch. Completar la suite Gazebo y ejecutar
`scripts/compare_loop_backends.py`; grabar vídeo con el terreno corregido;
revisar envolventes/renderer y completar el informe. No modificar ganancias
para mejorar artificialmente al híbrido.

Base: `ffc699c45cdfa777e0220991229fef9c99879151`, rama
`feat/gazebo-loop-six-carriers`. Esta página registra avances y fallos;
**todavía no acredita el cierre del traspaso**. Las salidas de esta sesión están
en `results/`, separadas de la evidencia versionada anterior.

## Resultados comprobados

- Ubuntu 24.04 en WSL, ROS 2 Jazzy, Gazebo CLI 8.11.0; WSLg dispone de
  `DISPLAY=:0` y `WAYLAND_DISPLAY=wayland-0`.
- Compilación nativa Release con colcon completada. El plugin del circuito
  compila sin cambios de API. Se conserva una advertencia de Eigen del plugin
  original (`FromTwoVectors`, `-Wmaybe-uninitialized`); no es un error de build.
- CTest nativo: `loop_core`, `loop_assets`, `physics` aprobados.
- `results/loop_cli_native_01`: cinco servicios CLI aprobados.
- `results/pilot_native_quick_01`: los tres pilotos completan 120 s y aprueban.
- Primera cámara real Ogre2: `results/loop_render_probe_01`; confirma carga de
  escena y movimiento. No es replay. El terreno aparece blanco, por lo que
  esa captura no acredita todavía la corrección de materiales.

## Fallos encontrados y correcciones en validación

1. `results/loop_gazebo_native_01`: cinco arranques fallidos. `Path.as_uri()`
   codificaba el espacio del workspace como `%20`, que el resolvedor de
   recursos de Harmonic no resolvía. Se usa ruta absoluta escapada para XML,
   sin codificación porcentual. Prueba de regresión con espacios, `&` y tilde.
   `gz sdf -k` había declarado válido el XML: no sustituye ejecutar el mundo.
2. `results/loop_gazebo_native_02`: ejecución interrumpida explícitamente por
   lentitud (aproximadamente RTF 0,2 en la primera muestra). No se contabiliza
   como servicio completo. El reloj de Gazebo ahora avanza a 10 ms, mientras
   el acumulador existente conserva todos los pasos de 2 ms del núcleo.
   La nueva metadata distingue ambos pasos. Es una optimización de la escena
   cinemática, pendiente de comparación completa de CSV con CLI.
3. Malla COLLADA: se añaden material explícito y normales para Ogre2. La
   prueba intermedia `loop_render_probe_02` reveló índices de normales mal
   interpretados al compartir offset; se separan los índices y se verifica
   su cardinalidad. `loop_render_probe_03/lower_004s.png` confirma terreno
   continuo verde; el cierre por servicio termina con código 0 y resumen.
4. Ciclo de vida: la primera prueba confirma pausa, paso manual y conservación
   de archivos al reset. La prueba debe esperar a que terminen TODOS los pasos
   manuales antes de reset; un acuse de servicio no acredita su ejecución.
   Una segunda ejecución no recibió acuse de avance manual bajo carga.
   `loop_lifecycle_03/checks.json` aprueba las ocho comprobaciones tras esperar
   los pasos pendientes y ampliar a 15 s el plazo de acuse: pausa, avance,
   reset con conservación del primer registro, reloj reiniciado y cierre
   limpio con código 0 y archivos completos en `reset_1`.

## Comandos de esta sesión

Desde la raíz, con `/opt/ros/jazzy/setup.bash` cargado:

```bash
colcon build --cmake-args -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
source install/setup.bash
ctest --test-dir build/agro_teleferico --output-on-failure
python3 scripts/run_loop_suite.py --binary build/agro_teleferico/agro_loop_cli --output results/loop_cli_native_01
python3 scripts/run_loop_suite.py --backend gazebo --plugin-dir install/agro_teleferico/lib --output results/loop_gazebo_native_03
python3 scripts/run_suite.py --quick --output results/pilot_native_quick_01
python3 scripts/run_suite.py --output results/pilot_native_full_01
python3 scripts/capture_loop.py --output results/loop_capture_overview_01 --gui --video --until 341 --timeout 1000
python3 tests/test_loop_native.py --output results/loop_lifecycle_02
```

Las carpetas existentes se conservan, incluso al fallar. Para repetir se debe
usar un nombre nuevo. El vídeo registra a 5 Hz simulados y reproduce a 20 fps
(4× nominal); `frame_times.csv` permite verificar cobertura y pérdidas.

## Pendientes de cierre

Cinco servicios Gazebo completos, igualdad de estados CLI/plugin, ciclo de vida
completo, regresión completa, capturas corregidas y vídeo normal/ráfaga,
envolventes en estaciones/apoyos, renderer/GPU, métricas de rendimiento e
informe final. No se modificaron ganancias ni supuestos físicos para favorecer
el híbrido. Siguen vigentes las limitaciones de `concepto_circuito.md`.

## Reserva de memoria actualizada por el usuario

La autorización posterior exige conservar 4 GB libres; se aplica conservadoramente
como 4 GiB en Windows. Las nuevas admisiones requieren dos muestras separadas
de 9 GiB para headless o 11 GiB para render. Se solicita cierre preventivo bajo
5 GiB, dejando margen antes de la reserva. El caso central_gust ya iniciado
recibe un vigilante Windows adicional; los casos siguientes incorporan los
umbrales en ambos supervisores. Las mediciones y umbrales históricos anteriores
se conservan como evidencia, pero no gobiernan ejecuciones posteriores.


## Segundo servicio nativo y gráficos

central_gust en results/loop_guarded_02 completa 340.802587245 s, cierre 0,
todas las comprobaciones aprobadas y paridad exacta de CSV/eventos con CLI
(cli_parity.json). Pico RSS del árbol 3.474651 GiB; mínimo libre Windows
9.773140 GiB; tiempo del supervisor 761.553419 s y RTF del plugin 0.454080.
El vigilante adicional terminó al cerrar ese supervisor.

Se generan y revisan visualmente los gráficos PNG/PDF del primer servicio en
results/loop_guarded_01/plots mediante scripts/plot_loop_native.py: error,
balanceo longitudinal/transversal, tensión, fuerza y potencia mecánica.
Las dos pruebas ligeras de memoria aprueban y se incorpora loop_guard a CTest
(pendiente reconfigurar CMake). hybrid_calm comienza en loop_guarded_03 tras
dos muestras de 14.120731 y 14.552601 GiB libres, separadas por cinco segundos.


## Consolidación y grabación con reserva

Se añade `collect_loop_native.py` para consolidar los cinco directorios separados
sin copiar ni sobrescribir la evidencia. Relee CSV, exige cierre limpio tanto
del guardián como del supervisor Windows y vuelve a comparar todos los campos
con CLI. `compare_cases` comparte los criterios originales con la suite; su
resultado se reprodujo exactamente sobre los cinco casos CLI existentes y una
suite incompleta se rechazó. La consolidación nativa todavía no se ha ejecutado:
faltan terminar tres casos. No confundir esta comprobación CLI con su validación.

El grabador acepta `--host-memory`, registra RSS y RAM libre y solicita cierre
por debajo de 5 GiB libres, por encima de 6 GiB RSS o ante STOP_REQUESTED.
El lanzador Windows `outputs/run_one_render.ps1` exige dos muestras de al menos
11 GiB. Se comprobaron sintaxis Python/PowerShell y pruebas de lectura de RAM;
la guarda dentro del grabador sigue pendiente de su primera ejecución real.
No se ha lanzado render durante el caso headless activo.

Estado de cierre actual:
- Compilación nativa y tres targets originales: aprobados antes de los cambios
  de empaquetado actuales; falta reinstalación y CTest con loop_guard añadido.
- Servicios completos y paridad: hybrid_gust y central_gust aprobados;
  hybrid_calm activo; dos sensibilidades pendientes.
- Pausa/reset/cierre: ocho comprobaciones aprobadas en loop_lifecycle_03.
- Regresión piloto: quick aprobado; 21 CSV completos y nueve comparaciones
  recuperadas aprobadas, con la limitación de cierre del supervisor ya descrita.
- Visuales: terreno corregido confirmado en probe_03; vídeo corregido completo,
  revisión de estaciones/apoyos y documentación de renderer todavía pendientes.
- Informe final, evidencia versionada y commit de entrega: pendientes.

### Fallo de supervisión y reintento del caso sin viento

`loop_guarded_03` terminó incompleto a ~43.66 s simulados. El guardián registró
`OSError(61, No data available)` y cerró Gazebo con código 0. Pico RSS
3.474865 GiB y mínimo libre observado 11.137367 GiB: no fue una parada por RAM.
La excepción no conservaba traza, por lo que no se atribuye con certeza a una
línea. Una lectura durante sustitución atómica Windows/DrvFS es la hipótesis.
Se añaden hasta tres intentos (100 ms entre ellos) SOLO para ENODATA/ENOENT al
leer la muestra. Se conserva la validación de antigüedad y se falla al agotar
los intentos. Cuatro pruebas aprueban, incluyendo error transitorio seguido de
muestra válida, muestra obsoleta y error persistente. Futuras excepciones del
guardián guardarán la traza completa en guard_error.txt.

Se conserva toda la carpeta fallida y se inicia el único reintento como
`loop_guarded_03_retry01`; no se reutilizan ni completan artificialmente sus CSV.

### Sincronización y comparación central/híbrido

`git fetch origin` completó sin cambios: HEAD y origin/feat/gazebo-loop-six-carriers
siguen en ffc699c45cdfa777e0220991229fef9c99879151, divergencia 0/0. No hay
entradas sin fusionar ni marcadores de conflicto en los directorios de código
y documentación revisados. No se fusiona main; los cambios de validación se
conservan sin commit hasta completar las comprobaciones pendientes.

Los dos servicios nativos completos arrojan un incremento del RMS longitudinal
híbrido de **4.552898 %** frente a central_only. Es peor en esta métrica, tal como
la evidencia exploratoria; no se modifican ganancias ni criterios.

La configuración de GitHub Actions añade la suite CLI del circuito y su prueba
nativa de pausa/reset/cierre; aún no se ha ejecutado remotamente esta revisión.
Se declaran Pillow y FFmpeg como dependencias del grabador. Las instrucciones
actualizadas distinguen grabación real de replay y el uso en máquina dedicada
del procedimiento vigilado vigente en este PC compartido.

### Zonas prioritarias de revisión visual

`check_loop_clearance.py` inspecciona las 40 908 poses CSV del servicio híbrido
completo contra 42 cajas estructurales (columnas, travesaños, plataformas y
motor). Usa esferas conservadoras de radio 0.85 m para bogie y palet/carga;
excluye intencionadamente contacto con guías/retenciones y no demuestra
separación continua entre muestras. No es una certificación de envolvente total.

El cribado resulta inconcluso: envolvente del bogie 2 cerca del motor inferior
a 228.3 s, cota -0.241 m; palet 3 sobre la plataforma inferior a 145.35 s,
cota -0.502 m. Una cota negativa indica solape de la esfera conservadora,
no interpenetración de las geometrías reales. Se añaden capturas a 145 y 228 s
para revisar esas zonas en vivo. No se alteran las dimensiones ni la dinámica
basándose únicamente en este cribado. Resultado conservado en
results/loop_guarded_01/clearance_screen.json.

## Tercer servicio completo

`results/loop_guarded_03_retry01/hybrid_calm` completó 340.802587245 s con
cierre 0 y todas las comprobaciones aprobadas. Pico RSS 3.475643 GiB;
mínimo libre Windows 10.891701 GiB; 704.132896 s de supervisor y RTF
0.491675. La paridad exacta de los tres CSV y eventos aprobó en
`results/loop_guarded_03_retry01/cli_parity.json`. No se repite este caso.
El intento fallido loop_guarded_03 se mantiene intacto como evidencia.

El cuarto servicio, hybrid_half_dt, se inicia en results/loop_guarded_04
después de confirmar cierre del anterior y las dos muestras de admisión.
Su resultado todavía está pendiente.

## Gráficas de los tres servicios nominales

`results/loop_three_case_plots_02` contiene PNG/PDF revisados visualmente y
JSON de métricas, calculados con los CSV completos. La primera versión de
paneles se conserva; la segunda usa colores consistentes entre gráficas.
RMS longitudinal (grados): híbrido/ráfaga 0.901140, central/ráfaga 0.861899,
híbrido/calma 0.896595. RMS transversal: 0.202451, 0.202449 y 0.107144.
La figura incluye el máximo absoluto transversal entre los seis carros y
la carga del carro 0 para contextualizar la ráfaga y el servicio. El RMS
agrega todas las muestras/carros; no equivale a una oscilación máxima.
No se infiere superioridad del híbrido ni recuperación eléctrica.

## Entorno gráfico y versiones observadas

Consulta ligera guardada en outputs/native_environment_01.txt: Ubuntu 24.04.4,
kernel WSL2 6.18.33.2, WSLg 1.0.73.2, Gazebo 8.11.0, ROS Jazzy,
ros_gz_bridge 1.0.22, colcon-core 0.21.0, NumPy 1.26.4 y FFmpeg 6.1.1.
La primera consulta GPU falló por formato; repetida directamente aprobó:
NVIDIA GeForce RTX 4050 Laptop GPU, controlador 610.62, 6141 MiB de VRAM.

El último registro Ogre preexistente identifica GL 4.5 / Mesa 25.2.8 y
**llvmpipe (LLVM 20.1.2, 256 bits)**, un renderer por CPU. Se preserva en
outputs/ogre2_before_corrected_capture.log antes de futuras capturas.
Esto no demuestra qué renderer usará la siguiente ejecución ni que la RTX se
haya empleado en las capturas previas. glxinfo no está instalado; no se instala
software adicional para esta consulta. /dev/dxg y el driver Mesa D3D12 están
presentes, pero su presencia tampoco prueba aceleración efectiva. Verificar
el registro de la grabación corregida y mantener guardas de RAM incluso si la
GPU parece ociosa.

## Cuarto servicio completo: mitad del paso

`results/loop_guarded_04/hybrid_half_dt` termina con código 0 y todas las
comprobaciones aprobadas; igualdad exacta de CSV/eventos con CLI en
`cli_parity.json`. Pico RSS 3.475140 GiB, mínimo libre Windows 11.706245 GiB,
tiempo del supervisor 769.455821 s. Se confirmó dt=0.001 s, shape_period=0.02 s,
visual_period=0.05 s y paso de escena Gazebo de 0.01 s.

Cambios relativos frente al híbrido nominal: RMS longitudinal 8.939145e-6,
RMS transversal 1.877846e-5, tensión máxima 1.409654e-11. Son fracciones;
el máximo equivale a 0.001878 %, inferior al umbral del 5 %. Resultado
conservado en convergence.json; no acredita la sensibilidad del cable todavía.

El último caso hybrid_half_shape se inicia en results/loop_guarded_05 después
de verificar cierre del anterior y admisión de memoria. No se repiten los
cuatro casos completos.

## Lanzador portátil y coordinación antes de render

Se incorpora scripts/windows/run_guarded_loop.ps1 (PowerShell 7) para casos
headless y captura. Deriva la raíz del repositorio y usa wslpath, sin rutas de
usuario fijadas. Sintaxis y conversión de esta ruta con espacios comprobadas;
su primera ejecución completa se hará al capturar, después del caso activo.
Las ejecuciones previas conservan sus supervisores y registros originales.

Se revisó el último turno de uchuvas: entrega terminada, esperando selección
humana, heartbeat pausado. Se envió únicamente un aviso de coordinación para
la futura captura, explícitamente sin reanudar ese objetivo ni su heartbeat.
Antes de render siguen siendo necesarias comprobación real de procesos y
las dos muestras de admisión; estado idle del chat no prueba ausencia de carga.

## Cinco servicios nativos y consolidación aprobados

El quinto servicio (`loop_guarded_05/hybrid_half_shape`) terminó con código 0,
pico RSS 3.474922 GiB, mínimo libre Windows 12.211201 GiB y 785.931443 s del
supervisor. La consolidación en `results/loop_native_consolidated_01/summary.json`
relee todos los CSV, verifica los cierres Windows/Linux y aprueba los cinco
casos, sus cinco comparaciones exactas con CLI y todos los criterios cruzados.

Máximo cambio por mitad de shape_period: 0.000499632 en fracción, equivalente
a **0.0499632 %**. La diferencia transversal máxima entre ráfaga y calma es
0.043979945 rad; el servicio de carga/descarga también coincide. Ninguna de
estas comprobaciones convierte el modelo reducido en contacto nativo o en
validación física de una instalación real.

Se prepara captura de tres cámaras en un mismo mundo para evitar repetir la
dinámica por cada vista; vídeo de la cámara principal y PNG de las tres.
Sintaxis comprobada, ejecución corta y completa todavía pendientes.

## Reinstalación y fallo de cierre gráfico

Colcon incremental concluyó correctamente en 1 min 17 s. CTest aprobó
loop_core, loop_assets, loop_guard y physics (4/4, 2.23 s).

`loop_capture_three_smoke_01` obtuvo 21 imágenes por cámara y alcanzó 4 s
simulados en overview/lower/upper. No se acepta la prueba: la salida Gazebo
fue -9 tras agotar cierre por servicio e INT. El servidor hijo creó un grupo
de procesos distinto y sobrevivió al cierre del grupo del lanzador. Se verificó
su partición exacta (agro_loop_capture_cf9edae87416451da086c3a303131c65), PID
4770, antes de enviar INT, TERM y finalmente KILL. La comprobación posterior
no encontró procesos propios gz/capture/ffmpeg. Se conserva vídeo, PNG, CSV,
logs y camera_coverage.json; es evidencia gráfica parcial con cierre fallido.

Durante esta prueba uchuvas solicitó prioridad para una tanda P4/P5 con Cycles.
Se difieren nuevos renders hasta su aviso de cierre y admisión propia renovada.
La reparación del cierre y el empaquetado de resultados no requieren iniciar
otra escena. La prueba de ciclo de vida headless previamente aprobada no
sustituye la comprobación de cierre de GUI/cámaras.

## Instrucción humana vigente: coordinación directa

El usuario indicó: «Olvida que hay otro agente, yo coordinaré el uso de memoria,
tú usa toda la memoria que necesites dejando al menos 4Gb libres».
Esta instrucción sustituye las esperas, coordinaciones y relevos entre chats.
No se consultarán ni enviarán mensajes a otros chats para continuar este trabajo.
Se actualizó el heartbeat existente, sin crear otra automatización.

Se retiran los límites artificiales de RSS de 4 GiB para headless y 6 GiB para
captura. RSS sigue registrándose; la condición de parada es la RAM libre real
de Windows: preventiva bajo 5 GiB, para preservar al menos 4 GiB. Las admisiones
iniciales de 9/11 GiB son estimaciones de arranque según consumos observados,
no límites del proceso. Continúa pendiente reparar y comprobar el cierre gráfico;
ninguna espera de autorización de otro chat bloquea ya esa tarea.

## Diagnóstico de cierre con procesos separados

Se ejecutaron cuatro pruebas cortas adicionales, conservadas en
`results/loop_capture_three_smoke_02` a `_05`. Cada una obtuvo 21 fotogramas
por cámara hasta 4 s simulados. El servidor separado terminó con código 0;
la GUI no terminó tras SIGINT y requirió SIGKILL (código -9). Son pruebas
fallidas, no una validación del cierre. En `_02` se confirmó el servicio de
parada; en `_03` a `_05` no se recibió confirmación aunque el servidor terminó.
Desactivar el diálogo de salida y restaurar la disposición SIGINT del lanzador
no resolvió el fallo. Se comprobó en /proc que los procesos de `_05` no tenían
señales bloqueadas ni ignoradas. No debe atribuirse todavía una causa al bloqueo.

La separación elimina el servidor huérfano observado con el lanzador combinado.
La inspección final no encontró procesos propios Gazebo, captura ni FFmpeg;
Windows disponía de 14.47 GiB libres. Se revisaron visualmente las imágenes
superior y general de `_02`: terreno verde continuo y estaciones visibles.
Pendientes: investigar el cierre gráfico, confirmar servicio de parada fiable,
grabar el recorrido completo y empaquetar el informe final. No se repitieron
los cinco servicios numéricos ya aprobados.

## Cierre gráfico comprobado y empaquetado nativo

`loop_capture_three_smoke_06` aprobó la captura de tres cámaras hasta 4 s:
21 fotogramas por vista, GUI=0, servidor=0, servicio stop confirmado y sin
errores. La inspección posterior no encontró procesos propios residuales.
El cierre ahora envía WM_DELETE_WINDOW solo a ventanas X11 cuyo _NET_WM_PID
corresponde al PID de nuestra GUI; la ejecución GUI usa Qt xcb y configuración
local sin diálogo de salida. Servidor y GUI tienen propietarios separados.
Esto evita depender del SIGINT que no concluyó las pruebas anteriores.
No se ha demostrado la causa interna del fallo de señales en Gazebo/Ruby/Qt.

Los cinco servicios nativos se empaquetaron en `docs/evidence/loop/native`:
CSV completos, configuración, guardas, supervisor, resumen comparativo,
paridad, gráficos y comprobaciones de ciclo de vida. Los ZIP se verificaron
con CRC y el manifiesto conserva SHA-256. No sustituyen la evidencia visual.

`loop_capture_complete_01` fue rechazado por admisión a 10.18 GiB libres;
no arrancó simulación. Una medición posterior dio 15.86 GiB libres. Se lanzó
`loop_capture_complete_02` mediante el supervisor con dos nuevas muestras;
su resultado debe comprobarse antes de declarar la grabación terminada.

## Revisión durante la grabación completa

La sesión 65966 permanece activa; no se ha reiniciado el caso. A 251 s de pared,
el CSV vivo alcanzó unos 107 s simulados, RSS observado 8.184 GiB y RAM Windows
libre 7.34 GiB. El log Ogre2 conservado en `capture/ogre2_during.log` confirma
llvmpipe (LLVM 20.1.2, Mesa 25.2.8), render CPU. La revisión de `lower_010s.png`
muestra estación inferior y terreno continuos; faltan los instantes posteriores.

Se repitieron las cuatro pruebas CTest con los cambios actuales: 4/4 PASS en
1.67 s. `verify_loop_capture.py` comprobó el vídeo corto `_06` con FFprobe y
una decodificación completa FFmpeg: 21 imágenes por vista, hueco máximo 0.2 s,
H264 1280x800, 20 fps, duración 1.05 s; PASS. El mismo verificador rechazó `_01`
por cierre forzado y ausencia de confirmación de parada. La prueba larga aún
no tiene resultado final; no se aplica la aprobación corta a toda su duración.

## Revisión de estaciones y ráfaga de la ejecución activa

Inspeccionadas imágenes reales de `loop_capture_complete_02`: `lower_145s.png`,
`upper_153s.png`, `overview_180s.png`, `overview_215s.png`, `lower_218s.png` y
`lower_228s.png`. La estación superior muestra el palet vacío tras la descarga;
la vista general muestra los carros y el indicador azul durante la ráfaga.
En el instante cercano al mínimo conservador bogie/motor (228 s), la vista
inferior no muestra cruce evidente de esos dos cuerpos. Tampoco se aprecia
penetración palet/plataforma en 145/153 s. Esto no resuelve las oclusiones de
la rueda tractora ni constituye un ensayo de contacto o envolvente continua.
Se conserva `clearance_screen.json` como resultado inconcluso de esferas,
no se modifica su criterio para declarar ausencia de colisiones.

Para recuperar margen de RAM se cerró únicamente la GUI propia con
WM_DELETE_WINDOW, verificando antes su PID 548 y partición exacta. El servidor
547 y las tres cámaras continuaron sin reinicio. `capture/gui_release.json`
registra las muestras alrededor de la intervención. A 542 s de pared había
unos 237 s simulados, RSS 4.385 GiB y 11.04 GiB libres en Windows. La grabación
sigue pendiente de terminar y de verificación integral.

## Cierre de validación nativa y entrega

`loop_capture_complete_02`: supervisor=0, GUI=0, servidor=0, stop confirmado,
341 s de cobertura en tres cámaras, 1706 imágenes por cámara, hueco máximo
0.2 s. Vídeo H264 1280x800, 20 fps, 85.3 s; decodificación completa PASS.
`verification.json` acredita servicio completo. Los CSV global/carriers/cables
son idénticos byte a byte al nominal headless; eventos idénticos. No quedaron
procesos propios tras el cierre. Pico RSS 8.418819 GiB; mínimo libre Windows
5.392113 GiB. Se ajustó admisión gráfica futura a 14 GiB según ese pico; sin GUI
el grabador admite 10 GiB. No hay límite artificial de RSS, sí reserva de host.

Capturas, vídeo, tiempos, logs del renderer, muestras de recursos y manifiesto
SHA-256 están en `docs/evidence/loop/native/capture`. Se inspeccionaron también
`upper_150s.png` y `overview_340s.png`, mostrando antes de descarga y final.
La reinstalación incremental final completó en 1 min 32 s; CTest 4/4 PASS en
2.34 s. Logs copiados a evidencia. Fetch origin confirmó divergencia 0/0 antes
del commit local; índice sin conflictos. No se fusionó main ni se publicó remoto.
El workflow CI está actualizado; no se afirma haberlo ejecutado en GitHub.

El informe de entrega es `docs/informe_nativo_circuito.md`. La auditoría conserva
las limitaciones de regresión recuperada, modelo reducido, oclusiones y revisión
geométrica muestreada. No se requiere reconstruir ni repetir los cinco casos.
