import carla
import math
import time


TARGET_SPEED = 10.0      # m/s
MIN_DIST = 6.0
TIME_HEADWAY = 1.8


def get_speed(vehicle):
    v = vehicle.get_velocity()
    return math.sqrt(v.x**2 + v.y**2 + v.z**2)


def longitudinal_distance(ev, tv):

    ev_tf = ev.get_transform()
    forward = ev_tf.get_forward_vector()

    rel = tv.get_location() - ev.get_location()

    dist = (
        rel.x * forward.x +
        rel.y * forward.y +
        rel.z * forward.z
    )

    dist -= (ev.bounding_box.extent.x + tv.bounding_box.extent.x)

    return max(dist, 0)


def acc_target_speed(ev_speed, distance):

    desired_dist = max(MIN_DIST, ev_speed * TIME_HEADWAY)

    error = distance - desired_dist

    # 🔥 tăng gain để phản ứng nhanh hơn
    k = 0.8

    v_cmd = ev_speed + k * error

    return max(0, min(TARGET_SPEED, v_cmd))


def find_vehicle(world, role):

    for v in world.get_actors().filter("vehicle.*"):
        if v.attributes.get("role_name") == role:
            return v

    return None


def run():

    client = carla.Client("localhost", 2000)
    client.set_timeout(10.0)

    world = None

    print("ACC controller started")

    while True:

        try:

            new_world = client.get_world()

            if world is None or world.id != new_world.id:
                world = new_world
                print("connected world")

            ego = find_vehicle(world, "ev")
            target = find_vehicle(world, "tv")

            if ego is None:
                time.sleep(0.05)
                continue

            ev_speed = get_speed(ego)

            # ===== nếu không có target → cruise =====
            if target is None:
                v_cmd = TARGET_SPEED
                dist = 999
            else:
                dist = longitudinal_distance(ego, target)
                v_cmd = acc_target_speed(ev_speed, dist)

            control = ego.get_control()

            speed_error = v_cmd - ev_speed

            # ===== THROTTLE =====
            if speed_error > 0:
                control.throttle = min(0.6, speed_error * 0.5)
                control.brake = 0

            # ===== BRAKE =====
            else:
                control.throttle = 0
                control.brake = min(0.8, -speed_error * 0.3)

            ego.apply_control(control)

            # DEBUG
            print(f"v={ev_speed:.2f} m/s | cmd={v_cmd:.2f} | dist={dist:.2f}")

            time.sleep(0.05)

        except RuntimeError:
            world = None
            time.sleep(1)


if __name__ == "__main__":
    run()