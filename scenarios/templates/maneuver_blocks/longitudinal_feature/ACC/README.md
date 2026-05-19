# Maneuver Blocks Classification & Mapping

## 1. Mục tiêu

- Chuẩn hóa quan hệ 1 maneuver-type ↔ 1 maneuver_block (logic template)
- Phân loại các maneuver_block theo ngữ nghĩa hành vi (natural language)
- Tái sử dụng block tối đa, chỉ tạo block mới khi khác bản chất
- Hỗ trợ group các file `.yaml` scenario theo block logic

---

## 2. Danh sách Maneuver-type (Nguồn đầu vào)

ID   Natural Language Description
-----------------------------------

 001  follow
 002  TV_appear
 003  TV_cutin_Left
 004  TV_cutin_Right
 005  newTV_cutin_Left
 006  newTV_cutin_Right
 007  TV_cutin_nStop
 008  TV_cutout_Left
 009  TV_cutout_Right
 010  TV1_cutout + TV2_appear
 011  TV1_cutout + TV2_appear
 012  TV1_cutout + TV2_static
 013  EV_cutout_Left
 014  EV_cutout_Right
 015  EV_cutout + newTV_appear
 016  EV_cutout + newTV_appear
 018  EV_bend_mode ~ curve
 019  EV_cutout + Turn_indicator
 020  Stop & Go

---

## 3. Phân loại Maneuver Blocks theo Ngữ nghĩa

### 3.1 Follow  Longitudinal Control

Đặc trưng không đổi làn, không cut-in  cut-out

Maneuver-type  Block
----------------------

 001  follow.xosc
 020  stop.xosc

✅ Đã có block, không cần tạo mới.

---

### 3.2 TV Appear  Static

Đặc trưng vehicle xuất hiện nhưng không lateral maneuver rõ ràng

Maneuver-type  Block
----------------------

 002  appear.xosc (new, khuyến nghị)
 012  cutout.xosc + static config

 Ghi chú  

- Nếu không tạo `appear.xosc`, có thể reuse `cutin.xosc` với laneOffset = 0  
- Tuy nhiên `appear.xosc` giúp semantic rõ ràng hơn

---

### 3.3 TV Cut-in

Đặc trưng Target Vehicle nhập vào lane Ego

Maneuver-type
---------------

 003, 004
 005, 006
 007

Maneuver block dùng chung  

- `cutin.xosc`

Phân biệt bằng parameter

- direction left  right
- isNewEntity true  false
- hasStopAfter (cho 007)

✅ Không cần nhân bản block theo LeftRight.

---

### 3.4 TV Cut-out

Đặc trưng Target Vehicle rời lane Ego

Maneuver-type  Block
----------------------

 008, 009  cutout.xosc
 010, 011  cutout.xosc + appear.xosc
 012  cutout.xosc

✅ Cho phép chain nhiều entity trong cùng scenario YAML.

---

### 3.5 EV Cut-out (Ego Vehicle Lane Change)

Đặc trưng Ego Vehicle đổi làn → khác bản chất TV

Maneuver-type  Block
----------------------

 013, 014  ego_cutout.xosc (new)
 015, 016  ego_cutout.xosc + appear.xosc
 019  ego_cutout_signal.xosc (new)

📌 Lý do tạo block mới

- Ego có controller khác TV
- Có logic turn indicator
- Có priority & safety khác

---

### 3.6 Geometry  Curve

Đặc trưng không phải lane-change discrete, mà là continuous geometry

Maneuver-type  Block
----------------------

 018  curve.xosc (new)

✅ Không nên reuse cutin  cutout.

---

## 4. Cấu trúc thư mục Maneuver Blocks (Đề xuất)

```text
templates
└── maneuver_blocks
    ├── follow.xosc
    ├── stop_n_resume.xosc
    ├── cutin.xosc
    ├── cutout.xosc
    ├── appear.xosc               
    ├── ego_cutout.xosc           
    ├── ego_cutout_signal.xosc    
    ├── cruise_control.xosc       
    ├── curve.xosc                
    └── README.md                
