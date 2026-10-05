-- SQLite schema of data/processed/job_market.sqlite (decision D-037).
-- The pipeline's `database` step deletes the file and recreates it from this
-- schema on every rebuild, then loads row-level tables. The SQL queries in
-- this folder recompute selected results from these rows; the cleaned
-- fields, categories and recommendation rankings themselves come from the
-- Python pipeline.

-- What produced this database: the schema version and the build's input
-- fingerprints (raw data, settings, code, environment, SQL). Identity by
-- content, not time, so a rebuild from the same inputs is byte-identical.
-- `python -m job_market check` compares them with the current build.
CREATE TABLE build_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per job of the cleaned master table (key columns only).
CREATE TABLE jobs (
    row_id                            INTEGER PRIMARY KEY,
    title_key                         TEXT,
    posted_date                       TEXT    NOT NULL,   -- YYYY-MM-DD (UTC)
    iso_week                          TEXT    NOT NULL,   -- e.g. 2024-W08
    contract_type                     TEXT    NOT NULL CHECK (contract_type IN ('hourly', 'fixed')),
    hourly_low                        REAL,
    hourly_high                       REAL,
    hourly_mid                        REAL,
    budget                            REAL,
    country                           TEXT,               -- NULL when unknown; never 'Unknown'
    eligible_for_timeseries           INTEGER NOT NULL CHECK (eligible_for_timeseries IN (0, 1)),
    eligible_for_hourly_rate_analysis INTEGER NOT NULL CHECK (eligible_for_hourly_rate_analysis IN (0, 1))
);

-- One frozen category prediction per job (Notebook 03).
CREATE TABLE job_categories (
    row_id           INTEGER PRIMARY KEY REFERENCES jobs (row_id),
    primary_category TEXT NOT NULL
);

-- Human category labels from data/labels (development and blind sets).
CREATE TABLE category_labels (
    label_set      TEXT    NOT NULL CHECK (label_set IN ('dev', 'blind')),
    sample_id      TEXT    NOT NULL,
    row_id         INTEGER NOT NULL REFERENCES jobs (row_id),
    human_category TEXT    NOT NULL,
    PRIMARY KEY (label_set, sample_id),
    UNIQUE (label_set, row_id)
);

-- Blind relevance judgements of the recommender (one per profile and title).
CREATE TABLE relevance_labels (
    profile_id TEXT    NOT NULL,
    title_key  TEXT    NOT NULL,
    relevance  INTEGER NOT NULL CHECK (relevance IN (0, 1, 2)),
    PRIMARY KEY (profile_id, title_key)
);

-- Each method's ranked top 5 per profile (rankings produced in Python; no labels here).
CREATE TABLE recommendation_results (
    profile_id TEXT    NOT NULL,
    method     TEXT    NOT NULL,
    rank       INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 5),
    row_id     INTEGER NOT NULL REFERENCES jobs (row_id),
    title_key  TEXT    NOT NULL,
    PRIMARY KEY (profile_id, method, rank)
);

-- Only the indexes the queries use.
CREATE INDEX jobs_posted_date ON jobs (posted_date);
CREATE INDEX jobs_country ON jobs (country);
CREATE INDEX jobs_title_key ON jobs (title_key);
CREATE INDEX job_categories_category ON job_categories (primary_category);
