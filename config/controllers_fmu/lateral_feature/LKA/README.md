# LKA FMU Controller for CARLA

This folder contains the FMI 2.0 Co-Simulation LKA controller and CARLA adapters.

The controller follows the same integration structure as the working ACC FMU
controller, but the control law is lateral:

- Sample EV speed, signed lane-center offset and lane heading error from CARLA.
- Keep a light longitudinal speed hold so the EV keeps moving in standalone tests.
- Set `lka_state = 1` when EV offset exceeds `activation_offset`.
- Apply steering opposite to lane offset and heading error to pull EV back to lane center.

## Files

```text
LKAController.py       FMU source model built with pythonfmu
LKA_controller.fmu     Built FMI 2.0 Co-Simulation package
LKA_fmu_controller.py  ScenarioRunner BasicControl wrapper for XOSC use
fmu_adapter.py         Shared FMU runtime and standalone CARLA adapter
signals.yaml           Signal contract between CARLA/scenario parameters and FMU variables
```

## LKA State

```text
0 = inactive or lane unavailable
1 = active lane-centering correction
```

## Rebuild FMU

After changing `LKAController.py`, rebuild from this folder:

```powershell
python -m pythonfmu build -f LKAController.py
```

`pythonfmu` creates `LKAController.fmu`; rename it to `LKA_controller.fmu`
to match the repository convention and `signals.yaml`.

## Parameter Ownership

Fixed controller tuning values such as activation offset, deadband, steering
gains, speed gain, max steer/throttle/brake and fixed delta seconds are owned by
`signals.yaml`.

Scenario parameter YAML files should only contain user-varying test inputs and
block parameters, for example EV/TV speed, lane id, weather, lane departure
trigger time and lane departure offset. Storyboards only pass dynamic scenario
values such as `target_speed`; all fixed controller defaults are loaded by
`LKA_fmu_controller.py` from `signals.yaml`.

## Standalone Adapter

With CARLA running and an ego vehicle using `role_name="ev"`:

```powershell
python fmu_adapter.py --config signals.yaml
```

The ScenarioRunner wrapper `LKA_fmu_controller.py` is the module referenced by
generated OpenSCENARIO files through `adapters/carla/lateral_feature/generated.py`.
