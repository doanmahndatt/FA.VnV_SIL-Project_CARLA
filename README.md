# 🔍 OpenSCENARIO Validation Agent

**Tool validation chuyên nghiệp cho OpenSCENARIO files (.xosc) tích hợp với CARLA Simulator**

Validation Agent giúp bạn kiểm tra tính hợp lệ của scenario files trước khi chạy simulation, phát hiện lỗi sớm và tiết kiệm thời gian debug.

---

## ✨ Tính Năng Chính

- ✅ **Schema Validation** - Kiểm tra cú pháp XML và tuân thủ OpenSCENARIO standard
- 🚗 **CARLA Compatibility** - Validate khả năng tương thích với CARLA Simulator
- 🧠 **Semantic Validation** - Phát hiện lỗi logic và tình huống không hợp lý
- 📊 **Detailed Reports** - Báo cáo chi tiết với errors, warnings và suggestions
- ⚡ **Batch Processing** - Validate nhiều files cùng lúc
- 🎯 **Easy to Use** - Không cần config phức tạp, chạy ngay được

---

## 🚀 Quick Start

### 1. Cài Đặt Dependencies

```bash
pip install lxml pyyaml
```

### 2. Validate Một File

```bash
python validate_xosc.py scenarios/generated/carla/acc_csc_003/acc_csc_003_001.xosc
```

### 3. Validate Cả Thư Mục

```bash
python validate_xosc.py scenarios/generated/carla/
```

### 4. Xem Kết Quả

```
================================================================================
Validating: scenarios/generated/carla/acc_csc_003/acc_csc_003_001.xosc
================================================================================

Running SchemaValidator...
  ✓ SchemaValidator: PASSED

Running CarlaValidator...
  ✓ CarlaValidator: PASSED

Running SemanticValidator...
  ✗ SemanticValidator: FAILED

  Warnings (2):
    • Vehicle speed 150 km/h vượt quá giới hạn CARLA (130 km/h)
      Location: //Init/Actions/Private[@entityRef='ego_vehicle']

================================================================================
✓ VALIDATION PASSED: scenarios/generated/carla/acc_csc_003/acc_csc_003_001.xosc
================================================================================
```

---

## 📖 Common Use Cases

### ✅ Validate File Trước Khi Commit

```bash
# Kiểm tra file vừa tạo/sửa
python validate_xosc.py scenarios/generated/carla/my_scenario/my_scenario_001.xosc
```

### ✅ Validate Toàn Bộ Generated Scenarios

```bash
# Kiểm tra tất cả scenarios đã generate
python validate_xosc.py scenarios/generated/
```

### ✅ CI/CD Integration

```bash
# Thêm vào CI pipeline
python validate_xosc.py scenarios/generated/carla/
if [ $? -eq 0 ]; then
    echo "All scenarios valid ✓"
else
    echo "Validation failed ✗"
    exit 1
fi
```

### ✅ Pre-Simulation Check

```bash
# Validate trước khi chạy CARLA simulation
python validate_xosc.py my_test_scenario.xosc && carla_runner.py my_test_scenario.xosc
```

---

## 📚 Documentation

- **[Architecture Overview](docs/architecture.md)** - Hiểu cấu trúc và design của tool
- **[Validation Rules](docs/validation_rules.md)** - Chi tiết các rules được kiểm tra
- **[User Guide](docs/user_guide.md)** - Hướng dẫn sử dụng đầy đủ
- **[Developer Guide](docs/developer_guide.md)** - Hướng dẫn mở rộng và customize

---

## 🔧 Requirements

- **Python**: 3.8+
- **Dependencies**:
  - `lxml` - XML parsing và validation
  - `pyyaml` - YAML configuration files
- **OpenSCENARIO**: Version 1.0+
- **CARLA Simulator**: 0.9.13+ (optional, for integration testing)

---

## 📁 Project Structure

```
Test_assets_v1.1/
├── validate_xosc.py              # 🎯 Main entry point - BẮT ĐẦU TỪ ĐÂY
├── validation_agent/              # Core validation logic
│   ├── core/
│   │   ├── schema_validator.py   # XML schema validation
│   │   ├── carla_validator.py    # CARLA compatibility checks
│   │   ├── semantic_validator.py # Logic validation
│   │   └── validation_result.py  # Result data models
│   └── rules/
│       └── carla_rules.yaml      # CARLA validation rules
├── scenarios/                     # Test scenarios
│   ├── generated/                # Generated scenarios
│   ├── templates/                # Scenario templates
│   └── parameters/               # Parameter files
└── docs/                         # Documentation
    ├── architecture.md
    ├── validation_rules.md
    ├── user_guide.md
    └── developer_guide.md
```

---

## 💡 Tips & Tricks

- 💾 **Lưu Output**: `python validate_xosc.py file.xosc > validation_report.txt`
- 🎯 **Focus on Errors**: Sửa errors trước, warnings sau
- 🔄 **Iterative Workflow**: Validate → Fix → Validate lại
- 📊 **Batch Reports**: Validate cả folder để có overview

---

## 🤝 Support & Contribution

- **Issues**: Báo lỗi hoặc đề xuất tính năng mới
- **Documentation**: Góp ý cải thiện docs
- **Code**: Mở rộng validators hoặc thêm rules mới

---

## 📝 License

Internal tool for SIL-HIL Testing Framework  
© 2026 - For project use only

---

## 🎯 Next Steps

1. ✅ Chạy `python validate_xosc.py --help` để xem usage
2. ✅ Test với một file mẫu: `python validate_xosc.py scenarios/generated/carla/acc_csc_003/acc_csc_003_001.xosc`
3. ✅ Đọc [User Guide](docs/user_guide.md) để hiểu sâu hơn
4. ✅ Tích hợp vào workflow của bạn

**Happy Validating! 🚀**