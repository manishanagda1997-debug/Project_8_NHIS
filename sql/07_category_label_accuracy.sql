-- Q7. Agreement between the human category labels and the frozen predictions.
-- The blind set is the honest result; the development set tuned the rules.
SELECT l.label_set,
       COUNT(*)                                                           AS labelled,
       SUM(CASE WHEN l.human_category = c.primary_category THEN 1 ELSE 0 END) AS correct,
       AVG(CASE WHEN l.human_category = c.primary_category THEN 1.0 ELSE 0.0 END) AS accuracy
FROM category_labels AS l
JOIN job_categories AS c USING (row_id)
GROUP BY l.label_set
ORDER BY l.label_set;
