# Modelo vigente: un vano, dos carros y lastre

Especificación de la variante `revised_supports`, consolidada el 26 de octubre
de 2026. **Verificado** significa comprobado en código o pruebas citadas;
**inferido**, una interpretación cuya causa o alcance no está demostrado;
**pendiente**, una comprobación o un cierre físico todavía no realizado.
Estas etiquetas no expresan aceptación de una instalación.

## Identidad, configuración y unidades

**Verificado — implementación.** El generador combina los valores de
[`loop.yaml`](../config/loop.yaml), el equipo
[`ballasted_revised_supports.json`](../config/ballasted_revised_supports.json)
y la escena. Aplica las sustituciones de escena de la variante y las opciones
explícitas de llenado, paso, actualización de forma y calma. El resultado se
guarda en YAML, metadatos y parámetros del núcleo; el SDF selecciona modo y viento.
El modo ballasted es siempre `central_only`, incluso cuando el selector histórico
del supervisor se llama `hybrid_*`. `baseline` y `compact_candidate` siguen
siendo elecciones explícitas; no son el valor predeterminado.

| Magnitud efectiva nominal | Valor / interpretación |
|---|---|
| Topología | `single_span=1`; dos carros persistentes; dos extremos |
| Patio y entre pisos | Dos nombres de la misma geometría: 8,60 m horizontales / 3,20 m de desnivel |
| Ladera | 12 m horizontales / 3 m de desnivel |
| Carriles / portantes | Centros en y=±1,10 m; dos portantes por carril, separados 0,42 m |
| Cabezal / suspensión | 2,40 m sobre piso local / 0,48 m |
| Tractor / base | Tractor 0,30 m sobre trayectoria; proyección de cabezal 0,90 m respecto de base |
| Masa de bogie / suspensión / recipiente | 3 / 0,6 / 1,4 kg |
| Carga en carro 0 / carro 1 | 5 / 10 kg durante servicio cargado |
| Referencia de velocidad / aceleración | 0,20 m/s / 0,04 m/s² |
| Servo principal | Masa equivalente 45 kg; límite de fuerza 600 N; radio de par 0,30 m |
| Acoplamiento pasivo | k=1800 N/m, c=70 N·s/m; carrera ±0,22 m, velocidad relativa ±0,18 m/s |
| Cable | EA=80000 N; masa 0,08 kg por metro horizontal; exceso de longitud natural 0,001 |
| Pasos nominales | Integración 0,002 s; forma 0,02 s; CSV 0,05 s; dibujo/estado 0,10 s |
| Base | 600 L de capacidad conceptual × 0,8; 480 kg de agua + 85 kg secos; huella 2,8 × 3,3 m |

**Verificado — unidades.** Posiciones y longitudes en m; tiempo en s; masas en kg;
ángulos en rad; velocidades angulares en rad/s; fuerza en N, par en N·m,
potencia en W y energía en J. `wind_bearing_deg` está en grados;
`ballast_litres` está en litros. `rolling_coefficient` y `main_drag`
son resistencias viscosas en N·s/m, no coeficientes adimensionales de fricción.
`soil_mu=0.55` sí es adimensional y supuesto.

La densidad efectiva del agua está fijada a 1000 kg/m³ en el núcleo. El campo
JSON `water_density_kg_m3` es metadato nominal: cambiarlo no cambia la dinámica
ni el cálculo de lastre. No se ofrece un modelo de fluidos de densidad variable.

## Coordenadas, trayectoria y geometría

**Verificado — convenciones.** +x va del extremo inferior A al superior B, +z
apunta arriba y y es transversal. El carril 0 está en y negativo y avanza hacia
+x; el carril 1 está en y positivo y regresa. Los retornos superior e inferior
son semicírculos horizontales, etiquetados `lane=-1` y `lane=-2`.
Las bases están centradas en x=-0,90 m y x=X+0,90 m.

La coordenada común q y cada fase/offset e parametrizan el arco nominal del
perfil de terreno: s=q+fase+e, envuelto sobre la longitud de circuito. No son la
longitud material ni el arco instantáneo del cable deformado. El terreno entre
extremos es lineal en esta variante. Las guías suavizan la entrada a los retornos
y transfieren carga entre cable y apoyo mediante una fracción alpha entre 0 y 1.

La derivada d=dP/ds usada en dinámica se calcula moviendo la carga y resolviendo
equilibrios vecinos, con paso nominal 0,03 m. No se deriva el quiebre de un cable
con una carga puntual fija. Por ello |d| no tiene por qué ser 1. La forma se
mantiene entre actualizaciones; no se incluyen todos sus términos temporales.

Los ángulos theta_x/theta_y son modos de desplazamiento en los ejes horizontales
globales, no ángulos locales de los carriles:

```text
pallet = pivot + L (sin(theta_x), sin(theta_y), -cos(theta_x) cos(theta_y))
velocity = d (v + e_dot) + L (cos(theta_x) omega_x, cos(theta_y) omega_y, 0)
```

**Verificado — aproximación.** Esta velocidad omite la componente vertical del
balanceo y otros términos de cambio de forma; tampoco es la derivada completa
de la posición publicada. Con ambos ángulos no nulos, la distancia pivot–pallet
no es exactamente L. Son aproximaciones de dos modos de pequeño ángulo, no
cinemática exacta de un péndulo esférico ni de un sólido de seis grados de libertad.

En el plugin, yaw sigue la tangente del recorrido; pitch es el negativo de la
inclinación de esa tangente. La canasta usa el producto de rotaciones
Ry(-theta_x) Rx(theta_y) Rz(yaw). La línea visual de suspensión une pivot y pallet;
no impone una restricción mecánica adicional.

## Cable, fuerzas, actuadores y restricciones

**Verificado — equilibrio por portante.** Para un vano de ancho horizontal D,
usar xi=x-x0, w=masa_por_metro_horizontal·g y Pj≥0 por carga puntual:

```text
V(xi) = V0 + w xi + sum(Pj para xj <= xi)
z' = V/H;  z'' = w/H entre cargas;  salto de z' = Pj/H
V0 = H (z1-z0)/D - w D/2 - sum(Pj (D-xj)/D)
T = sqrt(H²+V²)
L0 = integral[0,D] sqrt(1+z'²)/(1+T/EA) dxi
```

H>0 se obtiene por búsqueda de raíz y L0 permanece fijo al cambiar la carga.
L0 inicial es la distancia recta entre extremos multiplicada por (1+slack).
La tensión no se recorta: exceder el límite conceptual aborta el cálculo.
Es una aproximación elástica cuasiestática por metro horizontal, distinta de
la catenaria material del [piloto histórico](modelo.md).

Cada carro transmite m·g·alpha/2 a cada portante de su carril. La fracción
restante se asigna a la guía. El reparto es simétrico supuesto; no identifica
transferencia lateral. Las reacciones registradas son R_izq=-V0 y R_der=V(D):
su suma debe ser wD+sum(Pj). Positivo significa demanda hacia abajo sobre
el apoyo; negativo significa levantamiento y exige retención en el modelo.
Cada fila de cables.csv representa **un portante** del par. La energía de
cables multiplica por dos la suma de cada carril.

**Verificado — ecuaciones reducidas.** Con u_i=v+e_dot_i, m_i=tara+payload,
mh_i=suspensión+recipiente+payload y G_i=max(0.1, |d_i|²), donde 0.1 es
el suelo numérico y d2_i es la segunda derivada de la familia P(s):

```text
Fci = -k e_i - c e_dot_i + Flocal_i
a_ref_servo = a_ref + 4 (q_ref-q) + 4 (v_ref-v)
Fm = clamp(M a_ref_servo + sum(Fci) + b_main v, ±Fmax)
q_ddot = (Fm - sum(Fci) - b_main v)/M
e_ddot_i = (Fci - m_i g d_i,z - b_roll u_i
             - m_i (d_i · d2_i) u_i²)/(m_i G_i) - q_ddot
```

Los dos factores 4 del servo tienen unidades s⁻² y s⁻¹, respectivamente.
La reacción del acoplamiento vuelve al tractor con signo opuesto. En
`central_only`, Flocal=0; permanecen resorte y amortiguador. El núcleo integra
q y offsets; no asigna q directamente a la referencia. El par reportado es
Fm·0,30 m; el rotor visual gira con el radio de retorno y no representa por sí
solo una transmisión dimensionada.

Los modos pendulares reciben aceleración del pivote, amortiguamiento y fuerza
de viento. El arrastre usa velocidad relativa:
Fwind=0,5 rho Cd A |U-velocity| (U-velocity), con A dependiente de la carga.
La proyección horizontal entra en los péndulos; no hay un cierre de todas las
reacciones sobre el tractor. La ráfaga se habilita solo por la configuración
y tiene envolvente suave; calma la deshabilita.

**Verificado — dominio numérico.** Se comprueban finitud, parámetros positivos,
paso hasta 0,01 s, periodos no inferiores al paso, continuidad y separación de
guías. Se rechazan tensión ≥4000 N, ángulos por modo con |theta|≥0,35 rad,
aceleración vertical efectiva fuera de (0,2g, 3g), separación entre centros
≤1,5 m y holgura nominal de canasta al perfil ≤0,4 m. Son límites del modelo,
no capacidades certificadas. La holgura al perfil no comprueba losas o barandas.

La carga/descarga exige presencia de ambos carros y velocidades de línea y
offset inferiores a 0,012 m/s; no exige igualdad matemática a cero. La rampa
de masa dura payload_ramp (2 s por defecto). En demanda cada maniobra útil o
auxiliar debe cubrir al menos esa duración; las entradas incompatibles se
rechazan antes de abrir los registros de servicio. Los límites de carrera/velocidad relativa son topes y un
gobernador ideales, con intervenciones contadas. Su balance de impulsos no
está físicamente cerrado.

## Energía y bases

**Verificado — definición contable.** La energía declarada es:

```text
E = 0,5 M v² + E_cables
  + sum[0,5 m_i |d_i|² u_i² + 0,5 k e_i²
        + 0,5 mh_i L² (omega_x²+omega_y²)
        + m_i g z_pivot - mh_i g L cos(theta_x) cos(theta_y)]
residuo = E-E_inicial
          -(Wmotor+Wlocal+Wviento+Ecarga-Wperdidas-Etopes)
```

Wmotor integra Fm·v; Wlocal integra Flocal·e_dot; Wviento integra
Fwind·velocity. Las pérdidas incluyen resistencia de línea, rodadura viscosa,
amortiguador del acoplamiento y amortiguamiento pendular. Trabajo positivo y
absorbido se acumulan por separado, ambos como magnitudes positivas.

La corrección de este hito usa, a estado y forma congelados,
`Ecarga += delta_payload · dE/dpayload`:

```text
dE/dpayload = g z_pallet + 0,5 |d|² (v+e_dot)²
              + 0,5 L² (omega_x²+omega_y²)
```

Esto hace coherente el intercambio de masa con E; no impone conservación exacta
durante la integración ni compensa arbitrariamente el residuo. Los cambios de
forma del cable, la reacción pendular completa y la cinética cruzada siguen
incompletos. Si intervienen topes/gobernador, su energía requiere revisión
adicional: el salto de energía absoluta no coincide en general con la pérdida
calculada. Los seis casos archivados registraron cero intervenciones.
**Pendiente:** cierre físico de esos acoplamientos y de los impulsos.

**Verificado — lastre y cribado.** Masa de agua=litros·llenado con la densidad
fija indicada; el centro de gravedad pondera la masa seca y el nivel del agua.
La envolvente suma los cuatro portantes, carga transferida a guías, cotas de
tractor y una cota aerodinámica conservadora en cada estación:

```text
N = masa_base g + demanda_vertical
margen_deslizamiento = mu N / max(1e-9, fuerza_horizontal)
margen_vuelco = N min(base_x,base_y)/2 / max(1e-9, momento)
presion_media = N/(base_x base_y)
in_domain = N>0 y ambos margenes>=1
```

Las bases permanecen fijas aun cuando in_domain=0. La cota del tractor no es
una solución de sus tensiones. La presión media no representa la presión real
en cada pie, ni prueba capacidad de losa/suelo. El centro de gravedad registrado
no convierte el cribado en una simulación de vuelco.

## Contratos de software y procedencia

**Verificado — variante vigente.** CLI y AgroLoopSystem ejecutan el mismo
núcleo. Gazebo acumula tiempo simulado e integra con paso fijo; presenta poses
cinemáticas mediante SetWorldPoseCmd, sin gravedad/contacto aplicados de nuevo.

| Salida | Contrato |
|---|---|
| global.csv | Tiempo, etapa, q/referencia/velocidad, fuerza/par/potencia, viento, extremos de cable y términos energéticos |
| carriers.csv | ID persistente, carril/vano, offset, masas, posiciones/velocidad aproximada, ángulos, fuerzas e intervenciones |
| cables.csv | Una fila por carril/vano y portante representativo: longitud natural, H, tensión máxima, flecha, carga y reacciones |
| bases.csv | Dos estaciones: llenado, masas, CG, normal, fuerza horizontal, momento, márgenes, presión e in_domain |
| geometry.csv | ID, yaw/pitch de bogie y posición del acople usados también por la representación |
| summary.json | Origen, modo, estado, métricas, eventos y límites; no certificado |

Las etapas son 0=carga inicial, 1=primer trayecto, 2=descarga en parada,
3=resto del circuito y 4=espera final. El estado `completed` significa
despacho y recorrido terminados, no instalación aceptada. En una interrupción
se conserva `interrupted`; reset de una ejecución aún activa preserva
`reset_interrupted` y comienza en `reset_1`, etc. Un resultado ya terminado
conserva su estado previo. El CLI usa `partial_requested` para una duración parcial.

`/agro_loop/status` publica gz.msgs.StringMsg con JSON: model, time_s, stage,
wind_m_s, line_speed_m_s, main_force_N; en esta variante añade litros por base,
cuatro márgenes y static_domain_warning. Se publica al dibujar, nominalmente
cada 0,10 s simulado. Durante pausa no hay obligación de nuevas publicaciones.
No hay comandos individuales ni ACK propios de este modelo. Pausa, pasos y
reset usan `/world/agro_loop/control`; parada usa `/server_control`.
Un Boolean de respuesta no prueba que los pasos hayan concluido: observar
estadísticas del mundo y estado del núcleo antes de la siguiente orden.

**Verificado — ROS histórico, separado.** Las entradas ROS son
`/agro/goal_x` (Float64 finito dentro de [1, span-1]) y
`/agro/target_pose` (PoseStamped, marco world o vacío, valores finitos).
El adaptador reenvía la pose a `/agro/goal_pose_bridge`; ros_gz_bridge la
convierte a `gz.msgs.Pose` en `/agro/goal_pose`. También convierte goal_x
a `gz.msgs.Double` en el topic Gazebo del mismo nombre. AgroCableSystem
recibe estos mensajes Gazebo; comprueba cuaternión no nulo, normaliza y
comprueba factibilidad de la pose/trayecto muestreado.
Rechazar conserva el objetivo previo. Las solicitudes de pose anteriores al
siguiente paso pueden ser sustituidas por la última.

El vector `/agro/telemetry` tiene exactamente 50 doubles, índices desde cero:

| Índices | Significado |
|---|---|
| 0 | Tiempo simulado, s |
| 1–6 | x,y,z,roll,pitch,yaw |
| 7–12 | vx,vy,vz,wx,wy,wz |
| 13–18 | Objetivo de posición y orientación |
| 19–25 | Error de posición, error angular, esfuerzo, residuo de asignación, feasible, rejected, saturated |
| 26+3i, 27+3i, 28+3i | Tensión, longitud y velocidad para cable i, i=0…7 |

El adaptador publica pose, velocidad, ocho tensiones, ocho longitudes y
factibilidad. Rechaza la fila completa antes de publicar si su longitud no es
50, algún valor no es finito o el tiempo no cumple 0≤t<2³¹ s. El dominio es
el de segundos int32 no negativos de ROS Time; los nanosegundos son <10⁹.
La orientación publicada convierte roll/pitch/yaw a cuaternión.

No existe identificador de comando ni ACK correlacionado: eco del objetivo y
contador rejected prueban efectos observables, no recibos individuales.
Retransmitir un rechazo puede aumentar el contador varias veces. El cierre
Python es idempotente ante contexto ya cerrado, sin ocultar fallos inesperados;
SIGINT/SIGTERM marcan una solicitud de parada y el bucle `spin_once` (timeout
solicitado de 0,1 s) sale antes de destruir el nodo y llamar `try_shutdown`.
Se desactiva el cierre automático por señales de rclpy y se restauran los
handlers anteriores. Los dobles no prueban señales reales ni descubrimiento
DDS; los [ensayos nativos single/spider](validacion_minima_20261026.md) comprobaron
recepción, aplicación/rechazo y cierre por SIGINT para esas dos ejecuciones.

**Pendiente — validación externa.** Contacto rueda–cable, dinámica de bases,
resistencia/fatiga de apoyos, capacidad de losa, tolerancias y energía eléctrica
quedan fuera de esta implementación. Consultar las
[pruebas de este hito y el protocolo posterior](consolidacion_modelo.md).

## Programa opcional de demanda

El [piloto de demanda](piloto_demanda.md) conecta un programa de servicio opcional al mismo nucleo continuo. Define referencias de recorrido, operaciones en reposo y masa util/auxiliar por carro. Sin ese programa se conserva el comportamiento historico. El registro adicional `demand_status.csv` usa fases 0 reposo, 1 espera, 2 carga, 3 viaje, 4 descarga, 5 restitucion y 6 terminado; no debe confundirse con las fases historicas de `global.csv`. Las energias mecanicas mantienen las convenciones anteriores. El coste humano de manipulacion se representa en tiempo, no como consumo metabolico ni energia de una grua; la potencia auxiliar electrica es una sensibilidad hipotetica.
