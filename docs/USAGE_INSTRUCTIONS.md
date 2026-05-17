
# Hướng Dẫn Sử Dụng OpenSCENARIO Validation Agent

Hướng dẫn nhanh để bắt đầu sử dụng validation tool cho OpenSCENARIO files.

---

## 🚀 Getting Started - 3 Bước Đơn Giản

### Bước 1: Cài Đặt Dependencies

```bash
# Di chuyển vào thư mục project
cd Test_assets_v1.1

# Cài đặt các package cần thiết
pip install -r requirements.txt
```

### Bước 2: Validate File Đầu Tiên

```bash
# Validate một file .xosc
python validate_xosc.py scenarios/generated/carla/acc_csc_001/acc_csc_001_001.xosc
```

### Bước 3: Đọc Kết Quả

- ✓ **VALIDATION PASSED** = File hợp lệ, sẵn sàng sử dụng
- ✗ **VALIDATION FAILED** = Có lỗi cần sửa (xem phần Troubleshooting bên dưới)

---

## 📋 Common Workflows - Các Tình Huống Thường Gặp

### Workflow 1: Validate Một File Scenario

**Khi nào dùng:** Sau khi tạo hoặc chỉnh sửa một file .xosc

```bash
# Cú pháp
python validate_xosc.py <đường/dẫn/tới/file.xosc>

# Ví dụ cụ thể
python validate_xosc.py scenarios/generated/carla/acc_csc_003/acc_csc_003_001.xosc
```

**Kết quả mong đợi:**
```
================================================================================
Validating: scenarios/generated/carla/acc_csc_003/acc_csc_003_001.xosc
================================================================================

Running SchemaValidator...
  ✓ SchemaValidator: PASSED

Running CarlaValidator...
  ✓ CarlaValidator: PASSED

Running SemanticValidator...
  ✓ SemanticValidator: PASSED

================================================================================
✓ VALIDATION PASSED: scenarios/generated/carla/acc_csc_003/acc_csc_003_001.xosc
================================================================================
```

---

### Workflow 2: Validate Toàn Bộ Thư Mục

**Khi nào dùng:** Kiểm tra tất cả scenarios trong một test suite

```bash
# Validate tất cả .xosc files trong thư mục và các thư mục con
python validate_xosc.py scenarios/generated/carla/

# Hoặc validate một test suite cụ thể
python validate_xosc.py scenarios/generated/carla/acc_csc_001/
```

**Kết quả mong đợi:**
```
Tìm thấy 5 .xosc files

[... validation results cho từng file ...]

================================================================================
BATCH VALIDATION SUMMARY
================================================================================
Total files:  5
Passed:       4
Failed:       1
================================================================================
```

---

### Workflow 3: Validate Trước Khi Commit Code

**Khi nào dùng:** Kiểm tra code trước khi push lên Git

```bash
# 1. Validate tất cả scenarios đã tạo/chỉnh sửa
python validate_xosc.py scenarios/generated/

# 2. Nếu có lỗi, sửa file
# 3. Validate lại file đã sửa
python validate_xosc.py <file-đã-sửa.xosc>

# 4. Khi tất cả PASSED, commit code
git add .
git commit -m "Add/update scenarios - all validated"
```

---

### Workflow 4: Tạo Scenario Mới Từ Template

**Khi nào dùng:** Tạo scenario mới cho test case

```bash
# 1. Copy template
cp scenarios/templates/maneuver_blocks/cutin.xosc scenarios/generated/carla/my_scenario.xosc

# 2. Chỉnh sửa file my_scenario.xosc (thay đổi parameters, entities, etc.)

# 3. Validate ngay
python validate_xosc.py scenarios/generated/carla/my_scenario.xosc

# 4. Sửa lỗi nếu có và validate lại
```

---

### Workflow 5: Debug Scenario Thất Bại

**Khi nào dùng:** Scenario không chạy được trong CARLA

```bash
# 1. Validate file để tìm lỗi
python validate_xosc.py scenarios/generated/carla/problematic_scenario.xosc

# 2. Đọc kỹ các ERROR và WARNING messages
# 3. Sửa theo suggestions
# 4. Validate lại cho đến khi PASSED

# 5. Nếu vẫn có vấn đề, kiểm tra chi tiết hơn (xem Advanced Features)
```

---

## 🔧 What To Do When Validation Fails

### Step-by-Step Troubleshooting

#### 1️⃣ Đọc Error Messages

Khi validation fail, bạn sẽ thấy output như này:

```
Running SchemaValidator...
  ✗ SchemaValidator: FAILED

  Errors (2):
    • Missing required element 'Init'
      Location: /OpenSCENARIO/Storyboard
      Suggestion: Add Init element to Storyboard

    • Invalid value for attribute 'name'
      Location: /OpenSCENARIO/Entities/ScenarioObject[1]
      Suggestion: Entity name must not be empty
```

#### 2️⃣ Hiểu Các Loại Lỗi

**ERROR (🔴 - Phải sửa):**
- Lỗi nghiêm trọng, file không thể chạy được
- Phải sửa hết tất cả ERRORs trước khi dùng file

**WARNING (🟡 - Nên sửa):**
- File vẫn chạy được nhưng có thể có vấn đề
- Nên sửa để tránh bugs trong tương lai

**INFO (🔵 - Tham khảo):**
- Gợi ý để code tốt hơn
- Không bắt buộc phải sửa

#### 3️⃣ Sửa Lỗi Theo Thứ Tự

```bash
# Quy trình sửa lỗi:

# Bước 1: Sửa tất cả ERRORs trước
# - Đọc error message
# - Xem Location để biết vị trí lỗi trong file
# - Áp dụng Suggestion nếu có

# Bước 2: Validate lại
python validate_xosc.py <file.xosc>

# Bước 3: Nếu còn ERRORs, lặp lại Bước 1-2

# Bước 4: Khi hết ERRORs, xem xét sửa WARNINGs

# Bước 5: Validate lần cuối
python validate_xosc.py <file.xosc>
```

#### 4️⃣ Các Lỗi Thường Gặp & Cách Sửa

**Lỗi 1: Missing required element**
```
Error: Missing required element 'Init'
Location: /OpenSCENARIO/Storyboard

➜ Cách sửa: Thêm element thiếu vào đúng vị trí
```

**Lỗi 2: Invalid attribute value**
```
Error: Invalid value for 'name' attribute
Location: /OpenSCENARIO/Entities/ScenarioObject[1]

➜ Cách sửa: Kiểm tra giá trị attribute, đảm bảo đúng format
```

**Lỗi 3: CARLA compatibility issue**
```
Warning: Vehicle model 'audi.a3' not found in CARLA catalog
Location: Entity 'ego_vehicle'

➜ Cách sửa: Dùng vehicle model có trong CARLA:
   - vehicle.audi.a2
   - vehicle.tesla.model3
   - vehicle.bmw.grandtourer
   (Xem danh sách đầy đủ trong docs/CARLA_COMPATIBILITY.md)
```

**Lỗi 4: Semantic error**
```
Error: Collision detected between trajectories
Location: Maneuver 'LaneChange_Ego' and 'LaneChange_NPC1'

➜ Cách sửa: Điều chỉnh timing hoặc vị trí của các maneuvers
```

---

## 🎯 Advanced Features Quick Guide

### Tích Hợp Vào CI/CD Pipeline

Chi tiết: Xem `docs/CI_CD_INTEGRATION.md`

```bash
# Quick example
python validate_xosc.py scenarios/generated/ || exit 1
```

### Sử dụng API Trong Python Code

Chi tiết: Xem `docs/API_REFERENCE.md`

```python
from validation_agent.core.schema_validator import SchemaValidator

validator = SchemaValidator()
result = validator.validate("path/to/file.xosc")

if result.is_valid:
    print("✓ Valid!")
else:
    for error in result.errors:
        print(f"✗ {error.message}")
```

### Custom Validation Rules

Chi tiết: Xem `docs/CUSTOM_RULES.md`

```python
# Tạo custom validator cho dự án của bạn
# (Xem documentation để biết chi tiết)
```

### Batch Processing & Reports

Chi tiết: Xem `docs/ADVANCED_USAGE.md`

```bash
# Generate JSON report
python validate_xosc.py scenarios/generated/ --output-json report.json

# Generate HTML report
python validate_xosc.py scenarios/generated/ --output-html report.html
```

---

## 📚 Tài Liệu Bổ Sung

- **API Reference:** `docs/API_REFERENCE.md` - Chi tiết về các classes và methods
- **Architecture:** `docs/ARCHITECTURE.md` - Hiểu cấu trúc hệ thống
- **CARLA Compatibility:** `docs/CARLA_COMPATIBILITY.md` - Danh sách supported features
- **Custom Rules:** `docs/CUSTOM_RULES.md` - Tạo validation rules riêng
- **CI/CD Integration:** `docs/CI_CD_INTEGRATION.md` - Tích hợp vào pipeline

---

## ❓ Câu Hỏi Thường Gặp (FAQ)

### Q: Tôi có cần validate tất cả files không?

**A:** Có, nên validate:
- Mỗi khi tạo file mới
- Sau khi chỉnh sửa file
- Trước khi commit code
- Trước khi chạy test trên CARLA

### Q: File đã PASSED nhưng vẫn không chạy được trên CARLA?

**A:** Validation tool kiểm tra:
- Schema compliance (XML structure)
- CARLA compatibility (supported features)
- Semantic correctness (logic errors)

Nhưng không thể kiểm tra:
- Runtime issues (memory, performance)
- Environment-specific problems (CARLA version, plugins)

➜ Kiểm tra CARLA logs để debug thêm

### Q: Làm sao biết file .xosc của tôi dùng features gì của CARLA?

**A:** Chạy validation, tool sẽ báo:
- Supported features → OK
- Unsupported features → WARNING hoặc ERROR

### Q: Tôi có thể bỏ qua WARNINGs không?

**A:** Có thể, nhưng không khuyến khích:
- WARNINGs thường chỉ ra vấn đề tiềm ẩn
- Có thể gây lỗi khi chạy thật
- Nên sửa để đảm bảo chất lượng

---

## 🆘 Cần Trợ Giúp?

1. **Đọc error message kỹ** - Thường có suggestion rõ ràng
2. **Xem docs/** - Chi tiết về từng validator
3. **Kiểm tra examples/** - Các file .xosc mẫu đã validated
4. **Contact team** - Nếu vẫn gặp vấn đề

---

**Chúc bạn validate thành công! 🎉**