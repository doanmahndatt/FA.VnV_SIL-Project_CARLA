import carla
import time
import math

class CarlaCollector:
    """
    Collects ground-truth signals directly from CARLA.
    No KPI logic here – signal acquisition only.
    """

    def __init__(self, host="127.0.0.1", port=2000):
        self.client = carla.Client(host, port)
        self.client.set_timeout(60.0)

        self.world = self.client.get_world()
        self.ego_vehicle = None
        self.target_vehicle = None

        self.collision_events = []

    # ------------------------------------------------
    # Setup
    # ------------------------------------------------
    def bind_ego(self, role_name="ego"):
        for actor in self.world.get_actors().filter("vehicle.*"):
            if actor.attributes.get("role_name") == role_name:
                self.ego_vehicle = actor
                return
        raise RuntimeError("Ego vehicle not found")

    def bind_target(self, role_name="target"):
        for actor in self.world.get_actors().filter("vehicle.*"):
            if actor.attributes.get("role_name") == role_name:
                self.target_vehicle = actor
                return

    def attach_collision_sensor(self):
        bp = self.world.get_blueprint_library().find("sensor.other.collision")
        sensor = self.world.spawn_actor(
            bp,
            carla.Transform(),
            attach_to=self.ego_vehicle
        )
        sensor.listen(self._on_collision)

    def _on_collision(self, event):
        self.collision_events.append({
            "timestamp": time.time(),
            "other_actor": event.other_actor.id
        })

    # ------------------------------------------------
    # Signal collection
    # ------------------------------------------------
    def get_timestamp(self):
        snap = self.world.get_snapshot()
        return snap.timestamp.elapsed_seconds

    def get_ego_speed(self):
        v = self.ego_vehicle.get_velocity()
        return math.sqrt(v.x**2 + v.y**2 + v.z**2)

    def get_distance_to_target(self):
        if not self.target_vehicle:
            return None
        p1 = self.ego_vehicle.get_location()
        p2 = self.target_vehicle.get_location()
        return p1.distance(p2)

    def has_collision(self):
        return len(self.collision_events) > 0

    # ------------------------------------------------
    # Unified sample API
    # ------------------------------------------------
    def collect_sample(self):
        return {
            "timestamp": self.get_timestamp(),
            "signals": {
                "ego_speed": self.get_ego_speed(),
                "distance_to_target": self.get_distance_to_target(),
                "collision": self.has_collision()
            }
        }