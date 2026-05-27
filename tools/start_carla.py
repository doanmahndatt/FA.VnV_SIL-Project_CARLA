import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.project_paths import CARLA_EXECUTABLES, get_project_paths


def find_carla_executable(carla_root: Path) -> Path:
    for executable in CARLA_EXECUTABLES:
        path = carla_root / executable
        if path.exists():
            return path
    raise FileNotFoundError(f"CARLA executable not found in {carla_root}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start CARLA from the workspace root layout")
    parser.add_argument("--windowed", action="store_true", default=True)
    parser.add_argument("--resx", type=int, default=1280)
    parser.add_argument("--resy", type=int, default=720)
    parser.add_argument("carla_args", nargs="*", help="Additional arguments passed to CARLA")
    args = parser.parse_args()

    paths = get_project_paths(Path(__file__))
    if paths.carla_root is None:
        print(
            "CARLA_ROOT was not set and no CARLA* sibling folder was found next to the repo.",
            file=sys.stderr,
        )
        return 1

    executable = find_carla_executable(paths.carla_root)
    command = [
        str(executable),
        f"-ResX={args.resx}",
        f"-ResY={args.resy}",
        *args.carla_args,
    ]
    if args.windowed:
        command.insert(2, "-windowed")

    print(f"Starting CARLA: {executable}")
    subprocess.Popen(
        command,
        cwd=str(paths.carla_root),
        env=paths.build_subprocess_env(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
