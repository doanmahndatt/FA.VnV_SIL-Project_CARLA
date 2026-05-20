import subprocess
import time

def start_sut(cmd):
    return subprocess.Popen(cmd, shell=True)

def run_scenario(xosc):
    subprocess.Popen([
        "python3",
        "/opt/scenario_runner/scenario_runner.py",
        "--openscenario", xosc,
        "--sync"
    ])

if __name__ == "__main__":
    sut = start_sut(
        "ros2 launch autoware_launch autoware.launch.xml"
    )

    time.sleep(20)  # wait readiness (simplified demo)

    run_scenario("scenarios/general_scenarios/acc/acc_follow_001.xosc")

    time.sleep(60)
    sut.terminate()
