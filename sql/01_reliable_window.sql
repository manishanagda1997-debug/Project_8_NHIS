-- Q1. How many days and jobs are in the reliable time-series window?
SELECT MIN(posted_date)            AS first_day,
       MAX(posted_date)            AS last_day,
       COUNT(DISTINCT posted_date) AS days,
       COUNT(*)                    AS jobs
FROM jobs
WHERE eligible_for_timeseries = 1;
