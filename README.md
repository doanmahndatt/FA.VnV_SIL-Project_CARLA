# FA VnV SIL Test Assets for CARLA

This repository contains SIL test assets for generating, running, and reporting CARLA OpenSCENARIO `.xosc` scenarios. The current structure is domain-oriented: scenarios are grouped by `feature_domain` and `functional`.

Current main flow:

```text
logical YAML + parameter YAML
=> core YAML
=> CARLA .xosc
=> ScenarioRunner batch execution
=> Excel report
```

## 1. Environment Requirements

Target environment:

- Windows 10/11
- Python version compatible with your CARLA Python API wheel
- CARLA Simulator 0.9.16
- CARLA ScenarioRunner source in `scenario_runner/`
- CARLA Python API importable as `carla`
- Python packages from `requirements.txt`

Quick check:

```powershell
python --version
python -c "import carla; print('carla api ok')"
```

If `import carla` fails, install the CARLA Python API wheel that matches your Python version.

## 2. Recommended Workspace Layout

```text
FA_VnV/
|-- CARLA_0.9.16/
|   |-- CarlaUE4.exe
|   `-- PythonAPI/
`-- Test_assets_v1.3/
    |-- scenarios/
    |-- scenario_runner/
    |-- tools/
    `-- requirements.txt
```

The tools resolve paths through `tools/project_paths.py`.

Optional environment overrides:

```powershell
$env:FA_VNV_WORKSPACE_ROOT="C:\Self_Improvement\FA_VnV"
$env:TEST_ASSETS_ROOT="$env:FA_VNV_WORKSPACE_ROOT\Test_assets_v1.3"
$env:CARLA_ROOT="$env:FA_VNV_WORKSPACE_ROOT\CARLA_0.9.16"
```

## 3. Main Folder Structure

```text
Test_assets_v1.3/
│
├── .env                                              # Optional local environment file
├── .gitignore
├── pyproject.toml                                    # Project/tooling metadata, no validation-agent package
├── README.md                                         # This guide
├── requirements.txt                                  # Runtime and maintenance dependencies
│
├── 🚗 scenarios/
│   ├── logical/
│   │   └── <feature_domain_dir>/<functional>/        # Source logical YAML
│   ├── parameters/
│   │   └── <feature_domain_dir>/<functional>/        # Parameter YAML
│   ├── core/
│   │   └── <feature_domain_dir>/<functional>/        # Expanded core YAML folders
│   ├── generated/
│   │   └── carla/<feature_domain_dir>/<functional>/  # Generated .xosc folders
│   └── templates/
│       ├── storyboard/<feature_domain_dir>/          # Storyboard templates
│       └── maneuver_blocks/<feature_domain_dir>/     # Maneuver block templates
│
├── 🔀 expander/
│   ├── expander.py                                   # Logical YAML + parameters → core YAML
│   └── README.md                                     # Detailed expander guide
│
├── 🔌 adapters/
│   └── carla/
│       ├── generated.py                              # Core YAML → CARLA .xosc
│       └── README.md                                 # Detailed generator guide
│
├── 🖥  adas_sil_execution/
│   ├── kpi/                                          # KPI profiles, metrics, collectors, engine
│   ├── runner/                                       # SIL runner orchestration
│   ├── sim/                                          # Simulator configs
│   └── sut/                                          # System-under-test configs
│
├── ▶️ scenario_runner/
│   ├── scenario_runner.py                            # CARLA ScenarioRunner entrypoint
│   ├── srunner/                                      # ScenarioRunner library code/data
│   └── tests/                                        # ScenarioRunner test assets
│
├── 🛠  tools/
│   ├── run_batch.py                                  # GUI batch runner entrypoint
│   ├── project_paths.py                              # Portable path resolution
│   ├── GUI/
│   │   ├── batch_runner.py                           # Batch orchestration
│   │   ├── gui_runner.py                             # Tkinter GUI
│   │   ├── process_manager.py                        # Scenario/camera/HUD process management
│   │   └── report_writer.py                          # Excel reports
│   └── config/
│       ├── camera.py                                 # CARLA spectator camera
│       ├── hud.py                                    # Runtime HUD
│       └── KPI.py                                    # Runtime KPI monitor
│
├── ⚙️ config/
│   └── controllers/
│       └── ACC_controller.py                         # Controller/debug script
│
├── 📊 specifications/
│   ├── Test Requirements.xlsx
│   └── Test Scenarios.xlsx
│
├── 📈 report/
│   ├── <case_id>/                                    # Per-case Excel report folders
│   └── batch_<timestamp>/                            # Batch summary folders
│
├── 📖 docs/
│   └── path_structure.md                             # Portable path layout note
│
└── ...
```

The scenario folders continue deeper than the three-level view above. For example:

```text
scenarios/core/longitudinal_feature/ACC/acc_csc_001/acc_csc_001_001.yaml
scenarios/generated/carla/longitudinal_feature/ACC/acc_csc_001/acc_csc_001_001.xosc
```

## 4. Domain-Based Scenario Layout

Scenario data is stored by folder path:

```text
<feature_domain_dir>/<functional>/<scenario_id>
```

CLI selectors use the shorter domain name, for example `longitudinal/acc/acc_csc_001`, and scripts resolve it to `longitudinal_feature/ACC/acc_csc_001`.

Example for ACC:

```text
scenarios/logical/longitudinal_feature/ACC/acc_csc_001.yaml
scenarios/parameters/longitudinal_feature/ACC/acc_par_001.yaml
scenarios/core/longitudinal_feature/ACC/acc_csc_001/acc_csc_001_001.yaml
scenarios/generated/carla/longitudinal_feature/ACC/acc_csc_001/acc_csc_001_001.xosc
```

Each logical YAML must define:

```yaml
scenario_id: acc_csc_001
functional: ACC
feature_domain: Longitudinal
```

The scripts use `functional` and `feature_domain` as the source of truth for output paths and template resolution.

## 5. Install Dependencies

From repo root:

```powershell
cd C:\Self_Improvement\FA_VnV\Test_assets_v1.3
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `carla==0.9.16` cannot be installed from pip, install the wheel from your CARLA package:

```powershell
pip install C:\CARLA_0.9.16\PythonAPI\carla\dist\<matching-cp-tag>.whl
```

Do not put a `.whl` file directly in `PYTHONPATH`. If a temporary path override is needed, point to the API/source folders:

```powershell
$env:CARLA_ROOT="C:\CARLA_0.9.16"
$env:PYTHONPATH="$env:PYTHONPATH;$env:CARLA_ROOT\PythonAPI\carla;$env:CARLA_ROOT\PythonAPI\carla\agents"
```

## 6. Start CARLA Server

Open a separate terminal:

```powershell
cd C:\CARLA_0.9.16
.\CarlaUE4.exe -quality-level=Low -windowed -ResX=1280 -ResY=720
```

Wait until CARLA finishes loading the map.

Default connection:

```text
host = localhost
port = 2000
```

## 7. Generate Core YAML With Expander

`expander/expander.py` expands one logical scenario plus its parameter file into concrete core YAML cases.

Single scenario:

```powershell
python expander\expander.py longitudinal/acc/acc_csc_001 --clean
```

Multiple scenarios:

```powershell
python expander\expander.py longitudinal/acc/acc_csc_001 longitudinal/acc/acc_csc_002
```

Range:

```powershell
python expander\expander.py longitudinal/acc/acc_csc --from 1 --to 22 --clean
```

Whole functional folder:

```powershell
python expander\expander.py longitudinal/acc --clean
```

Everything under `scenarios/logical/`:

```powershell
python expander\expander.py --all --clean
```

Detailed guide:

```text
expander/README.md
```

## 8. Generate CARLA .xosc Files

`adapters/carla/generated.py` converts core YAML cases into CARLA OpenSCENARIO `.xosc` files.

Single scenario:

```powershell
python adapters\carla\generated.py longitudinal/acc/acc_csc_001 --clean
```

Multiple scenarios:

```powershell
python adapters\carla\generated.py longitudinal/acc/acc_csc_001 longitudinal/acc/acc_csc_002
```

Range:

```powershell
python adapters\carla\generated.py longitudinal/acc/acc_csc --from 1 --to 22 --clean
```

Whole functional folder:

```powershell
python adapters\carla\generated.py longitudinal/acc --clean
```

Everything under `scenarios/core/`:

```powershell
python adapters\carla\generated.py --all --clean
```

Detailed guide:

```text
adapters/carla/README.md
```

## 9. Run One .xosc Manually

Use this for quick debugging before running a batch.

```powershell
python scenario_runner\scenario_runner.py --openscenario scenarios\generated\carla\longitudinal_feature\ACC\acc_csc_001\acc_csc_001_001.xosc --reloadWorld
```

If the scenario is valid, CARLA should spawn the ego vehicle `ev` and target vehicle `tv` according to the `.xosc`.

## 10. Debug Camera And HUD

Run each tool in a separate terminal:

```powershell
python tools\config\camera.py
```

```powershell
python tools\config\hud.py
```

`camera.py` follows the ego vehicle with `role_name="ev"`.

`hud.py` shows runtime values such as:

- simulation time
- EV speed
- TV speed
- longitudinal distance
- TTC

If HUD values stay at zero, check whether the scenario spawned actors with the expected role names.

## 11. Run Batch With GUI

Main entrypoint:

```powershell
python tools\run_batch.py
```

The GUI recursively scans:

```text
scenarios/generated/carla/<feature_domain_dir>/<functional>/<scenario_id>/*.xosc
```

A selectable folder is the full relative scenario group, for example:

```text
longitudinal_feature/ACC/acc_csc_001
longitudinal_feature/ACC/acc_csc_002
```

GUI modes:

- `Single case`: run one `.xosc` case.
- `Single folder`: run all cases inside one scenario group.
- `Multi folder`: run all cases inside selected scenario groups.
- `All folders`: run all generated `.xosc` files.

When you click `Start`, the batch runner:

1. Starts `camera.py`.
2. Starts `hud.py`.
3. Runs each `.xosc` through ScenarioRunner.
4. Monitors KPI runtime.
5. Writes per-case and batch reports.
6. Reloads the CARLA world between cases.

When you click `Stop/End`, the batch runner:

1. Stops the current scenario process.
2. Stops the remaining queue.
3. Writes any available report data.
4. Stops camera/HUD processes started by the batch runner.

## 12. Reports

Per-case report:

```text
report/<case_id>/report.xlsx
```

Batch summary:

```text
report/batch_<timestamp>/summary.xlsx
```

Report sheets:

- `Summary`: total cases, pass/fail/stopped counts, pass rate.
- `All Cases`: all executed cases.
- `Failed Cases`: failed or stopped cases.

Common fail reasons:

- collision detected
- longitudinal distance below threshold
- ScenarioRunner timeout
- ScenarioRunner non-zero exit code
- KPI monitor unavailable or unable to read runtime actors

## 13. Recommended End-To-End Workflow

For one ACC scenario:

```powershell
python expander\expander.py longitudinal/acc/acc_csc_001 --clean
python adapters\carla\generated.py longitudinal/acc/acc_csc_001 --clean
python scenario_runner\scenario_runner.py --openscenario scenarios\generated\carla\longitudinal_feature\ACC\acc_csc_001\acc_csc_001_001.xosc --reloadWorld
```

If the single case works:

```powershell
python expander\expander.py longitudinal/acc/acc_csc --from 1 --to 22 --clean
python adapters\carla\generated.py longitudinal/acc/acc_csc --from 1 --to 22 --clean
python tools\run_batch.py
```

## 14. Troubleshooting

### `ModuleNotFoundError: No module named 'carla'`

Install the CARLA Python API wheel or set `PYTHONPATH` to the CARLA Python API folders.

### `Connection refused` or timeout on port 2000

CARLA server is not running, has not finished loading, or is using a different port.

### Scenario does not spawn vehicles

Check that the `.xosc` contains `ScenarioObject` entries with `role_name="ev"` and `role_name="tv"` if the camera/HUD/KPI tools require them.

### GUI shows no cases

Check that `.xosc` files exist under:

```text
scenarios/generated/carla/<feature_domain_dir>/<functional>/<scenario_id>/
```

Then click `Refresh` in the GUI.

### KPI is unavailable

Check that `tools/config/KPI.py` imports correctly and that CARLA actors exist with the expected role names.

### Excel report cannot be saved

Close any open Excel file under `report/`. The report writer may create a backup if the original file is locked.

## 15. Maintenance Notes

Before committing, inspect the working tree:

```powershell
git status --short
```

Generated scenario data can be large. Review generated YAML/XOSC changes separately from code changes when possible.
