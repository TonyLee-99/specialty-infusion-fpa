"""SYNTHETIC 837/835-shaped claims and remits for the RCM KPI method demo.

Every parameter below is INVENTED for illustration (listed in synthetic/rcm/PARAMETERS.md). The data
exists only to exercise the KPI SQL/DAX; it says nothing about any real practice.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from sifpa.paths import SYNTHETIC

SEED = 7
N_CLAIMS = 5000
AS_OF = date(2026, 9, 30)
PERIOD_START = date(2026, 1, 1)
LABEL = "SYNTHETIC"

# --- invented parameters (SYNTHETIC) ---
PAYERS = {  # share of claims, first-pass denial probability, median days to pay, contract multiple of base
    "Medicare FFS": (0.20, 0.06, 14, 1.00),
    "Medicare Advantage": (0.22, 0.14, 30, 0.98),
    "Commercial": (0.50, 0.12, 35, 1.25),
    "Medicaid": (0.08, 0.16, 45, 0.85),
}
CARC_GROUPS = {  # denial reason group: (share of denials, example CARC codes, overturn-on-appeal probability)
    "Authorization / precertification": (0.30, ["197", "15"], 0.55),
    "Eligibility / coverage": (0.22, ["27", "31"], 0.35),
    "Coding / bundling": (0.18, ["4", "97"], 0.60),
    "Medical necessity": (0.14, ["50"], 0.40),
    "Missing information": (0.10, ["16"], 0.80),
    "Timely filing / duplicate": (0.06, ["29", "18"], 0.05),
}
EDIT_PROB = 0.08  # claim needs a scrubber edit / resubmission before acceptance (not clean)
PATIENT_RESP_SHARE = 0.12  # share of allowed owed by the patient on paid claims
PATIENT_COLLECT_PROB = 0.70
BASE_ALLOWED_MEAN = 3200.0  # mean expected allowed per infusion claim (drug + admin), lognormal


def generate() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    names = list(PAYERS)
    shares = np.array([PAYERS[p][0] for p in names])
    payer = rng.choice(names, size=N_CLAIMS, p=shares / shares.sum())
    days = (AS_OF - PERIOD_START).days
    service = [PERIOD_START + timedelta(days=int(d)) for d in rng.integers(0, days, N_CLAIMS)]
    lag_submit = rng.integers(1, 6, N_CLAIMS)
    base = rng.lognormal(np.log(BASE_ALLOWED_MEAN) - 0.5 * 0.6**2, 0.6, N_CLAIMS)
    mult = np.array([PAYERS[p][3] for p in payer])
    expected = np.round(base * mult, 2)
    billed = np.round(expected * rng.uniform(2.0, 3.5, N_CLAIMS), 2)
    edited = rng.random(N_CLAIMS) < EDIT_PROB
    claims = pd.DataFrame({
        "data_label": LABEL,
        "claim_id": [f"SYN{i:06d}" for i in range(N_CLAIMS)],
        "patient_id": [f"SYNP{j:05d}" for j in rng.integers(0, 1400, N_CLAIMS)],
        "payer": payer,
        "service_date": service,
        "submit_date": [s + timedelta(days=int(lag)) for s, lag in zip(service, lag_submit, strict=True)],
        "billed_amount": billed,
        "expected_allowed": expected,
        "scrubber_edit": edited,
    })

    groups = list(CARC_GROUPS)
    gshares = np.array([CARC_GROUPS[g][0] for g in groups])
    remits = []
    for row in claims.itertuples():
        p_deny, pay_days = PAYERS[row.payer][1], PAYERS[row.payer][2]
        remit_date = row.submit_date + timedelta(days=int(rng.gamma(4, pay_days / 4)))
        if remit_date > AS_OF:
            continue  # still open in AR at the as-of date
        if rng.random() < p_deny:
            g = rng.choice(groups, p=gshares / gshares.sum())
            carc = rng.choice(CARC_GROUPS[g][1])
            remits.append((LABEL, row.claim_id, remit_date, 0.0, 0.0, "CO", carc, g, True, 1))
            if rng.random() < CARC_GROUPS[g][2]:  # appealed and overturned later
                d2 = remit_date + timedelta(days=int(rng.integers(20, 60)))
                if d2 <= AS_OF:
                    paid = round(row.expected_allowed * (1 - PATIENT_RESP_SHARE), 2)
                    remits.append((LABEL, row.claim_id, d2, paid, round(row.expected_allowed * PATIENT_RESP_SHARE, 2),
                                   "PR", "1", "Paid on appeal", False, 2))
        else:
            paid = round(row.expected_allowed * (1 - PATIENT_RESP_SHARE), 2)
            pr = round(row.expected_allowed * PATIENT_RESP_SHARE, 2)
            remits.append((LABEL, row.claim_id, remit_date, paid, pr, "PR", "1", "Paid", False, 1))
    remit = pd.DataFrame(remits, columns=["data_label", "claim_id", "remit_date", "payer_paid", "patient_resp",
                                          "adj_group", "carc_code", "carc_group", "denied", "remit_seq"])
    # patient collections on paid patient responsibility (SYNTHETIC)
    remit["patient_paid"] = np.where(rng.random(len(remit)) < PATIENT_COLLECT_PROB, remit["patient_resp"], 0.0)
    return claims, remit


def main() -> None:
    claims, remits = generate()
    out = SYNTHETIC / "rcm"
    out.mkdir(parents=True, exist_ok=True)
    claims.to_csv(out / "claims_837_SYNTHETIC.csv", index=False)
    remits.to_csv(out / "remits_835_SYNTHETIC.csv", index=False)
    print(f"SYNTHETIC: {len(claims)} claims, {len(remits)} remit lines -> {out}")


if __name__ == "__main__":
    main()
