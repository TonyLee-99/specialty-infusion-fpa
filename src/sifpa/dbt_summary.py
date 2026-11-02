"""After `dbt build`: summarise dbt/target/run_results.json -> outputs/dbt_summary.json (models, tests, status)."""

from __future__ import annotations

import json
from collections import Counter

from sifpa.paths import OUTPUTS, ROOT


def main() -> None:
    rr = json.loads((ROOT / "dbt/target/run_results.json").read_text())
    kinds, statuses = Counter(), Counter()
    singular = 0
    for r in rr["results"]:
        kind = r["unique_id"].split(".")[0]
        kinds[kind] += 1
        statuses[r["status"]] += 1
        if kind == "test" and ".assert_" in r["unique_id"]:
            singular += 1
    out = {"models": kinds["model"], "seeds": kinds["seed"], "tests": kinds["test"],
           "business_rule_tests": singular, "statuses": dict(statuses),
           "all_passed": set(statuses) <= {"success", "pass"}}
    (OUTPUTS / "dbt_summary.json").write_text(json.dumps(out, indent=2) + "\n")
    print(out)


if __name__ == "__main__":
    main()
