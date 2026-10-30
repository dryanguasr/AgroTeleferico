# Estado del mejoramiento del repositorio

La primera fase aborda CI e instalación desde la base 738c410. Las evidencias
publicadas se conservan sin modificaciones. La línea de nueve postes permanece
pausada: esta fase no realiza sus capturas ni su validación de recorrido completo.

La CI separa unitarios e instalación, ciclo de vida del piloto vigente de dos
carros, y regresiones históricas. Un fallo no cancela las otras suites. El circuito
reducido histórico usa la configuración de 13 apoyos preservada desde ffc699c.
La prueba de reinicio espera reloj cero y pausa antes de avanzar de nuevo;
mantiene la exigencia de acuses y registra las solicitudes.

Para comprobar una instalación, después de compilar con colcon y cargar ROS y
install/setup.bash, ejecutar desde el checkout:

```bash
python3 tests/test_installation.py
```

La prueba usa una carpeta temporal externa para importar todos los scripts
instalados, consultar las ayudas, generar el patio y leer la procedencia sin
depender del directorio fuente. No inicia Gazebo.

La primera fase se fusionó mediante el PR #3 en 67a2d3b, con las tres suites de CI
aprobadas. La segunda fase incorpora una réplica nativa corta de demanda y su
[guía de reproducción](reproduccion_demanda.md), con calibración nueva, paridad
y auditoría independiente. La aceptación se registra en smoke.json y en la suite
demand-native de CI. La línea de nueve postes continúa pausada.

La segunda fase se fusionó mediante el PR #4 en 4f755ee. La tercera fase
exige maniobras al menos tan largas como payload_ramp, incluida la manipulación
auxiliar, antes de crear registros de servicio. La rampa mantiene su perfil
quíntico; su valor por defecto sigue siendo 2 s. Los predictores nuevos incluyen
un manifiesto obligatorio que vincula tabla, configuración efectiva y núcleo.
Las campañas copian y congelan también ese manifiesto; las evidencias anteriores
siguen siendo legibles, pero necesitan nueva calibración para ejecutarse.

La tercera fase se fusionó mediante el PR #5 en 312f24f. La cuarta fase añade
aceptación del balance energético terminal (agro-demand-energy-v1), auditoría
independiente de telemetría e intercambio de masa y diagnóstico del máximo
transitorio. Los criterios y su alcance se describen en piloto_demanda.md.
Los balances transitorios incompletos siguen siendo una limitación del modelo.

La cuarta fase se fusionó mediante el PR #6 en 42d4072. La quinta fase
consolida los supervisores Windows en scripts/windows/guard_common.ps1 y las
utilidades Python sin ROS en scripts/supervision.py. Los tres comandos Windows
conservan sus argumentos, umbrales y destinos de resultados. La admisión se
comprueba antes de iniciar WSL; los errores de admisión, monitoreo y arranque
conservan supervisor.json. Una parada preventiva no puede terminar aprobada
por una salida cero del hijo. Se conserva STOP_REQUESTED y la limpieza por
identidad de procesos observados; no se usa limpieza global.

La CI incorpora windows-supervisor con pruebas de ocho casos de admisión,
fallo y cierre sin iniciar WSL ni simulaciones. Las cuatro suites Linux
verifican instalación, ciclo de vida, réplica nativa y regresiones históricas.

La sexta fase activa protección de main: PR obligatorio, rama actualizada,
los cinco checks anteriores ligados a GitHub Actions, conversaciones resueltas,
protección para administradores y prohibición de force push y borrado de main.
No se exige una revisión humana adicional: el número de aprobaciones es cero.

Siete ramas históricas integradas se retiraron tras verificar su ascendencia y
preservar cada cabeza en archive/20261029/<rama>. El tag
paused/nine-posts-20261029 conserva explícitamente la línea pausada; no se
repitieron capturas ni se promovió su evidencia parcial. La rama de esta entrega
se archiva antes de fusionar su PR y se retira solo después de quedar integrada.
Las próximas ramas de PR se borrarán automáticamente tras la fusión.

Con esta entrega quedan cubiertas las seis fases del plan. El cierre se verifica
con el PR de consolidación aprobado y fusionado, main protegido y sin PR abiertos
del plan. El informe de ejecución y las respuestas de GitHub quedan conservados
con las nuevas evidencias, sin modificar docs/evidence.
La aprobación de esta primera fase no cierra esos trabajos ni valida físicamente
el prototipo. Las campañas históricas no se repiten por cambios documentales.
