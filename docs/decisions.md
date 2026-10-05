# Decision register

Every decision that shapes a result has an entry here: what the project does,
why, and where the evidence lives. Entries use plain English so any reader can
check the reasoning.

## Foundation

### D-001 One pipeline produces every generated file

- **What:** `python -m job_market rebuild` reads the raw CSV and writes every
  processed table. Notebooks, reports, the dashboard and the database read
  these tables; they never compute their own private versions.
- **Why:** When each notebook computes its own numbers, two files can show
  two different answers to the same question. One pipeline gives one answer.
- **Evidence:** `src/job_market/pipeline.py`, `data/processed/run_manifest.json`.

### D-002 A run manifest records each build

- **What:** Each build writes `run_manifest.json` with four fingerprints
  (raw data, configuration, this project's own `src/job_market` source code,
  and the pinned environment file `environment.yml`), the installed package versions, row counts, and the size
  and SHA-256 hash of every output file. Each build has a `run_id`: a UTC
  timestamp plus a short hash of the four fingerprints. A change in any of the
  four marks the build stale. The build, every notebook and the lineage
  check also confirm that the `job_market` package Python imports is this
  project's `src/job_market`; if a copied or moved project runs another
  installed copy, they stop with the instruction `pip install -e . --no-deps`.
- **Why:** A reader can prove that a number in the report comes from a
  specific build of specific data with specific code, instead of trusting it.
- **Evidence:** `src/job_market/manifest.py`, `src/job_market/fingerprint.py`.

### D-003 Generated folders start empty on every build, and only they do

- **What:** `data/interim` and `data/processed` are emptied before each build.
  The lineage check fails if any file in them is not listed in the manifest.
  Before anything is deleted, a layout check requires every configured path
  to lie inside the project root, requires the raw CSV to sit in a
  sub-folder, and refuses any configuration where a generated folder equals,
  contains or sits inside a protected path: the configured raw CSV and its
  folder, the configured notebooks and reports folders, and the standard config,
  source, tests, docs and app folders. The two generated folders may not
  overlap, and the manifest must live inside the processed folder.
- **Why:** An old output file that survives a rebuild looks like current
  evidence but is not. Starting empty makes that impossible. The layout check
  makes sure a typing mistake in the configuration can never delete the
  source data.
- **Evidence:** `validate_layout` in `config.py`, `reset_generated_dirs` in
  `pipeline.py`; seventeen unsafe-path tests plus
  `test_unsafe_configuration_deletes_nothing`.

### D-004 Only empty cells count as missing when the raw file loads

- **What:** The loader turns off the pandas default that treats the text
  "NA", "None" or "null" as missing.
- **Why:** "NA" is a real country code (Namibia) and could be a real title.
  The default silently erases such values. In this dataset the result is the
  same either way, and the test `test_text_na_is_a_value_not_a_missing_cell`
  keeps it that way if the data changes.
- **Evidence:** `read_raw` in `steps/ingest.py`.

### D-005 All daily grouping uses UTC days

- **What:** Every timestamp carries a UTC offset, and all "per day" counts
  use the UTC calendar day.
- **Why:** Upwork is global; no single local time zone is more correct. UTC
  is the source's own zone, so no conversion error is possible.
- **Evidence:** `parse_timestamps` and `daily_coverage` in `steps/ingest.py`.

### D-006 Analytical outputs are deterministic

- **What:** Analytical outputs are byte-identical for the same raw data,
  code, configuration and pinned analysis environment. The run manifest is
  deliberately unique to each build, because it records the `run_id` and the
  start and finish times. Every CSV and JSON file uses UTF-8, LF line endings
  and a stable column and key order, and the hashes of configuration, code
  and `environment.yml` ignore line endings.
  In `.gitattributes`, the general `* text=auto` rule comes first and the
  `binary` rules for raw and generated data come last, because Git lets a
  later rule override an earlier one.
- **Why:** The same inputs must give the same hashes on Windows and Linux,
  and a Git checkout must never rewrite the bytes of a hashed file. Two full
  builds of the 244,828-row source produce identical analytical file hashes.
- **Evidence:** `src/job_market/io.py`, `.gitattributes`, tests
  `test_rebuild_is_byte_identical` and
  `test_git_keeps_hashed_files_byte_identical` (runs `git check-attr`).

### D-007 Saved notebooks are clean, top-to-bottom runs of the current build

- **What:** `python -m job_market run-notebooks` executes each notebook in a
  new kernel and saves the executed copy, with the build `run_id` in the
  notebook metadata. The first code cell calls `start()`, which checks the
  four build fingerprints and the hash of every output file, then prints
  `RUN_ID: ...`. `project.read_csv()` checks a file's hash again at read
  time. The notebook check fails if any code cell is not executed, if
  execution counts are not 1, 2, 3 ... in order, if any cell shows an error,
  if the first code cell does not call `start()` or print the `run_id`, or if
  the notebook's outputs come from another build.
- **Why:** A notebook with unexecuted cells, missing outputs or outputs from
  an older build is weak evidence. A fresh-kernel run guarantees that every
  saved output comes from the saved code, in order, with no hidden state.
- **Evidence:** `src/job_market/notebook.py`, `src/job_market/qa/notebooks.py`,
  `notebook_status` in `src/job_market/qa/lineage.py`; tests in
  `tests/test_notebooks.py` and `tests/test_integrity_and_safety.py`,
  including a real notebook-execution test.

### D-008 A pinned analysis environment produces the official results

- **What:** `environment.yml` pins the Python minor version (3.11) and the
  exact version of every package that can change a result. The manifest
  records the exact Python and package versions of each build. Two
  environments are compared with the pins: the one that builds the outputs
  (from the manifest) and the one running now. By default a difference is a
  **warning**: the project still runs with compatible versions, and the
  manifest records that the build does not match the pins. In **strict
  mode** (`JOB_MARKET_STRICT=1`), which continuous integration and the final
  verification use, any difference is an error. Python matches on its minor
  version (any 3.11.x); every package must match its pin exactly.
  `pyproject.toml` keeps compatible ranges for general installation.
- **Why:** A different pandas or scikit-learn version can change numbers
  slightly, so the official results come from one pinned environment. But a
  reader who installs with plain `pip` should be able to run the project and
  see a clear warning, not a wall of errors.
- **Evidence:** `environment.yml`, `src/job_market/environment.py`,
  `check_build_environment` and `check_current_environment` in
  `src/job_market/qa/project_checks.py`, `.github/workflows/ci.yml`.

### D-009 Timestamps parse with one explicit format

- **What:** `published_date` parses as ISO 8601 into UTC. Unparseable values
  are counted; a file where no value parses stops the build with a clear
  message.
- **Why:** A declared format applies one rule to every row. Letting pandas
  guess can parse different rows by different rules. All 244,828 source
  values follow the same 25-character ISO 8601 pattern and all parse.
- **Evidence:** `parse_timestamps` and `require_timestamps` in
  `steps/ingest.py`; two timestamp tests.

### D-010 Quality gates report failures; they never crash

- **What:** Each lineage check runs inside its own error handler. A check that
  cannot complete, for example because the raw CSV is missing, becomes an
  ERROR finding with a plain message, and the remaining checks still run.
- **Why:** A gate that stops with a Python traceback hides every other
  problem and reads as a broken tool. A clear list of findings shows exactly
  what to fix.
- **Evidence:** `run_lineage_check` in `src/job_market/qa/lineage.py`; test
  `test_missing_raw_file_is_a_finding_not_a_crash`.

### D-011 The raw dataset is not committed to Git

- **What:** `data/raw/` holds only a `.gitkeep` file in the repository. The
  README explains where to place the source CSV and gives its SHA-256 hash.
  The small processed tables and the run manifest are committed, so the
  saved notebooks and the notebook check work from a fresh clone.
- **Why:** The CSV is 50.6 MB of third-party data. Keeping it out of Git
  keeps the repository light, and the hash check proves that anyone who
  rebuilds uses exactly the same file.
- **Evidence:** `.gitignore`, `README.md`, `source_sha256` in the manifest.

## Data audit and cleaning (Notebook 01)

### D-012 Every raw row stays; problems become flags

- **What:** The master table `jobs_clean.parquet` has exactly one row per raw
  row (244,828). The eight raw columns stay unchanged; cleaned values live in
  new columns. Nothing is filled in and nothing is deleted. Eligibility flags
  (`valid_job_record`, `eligible_for_text_analysis`,
  `eligible_for_hourly_rate_analysis`, `eligible_for_budget_analysis`,
  `eligible_for_timeseries`) say which analysis may use each row.
- **Why:** Deleting rows hides decisions and cannot be undone by a reader.
  Flags keep the full audit trail, and each later analysis states exactly which
  population it uses. A kept row is preserved, not automatically valid for
  every analysis.
- **Evidence:** `build_master` in `steps/clean.py`; Notebook 01 section 5;
  tests `test_every_raw_row_is_kept_and_raw_columns_are_unchanged`,
  `test_empty_record_is_kept_but_excluded_from_every_analysis`.

### D-013 Day quality decides the time-series window

- **What:** Every UTC calendar day is compared with normal days of the
  **same weekday**. *Daily completeness* = the day's postings / the median
  postings of the same weekday; below 90% the day is `incomplete`. *Hourly
  completeness* = postings in one UTC hour / the median for the same weekday
  and hour; below 30% the hour is weak. A day that is not incomplete but has
  weak hours is `intraday_gap`; otherwise it is `complete`. The medians come
  from *reference days* (at least half the postings of a full collection
  day, where a full day is the 90th percentile of daily postings), which only
  keeps the sparse early weeks out of the medians. The time-series window is
  the longest unbroken run of days that are not incomplete: **16 February to
  23 March 2024 (37 days)**. Days with an intraday gap (17, 18 and 20
  February) stay in the window and are flagged.
- **Why:** Counting jobs per day on a day when the collector was partly
  offline would show a false drop in demand. Comparing a day with *itself*
  (its own median hour) lets a badly damaged day hide its damage: 15 February
  has 26% of a normal Thursday's postings and 18 weak hours against normal
  Thursdays, but only 4 against its own median hour. Comparing with the same
  weekday also handles the natural weekend dip. In this data, normal days
  reach 0.93-1.10 of their weekday median and damaged days 0.86 or less, so
  the 90% cut-off sits in a clear gap.
- **Change:** Replaces the first rule (weak hour against the day's own
  median, incomplete below 25% of the median day or with more than two weak
  hours). The window and the flagged days are identical under both rules; the
  new rule gives the stronger reason.
- **Limit:** About six days per weekday form each median, so the medians are
  robust to one damaged day per weekday, not to many. Jobs posted outside the
  window are still real jobs; they stay in every analysis that does not count
  jobs per day.
- **Evidence:** `day_quality` in `steps/clean.py`; `day_quality.csv` (with
  `completeness_ratio`); Notebook 01 sections 2.4-2.5; day-quality tests in
  `tests/test_clean.py`.

### D-014 Cleaned titles keep meaning; raw titles stay

- **What:** `title_clean` decodes HTML entities (`&amp;` becomes `&`),
  repairs mojibake (UTF-8 text decoded with a Windows code page, such as
  `fÃ¼r` for `für`), applies Unicode NFKC normalisation and collapses repeated
  spaces. Case and punctuation stay ("C++", "UI/UX"). `title_key` is the
  lower-case version with letters and digits, plus a `+` or `#` attached to
  the end of a word: "C++ Developer" -> `c++ developer`, "C# Developer" ->
  `c# developer`, "Audio + Video" -> `audio video`, "Node.js" -> `node js`.
  It matches repeated titles and feeds the title-word analysis. Titles that
  stay damaged are flagged.
- **Why:** The same job title must look the same to every later analysis,
  but the raw title is the evidence and is never overwritten. A key of
  letters and digits only would merge "C++", "C#" and "C" developers into one
  repeat key and one word; one key with attached `+`/`#` fixes repeats and
  word counts together, instead of keeping two nearly identical keys.
- **Change:** The first key dropped every symbol. It merged 37 keys (159
  jobs); the fix changes 4 repeated-title flags and 2 possible-repost flags
  (3-day window). It only splits keys, never merges them, so the existing
  label samples stay valid (no title key can newly appear in both).
- **Evidence:** `clean_title`, `repair_mojibake`, `title_key`; title tests in
  `tests/test_clean.py` and `tests/test_text.py`.

### D-015 Extreme pay values are flagged, never removed or clipped

- **What:** Hourly jobs whose highest rate is at or above the 99.9th
  percentile ($500/hour in this data) and fixed-price jobs whose budget is at
  or above the 99.9th percentile ($100,000) are flagged. Raw values stay.
- **Why:** Pay data has a long right tail of real, well-paid jobs, so a rule
  such as IQR would wrongly mark many of them as errors. Some values look like
  placeholders ($999/hour, $999,999), but the data cannot prove which ones.
  Each analysis reports its result with and without flagged values.
- **Evidence:** `add_pay_columns`; Notebook 01 section 2.8.

### D-016 Repeated titles and possible reposts are two different flags

- **What:** `repeated_title_<N>d`: the same `title_key` and the same known
  country as an earlier posting within N days. `possible_repost_<N>d`: in
  addition, the same contract type and the same exact, informative pay terms
  (a fixed budget, or both ends of an hourly range). N is 1, 3 and 7 days; 3 is
  the primary window. The first posting of a chain is never flagged. A missing
  country never matches another missing country, and missing pay never counts
  as the same pay. Values are compared exactly, never rounded.
- **Why:** Title and country alone flag popular roles: "social media manager"
  in the United States alone produces hundreds of matches, which is many
  clients wanting the same role, not one client reposting. Treating those as
  duplicates would shrink demand for exactly the most popular roles. Matching
  pay is much stronger evidence of the same client. The gaps between repeats
  show no natural break, so 3 days is a reasoned choice, and the 1-day and
  7-day versions test how much it matters.
- **Evidence:** `add_repeat_columns`, `pay_signature`; `repeat_sensitivity.csv`;
  Notebook 01 section 2.6; seven repeat tests.

### D-017 Missing pay and missing country are never filled in

- **What:** Budget is empty for every hourly job and hourly rates are empty
  for every fixed-price job: the field does not apply (structural
  missingness). Hourly jobs with one or no rate and jobs without a country are
  genuinely missing values. None of them is imputed; `hourly_mid` exists only
  when both ends of the range exist.
- **Why:** An invented salary is not data. Pay analyses use the rows that
  have the value and state their size.
- **Evidence:** `add_pay_columns`; Notebook 01 sections 2.1 and 2.2.

### D-018 Title script instead of a language guess

- **What:** `title_script` records which alphabet a title uses (Latin,
  Cyrillic, Arabic, CJK and others, `mixed` or `none`). No statistical language
  detection is applied.
- **Why:** The `langdetect` library was tested on this data during design. On
  a random sample of 2,000 ASCII-only titles with at least three words, it
  labelled 7.4% of its high-confidence (probability at least 0.90) answers as
  non-English, and in a sample of 15 of those labels 14 were wrong, for
  example "PHP LARAVEL MYSQL Expert" as Catalan and "Social media Manager" as
  Italian. Short job titles full of product names defeat it, and the full run
  takes about 20 minutes. The script of a character is an exact property, not
  a guess.
- **Limit:** Spanish, German or French titles written in the Latin alphabet
  are not separated from English ones.
- **Evidence:** `title_script`; title-script tests.

### D-019 The master table is stored as Parquet

- **What:** `jobs_clean.parquet` stores the master table; small audit tables
  stay CSV. `pyarrow` is pinned in `environment.yml`. Text columns with only
  a few distinct values (`title_script`, `iso_week`, `contract_type`,
  `pay_info`, `day_status`) are stored as categories, which keeps the table
  small in memory.
- **Why:** Parquet keeps column types (timestamps with their time zone,
  true/false flags, categories), so every notebook reads exactly the types the
  pipeline writes, and it loads far faster than a 245,000-row CSV.
- **Evidence:** `write_parquet` in `io.py`; test
  `test_parquet_round_trip_preserves_types`.

## Exploratory market analysis (Notebook 02)

### D-020 Countries need at least 30 pay-eligible jobs for pay display tables

- **What:** Notebook 02 shows country pay summaries only for countries with
  at least 30 eligible hourly jobs or at least 30 eligible fixed-budget jobs.
- **Why:** Very small groups can look extreme by chance and make an EDA chart
  hard to read. The rule only controls display; the rows stay in the data.
- **Evidence:** Notebook 02 section 3 and its claims check.

### D-021 Pay summaries use the median and IQR first

- **What:** Notebook 02 uses the median as the main pay level and the 25th to
  75th percentile range (IQR) as the main spread. It also reports mean,
  quantiles, skewness and kurtosis for context.
- **Why:** Hourly rates and fixed budgets have long high-value tails. The
  median and IQR are less affected by rare extreme postings than the mean or
  a min-max range.
- **Evidence:** Notebook 02 section 2 and section 3.

### D-022 Sensitivity checks match the metric being studied

- **What:** Pay checks compare results with and without flagged extreme pay;
  volume and title-demand checks compare with and without possible reposts;
  time-pattern checks compare with and without intraday-gap days.
- **Why:** Each risk affects a different kind of result. One blanket filter
  would either miss the real risk or remove rows for no reason.
- **Evidence:** Notebook 02 section 6.

### D-023 Missing-pay bias is checked within hourly jobs

- **What:** Hourly jobs with a complete rate range are compared with hourly
  jobs that have one rate or no rate. The comparison uses country mix, title
  word count, weekday and over-represented title words, with effect sizes
  rather than p-values alone.
- **Why:** Task 1 can only use jobs that state pay. With a large dataset,
  p-values can be tiny even when a difference is not practically important.
- **Limit:** Fixed-price jobs in the cleaned table already have a budget, so
  this missingness check is not needed for fixed budgets.
- **Evidence:** Notebook 02 section 4.

### D-024 Title-word exploration uses a small explicit stop-word list

- **What:** Reusable text helpers in `src/job_market/text.py` lower-case
  `title_key`, split on spaces and remove a short, explicit list of filler
  words (a, an, and, are, at, be, by, for, from, i, in, is, looking, my, need,
  needed, of, on, or, our, the, this, to, we, with, you, your). "on" and "an"
  were added after the first count showed "on" among the ten most common
  words. Words that can carry meaning in a title stay out of the list on
  purpose: "it" (IT support) and "us" (US-based).
  Phrases of two or more words are built from the words in their original
  order, and any phrase that contains a stop word is dropped.
- **Why:** The first title-word pass should be simple, transparent and easy to
  test before Notebook 03 builds categories. Removing stop words before
  pairing words would invent phrases nobody wrote ("web developer needed for
  wordpress" would give "developer wordpress").
- **Limit:** `title_key` already strips punctuation, so technical tokens such
  as `c++` and `.net` can lose information. Notebook 03 must decide how to
  handle that.
- **Evidence:** Notebook 02 section 5; `tests/test_text.py`.

### D-025 Daily comparisons use averages per day, never totals

- **What:** Any comparison between weekdays (or other groups of days) divides
  the number of postings by the number of days in that group.
- **Why:** The 37-day time-series window contains six Fridays and six
  Saturdays but only five of every other weekday. Raw totals make Friday look
  like the busiest day; per day, Friday is below Monday to Thursday.
- **Evidence:** Notebook 02 section 2.3 (raw total vs average per day) and
  its claims check.

## Job categories (Notebook 03)

### D-026 Job categories describe the work; one primary category per job

- **What:** Taxonomy 1.0 has 22 job-function categories plus Other / Unclear
  (`src/job_market/taxonomy.py`; definitions, examples and 39 tie-break rules
  in `docs/labelling_guide.md`). Each job gets exactly one primary category;
  other categories it also matches are stored as secondary matches. The
  client's industry (real estate, healthcare, crypto and others) is a separate,
  optional, multi-label `industry_tag` that never changes demand shares. A
  title naming two separate pieces of work with no stated priority ("logo and
  website") is Other / Unclear with both stored as secondary matches.
- **Why:** Tasks 2 and 3 count demand per category; one job counted twice
  would push shares above 100%. Industry and job function are different
  questions: a real-estate virtual assistant does virtual-assistant work.
  Picking the "more technical" deliverable for two-task titles would inflate
  technical categories, so those titles are not given an invented winner.
- **Limit:** About 1-2% of titles are two-task titles (estimated from a
  draft rule set); if more than 5% of the development titles end up in Other
  through this rule, the rule is reviewed before freezing.
- **Evidence:** `docs/labelling_guide.md`; the unmatched-title audit in
  Notebook 03.

### D-027 Three label sets with separate jobs, and a strict blind test

- **What:** Rule-assigned, high-confidence labels (weak labels) train the
  fallback classifier. A 150-title development set, labelled by hand, tunes
  the rules, weights and confidence threshold and compares rules-only with
  the hybrid. A 350-title blind test set, labelled by hand from the title
  alone with no predictions visible, is scored once after everything is
  frozen. The blind set is drawn first as a simple random sample of jobs; the
  development set comes from the remaining jobs (110 random, 20 short titles,
  20 titles joining two tasks). No title key appears in both sets. The sample
  settings live in `config/pipeline.toml` under `[labels]`, and
  `python -m job_market make-label-sheets` refuses to overwrite existing
  sheets.
- **Why:** Data that tunes a system cannot also grade it: the development
  labels stay out of training, and the blind labels stay out of every
  decision. Drawing the blind set first keeps it a true random sample of the
  market, so its accuracy describes the whole dataset.
- **Rule:** If the taxonomy, rules, model, threshold or tie-break logic
  changes after blind labelling starts, the blind test is no longer blind and
  a fresh sample is needed.
- **Limit:** One person labels both sets (single annotator); rare categories
  may have too few blind titles for a stable per-category score, in which case
  a separate diagnostic sample is reported apart from the overall accuracy.
- **Evidence:** `src/job_market/labels.py`, `tests/test_labels.py`.

### D-028 Hybrid categorization: rules first, a classifier only for the rest

- **What:** `src/job_market/categorize.py` builds a matching text from
  `title_clean` (technical tokens protected, punctuation removed, simple
  plurals reduced; rule patterns pass through the same normalization), scores
  every category with weighted patterns (3 specific phrase, 2 clear word, 1
  generic word; a category needs 2 points), and applies the tie-break table of
  the labelling guide. A title is split at "and", "&", "+" and " / "; two
  parts with strong evidence (3+ points) for different functions are two
  separate tasks (Other / Unclear), unless one part is marked minor ("a small
  logo") or the two categories are one piece of work in two technologies
  (iOS + mobile game, Python + React). Titles with no rule match go to a
  TF-IDF (words 1-2, characters 3-5) + logistic regression classifier trained
  only on weak labels (rule score 5+, no competing category, distinct titles,
  at most 4,000 per category). Below the probability threshold the job is
  Other / Unclear. The categorizer has its own version
  (`categorizer_version`, "0.1-dev" until the freeze, then "1.0"), separate
  from the taxonomy version: the taxonomy (category list and definitions) is
  frozen at 1.0 before labelling, while the rules, model and threshold are
  still tuned on the development labels. Output: `job_categories.parquet`, one row per job, joined
  on `row_id`; `jobs_clean.parquet` is not changed.
- **Why:** Rules are transparent: every category can be traced to the words
  that matched. The classifier is only needed where rules are silent. The
  rule words are hidden from the classifier's training text, because the
  classifier is only used on titles that contain no rule word; trained on the
  full text it learns the rule words and is unsure on exactly the titles it
  exists for (in a trial, 33% of unmatched titles reached probability 0.5
  with the words hidden, about 10% without).
- **Limit:** The classifier's agreement with the rules on held-out weak
  labels (about 0.49 with the rule words hidden) is not accuracy. Accuracy
  comes only from the human labels: the threshold and any rule changes are
  chosen on the development set and frozen before the blind test (D-027).
  Settings in `config/pipeline.toml` under `[categorize]`.
- **Evidence:** `src/job_market/steps/categorize.py`,
  `tests/test_categorize.py`, Notebook 03.

### D-029 Categorizer 1.0: rules tuned on the development labels, guarded fallback, frozen

- **What:** The 150 development labels tune the categorizer once, then it is
  frozen as `categorizer_version = "1.0"`.
  - *Rule changes*, each following an existing guide rule and tested with
    positive and "must not change" examples (`tests/test_categorize.py`): a
    bare "chatter" is Other (T30), "chatter" with support or selling words is
    Customer Service or Sales (T28/T29); "recruitment/recruiting" followed by
    a job role gives that role, while recruitment work itself (process,
    agency, consultant, specialist, coordinator, strategy, campaign, manager;
    "recruiter") stays HR (T25); consumer-style testing and survey or
    research participation is Other, technical testing stays Software (guide
    section 5); building an app with no stated platform is Software (T1/T4
    decide mobile and web); art or illustration for a website is Design
    unless the title says it builds the site (T5); a dashboard is Data when
    it is a data or reporting output and Web/Software when it is a coded
    product (T7); PR and running ads are Marketing, building for ads (API,
    script, integration) is Software (T13/T16); regulatory filings are
    Legal, writing an article about them is Writing (T24); missing tool words
    (OpenSCAD, Apify, trim videos). Rule-assigned Other is never a weak label.
  - *Effect on the development set:* agreement rises from 76% (114 of 150,
    first rule set) to 83% (125 of 150) after tuning; the classifier added
    nothing measurable on these titles at either stage.
  - *Not changed:* 15 remaining disagreements that are judgement calls
    ("Facebook verification", "AI influencer", "Practice Manager | CPA");
    special rules for single titles would turn the development set into an
    answer sheet. The two-task rule stays: it gives Other for 8 of 150
    development titles (5.3%), but the development sample deliberately
    contains 20 joined titles; across all jobs it affects about 2.5%. On the
    development set it matches the human label for only 2 of 5 titles it
    fires on, which Notebook 03 reports as a known weakness.
  - *Fallback classifier:* used only when no rule matches; a guess counts
    only at probability >= 0.70 and only for a fixed list of 14 categories.
    Every other guess is Other / Unclear (`below_threshold`,
    `fallback_blocked`).
- **Why:** The threshold and the guard come from a *masked proxy test*:
  weak-labelled titles split by `title_key` (GroupShuffleSplit, 0 keys shared
  with training), with the rule words hidden, so the test resembles the
  titles the classifier really meets. At 0.70 the unrestricted fallback
  agrees with the held-out high-confidence rule labels on 83.8% of 1,835
  predictions (84.6% on titles whose masked text has no identical twin in
  training). By category, AI & ML (55%), Photography (52%), Engineering
  (66%) and Legal (67%) fall below 70% with at least 30 predictions; HR,
  Education, Business and Audio have fewer than 30 predictions, which is
  insufficient evidence for a reliable fallback. One general rule (at least
  30 proxy predictions and at least 70% agreement) selects the 14 allowed
  categories; with the guard, agreement is 88.0% (89.1% without twins) on
  1,603 predictions. The list is frozen in `config/pipeline.toml`, not
  recalculated during a build; each build records whether its own proxy
  test still selects the same list (`fallback_list_matches_proxy_rule`).
- **Limit:** Proxy labels are rule labels, not human ground truth, so these
  numbers design the policy and are not accuracy; proxy agreement and the
  development agreement come from different populations and are not
  compared. Development agreement after tuning (83% overall, 91% on titles
  labelled without hesitation) is optimistic because the rules were tuned on
  those titles. The final accuracy comes only from the 350 blind labels,
  scored once.
- **Rule:** Nothing in the rules, weights, model, threshold or guard changes
  after blind labelling starts (D-027).
- **Evidence:** `src/job_market/categorize.py`,
  `src/job_market/steps/categorize.py`, `classifier_report.json`,
  `classifier_proxy_by_threshold.csv`, `classifier_proxy_by_category.csv`,
  `tests/test_categorize.py`, Notebook 03.

### D-030 Blind result and how it is reported

- **What:** After `categorizer-1.0` and the blind labels were committed and
  tagged (`blind-labels-final`), the frozen system was scored once on the 350
  blind titles: **241 of 350 = 68.9%** agreement (95% Wilson interval
  63.8%-73.5%); 76.2% on titles labelled without hesitation, 33.3% on titles
  marked unsure; rules only 68.6%. When the system names a category (not
  Other), it agrees 77.2% of the time; it predicts Other for 13.4% of blind
  titles where the annotator chose Other for 6.3%.
- **Why:** The blind set is a simple random sample drawn before any tuning,
  so it estimates agreement on the whole market. The development result
  (83%) is optimistic because the rules were tuned on those titles.
- **Label review:** The annotator considered a post-scoring review; under the
  agreed rule (only data-entry slips or labelling-guide violations, made in
  copies, original result stays primary) no change qualified, so the original
  labels are the only labels.
- **Consequence:** Software & IT, AI & ML, Engineering and Admin have low
  blind recall (31-46%), mostly because their titles fall into Other; their
  demand shares are therefore likely undercounted, and later notebooks show
  the Other share next to every category result.
- **Rule:** No rule, model, threshold or guard changes because of this
  result; improvements are listed as future work.
- **Evidence:** `steps/evaluate.py`, `label_evaluation_*.csv`, Notebook 03
  section 8.

### D-031 Pay analysis: three-layer keyword associations and client-country rates

- **What:** Hourly pay is the midpoint of a complete hourly range; fixed-price
  budgets are analysed separately. Models use log pay and report
  `(exp(b) - 1) x 100` percent. `country` is the **client's** country.
  Keywords are words and two-word phrases of `title_key` (binary presence per
  job), tested when they have at least 300 rated jobs **and** 100 distinct
  title keys; a word is dropped when 80% or more of its jobs also contain a
  kept phrase with it. Each keyword is measured in three layers (raw, same
  client country, same country + assigned category) by a within-group
  regression with standard errors clustered by `title_key`, and p-values
  adjusted with Benjamini-Hochberg across all tested keywords. Countries need
  30 rated jobs (D-020); each gets a median with a cluster-bootstrap interval
  and a category-adjusted index relative to the job-weighted average client.
  Explanatory power is measured on a 20% test split grouped by `title_key`
  (median baseline, country + category, plus title words). Sensitivity:
  without extreme rates, without possible reposts, low end and high end of
  the range.
- **Why:** Raw keyword differences mix the keyword with who posts it and what
  kind of job it is. The category is derived from the title, so the
  country + category layer partly removes the title signal itself; it is
  shown next to the other two layers, never as the single correct answer.
  Clustering by title stops repeated postings from counting as independent
  evidence; the FDR adjustment controls false discoveries among 322 tests.
- **Limit:** Associations, not causes; pay is what clients offer, not what
  freelancers earn. Title words explain about a quarter of the variation in
  log hourly pay. Category controls inherit the Other-heavy weakness of D-030.
  Rates cluster at round numbers, so median intervals can collapse to one
  value, and low-end rankings of mid-sized countries are unstable.
- **Evidence:** `src/job_market/pay.py`, `steps/pay.py`, `tests/test_pay.py`,
  `pay_*.csv`, Notebook 04.

### D-032 Short-window trends and the Task 7 framing

- **What:** Trends use only the 37-day time-series window. For each of the 22
  job functions, the daily share of jobs is regressed on time with weekday
  effects; the standard error uses Newey-West with a 7-day lag fixed before
  any result was seen; p-values are FDR-adjusted. Changes are reported in
  percentage points and as relative changes. Other / Unclear is monitored
  separately, never tested as an emerging category. Checks: without
  possible reposts, without the intraday-gap days, and the first two versus
  the last two complete Monday-Sunday weeks (2024-W08/W09 versus W10/W11).
  Keyword trends use the Notebook 04 support rules plus presence in at least
  3 ISO weeks; rare new terms are only counted per week.
- **Task 7:** Upwork is primarily an online freelance marketplace and the
  data has no structured remote/on-site field, so the share of remote jobs
  cannot be estimated. Task 7 measures client geography (World Bank regions,
  HHI and the effective number of countries = 1/HHI, weekly distinct
  countries as a volume-sensitive description), engagement structure (hourly
  share; full-time, part-time, long-term mentions) and explicit
  work-arrangement mentions in titles (whole words only; "local" alone is
  excluded because of "local seo"). Forecasts for the signals with enough data
  are made in Notebook 06; rare signals get none.
- **Why:** Shares cancel the weekly rhythm and collection gaps. The window is
  short and serially correlated, so effect sizes with intervals matter more
  than p-values.
- **Limit:** Five weeks cannot show long-term trends and may contain seasonal
  effects. An exploratory check (split date 26 February, chosen after seeing
  the daily charts) shows that part of the full-window change is an early
  step; gradual change continues for Writing (down) and AI & ML, Sales and
  E-commerce (up). The collection method is undocumented, so a collection
  change cannot be ruled out.
- **Evidence:** `src/job_market/trends.py`, `steps/trends.py`,
  `tests/test_trends.py`, `trend_*.csv`, `remote_*.csv`, Notebook 05.

### D-033 Short-horizon forecasts (Tasks 3, 7 and 8)

- **What:** Because the reliable history contains only 37 days, the forecast
  is limited to a short 14-day horizon; longer-range forecasts are not
  supported by enough history. Days 1-7 are the primary forecast; days 8-14
  are an extended outlook with greater uncertainty. The first 30 days are the
  development period; the final seven days are a reserved final forecast
  evaluation window: they are not used for model fitting or model selection
  (they are not blind in the sense of the taxonomy labels, because Notebook 05
  already described all 37 days).
- **Models:** Four models fixed before any evaluation: seasonal naive (same
  weekday last week), weekday mean (last 14 days), straight trend with
  weekday effects, and damped trend with phi = 0.9 set in configuration.
  One winner per series family, chosen by mean seasonal MASE in a
  rolling-origin backtest (origins after 14 to 23 development days, horizon
  7): the demand family (total jobs and the 23 category shares) and the
  Task 7 signal family (hourly share, North American client share, HHI).
  No category gets its own model. A 14-day check with the few possible
  origins is secondary only.
- **Metrics:** MAE, seasonal MASE (scale = in-sample mean absolute change
  versus seven days earlier) and Relative MAE (model MAE / seasonal-naive
  MAE on the same days; below 1 beats the baseline). No MAPE.
- **Coherence:** Category jobs = total forecast x shares, with shares clipped
  to [0, 1] and rescaled to sum to 1, so the 22 categories plus Other add up
  to the total every day; counts cannot be negative. Signals are clipped to
  their valid range.
- **Ranges:** 80% empirical forecast ranges from backtest errors at each
  horizon; beyond the tested 7 days they widen by sqrt(h / 7), a stated
  assumption. Task 3 ranks categories by expected jobs per day and flags
  neighbours whose ranges overlap as similarly high-demand.
- **Task 8:** The recent observed share (average of the final 7 days) is
  compared with the forecast next-7-day and 14-day averages from the better
  trend model. A direction is reported only if that model beat the seasonal
  baseline in development (Relative MAE < 1); otherwise "no reliable
  direction". Changes below 0.1 pp (0.001 for HHI) are "stable".
- **Limit:** Seven final days are one small check, days 8-14 are less directly
  validated, and five weeks cannot capture seasonality beyond the week. For
  total jobs the seasonal baseline beat the other models in the final window.
- **Evidence:** `src/job_market/forecast.py`, `steps/forecast.py`,
  `tests/test_forecast.py`, `forecast_*.csv`, Notebook 06.

### D-034 Job recommendations and the pooled blind relevance evaluation (Task 5)

- **What:** A freelancer types skills; the engine returns the 10 best-matching
  jobs from the final 14 observed days (the default; the app also offers 7,
  30 days or all). Three methods are compared, simplest first: a keyword
  count (profile words found in the title as whole words), word TF-IDF
  (single words and two-word phrases without stop words) and a hybrid of word
  and character TF-IDF (3-5 character pieces), averaged 50/50. The
  vectorizers are fitted on every title in the 37-day window. Sentence
  embeddings are left for future work: they add a large model dependency and
  are harder to explain, and the brief asks for scikit-learn.
- **Same treatment for every method:** the same pool; only the newest posting
  of each possible-repost chain (same title key, country and exact pay terms
  within 3 days; D-016) is kept; at most one result per title key unless too
  few different matches exist; only positive scores; ties go to the newer job.
- **Filters:** strict. Minimum hourly rate: a job passes when the maximum of
  the client's stated hourly range is at least the freelancer's minimum
  ($15-$35 passes a $30 minimum; $15-$25 does not); a job stating one rate
  uses it; jobs without a rate fail; fixed-price budgets are never compared
  with hourly rates. A minimum budget applies to fixed-price jobs only.
- **Evaluation:** 12 profiles written without looking at job titles and
  approved on 4 October 2026 before any result existed (they cover 12
  representative kinds of work, not every category). Each method's top 5
  per profile, without filters, is pooled by (profile, title key), shuffled
  within each profile and judged blind on the title only: 2 relevant, 1
  partly relevant, 0 not relevant. This is a pooled blind relevance
  evaluation of title-level relevance, not of whole-job suitability.
  `python -m job_market make-relevance-sheet` writes the sheet once and
  refuses to overwrite it. No file links a method to a job until the sheet
  is complete.
- **Winner rule (frozen before labelling):** highest mean graded nDCG@5
  (gain 2^label - 1; the ideal ranking comes from the judged pool of that
  profile; missing positions count as 0). Differences below 0.02 are
  effectively tied; then strict Precision@5 (only label 2 counts); then the
  simpler method. Results are reported per profile too.
- **Label-free checks:** for every profile, method and filter scenario
  (none; hourly minimum $30 and $50; fixed minimum $500): result counts
  (coverage and zero-result rate), distinct titles, filter violations and
  results outside the pool.
- **Related market keywords to explore:** terms from the Notebook 04 pay table
  and the Notebook 05 trend table that appear in at least 3 of the profile's
  50 best-matching titles, are not already in the profile, and have a
  positive same-country-and-category pay association or a rising share (FDR
  q < 0.05). Worded as associations, never as advice to learn a skill.
  **Post-output refinement (fixed once, not tuned again):** the first version
  returned generic words ("expert", "help", "build"), so a keyword must also
  add a word that is neither generic (a fixed list of request, action,
  seniority and job-role words) nor already in the profile (same first 5
  letters counts as present), and be at least twice as common in the matched
  jobs as in the whole pool (lift >= 2). No result is a valid answer. Only two
  profiles receive a keyword ("react", "design"). This feature is descriptive
  and separate from the blinded method evaluation.
- **Similar jobs:** a job's title is the query; the job itself is excluded and
  the same pool, repost and diversity rules apply. Checked with tests and
  examples, without a separate labelled evaluation.
- **Result:** the hybrid is selected by the frozen rule: mean nDCG@5 0.985,
  strict Precision@5 0.967; its nDCG lead over word TF-IDF (0.971) is inside
  the 0.02 tie margin, so Precision@5 decides; the keyword count (0.953) is
  outside it. 115 of the 122 judged titles were labelled relevant, so the
  scores are near the ceiling and no statistical superiority is claimed.
- **Record:** the tag `recommender-1.0` marks the frozen design and blank
  sheet; its CI run fails only because the notebooks had not been re-run
  after the rebuild (fixed in the next commit, outputs only). The tag is left
  in place so the freeze time stays on record. `relevance-labels-final`
  marks the completed labels, committed before scoring.
- **Evidence:** `src/job_market/recommend.py`, `steps/recommend.py`,
  `labels.py`, `tests/test_recommend.py`, `recommend_*.csv`,
  `data/labels/relevance_labels.xlsx`, Notebook 07.

### D-035 Web app and API (Task 5)

- **What:** One Flask app, started with `python -m job_market serve`: the
  recommendation page at `/` and a JSON API (`/api/health`,
  `/api/recommend`, `/api/similar/<row_id>`). The Task 6 dashboard will be a
  second page of the same app, reading the pipeline tables only.
- **Method:** the public page and API always use the evaluated winner, the
  hybrid word + character TF-IDF (`"method": "hybrid_word_character_tfidf"`
  in every response). There is no method switch: the methods were already
  compared, and an unknown parameter such as `method` is rejected.
- **Validation:** `skills` required (at most 300 characters); `days` in 7,
  14, 30 or all; `contract` in all, hourly or fixed; `min_hourly` only with
  `contract=hourly` and `min_budget` only with `contract=fixed`, both
  positive. A filter that does not fit the job type is a 400 error, never
  silently ignored. An unknown job ID is a 404.
- **Responses:** build ID, recommender version, method, the filters applied
  in plain words, candidate pool size, returned count, the results (title,
  link, pay exactly as stated: "$15-$35/hr", "$30/hr", "Fixed: $500" or
  "Rate not stated"), related market keywords or the no-keyword message, and
  short notes on the limits. No file paths.
- **Similar jobs:** the job itself and its possible reposts are excluded; the
  same pool, repost and diversity rules apply; 5 results.
- **Integrity:** at startup the app checks that the code and settings match
  the recorded build and verifies the SHA-256 of every file it reads. It
  does not need the raw CSV, so the same check works in Docker. The app
  lives in its own package (`src/job_market_web`), a presentation layer that
  calls `job_market.recommend`; editing the page does not change the analysis
  code fingerprint.
- **Tests:** `tests/test_web.py`: health, page, results and metadata, API
  results identical to the Python recommender, deterministic order, both
  filters, repost and diversity handling, every invalid request, 404s, and
  the pay text.
- **Limit:** Flask's built-in server is for local use; the Docker image will
  use a production server (decided at that stage).

### D-036 Market dashboard and monthly monitoring (Task 6)

- **What:** A second page of the Flask app, `/dashboard`, with a navigation
  bar shared with the recommendation page. It reads verified pipeline tables
  only; no grouping, testing, trend fitting or forecasting happens in Flask.
- **Monitor step:** a new pipeline step writes `monthly_market_summary.csv`,
  `monthly_category_share.csv`, `monthly_country_share.csv`,
  `weekly_market_summary.csv` and `weekly_category_share.csv` for the
  reliable time-series window only (16 February - 23 March 2024); the
  scattered earlier days are never mixed in.
- **Comparable measures:** months can be partial (February 14 days, March 23),
  so they are compared per day and as shares, never as totals. Volume is shown
  as jobs per day and as weekday-standardized jobs per day (the average of the
  seven weekday means; 1-23 March has four Fridays and Saturdays but three of
  every other weekday); the headline change uses the standardized value.
  Client geography uses the effective number of countries (1 / HHI), which
  does not grow with the number of days or jobs, and country shares of jobs
  with a known country; a missing country is never a country. The median
  hourly rate uses Notebook 04's population (midpoints of complete stated
  ranges). Changes between months are labelled "descriptive change between
  the last two observed periods", never growth rates; the tested trends stay
  those of Notebook 05.
- **Updates monthly:** refresh driven by new data. A newer extract plus
  `rebuild` adds new months and weeks with no code change (tested: a mini
  project rebuilt with synthetic April data shows "Apr 2024 (14 days)" on
  the page). The page shows the observed period and build ID. No scheduler is
  claimed, because the source has no live feed.
- **Forecasts:** shown dashed in a shaded period labelled "Forecast", with
  "Observed through" and the forecast dates written out; direction labels are
  Notebook 06's, including "No reliable direction", with no arrows.
- **Offline:** plotly.js is served from the installed plotly package, and the
  map uses a bundled Natural Earth 1:110m country outline (public domain;
  five small countries such as Singapore are too small to draw and are
  listed under the map). An empty base layer stops plotly.js from fetching
  its own outline, so no internet connection is needed.
- **Robustness fix found by the April test:** the forecast step divided by a
  zero MASE scale when a series never changes week on week (possible in tiny
  or synthetic data). The scale is now NaN in that case; outputs of the real
  build are byte-identical.
- **Evidence:** `src/job_market/monitor.py`, `steps/monitor.py`,
  `src/job_market_web/dashboard.py`, `templates/dashboard.html`,
  `tests/test_monitor.py`, `tests/test_dashboard.py`.

### D-037 SQL layer: SQLite database and cross-checks

- **What:** A pipeline step, `database`, deletes and recreates
  `data/processed/job_market.sqlite` from the committed `sql/schema.sql`. It
  holds row-level tables only: `jobs` (cleaned key fields), `job_categories`
  (frozen predictions), `category_labels` (read from the label sheets),
  `relevance_labels` (read from the relevance sheet) and
  `recommendation_results` (each method's ranked top 5, without labels), plus
  `build_info` (schema version and the build's input fingerprints: raw data,
  settings, code, environment and SQL). Identity is by content, not time:
  a build ID or creation time would make every rebuild differ, and the
  project requires a rebuild from the same inputs to be byte-identical (a
  first version stored them and failed that test). Keys and CHECK constraints guard the rows; indexes exist
  only for the columns the queries use. The file is regenerable and large, so
  it is not committed; the `.sql` files are, and their fingerprint is part of
  the build fingerprints.
- **Why SQLite:** built into Python, no server, works locally and in Docker,
  and supports joins, CTEs, window functions and indexes.
- **Queries:** eight files recompute the reliable window, monthly volume
  (plain and weekday-standardized), monthly category and country shares (all
  known countries), weekly hourly share, the median hourly offer by country
  (window-function median: the middle row for odd counts, the mean of the two
  middle rows for even counts, as NumPy), category label accuracy (labels
  joined to predictions, no stored accuracy read) and the recommender's
  nDCG@5 and strict Precision@5 (frozen D-034 definition: gains 0/1/3, the
  pooled ideal per profile, full-precision discount constants because
  SQLite builds may lack log2()).
- **Claim:** SQL independently reproduces selected aggregations and
  evaluation metrics from the pipeline's verified row-level outputs. It does
  not verify the whole project: the cleaned fields, taxonomy predictions and
  recommender rankings come from Python.
- **Comparison rule:** counts exactly equal. The pipeline's CSV tables store
  decimals rounded to 6 places, so a decimal passes when it is within half a
  unit of the 6th place plus 1e-9 of the stored value; medians and label
  accuracy are compared without that allowance. Result: all 1,176 compared
  values pass; the largest decimal difference is 4.99e-7 (rounding only).
- **Checks:** `check` fails when the database's `build_info` fingerprints
  differ from the current build; the manifest also records its SHA-256.
- **Evidence:** `sql/`, `src/job_market/database.py`, `steps/database.py`,
  `tests/test_database.py`, Notebook 08.
