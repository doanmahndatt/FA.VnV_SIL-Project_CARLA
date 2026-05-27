from pathlib import Path

import carla

try:
    from srunner.scenariomanager.actorcontrols.basic_control import BasicControl
    from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
except ImportError:
    from scenario_runner.srunner.scenariomanager.actorcontrols.basic_control import BasicControl
    from scenario_runner.srunner.scenariomanager.carla_data_provider import CarlaDataProvider

from fmu_adapter import (
    AEBFmuRuntime,
    AEBParameters,
    CarlaAEBSignalAdapter,
    DEFAULT_INPUTS,
    DEFAULT_OUTPUTS,
    control_from_fmu_output,
    load_yaml,
    signal_names,
)


class AebFmuController(BasicControl):
    def __init__(self, actor, args=None):
        super().__init__(actor)

        args = args or {}
        current_dir = Path(__file__).resolve().parent
        config_path = self._resolve_path(args.get("config"), current_dir / "signals.yaml")
        config = load_yaml(config_path)

        controller_cfg = config.get("controller", {})
        fmu_path = self._resolve_path(
            args.get("fmu"),
            current_dir / controller_cfg.get("fmu_file", "AEB_controller.fmu"),
        )

        parameter_args = dict(config.get("parameters", {}))
        parameter_args.update(args)

        self.parameters = AEBParameters.from_args(parameter_args)
        self.target_role_prefix = args.get(
            "target_role_prefix",
            config.get("carla", {}).get("target_role_prefix", "tv"),
        )
        self.fixed_delta_seconds = float(
            args.get(
                "fixed_delta_seconds",
                config.get("carla", {}).get("fixed_delta_seconds", 0.05),
            )
        )
        initial_speed = args.get("initial_speed")
        self.initial_speed = float(initial_speed) if initial_speed not in (None, "") else None

        self.fmu_runtime = AEBFmuRuntime(
            fmu_path=fmu_path,
            input_names=signal_names(config, "inputs", DEFAULT_INPUTS.keys()),
            output_names=signal_names(config, "outputs", DEFAULT_OUTPUTS),
        )
        self.signal_adapter = CarlaAEBSignalAdapter(
            ego=self._actor,
            target_role_prefix=self.target_role_prefix,
            waypoint_reached_threshold=self.parameters.waypoint_reached_threshold,
            world_getter=CarlaDataProvider.get_world,
        )
        self._last_logged_state = 0
        self._braking_started = False
        self._aeb_triggered = False

    def update_target_speed(self, speed):
        super().update_target_speed(speed)

    def reset(self):
        self._waypoints = []
        self._waypoints_updated = False
        self._reached_goal = False

    def run_step(self):
        if self._actor is None or not self._actor.is_alive:
            return

        self._waypoints = self.signal_adapter.prune_reached_waypoints(self._waypoints)
        self._reached_goal = not bool(self._waypoints)

        signals = self.signal_adapter.sample(self._waypoints)
        values = {}
        values.update(signals.as_fmu_inputs())
        values.update(self.parameters.as_fmu_inputs())

        result = self.fmu_runtime.step(values, self.fixed_delta_seconds)

        # Terminal brake guarantee at the Python layer.
        # Once AEB state >= 2 is ever seen, hold full brake until the FMU signals
        # parked (state = 4).  This remains correct even when the compiled FMU
        # binary pre-dates the internal _intervened flag.
        fmu_state = int(round(result.get("aeb_state", 0.0)))
        if fmu_state >= 2:
            self._aeb_triggered = True
        if self._aeb_triggered and fmu_state < 4:
            result = {
                **result,
                "brake": self.parameters.max_brake,
                "throttle": 0.0,
                "aeb_state": max(float(fmu_state), 3.0),
            }

        control = control_from_fmu_output(result)
        self._maintain_test_speed_until_braking(result)
        self._actor.apply_control(control)
        self._apply_park_lights(result)
        self._log_aeb_transition(result)

    def _maintain_test_speed_until_braking(self, result):
        state = int(round(result.get("aeb_state", 0.0)))
        if state in (2, 3, 4):
            self._braking_started = True
        if self.initial_speed is None or self._braking_started or state not in (0, 1):
            return
        forward = self._actor.get_transform().get_forward_vector()
        self._actor.set_target_velocity(
            carla.Vector3D(
                x=forward.x * self.initial_speed,
                y=forward.y * self.initial_speed,
                z=forward.z * self.initial_speed,
            )
        )

    def terminate(self):
        self.fmu_runtime.terminate()

    def _apply_park_lights(self, result):
        if int(round(result.get("aeb_state", 0.0))) != 4:
            return
        try:
            lights = self._actor.get_light_state()
            lights &= ~carla.VehicleLightState.Brake
            lights &= ~carla.VehicleLightState.LeftBlinker
            lights &= ~carla.VehicleLightState.RightBlinker
            self._actor.set_light_state(carla.VehicleLightState(lights))
        except RuntimeError:
            return

    def _log_aeb_transition(self, result):
        state = int(round(result.get("aeb_state", 0.0)))
        if state == self._last_logged_state:
            return
        self._last_logged_state = state
        if state <= 0:
            return

        state_name = {
            1: "WARNING",
            2: "ACTIVE",
            3: "EMERGENCY",
            4: "PARKED/AEB_TRIGGERED",
        }.get(state, str(state))
        print(
            "[AEB] target={} state={} ttc={:.2f}s brake={:.3f}".format(
                self.target_role_prefix,
                state_name,
                result.get("ttc", 999.0),
                result.get("brake", 0.0),
            )
        )
        if state == 4:
            print(
                "[AEB] parked foot_brake={:.3f} epb={} gear=P turn_signals={}".format(
                    result.get("brake", 0.0),
                    "ON" if result.get("hand_brake", 0.0) >= 0.5 else "OFF",
                    self._turn_signal_state(),
                )
            )

    def _turn_signal_state(self):
        try:
            lights = self._actor.get_light_state()
            indicators = carla.VehicleLightState.LeftBlinker | carla.VehicleLightState.RightBlinker
            return "ON" if lights & indicators else "OFF"
        except RuntimeError:
            return "UNKNOWN"

    @staticmethod
    def _resolve_path(value, default):
        if value is None or value == "":
            return Path(default).resolve()

        path = Path(value)
        if path.is_absolute():
            return path

        cwd_path = path.resolve()
        if cwd_path.exists():
            return cwd_path

        return (Path(__file__).resolve().parent / path).resolve()
