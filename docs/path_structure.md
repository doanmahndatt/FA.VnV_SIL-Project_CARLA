# Portable Path Layout

The code resolves paths from a workspace root instead of hard-coding drive-specific locations.

Recommended layout:

```text
FA_VnV/
|-- CARLA_0.9.16/
|   |-- CarlaUE4.exe
|   |-- PythonAPI/
|-- Test_assets_v1.3/
|   |-- scenarios/
|   |-- scenario_runner/
|   |-- tools/
```

Default resolution:

- `TEST_ASSETS_ROOT`: optional override for the test asset repo.
- `FA_VNV_WORKSPACE_ROOT`: optional override for the parent workspace folder.
- `CARLA_ROOT`: optional override for the CARLA installation folder.
- If `CARLA_ROOT` is not set, the tools look for a sibling folder named `CARLA*` or `carla*` next to the test asset repo.

Common commands:

```powershell
python tools\start_carla.py
python expander\expander.py acc_csc 003
python adapters\carla\generated.py acc_csc_003
python tools\run_batch.py
```

On a new machine, either keep the recommended folder layout or set environment variables:

```powershell
$env:FA_VNV_WORKSPACE_ROOT="D:\FA_VnV"
$env:TEST_ASSETS_ROOT="$env:FA_VNV_WORKSPACE_ROOT\Test_assets_v1.3"
$env:CARLA_ROOT="$env:FA_VNV_WORKSPACE_ROOT\CARLA_0.9.16"
```
