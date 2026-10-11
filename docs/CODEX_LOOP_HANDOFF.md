# Entrega a Codex: validación nativa pendiente

## Punto de partida

Continuar el trabajo de la rama `feat/gazebo-loop-six-carriers`, derivada del piloto `52298bf5935575e80fc20c975e34cd020b4249c5`. Revisar primero estado local, instrucciones del repositorio y divergencias remotas; no resetear cambios ajenos ni recrear el proyecto desde `main`.

Ya están implementados el núcleo C++17, cables multivano con cargas múltiples, seis carros, guía cerrada, actuadores principal/locales, estados de estación, viento, CSV/JSON, generador SDF/malla, plugin de Gazebo, launch, suite y reportador. No empezar escribiendo otra propuesta o arquitectura desde cero. Leer `concepto_circuito.md` y `informe_exploratorio_circuito.md` antes de modificar física.

## Comprobado aquí

- Compilación standalone y CTest: dos targets aprobados (núcleo y assets; este último contiene tres tests Python).
- Cinco servicios completos del modelo reducido, de unos 341 s, con configuración idéntica salvo modo/viento/resolución.
- Sensibilidad temporal y de actualización de cable; efectos de carga y viento; cumplimiento de límites internos.
- Inventario/continuidad geométrica, XML bien formado y referencias locales. Esto NO es validación por sdformat ni ejecución Gazebo.
- Barrido estático de 9, 13 y 17 pórticos.

Ver `evidence/loop/`. No hay resultados físicos, compilación de plugin, imágenes GUI ni regresión del piloto ejecutada en esta entrega. No existe ROS/Gazebo/Eigen en el entorno usado. Los metadatos de generación de pruebas pueden indicar `commit=unavailable`, porque se probó una copia de trabajo materializada; el manifiesto identifica base y hashes de fuentes.

## Trabajo restante, en orden

1. **Compilar nativo en Harmonic/Jazzy.** Ejecutar comandos de `demo_circuito.md`. Corregir únicamente incompatibilidades reales de API/build que aparezcan; registrar cambios. Revisar `ISystemReset`, evento Stop, `SetWorldPoseCmd` en modelos estáticos, publicación StringMsg y carga de plugin. No se han compilado con stubs para simular validación.
2. **Validar SDF y GUI.** Abrir el mundo y confirmar los seis carros, cuatro portantes y tractor separado; renderización de terreno/malla; transiciones/retornos continuos; carga/descarga; colores y rueda principal. Verificar especialmente bogies, guías, columnas, travesaños, estación inferior y motor. Los tests geométricos actuales NO prueban envolventes completas contra todos los apoyos. Ajustar la visualización sin alterar fuerzas para obtener un efecto vistoso.
3. **Ejecutar suite Gazebo.** Cinco servicios, pausa/reset/cierre limpios y archivos completos. Comparar estados/tiempos del núcleo CLI y plugin con la misma configuración: cualquier diferencia debe explicarse antes de interpretar métricas. Medir factor de tiempo real y tiempo de arranque; reducir elementos exclusivamente visuales si la GUI es lenta, sin suprimir flecha ni fenómenos centrales.
4. **Regresión de piloto.** CTest nativo debe incluir `physics`, `loop_core`, `loop_assets`. Ejecutar `scripts/run_suite.py --quick` y, si es viable, suite completa heredada. Separar fallos preexistentes de regresiones; no sobrescribir sus evidencias versionadas.
5. **Evidencia visual e informe final.** Capturas y vídeo de operación normal/perturbada provenientes de la ejecución. Documentar WSLg, GPU/renderer, versiones, commit y comandos. Actualizar resultados con evidencia nativa, sin presentar el modelo reducido como contacto real o Sim2Real.

## Puntos de revisión científica que no deben ocultarse

La ley local nominal aumenta aproximadamente 4,6% el RMS longitudinal frente a central_only. NO ajustar criterios para declarar una mejora. Es un comparador inicial, no un controlador óptimo.

El gobernador ideal del ajuste local interviene frecuentemente. Contador de muestras saturadas no equivale a número de episodios. Revisar mecanismo y transición si se busca mayor fidelidad; mantener un caso de referencia sin cambiar parámetros a escondidas.

El residuo energético no nulo refleja acoplamientos incompletos. No afirmar recuperación eléctrica ni ahorro validado. Reacciones negativas exigen retenciones; el modelo no acredita que los postes artesanales puedan soportarlas.

Los siguientes desarrollos son posteriores, no requisitos para cerrar esta entrega conceptual: conservación energética acoplada completa, interacción rueda–cable, rigidez torsional, deslizamiento de portantes entre vanos, despacho óptimo/buffers, recuperación eléctrica y control aprendido.

## Cierre esperado

Informar commit, código corregido, comandos, pruebas aprobadas/fallidas, capturas, desempeño y limitaciones. No fusionar a `main` ni borrar la rama piloto sin autorización. Si una prueba nativa revela un bloqueo de modelo, dejarlo explícito y repararlo con prueba de regresión; no entregar una animación que sustituya silenciosamente la dinámica.
