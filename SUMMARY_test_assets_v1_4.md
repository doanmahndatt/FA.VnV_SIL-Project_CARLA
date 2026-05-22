# FA_VnV — Test Assets v1.4 · Summary Report

> **Mục đích:** Tóm tắt hiện trạng test asset để gửi tham khảo xây dựng AI tool & báo cáo nội bộ.
> **Ngày:** 2026-05-22 · **Phiên bản:** v1.4 · **Simulator:** CARLA 0.9.16

---

## 1. Tổng quan dự án

Bộ test asset FA_VnV v1.4 là framework SIL (Software-in-the-Loop) dùng để sinh, thực thi và đánh giá tự động các kịch bản kiểm thử tính năng ADAS (ACC, AEB, LKA) trên simulator CARLA. Kịch bản được định nghĩa theo chuẩn OpenSCENARIO, controller được đóng gói theo chuẩn FMI 2.0 (FMU), kết quả được xuất tự động ra báo cáo Excel.

**Kiến trúc 3 tầng:**
```
Logical YAML + Parameters  →  Core YAML (expanded)  →  XOSC (executable)
        [define]                   [parameterize]           [run on CARLA]
```

---

## 2. Thống kê Test Cases

### 2.1 Tổng hợp theo Feature Domain

| Feature Domain | Function | # Scenario ID | # Core YAML (Test Cases) | # Executable Scripts (.xosc) |
|---|:---:|:---:|:---:|:---:|
| Brake Feature | AEB | 4 | 102 | 102 |
| Lateral Feature | LKA | 1 | 1 | 1 |
| Longitudinal Feature | ACC | 22 | 2,220 | 2,220 |
| **TỔNG CỘNG** | | **27** | **2,323** | **2,323** |

> **Ghi chú:** Mỗi Core YAML tương ứng 1:1 với 1 file .xosc executable. Tổng 2,323 test scripts đã sẵn sàng chạy trên CARLA.

---

### 2.2 Chi tiết theo Scenario ID

#### Brake Feature / AEB (Automatic Emergency Braking)

| Scenario ID | Mô tả ngắn | # Test Cases |
|---|---|:---:|
| aeb_csc_001 | AEB activation — leading vehicle stationary | 30 |
| aeb_csc_003 | AEB activation — leading vehicle decelerating | 18 |
| aeb_csc_005 | AEB activation — crossing pedestrian / cyclist | 36 |
| aeb_csc_007 | AEB deactivation conditions | 18 |
| **Subtotal AEB** | | **102** |

#### Lateral Feature / LKA (Lane Keeping Assist)

| Scenario ID | Mô tả ngắn | # Test Cases |
|---|---|:---:|
| lka_csc_001 | LKA lane-keeping with oncoming traffic | 1 |
| **Subtotal LKA** | | **1** |

#### Longitudinal Feature / ACC (Adaptive Cruise Control)

| Scenario ID | Mô tả ngắn | # Test Cases |
|---|---|:---:|
| acc_csc_001 | ACC Free-flow — no lead vehicle | 24 |
| acc_csc_002 | ACC Follow mode — steady-state following | 36 |
| acc_csc_003 | ACC Follow — lead vehicle decelerating | 48 |
| acc_csc_004 | ACC Follow — lead vehicle accelerating | 48 |
| acc_csc_005 | ACC Follow — lead vehicle stopping | 24 |
| acc_csc_006 | ACC Follow — TV2 cut-in from adjacent lane | 24 |
| acc_csc_007 | ACC Follow — multiple speed variation combinations | 216 |
| acc_csc_008 | ACC Follow — ego speed × lead speed matrix | 192 |
| acc_csc_009 | ACC Follow — distance error sweep | 192 |
| acc_csc_010 | ACC Follow — time gap variation | 144 |
| acc_csc_011 | ACC Follow — min distance variation | 144 |
| acc_csc_012 | ACC Cut-in — from right lane | 72 |
| acc_csc_013 | ACC Cut-in — from left lane | 72 |
| acc_csc_014 | ACC Cut-out — lead vehicle changes lane right | 192 |
| acc_csc_015 | ACC Cut-out — lead vehicle changes lane left | 192 |
| acc_csc_016 | ACC Merge — entering highway | 144 |
| acc_csc_017 | ACC Deceleration — lead vehicle hard brake | 144 |
| acc_csc_018 | ACC Standstill — go-and-stop traffic | 48 |
| acc_csc_019 | ACC Standstill — resume from stop | 48 |
| acc_csc_020 | ACC Target speed change — driver override | 12 |
| acc_csc_021 | ACC Edge cases — sensor noise / gap variation | 96 |
| acc_csc_022 | ACC Combined — multi-actor scenarios | 108 |
| **Subtotal ACC** | | **2,220** |

---

### 2.3 Controller Coverage

| Feature Domain | Function | Loại Controller | Binary | Inputs | Outputs | Params chính |
|---|---|---|---|:---:|:---:|---|
| Brake | AEB | FMU — FMI 2.0 CoSim | `AEB_controller.fmu` | 17 | 8 | ttc_brake=1.5s, ttc_emergency=0.8s, max_brake=1.0 |
| Lateral | LKA | FMU — FMI 2.0 CoSim | `LKA_controller.fmu` | 11 | 4 | activation_offset=0.20m, deadband=0.05m, kp_offset=0.11 |
| Longitudinal | ACC | FMU — FMI 2.0 CoSim | `ACC_controller.fmu` | 12 | 9 | time_gap=2.2s, min_dist=8m, kp_speed=0.20, max_brake=0.45 |

> Controller được compile từ Python sang .fmu — plug-and-play với bất kỳ FMI-compliant simulator nào (CARLA, CarMaker, IPG...).

---

### 2.4 Định nghĩa Logical & Parameters

| Loại file | Số lượng | Vị trí |
|---|:---:|---|
| Logical YAML (định nghĩa kịch bản) | 27 | `scenarios/general_scenarios/logical/` |
| Parameter YAML (không gian tham số) | 27 | `scenarios/general_scenarios/parameters/` |
| Core YAML (test case đã expand) | 2,323 | `scenarios/general_scenarios/core/` |
| XOSC executable | 2,323 | `scenarios/general_scenarios/generated/carla/` |

---

## 3. Mô tả `config/` — Controller & Traffic Configuration

```
config/
├── controllers_fmu/          ← FMU-based closed-loop controllers
│   ├── brake_feature/AEB/    ← AEB: controller + FMI adapter + signals.yaml + .fmu
│   ├── lateral_feature/LKA/  ← LKA: controller + FMI adapter + signals.yaml + .fmu
│   └── longitudinal_feature/ACC/ ← ACC: controller + FMI adapter + signals.yaml + .fmu
├── controllers_py/           ← Python reference controllers (fallback/debug)
│   └── longitudinal_feature/ACC/ACC_controller.py
└── traffic/                  ← Background traffic profiles (per feature)
    ├── urban_traffic.yaml            ← base profile (fallback)
    ├── longitudinal_feature/ACC/     ← acc_traffic.yaml
    ├── lateral_feature/LKA/          ← lka_traffic.yaml
    ├── brake_feature/AEB/            ← aeb_traffic.yaml
    ├── brake_feature/RAEB/           ← raeb_traffic.yaml
    └── longitudinal_feature/HWA/     ← hwa_traffic.yaml
```

### 3.1 `config/controllers_fmu/` — FMU Controllers

Mỗi feature domain chứa một bộ 4 file:

| File | Vai trò |
|---|---|
| `ACCController.py` (hoặc AEB/LKA) | Logic điều khiển core — implement FMI2 Slave interface, chứa `do_step()` |
| `fmu_adapter.py` | Bridge giữa CARLA world và FMU: lấy signals từ simulator, đẩy vào FMU, lấy output áp vào xe |
| `signals.yaml` | Khai báo toàn bộ I/O signals, mapping nguồn dữ liệu (CARLA sensor / scenario param / controller param) |
| `*.fmu` | Binary FMU được compile từ `ACCController.py` bằng `pythonfmu` — có thể dùng với bất kỳ simulator FMI-compliant |

**Luồng hoạt động mỗi simulation step (0.05s):**
```
CARLA World → fmu_adapter (sample signals) → FMU.do_step() → fmu_adapter (parse output) → vehicle.apply_control()
```

**Ví dụ: ACC Controller logic (`ACCController.py:do_step`):**
- Tính `safe_distance = max(min_dist, ego_speed × time_gap)`
- Tính `distance_error = lead_distance − safe_distance`
- Rate-limit `acc_target_speed` để tránh phanh gấp khi TV cutin
- Output `throttle` / `brake` trong giới hạn `max_throttle` / `max_brake`

### 3.2 `config/controllers_py/` — Python Reference Controllers

Controller thuần Python không cần FMU toolchain — dùng để debug nhanh hoặc so sánh với FMU version. Hiện có ACC reference controller, sử dụng cùng logic với FMU nhưng chạy trực tiếp trong ScenarioRunner.

### 3.3 `config/traffic/` — Background Traffic Profiles

Mỗi feature có profile traffic riêng, tối ưu cho kịch bản test tương ứng:

| Profile | Đặc điểm nổi bật |
|---|---|
| `acc_traffic.yaml` | 20 TVs, spawn mọi lane trừ lane EV, spacing 20m, following distance 8m, collision avoidance enabled |
| `lka_traffic.yaml` | Oncoming traffic (opposite heading), avoid junction spawn, speed 22–32 kph |
| `aeb_traffic.yaml` | Tốc độ thấp 5–15 kph, spawn range ngắn, mật độ cao xung quanh EV |
| `urban_traffic.yaml` | Base profile — fallback cho các feature chưa có profile riêng |

Tất cả profiles hỗ trợ: `respawn_dormant_vehicles`, `collision_avoidance_enabled`, `exclude_same_lane_as_ego`, per-vehicle speed variation.

---

## 4. Mô tả `tools/` — Runtime Tools & GUI

```
tools/
├── project_paths.py          ← Portable path resolver (env var + auto-discovery)
├── start_carla.py            ← One-command CARLA server launcher
├── run_batch.py              ← GUI entrypoint: python tools/run_batch.py
├── config/
│   ├── camera.py             ← Spectator bird-view camera (follows EV)
│   ├── hud.py                ← Real-time pygame visualization HUD
│   ├── KPI.py                ← Standalone KPI monitor class
│   └── maps_CARLA/OpenDrive/ ← 16 XODR OpenDrive map files
└── GUI/
    ├── gui_runner.py         ← Tkinter GUI: 4-panel scenario selector
    ├── batch_runner.py       ← Batch orchestrator
    ├── process_manager.py    ← Process lifecycle manager
    └── report_writer.py      ← Excel report writer
```

### 4.1 `tools/config/` — Runtime Visualization & Monitoring

#### `camera.py` — Spectator Camera
- Tự động tìm vehicle `role_name="ev"` và attach birdview camera
- Exponential smoothing (α=0.12) để camera theo mượt, không giật
- Chạy song song với ScenarioRunner ở 20Hz

#### `hud.py` — Real-time ADAS Visualization HUD (34KB)
Pygame-based HUD hiển thị đầy đủ trạng thái simulation theo thời gian thực:

| Panel | Thông tin hiển thị |
|---|---|
| Camera view | Video từ camera gắn trên EV |
| Server metrics | FPS server/client, simulation time, map name |
| Ego state | Speed (kph), heading, lane position, lane offset (m) |
| Control output | Throttle / Brake / Steer bars (normalized) |
| ADAS feature | ACC: state, target speed, time gap, safe distance / AEB: TTC thresholds, state / LKA: lane offset, deadband, state |
| Nearby vehicles | Danh sách TVs với khoảng cách |

- Hỗ trợ switch feature bằng **F2** (ACC ↔ AEB ↔ LKA)
- Lane detection từ OpenDrive XML maps
- Chạy ở 30 FPS, 1280×720

#### `KPI.py` — Standalone KPI Monitor
Track các chỉ số chất lượng trong khi scenario chạy:

| KPI | Cách tính | Điều kiện FAIL |
|---|---|---|
| Minimum distance | Center-to-center trừ bounding box của cả 2 xe | < 6.0 m |
| Collision | Collision sensor gắn trên EV | Bất kỳ va chạm nào |
| Speed range | Min/max ego speed trong suốt scenario | — |

Output: `{result: PASS/FAIL, fail_reason, fail_time, max_speed, min_speed, min_distance}`

### 4.2 `tools/GUI/` — Batch Execution Framework

#### `gui_runner.py` — Scenario Selector GUI
Tkinter GUI với 4-panel tree navigation:
```
Feature Domain  →  Function  →  Scenario Group  →  Individual Case
(Longitudinal)     (ACC)        (acc_csc_001)       (acc_csc_001_024)
```
Modes: chạy 1 case, 1 folder, nhiều folders, hoặc tất cả. Có log output và progress bar.

#### `batch_runner.py` — Batch Orchestrator
Điều phối toàn bộ batch execution theo flow:

```
1. Discover jobs  →  2. Start ScenarioRunner  →  3. Monitor KPI
       ↓                                                ↓
4. Detect result (PASS/FAIL/TIMEOUT)  →  5. Write report  →  6. Reload CARLA world
```

- Tự động detect feature từ path để load đúng traffic config
- Timeout handling: scenario không kết thúc trong thời gian cho phép → TIMEOUT
- Background vehicles không tính vào KPI (lọc theo `role_name`)

#### `process_manager.py` — Process Lifecycle Manager
Quản lý vòng đời tất cả subprocess:

| Process | Lệnh | Tự động start |
|---|---|---|
| `camera.py` | `python tools/config/camera.py` | Trước mỗi scenario |
| `hud.py` | `python tools/config/hud.py --feature ACC` | Trước mỗi scenario |
| `scenario_runner.py` | `python scenario_runner.py --openscenario <xosc> --reloadWorld --urbanTraffic ...` | Mỗi test case |

- Auto-detect feature từ path để pass `--feature` đúng cho HUD
- Load sim config theo hierarchy: `adas_sil_execution/sim/<feature>/<function>/carla_0_9_16.yaml` → fallback root
- Graceful terminate → 5s wait → force kill

#### `report_writer.py` — Excel Report Writer
Tự động sinh báo cáo Excel sau mỗi batch:

| File output | Sheets | Nội dung |
|---|---|---|
| `report/<case_id>/report.xlsx` | Summary, All Cases, Failed Cases | Per-case result |
| `report/batch_<timestamp>/summary.xlsx` | Summary, All Cases, Failed Cases | Batch tổng hợp |

Columns: `case_id`, `result`, `fail_reason`, `fail_time`, `min_distance`, `max_speed`, `min_speed`, `elapsed_s`

---

## 5. Cấu trúc thư mục Project

```
Test_assets_v1.4/
│
├── scenarios/general_scenarios/
│   ├── logical/              ← 27 YAML (scenario concept definitions)
│   ├── parameters/           ← 27 YAML (parameter spaces)
│   ├── core/                 ← 2,323 YAML (expanded test cases)
│   │   ├── brake_feature/AEB/      (4 IDs · 102 cases)
│   │   ├── lateral_feature/LKA/    (1 ID  ·   1 case)
│   │   └── longitudinal_feature/ACC/ (22 IDs · 2,220 cases)
│   └── generated/carla/      ← 2,323 XOSC (OpenSCENARIO executables, 1:1 với core)
│
├── config/                   ← [xem Section 3]
│   ├── controllers_fmu/      (ACC + AEB + LKA FMU controllers)
│   ├── controllers_py/       (Python reference controllers)
│   └── traffic/              (per-feature traffic profiles)
│
├── tools/                    ← [xem Section 4]
│   ├── config/               (camera, HUD, KPI monitor, maps)
│   └── GUI/                  (batch runner, process manager, report writer)
│
├── adapters/carla/           ← YAML → XOSC generators (per feature domain)
├── scenario_runner/          ← ScenarioRunner library (CARLA integration)
├── adas_sil_execution/       ← SIL execution framework (KPI engine, collectors, reports)
├── expander/                 ← Logical + Parameters → Core YAML expander
│
├── PLAN_acc_smooth_traffic_refactor.md
└── README.md
```

---

## 6. Quick Reference — Số liệu chốt cho báo cáo

| Chỉ số | Giá trị |
|---|---|
| Tổng số Scenario ID (logical) | **27** |
| Tổng số Test Cases (Core YAML) | **2,323** |
| Tổng số Test Scripts executable (XOSC) | **2,323** |
| Feature domains covered | **3** (Brake · Lateral · Longitudinal) |
| Functions implemented | **3** (AEB · LKA · ACC) |
| Controllers (FMU) | **3** (AEB · LKA · ACC) |
| Simulator | **CARLA 0.9.16** |
| Scenario format | **OpenSCENARIO 1.x (.xosc)** |
| Controller standard | **FMI 2.0 CoSimulation (.fmu)** |
| KPI metrics | **Collision · Min Distance · Jerk · TTC** |
| Report format | **Excel (.xlsx) — auto-generated** |
