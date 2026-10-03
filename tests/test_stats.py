import pandas as pd
import pytest

from job_market.stats import cramers_v


def test_independent_variables_give_zero():
    table = pd.DataFrame([[50, 50], [50, 50]])
    assert cramers_v(table) == pytest.approx(0.0)


def test_perfect_association_gives_one():
    table = pd.DataFrame([[100, 0], [0, 100]])
    assert cramers_v(table) == pytest.approx(1.0)


def test_value_does_not_grow_with_sample_size():
    small = pd.DataFrame([[60, 40], [40, 60]])
    assert cramers_v(small) == pytest.approx(cramers_v(small * 1000))


def test_empty_rows_and_single_columns_are_handled():
    assert cramers_v(pd.DataFrame([[10, 0], [0, 0]])) == 0.0
    assert cramers_v(pd.DataFrame([[5], [7]])) == 0.0
