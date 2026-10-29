# Consolidación matemática y de software — 26 de octubre de 2026

Hito cerrado en código, especificación y pruebas locales. Al cerrar este hito,
la validación posterior en Gazebo estaba **pendiente**. Se ejecutó después por
solicitud del usuario; consultar los [resultados nativos y vídeos nuevos](validacion_minima_20261026.md).
Este documento conserva la evidencia y el protocolo del cierre original.
La [especificación vigente](modelo_vigente.md) describe las hipótesis y contratos.

## Base y evidencia preservada

**Verificado.** Se trabajó sobre `feat/ballasted-two-carrier-demo`, base
`6a824b4dc03be8e2cdb4bf4200c7289bdf7cd7cb`, inicialmente limpia. No se encontró
AGENTS.md en el repositorio, el espacio de trabajo ni sus ancestros.
La variante es `revised_supports`, un vano/dos carros/`central_only`.
Patio y entre pisos son alias geométricos; no se cuentan como instalaciones distintas.

Antes de editar coincidían los hashes de las 25 fuentes y los 47 archivos del
[manifiesto histórico](evidence/single_span_revised/manifest.json). Esos archivos
de resultados se conservan intactos. Las fuentes corregidas tienen hashes
nuevos en la [evidencia de este hito](evidence/model_consistency_20261026/results.json);
no se reescribe el manifiesto anterior para atribuirle el código nuevo.

**Verificado en registros.** Las capturas vigentes de patio y ladera ya estaban
completas: 816/976 fotogramas por cámara, cierre limpio y cinco CSV idénticos a
su núcleo de referencia. No se repitieron pilotos, capturas ni campañas.
Los seis casos archivados incluyen viento/calma, medio paso y lastre de 120 L.
Este último termina el recorrido pero falla el cribado de bases
(márgenes mínimos 0,670 y 0,634). Los seis casos registran cero intervenciones
de gobernador/topes. Nada de ello certifica estructura o seguridad.

## Hallazgos y cambios

| Conclusión | Clasificación | Tratamiento |
|---|---|---|
| El flujo de carga usaba una cinética distinta de la definida por energy() | Verificada por probe C++ y nuevas pruebas | Corregido mediante la derivada de E respecto de payload, con forma/estado fijos |
| El supervisor guardaba medio dt/medio período de forma sin transmitirlos al generador ballasted; tampoco transmitía calma | Verificada con dobles del flujo original | Propagación explícita; prueba de todos los archivos efectivos |
| Una futura ejecución por esa ruta podía tener una etiqueta distinta de la configuración ejecutada | Inferida del flujo comprobado | Se elimina la discrepancia; no se encontró una campaña ballasted archivada afectada |
| La campaña archivada usó run_ballasted_core, que sí transmitía dt/calm | Verificada por código y metadatos | Resultados anteriores preservados |
| El cierre de la interfaz Python podía ejecutar shutdown dos veces | Verificada en single.log y reproducida con doble | try_shutdown idempotente y tratamiento de ExternalShutdownException |
| Una fila de 50 valores con tiempo NaN causaba ValueError; otros no finitos podían llegar a publicaciones | Verificada en prueba de entrada límite, no observada en los registros reales | Rechazo previo completo, finitud y tiempo representable |
| Descubrimiento DDS/Gazebo tardío causó el fallo histórico de comandos | Inferida; no establecida por los registros conservados | Se mantiene como hipótesis, sin nueva promesa de ACK |
| El cierre real de todos los nodos, señales, transporte y nuevo núcleo en Gazebo funciona | Pendiente | Protocolo acotado más abajo |

En `results/ros_integration/single.csv` y `spider.csv` hay 53 filas por caso
hasta 1,041 s, objetivos 12/10,2 presentes y rejected final=1. Esto demuestra
efectos de aceptación y rechazo. `single.log` registra
`rcl_shutdown already called`; `spider.log` registra un segundo
KeyboardInterrupt durante destroy_node. Los bridges C++ acabaron con -2.
No se atribuyen todos esos cierres a una única causa ni se afirma que el arreglo
Python resuelva las señales de los bridges.

El probe aislado de carga con balanceo midió ΔE=602,99346732783533 J frente a
flujo anterior=602,99119159577685 J: diferencia 0,00227573205848 J.
La expresión corregida coincide con ΔE hasta 2,3×10⁻¹³ J. Este es un caso
algebraico de contabilidad a estado fijo; no es el residuo de una campaña.

Cambios de interfaz: parámetro opcional `shape_period` al final de las firmas
Python de configuración/generación y opción CLI `--shape-period`. Se conservan
las posiciones de argumentos previos, variantes y formatos CSV/JSON.
La telemetría ROS válida conserva su mapeo; una fila inválida no genera mensajes
derivados parciales. El cierre intenta destruir el nodo y cerrar el contexto;
si hay errores de limpieza, conserva la excepción original y añade contexto.
No se introducen topics, identificadores de comandos ni acuses nuevos.

La dinámica y las poses no cambian por la corrección energética: el término
modificado solo alimenta la contabilidad/residuo. No se exige igualdad del
flujo energético nuevo con los CSV históricos.

## Pruebas ejecutadas

**Verificado — ejecución actual.** En Ubuntu 24.04 vía WSL se recompiló el
núcleo con C++17 y se ejecutó CTest standalone: **7/7 aprobadas**, 2,10 s de
tiempo total de pruebas. La compilación y CTest terminaron con código 0.
El [log detallado](evidence/model_consistency_20261026/standalone_ctest.log)
y los [hashes/resultados](evidence/model_consistency_20261026/results.json)
identifican las fuentes comprobadas.

| Prueba | Resultado y alcance |
|---|---|
| ballasted_core | 24 casos nuevos: carga/descarga, cada carro y ambos, balanceo nulo/no nulo, velocidad nula/no nula bajo umbral de servicio; error absoluto <10⁻¹⁰ J. Conserva continuidad, masas, llenado y flecha |
| loop_core | Equilibrio de reacciones, extremos del cable, longitud natural fija, continuidad, IDs y dominio |
| ballasted_assets | Tres pruebas de escenas/equipo y conservación geométrica del edificio |
| ballasted_geometry | Regresión de envolventes de cajas; no contacto continuo |
| loop_assets | Regresión de activos del circuito histórico |
| loop_guard | Ocho pruebas, incluidas cuatro de configuración: cinco selectores con dobles y generación temporal; igualdad YAML/metadatos/params, modo y viento del SDF, variantes y alias |
| ros_interface_unit | 16 pruebas con dobles; incluye 150 combinaciones de campo no finito, límites de tiempo, índices y cuaternión, cierres normales/interrumpidos y preservación de errores |

Además, los tests nuevos de energía fallaron contra la fórmula anterior en un
binario temporal, con el mensaje de discrepancia de flujo, y pasaron con la
fórmula corregida. No se editó el núcleo para ejecutar ese control negativo.
Los dobles importan la interfaz real y reemplazan únicamente sus dependencias
ROS; no son una validación de DDS, señales del sistema operativo ni Gazebo.

Reproducción desde la raíz del repositorio en WSL:

```bash
cmake -S . -B build-ballasted -DAGRO_LOOP_STANDALONE=ON -DBUILD_TESTING=ON
cmake --build build-ballasted -j1
ctest --test-dir build-ballasted --output-on-failure -j1
```

La compilación standalone excluye el plugin y la prueba histórica dependiente
de Eigen/ROS. Recompilar el plugin corregido es un requisito del protocolo
posterior, no un resultado atribuido a estas siete pruebas.

## Protocolo mínimo posterior en Gazebo

**Pendiente — no ejecutado en este hito.** Objetivo: comprobar integración y
ciclo de vida del código corregido, sin repetir servicios completos ni vídeos.
El test existente `test_loop_native.py` genera seis carros y
`test_ros_integration.py` reutiliza una ruta histórica; no ejecutarlos sin
adaptar escena, destino y supervisión conforme a este protocolo.

### Preparación común

1. Compilar el plugin actualizado con ROS 2 Jazzy/Gazebo Harmonic, un proceso de
   compilación a la vez; registrar commit base, diff, hashes de fuentes y
   libAgroLoopSystem.so, versiones, comando y configuración efectiva.
2. Usar una carpeta nueva, por ejemplo `results/model_consistency_native_01`;
   si existe, elegir el siguiente número. Usar GZ_PARTITION nuevo y un dominio
   ROS libre para las pruebas históricas. Nunca sobrescribir evidencia previa.
3. Aplicar las guardas del supervisor existente: dos muestras de memoria libre
   ≥9 GiB separadas 5 s antes de Gazebo sin render; muestreo durante ejecución
   cada segundo, parada preventiva bajo 5 GiB y reserva de 4 GiB. Timeout de
   pared 120 s por comprobación. Parar solo los procesos lanzados por ella.
   Si no hay admisión, registrar `not_run` y terminar; no reducir umbrales.

### Una comprobación breve de la variante vigente

Generar ladera `revised_supports`, `central_only`, dt=0,001 s,
shape_period=0,01 s, calma y sin parada automática por ciclo completo.
La generación puede prepararse sin lanzar Gazebo:

```bash
python3 scripts/generate_ballasted.py --scenario ladera_agricola \
  --variant revised_supports --dt 0.001 --shape-period 0.01 --calm --gui \
  --output results/model_consistency_native_01/pilot
```

Aquí `--gui` solo conserva el mundo abierto y limita el factor de tiempo
real del generador; el proceso Gazebo se lanza **sin GUI**, con
`gz sim -s <world.sdf>` y sin `-r`, inicialmente pausado.
Verificar antes de lanzar la igualdad de valores en input.yaml, metadata.json,
loop.params y el SDF; `gust=false`, `mode=central_only`.
El paso del mundo ballasted es 0,02 s, distinto del dt interno de 0,001 s.

Secuencia mediante los mismos mensajes/tipos de `test_loop_native.py`:

1. Suscribirse a /world/agro_loop/stats y /agro_loop/status. Esperar mundo
   pausado; no exigir estado del núcleo antes de su primer paso.
2. Enviar WorldControl(pause=True, multi_step=200). Exigir acuse y luego
   observar finalización de los 200 pasos: mundo pausado a 4,00 s y estado
   del núcleo a 4,00 s (tolerancia 10⁻⁶ s). La carga inicial debe estar
   terminada. Conservar las muestras recibidas y su hora de recepción.
3. Esperar 0,3 s para drenar mensajes y observar 1 s de pared: reloj del mundo
   y último reloj del núcleo deben permanecer constantes. No confundir ausencia
   de nuevas publicaciones durante pausa con fallo.
4. Solicitar otros diez pasos, esperar todos ellos y pausa a 4,20 s antes de
   enviar reset. No usar la respuesta Boolean como prueba de finalización.
5. Enviar WorldControl(pause=True, reset.all=True). Exigir
   summary.json con `reset_interrupted`, datos previos preservados y nueva
   carpeta reset_1. Solicitar 50 pasos: reloj nuevo a 1,00 s, independiente
   del segmento anterior. Comprobar también reanudación explícita con
   WorldControl(pause=False): observar avance y volver a pausar.
6. Solicitar ServerControl(stop=True), esperar acuse **y** terminación del
   proceso con código 0. El segmento reset_1 debe cerrar como `interrupted`,
   sin sobrescribir el segmento anterior. Registrar tiempos reales del núcleo.
7. Ejecutar CLI por los mismos 4200 pasos con el **mismo** loop.params:
   `agro_loop_cli --config <loop.params> --output <nuevo_cli> --mode central_only --no-wind --until 4.1995`.
   El umbral interior al último paso evita añadir un paso por redondeo de
   la suma temporal; comprobar que el tiempo registrado termina en 4,20 s.
   Comparar byte a byte global/carriers/cables/bases/geometry del segmento
   anterior al reset, incluyendo esquema, orden y número de filas. Se esperan
   estados finales distintos en summary (partial_requested/reset_interrupted),
   pero eventos físicos y datos comunes iguales.

El comparador histórico `compare_loop_backends.py` exige servicios completos
y solo tres CSV: para esta prueba usar igualdad de bytes de los cinco archivos,
sin modificar ese comparador para simular un servicio completo. Si hay
diferencia, conservar ambos resultados y registrar el primer campo/tiempo
distinto; no regenerar automáticamente los valores esperados.

### Dos comprobaciones ROS históricas breves

Ejecutar single y spider secuencialmente con destinos nuevos y las mismas
guardas. Esperar una fila de 50 valores con tiempo >1 s. En single solicitar
x=12 y después x=100; en spider solicitar (10,2;0;7,68) con cuaternión identidad
y después x=100. Conservar el eco del objetivo válido, incremento de rejected
y mantenimiento del objetivo tras el rechazo. Retransmitir cada 0,2 s solo
mientras se espera el efecto, con límite de 20 s por solicitud.

Cerrar mediante la señal de terminación normal del launch, registrar por
separado códigos de launch, interfaz, bridges y Gazebo, y verificar ausencia de
doble shutdown. Una señal o código distinto en un bridge se registra como
resultado propio, no como fallo demostrado del adaptador Python. Este smoke
no necesita completar las trayectorias ni producir imágenes.

### Criterio de resultado y límites

Cada comprobación informa `passed`, `failed` o `not_run`, evidencia y motivo;
los acuses y cambios observados se guardan por separado. No promover a
verificada una comprobación no ejecutada. La paridad del mismo núcleo confirma
su integración, no una validación física independiente.

**Pendiente fuera del hito:** cierre completo cable–péndulo/impulsos, contacto
rueda–cable, dinámica de bases y líquidos, resistencia/fatiga, tolerancias y
capacidad portante del sitio. No se continúan buscando mejoras adicionales
para cerrar esta entrega.
