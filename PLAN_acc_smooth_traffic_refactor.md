# Plan: ACC CSC-006 Smooth Control + Traffic Infrastructure Separation

**Date:** 2026-05-22  
**Author:** datdm7.fpt  
**Priority:** High — impacts demo stability and codebase maintainability

---

## Overview

Ba workstream độc lập, thứ tự ưu tiên:

| # | Workstream | Priority | Impact |
|---|---|---|---|
| 1 | ACC controller smooth follow khi TV2 cutin | CRITICAL | Demo fail nếu không fix |
| 2 | TV-background collision avoidance (code) | HIGH | Collision = fail demo |
| 3 | Tách traffic config theo feature domain | MEDIUM | Maintainability / correctness |

---

## Workstream 1 — ACC CSC-006: Smooth Follow Khi TV2 Cut-In

### Root Cause Analysis

Trace qua `ACCController.py:do_step()` với scenario điển hình:
TV2 cutin vào cách EV 8 m, EV đang chạy 30 kph (8.33 m/s):

```
safe_distance  = ego_speed × time_gap = 8.33 × 1.8 = 15.0 m
distance_error = lead_distance − safe_distance = 8 − 15 = −7.0 m  (quá gần)

acc_target_speed = ego_speed − |distance_error| / time_gap
                 = 8.33 − 7.0 / 1.8
                 = 4.44 m/s  ← target speed giảm 3.9 m/s NGAY LẬP TỨC

speed_error  = acc_target_speed − ego_speed = 4.44 − 8.33 = −3.89 m/s
raw_accel    = kp_speed × speed_error = 0.35 × (−3.89) = −1.36
brake output = min(max_brake, |raw_accel|) = min(0.65, 1.36) = 0.65  ← PHANH TỐI ĐA
```

EV phanh cứng → khoảng cách tăng → `distance_error` chuyển dương → full throttle → lặp lại.  
**Kết quả**: dao động brake↔throttle liên tục = jerky follow, fail demo.

### Nguyên nhân cốt lõi

1. **Không có rate-limit** trên `acc_target_speed`: bất kỳ thay đổi khoảng cách đột ngột nào đều tạo ra lệnh điều khiển step-change.
2. **`kp_speed = 0.35` quá cao**: với speed_error ~4 m/s, cho ra `raw_accel = 1.4` vượt `max_brake = 0.65` → luôn kẹt ở max.
3. **`time_gap = 1.8 s` ngắn**: phát hiện cutin muộn, distance_error đã lớn trước khi phản ứng.
4. **Không có deadband**: lỗi khoảng cách nhỏ (±1 m) vẫn tạo ra lệnh điều khiển.

### Thay đổi cần thực hiện

#### File 1: `config/controllers_fmu/longitudinal_feature/ACC/ACCController.py`

**Thêm state variable** `_prev_target_speed` (init = 0.0, cùng chỗ với `_prev_acceleration`):
```python
self._prev_target_speed = 0.0
```

**Thêm rate-limiter cho `acc_target_speed`** trong `do_step()` — sau khi tính `raw_target_speed`, trước khi gán `self.acc_target_speed`:
```python
# Rate-limit: max 2.0 m/s change per second → smooth decel/accel
_max_delta = 2.0 * step_size
raw_target = <giá trị tính được hiện tại>
self.acc_target_speed = max(
    self._prev_target_speed - _max_delta,
    min(self._prev_target_speed + _max_delta, raw_target),
)
self._prev_target_speed = self.acc_target_speed
```

**Thêm distance_error deadband** — trước khi tính `acc_target_speed`:
```python
# Deadband ±1.0 m: không phản ứng với lỗi nhỏ
_DEADBAND = 1.0
if abs(self.distance_error) < _DEADBAND:
    effective_error = 0.0
else:
    effective_error = self.distance_error - (_DEADBAND if self.distance_error > 0 else -_DEADBAND)
```
Thay `self.distance_error` bằng `effective_error` trong phần tính `acc_target_speed`.

**Tune defaults** trong `__init__`:

| Parameter | Giá trị cũ | Giá trị mới | Lý do |
|---|---|---|---|
| `self.time_gap` | 2.0 s | **2.4 s** | Phát hiện sớm hơn, distance_error nhỏ hơn lúc cutin |
| `self.kp_speed` | 0.35 | **0.20** | P-gain thấp hơn → không vượt max_brake trong điều kiện thông thường |
| `self.max_brake` | 0.65 | **0.45** | Cap brake → loại bỏ panic stop; 0.45 đủ để dừng kịp an toàn |
| `self.min_distance` | 5.0 m | **8.0 m** | Buffer lớn hơn, cutin detection sớm hơn |

#### File 2: `config/controllers_fmu/longitudinal_feature/ACC/signals.yaml`

Sync `parameters` section với defaults mới:

```yaml
parameters:
  time_gap: 2.2          # was 1.8 — NOTE: signals.yaml khác với ACCController.py default, đây là runtime value
  kp_speed: 0.20         # was 0.35
  max_brake: 0.45        # was 0.65
  min_distance: 8.0      # was 10.0 (signals.yaml đang dùng 10, giữ nguyên hoặc tune xuống 8)
  # các parameter khác giữ nguyên
```

> **Lưu ý quan trọng**: `signals.yaml` hiện có `time_gap: 1.8` nhưng `ACCController.py` default là 2.0 → bất nhất.  
> Sau khi sửa, cả hai file phải đồng bộ: `time_gap = 2.2`.

### Kết quả kỳ vọng

- Khi TV2 cutin ở 8 m: `acc_target_speed` giảm từ từ (~2 m/s/s) thay vì step-change
- `brake` output tối đa ~0.35 thay vì 0.65 → không còn phanh gấp
- EV decelerate mượt, bám theo TV2 sau 3–5 giây thay vì oscillate

---

## Workstream 2 — TV-Background Collision Avoidance

### Root Cause Analysis

`urban_traffic.yaml` đã có config:
```yaml
collision_avoidance_enabled: true
collision_brake_distance_m: 12.0
collision_slow_distance_m: 26.0
collision_lateral_window_m: 3.2
```

Nhưng `urban_traffic_manager.py:_run_lane_follow_step()` **không đọc bất kỳ key nào trong số này**.  
TM autopilot có thể tự tránh nhau, nhưng khi `agent_fallback_mode: lane_follow` active thì hoàn toàn không có vehicle avoidance.

### Thay đổi cần thực hiện

#### File: `scenario_runner/srunner/scenariomanager/urban_traffic_manager.py`

**Thêm method `_forward_vehicle_distance(vehicle)`**:

```python
def _forward_vehicle_distance(self, vehicle):
    """
    Khoảng cách đến xe gần nhất phía trước trong vùng lateral window.
    Chỉ dùng trong lane_follow fallback.
    """
    lateral_window = float(self._profile.get("collision_lateral_window_m", 3.5))
    transform = vehicle.get_transform()
    fwd = transform.get_forward_vector()
    loc = transform.location
    min_dist = float("inf")
    for other in self.world.get_actors().filter("vehicle.*"):
        if other.id == vehicle.id:
            continue
        rel = other.get_location() - loc
        along = rel.x * fwd.x + rel.y * fwd.y  # projection lên trục forward
        if along < 1.0:                          # bỏ qua xe phía sau / cạnh bên
            continue
        lateral = abs(rel.x * (-fwd.y) + rel.y * fwd.x)
        if lateral < lateral_window:
            min_dist = min(min_dist, along)
    return min_dist
```

**Inject collision check vào `_run_lane_follow_step()`** — TRƯỚC phần `stop_for_light`:

```python
if bool(self._profile.get("collision_avoidance_enabled", False)):
    fwd_dist = self._forward_vehicle_distance(vehicle)
    brake_dist = float(self._profile.get("collision_brake_distance_m", 12.0))
    slow_dist  = float(self._profile.get("collision_slow_distance_m", 26.0))

    if fwd_dist < brake_dist:
        vehicle.apply_control(carla.VehicleControl(throttle=0.0, steer=steer, brake=0.8))
        return  # skip tất cả logic phía dưới

    if fwd_dist < slow_dist:
        # Tuyến tính scale target_speed: 100% ở slow_dist, 20% ở brake_dist
        scale = (fwd_dist - brake_dist) / max(slow_dist - brake_dist, 1.0)
        target_speed = target_speed * (0.2 + 0.8 * scale)
```

### Kết quả kỳ vọng

- TV-background dừng lại khi xe phía trước trong vòng 12 m
- Giảm tốc từ từ khi xe phía trước trong vòng 26 m
- Zero collision trong 60s demo với 20 background TVs

---

## Workstream 3 — Tách Traffic Config theo Feature Domain

### Vấn đề Hiện Tại

Một file `config/traffic/urban_traffic.yaml` + một profile `urban_acc_aeb` dùng cho **tất cả** features.  
ACC (cần dense traffic, cutin-safe), LKA (cần oncoming, opposite heading), AEB (cần slow + short range) đang share cùng config → không thể tối ưu cho từng feature.

### Target Folder Structure

```
config/traffic/
├── urban_traffic.yaml                          ← giữ nguyên làm fallback / base reference
├── longitudinal_feature/
│   ├── ACC/
│   │   └── acc_traffic.yaml                    ← tuned for ACC cutin/follow
│   └── HWA/
│       └── hwa_traffic.yaml                    ← placeholder (copy từ ACC)
├── lateral_feature/
│   └── LKA/
│       └── lka_traffic.yaml                    ← oncoming + opposite heading
└── brake_feature/
    ├── AEB/
    │   └── aeb_traffic.yaml                    ← slow speed, short range
    └── RAEB/
        └── raeb_traffic.yaml                   ← placeholder

adas_sil_execution/sim/
├── carla_0_9_16.yaml                           ← giữ nguyên làm fallback
├── longitudinal_feature/
│   ├── ACC/
│   │   └── carla_0_9_16.yaml                   ← traffic.config → .../ACC/acc_traffic.yaml
│   └── HWA/
│       └── carla_0_9_16.yaml
├── lateral_feature/
│   └── LKA/
│       └── carla_0_9_16.yaml                   ← traffic.config → .../LKA/lka_traffic.yaml
└── brake_feature/
    ├── AEB/
    │   └── carla_0_9_16.yaml
    └── RAEB/
        └── carla_0_9_16.yaml
```

### Profile Differences per Feature

| Feature | Key config so với `urban_traffic.yaml` base |
|---|---|
| **ACC** | `require_opposite_heading: false`, `spawn_only_opposite_lane: false`, `global_distance_to_leading_vehicle: 8.0`, `collision_avoidance_enabled: true` |
| **LKA** | `require_opposite_heading: true`, `spawn_only_opposite_lane: true`, `avoid_junction_spawn: true`, `desired_speed_kph_range: [22, 32]` |
| **AEB** | `desired_speed_kph_range: [5, 15]`, `vehicle_count: 8`, `max_spawn_distance_from_ego: 60`, `min_spawn_distance_from_ego: 10` |
| **HWA** | Giống ACC nhưng `desired_speed_kph_range: [60, 100]`, `global_distance_to_leading_vehicle: 25` |

### Auto-Resolve Logic trong `scenario_runner.py`

Hiện tại `--urbanTrafficConfig` là một CLI arg, default `config/traffic/urban_traffic.yaml`.  
Thêm logic auto-resolve từ xosc path vào hàm xử lý args:

```python
# scenario_runner.py — trong phần load scenario config
def _resolve_traffic_config(xosc_path, base_config_dir="config/traffic"):
    """
    Từ path xosc, extract feature domain/function và tìm traffic config tương ứng.
    Ví dụ: .../longitudinal_feature/ACC/acc_csc_006_001.xosc
           → config/traffic/longitudinal_feature/ACC/acc_traffic.yaml
    Fallback: config/traffic/urban_traffic.yaml
    """
    import re
    from pathlib import Path
    match = re.search(
        r"(longitudinal_feature|lateral_feature|brake_feature|parking_feature)/(\w+)/",
        str(xosc_path)
    )
    if match:
        feature_path = Path(base_config_dir) / match.group(1) / match.group(2)
        candidate = feature_path / "{}_traffic.yaml".format(match.group(2).lower())
        if candidate.exists():
            return str(candidate)
    return str(Path(base_config_dir) / "urban_traffic.yaml")
```

Gọi function này khi `--urbanTrafficConfig` không được override tường minh, hoặc thêm flag `--urbanTrafficAutoConfig`.

---

## Implementation Checklist

### Phase 1 — ACC Controller Fix (CRITICAL, thực hiện trước)

- [ ] `ACCController.py`: thêm `_prev_target_speed = 0.0` vào `__init__`
- [ ] `ACCController.py`: thêm `_DEADBAND = 1.0` và deadband logic trong `do_step()`
- [ ] `ACCController.py`: thêm rate-limiter (`max_delta = 2.0 * step_size`) cho `acc_target_speed`
- [ ] `ACCController.py`: update defaults: `time_gap=2.4`, `kp_speed=0.20`, `max_brake=0.45`, `min_distance=8.0`
- [ ] `signals.yaml`: sync `time_gap: 2.2`, `kp_speed: 0.20`, `max_brake: 0.45`
- [ ] Test: `acc_csc_006_001.xosc` → verify EV decelerate mượt, không oscillate

### Phase 2 — TV-BG Collision Avoidance

- [ ] `urban_traffic_manager.py`: thêm `_forward_vehicle_distance(vehicle)` method
- [ ] `urban_traffic_manager.py`: inject collision check vào đầu `_run_lane_follow_step()`
- [ ] Test: chạy 20 TVs trong 60s, log `[URBAN_TRAFFIC]` không có collision warning

### Phase 3 — Traffic Config Separation

- [ ] Tạo `config/traffic/longitudinal_feature/ACC/acc_traffic.yaml`
- [ ] Tạo `config/traffic/lateral_feature/LKA/lka_traffic.yaml`
- [ ] Tạo `config/traffic/brake_feature/AEB/aeb_traffic.yaml`
- [ ] Tạo `config/traffic/longitudinal_feature/HWA/hwa_traffic.yaml` (placeholder)
- [ ] Tạo `config/traffic/brake_feature/RAEB/raeb_traffic.yaml` (placeholder)
- [ ] Tạo các `adas_sil_execution/sim/{feature}/{fn}/carla_0_9_16.yaml` tương ứng
- [ ] `scenario_runner.py`: thêm `_resolve_traffic_config()` + wire vào arg parsing
- [ ] Test: run ACC scenario → log shows `acc_traffic.yaml`; run LKA → shows `lka_traffic.yaml`

---

## Notes & Risks

| Risk | Mitigation |
|---|---|
| `max_brake: 0.45` quá thấp cho AEB scenario | AEB dùng riêng `aeb_traffic.yaml`, không liên quan ACC controller |
| Rate-limiter có thể làm EV phản ứng chậm với emergency braking | Chỉ apply rate-limit cho `acc_target_speed`, không block emergency logic trong layer trên |
| `_forward_vehicle_distance()` scan toàn bộ actors mỗi tick → perf | Chỉ active khi `collision_avoidance_enabled: true` và `agent_fallback_mode: lane_follow`; 20 TVs × 60 Hz = chấp nhận được |
| Auto-resolve xosc path có thể fail nếu path format khác | Luôn có fallback về `urban_traffic.yaml` |
| `ACCController.fmu` cần rebuild sau khi sửa `ACCController.py` | Ghi rõ trong release notes: phải chạy `pythonfmu build` và cập nhật `.fmu` file |
