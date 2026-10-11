"""Job-function rules and the categorize step (decisions D-026 to D-028)."""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:            # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

import pandas as pd
import pytest

from job_market.categorize import categorize_title, category_text, industry_tags, score_text
from job_market.steps import categorize as step
from job_market.steps.clean import title_key
from job_market.taxonomy import CATEGORY_IDS, OTHER

from conftest import REPO_ROOT

CONFIG = tomllib.loads((REPO_ROOT / "config" / "pipeline.toml").read_text(encoding="utf-8"))["categorize"]


def category(title: str) -> str | None:
    return categorize_title(title).category


# ------------------------------------------------------------------ matching text


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("C++ developer", "cpp developer"),
        ("C# and .NET expert", "csharp and dotnet expert"),
        ("Node.js / Next.js", "nodejs nextjs"),
        ("E-commerce store", "ecommerce store"),
        ("UI/UX designers", "ui ux designer"),
        ("Videos for TikTok", "video for tiktok"),
        ("iOS apps on AWS", "ios app on aws"),
        ("Sales reps", "sale rep"),
    ],
)
def test_category_text(title, expected):
    assert category_text(title) == expected


def test_category_text_handles_missing_values():
    assert category_text(None) == ""
    assert categorize_title(None).method == "no_match"


def test_patterns_are_normalized_like_titles():
    # "google ads" in a title and "google ad" in the rules must meet.
    assert category("Google Ads expert") == "digital_marketing"
    assert category("Sales representative") == "sales_lead_generation"


def test_repeated_pattern_counts_once():
    scores, _ = score_text(category_text("3d modeling"))
    assert scores["design_creative"] == 3


# ------------------------------------------------------------------ tie-breaks


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Flutter developer for web and mobile", "mobile_development"),       # T1
        ("AI chatbot developer", "ai_ml"),                                     # T2
        ("Write blog posts using ChatGPT", "writing_content"),                 # T3
        ("WordPress website design", "web_development"),                       # T4
        ("Figma UI/UX design for a web app", "design_creative"),               # T5
        ("Python scraper for a website data", "software_it"),                  # T6
        ("Data entry into Excel", "admin_virtual_assistance"),                 # T8
        ("Script for an animated explainer video", "writing_content"),         # T9
        ("Voiceover for a YouTube video", "audio_music"),                      # T10
        ("YouTube thumbnail design", "design_creative"),                       # T11
        ("Social media manager for Instagram", "digital_marketing"),           # T13
        ("Appointment setter for marketing agency", "sales_lead_generation"),  # T14
        ("Amazon product listing", "ecommerce_operations"),                    # T15
        ("Amazon PPC campaign", "digital_marketing"),                          # T16
        ("Customer support for online store", "customer_service"),             # T17
        ("Bookkeeper for small business", "accounting_finance"),               # T19
        ("AutoCAD floor plan design", "engineering_architecture"),             # T20
        ("Product photo retouching", "photography"),                           # T21
        ("Translate a book to Spanish", "translation_transcription"),          # T22
        ("Payroll processing", "accounting_finance"),                          # T34
        ("UGC video creator", "video_animation"),                              # T26
        ("Shopify Plus Developer", "web_development"),                         # T4
    ],
)
def test_tie_breaks(title, expected):
    assert category(title) == expected


# ------------------------------------------------------------------ two deliverables


def test_two_separate_tasks_go_to_other_with_both_kept():
    result = categorize_title("Logo and website")
    assert result.category == OTHER
    assert result.method == "two_tasks"
    assert set(result.secondary[:2]) == {"design_creative", "web_development"}


def test_minor_task_gives_priority_to_the_other():
    assert category("Build a website and make a small logo") == "web_development"


def test_one_job_in_two_technologies_is_not_two_tasks():
    assert category("Looking for iOS & mobile game developer") == "mobile_development"
    assert categorize_title("Python and React developer").method == "rule"


def test_same_function_twice_is_one_task():
    assert category("Data entry and web research") == "admin_virtual_assistance"


def test_no_rule_match_is_left_to_the_classifier():
    result = categorize_title("Canvas project")
    assert result.category is None
    assert result.method == "no_match"


def test_industry_tags_are_separate_from_the_category():
    text = category_text("Bookkeeper for a dental clinic")
    assert category("Bookkeeper for a dental clinic") == "accounting_finance"
    assert industry_tags(text) == ["healthcare"]


# ------------------------------------------------------------------ step helpers


def test_hide_terms_removes_longest_phrase_first():
    assert step.hide_terms("shopify store manager for fashion", "store manager; store") == "shopify for fashion"
    assert step.hide_terms("logo", "logo") == ""


def test_weak_labels_keep_only_strong_unopposed_rules():
    rules = step.rule_table(pd.Series(["Logo design for a bakery", "Logo", "Logo and website", "Canvas project"]), 2)
    labels = step.weak_labels(rules, min_score=5, max_per_category=10, seed=1)
    assert labels["title_clean"].tolist() == ["Logo design for a bakery"]
    assert labels["training_text"].iloc[0] == "for a bakery"


def test_decide_uses_the_threshold():
    rules = pd.DataFrame(
        {
            "category_text": ["logo", "abc", "xyz", "", "logo and website"],
            "rule_method": ["rule", "no_match", "no_match", "no_match", "two_tasks"],
            "rule_category": ["design_creative", None, None, None, OTHER],
            "classifier_category": ["design_creative", "writing_content", "legal", None, "web_development"],
            "classifier_probability": [0.9, 0.8, 0.2, 0.0, 0.9],
        }
    )
    out = step.decide(rules, threshold=0.5)
    assert out["category_method"].tolist() == ["rule", "tfidf_classifier", "below_threshold", "no_text", "two_tasks"]
    assert out["primary_category"].tolist() == ["design_creative", "writing_content", OTHER, OTHER, OTHER]


def _training_frame() -> pd.DataFrame:
    """Enough distinct titles in three categories to train a small classifier."""
    places = ["for bakery", "for gym", "for dentist", "for school", "for hotel", "for cafe", "for farm",
              "for shop", "for clinic", "for agency", "for startup", "for church", "for salon", "for garage",
              "for florist", "for brewery", "for spa", "for zoo", "for museum", "for library", "for theatre",
              "for hostel", "for pharmacy", "for kennel", "for marina"]
    titles = []
    for place in places:
        titles += [f"Logo design {place} brand", f"Bookkeeper accountant {place} ledger",
                   f"Video editor youtube video {place} reels"]
    titles += ["Bakery gym hotel", "Totally unknown words", None]
    return pd.DataFrame({"row_id": range(len(titles)), "title_clean": titles})


def test_categorize_jobs_end_to_end():
    frame = _training_frame()
    settings = dict(CONFIG, min_weak_labels_per_category=5, max_char_features=5000)
    jobs, model, report, proxy = step.categorize_jobs(frame, settings, seed=7)
    assert model is not None and report["classifier_trained"]
    assert list(jobs.columns) == list(step.OUTPUT_COLUMNS)
    assert len(jobs) == len(frame)                                # every job keeps one row
    assert jobs["row_id"].tolist() == frame["row_id"].tolist()
    assert set(jobs["primary_category"].dropna()) <= set(CATEGORY_IDS)
    assert jobs["primary_category"].notna().all()
    assert jobs.loc[0, "primary_category"] == "design_creative"
    assert jobs.loc[0, "category_method"] == "rule"
    assert jobs["category_method"].iloc[-1] == "no_text"
    unmatched = jobs.iloc[-3:-1]
    assert set(unmatched["category_method"]) <= {"tfidf_classifier", "below_threshold"}
    assert (jobs["taxonomy_version"] == "1.0").all()
    assert (jobs["categorizer_version"] == CONFIG["categorizer_version"]).all()
    assert report["categorizer_version"] == CONFIG["categorizer_version"]
    assert report["proxy_title_keys_shared_with_training"] == 0
    assert list(proxy["by_threshold"]["threshold"]) == list(step.PROXY_THRESHOLDS)


def test_categorize_jobs_without_enough_weak_labels():
    frame = pd.DataFrame({"row_id": [1, 2, 3], "title_clean": ["Logo designer", "Canvas project", None]})
    jobs, model, report, _ = step.categorize_jobs(frame, CONFIG, seed=7)
    assert model is None and report["classifier_trained"] is False
    assert jobs["category_method"].tolist() == ["rule", "below_threshold", "no_text"]
    assert jobs["primary_category"].tolist() == ["design_creative", OTHER, OTHER]


def test_category_summary_shares_add_up():
    jobs, _, _, _ = step.categorize_jobs(_training_frame(), dict(CONFIG, min_weak_labels_per_category=5), seed=7)
    summary = step.category_summary(jobs)
    assert summary["jobs"].sum() == len(jobs)
    assert summary["share_of_all_jobs"].sum() == pytest.approx(1.0, abs=1e-5)


# ------------------------------------------------------------------ dev-review rules (decision D-029)
# Each change has positive cases and "must not change" cases, so a fix for one
# title cannot quietly break a neighbouring kind of title.


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # T25: recruitment + a job role -> that role; recruitment work itself -> HR
        ("Recruitment Product Designer", "design_creative"),
        ("Recruiting Video Editors", "video_animation"),
        ("Recruitment WordPress Developer", "web_development"),
        ("Recruiting Python Developer", "software_it"),
        ("Recruitment Process Consultant", "hr_recruiting"),
        ("Recruitment Specialist", "hr_recruiting"),
        ("Recruitment Coordinator", "hr_recruiting"),
        ("Recruitment Strategy Consultant", "hr_recruiting"),
        ("Recruitment Agency Consultant", "hr_recruiting"),
        ("Recruitment Campaign Manager", "hr_recruiting"),
        ("Recruiter", "hr_recruiting"),
        ("Technical Recruiter", "hr_recruiting"),
        ("IT Recruiter", "hr_recruiting"),
        # Outside the 22 functions; technical testing stays software
        ("Paid Product Tester", OTHER),
        ("Mystery Shopper", OTHER),
        ("Mobile App Beta Tester", OTHER),
        ("Take our 5 minute survey", OTHER),
        ("QA Tester", "software_it"),
        ("Software Tester", "software_it"),
        # T28-T30: chatter
        ("Experienced OnlyFans Chatter", OTHER),
        ("Chatter for customer support", "customer_service"),
        ("Chatter to upsell PPV content", "sales_lead_generation"),
        # App with no platform -> software; platform or pure design decides otherwise
        ("Create a construction management app", "software_it"),
        ("Figma UI for construction app", "design_creative"),
        ("Android construction app", "mobile_development"),
        ("Build an AI app", "ai_ml"),
        ("Build a web app", "web_development"),
        # T5: art for a website is design; building the site is web
        ("Website Illustrator/Visual Artist", "design_creative"),
        ("Build a WordPress website with illustrations", "web_development"),
        # T7: dashboard as a data output -> data; as a coded product -> web/software
        ("Power BI Dashboard", "data_analytics"),
        ("Tableau dashboard", "data_analytics"),
        ("Excel dashboard", "data_analytics"),
        ("Analyse data and build dashboard", "data_analytics"),
        ("SaaS Dashboard Developer", "software_it"),
        ("Build a cold email SaaS - dashboard and backend", "web_development"),
        # T13/T16: PR and running Amazon ads -> marketing; building for ads -> software
        ("Amazon PPC Specialist", "digital_marketing"),
        ("Manage Amazon ads", "digital_marketing"),
        ("Amazon advertising campaign", "digital_marketing"),
        ("Perpetua Ads Amazon Account Manager", "digital_marketing"),
        ("Amazon Ads API Developer", "software_it"),
        ("Amazon product listing", "ecommerce_operations"),
        ("Professional PR Coach to Pitch Big Media", "digital_marketing"),
        ("Public relations specialist", "digital_marketing"),
        ("Business coach", "business_project_management"),
        # T24: regulatory filings -> legal; writing about them -> writing
        ("SEC Filing Assistance", "legal"),
        ("13D Sec Filing", "legal"),
        ("Article About SEC Filings", "writing_content"),
        ("Write a contract", "legal"),
        # Missing tool words
        ("Shoe design in Openscad Pro", "engineering_architecture"),
        ("Need Developer with Apify scraping", "software_it"),
        ("Trim videos for Instagram", "video_animation"),
    ],
)
def test_dev_review_rules(title, expected):
    assert category(title) == expected


def test_other_from_rules_is_never_a_weak_label():
    rules = step.rule_table(pd.Series(["Mystery shopper visit for a bakery in a small town"]), 2)
    assert rules["rule_category"].iloc[0] == OTHER
    assert step.weak_labels(rules, min_score=0, max_per_category=10, seed=1).empty


def test_proxy_split_never_shares_a_title_key():
    labels = pd.DataFrame({"title_clean": ["Logo design", "logo design!!", "LOGO DESIGN", "Video editor", "video editor.",
                                           "Bookkeeper", "Web developer", "SEO expert", "Data entry", "Translator"]})
    for seed in range(10):
        train, test = step.proxy_split(labels, 0.3, seed)
        train_keys = set(train["title_clean"].map(title_key))
        assert not train_keys & set(test["title_clean"].map(title_key))


def test_fallback_guard_sends_blocked_categories_to_other():
    rules = pd.DataFrame(
        {
            "category_text": ["abc", "def", "ghi"],
            "rule_method": ["no_match"] * 3,
            "rule_category": [None] * 3,
            "classifier_category": ["web_development", "hr_recruiting", "hr_recruiting"],
            "classifier_probability": [0.9, 0.9, 0.5],
        }
    )
    out = step.decide(rules, threshold=0.7, allowed=["web_development"])
    assert out["category_method"].tolist() == ["tfidf_classifier", "fallback_blocked", "below_threshold"]
    assert out["primary_category"].tolist() == ["web_development", OTHER, OTHER]


def test_frozen_fallback_list_is_valid():
    allowed = CONFIG["fallback_categories"]
    assert len(allowed) == len(set(allowed)) == 14
    assert set(allowed) <= set(CATEGORY_IDS) - {OTHER}
    assert CONFIG["categorizer_version"] == "1.0"
    assert CONFIG["classifier_threshold"] == 0.7
