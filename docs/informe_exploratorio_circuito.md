# Informe exploratorio: circuito multicarro

Este informe conserva los resultados standalone iniciales. La validación
posterior en Harmonic/Jazzy y sus evidencias están en el
[informe nativo](informe_nativo_circuito.md); no se han sustituido estos datos.

## Evidencia obtenida y alcance

Se ejecutó el núcleo reducido C++17, no Gazebo. CMake standalone compiló y CTest aprobó dos targets; `loop_assets` contiene tres pruebas Python. XML bien formado no equivale a validación SDF nativa. Los cinco servicios finalizaron y aprobaron los criterios internos definidos en `run_loop_suite.py`.

El lanzador agregado fue interrumpido por el límite del entorno durante el quinto caso. Se conservó el directorio incompleto, se repitió ese caso completo con la misma configuración y se agregaron los resultados usando la misma función de evaluación. Esto está anotado en `evidence/loop/reduced_suite.json`; no se afirma que la primera ejecución agregada terminara sola.

## Resultados del escenario nominal

| Magnitud | Resultado del modelo |
|---|---:|
| Carros / pórticos únicos | 6 / 13 |
| Longitud de referencia del circuito | 123.294 m |
| Tiempo simulado | 340.803 s |
| Carga / descarga del carro 0 | 20 / 20 kg |
| Error máximo de referencia principal | 0.000094 m |
| Fuerza principal máxima | 1095.51 N |
| Par equivalente, radio 0,3 m | 328.65 Nm |
| Fuerza local máxima | 10.32 N |
| Norma máxima del balanceo | 5.993 grados |
| Tensión máxima de portante | 638.46 N |
| Holgura mínima nominal al terreno | 3.980 m |
| Carrera local máxima usada | 0.165 m |
| Trabajo mecánico principal positivo / absorbido | 18429.55 / 16647.31 J |
| Residuo energético final | 130.29 J |

Las cifras NO son capacidades constructivas. La fuente detallada y sus comprobaciones están en `evidence/loop/reduced_suite.json`. La configuración define un servo principal ideal de fuerza y un dominio de operación limitado; el error pequeño no equivale a precisión de un dispositivo real.

## Qué no hay que ocultar

La ley local inicial obtiene un RMS longitudinal de 0.01572787 rad frente a 0.01504297 rad del central: **+4.55%**, es decir, empeora ligeramente. No se ajustó el resultado para hacer ganar al híbrido. Es una ley inicial para explorar, no la conclusión de que los motores locales no sirvan.

Se registraron 8041 intervenciones discretas acumuladas del gobernador o límites. Con dt=0,002 s equivalen a unas 16.08 carro-segundos de muestras afectadas; NO son ese número de episodios independientes. Debe revisarse esa idealización antes de interpretar esfuerzos y pérdidas como diseño mecánico.

La ráfaga produjo una diferencia transversal máxima de 2.520 grados respecto al caso sin viento. Esa diferencia procede de la dinámica, no de una animación de orientación. Queda pendiente verificar que se perciba con el encuadre de Gazebo.

La sensibilidad al reducir el paso y al aumentar la frecuencia de forma permanece por debajo del umbral interno del 5% para RMS de balanceo y tensión máxima. La convergencia de esas métricas NO demuestra cierre energético ni contacto correcto.

El residuo energético es no nulo y cambia con la discretización de la forma. Se excluyen términos de retroacción pendular y acoplamiento temporal del cable; no hay almacenamiento eléctrico. **La energía absorbida no se presenta como ahorro ni electricidad recuperada.**

## Selección de apoyos

Barrido estático con dos cargas completas por vano, cada vano ensayado por separado:

| Pórticos | Tensión máxima por cable | Flecha máxima | Holgura nominal mínima |
|---:|---:|---:|---:|
| 9 | 966.79 N | 0.516 m | 3.442 m |
| 13 | 971.38 N | 0.460 m | 4.033 m |
| 17 | 971.54 N | 0.327 m | 4.308 m |

Se mantienen 13 como punto de partida cercano a lo solicitado. Las alternativas no cambian solamente tensión: modifican flecha, holgura, número de retenciones e infraestructura. Los tres casos incluyen extremos con reacción vertical negativa; no serían físicamente equivalentes a simples apoyos sin retención. Ver `concepto_circuito.md`.

## Pendientes limitados a integración y revisión

Compilar el plugin en Harmonic/Jazzy; validar SDF/malla; ejecutar los cinco casos en Gazebo; comprobar pausa/reset, velocidad de visualización, retornos y envolventes contra estructuras; ejecutar regresión del piloto; capturar operación real de la simulación. La lista y los comandos están en `CODEX_LOOP_HANDOFF.md` y `demo_circuito.md`.

No se tomó ninguna captura de Gazebo ni se midió su factor de tiempo real. El tiempo de cómputo standalone registrado excluye renderer y transporte Gazebo. Tampoco se verificó la instalación WSL del usuario.
