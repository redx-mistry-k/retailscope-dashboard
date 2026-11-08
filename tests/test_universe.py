import numpy as np
import pytest

from retailscope.data import generate_population
from retailscope.universe import estimate_two_list_universe, simulate_two_lists


def test_chapman_two_list_point_estimate():
    result = estimate_two_list_universe({"1", "2", "3", "4"}, {"1", "2", "5", "6"})
    assert result.overlap_n == 2
    assert result.estimated_n == pytest.approx(25 / 3 - 1)


def test_sparse_overlap_withholds_universe_estimate():
    result = estimate_two_list_universe({"1", "2"}, {"2", "3"})
    assert np.isnan(result.estimated_n)
    assert result.status == "Insufficient list overlap"


def test_two_list_simulation_reproducible_and_census_exact():
    population = generate_population(480, seed=8)
    a = simulate_two_lists(population, .4, .6, seed=12)
    b = simulate_two_lists(population, .4, .6, seed=12)
    assert a == b
    census = simulate_two_lists(population, 1, 1, seed=12)
    assert census.estimated_n == len(population)
