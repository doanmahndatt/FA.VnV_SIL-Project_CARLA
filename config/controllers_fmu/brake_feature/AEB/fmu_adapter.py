import argparse
import math
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import carla

try:
    import yaml
except ImportError as exc:
    raise ImportError("Missing dependency: pyyaml. Install with: pip install pyyaml") from exc

try:
    from fmpy import extract, read_model_description
    from fmpy.fmi2 import FMU2Slave
except ImportError as exc:
    raise ImportError("Missing dependency: fmpy. Install with: pip install fmpy") from exc


DEFAULT_INPUTS = {
    "ego_speed": 0.0,
    "lead_distance": 999.0,
    "lead_speed": 0.0,
    "target_speed": 20.0,
    "heading_error": 0.0,
    "has_lead": 0.0,
    "has_waypoint": 0.0,
    "min_distance": 4.5,
    "warning_ttc": 1.8,
    "brake_ttc": 1.0,
    "emergency_ttc": 0.55,
    "kp_speed": 0.35,
    "kp_brake": 0.45,
    "max_throttle": 0.75,
    "max_brake": 1.0,
    "brake_hold_time": 0.5,
    "hard_brake_distance": 3.2,
    "park_speed_threshold": 0.25,
    "park_hold_delay": 1.5,
    "kp_steer": 1.2,
    "max_steer": 0.6,
}

DEFAULT_OUTPUTS = (
    "throttle",
    "brake",
    "steer",
    "deceleration",
    "ttc",
    "relative_speed",
    "safe_distance",
    "distance_error",
    "aeb_state",
    "hand_brake",
    "manual_gear_shift",
    "gear",
)


@dataclass(frozen=True)
class AEBParameters:
    target_speed: float = 20.0
    min_distance: float = 4.5
    warning_ttc: float = 1.8
    brake_ttc: float = 1.0
    emergency_ttc: float = 0.55
    kp_speed: float = 0.35
    kp_brake: float = 0.45
    max_throttle: float = 0.75
    max_brake: float = 1.0
    brake_hold_time: float = 0.5
    hard_brake_distance: float = 3.2
    park_speed_threshold: float = 0.25
    park_hold_delay: float = 1.5
    kp_steer: float = 1.2
    max_steer: float = 0.6
    waypoint_reached_threshold: float = 2.0

    @classmethod
    def from_args(cls, args: dict | None) -> "AEBParameters":
        args = args or {}
        return cls(
            target_speed=_float_arg(args, "target_speed", _float_arg(args, "desired_speed", 20.0)),
            min_distance=_float_arg(args, "min_distance", 4.5),
            warning_ttc=_float_arg(args, "warning_ttc", 1.8),
            brake_ttc=_float_arg(args, "brake_ttc", 1.0),
            emergency_ttc=_float_arg(args, "emergency_ttc", 0.55),
            kp_speed=_float_arg(args, "kp_speed", 0.35),
            kp_brake=_float_arg(args, "kp_brake", 0.45),
            max_throttle=_float_arg(args, "max_throttle", 0.75),
            max_brake=_float_arg(args, "max_brake", 1.0),
            brake_hold_time=_float_arg(args, "brake_hold_time", 0.5),
            hard_brake_distance=_float_arg(args, "hard_brake_distance", 3.2),
            park_speed_threshold=_float_arg(args, "park_speed_threshold", 0.25),
            park_hold_delay=_float_arg(args, "park_hold_delay", 1.5),
            kp_steer=_float_arg(args, "kp_steer", 1.2),
            max_steer=_float_arg(args, "max_steer", 0.6),
            waypoint_reached_threshold=_float_arg(args, "waypoint_reached_threshold", 2.0),
        )

    def as_fmu_inputs(self) -> dict[str, float]:
        return {
            "target_speed": self.target_speed,
            "min_distance": self.min_distance,
            "warning_ttc": self.warning_ttc,
            "brake_ttc": self.brake_ttc,
            "emergency_ttc": self.emergency_ttc,
            "kp_speed": self.kp_speed,
            "kp_brake": self.kp_brake,
            "max_throttle": self.max_throttle,
            "max_brake": self.max_brake,
            "brake_hold_time": self.brake_hold_time,
            "hard_brake_distance": self.hard_brake_distance,
            "park_speed_threshold": self.park_speed_threshold,
            "park_hold_delay": self.park_hold_delay,
            "kp_steer": self.kp_steer,
            "max_steer": self.max_steer,
        }


@dataclass(frozen=True)
class AEBSignals:
    ego_speed: float
    lead_distance: float
    lead_speed: float
    heading_error: float
    has_lead: bool
    has_waypoint: bool

    def as_fmu_inputs(self) -> dict[str, float]:
        return {
            "ego_speed": self.ego_speed,
            "lead_distance": self.lead_distance,
            "lead_speed": self.lead_speed,
            "heading_error": self.heading_error,
            "has_lead": 1.0 if self.has_lead else 0.0,
            "has_waypoint": 1.0 if self.has_waypoint else 0.0,
        }


class AEBFmuRuntime:
    def __init__(
        self,
        fmu_path: Path,
        input_names: Iterable[str] | None = None,
        output_names: Iterable[str] | None = None,
    ):
        self.fmu_path = Path(fmu_path).resolve()
        if not self.fmu_path.exists():
            raise FileNotFoundError(f"FMU not found: {self.fmu_path}")

        self.input_names = tuple(input_names or DEFAULT_INPUTS.keys())
        self.output_names = tuple(output_names or DEFAULT_OUTPUTS)
        self.unzipdir = Path(tempfile.mkdtemp(prefix="aeb_fmu_"))
        extract(str(self.fmu_path), unzipdir=str(self.unzipdir))
        self.model_description = read_model_description(str(self.fmu_path))

        if self.model_description.coSimulation is None:
            raise ValueError("AEB FMU must expose an FMI 2.0 Co-Simulation interface")

        self.vr = {
            variable.name: variable.valueReference
            for variable in self.model_description.modelVariables
        }

        self._validate_variables()

        self.fmu = FMU2Slave(
            guid=self.model_description.guid,
            unzipDirectory=str(self.unzipdir),
            modelIdentifier=self.model_description.coSimulation.modelIdentifier,
            instanceName="AEBControllerInstance",
        )

        self.current_time = 0.0
        self.initialized = False

    def _validate_variables(self):
        missing = [name for name in [*self.input_names, *self.output_names] if name not in self.vr]
        if missing:
            raise ValueError(
                "FMU variable mismatch. Rebuild AEB_controller.fmu from AEBController.py. "
                "Missing variables in modelDescription.xml: " + ", ".join(missing)
            )

    def initialize(self):
        if self.initialized:
            return

        self.fmu.instantiate()
        self.fmu.setupExperiment(startTime=0.0)
        self.fmu.enterInitializationMode()
        self.fmu.exitInitializationMode()
        self.initialized = True

    def step(self, values: dict[str, float], dt: float) -> dict[str, float]:
        if not self.initialized:
            self.initialize()

        merged = dict(DEFAULT_INPUTS)
        merged.update(values)

        self.fmu.setReal(
            [self.vr[name] for name in self.input_names],
            [float(merged[name]) for name in self.input_names],
        )
        self.fmu.doStep(
            currentCommunicationPoint=self.current_time,
            communicationStepSize=float(dt),
        )
        self.current_time += float(dt)

        output_values = self.fmu.getReal([self.vr[name] for name in self.output_names])
        return {name: float(value) for name, value in zip(self.output_names, output_values)}

    def terminate(self):
        if self.initialized:
            try:
                self.fmu.terminate()
            finally:
                self.fmu.freeInstance()
                self.initialized = False

        if self.unzipdir.exists():
            shutil.rmtree(self.unzipdir, ignore_errors=True)


class CarlaAEBSignalAdapter:
    def __init__(
        self,
        ego,
        target_role_prefix: str = "tv",
        waypoint_reached_threshold: float = 2.0,
        world_getter=None,
    ):
        self.ego = ego
        self.target_role_prefix = target_role_prefix
        self.waypoint_reached_threshold = float(waypoint_reached_threshold)
        self.world_getter = world_getter

    def sample(self, waypoints=None) -> AEBSignals:
        waypoints = waypoints or []
        world = self._get_world()
        target = self._find_target_actor(world)
        ego_speed = get_speed(self.ego)

        if target is not None:
            lead_distance = longitudinal_distance(self.ego, target)
            lead_speed = get_speed(target)
            has_lead = True
        else:
            lead_distance = 999.0
            lead_speed = ego_speed
            has_lead = False

        heading_error, has_waypoint = self._heading_error_from_waypoints(waypoints)

        return AEBSignals(
            ego_speed=ego_speed,
            lead_distance=lead_distance,
            lead_speed=lead_speed,
            heading_error=heading_error,
            has_lead=has_lead,
            has_waypoint=has_waypoint,
        )

    def prune_reached_waypoints(self, waypoints):
        actor_location = self.ego.get_location()
        while (
            waypoints
            and waypoints[0].location.distance(actor_location) < self.waypoint_reached_threshold
        ):
            waypoints = waypoints[1:]
        return waypoints

    def _get_world(self):
        if self.world_getter is not None:
            return self.world_getter()
        return self.ego.get_world()

    def _find_target_actor(self, world):
        if world is None:
            return None

        candidates = []
        for actor in world.get_actors().filter("vehicle.*"):
            if actor.id == self.ego.id or not actor.is_alive:
                continue

            role = actor.attributes.get("role_name", "")
            if not role.startswith(self.target_role_prefix):
                continue

            if not is_same_lane(world, self.ego, actor):
                continue

            distance = longitudinal_distance(self.ego, actor)
            if distance <= 0.0:
                continue

            candidates.append((distance, actor))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _heading_error_from_waypoints(self, waypoints):
        if not waypoints:
            return 0.0, False

        actor_location = self.ego.get_location()
        lookahead_distance = max(4.0, get_speed(self.ego) * 0.4)
        target_location = waypoints[0].location
        for waypoint in waypoints:
            target_location = waypoint.location
            if target_location.distance(actor_location) >= lookahead_distance:
                break

        return heading_error(self.ego.get_transform(), target_location), True


class CarlaAEBAdapter:
    def __init__(
        self,
        host: str,
        port: int,
        timeout_s: float,
        ego_role_name: str,
        target_role_prefix: str,
        fixed_delta_seconds: float,
        fmu_runtime: AEBFmuRuntime,
        parameters: AEBParameters,
    ):
        self.client = carla.Client(host, port)
        self.client.set_timeout(timeout_s)
        self.ego_role_name = ego_role_name
        self.target_role_prefix = target_role_prefix
        self.fixed_delta_seconds = float(fixed_delta_seconds)
        self.fmu_runtime = fmu_runtime
        self.parameters = parameters

    def run(self):
        print("[AEB_FMU_ADAPTER] Started.")
        try:
            while True:
                world = self.client.get_world()
                ego = self._find_ego_vehicle(world)
                if ego is None:
                    print(f"[AEB_FMU_ADAPTER] Waiting for ego role_name='{self.ego_role_name}'...")
                    time.sleep(0.5)
                    continue

                signal_adapter = CarlaAEBSignalAdapter(
                    ego=ego,
                    target_role_prefix=self.target_role_prefix,
                    waypoint_reached_threshold=self.parameters.waypoint_reached_threshold,
                    world_getter=lambda: world,
                )
                signals = signal_adapter.sample()
                result = self.step_fmu(signals)
                control = control_from_fmu_output(result)
                ego.apply_control(control)

                print(
                    "[AEB_FMU_ADAPTER] "
                    f"ego_speed={signals.ego_speed:.2f}m/s "
                    f"lead_distance={signals.lead_distance:.2f}m "
                    f"lead_speed={signals.lead_speed:.2f}m/s "
                    f"ttc={result.get('ttc', 999.0):.2f}s "
                    f"state={result.get('aeb_state', 0.0):.0f} "
                    f"brake={control.brake:.3f} "
                    f"steer={control.steer:.3f}"
                )

                time.sleep(self.fixed_delta_seconds)

        except KeyboardInterrupt:
            print("[AEB_FMU_ADAPTER] Stopped by user.")
        finally:
            self.fmu_runtime.terminate()

    def step_fmu(self, signals: AEBSignals) -> dict[str, float]:
        values = {}
        values.update(signals.as_fmu_inputs())
        values.update(self.parameters.as_fmu_inputs())
        return self.fmu_runtime.step(values, self.fixed_delta_seconds)

    def _find_ego_vehicle(self, world):
        for actor in world.get_actors().filter("vehicle.*"):
            role_name = actor.attributes.get("role_name", "")
            if role_name == self.ego_role_name and actor.is_alive:
                return actor
        return None


def control_from_fmu_output(result: dict[str, float]) -> carla.VehicleControl:
    control = carla.VehicleControl()
    control.manual_gear_shift = False
    control.hand_brake = False
    control.reverse = False
    control.throttle = clamp(result.get("throttle", 0.0), 0.0, 1.0)
    control.brake = clamp(result.get("brake", result.get("deceleration", 0.0)), 0.0, 1.0)
    control.steer = clamp(result.get("steer", 0.0), -1.0, 1.0)
    control.hand_brake = bool(result.get("hand_brake", 0.0) >= 0.5)
    control.manual_gear_shift = bool(result.get("manual_gear_shift", 0.0) >= 0.5)
    if control.manual_gear_shift:
        control.gear = int(round(result.get("gear", 0.0)))
    return control


def get_speed(vehicle) -> float:
    velocity = vehicle.get_velocity()
    return math.sqrt(velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z)


def longitudinal_distance(ev, tv) -> float:
    ev_tf = ev.get_transform()
    forward = ev_tf.get_forward_vector()
    rel = tv.get_location() - ev.get_location()
    projected = rel.x * forward.x + rel.y * forward.y + rel.z * forward.z
    projected -= ev.bounding_box.extent.x + tv.bounding_box.extent.x
    return max(projected, 0.0)


def is_same_lane(world, ev, tv) -> bool:
    world_map = world.get_map()
    if world_map is None:
        return False

    ev_wp = get_waypoint(world_map, ev)
    tv_wp = get_waypoint(world_map, tv)
    if ev_wp is None or tv_wp is None:
        return False

    return ev_wp.road_id == tv_wp.road_id and ev_wp.lane_id == tv_wp.lane_id


def get_waypoint(world_map, vehicle):
    try:
        return world_map.get_waypoint(
            vehicle.get_location(),
            project_to_road=True,
            lane_type=carla.LaneType.Driving,
        )
    except RuntimeError:
        return None


def heading_error(actor_transform, target_location) -> float:
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


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def signal_names(config: dict, key: str, defaults: Iterable[str]) -> tuple[str, ...]:
    section = config.get(key, {})
    if isinstance(section, dict) and section:
        return tuple(section.keys())
    return tuple(defaults)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _float_arg(args: dict, key: str, default: float) -> float:
    value = args.get(key, default)
    if value is None or value == "":
        return float(default)
    return float(value)


def parse_args():
    parser = argparse.ArgumentParser(description="CARLA AEB FMU Adapter")
    parser.add_argument("--config", default=None, help="Path to signals.yaml")
    parser.add_argument("--fmu", default=None, help="Path to AEB_controller.fmu")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--target-speed", type=float, default=None)
    parser.add_argument("--min-distance", type=float, default=None)
    parser.add_argument("--warning-ttc", type=float, default=None)
    parser.add_argument("--brake-ttc", type=float, default=None)
    parser.add_argument("--emergency-ttc", type=float, default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    current_dir = Path(__file__).resolve().parent

    config_path = Path(args.config).resolve() if args.config else current_dir / "signals.yaml"
    config = load_yaml(config_path)

    controller_cfg = config.get("controller", {})
    fmu_path = (
        Path(args.fmu).resolve()
        if args.fmu
        else current_dir
        / controller_cfg.get(
            "fmu_file",
            "AEB_controller.fmu",
        )
    )

    carla_cfg = config.get("carla", {})
    parameters_cfg = dict(config.get("parameters", {}))
    if args.target_speed is not None:
        parameters_cfg["target_speed"] = args.target_speed
    if args.min_distance is not None:
        parameters_cfg["min_distance"] = args.min_distance
    if args.warning_ttc is not None:
        parameters_cfg["warning_ttc"] = args.warning_ttc
    if args.brake_ttc is not None:
        parameters_cfg["brake_ttc"] = args.brake_ttc
    if args.emergency_ttc is not None:
        parameters_cfg["emergency_ttc"] = args.emergency_ttc

    fmu_runtime = AEBFmuRuntime(
        fmu_path=fmu_path,
        input_names=signal_names(config, "inputs", DEFAULT_INPUTS.keys()),
        output_names=signal_names(config, "outputs", DEFAULT_OUTPUTS),
    )

    adapter = CarlaAEBAdapter(
        host=args.host or carla_cfg.get("host", "localhost"),
        port=args.port or int(carla_cfg.get("port", 2000)),
        timeout_s=float(carla_cfg.get("timeout_s", 60.0)),
        ego_role_name=carla_cfg.get("ego_role_name", "ev"),
        target_role_prefix=carla_cfg.get("target_role_prefix", "tv"),
        fixed_delta_seconds=float(carla_cfg.get("fixed_delta_seconds", 0.05)),
        fmu_runtime=fmu_runtime,
        parameters=AEBParameters.from_args(parameters_cfg),
    )
    adapter.run()


if __name__ == "__main__":
    main()
