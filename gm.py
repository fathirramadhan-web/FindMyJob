import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

import config

def _read_account(path: Path):
    if not path.exists():
        raise FileNotFoundError(
            f"{path} tidak ada. Buat file berisi dua baris:\n  email=alamat@gmail.com\n  password=secret")
    text = path.read_text(encoding="utf-8")
    creds = dict(re.findall(r"^\s*(\w+)\s*=\s*(.+?)\s*$", text, re.M))
    for k in ("email", "password"):
        if k not in creds or not creds[k]:
            raise ValueError(f"Key '{k}' tidak ditemukan di {path}")
    return creds["email"], creds["password"]

def launch(pw, profile: Path | None = None, **kw):
    profile = profile or config.PROFILE_DIR
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=False,
        viewport=None,
        args=["--disable-blink-features=AutomationControlled"],
        **kw,
    )

def login_google(account_file: Path | None = None, profile: Path | None = None, verbose=True, pw=None):
    account_file = account_file or config.ACCOUNT_FILE
    email, password = _read_account(account_file)
    if pw is not None:
        _login_google_with(pw, account_file, profile, email, password, verbose)
        return
    with sync_playwright() as p:
        _login_google_with(p, account_file, profile, email, password, verbose)

def _login_google_with(pw, account_file, profile, email, password, verbose=True):
    ctx = launch(pw, profile=profile)
    page = ctx.new_page()
    page.goto("https://accounts.google.com/signin", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    email_input = page.locator("#identifierId")
    if "myaccount.google" in page.url:
        if verbose:
            print("[OK] Sudah login (session aktif).")
        ctx.close()
        return
    if not email_input.count():
        raise RuntimeError("Halaman login Google tak terdeteksi (form email tak muncul).")
    if verbose:
        print("[..] Belum login, mengisi email ...")
    page.fill("#identifierId", email)
    page.click("#identifierNext")

    pw_field = None
    for _ in range(30):
        page.wait_for_timeout(500)

        if "/challenge/" in page.url or "verify" in page.title().lower():
            if verbose:
                print("[..] Kena challenge Google (captcha/verifikasi).")
                print("    SELESAIKAN MANUAL DI BROWSER yang terbuka. Script menunggu 3 menit ...")
            for _ in range(180):
                page.wait_for_timeout(1000)
                if "myaccount.google" in page.url:
                    if verbose:
                        print("[OK] Challenge selesai, login sukses.")
                    ctx.close()
                    return
            raise RuntimeError("Challenge belum diselesaikan (timeout 3 menit).")
        for sel in ("input[name='Passwd']:visible", "input[type=password]:not([aria-hidden='true']):visible",
                    "input[type=password]:visible"):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    pw_field = loc
                    break
            except Exception:
                pass
        if pw_field:
            break
    if not pw_field:
        raise RuntimeError("Field password Google tidak muncul (mungkin 2FA/alur lain).")

    if verbose:
        print("[..] Mengisi password ...")
    pw_field.fill(password)
    page.click("#passwordNext")

    for _ in range(120):
        url = page.url
        if "myaccount.google" in url or "gds.google" in url:
            if verbose:
                print("[OK] Login sukses.")
            break
        try:
            low = page.content().lower()
        except Exception:
            low = ""
        if any(s in low for s in ("2-step", "two-step", "challenge")):
            if verbose:
                print("[..] Kena 2FA/challenge. Selesaikan manual di browser ya.")
        page.wait_for_timeout(1000)
    else:
        if verbose:
            print("[!] Login belum terdeteksi; cek browser secara manual.")
    ctx.close()

def launch_site(pw, site: str, **kw):
    profile = config.site_auth(site)["profile"]
    profile.mkdir(parents=True, exist_ok=True)
    return launch(pw, profile=profile, **kw)

def login_jobstreet(page):
    page.goto("https://id.jobstreet.com/id/oauth/login/?returnUrl=%2F",
            wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(4000)
    if page.url.startswith("https://id.jobstreet.com/"):
        return
    page.locator("text=Lanjutkan dengan Google").first.click()
    for _ in range(30):
        page.wait_for_timeout(2000)
        if "accounts.google.com" in page.url:
            break
    email = _current_email(config.site_auth("jobstreet")["account"])
    acc = page.locator(f"div[data-identifier='{email}']")
    if not acc.count():
        acc = page.locator(f"text={email}")
    acc.first.click()
    for _ in range(40):
        page.wait_for_timeout(2000)
        if "accounts.google.com" not in page.url:
            break

def login_glints(page):
    page.goto("https://glints.com/id", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(3000)
    if _glints_logged_in(page):
        return
    loc = page.locator("button:has-text('Masuk'), a:has-text('Masuk')").first
    if loc.count():
        loc.click()
        page.wait_for_timeout(2500)
    g = page.locator("button:has-text('Sign in as'), button:has-text('Google')").first
    if g.count():
        g.click()
        page.wait_for_timeout(5000)
    email = _current_email(config.site_auth("glints")["account"])
    for _ in range(30):
        gp = next((p for p in page.context.pages if "accounts.google.com" in p.url), None)
        if not gp:
            break
        acc = gp.locator(f"div[data-identifier='{email}']").first
        if acc.count():
            acc.click()
            gp.wait_for_timeout(3000)
            continue
        page.wait_for_timeout(1500)
    page.wait_for_timeout(2000)

def _glints_logged_in(page) -> bool:
    try:
        txt = page.inner_text("body")[:800]
    except Exception:
        return False
    return not re.search(r"\bMASUK\b|\bDAFTAR\b", txt, re.I)

def login_site(pw, site: str):
    auth = config.site_auth(site)
    login_google(account_file=auth["account"], profile=auth["profile"], verbose=False, pw=pw)
    ctx = launch(pw, profile=auth["profile"])
    page = ctx.new_page()
    if site == "jobstreet":
        login_jobstreet(page)
    elif site == "glints":
        login_glints(page)
    elif site == "indeed":
        page.goto(config.SITES["indeed"]["fetch"].format(query="react", location="jakarta"),
                wait_until="domcontentloaded", timeout=40000)
    else:
        page.goto(config.SITES[site].get("login_url", "https://www.google.com"),
                wait_until="domcontentloaded", timeout=40000)
    return ctx, page

def login_site_standalone(site: str):
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        ctx, page = login_site(pw, site)
    except Exception:
        pw.stop()
        raise
    return ctx, page, pw

def _current_email(account_file: Path) -> str:
    return _read_account(account_file)[0]

if __name__ == "__main__":
    try:
        login_google()
    except Exception as e:
        print(f"[ERR] {e}")
        sys.exit(1)
