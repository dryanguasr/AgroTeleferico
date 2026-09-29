# Modelo físico

## Catenaria elástica

La coordenada material `s` mide longitud sin estirar. Con rigidez `EA`, tensión horizontal `H>0` y peso material `w`, la tensión vertical es `V(s)=V0+w*s`. Se integran analíticamente:

```
dx/ds = H/sqrt(H²+V²) + H/EA
dz/ds = V/sqrt(H²+V²) + V/EA
```

En el carro, `V` salta en el peso aplicado. Newton con búsqueda de paso resuelve `log(H)`, `V0` y coordenada material del carro para satisfacer su posición horizontal y los extremos fijos. Un fallo de convergencia aborta el ensayo. El doble portante recibe la mitad del peso en cada cable. `pretension_slack` fija exceso de longitud natural, no tensión nula bajo carga. No hay vibraciones distribuidas y el balanceo no retroalimenta el reparto vertical.

## Carro

Se aproxima la pendiente con la media de tangentes a ambos lados de la carga. La ecuación longitudinal proyecta gravedad, tracción y resistencia; un control de velocidad sigue la posición. El esfuerzo se limita por `mu*(m*g/sqrt(1+grade²)+clamp_normal_force)`. El apriete normal adicional, de 150 N por defecto, representa ruedas opuestas que sujetan el cable: el peso propio no bastaba para subir sin deslizar en el tramo de mayor pendiente. La referencia conserva un 10 % de margen sobre la velocidad máxima; no se impone un freno cinemático ideal sobre la velocidad real.

Péndulos amortiguados representan balanceo por aceleración longitudinal y fuerza lateral. El doble portante añade rigidez lateral equivalente de 35 s⁻²; es un supuesto agregado, no una identificación estructural. Euler semiimplícito integra el estado reducido; el equilibrio de catenaria representa las reacciones verticales. No se calculan contactos 3D rueda–cable. En los carros la longitud publicada es la longitud natural del portante, y la tensión publicada es su máximo; en la plataforma se publican longitud geométrica y tensión por cable.

## Plataforma de ocho cables

El cable va del anclaje `a_i` al punto `p+R*b_i`. La matriz de esfuerzo tiene columnas `[d_i; (R*b_i) × d_i]`, con `d_i` dirigido hacia el anclaje. Se resuelve mínimos cuadrados con `Tmin <= T_i <= Tmax`, usando solución interior y gradiente proyectado al tocar límites. La norma residual combina N y N·m con escala característica de 1 m, y umbral 0,1.

La ley es `max(0,k*(length-rest)+c*length_rate)` para cable extendido; en holgura es cero. El amortiguador representa separación de extremos, no fricción del cabrestante. Longitud natural y velocidad del cabrestante están acotadas. El límite superior de tensión se aplica al comando; la tensión física no se recorta.

Gazebo recibe fuerza y momento en el centro del cuerpo, incluidos brazos de palanca, e integra gravedad e inercia. La inercia supuesta es `m*[.12,.12,.18] kg·m²`, independiente de la caja visual. Las líneas visuales no colisionan ni generan fuerzas.

## Parámetros e interfaces

`config/pilot.yaml` usa SI. La demostración v1 admite luz de 20 m: cambiarla requiere adaptar trayectorias y ventana de anclajes, y se rechaza por ahora. Masa total = vehículo + carga. Control y física se ejecutan en `PreUpdate`, con tiempo simulado; telemetría a 50 Hz. ROS transporta objetivos externos y mensajes tipados; el control interno no depende de latencia ROS. Un adaptador C++ convierte `gz.msgs.Double_V` en `Float64MultiArray`, ya que el bridge estándar de Jazzy no incluye esa pareja.

Se comprueban poses externas y 21 muestras del trayecto interpolado contra la ventana geométrica y factibilidad estática. Esto es una precomprobación discreta, no una prueba de viabilidad dinámica continua. El residuo de asignación durante el movimiento se publica por separado; `rejected` cuenta objetivos descartados. Un objetivo rechazado conserva el anterior.
