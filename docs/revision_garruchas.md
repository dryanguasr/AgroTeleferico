# Revisión: postes en T, garruchas y cámara de seguimiento

La solicitud del usuario y sus dos fotografías orientan esta revisión visual:
un mástil central con travesaño en T, y un carro agrícola con ruedas visibles
y jaula abierta. No se copian dimensiones ni se atribuye una licencia a las
fotografías; no se incorporan como assets del repositorio.

## Cambios

- Se pasa de 13 apoyos a 9, incluidos los extremos. La separación horizontal
  pasa de 4 a 6 m; el perfil de tres valles y dos picos conserva sus 48 m.
- Cada soporte tiene un mástil central y travesaño elevado. Se mantienen dos
  portantes por carril y el tractor separado. El nombre interno `portal_*`
  se conserva por compatibilidad, pero su geometría ya no es un pórtico.
- Los carros tienen bastidor abierto, cuatro ruedas con pestañas y jaula
  naranja de carga. Es una adaptación de la referencia de garrucha a los dos
  portantes existentes, no una reproducción de una garrucha de cable único.
- La masa de la jaula está incluida en la tara supuesta del palet; no se ha
  identificado una masa real ni dimensionado la estructura.
- Una cámara del mismo mundo sigue la posición simulada del palet del carro 0.
  El vídeo final superpone esa vista en un recuadro 384×240 sobre la vista
  general 1280×800. Las marcas de tiempo de ambas cámaras deben coincidir.
  No se usa un recorte ampliado de la vista general ni un replay de CSV.

## Ajuste y validación

Con nueve apoyos y las guías anteriores de 0.8 m por lado, la simulación
rechazó una aceleración vertical fuera de dominio alrededor de 111.4 s. Los
cinco fallos se conservan en `results/loop_towers_cli_01`. Se amplió la zona
de transición a 1.4 m por lado, sin cambiar límites de aceptación ni ganancias
del controlador. Las guías no se superponen dentro de los vanos de 6 m.

La variante intermedia `results/loop_towers_cli_02` aprobó cinco recorridos y sus comparaciones:
control híbrido/central, con/sin ráfaga, mitad de paso temporal y de intervalo
de actualización de forma. La mayor variación de convergencia fue 0.05739 %,
inferior al 5 %. La respuesta transversal con/sin ráfaga difirió hasta
0.04348 rad. Colcon compiló el seguimiento de cámara y CTest aprobó 4/4.

La cámara cercana reveló después una interferencia visible entre jaula y guía
inclinada a 60 s, que la comprobación de distancia entre centros no detecta.
Se detuvo `loop_garruchas_complete_01` a 89.8 s, con servidor=0 y evidencia
parcial conservada. No se entrega como vídeo completo. Se amplió la suspensión
de 1.0 a 1.6 m y se alejó ligeramente la cámara para incluir todo el carro.
Esto cambia la dinámica pendular: requiere una nueva suite, no basta con los
resultados de la suspensión corta. La plataforma de estación baja con la
longitud de suspensión, conforme a su fórmula de generación existente.

La configuración corregida pasó `results/loop_towers_cli_03`: cinco servicios
completos, misma carga/descarga y comparaciones aprobadas. La variación máxima
de convergencia fue 0.01851 %, la tensión máxima 634.09 N y la distancia mínima
del punto del palet al terreno 2.754 m. El híbrido aumentó el RMS longitudinal
un 2.62 % respecto al central en esta configuración; no se afirma una mejora.
El resumen completo está en [cli_suite.json](evidence/loop/garruchas/cli_suite.json).

## Vídeo disponible y trabajo pendiente

[Vista previa con recuadro de seguimiento](evidence/loop/garruchas/gazebo_pip_partial.mp4)
(31.35 s de vídeo a 4×; 125.2 s simulados). [Fotograma](evidence/loop/garruchas/pip_preview.png).
Ambas cámaras se renderizaron simultáneamente en Gazebo: sus 627 marcas de
tiempo coinciden. La composición y la decodificación completa del MP4 pasaron.
Esto verifica el vídeo parcial, **no el recorrido completo de 341 s**.

La segunda captura corregida, `loop_garruchas_complete_03`, también tuvo una
parada preventiva: 4.520 GiB libres Windows, RSS del árbol de 4.023 GiB,
servidor y solicitud de cierre correctos. No quedaron procesos propios de
Gazebo, captura ni ffmpeg tras el cierre. Se conserva la evidencia de ambas
paradas por memoria. No se intenta de nuevo de forma inmediata: falta margen
estable para completar la captura, revisar descarga/regreso y comparar los
CSV nativos completos con la suite CLI de esta configuración.

Se inspeccionaron la vista general, el seguimiento a 60 s y el recuadro
compuesto. La suspensión larga separa visualmente la jaula de las ruedas;
esta inspección puntual no certifica ausencia de colisiones en todo el ciclo.
Los resultados históricos de 13 apoyos permanecen en `docs/evidence/loop/native`
y no se presentan como resultados de nueve apoyos.

## Reproducción

Desde PowerShell 7, con el entorno nativo compilado:

```powershell
./scripts/windows/run_guarded_loop.ps1 -RunName loop_garruchas_new -Case capture -View overview -Until 341 -NoGui -FollowCarrier
```

Después, en Ubuntu/WSL desde el repositorio:

```bash
python3 scripts/verify_loop_capture.py --capture results/loop_garruchas_new/capture --expected-views overview,follow --output results/loop_garruchas_new/verification.json
python3 scripts/compose_loop_pip.py --capture results/loop_garruchas_new/capture
```

`-NoGui` evita una segunda vista interactiva que consume RAM; ambas cámaras
siguen renderizando en Gazebo. El supervisor conserva el margen de al menos
4 GiB libres Windows, con parada preventiva bajo 5 GiB. No ejecutar dos
grabaciones propias simultáneamente. Las salidas existentes se preservan.

Los apoyos retenidos, las guías idealizadas, el equilibrio cuasiestático y el
contacto no resuelto siguen siendo limitaciones del modelo. Una apariencia
más cercana a un teleférico no constituye validación estructural o de contacto.

La captura corregida loop_garruchas_complete_02 se detuvo preventivamente a 81.8 s al medir 4.673 GiB libres Windows (servidor=0). Se conserva como intento parcial por memoria, no como fallo físico ni servicio completo. La siguiente captura usa la misma reserva y comprueba de nuevo la admisión.
