# Job Market Analysis and Recommendation System

**Final report** · Manisha Nagda · October 2026

Repository: [github.com/manishanagda1997-debug/job-market-analysis](https://github.com/manishanagda1997-debug/job-market-analysis)

**Contents**

1. Executive summary
2. Data and project scope
3. Data quality and methodology
4. Task 1: Keywords and pay
5. Task 2: Emerging job categories
6. Task 3: High-demand role forecasting
7. Task 4: Client-country hourly rates
8. Task 5: Recommendation engine
9. Task 6: Monthly market dashboard
10. Task 7: Online and remote hiring landscape
11. Task 8: Future job-market outlook and scenarios
12. Engineering and reproducibility
13. Tools and technology choices
14. Limitations
15. Conclusion

## 1. Executive summary

This report analyses 244,828 Upwork job postings, mostly from February and March 2024. Results over time use the reliable collection window of 37 days, 16 February to 23 March 2024 (229,520 jobs). The data contains job titles, not descriptions, so every result describes titles. One reproducible pipeline produces all results, and code checks every number quoted in the analysis notebooks.

**Task 1: Do title keywords relate to offered pay?**
Of 322 frequent title keywords, about two-thirds are linked with significantly higher or lower hourly offers, even among jobs from the same client country and job category (false discovery rate 5%). These are associations, not causes.

- **Higher offers:** titles containing words such as "consultant", "tax", "financial", "strategy" and "videographer". For example, titles with "consultant" offer about 77% more than similar jobs.
- **Lower offers:** titles with "virtual assistant" (about 38% less), "customer service", "lead generation" and "Canva".

Title words explain about a quarter of the variation in hourly offers.
*Limit:* these are offers in postings, not earnings. A title word may also be linked with other factors that are not included in the data.

**Task 2: Which job categories are emerging?**
Within the window, 9 of 22 job functions change their share of postings significantly.

- **Gaining share:** Digital Marketing (+1.0 percentage points, +10%), Video, Design, Sales, E-commerce, and AI & Machine Learning.
- **Losing share:** Writing & Content (from 5.8% to 3.7% of postings, −35%), Admin (−1.4 points) and Translation (−0.9 points).

The directions hold without possible reposts, without days with collection gaps, and in a complete-week comparison. Part of the change is a step around 26 February. Gradual change continues after it for Writing (down) and for AI & ML, Sales and E-commerce (up).
*Limit:* five weeks show short-term shifts, not long-run trends. The categories agree with blind human labels for 68.9% of titles.

**Task 3: Which roles will be in high demand?**
Web Development, Design & Creative and Digital Marketing remain the highest-demand functions over the next week, at about 900, 715 and 665 jobs a day. The forecasting model is a weekday mean. The selection rule uses earlier data and stays fixed before the final test. In the reserved final week, it beats the simple seasonal baseline for 20 of 23 category series, with a mean Relative MAE of 0.84. It does not beat the baseline for total volume.
*Limit:* five weeks of history and one week of final testing; neighbouring ranks often overlap.

**Task 4: How do hourly rates differ by client country?**
91 client countries have at least 30 jobs with a complete hourly range. US clients offer the highest typical rate among large markets: a median of $25 an hour, about 9% above average for the same kinds of jobs. Part of the differences between countries comes from the mix of work. Australian clients, for example, have a near-average median, but their adjusted index is about 12% below average after accounting for job-category mix. An interactive map shows both views.
*Limit:* the rate is the midpoint of the range the client states. Small countries have wide uncertainty.

**Task 5: Can we recommend relevant jobs from a freelancer's skills?**
Yes. A working web page and JSON API recommend jobs from the last 14 days of postings (82,565 jobs after keeping only the newest of likely reposts). It offers strict pay filters, similar jobs, and related market keywords.

A blind pooled relevance check compares three matching methods across 12 freelancer profiles. The person giving the relevance labels does not see which method returns each job. Under the scoring rule that stays fixed before evaluation, the hybrid word-and-character TF-IDF method wins: nDCG@5 is 0.985 and strict Precision@5 is 0.967, compared with 0.953 nDCG@5 for simple keyword matching.
*Limit:* matching uses titles only; 12 profiles is a small evaluation; the postings are from 2024.

**Task 6: How can market changes be tracked month by month?**
A dashboard shows, for each observed month:

- headline numbers, and weekly volume and category shares;
- the tested category trends;
- pay keywords and the country map;
- forecasts and online-hiring signals.

It updates through a fixed chain: a new monthly extract → pipeline rebuild → updated monthly tables → updated dashboard. In the current data, both months are partial. Weekday-standardised volume moves from 6,348 jobs a day in February to 6,171 in March (−2.8%). This is a descriptive change, not a tested trend.
*Limit:* there is no live data feed, and only two partial months exist so far.

**Task 7: What is changing in online and remote hiring?**
The dataset has no structured remote or on-site field, so it cannot measure the percentage of jobs that are remote or show a direct shift between office and remote work. Explicit work-arrangement words are rare: "remote" appears in about 0.5% of titles and on-site requirements in under 0.1%. The signals the data can measure are mostly stable:

- **Client geography:** about 46% of clients are in North America, and the client base is as concentrated as if about 5 countries had equal shares.
- **Hourly vs fixed-price:** fixed-price work gains slightly. The hourly share falls from 58.3% to 56.1%, a significant change of −2.2 points.

The forecasts expect all three signals to stay about where they are over the next two weeks.
*Limit:* this analysis describes online-hiring patterns and explicit title mentions. It does not measure the share of office jobs versus remote jobs.

**Task 8: What does the near future look like?**

- **Central outlook:** about 6,100 jobs a day in the next week.
- **80% empirical range:** the first-week range is about 5,930 to 6,310 jobs a day, based on the forecast errors from backtesting.
- **Trend-continuation scenario:** a modest continuing rise is supported for Digital Marketing, Video, Design and, marginally, Business & Project Management. For major Task 2 movers such as Writing and AI & ML, the trend model does not beat the baseline, so the outlook is "no reliable direction".

The trend-continuation result is an alternative scenario, not the selected forecast. The full forecast horizon is 14 days, and uncertainty is wider in the second week.
*Limit:* five weeks of history; these are statistical scenarios, not economic forecasts.

**Engineering.** The project can reproduce the analysis from the raw file with one command. It also checks the work through:

- file hashes and lineage checks;
- more than 400 automated tests and continuous integration;
- SQL that reproduces selected aggregations and evaluation metrics;
- Docker deployment with Nginx, Gunicorn and Flask.

### Key numbers

Each number in this table is checked against the committed result tables by `tests/test_report.py`.

<!-- key-numbers:start -->
| Area | Result | Evidence |
|---|---|---|
| Data | 244,828 postings; 229,520 jobs in the reliable 37-day window (16 Feb - 23 Mar 2024) | Notebook 01 |
| Task 1: pay words | "consultant" about +77% and "virtual assistant" about -38% against jobs in the same country and category | Notebook 04 |
| Task 2: emerging categories | 9 job functions change share significantly; Writing & Content falls from 5.8% to 3.7% of postings (-35%) | Notebook 05 |
| Task 3: high demand | Web Development, Design & Creative and Digital Marketing lead the next week at about 900, 715 and 665 jobs a day | Notebook 06 |
| Tasks 3 and 8: forecast test | The weekday mean beats the seasonal baseline for 20 of 23 category series in the reserved final week (mean Relative MAE 0.84) | Notebook 06 |
| Task 4: countries | 91 client countries with at least 30 rated hourly jobs; United States median $25/h, adjusted index +9% | Notebook 04 |
| Task 5: recommender | Hybrid TF-IDF: nDCG@5 0.985, strict Precision@5 0.967 over 12 blind-labelled profiles | Notebook 07 |
| Task 5: candidate pool | 82,565 jobs in the 14-day pool after keeping the newest posting of each possible-repost chain | Notebook 07 |
| Task 6: dashboard | Weekday-standardised volume 6,348 jobs a day in Feb 2024 and 6,171 in Mar 2024 (-2.8%) | Dashboard |
| Task 7: online hiring | Hourly share falls from 58.3% to 56.1% over the window | Notebook 05 |
| Task 8: outlook | Central outlook about 6,100 jobs a day; 80% empirical range 5,930-6,310 for days 1-7 | Notebook 06 |
| Job categories | 68.9% agreement with blind human labels (241 of 350 titles) | Notebook 03 |
| SQL cross-checks | 8 SQL queries reproduce every compared pipeline value | Notebook 08 |
<!-- key-numbers:end -->

## 2. Data and project scope

The source is the Upwork job-postings file supplied with the assignment: 244,828 rows and 8 columns. Each row is one job posting. The columns are the title, the link, the posting time, whether the job is hourly, the low and high hourly rate, the fixed-price budget, and the client's country. There are no job descriptions, skills lists, freelancer data or final contract values, so every result describes what the client writes in the title and offers in the posting.

| Item | Value |
|---|---|
| Rows | 244,828 |
| Valid job rows | 244,827 |
| Hourly / fixed-price jobs | 140,937 / 103,891 |
| Postings with a client country | 98% (212 countries) |
| Distinct cleaned titles | 205,289 |
| Exact duplicate rows | 0 |
| Reliable time-series window | 16 February - 23 March 2024 (37 days, 229,520 jobs) |

One row has no title, link or country, so it does not meet the valid-job rule and is excluded from analysis. Each analysis then uses the eligible subset needed for that question.

The postings run from November 2023 to March 2024, but collection is thin before mid-February and the last day is cut off. I compare each day's volume with the median for the same weekday. A day with less than 90% of that median is incomplete. The primary time-series window runs from 16 February to 23 March. Every day in this window meets the daily-volume rule, while 17, 18 and 20 February still carry small intraday-gap flags and stay in sensitivity checks. Days outside the window are incomplete. All time-based analyses use this 37-day window. Among the 244,827 valid jobs, 15,307 fall outside it and remain available for analyses that do not depend on time.

![Figure 1: Jobs per day in the reliable window](figures/f1_daily_volume.png)

*Figure 1. Jobs per day, 16 February - 23 March 2024. The weekly cycle is strong: Monday to Thursday have about 6,800-7,100 jobs a day, weekends about 4,400-4,800. Because the window has six Fridays and Saturdays but five of every other weekday, for period comparisons, I use averages per day rather than raw totals.*

**Evidence:** Notebooks 00 and 01; `raw_column_profile.csv`, `raw_daily_coverage.csv`, `day_quality.csv`.

## 3. Data quality and methodology

**Cleaning.** I never change or delete the original values. The cleaned master table adds new columns next to them:

- **Titles:** 10,130 titles contain HTML codes (such as `&amp;`) and 208 contain garbled characters from a wrong text encoding. I repair both in a cleaned title and keep the raw title.
- **Pay:** hourly and fixed-price fields never mix, and no range is inverted. About 27% of hourly jobs state no rate; I do not fill these gaps. Hourly pay is the midpoint of a complete stated range. Values at or above the 99.9% quantile ($500 an hour, $100,000 budgets) include placeholders such as $999 an hour, so I flag them and report pay results with and without them.
- **Repeats:** a title can appear again because a posting may be repeated or because several clients post similar jobs. I flag a *possible repost* only when the title, country, contract type and exact pay all match a posting from the previous 3 days (9,190 jobs). I never delete these jobs; I use the flag for sensitivity checks.
- **Eligibility:** each analysis uses a stated subset. For example, hourly pay uses only jobs with a complete range, and trends use only the 37-day window.

**Job categories.** The data has no category field, so I build one. Every job gets exactly one primary category: one of 22 job functions, or *Other / Unclear*. Transparent keyword rules decide 87% of jobs. A TF-IDF logistic-regression classifier, trained on titles the rules label, handles about 1% more. It only decides when its confidence is at least 0.70, and only in the 14 categories where it passes a reliability check on titles it does not see in training. The remaining titles go to *Other / Unclear*.

I test the categories against my own human labels in two sets:

- 150 development titles, which I label and then use to tune the rules (83.3% agreement after tuning);
- 350 blind titles, a random sample I draw before any tuning. I label them without seeing the system's predictions; the label sheet shows only the title. The categorizer stays frozen, and I score this set once.

On the blind set, the system agrees with my label for 68.9% of titles (241 of 350; 95% interval 63.8%-73.5%). When it names a category rather than *Other*, it agrees 77.2% of the time. On the blind set, the system chooses *Other / Unclear* for 13.4% of titles; I choose it for 6.3%. Software & IT, AI & ML, Engineering and Admin have low recall (31-46%), so their observed shares are likely to be understated. Every later result that uses categories inherits this uncertainty, and I show the *Other* share next to category results.

**Statistical rules used throughout.**

- **Multiple testing:** when I test many keywords or categories at once, I use the Benjamini-Hochberg false discovery rate (FDR) at 5%. This controls the expected share of false positives among the results called significant.
- **Repeated titles:** for pay, standard errors are clustered by title, so many postings of the same title do not count as independent evidence.
- **Trends over time:** standard errors use Newey-West with a 7-day lag, which allows for days that are not independent. I fix the lag before seeing any result.
- **Sensitivity checks:** for the main pay and trend analyses, I repeat the results under alternative reasonable choices, such as removing possible reposts, removing the three gap days and, for pay, removing extreme values.
- **Fixed rules first:** I fix model choices, thresholds and evaluation rules before the final evaluation, and I run the final evaluation once.

**Evidence:** Notebooks 01, 02 and 03; `cleaning_log.csv`, `eligibility_counts.csv`, `label_evaluation_summary.csv`, `docs/decisions.md`.

## 4. Task 1: Keywords and pay

**Question.** Which words in job titles go with higher or lower offered pay?

**Method.** I take words and two-word phrases from the cleaned titles and keep those with at least 300 jobs with a complete hourly range and at least 100 different titles: 322 keywords. For each keyword I model log hourly pay in three layers:

1. **Raw:** keyword only.
2. **Country-adjusted:** the regression gives each client country its own baseline, so differences in country mix do not drive the keyword result.
3. **Country-and-category-adjusted:** each combination of country and job category gets its own baseline, so the keyword is compared with jobs in the same country and job function.

**The third layer is the most adjusted comparison, but it is not the only useful answer.** Category itself comes from the title, so controlling for it removes part of the title signal. I therefore show all three. Fixed-price budgets get the same analysis separately (`pay_keywords_budget.csv`); hourly rates and budgets are never mixed.

**Results.** 206 of the 322 keywords (64%) remain significant in the third layer (FDR 5%).

| Title word | Raw difference | Same country and category |
|---|---|---|
| consultant | +84% | +77% (95% interval +68% to +86%) |
| virtual assistant | −62% | −38% (−42% to −34%) |
| python | +10% | −7.5% |
| blockchain | +74% | +44% |

- **Higher offers:** consulting and specialist words, such as "consultant", "consultation", "tax", "financial", "strategy" and "videographer".
- **Lower offers:** assistant and volume-work words, such as "virtual assistant", "customer service", "lead generation" and "list". Common platform skills are also lower than similar jobs: "Shopify", "WordPress" and "Flutter" by 8-13%, and "SEO", "Excel" and "Canva" by 19-35%.
- **Adjustment changes the result for some words.** "Python" looks 10% higher in the raw comparison but 7.5% lower after country and category adjustment. This sign change shows that the raw association depends strongly on the mix of job categories. "AI" is 19% higher in the raw comparison, but the difference is not significant after adjustment.

![Figure 2: Title words linked with higher or lower hourly offers](figures/f2_pay_keywords.png)

*Figure 2. Difference in hourly offers for jobs whose title contains the word, compared with jobs from the same client country and category. Black lines show 95% intervals; only significant words (FDR 5%) are shown, the 12 strongest in each direction.*

**How much do titles explain?** On a 20% test split where no title appears in both training and test, country and category alone explain about 11% of the variation in log hourly offers. Adding title words raises this to about 26%, with a median error of about $8 an hour. So title words add useful information, but the model still leaves most of the variation in hourly offers unexplained. The keyword results are stable across five reasonable analysis choices (correlation with the main result at least 0.97; same direction for at least 93% of keywords).

*Limit:* these are associations, not causes. A title word may also be linked with other factors that are not included in the data. Pay is what clients offer, not what freelancers earn.

**Evidence:** Notebook 04 (Task 1); `pay_keywords_hourly.csv`, `pay_keywords_budget.csv`, `pay_keyword_sensitivity.csv`, `pay_prediction.csv`.

## 5. Task 2: Emerging job categories

**Question.** Which job categories gain or lose ground over time?

**Method.** For each of the 22 job functions, I calculate its share of each day's postings in the 37-day window. A share is better than a count here, because total volume changes with the weekday. I fit a straight-line trend with weekday effects and report the change across the window in percentage points and in relative terms, with Newey-West intervals and FDR-adjusted p-values. *Other / Unclear* is monitored separately, not tested as a category. I then check every significant result three ways: without possible reposts, without the gap days, and comparing the first two with the last two complete weeks.

**Results.** 9 of the 22 functions change significantly.

| Function | Share at start → end of window | Change in points | Relative change |
|---|---|---|---|
| Digital Marketing | 10.0% → 11.0% | +1.0 | +10% |
| Video & Animation | 6.5% → 7.1% | +0.6 | +10% |
| Design & Creative | 11.4% → 11.9% | +0.5 | +4% |
| Sales & Lead Generation | 3.7% → 4.1% | +0.4 | +10% |
| AI & Machine Learning | 1.3% → 1.5% | +0.25 | +19% |
| E-commerce Operations | 1.7% → 1.8% | +0.16 | +9% |
| Translation & Transcription | 2.3% → 1.3% | −0.9 | −41% |
| Admin & Virtual Assistance | 4.8% → 3.4% | −1.4 | −29% |
| Writing & Content | 5.8% → 3.7% | −2.0 | −35% |

*Start and end shares come from the fitted trend line and are rounded separately, so a difference can be off by 0.1 point.*

- **The directions hold in every check.** The sizes vary between checks, so I read them as ranges, not exact values. For example, Writing falls 35% in the trend line and 19% in the complete-week comparison.
- **Part of the change is a step, not a smooth trend.** Around 26 February several shares shift at once. After that step, gradual change continues only for Writing (−13%) and for AI & ML (+13%), Sales (+9%) and E-commerce (+7%). For Admin, Translation, Marketing, Video and Design, the later period shows no clear trend.
- **Title keywords show the same pattern.** "Writers", "data entry", "translation", "writing" and "documents" lose about half or more of their share, while "crypto" nearly doubles (+97%).
- **No sign of changing classification coverage.** *Other / Unclear* stays near 12.5% of postings, so there is no sign that the main shifts come from changing classification coverage.

![Figure 3: Change in category share over the window](figures/f3_category_trends.png)

*Figure 3. Change in each function's share of daily postings over the window, with 95% Newey-West intervals. Blue: significant rise; orange: significant fall; grey: no clear trend after the FDR adjustment. The intervals are not adjusted for multiple testing, so a grey bar can have an interval that just excludes zero (Web Development, Software & IT and Mobile Development).*

*Limit:* five weeks show short-term shifts in what clients post, not long-run industry trends. Category results carry the 68.9% blind agreement from Section 3.

**Evidence:** Notebook 05 (Task 2); `trend_categories.csv`, `trend_category_daily.csv`, `trend_keywords.csv`, `trend_other_monitor.csv`.

## 6. Task 3: High-demand role forecasting

**Question.** Which job functions will have the most postings in the near future?

**Method.** The reliable history is only 37 days, so I forecast a short horizon of 14 days (24 March - 6 April 2024). Days 1-7 are the main forecast; days 8-14 are an extended outlook with more uncertainty. I split the history into two parts:

- **Development period (first 30 days):** I compare four models fixed in advance: a seasonal baseline (the same weekday last week), a weekday mean (the average of the last 14 days for each weekday), a straight trend with weekday effects, and a damped trend. I test them with a rolling backtest that makes 7-day forecasts from ten starting points. The rule picks the model with the lowest mean seasonal MASE, one model for the whole family of demand series (total jobs plus the 23 category shares).
- **Reserved final week (last 7 days):** the model uses no data from these days for fitting or model choice. I score this window once after the model-selection rule chooses the winner. Notebook 05 still describes the full 37-day period, so I call this a reserved final evaluation window rather than a blind test.

Category forecasts are total jobs multiplied by the forecast category shares, so the 22 functions plus *Other* always add up to the total. Each forecast has an 80% empirical range from backtest errors for days 1-7 and a wider extended range for days 8-14 (Section 11).

**Model choice.** The weekday mean wins: its mean MASE in development is 0.77, against 0.82 for the damped trend, 0.84 for the straight trend and 0.86 for the seasonal baseline. Averaged across the 24 demand series, its Relative MAE is 1.01, which is close to the seasonal baseline. The two trend models have higher backtest error. A secondary 14-day check from three starting points gives the same winner.

**Final-week result.** For 20 of the 23 category series, the weekday mean beats the seasonal baseline (mean Relative MAE 0.84; below 1 means better than the baseline). For total jobs it does not: the baseline is best there, and every other model has a Relative MAE of about 1.5.

**Outlook for the next 7 days.**

| Rank | Function | Forecast jobs a day | 80% range |
|---|---|---|---|
| 1 | Web Development | about 900 | 846-951 |
| 2 | Design & Creative | about 715 | 664-770 |
| 3 | Digital Marketing | about 665 | 617-710 |
| 4 | Software & IT | about 465 | 434-497 |

*Other / Unclear* sits at about 760 jobs a day, between first and second place, and is not ranked as a function. The ranges of Design and Marketing overlap, so I treat them as similarly high-demand rather than as a clear second and third. Software & IT is likely to be understated, because many of its titles fall into *Other* (Section 3).

![Figure 4: Category outlook for the next 7 days](figures/f4_category_outlook.png)

*Figure 4. Forecast jobs a day for each function over the next 7 days, with 80% empirical ranges. Overlapping ranges mean similar demand.*

*Limit:* five weeks of history and one week of final testing. The forecast assumes the recent weekly pattern continues; it cannot see events, seasons or platform changes outside the data.

**Evidence:** Notebook 06; `forecast_model_choice.csv`, `forecast_backtest_14d.csv`, `forecast_final_evaluation.csv`, `forecast_demand_outlook.csv`, `forecast_demand_daily.csv`.

## 7. Task 4: Client-country hourly rates

**Question.** How do offered hourly rates differ by the client's country?

**Method.** Hourly pay is the midpoint of a complete stated range. I include every client country with at least 30 such jobs: 91 countries. For each one I report two numbers:

- **Median offer:** the typical rate, with a bootstrap interval that resamples titles, not single postings.
- **Adjusted index:** how much a country's clients offer compared with the average client *for the same job categories*. This separates "this country pays more" from "this country posts different kinds of work".

**Results.**

| Client country | Jobs | Median offer | Adjusted index |
|---|---|---|---|
| United States | 46,620 | $25.00 | +9% |
| United Kingdom | 8,113 | $22.50 | +2% |
| Australia | 5,682 | $21.00 | −12% |
| India | 4,337 | $20.00 | −21% |
| Philippines | 902 | $13.00 | −20% |

- **US clients offer the highest typical rate among large markets:** a median of $25 an hour and about 9% above average for the same kinds of jobs.
- **The UK, Germany and Switzerland are close to average** once job mix is taken into account (within ±6%).
- **Job mix matters.** Australia's median is close to the overall typical rate, but its adjusted index is about 12% below average after accounting for job-category mix. India and the Philippines are about 20% below average after adjustment.
- South Korea, Japan and Taiwan have adjusted indexes 28-48% below average.

**Stability.** Country rankings hardly change without extreme rates or without possible reposts (rank correlation at least 0.96). They change more if I use the high end of each range (0.90) or the low end (0.69), so the ranking of mid-sized countries at the low end is less certain.

![Figure 5: Median offer and adjusted index for the largest client countries](figures/f5_country_rates.png)

*Figure 5. Median hourly offer and category-adjusted index for the client countries with the most rated jobs. The interactive world map is in Notebook 04 and on the dashboard.*

*Limit:* rates are offers, not earnings, and many hourly jobs state no rate. Rates cluster at round numbers, so some median intervals collapse to a single value. Countries near the 30-job minimum have wide uncertainty.

**Evidence:** Notebook 04 (Task 4); `pay_countries.csv`, `pay_country_sensitivity.csv`.

## 8. Task 5: Recommendation engine

**Question.** Can a freelancer type their skills and get relevant jobs from the available postings?

**What it does.** A freelancer enters skills separated by commas. By default, the engine searches jobs from the last 14 days; the interface also allows 7 days, 30 days or all available jobs. The fixed evaluation uses the 14-day pool. The engine returns the 10 best-matching jobs, with pay shown as the client states it, for example `$15–$35/hr`.

The filters are strict. For an hourly filter, a job passes when the highest hourly rate it states reaches the requested minimum; a job that states no hourly rate never passes. For fixed-price work, the stated budget must meet or exceed the requested minimum. Hourly rates and fixed-price budgets are never compared with each other. Each result offers 5 similar jobs. A side panel shows related market keywords when the evidence from Tasks 1 and 2 supports one.

**Design choices.**

- **Candidate pool:** 85,635 jobs from the last 14 days. I keep only the newest posting of each possible-repost chain, which leaves 82,565 jobs.
- **Diversity:** at most one result per title, unless too few different titles match, so the list does not show the same job ten times.
- **Matching methods:** I build three methods, from simple to complex: keyword overlap, word TF-IDF, and a hybrid of word and character TF-IDF. Character pieces help with spelling variants and different word forms.

**Evaluation.** I write 12 freelancer profiles covering different kinds of work. For each profile, the top 5 results of all three methods go into one pooled sheet, shuffled, with the method hidden. I label each title 0 (not relevant), 1 (partly relevant) or 2 (relevant), and only then compute the scores. The scoring rule stays fixed before evaluation:

1. The main score is nDCG@5 against the best possible ranking of everything judged for that profile.
2. If two methods differ by less than 0.02, they count as tied, and strict Precision@5 decides (only label 2 counts).
3. If they are still tied, the simpler method wins.

| Method | Mean nDCG@5 | Strict Precision@5 |
|---|---|---|
| Keyword overlap | 0.953 | 0.933 |
| Word TF-IDF | 0.971 | 0.950 |
| **Hybrid TF-IDF (winner)** | **0.985** | **0.967** |

The hybrid and word TF-IDF methods are within the 0.02 tie margin, so strict Precision@5 decides, and the hybrid wins. Keyword overlap is outside the margin. All three methods are very good at matching titles: seven of the 12 profiles are perfect for every method. The fixed rule selects a winner, but the small differences do not show that one method is generally better.

**Product checks.** For every profile and every filter setting (no filter, at least $30/h, at least $50/h, fixed price at least $500), every method returns a full list of 10 different titles, with no filter violations and no job from outside the pool. Even at $50 an hour, thousands of jobs remain as candidates.

**Related keywords.** A keyword appears only if it has a significant pay or growth result from Tasks 1 or 2, appears in at least 3 of the 50 best matches, is not a generic word, and is at least twice as common in the matches as in the whole pool. Only two profiles get a keyword ("react" and "design"); the other ten get none. An initial check returns generic words such as "expert" and "help", so I add the generic-word rule and the "twice as common" rule once. I do not tune the feature again after that. This feature is descriptive and separate from the method evaluation.

**API and interface.** The Flask app uses exactly the same code as Notebook 07, and only the winning method:

| Address | Returns |
|---|---|
| `/` | the recommendation page |
| `/api/recommend?skills=…&days=…&contract=…&min_hourly=…&min_budget=…` | 10 jobs, the filters applied in words, related keywords |
| `/api/similar/<row_id>` | the 5 most similar jobs |
| `/api/health` | build ID, method and number of indexed jobs |

Invalid parameters return a clear 400 error; an unknown job returns 404. The full parameter list is in the README.

![Figure 6: Relevance scores of the three matching methods](figures/f6_recommender_eval.png)

*Figure 6. Mean nDCG@5 and strict Precision@5 for the three methods over 12 blind-labelled profiles. The dashed line marks the 0.02 tie margin below the best nDCG@5.*

![Recommendation page](../docs/images/recommender.png)

*The recommendation page for the skills "python, pandas, sql, power bi dashboards", hourly jobs from $30 an hour.*

*Limit:* matching uses titles only. The evaluation has 12 profiles and one judge, and most judged titles are relevant (115 of 122 get label 2), so the evaluation shows strong title-level relevance on these 12 profiles, but it cannot separate the three methods with high confidence. The postings are from 2024, and there is no click or application data for learning from behaviour.

**Evidence:** Notebook 07; `recommend_relevance_summary.csv`, `recommend_relevance_by_profile.csv`, `recommend_checks.csv`, `recommend_pool_sizes.csv`, `recommend_related_keywords.csv`; `src/job_market_web/`.

## 9. Task 6: Monthly market dashboard

**Question.** How can someone follow changes in the job market month by month?

**What it shows.** The dashboard at `/dashboard` has:

- headline numbers for each observed month: weekday-standardised jobs per day, hourly share, median hourly rate, and the effective number of client countries;
- weekly volume and weekly category shares, with a category selector;
- monthly category shares and the top client countries by month;
- the tested emerging and falling categories (Task 2);
- title words linked with higher or lower offers, and the country map (Tasks 1 and 4);
- the total and category forecasts, and the online-hiring signals (Tasks 3, 7 and 8).

**How it updates.** The dashboard computes nothing itself. It only draws verified tables from the current build:

> new monthly extract → pipeline rebuild → updated monthly and weekly tables → updated dashboard

New months and weeks appear without any code change. An automated test checks this: it builds a synthetic extract that runs into April 2024 and confirms that "Apr 2024 (14 days)" appears in the monthly table and on the page. There is no automatic schedule, because the source has no live feed; a refresh starts when a new extract arrives.

**Fair month comparisons.** A month can be partial, and months have different numbers of each weekday. So I do not compare monthly totals. I compare jobs per day standardised by weekday, and shares. I label partial months with their number of days. Changes between months are descriptive; the tested trends are in Task 2.

**Current data.** Both observed months are partial: February has 14 days and March 23.

| | Feb 2024 (14 days) | Mar 2024 (23 days) |
|---|---|---|
| Jobs per day, weekday-standardised | 6,348 | 6,171 (−2.8%) |
| Hourly share | 58.1% | 57.0% |
| Median hourly rate | $22.50 | $22.50 |
| Effective number of client countries | 5.25 | 5.19 |

![Market dashboard](../docs/images/dashboard.png)

*The top of the dashboard: headline numbers per month, weekly volume and weekly category share.*

*Limit:* only two partial months exist, so month-to-month changes are short and descriptive. The dashboard works offline, but it shows only what the latest build contains.

**Evidence:** web app (`/dashboard`); `monthly_market_summary.csv`, `monthly_category_share.csv`, `monthly_country_share.csv`, `weekly_market_summary.csv`, `weekly_category_share.csv`; `tests/test_dashboard.py`.

## 10. Task 7: Online and remote hiring landscape

**Question.** What is changing in online and remote hiring?

**What the data can and cannot measure.** The dataset has no structured remote or on-site field, so it cannot measure the percentage of jobs that are remote or show a direct shift between office and remote work. Instead, I measure three things the data does contain:

1. **Client geography:** where the clients who post online work are.
2. **Engagement structure:** hourly against fixed-price work, and mentions of long-term, full-time or part-time work.
3. **Explicit work-arrangement words:** "remote", "on-site", "hybrid", "work from home" and time-zone requirements in titles.

**Method.** I use the 37-day window and the same trend method as Task 2: a daily series, a weekday-adjusted straight-line trend, and Newey-West intervals. Countries are grouped into World Bank regions. Concentration uses the Herfindahl-Hirschman index (HHI), turned into an "effective number of countries": 1 / HHI, the number of equally sized countries that would give the same concentration.

**Results.**

- **Client geography is stable.** About 46% of clients with a known country are in North America, about 24% in Europe & Central Asia, about 11% in East Asia & Pacific, and 9-11% in South Asia each week. The client base is as concentrated as about 5.2 equally sized countries. None of these measures shows a trend over the window. About 2% of jobs have no country.
- **Fixed-price work gains slightly.** The hourly share falls from 58.3% to 56.1% over the window, a change of −2.2 points whose interval stays below zero.
- **Engagement words are rare.** "Long-term" or "ongoing" appears in about 1% of titles, and "full-time" and "part-time" in about 0.4% each.
- **Explicit arrangement words are rare and flat.** "Remote" appears in about 0.5% of titles, on-site or in-person requirements in under 0.1%, and time-zone requirements in about 0.1%. "Hybrid" and "work from home" appear in only a handful of titles a week. The weekly intervals overlap, so there is no measurable change.

**Forecasts (Notebook 06).** For the three signals with enough data, the same forecasting approach as Task 3 gives:

| Signal | Recent (last 7 days) | Forecast, next 14 days | Direction |
|---|---|---|---|
| Hourly share | 56.7% | 56.5% | no reliable direction |
| North American client share | 46.5% | 46.3% | no reliable direction |
| Effective number of client countries | about 5.2 | about 5.3 | stable |

The chosen model is the weekday mean. In the reserved final week, it beats the seasonal baseline for hourly share, but not for North American share or concentration, where the trend models have lower error in that week. I do not change the selected model after this final check. The errors remain small; for example, the North American share has an error of about 0.9 percentage points. Rare signals such as "remote" or "hybrid" get no forecast, because their counts are too small for a defensible one.

![Figure 7: Hourly share and North American client share, observed and forecast](figures/f7_online_signals.png)

*Figure 7. Daily hourly share and North American client share in the window, followed by the 14-day forecast with its range (80% empirical for days 1-7, extended for days 8-14).*

**What this means.** The clearest change in this dataset is the mix between hourly and fixed-price work: fixed-price work gains slightly. Client geography stays stable, while explicit work-arrangement words are too rare to show a clear change. A direct measure of remote work would need a structured remote/on-site field or information from the job descriptions.

*Limit:* this analysis describes online-hiring patterns and explicit title mentions. It does not measure the share of office jobs versus remote jobs. Five weeks show short-term movement only.

**Evidence:** Notebook 05 (Task 7), Notebook 06; `remote_series_trends.csv`, `remote_signals_weekly.csv`, `remote_regions_weekly.csv`, `remote_geography_weekly.csv`, `forecast_signals_outlook.csv`.

## 11. Task 8: Future job-market outlook and scenarios

**Question.** What does the job market look like over the next weeks?

I separate three things that are easy to mix up:

1. **Central outlook:** the selected weekday-mean forecast.
2. **Forecast range:** an 80% empirical range from backtest errors for days 1-7, and a wider extended range for days 8-14. It shows the uncertainty around the central forecast; it is not a separate scenario.
3. **Trend-continuation scenario:** what happens if the recent direction of each category continues. For the trend-continuation scenario only, I compare the two predefined trend models for each category using development backtests and use the better one. This does not change the central forecast, which stays the weekday mean. I report a direction only if that model beats the seasonal baseline in development (Relative MAE below 1); otherwise the result is "no reliable direction". A change smaller than 0.1 percentage points is "stable".

**Central outlook and range.**

| Total jobs a day | Central | Forecast range |
|---|---|---|
| Recent (last 7 days) | about 6,084 | — |
| Days 1-7 | about 6,117 | 5,931-6,307 |
| Days 8-14 | about 6,117 | 5,913-6,355 |

The central outlook is flat: total demand stays close to recent levels. The range for days 1-7 is an 80% empirical range from the 10th and 90th percentiles of backtest errors. For days 8-14, I widen that first-week range using square-root-of-horizon scaling, because the data does not provide enough independent 14-day forecast errors. I therefore treat the second-week band as an extended range, not a purely empirical interval.

**Trend-continuation scenario by category.**

| Direction | Categories |
|---|---|
| **Rising** (up to about +0.5 points of share) | Digital Marketing, Video & Animation, Design & Creative, and marginally Business & Project Management |
| **Stable** (9 categories) | Mobile Development, Software & IT, Photography, Sales & Lead Generation, Accounting & Finance, Legal, Engineering & Architecture, E-commerce Operations, HR & Recruiting |
| **No reliable direction** | Web Development, AI & ML, Data & Analytics, Writing & Content, Translation, Admin, Customer Service, Audio & Music, Education & Tutoring, and *Other / Unclear* |

Business & Project Management is only marginal: its trend model is barely better than the baseline (Relative MAE 0.996). The trend-continuation result is an alternative scenario, not the selected forecast.

**How this connects to Task 2.** Some of the biggest movers inside the window, such as Writing, Admin, Translation and AI & ML, get "no reliable direction" here. This is not a contradiction. Task 2 describes what happens *within* the five weeks, including the step around 26 February. Task 8 asks whether a trend model can predict the *next* days better than a simple baseline, and for these categories it cannot. A large past change does not guarantee that the same change continues.

![Figure 8: Total jobs per day, observed and forecast](figures/f8_total_outlook.png)

*Figure 8. Total jobs a day in the window, followed by the 14-day central outlook: the 80% empirical range for days 1-7 and the extended range for days 8-14.*

*Limit:* a 14-day horizon from five weeks of history. These are statistical scenarios, not economic forecasts: they cannot see seasonality beyond the week, platform changes or outside events. The total forecast does not beat the seasonal baseline in the final week (Section 6).

**Evidence:** Notebook 06; `forecast_demand_outlook.csv`, `forecast_demand_daily.csv`, `forecast_backtest_14d.csv`, `forecast_final_evaluation.csv`.

## 12. Engineering and reproducibility

I build the project so that anyone can rerun it and check the results.

**One pipeline.** A single command, `python -m job_market rebuild`, runs ten steps in order: ingest, clean, categorize, evaluate, pay, trends, forecast, recommend, monitor and database. Every threshold and path sits in one configuration file, `config/pipeline.toml`, and every analytical decision has a written reason in `docs/decisions.md`.

**A record of each build.** Each rebuild writes a run manifest. It stores SHA-256 fingerprints of the raw file, the configuration, the code, the environment and the SQL files, and a hash of every output file. The command `python -m job_market check` then confirms that:

- the raw data, settings, code and environment still match the build;
- every output matches its recorded hash, and no stale file exists;
- every notebook is a clean, top-to-bottom run of the current build.

**Notebooks that cannot drift.** The notebooks use the verified pipeline outputs rather than maintaining a separate analysis pipeline. Each analysis notebook (01 to 08) ends with a claims cell that checks every number quoted in its text against the data. If a quoted number is wrong, the notebook fails.

**Frozen evaluations.** I freeze each evaluation before I calculate its final score:

- Git tags `categorizer-1.0` and `blind-labels-final` freeze the category system and blind labels before the blind score;
- `recommender-1.0` and `relevance-labels-final` freeze the recommender settings and relevance labels before scoring;
- the configuration fixes the forecast models and model-selection rule before the reserved final week is scored.

**Automated tests and continuous integration.** More than 400 automated tests cover cleaning, categories, pay, trends, forecasts, the recommender, the web app, the dashboard, the database and the Docker setup. Many of them run the whole pipeline on a small synthetic project. On every push, GitHub Actions runs two jobs on a pinned Ubuntu 24.04 runner:

1. **test:** installs the pinned environment in strict mode, runs all tests and checks the committed notebooks;
2. **docker:** validates the Compose file, builds both images, and runs smoke checks on them.

**Independent SQL checks.** The pipeline also writes a SQLite database. The eight cross-check queries start from row-level jobs, category predictions, human labels and recommender rankings rather than from pre-calculated summary results. They recompute selected results, including the time window, monthly and weekly volumes, category and country shares, country medians, label accuracy, and the recommender's nDCG@5 and Precision@5. Notebook 08 compares every value with the pipeline. Counts match exactly, and decimals match within the 6-decimal rounding of the stored tables. SQL reproduces selected aggregations and evaluation metrics; it does not re-verify the whole project, because the cleaned fields, the categories and the rankings come from Python.

**Docker deployment.** Two services, each with its own Dockerfile, run under Docker Compose:

- **Nginx** (web server) is the only service with a public port (8080) and passes requests to the application;
- **Gunicorn + Flask** (application server) runs one worker with four threads, because each worker process would hold its own copy of the large search index.

The application image holds code and the pinned environment only. The verified outputs are mounted read-only, so the website cannot change them. Nginx starts only after the application passes its health check. The application container runs as a non-root user; Nginx uses the standard image, whose worker processes run as the unprivileged `nginx` user. A separate on-demand `pipeline` service reuses the application image to rebuild all outputs inside Linux.

**Cross-platform check.** I run the main build on Windows and also rebuild it inside the Linux Docker container. The compared outputs match byte-for-byte except `label_evaluation_items.csv`, `pay_prediction.csv` and the run manifest. The first two differ only in small floating-point values, such as classifier probabilities in the sixth decimal place and a pay-prediction median error of $8.399 versus $8.398. The manifest changes because it records the new hashes. Category counts, labels and every reported result stay the same.

**Evidence:** `src/job_market/`, `config/pipeline.toml`, `data/processed/run_manifest.json`, `tests/`, `.github/workflows/ci.yml`, `sql/`, Notebook 08, `docker/`, `docker-compose.yml`, `docs/decisions.md`.

## 13. Tools and technology choices

| Tool | Where I use it |
|---|---|
| Python, Pandas | The whole pipeline and the notebooks |
| SQL (SQLite) | A row-level database and eight cross-check queries (Notebook 08) |
| scikit-learn | TF-IDF features, the category classifier (logistic regression), the pay model (ridge regression) and the recommender's TF-IDF matching |
| SciPy, NumPy | Statistical tests, regressions and forecasting calculations |
| Matplotlib | Static charts in the notebooks and in this report |
| Plotly | The interactive country map and every dashboard chart, served offline |
| Flask | The recommendation page, the JSON API and the dashboard |
| Gunicorn, Nginx | Application server and web server in the deployment |
| Docker, Docker Compose | Packaging and running the services |
| GitHub Actions | Tests, notebook checks and Docker builds on every push |

**Why no TensorFlow.** TensorFlow is not used because the available data and project tasks do not require a deep-learning model. The selected statistical and scikit-learn methods are lighter, easier to interpret and directly validated on the available data. The hybrid TF-IDF recommender reaches nDCG@5 of 0.985 in the blinded relevance evaluation, so adding a heavier neural model is not justified by the project evidence.

Seaborn is also not needed: Matplotlib and Plotly cover every chart.

## 14. Limitations

I report each task's limits in its own section. Here they are in one place.

**The data**

- **Titles only.** There are no job descriptions, skills lists or final contract values, so every result describes what clients write in short titles and offer in the posting.
- **A short window.** The reliable history is 37 days. Trends are short-term shifts, and forecasts reach 14 days at most.
- **Unknown collection process.** The source does not describe how the postings are collected. Days outside the window are incomplete, and three days inside it have small gaps.
- **Missing pay.** About 27% of hourly jobs state no rate, and pay results describe only jobs that state pay.
- **No remote field.** The data cannot measure the share of remote jobs or a shift between office and remote work.
- **Old postings.** The jobs are from early 2024, so links may now point to closed jobs.

**The methods**

- **Categories.** The categories agree with blind human labels for 68.9% of titles, and Software & IT, AI & ML, Engineering and Admin are likely to be understated. Every category result carries this uncertainty.
- **One annotator.** I label all category and relevance sets myself. A second independent annotator would allow an agreement check between people.
- **Associations, not causes.** Pay associations and observed trends do not establish what causes the differences.
- **Small recommender evaluation.** Twelve profiles and one judge, with most judged titles relevant, cannot separate close methods with high confidence.
- **One final forecast week.** The reserved final evaluation covers 7 days, and the total forecast does not beat the seasonal baseline there. The second-week range relies on a square-root-of-horizon assumption.

**What more data would allow**

- Job descriptions and skills lists would allow better categories, skill-level pay analysis and richer recommendations.
- A longer history, ideally more than a year, would allow real seasonal patterns and longer forecasts.
- A structured remote/on-site field would allow a direct answer to the remote-work question.
- Click or application data would allow a recommender that learns from behaviour, and a fair test of heavier models.

## 15. Conclusion

This project answers all eight tasks from 244,828 Upwork job postings. Time-based analysis uses the reliable 37-day window. It identifies title words linked with offered pay, short-term shifts between job categories, a 14-day demand outlook, differences in offered rates by client country, and the online-hiring signals the data can measure.

It also builds two working tools: a job recommender with an API and web page, whose matching method is selected under a fixed evaluation rule using blind relevance labels, and a dashboard that updates when a new monthly extract is added.

Every result comes from one pipeline that can be rerun from the raw file and is checked by automated tests, notebook claims checks and SQL cross-checks. The main limits are the short time window, titles without job descriptions, a single annotator and the missing remote/on-site field.
