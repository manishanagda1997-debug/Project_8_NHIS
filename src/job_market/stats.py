"""Small statistics helpers shared by several notebooks."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency


def cramers_v(table: pd.DataFrame) -> float:
    """Cramér's V for a contingency table (counts of two categorical variables).

    Cramér's V measures how strongly two categorical variables are associated:
    0 means no association, 1 means one variable fully determines the other.
    Unlike a p-value, it does not grow with the number of rows, so it stays
    meaningful on large data. Common reading: below 0.1 negligible, 0.1-0.3
    small, 0.3-0.5 medium, above 0.5 large (for tables with two columns).
    """
    counts = np.asarray(table, dtype=float)
    counts = counts[counts.sum(axis=1) > 0][:, counts.sum(axis=0) > 0]
    rows, cols = counts.shape
    if rows < 2 or cols < 2:
        return 0.0
    chi2 = chi2_contingency(counts, correction=False)[0]
    return float(np.sqrt(chi2 / (counts.sum() * (min(rows, cols) - 1))))
