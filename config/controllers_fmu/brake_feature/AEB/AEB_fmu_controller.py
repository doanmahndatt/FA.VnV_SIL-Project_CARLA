from pathlib import Path

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
        self._actor.apply_control(control_from_fmu_output(result))

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
