# ACC FMU Controller for CARLA

This folder contains the FMI 2.0 Co-Simulation ACC controller and the CARLA adapters
that feed runtime signals into the FMU.

## Files

```text
ACCController.py       FMU source model built with pythonfmu
ACC_controller.fmu     Built FMI 2.0 Co-Simulation package
ACC_fmu_controller.py  ScenarioRunner BasicControl wrapper for future XOSC use
fmu_adapter.py         Shared FMU runtime and standalone CARLA adapter
signals.yaml           Signal contract between CARLA/scenario parameters and FMU variables
```

## FMU Signal Contract

Inputs:

- `ego_speed`, `lead_distance`, `lead_speed`
- `target_speed`, `time_gap`, `min_distance`
- `heading_error`, `has_lead`, `has_waypoint`
- `kp_speed`, `kp_steer`, `max_throttle`, `max_brake`, `max_steer`

Outputs:

- `throttle`, `brake`, `steer`
- `acceleration`, `deceleration`, `jerk`
- `acc_target_speed`, `safe_distance`, `distance_error`

## Rebuild FMU

After changing `ACCController.py`, rebuild the FMU from this folder:

```powershell
python -m pythonfmu build -f ACCController.py
```

The generated FMU must expose the variables listed in `signals.yaml`; otherwise
`fmu_adapter.py` will fail fast with a variable mismatch.

## Standalone Adapter

With CARLA running and an ego vehicle using `role_name="ev"`:

```powershell
python fmu_adapter.py --config signals.yaml
```

The standalone adapter controls longitudinal behavior and only applies steering
when route heading input is available. The ScenarioRunner wrapper
`ACC_fmu_controller.py` provides waypoint-based `heading_error` for XOSC-driven
execution.
