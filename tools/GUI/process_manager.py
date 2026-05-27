import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.project_paths import get_project_paths


class ProcessManager:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.paths = get_project_paths(self.repo_root)
        self.tools_dir = self.repo_root / "tools"
        self.config_dir = self.tools_dir / "config"
        self.scenario_runner = self.paths.scenario_runner_script
        self.sync_enabled, self.fixed_delta_seconds, self.frame_rate, self.load_timeout = (
            self._load_carla_sync_settings()
        )
        self.traffic_enabled, self.traffic_config, self.traffic_profile = (
            self._load_urban_traffic_settings()
        )
        self.camera_process = None
        self.hud_process = None
        self.current_scenario_process = None

    def start_support_tools(self, feature=None):
        if not self._is_running(self.camera_process):
            self.camera_process = self._start_python(self.config_dir / "camera.py")

        if not self._is_running(self.hud_process):
            args = ["--feature", feature] if feature else []
            self.hud_process = self._start_python(self.config_dir / "hud.py", args)

    def start_scenario(self, xosc_path: Path):
        xosc_path = Path(xosc_path).resolve()
        sim_config_path = self._sim_config_path_for_xosc(xosc_path)
        self.sync_enabled, self.fixed_delta_seconds, self.frame_rate, self.load_timeout = (
            self._load_carla_sync_settings(sim_config_path)
        )
        self.traffic_enabled, self.traffic_config, self.traffic_profile = (
            self._load_urban_traffic_settings(sim_config_path, xosc_path)
        )

        if self.sync_enabled:
            self._apply_synchronous_world_settings()

        args = [
            str(self.scenario_runner),
            "--openscenario",
            str(xosc_path),
            "--reloadWorld",
            "--timeout",
            str(self.load_timeout),
        ]
        if self.sync_enabled:
            args.extend(["--sync", "--frameRate", str(self.frame_rate)])
        if self.traffic_enabled:
            args.append("--urbanTraffic")
            args.extend(["--urbanTrafficConfig", str(self.traffic_config)])
            if self.traffic_profile:
                args.extend(["--urbanTrafficProfile", str(self.traffic_profile)])
        self.current_scenario_process = self._start_python(args[0], args[1:])
        return self.current_scenario_process

    def _apply_synchronous_world_settings(self):
        try:
            import carla

            client = carla.Client("localhost", 2000)
            client.set_timeout(self.load_timeout)
            world = client.get_world()
            settings = world.get_settings()
            settings.synchronous_mode = True
            settings.fixed_delta_seconds = self.fixed_delta_seconds
            world.apply_settings(settings)
            client.get_trafficmanager().set_synchronous_mode(True)
        except RuntimeError:
            return

    def _load_carla_sync_settings(self, config_path=None):
        config_path = config_path or self.repo_root / "adas_sil_execution" / "sim" / "carla_0_9_16.yaml"
        default_sync = True
        default_fixed_delta_seconds = 0.05
        default_frame_rate = 20
        default_load_timeout = 30.0

        if not config_path.exists():
            return default_sync, default_fixed_delta_seconds, default_frame_rate, default_load_timeout

        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            return default_sync, default_fixed_delta_seconds, default_frame_rate, default_load_timeout

        simulator = config.get("simulator", {})
        sync_enabled = bool(simulator.get("sync", default_sync))
        load_timeout = float(simulator.get("timeout_s", default_load_timeout))
        fixed_delta_seconds = float(
            simulator.get("fixed_delta_seconds", default_fixed_delta_seconds)
        )
        frame_rate = (
            round(1.0 / fixed_delta_seconds) if fixed_delta_seconds > 0 else default_frame_rate
        )
        return sync_enabled, fixed_delta_seconds, frame_rate, load_timeout

    def _load_urban_traffic_settings(self, config_path=None, xosc_path=None):
        config_path = config_path or self.repo_root / "adas_sil_execution" / "sim" / "carla_0_9_16.yaml"
        default_traffic_config = self.repo_root / "config" / "traffic" / "urban_traffic.yaml"

        if not config_path.exists():
            return True, default_traffic_config, "urban_acc_aeb"

        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            return True, default_traffic_config, "urban_acc_aeb"

        traffic = (config.get("simulator", {}) or {}).get("traffic", {}) or {}
        enabled = bool(traffic.get("enabled", True))
        traffic_config = Path(traffic.get("config", self._traffic_config_path_for_xosc(xosc_path) or default_traffic_config))
        if not traffic_config.is_absolute():
            traffic_config = self.repo_root / traffic_config
        profile = traffic.get("profile", "urban_acc_aeb")

        return enabled, traffic_config, profile

    def _sim_config_path_for_xosc(self, xosc_path):
        feature = self._feature_domain_from_path(xosc_path)
        if feature is not None:
            candidate = (
                self.repo_root
                / "adas_sil_execution"
                / "sim"
                / feature[0]
                / feature[1]
                / "carla_0_9_16.yaml"
            )
            if candidate.exists():
                return candidate
        return self.repo_root / "adas_sil_execution" / "sim" / "carla_0_9_16.yaml"

    def _traffic_config_path_for_xosc(self, xosc_path):
        feature = self._feature_domain_from_path(xosc_path)
        if feature is None:
            return None
        candidate = (
            self.repo_root
            / "config"
            / "traffic"
            / feature[0]
            / feature[1]
            / "{}_traffic.yaml".format(feature[1].lower())
        )
        return candidate if candidate.exists() else None

    @staticmethod
    def _feature_domain_from_path(path):
        if path is None:
            return None
        parts = Path(path).as_posix().split("/")
        domains = {"longitudinal_feature", "lateral_feature", "brake_feature", "parking_feature"}
        for index, part in enumerate(parts[:-1]):
            if part in domains:
                return part, parts[index + 1]
        return None

    def terminate_current_scenario(self):
        self._terminate(self.current_scenario_process)
        self.current_scenario_process = None

    def terminate_support_tools(self):
        self._terminate(self.camera_process)
        self._terminate(self.hud_process)
        self.camera_process = None
        self.hud_process = None

    def terminate_all(self):
        self.terminate_current_scenario()
        self.terminate_support_tools()

    def _start_python(self, script, args=None):
        args = args or []
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        return subprocess.Popen(
            [sys.executable, str(script), *args],
            cwd=str(self.repo_root),
            env=self.paths.build_subprocess_env(),
            creationflags=creationflags,
        )

    @staticmethod
    def _is_running(process):
        return process is not None and process.poll() is None

    @staticmethod
    def _terminate(process, timeout=5):
        if process is None or process.poll() is not None:
            return

        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout)

        time.sleep(0.2)
