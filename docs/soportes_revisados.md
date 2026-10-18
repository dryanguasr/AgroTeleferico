# Piloto entre pisos con soportes exteriores

El escenario predeterminado `buitrago_patio` sitúa una estación en el piso 1
(patio, z=0) y la otra en el piso 2 (corredor, z=3,20 m). El vano horizontal
mide 8,60 m: una inclinación global de unos 20,4°. La altura entre pisos es
la que ya tenía el edificio conceptual; no es una medición de la fotografía.
Se retiraron árboles, materas, hojas y escalera de la escena revisada. Se
conservaron las losas, barandillas, columnas, franjas de fachada y cubierta.

## Qué cambia en las bases

- El mástil central atravesaba el depósito. Ahora el depósito descansa en
  dos cunas y los postes se fijan al bastidor por fuera del recorrido.
- Los postes laterales y el poste trasero dejan libre el volumen de retorno
  de la canasta y del bogie. Las diagonales quedan en los planos laterales.
- Los asientos cortos sostienen las guías desde el exterior. Se ubican en
  la zona horizontal del retorno, para que las ruedas y la jaula no los
  atraviesen al pasar de la pendiente al retorno.
- El travesaño se retrasa dentro del retorno. El tractor queda a 0,30 m
  sobre la trayectoria; el acople inclinado no atraviesa el travesaño.
- El motor inferior se monta mediante una ménsula y un eje explícitos,
  separado del travesaño. Las ruedas retraídas tienen sus soportes visibles.
- La representación de las guías de transición sigue la misma trayectoria
  suavizada que el núcleo usa para el bogie. Sigue siendo una representación
  de un modelo reducido, no un cálculo de contacto rueda–guía.

Las uniones entre miembros estructurales conectados pueden solaparse como
representación de una unión soldada. Eso no se confunde con que un carro,
una rueda o una carga atraviese un elemento fijo. Los asientos y las secciones
son geometría conceptual: no se han dimensionado por resistencia o fatiga.

El equipo usa 480 L de agua por base, masa seca supuesta de 85 kg y huella
de 2,8 × 3,3 m. El centro de la base superior está en x=9,50 m y el extremo
del vano en x=8,60 m. El borde frontal de la base queda 0,10 m dentro del
corredor modelado. La altura nominal deja 0,05 m al intradós. Ambas holguras
necesitan medidas reales y tolerancias antes de plantear una instalación.

## Verificación reproducible

`scripts/audit_support_clearance.py` revisa el ciclo completo cada 0,05 s.
Usa las orientaciones de bogies y acoples que registra el propio núcleo,
no una reconstrucción aproximada de la pendiente. Examina cajas orientadas;
los cilindros se encierran conservadoramente en cajas orientadas.

La revisión incluye soportes y motor frente al edificio, depósito frente a
miembros estructurales, motor frente a soportes, y ruedas/pestañas, chasis,
acoples, suspensión, canastas y cargas frente a los soportes y el edificio.
Incluye la franja de fachada que faltaba en el análisis anterior. Los
primeros intentos rechazados se conservan en `results/` como evidencia local.

Quedan fuera el contacto rueda–guía, el contacto con terreno/plataformas,
los cables flexibles y las interacciones del tractor y poleas. El muestreo
no garantiza ausencia de colisiones entre muestras. No es validación
estructural, física ni certificación. Los márgenes de bases son estimaciones analíticas con bases fijas;
la capacidad de la losa y el suelo permanece desconocida.

La configuración anterior sigue disponible explícitamente con
`--variant baseline` y `--variant compact_candidate`. El patio plano
anterior se conserva en `config/legacy/buitrago_patio.json`. La variante
predeterminada es `revised_supports`. Los casos `buitrago_patio` y
`buitrago_entre_pisos` ahora representan la misma geometría entre pisos;
se conservan ambos nombres por compatibilidad, sin afirmar que son dos
instalaciones diferentes.

## Ejecutar

Desde la raíz del repositorio, el supervisor de Windows conserva dos
muestras de al menos 10 GiB libres para capturas sin GUI, separadas 5 s,
parada preventiva bajo 5 GiB y reserva de 4 GiB. No se deben reutilizar
nombres de carpetas de resultados existentes.

```powershell
& './scripts/windows/run_guarded_loop.ps1' -RunName nueva_toma_patio -Case capture -Scenario buitrago_patio -Variant revised_supports -NoGui -AllViews -FollowCarrier -Until 163
```

En WSL, las pruebas del núcleo y el análisis geométrico son reproducibles:

```bash
cmake -S . -B build-ballasted -DAGRO_LOOP_STANDALONE=ON
cmake --build build-ballasted -j1
ctest --test-dir build-ballasted --output-on-failure
python3 scripts/run_ballasted_core.py --output results/nueva_campana
python3 scripts/audit_support_clearance.py results/nueva_campana/00_buitrago_patio
```

## Resultados del diseño revisado

Las siete pruebas CTest pasan. La campaña incluye los dos nombres de escena
entre pisos, ladera con viento, ladera sin viento, medio paso temporal y
patio con solo 120 L por base. Todos completan el movimiento; el último
caso **falla la estabilidad preliminar**, con márgenes mínimos de 0,670
frente a deslizamiento y 0,634 frente a vuelco. No es una condición aprobada.
Con 480 L, los mínimos son 2,109/1,996 en el patio y 2,033/2,006 en ladera.

La auditoría geométrica final no detecta intersecciones dentro de su alcance:
1.745.686 pares sobre 6.484 muestras en patio y otros tantos en su alias
entre pisos; 1.273.755 pares sobre 7.762 muestras en ladera. Las advertencias
de esfera envolvente en `assessment.json` son candidatos conservadores de
la primera fase; `support_clearance.json` contiene la comprobación detallada
de las piezas enumeradas. La instalación permanece sin aceptación física.

Al reducir el paso de 0,002 a 0,001 s, la diferencia máxima de recorrido es
0,00001923 m. El viento produce una diferencia máxima de balanceo transversal
de 0,014939 rad frente al caso en calma. Los márgenes no comprueban capacidad
portante de losa, resistencia de uniones ni tolerancias de montaje.

La evidencia crítica se guarda en [single_span_revised](evidence/single_span_revised/manifest.json):
vídeos, imágenes, verificaciones, resúmenes y archivos comprimidos con mundos
y telemetría. Los mundos archivados conservan sus rutas de ejecución originales
como procedencia; para ejecutarlos en otra máquina se debe regenerar la escena
con los comandos anteriores. El manifiesto permite comprobar los hashes de
archivos y fuentes. La fotografía de referencia permanece fuera del repositorio.

### Capturas verificadas

| Escena | Cobertura por cámara | Vídeos | RAM libre mínima |
|---|---|---|---|
| Patio entre pisos | 816 fotogramas, 0,04–163 s | 40,8 s a 20 fps | 6,869 GiB |
| Ladera | 976 fotogramas, 0,04–195 s | 48,8 s a 20 fps | 7,151 GiB |

Las cuatro cámaras de cada toma cubren el ciclo, con intervalo máximo de
0,20 s. Los vídeos general y de seguimiento decodifican sin error. Los cinco
CSV (`global`, `carriers`, `cables`, `bases`, `geometry`) coinciden byte a byte
con el núcleo de referencia. Gazebo terminó con salida 0; no se activó la
parada preventiva y se conservó la reserva. Se inspeccionaron imágenes
generales y de estación, cruce de barandilla y retorno. Los postes o franjas
del edificio ocultan parcialmente algunas piezas según el encuadre; se
conservan las vistas complementarias y los obstáculos reales del modelo.

- [Patio, general](evidence/single_span_revised/capture_patio/gazebo.mp4).
- [Patio, seguimiento](evidence/single_span_revised/capture_patio/follow.mp4).
- [Ladera, general](evidence/single_span_revised/capture_ladera/gazebo.mp4).
- [Ladera, seguimiento](evidence/single_span_revised/capture_ladera/follow.mp4).
