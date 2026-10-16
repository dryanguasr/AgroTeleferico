# Protocolo de validación

CTest comprueba condiciones de extremo, reacciones y flecha analítica de catenaria, varias posiciones/cargas en ladera, tensión unilateral, rango de la matriz de ocho cables y rechazo de esfuerzos imposibles.

La suite ejecuta 18 ensayos nominales (tres escenarios, cargas 0/5/10 kg, pasos 1/0,5 ms), de 120 s simulados, y tres ensayos de perturbación lateral de 20 N entre 35 y 36 s.

RMS desde el segundo 2: error longitudinal de carros, distancia 3D de plataforma; error angular = ángulo de rotación relativa. Criterios: duración completa, datos finitos, tensión no negativa, RMS posición ≤0,1 m, RMS angular ≤5°, error final ≤0,1 m y ausencia de asignaciones inviables. Convergencia temporal <5 % en RMS de posición, RMS angular y máxima tensión. Denominadores mínimos explícitos: 1 mm, 0,1° y 1 N, para evitar error relativo indefinido cerca de cero.

Cada ensayo conserva configuración, SDF, CSV, log, gráfico y métricas. `summary.json` agrega el resultado. Un proceso con salida cero pero sin CSV no cuenta como éxito. Factor de tiempo real = tiempo simulado / tiempo de pared, incluyendo arranque y cierre.

Las grabaciones de reproducción de telemetría se identifican como tales. Una captura GUI verifica visualización, no sustituye las pruebas numéricas. El estado de ejecución local y el de GitHub Actions se reportan por separado.
