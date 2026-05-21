# Source Folder Execution Flow

Tai lieu nay mo ta 6 folder chinh trong source code va cach chung lien ket voi nhau trong phase generation va phase execution.

Pham vi:

- `specifications`
- `scenarios`
- `expander`
- `adapters`
- `config`
- `tools`

Tong luong xu ly:

```text
specifications
  -> scenarios/logical + scenarios/parameters + scenarios/templates
  -> expander
  -> scenarios/core
  -> adapters/carla
  -> scenarios/generated/carla
  -> tools/run_batch.py + tools/GUI
  -> scenario_runner + CARLA + config/controllers_fmu
  -> tools/config/KPI.py
  -> report/*.xlsx
```

## 1. `specifications`

`specifications` la lop dau vao ve nghiep vu va truy vet test. Folder nay hien chua cac file Excel:

```text
specifications/
|-- Naming Conventions.xlsx
|-- Test Requirements & Assessment Index.xlsx
`-- Test Scenarios.xlsx
```

Vai tro:

- `Test Requirements & Assessment Index.xlsx`: quan ly requirement, assessment item, chi so danh gia va mapping voi test scenario.
- `Test Scenarios.xlsx`: mo ta danh sach scenario can test, dieu kien tien quyet, actor, behavior, expected result.
- `Naming Conventions.xlsx`: quy tac dat ten `scenario_id`, `parameter_id`, folder domain/function, case id.

Folder nay khong duoc script Python import truc tiep trong execution flow hien tai. No la nguon manual/source-of-truth de tao va review cac file YAML trong `scenarios/logical` va `scenarios/parameters`.

Lien ket xuong source:

```text
specifications/Test Scenarios.xlsx
  -> scenarios/general_scenarios/logical/<feature_domain>/<functional>/<scenario_id>.yaml

specifications/Test Requirements & Assessment Index.xlsx
  -> KPI/expected behavior
  -> report result review

specifications/Naming Conventions.xlsx
  -> acc_csc_001, acc_par_001, acc_csc_001_001
```

## 2. `scenarios`

`scenarios` la trung tam du lieu test. Phan code hien dung root:

```text
scenarios/general_scenarios/
```

Cau truc chinh:

```text
scenarios/general_scenarios/
|-- logical/
|-- parameters/
|-- core/
|-- templates/
`-- generated/
```

### `logical`

Chua YAML logic muc cao cua scenario.

Vi du:

```text
scenarios/general_scenarios/logical/longitudinal_feature/ACC/acc_csc_001.yaml
```

No mo ta:

- `scenario_id`: ma scenario logical, vi du `acc_csc_001`.
- `functional`: function ADAS, vi du `ACC`.
- `feature_domain`: domain, vi du `Longitudinal`.
- `pre_condition`: dieu kien tien quyet.
- `actors`: ego vehicle, target vehicle, lane, state.
- `maneuvers`: behavior chinh can dua vao OpenSCENARIO.

### `parameters`

Chua YAML parameter tuong ung voi logical scenario.

Vi du:

```text
scenarios/general_scenarios/parameters/longitudinal_feature/ACC/acc_par_001.yaml
```

Quy tac mapping hien tai:

```text
acc_csc_001 -> acc_par_001
```

No khai bao cac list gia tri dau vao, vi du:

- `ev_lane_id`, `tv_lane_id`
- `ev_speed`, `tv_speed`
- `light`, `weather`
- thoi gian response hoac cac bien dieu kien rieng cua scenario

Neu co `constraints`, `expander` se dung constraints de loai combination khong hop le.

### `core`

Chua YAML da expand tu `logical` + `parameters`.

Vi du:

```text
scenarios/general_scenarios/core/longitudinal_feature/ACC/acc_csc_001/acc_csc_001_001.yaml
```

Moi file core la mot concrete test case. Dang du lieu co dang:

```yaml
scenario_id: acc_csc_001_001
logic:
  scenario_id: acc_csc_001
  functional: ACC
  feature_domain: Longitudinal
parameters:
  ev_speed: 10
  tv_speed: 5
  light: day
  weather: clear
```

`core` la output cua `expander` va input cua domain generator, vi du `adapters/carla/longitudinal_feature/generated.py` hoac `adapters/carla/brake_feature/generated.py`.

### `templates`

Chua template XML/OpenSCENARIO de build `.xosc`.

```text
scenarios/general_scenarios/templates/
|-- storyboard/
`-- maneuver_blocks/
```

- `storyboard`: khung OpenSCENARIO tong, chua map, entity, storyboard, placeholder.
- `maneuver_blocks`: cac block hanh vi lon theo function, vi du ACC cruise, stop, cutin, cutout.

Domain `generated.py` doc `logic.maneuvers.type`, tim maneuver block tuong ung, render placeholder bang `parameters`, roi insert vao storyboard.

### `generated`

Chua file `.xosc` da sinh ra cho CARLA ScenarioRunner.

Vi du:

```text
scenarios/general_scenarios/generated/carla/longitudinal_feature/ACC/acc_csc_001/acc_csc_001_001.xosc
```

Day la input truc tiep cua execution phase.

## 3. `expander`

`expander` bien logical scenario thanh concrete core cases.

File chinh:

```text
expander/expander.py
```

Input:

```text
scenarios/general_scenarios/logical/<domain>/<function>/<scenario_id>.yaml
scenarios/general_scenarios/parameters/<domain>/<function>/<parameter_id>.yaml
```

Output:

```text
scenarios/general_scenarios/core/<domain>/<function>/<scenario_id>/<case_id>.yaml
```

Logic hoat dong:

1. Resolve repo path bang `tools.project_paths.get_project_paths`.
2. Resolve selector, vi du `longitudinal/acc/acc_csc_001`.
3. Load logical YAML.
4. Tim parameter YAML bang cach doi `csc` thanh `par`.
5. Lay tat ca list trong `parameters`.
6. Tao Cartesian product bang `itertools.product`.
7. Neu co `constraints`, dung `validate_constraints()` de skip combination khong hop le.
8. Build core scenario:

```text
logical + 1 parameter combination -> acc_csc_001_001.yaml
logical + 1 parameter combination -> acc_csc_001_002.yaml
...
```

Che do chay:

```powershell
python expander\expander.py longitudinal/acc/acc_csc_001 --clean
python expander\expander.py longitudinal/acc/acc_csc --from 1 --to 22 --clean
python expander\expander.py longitudinal/acc --clean
python expander\expander.py --all --clean
```

`--clean` xoa output cu bang cach rename folder sang `.trash_*` roi delete. Cach nay giam loi file lock tren Windows.

## 4. `adapters`

`adapters` la lop convert asset trung gian sang format cua simulator/tool cu the. Hien co adapter cho CARLA:

```text
adapters/carla/
|-- generated_wrapper.py
|-- longitudinal_feature/generated.py
|-- brake_feature/generated.py
`-- README.md
```

File chinh:

```text
adapters/carla/<feature_domain>/generated.py
```

Input:

```text
scenarios/general_scenarios/core/<domain>/<function>/<scenario_id>/<case_id>.yaml
scenarios/general_scenarios/templates/storyboard/...
scenarios/general_scenarios/templates/maneuver_blocks/...
config/controllers_fmu/<domain>/<function>/...
```

Output:

```text
scenarios/general_scenarios/generated/carla/<domain>/<function>/<scenario_id>/<case_id>.xosc
```

Logic hoat dong:

1. Load core YAML.
2. Lay `functional` va `feature_domain` tu top-level hoac `logic`.
3. Resolve storyboard template:
   - ACC single target vehicle: `ACC_single-TV_storyboard.xosc`
   - ACC multi target vehicles: `ACC_multi-TVs_storyboard.xosc`
   - fallback theo function/domain neu co.
4. Discover maneuver block trong:

```text
scenarios/general_scenarios/templates/maneuver_blocks/<domain>/<function>/
```

5. Doc `logic.maneuvers`, map `type` sang maneuver block XML.
6. Render placeholder `${...}` bang parameter trong core YAML.
7. Insert maneuver group vao `<Act>` cua storyboard.
8. Resolve controller artifact trong `config/controllers_fmu`.
9. Replace placeholder controller:

```text
${controller_module}
${controller_config}
${controller_fmu}
```

10. Map environment tu parameter `light` va `weather`.
11. Ghi `.xosc` ra `scenarios/general_scenarios/generated/carla`.

Che do chay:

```powershell
python adapters\carla\longitudinal_feature\generated.py longitudinal/acc/acc_csc_001 --clean
python adapters\carla\longitudinal_feature\generated.py longitudinal/acc/acc_csc --from 1 --to 22 --clean
python adapters\carla\longitudinal_feature\generated.py longitudinal/acc --clean
python adapters\carla\generated_wrapper.py --all --clean
```

Lien ket quan trong voi `config`:

```text
core YAML metadata
  -> feature_domain=Longitudinal, functional=ACC
  -> config/controllers_fmu/longitudinal_feature/ACC/ACC_fmu_controller.py
  -> config/controllers_fmu/longitudinal_feature/ACC/signals.yaml
  -> config/controllers_fmu/longitudinal_feature/ACC/ACC_controller.fmu
```

Neu cac file controller nay thieu, generator se fail fast.

## 5. `config`

`config` chua controller va signal contract dung trong `.xosc` execution.

Cau truc hien tai:

```text
config/
|-- controllers_fmu/
|   `-- longitudinal_feature/ACC/
|       |-- ACCController.py
|       |-- ACC_controller.fmu
|       |-- ACC_fmu_controller.py
|       |-- fmu_adapter.py
|       |-- signals.yaml
|       `-- README.md
`-- controllers_py/
    `-- longitudinal_feature/ACC/ACC_controller.py
```

### `controllers_fmu`

Day la controller path chinh ma domain generator gan vao `.xosc`.

Vai tro tung file ACC:

- `ACCController.py`: source model de build FMU bang `pythonfmu`.
- `ACC_controller.fmu`: FMI 2.0 Co-Simulation binary package.
- `ACC_fmu_controller.py`: ScenarioRunner `BasicControl` wrapper. Khi ScenarioRunner chay `.xosc`, wrapper nay dieu khien ego actor.
- `fmu_adapter.py`: runtime adapter dung `fmpy`, lay signal tu CARLA, step FMU, convert output thanh `carla.VehicleControl`.
- `signals.yaml`: contract giua CARLA/scenario/controller va FMU variables.

Runtime controller flow:

```text
ScenarioRunner loads XOSC
  -> XOSC references ACC_fmu_controller.py
  -> AccFmuController actor control starts
  -> fmu_adapter.ACCFmuRuntime loads ACC_controller.fmu
  -> CarlaACCSignalAdapter samples CARLA state
  -> FMU step()
  -> output throttle/brake/steer
  -> actor.apply_control(...)
```

### `controllers_py`

Chua controller Python thu nghiem/debug. Flow generation hien tai uu tien `controllers_fmu`, khong resolve `controllers_py` trong domain generator.

## 6. `tools`

`tools` la lop orchestration va runtime utilities.

Cau truc chinh:

```text
tools/
|-- project_paths.py
|-- run_batch.py
|-- start_carla.py
|-- GUI/
|   |-- gui_runner.py
|   |-- batch_runner.py
|   |-- process_manager.py
|   `-- report_writer.py
`-- config/
    |-- camera.py
    |-- hud.py
    `-- KPI.py
```

### `project_paths.py`

Dung de resolve path portable cho toan bo repo.

No tim:

- `repo_root`: folder co `pyproject.toml`, `scenarios`, `scenario_runner`.
- `workspace_root`: parent cua repo hoac `FA_VNV_WORKSPACE_ROOT`.
- `carla_root`: folder CARLA tu `CARLA_ROOT` hoac scan workspace.

No cung cap:

- `scenarios_root`
- `generated_xosc_root`
- `core_scenarios_root`
- `scenario_runner_script`
- `report_root`
- `build_subprocess_env()`
- `ensure_carla_python_imports()`

`expander`, `adapters`, `tools/run_batch.py`, `BatchRunner`, `ProcessManager` deu dung file nay.

### `run_batch.py`

Entry point de mo GUI batch runner:

```powershell
python tools\run_batch.py
```

Flow:

```text
run_batch.py
  -> get_project_paths().ensure_carla_python_imports()
  -> BatchRunnerGUI(paths.repo_root)
  -> Tkinter GUI
```

### `tools/GUI/gui_runner.py`

Xay giao dien chon case de chay. GUI discover jobs tu `.xosc` da generate.

Mode hien co:

- `single_case`: chay mot case.
- `single_folder`: chay mot scenario folder.
- `multi_folder`: chay nhieu folder duoc tick.
- `all_folders`: chay tat ca folder trong function dang chon.

GUI khong tu generate `.xosc`; no chi chay nhung `.xosc` da co trong `scenarios/generated/carla`.

### `tools/GUI/batch_runner.py`

La core execution orchestrator.

Nhiem vu:

1. Discover `.xosc` trong `scenarios/general_scenarios/generated/carla`.
2. Map moi `.xosc` ve core YAML tuong ung trong `scenarios/general_scenarios/core`.
3. Tao `ScenarioJob`.
4. Start support tools `camera.py` va `hud.py`.
5. Start tung scenario qua `scenario_runner.py --openscenario`.
6. Tao KPI monitor va goi `kpi.step()` trong loop.
7. Doi process ket thuc, timeout, hoac user stop.
8. Tong hop result.
9. Ghi report case va batch summary.
10. Reload CARLA world sau moi case.

### `tools/GUI/process_manager.py`

Quan ly subprocess:

- Start `tools/config/camera.py`
- Start `tools/config/hud.py`
- Start ScenarioRunner:

```text
python scenario_runner/scenario_runner.py --openscenario <case.xosc> --reloadWorld
```

- Terminate scenario hien tai.
- Terminate support tools.
- Build subprocess env co CARLA Python API path.

### `tools/GUI/report_writer.py`

Ghi Excel report bang pandas:

```text
report/<case_id>/report.xlsx
report/batch_<timestamp>/summary.xlsx
```

Moi report gom:

- `Summary`
- `All Cases`
- `Failed Cases`

### `tools/config/camera.py`

Runtime spectator camera. Script ket noi CARLA `localhost:2000`, tim vehicle co `role_name="ev"`, roi set spectator birdview theo ego vehicle.

### `tools/config/hud.py`

Runtime HUD bang pygame. Script hien thi:

- EV speed
- target vehicle speed
- distance
- TTC
- lane/map information

HUD tim ego bang `role_name="ev"` va target bang prefix `tv`.

### `tools/config/KPI.py`

Runtime KPI monitor.

Logic hien tai:

- Ket noi CARLA.
- Tim EV bang `role_name="ev"`.
- Tim TV bang `role_name="tv"`.
- Attach collision sensor vao EV.
- Tinh speed, longitudinal distance.
- Fail neu collision.
- Fail neu distance bumper-to-bumper < 6m.
- Tra ve result `PASS`/`FAIL` kem metric:
  - `fail_reason`
  - `fail_time`
  - `ev_max_speed`
  - `ev_min_speed`
  - `dist_min`

## Phase Execution A-Z

### Phase A: Define test source

Nguoi dung doc `specifications`, sau do tao/cap nhat:

```text
scenarios/general_scenarios/logical/...
scenarios/general_scenarios/parameters/...
scenarios/general_scenarios/templates/...
config/controllers_fmu/...
```

Day la phase authoring. Chua chay CARLA.

### Phase B: Expand logical scenario

Chay:

```powershell
python expander\expander.py longitudinal/acc/acc_csc_001 --clean
```

Ket qua:

```text
logical YAML + parameter YAML
  -> many concrete core YAML files
```

Vi du:

```text
acc_csc_001.yaml + acc_par_001.yaml
  -> acc_csc_001_001.yaml
  -> acc_csc_001_002.yaml
  -> ...
```

### Phase C: Generate CARLA OpenSCENARIO

Chay:

```powershell
python adapters\carla\longitudinal_feature\generated.py longitudinal/acc/acc_csc_001 --clean
```

Ket qua:

```text
core YAML + storyboard template + maneuver blocks + config controller
  -> .xosc
```

File `.xosc` luc nay da chua du thong tin de ScenarioRunner spawn actor, gan behavior, gan controller va chay trong CARLA.

### Phase D: Start CARLA

CARLA server phai dang chay truoc execution:

```text
localhost:2000
```

Co the start bang tay hoac dung tool rieng neu da setup duong dan CARLA.

### Phase E: Select and run cases

Chay GUI:

```powershell
python tools\run_batch.py
```

GUI load `.xosc` tu:

```text
scenarios/general_scenarios/generated/carla
```

User chon single case/folder/multi folder/all folder.

### Phase F: Runtime orchestration

Khi bam Start:

```text
BatchRunner.run()
  -> ProcessManager.start_support_tools()
     -> camera.py
     -> hud.py
  -> for each ScenarioJob:
     -> ProcessManager.start_scenario(xosc)
        -> scenario_runner/scenario_runner.py --openscenario <xosc> --reloadWorld
     -> KPIMonitor.step() loop
     -> wait scenario end/timeout/stop
     -> ReportWriter.write_case_report()
     -> ReportWriter.write_batch_summary()
     -> reload CARLA world
```

### Phase G: ScenarioRunner + controller execution

Trong khi ScenarioRunner chay `.xosc`:

```text
.xosc
  -> ScenarioRunner parse OpenSCENARIO
  -> spawn EV/TV actors
  -> load map and storyboard
  -> import controller module from config/controllers_fmu
  -> AccFmuController.run_step()
  -> fmu_adapter samples CARLA signals
  -> ACC_controller.fmu computes control
  -> apply throttle/brake/steer to EV
```

Song song:

```text
camera.py follows EV
hud.py displays runtime metrics
KPI.py checks pass/fail condition
```

### Phase H: Reporting

Sau moi case:

```text
BatchRunner.run_one()
  -> row result
  -> report/<case_id>/report.xlsx
```

Sau batch:

```text
report/batch_<timestamp>/summary.xlsx
```

Report gom result, reason, duration, KPI metric, xosc path va environment parameter.

## Dependency Map

```text
specifications
  informs
scenarios/logical + scenarios/parameters
  consumed by
expander/expander.py
  writes
scenarios/core
  consumed by
adapters/carla/<feature_domain>/generated.py
  consumes also
scenarios/templates + config/controllers_fmu
  writes
scenarios/generated/carla/*.xosc
  consumed by
tools/GUI/batch_runner.py
  starts
scenario_runner/scenario_runner.py + tools/config/camera.py + tools/config/hud.py
  uses
config/controllers_fmu at ScenarioRunner runtime
  monitored by
tools/config/KPI.py
  reported by
tools/GUI/report_writer.py
```

## Practical Order Of Operations

1. Cap nhat `specifications` neu requirement/test matrix thay doi.
2. Cap nhat `scenarios/general_scenarios/logical`.
3. Cap nhat `scenarios/general_scenarios/parameters`.
4. Cap nhat `scenarios/general_scenarios/templates` neu behavior XOSC thay doi.
5. Cap nhat `config/controllers_fmu` neu controller/signals thay doi.
6. Chay `expander`.
7. Chay domain generator, vi du `adapters/carla/longitudinal_feature/generated.py` hoac `adapters/carla/brake_feature/generated.py`.
8. Start CARLA.
9. Chay `tools/run_batch.py`.
10. Review `report`.

## Important Notes

- `expander` khong tao `.xosc`; no chi tao `core YAML`.
- `adapters/carla` khong chay simulation; no chi tao `.xosc`.
- `tools/run_batch.py` khong generate scenario; no chi discover va execute `.xosc` da ton tai.
- `config/controllers_fmu` duoc gan vao `.xosc` o generation phase, nhung controller thuc su chay o execution phase trong ScenarioRunner.
- `specifications` la source-of-truth ve test design, nhung hien khong co script nao parse Excel truc tiep trong pipeline.
- `tools/project_paths.py` la diem chung giup cac script chay duoc tu repo root hoac subfolder.
