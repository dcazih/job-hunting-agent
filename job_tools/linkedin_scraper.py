import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode

BASE_SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)
JOB_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def build_search_url(keywords, location, start=0):
    """
    Builds the public LinkedIn guest jobs search URL.

    keywords: job search query, e.g. "software engineer"
    location: location string, e.g. "United States", "Albuquerque, New Mexico", "Remote"
    start: pagination offset, usually 0, 25, 50...
    """

    params = {
        "keywords": keywords,
        "location": location,
        "start": start,
    }

    return f"{BASE_SEARCH_URL}?{urlencode(params)}"


def fetch_search_page(keywords, location, start=0):
    url = build_search_url(keywords, location, start)

    response = requests.get(url, headers=HEADERS, timeout=15)

    if response.status_code != 200:
        raise RuntimeError(
            f"Request failed with status {response.status_code}. "
            f"LinkedIn may have blocked the request or changed the endpoint."
        )

    return response.text


def parse_job_cards(html):
    """
    Parses the search results HTML and extracts basic job info.
    """

    soup = BeautifulSoup(html, "html.parser")

    cards = soup.select("li")

    jobs = []

    for card in cards:
        title_el = card.select_one(".base-search-card__title")
        company_el = card.select_one(".base-search-card__subtitle")
        location_el = card.select_one(".job-search-card__location")
        link_el = card.select_one("a.base-card__full-link")
        time_el = card.select_one("time")

        if not title_el or not company_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True)
        location = location_el.get_text(strip=True) if location_el else None
        url = link_el.get("href")
        listed_at = time_el.get("datetime") if time_el else None

        job_id = extract_job_id(url)

        jobs.append(
            {
                "job_id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "listed_at": listed_at,
                "url": url,
            }
        )

    return jobs


def extract_job_id(url):
    """
    LinkedIn public job URLs often end with something like:
    software-engineer-1234567890

    This function grabs the final numeric ID if present.
    """

    if not url:
        return None

    clean_url = url.split("?")[0]
    last_chunk = clean_url.rstrip("/").split("-")[-1]

    return last_chunk if last_chunk.isdigit() else None


def fetch_job_description(job_id):
    """
    Fetches a public job description page from the guest job endpoint.
    """

    if not job_id:
        return None

    url = JOB_DETAIL_URL.format(job_id)

    response = requests.get(url, headers=HEADERS, timeout=15)

    if response.status_code != 200:
        print(f"Could not fetch description for {job_id}: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    description_el = soup.select_one(".show-more-less-html__markup")

    if not description_el:
        return None

    return description_el.get_text(separator="\n", strip=True)


def scrape_jobs(
    keywords="software engineering",
    location="United States",
    pages=1,
    is_canceled=None,
    on_job_found=None,
):
    """
    Scrapes multiple result pages.
    pages=2 means offsets 0 and 25.
    """

    all_jobs = []

    for page in range(pages):
        if callable(is_canceled) and is_canceled():
            raise RuntimeError("Search was canceled by user.")
        start = page * 25
        print(f"Fetching page {page + 1}, start={start}...")

        # Get jobs on the page
        html = fetch_search_page(keywords, location, start=start)
        jobs = parse_job_cards(html)
        print(f"Found {len(jobs)} jobs on this page.")

        # Get descriptions of found jobs
        for job_index, job in enumerate(jobs, start=1):
            if callable(is_canceled) and is_canceled():
                raise RuntimeError("Search was canceled by user.")
            print(f"Fetching description: {job['title']} at {job['company']}")

            if callable(on_job_found):
                on_job_found(
                    job=job,
                    page_index=page + 1,
                    page_count=pages,
                    job_index=len(all_jobs) + job_index,
                    page_job_count=len(jobs),
                )

            job["description"] = fetch_job_description(job["job_id"])

            sleep_secs = random.uniform(0.6, 1.4)
            if callable(is_canceled):
                slept = 0.0
                while slept < sleep_secs:
                    if is_canceled():
                        raise RuntimeError("Search was canceled by user.")
                    step = min(0.25, sleep_secs - slept)
                    time.sleep(step)
                    slept += step
            else:
                time.sleep(sleep_secs)

        all_jobs.extend(jobs)

        sleep_secs = random.uniform(1, 2)  # Prevents endpoint hammering.
        if callable(is_canceled):
            slept = 0.0
            while slept < sleep_secs:
                if is_canceled():
                    raise RuntimeError("Search was canceled by user.")
                step = min(0.25, sleep_secs - slept)
                time.sleep(step)
                slept += step
        else:
            time.sleep(sleep_secs)

    # Deduplicate by job_id or URL
    seen = set()
    unique_jobs = []

    for job in all_jobs:
        key = job["job_id"] or job["url"]

        if key in seen:
            continue

        seen.add(key)
        unique_jobs.append(job)

    return unique_jobs


if __name__ == "__main__":
    import pandas as pd

    jobs = scrape_jobs(
        keywords="software engineer",
        location="United States",
        pages=1,
    )

    df = pd.DataFrame(jobs)

    print("\nTop results:")
    print(df.head(10).to_string(index=False))

    df.to_csv("linkedin_software_engineering_jobs.csv", index=False)

    print(f"\nSaved {len(df)} jobs to linkedin_software_engineering_jobs.csv")
