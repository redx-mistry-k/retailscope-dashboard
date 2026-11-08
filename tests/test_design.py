import numpy as np
import pandas as pd
import pytest

from retailscope.data import generate_population
from retailscope.design import allocate_neyman, compare_allocations, simulate_designs
from retailscope.stats import estimate_market, flag_quality_issues


def test_neyman_allocation_respects_sd_minimum_and_cap():
    counts = pd.Series([10, 20], index=["low", "high"])
    allocation = allocate_neyman(counts, pd.Series([0, 100], index=counts.index), 12)
    assert allocation.to_dict() == {"low": 2, "high": 10}
    with pytest.raises(ValueError):
        allocate_neyman(counts, pd.Series([1, 1], index=counts.index), 3)


def test_designer_allocations_and_simulation_reproducible():
    population = generate_population(480, seed=8)
    allocation = compare_allocations(population, 120)
    assert allocation.proportional_n.sum() == 120
    assert allocation.neyman_n.sum() == 120
    assert (allocation.neyman_n <= allocation.universe_stores).all()
    a = simulate_designs(population, 120, repetitions=20, seed=42)
    b = simulate_designs(population, 120, repetitions=20, seed=42)
    pd.testing.assert_frame_equal(a, b)
    assert set(a.design) == {"Simple random", "Proportional stratified", "Neyman stratified"}
    assert a.rmse_pct.ge(0).all()
    assert a.coverage_pct.between(0, 100).all()


def test_estimator_rejects_frame_mismatch_and_nonfinite_sales():
    population = generate_population(480, seed=8)
    sample = population.iloc[:80].rename(columns={"monthly_sales_inr": "observed_sales_inr"}).copy()
    bad = sample.copy()
    bad.loc[bad.index[0], "store_id"] = "not-in-frame"
    with pytest.raises(ValueError, match="outside"):
        estimate_market(population, bad)
    bad = sample.copy()
    bad.loc[bad.index[0], "region"] = "Wrong region"
    with pytest.raises(ValueError, match="strata"):
        estimate_market(population, bad)
    bad = sample.copy()
    bad.loc[bad.index[0], "observed_sales_inr"] = np.inf
    with pytest.raises(ValueError, match="finite"):
        estimate_market(population, bad)


def test_quality_flags_all_duplicate_rows():
    population = generate_population(480, seed=8)
    sample = population.iloc[:20].rename(columns={"monthly_sales_inr": "observed_sales_inr"})
    duplicated = pd.concat([sample, sample.iloc[[0]]], ignore_index=True)
    quality = flag_quality_issues(duplicated)
    assert quality.duplicate_store_id.sum() == 2
    assert quality.loc[quality.duplicate_store_id, "review_required"].all()
