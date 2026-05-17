import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .process_manager import ProcessManager
from .report_writer import ReportWriter


HOST = "localhost"
PORT = 2000


@dataclass(frozen=True)
class ScenarioJob:
    case_id: str
    group_name: str
    xosc_path: Path


class BatchRunner:
    def __init__(self, repo_root: Path, case_timeout_seconds: int = 120):
        self.repo_root = Path(repo_root).resolve()
        self.xosc_root = self.repo_root / "scenarios" / "generated" / "carla"
        self.core_root = self.repo_root / "scenarios" / "core"
        self.report_writer = ReportWriter(self.repo_root / "report")
        self.process_manager = ProcessManager(self.repo_root)
        self.case_timeout_seconds = case_timeout_seconds
        self.stop_event = threading.Event()
        self.results = []

    def discover_groups(self) -> List[str]:
        if not self.xosc_root.exists():
            return []
        return sorted(p.name for p in self.xosc_root.iterdir() if p.is_dir())

    def discover_jobs(self) -> List[ScenarioJob]:
        jobs = []
        for path in sorted(self.xosc_root.glob("*/*.xosc")):
            jobs.append(ScenarioJob(path.stem, path.parent.name, path))
        return jobs

    def jobs_for_groups(self, groups: List[str]) -> List[ScenarioJob]:
        selected = set(groups)
        return [job for job in self.discover_jobs() if job.group_name in selected]

    def job_for_case(self, case_id: str) -> Optional[ScenarioJob]:
        for job in self.discover_jobs():
            if job.case_id == case_id:
                return job
        return None

    def stop(self):
        self.stop_event.set()
        self.process_manager.terminate_current_scenario()

    def shutdown(self):
        self.stop()
        self.process_manager.terminate_all()
        self.report_writer.write_batch_summary(self.results)

    def run(self, jobs: List[ScenarioJob], keep_support_tools=True, on_log=None, on_progress=None):
        self.stop_event.clear()
        self.results = []

        if on_log:
            on_log(f"Chuẩn bị chạy {len(jobs)} case.")

        if not jobs:
            if on_log:
                on_log("Không có case nào để chạy.")
            return []

        self.process_manager.start_support_tools()
        if on_log:
            on_log("Đã khởi chạy camera.py và hud.py.")

        for index, job in enumerate(jobs, start=1):
            if self.stop_event.is_set():
                break

            if on_progress:
                on_progress(index - 1, len(jobs), f"Đang chạy {job.case_id}")

            row = self.run_one(job, on_log=on_log)
            self.results.append(row)
            self.report_writer.write_case_report(row)
            self.report_writer.write_batch_summary(self.results)

            if on_progress:
                on_progress(index, len(jobs), f"Hoàn tất {job.case_id}: {row['result']}")

            if self.stop_event.is_set():
                break

            self._reload_world_after_case(job, on_log=on_log)

        if not keep_support_tools:
            self.process_manager.terminate_support_tools()

        self.report_writer.write_batch_summary(self.results)

        if on_log:
            on_log(f"Batch kết thúc. Đã ghi {len(self.results)} kết quả.")

        return self.results

    def run_one(self, job: ScenarioJob, on_log=None) -> Dict:
        started_at = datetime.now()
        params = self._load_core_params(job.case_id)
        process = None
        timeout = False
        stopped = False
        kpi_error = ""

        if on_log:
            on_log(f"START {job.case_id} | group={job.group_name}")

        try:
            process = self.process_manager.start_scenario(job.xosc_path)
            kpi = self._create_kpi_monitor()
            deadline = time.time() + self.case_timeout_seconds

            while True:
                if self.stop_event.is_set():
                    stopped = True
                    self.process_manager.terminate_current_scenario()
                    break

                if time.time() > deadline:
                    timeout = True
                    self.process_manager.terminate_current_scenario()
                    break

                if kpi is not None:
                    try:
                        kpi.step()
                    except Exception as exc:
                        kpi_error = str(exc)

                if process.poll() is not None:
                    break

                time.sleep(0.05)

            exit_code = process.poll() if process is not None else None
            kpi_result = kpi.get_result() if kpi is not None else self._empty_kpi_result("kpi_unavailable")

        except Exception as exc:
            exit_code = process.poll() if process is not None else None
            kpi_result = self._empty_kpi_result(str(exc))
            kpi_error = str(exc)
        finally:
            self.process_manager.terminate_current_scenario()

        duration = round((datetime.now() - started_at).total_seconds(), 2)

        result = kpi_result["result"]
        fail_reason = kpi_result["fail_reason"]
        if stopped:
            result = "STOPPED"
            fail_reason = "stopped_by_user"
        elif timeout:
            result = "TIMEOUT"
            fail_reason = f"case_timeout_{self.case_timeout_seconds}s"
        elif exit_code not in (0, None) and result == "PASS":
            result = "FAIL"
            fail_reason = f"scenario_runner_exit_{exit_code}"

        row = {
            "case_id": job.case_id,
            "group": job.group_name,
            "xosc_path": str(job.xosc_path),
            "light": params.get("light", "unknown"),
            "weather": params.get("weather", "unknown"),
            "result": result,
            "fail_reason": fail_reason,
            "fail_time": kpi_result["fail_time"],
            "ev_max_speed": kpi_result["ev_max_speed"],
            "ev_min_speed": kpi_result["ev_min_speed"],
            "dist_min": kpi_result["dist_min"],
            "scenario_exit_code": exit_code,
            "duration_seconds": duration,
            "kpi_error": kpi_error,
            "timestamp": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

        if on_log:
            on_log(f"END {job.case_id} | result={row['result']} | reason={row['fail_reason']}")

        return row

    def _create_kpi_monitor(self):
        try:
            from config.KPI import KPIMonitor

            return KPIMonitor(host=HOST, port=PORT)
        except Exception:
            return None

    def _load_core_params(self, case_id: str) -> Dict:
        scenario_prefix = "_".join(case_id.split("_")[:3])
        core_path = self.core_root / scenario_prefix / f"{case_id}.yaml"
        if not core_path.exists():
            return {}

        with core_path.open("r", encoding="utf-8") as file:
            core = yaml.safe_load(file) or {}

        return core.get("parameters", {}) or {}

    def _reload_world_after_case(self, job: ScenarioJob, on_log=None):
        try:
            import carla

            map_name = self._get_map_from_xosc(job.xosc_path).split("/")[-1]
            if on_log:
                on_log(f"Reload world: {map_name}")

            client = carla.Client(HOST, PORT)
            client.set_timeout(10.0)
            client.load_world(map_name)
            time.sleep(3)
        except Exception as exc:
            if on_log:
                on_log(f"WARN không reload được world sau {job.case_id}: {exc}")

    @staticmethod
    def _get_map_from_xosc(xosc_path: Path) -> str:
        tree = ET.parse(xosc_path)
        root = tree.getroot()
        logic = root.find(".//LogicFile")
        if logic is not None:
            return logic.attrib.get("filepath", "Town03")
        return "Town03"

    @staticmethod
    def _empty_kpi_result(reason: str) -> Dict:
        return {
            "result": "FAIL",
            "fail_reason": reason,
            "fail_time": None,
            "ev_max_speed": 0,
            "ev_min_speed": 0,
            "dist_min": 0,
        }
