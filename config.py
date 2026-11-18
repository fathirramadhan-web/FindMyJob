from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
SECRETS_DIR = BASE / "secrets"
SESSION_DIR = BASE / "session"
ACCOUNT_FILE = SECRETS_DIR / "account.txt"
CV_DEFAULT = DATA_DIR / "cv.pdf"
CSV_FILE = DATA_DIR / "jobs-pipeline.csv"
SHEET_FILE = DATA_DIR / "jobs-pipeline.xlsx"
PROFILE_DIR = SESSION_DIR / "browser_profile"

import os
GSHEET_SHEET_URL = os.environ.get(
    "JOBBOT_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/<SHEET_ID_ANDA>/edit#gid=0",
)

SITE_ACCOUNTS = {

    "indeed":    {"account": SECRETS_DIR / "account2.txt", "profile": PROFILE_DIR / "account2"},
    "jobstreet": {"account": SECRETS_DIR / "account2.txt", "profile": PROFILE_DIR / "account2"},
    "glints":    {"account": SECRETS_DIR / "account2.txt", "profile": PROFILE_DIR / "account2"},
    "linkedin":  {"account": ACCOUNT_FILE,          "profile": PROFILE_DIR},
    "glassdoor": {"account": ACCOUNT_FILE,          "profile": PROFILE_DIR},
}
DEFAULT_SITE = "indeed"

def site_auth(site: str) -> dict:
    return SITE_ACCOUNTS.get(site, {"account": ACCOUNT_FILE, "profile": PROFILE_DIR})

LOCATIONS = ["jakarta", "bandung", "cirebon", "yogyakarta", "surabaya", "remote"]
MAX_PAGES = 1
MAX_QUERIES = 5
MAX_SEARCHES = 6
DESC_LIMIT = 8

SITES = {
    "indeed": {
        "fetch": "https://id.indeed.com/jobs?q={query}&l={location}",
        "login_url": "https://id.indeed.com/",
        "desc_sel": ".simple-job-description-html, .react-native-html-content, #jobDescriptionText",
        "card_sel": "div.tapItem.result, .result, [data-jk]",
        "fields": {
            "title": "a.jcs-JobTitle, .jobTitle span, .jobTitle, h2 a",
            "company": "[data-testid='company-name'], .companyName",
            "location": "[data-testid='text-location'], .companyLocation",
            "link": "a.jcs-JobTitle, .jobTitle a, h2 a",
        },
    },
    "linkedin": {

        "guest_url": ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                      "?keywords={query}&location={location}&start={start}"),
        "per_page": 10,
        "fetch": "https://www.linkedin.com/jobs/search?keywords={query}&location={location}",
        "login_url": "https://www.linkedin.com/login",
        "desc_sel": None,
        "card_sel": "li",
        "fields": {
            "title": ".base-search-card__title",
            "company": ".base-search-card__subtitle",
            "location": ".job-search-card__location",
            "link": "a.base-card__full-link",
        },
    },
    "jobstreet": {
        "fetch": "https://id.jobstreet.com/id/job-search/{query}-jobs-in-{location}/",
        "login_url": "https://id.jobstreet.com/",
        "desc_sel": "[data-automation='jobAdDetails'], [data-automation='jobDescription']",
        "salary_sel": "[data-automation='job-detail-salary']",
        "card_sel": "article[data-automation='normalJob'], [data-testid='job-card']",
        "fields": {
            "title": "[data-automation='jobTitle']",
            "company": "[data-automation='jobCompany']",
            "location": "[data-automation='jobLocation']",
            "link": "a[data-automation='job-list-view-job-link'], a[data-testid='job-list-view-job-link']",
        },
    },
    "glints": {

        "fetch": "https://glints.com/id/opportunities/jobs/explore?keyword={query}&country=ID&locationName={location}",
        "login_url": "https://glints.com/id",
        "scroll": 3,
        "card_sel": "div[role='article'][aria-label^='Job: ']",

        "aria_parse": True,
        "fields": {
            "title": "h2 a",
            "link": "h2 a[href]",
            "salary": "[class*='SalaryWrapper']",
        },
        "desc_sel": "[class*='JobDescriptionsc__DescriptionContainer'], [class*='Opportunitysc__JobDescriptionContainer']",
        "salary_sel": "[class*='BasicSalary'], [class*='SalaryJobOverview']",
    },
    "glassdoor": {
        "fetch": "https://www.glassdoor.co.id/Job/{query}-jobs-SRCH_KN0.htm?locKeyword={location}",
        "login_url": "https://www.glassdoor.co.id/",
        "desc_sel": ".jobDescriptionContent, #JobDescriptionContainer",
        "card_sel": "[data-job-id]",
        "fields": {
            "title": ".jobTitle a, a[data-test='job-link']",
            "company": ".employerName",
            "location": ".location",
            "link": "a.jobLink, a.jobTitle",
        },
    },
}

DEFAULT_SITE = "indeed"

BOT_PATTERNS = ["unusual traffic", "captcha", "verify you are human", "access denied",
                "enable javascript", "tunggu sebentar"]
