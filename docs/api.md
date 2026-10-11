# Recommendation API

The web app serves a JSON API next to the recommendation page and the dashboard. Start it with `python -m job_market serve` (address `http://localhost:5000`) or with Docker (`http://localhost:8080`). All endpoints use `GET` and return JSON.

The app starts only when the build is verified and the recommendation method is approved in `config/recommender_approval.toml` (decision D-040). Successful API responses identify the build and recommendation method. Errors return a JSON message explaining the problem.

| Endpoint | Returns |
|---|---|
| `/api/health` | Whether the app is ready, the build, the recommender method and the indexed jobs |
| `/api/recommend` | The 10 best-matching jobs for the skills entered, with the filters applied and related market keywords |
| `/api/similar/<row_id>` | The 5 jobs most like one job |

The examples come from the official build `20261011T132714Z-e537465460`. Each example shows only the first item of `results`. The `returned_count` field gives the number of results in the complete response; the other lists are shown in full.

## `/api/health`

No parameters.

```json
{
  "status": "ok",
  "build_id": "20261011T132714Z-e537465460",
  "recommender_version": "1.0",
  "method": "hybrid_word_character_tfidf",
  "method_status": "chosen by the relevance test on this data",
  "approval_note": "",
  "approval_ref": "1570666f51a563e3240102b12a1968b3ad41c5c80ff67aa941d63b4eaf3755c1",
  "build_approval_ref": "1570666f51a563e3240102b12a1968b3ad41c5c80ff67aa941d63b4eaf3755c1",
  "first_day": "2024-02-16",
  "last_day": "2024-03-23",
  "observed_days": 37,
  "data_years": "2024",
  "profiles": 12,
  "indexed_jobs": 229520,
  "days_options": [
    "7",
    "14",
    "30",
    "all"
  ]
}
```

## `/api/recommend`

| Parameter | Required | Accepted values | Default |
|---|---|---|---|
| `skills` | yes | free text, at most 300 characters, at least one word | none |
| `days` | no | `7`, `14`, `30` or `all` (the period counted back from the last day of the data) | `14` |
| `contract` | no | `all`, `hourly` or `fixed` | `all` |
| `min_hourly` | no | a positive number up to 1,000; only with `contract=hourly` | none |
| `min_budget` | no | a positive number up to 1,000,000; only with `contract=fixed` | none |

Filter rules:

- An hourly job passes `min_hourly` when the upper end of the client's stated hourly range reaches the minimum. This does not mean the client offers that amount as the starting rate: a job showing `$18–$50/hr` passes a minimum of 30. A job with only one stated rate uses that rate. Jobs without a stated rate do not pass.
- `min_budget` compares fixed-price budgets only. Hourly rates and budgets are never compared with each other.
- Only the newest posting of each possible-repost chain is returned, and at most one result per title unless too few different titles match.

Example request:

```text
/api/recommend?skills=python%2C%20sql&days=14&contract=hourly&min_hourly=30
```

Response:

```json
{
  "build_id": "20261011T132714Z-e537465460",
  "recommender_version": "1.0",
  "method": "hybrid_word_character_tfidf",
  "method_status": "chosen by the relevance test on this data",
  "approval_note": "",
  "approval_ref": "1570666f51a563e3240102b12a1968b3ad41c5c80ff67aa941d63b4eaf3755c1",
  "build_approval_ref": "1570666f51a563e3240102b12a1968b3ad41c5c80ff67aa941d63b4eaf3755c1",
  "first_day": "2024-02-16",
  "last_day": "2024-03-23",
  "observed_days": 37,
  "data_years": "2024",
  "profiles": 12,
  "query": {
    "skills": "python, sql",
    "days": 14,
    "contract": "hourly",
    "min_hourly": 30.0,
    "min_budget": null
  },
  "filters_applied": [
    "Jobs posted in the final 14 days of the data.",
    "Only the newest posting of each possible-repost chain; at most one result per title unless too few different titles match.",
    "Hourly jobs only.",
    "Minimum hourly rate $30: a job passes when the maximum of the client's stated hourly range reaches it; jobs without a stated rate are excluded."
  ],
  "candidate_pool_size": 19471,
  "returned_count": 10,
  "results": [
    {
      "rank": 1,
      "row_id": 237057,
      "title": "Python & SQL Developer Needed for Data Analytics, Data Science, and Visualization",
      "link": "https://www.upwork.com/jobs/Python-amp-SQL-Developer-Needed-for-Data-Analytics-Data-Science-and-Visualization_%7E012e5c303ca13cec98?source=rss",
      "contract_type": "hourly",
      "pay": "$18–$50/hr",
      "country": "United States",
      "posted_date": "2024-03-19",
      "category": "data_analytics",
      "score": 0.4704
    }
  ],
  "related_keywords": {
    "items": [
      {
        "keyword": "script",
        "matching_jobs": 3,
        "lift": 6.91,
        "sentence": "'script' appears in 3 of the best-matching jobs (6.9 times its share in all pool jobs); associated with +10% higher hourly offers in the same country and category."
      }
    ],
    "message": null
  },
  "notes": [
    "Matches are based on job titles only; the data has no job descriptions.",
    "Jobs were posted from 2024-02-16 to 2024-03-23; links may point to closed jobs.",
    "Related market keywords describe associations in the data, not advice on what to learn."
  ]
}
```

Main response fields:

| Field | Meaning |
|---|---|
| `method`, `method_status` | The recommendation method served and how it was chosen |
| `approval_ref`, `build_approval_ref` | Hash of the approval record now, and when the build ran |
| `query` | The validated request |
| `filters_applied` | The filters in plain words |
| `candidate_pool_size` | Jobs that pass the period and filters |
| `results` | Ranked jobs: `rank`, `row_id`, `title`, `link`, `contract_type`, `pay`, `country`, `posted_date`, `category`, `score` |
| `related_keywords` | Terms that appear more often in the best-matching jobs and have pay or trend evidence; `message` explains an empty list |
| `notes` | The limits of the results |

The `score` shows how closely a job title matches the search text under the selected recommendation method (for similar jobs, how closely it matches the selected job's title). It is not a measure of job quality or of the chance of getting the job.

## `/api/similar/<row_id>`

`row_id` is a job's `row_id` from a recommendation result. The only parameter is `days`, as above. The selected job itself is excluded from the results.

Example request:

```text
/api/similar/237057?days=14
```

Response:

```json
{
  "build_id": "20261011T132714Z-e537465460",
  "recommender_version": "1.0",
  "method": "hybrid_word_character_tfidf",
  "method_status": "chosen by the relevance test on this data",
  "approval_note": "",
  "approval_ref": "1570666f51a563e3240102b12a1968b3ad41c5c80ff67aa941d63b4eaf3755c1",
  "build_approval_ref": "1570666f51a563e3240102b12a1968b3ad41c5c80ff67aa941d63b4eaf3755c1",
  "first_day": "2024-02-16",
  "last_day": "2024-03-23",
  "observed_days": 37,
  "data_years": "2024",
  "profiles": 12,
  "selected": {
    "row_id": 237057,
    "title": "Python & SQL Developer Needed for Data Analytics, Data Science, and Visualization",
    "link": "https://www.upwork.com/jobs/Python-amp-SQL-Developer-Needed-for-Data-Analytics-Data-Science-and-Visualization_%7E012e5c303ca13cec98?source=rss",
    "contract_type": "hourly",
    "pay": "$18–$50/hr",
    "country": "United States",
    "posted_date": "2024-03-19",
    "category": "data_analytics"
  },
  "days": 14,
  "returned_count": 5,
  "results": [
    {
      "rank": 1,
      "row_id": 183783,
      "title": "Data Analytics Visualization",
      "link": "https://www.upwork.com/jobs/Data-Analytics-Visualization_%7E01dd2adb594bfd6b22?source=rss",
      "contract_type": "hourly",
      "pay": "$20–$50/hr",
      "country": "United States",
      "posted_date": "2024-03-11",
      "category": "data_analytics",
      "score": 0.5766
    }
  ]
}
```

## Errors

Errors return a JSON object with one `error` message. A filter that does not fit the chosen contract type is an error, never silently ignored.

| Request | Status | `error` |
|---|---|---|
| `/api/recommend` | 400 | skills is required, for example skills=python, pandas, sql. |
| `/api/recommend?skills=python&min_hourly=30` | 400 | min_hourly can only be used with contract=hourly. |
| `/api/recommend?skills=python&days=3` | 400 | days must be one of 7, 14, 30 or all. |
| `/api/recommend?skills=python&foo=1` | 400 | Unknown parameter(s): foo. Allowed: contract, days, min_budget, min_hourly, skills. |
| `/api/similar/abc` | 400 | row_id must be a whole number. |
| `/api/similar/999999999` | 404 | Job not found. |
| `/api/nothing` | 404 | Not found. |

Other checks return the same kind of message, for example a `skills` value over 300 characters or a `min_hourly` that is not a positive number.
