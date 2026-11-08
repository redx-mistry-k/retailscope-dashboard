"""Design-based market estimates and diagnostics for the retail survey demo."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from .data import STRATA


@dataclass(frozen=True)
class Estimate:
    estimate_inr: float
    standard_error_inr: float
    ci_low_inr: float
    ci_high_inr: float
    confidence: float
    universe_n: int
    sampled_n: int
    responded_n: int
    cv_pct: float
    validity: str

    @property
    def coverage_pct(self) -> float:
        return (100 * self.sampled_n / self.universe_n) if self.universe_n else 0.0

    @property
    def response_rate_pct(self) -> float:
        return (100 * self.responded_n / self.sampled_n) if self.sampled_n else 0.0


def estimate_market(population: pd.DataFrame, sample: pd.DataFrame,
                    confidence: float = 0.95) -> Estimate:
    """Stratified expansion estimate with normal CI and finite population correction.

    For each stratum h: T_hat_h = N_h * mean(respondent sales),
    V_hat_h = N_h^2 * (1 - r_h/N_h) * s_h^2 / r_h.

    r_h is the number of responding sampled stores. This treats nonresponse as
    conditionally random within strata and does not capture frame error,
    measurement error, nonresponse bias or variance from universe estimation.
    """
    if not 0.5 <= confidence < 1:
        raise ValueError("confidence must be between 0.5 and 1")
    if population.empty:
        raise ValueError("Selected market has no stores")
    if population["store_id"].duplicated().any():
        raise ValueError("Duplicate universe store_id values invalidate weighting")
    if sample["store_id"].duplicated().any():
        raise ValueError("Duplicate sample store_id values cannot be weighted")
    frame = population.set_index("store_id")[STRATA]
    survey = sample.set_index("store_id")[STRATA]
    if not survey.index.isin(frame.index).all():
        raise ValueError("Sample contains store_id values outside the selected universe")
    if not survey.equals(frame.reindex(survey.index)):
        raise ValueError("Sample strata do not match the universe frame")
    if not np.isfinite(sample["observed_sales_inr"].dropna().to_numpy(dtype=float)).all():
        raise ValueError("Observed sales must be finite")
    pop_counts = population.groupby(STRATA, observed=True).size()
    sample_counts = sample.groupby(STRATA, observed=True).size()
    if (pop_counts.index.difference(sample_counts.index)).size:
        raise ValueError("Sample has unrepresented population strata")
    if (sample_counts.reindex(pop_counts.index, fill_value=0) > pop_counts).any():
        raise ValueError("Sample size exceeds universe size in a stratum")
    if (sample["observed_sales_inr"].dropna() < 0).any():
        raise ValueError("Negative observed sales require validation before estimation")

    totals = []
    variances = []
    insufficient = False
    for key, N_h in pop_counts.items():
        observed = sample.loc[
            (sample["region"] == key[0]) & (sample["store_type"] == key[1]),
            "observed_sales_inr",
        ].dropna()
        r_h = len(observed)
        if r_h == 0:
            return Estimate(np.nan, np.nan, np.nan, np.nan, confidence,
                            len(population), len(sample), int(sample.observed_sales_inr.notna().sum()),
                            np.nan, "Unestimable: one or more strata have no responses")
        totals.append(int(N_h) * float(observed.mean()))
        if r_h < 2 and int(N_h) > 1:
            insufficient = True
        elif r_h == int(N_h):
            variances.append(0.0)
        else:
            variances.append((int(N_h) ** 2) * (1 - r_h / int(N_h))
                             * float(observed.var(ddof=1)) / r_h)
    total = float(sum(totals))
    base = (len(population), len(sample), int(sample.observed_sales_inr.notna().sum()))
    if insufficient:
        return Estimate(total, np.nan, np.nan, np.nan, confidence, *base,
                        np.nan, "Insufficient responses to quantify uncertainty")
    se = float(np.sqrt(sum(variances)))
    z = norm.ppf((1 + confidence) / 2)
    lower, upper = total - z * se, total + z * se
    cv = 100 * se / total if total > 0 else np.nan
    return Estimate(total, se, lower, upper, confidence, *base, cv, "OK")


def summarize_regions(population: pd.DataFrame, sample: pd.DataFrame,
                      confidence: float = 0.95) -> pd.DataFrame:
    rows = []
    for region in sorted(population.region.unique()):
        pop_r = population.loc[population.region == region]
        sample_r = sample.loc[sample.region == region]
        est = estimate_market(pop_r, sample_r, confidence)
        rows.append({
            "region": region,
            "universe_stores": est.universe_n,
            "sampled_stores": est.sampled_n,
            "responding_stores": est.responded_n,
            "coverage_pct": est.coverage_pct,
            "response_rate_pct": est.response_rate_pct,
            "market_sales_inr": est.estimate_inr,
            "ci_low_inr": est.ci_low_inr,
            "ci_high_inr": est.ci_high_inr,
            "standard_error_inr": est.standard_error_inr,
            "cv_pct": est.cv_pct,
            "status": est.validity,
        })
    return pd.DataFrame(rows).sort_values("market_sales_inr", ascending=False).reset_index(drop=True)


def flag_quality_issues(sample: pd.DataFrame) -> pd.DataFrame:
    """Advisory outlier review using store-type-specific log-sales robust z-scores.

    Flags are *not* automatic removals from the estimates. High sales can be real.
    """
    result = sample.copy()
    result["duplicate_store_id"] = result["store_id"].duplicated(keep=False)
    result["missing_sales"] = result["observed_sales_inr"].isna()
    result["invalid_sales"] = (result["observed_sales_inr"].lt(0) |
                               ~np.isfinite(result["observed_sales_inr"].fillna(0))).fillna(False)
    result["possible_outlier"] = False
    for _, indices in result.groupby("store_type", observed=True).groups.items():
        sales = result.loc[indices, "observed_sales_inr"]
        logged = np.log1p(sales.where(sales >= 0))
        median = logged.median()
        mad = (logged - median).abs().median()
        if pd.notna(mad) and mad > 1e-10:
            robust_z = 0.6745 * (logged - median) / mad
            result.loc[indices, "possible_outlier"] = robust_z.abs().gt(3.5).fillna(False)
    result["review_required"] = result[["duplicate_store_id", "missing_sales", "invalid_sales", "possible_outlier"]].any(axis=1)
    return result


def compare_with_synthetic_truth(population: pd.DataFrame, estimated: Estimate) -> dict:
    """Diagnostic only: not a method that is possible with an unknown real universe."""
    truth = float(population.monthly_sales_inr.sum())
    return {
        "synthetic_truth_inr": truth,
        "estimated_inr": estimated.estimate_inr,
        "signed_error_pct": 100 * (estimated.estimate_inr - truth) / truth,
        "within_ci": bool(estimated.ci_low_inr <= truth <= estimated.ci_high_inr),
    }
