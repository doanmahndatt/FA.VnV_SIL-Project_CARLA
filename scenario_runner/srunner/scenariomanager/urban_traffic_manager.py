#!/usr/bin/env python

"""
Background urban traffic support for ScenarioRunner.

The OpenSCENARIO files define the ego and target actors used by ACC/AEB. This
module adds independent Traffic Manager NPCs around them without changing the
scenario actors or their role names.
"""

from __future__ import print_function

import random
import math
from pathlib import Path

import yaml

import carla

try:
    from agents.navigation.basic_agent import BasicAgent
except ImportError:
    BasicAgent = None


class UrbanTrafficManager(object):
    """
    Spawn and clean up Traffic Manager controlled background vehicles.
    """

    def __init__(self, client, world, traffic_manager, traffic_manager_port, config_path=None, profile=None):
        self.client = client
        self.world = world
        self.traffic_manager = traffic_manager
        self.traffic_manager_port = int(traffic_manager_port)
        self.config_path = Path(config_path).resolve() if config_path else None
        self.profile_name = profile
        self.vehicles = []
        self._rng = random.Random()
        self._warned_tm_methods = set()
        self._profile = None
        self._target_count = 0
        self._role_name = "background"
        self._settings_applied_actor_ids = set()
        self._last_status_time = -1.0
        self._status_prints = 0
        self._last_keepalive_time = -1.0
        self._fallback_agents = {}
        self._fallback_red_runners = set()

    def start(self):
        config = self._load_config()
        if not config.get("enabled", True):
            print("[URBAN_TRAFFIC] disabled by config")
            return []

        profile_name = self.profile_name or config.get("default_profile", "urban_acc_aeb")
        profile = (config.get("profiles") or {}).get(profile_name)
        if profile is None:
            raise RuntimeError("Urban traffic profile '{}' not found".format(profile_name))

        seed = int(profile.get("seed", 0))
        self._rng.seed(seed)
        self.traffic_manager.set_random_device_seed(seed)
        self.traffic_manager.set_synchronous_mode(self.world.get_settings().synchronous_mode)
        self._apply_global_tm_settings(profile)

        blueprints = self._select_blueprints(profile)
        spawn_points = self._select_spawn_points(profile)
        configured_count = int(profile.get("vehicle_count", 0))
        max_count = int(profile.get("max_vehicle_count", configured_count))
        target_count = min(configured_count, max_count, len(spawn_points))

        role_name = str(profile.get("role_name", "background"))
        self._profile = profile
        self._target_count = target_count
        self._role_name = role_name
        max_attempts = min(
            len(spawn_points),
            max(target_count, target_count * int(profile.get("spawn_attempt_multiplier", 5)))
        )
        failed_count = 0
        self.vehicles = []
        for spawn_point in spawn_points[:max_attempts]:
            blueprint = self._rng.choice(blueprints)
            if blueprint.has_attribute("role_name"):
                blueprint.set_attribute("role_name", role_name)
            if blueprint.has_attribute("color"):
                colors = blueprint.get_attribute("color").recommended_values
                if colors:
                    blueprint.set_attribute("color", self._rng.choice(colors))
            if blueprint.has_attribute("driver_id"):
                drivers = blueprint.get_attribute("driver_id").recommended_values
                if drivers:
                    blueprint.set_attribute("driver_id", self._rng.choice(drivers))

            vehicle = self.world.try_spawn_actor(
                blueprint,
                self._copy_spawn_transform(spawn_point, profile)
            )
            if vehicle is None:
                failed_count += 1
                if failed_count <= int(profile.get("spawn_failure_log_limit", 5)):
                    print(
                        "[URBAN_TRAFFIC] WARN spawn failed for {} at {}".format(
                            blueprint.id,
                            spawn_point.location,
                        )
                    )
                continue
            self.vehicles.append(vehicle)
            if len(self.vehicles) >= target_count:
                break

        for vehicle in self.vehicles:
            try:
                self._activate_vehicle(vehicle, profile, apply_settings=True)
            except Exception as exc:  # pylint: disable=broad-except
                print("[URBAN_TRAFFIC] WARN vehicle TM settings failed: {}".format(exc))

        self._warm_up_traffic_manager(int(profile.get("warmup_ticks", 5)))
        self._maybe_enable_agent_fallback(profile)
        self.tick(sim_time=0.0, force=True)

        print(
            "[URBAN_TRAFFIC] requested {} background vehicles, spawned {}, moving {}, failed {}".format(
                target_count,
                len(self.vehicles),
                self._moving_vehicle_count(),
                failed_count,
            )
        )
        return self.vehicles

    def destroy(self):
        if not self.vehicles:
            return

        batch = []
        for vehicle in self.vehicles:
            if vehicle is not None and vehicle.is_alive:
                batch.append(carla.command.DestroyActor(vehicle))

        if batch:
            self.client.apply_batch_sync(batch)

        print("[URBAN_TRAFFIC] destroyed {} background vehicles".format(len(batch)))
        self.vehicles = []
        self._settings_applied_actor_ids.clear()
        self._fallback_agents.clear()
        self._fallback_red_runners.clear()

    def tick(self, sim_time=None, force=False):
        """
        Keep Traffic Manager ownership alive during ScenarioRunner execution.

        OpenSCENARIO controllers should only control actors from the scenario file.
        Background vehicles are not registered there, so this only touches actors
        spawned by this class with role_name=background.
        """
        if not self.vehicles or self._profile is None:
            return

        fallback_active = bool(self._fallback_agents)
        keepalive_due = self._is_keepalive_due(sim_time, force) and not fallback_active
        if keepalive_due:
            try:
                self.traffic_manager.set_synchronous_mode(self.world.get_settings().synchronous_mode)
            except Exception as exc:  # pylint: disable=broad-except
                if "set_synchronous_mode" not in self._warned_tm_methods:
                    print("[URBAN_TRAFFIC] WARN TrafficManager.set_synchronous_mode failed: {}".format(exc))
                    self._warned_tm_methods.add("set_synchronous_mode")

        alive = []
        for vehicle in self.vehicles:
            if vehicle is None or not vehicle.is_alive:
                continue
            if vehicle.attributes.get("role_name") != self._role_name:
                continue

            alive.append(vehicle)
            try:
                apply_settings = vehicle.id not in self._settings_applied_actor_ids
                if keepalive_due or apply_settings:
                    self._activate_vehicle(vehicle, self._profile, apply_settings=apply_settings)
            except Exception as exc:  # pylint: disable=broad-except
                print("[URBAN_TRAFFIC] WARN autopilot keepalive failed for {}: {}".format(vehicle.id, exc))

        self.vehicles = alive
        if fallback_active:
            self._run_agent_fallback(alive)
        self._print_runtime_status(sim_time, force=force)

    def _load_config(self):
        if self.config_path is None:
            return {"enabled": False}
        with self.config_path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    def _select_blueprints(self, profile):
        library = self.world.get_blueprint_library()
        blueprints = list(library.filter(str(profile.get("blueprint_filter", "vehicle.*"))))
        keywords = [str(item).lower() for item in profile.get("blueprint_model_keywords", [])]
        if keywords:
            blueprints = [bp for bp in blueprints if any(keyword in bp.id.lower() for keyword in keywords)]

        blueprints = [
            bp
            for bp in blueprints
            if bp.has_attribute("number_of_wheels")
            and int(bp.get_attribute("number_of_wheels")) == 4
        ]
        if not blueprints:
            raise RuntimeError("No vehicle blueprints matched urban traffic config")
        return blueprints

    def _select_spawn_points(self, profile):
        spawn_points = list(self.world.get_map().get_spawn_points())
        self._rng.shuffle(spawn_points)

        existing_locations = []
        ego_locations = []
        protected_locations = []
        for actor in self.world.get_actors().filter("vehicle.*"):
            role = actor.attributes.get("role_name", "")
            location = actor.get_location()
            existing_locations.append(location)
            if role in ("ev", "ego", "hero"):
                ego_locations.append(location)
                protected_locations.append(location)
            elif role.startswith("tv"):
                protected_locations.append(location)

        # Resolve ego reference waypoint for topology-based filters
        ego_waypoint = None
        if ego_locations:
            ref_loc = self._select_reference_ego_location(ego_locations)
            ego_waypoint = self.world.get_map().get_waypoint(
                ref_loc, project_to_road=True, lane_type=carla.LaneType.Driving
            )

        # Topology filters — applied before distance-based selection
        if ego_waypoint is not None:
            if bool(profile.get("require_opposite_heading", False)) or bool(profile.get("spawn_only_opposite_lane", False)):
                before = len(spawn_points)
                spawn_points = self._filter_opposite_heading(spawn_points, ego_waypoint)
                print("[URBAN_TRAFFIC] opposite_heading: {} -> {} spawn candidates".format(
                    before, len(spawn_points)))

            if bool(profile.get("exclude_same_lane_as_ego", False)):
                spawn_points = [
                    sp for sp in spawn_points
                    if not self._same_lane_as_waypoint(sp.location, ego_waypoint)
                ]

            if bool(profile.get("exclude_same_lane_id_globally", False)):
                spawn_points = [
                    sp for sp in spawn_points
                    if not self._same_lane_id_as_waypoint(sp.location, ego_waypoint)
                ]

            if bool(profile.get("require_same_road_as_ego", False)):
                spawn_points = [
                    sp for sp in spawn_points
                    if self._on_same_road(sp.location, ego_waypoint)
                ]

        if bool(profile.get("avoid_junction_spawn", False)):
            spawn_points = [
                sp for sp in spawn_points
                if not self._at_junction(sp.location)
            ]

        safe_radius = float(profile.get("safe_radius_around_existing_vehicles", 0.0))
        ego_radius = float(profile.get("safe_radius_around_ego", safe_radius))
        min_ego_distance = float(profile.get("min_spawn_distance_from_ego", 0.0))
        max_ego_distance = float(profile.get("max_spawn_distance_from_ego", 0.0))
        min_spacing = float(profile.get("min_spawn_spacing", 0.0))
        selected = []

        if ego_locations:
            ego_locations = [self._select_reference_ego_location(ego_locations)]

        if ego_locations and bool(profile.get("prefer_spawn_near_ego", True)):
            preferred_road_ids = self._preferred_road_ids(profile)
            spawn_points.sort(
                key=lambda item: (
                    0 if self._road_id(item.location) in preferred_road_ids else 1,
                    self._distance_to_nearest(item.location, ego_locations)
                    + self._rng.uniform(0.0, 4.0),
                )
            )

        for spawn_point in spawn_points:
            location = spawn_point.location
            if ego_locations and max_ego_distance > 0:
                distance_to_ego = self._distance_to_nearest(location, ego_locations)
                if distance_to_ego > max_ego_distance:
                    continue
                if distance_to_ego < min_ego_distance:
                    continue
            if self._too_close(location, existing_locations, safe_radius):
                continue
            if self._too_close(location, protected_locations, ego_radius):
                continue
            if self._too_close(location, [item.location for item in selected], min_spacing):
                continue
            selected.append(spawn_point)

        return selected

    def _filter_opposite_heading(self, spawn_points, ego_waypoint, tolerance_deg=65.0):
        """Keep only spawn points whose road heading is ~180 deg opposite to ego."""
        ego_yaw = ego_waypoint.transform.rotation.yaw
        result = []
        for sp in spawn_points:
            wp = self.world.get_map().get_waypoint(
                sp.location, project_to_road=True, lane_type=carla.LaneType.Driving
            )
            if wp is None:
                continue
            diff = abs(self._normalize_degrees(wp.transform.rotation.yaw - ego_yaw))
            # Accept headings in the range [180-tol, 180+tol] degrees apart
            if diff >= 180.0 - tolerance_deg:
                result.append(sp)
        return result

    def _same_lane_as_waypoint(self, location, ego_waypoint):
        """True when location projects onto the exact same lane as ego_waypoint."""
        wp = self.world.get_map().get_waypoint(
            location, project_to_road=True, lane_type=carla.LaneType.Driving
        )
        if wp is None or ego_waypoint is None:
            return False
        return wp.road_id == ego_waypoint.road_id and wp.lane_id == ego_waypoint.lane_id

    def _same_lane_id_as_waypoint(self, location, ego_waypoint):
        """True when location projects onto any lane with the same signed lane_id as ego."""
        wp = self.world.get_map().get_waypoint(
            location, project_to_road=True, lane_type=carla.LaneType.Driving
        )
        if wp is None or ego_waypoint is None:
            return False
        return wp.lane_id == ego_waypoint.lane_id

    def _on_same_road(self, location, ego_waypoint):
        """True when location is on the same road_id as ego_waypoint (any lane/direction)."""
        wp = self.world.get_map().get_waypoint(
            location, project_to_road=True, lane_type=carla.LaneType.Driving
        )
        return wp is not None and wp.road_id == ego_waypoint.road_id

    def _road_id(self, location):
        wp = self.world.get_map().get_waypoint(
            location, project_to_road=True, lane_type=carla.LaneType.Driving
        )
        return wp.road_id if wp is not None else None

    @staticmethod
    def _preferred_road_ids(profile):
        road_ids = set()
        for value in profile.get("preferred_road_ids", []) or []:
            try:
                road_ids.add(int(value))
            except (TypeError, ValueError):
                continue
        return road_ids

    def _at_junction(self, location):
        """True when location projects onto a junction waypoint."""
        wp = self.world.get_map().get_waypoint(
            location, project_to_road=True, lane_type=carla.LaneType.Driving
        )
        return wp is not None and wp.is_junction

    @staticmethod
    def _distance_to_nearest(location, locations):
        if not locations:
            return float("inf")
        return min(location.distance(other) for other in locations)

    @staticmethod
    def _select_reference_ego_location(locations):
        if len(locations) == 1:
            return locations[0]
        center_x = sum(location.x for location in locations) / len(locations)
        center_y = sum(location.y for location in locations) / len(locations)
        center_z = sum(location.z for location in locations) / len(locations)
        center = carla.Location(x=center_x, y=center_y, z=center_z)
        return min(locations, key=lambda location: location.distance(center))

    @staticmethod
    def _too_close(location, locations, radius):
        if radius <= 0:
            return False
        return any(location.distance(other) < radius for other in locations)

    @staticmethod
    def _copy_spawn_transform(spawn_point, profile):
        z_offset = float(profile.get("spawn_z_offset", 0.35))
        return carla.Transform(
            carla.Location(
                x=spawn_point.location.x,
                y=spawn_point.location.y,
                z=spawn_point.location.z + z_offset,
            ),
            carla.Rotation(
                pitch=spawn_point.rotation.pitch,
                yaw=spawn_point.rotation.yaw,
                roll=spawn_point.rotation.roll,
            ),
        )

    def _apply_global_tm_settings(self, profile):
        if "global_distance_to_leading_vehicle" in profile:
            self._tm_call(
                "set_global_distance_to_leading_vehicle",
                float(profile["global_distance_to_leading_vehicle"])
            )
        if "global_percentage_speed_difference" in profile:
            self._tm_call(
                "global_percentage_speed_difference",
                float(profile["global_percentage_speed_difference"])
            )
        if bool(profile.get("hybrid_physics_mode", False)):
            self._tm_call("set_hybrid_physics_mode", True)
            self._tm_call(
                "set_hybrid_physics_radius",
                float(profile.get("hybrid_physics_radius", 70.0))
            )
        if bool(profile.get("respawn_dormant_vehicles", False)):
            self._tm_call("set_respawn_dormant_vehicles", True)

    def _apply_vehicle_tm_settings(self, vehicle, profile):
        if bool(profile.get("vehicle_lights", True)):
            self._tm_call("update_vehicle_lights", vehicle, True)

        self._tm_call("auto_lane_change", vehicle, bool(profile.get("auto_lane_change", True)))
        self._tm_call(
            "vehicle_percentage_speed_difference",
            vehicle, self._range_value(profile, "per_vehicle_speed_difference_range", 0.0)
        )
        self._tm_call("ignore_lights_percentage", vehicle, self._traffic_light_ignore_percent(profile))
        self._tm_call(
            "ignore_signs_percentage",
            vehicle, self._range_value(profile, "ignore_signs_percentage_range", 0.0)
        )
        self._tm_call(
            "ignore_walkers_percentage",
            vehicle, self._range_value(profile, "ignore_walkers_percentage_range", 0.0)
        )
        self._tm_call(
            "random_left_lanechange_percentage",
            vehicle, self._range_value(profile, "random_left_lanechange_percentage_range", 0.0)
        )
        self._tm_call(
            "random_right_lanechange_percentage",
            vehicle, self._range_value(profile, "random_right_lanechange_percentage_range", 0.0)
        )
        if "desired_speed_kph_range" in profile:
            self._tm_call(
                "set_desired_speed",
                vehicle,
                self._range_value(profile, "desired_speed_kph_range", 30.0)
            )
        elif "desired_speed_kph" in profile:
            self._tm_call("set_desired_speed", vehicle, float(profile["desired_speed_kph"]))

        self._settings_applied_actor_ids.add(vehicle.id)

    def _activate_vehicle(self, vehicle, profile, apply_settings):
        vehicle.set_simulate_physics(True)
        vehicle.set_autopilot(True, self.traffic_manager_port)
        if apply_settings:
            self._apply_vehicle_tm_settings(vehicle, profile)

    def _maybe_enable_agent_fallback(self, profile):
        if not bool(profile.get("agent_fallback_enabled", True)):
            return
        if BasicAgent is None:
            print("[URBAN_TRAFFIC] WARN BasicAgent fallback unavailable")
            return

        min_moving = int(profile.get("fallback_min_moving_after_warmup", 3))
        if self._moving_vehicle_count() >= min_moving:
            return

        for vehicle in self.vehicles:
            if vehicle is None or not vehicle.is_alive:
                continue
            self._create_agent_fallback(vehicle, profile)

        if self._fallback_agents:
            print(
                "[URBAN_TRAFFIC] TM autopilot produced low movement; "
                "using {} fallback for {} background vehicles".format(
                    profile.get("agent_fallback_mode", "lane_follow"),
                    len(self._fallback_agents)
                )
            )

    def _create_agent_fallback(self, vehicle, profile):
        try:
            red_runner = self._rng.uniform(0.0, 100.0) < float(
                profile.get("red_light_runner_percentage", 0.0)
            )
            vehicle.set_autopilot(False, self.traffic_manager_port)
            vehicle.set_simulate_physics(True)
            if profile.get("agent_fallback_mode", "lane_follow") == "lane_follow":
                self._fallback_agents[vehicle.id] = {
                    "target_speed_mps": self._range_value(
                        profile,
                        "desired_speed_kph_range",
                        30.0
                    ) / 3.6,
                    "red_runner": red_runner,
                }
                if red_runner:
                    self._fallback_red_runners.add(vehicle.id)
                return

            opt_dict = {
                "ignore_traffic_lights": red_runner,
                "ignore_vehicles": bool(profile.get("agent_ignore_vehicles", True)),
            }
            agent = BasicAgent(
                vehicle,
                target_speed=self._range_value(profile, "desired_speed_kph_range", 30.0),
                opt_dict=opt_dict,
                map_inst=self.world.get_map(),
            )
            if red_runner:
                self._fallback_red_runners.add(vehicle.id)
            self._set_agent_destination(agent, vehicle, profile)
            self._fallback_agents[vehicle.id] = agent
        except Exception as exc:  # pylint: disable=broad-except
            print("[URBAN_TRAFFIC] WARN BasicAgent setup failed for {}: {}".format(vehicle.id, exc))

    def _run_agent_fallback(self, vehicles):
        alive_ids = set()
        for vehicle in vehicles:
            alive_ids.add(vehicle.id)
            agent = self._fallback_agents.get(vehicle.id)
            if agent is None:
                self._create_agent_fallback(vehicle, self._profile)
                agent = self._fallback_agents.get(vehicle.id)
            if agent is None:
                continue

            try:
                if isinstance(agent, dict):
                    self._run_lane_follow_step(vehicle, agent)
                    continue
                if agent.done():
                    self._set_agent_destination(agent, vehicle, self._profile)
                vehicle.apply_control(agent.run_step())
            except Exception as exc:  # pylint: disable=broad-except
                print("[URBAN_TRAFFIC] WARN fallback step failed for {}: {}".format(vehicle.id, exc))

        for actor_id in list(self._fallback_agents):
            if actor_id not in alive_ids:
                self._fallback_agents.pop(actor_id, None)
                self._fallback_red_runners.discard(actor_id)

    def _set_agent_destination(self, agent, vehicle, profile):
        destination = self._random_destination(vehicle, profile)
        if destination is not None:
            agent.set_destination(destination, vehicle.get_location())

    def _run_lane_follow_step(self, vehicle, state):
        transform = vehicle.get_transform()
        location = transform.location
        waypoint = self.world.get_map().get_waypoint(
            location,
            project_to_road=True,
            lane_type=carla.LaneType.Driving,
        )
        if waypoint is None:
            return

        next_waypoints = waypoint.next(8.0)
        if not next_waypoints:
            next_waypoints = waypoint.next(3.0)
        if not next_waypoints:
            return

        target_waypoint = self._rng.choice(next_waypoints) if len(next_waypoints) > 1 else next_waypoints[0]
        target_location = target_waypoint.transform.location
        dx = target_location.x - location.x
        dy = target_location.y - location.y
        target_yaw = math.degrees(math.atan2(dy, dx))
        yaw_error = self._normalize_degrees(target_yaw - transform.rotation.yaw)
        steer = max(-0.55, min(0.55, yaw_error / 45.0))

        velocity = vehicle.get_velocity()
        speed = (velocity.x * velocity.x + velocity.y * velocity.y) ** 0.5
        target_speed = float(state["target_speed_mps"])

        if bool(self._profile.get("collision_avoidance_enabled", False)):
            forward_distance = self._forward_vehicle_distance(vehicle)
            brake_distance = float(self._profile.get("collision_brake_distance_m", 12.0))
            slow_distance = float(self._profile.get("collision_slow_distance_m", 26.0))

            if forward_distance < brake_distance:
                vehicle.apply_control(carla.VehicleControl(throttle=0.0, steer=steer, brake=0.8))
                return

            if forward_distance < slow_distance:
                scale = (forward_distance - brake_distance) / max(slow_distance - brake_distance, 1.0)
                target_speed *= 0.2 + 0.8 * max(0.0, min(1.0, scale))

        stop_for_light = (
            not state.get("red_runner", False)
            and vehicle.is_at_traffic_light()
            and vehicle.get_traffic_light_state() == carla.TrafficLightState.Red
        )
        if stop_for_light:
            control = carla.VehicleControl(throttle=0.0, steer=steer, brake=0.8)
        elif speed < target_speed:
            control = carla.VehicleControl(throttle=0.45, steer=steer, brake=0.0)
        elif speed > target_speed * 1.15:
            control = carla.VehicleControl(throttle=0.0, steer=steer, brake=0.25)
        else:
            control = carla.VehicleControl(throttle=0.12, steer=steer, brake=0.0)

        vehicle.apply_control(control)

    def _forward_vehicle_distance(self, vehicle):
        """
        Distance to the nearest vehicle ahead inside the configured lateral window.
        Used only by the lane_follow fallback, where CARLA TM avoidance is bypassed.
        """
        transform = vehicle.get_transform()
        forward = transform.get_forward_vector()
        location = transform.location
        lateral_window = float(self._profile.get("collision_lateral_window_m", 3.5))
        nearest = float("inf")

        for other in self.world.get_actors().filter("vehicle.*"):
            if other.id == vehicle.id or not other.is_alive:
                continue

            other_location = other.get_location()
            delta_x = other_location.x - location.x
            delta_y = other_location.y - location.y
            along = delta_x * forward.x + delta_y * forward.y
            if along < 1.0:
                continue

            lateral = abs(delta_x * (-forward.y) + delta_y * forward.x)
            if lateral < lateral_window:
                nearest = min(nearest, along)

        return nearest

    @staticmethod
    def _normalize_degrees(angle):
        while angle > 180.0:
            angle -= 360.0
        while angle < -180.0:
            angle += 360.0
        return angle

    def _random_destination(self, vehicle, profile):
        spawn_points = list(self.world.get_map().get_spawn_points())
        if not spawn_points:
            return None

        min_distance = float(profile.get("agent_min_route_distance", 40.0))
        origin = vehicle.get_location()
        candidates = [sp.location for sp in spawn_points if sp.location.distance(origin) >= min_distance]
        if not candidates:
            candidates = [sp.location for sp in spawn_points]
        return self._rng.choice(candidates)

    def _range_value(self, profile, key, default):
        values = profile.get(key)
        if not values:
            return float(default)
        lower, upper = float(values[0]), float(values[1])
        return self._rng.uniform(lower, upper)

    def _traffic_light_ignore_percent(self, profile):
        runner_chance = float(profile.get("red_light_runner_percentage", 0.0))
        if self._rng.uniform(0.0, 100.0) < runner_chance:
            return float(profile.get("red_light_runner_ignore_lights_percentage", 100.0))
        return float(profile.get("normal_driver_ignore_lights_percentage", 0.0))

    def _warm_up_traffic_manager(self, ticks):
        ticks = max(1, int(ticks))
        for _ in range(ticks):
            if self.world.get_settings().synchronous_mode:
                self.world.tick()
            else:
                self.world.wait_for_tick()

    def _moving_vehicle_count(self):
        moving = 0
        for vehicle in self.vehicles:
            if vehicle is None or not vehicle.is_alive:
                continue
            velocity = vehicle.get_velocity()
            speed = (velocity.x * velocity.x + velocity.y * velocity.y) ** 0.5
            if speed > 0.2:
                moving += 1
        return moving

    def _is_keepalive_due(self, sim_time, force):
        if force:
            if sim_time is not None:
                self._last_keepalive_time = sim_time
            return True
        if sim_time is None:
            return True

        interval = float(self._profile.get("keepalive_interval", 1.0))
        if self._last_keepalive_time < 0.0 or sim_time - self._last_keepalive_time >= interval:
            self._last_keepalive_time = sim_time
            return True
        return False

    def _print_runtime_status(self, sim_time, force=False):
        if sim_time is None:
            return

        interval = float(self._profile.get("status_log_interval", 2.0))
        max_prints = int(self._profile.get("status_log_count", 5))
        if not force:
            if self._status_prints >= max_prints:
                return
            if self._last_status_time >= 0.0 and sim_time - self._last_status_time < interval:
                return

        self._last_status_time = sim_time
        self._status_prints += 1
        min_distance, max_distance = self._distance_range_to_reference_ego()
        print(
            "[URBAN_TRAFFIC] runtime active={} moving={} dist_to_ev={} sync={} tm_port={}".format(
                len(self.vehicles),
                self._moving_vehicle_count(),
                self._format_distance_range(min_distance, max_distance),
                self.world.get_settings().synchronous_mode,
                self.traffic_manager_port,
            )
        )

    def _distance_range_to_reference_ego(self):
        ego_location = self._current_reference_ego_location()
        if ego_location is None:
            return None, None

        distances = [
            ego_location.distance(vehicle.get_location())
            for vehicle in self.vehicles
            if vehicle is not None and vehicle.is_alive
        ]
        if not distances:
            return None, None
        return min(distances), max(distances)

    def _current_reference_ego_location(self):
        locations = []
        for actor in self.world.get_actors().filter("vehicle.*"):
            if actor.attributes.get("role_name", "") in ("ev", "ego", "hero"):
                locations.append(actor.get_location())
        if not locations:
            return None
        return self._select_reference_ego_location(locations)

    @staticmethod
    def _format_distance_range(min_distance, max_distance):
        if min_distance is None or max_distance is None:
            return "n/a"
        return "{:.1f}-{:.1f}m".format(min_distance, max_distance)

    def _spawn_leading_tvs(self, profile):
        """
        Disabled for ADAS demos: background traffic must not create same-direction
        leading TVs that can interfere with EV lane behavior or OpenSCENARIO TVs.
        """
        return

        cfg = profile.get("leading_tv", {})
        if not bool(cfg.get("enabled", False)):
            return

        ego_wp = self._ego_waypoint()
        if ego_wp is None:
            print("[URBAN_TRAFFIC] leading_tv: ego not found, skipping")
            return

        adj_wp = self._same_direction_adjacent_lane(ego_wp)
        if adj_wp is None:
            print("[URBAN_TRAFFIC] leading_tv: no same-direction adjacent lane found, skipping")
            return

        turn_dests = self._junction_turn_destinations(adj_wp, max_dist=90.0)
        blueprints = self._select_blueprints(profile)
        role_name = str(profile.get("role_name", "background"))
        z_offset = float(profile.get("spawn_z_offset", 0.35))
        ahead_distances = cfg.get("ahead_distances_m", [14.0, 30.0])
        count = 0

        for idx, dist in enumerate(ahead_distances[:2]):
            wps = adj_wp.next(float(dist))
            if not wps:
                print("[URBAN_TRAFFIC] leading_tv: no waypoint at {:.0f}m ahead".format(dist))
                continue
            target_wp = wps[0]

            bp = self._rng.choice(blueprints)
            if bp.has_attribute("role_name"):
                bp.set_attribute("role_name", role_name)
            if bp.has_attribute("color"):
                colors = bp.get_attribute("color").recommended_values
                if colors:
                    bp.set_attribute("color", self._rng.choice(colors))

            spawn_tf = carla.Transform(
                carla.Location(
                    x=target_wp.transform.location.x,
                    y=target_wp.transform.location.y,
                    z=target_wp.transform.location.z + z_offset,
                ),
                target_wp.transform.rotation,
            )
            vehicle = self.world.try_spawn_actor(bp, spawn_tf)
            if vehicle is None:
                print("[URBAN_TRAFFIC] leading_tv: spawn failed at {:.0f}m".format(dist))
                continue

            speed_kph = self._range_value(cfg, "desired_speed_kph_range", 32.0)
            dest = turn_dests[idx] if idx < len(turn_dests) else None

            vehicle.set_simulate_physics(True)
            if dest is not None and BasicAgent is not None:
                try:
                    agent = BasicAgent(
                        vehicle,
                        target_speed=speed_kph,
                        opt_dict={"ignore_traffic_lights": False, "ignore_vehicles": False},
                        map_inst=self.world.get_map(),
                    )
                    agent.set_destination(dest, vehicle.get_location())
                    self._fallback_agents[vehicle.id] = agent
                except Exception as exc:  # pylint: disable=broad-except
                    print("[URBAN_TRAFFIC] leading_tv: BasicAgent failed ({}), using TM".format(exc))
                    vehicle.set_autopilot(True, self.traffic_manager_port)
                    self._apply_leading_tm_settings(vehicle, speed_kph)
            else:
                vehicle.set_autopilot(True, self.traffic_manager_port)
                self._apply_leading_tm_settings(vehicle, speed_kph)

            self._tm_call("update_vehicle_lights", vehicle, True)
            self._settings_applied_actor_ids.add(vehicle.id)
            self.vehicles.append(vehicle)
            count += 1

        print("[URBAN_TRAFFIC] leading_tv: spawned {} TVs in adjacent lane ({} turn destinations found)".format(
            count, len(turn_dests)))

    def _apply_leading_tm_settings(self, vehicle, speed_kph):
        self._tm_call("set_desired_speed", vehicle, speed_kph)
        self._tm_call("auto_lane_change", vehicle, False)
        self._tm_call("ignore_lights_percentage", vehicle, 0.0)
        self._tm_call("ignore_signs_percentage", vehicle, 0.0)

    def _ego_waypoint(self):
        for actor in self.world.get_actors().filter("vehicle.*"):
            if actor.attributes.get("role_name", "") in ("ev", "ego", "hero"):
                return self.world.get_map().get_waypoint(
                    actor.get_location(), project_to_road=True, lane_type=carla.LaneType.Driving
                )
        return None

    def _same_direction_adjacent_lane(self, ego_wp, yaw_tolerance=45.0):
        """Return the nearest drivable adjacent lane going in the same direction as ego_wp."""
        for get_lane in (ego_wp.get_left_lane, ego_wp.get_right_lane):
            adj = get_lane()
            if adj is None or adj.lane_type != carla.LaneType.Driving:
                continue
            yaw_diff = abs(self._normalize_degrees(
                adj.transform.rotation.yaw - ego_wp.transform.rotation.yaw
            ))
            if yaw_diff <= yaw_tolerance:
                return adj
        return None

    def _junction_turn_destinations(self, start_wp, max_dist=90.0):
        """
        Walk forward from start_wp to find the next junction.
        Return 2 destinations past that junction — one for each turn direction —
        so the 2 leading TVs split at the intersection.
        """
        current = start_wp
        walked = 0.0
        step = 3.0

        while walked < max_dist:
            nexts = current.next(step)
            if not nexts:
                break
            current = nexts[0]
            walked += step
            if current.is_junction:
                break

        if not current.is_junction:
            return []

        try:
            junction = current.get_junction()
            all_pairs = junction.get_waypoints(carla.LaneType.Driving)
        except Exception:  # pylint: disable=broad-except
            return []

        entry_yaw = start_wp.transform.rotation.yaw
        buckets = {"neg": [], "pos": []}
        for _, exit_wp in all_pairs:
            if exit_wp.is_junction:
                continue
            yaw_diff = self._normalize_degrees(exit_wp.transform.rotation.yaw - entry_yaw)
            if abs(yaw_diff) < 20.0:
                continue
            buckets["pos" if yaw_diff > 0 else "neg"].append(exit_wp)

        destinations = []
        for key in ("neg", "pos"):
            if not buckets[key]:
                continue
            exit_wp = buckets[key][0]
            further = exit_wp.next(25.0)
            dest_wp = further[0] if further else exit_wp
            destinations.append(dest_wp.transform.location)

        return destinations

    def _tm_call(self, method_name, *args):
        method = getattr(self.traffic_manager, method_name, None)
        if method is None:
            if method_name not in self._warned_tm_methods:
                print("[URBAN_TRAFFIC] WARN TrafficManager has no '{}'".format(method_name))
                self._warned_tm_methods.add(method_name)
            return None

        try:
            return method(*args)
        except Exception as exc:  # pylint: disable=broad-except
            if method_name not in self._warned_tm_methods:
                print("[URBAN_TRAFFIC] WARN TrafficManager.{} failed: {}".format(method_name, exc))
                self._warned_tm_methods.add(method_name)
            return None
