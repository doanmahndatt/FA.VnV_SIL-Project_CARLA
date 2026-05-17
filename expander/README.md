*** 
file expander.py là phần mở rộng mới:
- có thể gen single hoặc multi. Nghĩa là có thể chọn 1 suffix 001, 002,... hoặc là toàn bộ.

 command:
 py expander.py acc_csc 002 --clean
 py expander.py acc_csc --from 001 --to 020 --clean

 - tag "--clean" có nhiệm vụ remove toàn bộ old data,tránh việc trùng lặp khi merge -> tối ưu hơn
 ***