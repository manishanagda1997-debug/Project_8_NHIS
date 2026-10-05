-- Q8. nDCG@5 and strict Precision@5 per profile and method, from the blind
-- relevance judgements (frozen definition, decision D-034):
--   gain = 2^label - 1  (labels 0/1/2 -> gains 0/1/3)
--   DCG@5  = sum over the method's ranks 1-5 of gain / log2(rank + 1)
--   IDCG@5 = the same sum for the best five labels judged for that profile
--            (the whole pooled set, so all methods share one ideal)
--   nDCG@5 = DCG@5 / IDCG@5 (0 when nothing judged is relevant)
--   strict Precision@5 = share of the 5 positions labelled 2
-- Discounts are full-precision constants (SQLite builds may lack log2()).
WITH discount (rank, value) AS (
    VALUES (1, 1.0),
           (2, 0.6309297535714575),
           (3, 0.5),
           (4, 0.4306765580733931),
           (5, 0.3868528072345416)
),
judged AS (
    SELECT r.profile_id, r.method, r.rank, l.relevance,
           CASE l.relevance WHEN 2 THEN 3 WHEN 1 THEN 1 ELSE 0 END AS gain
    FROM recommendation_results AS r
    JOIN relevance_labels AS l
      ON l.profile_id = r.profile_id AND l.title_key = r.title_key
),
dcg AS (
    SELECT j.profile_id, j.method,
           SUM(j.gain * d.value)                                AS dcg,
           SUM(CASE WHEN j.relevance = 2 THEN 1 ELSE 0 END) / 5.0 AS strict_precision_at_5
    FROM judged AS j
    JOIN discount AS d USING (rank)
    GROUP BY j.profile_id, j.method
),
ideal AS (
    SELECT profile_id,
           CASE relevance WHEN 2 THEN 3 WHEN 1 THEN 1 ELSE 0 END                 AS gain,
           ROW_NUMBER() OVER (PARTITION BY profile_id ORDER BY relevance DESC) AS rank
    FROM relevance_labels
),
idcg AS (
    SELECT i.profile_id, SUM(i.gain * d.value) AS idcg
    FROM ideal AS i
    JOIN discount AS d USING (rank)
    GROUP BY i.profile_id
)
SELECT g.profile_id,
       g.method,
       CASE WHEN i.idcg > 0 THEN g.dcg / i.idcg ELSE 0.0 END AS ndcg_at_5,
       g.strict_precision_at_5
FROM dcg AS g
JOIN idcg AS i USING (profile_id)
ORDER BY g.profile_id, g.method;
