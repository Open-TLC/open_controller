# Dual model

A two-intersection SUMO scenario used as the default model of the container
stacks (`run_simengine.sh` runs the independent engine on it). The
directory holds both configuration generations:

- `contr.yaml`, `integrated_contr.yaml` - controller configurations in the
  current YAML format (see
  [configuration reference](../../services/control_engine/doc/configuration.md))
- `simsource.json` - the independent engine's JSON configuration (legacy
  format, staged for migration)
- `bumblebee_controller.yaml`, `bumblebee_trainer.yaml` - configurations for
  the bumblebee controller experiments (controller type not yet supported by
  the controller creation)
- `dual.sumocfg`, `dual.net.xml`, `dual.rou.xml`, `dual.add.xml` - the SUMO
  scenario itself
