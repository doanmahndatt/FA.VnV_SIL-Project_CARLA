import pandas as pd

def generate_excel_report(results, output_path):
    """
    results = list of dict:
    {
      "test_id": str,
      "scenario": str,
      "kpi_profile": str,
      "summary": engine.summary(),
      "timeline": engine.get_timeline()
    }
    """

    # -------- Summary Sheet --------
    total = len(results)
    passed = sum(1 for r in results if r["summary"]["verdict"] == "PASS")
    failed = total - passed

    summary_df = pd.DataFrame([{
        "Total Tests": total,
        "PASS": passed,
        "FAIL": failed,
        "Overall Verdict": "PASS" if failed == 0 else "FAIL"
    }])

    # -------- Test Overview --------
    overview_df = pd.DataFrame([
        {
            "Test ID": r["test_id"],
            "Scenario": r["scenario"],
            "KPI Profile": r["kpi_profile"],
            "Verdict": r["summary"]["verdict"],
            "Fail Reason": (
                r["summary"]["violations"][0]["message"]
                if r["summary"]["violations"] else ""
            )
        }
        for r in results
    ])

    # -------- KPI Summary --------
    kpi_df = pd.DataFrame([
        {
            "Test ID": r["test_id"],
            "Min Distance (m)": r["summary"]["min_distance"],
            "Min TTC (s)": r["summary"]["min_ttc"],
            "Max Jerk (m/s³)": r["summary"]["max_jerk"]
        }
        for r in results
    ])

    # -------- Violation Log --------
    viol_rows = []
    for r in results:
        for v in r["summary"]["violations"]:
            viol_rows.append({
                "Test ID": r["test_id"],
                "Time (s)": v["timestamp"],
                "Type": v["type"],
                "Description": v["message"]
            })
    violation_df = pd.DataFrame(viol_rows)

    # -------- Write Excel --------
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        overview_df.to_excel(writer, sheet_name="Test_Overview", index=False)
        kpi_df.to_excel(writer, sheet_name="KPI_Summary", index=False)
        violation_df.to_excel(writer, sheet_name="Violations", index=False)

        # Timeline per test (optional)
        for r in results:
            tl_df = pd.DataFrame(r["timeline"])
            tl_df.to_excel(
                writer,
                sheet_name=f"Timeline_{r['test_id']}"[:31],
                index=False
            )