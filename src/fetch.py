# Fetch IT job postings from the ITviec public sitemap.
# Author: Nguyen Vu Truong Phuc
#
# The site publishes a sitemap for crawlers and embeds schema.org JobPosting
# JSON-LD on every job page, so no HTML scraping is needed. Each run appends to
# data/raw/jobs_raw.jsonl and skips URLs already stored, so it can be resumed.

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path

SITEMAP_INDEX = "https://itviec.com/dunggiatminh.xml"
JOBS_SITEMAP_HINT = "jobs_desc_en"
ROBOTS_URL = "https://itviec.com/robots.txt"

UA = (
    "vn-it-job-market/1.0 (student research project; "
    "contact pn849222@gmail.com) python-urllib"
)

RAW_PATH = Path("data/raw/jobs_raw.jsonl")
LD_JSON = re.compile(r"<script type='application/ld\+json'>\s*(\{.*?\})\s*</script>", re.S)
LOC = re.compile(r"<loc>([^<]+)</loc>")


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def check_robots(url):
    """Refuse to fetch anything robots.txt disallows for our user agent.

    RobotFileParser.read() sends its own user agent, which the site blocks; a
    failed read makes the parser disallow everything. Fetching the file with our
    own header and handing the text to parse() avoids that false negative.
    """
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(get(ROBOTS_URL).splitlines())
    return rp.can_fetch(UA, url)


def job_urls():
    """Resolve the sitemap index to the list of individual job page URLs."""
    index = get(SITEMAP_INDEX)
    maps = [u for u in LOC.findall(index) if JOBS_SITEMAP_HINT in u]
    if not maps:
        sys.exit("No job sitemap found in the index; the site layout may have changed.")
    return LOC.findall(get(maps[0]))


def extract_posting(html):
    """Return the JobPosting JSON-LD block from a job page, or None."""
    for block in LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return None


def already_fetched():
    if not RAW_PATH.exists():
        return set()
    done = set()
    with RAW_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                done.add(json.loads(line)["source_url"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="stop after N new jobs (0 = all)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    args = ap.parse_args()

    if not check_robots("https://itviec.com/it-jobs/"):
        sys.exit("robots.txt disallows job pages for this user agent. Stopping.")

    urls = job_urls()
    done = already_fetched()
    todo = [u for u in urls if u not in done]
    if args.limit:
        todo = todo[: args.limit]

    print(f"{len(urls)} jobs in sitemap, {len(done)} already stored, fetching {len(todo)}")
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)

    saved = failed = 0
    with RAW_PATH.open("a", encoding="utf-8") as out:
        for i, url in enumerate(todo, 1):
            try:
                posting = extract_posting(get(url))
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                print(f"  [{i}/{len(todo)}] fetch failed: {type(exc).__name__} {url}")
                failed += 1
                time.sleep(args.delay)
                continue

            if posting is None:
                print(f"  [{i}/{len(todo)}] no JobPosting block: {url}")
                failed += 1
            else:
                posting["source_url"] = url
                posting["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                out.write(json.dumps(posting, ensure_ascii=False) + "\n")
                out.flush()
                saved += 1
                if saved % 25 == 0:
                    print(f"  [{i}/{len(todo)}] {saved} saved")

            time.sleep(args.delay)

    print(f"done: {saved} saved, {failed} failed -> {RAW_PATH}")


if __name__ == "__main__":
    main()
