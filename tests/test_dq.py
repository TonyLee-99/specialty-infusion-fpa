"""F13: data-quality checks run with no hard failure, and the monthly pack ran end to end."""

import json
from pathlib import Path

from sifpa.monthly_pack import STEPS

ROOT = Path(__file__).resolve().parents[1]


def test_dq_report_has_no_hard_failures_and_flags_anomalies():
    r = json.loads((ROOT / "outputs/dq_report.json").read_text())
    assert r["n_fail"] == 0
    assert r["n_pass"] >= 5
    statuses = {c["status"] for c in r["checks"]}
    assert statuses <= {"pass", "flag", "fail"}


def test_monthly_pack_covers_the_pipeline_and_quantifies_manual_steps():
    targets = [s[0] for s in STEPS]
    for t in ("ingest", "dbt", "dq", "variance", "exports", "kpis", "excel", "memo", "scorecard", "test"):
        assert t in targets
    last = json.loads((ROOT / "outputs/monthly_pack_last.json").read_text())
    assert last["all_ok"] is True
    assert last["manual_steps_replaced"] >= 10
    assert "ESTIMATE" in last["manual_estimate_label"]
    # the summary is written once before the test step (so the suite can read it) and again after
    assert [s["step"] for s in last["steps"]] in (targets, targets[:-1])


def test_makefile_exposes_monthly_pack():
    assert "monthly-pack:" in (ROOT / "Makefile").read_text()
