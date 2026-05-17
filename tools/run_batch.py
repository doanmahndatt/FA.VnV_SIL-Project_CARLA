import os
import subprocess
import time
import carla
import pandas as pd
from datetime import datetime
import xml.etree.ElementTree as ET
import signal
import sys
import atexit
import yaml

from KPI import KPIMonitor   # 🔥 KPI monitor (real-time)

# ================= CONFIG =================

SCENARIO_RUNNER = r"\scenario_runner\scenario_runner.py"
XOSC_DIR = r"\scenarios\generated\carla"

HOST = "localhost"
PORT = 2000

REPORT_DIR = "../report"
REPORT_FILE = os.path.join(REPORT_DIR, "report_latest.xlsx")

# lưu toàn bộ kết quả
results = []


# ================= EXIT HANDLER =================
# đảm bảo khi Ctrl+C hoặc đóng window vẫn lưu report

def handle_exit(signal_received=None, frame=None):
    print("\n[INFO] Program stopped → saving report...")
    export_excel()
    sys.exit(0)


# ================= HELPER: LOAD MAP =================
# lấy map name từ file xosc để reload world

def get_map_from_xosc(xosc_path):
    tree = ET.parse(xosc_path)
    root = tree.getroot()

    logic = root.find(".//LogicFile")
    if logic is not None:
        return logic.attrib.get("filepath", "Town03")

    return "Town03"


# ================= HELPER: RELOAD WORLD =================
# reset CARLA sau mỗi test case

def reload_world(map_name):
    client = carla.Client(HOST, PORT)
    client.set_timeout(10.0)

    # fix path Carla/Maps/Town03 → Town03
    map_name = map_name.split("/")[-1]

    print(f"[INFO] Reloading world: {map_name}")
    client.load_world(map_name)

    time.sleep(3)


# ================= HELPER: LOAD CORE PARAM =================
# 🔥 đọc lại parameter từ core.yaml để lấy light, weather

def load_core_params(case_id):

    # ví dụ: acc_csc_003_001 → acc_csc_003
    scenario_prefix = "_".join(case_id.split("_")[:3])

    core_dir = f"../scenarios/core/{scenario_prefix}"
    core_path = os.path.join(core_dir, f"{case_id}.yaml")

    if not os.path.exists(core_path):
        print(f"[WARN] core.yaml not found for {case_id}")
        return {}

    with open(core_path, "r") as f:
        core = yaml.safe_load(f)

    return core.get("parameters", {})


# ================= EXPORT REPORT =================
# xuất Excel gồm Summary + All + Failed

def export_excel():

    if len(results) == 0:
        return

    os.makedirs(REPORT_DIR, exist_ok=True)

    df = pd.DataFrame(results)

    total = len(df)
    fail = len(df[df["result"] == "FAIL"])
    pass_rate = (total - fail) / total if total > 0 else 0

    summary = pd.DataFrame([
        {"metric": "total_cases", "value": total},
        {"metric": "failed_cases", "value": fail},
        {"metric": "pass_rate", "value": round(pass_rate, 3)}
    ])

    failed_df = df[df["result"] == "FAIL"]

    try:
        with pd.ExcelWriter(REPORT_FILE) as writer:
            summary.to_excel(writer, sheet_name="Summary", index=False)
            df.to_excel(writer, sheet_name="All Cases", index=False)
            failed_df.to_excel(writer, sheet_name="Failed Cases", index=False)

        print(f"[REPORT] Updated: {REPORT_FILE}")

    except PermissionError:
        print("[WARNING] Excel file is open → saving backup...")

        backup_file = REPORT_FILE.replace(".xlsx", "_backup.xlsx")

        with pd.ExcelWriter(backup_file) as writer:
            summary.to_excel(writer, sheet_name="Summary", index=False)
            df.to_excel(writer, sheet_name="All Cases", index=False)
            failed_df.to_excel(writer, sheet_name="Failed Cases", index=False)

        print(f"[REPORT] Saved backup: {backup_file}")


# ================= MAIN RUNNER =================

def run_all():

    files = sorted([f for f in os.listdir(XOSC_DIR) if f.endswith(".xosc")])

    print(f"[INFO] Found {len(files)} scenarios")

    for f in files:

        xosc_path = os.path.join(XOSC_DIR, f)

        # ===== LOAD PARAM (light, weather) =====
        case_id = f.replace(".xosc", "")
        params = load_core_params(case_id)

        light = params.get("light", "unknown")
        weather = params.get("weather", "unknown")

        # ===== PRINT RUN INFO =====
        print(f"\n[RUN] {f} | light={light} | weather={weather}")

        start_time = datetime.now()

        # ===== START SCENARIO =====
        process = subprocess.Popen([
            "python",
            SCENARIO_RUNNER,
            "--openscenario",
            xosc_path
        ])

        # ===== KPI MONITOR (REAL-TIME) =====
        kpi = KPIMonitor()
        kpi_result = kpi.run_monitor(duration=30)

        process.wait()  # đảm bảo scenario runner kết thúc

        # ===== LOAD PARAM (light, weather) =====
        case_id = f.replace(".xosc", "")
        params = load_core_params(case_id)

        light = params.get("light", "unknown")
        weather = params.get("weather", "unknown")

        # ===== SAVE RESULT =====
        row = {
            "case_id": case_id,

            # 🔥 ENV PARAM
            "light": light,
            "weather": weather,

            # KPI RESULT
            "result": kpi_result["result"],
            "fail_reason": kpi_result["fail_reason"],
            "fail_time": kpi_result["fail_time"],
            "ev_max_speed": kpi_result["ev_max_speed"],
            "ev_min_speed": kpi_result["ev_min_speed"],
            "dist_min": kpi_result["dist_min"],

            # TIME
            "timestamp": start_time.strftime("%Y-%m-%d %H:%M:%S")
        }

        results.append(row)

        # ===== PRINT RESULT REAL-TIME =====
        print(f"[RESULT] {case_id} | {light} | {weather} | {row['result']}")

        # ===== SAVE NGAY (ANTI DATA LOSS) =====
        export_excel()

        # ===== RESET WORLD =====
        map_name = get_map_from_xosc(xosc_path)
        reload_world(map_name)

    print("\n[INFO] All scenarios completed")


# ================= ENTRY POINT =================

def main():
    signal.signal(signal.SIGINT, handle_exit)   # Ctrl+C
    atexit.register(export_excel)               # đóng window vẫn lưu
    run_all()


if __name__ == "__main__":
    main()