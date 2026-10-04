"""Job recommendations from job titles (decision D-034).

A freelancer types a few skills; the engine returns the best-matching recent
jobs. Three retrieval methods are compared, simplest first:

* ``keyword``: how many of the profile's words (stop words excluded) appear
  in the title as whole words;
* ``tfidf_word``: cosine similarity of TF-IDF vectors built from single words
  and two-word phrases (no phrase contains a stop word);
* ``tfidf_hybrid``: the average of the word similarity and a character
  similarity (3-5 character pieces inside word boundaries), which also links
  "dev" to "developer" or "wordpress" to "word press".

Every method sees the same candidate pool, the same repost handling and the
same diversity rule, so only the matching differs:

* **reposts**: within a chain of possible reposts (same title key, country
  and exact pay terms, at most 3 days apart; decision D-016) only the newest
  posting is kept;
* **diversity**: at most one result per title key, unless there are not
  enough different matches; then the remaining matches fill the list in
  score order;
* only jobs with a positive score are returned; ties go to the newer job.

Filters are strict yes/no rules. Minimum hourly rate: a job passes when the
maximum of the client's stated hourly range is at least the freelancer's
minimum (a $15-$35 job passes a $30 minimum; $15-$25 does not). A job that
states only one rate uses that rate. Jobs without an hourly rate fail an
hourly filter, and fixed-price budgets are never compared with hourly rates.

The evaluation (pooled blind relevance judgements) is title-level: it asks
whether the title fits the profile, not whether the whole job suits the person.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .text import ngrams, tokenize

METHODS = ("keyword", "tfidf_word", "tfidf_hybrid")


def make_title_key(text: str) -> str:
    """The cleaning step's title key, so queries are normalized exactly like titles."""
    from .steps.clean import title_key      # imported here: the steps package imports this module

    return title_key(str(text or ""))


# ------------------------------------------------------------------ pool


def newest_in_repost_chain(frame: pd.DataFrame, days: int = 3) -> pd.Series:
    """True for jobs to keep: drop a job when a *later* possible repost exists.

    A possible repost has the same title key, the same known country and the
    same exact, informative pay terms (``pay_signature``), at most ``days``
    apart. Keeping the newest posting of each chain is the reverse of the
    cleaning flag, which keeps the first.
    """
    keys = ["title_key", "country", "pay_signature"]
    eligible = frame["country"].notna() & frame["pay_signature"].fillna("").ne("")
    subset = frame.loc[eligible, keys + ["posted_at"]].sort_values("posted_at", kind="mergesort")
    gap_to_next = -subset.groupby(keys, sort=False, observed=True)["posted_at"].diff(-1)
    has_later = gap_to_next.notna() & (gap_to_next <= pd.Timedelta(days=days))
    return ~has_later.reindex(frame.index, fill_value=False).astype(bool)


def pool_mask(frame: pd.DataFrame, pool_days: int) -> pd.Series:
    """Jobs posted in the final ``pool_days`` observed days (0 = all days)."""
    if pool_days <= 0:
        return pd.Series(True, index=frame.index)
    dates = np.sort(frame["posted_date"].unique())
    first = dates[-pool_days] if len(dates) >= pool_days else dates[0]
    return frame["posted_date"] >= first


def stated_hourly_max(frame: pd.DataFrame) -> pd.Series:
    """The highest stated hourly rate (NaN when the job states none or is fixed-price)."""
    top = frame[["hourly_low", "hourly_high"]].max(axis=1, skipna=True)
    return top.where(frame["contract_type"].astype(str).eq("hourly"))


def filter_mask(frame: pd.DataFrame, contract: str | None = None, min_hourly: float | None = None,
                min_budget: float | None = None) -> pd.Series:
    """Strict filters. ``min_hourly`` implies hourly jobs; ``min_budget`` implies fixed-price jobs."""
    contract_type = frame["contract_type"].astype(str)
    keep = pd.Series(True, index=frame.index)
    if contract:
        keep &= contract_type.eq(contract)
    if min_hourly is not None:
        keep &= stated_hourly_max(frame).ge(min_hourly).fillna(False).astype(bool)
    if min_budget is not None:
        keep &= contract_type.eq("fixed") & frame["budget"].ge(min_budget).fillna(False).astype(bool)
    return keep


# ----------------------------------------------------------------- index


def word_analyzer(text: str) -> list[str]:
    """Single words and two-word phrases without stop words, from a title key."""
    return list(ngrams(text, 1)) + list(ngrams(text, 2))


@dataclass
class Index:
    """Fitted text index over one table of jobs (row order = ``jobs`` order)."""

    jobs: pd.DataFrame
    word_vectorizer: Any
    char_vectorizer: Any
    word_matrix: Any
    char_matrix: Any
    token_sets: list[frozenset[str]]
    hybrid_word_weight: float
    order_key: np.ndarray = field(repr=False, default=None)

    def query_key(self, text: str) -> str:
        return make_title_key(text)


def build_index(jobs: pd.DataFrame, rules: dict) -> Index:
    """Fit the word and character TF-IDF on the titles of ``jobs``.

    ``jobs`` needs ``title_key`` and ``posted_at``; the vectorizers are fitted on
    every indexed title (the whole time-series window), so the same index
    serves every recency option.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    jobs = jobs.reset_index(drop=True)
    keys = jobs["title_key"].fillna("").astype(str).tolist()
    word = TfidfVectorizer(analyzer=word_analyzer, min_df=int(rules["word_min_df"]), sublinear_tf=True,
                           dtype=np.float32)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(int(rules["char_ngram_min"]), int(rules["char_ngram_max"])),
                           min_df=int(rules["char_min_df"]), sublinear_tf=True, dtype=np.float32)
    word_matrix = word.fit_transform(keys)
    char_matrix = char.fit_transform(keys)
    posted = pd.to_datetime(jobs["posted_at"]).astype("int64").to_numpy()
    return Index(jobs=jobs, word_vectorizer=word, char_vectorizer=char, word_matrix=word_matrix,
                 char_matrix=char_matrix, token_sets=[frozenset(tokenize(k)) for k in keys],
                 hybrid_word_weight=float(rules["hybrid_word_weight"]), order_key=posted)


def scores(index: Index, query: str, method: str, rows: np.ndarray | None = None) -> np.ndarray:
    """Score every indexed job (or the given row positions) against a query text."""
    key = index.query_key(query)
    positions = np.arange(len(index.jobs)) if rows is None else np.asarray(rows)
    if method == "keyword":
        wanted = frozenset(tokenize(key))
        return np.array([len(wanted & index.token_sets[p]) for p in positions], dtype=float)
    word = (index.word_matrix[positions] @ index.word_vectorizer.transform([key]).T).toarray().ravel()
    if method == "tfidf_word":
        return word
    if method == "tfidf_hybrid":
        char = (index.char_matrix[positions] @ index.char_vectorizer.transform([key]).T).toarray().ravel()
        weight = index.hybrid_word_weight
        return weight * word + (1 - weight) * char
    raise ValueError(f"unknown method {method}")


def diverse_top(candidates: pd.DataFrame, k: int) -> pd.DataFrame:
    """Top ``k`` rows of a ranked table, at most one per title key unless too few differ."""
    first = ~candidates["title_key"].duplicated()
    chosen = candidates[first].head(k)
    if len(chosen) < k:
        chosen = pd.concat([chosen, candidates[~first].head(k - len(chosen))])
        chosen = chosen.loc[candidates.index.intersection(chosen.index)]       # back into score order
    return chosen


def recommend(index: Index, query: str, method: str, candidate_mask: pd.Series | np.ndarray, k: int,
              exclude_rows: set[int] | None = None, all_scores: np.ndarray | None = None) -> pd.DataFrame:
    """Ranked recommendations among the candidates (positive scores only).

    ``candidate_mask`` is aligned with ``index.jobs`` (pool, kept reposts and
    filters already combined). Ties go to the newer job, then the lower row id.
    ``all_scores`` (scores for every indexed job) can be passed to reuse one
    scoring pass across several filter settings.
    """
    mask = np.array(candidate_mask, dtype=bool)
    if exclude_rows:
        mask &= ~index.jobs["row_id"].isin(exclude_rows).to_numpy()
    rows = np.flatnonzero(mask)
    if len(rows) == 0:
        return index.jobs.iloc[[]].assign(score=pd.Series(dtype=float), rank=pd.Series(dtype=int))
    values = all_scores[rows] if all_scores is not None else scores(index, query, method, rows)
    positive = values > 0
    rows, values = rows[positive], values[positive]
    order = np.lexsort((index.jobs["row_id"].to_numpy()[rows], -index.order_key[rows], -np.round(values, 9)))
    ranked = index.jobs.iloc[rows[order]].assign(score=values[order])
    top = diverse_top(ranked, k)
    return top.assign(rank=np.arange(1, len(top) + 1))


def similar_jobs(index: Index, row_id: int, method: str, candidate_mask: pd.Series | np.ndarray, k: int) -> pd.DataFrame:
    """Jobs most like one job: its title is the query and the job itself is excluded."""
    match = index.jobs.index[index.jobs["row_id"] == row_id]
    if len(match) == 0:
        raise KeyError(f"row_id {row_id} is not in the index")
    title = index.jobs.loc[match[0], "title_key"]
    return recommend(index, title, method, candidate_mask, k, exclude_rows={int(row_id)})


# ------------------------------------------------------------ evaluation


def dcg(gains: list[float]) -> float:
    return float(sum((2 ** g - 1) / np.log2(i + 2) for i, g in enumerate(gains)))


def ndcg_at_k(ranked_labels: list[float], judged_labels: list[float], k: int) -> float:
    """Graded nDCG@k with gains 2**label - 1.

    ``ranked_labels``: the labels of a method's results in rank order (missing
    positions count as 0). ``judged_labels``: every label judged for the
    profile (the pooled ideal ranking). 0 when nothing judged is relevant.
    """
    ideal = dcg(sorted(judged_labels, reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg(list(ranked_labels[:k])) / ideal


def strict_precision_at_k(ranked_labels: list[float], k: int) -> float:
    """Share of the top ``k`` positions labelled 2 (relevant); missing positions count as not relevant."""
    return float(sum(1 for label in ranked_labels[:k] if label == 2) / k)


def choose_winner(summary: pd.DataFrame, methods: list[str], tie_threshold: float) -> tuple[str, str]:
    """Frozen rule: best mean nDCG@5; within ``tie_threshold`` -> strict P@5; then the simpler method."""
    table = summary.set_index("method").loc[methods]
    best = table["mean_ndcg"].max()
    tied = [m for m in methods if best - table.loc[m, "mean_ndcg"] < tie_threshold]
    if len(tied) == 1:
        return tied[0], "highest mean nDCG@5"
    top_p = table.loc[tied, "mean_precision"].max()
    still = [m for m in tied if np.isclose(table.loc[m, "mean_precision"], top_p)]
    if len(still) == 1:
        return still[0], "nDCG@5 effectively tied; highest strict Precision@5"
    return still[0], "nDCG@5 and Precision@5 tied; simpler method"


# -------------------------------------------------- related market keywords


def related_keywords(top_titles: pd.Series, profile: str, pay: pd.DataFrame, trend: pd.DataFrame,
                     min_jobs: int, max_terms: int, max_q: float, market_titles: pd.Series | None = None,
                     min_lift: float = 0.0, generic_words: frozenset[str] | set[str] = frozenset(),
                     prefix_chars: int = 0) -> pd.DataFrame:
    """Related market keywords to explore (descriptive associations, not advice).

    Candidates are the terms of the Notebook 04 pay table and the Notebook 05
    trend table with supporting evidence: a positive same-country-and-category
    pay association, or a rising keyword share, each with FDR q below
    ``max_q`` (thresholds unchanged from those notebooks). A candidate is kept
    only when

    * it appears in at least ``min_jobs`` of the profile's top matching titles;
    * it adds at least one word that is neither generic (``generic_words``:
      request, action, seniority and job-role words) nor already in the
      profile; a word counts as already present when it shares its first
      ``prefix_chars`` letters with a profile word ("analyst" ~ "analysis"),
      or is identical for shorter words;
    * it is disproportionately common in the matched jobs: its share there is
      at least ``min_lift`` times its share in ``market_titles`` (the pool).

    An empty result is a valid answer: no strongly supported keyword.
    (Decision D-034: the generic-word, prefix and lift rules were added once,
    after the first version returned overly generic words.)
    """
    profile_key = make_title_key(profile)
    profile_terms = set(ngrams(profile_key, 1)) | set(ngrams(profile_key, 2))
    profile_words = set(profile_key.split())

    def already_present(word: str) -> bool:
        if word in profile_words:
            return True
        if prefix_chars and len(word) >= prefix_chars:
            return any(len(p) >= prefix_chars and p[:prefix_chars] == word[:prefix_chars] for p in profile_words)
        return False

    def adds_something(term: str) -> bool:
        return any(not w.isdigit() and w not in generic_words and not already_present(w) for w in term.split())

    def term_sets(titles: pd.Series) -> list[set[str]]:
        return [set(ngrams(t, 1)) | set(ngrams(t, 2)) for t in titles.fillna("").astype(str)]

    title_terms = term_sets(top_titles)
    market_terms = term_sets(market_titles) if market_titles is not None and min_lift > 0 else None
    evidence = {}
    if not pay.empty:
        for row in pay.itertuples(index=False):
            if row.country_category_p_fdr < max_q and row.country_category_pct > 0:
                evidence.setdefault(row.keyword, {})["pay_pct"] = float(row.country_category_pct)
    if not trend.empty:
        for row in trend.itertuples(index=False):
            if row.p_fdr < max_q and row.change_pp > 0:
                evidence.setdefault(row.keyword, {})["trend_relative_pct"] = float(row.relative_change_pct)
    rows = []
    for term, facts in evidence.items():
        if term in profile_terms or not adds_something(term):
            continue
        count = sum(term in terms for terms in title_terms)
        if count < min_jobs:
            continue
        lift = np.nan
        if market_terms is not None:
            market_share = sum(term in terms for terms in market_terms) / max(len(market_terms), 1)
            lift = (count / len(title_terms)) / market_share if market_share > 0 else np.inf
            if lift < min_lift:
                continue
        rows.append({"keyword": term, "matching_jobs": count, "lift": lift, **facts})
    columns = ["keyword", "matching_jobs", "lift", "pay_pct", "trend_relative_pct"]
    if not rows:
        return pd.DataFrame(columns=columns)
    table = pd.DataFrame(rows).reindex(columns=columns)
    return table.sort_values(["matching_jobs", "keyword"], ascending=[False, True]).head(max_terms).reset_index(drop=True)


NO_KEYWORD_MESSAGE = "No strongly supported related market keyword is available for this profile."


def describe_keyword(row: pd.Series) -> str:
    """Plain-English evidence for one related keyword (never causal)."""
    parts = []
    if pd.notna(row.get("pay_pct")):
        parts.append(f"associated with {row['pay_pct']:+.0f}% higher hourly offers in the same country and category")
    if pd.notna(row.get("trend_relative_pct")):
        parts.append(f"its job share grew {row['trend_relative_pct']:+.0f}% over the observed weeks")
    lift = f" ({row['lift']:.1f} times its share in all pool jobs)" if pd.notna(row.get("lift")) else ""
    return (f"'{row['keyword']}' appears in {int(row['matching_jobs'])} of the best-matching jobs{lift}; "
            + " and ".join(parts) + ".")
