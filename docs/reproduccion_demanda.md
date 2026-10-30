# Reproducción del piloto de demanda

El camino mínimo reproduce una demanda fija de dos pedidos sobre el patio con
soportes revisados, dos carros, control central y calma. Ejecuta la política C:
8 kg suben al inicio y 8 kg se solicitan para bajar a los 70 s; ambos pedidos
son conocidos al inicio, con manejo de 20 s y plazos de 500 s. En esta prueba
la capacidad de mercancía adelantable es cero para exigir viajes separados;
los módulos auxiliares permanecen habilitados. Las llegadas terminan a los 90 s;
el simulador continúa hasta
entregar los pedidos, restituir los módulos y volver al estado terminal. El
límite de 900 s simulados detecta servicios que no cierren.

Es una regresión de integración, no una comparación estadística de políticas.
La línea de nueve postes sigue pausada y no participa en estos comandos.

## Preparar Ubuntu 24.04 con ROS 2 Jazzy

Usar una instalación de ROS 2 Jazzy configurada para Ubuntu 24.04. Desde la raíz
del checkout, instalar las dependencias y compilar. Estos comandos también se
ejecutan dentro de Ubuntu WSL; el inicio de cargas en WSL se hace después mediante
el supervisor Windows, para medir la memoria del host real.

```bash
sudo apt-get update
sudo apt-get install -y ros-jazzy-ros-base ros-jazzy-launch-ros ros-jazzy-ros-gz \
  ros-jazzy-gz-sim-vendor ros-jazzy-gz-plugin-vendor libeigen3-dev \
  python3-colcon-common-extensions python3-yaml python3-numpy python3-matplotlib \
  python3-scipy python3-pil ffmpeg
source /opt/ros/jazzy/setup.bash
colcon build --executor sequential --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
colcon test --event-handlers console_direct+
colcon test-result --verbose
python3 tests/test_installation.py
```

Registrar el commit con `git rev-parse HEAD`. Para reproducir exactamente una
entrega, usar un checkout limpio de ese commit y conservar el entorno instalado.
No ejecutar comandos en la carpeta contenedora que está fuera del repositorio.

## Una réplica en Linux nativo

Después de cargar ROS y la instalación, desde cualquier directorio escribible:

```bash
python3 "$(ros2 pkg prefix agro_teleferico)/lib/agro_teleferico/run_demand_smoke.py" \
  --linux-host --output results/demand_smoke_01
```

`--linux-host` mide MemAvailable de /proc/meminfo en un host Linux dedicado; se
rechaza en WSL. Se requieren dos muestras separadas cinco segundos con al menos
7 GiB libres. Se detiene por debajo de 5 GiB para proteger la reserva de 4 GiB.
No ejecutar esta modalidad en un contenedor cuya cuota sea menor que la memoria
del host. La prueba no renderiza imágenes ni abre una GUI.

## Una réplica en Windows y WSL

Compilar antes en el checkout de WSL y abrir PowerShell 7 en la raíz del mismo
repositorio Windows. El archivo de tarea incluido ejecuta el programa fuente
con las bibliotecas y binarios de la instalación cargada por el supervisor:

```powershell
./scripts/windows/run_guarded_demand.ps1 -RunName demand_smoke_guard_01 -TaskFile config/demand_smoke_task.json
```

El supervisor actualiza la memoria Windows y transmite su ruta mediante
`{host_memory}`. Conserva admisión, salidas, errores y procesos en
`results/demand_smoke_guard_01`; los resultados de la réplica quedan en
`results/demand_smoke_01`. Si falta RAM, conservar el intento y repetir más tarde
con otro RunName y otra ruta --output en una copia del JSON de tarea. No bajar
umbrales ni reutilizar directorios. Un archivo STOP_REQUESTED en el directorio
del supervisor solicita la parada preventiva.

## Qué comprobar en la salida

El código de salida debe ser cero y smoke.json debe contener passed=true y
todos sus checks en true. El programa genera y conserva:

| Archivo | Comprobación |
|---|---|
| requests.csv y dispatch.params | Entradas fijas efectivamente utilizadas |
| preparation/generated/loop.params | Configuración física del patio |
| calibration/predictor.csv y predictor.csv.manifest | 363 celdas recalibradas con ese núcleo y esa configuración |
| smoke.json | Hashes, procesos, aceptación y métricas de la réplica |
| native/validation.json | Cierre comparable y seis CSV idénticos entre Gazebo y CLI |
| gazebo_energy_audit.json y cli_energy_audit.json | Reconstrucción y aceptación energética terminal |
| gazebo_audit.json y cli_audit.json | Auditorías independientes de pedidos, operaciones e inventarios |
| calibration.log y validation.log | Diagnóstico, también cuando falle |

Se exige entregar los dos pedidos y utilizar los buffers. El check energy_acceptance
debe ser true; aplica el contrato energético terminal descrito en piloto_demanda.md.
El máximo residuo transitorio queda como diagnóstico, con los límites del modelo.
Se conservan las dos auditorías energéticas. La auditoría comprueba
su restitución y conservación, además de capacidad, calendarios y resumen. La
configuración nativa debe coincidir por hash con la usada para calibrar; el
binario y las entradas deben permanecer intactos. El cargador general exige
predictor.csv.manifest junto al CSV, con hashes SHA-256 de tabla, configuración
efectiva y núcleo compilado. Conservar ambos archivos juntos. Cambiar geometría,
integración, rampa o núcleo exige recalibrar; una tabla histórica sin manifiesto
se conserva como evidencia y se rechaza para nuevas ejecuciones.

Las métricas de smoke.json describen una sola realización. No calcular intervalos
de confianza ni rankings A/B/C/D con ella. La paridad comprueba integración del
mismo núcleo; no valida contacto rueda–cable, estructura ni consumo eléctrico real.

## Campaña completa opcional

No es necesaria para aprobar la réplica corta. Desde el checkout puede prepararse
una nueva campaña de 720 ejecuciones usando los parámetros y la calibración
acabados de generar:

```bash
python3 scripts/demand_campaign.py generate --config config/demand_pilot.json \
  --params results/demand_smoke_01/preparation/generated/loop.params \
  --predictor results/demand_smoke_01/calibration/predictor.csv \
  --output results/demand_campaign_new
```

La generación congela entradas y no inicia simulaciones. La ejecución se hace
bajo el supervisor de memoria mediante un JSON de tarea con minimum_free_gib=6,
timeout_s suficiente y argv equivalente a:

```text
python3 scripts/demand_campaign.py run --campaign results/demand_campaign_new --binary build/agro_teleferico/agro_loop_cli --host-memory {host_memory}
```

En Windows usar run_guarded_demand.ps1 con ese archivo y un RunName nuevo. El
runner también comprueba memoria durante cada caso. Para un ensayo acotado añadir
--limit 1; al quedar la matriz incompleta devuelve código distinto de cero y no
debe presentarse como campaña aprobada. Para continuar, usar --resume conservando
exactamente binario, fuentes e inputs; el runner verifica hashes.

Tras completar la matriz, auditar y analizar en salidas nuevas:

```bash
python3 scripts/audit_demand_outputs.py --campaign results/demand_campaign_new --output results/demand_campaign_new/audit_01.json
python3 scripts/analyze_demand.py --campaign results/demand_campaign_new --output results/demand_analysis_new
```

Los resultados publicados en docs/evidence se conservan inmutables. Los nuevos
resultados se guardan en results/ y como artefactos de CI; una promoción a release
requiere revisión de manifiestos y alcance. La suite demand-native de GitHub
ejecuta la réplica corta desde el paquete instalado y adjunta sus resultados.

Para auditar la energía de una ejecución completa en una salida nueva, desde el
checkout (o usando el script instalado):

```bash
python3 scripts/audit_demand_energy.py --requests results/demand_smoke_01/requests.csv \
  --params results/demand_smoke_01/preparation/generated/loop.params \
  --run results/demand_smoke_01/native/reference --output results/energy_audit_new.json
```

Ejecutar también audit_demand_outputs.py para verificar inventarios y pedidos.
Las campañas compactas conservan el estado inicial y final para esta auditoría;
el máximo transitorio completo procede del núcleo, no del muestreo compacto.

## Supervisión compartida

Los comandos Windows run_guarded_demand.ps1, run_guarded_loop.ps1 y
run_guarded_validation.ps1 delegan la admisión y el monitoreo a guard_common.ps1.
Se mantienen las dos muestras separadas cinco segundos, los mínimos por tarea,
la parada bajo 5 GiB y la reserva de 4 GiB. La muestra de memoria incluye un
historial de 15 s para todas las modalidades. Las utilidades Python compartidas
se instalan como supervision.py, sin importar ROS ni generadores de escenas.

Una admisión rechazada conserva admission.json y supervisor.json sin iniciar
WSL. Un fallo de monitoreo o una solicitud STOP_REQUESTED solicita parada y
espera hasta 55 s al hijo. Si queda vivo, se conserva su PID y el fallo; la
limpieza posterior debe usar identidad y ámbito registrados, nunca kill global.
Reintentar siempre con RunName y salida nuevos. El resultado Windows es fallo
ante parada preventiva o fallo de monitoreo aunque el proceso hijo salga cero.
