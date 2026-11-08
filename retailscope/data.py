"""Reproducible synthetic retail population and stratified survey sample."""
from __future__ import annotations

import numpy as np
import pandas as pd

REGIONS = {
    "Chennai": {"share": 0.32, "factor": 1.25, "lat": 13.0827, "lon": 80.2707},
    "Coimbatore": {"share": 0.19, "factor": 1.10, "lat": 11.0168, "lon": 76.9558},
    "Madurai": {"share": 0.16, "factor": 0.96, "lat": 9.9252, "lon": 78.1198},
    "Tiruchirappalli": {"share": 0.13, "factor": 0.94, "lat": 10.7905, "lon": 78.7047},
    "Salem": {"share": 0.11, "factor": 0.89, "lat": 11.6643, "lon": 78.1460},
    "Tirunelveli": {"share": 0.09, "factor": 0.85, "lat": 8.7139, "lon": 77.7567},
}
STORE_TYPES = {
    "Kirana": {"share": 0.56, "median_sales": 350_000},
    "Mini market": {"share": 0.25, "median_sales": 930_000},
    "Supermarket": {"share": 0.15, "median_sales": 2_700_000},
    "Hypermarket": {"share": 0.04, "median_sales": 9_000_000},
}
STRATA = ["region", "store_type"]


def generate_population(size: int = 9600, seed: int = 2026) -> pd.DataFrame:
    """Return a *fully synthetic* finite retail population with sales ground truth.

    No proprietary NIQ dataset, real store list, or true geographic estimates are used.
    """
    if size < 240:
        raise ValueError("Population must contain at least 240 stores")
    rng = np.random.default_rng(seed)
    regions = np.array(list(REGIONS))
    formats = np.array(list(STORE_TYPES))
    chosen_regions = rng.choice(regions, size=size, p=[REGIONS[r]["share"] for r in regions])
    chosen_formats = rng.choice(formats, size=size, p=[STORE_TYPES[t]["share"] for t in formats])
    region_factor = np.array([REGIONS[r]["factor"] for r in chosen_regions])
    median_sales = np.array([STORE_TYPES[t]["median_sales"] for t in chosen_formats])
    # Log-normal right-skew is a stylised assumption, not a calibrated market model.
    monthly_sales = median_sales * region_factor * rng.lognormal(mean=0, sigma=0.48, size=size)
    lat = np.array([REGIONS[r]["lat"] for r in chosen_regions]) + rng.normal(0, 0.065, size)
    lon = np.array([REGIONS[r]["lon"] for r in chosen_regions]) + rng.normal(0, 0.065, size)
    return pd.DataFrame(
        {
            "store_id": [f"TN-{i:05d}" for i in range(1, size + 1)],
            "region": chosen_regions,
            "store_type": chosen_formats,
            "monthly_sales_inr": monthly_sales.round(2),
            "latitude": lat.round(5),
            "longitude": lon.round(5),
        }
    )


def allocate_proportional(counts: pd.Series, target_n: int, min_per_stratum: int = 3) -> pd.Series:
    """Integer proportional allocation with a minimum and finite stratum caps."""
    if counts.empty or counts.le(0).any():
        raise ValueError("All listed strata must have positive population counts")
    if target_n > int(counts.sum()):
        raise ValueError("Sample cannot exceed population")
    base = counts.clip(upper=min_per_stratum).astype(int)
    if target_n < int(base.sum()):
        raise ValueError(f"Sample must be at least {int(base.sum())} for this design")
    allocation = base.copy()
    wanted = counts * (target_n / counts.sum())
    # Greedily allocate to largest fractional/proportional deficits.
    for _ in range(target_n - int(allocation.sum())):
        eligible = allocation < counts
        deficits = (wanted - allocation).where(eligible, -float("inf"))
        index = deficits.idxmax()
        allocation.loc[index] += 1
    return allocation


def draw_sample(population: pd.DataFrame, target_n: int = 720, seed: int = 77,
                nonresponse_rate: float = 0.025) -> pd.DataFrame:
    """Draw SRSWOR independently within region x store type strata.

    Simulated item nonresponse is marked as NaN; no outcome values are inferred.
    The estimator later applies within-stratum response adjustment, conditional
    on the assumption that responses are random inside each stratum.
    """
    if not 0 <= nonresponse_rate < 1:
        raise ValueError("nonresponse_rate must be in [0, 1)")
    strata = population.groupby(STRATA, observed=True).size()
    allocation = allocate_proportional(strata, target_n)
    rng = np.random.default_rng(seed)
    selected = []
    for key, group in population.groupby(STRATA, sort=True, observed=True):
        positions = rng.choice(len(group), size=int(allocation.loc[key]), replace=False)
        selected.append(group.iloc[positions].copy())
    result = pd.concat(selected, ignore_index=True)
    result = result.rename(columns={"monthly_sales_inr": "observed_sales_inr"})
    result["response_status"] = "Received"
    no_response = rng.random(len(result)) < nonresponse_rate
    result.loc[no_response, "observed_sales_inr"] = np.nan
    result.loc[no_response, "response_status"] = "Missing sales"
    return result.sort_values("store_id").reset_index(drop=True)
