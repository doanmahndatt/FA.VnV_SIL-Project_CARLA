from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


class ReportWriter:
    def __init__(self, report_root: Path):
        self.report_root = Path(report_root).resolve()
        self.report_root.mkdir(parents=True, exist_ok=True)
        self.batch_dir: Optional[Path] = None

    def write_case_report(self, row: Dict):
        case_id = row["case_id"]
        case_dir = self.report_root / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        self._write_rows(case_dir / "report.xlsx", [row])

    def write_batch_summary(self, rows: List[Dict]):
        if not rows:
            return
        if self.batch_dir is None:
            self.batch_dir = self.report_root / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.batch_dir.mkdir(parents=True, exist_ok=True)
        self._write_rows(self.batch_dir / "summary.xlsx", rows)

    def _write_rows(self, path: Path, rows: List[Dict]):
        df = pd.DataFrame(rows)
        failed_df = df[df["result"].isin(["FAIL", "STOPPED", "TIMEOUT", "ERROR"])]
        pass_count = len(df[df["result"] == "PASS"])
        total = len(df)

        summary = pd.DataFrame(
            [
                {"metric": "total_cases", "value": total},
                {"metric": "passed_cases", "value": pass_count},
                {"metric": "failed_or_stopped_cases", "value": len(failed_df)},
                {"metric": "pass_rate", "value": round(pass_count / total, 3) if total else 0},
            ]
        )

        try:
            with pd.ExcelWriter(path) as writer:
                summary.to_excel(writer, sheet_name="Summary", index=False)
                df.to_excel(writer, sheet_name="All Cases", index=False)
                failed_df.to_excel(writer, sheet_name="Failed Cases", index=False)
        except PermissionError:
            backup = path.with_name(f"{path.stem}_backup_{datetime.now().strftime('%H%M%S')}{path.suffix}")
            with pd.ExcelWriter(backup) as writer:
                summary.to_excel(writer, sheet_name="Summary", index=False)
                df.to_excel(writer, sheet_name="All Cases", index=False)
                failed_df.to_excel(writer, sheet_name="Failed Cases", index=False)
