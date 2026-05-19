import os
import subprocess
import sys
import time
from pathlib import Path

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
        self.camera_process = None
        self.hud_process = None
        self.current_scenario_process = None

    def start_support_tools(self):
        if not self._is_running(self.camera_process):
            self.camera_process = self._start_python(self.config_dir / "camera.py")

        if not self._is_running(self.hud_process):
            self.hud_process = self._start_python(self.config_dir / "hud.py")

    def start_scenario(self, xosc_path: Path):
        args = [
            str(self.scenario_runner),
            "--openscenario",
            str(Path(xosc_path).resolve()),
            "--reloadWorld",
        ]
        self.current_scenario_process = self._start_python(args[0], args[1:])
        return self.current_scenario_process

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
