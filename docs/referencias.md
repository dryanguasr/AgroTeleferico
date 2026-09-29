# Referencias inspeccionadas

Consulta: 2026-09-29. No se ejecutaron estos proyectos ni se afirma compatibilidad directa con Harmonic. El código del piloto es nuevo.

| Proyecto | Revisión consultada | Aporte y límites |
|---|---|---|
| [Gazebo_cable](https://github.com/jmz3/Gazebo_cable) | `660a4679f9f277f1af61a7b07f76b20c7f871698` | README inspeccionado: cable segmentado con extremo controlado, ROS 1/catkin. No se detectó licencia declarada: no se copia código. |
| [cdpr-simulation](https://github.com/balazs-bamer/cdpr-simulation) | `d8b6fa54eb4c150b2903e9c8ef629655d4739d7e` | README, árbol y JointForceCalculator.cpp inspeccionados. Modelos CDPR y control en ROS Melodic/Gazebo Classic. MIT global; el archivo inspeccionado lleva Apache-2.0. Conservar avisos por archivo si se reutiliza posteriormente. |
| [CARDSFlow](https://github.com/CARDSflow/CARDSflow) | `974f81d38ce97aff6f33a7b3cd78421e62f6b0e7` | README, licencia y [página oficial](https://roboy.org/cardsflow/) inspeccionados. CAD, simulación y control con CASPR. BSD-3-Clause en el repositorio padre; comprobar licencias de cada submódulo antes de reutilizar. |
| [CaRoSim](https://github.com/aau-cns/CaRoSim) | `4fdd334b5d8ecbfcdd3779276d94ac7824ed80ea` | README y licencia inspeccionados. Estudio de flecha de cables; usa Unity3D, no Gazebo. BSD-2-Clause; dependencias de Unity pueden tener condiciones diferentes. No se incorpora como dependencia. |

`cdpr-simulation` cita a Franklin Okoli, Yuchuan Lang, Olivier Kermorgant y Stéphane Caro, “Cable-Driven Parallel Robot simulation using Gazebo and ROS”, 2018. Se registra el antecedente sin afirmar reproducir sus experimentos.

La búsqueda inicial no localizó un carro agrícola de doble portante listo para reutilizar en Gazebo; esto no demuestra inexistencia. Se optó por una implementación reducida propia y control determinista antes de aprendizaje por refuerzo. La base Jazzy/Harmonic sigue la [matriz oficial](https://gazebosim.org/docs/harmonic/ros_installation/).
