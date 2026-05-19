import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


REPO_MARKERS = ("pyproject.toml", "scenarios", "scenario_runner")
CARLA_EXECUTABLES = ("CarlaUE4.exe", "CarlaUE4.sh", "CarlaUnreal.exe", "CarlaUnreal.sh")
CARLA_VERSION = "0.9.16"


@dataclass(frozen=True)
class ProjectPaths:
    repo_root: Path
    workspace_root: Path
    carla_root: Optional[Path]

    @property
    def scenarios_root(self) -> Path:
        return self.repo_root / "scenarios"

    @property
    def scenario_runner_script(self) -> Path:
        return self.repo_root / "scenario_runner" / "scenario_runner.py"

    @property
    def generated_xosc_root(self) -> Path:
        return self.scenarios_root / "generated" / "carla"

    @property
    def core_scenarios_root(self) -> Path:
        return self.scenarios_root / "core"

    @property
    def report_root(self) -> Path:
        return self.repo_root / "report"

    @property
    def tools_root(self) -> Path:
        return self.repo_root / "tools"

    @property
    def carla_python_paths(self) -> list[Path]:
        if self.carla_root is None:
            return []

        python_api = self.carla_root / "PythonAPI" / "carla"
        paths = [
            python_api,
            python_api / "agents",
        ]
        dist = python_api / "dist"
        if dist.exists():
            paths.extend(sorted(dist.glob("*.egg")))
        return [path.resolve() for path in paths if path.exists()]

    def build_subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.carla_root is not None:
            env.setdefault("CARLA_ROOT", str(self.carla_root))

        python_paths = [str(path) for path in self.carla_python_paths]
        existing = _clean_pythonpath(env.get("PYTHONPATH"))
        if existing:
            python_paths.extend(existing.split(os.pathsep))
        if python_paths:
            env["PYTHONPATH"] = os.pathsep.join(_dedupe_pythonpath(python_paths))
        return env

    def ensure_carla_python_imports(self) -> None:
        _remove_wheel_paths_from_sys_path()
        for path in reversed(self.carla_python_paths):
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)


def get_project_paths(start: Path | str | None = None) -> ProjectPaths:
    repo_root = _resolve_repo_root(start)
    workspace_root = _resolve_workspace_root(repo_root)
    carla_root = _resolve_carla_root(workspace_root)
    return ProjectPaths(
        repo_root=repo_root,
        workspace_root=workspace_root,
        carla_root=carla_root,
    )


def _resolve_repo_root(start: Path | str | None = None) -> Path:
    env_root = os.environ.get("TEST_ASSETS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    start_path = Path(start or __file__).resolve()
    if start_path.is_file():
        start_path = start_path.parent

    for candidate in (start_path, *start_path.parents):
        if _looks_like_repo_root(candidate):
            return candidate

    raise RuntimeError(
        "Cannot find test asset repo root. Set TEST_ASSETS_ROOT to the repo folder."
    )


def _resolve_workspace_root(repo_root: Path) -> Path:
    env_root = os.environ.get("FA_VNV_WORKSPACE_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return repo_root.parent.resolve()


def _resolve_carla_root(workspace_root: Path) -> Optional[Path]:
    env_root = os.environ.get("CARLA_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    candidates = _candidate_carla_dirs(workspace_root)
    for candidate in candidates:
        if _looks_like_carla_root(candidate):
            return candidate.resolve()
    return None


def _candidate_carla_dirs(workspace_root: Path) -> Iterable[Path]:
    if not workspace_root.exists():
        return []

    candidates = []
    for pattern in ("CARLA*", "carla*"):
        candidates.extend(path for path in workspace_root.glob(pattern) if path.is_dir())
    return sorted(
        set(candidates),
        key=lambda path: (CARLA_VERSION not in path.name, path.name.lower()),
    )


def _looks_like_repo_root(path: Path) -> bool:
    return all((path / marker).exists() for marker in REPO_MARKERS)


def _looks_like_carla_root(path: Path) -> bool:
    return any((path / executable).exists() for executable in CARLA_EXECUTABLES)


def _clean_pythonpath(value: Optional[str]) -> str:
    if not value:
        return ""
    return os.pathsep.join(_dedupe_pythonpath(value.split(os.pathsep)))


def _remove_wheel_paths_from_sys_path() -> None:
    sys.path[:] = [
        entry
        for entry in sys.path
        if not entry.lower().endswith(".whl")
    ]


def _dedupe_pythonpath(entries: Iterable[str]) -> list[str]:
    result = []
    seen = set()
    for entry in entries:
        if not entry or entry.lower().endswith(".whl"):
            continue
        key = str(Path(entry).resolve()).lower() if Path(entry).exists() else entry.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result
