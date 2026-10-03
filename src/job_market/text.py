"""Small reusable text helpers for job-title exploration (decision D-024).

Words come from ``title_key`` (lower case, letters and digits only, built in
the cleaning step). Stop words are common filler words that carry little
meaning in a job title.

Phrases (n-grams) are built from the words in their original order, and any
phrase that contains a stop word is dropped. Removing stop words first and
pairing the remaining words would invent phrases nobody wrote: "web developer
needed for wordpress" would produce "developer wordpress".
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator

import pandas as pd

# Filler words only. Words that can carry meaning in a job title stay out of
# this list on purpose: "it" (IT support), "us" (US-based), "up", "free".
STOP_WORDS = frozenset(
    {
        "a", "an", "and", "are", "at", "be", "by", "for", "from", "i", "in", "is",
        "looking", "my", "need", "needed", "of", "on", "or", "our", "the", "this",
        "to", "we", "with", "you", "your",
    }
)


def words(title_key: object) -> list[str]:
    """All words of a title key, in order, stop words included."""
    if not isinstance(title_key, str):
        return []
    return title_key.lower().split()


def tokenize(title_key: object) -> list[str]:
    """Words of a title key without stop words (for single-word counts)."""
    return [word for word in words(title_key) if word not in STOP_WORDS]


def ngrams(title_key: object, n: int) -> Iterator[str]:
    """Phrases of ``n`` consecutive words that contain no stop word.

    ``n = 1`` gives the same words as ``tokenize``.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    tokens = words(title_key)
    for index in range(len(tokens) - n + 1):
        window = tokens[index : index + n]
        if not any(word in STOP_WORDS for word in window):
            yield " ".join(window)


def count_ngrams(series: Iterable[object], n: int = 1) -> Counter[str]:
    """Count phrases of ``n`` words over many title keys."""
    counts: Counter[str] = Counter()
    for title_key in series:
        counts.update(ngrams(title_key, n))
    return counts


def top_ngrams(series: pd.Series, n: int = 1, k: int = 20) -> pd.DataFrame:
    """The ``k`` most common phrases of ``n`` words, as a table of term and count."""
    if n < 1:
        raise ValueError("n must be at least 1")
    if k < 1:
        raise ValueError("k must be at least 1")
    counts = count_ngrams(series.dropna(), n)
    return pd.DataFrame(counts.most_common(k), columns=["term", "count"])
