# ================= IMPORT LIBRARIES =================

import carla      # CARLA Python API → truy cập world, vehicle, transform
import pygame     # thư viện tạo cửa sổ HUD 2D
import time       # dùng sleep để điều chỉnh tốc độ update HUD
import math       # dùng sqrt để tính độ lớn vector vận tốc


# ================= INIT PYGAME WINDOW =================

pygame.init()   # khởi tạo pygame engine

# tạo cửa sổ HUD kích thước 420x160 pixel
screen = pygame.display.set_mode((420,160))

# đặt tiêu đề cửa sổ
pygame.display.set_caption("ADAS HUD")

# chọn font monospace để số không bị nhảy vị trí khi thay đổi
font = pygame.font.SysFont("consolas",20)



# ================= CONNECT TO CARLA =================

# kết nối tới CARLA server đang chạy ở localhost port 2000
client = carla.Client("localhost",2000)

# timeout 10 giây nếu không kết nối được
client.set_timeout(10)



# ================= HELPER FUNCTIONS =================

def find_vehicle(world, role):
    """
    tìm vehicle theo role_name trong OpenSCENARIO
    ví dụ:
        role_name="ev"
        role_name="tv"
    """

    # lấy toàn bộ actor là vehicle trong world
    for v in world.get_actors().filter("vehicle.*"):

        # kiểm tra role_name
        if v.attributes.get("role_name")==role:

            return v   # trả về vehicle nếu tìm thấy

    return None   # nếu chưa spawn thì trả về None



def get_speed(vehicle):
    """
    tính vận tốc xe theo km/h
    CARLA trả về velocity vector đơn vị m/s
    """

    # vector vận tốc 3D
    v = vehicle.get_velocity()

    # độ lớn vector vận tốc → đổi sang km/h
    return 3.6*math.sqrt(v.x**2+v.y**2+v.z**2)



def longitudinal_distance(ev, tv):
    """
    khoảng cách theo hướng chuyển động EV
    phù hợp logic ACC

    không dùng khoảng cách euclidean vì:
        xe có thể lệch lane
        distance 3D không phản ánh khoảng cách dọc
    """

    # transform của EV
    ev_tf = ev.get_transform()

    # vector hướng chuyển động EV
    forward = ev_tf.get_forward_vector()

    # vector từ EV tới TV
    rel = tv.get_location() - ev.get_location()


    # chiếu vector khoảng cách lên hướng forward
    # kết quả là khoảng cách dọc theo lane
    dist = (

        rel.x*forward.x
        + rel.y*forward.y
        + rel.z*forward.z

    )


    # trừ chiều dài xe để gần bumper-to-bumper distance
    # extent.x = nửa chiều dài xe
    dist -= 0.5*(

        ev.bounding_box.extent.x
        + tv.bounding_box.extent.x

    )*2


    # tránh distance âm khi xe overlap
    return max(dist,0)



# ================= MAIN LOOP =================

# lưu thời điểm EV spawn để reset time về 0
start_time = None


while True:

    # xử lý event pygame để cửa sổ không bị treo
    pygame.event.pump()


    # lấy world hiện tại
    world = client.get_world()


    # tìm ego vehicle và target vehicle
    ev = find_vehicle(world,"ev")

    tv = find_vehicle(world,"tv")



    # ================= KHI EV & TV ĐÃ SPAWN =================

    if ev and tv:

        # thời gian simulation của CARLA
        snapshot_time = world.get_snapshot().timestamp.elapsed_seconds


        # reset time khi EV xuất hiện lần đầu
        if start_time is None:

            start_time = snapshot_time


        # thời gian scenario bắt đầu từ khi EV spawn
        sim_time = snapshot_time - start_time



        # vận tốc EV và TV
        ev_speed = get_speed(ev)

        tv_speed = get_speed(tv)



        # khoảng cách longitudinal (chuẩn ACC)
        dist = longitudinal_distance(ev,tv)



        # relative speed (m/s)
        rel_speed = (ev_speed-tv_speed)/3.6



        # TTC chỉ có ý nghĩa khi EV tiến gần TV
        if rel_speed > 0.1:

            ttc = dist/rel_speed

        else:

            # nếu tốc độ gần bằng nhau → TTC vô hạn
            ttc = 999



    # ================= KHI SCENARIO CHƯA SPAWN XE =================

    else:

        # reset start time để scenario chạy lại không bị cộng dồn
        start_time = None


        # giá trị mặc định
        sim_time=0

        ev_speed=0

        tv_speed=0

        dist=0

        ttc=0



    # ================= DRAW HUD =================

    # màu nền xám đậm
    screen.fill((25,25,25))



    # danh sách text hiển thị
    lines = [

        f"time : {sim_time:6.2f} s",

        f"EV   : {ev_speed:6.2f} km/h",

        f"TV   : {tv_speed:6.2f} km/h",

        f"dist : {dist:6.2f} m",

        f"TTC  : {ttc:6.2f} s"

    ]


    # vị trí dòng đầu tiên
    y=15


    # vẽ từng dòng text
    for l in lines:

        # render text màu trắng
        txt=font.render(l,True,(255,255,255))

        # vẽ text lên cửa sổ HUD
        screen.blit(txt,(20,y))

        # xuống dòng tiếp theo
        y+=26



    # cập nhật cửa sổ HUD
    pygame.display.flip()



    # delay để chạy ~20 Hz
    # khớp với fixed_delta_seconds = 0.05 của ScenarioRunner
    time.sleep(0.05)