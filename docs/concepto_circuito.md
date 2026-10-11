# Circuito de seis carros: decisión mecánica provisional

## Estado y propósito

Extensión aislada del piloto en `52298bf5935575e80fc20c975e34cd020b4249c5`. Los escenarios `single`, `double` y `spider` conservan sus archivos. Este módulo no es un diseño constructivo, una certificación, un piloto físico ni una validación Sim2Real. Las cifras de YAML son hipótesis reversibles en SI.

## Topología y reacciones

- Dos carriles, cada uno con dos cables portantes estacionarios; reparto vertical simétrico entre portantes. Un tractor separado, dibujado naranja, cierra el circuito y recibe accionamiento en la estación inferior.
- Seis carros identificados permanentemente, tres inicialmente por carril. En los retornos es normal que algunos estén en estaciones.
- El motor principal gobierna una coordenada común `q`. Cada acoplamiento incluye una corrección longitudinal `offset` de carrera limitada, resorte, amortiguador y motor local. La fuerza que recibe el carro se devuelve con signo opuesto al tractor. No hay propulsión independiente ilimitada.
- `central_only` conserva los acoplamientos pasivos; `central_local` añade una ley inicial dependiente del balanceo. Ambos modos atienden la misma demanda y referencia. No se presupone superioridad híbrida.
- El par registrado usa radio equivalente de accionamiento de 0,3 m. La rueda visible de retorno tiene radio 2 m; representa otra etapa de transmisión, no un eje con radios contradictorios. La transmisión detallada, su eficiencia y la fabricabilidad siguen abiertas.
- Palet desmontable no significa pinza desacoplable del tractor. Las operaciones de carga/descarga detienen toda la línea. No se representan personas ni manipulación automática de palets.

## Terreno y apoyos

Perfil suave cosenoidal: `(0,0), (12,6), (24,1), (36,9), (48,3)` m. Tres valles, dos picos de distinta altura; la estación final queda 3 m por encima de la inicial. Los nombres subida/bajada indican destino, no el signo instantáneo del movimiento vertical.

Cuatro apoyos por intervalo entre extremos topográficos, INCLUYENDO extremos, resultan en 13 pórticos únicos. Se compararon 9, 13 y 17 pórticos mediante un barrido estático con dos carros llenos por vano, ensayando cada vano por separado. Ver `evidence/loop/supports.json`. Con 13 se conserva flecha apreciable y más holgura nominal que con 9; no es una optimización global ni prueba de resistencia.

Los cálculos muestran reacciones verticales negativas en algunos extremos. Por eso la hipótesis es de **anclajes/retenciones capaces de sujetar en ambos sentidos**, no de cables apoyados libremente sobre postes ordinarios. Cada vano tiene longitud natural propia y extremos retenidos. No se modela deslizamiento del portante a través de una torre ni transferencia automática de longitud entre vanos. La construcción de esas retenciones debe revisarse antes de afirmar viabilidad mecánica real.

Las guías rígidas locales transfieren suavemente la carga al apoyo alrededor de cada pórtico. Los retornos son guías semicirculares. Esta aproximación evita cambios instantáneos de trayectoria, pero NO sustituye el diseño de ruedas, rodillos, articulaciones y tolerancias.

## Qué física calcula y qué simplifica

### Cable

`Span` resuelve equilibrio vertical con carga distribuida por metro horizontal y cargas puntuales. `z'' = w/H`; una carga puntual provoca un salto de pendiente `P/H`. La tensión horizontal se obtiene imponiendo la longitud natural fija:

`L0 = integral sqrt(1 + z'^2) / (1 + T/EA) dx`.

Se integra por cuadratura y se resuelve una raíz positiva; las tensiones no se recortan. Es una aproximación elástica cuasiestática en coordenadas horizontales, **no la catenaria exacta de coordenada material del piloto ni un modelo de vibración distribuida**. No se recalibra la holgura para acomodar cada nueva carga.

Se aceptan varias cargas por vano. La posición del carro y las líneas visibles proceden de este equilibrio y de las guías. Para derivar aceleraciones se diferencia la familia de equilibrios con la carga móvil, no el quiebre geométrico de una carga puntual inmóvil. Se conserva un retardo de actualización de forma parametrizado y se comprueba sensibilidad al reducirlo.

### Carros y ajuste local

Dinámica reducida de `q` y offsets; servo principal de fuerza ideal con saturación. El ajuste local tiene carrera, fuerza y velocidad acotadas. La limitación de velocidad/end stops es un **gobernador ideal**, no un mecanismo ya diseñado. Se cuentan sus intervenciones y se estima su disipación; no ocultar que se activa durante la demostración.

Los palets tienen dos modos pendulares, excitados por aceleración del apoyo y arrastre de viento con velocidad relativa. No se asignan ángulos sinusoidales. El viento tiene envolvente suave y entra una sola vez en las ecuaciones. La perturbación transversal no se elimina mágicamente con un ajuste longitudinal.

La reacción completa del péndulo sobre el tractor y los términos temporales cruzados de deformación del cable no están cerrados. La masa suspendida y su energía están representadas, pero esto no constituye un modelo acoplado conservativo exacto. La inercia de los dos modos se aproxima con masa por longitud al cuadrado; no se afirma haber identificado un sólido 6 GDL.

### Gazebo

El plugin integra el mismo núcleo en tiempo de simulación. Los modelos nativos son representaciones cinemáticas, sin gravedad/contacto aplicado por segunda vez. `SetWorldPoseCmd` presenta estados calculados, no una grabación ni una simulación nativa rueda–cable. No se calculan colisiones; se comprueban holgura al terreno y separación entre centros con envolvente simplificada.

Los cables se dibujan con segmentos de centro y dirección calculados y longitud visual fija con 5% de solape. No confundir ese grosor/solape de visualización con longitud, tensión o contacto físico. La envolvente completa palet–torres y la calidad de las transiciones requieren revisión visual nativa.

## Energía y servicio comparable

Se registran trabajo principal motriz/absorbido, trabajo local, disipación estimada, acción del viento, intercambio de masa en estación y energía total aproximada. La energía de carga/descarga se registra como flujo de material, no recuperación eléctrica.

La potencia negativa es absorción MECÁNICA. No hay convertidor, batería, paneles, generador ni almacenamiento modelados. El balance publica un residuo no nulo; faltan términos de acoplamiento y el gobernador ideal no demuestra cierre energético. No usar estas cifras para afirmar ahorro eléctrico, dimensionar anclajes ni seleccionar motores comerciales.

El despacho es libreteado. Buffers, optimización logística, accionamiento individual completo y aprendizaje quedan fuera de esta versión.
