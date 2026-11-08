"""Reproducible sample-design comparisons on a known synthetic population."""
from __future__ import annotations


import numpy as np
import pandas as pd
from scipy.stats import norm

from .data import STRATA


def allocate_neyman(counts: pd.Series, standard_deviations: pd.Series,
                    target_n: int, min_per_stratum: int = 2) -> pd.Series:
    """Allocate in proportion to N_h S_h, subject to integer caps and minima.

    The SDs here come from the fully known *synthetic* universe. In fieldwork,
    they would need to be estimated from pilot or historical data.
    """
    if counts.empty or counts.le(0).any() or target_n > int(counts.sum()):
        raise ValueError("Invalid stratum counts or sample size")
    if min_per_stratum < 0:
        raise ValueError("Minimum allocation cannot be negative")
    base = counts.clip(upper=min_per_stratum).astype(int)
    if target_n < int(base.sum()):
        raise ValueError(f"Sample must be at least {int(base.sum())} for this design")
    sd = standard_deviations.reindex(counts.index).fillna(0).clip(lower=0)
    if not np.isfinite(sd.to_numpy()).all():
        raise ValueError("Standard deviations must be finite")
    weights = counts * sd
    if weights.sum() == 0:
        weights = counts.astype(float)
    wanted = target_n * weights / weights.sum()
    allocation = base.copy()
    for _ in range(target_n - int(allocation.sum())):
        deficits = (wanted - allocation).where(allocation < counts, -np.inf)
        allocation.loc[deficits.idxmax()] += 1
    return allocation


def compare_allocations(population: pd.DataFrame, target_n: int) -> pd.DataFrame:
    """Return design allocations for each region by store-format stratum."""
    from .data import allocate_proportional

    grouped = population.groupby(STRATA, observed=True).monthly_sales_inr
    counts = grouped.size()
    sd = grouped.std().fillna(0)
    proportional = allocate_proportional(counts, target_n, min_per_stratum=2)
    neyman = allocate_neyman(counts, sd, target_n)
    result = pd.DataFrame({
        "universe_stores": counts,
        "synthetic_sales_sd_inr": sd,
        "proportional_n": proportional,
        "neyman_n": neyman,
    }).reset_index()
    return result


def simulate_designs(population: pd.DataFrame, target_n: int, repetitions: int = 100,
                     seed: int = 77, confidence: float = .95) -> pd.DataFrame:
    """Repeated SRS, proportional and Neyman draws; no simulated nonresponse.

    Report bias, RMSE and empirical CI coverage against the known synthetic
    total. Intervals are normal approximations using sample variance and FPC.
    """
    if repetitions < 2:
        raise ValueError("At least two simulation repetitions are required")
    if not .5 <= confidence < 1:
        raise ValueError("Invalid confidence level")
    if target_n < 2 or target_n > len(population):
        raise ValueError("Sample size must be between 2 and population size")
    table = compare_allocations(population, target_n)
    groups = population.groupby(STRATA, observed=True)
    arrays = [group.monthly_sales_inr.to_numpy(dtype=float) for _, group in groups]
    all_sales = population.monthly_sales_inr.to_numpy(dtype=float)
    truth = float(all_sales.sum())
    z = norm.ppf((1 + confidence) / 2)
    rng = np.random.default_rng(seed)
    rows = []
    for design in ("Simple random", "Proportional stratified", "Neyman stratified"):
        allocations = (table.proportional_n.to_numpy() if design == "Proportional stratified"
                       else table.neyman_n.to_numpy())
        estimates, covers, widths = [], [], []
        for _ in range(repetitions):
            if design == "Simple random":
                draw = rng.choice(all_sales, size=target_n, replace=False)
                estimate = len(all_sales) * float(draw.mean())
                variance = len(all_sales) ** 2 * (1 - target_n / len(all_sales)) * float(draw.var(ddof=1)) / target_n
            else:
                estimate, variance = 0.0, 0.0
                for values, n_h in zip(arrays, allocations):
                    n_h = int(n_h)
                    draw = rng.choice(values, size=n_h, replace=False)
                    estimate += len(values) * float(draw.mean())
                    if n_h < len(values):
                        if n_h < 2:
                            raise ValueError("Every sampled stratum needs two observations for an interval")
                        variance += len(values) ** 2 * (1 - n_h / len(values)) * float(draw.var(ddof=1)) / n_h
            half_width = z * np.sqrt(max(variance, 0))
            estimates.append(estimate)
            covers.append(estimate - half_width <= truth <= estimate + half_width)
            widths.append(2 * half_width)
        errors = np.asarray(estimates) - truth
        rows.append({"design": design, "sample_n": target_n, "repetitions": repetitions,
                     "bias_pct": 100 * float(errors.mean()) / truth,
                     "rmse_pct": 100 * float(np.sqrt(np.mean(errors ** 2))) / truth,
                     "coverage_pct": 100 * float(np.mean(covers)),
                     "mean_ci_width_pct": 100 * float(np.mean(widths)) / truth})
    return pd.DataFrame(rows)
