import numpy as np
import pandas as pd
import pytest

from retailscope.data import STRATA, allocate_proportional, draw_sample, generate_population
from retailscope.stats import (
    compare_with_synthetic_truth, estimate_market, flag_quality_issues,
    summarize_regions,
)


@pytest.fixture(scope="module")
def pop():
    return generate_population(1200, seed=103)


@pytest.fixture(scope="module")
def sample(pop):
    return draw_sample(pop, target_n=300, seed=12, nonresponse_rate=0.0)


def test_population_is_deterministic():
    pd.testing.assert_frame_equal(generate_population(500, 42), generate_population(500, 42))


def test_population_has_unique_stores_and_positive_sales(pop):
    assert pop.store_id.is_unique
    assert pop.monthly_sales_inr.gt(0).all()
    assert len(pop) == 1200


def test_allocation_exact_with_stratum_minimum(pop):
    counts = pop.groupby(STRATA).size()
    allocation = allocate_proportional(counts, 300)
    assert allocation.sum() == 300
    assert (allocation >= counts.clip(upper=3)).all()
    assert (allocation <= counts).all()


def test_allocation_rejects_impossible_target(pop):
    counts = pop.groupby(STRATA).size()
    with pytest.raises(ValueError):
        allocate_proportional(counts, len(pop) + 1)
    with pytest.raises(ValueError):
        allocate_proportional(counts, 1)


def test_sampling_deterministic_and_without_replacement(pop):
    a = draw_sample(pop, 300, seed=16)
    b = draw_sample(pop, 300, seed=16)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 300
    assert a.store_id.is_unique
    assert set(a.store_id).issubset(set(pop.store_id))


def test_full_census_matches_ground_truth(pop):
    full_sample = draw_sample(pop, target_n=len(pop), seed=1, nonresponse_rate=0)
    est = estimate_market(pop, full_sample)
    assert est.validity == "OK"
    assert est.estimate_inr == pytest.approx(pop.monthly_sales_inr.sum())
    assert est.standard_error_inr == pytest.approx(0)
    assert est.ci_low_inr == pytest.approx(est.estimate_inr)
    assert est.ci_high_inr == pytest.approx(est.estimate_inr)


def test_constant_sales_within_strata_gives_exact_total(pop):
    fixed = pop.copy()
    fixed["monthly_sales_inr"] = (fixed.groupby(STRATA).ngroup() + 1) * 50000.0
    sampled = draw_sample(fixed, target_n=300, seed=2, nonresponse_rate=0)
    est = estimate_market(fixed, sampled)
    assert est.estimate_inr == pytest.approx(fixed.monthly_sales_inr.sum())
    assert est.standard_error_inr == pytest.approx(0, abs=1e-6)


def test_confidence_level_broadens_interval(pop, sample):
    lo = estimate_market(pop, sample, confidence=.90)
    hi = estimate_market(pop, sample, confidence=.99)
    assert hi.ci_high_inr - hi.ci_low_inr > lo.ci_high_inr - lo.ci_low_inr
    assert lo.estimate_inr == pytest.approx(hi.estimate_inr)


def test_regional_totals_add_to_overall(pop, sample):
    total = estimate_market(pop, sample)
    by_region = summarize_regions(pop, sample)
    assert by_region.market_sales_inr.sum() == pytest.approx(total.estimate_inr)
    assert np.square(by_region.standard_error_inr).sum() == pytest.approx(total.standard_error_inr**2)
    assert by_region.sampled_stores.sum() == len(sample)


def test_filtering_store_formats_is_consistent(pop, sample):
    sliced_pop = pop[pop.store_type.isin(["Kirana", "Mini market"])]
    sliced_sample = sample[sample.store_type.isin(["Kirana", "Mini market"])]
    est = estimate_market(sliced_pop, sliced_sample)
    assert est.universe_n == len(sliced_pop)
    assert est.sampled_n == len(sliced_sample)


def test_missing_responses_are_excluded(pop, sample):
    adjusted = sample.copy()
    adjusted.loc[adjusted.index[:8], "observed_sales_inr"] = np.nan
    est = estimate_market(pop, adjusted)
    assert est.responded_n == len(sample) - 8
    assert est.estimate_inr > 0


def test_zero_responses_in_stratum_withholds_estimate(pop, sample):
    adjusted = sample.copy()
    first = adjusted.iloc[0]
    mask = (adjusted.region == first.region) & (adjusted.store_type == first.store_type)
    adjusted.loc[mask, "observed_sales_inr"] = np.nan
    est = estimate_market(pop, adjusted)
    assert est.validity.startswith("Unestimable")
    assert np.isnan(est.estimate_inr)


def test_one_response_withholds_precision(pop, sample):
    adjusted = sample.copy()
    first = adjusted.iloc[0]
    mask = (adjusted.region == first.region) & (adjusted.store_type == first.store_type)
    affected = adjusted.index[mask]
    adjusted.loc[affected[1:], "observed_sales_inr"] = np.nan
    est = estimate_market(pop, adjusted)
    assert est.validity.startswith("Insufficient")
    assert np.isnan(est.standard_error_inr)


def test_duplicate_store_and_negative_sales_rejected(pop, sample):
    duplicates = pd.concat([sample, sample.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate"):
        estimate_market(pop, duplicates)
    invalid = sample.copy()
    invalid.loc[invalid.index[0], "observed_sales_inr"] = -500
    with pytest.raises(ValueError, match="Negative"):
        estimate_market(pop, invalid)


def test_quality_detection_flags_missing_and_extreme_sales(sample):
    modified = sample.copy()
    modified.loc[modified.index[0], "observed_sales_inr"] = np.nan
    modified.loc[modified.index[1], "observed_sales_inr"] = 1e15
    quality = flag_quality_issues(modified)
    assert quality.missing_sales.sum() == 1
    assert quality.possible_outlier.sum() >= 1
    assert quality.review_required.sum() >= 2


def test_diagnostic_benchmark_does_not_change_estimate(pop, sample):
    est = estimate_market(pop, sample)
    diagnostic = compare_with_synthetic_truth(pop, est)
    assert diagnostic["synthetic_truth_inr"] == pytest.approx(pop.monthly_sales_inr.sum())
    assert diagnostic["estimated_inr"] == pytest.approx(est.estimate_inr)
