-- Q5. Jobs per day and the hourly share by ISO week (Monday-Sunday).
SELECT iso_week,
       COUNT(DISTINCT posted_date)                       AS days_observed,
       COUNT(*)                                          AS jobs,
       COUNT(*) * 1.0 / COUNT(DISTINCT posted_date)      AS jobs_per_day,
       100.0 * AVG(CASE WHEN contract_type = 'hourly' THEN 1.0 ELSE 0.0 END) AS hourly_share_pct
FROM jobs
WHERE eligible_for_timeseries = 1
GROUP BY iso_week
ORDER BY iso_week;
