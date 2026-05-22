# FA VnV — SIL Test Assets v1.4

### Author: DatDM7.FPT
### Supervisor: TungNV68.FPT

> CARLA 0.9.16 · OpenSCENARIO · FMI 2.0 · ADAS (ACC / AEB / LKA)

Framework SIL (Software-in-the-Loop) để sinh, thực thi và đánh giá tự động các kịch bản kiểm thử tính năng ADAS trên CARLA simulator. Toàn bộ pipeline chạy trên Windows, không cần phần cứng thực tế.

---

## 1. Main Flow (v1.4)

```
┌─────────────────────────────────────────────────────────────────────┐
│  [DEFINE]  logical YAML + parameters YAML                           │
│            scenarios/general_scenarios/logical/<domain>/<fn>/       │
│            scenarios/general_scenarios/parameters/<domain>/<fn>/    │
└───────────────────────┬─────────────────────────────────────────────┘
                        │  expander/expander.py
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [EXPAND]  core YAML (parameterized test cases)                     │
│            scenarios/general_scenarios/core/<domain>/<fn>/<id>/     │
└───────────────────────┬─────────────────────────────────────────────┘
                        │  adapters/carla/<domain>/generated.py
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [GENERATE]  CARLA OpenSCENARIO (.xosc)                             │
│              scenarios/general_scenarios/generated/carla/...        │
└───────────────────────┬─────────────────────────────────────────────┘
                        │  tools/run_batch.py  (GUI)
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [EXECUTE]  CARLA + ScenarioRunner + FMU Controller                 │
│             + urban_traffic_manager (background TVs)                │
│             + camera.py  +  hud.py                                  │
└───────────────────────┬─────────────────────────────────────────────┘
                        │  tools/config/KPI.py
                        │  adas_sil_execution/kpi/
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [EVALUATE]  KPI: min_distance · collision · jerk · TTC             │
└───────────────────────┬─────────────────────────────────────────────┘
                        │  tools/GUI/report_writer.py
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [REPORT]  Excel (.xlsx)                                            │
│            report/<case_id>/report.xlsx                             │
│            report/batch_<timestamp>/summary.xlsx                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Environment Requirements

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| OS | Windows 10 / 11 (64-bit) | Bắt buộc — CARLA exe chỉ chạy trên Windows |
| Python | 3.8 – 3.10 | Phải khớp với CARLA Python API wheel |
| CARLA Simulator | **0.9.16** | Bắt buộc — API thay đổi giữa các phiên bản |
| CARLA ScenarioRunner | 0.9.16 (bundle) | Đã có sẵn trong `scenario_runner/` |
| Git | Bất kỳ | Quản lý version |
| RAM | ≥ 16 GB | CARLA + Python + HUD |
| GPU | ≥ 4 GB VRAM | Render CARLA (dùng `-quality-level=Low` nếu cần) |

Kiểm tra nhanh sau khi cài:

```powershell
python --version
python -c "import carla; print('carla ok', carla.__version__)"
python -c "import yaml, pandas, openpyxl, pygame; print('deps ok')"
```

---

## 3. Workspace Layout

```
FA_VnV/                                ← FA_VNV_WORKSPACE_ROOT
├── CARLA_0.9.16/                      ← CARLA_ROOT
│   ├── CarlaUE4.exe
│   └── PythonAPI/carla/dist/*.whl
└── Test_assets_v1.4/                  ← TEST_ASSETS_ROOT  (repo root)
    ├── adapters/
    ├── adas_sil_execution/
    ├── config/
    ├── expander/
    ├── report/
    ├── scenario_runner/
    ├── scenarios/
    ├── tools/
    ├── requirements.txt
    └── README.md  ← file này
```

Path resolver tự động tìm root dựa trên `pyproject.toml` hoặc thư mục `scenarios/`.  
Override bằng biến môi trường nếu cần:

```powershell
$env:FA_VNV_WORKSPACE_ROOT = "C:\Self_Improvement\FA_VnV"
$env:TEST_ASSETS_ROOT      = "$env:FA_VNV_WORKSPACE_ROOT\Test_assets_v1.4"
$env:CARLA_ROOT            = "$env:FA_VNV_WORKSPACE_ROOT\CARLA_0.9.16"
```

---

## 4. System Architecture

```
┌──────────────────── SCENARIO DEFINITION LAYER ─────────────────────┐
│  logical YAML  ──>  parameters YAML  ──>  expander.py              │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌──────────────────── SCENARIO GENERATION LAYER ─────────────────────┐
│  core YAML  ──>  adapters/carla/*.py  ──>  .xosc (OpenSCENARIO)    │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌──────────────────── EXECUTION LAYER ───────────────────────────────┐
│  tools/GUI/ (BatchRunner + ProcessManager)                          │
│    ├── ScenarioRunner  ──>  CARLA world                             │
│    ├── FMU Controller  ──>  EV control (ACC / AEB / LKA)           │
│    ├── UrbanTrafficManager  ──→  background TVs                     │
│    ├── camera.py  ──>  birdview spectator                           │
│    └── hud.py     ──>  real-time metrics HUD                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌──────────────────── KPI & REPORTING LAYER ─────────────────────────┐
│  KPI.py / kpi_engine.py  ──>  collect metrics                       │
│  report_writer.py         ──>  Excel (.xlsx)                        │
└────────────────────────────────────────────────────────────────────┘
```

**Controller loop (per simulation tick = 0.05 s):**

```
CARLA world  ──>  fmu_adapter.sample()  ──>  FMU.do_step()  ──>  vehicle.apply_control()
```

---

## 5. Folder Structure (Level 4)

```
Test_assets_v1.4/
│
├── scenarios/
│   └── general_scenarios/
│       ├── logical/                          ← [DEFINE] Concept scenarios
│       │   ├── brake_feature/AEB/            │  4 YAML files (1 per scenario_id)
│       │   ├── lateral_feature/LKA/          │  1 YAML file
│       │   └── longitudinal_feature/ACC/     │  22 YAML files
│       │
│       ├── parameters/                       ← [DEFINE] Parameter spaces
│       │   ├── brake_feature/AEB/            │  4 YAML (1:1 với logical)
│       │   ├── lateral_feature/LKA/          │  1 YAML
│       │   └── longitudinal_feature/ACC/     │  22 YAML
│       │
│       ├── core/                             ← [EXPAND] Concrete test cases
│       │   ├── brake_feature/
│       │   │   └── AEB/
│       │   │       ├── aeb_csc_001/          │  30 YAML  (acc_csc_001_001..030)
│       │   │       ├── aeb_csc_003/          │  18 YAML
│       │   │       ├── aeb_csc_005/          │  36 YAML
│       │   │       └── aeb_csc_007/          │  18 YAML
│       │   ├── lateral_feature/
│       │   │   └── LKA/lka_csc_001/          │   1 YAML
│       │   └── longitudinal_feature/
│       │       └── ACC/
│       │           ├── acc_csc_001/          │  24 YAML
│       │           ├── acc_csc_002/          │  36 YAML
│       │           ├── ...                   │  ...
│       │           └── acc_csc_022/          │ 108 YAML
│       │                              TOTAL: │ 2,323 YAML
│       │
│       ├── generated/carla/                  ← [GENERATE] OpenSCENARIO executables
│       │   ├── brake_feature/AEB/            │  102 XOSC
│       │   ├── lateral_feature/LKA/          │    1 XOSC
│       │   └── longitudinal_feature/ACC/     │ 2,220 XOSC
│       │                              TOTAL: │ 2,323 XOSC (1:1 với core YAML)
│       │
│       └── templates/
│           ├── storyboard/                   ← Base storyboard XML per feature
│           └── maneuver_blocks/              ← Reusable maneuver XML blocks
│
├── expander/
│   ├── expander.py                           ← Main expand tool
│   └── README.md
│
├── adapters/
│   └── carla/
│       ├── _generated_common.py              ← Core XOSC generation engine (shared)
│       ├── generated_wrapper.py              ← Compatibility wrapper (all domains)
│       ├── longitudinal_feature/generated.py ← ACC/HWA generator
│       ├── lateral_feature/generated.py      ← LKA generator
│       ├── brake_feature/generated.py        ← AEB/RAEB generator
│       └── README.md
│
├── config/
│   ├── controllers_fmu/                      ← FMI 2.0 closed-loop controllers
│   │   ├── brake_feature/AEB/
│   │   │   ├── AEBController.py              ← FMU logic (Fmi2Slave)
│   │   │   ├── AEB_fmu_controller.py         ← BasicControl adapter cho ScenarioRunner
│   │   │   ├── fmu_adapter.py                ← Signal bridge CARLA↔FMU
│   │   │   ├── signals.yaml                  ← I/O signal mapping + default params
│   │   │   └── AEB_controller.fmu            ← Compiled binary (pythonfmu build)
│   │   ├── lateral_feature/LKA/
│   │   │   ├── LKAController.py
│   │   │   ├── LKA_fmu_controller.py
│   │   │   ├── fmu_adapter.py
│   │   │   ├── signals.yaml
│   │   │   └── LKA_controller.fmu
│   │   └── longitudinal_feature/ACC/
│   │       ├── ACCController.py
│   │       ├── ACC_fmu_controller.py
│   │       ├── fmu_adapter.py
│   │       ├── signals.yaml
│   │       └── ACC_controller.fmu
│   │
│   ├── controllers_py/                       ← Python reference controllers
│   │   └── longitudinal_feature/ACC/
│   │       └── ACC_controller.py
│   │
│   └── traffic/                              ← Background traffic profiles
│       ├── urban_traffic.yaml                ← Base profile (fallback)
│       ├── longitudinal_feature/
│       │   ├── ACC/acc_traffic.yaml          ← ACC-tuned traffic
│       │   └── HWA/hwa_traffic.yaml
│       ├── lateral_feature/
│       │   └── LKA/lka_traffic.yaml          ← LKA: oncoming, opposite heading
│       └── brake_feature/
│           ├── AEB/aeb_traffic.yaml          ← AEB: slow, short range
│           └── RAEB/raeb_traffic.yaml
│
├── adas_sil_execution/
│   ├── interface/
│   │   ├── signal_mapping.yaml               ← Ánh xạ tên signal giữa SUT↔KPI
│   │   └── timing_model.yaml                 ← Latency / sync model
│   ├── kpi/
│   │   ├── engine/kpi_engine.py              ← KPIEngine: collect + verdict
│   │   ├── collectors/
│   │   │   ├── carla_collector.py            ← Lấy data từ CARLA actors
│   │   │   └── ros2_collector.py             ← Lấy data từ ROS2 topics
│   │   ├── metrics/
│   │   │   ├── jerk.py                       ← Jerk metric (stateful)
│   │   │   └── ttc.py                        ← Time-To-Collision metric
│   │   └── profiles/
│   │       └── acc_follow.yaml               ← KPI threshold profile cho ACC
│   ├── report/
│   │   └── excel_reporter.py                 ← Sinh báo cáo Excel từ KPIEngine
│   ├── runner/
│   │   └── adas_sil_runner.py                ← SIL runner stub (WIP)
│   ├── sim/
│   │   └── carla_0_9_16.yaml                 ← Simulator config (sync, traffic)
│   └── sut/
│       ├── sut_base.yaml                     ← Base SUT config template
│       └── oem_like_autoware.yaml            ← Autoware-based SUT profile
│
├── scenario_runner/
│   ├── scenario_runner.py                    ← Entrypoint chính của ScenarioRunner
│   └── srunner/
│       ├── scenariomanager/
│       │   ├── urban_traffic_manager.py      ← Background TV spawner (custom)
│       │   └── ...
│       ├── scenarios/
│       ├── tools/
│       └── ...
│
├── tools/
│   ├── project_paths.py                      ← Portable path resolver
│   ├── start_carla.py                        ← CARLA server launcher
│   ├── run_batch.py                          ← GUI entrypoint
│   ├── config/
│   │   ├── camera.py                         ← Spectator birdview camera
│   │   ├── hud.py                            ← Real-time pygame HUD (34KB)
│   │   ├── KPI.py                            ← Standalone KPI monitor
│   │   └── maps_CARLA/OpenDrive/             ← 16 XODR map files
│   └── GUI/
│       ├── gui_runner.py                     ← Tkinter 4-panel GUI
│       ├── batch_runner.py                   ← Batch orchestrator
│       ├── process_manager.py                ← Process lifecycle manager
│       └── report_writer.py                  ← Excel writer
│
├── report/                                   ← [OUTPUT] Tự động tạo khi chạy
│   ├── <case_id>/report.xlsx
│   └── batch_<timestamp>/summary.xlsx
│
├── specifications/
│   ├── Test Requirements.xlsx
│   └── Test Scenarios.xlsx
│
├── docs/
│   └── path_structure.md
│
├── pyproject.toml
├── requirements.txt
└── .gitignore
```

---

## 6. Mô tả chi tiết từng Folder

### 6.1 `scenarios/general_scenarios/`

Toàn bộ dữ liệu kịch bản được tổ chức theo cấp bậc:

```
<feature_domain_dir> / <functional> / <scenario_id> / <case_file>
```

CLI selector dùng tên ngắn (ví dụ `longitudinal/acc/acc_csc_001`), script tự resolve thành `longitudinal_feature/ACC/acc_csc_001`.

| Sub-folder | Vai trò | Người tạo |
|---|---|---|
| `logical/` | Định nghĩa khái niệm scenario: actors, maneuvers, điều kiện trigger | Dev / Test Engineer |
| `parameters/` | Không gian tham số: tốc độ, khoảng cách, thời tiết, v.v. | Dev / Test Engineer |
| `core/` | Kết quả expand: mỗi file = 1 test case cụ thể | Auto (expander.py) |
| `generated/carla/` | File XOSC có thể chạy ngay trên CARLA | Auto (adapters) |
| `templates/` | XML template tái sử dụng cho storyboard và maneuver blocks | Dev |

**Ví dụ acc_csc_006 (TV2 cut-in):**
```
logical/.../ACC/acc_csc_006.yaml         → Định nghĩa: FL mode cut-in, 3 actors (ev, tv1, tv2)
parameters/.../ACC/acc_csc_006.yaml      → 24 combinations (speed × distance × timing)
core/.../ACC/acc_csc_006/
    acc_csc_006_001.yaml                 → case 1: speed=30kph, dist=20m, timing=T1
    acc_csc_006_002.yaml                 → case 2: speed=30kph, dist=25m, timing=T1
    ...
    acc_csc_006_024.yaml                 → case 24: speed=50kph, dist=35m, timing=T3
generated/carla/.../ACC/acc_csc_006/
    acc_csc_006_001.xosc ... 024.xosc   → OpenSCENARIO executables
```

---

### 6.2 `expander/`

Công cụ sinh Core YAML từ Logical + Parameters.

**`expander.py` làm gì:**
1. Load `logical/<domain>/<fn>/<scenario_id>.yaml` — đọc actors, maneuvers, conditions
2. Load `parameters/<domain>/<fn>/<scenario_id>.yaml` — đọc danh sách parameter combinations
3. Validate constraints (ví dụ: `ev_speed < tv_speed`, `distance > 10`)
4. Sinh từng file `core/<domain>/<fn>/<scenario_id>/<case_id>.yaml` với giá trị cụ thể

**Cấu trúc logical YAML (bắt buộc):**
```yaml
scenario_id:    acc_csc_006
functional:     ACC
feature_domain: Longitudinal
actors:
  - role: ev
  - role: tv1
  - role: tv2
maneuvers:
  - cutin_event: {actor: tv2, ...}
```

**Cấu trúc parameters YAML:**
```yaml
combinations:
  - ev_speed: 30.0
    tv1_speed: 25.0
    cutin_distance: 20.0
    ...
  - ev_speed: 40.0
    ...
constraints:
  - "ev_speed > tv1_speed"   # giữ nguyên ACC free-flow
```

---

### 6.3 `adapters/carla/`

Chuyển đổi Core YAML → CARLA OpenSCENARIO (.xosc).

**`_generated_common.py`** — engine chính, dùng chung cho tất cả features:
- `load_core_cases()`: quét core YAML folder
- `discover_maneuver_blocks()`: load XML blocks từ `templates/maneuver_blocks/`
- `load_storyboard_template()`: load base storyboard từ `templates/storyboard/`
- `build_xosc()`: assemble XML hoàn chỉnh (Entities + Storyboard + Init)
- `inject_controller_defaults()`: gắn FMU controller params vào XOSC

**Domain wrappers** (mỗi cái chỉ scan template của domain mình):
- `longitudinal_feature/generated.py` → ACC, HWA
- `lateral_feature/generated.py` → LKA
- `brake_feature/generated.py` → AEB, RAEB

**`generated_wrapper.py`** — compatibility wrapper, hỗ trợ lệnh cũ `generated_wrapper.py --all`.

---

### 6.4 `config/`

Tất cả cấu hình runtime của controllers và background traffic.

#### `config/controllers_fmu/<domain>/<fn>/`

Mỗi feature có đầy đủ 5 files:

| File | Mô tả |
|---|---|
| `*Controller.py` | Logic điều khiển — implement `Fmi2Slave.do_step()`, tính throttle/brake/steer |
| `*_fmu_controller.py` | BasicControl adapter — kết nối ScenarioRunner ↔ FMU runtime |
| `fmu_adapter.py` | Signal bridge — lấy signals từ CARLA world, đưa vào FMU, nhận output |
| `signals.yaml` | Khai báo tất cả I/O signals + default parameters + source mapping |
| `*.fmu` | Binary FMU compiled từ `*Controller.py` (pythonfmu build) |

**Signal flow mỗi tick:**
```
CARLA ego/target actors
  → fmu_adapter.sample(waypoints)      # lấy speed, distance, heading_error, v.v.
  → ACCParameters.as_fmu_inputs()      # merge controller params
  → fmu_runtime.step(inputs, dt)       # gọi FMU.do_step()
  → control_from_fmu_output(result)    # parse throttle/brake/steer
  → vehicle.apply_control(control)     # áp lên EV
```

**ACC Controller params (signals.yaml):**

| Param | Giá trị | Ý nghĩa |
|---|---|---|
| `time_gap` | 2.2 s | Khoảng cách thời gian an toàn |
| `min_distance` | 8.0 m | Khoảng cách tối thiểu tuyệt đối |
| `kp_speed` | 0.20 | P-gain điều khiển tốc độ |
| `max_brake` | 0.45 | Lực phanh tối đa (sau khi tune) |
| `max_throttle` | 0.75 | Ga tối đa |

#### `config/traffic/<domain>/<fn>/`

Per-feature traffic profiles — mỗi feature có cài đặt traffic riêng:

| Profile | Đặc trưng |
|---|---|
| `acc_traffic.yaml` | 20 TVs, mọi lane trừ EV, spacing 20m, following distance 8m, collision avoidance |
| `lka_traffic.yaml` | Oncoming traffic (opposite heading), avoid junction spawn, 22–32 kph |
| `aeb_traffic.yaml` | Tốc độ thấp 5–15 kph, spawn range ngắn ≤60m, mật độ cao |
| `urban_traffic.yaml` | Base fallback — dùng khi không có profile riêng |

---

### 6.5 `adas_sil_execution/`

Framework đánh giá KPI và xuất báo cáo. Hoạt động độc lập với ScenarioRunner.

#### `kpi/engine/kpi_engine.py` — `KPIEngine`
- `push_sample(sample)`: nhận data point từ collector mỗi tick
- `_process_sample()`: tính jerk, TTC, track min_distance
- `_check_violations()`: so sánh với thresholds trong profile
- `verdict()`: trả về PASS/FAIL + danh sách violations
- `summary()`: xuất dict đầy đủ cho report

#### `kpi/collectors/`
- `carla_collector.py`: kết nối CARLA 127.0.0.1:2000, lấy ego/target speed + distance, attach collision sensor
- `ros2_collector.py`: subscribe ROS2 topics `/localization/kinematic_state`, `/control/command/control_cmd`

#### `kpi/metrics/`
- `jerk.py`: tính jerk từ acceleration signal (stateful — cần reset() giữa các scenarios)
- `ttc.py`: TTC = distance / relative_speed; clip ở max_ttc=100.0s khi relative_speed≈0

#### `kpi/profiles/acc_follow.yaml`
```yaml
thresholds:
  min_distance_m: 2.0
  min_ttc_s: 1.5
  max_jerk_mps3: 3.0
verdict:
  collision: fail
  ttc_violation: fail
```

#### `report/excel_reporter.py`
- Nhận `results` dict từ KPIEngine
- Sinh file Excel với sheets: Summary, Test_Overview, KPI_Summary, Violations, Timeline_<id>

#### `sim/carla_0_9_16.yaml`
```yaml
simulator:
  name: CARLA
  version: 0.9.16
  timeout_s: 30.0
  sync: true
  fixed_delta_seconds: 0.05
  traffic:
    enabled: true
    config: config/traffic/urban_traffic.yaml
    profile: urban_acc_aeb
```

#### `interface/signal_mapping.yaml`
Ánh xạ tên signal giữa SUT output và KPI engine input — cho phép swap SUT mà không cần sửa KPI code.

---

### 6.6 `tools/`

Tất cả công cụ runtime: launcher, visualization, GUI, reporting.

#### `tools/project_paths.py`
- `ProjectPaths` dataclass: resolve tất cả đường dẫn quan trọng
- Ưu tiên env vars → tự tìm root bằng marker (`pyproject.toml`, `scenarios/`)
- `build_subprocess_env()`: build PYTHONPATH cho subprocess (thêm CARLA .egg)
- Dùng xuyên suốt tất cả tools — **không hardcode path ở nơi khác**

#### `tools/start_carla.py`
```powershell
python tools\start_carla.py --quality-level Low --windowed --resx 1280 --resy 720
```

#### `tools/config/camera.py`
- Tự tìm vehicle `role_name="ev"`, set spectator ở 32m phía trên, pitch -55°
- Exponential smoothing α=0.12 — camera theo mượt không giật
- 20 Hz

#### `tools/config/hud.py` (34KB)
Real-time pygame HUD — hiển thị:

| Panel | Data |
|---|---|
| Camera | Video từ camera gắn EV |
| Server | FPS, simulation time, map |
| Ego state | Speed, heading, lane offset |
| Control | Throttle / Brake / Steer bars |
| ADAS | ACC: target_speed, time_gap, safe_distance / AEB: TTC / LKA: lane_offset, state |
| Nearby TVs | Distance list |

Switch feature: **F2** (ACC → AEB → LKA → ACC)

#### `tools/config/KPI.py` — `KPIMonitor`
- Attach collision sensor lên EV
- Track: min_distance (center-to-center trừ bounding box), collision flag, speed range
- `run_monitor(duration=30)`: chạy ở 20Hz trong `duration` giây
- Output: `{result: PASS/FAIL, fail_reason, fail_time, min_distance, ...}`
- **FAIL** nếu: collision hoặc distance < 6.0m

#### `tools/GUI/process_manager.py` — `ProcessManager`
Quản lý toàn bộ subprocess trong một batch execution:

| Subprocess | Khi nào |
|---|---|
| `camera.py` | Start trước mỗi scenario, reuse nếu đang chạy |
| `hud.py --feature ACC` | Start trước, feature auto-detect từ xosc path |
| `scenario_runner.py` | Start cho mỗi test case |

Lệnh scenario_runner được build tự động:
```
python scenario_runner.py
  --openscenario <xosc_path>
  --reloadWorld
  --sync --frameRate 20
  --urbanTraffic
  --urbanTrafficConfig config/traffic/<feature>/<fn>/<fn>_traffic.yaml
  --urbanTrafficProfile <profile_name>
```

Traffic config được resolve theo hierarchy:
1. `adas_sil_execution/sim/<feature>/<fn>/carla_0_9_16.yaml` → lấy `traffic.config`
2. Fallback: `config/traffic/urban_traffic.yaml`

#### `tools/GUI/batch_runner.py` — `BatchRunner`
Flow mỗi job:
```
discover_jobs() → start_camera() → start_hud()
→ [for each xosc]:
    run_scenario() → monitor_kpi(timeout) → detect_result()
    → write_per_case_report() → reload_carla_world()
→ write_batch_summary()
```

Kết quả có thể là: `PASS` / `FAIL` / `STOPPED` / `TIMEOUT`

#### `tools/GUI/gui_runner.py` — `BatchRunnerGUI`
4-panel tree: **Feature Domain → Function → Scenario Group → Individual Case**
Modes: Single case / Single folder / Multi folder / All folders

#### `tools/GUI/report_writer.py` — `ReportWriter`
Excel sheets:
- `Summary`: total, passed, failed, stopped, pass rate %
- `All Cases`: tất cả kết quả
- `Failed Cases`: filter FAIL + STOPPED + TIMEOUT

Columns: `case_id · result · fail_reason · fail_time · min_distance · max_speed · min_speed · elapsed_s`

---

## 7. Execution Loop — A-Z Connection

Sơ đồ kết nối chi tiết từ file đầu tiên đến report cuối cùng:

```
[1] Engineer viết/sửa:
    scenarios/general_scenarios/logical/longitudinal_feature/ACC/acc_csc_006.yaml
    scenarios/general_scenarios/parameters/longitudinal_feature/ACC/acc_csc_006.yaml

         │
         ▼  python expander\expander.py longitudinal/acc/acc_csc_006 --clean
         │
         │  expander.py
         │    load_yaml(logical)  +  load_yaml(parameters)
         │    validate_constraints(combination)
         │    render template → write core YAML

[2] Output: scenarios/general_scenarios/core/longitudinal_feature/ACC/acc_csc_006/
            acc_csc_006_001.yaml  ...  acc_csc_006_024.yaml

         │
         ▼  python adapters\carla\longitudinal_feature\generated.py longitudinal/acc/acc_csc_006 --clean
         │
         │  _generated_common.py
         │    load_core_cases(core_dir)
         │    load_storyboard_template(templates/storyboard/longitudinal_feature/)
         │    discover_maneuver_blocks(templates/maneuver_blocks/longitudinal_feature/)
         │    inject_controller_defaults(CONTROLLER_DEFAULTS)  ← từ signals.yaml
         │    build_xosc(entities + init + storyboard)
         │    write → .xosc

[3] Output: scenarios/general_scenarios/generated/carla/longitudinal_feature/ACC/acc_csc_006/
            acc_csc_006_001.xosc  ...  acc_csc_006_024.xosc

         │
         ▼  python tools\run_batch.py  (GUI)
         │  Chọn "longitudinal_feature/ACC/acc_csc_006" → Start
         │
         │  ProcessManager.run_scenario(xosc_path)
         │    ├── start camera.py  (birdview, 20Hz)
         │    ├── start hud.py --feature ACC  (pygame, 30FPS)
         │    └── start scenario_runner.py \
         │            --openscenario acc_csc_006_001.xosc \
         │            --reloadWorld --sync --frameRate 20 \
         │            --urbanTraffic --urbanTrafficConfig config/traffic/longitudinal_feature/ACC/acc_traffic.yaml
         │
         │  Trong scenario_runner.py:
         │    CARLA world load + spawn actors (ev, tv1, tv2)
         │    AccFmuController.run_step() mỗi tick:
         │      fmu_adapter.sample() → ACCFmuRuntime.step() → apply_control(ev)
         │    UrbanTrafficManager.start() → spawn 20 background TVs
         │    UrbanTrafficManager.tick() → keepalive TM autopilot
         │
         │  Đồng thời: KPIMonitor.run_monitor(duration=30)
         │    → collision_sensor.listen()
         │    → measure distance (center-to-center − bounding_box)
         │    → detect: distance < 6m  OR  collision → FAIL

[4] Per-case result → report_writer.write_case_report()
    Output: report/acc_csc_006_001/report.xlsx

[5] Sau khi chạy hết batch:
    report_writer.write_batch_summary()
    Output: report/batch_20260522_143022/summary.xlsx
            Sheets: Summary | All Cases | Failed Cases
```

---

## 8. Installation — Từ A đến Z

### Bước 1: Cài Python

```powershell
# Kiểm tra version
python --version   # Cần 3.8, 3.9 hoặc 3.10

# Nếu chưa có, tải từ python.org, chọn đúng bit với CARLA wheel
```

### Bước 2: Clone / Unzip repo

```powershell
cd C:\Self_Improvement\FA_VnV
# Repo đã có sẵn tại Test_assets_v1.4\
cd Test_assets_v1.4
```

### Bước 3: Tạo virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate

# Verify
python -c "import sys; print(sys.prefix)"
```

### Bước 4: Cài CARLA Python API

```powershell
# Tìm file .whl khớp với Python version của bạn
# Ví dụ Python 3.10 → carla-0.9.16-cp310-cp310-win_amd64.whl

pip install C:\Self_Improvement\FA_VnV\CARLA_0.9.16\PythonAPI\carla\dist\carla-0.9.16-cp310-cp310-win_amd64.whl

# Verify
python -c "import carla; print('carla', carla.__version__)"
```

### Bước 5: Cài dependencies

```powershell
pip install -r requirements.txt

# Verify
python -c "import yaml, pandas, openpyxl, pygame, pythonfmu; print('all deps ok')"
```

### Bước 6: Cài đặt biến môi trường (optional nhưng khuyến nghị)

```powershell
# Thêm vào PowerShell profile ($PROFILE) hoặc .env
$env:FA_VNV_WORKSPACE_ROOT = "C:\Self_Improvement\FA_VnV"
$env:TEST_ASSETS_ROOT      = "$env:FA_VNV_WORKSPACE_ROOT\Test_assets_v1.4"
$env:CARLA_ROOT            = "$env:FA_VNV_WORKSPACE_ROOT\CARLA_0.9.16"
```

---

## 9. Startup Guide — Case by Case

### Case A: Chạy 1 scenario đơn lẻ (debug)

```powershell
# Terminal 1 — CARLA server
cd C:\Self_Improvement\FA_VnV\CARLA_0.9.16
.\CarlaUE4.exe -quality-level=Low -windowed -ResX=1280 -ResY=720

# Terminal 2 — (optional) camera
cd C:\Self_Improvement\FA_VnV\Test_assets_v1.4
python tools\config\camera.py

# Terminal 3 — (optional) HUD
python tools\config\hud.py --feature ACC

# Terminal 4 — chạy scenario
python scenario_runner\scenario_runner.py \
  --openscenario scenarios\general_scenarios\generated\carla\longitudinal_feature\ACC\acc_csc_006\acc_csc_006_001.xosc \
  --reloadWorld
```

### Case B: Chạy 1 scenario với urban traffic (realistic)

```powershell
python scenario_runner\scenario_runner.py \
  --openscenario scenarios\general_scenarios\generated\carla\longitudinal_feature\ACC\acc_csc_006\acc_csc_006_001.xosc \
  --reloadWorld --sync --frameRate 20 \
  --urbanTraffic \
  --urbanTrafficConfig config\traffic\longitudinal_feature\ACC\acc_traffic.yaml \
  --urbanTrafficProfile urban_acc_aeb
```

### Case C: Expand + Generate + chạy 1 scenario mới (end-to-end 1 case)

```powershell
# Expand
python expander\expander.py longitudinal/acc/acc_csc_006 --clean

# Generate XOSC
python adapters\carla\longitudinal_feature\generated.py longitudinal/acc/acc_csc_006 --clean

# Verify xosc exists
ls scenarios\general_scenarios\generated\carla\longitudinal_feature\ACC\acc_csc_006\

# Chạy case đầu tiên
python scenario_runner\scenario_runner.py \
  --openscenario scenarios\general_scenarios\generated\carla\longitudinal_feature\ACC\acc_csc_006\acc_csc_006_001.xosc \
  --reloadWorld
```

### Case D: Batch run toàn bộ ACC (GUI)

```powershell
# Terminal 1 — CARLA (để chạy)
.\CarlaUE4.exe -quality-level=Low -windowed

# Terminal 2 — GUI
cd C:\Self_Improvement\FA_VnV\Test_assets_v1.4
python tools\run_batch.py
# GUI tự khởi động camera + HUD cho mỗi scenario
```

GUI: Chọn domain `Longitudinal` → `ACC` → chọn scenario group → `Start`

### Case E: Expand + Generate tất cả + Batch run toàn bộ

```powershell
# Expand tất cả
python expander\expander.py --all --clean

# Generate tất cả (chạy từng domain)
python adapters\carla\longitudinal_feature\generated.py --all --clean
python adapters\carla\lateral_feature\generated.py --all --clean
python adapters\carla\brake_feature\generated.py --all --clean

# Batch run
python tools\run_batch.py
# GUI: chọn "All folders" → Start
```

### Case F: Generate lại sau khi sửa template (không cần re-expand)

```powershell
# Chỉ re-generate XOSC, giữ nguyên core YAML
python adapters\carla\longitudinal_feature\generated.py longitudinal/acc/acc_csc_006 --clean
```

### Case G: Xem report sau batch

```powershell
# Report được tự động tạo tại:
explorer report\batch_<timestamp>\summary.xlsx
```

### Case H: Chạy với LKA traffic profile

```powershell
python scenario_runner\scenario_runner.py \
  --openscenario scenarios\general_scenarios\generated\carla\lateral_feature\LKA\lka_csc_001\lka_csc_001_001.xosc \
  --reloadWorld --sync --frameRate 20 \
  --urbanTraffic \
  --urbanTrafficConfig config\traffic\lateral_feature\LKA\lka_traffic.yaml \
  --urbanTrafficProfile urban_acc_aeb
```

---

## 10. Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'carla'` | Chưa cài CARLA wheel hoặc sai Python version | Cài đúng .whl, kiểm tra `python --version` |
| `Connection refused port 2000` | CARLA chưa khởi động hoặc đang load | Đợi CARLA load xong, thử `telnet localhost 2000` |
| Scenario không spawn vehicles | XOSC thiếu `ScenarioObject` với đúng `role_name` | Check XOSC, re-generate |
| GUI không hiện cases | Không tìm thấy .xosc files | Chạy step Generate, click `Refresh` trong GUI |
| HUD hiện 0 cho tất cả | ScenarioRunner chưa spawn actors | Kiểm tra role_name = "ev" / "tv1" trong XOSC |
| `KeyError: 'thresholds'` trong KPI | Profile YAML dùng key `metrics:` thay vì `thresholds:` | Sửa `acc_follow.yaml`: đổi `metrics:` → `thresholds:` |
| Excel report không lưu được | File đang mở trong Excel | Đóng Excel, report_writer sẽ tạo backup tự động |
| FMU không load | .fmu binary lỗi hoặc sai Python version | Rebuild: `pythonfmu build -f ACCController.py` |
| Background TVs va chạm nhau | `collision_avoidance_enabled: false` | Bật trong traffic YAML + implement code (xem WS2 plan) |

---

## 11. Maintenance Notes

### Git workflow

```powershell
git status --short   # Kiểm tra trước khi commit

# Generated files rất lớn — KHÔNG commit toàn bộ generated/
# Chỉ commit khi thay đổi templates hoặc core logic
git add scenarios\general_scenarios\logical\
git add scenarios\general_scenarios\parameters\
git add adapters\ config\ tools\ expander\
git commit -m "feat: add acc_csc_023 scenario"
```

### Rebuild FMU sau khi sửa controller

```powershell
cd config\controllers_fmu\longitudinal_feature\ACC
pythonfmu build -f ACCController.py
# Output: ACCController.fmu (ghi đè file cũ)
# Copy sang ACC_controller.fmu nếu cần đổi tên
```

### Sync signals.yaml sau khi tune controller

Bất cứ khi nào sửa `ACCController.py` defaults, cần sync `signals.yaml`:
- `time_gap` trong `ACCController.__init__` ↔ `parameters.time_gap` trong `signals.yaml`
- Nếu không sync → FMU và adapter dùng khác nhau → behavior khác nhau giữa FMU và Python controller

### Clean generated files

```powershell
# Xóa core YAML của 1 scenario
python expander\expander.py longitudinal/acc/acc_csc_006 --clean
# (--clean rename thư mục cũ thành .trash_*, không xóa cứng)

# Xóa .trash_ folders thủ công
Remove-Item -Recurse -Force scenarios\general_scenarios\core\longitudinal_feature\ACC\.trash_*
Remove-Item -Recurse -Force scenarios\general_scenarios\generated\carla\longitudinal_feature\ACC\.trash_*
```

### Thêm feature mới

1. Tạo `scenarios/general_scenarios/logical/<new_domain>/<Fn>/` + logical YAML
2. Tạo `scenarios/general_scenarios/parameters/<new_domain>/<Fn>/` + params YAML
3. Tạo `templates/storyboard/<new_domain>/` + `templates/maneuver_blocks/<new_domain>/`
4. Tạo `adapters/carla/<new_domain>/generated.py` (copy từ longitudinal_feature)
5. Tạo `config/controllers_fmu/<new_domain>/<Fn>/` với đủ 5 files
6. Tạo `config/traffic/<new_domain>/<Fn>/<fn>_traffic.yaml`
7. Chạy `expander.py` + `generated.py` → kiểm tra XOSC

---

## 12. Định hướng phát triển (Roadmap)

Chi tiết trong [`PLAN_acc_smooth_traffic_refactor.md`](PLAN_acc_smooth_traffic_refactor.md).

### P1 — ACC CSC-006: Fix jerky control khi TV2 cut-in (CRITICAL)

**Vấn đề:** `ACCController.py:do_step()` không có rate-limiter → step-change target speed → full brake ngay lập tức khi TV2 cutin.

**Fix:**
- Thêm `_prev_target_speed` + rate-limiter (max 2.0 m/s/s)
- Thêm distance_error deadband ±1.0m
- Tune: `kp_speed` 0.35→0.20, `max_brake` 0.65→0.45, `time_gap` 1.8→2.2 (signals.yaml)
- Rebuild `.fmu` sau khi sửa

### P2 — TV-Background: Collision Avoidance (HIGH)

**Vấn đề:** `_run_lane_follow_step()` không implement `collision_avoidance_enabled` (đã có trong YAML nhưng Python bỏ qua).

**Fix:**
- Thêm `_forward_vehicle_distance(vehicle)`: scan actors phía trước trong lateral window 3.2m
- Inject check vào `_run_lane_follow_step()`: brake nếu dist < 12m, slow nếu dist < 26m

### P3 — Traffic Config: Tách theo Feature Domain (MEDIUM)

**Hiện tại:** Một `urban_traffic.yaml` dùng cho tất cả.  
**Mục tiêu:** Per-feature profiles đã tạo, cần wire vào runner:
- `process_manager.py`: resolve traffic config từ xosc path
- `scenario_runner.py`: thêm `_resolve_traffic_config()` auto-detect từ `<feature>/<fn>` trong path

### P4 — Thêm HWA + RAEB scenarios (MEDIUM)

- `config/traffic/longitudinal_feature/HWA/hwa_traffic.yaml` đã có (placeholder)
- Cần: logical YAML, parameters YAML, templates, controller

### P5 — KPI Engine: Fix profile key mismatch (LOW — nhưng cần fix sớm)

`acc_follow.yaml` dùng key `metrics:` nhưng `kpi_engine.py` expect `thresholds:` → KeyError khi chạy.  
Fix: đổi YAML key thành `thresholds:`.

### P6 — Logging Framework (LOW)

Thay toàn bộ `print()` bằng `logging` module với levels và file output.

### P7 — CI/CD Integration (FUTURE)

- Script tự động chạy batch sau khi merge
- Compare KPI metrics giữa các versions
- Gate: fail nếu pass rate < 95%

---

## 13. Quick Reference

| Lệnh | Mục đích |
|---|---|
| `python expander\expander.py longitudinal/acc/acc_csc_001 --clean` | Expand 1 scenario |
| `python expander\expander.py longitudinal/acc --clean` | Expand toàn bộ ACC |
| `python expander\expander.py --all --clean` | Expand tất cả |
| `python adapters\carla\longitudinal_feature\generated.py longitudinal/acc/acc_csc_001 --clean` | Generate XOSC |
| `python adapters\carla\longitudinal_feature\generated.py --all --clean` | Generate tất cả ACC |
| `python tools\run_batch.py` | Mở GUI batch runner |
| `python tools\config\camera.py` | Birdview camera |
| `python tools\config\hud.py --feature ACC` | HUD |
| `python tools\start_carla.py` | Khởi động CARLA |

| Metric | File | Default |
|---|---|---|
| Min safe distance | `tools/config/KPI.py` | 6.0 m |
| Time gap (ACC) | `config/controllers_fmu/.../signals.yaml` | 2.2 s |
| Max brake (ACC) | `config/controllers_fmu/.../signals.yaml` | 0.45 |
| Background TVs | `config/traffic/*/acc_traffic.yaml` | 20 vehicles |
| Simulation step | `adas_sil_execution/sim/carla_0_9_16.yaml` | 0.05 s (20 Hz) |

---
