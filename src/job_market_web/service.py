"""Request validation and responses for the recommendation API (decision D-035).

The public API always uses the evaluated winner (the hybrid word + character
TF-IDF). Every request parameter is checked; a filter that does not fit the
chosen job type is an error, never silently ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from job_market.recommend import (
    NO_KEYWORD_MESSAGE, Index, build_index, describe_keyword, filter_mask, market_term_shares, pay_text, pool_mask,
    recommend, related_keywords, similar_jobs,
)

PUBLIC_METHOD_NAMES = {"tfidf_hybrid": "hybrid_word_character_tfidf", "tfidf_word": "word_tfidf",
                       "keyword": "keyword_count"}
DAY_CHOICES = {"7": 7, "14": 14, "30": 30, "all": 0}
CONTRACTS = ("all", "hourly", "fixed")
MAX_SKILLS_CHARS = 300
MAX_HOURLY = 1000.0
MAX_BUDGET = 1_000_000.0
RECOMMEND_PARAMS = {"skills", "days", "contract", "min_hourly", "min_budget"}
SIMILAR_PARAMS = {"days"}
NOTES = [
    "Matches are based on job titles only; the data has no job descriptions.",
    "Jobs were posted in February and March 2024; links may point to closed jobs.",
    "Related market keywords describe associations in the data, not advice on what to learn.",
]


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _number(raw: str, name: str, upper: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ApiError(400, f"{name} must be a number.") from None
    if not math.isfinite(value) or value <= 0:
        raise ApiError(400, f"{name} must be a positive number.")
    if value > upper:
        raise ApiError(400, f"{name} must be at most {upper:,.0f}.")
    return value


def parse_days(args: dict[str, str]) -> int:
    raw = str(args.get("days", "14")).strip().lower()
    if raw not in DAY_CHOICES:
        raise ApiError(400, "days must be one of 7, 14, 30 or all.")
    return DAY_CHOICES[raw]


def parse_recommend(args: dict[str, str]) -> dict[str, Any]:
    """Validate the query of /api/recommend."""
    unknown = sorted(set(args) - RECOMMEND_PARAMS)
    if unknown:
        raise ApiError(400, f"Unknown parameter(s): {', '.join(unknown)}. Allowed: {', '.join(sorted(RECOMMEND_PARAMS))}.")
    skills = str(args.get("skills", "")).strip()
    if not skills:
        raise ApiError(400, "skills is required, for example skills=python, pandas, sql.")
    if len(skills) > MAX_SKILLS_CHARS:
        raise ApiError(400, f"skills must be at most {MAX_SKILLS_CHARS} characters.")
    if not any(ch.isalnum() for ch in skills):
        raise ApiError(400, "skills must contain at least one word.")
    contract = str(args.get("contract", "all")).strip().lower()
    if contract not in CONTRACTS:
        raise ApiError(400, "contract must be one of all, hourly or fixed.")
    min_hourly = min_budget = None
    if args.get("min_hourly") not in (None, ""):
        if contract != "hourly":
            raise ApiError(400, "min_hourly can only be used with contract=hourly.")
        min_hourly = _number(args["min_hourly"], "min_hourly", MAX_HOURLY)
    if args.get("min_budget") not in (None, ""):
        if contract != "fixed":
            raise ApiError(400, "min_budget can only be used with contract=fixed.")
        min_budget = _number(args["min_budget"], "min_budget", MAX_BUDGET)
    return {"skills": skills, "days": parse_days(args), "contract": contract, "min_hourly": min_hourly,
            "min_budget": min_budget}


def describe_filters(query: dict[str, Any]) -> list[str]:
    days = query["days"]
    lines = ["Jobs posted in " + ("all available days (37)." if days == 0 else f"the final {days} days of the data.")]
    lines.append("Only the newest posting of each possible-repost chain; at most one result per title unless "
                 "too few different titles match.")
    if query["contract"] == "hourly":
        lines.append("Hourly jobs only.")
    elif query["contract"] == "fixed":
        lines.append("Fixed-price jobs only.")
    if query["min_hourly"] is not None:
        lines.append(f"Minimum hourly rate ${query['min_hourly']:g}: a job passes when the maximum of the client's "
                     "stated hourly range reaches it; jobs without a stated rate are excluded.")
    if query["min_budget"] is not None:
        lines.append(f"Minimum budget ${query['min_budget']:g}: fixed-price jobs whose budget is at least this amount.")
    return lines


@dataclass
class RecommenderService:
    """Holds the index and evidence tables; answers API requests."""

    index: Index
    rules: dict
    method: str
    build_id: str
    pay: pd.DataFrame = field(default_factory=pd.DataFrame)
    trend: pd.DataFrame = field(default_factory=pd.DataFrame)
    _shares: dict[int, dict[str, float]] = field(default_factory=dict, repr=False)

    @classmethod
    def from_tables(cls, jobs: pd.DataFrame, rules: dict, method: str, build_id: str,
                    pay: pd.DataFrame | None = None, trend: pd.DataFrame | None = None) -> "RecommenderService":
        return cls(index=build_index(jobs, rules), rules=rules, method=method, build_id=build_id,
                   pay=pay if pay is not None else pd.DataFrame(), trend=trend if trend is not None else pd.DataFrame())

    # ------------------------------------------------------------ helpers
    @property
    def public_method(self) -> str:
        return PUBLIC_METHOD_NAMES.get(self.method, self.method)

    def meta(self) -> dict[str, Any]:
        return {"build_id": self.build_id, "recommender_version": str(self.rules.get("recommender_version", "")),
                "method": self.public_method}

    def pool(self, days: int) -> np.ndarray:
        jobs = self.index.jobs
        return (pool_mask(jobs, days) & jobs["newest_in_chain"]).to_numpy()

    def market_shares(self, days: int) -> dict[str, float]:
        if days not in self._shares:
            terms = set(self.pay.get("keyword", pd.Series(dtype=str))) | set(self.trend.get("keyword", pd.Series(dtype=str)))
            titles = self.index.jobs.loc[self.pool(days), "title_key"]
            self._shares[days] = market_term_shares(titles, terms)
        return self._shares[days]

    @staticmethod
    def job_record(row: pd.Series, rank: int | None = None) -> dict[str, Any]:
        record = {
            "row_id": int(row["row_id"]),
            "title": row["title_clean"],
            "link": row["link"] if isinstance(row.get("link"), str) else None,
            "contract_type": str(row["contract_type"]),
            "pay": pay_text(row["contract_type"], row["hourly_low"], row["hourly_high"], row["budget"]),
            "country": row["country"] if isinstance(row.get("country"), str) else None,
            "posted_date": pd.Timestamp(row["posted_date"]).strftime("%Y-%m-%d"),
            "category": row.get("primary_category"),
        }
        if rank is not None:
            record = {"rank": int(rank), **record, "score": round(float(row["score"]), 4)}
        return record

    # ------------------------------------------------------------ endpoints
    def health(self) -> dict[str, Any]:
        return {"status": "ok", **self.meta(), "indexed_jobs": int(len(self.index.jobs)),
                "days_options": list(DAY_CHOICES)}

    def recommend(self, args: dict[str, str]) -> dict[str, Any]:
        query = parse_recommend(args)
        jobs = self.index.jobs
        allowed = self.pool(query["days"]) & filter_mask(
            jobs, contract=None if query["contract"] == "all" else query["contract"],
            min_hourly=query["min_hourly"], min_budget=query["min_budget"]).to_numpy()
        top = recommend(self.index, query["skills"], self.method, allowed, int(self.rules["results"]))
        related = self.related(query["skills"], query["days"])
        return {**self.meta(), "query": query, "filters_applied": describe_filters(query),
                "candidate_pool_size": int(allowed.sum()), "returned_count": int(len(top)),
                "results": [self.job_record(row, row["rank"]) for _, row in top.iterrows()],
                "related_keywords": related, "notes": NOTES}

    def related(self, skills: str, days: int) -> dict[str, Any]:
        rules = self.rules
        top = recommend(self.index, skills, self.method, self.pool(days), int(rules["related_top_jobs"]))
        table = related_keywords(top["title_key"], skills, self.pay, self.trend, int(rules["related_min_jobs"]),
                                 int(rules["related_max_terms"]), float(rules["related_max_q"]),
                                 min_lift=float(rules["related_min_lift"]),
                                 generic_words=frozenset(rules["related_generic_words"]),
                                 prefix_chars=int(rules["related_prefix_chars"]),
                                 market_shares=self.market_shares(days))
        items = [{"keyword": row["keyword"], "matching_jobs": int(row["matching_jobs"]),
                  "lift": round(float(row["lift"]), 2), "sentence": describe_keyword(row)} for _, row in table.iterrows()]
        return {"items": items, "message": None if items else NO_KEYWORD_MESSAGE}

    def similar(self, row_id: int, args: dict[str, str]) -> dict[str, Any]:
        unknown = sorted(set(args) - SIMILAR_PARAMS)
        if unknown:
            raise ApiError(400, f"Unknown parameter(s): {', '.join(unknown)}. Allowed: days.")
        days = parse_days(args)
        jobs = self.index.jobs
        match = np.flatnonzero(jobs["row_id"].to_numpy() == row_id)
        if len(match) == 0:
            raise ApiError(404, "Job not found.")
        top = similar_jobs(self.index, row_id, self.method, self.pool(days), 5)
        return {**self.meta(), "selected": self.job_record(jobs.iloc[match[0]]), "days": days,
                "returned_count": int(len(top)), "results": [self.job_record(row, row["rank"]) for _, row in top.iterrows()]}
