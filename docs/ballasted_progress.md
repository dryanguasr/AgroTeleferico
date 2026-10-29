# Piloto de un vano con lastre rellenable

> Historial de desarrollo. El diseño vigente, la nueva escena entre pisos y
> la evidencia versionada se describen en [Soportes revisados](soportes_revisados.md).
> Los estados y rutas de `results/` que siguen son registros de intentos previos.

## Estado actual: capturas pendientes completadas

Tras liberar RAM se completaron y verificaron la vista general corregida del
patio y las capturas de la variante compacta entre pisos. Ya no quedan tomas
pendientes por memoria. Las entradas de bloqueo posteriores en este documento
son historial conservado, no el estado actual. No quedan trabajos propios
activos; no se publicaron cambios ni se reactivaron automatizaciones.

Vídeos recomendados, locales:

- [Patio: vista general corregida](../results/ballasted_capture_patio_06/capture/gazebo.mp4).
- [Variante compacta: estación superior y cruce de barandilla](../results/ballasted_capture_compact_pisos_02/capture/gazebo.mp4).
- [Variante compacta: seguimiento corregido](../results/ballasted_capture_compact_pisos_02/capture/follow.mp4).
- [Variante compacta: vista general](../results/ballasted_capture_compact_pisos_01/capture/gazebo.mp4).
- [Ladera: vista general](../results/ballasted_capture_ladera_03/capture/gazebo.mp4).

| Toma | Vistas | Fotogramas por vista | Ciclo simulado | RAM libre mínima | RSS máximo |
|---|---|---|---|---|---|
| Patio 06 | General | 656 | 0,04–131 s | 6,775 GiB | 2,260 GiB |
| Compacta pisos 01 | General, inferior, superior, seguimiento | 816 | 0,04–163 s | 5,738 GiB | 2,823 GiB |
| Compacta pisos 02 | Superior, seguimiento corregido | 816 | 0,04–163 s | 8,309 GiB | 2,736 GiB |

Las tres verificaciones pasan: cierre limpio de Gazebo, cobertura sin huecos
mayores de 0,20 s, decodificación de todos los vídeos, conteo de fotogramas y
cuatro CSV idénticos byte a byte a su respectivo núcleo de referencia. Vídeos
1280 × 800 a 20 fps, reproducción nominal 4×; patio 32,8 s y compacta 40,8 s.
Cada carpeta `capture` conserva `verification.json`, mundo, metadatos,
procedencia y telemetría. Las admisiones usaron dos muestras separadas por
5 s y el mínimo intacto de 10 GiB; no se activó la parada preventiva.

Inspección visual: se abrió el patio a 4 s y la variante compacta en vistas
general/superior a 4 s, superior a 50 y 90 s, y seguimiento a 50 y 70 s.
El nuevo encuadre del patio muestra ambas bases y el vano. En la primera
toma compacta, el seguimiento a 50 s quedaba oculto por la losa. Se conserva
esa evidencia y se corrigió exclusivamente la cámara del equipo con cabezal
proyectado en `LoopSystem`: offset (-2,4; -3,2; 1,1) m desde la canasta,
observando desde el lado abierto del vano. El complemento recompiló con un
solo proceso. La segunda toma permite ver la canasta al cruzar y retornar;
la banda del edificio todavía oculta parcialmente la parte alta del bogie
en algunos encuadres del retorno. La vista superior complementa esa zona.
No se quitó ni modificó ningún obstáculo para mejorar las imágenes.

Esto cierra las capturas y su revisión visual parcial. Continúan pendientes
la revisión geométrica integral, las medidas reales y la comprobación
estructural descritas abajo. La variante no se declara instalación aceptada.

## Variante compacta separada: revisión del 17 de octubre

La configuración base y sus resultados se conservan. La alternativa se selecciona
explícitamente con `--variant compact_candidate` o `-Variant compact_candidate`;
no sustituye el valor predeterminado. Su archivo es
`config/ballasted_compact_candidate.json`. El edificio, sus losas y barandillas
son idénticos en ambas variantes, comprobado por prueba de activos.

Se exploraron primero 96 combinaciones sin proyección y después 168 con
proyección (`results/ballasted_layout_review_01`). El cribado estático usa
envolventes simplificadas y una fuerza tractora nominal, no cargas extremas.
La alternativa elegida adelanta el cabezal 0,90 m respecto a la base: en el
corredor la base queda en x=9,50 m y el extremo del vano en x=8,60 m. Mantiene
la huella de 2,8 × 3,3 m, con el borde de base a 0,10 m del borde supuesto del
corredor. Dos postes laterales y brazos visibles sustituyen al mástil central
que interferiría con el retorno. El tractor se coloca 0,35 m sobre el recorrido,
la suspensión mide 0,48 m y la holgura del cable es 0,001. El equipo compacto
es común a los tres escenarios. No se agregaron apoyos intermedios ni anclajes
al edificio.

Los postes llegan a 2,91 m sobre el piso: dejan 0,05 m frente al intradós
supuesto de 2,96 m. Esta holgura nominal no incluye tolerancias, deformación
de la estructura ni medición del edificio. La masa seca de 85 kg y su centro
de gravedad siguen siendo supuestos; falta calcular y pesar el conjunto real.

La compilación independiente y la del complemento Gazebo terminaron sin error.
Pasaron las seis pruebas de CTest, incluida la conservación del edificio y la
geometría de la nueva variante. `results/ballasted_compact_01` contiene seis
ciclos completos del núcleo: los tres escenarios, ladera sin viento, ladera
con medio paso y patio con 120 L. La diferencia máxima al reducir el paso es
0,00001923 m; el viento cambia el balanceo transversal hasta 0,014939 rad.

Con 480 L por base, los márgenes mínimos preliminares de deslizamiento/vuelco
son 2,126/2,140 en patio, 2,109/1,990 entre pisos y 2,033/2,000 en ladera.
**El caso de 120 L falla**: márgenes mínimos 0,803/0,808 y 453 muestras fuera
del dominio por base. Un ciclo completado no implica estabilidad aceptada.
La proyección se incluye ahora en el momento conservador sobre la base.

La revisión SAT de cajas guardadas no encuentra intersecciones en patio
(241.966 pares) ni entre pisos (342.928 pares): estaciones contra losas y
barandillas, y canastas/cargas contra esos obstáculos y las cajas de estaciones
en todo el recorrido, incluidos retornos. Informes `geometry_full_01.json`
en cada caso. La esfera conservadora del evaluador inicial aún señala
candidatos; la prueba de cajas afina ese aviso, sin certificar la instalación.
Quedan fuera bogies/ruedas, suspensión, cables/tractor, arriostramientos,
otros obstáculos del lugar, colisiones continuas y resistencia estructural.

Gazebo sin render completó la variante entre pisos en
`results/ballasted_compact_native_pisos_01`: salida 0, 23,33 s reales,
RAM libre mínima 8,829 GiB, RSS máximo 1,469 GiB. Los cuatro CSV son idénticos
byte a byte al núcleo; evidencia en `parity.json`. La variante aún necesita
inspección visual propia y revisión integral; no se declara aceptada.

Para decidir una implantación real faltan las medidas de altura libre,
barandilla, borde y ancho útil del corredor; capacidad portante de la losa y
cargas puntuales admisibles en pies; masa/centro de gravedad del equipo;
rigidez y resistencia de brazos, postes y uniones; tolerancias, flecha y
separaciones de todos los elementos móviles. La alternativa deja documentada
la colocación propuesta sin suponer que estas comprobaciones ya existen.

### Capturas y memoria de esta continuación

`ballasted_capture_ladera_02` no lanzó Gazebo: segunda muestra 9,704 GiB
frente a 10 GiB. Después de completar trabajo independiente, dos nuevas
muestras dieron 10,172 y 10,169 GiB y admitieron `ballasted_capture_ladera_03`.
La toma terminó con salida 0 y verificación aprobada: cuatro vistas con 976
fotogramas cada una, 0,04–195 s simulados, hueco máximo 0,20 s. Los dos vídeos
duran 48,8 s a 20 fps (4×); decodificación correcta y cuatro CSV idénticos al
núcleo nominal. RAM libre mínima 7,214 GiB y RSS máximo 2,618 GiB. Se abrieron
las imágenes general y de estación a 4 s y seguimiento a 90 s. Evidencia:
`results/ballasted_capture_ladera_03/capture/verification.json`.

- [Ladera, general](../results/ballasted_capture_ladera_03/capture/gazebo.mp4).
- [Ladera, seguimiento](../results/ballasted_capture_ladera_03/capture/follow.mp4).

La mejora de patio `ballasted_capture_patio_04` fue rechazada por el supervisor
en la primera muestra: 9,215 GiB frente al mínimo de 10 GiB. **No lanzó
Gazebo ni generó captura**; `admission.json` conserva la evidencia. No hubo
denegación de permisos ni error de cuota. La captura de la variante compacta
queda pendiente por la misma disponibilidad de memoria; no se intentó.
No quedan trabajos propios activos ni resultados inciertos. Se mantienen reserva de
4 GiB y parada preventiva bajo 5 GiB, sin cerrar procesos ajenos.

Comandos para futuras tomas, siempre en carpetas nuevas y de una en una:

```powershell
& './scripts/windows/run_guarded_loop.ps1' -RunName ballasted_capture_patio_05 -Case capture -Scenario buitrago_patio -NoGui -View overview -Until 131
& './scripts/windows/run_guarded_loop.ps1' -RunName ballasted_capture_compact_pisos_01 -Case capture -Scenario buitrago_entre_pisos -Variant compact_candidate -NoGui -AllViews -FollowCarrier -Until 163
```

Los apartados siguientes conservan el historial de la configuración base.

Estado vigente: núcleo ensayado, tres escenarios completos en Gazebo sin render y capturas completas verificadas de patio y entre pisos. Pendientes: captura de ladera, mejora del encuadre general de patio y revisión geométrica integral. Rama `feat/ballasted-two-carrier-demo`, base `839396ca156384e5c6c704ae5035c68abe237acf`. No se publicaron cambios ni se reactivaron automatizaciones. La fotografía sigue fuera del repositorio.

## Implementación

Se reutilizan el equilibrio elástico de cables, integrador, registro y plugin `AgroLoopSystem`. La opción `single_span=1` añade dos extremos y dos carros persistentes, sin cambiar la topología histórica por defecto. El modo es `central_only`; ambos carros cargan y descargan en parada. Las guías llegan horizontalmente a las estaciones. El modelo es reducido, sin contacto nativo rueda–cable ni dinámica nativa de bases.

`config/ballasted_common.json` contiene el equipo y tres JSON seleccionan las escenas. `scripts/generate_ballasted.py` genera los mundos con un atrio compartido para ambos casos Buitrago. Las dimensiones son supuestos, no medidas extraídas de la foto.

| Parámetro | Valor supuesto |
|---|---|
| Vano patio / entre pisos / ladera | 6 / 10 / 12 m |
| Desnivel | 0 / 3,2 / 3 m |
| Cabezal sobre piso local | 2,4 m |
| Radio retorno / separación carriles | 1,1 / 2,2 m |
| Separación de portantes de cada carril | 0,42 m |
| Tara: bogie / suspensión / recipiente | 3 / 0,6 / 1,4 kg |
| Carga ascendente / descendente | 5 / 10 kg |
| Velocidad / aceleración | 0,2 m/s / 0,04 m/s² |
| Suspensión | 0,55 m |
| Depósito nominal / llenado por estación | 600 / 480 litros |
| Masa seca / con agua por estación | 85 / 565 kg |
| Huella / fricción supuesta | 2,8 × 3,3 m / 0,55 |
| Pretensión tractor | 100 N |
| Paso / registro / visualización | 0,002 / 0,05 / 0,1 s |

El patio se acortó de 8 a 6 m para que la estación y retorno queden antes del corredor supuesto. El motor está en A/inferior; el tractor separado muestra marcadores de movimiento. Los recipientes se mantienen durante las operaciones; no hay teletransportación de carros.

## Lastre y física

El agua se calcula como `1000 × litros/1000 × llenado` kg; el centro de gravedad cambia con el nivel. `bases.csv` registra litros, masas, centro de gravedad, normal, fuerza horizontal, momento, presión media y márgenes por estación. Las fuerzas incluyen cuatro portantes, peso propio, cargas móviles, transferencia a guías, una envolvente conservadora del tractor y fuerza aerodinámica horizontal. Se consideran alturas de aplicación y brazos de las cargas en retorno. Valores fuera del dominio producen `in_domain=0` y advertencias, sin añadir lastre o fricción silenciosamente.

Las bases son cinemáticamente fijas: no se ha simulado deslizamiento, vuelco, líquidos ni resistencia de losa. El análisis cuasiestático y la presión media no aprueban la instalación. La envolvente del tractor no es una identificación de sus tensiones ni dinámica de contacto. El agua modifica masa y análisis, no únicamente apariencia.

Los portantes conservan longitud natural fija y flecha dependiente de la carga. En `cables.csv`, cada fila `(lane, span)` contiene valores por cable de un par simétrico: representa dos portantes iguales, no un reparto asimétrico identificado. Las primitivas visuales y guías son aproximaciones segmentadas pendientes de revisión detallada.

El balance registra trabajo positivo y absorbido, pérdidas, energía de carga/descarga de ambos carros y residuo. Energía absorbida no equivale a electricidad almacenada. El acoplamiento cable–péndulo sigue siendo reducido; no hay ahorro físico ni Sim2Real acreditado.

## Evidencia comprobada

Campaña: `results/ballasted_core_04/suite.json`; resumen: `reassessment.json`. Incluye comandos, hashes de binario/fuentes, configuración, telemetría, eventos, logs e informes.

| Caso nominal | Tiempo simulado | Tensión máxima por portante | Residuo energético final |
|---|---:|---:|---:|
| Patio | 130,265 s | 255,847 N | 0,175 J |
| Entre pisos | 175,261 s | 262,202 N | 0,614 J |
| Ladera | 193,959 s | 266,232 N | 0,967 J |

Seis casos completaron el núcleo: los tres nominales, ladera sin ráfaga, ladera con mitad de paso y patio con 120 litros por base. Pasan IDs persistentes, dos estaciones, vuelta completa, ausencia de fuerza de motor local, servicio de ambos carros y carga en parada. Diferencia máxima de recorrido al reducir el paso: `1,923e-5 m`, frente a tolerancia de 0,005 m. La ráfaga cambia el balanceo transversal hasta 0,01498 rad.

En patio, el margen mínimo preliminar de vuelco baja de 2,921 a 1,102 al pasar de 480 a 120 litros; el de deslizamiento baja de 2,929 a 1,106. No se interpretan esos valores como capacidades seguras.

Compilación ROS 2 Jazzy/Gazebo 8.11.0: código 0. CTest: 6/6, cubriendo núcleo, assets, supervisor y física histórica. El test nuevo incluye continuidad, cargas 0/5/10 kg, llenado y rechazo de parámetros inválidos. Los fallos previos quedan conservados: `ballasted_core_02` detectó movimiento durante carga; `ballasted_core_03` completó simulaciones pero falló al serializar NumPy en informes. La campaña 04 es posterior a las correcciones.

## Geometría y evidencia pendiente

Entre pisos aparecen candidatos de interferencia de los recipientes con la baranda y de la estación superior con la losa siguiente. Se conservan barandas y losas: no se abrieron huecos ni se quitaron obstáculos. Etiqueta requerida: **ubicación conceptual; capacidad de losa y autorización pendientes**.

La revisión actual usa envolventes conservadoras muestreadas para recipiente–baranda y estación–losa. Faltan envolventes completas de bogies, cargas, suspensión, cables, tractor, guías, arriostramientos, patas y obstáculos del sitio. No se acredita ausencia continua de colisiones. La paridad nativa/CLI de los tres escenarios ya está comprobada. La revisión visual es parcial y falta la captura de ladera; véase el cierre actualizado al final.

## Ejecución reproducible

Desde la raíz en WSL:

```bash
source /opt/ros/jazzy/setup.bash
CMAKE_BUILD_PARALLEL_LEVEL=1 colcon build --executor sequential --cmake-args -DBUILD_TESTING=ON
ctest --test-dir build/agro_teleferico --output-on-failure
python3 scripts/run_ballasted_core.py --binary install/agro_teleferico/lib/agro_teleferico/agro_loop_cli --output results/ballasted_core_new
python3 scripts/summarize_ballasted.py results/ballasted_core_new
```

En este PC compartido, ejecutar un caso pesado a la vez mediante PowerShell:

```powershell
./scripts/windows/run_guarded_loop.ps1 -RunName ballasted_patio_new -Case central_gust -Scenario buitrago_patio
./scripts/windows/run_guarded_loop.ps1 -RunName ballasted_patio_capture_new -Case capture -Scenario buitrago_patio -NoGui -AllViews -FollowCarrier -Until 131
```

Cambiar `-Scenario` por `buitrago_entre_pisos` o `ladera_agricola`; para capturas usar respectivamente `-Until 176` y `-Until 195`. Los interiores siguen sin ráfaga aunque el selector histórico del supervisor se llame `central_gust`. Los directorios deben ser nuevos.

Se mantienen dos mediciones de admisión separadas, 9 GiB para Gazebo sin render, 10 GiB para captura sin GUI y 14 GiB con GUI. Parada preventiva bajo 5 GiB y reserva de 4 GiB. No se detienen procesos ajenos ni se eluden controles. `ballasted_native_patio_01` quedó sin iniciar por 8,758 GiB; `ballasted_capture_patio_01` por 9,564 GiB frente al mínimo de 10. No son errores de cuota o permisos.

`ballasted.launch.py` ofrece escenario, llenado, salida y GUI para entornos dedicados. En este PC debe preferirse el supervisor. Las capturas usan sensores de Gazebo en vivo, con leyenda; no son un replay de telemetría.

## Antes de diseño físico

Se necesitan levantamiento dimensional del atrio, capacidad de losa y autorización, propiedades de suelo y nivelación, diseño de retornos y freno, rigidez/pretensión identificadas, contención del depósito y revisión estructural del bastidor. No se ha autorizado ni realizado montaje físico.

## Actualización de verificación nativa

`results/ballasted_native_patio_02/central_gust/guard_summary.json` confirma
patio completo en Gazebo, salida 0, sin parada preventiva. Tiempo de pared:
133,57 s; RAM libre mínima: 7,651 GiB; RSS máximo del árbol: 1,462 GiB.
`parity.json` confirma igualdad byte a byte de `global.csv`, `carriers.csv`,
`cables.csv` y `bases.csv` frente a la campaña 04. No hay vídeo de esta
prueba porque se ejecutó sin render.

`results/ballasted_edges_01` añade dos comprobaciones completas: masas
iguales de 5 kg en patio (entrada motriz neta 16,649 J, sin ganancia mecánica
neta) y depósito vacío. El segundo caso produce advertencia: margen mínimo
de vuelco 0,496 y de deslizamiento 0,498; las bases permanecen fijas y eso
no se interpreta como estabilidad física.

El indicador de separación del suelo del núcleo usa el perfil inclinado
entre extremos como referencia en el caso entre pisos. No sustituye la
comprobación contra la geometría real de piso, baranda o losa del asset.
Las ejecuciones sin render nuevas permiten factor de tiempo real libre;
las capturas mantienen factor solicitado 1. El paso del núcleo no cambia.

## Punto de continuación (17 de octubre de 2026)

Entre pisos completó Gazebo: salida 0, sin parada preventiva, 179,30 s de
pared, RAM libre mínima 5,684 GiB, RSS máximo 1,462 GiB. Sus cuatro CSV
son idénticos byte a byte a la campaña 04; evidencia en
`results/ballasted_native_pisos_01/parity.json`. Persisten los candidatos
geométricos de baranda/losa y no se acepta la ubicación.

El SDF entre pisos pasó `gz sdf -k`; los scripts y el launch pasaron
comprobación de sintaxis. No hay procesos de simulación lanzados por este
trabajo pendientes: ambos supervisores cerraron con código 0.

Bloqueo en el cierre anterior: última muestra de Windows 8,49 GiB libres, inferior a los
9 GiB de admisión sin render y 10 GiB de captura sin GUI. No se inició
Gazebo de ladera ni se generaron vídeos. No falta autorización del usuario.

Al continuar, medir memoria y usar directorios nuevos. Prioridad:
1. Ejecutar `ladera_agricola` con supervisor y comprobar paridad con el caso 02 de la campaña 04.
2. Capturar patio (131 s), entre pisos (176 s) y ladera (195 s), uno a la vez, con admisión y monitoreo.
3. Abrir las imágenes y revisar envolventes completas, especialmente guías y retornos.
4. Mantener el conflicto entre pisos explícito; ajustar solo con geometría justificable, nunca retirar obstáculos para ocultarlo.
5. Verificar vídeos, eventos, cierre de procesos y cobertura; actualizar el informe con evidencia real.

La rama contiene cambios locales sin commit nuevo. Base conservada:
`839396ca156384e5c6c704ae5035c68abe237acf`. El Goal no está terminado.

## Continuación: ladera y geometría de baranda/losa

La ladera nativa completó 193,959 s simulados, salida 0, en 23,239 s de
pared con factor de tiempo real libre. RAM libre mínima: 8,813 GiB; RSS
máximo: 1,265 GiB. Sus cuatro CSV coinciden byte a byte con la campaña 04.
Evidencia: `results/ballasted_native_ladera_01/central_gust/guard_summary.json`
y `results/ballasted_native_ladera_01/parity.json`. Ya están completos los
tres casos Gazebo sin render, separados de la campaña del núcleo reducido.

La revisión `review_ballasted_geometry.py` lee el SDF guardado y la
telemetría; no ejecuta simulación. Usa separación de ejes para cajas
orientadas y aplica las rotaciones del recipiente del plugin en los tramos
rectos. Su prueba de solape, separación, contacto tangencial y rotación
pasó. No se extrapola a contacto físico ni a todo el recorrido continuo.

Resultado en `results/ballasted_core_04/01_buitrago_entre_pisos/geometry_boxes_01.json`:
- Una intersección estática confirmada entre las cajas visuales del mástil
  superior y la losa del segundo corredor. Intervalo vertical común:
  6,16–6,40 m; solape de 0,12 × 0,12 × 0,24 m.
- 84 combinaciones de primitivas móviles y obstáculos intersectan en
  muestras guardadas, tras 431.360 comparaciones de cajas. Afectan a ambos
  carros, sus recipientes y algunas cargas, con pasamanos, travesaños y
  postes de la baranda. El primer contacto muestreado del carro 1 aparece
  a 17,55 s; el del carro 0 a 49,35 s.
- Los intervalos primero/último de cada combinación pueden abarcar varias
  pasadas; no significan contacto continuo durante todo ese intervalo.
- Quedan fuera ruedas/bogie, suspensión, cables/tractor, arriostramientos,
  orientaciones de retorno y otros obstáculos. La prueba es más precisa
  que la envolvente inicial, pero no es validación integral de colisiones.

Con el piso superior en 3,2 m y el intradós siguiente en 6,16 m, la altura
libre modelada es 2,96 m; el mástil actual alcanza 3,20 m sobre su piso.
Reducir el conjunto superior exige revisar también tractor y bogie; elevar
el recorrido para superar la baranda agrava la restricción de altura. No
se alteraron medidas del edificio ni se quitaron obstáculos para aprobarlo.

## Primera captura completa de patio

`results/ballasted_capture_patio_02/capture/verification.json` pasa cobertura,
decodificación, cierre y paridad. Cuatro cámaras, 656 fotogramas por cámara,
de 0,04 a 131 s, separación máxima 0,20 s. Vídeos de 32,8 s a 20 fps,
reproducción nominal 4×. RAM libre mínima 7,203 GiB, RSS máximo 2,831 GiB.

Se abrieron imágenes general, estación y seguimiento. La vista general de
esta primera toma queda parcialmente ocultada por el corredor: se conserva
como evidencia, pero no es el encuadre general preferido. Las imágenes de
estación muestran los niveles de agua y ambas bases; el seguimiento muestra
bogie, suspensión, recipiente y retorno. La cámara general se corrigió para
nuevas tomas. `ballasted_capture_patio_03` no llegó a iniciarse: segunda
muestra de admisión 9,727 GiB frente al mínimo de 10 GiB.

## Cierre de esta continuación

**Núcleo reducido:** se conservan las ocho ejecuciones previas y sus pruebas.
**Gazebo sin render:** los tres escenarios completos, salida 0 y paridad
byte a byte de los cuatro CSV con los casos nominales de la campaña 04.
**Capturas:** patio y entre pisos completos y verificados; ladera pendiente.
**Geometría:** revisión estática de cajas y revisión visual parcial confirman
interferencias del modelo entre pisos. No es validación física.

Entre pisos: `results/ballasted_capture_pisos_01/capture/verification.json`
aprobado, 881 fotogramas por vista, 0,04–176 s simulados, hueco máximo
0,20 s. Vídeos de 44,05 s a 20 fps, reproducción nominal 4×. RAM libre
mínima 6,983 GiB, RSS máximo 2,821 GiB. Se abrieron vistas general, superior
y seguimiento, incluidas las imágenes de 50 s donde se aprecia el cruce
por la baranda. El aviso de ubicación no aceptada está visible.

Vídeos locales (no publicados):
- Patio, general original parcialmente ocluida: [MP4](../results/ballasted_capture_patio_02/capture/gazebo.mp4).
- Patio, seguimiento completo: [MP4](../results/ballasted_capture_patio_02/capture/follow.mp4).
- Entre pisos, general: [MP4](../results/ballasted_capture_pisos_01/capture/gazebo.mp4).
- Entre pisos, seguimiento y conflicto: [MP4](../results/ballasted_capture_pisos_01/capture/follow.mp4).

La toma `ballasted_capture_ladera_01` no inició Gazebo: admisión de
9,829 GiB frente al mínimo de 10 GiB. La mejora general de patio
`ballasted_capture_patio_03` tampoco inició: segunda muestra 9,727 GiB.
Se conservan ambos `admission.json`. No hubo denegación de permisos ni
error de cuota. Ningún proceso pesado propio queda pendiente de cierre.
No se cerraron procesos ajenos ni se reactivaron automatizaciones.

Próximo paso: cuando dos muestras separadas superen 10 GiB, grabar ladera
195 s y repetir solo la vista general corregida de patio 131 s, en carpetas
nuevas y secuencialmente. Verificar cada toma con `verify_ballasted_capture.py`
y abrir sus imágenes. No modificar los umbrales para forzar admisión.

## Nueva admisión tras la indicación «Procede»

El intento ballasted_capture_patio_05 fue rechazado antes de lanzar Gazebo: primera muestra de 8,115 GiB libres frente a 10 GiB requeridos. Evidencia: results/ballasted_capture_patio_05/admission.json. No hubo segunda muestra, captura, denegación de permisos ni resultado incierto. La toma de la variante compacta sigue pendiente por el mismo umbral; no se intentó. Se conservaron las protecciones y no se cerraron procesos ajenos ni se reactivaron automatizaciones. No quedan trabajos propios activos.
