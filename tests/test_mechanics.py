"""F04: Medicare buy-and-bill payment mechanics (ADR 0003)."""

import math

import pytest

from sifpa import mechanics as M


def test_asp_plus_6_nets_to_asp_plus_4_3_after_sequestration():
    # 1.06 x (0.8 x 0.98 + 0.2) = 1.04304
    assert M.net_addon_after_sequestration() == pytest.approx(0.04304, abs=1e-9)


def test_uncollected_coinsurance_eats_the_addon():
    # 10% of the 20% coinsurance uncollected: 1.06 x (0.784 + 0.18) - 1 = 2.184%
    assert M.net_addon_after_sequestration(coinsurance_collection_rate=0.9) == pytest.approx(0.02184, abs=1e-9)


def test_biosimilar_addon_is_on_reference_asp():
    # cheaper biosimilar gets the same add-on dollars as the reference
    assert M.biosimilar_payment_limit(10.0, 30.0, 0.08) == pytest.approx(12.4)
    assert M.implied_biosimilar_asp(12.4, M.payment_limit(30.0), 0.08) == pytest.approx(10.0)


def test_payment_limit_round_trip():
    assert M.implied_asp(M.payment_limit(28.166)) == pytest.approx(28.166)


@pytest.mark.parametrize("hours,units", [(0.5, 0), (1.0, 0), (1.5, 0), (1.6, 1), (2.0, 1), (3.5, 2), (4.0, 3)])
def test_infusion_addon_units_follow_cpt_time_rule(hours, units):
    assert M.infusion_addon_units(hours) == units


def test_pfs_96413_ohio_cy2026_by_hand():
    # RVU26D: work 0.28, PE non-facility 3.64, MP 0.07; Ohio GPCI 1.000 / 0.913 / 1.008; CF 33.4009
    expected = (0.28 * 1.0 + 3.64 * 0.913 + 0.07 * 1.008) * 33.4009
    assert M.pfs_payment(0.28, 3.64, 0.07, 1.0, 0.913, 1.008, 33.4009) == pytest.approx(expected)
    assert math.isclose(expected, 122.71, abs_tol=0.01)


def test_lag_spread_sign():
    # prices falling: PL built on the older, higher ASP pays above today's price
    assert M.lag_spread(M.payment_limit(30.0), 27.0) > 0
    assert M.lag_spread(M.payment_limit(30.0), 33.0) < 0
