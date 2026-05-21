# AEB FMU Controller for CARLA

This folder contains the FMI 2.0 Co-Simulation AEB controller and CARLA adapters.

The controller is derived from the working ACC FMU controller structure, but the
control law is AEB-specific:

- Find the nearest target vehicle in front of EV on the same lane.
- Compute bumper-to-bumper distance, relative closing speed and TTC.
- Stay inactive when no lead vehicle exists or TTC is safe.
- Apply warning brake, normal AEB brake or emergency brake as TTC/distance risk increases.
- Hold brake briefly after intervention to avoid flicker.

## Files

```text
AEBController.py       FMU source model built with pythonfmu
AEB_controller.fmu     Built FMI 2.0 Co-Simulation package
AEB_fmu_controller.py  ScenarioRunner BasicControl wrapper for XOSC use
fmu_adapter.py         Shared FMU runtime and standalone CARLA adapter
signals.yaml           Signal contract between CARLA/scenario parameters and FMU variables
```

## AEB States

```text
0 = inactive
1 = warning brake
2 = AEB active
3 = emergency brake
```

## Rebuild FMU

After changing `AEBController.py`, rebuild from this folder:

```powershell
python -m pythonfmu build -f AEBController.py
```

The generated FMU must expose the variables listed in `signals.yaml`.

## Parameter Ownership

Fixed controller tuning values such as TTC thresholds, gains, max brake/steer,
hold time and fixed delta seconds are owned by `signals.yaml`.

Scenario parameter YAML files should only contain user-varying test inputs and
block parameters, for example EV/TV speed, lane id, weather, trigger time and
TV deceleration. Storyboards only pass dynamic scenario values such as
`target_speed`; all fixed controller defaults are loaded by `AEB_fmu_controller.py`
from `signals.yaml`.

## Standalone Adapter

With CARLA running and an ego vehicle using `role_name="ev"`:

```powershell
python fmu_adapter.py --config signals.yaml
```

The ScenarioRunner wrapper `AEB_fmu_controller.py` is the module referenced by
generated OpenSCENARIO files through `adapters/carla/brake_feature/generated.py`.
