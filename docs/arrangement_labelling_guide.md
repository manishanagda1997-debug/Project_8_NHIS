# Labelling guide: work-arrangement and time-zone wording in job titles

**Version:** 1.0 · 7 October 2026
**Decision:** D-041. This guide is fixed before any title is labelled.

## What is being measured

Only **explicit wording in the job title**. The question is never "is this job
really remote?" but "does this title say so?". A title that does not mention
the arrangement is "no", even if the job is probably remote. Titles alone
cannot tell how many jobs are actually remote, on-site or bound to a time zone.

Judge each title **on its own**: no rule output, group, count or date is shown,
and none should be looked up. Answer three questions independently. One title
can be "yes" on more than one question.

**Hybrid.** When "hybrid" clearly describes the working arrangement, label
remote/home = yes and on-site = yes. For example, "Business Analyst (Hybrid)"
means both. Uses such as hybrid app, hybrid cloud, hybrid vehicle or hybrid
solar do not describe the working arrangement (no on both). If the meaning is
genuinely unclear, use `unclear`.

Each answer is `yes`, `no` or `unclear`. Use `unclear` only when the title
could reasonably be read either way; do not use it to avoid a decision.

## Question 1: remote or home-working wording

**Yes** when the title explicitly says the work is done remotely, from home or
from anywhere, including a service delivered remotely.

| Title | Answer | Why |
|---|---|---|
| Remote Project Manager | yes | says remote |
| Executive Assistant (Remote) | yes | says remote |
| Work from home data entry | yes | home working |
| Remote IT help with a PC | yes | the service is delivered remotely |
| Hybrid (3 days/wk onsite) Business Analyst | yes | hybrid includes remote days |
| Remote analyst - must reside in Texas | yes | remote, with a residency restriction |
| Remote sensing analysis with Python | no | "remote sensing" is a field, not an arrangement |
| Remote control car repair | no | a device |
| Virtual assistant | no | "virtual" alone is a job title, not an arrangement statement |
| Remote? | unclear | cannot tell what is meant |

## Question 2: on-site requirement wording

**Yes** when the title explicitly requires **physical attendance** at a place:
on site, onsite, in person, in office, attend the office, come to a location.

**A location or residency restriction is not on-site work by itself.** "Must
reside in", "based in", "local to", "locals only" or "relocate" can describe a
fully remote job open only to people in one place. Label it on-site only when
the title also states physical attendance. With an explicit remote statement,
it is `no`; with location wording alone and nothing about attendance, it is
`unclear`.

| Title | Answer | Why |
|---|---|---|
| Onsite technician needed in Dallas | yes | on site |
| In-person event staff | yes | in person |
| Must attend the Austin office three days weekly | yes | physical attendance stated |
| Hybrid (3 days/wk onsite) Business Analyst | yes | on-site days |
| Remote analyst - must reside in Texas | no | remote job with a residency restriction |
| Must be local to Austin | unclear | location stated, attendance not stated |
| UK based accountant | unclear | location stated, attendance not stated |
| Local SEO for a dental clinic | no | "local SEO" is a marketing service |
| Photographer for a wedding in Rome | no | presence is implied, not stated as a requirement |

## Question 3: time-zone requirement

**Yes** when the title requires working in, or being available during, a time
zone or set hours.

| Title | Answer | Why |
|---|---|---|
| Executive Assistant - EST Timezone | yes | working hours in a time zone |
| (PST ONLY) Airbnb response manager | yes | availability in a time zone |
| Trainer for a class in GMT+8 timezone | yes | session hours in a time zone |
| Night shift chat support (US hours) | yes | set hours |
| PST to IMAP migration | no | PST is an Outlook file type here |
| Deadline Sunday AEDT | no | a deadline, not working hours |
| Need it done before 7am EST | no | a deadline |
| Build a UTC-to-EST conversion tool | no | mentions time zones, requires no working hours |

## Tie-breaks

* A time-zone word counts only when it sets **working hours or availability**.
  Naming a time zone for any other reason (a deadline, a conversion tool, a
  file type such as PST) is `no`.
* Words in another language follow the same rules if the meaning is clear;
  otherwise `unclear`.
* A title that is only a company or product name: `no` on all three.
* Do not change a label after the evaluation labels are frozen. A clear typing
  error is fixed only before the freeze.
