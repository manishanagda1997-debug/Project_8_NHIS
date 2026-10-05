-- Q3. Share of each month's jobs by job function (category).
SELECT substr(j.posted_date, 1, 7) AS month,
       c.primary_category,
       COUNT(*)                    AS jobs,
       100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY substr(j.posted_date, 1, 7)) AS share_pct
FROM jobs AS j
JOIN job_categories AS c USING (row_id)
WHERE j.eligible_for_timeseries = 1
GROUP BY month, c.primary_category
ORDER BY month, jobs DESC, c.primary_category;
