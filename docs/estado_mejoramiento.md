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

Las siguientes fases siguen pendientes: réplica nativa corta de demanda y guía
completa de reproducción; contratos de rampa y calibración; aceptación energética;
consolidación de supervisores; protección de main y retirada de ramas integradas.
La aprobación de esta primera fase no cierra esos trabajos ni valida físicamente
el prototipo. Las campañas históricas no se repiten por cambios documentales.
