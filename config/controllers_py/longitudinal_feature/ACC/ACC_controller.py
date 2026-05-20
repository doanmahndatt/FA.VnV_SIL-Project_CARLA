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
        self.target_role_prefix = args.get("target_role_prefix", args.get("target_role", "tv"))

        self.min_distance = float(args.get("min_distance", 10.0))
        self.time_headway = float(args.get("time_headway", 1.8))
        self.kp_speed = float(args.get("kp_speed", 0.35))
        self.kp_steer = float(args.get("kp_steer", 1.2))
        self.max_throttle = float(args.get("max_throttle", 0.75))
        self.max_brake = float(args.get("max_brake", 0.65))
        self.max_steer = float(args.get("max_steer", 0.6))
        self.waypoint_reached_threshold = float(args.get("waypoint_reached_threshold", 2.0))

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
            ev_lane_id, tv_lane_id = self._get_lane_ids(self._actor, target_actor)
            distance = self._longitudinal_distance(self._actor, target_actor)
            target_speed = self._compute_acc_target_speed(ev_speed, distance)
        else:
            ev_lane_id = None
            tv_lane_id = None
            distance = None
            target_speed = self.desired_speed

        control = self._speed_control(ev_speed, target_speed)
        control.steer = self._waypoint_steer_control()
        self._actor.apply_control(control)

        print(
            "[ACC_CTRL] "
            f"ev={ev_speed:.2f}m/s "
            f"target={target_speed:.2f}m/s "
            f"ev_lane={ev_lane_id if ev_lane_id is not None else 'None'} "
            f"tv_lane={tv_lane_id if tv_lane_id is not None else 'None'} "
            f"waypoints={len(self._waypoints)} "
            f"dist={distance if distance is not None else 'None'}"
        )

    def _find_target_actor(self):
        world = CarlaDataProvider.get_world()
        if world is None:
            return None

        candidates = []

        for actor in world.get_actors().filter("vehicle.*"):
            if actor.id == self._actor.id:
                continue

            role = actor.attributes.get("role_name")
            if not role or not role.startswith(self.target_role_prefix) or not actor.is_alive:
                continue

            if not self._is_same_lane(self._actor, actor):
                continue

            distance = self._longitudinal_distance(self._actor, actor)
            if distance <= 0.0:
                continue

            candidates.append((distance, actor))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

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

    @staticmethod
    def _get_lane_ids(ev, tv):
        world = CarlaDataProvider.get_world()
        if world is None:
            return None, None

        world_map = world.get_map()
        if world_map is None:
            return None, None

        ev_waypoint = AccController._get_waypoint(world_map, ev)
        tv_waypoint = AccController._get_waypoint(world_map, tv)

        return AccController._lane_id(ev_waypoint), AccController._lane_id(tv_waypoint)

    @staticmethod
    def _is_same_lane(ev, tv):
        world = CarlaDataProvider.get_world()
        if world is None:
            return False

        world_map = world.get_map()
        if world_map is None:
            return False

        ev_waypoint = AccController._get_waypoint(world_map, ev)
        tv_waypoint = AccController._get_waypoint(world_map, tv)
        if ev_waypoint is None or tv_waypoint is None:
            return False

        return (
            ev_waypoint.road_id == tv_waypoint.road_id
            and ev_waypoint.lane_id == tv_waypoint.lane_id
        )

    @staticmethod
    def _get_waypoint(world_map, vehicle):
        try:
            return world_map.get_waypoint(
                vehicle.get_location(),
                project_to_road=True,
                lane_type=carla.LaneType.Driving,
            )
        except RuntimeError:
            return None

    @staticmethod
    def _lane_id(waypoint):
        if waypoint is None:
            return None
        return waypoint.lane_id

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

        error = target_speed - current_speed

        if error >= 0:
            control.throttle = min(self.max_throttle, self.kp_speed * error)
            control.brake = 0.0
        else:
            control.throttle = 0.0
            control.brake = min(self.max_brake, self.kp_speed * abs(error))

        return control

    def _waypoint_steer_control(self):
        if not self._waypoints:
            self._reached_goal = False
            return 0.0

        actor_location = self._actor.get_location()
        while (
            self._waypoints
            and self._waypoints[0].location.distance(actor_location) < self.waypoint_reached_threshold
        ):
            self._waypoints = self._waypoints[1:]

        if not self._waypoints:
            self._reached_goal = True
            return 0.0

        self._reached_goal = False
        target_location = self._select_lookahead_waypoint(actor_location)
        actor_transform = self._actor.get_transform()
        heading_error = self._heading_error(actor_transform, target_location)
        steer = self.kp_steer * heading_error
        return max(-self.max_steer, min(self.max_steer, steer))

    def _select_lookahead_waypoint(self, actor_location):
        lookahead_distance = max(4.0, self._get_speed(self._actor) * 0.4)
        target = self._waypoints[0].location
        for waypoint in self._waypoints:
            target = waypoint.location
            if target.distance(actor_location) >= lookahead_distance:
                break
        return target

    @staticmethod
    def _heading_error(actor_transform, target_location):
        actor_location = actor_transform.location
        target_yaw = math.atan2(
            target_location.y - actor_location.y,
            target_location.x - actor_location.x,
        )
        actor_yaw = math.radians(actor_transform.rotation.yaw)
        error = target_yaw - actor_yaw

        while error > math.pi:
            error -= 2.0 * math.pi
        while error < -math.pi:
            error += 2.0 * math.pi

        return error
