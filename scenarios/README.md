*** 

* Giải thích về folder structure

- logical: là folder chứa các file .yaml định nghĩa về behavior và logic của TestScenario
- parameters: là folder chứa các file. yaml tương ứng, khai báo các thông số và giá trị của chúng
- core: là folder chứa các file .yaml được TỰ ĐỘNG gen từ 2 folder logical và params -> merge lại thành 1 Test Scenario khai báo hoàn chỉnh
- templates: 
  + maneuver_blocks: các action logic lớn của func, sẽ được sử dụng và kết hợp cùng storyboard
  + storyboard: phần khung xương khai báo chính khi gen ra TS-formated CARLA.
- generated:
  + phần TS.xosc (chuẩn ASAM OpenSCENARIO) được gen ra từ core + storyBoard + maneuver_blocks
***