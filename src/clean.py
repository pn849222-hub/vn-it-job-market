# Clean the raw JobPosting records into a tidy SQLite database.
# Author: Nguyen Vu Truong Phuc
#
# Reads data/raw/jobs_raw.jsonl and writes data/processed/jobs.db with two
# tables: jobs (one row per posting) and job_skills (one row per job/skill
# pair, so skill demand can be counted with SQL).

import json
import re
import sqlite3
from pathlib import Path

RAW_PATH = Path("data/raw/jobs_raw.jsonl")
DB_PATH = Path("data/processed/jobs.db")
CSV_PATH = Path("data/processed/jobs.csv")

# The site writes the same technology several ways ("PostgreSql", "Postgresql").
# Counting skill demand means folding those together first.
SKILL_ALIASES = {
    "postgresql": "PostgreSQL",
    "postgresql ": "PostgreSQL",
    "postgres": "PostgreSQL",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "node.js": "Node.js",
    "reactjs": "React",
    "react js": "React",
    "react native": "React Native",
    "vuejs": "Vue.js",
    "vue js": "Vue.js",
    "angularjs": "Angular",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "golang": "Go",
    "go": "Go",
    "c#": "C#",
    ".net": ".NET",
    "asp.net": ".NET",
    "dotnet": ".NET",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "sql": "SQL",
    "mysql": "MySQL",
    "mssql": "SQL Server",
    "sql server": "SQL Server",
    "nosql": "NoSQL",
    "mongodb": "MongoDB",
    "html5": "HTML/CSS",
    "html": "HTML/CSS",
    "css": "HTML/CSS",
    "qa qc": "QA/QC",
    "qa/qc": "QA/QC",
    "english": "English",
    "japanese": "Japanese",
    "oop": "OOP",
    "ai": "AI",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "devops": "DevOps",
    "linux": "Linux",
    "docker": "Docker",
    "python": "Python",
    "java": "Java",
    "php": "PHP",
}

# Seniority is not a field on the posting, so it is read off the title.
# Order matters: the first pattern that matches wins, most senior first.
SENIORITY_PATTERNS = [
    ("Manager/Head", r"\b(manager|head|director|cto|chief)\b"),
    ("Lead/Principal", r"\b(lead|principal|architect|expert)\b"),
    ("Senior", r"\b(senior|sr\.?|experienced)\b"),
    ("Middle", r"\b(middle|mid|intermediate)\b"),
    ("Junior", r"\b(junior|jr\.?)\b"),
    ("Intern/Fresher", r"\b(intern|internship|fresher|trainee|graduate)\b"),
]

SALARY_RANGE = re.compile(r"([\d,.]+)\s*(?:-|to|–|—)\s*([\d,.]+)")
SALARY_SINGLE = re.compile(r"(?:up\s*to|from|upto)?\s*([\d,.]+)")

# The JSON-LD currency field says USD on every posting, including ones whose text
# reads "14 - 16 million VND/month" or "Up To 46Mil (Net)". Trusting that field
# would average 14 (million dong) together with 1500 (dollars), so the currency is
# read off the text instead and everything is normalized to USD.
VND_MARKERS = re.compile(r"vnd|đồng|dong|triệu|tr/|/tr\b|\bvnđ\b", re.I)
MILLION_SUFFIX = re.compile(r"\d\s*(?:m|mil|mill|million|tr)\b", re.I)

# Mid-market rate in mid-2026, used only to put VND and USD postings on one axis.
# A single documented constant keeps the conversion visible and easy to update.
VND_PER_USD = 26_300

# Some postings write dong with dot separators and no unit at all
# ("16.000.000- 21.000.000"), which no marker catches. No IT job on this board
# advertises tens of thousands of dollars a month, so a figure above this bound
# is dong that was missed, and gets converted rather than believed.
USD_PLAUSIBLE_MAX = 20_000

# Tags the board files alongside real skills. They describe who may apply, not
# what the job requires, so they would distort any "most requested skill" count.
NON_SKILL_TAGS = {
    "internship accepted",
    "fresher accepted",
    "new graduate accepted",
}


def normalize_skill(raw):
    name = raw.strip()
    if not name or name.lower() in NON_SKILL_TAGS:
        return None
    return SKILL_ALIASES.get(name.lower(), name)


def parse_number(text):
    """Read a figure written for people: '1,500', '2.500', '46', '1.5'."""
    text = text.strip().rstrip(".")
    if "," in text and "." in text:          # '1,500.50' -> thousands then decimal
        text = text.replace(",", "")
    elif text.count(",") >= 1:               # '1,500' / '1,500,000'
        text = text.replace(",", "")
    elif text.count(".") > 1:                # '2.500.000' -> dots as thousands
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def detect_currency(text):
    """VND when the text names dong or uses a millions suffix, else USD."""
    if VND_MARKERS.search(text) or MILLION_SUFFIX.search(text):
        return "VND"
    return "USD"


def to_usd(amount, currency, text):
    """Normalize one figure to USD per month."""
    if amount is None:
        return None
    if currency != "VND":
        return amount
    # "46Mil" and "16 million" are written in millions; "26,000,000" is not.
    if MILLION_SUFFIX.search(text) and amount < 1_000:
        amount *= 1_000_000
    return round(amount / VND_PER_USD, 2)


def parse_salary(base_salary):
    """Return (currency, min_usd, max_usd, raw_text, disclosed).

    Most postings hide the figure behind a slogan such as "You'll love it", so
    `disclosed` records whether a number was published at all — that rate is
    itself one of the findings.
    """
    if isinstance(base_salary, dict):
        value = base_salary.get("value")
        raw = value.get("value") if isinstance(value, dict) else value
    else:
        raw = base_salary
    if raw is None:
        return None, None, None, None, False

    text = str(raw).strip()
    if not re.search(r"\d", text):
        return None, None, None, text, False

    currency = detect_currency(text)

    match = SALARY_RANGE.search(text)
    if match:
        low = to_usd(parse_number(match.group(1)), currency, text)
        high = to_usd(parse_number(match.group(2)), currency, text)
    else:
        match = SALARY_SINGLE.search(text)
        single = to_usd(parse_number(match.group(1)), currency, text) if match else None
        low = high = single

    if low is None:
        return currency, None, None, text, False

    if currency == "USD" and low > USD_PLAUSIBLE_MAX:
        currency = "VND"
        low = round(low / VND_PER_USD, 2)
        high = round(high / VND_PER_USD, 2) if high is not None else None

    if high is not None and high < low:
        low, high = high, low
    return currency, low, high, text, True


def seniority(title):
    low = (title or "").lower()
    for label, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, low):
            return label
    return "Unspecified"


def first_location(posting):
    locations = posting.get("jobLocation") or []
    if not isinstance(locations, list) or not locations:
        return None, None
    address = locations[0].get("address") if isinstance(locations[0], dict) else None
    if not isinstance(address, dict):
        return None, None
    return address.get("addressRegion"), address.get("addressLocality")


def months_experience(posting):
    requirements = posting.get("experienceRequirements")
    if isinstance(requirements, dict):
        return requirements.get("monthsOfExperience")
    return None


def company_name(posting):
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        return org.get("name")
    if isinstance(org, str):
        return org
    return None


def job_id(url):
    """Use the full URL slug as the identifier.

    The trailing number looks like a posting id but is not unique: three
    unrelated postings share "1922", for example. Keying on it silently dropped
    around fifty real jobs, so the whole slug is used instead.
    """
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


def load_rows():
    jobs, skills = [], []
    seen = set()

    with RAW_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            posting = json.loads(line)

            url = posting.get("source_url")
            jid = job_id(url)
            if jid in seen:
                continue
            seen.add(jid)

            region, district = first_location(posting)
            currency, low, high, salary_text, disclosed = parse_salary(
                posting.get("baseSalary")
            )
            title = posting.get("title")

            jobs.append(
                {
                    "job_id": jid,
                    "title": title,
                    "company": company_name(posting),
                    "city": region,
                    "district": district,
                    "seniority": seniority(title),
                    "employment_type": posting.get("employmentType"),
                    "posted_date": posting.get("datePosted"),
                    "valid_through": posting.get("validThrough"),
                    "months_experience": months_experience(posting),
                    "salary_currency": currency,
                    "salary_min_usd": low,
                    "salary_max_usd": high,
                    "salary_raw": salary_text,
                    "salary_disclosed": int(disclosed),
                    "source_url": url,
                }
            )

            raw_skills = posting.get("skills") or ""
            for part in str(raw_skills).split(","):
                name = normalize_skill(part)
                if name:
                    skills.append({"job_id": jid, "skill": name})

    return jobs, skills


def write_db(jobs, skills):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE jobs (
            job_id            TEXT PRIMARY KEY,
            title             TEXT,
            company           TEXT,
            city              TEXT,
            district          TEXT,
            seniority         TEXT,
            employment_type   TEXT,
            posted_date       TEXT,
            valid_through     TEXT,
            months_experience INTEGER,
            salary_currency   TEXT,   -- detected from the text, not the metadata
            salary_min_usd    REAL,   -- VND postings converted at VND_PER_USD
            salary_max_usd    REAL,
            salary_raw        TEXT,   -- original string, kept so figures are auditable
            salary_disclosed  INTEGER,
            source_url        TEXT
        );
        CREATE TABLE job_skills (
            job_id TEXT REFERENCES jobs(job_id),
            skill  TEXT,
            PRIMARY KEY (job_id, skill)
        );
        CREATE INDEX idx_skill ON job_skills(skill);
        """
    )
    con.executemany(
        "INSERT INTO jobs VALUES (:job_id,:title,:company,:city,:district,:seniority,"
        ":employment_type,:posted_date,:valid_through,:months_experience,"
        ":salary_currency,:salary_min_usd,:salary_max_usd,:salary_raw,"
        ":salary_disclosed,:source_url)",
        jobs,
    )
    con.executemany(
        "INSERT OR IGNORE INTO job_skills VALUES (:job_id,:skill)", skills
    )
    con.commit()
    con.close()


def main():
    if not RAW_PATH.exists():
        raise SystemExit(f"{RAW_PATH} not found. Run src/fetch.py first.")

    jobs, skills = load_rows()
    write_db(jobs, skills)

    import pandas as pd

    frame = pd.DataFrame(jobs)
    frame.to_csv(CSV_PATH, index=False)

    disclosed = frame["salary_disclosed"].sum()
    print(f"jobs:            {len(jobs)}")
    print(f"skill mentions:  {len(skills)} ({frame['job_id'].nunique()} jobs)")
    print(f"salary shown:    {disclosed} ({disclosed / len(jobs):.0%})")
    print(f"cities:          {frame['city'].nunique()}")
    print(f"companies:       {frame['company'].nunique()}")
    print(f"wrote {DB_PATH} and {CSV_PATH}")


if __name__ == "__main__":
    main()
