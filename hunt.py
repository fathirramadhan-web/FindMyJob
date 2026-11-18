import random
import re
import time
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

import config
import gm

BOT_PATTERNS = ["unusual traffic", "captcha", "verify you are human",
                "access denied", "robot check", "tunggu sebentar"]

_ARIA = re.compile(r"Job:\s*(?P<title>.*?),\s*Company:\s*(?P<company>.*?),\s*Location:\s*(?P<location>.*)$")

def _looks_blocked(page) -> bool:
    try:
        low = page.content().lower()
    except Exception:
        return False
    return any(p in low for p in BOT_PATTERNS)

def _manual_pause(page, reason: str):
    print(f"[!] {reason}. Selesaikan manual di browser, lalu tekan Enter di sini.")
    try:
        input("> ")
    except EOFError:
        print("[!] stdin tertutup (mode cron) — dilewati, scrape dilanjutkan apa adanya")
    page.wait_for_timeout(1000)

def _txt(el) -> str:
    return re.sub(r"\s+", " ", el.inner_text()).strip() if el else ""

def _abs_url(page, href: str) -> str:
    from urllib.parse import urljoin
    return urljoin(page.url, href) if href else ""

def _scrape_guest(page, ctx, site: str, query: str, location: str) -> list[dict]:
    cfg = config.SITES[site]
    jobs, seen = [], set()
    for page_no in range(1, config.MAX_PAGES + 1):
        start = (page_no - 1) * cfg.get("per_page", 10)
        url = cfg["guest_url"].format(query=quote_plus(query),
                                    location=quote_plus(location), start=start)
        try:
            resp = ctx.request.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        except Exception as e:
            print(f"[!] request gagal: {str(e)[:80]}")
            break
        if resp.status != 200 or "base-search-card" not in resp.text():
            if resp.status != 200:
                print(f"[!] status {resp.status} pada halaman {page_no}")
            break
        page.set_content(resp.text(), wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        n_before = len(jobs)
        cards = page.locator(cfg["card_sel"])
        for i in range(cards.count()):
            c = cards.nth(i)
            f = cfg["fields"]
            def _g(sel):
                try:
                    loc = c.locator(sel).first
                    return _txt(loc) if loc.count() else None
                except Exception:
                    return None
            title = _g(f["title"]) or ""
            href = None
            try:
                l0 = c.locator(f["link"]).first
                if l0.count():
                    href = l0.get_attribute("href")
            except Exception:
                pass
            if not title or not href:
                continue
            link = _abs_url(page, href)
            key = link.split("?")[0].split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            jobs.append({"title": title, "company": _g(f["company"]) or "",
                        "location": _g(f["location"]) or location,
                        "link": link, "source": site, "description": ""})
        if len(jobs) == n_before:
            break
    return jobs

def scrape_listing(page, site: str, query: str, location: str) -> list[dict]:
    cfg = config.SITES[site]
    url = cfg["fetch"].format(query=quote_plus(query), location=quote_plus(location))
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500 + random.randint(0, 3000))

    if _looks_blocked(page):
        _manual_pause(page, "Kena anti-bot/captcha")

    for _ in range(int(cfg.get("scroll", 0))):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(1500 + random.randint(0, 1000))

    jobs, seen = [], set()
    for page_no in range(1, config.MAX_PAGES + 1):
        cards = page.locator(cfg["card_sel"])
        n = cards.count()
        if n == 0:
            _manual_pause(page, f"Halaman {page_no}: 0 kartu lowongan (mungkin layout beda/harus login)")
            cards = page.locator(cfg["card_sel"])
            n = cards.count()
            if n == 0:
                break

        for i in range(n):
            c = cards.nth(i)
            f = cfg["fields"]
            def _g(sel, first_only=True):
                try:
                    loc = c.locator(sel) if first_only else c.locator(sel)
                    loc = loc.first if first_only else loc.nth(0)
                    if loc.count():
                        return _txt(loc)
                except Exception:
                    pass
                return None
            title = _g(f["title"]) if f.get("title") else _txt(c)
            company = _g(f["company"]) if f.get("company") else ""
            loc = _g(f["location"]) if f.get("location") else ""
            if cfg.get("aria_parse"):

                try:
                    m = _ARIA.match(c.get_attribute("aria-label") or "")
                except Exception:
                    m = None
                if m:
                    title = title or m["title"]
                    company = company or m["company"]
                    loc = loc or m["location"]
            href = None
            if f.get("link"):
                try:
                    l0 = c.locator(f["link"]).first
                    if l0.count():
                        href = l0.get_attribute("href")
                except Exception:
                    href = None
            if not title or not href:
                continue
            link = _abs_url(page, href)
            salary = _g(f["salary"]) if f.get("salary") else ""
            if salary and any(k in salary.lower() for k in ("tidak menampilkan", "tidak mengungkap")):
                salary = ""
            key = link.split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            jobs.append({"title": title, "company": company, "location": loc or location,
                        "link": link, "source": site, "description": "", "salary": salary or ""})

        nxt = page.locator("a[aria-label='Next'], a[aria-label='Berikutnya'], .pn, li[data-automation='page-next'] a").first
        if nxt.count() and "disabled" not in (nxt.get_attribute("class") or ""):
            try:
                time.sleep(random.uniform(2.0, 5.0))
                nxt.click()
                page.wait_for_timeout(2500 + random.randint(0, 3000))
                if _looks_blocked(page):
                    _manual_pause(page, "Kena anti-bot setelah pindah halaman")
            except Exception:
                break
        else:
            break
    return jobs

def fetch_description(page, site: str, link: str) -> str:
    return fetch_details(page, site, link).get("description", "")

def fetch_details(page, site: str, link: str) -> dict:
    cfg = config.SITES[site]
    out = {"description": "", "salary": ""}
    try:
        page.goto(link, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1800)
    except Exception:
        return out
    for key, sel_key in (("description", "desc_sel"), ("salary", "salary_sel")):
        sel = cfg.get(sel_key)
        if not sel:
            continue
        try:
            el = page.locator(sel).first
            if el.count():
                out[key] = _txt(el)
        except Exception:
            pass
    return out

def enrich(jobs: list[dict], site: str, limit: int = 0) -> None:
    if not jobs or not config.SITES[site].get("desc_sel"):
        return
    subset = jobs[:limit] if limit else jobs
    with sync_playwright() as pw:
        ctx = gm.launch_site(pw, site)
        page = ctx.new_page()
        try:
            for j in subset:
                det = fetch_details(page, site, j["link"])
                j["description"] = det["description"]
                j["salary"] = det["salary"]
        finally:
            ctx.close()

def search(site: str, query: str, location: str, with_desc: bool = False) -> list[dict]:
    cfg = config.SITES.get(site)
    if not cfg:
        raise ValueError(f"Situs tidak dikenal: {site}. Pilihan: {list(config.SITES)}")
    with sync_playwright() as pw:
        ctx = gm.launch_site(pw, site)
        if cfg.get("guest_url"):

            page = ctx.new_page()
            try:
                jobs = _scrape_guest(page, ctx, site, query, location)
            finally:
                ctx.close()
            return jobs
        page = ctx.new_page()
        try:
            jobs = scrape_listing(page, site, query, location)
            if with_desc:
                for j in jobs:
                    det = fetch_details(page, site, j["link"])
                    j["description"], j["salary"] = det["description"], det["salary"]
        finally:
            ctx.close()
    return jobs

if __name__ == "__main__":
    m = _ARIA.match("Job: Full Stack Dev, Company: PT Contoh, Location: Kab. Bekasi , Jawa Barat")
    assert m and m["company"] == "PT Contoh" and m["title"] == "Full Stack Dev"
    out = search(config.DEFAULT_SITE, "developer", config.LOCATIONS[0])
    print(f"[OK] {len(out)} lowongan dari {config.DEFAULT_SITE}")
    for j in out[:5]:
        print(" -", j["title"], "|", j["company"], "|", j["link"])
