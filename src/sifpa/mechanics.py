"""Medicare Part B buy-and-bill payment mechanics (ADR 0003). Pure functions, unit-tested.

Vocabulary
  PL   payment limit published by CMS for a quarter (allowed amount per billing unit)
  ASP  manufacturer average sales price; PL(t) is built from ASP(t-2)
"""

from __future__ import annotations

import math

ASP_ADDON = 0.06
IRA_BIOSIMILAR_ADDON = 0.08
SEQUESTRATION = 0.02
COINSURANCE = 0.20


def payment_limit(asp: float, addon: float = ASP_ADDON) -> float:
    """Single-source / reference product: PL = ASP x (1 + 6%)."""
    return asp * (1 + addon)


def biosimilar_payment_limit(asp_biosimilar: float, asp_reference: float, addon: float = ASP_ADDON) -> float:
    """Biosimilar: own ASP + add-on computed on the *reference* product's ASP (SSA 1847A(b)(8))."""
    return asp_biosimilar + addon * asp_reference


def implied_asp(pl: float, addon: float = ASP_ADDON) -> float:
    return pl / (1 + addon)


def implied_biosimilar_asp(pl_biosimilar: float, pl_reference: float, addon: float) -> float:
    return pl_biosimilar - addon * implied_asp(pl_reference)


def provider_collection_factor(coinsurance_collection_rate: float = 1.0,
                               sequestration: float = SEQUESTRATION,
                               coinsurance: float = COINSURANCE) -> float:
    """Share of the allowed amount a practice actually collects under Medicare FFS.

    Medicare pays 80% of allowed, reduced 2% by sequestration; the beneficiary owes 20% (collected at
    `coinsurance_collection_rate`). With full collection: 0.8 x 0.98 + 0.2 = 0.984.
    """
    return (1 - coinsurance) * (1 - sequestration) + coinsurance * coinsurance_collection_rate


def net_addon_after_sequestration(addon: float = ASP_ADDON, coinsurance_collection_rate: float = 1.0) -> float:
    """Effective margin over ASP after sequestration: ASP+6% nets to ~ASP+4.3%."""
    return (1 + addon) * provider_collection_factor(coinsurance_collection_rate) - 1


def pfs_payment(work_rvu: float, pe_rvu: float, mp_rvu: float,
                pw_gpci: float, pe_gpci: float, mp_gpci: float, conversion_factor: float) -> float:
    """Physician fee schedule non-facility payment (allowed) for one unit of a code."""
    return (work_rvu * pw_gpci + pe_rvu * pe_gpci + mp_rvu * mp_gpci) * conversion_factor


def infusion_addon_units(admin_hours: float) -> int:
    """Units of the 'each additional hour' add-on code (96415 / 96366).

    CPT time rule: the initial code covers up to the first hour; an additional-hour unit is billable once
    more than 30 minutes of that hour have passed. So 1.5 h -> 0, 2 h -> 1, 3.5 h -> 2, 4 h -> 3.
    """
    return max(0, math.ceil(admin_hours - 1.5 - 1e-9))


def lag_spread(pl_now: float, asp_now: float) -> float:
    """Medicare payment above the current market price per unit: positive when prices are falling."""
    return pl_now - asp_now
