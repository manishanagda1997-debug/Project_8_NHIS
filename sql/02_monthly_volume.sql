-- Q2. Jobs per day by calendar month: plain and weekday-standardized.
-- Weekday-standardized = the average of the seven weekday means, so a month
-- with more Fridays or Saturdays is not favoured (NULL if a weekday is missing).
WITH daily AS (
    SELECT substr(posted_date, 1, 7)                  AS month,
           posted_date,
           CAST(strftime('%w', posted_date) AS INTEGER) AS weekday,
           COUNT(*)                                   AS jobs
    FROM jobs
    WHERE eligible_for_timeseries = 1
    GROUP BY posted_date
),
weekday_means AS (
    SELECT month, weekday, AVG(jobs) AS mean_jobs
    FROM daily
    GROUP BY month, weekday
),
standardized AS (
    SELECT month, CASE WHEN COUNT(*) = 7 THEN AVG(mean_jobs) END AS jobs_per_day_weekday_std
    FROM weekday_means
    GROUP BY month
)
SELECT d.month,
       MIN(d.posted_date)         AS first_day,
       MAX(d.posted_date)         AS last_day,
       COUNT(*)                   AS days_observed,
       SUM(d.jobs)                AS jobs,
       SUM(d.jobs) * 1.0 / COUNT(*) AS jobs_per_day,
       s.jobs_per_day_weekday_std
FROM daily AS d
JOIN standardized AS s USING (month)
GROUP BY d.month
ORDER BY d.month;
