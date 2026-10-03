"""Step 2 - clean: one master table with every raw row, cleaned text,
foundational features and flags.

Rules of this step (decisions D-012 to D-019):

* Every raw row stays. 244,828 rows in, 244,828 rows out. Problems become
  flag columns; nothing is filled in and nothing is deleted.
* The eight raw columns stay byte-for-byte unchanged. Cleaned values live in
  new columns next to them.
* Eligibility flags say which later analysis may use a row. A row that is
  kept is not automatically valid for every analysis.

The output ``jobs_clean.parquet`` is the single input of every later
notebook, the database and the dashboard. Small audit tables record each
cleaning rule with its evidence and the number of rows it touches.
"""

from __future__ import annotations

import html
import re
import unicodedata
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from ..config import Settings
from ..io import write_csv, write_parquet
from ..manifest import StepRecord, describe_output

NAME = "clean"
DESCRIPTION = "Clean titles, add time, pay, quality, repeat and eligibility columns; keep every raw row."

RAW_COLUMNS = ("title", "link", "published_date", "is_hourly", "hourly_low", "hourly_high", "budget", "country")
# Text columns with only a few distinct values, stored as categories.
CATEGORY_COLUMNS = ("title_script", "iso_week", "contract_type", "pay_info", "day_status")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Typical traces of UTF-8 bytes decoded with a Windows code page ("mojibake"),
# for example "f\u00c3\u00bcr" for "f\u00fcr", "\u00e2\u20ac\u2122" for a right quote and
# "\u011f\u0178\u0161\u20ac" for an emoji. Used to flag titles that stay damaged.
MOJIBAKE = re.compile(
    "\u00c3|\u00e2\u20ac|\u00c2|\u00f0\u0178|\u011f\u0178|\u011e[^\\sA-Za-z]|"
    "\u00d1[\u0080-\u20ff]|\u00ce[\u0080-\u20ff]|\u00cf[\u0080-\u20ff]"
)
HTML_ENTITY = re.compile(r"&(?:[A-Za-z]+|#\d+|#x[0-9A-Fa-f]+);")
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")
NON_WORD = re.compile(r"[^\w]+")
UNDERSCORE = re.compile(r"_+")


# ------------------------------------------------------------------ titles


def repair_mojibake(text: str) -> tuple[str, bool]:
    """Undo one round of UTF-8 text decoded with a Windows code page.

    Re-encoding with the wrong code page and decoding as UTF-8 succeeds only
    for genuine mojibake: correct text such as "für" does not form valid
    UTF-8 bytes when re-encoded, so the attempt fails and the text stays
    unchanged. ASCII text is never touched.
    """
    if text.isascii():
        return text, False
    for encoding in ("cp1252", "cp1254", "latin-1"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired != text:
            return repaired, True
    return text, False


def clean_title(raw: Any) -> tuple[str | None, bool, bool]:
    """Return (clean title, had HTML entities, mojibake repaired).

    Steps: decode HTML entities (``&amp;`` becomes ``&``), repair mojibake,
    apply Unicode NFKC normalisation (full-width letters and similar variants
    become their standard form) and collapse repeated whitespace. Letter case
    and punctuation stay, because they carry meaning ("C++", "UI/UX").
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None, False, False
    text = str(raw)
    had_entities = bool(HTML_ENTITY.search(text))
    # Entities can be double-encoded ("&amp;amp;"), so decode until stable.
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text, repaired = repair_mojibake(text)
    text = unicodedata.normalize("NFKC", text)
    text = " ".join(text.split())
    return (text or None), had_entities, repaired


def title_key(clean: str | None) -> str:
    """Matching key for repeated titles: lower case, letters and digits only.

    "Logo Design!!" and "logo design" share the key ``logo design``. Emoji and
    punctuation drop out; letters of every alphabet stay.
    """
    if not clean:
        return ""
    key = NON_WORD.sub(" ", clean.casefold())
    key = UNDERSCORE.sub(" ", key)
    return " ".join(key.split())


@lru_cache(maxsize=None)
def _script_of(char: str) -> str | None:
    """The writing system of one letter, from its Unicode name."""
    if not unicodedata.category(char).startswith("L"):
        return None
    name = unicodedata.name(char, "")
    for prefix, script in (
        ("LATIN", "latin"),
        ("CYRILLIC", "cyrillic"),
        ("ARABIC", "arabic"),
        ("CJK", "cjk"),
        ("HIRAGANA", "cjk"),
        ("KATAKANA", "cjk"),
        ("HANGUL", "cjk"),
        ("DEVANAGARI", "devanagari"),
        ("GREEK", "greek"),
        ("HEBREW", "hebrew"),
        ("THAI", "thai"),
    ):
        if name.startswith(prefix):
            return script
    return "other"


def title_script(clean: str | None) -> str:
    """The alphabet a title is written in.

    ``latin`` when every letter is Latin; the other script's name when more
    than half of the letters belong to it; ``mixed`` when non-Latin letters
    are a minority; ``none`` when the title has no letters. This is an exact
    property of the characters, not a statistical language guess.
    """
    if not clean:
        return "none"
    counts: dict[str, int] = {}
    for char in clean:
        script = _script_of(char)
        if script:
            counts[script] = counts.get(script, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return "none"
    non_latin = {k: v for k, v in counts.items() if k != "latin"}
    if not non_latin:
        return "latin"
    top, top_count = max(sorted(non_latin.items()), key=lambda item: item[1])
    return top if top_count * 2 > total else "mixed"


def add_title_columns(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame["title"].map(clean_title)
    frame["title_clean"] = cleaned.map(lambda item: item[0]).astype("string")
    frame["title_had_html_entities"] = cleaned.map(lambda item: item[1]).astype(bool)
    frame["title_mojibake_repaired"] = cleaned.map(lambda item: item[2]).astype(bool)
    clean = frame["title_clean"].fillna("").astype(object)
    frame["title_mojibake_unrepaired"] = clean.str.contains(MOJIBAKE).astype(bool)
    frame["title_has_replacement_char"] = clean.str.contains("\ufffd", regex=False).astype(bool)
    frame["title_has_emoji"] = clean.str.contains(EMOJI).astype(bool)
    frame["title_key"] = clean.map(title_key).astype("string")
    frame["title_word_count"] = frame["title_key"].str.split().str.len().fillna(0).astype("int64")
    frame["title_char_count"] = clean.str.len().astype("int64")
    frame["title_script"] = frame["title_clean"].map(lambda t: title_script(None if pd.isna(t) else t)).astype("string")
    return frame


# -------------------------------------------------------------------- time


def add_time_columns(frame: pd.DataFrame, timestamps: pd.Series) -> pd.DataFrame:
    """UTC timestamp, calendar day, weekday, hour and ISO week (decision D-005)."""
    frame["posted_at"] = timestamps
    frame["posted_date"] = timestamps.dt.tz_localize(None).dt.normalize()
    frame["weekday"] = pd.Categorical(timestamps.dt.dayofweek.map(dict(enumerate(WEEKDAYS))), categories=WEEKDAYS)
    frame["hour"] = timestamps.dt.hour.astype("int64")
    iso = timestamps.dt.isocalendar()
    frame["iso_week"] = (iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)).astype("string")
    return frame


def day_quality(timestamps: pd.Series, rules: dict[str, Any]) -> pd.DataFrame:
    """Rate every UTC calendar day between the first and last posting.

    A day is ``incomplete`` when it has fewer postings than
    ``min_day_volume_share`` of the median day, or more than
    ``max_weak_hours_for_gap`` weak hours. A weak hour has fewer postings than
    ``weak_hour_share`` of that day's median hour (an empty hour is weak).
    A day with one or two weak hours is ``intraday_gap``; otherwise it is
    ``complete``. Calendar days without any posting count as incomplete.
    """
    valid = timestamps.dropna()
    day = valid.dt.tz_localize(None).dt.normalize()
    calendar = pd.date_range(day.min(), day.max(), freq="D")
    hours = pd.crosstab(day, valid.dt.hour).reindex(index=calendar, columns=range(24), fill_value=0)
    postings = hours.sum(axis=1)
    median_hour = hours.median(axis=1)
    weak = hours.lt(rules["weak_hour_share"] * median_hour.to_numpy()[:, None]).sum(axis=1)
    low_volume = postings < rules["min_day_volume_share"] * postings[postings > 0].median()
    status = np.where(
        low_volume | (weak > rules["max_weak_hours_for_gap"]),
        "incomplete",
        np.where(weak > 0, "intraday_gap", "complete"),
    )
    table = pd.DataFrame(
        {"date": calendar, "postings": postings.to_numpy(), "weak_hours": weak.to_numpy(), "status": status}
    )
    table["in_timeseries_window"] = _longest_usable_run(table["status"])
    return table


def _longest_usable_run(status: pd.Series) -> pd.Series:
    """True for the longest unbroken run of days that are not incomplete."""
    usable = (status != "incomplete").to_numpy()
    best_start, best_length, start = 0, 0, None
    for i, ok in enumerate(list(usable) + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start > best_length:
                best_start, best_length = start, i - start
            start = None
    window = np.zeros(len(usable), dtype=bool)
    window[best_start : best_start + best_length] = True
    return pd.Series(window, index=status.index)


# --------------------------------------------------------------------- pay


def add_pay_columns(frame: pd.DataFrame, rules: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, float]]:
    """Contract type, pay completeness, hourly midpoint and extreme-value flags.

    Missing pay values are never filled in. The midpoint exists only when both
    ends of an hourly range exist. Extreme values are flagged, never removed
    or clipped (decision D-015).
    """
    hourly = frame["is_hourly"]
    low, high, budget = frame["hourly_low"], frame["hourly_high"], frame["budget"]
    frame["contract_type"] = pd.Series(np.where(hourly, "hourly", "fixed"), index=frame.index).astype("string")
    pay_info = np.select(
        [hourly & low.notna() & high.notna(), hourly & low.notna(), hourly, budget.notna()],
        ["hourly_range", "hourly_low_only", "hourly_no_rate", "fixed_budget"],
        default="fixed_no_budget",
    )
    frame["pay_info"] = pd.Series(pay_info, index=frame.index).astype("string")
    frame["hourly_mid"] = np.where(frame["pay_info"] == "hourly_range", (low + high) / 2.0, np.nan)
    frame["contract_pay_mismatch"] = (hourly & budget.notna()) | (~hourly & (low.notna() | high.notna()))
    frame["rate_range_inverted"] = (low > high).fillna(False)

    quantile = rules["extreme_quantile"]
    top_rate = high.fillna(low)
    thresholds = {
        "extreme_hourly_rate_threshold": float(top_rate[hourly].quantile(quantile)),
        "extreme_budget_threshold": float(budget[~hourly].quantile(quantile)),
    }
    frame["extreme_hourly_rate_flag"] = hourly & (top_rate >= thresholds["extreme_hourly_rate_threshold"])
    frame["extreme_budget_flag"] = ~hourly & (budget >= thresholds["extreme_budget_threshold"])
    frame["extreme_hourly_rate_flag"] = frame["extreme_hourly_rate_flag"].fillna(False).astype(bool)
    frame["extreme_budget_flag"] = frame["extreme_budget_flag"].fillna(False).astype(bool)
    return frame, thresholds


def pay_signature(frame: pd.DataFrame) -> pd.Series:
    """Exact pay terms for repost matching; empty when the pay is not informative.

    Fixed price: the exact budget. Hourly: the exact low and high rate, only
    when both exist. Hourly jobs with one or no rate get no signature, so two
    jobs that both lack pay can never count as having "the same pay"
    (decision D-016). Values are compared exactly, never rounded.
    """
    def exact(values: pd.Series) -> pd.Series:
        return values.map(lambda v: "" if pd.isna(v) else repr(float(v)))

    hourly_sig = "hourly|" + exact(frame["hourly_low"]) + "|" + exact(frame["hourly_high"])
    fixed_sig = "fixed|" + exact(frame["budget"])
    signature = np.where(
        frame["pay_info"] == "hourly_range",
        hourly_sig,
        np.where(frame["pay_info"] == "fixed_budget", fixed_sig, ""),
    )
    return pd.Series(signature, index=frame.index).astype("string")


# ----------------------------------------------------------------- repeats


def earlier_match_within(frame: pd.DataFrame, keys: list[str], eligible: pd.Series, days: int) -> pd.Series:
    """True when an earlier posting with the same keys exists within ``days``.

    The first posting of each chain stays unflagged, so removing flagged rows
    in a sensitivity test keeps exactly one posting per chain.
    """
    subset = frame.loc[eligible, keys + ["posted_at"]].sort_values("posted_at", kind="mergesort")
    gap = subset.groupby(keys, sort=False, observed=True)["posted_at"].diff()
    flagged = gap.notna() & (gap <= pd.Timedelta(days=days))
    return flagged.reindex(frame.index, fill_value=False).astype(bool)


def add_repeat_columns(frame: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    """Repeated-title and possible-repost flags for each window (decision D-016).

    ``repeated_title_<N>d``: same title key and same known country, any pay.
    An upper bound and a repeated-demand signal, not a repost estimate.
    ``possible_repost_<N>d``: additionally the same contract type and the same
    exact, informative pay terms. Stronger evidence of a repost, not proof.
    A missing country never matches another missing country.
    """
    frame["pay_signature"] = pay_signature(frame)
    base = frame["valid_job_record"] & frame["usable_title"] & frame["country"].notna()
    with_pay = base & (frame["pay_signature"] != "")
    for days in windows:
        frame[f"repeated_title_{days}d"] = earlier_match_within(frame, ["title_key", "country"], base, days)
        frame[f"possible_repost_{days}d"] = earlier_match_within(
            frame, ["title_key", "country", "pay_signature"], with_pay, days
        )
    return frame


# -------------------------------------------------------------------- step


def build_master(raw: pd.DataFrame, timestamps: pd.Series, rules: dict[str, Any]) -> tuple[pd.DataFrame, dict]:
    """Build the master table from the typed raw frame. Pure function: no files."""
    frame = raw.copy()
    frame.insert(0, "row_id", np.arange(len(frame), dtype="int64"))
    frame = add_title_columns(frame)
    frame = add_time_columns(frame, timestamps)
    frame, thresholds = add_pay_columns(frame, rules)

    frame["country_known"] = frame["country"].notna()
    frame["valid_job_record"] = frame["title"].notna() & frame["link"].notna() & frame["posted_at"].notna()
    frame["usable_title"] = (frame["title_key"].fillna("").str.len() > 0).astype(bool)

    days = day_quality(timestamps, rules)
    lookup = days.set_index("date")
    frame["day_status"] = frame["posted_date"].map(lookup["status"]).astype("string")
    frame["in_timeseries_window"] = frame["posted_date"].map(lookup["in_timeseries_window"]).fillna(False).astype(bool)

    frame = add_repeat_columns(frame, list(rules["repeat_windows_days"]))

    valid = frame["valid_job_record"]
    frame["eligible_for_text_analysis"] = (valid & frame["usable_title"]).astype(bool)
    frame["eligible_for_hourly_rate_analysis"] = (valid & (frame["pay_info"] == "hourly_range")).astype(bool)
    frame["eligible_for_budget_analysis"] = (valid & (frame["pay_info"] == "fixed_budget")).astype(bool)
    frame["eligible_for_timeseries"] = (valid & frame["in_timeseries_window"]).astype(bool)
    frame = as_categories(frame, CATEGORY_COLUMNS)
    return frame, {"thresholds": thresholds, "day_quality": days}


def as_categories(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Store low-variety text columns as categories (decision D-019).

    A category column stores each distinct value once and gives every row a
    small number pointing to it. "hourly_range" repeated 98,775 times costs
    one string instead of 98,775, which keeps the master table small enough
    for any laptop. Categories are sorted, so the stored file is identical on
    every build.
    """
    for column in columns:
        values = frame[column].astype(object)
        categories = sorted(values.dropna().unique())
        frame[column] = pd.Categorical(values, categories=categories)
    return frame


def cleaning_log(frame: pd.DataFrame, days: pd.DataFrame, thresholds: dict[str, float], rules: dict) -> pd.DataFrame:
    """One row per cleaning rule: problem, evidence, decision and rows affected."""
    hourly = frame["is_hourly"]
    window = days[days["in_timeseries_window"]]
    primary = rules["primary_repeat_window_days"]
    rows = [
        (
            "C01",
            "Empty record",
            "Title, link and country are all empty in the same row.",
            "Keep the row; valid_job_record = False excludes it from every analysis.",
            int((~frame["valid_job_record"]).sum()),
        ),
        (
            "C02",
            "Budget is empty for hourly jobs; rates are empty for fixed-price jobs",
            f"{int((hourly & frame['budget'].isna()).sum()):,} of {int(hourly.sum()):,} hourly jobs lack a budget and "
            f"{int((~hourly & frame['hourly_low'].isna()).sum()):,} of {int((~hourly).sum()):,} fixed-price jobs "
            "lack rates; contract_pay_mismatch is "
            f"{int(frame['contract_pay_mismatch'].sum())}.",
            "Structural: the field does not apply to that contract type, so every valid row has one. "
            "Never filled in; hourly and fixed-price pay are analysed apart.",
            int(frame["valid_job_record"].sum()),
        ),
        (
            "C03",
            "Hourly jobs without a complete rate range",
            f"{int((frame['pay_info'] == 'hourly_low_only').sum()):,} have only a low rate and "
            f"{int((frame['pay_info'] == 'hourly_no_rate').sum()):,} have no rate.",
            "Genuinely missing. No midpoint and no imputation; excluded from hourly-rate analysis only.",
            int(frame["pay_info"].isin(["hourly_low_only", "hourly_no_rate"]).sum()),
        ),
        (
            "C04",
            "Missing country",
            f"{int((~frame['country_known'] & frame['valid_job_record']).sum()):,} valid jobs have no country.",
            "Kept as missing (never 'Unknown' matched to 'Unknown'); excluded only where country is needed.",
            int((~frame["country_known"] & frame["valid_job_record"]).sum()),
        ),
        (
            "C05",
            "HTML entities in titles",
            "Titles contain codes such as &amp; and &quot; instead of & and \".",
            "Decoded in title_clean; the raw title is kept.",
            int(frame["title_had_html_entities"].sum()),
        ),
        (
            "C06",
            "Mojibake in titles",
            "UTF-8 text decoded with a Windows code page, for example 'fÃ¼r' for 'für'.",
            "Repaired in title_clean only when re-encoding the text decodes cleanly as UTF-8; the raw title is kept.",
            int(frame["title_mojibake_repaired"].sum()),
        ),
        (
            "C07",
            "Unrecoverable characters",
            "Titles contain the Unicode replacement character, or damaged text that no single repair fixes; "
            "the original letters are lost at the source.",
            "Flagged (title_has_replacement_char, title_mojibake_unrepaired); the rest of the title stays usable.",
            int((frame["title_has_replacement_char"] | frame["title_mojibake_unrepaired"]).sum()),
        ),
        (
            "C08",
            "Extreme hourly rates",
            f"Highest rate at or above the {rules['extreme_quantile']:.1%} quantile "
            f"(${thresholds['extreme_hourly_rate_threshold']:,.0f}/hr), including placeholder-like values such as $999.",
            "Flagged (extreme_hourly_rate_flag); raw values kept; analyses report results with and without them.",
            int(frame["extreme_hourly_rate_flag"].sum()),
        ),
        (
            "C09",
            "Extreme fixed-price budgets",
            f"Budget at or above the {rules['extreme_quantile']:.1%} quantile "
            f"(${thresholds['extreme_budget_threshold']:,.0f}), including values such as $999,999 and $1,000,000.",
            "Flagged (extreme_budget_flag); raw values kept; analyses report results with and without them.",
            int(frame["extreme_budget_flag"].sum()),
        ),
        (
            "C10",
            "Incomplete collection days",
            f"Days with too few postings or more than {rules['max_weak_hours_for_gap']} weak hours.",
            f"Outside the time-series window ({window['date'].min():%Y-%m-%d} to {window['date'].max():%Y-%m-%d}); "
            "the jobs stay in every non-time-series analysis.",
            int((frame["valid_job_record"] & ~frame["in_timeseries_window"]).sum()),
        ),
        (
            "C11",
            "Days with an intraday gap",
            "One or two hours with almost no postings inside an otherwise normal day.",
            "Kept in the window and flagged (day_status = intraday_gap) for sensitivity checks.",
            int((frame["day_status"] == "intraday_gap").sum()),
        ),
        (
            "C12",
            "Repeated titles",
            f"Same title key and country as a posting in the previous {primary} days.",
            f"Flagged (repeated_title_{primary}d): repeated demand, not a repost estimate.",
            int(frame[f"repeated_title_{primary}d"].sum()),
        ),
        (
            "C13",
            "Possible reposts",
            f"Same title key, country, contract type and exact pay as a posting in the previous {primary} days.",
            f"Flagged (possible_repost_{primary}d); never deleted; used for sensitivity checks.",
            int(frame[f"possible_repost_{primary}d"].sum()),
        ),
    ]
    return pd.DataFrame(rows, columns=["rule_id", "problem", "evidence", "decision", "rows_affected"])


def repeat_sensitivity(frame: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    rows = []
    for days in windows:
        for kind in ("repeated_title", "possible_repost"):
            flag = frame[f"{kind}_{days}d"]
            rows.append(
                {
                    "flag": f"{kind}_{days}d",
                    "window_days": days,
                    "rows_flagged": int(flag.sum()),
                    "share_of_valid_rows_pct": round(100.0 * flag.sum() / frame["valid_job_record"].sum(), 2),
                    "share_with_short_title_pct": round(100.0 * (flag & (frame["title_word_count"] <= 3)).sum()
                                                        / max(int(flag.sum()), 1), 2),
                }
            )
    return pd.DataFrame(rows)


def eligibility_counts(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [c for c in frame.columns if c.startswith("eligible_for_")] + ["valid_job_record"]
    return pd.DataFrame(
        {
            "flag": columns,
            "rows": [int(frame[c].sum()) for c in columns],
            "share_of_all_rows_pct": [round(100.0 * frame[c].mean(), 2) for c in columns],
        }
    )


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    rules = settings.section("cleaning")
    frame, extra = build_master(context["raw"], context["raw_timestamps"], rules)
    days, thresholds = extra["day_quality"], extra["thresholds"]

    processed = settings.path("processed_dir")
    master_path = write_parquet(frame, processed / "jobs_clean.parquet")
    record.outputs.append(describe_output(master_path, settings.root, rows=len(frame)))
    tables = {
        "cleaning_log.csv": cleaning_log(frame, days, thresholds, rules),
        "day_quality.csv": days.assign(date=days["date"].dt.strftime("%Y-%m-%d")),
        "repeat_sensitivity.csv": repeat_sensitivity(frame, list(rules["repeat_windows_days"])),
        "eligibility_counts.csv": eligibility_counts(frame),
    }
    for name, table in tables.items():
        path = write_csv(table, processed / name)
        record.outputs.append(describe_output(path, settings.root, rows=len(table)))

    window = days[days["in_timeseries_window"]]
    record.metrics = {
        "clean_rows": int(len(frame)),
        "valid_job_records": int(frame["valid_job_record"].sum()),
        "timeseries_window_start": f"{window['date'].min():%Y-%m-%d}",
        "timeseries_window_end": f"{window['date'].max():%Y-%m-%d}",
        "timeseries_window_days": int(len(window)),
        **{k: round(v, 2) for k, v in thresholds.items()},
    }
    context["excluded_time_series_dates"] = days.loc[~days["in_timeseries_window"], "date"].dt.strftime("%Y-%m-%d").tolist()
    context["clean"] = frame
    return record
