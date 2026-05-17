# 1. Chạy 1 scenario
python generated.py acc_csc_002 --clean

# 2. Chạy nhiều scenario
python generated.py acc_csc_001 acc_csc_002 acc_csc_003

# 3. Chạy theo range
python generated.py acc_csc_001:acc_csc_010 --clean

# 4. Chạy tất cả scenario trong core/
python generated.py --all --clean