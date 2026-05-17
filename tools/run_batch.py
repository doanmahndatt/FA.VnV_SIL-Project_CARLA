from pathlib import Path

from GUI.gui_runner import BatchRunnerGUI


def main():
    repo_root = Path(__file__).resolve().parents[1]
    app = BatchRunnerGUI(repo_root)
    app.run()


if __name__ == "__main__":
    main()
