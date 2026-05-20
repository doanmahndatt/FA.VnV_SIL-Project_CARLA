import carla
import time
import math


class KPIMonitor:

    def __init__(self, host="localhost", port=2000):

        self.client = carla.Client(host, port)
        self.client.set_timeout(60.0)

        self.world = None
        self.collision_sensor = None

        self.reset()

    # ================= RESET =================

    def reset(self):

        self.destroy_collision_sensor()

        self.ev_max_speed = 0
        self.ev_min_speed = 999

        self.dist_min = 999

        self.fail = False
        self.fail_reason = ""
        self.fail_time = None

    def destroy_collision_sensor(self):

        if self.collision_sensor is not None:
            try:
                self.collision_sensor.stop()
                self.collision_sensor.destroy()
            except Exception:
                pass
            finally:
                self.collision_sensor = None

    # ================= BASIC =================

    def get_speed(self, vehicle):
        v = vehicle.get_velocity()
        return math.sqrt(v.x**2 + v.y**2 + v.z**2)

    def find_vehicle(self, role):

        for v in self.world.get_actors().filter("vehicle.*"):
            if v.attributes.get("role_name") == role:
                return v

        return None

    # ================= DISTANCE (FIXED) =================

    def longitudinal_distance(self, ev, tv):

        ev_tf = ev.get_transform()
        forward = ev_tf.get_forward_vector()

        rel = tv.get_location() - ev.get_location()

        dist = (
            rel.x * forward.x +
            rel.y * forward.y +
            rel.z * forward.z
        )

        # 🔥 IMPORTANT: subtract bounding box length
        dist -= (ev.bounding_box.extent.x + tv.bounding_box.extent.x)

        return max(dist, 0)

    # ================= COLLISION SENSOR =================

    def attach_collision_sensor(self, vehicle):

        blueprint = self.world.get_blueprint_library().find("sensor.other.collision")

        sensor = self.world.spawn_actor(
            blueprint,
            carla.Transform(),
            attach_to=vehicle
        )

        sensor.listen(lambda event: self.on_collision(event))

        return sensor

    def on_collision(self, event):

        if not self.fail:
            self.fail = True
            self.fail_reason = "collision_detected"
            self.fail_time = round(event.timestamp, 2)

    # ================= STEP =================

    def step(self):

        self.world = self.client.get_world()

        ev = self.find_vehicle("ev")
        tv = self.find_vehicle("tv")

        if ev is None or tv is None:
            return

        # attach sensor once
        if self.collision_sensor is None:
            self.collision_sensor = self.attach_collision_sensor(ev)

        ev_speed = self.get_speed(ev)
        dist = self.longitudinal_distance(ev, tv)

        sim_time = self.world.get_snapshot().timestamp.elapsed_seconds

        # ===== KPI UPDATE =====
        self.ev_max_speed = max(self.ev_max_speed, ev_speed)
        self.ev_min_speed = min(self.ev_min_speed, ev_speed)
        self.dist_min = min(self.dist_min, dist)

        # ===== FAIL DETECTION =====
        if dist < 6.0 and not self.fail:
            self.fail = True
            self.fail_reason = "distance_below_6m"
            self.fail_time = round(sim_time, 2)

    # ================= RUN =================

    def run_monitor(self, duration=30):

        self.reset()

        start = time.time()

        while time.time() - start < duration:

            try:
                self.step()
                time.sleep(0.05)   # ~20Hz
            except Exception as exc:
                print(f"[KPI][WARN] {exc}")

        return self.get_result()

    def get_result(self):

        result = "FAIL" if self.fail else "PASS"

        return {
            "result": result,
            "fail_reason": self.fail_reason,
            "fail_time": self.fail_time,
            "ev_max_speed": round(self.ev_max_speed, 2),
            "ev_min_speed": round(self.ev_min_speed, 2),
            "dist_min": round(self.dist_min, 2)
        }
