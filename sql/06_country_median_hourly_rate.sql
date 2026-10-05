-- Q6. Median hourly offer by client country (Notebook 04's population:
-- jobs eligible for hourly-rate analysis; countries with at least
-- :min_country_jobs such jobs). SQLite has no MEDIAN function, so rows are
-- ranked with a window function: an odd count takes the middle row, an even
-- count averages the two middle rows (the same rule as pandas / NumPy).
WITH population AS (
    SELECT country, hourly_mid
    FROM jobs
    WHERE eligible_for_hourly_rate_analysis = 1
      AND country IS NOT NULL
),
counted AS (
    SELECT country, COUNT(*) AS jobs
    FROM population
    GROUP BY country
    HAVING COUNT(*) >= :min_country_jobs
),
ranked AS (
    SELECT p.country,
           p.hourly_mid,
           c.jobs,
           ROW_NUMBER() OVER (PARTITION BY p.country ORDER BY p.hourly_mid) AS position
    FROM population AS p
    JOIN counted AS c USING (country)
)
SELECT country,
       jobs,
       AVG(hourly_mid) AS median_rate
FROM ranked
WHERE position IN ((jobs + 1) / 2, (jobs + 2) / 2)   -- integer division
GROUP BY country, jobs
ORDER BY country;
