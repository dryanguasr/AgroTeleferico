# Vídeos representativos

## Piloto actual: soportes exteriores y patio entre pisos

- [Patio: vista general](evidence/single_span_revised/capture_patio/gazebo.mp4).
- [Patio: seguimiento del carro](evidence/single_span_revised/capture_patio/follow.mp4).
- [Ladera: vista general](evidence/single_span_revised/capture_ladera/gazebo.mp4).
- [Ladera: seguimiento](evidence/single_span_revised/capture_ladera/follow.mp4).

Grabaciones completas de Gazebo, reproducción nominal 4×. Consulte el
[alcance de la revisión y las verificaciones](soportes_revisados.md).

## Circuito histórico de seis carros

Selección de grabaciones existentes del circuito de seis carros, renderizadas
en Gazebo. Los MP4 están incluidos en esta rama del repositorio; si GitHub no
ofrece reproducción en la página del archivo, usar **View raw / Download**.

| Vídeo | Duración del MP4 | Qué muestra | Alcance |
|---|---:|---|---|
| [Circuito completo: vista exterior](evidence/loop/native/capture/gazebo.mp4) | 85.30 s | Recorrido, carga, descarga y ráfaga en la variante anterior de 13 apoyos | Servicio completo; cobertura de 341 s simulados |
| [Postes en T y garruchas con recuadro](evidence/loop/garruchas/gazebo_pip_partial.mp4) | 31.35 s | Nueve postes, vanos de 6 m y seguimiento cercano superpuesto a la vista general | Parcial; hasta 125.2 s simulados, detenido por reserva de RAM |
| [Detalle de la garrucha](videos/garrucha_seguimiento_parcial.mp4) | 31.35 s | Cámara de seguimiento a resolución completa: ruedas, suspensión y jaula de carga | La misma ejecución parcial del vídeo anterior, no otro ensayo |

Los vídeos se reproducen nominalmente a 4×, a 1280×800 y 20 fps. El detalle
contiene 627 fotogramas y se verificó mediante decodificación completa antes
de publicarlo. Su archivo original es
`results/loop_garruchas_complete_03/capture/follow.mp4`; se copia sin recodificar.
Los hashes y tamaños de los tres vídeos constan en [manifest.json](videos/manifest.json).

![Vista general y recuadro de seguimiento](evidence/loop/garruchas/pip_preview.png)

## Evidencia y pendientes

- [Verificación del circuito completo](evidence/loop/native/capture/verification.json).
- [Sincronización y verificación del recuadro parcial](evidence/loop/garruchas/partial_pip_verification.json).
- [Revisión de garruchas y punto de retomada](revision_garruchas.md).

Esta selección corresponde a la extensión del circuito. Para los tres escenarios
originales (`single`, `double`, `spider`), están disponibles las escenas y métricas
en [resultados del piloto](resultados.md); esta publicación no añade vídeos nuevos
de esos escenarios ni los sustituye por vídeos del circuito.

Queda pendiente grabar el recorrido completo de la revisión de nueve postes y
validar sus resultados nativos completos. El heartbeat permanece **suspendido**
por solicitud del usuario; publicar esta selección no reactiva el trabajo.
