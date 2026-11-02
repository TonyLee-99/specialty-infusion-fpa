"""`make monthly-pack`: the recurring FP&A refresh as one command.

refresh public pulls -> dbt build + data tests -> analyses -> star-schema exports + PBIP -> SQL-twin KPIs
-> Excel scenarios -> memo -> scorecard + screenshots -> README -> data-quality checks -> test suite.
Each step is timed; outputs/monthly_pack_last.json records the run and the manual steps it replaces.
`--offline` skips the network pull and reuses data/raw.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime

from sifpa.paths import OUTPUTS, ROOT

# (make target, the manual step it replaces). Manual minutes are an ESTIMATE of doing it by hand in
# Excel/SQL each month (labelled as such in the output); the automated time is measured.
STEPS = [
    ("ingest", "Download the new ASP quarter, PFS/GPCI, CMS utilization, PLACES/Census files; check row counts", 60),
    ("dbt", "Clean, join and validate source tables (HCPCS changes, biosimilar codes, reconciliations)", 90),
    ("fixtures", "(no manual equivalent: keeps the offline CI slice in sync)", 0),
    ("margin", "Rebuild per-infusion margin by drug and payer; refresh lag spread", 60),
    ("forecast", "Re-forecast ASP and volume; re-score against last quarter", 60),
    ("scenarios", "Update base / biosimilar / policy scenarios for the plan", 45),
    ("benchmark", "Refresh provider scorecards and peer percentiles", 45),
    ("market", "Refresh market white-space ranking", 30),
    ("rcm", "Refresh RCM KPI layer (SYNTHETIC demo here)", 20),
    ("exports", "Export star-schema extracts for the Power BI model", 20),
    ("pbi", "Update semantic-model tables/measures", 15),
    ("kpis", "Tie out dashboard KPIs to the SQL numbers", 30),
    ("excel", "Roll the Excel scenario workbook forward", 30),
    ("memo", "Re-write the executive memo numbers", 45),
    ("scorecard", "Rebuild scorecard pages", 30),
    ("screenshots", "Screenshot pages for the deck", 10),
    ("readme", "Update documentation numbers", 10),
    ("dq", "Eyeball anomalies (price jumps, coverage gaps, realization)", 30),
    ("test", "(no manual equivalent: regression suite)", 0),
]


def write_summary(log: list[dict], t_all: float, offline: bool) -> dict:
    summary = {
        "run_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "offline": offline,
        "all_ok": all(s["status"] != "failed" for s in log),
        "automated_minutes_measured": round((time.time() - t_all) / 60, 1),
        "manual_steps_replaced": sum(1 for s in log if s["manual_minutes_estimate"] > 0),
        "manual_hours_estimate": round(sum(minutes for _t, _m, minutes in STEPS) / 60, 1),
        "manual_estimate_label": "ESTIMATE (analyst minutes per step, not measured)",
        "steps": log,
    }
    (OUTPUTS / "monthly_pack_last.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    offline = "--offline" in sys.argv
    log, t_all = [], time.time()
    for target, manual, minutes in STEPS:
        if target == "test":  # the suite checks this run's summary + README, so write both before testing
            write_summary(log, t_all, offline)
            subprocess.run(["make", "readme"], cwd=ROOT, capture_output=True, check=False)
        if offline and target == "ingest":
            log.append({"step": target, "status": "skipped (offline)", "seconds": 0, "manual_step": manual,
                        "manual_minutes_estimate": minutes})
            continue
        t0 = time.time()
        proc = subprocess.run(["make", target], cwd=ROOT, capture_output=True, text=True)
        status = "ok" if proc.returncode == 0 else "failed"
        log.append({"step": target, "status": status, "seconds": round(time.time() - t0, 1), "manual_step": manual,
                    "manual_minutes_estimate": minutes})
        print(f"{target:12s} {status:7s} {log[-1]['seconds']:6.1f}s")
        if status == "failed":
            print(proc.stdout[-2000:], proc.stderr[-2000:])
            break
    summary = write_summary(log, t_all, offline)
    # README quotes this run's timing, so render it once more after the summary exists
    subprocess.run(["make", "readme"], cwd=ROOT, capture_output=True, check=False)
    print(f"monthly pack: {'OK' if summary['all_ok'] else 'FAILED'} in {summary['automated_minutes_measured']} min; "
          f"replaces {summary['manual_steps_replaced']} manual steps (~{summary['manual_hours_estimate']} h, estimate)")
    if not summary["all_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
