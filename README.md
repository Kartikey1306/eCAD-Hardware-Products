# PR assets

Images shown in the multi-domain pull requests (issue #27). Not part of the
code; nothing here is read by the pipeline.

- `images/robotic_joint_001.png` -- the mechanical sample's STEP assembly,
  rendered from `datasets/cad/robotic_joint_001/source/robotic_joint_001.step`
  with OpenCASCADE (cadquery-ocp 8.0.1) and VTK.
- `images/servo_supply_001_waveforms.png` -- the electrical sample's bus
  voltage and supply current, from ngspice-47 running the committed deck
  `datasets/cad/servo_supply_001/derived/electrical/servo_supply_001.cir`
  with a data-dump block added to a scratch copy only.
