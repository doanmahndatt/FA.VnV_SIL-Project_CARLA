*sau khi update GUI và refactor toàn bộ folder, có 1 số vấn đề sau:
- các case CPNA là kiểu kịch bản VRU băng qua đường theo phương ngang, vuông góc với phương di chuyển của EV --> hiện tại đang là cùng 1 chiều dọc, hãy fix phần này
- khi tôi run CARLA thì đến giây thứ 6 đã mất, tôi muốn verify xem AEB có trigger và notice user khi TTC đến VRU đạt ngưỡng trigger function --> hãy fix phần này
- các thông số được fixed trong ParameterDeclaration hãy giữ nguyên vì đây là những thông số dc định nghĩa theo tài liệu NCAP_2025