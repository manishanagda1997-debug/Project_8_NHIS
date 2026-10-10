"""Pay analysis helpers for Task 1 (keywords and pay) and Task 4 (country rates).

Decision D-031. All pay models work on the natural log of pay, so a
coefficient ``b`` is a ratio: the percentage difference is ``(exp(b) - 1) * 100``
(``b * 100`` is only an approximation for small ``b``).

Keyword associations are measured in three layers, each answering a different
question:

* ``raw``: jobs with the keyword versus jobs without it;
* ``country``: the same comparison *within the same client country*;
* ``country_category``: within the same client country *and* assigned job
  function. The category is itself derived from the title, so this layer
  partly controls away the title signal under study; it is reported next to
  the others, never as "the" correct answer.

Uncertainty is clustered by ``title_key``: postings that share a title are not
independent evidence. All results are associations, not causal effects.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import norm

from .text import STOP_WORDS, words

LAYERS = ("raw", "country", "country_category")
OTHER_COUNTRY = "(other)"
MISSING_COUNTRY = "(missing)"

# ISO 3166 alpha-3 codes for the interactive map. Countries not listed here
# still appear in every table; the notebook lists any that are missing a code.
ISO3 = {
    "Afghanistan": "AFG", "Albania": "ALB", "Algeria": "DZA", "Andorra": "AND", "Argentina": "ARG",
    "Armenia": "ARM", "Australia": "AUS", "Austria": "AUT", "Azerbaijan": "AZE", "Bahamas": "BHS",
    "Bahrain": "BHR", "Bangladesh": "BGD", "Barbados": "BRB", "Belarus": "BLR", "Belgium": "BEL",
    "Bermuda": "BMU", "Bolivia": "BOL", "Bosnia and Herzegovina": "BIH", "Botswana": "BWA", "Brazil": "BRA",
    "Brunei": "BRN", "Bulgaria": "BGR", "Cambodia": "KHM", "Cameroon": "CMR", "Canada": "CAN",
    "Cayman Islands": "CYM", "Chile": "CHL", "China": "CHN", "Colombia": "COL", "Costa Rica": "CRI",
    "Croatia": "HRV", "Cyprus": "CYP", "Czech Republic": "CZE", "Denmark": "DNK", "Dominican Republic": "DOM",
    "Ecuador": "ECU", "Egypt": "EGY", "El Salvador": "SLV", "Estonia": "EST", "Ethiopia": "ETH",
    "Fiji": "FJI", "Finland": "FIN", "France": "FRA", "Georgia": "GEO", "Germany": "DEU", "Ghana": "GHA",
    "Gibraltar": "GIB", "Greece": "GRC", "Guam": "GUM", "Guatemala": "GTM", "Honduras": "HND",
    "Hong Kong": "HKG", "Hungary": "HUN", "Iceland": "ISL", "India": "IND", "Indonesia": "IDN",
    "Iran": "IRN", "Iraq": "IRQ", "Ireland": "IRL", "Israel": "ISR", "Italy": "ITA", "Ivory Coast": "CIV",
    "Jamaica": "JAM", "Japan": "JPN", "Jordan": "JOR", "Kazakhstan": "KAZ", "Kenya": "KEN", "Kuwait": "KWT",
    "Kyrgyzstan": "KGZ", "Latvia": "LVA", "Lebanon": "LBN", "Libya": "LBY", "Liechtenstein": "LIE",
    "Lithuania": "LTU", "Luxembourg": "LUX", "Macao": "MAC", "Macedonia": "MKD", "Madagascar": "MDG",
    "Malawi": "MWI", "Malaysia": "MYS", "Maldives": "MDV", "Malta": "MLT", "Mauritius": "MUS",
    "Mexico": "MEX", "Moldova": "MDA", "Monaco": "MCO", "Mongolia": "MNG", "Montenegro": "MNE",
    "Morocco": "MAR", "Mozambique": "MOZ", "Myanmar": "MMR", "Namibia": "NAM", "Nepal": "NPL",
    "Netherlands": "NLD", "New Zealand": "NZL", "Nicaragua": "NIC", "Nigeria": "NGA", "Norway": "NOR",
    "Oman": "OMN", "Pakistan": "PAK", "Palestinian Territories": "PSE", "Panama": "PAN",
    "Papua New Guinea": "PNG", "Paraguay": "PRY", "Peru": "PER", "Philippines": "PHL", "Poland": "POL",
    "Portugal": "PRT", "Puerto Rico": "PRI", "Qatar": "QAT", "Romania": "ROU", "Russia": "RUS",
    "Rwanda": "RWA", "Saudi Arabia": "SAU", "Senegal": "SEN", "Serbia": "SRB", "Singapore": "SGP",
    "Slovakia": "SVK", "Slovenia": "SVN", "South Africa": "ZAF", "South Korea": "KOR", "Spain": "ESP",
    "Sri Lanka": "LKA", "Sweden": "SWE", "Switzerland": "CHE", "Taiwan": "TWN", "Tanzania": "TZA",
    "Thailand": "THA", "Trinidad and Tobago": "TTO", "Tunisia": "TUN", "Turkey": "TUR", "Uganda": "UGA",
    "Ukraine": "UKR", "United Arab Emirates": "ARE", "United Kingdom": "GBR", "United States": "USA",
    "Uruguay": "URY", "Uzbekistan": "UZB", "Venezuela": "VEN", "Vietnam": "VNM", "Yemen": "YEM",
    "Zambia": "ZMB", "Zimbabwe": "ZWE",
}


def percent(log_ratio: float | np.ndarray) -> float | np.ndarray:
    """Percentage difference from a log ratio: (exp(b) - 1) * 100."""
    return (np.exp(log_ratio) - 1.0) * 100.0


# ------------------------------------------------------------------ keywords


def title_terms(title_key: object) -> set[str]:
    """Binary presence: the distinct words and two-word phrases of one title.

    Stop words are dropped, and a phrase never spans a stop word (decision
    D-024). Words come from ``title_key``, which keeps ``c++`` and ``c#``.
    """
    tokens = words(title_key)
    single = {t for t in tokens if t not in STOP_WORDS}
    pairs = {f"{a} {b}" for a, b in zip(tokens, tokens[1:]) if a not in STOP_WORDS and b not in STOP_WORDS}
    return single | pairs


def select_keywords(
    title_keys: pd.Series, min_jobs: int, min_title_keys: int, overlap: float
) -> pd.DataFrame:
    """Keywords with enough support, one row each.

    A keyword needs ``min_jobs`` jobs and ``min_title_keys`` distinct title keys,
    so one heavily repeated title cannot carry it. A single word is dropped
    when at least ``overlap`` of its jobs also contain a kept two-word phrase
    that includes it ("social" inside "social media"): the two would measure
    the same jobs twice.
    """
    jobs: Counter[str] = Counter()
    keys: dict[str, set[str]] = defaultdict(set)
    for key in title_keys:
        for term in title_terms(key):
            jobs[term] += 1
            keys[term].add(key)
    kept = {t for t, n in jobs.items() if n >= min_jobs and len(keys[t]) >= min_title_keys}
    phrases = [t for t in kept if " " in t]
    dropped: dict[str, str] = {}
    if phrases:
        term_sets = [title_terms(key) for key in title_keys]
        for word in sorted(t for t in kept if " " not in t):
            containing = [p for p in phrases if word in p.split()]
            if not containing:
                continue
            with_word = [terms for terms in term_sets if word in terms]
            covered = sum(1 for terms in with_word if any(p in terms for p in containing))
            if with_word and covered / len(with_word) >= overlap:
                dropped[word] = max(containing, key=lambda p: jobs[p])
    rows = [
        {"keyword": t, "jobs": jobs[t], "title_keys": len(keys[t]), "words": len(t.split())}
        for t in sorted(kept - set(dropped))
    ]
    return pd.DataFrame(rows, columns=["keyword", "jobs", "title_keys", "words"])


def keyword_matrix(title_keys: Iterable[object], keywords: list[str]) -> sparse.csc_matrix:
    """Binary job x keyword matrix (1 = the title contains the keyword)."""
    keys = list(title_keys)
    index = {k: i for i, k in enumerate(keywords)}
    rows, cols = [], []
    for row, key in enumerate(keys):
        for term in title_terms(key):
            col = index.get(term)
            if col is not None:
                rows.append(row)
                cols.append(col)
    data = np.ones(len(rows), dtype=np.float64)
    return sparse.csc_matrix((data, (rows, cols)), shape=(len(keys), len(keywords)))


# ------------------------------------------------------------------ estimation


def _codes(values: pd.Series | np.ndarray) -> np.ndarray:
    return pd.factorize(pd.Series(values).astype(str), sort=True)[0]


def within_association(
    y: np.ndarray, x: np.ndarray, cells: np.ndarray, clusters: np.ndarray
) -> tuple[float, float]:
    """Slope of ``y`` on a 0/1 ``x`` within groups (``cells``), with a
    cluster-robust standard error.

    Demeaning both variables inside each cell is the same as a regression with
    one dummy per cell (Frisch-Waugh-Lovell theorem). The standard error adds up
    each cluster's contribution (CR1, with the G/(G-1) correction), so repeated
    postings of one title count as one piece of evidence.
    """
    counts = np.bincount(cells)
    safe = np.maximum(counts, 1)
    x_t = x - (np.bincount(cells, weights=x) / safe)[cells]
    y_t = y - (np.bincount(cells, weights=y) / safe)[cells]
    sxx = float(x_t @ x_t)
    if sxx <= 1e-12:
        return float("nan"), float("nan")
    beta = float(x_t @ y_t) / sxx
    score = np.bincount(clusters, weights=x_t * (y_t - beta * x_t))
    groups = int((np.bincount(clusters) > 0).sum())
    variance = (groups / max(groups - 1, 1)) * float(score @ score) / sxx**2
    return beta, float(np.sqrt(variance))


def benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
    """False-discovery-rate adjusted p-values (Benjamini-Hochberg).

    Testing hundreds of keywords makes some look significant by chance; the
    adjusted value controls the expected share of false discoveries.
    """
    p = np.asarray(p_values, dtype=float)
    adjusted = np.full(p.shape, np.nan)
    ok = ~np.isnan(p)
    values = p[ok]
    if values.size == 0:
        return adjusted
    order = np.argsort(values)
    ranked = values[order] * values.size / np.arange(1, values.size + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    result = np.empty_like(values)
    result[order] = np.minimum(ranked, 1.0)
    adjusted[ok] = result
    return adjusted


def keyword_associations(
    frame: pd.DataFrame, value: str, keywords: list[str], country_group: pd.Series, category: pd.Series
) -> pd.DataFrame:
    """Three-layer keyword association table for one pay measure.

    ``frame`` holds ``title_key`` and the pay column ``value`` (positive);
    ``country_group`` and ``category`` align with ``frame``.
    """
    y = np.log(frame[value].to_numpy(dtype=float))
    matrix = keyword_matrix(frame["title_key"].tolist(), keywords)
    clusters = _codes(frame["title_key"])
    cells = {
        "raw": np.zeros(len(frame), dtype=np.int64),
        "country": _codes(country_group),
        "country_category": _codes(country_group.astype(str) + "|" + category.astype(str)),
    }
    pay = frame[value].to_numpy(dtype=float)
    rows = []
    for j, keyword in enumerate(keywords):
        x = matrix[:, j].toarray().ravel()
        has = x > 0
        row = {
            "keyword": keyword,
            "jobs": int(has.sum()),
            "title_keys": int(pd.Series(clusters[has]).nunique()),
            "median_with": float(np.median(pay[has])) if has.any() else np.nan,
            "median_without": float(np.median(pay[~has])) if (~has).any() else np.nan,
        }
        for layer in LAYERS:
            beta, se = within_association(y, x, cells[layer], clusters)
            z = beta / se if se and se > 0 else np.nan
            row[f"{layer}_pct"] = percent(beta)
            row[f"{layer}_low_pct"] = percent(beta - 1.96 * se)
            row[f"{layer}_high_pct"] = percent(beta + 1.96 * se)
            row[f"{layer}_p"] = float(2 * norm.sf(abs(z))) if np.isfinite(z) else np.nan
        rows.append(row)
    columns = ["keyword", "jobs", "title_keys", "median_with", "median_without"] + [
        f"{layer}_{part}" for layer in LAYERS for part in ("pct", "low_pct", "high_pct", "p")]
    table = pd.DataFrame(rows, columns=columns)
    for layer in LAYERS:
        table[f"{layer}_p_fdr"] = benjamini_hochberg(table[f"{layer}_p"].to_numpy())
    return table


# ------------------------------------------------------------------ countries


def country_groups(country: pd.Series, keep: set[str]) -> pd.Series:
    """Countries with enough jobs keep their name; others become "(other)";
    a missing country stays its own group, never merged with real names."""
    text = country.astype("object")
    grouped = text.where(text.isin(keep), OTHER_COUNTRY)
    return grouped.where(text.notna(), MISSING_COUNTRY).astype(str)


def weighted_median(sorted_values: np.ndarray, weights: np.ndarray) -> float:
    """Median of values (already sorted) that each count ``weights`` times."""
    cumulative = np.cumsum(weights)
    return float(sorted_values[np.searchsorted(cumulative, cumulative[-1] / 2.0)])


def bootstrap_median(
    values: np.ndarray, clusters: np.ndarray, reps: int, rng: np.random.Generator
) -> tuple[float, float]:
    """95% percentile interval for a median, resampling whole title clusters.

    Drawing clusters with replacement is the same as giving every job the
    number of times its cluster was drawn as a weight, which keeps this fast.
    """
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    codes = pd.factorize(clusters)[0][order]
    n_clusters = codes.max() + 1
    medians = np.empty(reps)
    for r in range(reps):
        multiplicity = np.bincount(rng.integers(0, n_clusters, n_clusters), minlength=n_clusters)
        medians[r] = weighted_median(sorted_values, multiplicity[codes].astype(float))
    low, high = np.percentile(medians, [2.5, 97.5])
    return float(low), float(high)


def bootstrap_mean(
    values: np.ndarray, clusters: np.ndarray, reps: int, rng: np.random.Generator
) -> tuple[float, float]:
    """95% percentile interval for a mean, resampling whole title clusters (as ``bootstrap_median``)."""
    codes = pd.factorize(clusters)[0]
    n_clusters = codes.max() + 1
    means = np.empty(reps)
    for r in range(reps):
        weights = np.bincount(rng.integers(0, n_clusters, n_clusters), minlength=n_clusters)[codes].astype(float)
        means[r] = float(weights @ values / weights.sum())
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def country_effects(
    y: np.ndarray, country: np.ndarray, category: np.ndarray, weights: np.ndarray | None = None
) -> np.ndarray:
    """Additive model log pay = country effect + category effect.

    Returns one effect per country code (in code order). Solved with the
    normal equations on a sparse dummy matrix; the first category is the
    reference (any choice gives the same country differences).
    """
    n = len(y)
    countries = int(country.max()) + 1
    categories = int(category.max()) + 1
    rows = np.arange(n)
    c_part = sparse.csr_matrix((np.ones(n), (rows, country)), shape=(n, countries))
    k_part = sparse.csr_matrix((np.ones(n), (rows, category)), shape=(n, categories))[:, 1:]
    design = sparse.hstack([c_part, k_part]).tocsr()
    w = np.ones(n) if weights is None else weights
    weighted = design.multiply(w[:, None]).tocsr()
    xtx = (design.T @ weighted).toarray()
    xty = weighted.T @ y
    coef = np.linalg.lstsq(xtx, xty, rcond=None)[0]
    return coef[:countries]


def adjusted_country_index(
    y: np.ndarray, country: np.ndarray, category: np.ndarray, clusters: np.ndarray, reps: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Category-adjusted country index in percent, with a cluster bootstrap.

    The index compares clients in each country with the job-weighted average
    client, holding the job-category mix fixed: +20 means 20% more for the
    same kinds of work.
    """
    jobs = np.bincount(country)
    share = jobs / jobs.sum()

    def index(effects: np.ndarray) -> np.ndarray:
        return percent(effects - float(effects @ share))

    point = index(country_effects(y, country, category))
    cluster_codes = pd.factorize(clusters)[0]
    n_clusters = cluster_codes.max() + 1
    draws = np.empty((reps, len(point)))
    for r in range(reps):
        multiplicity = np.bincount(rng.integers(0, n_clusters, n_clusters), minlength=n_clusters)
        draws[r] = index(country_effects(y, country, category, multiplicity[cluster_codes].astype(float)))
    low, high = np.nanpercentile(draws, [2.5, 97.5], axis=0)
    return pd.DataFrame({"adjusted_index_pct": point, "adjusted_low_pct": low, "adjusted_high_pct": high})
