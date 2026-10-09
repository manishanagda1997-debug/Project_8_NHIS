"""Short-window trend helpers for Task 2 (emerging categories) and Task 7
(online-hiring signals). Decision D-032.

The trustworthy window has only 37 days, so every trend here means "change
within these five weeks", never a long-term trend. Shares (a category's share
of all jobs per day) are used instead of counts, because counts move with the
weekday and with collection gaps.

The trend model is ordinary least squares::

    share_t = a + b * t + weekday effects + error

``b`` is the daily change in share. Neighbouring days are correlated, so its
standard error uses the Newey-West (HAC) estimator with a lag fixed in the
configuration before any result was seen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from .pay import benjamini_hochberg

# World Bank regions (with Malta placed in Europe & Central Asia). Missing
# countries stay missing and are never assigned a region.
REGIONS = {
    "North America": ["United States", "Canada", "Bermuda", "Greenland", "United States Minor Outlying Islands"],
    "Latin America & Caribbean": [
        "Mexico", "Brazil", "Colombia", "Argentina", "Peru", "Chile", "Costa Rica", "Dominican Republic", "Jamaica",
        "Venezuela", "Panama", "Ecuador", "Uruguay", "Trinidad and Tobago", "Honduras", "Cayman Islands", "Paraguay",
        "Guatemala", "El Salvador", "Saint Lucia", "Bolivia", "Bahamas", "Nicaragua", "Barbados",
        "British Virgin Islands", "Aruba", "Belize", "United States Virgin Islands", "Haiti",
        "Sint Maarten (Dutch part)", "Curacao", "Grenada", "Antigua and Barbuda", "Guyana",
        "Saint Vincent and the Grenadines", "Guadeloupe", "Netherlands Antilles", "Anguilla", "Saint Kitts and Nevis",
        "Turks and Caicos Islands", "Bonaire, Sint Eustatius and Saba", "Dominica", "Martinique", "Suriname",
        "French Guiana", "Puerto Rico", "Cuba",
    ],
    "Europe & Central Asia": [
        "United Kingdom", "Germany", "Netherlands", "France", "Spain", "Ukraine", "Italy", "Switzerland", "Poland",
        "Sweden", "Ireland", "Turkey", "Belgium", "Denmark", "Romania", "Malta", "Portugal", "Norway", "Austria",
        "Cyprus", "Estonia", "Czech Republic", "Greece", "Bulgaria", "Lithuania", "Hungary", "Serbia", "Georgia",
        "Finland", "Latvia", "Armenia", "Slovenia", "Croatia", "Slovakia", "Macedonia", "Kazakhstan", "Moldova",
        "Albania", "Bosnia and Herzegovina", "Uzbekistan", "Azerbaijan", "Luxembourg", "Montenegro", "Iceland",
        "San Marino", "Isle of Man", "Gibraltar", "Kyrgyzstan", "Jersey", "Andorra", "Monaco", "Russia",
        "Turkmenistan", "Liechtenstein", "Tajikistan", "Guernsey", "Belarus", "Holy See", "Aland Islands",
        "Faroe Islands", "Kosovo",
    ],
    "Middle East & North Africa": [
        "United Arab Emirates", "Israel", "Saudi Arabia", "Egypt", "Morocco", "Lebanon", "Qatar", "Kuwait", "Jordan",
        "Bahrain", "Oman", "Algeria", "Tunisia", "Palestinian Territories", "Yemen", "Djibouti", "Iraq", "Iran",
        "Libya", "Syria",
    ],
    "South Asia": ["India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal", "Maldives", "Bhutan", "Afghanistan"],
    "East Asia & Pacific": [
        "Australia", "New Zealand", "Singapore", "Philippines", "China", "Hong Kong", "Malaysia", "Japan", "Thailand",
        "Indonesia", "South Korea", "Vietnam", "Taiwan", "Cambodia", "Mongolia", "French Polynesia", "American Samoa",
        "Brunei Darussalam", "Myanmar", "Papua New Guinea", "Guam", "Macao", "Palau", "New Caledonia",
        "Northern Mariana Islands", "Micronesia, Federated States of", "Laos", "Fiji", "Kiribati", "Samoa",
        "Cocos (Keeling) Islands", "Timor-Leste", "Vanuatu", "Niue", "Tuvalu", "Cook Islands", "Solomon Islands",
        "Tonga", "Marshall Islands", "Nauru",
    ],
    "Sub-Saharan Africa": [
        "South Africa", "Nigeria", "Kenya", "Ethiopia", "Uganda", "Tanzania", "Mauritius", "Zambia", "Ghana",
        "Cameroon", "Rwanda", "Somalia", "Zimbabwe", "Seychelles", "Cote d'Ivoire", "Cote d&#039;Ivoire", "Reunion",
        "Mozambique", "Benin", "Madagascar", "Namibia", "Senegal", "Angola", "Botswana", "Mauritania", "Sierra Leone",
        "Togo", "Congo, the Democratic Republic of the", "Malawi", "Gabon", "Mali", "Gambia", "Guinea", "Swaziland",
        "Congo", "Eritrea", "Comoros", "Saint Helena", "Central African Republic", "Chad", "Burkina Faso", "Niger",
        "Burundi", "Liberia", "Lesotho", "South Sudan", "Sudan", "Cape Verde", "Equatorial Guinea", "Guinea-Bissau",
        "Mayotte", "Sao Tome and Principe",
    ],
}
COUNTRY_REGION = {country: region for region, countries in REGIONS.items() for country in countries}
UNMAPPED_REGION = "(unmapped)"

# Explicit wording signals in job titles (decisions D-032 and D-041). These
# detect explicit title wording only, never the share of jobs that are actually
# remote or on-site. Matching is on whole words or phrases of ``title_key``;
# the hybrid forms also use the cleaned title, which keeps brackets and dashes.
#
# Work-arrangement rules, version 1.0 (D-041): written from the development
# labels only and frozen with the tag ``arrangement-rules-1.0``. The rules used
# to draw the audit samples are kept, frozen, in ``arrangement.py`` and are
# never used for reported results.
ARRANGEMENT_RULES_VERSION = "1.0"

_REMOTE_TECH = (r"access|desktop|servers?|controls?|sensing|networking|network|monitoring|asics|database|backup|"
                r"repository|machines?|devices?|teams?")
_HOME = r"work from home|wfh|home based|from home|work from anywhere|from anywhere|anywhere in the world"
_HYBRID_TECH = (r"app|apps|cloud|mobile|solar|power|ad|email|server|migration|configuration|casual|blockchain|"
                r"ecommerce|ionic|website|aws")
_ATTEND = r"in person|in office|at our office|office visit|must attend|attend the office"
# "for an in-person event" describes what the work is for, not where it is done.
_IN_PERSON_EVENT = r"for (?:(?:a|an|the|our|my|local)\s)*in person (?:events?|hackathon|conference|meetings?)"
_ZONE_CODES = r"est|edt|pst|pdt|cst|cdt|mst|mdt|bst|cet|cest|aest|aedt"
_TZ_WORDS = r"time zone|timezone|time zones|us hours|uk hours|eu hours|business hours"
_TZ_PHRASES = (r"night shift|day shift|(?:pacific|eastern|central|mountain) time|us time|uk time|australian time|"
               r"est time|pst time")
_DEADLINE = r"by|before|until|due|deadline|delivery"
_TIME_MARK = (r"\S*\d\S*|am|pm|noon|midnight|tomorrow|tonight|today|eod|"
              r"monday|tuesday|wednesday|thursday|friday|saturday|sunday")
_AVAILABILITY = r"available|availability|shift|hours|meeting|call|chat|time zone|timezone|work|working"
_TECHNICAL = (r"outlook|imap|ost|migration|migrate|convert|converter|conversion|import|export|file|files|mailbox|"
              r"exchange|duplicate|duplicates|certified|certification|exam|scrum|technologist")
_WORK_TIME = r"time|timezone|zone|zones|hours|hrs|shift|available|availability|work|working|during|between|am|pm|\S*\d\S*"

# Reported series: (output name, column). User-facing names say "wording".
ARRANGEMENT_SIGNALS = {
    "remote / home wording": "remote_or_home",
    "on-site / in-person wording": "on_site_required",
    "time-zone requirement wording": "time_zone_required",
}
ENGAGEMENT_PATTERNS = {
    "full time": r"full time|fulltime",
    "part time": r"part time|parttime",
    "long term / ongoing": r"long term|longterm|ongoing",
}
SIGNALS = (*ARRANGEMENT_SIGNALS, *ENGAGEMENT_PATTERNS)
ENGAGEMENT_SIGNALS = tuple(ENGAGEMENT_PATTERNS)


def _words(title_keys: pd.Series) -> pd.Series:
    return " " + title_keys.fillna("").astype(str) + " "


def _has(text: pd.Series, pattern: str) -> pd.Series:
    return text.str.contains(pattern, regex=True)


def hybrid_arrangement(title_keys: pd.Series, titles: pd.Series) -> pd.Series:
    """"Hybrid" written as a working arrangement (rules 1.0)."""
    k = _words(title_keys)
    t = titles.fillna("").astype(str)
    return (_has(k, r"\shybrid (?:role|position|work|job|schedule|model)\s") | _has(k, r"\shybrid\s$")
            | _has(t, r"(?i)\bhybrid[\s-]+(?:role|position|work|job|schedule|model|opportunity)\b")
            | _has(t, r"(?i)\(\s*hybrid\s*\)")
            | (_has(t, r"(?i)\(\s*hybrid\s*[-–:]\s*[a-z]") & ~_has(t, rf"(?i)\(\s*hybrid\s*[-–:]\s*(?:{_HYBRID_TECH})\b"))
            | _has(t, r"(?i)\bhybrid\s*\(\s*\d")
            | _has(t, r"(?i)\bhybrid\s+[-–]\s"))


def arrangement_flags(title_keys: pd.Series, titles: pd.Series) -> pd.DataFrame:
    """The three work-arrangement wording labels under rules 1.0 (D-041)."""
    k = _words(title_keys)
    hybrid = hybrid_arrangement(title_keys, titles)
    # "remote" counts unless every occurrence describes technology or a team.
    remote_word = _has(k.str.replace(rf"\sremote (?:{_REMOTE_TECH})(?=\s)", " ", regex=True), r"\s(?:remote|remotely)\s")
    remote = remote_word | _has(k, rf"\s(?:{_HOME})\s") | hybrid
    attend = _has(k, rf"\s(?:{_ATTEND})\s") & ~_has(k, rf"\s{_IN_PERSON_EVENT}\s")
    onsite_word = _has(k, r"\s(?:on site|onsite)\s") & ~_has(k, r"\sseo\s")
    onsite = attend | onsite_word | hybrid
    zone_word = _has(k, rf"\s(?:{_TZ_WORDS}|{_ZONE_CODES}|{_TZ_PHRASES})\s")
    gmt_utc = _has(k, r"\s(?:gmt|utc)\s") & (_has(k, r"\s(?:gmt|utc) \d") | _has(k, r"\s(?:time|timezone|zone|hours)\s"))
    any_zone = rf"(?:{_TZ_WORDS}|{_TZ_PHRASES}|{_ZONE_CODES}|gmt|utc)"
    deadline = _has(k, rf"\s(?:{_DEADLINE})\s(?:\S+\s){{0,4}}(?:{_TIME_MARK})\s(?:\S+\s){{0,2}}{any_zone}\s")
    availability = _has(k, rf"\s(?:{_AVAILABILITY})\s")
    code = _has(k, rf"\s(?:{_ZONE_CODES}|gmt|utc)\s")
    technical = (code & _has(k, rf"\s(?:{_TECHNICAL})\s") & ~_has(k, rf"\s(?:{_WORK_TIME})\s")
                 & ~_has(k, rf"\s(?:{_TZ_WORDS}|{_TZ_PHRASES})\s"))
    time_zone = (zone_word | gmt_utc) & ~(deadline & ~availability) & ~technical
    return pd.DataFrame({"remote_or_home": remote, "on_site_required": onsite, "time_zone_required": time_zone,
                         "hybrid_arrangement": hybrid}, index=title_keys.index)


def region_of(country: pd.Series) -> pd.Series:
    """World Bank region of each client country; missing stays missing."""
    text = country.astype("object")
    region = text.map(COUNTRY_REGION).fillna(UNMAPPED_REGION)
    return region.where(text.notna(), None)


def signal_flags(title_keys: pd.Series, titles: pd.Series) -> pd.DataFrame:
    """One boolean column per reported signal: arrangement rules 1.0 plus engagement words."""
    arrangement = arrangement_flags(title_keys, titles)
    text = _words(title_keys)
    columns = {name: arrangement[column] for name, column in ARRANGEMENT_SIGNALS.items()}
    columns.update({name: text.str.contains(rf"\s(?:{pattern})\s", regex=True)
                    for name, pattern in ENGAGEMENT_PATTERNS.items()})
    return pd.DataFrame(columns, index=title_keys.index)


# ------------------------------------------------------------------ trend model


def newey_west_cov(design: np.ndarray, residuals: np.ndarray, lag: int) -> np.ndarray:
    """Newey-West (Bartlett kernel) covariance of OLS coefficients."""
    n = design.shape[0]
    scores = design * residuals[:, None]
    meat = scores.T @ scores
    for k in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - k / (lag + 1.0)
        gamma = scores[k:].T @ scores[:-k]
        meat += weight * (gamma + gamma.T)
    bread = np.linalg.pinv(design.T @ design)
    return bread @ meat @ bread


def trend_fit(values: np.ndarray, dates: pd.Series, lag: int) -> dict[str, float]:
    """Weekday-adjusted linear trend of a daily series.

    Returns the change across the whole window (last day minus first day,
    from the fitted line), its 95% interval, the relative change against the
    fitted first-day level, and a two-sided p-value.
    """
    dates = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    t = (dates - dates.min()).dt.days.to_numpy(dtype=float)
    weekdays = pd.get_dummies(dates.dt.dayofweek, prefix="d", drop_first=True, dtype=float).to_numpy()
    design = np.column_stack([np.ones_like(t), t, weekdays])
    y = np.asarray(values, dtype=float)
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ coef
    cov = newey_west_cov(design, residuals, lag)
    slope, se = float(coef[1]), float(np.sqrt(max(cov[1, 1], 0.0)))
    span = float(t.max() - t.min())
    # Fitted level at the start, averaged over weekdays as they occur in the window.
    start = float(np.mean(design @ coef - slope * t))
    change, half = slope * span, 1.96 * se * span
    z = slope / se if se > 0 else np.nan
    return {
        "days": int(len(y)),
        "start_level": start,
        "end_level": start + change,
        "change": change,
        "change_low": change - half,
        "change_high": change + half,
        "relative_change_pct": 100.0 * change / start if start else np.nan,
        "relative_low_pct": 100.0 * (change - half) / start if start else np.nan,
        "relative_high_pct": 100.0 * (change + half) / start if start else np.nan,
        "p": float(2 * norm.sf(abs(z))) if np.isfinite(z) else np.nan,
    }


def complete_weeks(dates: pd.Series) -> list[str]:
    """ISO weeks (Monday-Sunday) whose seven days are all present."""
    days = pd.to_datetime(pd.Series(dates).drop_duplicates())
    iso = days.dt.isocalendar()
    week = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    counts = week.value_counts()
    return sorted(counts[counts == 7].index)


def daily_shares(frame: pd.DataFrame, group: str, date: str = "posted_date") -> pd.DataFrame:
    """Jobs and share of jobs per day for every value of ``group`` (zero days kept)."""
    counts = frame.groupby([date, group], observed=True).size().unstack(fill_value=0)
    shares = counts.div(counts.sum(axis=1), axis=0)
    long = counts.stack().rename("jobs").to_frame().join(shares.stack().rename("share"))
    return long.reset_index().rename(columns={date: "date"})


def trend_table(shares: pd.DataFrame, group: str, lag: int) -> pd.DataFrame:
    """Trend of the daily share of each group, with FDR-adjusted p-values.

    Changes are reported in percentage points (``change_pp``) and as a
    relative change, because +13% of a 1% share is only +0.13 points.
    """
    rows = []
    for name, part in shares.groupby(group, observed=True):
        part = part.sort_values("date")
        fit = trend_fit(part["share"].to_numpy(), part["date"], lag)
        rows.append({
            group: name, "jobs": int(part["jobs"].sum()), "mean_share_pct": 100 * part["share"].mean(),
            "start_share_pct": 100 * fit["start_level"], "end_share_pct": 100 * fit["end_level"],
            "change_pp": 100 * fit["change"], "change_low_pp": 100 * fit["change_low"],
            "change_high_pp": 100 * fit["change_high"], "relative_change_pct": fit["relative_change_pct"],
            "relative_low_pct": fit["relative_low_pct"], "relative_high_pct": fit["relative_high_pct"], "p": fit["p"],
        })
    table = pd.DataFrame(rows)
    if not table.empty:
        table["p_fdr"] = benjamini_hochberg(table["p"].to_numpy())
    return table


def week_comparison(frame: pd.DataFrame, group: str, weeks: list[str]) -> pd.DataFrame:
    """Share in the first two complete weeks versus the last two complete weeks."""
    if len(weeks) < 4:
        return pd.DataFrame(columns=[group, "first_weeks_share_pct", "last_weeks_share_pct",
                                     "week_change_pp", "week_relative_pct"])
    first, last = set(weeks[:2]), set(weeks[-2:])

    def shares(part: pd.DataFrame) -> pd.Series:
        return 100 * part[group].value_counts(normalize=True)

    a = shares(frame[frame["iso_week"].isin(first)])
    b = shares(frame[frame["iso_week"].isin(last)])
    table = pd.DataFrame({"first_weeks_share_pct": a, "last_weeks_share_pct": b}).fillna(0.0)
    table["week_change_pp"] = table["last_weeks_share_pct"] - table["first_weeks_share_pct"]
    table["week_relative_pct"] = 100 * table["week_change_pp"] / table["first_weeks_share_pct"].replace(0, np.nan)
    return table.rename_axis(group).reset_index()


def concentration(country: pd.Series) -> tuple[float, float]:
    """Herfindahl-Hirschman index of client countries (missing excluded) and
    the effective number of countries, 1 / HHI."""
    shares = country.dropna().value_counts(normalize=True)
    hhi = float((shares ** 2).sum()) if len(shares) else np.nan
    return hhi, (1.0 / hhi if hhi else np.nan)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (np.nan, np.nan)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))
