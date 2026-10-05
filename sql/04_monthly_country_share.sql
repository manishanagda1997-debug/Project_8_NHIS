-- Q4. Share of each month's jobs with a known client country, for every country.
-- A missing country is excluded, never counted as a country of its own.
SELECT substr(posted_date, 1, 7) AS month,
       country,
       COUNT(*)                  AS jobs,
       100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY substr(posted_date, 1, 7)) AS share_pct
FROM jobs
WHERE eligible_for_timeseries = 1
  AND country IS NOT NULL
GROUP BY month, country
ORDER BY month, jobs DESC, country;
