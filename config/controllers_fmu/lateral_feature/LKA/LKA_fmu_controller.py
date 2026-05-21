from pathlib import Path

try:
    from srunner.scenariomanager.actorcontrols.basic_control import BasicControl
    from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
except ImportError:
    from scenario_runner.srunner.scenariomanager.actorcontrols.basic_control import BasicControl
    from scenario_runner.srunner.scenariomanager.carla_data_provider import CarlaDataProvider

from fmu_adapter import (
    DEFAULT_INPUTS,
    DEFAULT_OUTPUTS,
    LKAFmuRuntime,
    LKAParameters,
    CarlaLKASignalAdapter,
    control_from_fmu_output,
    load_yaml,
    signal_names,
)


class LkaFmuController(BasicControl):
    def __init__(self, actor, args=None):
        super().__init__(actor)

        args = args or {}
        current_dir = Path(__file__).resolve().parent
        config_path = self._resolve_path(args.get("config"), current_dir / "signals.yaml")
        config = load_yaml(config_path)

        controller_cfg = config.get("controller", {})
        fmu_path = self._resolve_path(
            args.get("fmu"),
            current_dir / controller_cfg.get("fmu_file", "LKA_controller.fmu"),
        )

        parameter_args = dict(config.get("parameters", {}))
        parameter_args.update(args)

        self.parameters = LKAParameters.from_args(parameter_args)
        self.fixed_delta_seconds = float(
            args.get(
                "fixed_delta_seconds",
                config.get("carla", {}).get("fixed_delta_seconds", 0.05),
            )
        )

        self.fmu_runtime = LKAFmuRuntime(
            fmu_path=fmu_path,
            input_names=signal_names(config, "inputs", DEFAULT_INPUTS.keys()),
            output_names=signal_names(config, "outputs", DEFAULT_OUTPUTS),
        )
        self.signal_adapter = CarlaLKASignalAdapter(
            ego=self._actor,
            world_getter=CarlaDataProvider.get_world,
        )
        self.offset_command_steer = float(parameter_args.get("offset_command_steer", 0.28))

    def update_target_speed(self, speed):
        super().update_target_speed(speed)
        self.parameters = LKAParameters(
            target_speed=float(speed),
            activation_offset=self.parameters.activation_offset,
            deadband_offset=self.parameters.deadband_offset,
            kp_offset=self.parameters.kp_offset,
            kp_heading=self.parameters.kp_heading,
            kp_speed=self.parameters.kp_speed,
            max_steer=self.parameters.max_steer,
            max_throttle=self.parameters.max_throttle,
            max_brake=self.parameters.max_brake,
        )

    def reset(self):
        self._waypoints = []
        self._waypoints_updated = False
        self._offset = 0
        self._offset_updated = False
        self._reached_goal = False

    def run_step(self):
        if self._actor is None or not self._actor.is_alive:
            return

        signals = self.signal_adapter.sample()
        values = {}
        values.update(signals.as_fmu_inputs())
        values.update(self.parameters.as_fmu_inputs())

        result = self.fmu_runtime.step(values, self.fixed_delta_seconds)
        control = control_from_fmu_output(result)

        # ScenarioRunner sends LaneOffsetAction targets through update_offset().
        # Use that command as a short driver-disturbance input, then let the FMU
        # correct once the scenario releases the requested offset back to zero.
        requested_offset = float(getattr(self, "_offset", 0.0) or 0.0)
        if abs(requested_offset) > 0.05:
            steer = abs(self.offset_command_steer)
            control.steer = steer if requested_offset > 0 else -steer

        self._actor.apply_control(control)

    def terminate(self):
        self.fmu_runtime.terminate()

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
