import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.project_paths import get_project_paths

get_project_paths(__file__).ensure_carla_python_imports()

from tools.GUI.gui_runner import BatchRunnerGUI


def main():
    paths = get_project_paths(Path(__file__))
    app = BatchRunnerGUI(paths.repo_root)
    app.run()


if __name__ == "__main__":
    main()
