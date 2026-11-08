"""Illustrative two-list store-universe estimation on synthetic records."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class UniverseEstimate:
    list_a_n: int
    list_b_n: int
    overlap_n: int
    estimated_n: float
    status: str


def estimate_two_list_universe(list_a_ids: set[str], list_b_ids: set[str]) -> UniverseEstimate:
    """Chapman two-list point estimate; withhold when overlap is sparse.

    Assumes a closed population, independent lists, equal capture probability
    within the domain, accurate matching, and no duplicate or false records.
    """
    a, b = len(list_a_ids), len(list_b_ids)
    overlap = len(list_a_ids & list_b_ids)
    if overlap < 2:
        return UniverseEstimate(a, b, overlap, np.nan, "Insufficient list overlap")
    estimate = (a + 1) * (b + 1) / (overlap + 1) - 1
    return UniverseEstimate(a, b, overlap, float(estimate), "Illustrative estimate")


def simulate_two_lists(population: pd.DataFrame, probability_a: float = .45,
                       probability_b: float = .55, seed: int = 77) -> UniverseEstimate:
    """Independently include known synthetic stores in two pretend lists."""
    if not 0 < probability_a <= 1 or not 0 < probability_b <= 1:
        raise ValueError("List inclusion probabilities must be in (0, 1]")
    if population.store_id.duplicated().any():
        raise ValueError("Population store IDs must be unique")
    rng = np.random.default_rng(seed)
    ids = population.store_id.to_numpy()
    a = set(ids[rng.random(len(ids)) < probability_a])
    b = set(ids[rng.random(len(ids)) < probability_b])
    return estimate_two_list_universe(a, b)
