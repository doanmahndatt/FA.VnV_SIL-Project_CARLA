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
    "target_speed": 15.0,
    "lane_offset": 0.0,
    "heading_error": 0.0,
    "has_lane": 0.0,
    "activation_offset": 0.25,
    "deadband_offset": 0.05,
    "kp_offset": 0.22,
    "kp_heading": 0.85,
    "kp_speed": 0.25,
    "max_steer": 0.45,
    "max_throttle": 0.45,
    "max_brake": 0.25,
}

DEFAULT_OUTPUTS = (
    "throttle",
    "brake",
    "steer",
    "corrected_offset",
    "lka_state",
)


@dataclass(frozen=True)
class LKAParameters:
    target_speed: float = 15.0
    activation_offset: float = 0.25
    deadband_offset: float = 0.05
    kp_offset: float = 0.22
    kp_heading: float = 0.85
    kp_speed: float = 0.25
    max_steer: float = 0.45
    max_throttle: float = 0.45
    max_brake: float = 0.25

    @classmethod
    def from_args(cls, args: dict | None) -> "LKAParameters":
        args = args or {}
        return cls(
            target_speed=_float_arg(args, "target_speed", _float_arg(args, "desired_speed", 15.0)),
            activation_offset=_float_arg(args, "activation_offset", 0.25),
            deadband_offset=_float_arg(args, "deadband_offset", 0.05),
            kp_offset=_float_arg(args, "kp_offset", 0.22),
            kp_heading=_float_arg(args, "kp_heading", 0.85),
            kp_speed=_float_arg(args, "kp_speed", 0.25),
            max_steer=_float_arg(args, "max_steer", 0.45),
            max_throttle=_float_arg(args, "max_throttle", 0.45),
            max_brake=_float_arg(args, "max_brake", 0.25),
        )

    def as_fmu_inputs(self) -> dict[str, float]:
        return {
            "target_speed": self.target_speed,
            "activation_offset": self.activation_offset,
            "deadband_offset": self.deadband_offset,
            "kp_offset": self.kp_offset,
            "kp_heading": self.kp_heading,
            "kp_speed": self.kp_speed,
            "max_steer": self.max_steer,
            "max_throttle": self.max_throttle,
            "max_brake": self.max_brake,
        }


@dataclass(frozen=True)
class LKASignals:
    ego_speed: float
    lane_offset: float
    heading_error: float
    has_lane: bool

    def as_fmu_inputs(self) -> dict[str, float]:
        return {
            "ego_speed": self.ego_speed,
            "lane_offset": self.lane_offset,
            "heading_error": self.heading_error,
            "has_lane": 1.0 if self.has_lane else 0.0,
        }


class LKAFmuRuntime:
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
        self.unzipdir = Path(tempfile.mkdtemp(prefix="lka_fmu_"))
        extract(str(self.fmu_path), unzipdir=str(self.unzipdir))
        self.model_description = read_model_description(str(self.fmu_path))

        if self.model_description.coSimulation is None:
            raise ValueError("LKA FMU must expose an FMI 2.0 Co-Simulation interface")

        self.vr = {
            variable.name: variable.valueReference
            for variable in self.model_description.modelVariables
        }
        self._validate_variables()

        self.fmu = FMU2Slave(
            guid=self.model_description.guid,
            unzipDirectory=str(self.unzipdir),
            modelIdentifier=self.model_description.coSimulation.modelIdentifier,
            instanceName="LKAControllerInstance",
        )

        self.current_time = 0.0
        self.initialized = False

    def _validate_variables(self):
        missing = [name for name in [*self.input_names, *self.output_names] if name not in self.vr]
        if missing:
            raise ValueError(
                "FMU variable mismatch. Rebuild LKA_controller.fmu from LKAController.py. "
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


class CarlaLKASignalAdapter:
    def __init__(self, ego, world_getter=None):
        self.ego = ego
        self.world_getter = world_getter

    def sample(self) -> LKASignals:
        world = self._get_world()
        world_map = world.get_map() if world is not None else None
        ego_speed = get_speed(self.ego)

        if world_map is None:
            return LKASignals(
                ego_speed=ego_speed,
                lane_offset=0.0,
                heading_error=0.0,
                has_lane=False,
            )

        waypoint = get_waypoint(world_map, self.ego)
        if waypoint is None:
            return LKASignals(
                ego_speed=ego_speed,
                lane_offset=0.0,
                heading_error=0.0,
                has_lane=False,
            )

        lane_offset = signed_lane_offset(self.ego, waypoint)
        lane_heading_error = heading_error(
            self.ego.get_transform().rotation.yaw,
            waypoint.transform.rotation.yaw,
        )

        return LKASignals(
            ego_speed=ego_speed,
            lane_offset=lane_offset,
            heading_error=lane_heading_error,
            has_lane=True,
        )

    def _get_world(self):
        if self.world_getter is not None:
            return self.world_getter()
        return self.ego.get_world()


class CarlaLKAAdapter:
    def __init__(
        self,
        host: str,
        port: int,
        timeout_s: float,
        ego_role_name: str,
        fixed_delta_seconds: float,
        fmu_runtime: LKAFmuRuntime,
        parameters: LKAParameters,
    ):
        self.client = carla.Client(host, port)
        self.client.set_timeout(timeout_s)
        self.ego_role_name = ego_role_name
        self.fixed_delta_seconds = float(fixed_delta_seconds)
        self.fmu_runtime = fmu_runtime
        self.parameters = parameters

    def run(self):
        print("[LKA_FMU_ADAPTER] Started.")
        try:
            while True:
                world = self.client.get_world()
                ego = self._find_ego_vehicle(world)
                if ego is None:
                    print(f"[LKA_FMU_ADAPTER] Waiting for ego role_name='{self.ego_role_name}'...")
                    time.sleep(0.5)
                    continue

                signal_adapter = CarlaLKASignalAdapter(ego=ego, world_getter=lambda: world)
                signals = signal_adapter.sample()
                result = self.step_fmu(signals)
                control = control_from_fmu_output(result)
                ego.apply_control(control)

                print(
                    "[LKA_FMU_ADAPTER] "
                    f"ego_speed={signals.ego_speed:.2f}m/s "
                    f"lane_offset={signals.lane_offset:.2f}m "
                    f"heading_error={signals.heading_error:.3f}rad "
                    f"state={result.get('lka_state', 0.0):.0f} "
                    f"throttle={control.throttle:.3f} "
                    f"brake={control.brake:.3f} "
                    f"steer={control.steer:.3f}"
                )

                time.sleep(self.fixed_delta_seconds)

        except KeyboardInterrupt:
            print("[LKA_FMU_ADAPTER] Stopped by user.")
        finally:
            self.fmu_runtime.terminate()

    def step_fmu(self, signals: LKASignals) -> dict[str, float]:
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
    control.brake = clamp(result.get("brake", 0.0), 0.0, 1.0)
    control.steer = clamp(result.get("steer", 0.0), -1.0, 1.0)
    return control


def get_speed(vehicle) -> float:
    velocity = vehicle.get_velocity()
    return math.sqrt(velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z)


def get_waypoint(world_map, vehicle):
    try:
        return world_map.get_waypoint(
            vehicle.get_location(),
            project_to_road=True,
            lane_type=carla.LaneType.Driving,
        )
    except RuntimeError:
        return None


def signed_lane_offset(vehicle, waypoint) -> float:
    vehicle_location = vehicle.get_location()
    lane_center = waypoint.transform.location
    right = waypoint.transform.get_right_vector()
    delta = vehicle_location - lane_center
    return delta.x * right.x + delta.y * right.y + delta.z * right.z


def heading_error(actor_yaw_deg: float, lane_yaw_deg: float) -> float:
    error = math.radians(actor_yaw_deg - lane_yaw_deg)
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
    parser = argparse.ArgumentParser(description="CARLA LKA FMU Adapter")
    parser.add_argument("--config", default=None, help="Path to signals.yaml")
    parser.add_argument("--fmu", default=None, help="Path to LKA_controller.fmu")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--target-speed", type=float, default=None)
    parser.add_argument("--activation-offset", type=float, default=None)
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
        else current_dir / controller_cfg.get("fmu_file", "LKA_controller.fmu")
    )

    carla_cfg = config.get("carla", {})
    parameters_cfg = dict(config.get("parameters", {}))
    if args.target_speed is not None:
        parameters_cfg["target_speed"] = args.target_speed
    if args.activation_offset is not None:
        parameters_cfg["activation_offset"] = args.activation_offset

    fmu_runtime = LKAFmuRuntime(
        fmu_path=fmu_path,
        input_names=signal_names(config, "inputs", DEFAULT_INPUTS.keys()),
        output_names=signal_names(config, "outputs", DEFAULT_OUTPUTS),
    )

    adapter = CarlaLKAAdapter(
        host=args.host or carla_cfg.get("host", "localhost"),
        port=args.port or int(carla_cfg.get("port", 2000)),
        timeout_s=float(carla_cfg.get("timeout_s", 60.0)),
        ego_role_name=carla_cfg.get("ego_role_name", "ev"),
        fixed_delta_seconds=float(carla_cfg.get("fixed_delta_seconds", 0.05)),
        fmu_runtime=fmu_runtime,
        parameters=LKAParameters.from_args(parameters_cfg),
    )
    adapter.run()


if __name__ == "__main__":
    main()
