# Analyze the cleaned job data and write charts plus a findings report.
# Author: Nguyen Vu Truong Phuc
#
# Every aggregation is a SQL query against data/processed/jobs.db, so the
# numbers in outputs/findings.md can be reproduced in any SQL client.

import sqlite3
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

DB_PATH = Path("data/processed/jobs.db")
OUT_DIR = Path("outputs")
REPORT_PATH = OUT_DIR / "findings.md"

# Palette validated for colour-vision deficiency; one hue per single-series chart.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_SOFT, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"

# Language requirements are tagged as skills. Separating them from technologies
# keeps "the most in-demand skill" from being answered with "English".
LANGUAGE_SKILLS = ("English", "Japanese", "Korean", "Chinese", "Vietnamese")

QUERIES = {
    "top_skills": """
        SELECT s.skill, COUNT(*) AS jobs
        FROM job_skills s
        WHERE s.skill NOT IN ({langs})
        GROUP BY s.skill
        ORDER BY jobs DESC
        LIMIT 20
    """,
    "languages": """
        SELECT s.skill, COUNT(*) AS jobs
        FROM job_skills s
        WHERE s.skill IN ({langs})
        GROUP BY s.skill
        ORDER BY jobs DESC
    """,
    "by_city": """
        SELECT COALESCE(city, 'Not stated') AS city, COUNT(*) AS jobs
        FROM jobs
        GROUP BY city
        ORDER BY jobs DESC
    """,
    "by_seniority": """
        SELECT seniority, COUNT(*) AS jobs,
               ROUND(AVG(salary_disclosed) * 100, 1) AS pct_salary_shown
        FROM jobs
        GROUP BY seniority
        ORDER BY jobs DESC
    """,
    "salary_by_seniority": """
        SELECT seniority,
               COUNT(*)                  AS jobs,
               ROUND(AVG(salary_min_usd))    AS avg_min_usd,
               ROUND(AVG(salary_max_usd))    AS avg_max_usd
        FROM jobs
        WHERE salary_disclosed = 1
        GROUP BY seniority
        HAVING jobs >= 5
        ORDER BY avg_max_usd DESC
    """,
    "disclosure": """
        SELECT COUNT(*) AS jobs,
               SUM(salary_disclosed) AS shown,
               ROUND(AVG(salary_disclosed) * 100, 1) AS pct_shown
        FROM jobs
    """,
    "top_companies": """
        SELECT company, COUNT(*) AS jobs
        FROM jobs
        WHERE company IS NOT NULL
        GROUP BY company
        ORDER BY jobs DESC
        LIMIT 10
    """,
    "top_paying_skills": """
        SELECT s.skill,
               COUNT(*) AS jobs,
               ROUND(AVG((j.salary_min_usd + j.salary_max_usd) / 2.0)) AS avg_usd
        FROM job_skills s
        JOIN jobs j ON j.job_id = s.job_id
        WHERE j.salary_disclosed = 1
          AND s.skill NOT IN ({langs})
        GROUP BY s.skill
        HAVING jobs >= 5
        ORDER BY avg_usd DESC
        LIMIT 12
    """,
}


def style_axes(ax, title, subtitle=None):
    """Recessive grid and axes; the data carries the ink.

    Title and subtitle are offset in points rather than axes fractions, so they
    keep the same gap whatever the figure height.
    """
    ax.annotate(title, xy=(0, 1), xycoords="axes fraction",
                xytext=(0, 32), textcoords="offset points",
                color=INK, fontsize=13, fontweight="bold", va="bottom")
    if subtitle:
        ax.annotate(subtitle, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 14), textcoords="offset points",
                    color=INK_SOFT, fontsize=9.5, va="bottom")
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#d8d7d2")
    ax.tick_params(colors=INK_SOFT, labelsize=9.5, length=0)
    ax.set_axisbelow(True)


def barh(frame, label_col, value_col, title, subtitle, filename, color=BLUE, unit=""):
    """Horizontal bar chart: magnitude comparison, one series, direct labels."""
    frame = frame.iloc[::-1]
    height = max(3.0, 0.34 * len(frame) + 1.6)
    fig, ax = plt.subplots(figsize=(8.6, height), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    ax.barh(frame[label_col], frame[value_col], color=color, height=0.62)
    style_axes(ax, title, subtitle)
    ax.get_xaxis().set_visible(False)

    span = frame[value_col].max()
    for y, value in enumerate(frame[value_col]):
        ax.text(value + span * 0.015, y, f"{value:,.0f}{unit}",
                va="center", color=INK_SOFT, fontsize=9)
    ax.set_xlim(0, span * 1.12)

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT_DIR / filename, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return filename


def salary_range_chart(frame, filename):
    """Dumbbell: the advertised floor and ceiling are two series, so both are
    labelled and a legend is present."""
    frame = frame.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.6, 0.6 * len(frame) + 2.2), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    y = range(len(frame))
    ax.hlines(y, frame["avg_min_usd"], frame["avg_max_usd"],
              color="#d8d7d2", linewidth=2, zorder=1)
    ax.scatter(frame["avg_min_usd"], y, s=90, color=BLUE, zorder=2,
               label="Advertised floor", edgecolor=SURFACE, linewidth=2)
    ax.scatter(frame["avg_max_usd"], y, s=90, color=ORANGE, zorder=2,
               label="Advertised ceiling", edgecolor=SURFACE, linewidth=2)

    ax.set_yticks(list(y))
    ax.set_yticklabels(frame["seniority"])
    style_axes(ax, "Advertised monthly salary by seniority",
               "USD per month, average of the ranges that name a figure")
    ax.grid(axis="x", color="#eceae5", linewidth=1)
    ax.xaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")

    # Labels sit outside their own dot - floor to the left, ceiling to the right -
    # so a narrow range cannot overlap itself and the top row cannot reach the title.
    for i, row in enumerate(frame.itertuples()):
        ax.annotate(f"${row.avg_min_usd:,.0f}", xy=(row.avg_min_usd, i),
                    xytext=(-10, 0), textcoords="offset points",
                    ha="right", va="center", color=INK_SOFT, fontsize=8.5)
        ax.annotate(f"${row.avg_max_usd:,.0f}", xy=(row.avg_max_usd, i),
                    xytext=(10, 0), textcoords="offset points",
                    ha="left", va="center", color=INK_SOFT, fontsize=8.5)

    ax.set_ylim(-0.6, len(frame) - 0.4)
    ax.margins(x=0.14)

    legend = ax.legend(frameon=False, loc="lower right", fontsize=9)
    for text in legend.get_texts():
        text.set_color(INK_SOFT)

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT_DIR / filename, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return filename


def run_queries(con):
    langs = ",".join(f"'{name}'" for name in LANGUAGE_SKILLS)
    return {
        name: pd.read_sql_query(sql.format(langs=langs), con)
        for name, sql in QUERIES.items()
    }


def write_report(results, charts):
    disclosure = results["disclosure"].iloc[0]
    skills = results["top_skills"]
    cities = results["by_city"]
    languages = results["languages"]

    total = int(disclosure["jobs"])
    shown = int(disclosure["shown"] or 0)
    top_city = cities.iloc[0]
    english = languages[languages["skill"] == "English"]["jobs"]
    english_pct = (int(english.iloc[0]) / total * 100) if len(english) else 0

    lines = [
        "# Findings",
        "",
        f"Based on {total} IT job postings collected from the ITviec public "
        "sitemap. Every number below comes from a SQL query in `src/analyze.py`.",
        "",
        "## 1. Most postings do not name a salary",
        "",
        f"Only **{shown} of {total} postings ({disclosure['pct_shown']}%)** publish a "
        "figure. The rest replace the number with a slogan such as \"You'll love it\", "
        "so a candidate cannot compare offers before applying. Any salary figure in "
        "this report therefore describes the minority of employers willing to post one, "
        "not the market as a whole.",
        "",
        "## 2. English is a listed requirement, not a bonus",
        "",
        f"English appears as a required skill on **{english_pct:.0f}%** of postings, "
        "which puts it among the most requested items of any kind - ahead of most "
        "individual technologies.",
        "",
        "## 3. What employers actually ask for",
        "",
        "Top ten requested technologies:",
        "",
        "| # | Skill | Postings | Share |",
        "|---|-------|---------:|------:|",
    ]
    for i, row in enumerate(skills.head(10).itertuples(), 1):
        lines.append(f"| {i} | {row.skill} | {row.jobs} | {row.jobs / total * 100:.1f}% |")

    lines += [
        "",
        "## 4. The market is concentrated in one city",
        "",
        f"**{top_city['city']}** holds {top_city['jobs']} of {total} postings "
        f"({top_city['jobs'] / total * 100:.0f}%).",
        "",
        "| City | Postings |",
        "|------|---------:|",
    ]
    for row in cities.head(6).itertuples():
        lines.append(f"| {row.city} | {row.jobs} |")

    salary = results["salary_by_seniority"]
    if not salary.empty:
        lines += [
            "",
            "## 5. Advertised pay by seniority",
            "",
            "Averages over postings that name a USD range. Groups with fewer than "
            "five such postings are left out.",
            "",
            "| Seniority | Postings | Avg floor | Avg ceiling |",
            "|-----------|---------:|----------:|------------:|",
        ]
        for row in salary.itertuples():
            lines.append(
                f"| {row.seniority} | {row.jobs} | ${row.avg_min_usd:,.0f} | "
                f"${row.avg_max_usd:,.0f} |"
            )

    lines += [
        "",
        "## Charts",
        "",
    ]
    lines += [f"![{name}](./{name})" for name in charts]

    lines += [
        "",
        "## Limitations",
        "",
        "- One job board only, so the figures describe ITviec's listings rather "
        "than every IT vacancy in Vietnam.",
        "- A snapshot of currently open postings, not a time series.",
        "- `monthsOfExperience` arrives pre-bucketed by the source, so it is "
        "reported as a band and not treated as a precise number.",
        "- Seniority is inferred from the job title, so postings with a vague "
        "title fall into \"Unspecified\".",
        "- Salary figures cover only the postings that disclose one, which "
        "biases them toward employers competing openly on pay.",
        "",
    ]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run src/clean.py first.")

    OUT_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    results = run_queries(con)
    con.close()

    charts = [
        barh(results["top_skills"], "skill", "jobs",
             "Most requested technologies",
             "Number of open postings naming each skill",
             "top_skills.png"),
        barh(results["by_city"].head(8), "city", "jobs",
             "Where the jobs are",
             "Open postings by city",
             "by_city.png", color=AQUA),
        barh(results["by_seniority"], "seniority", "jobs",
             "Seniority mix",
             "Inferred from the job title",
             "by_seniority.png", color=ORANGE),
    ]
    if not results["salary_by_seniority"].empty:
        charts.append(salary_range_chart(results["salary_by_seniority"],
                                         "salary_by_seniority.png"))

    write_report(results, charts)

    disclosure = results["disclosure"].iloc[0]
    print(f"jobs analyzed:   {int(disclosure['jobs'])}")
    print(f"salary shown:    {int(disclosure['shown'] or 0)} ({disclosure['pct_shown']}%)")
    print("\ntop skills:")
    print(textwrap.indent(results["top_skills"].head(10).to_string(index=False), "  "))
    print(f"\ncharts: {', '.join(charts)}")
    print(f"report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
