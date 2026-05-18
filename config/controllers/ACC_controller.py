import math

import carla

try:
    from srunner.scenariomanager.actorcontrols.basic_control import BasicControl
    from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
except ImportError:
    from scenario_runner.srunner.scenariomanager.actorcontrols.basic_control import BasicControl
    from scenario_runner.srunner.scenariomanager.carla_data_provider import CarlaDataProvider


class AccController(BasicControl):
    def __init__(self, actor, args=None):
        super().__init__(actor)

        args = args or {}
        if "desired_speed" not in args:
            raise ValueError("ACC_controller requires 'desired_speed' from XOSC properties")

        self.desired_speed = float(args["desired_speed"])
        self.target_role = args.get("target_role", "tv")

        self.min_distance = float(args.get("min_distance", 10.0))
        self.time_headway = float(args.get("time_headway", 1.8))
        self.kp_speed = float(args.get("kp_speed", 0.35))
        self.max_throttle = float(args.get("max_throttle", 0.75))
        self.max_brake = float(args.get("max_brake", 0.65))

    def update_target_speed(self, speed):
        super().update_target_speed(speed)
        self.desired_speed = float(speed)

    def reset(self):
        self._actor = None

    def run_step(self):
        if self._actor is None or not self._actor.is_alive:
            return

        target_actor = self._find_target_actor()
        ev_speed = self._get_speed(self._actor)

        if target_actor is not None:
            distance = self._longitudinal_distance(self._actor, target_actor)
            target_speed = self._compute_acc_target_speed(ev_speed, distance)
        else:
            distance = None
            target_speed = self.desired_speed

        control = self._speed_control(ev_speed, target_speed)
        self._actor.apply_control(control)

        print(
            "[ACC_CTRL] "
            f"ev={ev_speed:.2f}m/s "
            f"target={target_speed:.2f}m/s "
            f"dist={distance if distance is not None else 'None'}"
        )

    def _find_target_actor(self):
        world = CarlaDataProvider.get_world()
        if world is None:
            return None

        for actor in world.get_actors().filter("vehicle.*"):
            if actor.id == self._actor.id:
                continue

            role = actor.attributes.get("role_name")
            if role == self.target_role and actor.is_alive:
                return actor

        return None

    @staticmethod
    def _get_speed(vehicle):
        velocity = vehicle.get_velocity()
        return math.sqrt(
            velocity.x * velocity.x +
            velocity.y * velocity.y +
            velocity.z * velocity.z
        )

    @staticmethod
    def _longitudinal_distance(ev, tv):
        ev_tf = ev.get_transform()
        forward = ev_tf.get_forward_vector()
        rel = tv.get_location() - ev.get_location()

        projected = rel.x * forward.x + rel.y * forward.y + rel.z * forward.z
        projected -= ev.bounding_box.extent.x + tv.bounding_box.extent.x

        return max(projected, 0.0)

    def _compute_acc_target_speed(self, ev_speed, distance):
        safe_distance = max(self.min_distance, ev_speed * self.time_headway)
        distance_error = distance - safe_distance

        if distance_error >= 0:
            return self.desired_speed

        reduction = abs(distance_error) / max(self.time_headway, 0.1)
        return max(0.0, min(self.desired_speed, ev_speed - reduction))

    def _speed_control(self, current_speed, target_speed):
        control = carla.VehicleControl()
        control.manual_gear_shift = False
        control.hand_brake = False
        control.reverse = False
        control.steer = 0.0

        error = target_speed - current_speed

        if error >= 0:
            control.throttle = min(self.max_throttle, self.kp_speed * error)
            control.brake = 0.0
        else:
            control.throttle = 0.0
            control.brake = min(self.max_brake, self.kp_speed * abs(error))

        return control
