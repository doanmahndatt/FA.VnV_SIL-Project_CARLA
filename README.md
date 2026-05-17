# FA VnV SIL Test Assets for CARLA

Repo này chứa bộ test asset dùng để generate, chạy và review các file OpenSCENARIO `.xosc` trên CARLA Simulator bằng ScenarioRunner. Flow hiện tại tập trung vào các case ACC. File `.xosc` đã generate nằm theo cấu trúc:

```text
scenarios/generated/carla/<nhóm_case>/<case_id>.xosc
```

Ví dụ:

```text
scenarios/generated/carla/acc_csc_001/acc_csc_001_001.xosc
```

## 1. Yêu Cầu Môi Trường

Môi trường hiện tại đang dùng:

- Windows 10/11
- Python 3.10.14
- CARLA Simulator 0.9.15
- ScenarioRunner source đã có sẵn trong thư mục `scenario_runner/`
- Python packages cho tool nội bộ: `pandas`, `pyyaml`, `pygame`, `openpyxl`
- CARLA Python API phải import được module `carla`

Kiểm tra nhanh:

```powershell
python --version
python -c "import carla; print('carla api ok')"
```

Nếu lệnh import `carla` bị lỗi, cần cài CARLA Python API hoặc set lại `PYTHONPATH` theo bước 3.

## 2. Cấu Trúc Thư Mục Quan Trọng

```text
Test_assets_v1.1/
|-- scenarios/
|   |-- logical/                 # YAML logic test scenario
|   |-- parameters/              # YAML parameter set
|   |-- core/                    # YAML đã merge từ logical + parameters
|   |-- templates/               # OpenSCENARIO template và maneuver block
|   |-- generated/carla/         # File .xosc để chạy trên CARLA
|-- scenario_runner/             # CARLA ScenarioRunner
|-- tools/
|   |-- run_batch.py             # GUI batch runner
|   |-- GUI/
|   |   |-- gui_runner.py        # Tkinter GUI
|   |   |-- batch_runner.py      # Điều phối chạy scenario và KPI
|   |   |-- process_manager.py   # Quản lý camera.py, hud.py, scenario_runner.py
|   |   |-- report_writer.py     # Xuất report theo case và theo batch
|   |-- config/
|   |   |-- camera.py            # Bird-view spectator camera
|   |   |-- hud.py               # HUD Pygame hiển thị speed, distance, TTC
|   |   |-- KPI.py               # KPI monitor runtime
|   |-- acc_controller.py        # Controller/debug tool nếu cần
|-- report/                      # Output Excel report
|-- requirements.txt
```

## 3. Cài Đặt Từ Đầu

### Bước 1: Tải Và Giải Nén CARLA

Tải CARLA 0.9.15 cho Windows từ trang release của CARLA, sau đó giải nén vào một thư mục cố định, ví dụ:

```text
C:\CARLA_0.9.15
```

Trong thư mục CARLA cần có file chạy server:

```text
C:\CARLA_0.9.15\CarlaUE4.exe
```

### Bước 2: Tạo Virtual Environment

Từ thư mục repo:

```powershell
cd C:\Self_Improvement\FA_VnV\Test_assets_v1.1
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
```

### Bước 3: Cài Dependencies

```powershell
pip install -r requirements.txt
pip install pygame openpyxl
```

Với Python 3.10.14 và CARLA 0.9.15 trên Windows, ưu tiên cài CARLA Python API bằng file `.whl` trong thư mục CARLA:

```powershell
pip install C:\CARLA_0.9.15\PythonAPI\carla\dist\carla-0.9.15-cp310-cp310-win_amd64.whl
```

Nếu tên file `.whl` khác một chút, kiểm tra bằng:

```powershell
dir C:\CARLA_0.9.15\PythonAPI\carla\dist\*.whl
```

Nếu không cài bằng `.whl`, có thể set `PYTHONPATH` tạm thời trong terminal hiện tại:

```powershell
$env:CARLA_ROOT="C:\CARLA_0.9.15"
$env:PYTHONPATH="$env:PYTHONPATH;$env:CARLA_ROOT\PythonAPI\carla;$env:CARLA_ROOT\PythonAPI\carla\agents;$env:CARLA_ROOT\PythonAPI\carla\dist\carla-0.9.15-py3.10-win-amd64.egg"
```

Kiểm tra:

```powershell
python -c "import carla; print('carla api ok')"
```

## 4. Khởi Chạy CARLA Server

Mở terminal mới và chạy:

```powershell
cd C:\CARLA_0.9.15
.\CarlaUE4.exe -quality-level=Low -windowed -ResX=1280 -ResY=720
```

Đợi đến khi CARLA map load xong. Tool mặc định kết nối vào:

```text
host = localhost
port = 2000
```

## 5. Chạy Thử Một File .xosc Bằng ScenarioRunner

Mở terminal mới tại repo, active `.venv`, sau đó chạy:

```powershell
cd C:\Self_Improvement\FA_VnV\Test_assets_v1.1
.\.venv\Scripts\activate
python scenario_runner\scenario_runner.py --openscenario scenarios\generated\carla\acc_csc_001\acc_csc_001_001.xosc --reloadWorld
```

Nếu scenario hợp lệ, CARLA sẽ spawn ego vehicle `ev` và target vehicle `tv` theo file `.xosc`.

## 6. Mở Camera Và HUD Để Debug

Chạy mỗi tool trong một terminal riêng:

```powershell
python tools\config\camera.py
```

```powershell
python tools\config\hud.py
```

`camera.py` điều khiển spectator theo ego vehicle có `role_name="ev"`.

`hud.py` hiển thị các giá trị runtime:

- simulation time
- EV speed
- TV speed
- longitudinal distance
- TTC

Nếu HUD hiển thị toàn 0, thường là scenario chưa spawn đủ `ev` và `tv`, hoặc role name trong `.xosc` khác với tool.

## 7. Chạy Batch Bằng GUI

Script chính:

```text
tools/run_batch.py
```

Chạy:

```powershell
cd C:\Self_Improvement\FA_VnV\Test_assets_v1.1
python tools\run_batch.py
```

GUI sẽ tự scan các file `.xosc` trong:

```text
scenarios/generated/carla/
```

Các chế độ chạy:

- `Single case`: chọn một file `.xosc` cụ thể.
- `Single folder`: chọn một sub-folder, ví dụ `acc_csc_003`.
- `Multi folder`: chọn hai hoặc nhiều sub-folder.
- `All folders`: chạy toàn bộ sub-folder trong `scenarios/generated/carla/`.

Phản ứng chọn trong GUI:

- Với `Single case`, sau khi chọn một case, các case còn lại sẽ bị làm mờ và không thể chọn nhầm. Bấm `Bỏ chọn` nếu muốn đổi case.
- Với `Single folder`, sau khi chọn một folder, các folder còn lại sẽ bị làm mờ. Bấm `Bỏ chọn` nếu muốn đổi folder.
- Với `Multi folder`, tick `☑` ở cột `Chọn` để chọn nhiều folder; danh sách case bên phải chỉ hiển thị case thuộc các folder đã tick.
- Với `All folders`, toàn bộ folder được tick sẵn và bị khóa để thể hiện tool sẽ chạy tất cả.

Khi bấm `Start`, tool sẽ:

1. Tự mở `camera.py`.
2. Tự mở `hud.py`.
3. Chạy từng `.xosc` bằng ScenarioRunner.
4. Monitor KPI runtime.
5. Xuất report theo từng `case_id`.
6. Reload CARLA world giữa các case.

Khi bấm `Stop/End`, tool sẽ:

1. Dừng scenario hiện tại.
2. Dừng batch queue.
3. Ghi lại report đã có.
4. Dừng camera/HUD nếu chúng được mở bởi batch runner.

## 8. Output Report

Mỗi case sẽ có folder riêng:

```text
report/<case_id>/report.xlsx
```

Ví dụ:

```text
report/acc_csc_003_001/report.xlsx
```

Khi chạy multi/all folder, tool tạo thêm batch summary:

```text
report/batch_<timestamp>/summary.xlsx
```

File Excel có các sheet:

- `Summary`: tổng số case, số case pass/fail/stopped, pass rate.
- `All Cases`: toàn bộ case đã chạy.
- `Failed Cases`: các case fail hoặc stopped.

Một case có thể fail nếu:

- collision detected
- longitudinal distance nhỏ hơn ngưỡng 6m
- ScenarioRunner timeout hoặc bị stop
- KPI monitor không đọc được actor runtime

## 9. Workflow Chạy Một Nhóm Test

Ví dụ chạy nhóm `acc_csc_003`:

1. Kiểm tra file `.xosc`:

```powershell
dir scenarios\generated\carla\acc_csc_003\*.xosc
```

2. Khởi động CARLA server.

3. Chạy GUI:

```powershell
python tools\run_batch.py
```

4. Chọn mode `Single folder`.

5. Chọn folder `acc_csc_003`.

6. Bấm `Start`.

7. Theo dõi CARLA viewport, HUD, log GUI và report trong `report/`.

## 10. Kiến Trúc Batch Runner

Batch runner được tách thành các phần nhỏ:

```text
tools/
|-- run_batch.py             # GUI entrypoint
|-- GUI/
|   |-- gui_runner.py        # Tkinter GUI
|   |-- batch_runner.py      # BatchRunner, ScenarioJob, report orchestration
|   |-- process_manager.py   # start/stop camera.py, hud.py, scenario_runner.py
|   `-- report_writer.py     # Excel writer theo case_id và summary
|-- config/
|   |-- camera.py            # Bird-view spectator camera
|   |-- hud.py               # Runtime HUD
|   `-- KPI.py               # KPI monitor
```

Luồng chạy:

1. GUI scan recursive `scenarios/generated/carla/*/*.xosc`.
2. Người dùng chọn mode và case/folder.
3. Bấm `Start`.
4. `ProcessManager` start `camera.py` và `hud.py`.
5. `BatchRunner` chạy từng `.xosc` từ queue.
6. Mỗi case:
   - tạo output folder `report/<case_id>/`
   - start ScenarioRunner
   - monitor KPI
   - ghi `report/<case_id>/report.xlsx`
   - reload world
7. Nếu multi/all:
   - ghi thêm `report/batch_<timestamp>/summary.xlsx`
8. Bấm `Stop/End`:
   - terminate scenario process hiện tại
   - stop KPI loop
   - export report đang có
   - reload world nếu CARLA còn kết nối
   - giữ GUI không bị treo

## 11. Troubleshooting

### `ModuleNotFoundError: No module named 'carla'`

CARLA Python API chưa nằm trong Python path. Cài `.whl` hoặc set `PYTHONPATH` theo bước 3.

### `Connection refused` Hoặc Timeout Port 2000

CARLA server chưa chạy, chưa load xong map, hoặc port khác 2000.

### Scenario Không Spawn Xe

Kiểm tra `.xosc` có `ScenarioObject` với `role_name="ev"` và `role_name="tv"` hay không. `camera.py`, `hud.py` và `KPI.py` đang phụ thuộc vào hai role name này.

### GUI Không Hiện Case

Kiểm tra file `.xosc` có nằm đúng dưới:

```text
scenarios/generated/carla/<sub-folder>/
```

### Excel Report Không Save Được

Đóng file Excel đang mở. Tool sẽ thử ghi backup nếu gặp `PermissionError`.

### Stop/End Không Dừng Ngay

Một số process con của CARLA/ScenarioRunner có thể cần vài giây để terminate. Nếu vẫn còn process treo, đóng terminal hoặc kill process Python tương ứng trong Task Manager.

## 12. Git Note

Repo này đã ignore các file model, asset lớn và LFS pointer cũ. Trước khi commit nên kiểm tra:

```powershell
git status --ignored
git lfs ls-files
```

`git lfs ls-files` nên không in ra gì.
