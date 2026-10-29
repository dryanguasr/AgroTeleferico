# Piloto de demanda bidireccional y buffers

## Diseño congelado

Variante `revised_supports`, patio entre pisos (8,6 m horizontales, 3,2 m de
desnivel), dos carros acoplados y modo `central_only`, en calma. Se preserva
el programa histórico como modo predeterminado. No hay inversión de marcha
ni accionamiento independiente de los carros.

| Política | Despacho | Inventarios opcionales |
|---|---|---|
| A | Inmediato | Ninguno |
| B | Espera coordinada, máximo 60 s y limitada por plazos | Ninguno |
| C | Inmediato | Mercancía adelantable y contrapesos |
| D | Espera coordinada, máximo 60 s y limitada por plazos | Ambos |

La configuración reproducible está en `config/demand_pilot.json`. Sus valores
son **supuestos sintéticos**, no demanda agrícola medida ni capacidades
certificadas. Cada réplica tiene 60 minutos de llegadas, más entrega de cola
y restitución; las tasas son 12, 24 y 36 pedidos/h. Se comparan demanda
equilibrada y predominio alternado cada diez minutos. Treinta semillas por
combinación, compartidas entre las cuatro políticas, producen 720 ejecuciones.

Los pedidos indivisibles pesan 2/5/8 kg (40/40/20 %) y vencen 6/9/12 minutos
después de solicitarse (20/60/20 %). El 30 % puede anunciarse hasta 120 s antes;
no se conoce antes del anuncio y sólo C/D puede adelantarlo. Un operario por
estación atiende los primeros ocho minutos de cada ciclo de diez. Cada carga
o descarga dura triangular(12,20,35) s + 2 s/kg, incluyendo la rampa de masa
de dos segundos. Una operación no cruza el cierre de su ventana.

La capacidad experimental es 10 kg por carro, contando mercancía y auxiliares.
Cada estación dispone de diez módulos auxiliares identificados de 1 kg y
20 kg de espacio para mercancía futura preparada en origen. Los módulos son
distintos del lastre fijo de las bases. Su manipulación cuesta 8+2n s por
conjunto y operación.

## Interpretación de la comparación

La prioridad es entregar dentro de plazo. No se descartan pedidos retrasados.
Los cuatro casos conservan la misma demanda, estado inicial y criterios de
cierre. Al finalizar se entregan todos los pedidos, se restituyen los módulos
a su estación original y los carros regresan vacíos a su posición inicial.
La restitución cuenta en tiempo y energía; no se permite obtener un ahorro
aparente consumiendo el inventario potencial de la estación superior.

La física es continua entre viajes. El predictor de despacho utiliza el mismo
modelo reducido y sólo pedidos conocidos; su resultado es una heurística, no
una prueba de óptimo global. Las diferencias estadísticas son pareadas por
semilla, con intervalos bootstrap del 95 % y 10 000 remuestreos.

El resultado mecánico primario es trabajo motriz positivo, total y por kg útil.
El trabajo absorbido, las pérdidas, el intercambio de masa y el residuo se
mantienen separados. La sensibilidad eléctrica es **hipotética**:

```text
consumo_estimado = trabajo_positivo / eficiencia + potencia_auxiliar * tiempo_encendido
recuperación_potencial = eficiencia_regenerativa * trabajo_absorbido
saldo_hipotético = consumo_estimado - recuperación_potencial
```

Se cruzan eficiencias 0,70/0,85/0,95, potencias auxiliares 0/5/20 W durante toda
la ejecución y recuperación 0/0,50. No se supone batería ni almacenamiento
eléctrico demostrado.

## Evidencia de ejecución

**Verificado (preflight, revisión 2):** 14/14 CTest aprobadas. Las 363
celdas del predictor permanecen idénticas y los cinco CSV del caso histórico
mantienen igualdad exacta. Las cuatro políticas entregaron los 51 pedidos del
caso de estrés y terminaron comparables, sin topes; una auditoría independiente
reconstruyó pedidos, operaciones e inventarios y aprobó los cuatro casos.
La evidencia está en `results/demand_preflight_02`.

**Verificado (corrección):** la protección de plazos de B/D debe incluir
el conjunto de pedidos conocidos que requiere más de dos viajes, no solamente
el siguiente lote. El caso reproducido entregaba el tercer pedido a 406,78 s
(vencimiento 330 s); ahora entrega a 315,78 s. Otro caso carga a 419,002 s,
termina antes del cierre a 480 s y entrega a 630 s (vencimiento 650 s).
El objetivo energético conserva dos viajes; el pronóstico de plazos utiliza
un recorrido factible del trabajo conocido. Esto no garantiza cumplir demandas
inviables ni conocer pedidos no anunciados.

**Verificado (procedencia):** la campaña preliminar `demand_campaign_01`
se conserva separada (42 completadas, una interrumpida y 677 pendientes).
Se excluye de la comparación final porque precede a esa corrección.
`demand_campaign_02` contiene las mismas 180 demandas, verificadas por hash,
y ejecuta la matriz completa con una única revisión. Fuentes y binarios
se archivaron en `results/demand_revision_02/source_and_binaries.zip`.

**Verificado:** las 720 ejecuciones se completaron y aprobaron la auditoría independiente. Se entregan comparación pareada, sensibilidad eléctrica, cuatro validaciones completas en Gazebo y cuatro vídeos con HUD. Los resultados y límites están en [resultados_demanda.md](resultados_demanda.md).

## Vídeos representativos

Se seleccionará la semilla de la demanda nominal desequilibrada cuyo trabajo
de A sea más próximo a su mediana. Los cuatro vídeos usarán esa misma demanda
y la ventana [600,1200) s, en 1080p, 20 fps y 4×: 150 s por política.

| Archivo | Política |
|---|---|
| `A_inmediato.mp4` | Inmediato sin buffers |
| `B_coordinado.mp4` | Coordinado sin buffers |
| `C_inmediato_buffers.mp4` | Inmediato con buffers |
| `D_coordinado_buffers.mp4` | Coordinado con buffers |

Los fotogramas procederán de sensores Gazebo y el HUD se compondrá con muestras
anteriores o simultáneas de la misma ejecución. Mostrará colas, holguras,
despacho, operarios, carga útil/auxiliar, inventarios, velocidad, tensión y
energía. Se distinguirá telemetría reducida de estimación eléctrica hipotética.

**Pendiente fuera de este hito:** contacto rueda–cable, cierre físico completo
de péndulos/cable, resistencia, fatiga, capacidad de losa/suelo y seguridad.
La paridad nativa/CLI comprueba ejecución del mismo núcleo; no valida esas
hipótesis físicas de forma independiente.

## Ajuste de admisión de memoria solicitado por el usuario

**Verificado:** la captura corta `demand_capture_probe_02` midió un pico RSS del árbol de 2,2213 GiB y la prueba CLI `demand_stress_guard_01`, 0,0233 GiB. **Inferido:** para esta configuración secuencial, se adopta admisión de 6 GiB para CLI, 7 GiB para Gazebo sin render y 8 GiB para captura de demanda sin GUI. Se mantienen dos muestras reales separadas por 5 s, vigilancia continua, parada preventiva bajo 5 GiB y reserva de 4 GiB. La GUI conserva 14 GiB. **Verificado en vídeos completos:** pico del árbol 2.2424 GiB; mínimo libre Windows 5.0281 GiB, sin activar la parada preventiva. Los registros previos conservan sus umbrales originales.

**Ajuste posterior verificado:** la admisión de vídeo se calibró a 7,5 GiB tras un segundo bloqueo previo a iniciar Gazebo (segunda muestra: 7,88 GiB). Se conserva el pico medido de referencia de 2,2213 GiB, vigilancia continua, parada bajo 5 GiB y reserva de 4 GiB. Los valores de 8 GiB de los registros anteriores documentan sus umbrales originales.
