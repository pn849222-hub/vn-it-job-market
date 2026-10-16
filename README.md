# Vietnam IT Job Market

What Vietnamese employers actually ask for in IT job postings — collected,
cleaned, and analyzed end to end.

Unlike a Kaggle download, this dataset did not exist before: it is built from
live job postings, which means the messy parts (missing salaries, mislabelled
currencies, tags that are not skills) had to be handled rather than assumed away.

A companion repo, [job-market-api](https://github.com/pn849222-hub/job-market-api),
serves this database over an ASP.NET Core REST API.

---

## Headline findings

See [outputs/findings.md](outputs/findings.md) for the full report with charts.

| | Finding |
|---|---|
| 1 | Roughly **two thirds of postings never name a salary**, replacing the figure with a slogan such as "You'll love it" |
| 2 | **English is requested more often than any single technology** — it is a requirement, not a bonus |
| 3 | The market is concentrated in **Ho Chi Minh City**, with Hanoi second and everywhere else marginal |
| 4 | Among postings that do publish a range, senior roles advertise several times what junior roles do |

![Most requested technologies](outputs/top_skills.png)

---

## How it works

```
ITviec sitemap  →  fetch.py  →  jobs_raw.jsonl  →  clean.py  →  jobs.db  →  analyze.py  →  charts + findings.md
```

| Step | Script | What it does |
|------|--------|--------------|
| Collect | `src/fetch.py` | Reads the site's published sitemap, then pulls the schema.org `JobPosting` JSON-LD from each job page |
| Clean | `src/clean.py` | Normalizes skills, parses salaries, infers seniority, writes SQLite |
| Analyze | `src/analyze.py` | Runs the SQL aggregations, renders the charts, writes the report |

### Why the sitemap and not HTML scraping

The job listing pages are rendered in JavaScript, so there is nothing to parse in
the HTML. But every job *detail* page embeds a `JobPosting` JSON-LD block for
search engines, and the site publishes a sitemap listing those pages. That path
is both more reliable than scraping markup and the one the site intends crawlers
to use.

### Collecting responsibly

- `robots.txt` is fetched and checked before anything else; the script exits if
  job pages are disallowed.
- One request every 1.5 seconds, single threaded.
- The user agent identifies the project and a contact address.
- Only job data is stored — no candidate or personal information.
- `data/raw/` is gitignored. This repo ships the code, not a republished copy of
  someone else's listings.

---

## Data problems worth knowing about

Real data arrives broken. These were found and handled:

**The currency field lies.** Every posting reports `"currency": "USD"` in its
JSON-LD, including ones whose text reads `14 – 16 million VND/month` or
`Up To 46Mil (Net)`. Trusting that field would have averaged `14` (million dong)
together with `1500` (dollars). Currency is therefore read from the text, and
everything is converted to USD per month at a documented rate.

**Dong written without a unit.** Some postings write `16.000.000- 21.000.000`
with no currency marker at all. Since no job on this board advertises tens of
thousands of US dollars a month, any figure above a plausibility bound is treated
as dong that was missed.

**Not every tag is a skill.** `Internship Accepted` and `Fresher Accepted` sit in
the same field as `Python` and `Kubernetes`. They describe who may apply, not what
the job needs, so they are excluded from skill demand counts.

**The same technology, spelled several ways.** `PostgreSql`, `Postgres`,
`NodeJS`, `Node js`, `.Net Core` — folded together before counting.

**Languages are filed as skills.** English and Japanese appear alongside
technologies. They are counted separately, otherwise "the most in-demand skill in
Vietnamese IT" is answered with "English" — which is true, but not what the
question means.

---

## Run it yourself

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/fetch.py          # ~17 minutes at the default polite delay
python src/clean.py
python src/analyze.py
```

`src/fetch.py --limit 20` fetches a small sample instead. The script is
resumable: it skips URLs already in `data/raw/jobs_raw.jsonl`, so an interrupted
run can simply be started again.

---

## Querying the data

`data/processed/jobs.db` is plain SQLite — open it with any client.

```sql
-- Which skills appear most often alongside Python?
SELECT other.skill, COUNT(*) AS together
FROM job_skills python
JOIN job_skills other ON other.job_id = python.job_id AND other.skill <> 'Python'
WHERE python.skill = 'Python'
GROUP BY other.skill
ORDER BY together DESC
LIMIT 10;
```

### Schema

**jobs** — one row per posting

| Column | Notes |
|--------|-------|
| `job_id` | the board's own posting id |
| `title`, `company`, `city`, `district` | |
| `seniority` | inferred from the title |
| `employment_type`, `posted_date`, `valid_through` | |
| `months_experience` | pre-bucketed by the source; treat as a band |
| `salary_currency` | detected from the text, not the metadata |
| `salary_min_usd`, `salary_max_usd` | normalized to USD per month |
| `salary_raw` | the original string, kept so every figure is auditable |
| `salary_disclosed` | whether a number was published at all |
| `source_url` | |

**job_skills** — one row per job/skill pair

---

## Limitations

- One job board, so this describes ITviec's listings rather than every IT vacancy
  in Vietnam.
- A snapshot of currently open postings, not a time series.
- Salary figures cover only the minority of employers who publish one, which
  biases them toward companies competing openly on pay.
- Seniority comes from the job title, so vaguely titled postings land in
  "Unspecified".
- VND is converted at one fixed rate, not the rate on each posting's date.

---

## Tech

Python 3 · pandas · matplotlib · SQLite · no scraping framework — the standard
library is enough when the data is already structured.

Built by [Nguyen Vu Truong Phuc](https://github.com/pn849222-hub).
Data belongs to ITviec and the employers who posted it; this repo contains code
and aggregate findings only.
