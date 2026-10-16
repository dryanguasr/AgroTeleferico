# GOAL — AgroTeleférico: circuito conceptual multicarro en Gazebo

## 1. Resultado buscado

Extiende el repositorio existente `dryanguasr/AgroTeleferico` con una demostración conceptual reproducible en Gazebo para Linux/WSL. Debe mostrar un circuito cerrado de transporte agrícola sobre terreno irregular, con un par de carriles y seis carros: tres inicialmente en cada carril. Cada carril tendrá dos cables portantes flexibles. Un motor principal en la estación inferior dirigirá la circulación y pequeños actuadores locales permitirán refinamientos limitados del movimiento.

La demostración mostrará circulación continua, transiciones entre carriles en las estaciones, paradas de carga/descarga libreteadas, flecha de cables dependiente de las cargas, balanceo y una ráfaga de viento suave pero perceptible. Entrega también registros y un informe exploratorio sobre arquitectura, control y energía.

El resultado es una herramienta de discusión y experimentación conceptual, NO un diseño constructivo, un equipo certificado, un piloto físico ni una validación Sim2Real. No convertir esta tarea en otra revisión bibliográfica, una optimización logística completa o un proyecto de cosecha/percepción agrícola.

## 2. Auditoría inicial y conservación del trabajo existente

Al preparar este goal, el desarrollo se encontraba en `feat/gazebo-cable-pilot`; `main` contenía únicamente README y licencia. La rama del piloto documentaba Gazebo Harmonic, ROS 2 Jazzy y escenarios `single`, `double` y `spider`. Sus carros utilizan dinámica reducida, catenaria elástica cuasiestática y péndulos de balanceo; no resuelven contacto rueda–cable.

Verifica el estado ACTUAL local y remoto antes de trabajar: ramas, cambios sin confirmar, instrucciones del repositorio, dependencias y pruebas. Lee `README.md`, `docs/modelo.md`, `docs/validacion.md`, `config/pilot.yaml` y el código pertinente. Puede haber avances posteriores a esta inspección: consérvalos. El piloto documenta restricciones de escala a 20 m; no supongas que cambiar esa cifra basta para generar una ruta multivano.

Crea una rama de trabajo desde la base que contenga el desarrollo útil, por ejemplo `feat/gazebo-loop-six-carriers`. No reinicies desde el `main` mínimo ni sobrescribas cambios ajenos. Reutiliza generadores, física, interfaces y registro cuando corresponda, manteniendo operativos los escenarios anteriores.

Conserva el entorno instalado. No migres de versión ni reinstales ROS/Gazebo sin necesidad. Prioriza el filesystem de Linux y proporciona ejecución gráfica con WSLg y alternativa headless. Haz commits locales claros; no fuerces cambios remotos, merges ni publicación sin autorización o un flujo previo explícitamente autorizado.

## 3. Interpretación mecánica provisional

La función exacta de los dos cables no quedó cerrada por el usuario. Para avanzar sin otra ronda de preguntas, adopta y documenta esta hipótesis reversible:

- Dos portantes paralelos por carril: cuatro líneas portantes en total, apoyadas en torres/pórticos.
- Un circuito tractor separado, cerrado, accionado por el motor principal inferior. Distingue gráficamente portantes y tracción.
- Bogie de apoyo, suspensión y palet de carga como elementos diferenciados.
- Actuación local de pequeña autoridad, con un mecanismo de reacción definido y límites de fuerza/par, velocidad y recorrido.

Antes de implementar, deja un esquema y una decisión de arquitectura en `docs/concepto_circuito.md`: qué cable soporta, cuál arrastra, qué mueve cada motor y cómo se cierran las reacciones. No ocultes el circuito tractor adicional como si los dos portantes estáticos se moviesen solos. Si seleccionas otra interpretación de los dos cables, explica expresamente el cambio y conserva la intención del usuario.

### Motor director y ajustes locales

El motor principal gobierna una coordenada de avance del circuito. Los seis carros vinculados a la tracción comparten su movimiento principal. Los motores locales NO conceden velocidad o posición independientes ilimitadas a carros rígidamente sujetos al mismo tractor.

Como realización conceptual preferida, estudia un acoplamiento longitudinal de ajuste limitado entre el punto de arrastre y el bogie/suspensión. Representa su transmisión, carrera y reacción sobre el conjunto. Otra realización es admisible si resulta más coherente y queda justificada. No simules motores pequeños como fuerzas arbitrarias sin reacción o como teletransportaciones del carro.

Implementa `central_only` y `central_local`, priorizando la demostración del segundo y usando el primero como referencia. La arquitectura de motores exclusivamente embarcados queda para el informe, no para construir otra simulación completa ahora.

Mantén la subactuación: los motores locales no deben bloquear mágicamente todos los movimientos de la carga. Especifica qué modo se controla y cuál queda con amortiguación pasiva; una perturbación transversal no se cancela automáticamente con un ajuste longitudinal.

### Circuito y estaciones

Las estaciones inferior y superior conectan ambos carriles mediante retornos continuos. Es admisible modelar guías rígidas locales en las estaciones y su transición a los portantes; declara esa simplificación. Respeta radios de retorno, orientación del bogie y espacio del palet. No hagas saltos de posición entre extremos.

Para esta versión, usa paradas globales de la línea durante carga/descarga. No agregues pinzas desembragables para permitir paradas individuales salvo que resulten imprescindibles y se documente su modelo. El palet desmontable no equivale a un carro desacoplable del tractor.

Los seis carros conservan identidad durante toda la ejecución. La distribución tres/tres es inicial: durante los retornos habrá carros en estaciones y no tiene que mantenerse ese reparto en cada instante.

## 4. Terreno irregular y distribución de apoyos

Construye una ruta con cinco hitos topográficos, en este orden:

**Valle inferior → pico menor → valle intermedio → pico mayor → valle final.**

Esto representa tres valles y dos picos de diferente altura. La estación final debe quedar a mayor cota que la inicial, aunque existan subidas y bajadas intermedias en ambos sentidos. Usa un perfil suave que no introduzca extremos extra por interpolación.

Como semilla ilustrativa, no como especificación aprobada, puedes evaluar puntos `(x,z)` en metros: `(0,0), (12,6), (24,1), (36,9), (48,3)`. Desplaza, amplía o modifica esos valores cuando lo requieran holguras, radios o estabilidad, conservando los cinco hitos. Documenta la geometría finalmente utilizada.

Los nombres «subida» y «bajada» indican destino entre estaciones, no el signo de velocidad vertical de todos sus tramos. Calcula el trabajo gravitacional con la cota y movimiento reales de cada carro.

El usuario imagina aproximadamente cuatro postes por segmento valle–pico. Úsalo como punto inicial de evaluación, NO como número definitivo. Aclara si incluye extremos, evita duplicar apoyos compartidos y entrega el número único de torres/pórticos. Un pórtico puede sostener ambos carriles.

Compara de forma sencilla dos o tres distribuciones próximas a esa densidad. Busca flecha visible y moderada, tensión positiva acotada y holgura suficiente para palets bajo carga y viento. No minimices tensiones sin considerar distancia al suelo ni escojas apoyos solo por estética.

Diferencia apoyos ordinarios, terminales, tensores y retenciones donde hagan falta. Cerca de los valles verifica el signo de las reacciones: no impongas contacto mediante una fuerza ficticia de un apoyo que, mecánicamente, no podría retener el cable. Declara cualquier condición de apoyo idealizada.

## 5. Carros, palets y supuestos nominales

Modela seis bogies/suspensiones con identificadores persistentes. Los palets deben verse montables/desmontables; usa geometrías sencillas de plataforma y cajas sujetas. No implementes personas, montacargas ni una operación compleja de manipulación.

Todos los parámetros estarán en YAML, en SI y con origen etiquetado: requisito del usuario, supuesto conceptual, heredado del piloto o calculado. Distingue masa de bogie, suspensión, palet y carga; actualiza también inercia y área expuesta cuando corresponda.

Como rangos de arranque revisables, considera una tara total cercana a 15 kg por carro, cargas de 0/10/20 kg, suspensión del orden de 1 m, velocidad de línea de 0,3–0,5 m/s y aceleración limitada inicialmente a unos 0,1 m/s². Son supuestos de demostración, NO capacidades verificadas, valores seguros certificados ni recomendaciones de fabricación. Ajusta lo que no resulte consistente y explica por qué.

Dimensiona nominalmente el motor principal, los ajustes locales y el frenado a partir del caso simulado. Separa potencia continua, potencia pico, par, radio de transmisión y energía por recorrido. «Grande» y «pequeño» describen su función relativa; no fijes potencias de catálogo sin una cuenta preliminar.

## 6. Física mínima: flexibilidad y perturbaciones reales del modelo

Prioriza una ampliación del modelo reducido existente si permite reproducir los efectos requeridos de forma estable. No es obligatorio resolver contacto fino rueda–cable ni vibraciones distribuidas de todo el circuito.

### Cables multivano

Calcula el equilibrio/deformación de cada vano considerando peso propio y cargas móviles. Una catenaria elástica por tramos o discretización equivalente es aceptable si documentas supuestos, convergencia y limitaciones. Debe admitir más de un carro sobre el mismo vano.

La forma visible del cable debe proceder del modelo que posiciona y soporta las cargas; no de una curva decorativa independiente. Al desplazarse, cargarse o descargarse un carro deben cambiar coherentemente geometría y tensiones del vano afectado. Conserva la continuidad del movimiento al cruzar apoyos y documenta el tratamiento de la transición.

Fija longitud natural/pretensado y condiciones de tensado por configuración. No retenses automáticamente en cada paso para conseguir una imagen conveniente. No recortes las tensiones calculadas para hacer que parezcan admisibles: limita comandos y registra/rechaza estados fuera del dominio modelado.

Si adoptas reparto simétrico entre los dos portantes, identifícalo como aproximación: no sirve para acreditar transferencia lateral detallada de carga bajo viento. No dupliques gravedad o fuerzas al combinar modelo reducido y física nativa de Gazebo.

### Balanceo y viento

Integra al menos balanceo longitudinal y transversal, con inercia y amortiguamiento explícitos. El balanceo debe responder a aceleraciones, paso por el perfil y perturbaciones, no a una animación sinusoidal prescrita.

Programa una ráfaga con inicio y fin suaves durante un tramo representativo. Como semilla, evalúa viento de 3–5 m/s durante 8–12 s; calcula su acción a partir de un modelo de arrastre con velocidad relativa, área, densidad y coeficiente documentados, o justifica una fuerza equivalente.

Aplica la perturbación al modelo dinámico que integra el estado. Puede hacerse mediante fuerzas/pares nativos cuando corresponda o en las ecuaciones reducidas, pero nunca en ambos a la vez. No alteres directamente orientación o posición para simular viento.

La oscilación debe ser suave pero visible. Mejora encuadre, indicadores y flechas antes de exagerar fuerzas o modificar amortiguamiento sin explicación. No programes que el controlador híbrido necesariamente gane: conserva y explica el resultado real.

## 7. Secuencia libreteada

Usa una máquina de estados parametrizable y tiempo de simulación, no retardos de reloj real. Implementa esta secuencia:

1. Vista general, etiquetas de estaciones/carriles y seis carros en la configuración inicial.
2. Parada de carga en una estación; cambio visible de cajas/palet y del estado mecánico correspondiente.
3. Arranque suave y circulación con carros en ambos sentidos, mostrando flecha y paso por apoyos.
4. Llegada a estación, frenado y parada global; descarga y preparación del retorno.
5. Continuación por las curvas de retorno sin teletransportación.
6. Ráfaga de viento, respuesta de los palets y actuación local cuando está habilitada.
7. Recuperación y parada final, con resumen de eventos y métricas.

Vincula eventos de estación a presencia del carro y velocidad compatible, no a tiempos arbitrarios cuando el carro podría estar en otro lugar. Cambia carga únicamente con el sistema detenido y documenta la entrada/salida de masa y energía; no sumes esos cambios como recuperación eléctrica.

Garantiza al menos un recorrido cerrado completo de un carro identificado y una operación de carga y descarga. La coordinación es predefinida: deja extensiones para un planificador futuro, pero no implementes optimización, RL ni gestión de buffers en esta fase.

## 8. Telemetría y balance energético exploratorio

Registra CSV y metadatos JSON, con unidades, configuración, semilla, commit, versiones y procedencia de cada señal: estado del modelo reducido, estado nativo, entrada libreteada o estimación derivada.

Por carro: ID, tramo/estación, avance curvilíneo, posición, velocidad, masa/tara/carga, ángulos de balanceo, corrección local, saturaciones y eventos. Por vano: carga aplicada, flecha, tensión y holgura mínima. Globalmente: avance/velocidad del tractor, fuerza/par/potencia principal, contribución local, viento, estado operativo y tiempo de simulación.

Calcula energía mecánica motriz y energía mecánica absorbida por separado. Una potencia mecánica negativa NO demuestra energía almacenada: si no modelas convertidor, receptor y eficiencias, informa «potencial de recuperación» o «energía absorbida», no ahorro eléctrico logrado.

Incluye trabajo gravitacional según la trayectoria real, variación cinética y, cuando corresponda, elástica, pérdidas, trabajo del viento y energía asociada a carga/descarga. Si el modelo cuasiestático no permite cerrar el balance, publica el residuo y las limitaciones; no fabriques un balance exacto.

Compara central/híbrido con el mismo servicio, carga, ráfaga y condiciones iniciales. No declares ventaja energética cuando una ejecución transportó menos carga, terminó antes de completar el servicio o cambió sus inventarios. No agregues paneles, diésel ni baterías complejas: documenta qué haría falta para analizarlos después.

## 9. Entregables

Adapta nombres y estructura al repositorio, evitando duplicados:

- Mundo y configuración conceptual reproducible, con parámetro de número de carros/carriles sin asumir escalabilidad ya validada.
- Launch de demostración GUI y headless, más ejecución comparativa `central_only`/`central_local`.
- `docs/concepto_circuito.md`: arquitectura, hipótesis mecánicas, geometría, apoyos y simplificaciones.
- `docs/demo_circuito.md`: instrucciones Linux/WSL, controles, secuencia y recuperación de errores.
- `docs/informe_exploratorio_circuito.md`: resultados efectivamente obtenidos, limitaciones y siguientes experimentos.
- Pruebas automatizadas y registro de resultados, sin sobrescribir la evidencia del piloto anterior.
- Capturas de vista general, estaciones, flexión y viento; video obtenido de la ejecución si el entorno permite capturarlo. Objetivo visual: 1080p cuando sea viable, sin hacerlo requisito para simular.

El informe comparará conceptualmente accionamiento central, central+local y motores embarcados; explicará la elección de apoyos y qué no puede concluirse sobre escala real. Dejará preguntas para futura coordinación de cargas, buffers, recuperación, identificación y Sim2Real.

Las imágenes/video deben provenir de la ejecución. Un replay de registros se admite si está identificado como tal. Si no hay GUI o codificador, entrega los comandos y declara la captura pendiente; no inventes evidencia visual.

## 10. Aceptación y validación proporcionadas al alcance

Define tolerancias numéricas explícitas antes de comparar; justifícalas como criterios internos, no normas de seguridad ni metas industriales.

A. La configuración genera tres valles, dos picos distintos, un par de carriles, seis carros y dos portantes por carril; distingue su tracción.

B. Se mantienen los seis IDs, se recorren los retornos y no hay saltos de posición ni cruces evidentes de palets/terreno/apoyos. Documenta comprobación geométrica cuando no exista contacto nativo.

C. Una prueba controlada con la misma geometría y distinta carga muestra variación física de flecha/tensión. Incluye un caso con dos cargas en un vano y conserva trazabilidad.

D. La ráfaga causa respuesta no nula y acotada, seguida de evolución coherente al cesar. Evalúa central/híbrido sin exigir que este último sea superior.

E. Los actuadores locales respetan límites y el acoplamiento principal; carga/descarga cumple las condiciones de estación y parada.

F. La simulación termina sin NaN ni divergencia, y las violaciones de dominio se reportan. Ejecuta una sensibilidad numérica acotada con dos pasos de integración o resolución de cable.

G. La comparación energética documenta hipótesis y límites; no convierte aproximaciones visuales o energía mecánica negativa en resultados eléctricos certificados.

H. Los escenarios y pruebas anteriores siguen funcionando, o se documenta un fallo preexistente separado de las regresiones introducidas.

I. El README contiene comandos exactos de construcción, ejecución, comparación, captura y pruebas. Informa tiempo de cómputo y factor de tiempo real medidos; prioriza ejecución utilizable antes que detalle ornamental.

## 11. Orden de ejecución y cierre

Trabaja por hitos: (1) auditoría y decisión mecánica; (2) geometría/circuito con seis carros; (3) cargas y cables multivano; (4) tracción principal y ajustes locales; (5) estaciones y viento; (6) comparación, documentación y evidencia.

Continúa de forma autónoma con supuestos explícitos y reversibles. Consulta solo si aparece un bloqueo que impida satisfacer el concepto o requiera modificar destructivamente lo existente. Si la fidelidad completa resulta demasiado costosa, reduce complejidad del modelo y declara el límite, pero no elimines los fenómenos centrales ni presentes una animación como validación física.

Al finalizar informa: commit/rama, cambios, comandos, pruebas ejecutadas y sus resultados, ubicación de evidencias, limitaciones, qué falta para la siguiente iteración y qué decisiones mecánicas merecen revisión humana. No basta con entregar un plan: el objetivo es una demostración ejecutable y documentada.

## Fuentes de partida consultadas al redactar este goal

- Repositorio: `dryanguasr/AgroTeleferico`, rama `feat/gazebo-cable-pilot`; README y `docs/modelo.md`. Inspección de contenido, no ejecución ni validación independiente de sus resultados.
- Documentación oficial de Gazebo Harmonic: instalación e integración con ROS; APIs `ISystemPreUpdate`, `WindEffects` y `ApplyLinkWrench`. Consultar las versiones disponibles en el entorno antes de seleccionar una API.
- Requisitos y decisiones expresados por el usuario en esta conversación. Los valores nominales adicionales son semillas de diseño conceptual, no parámetros identificados de un sistema real.
