import sys

from playwright.sync_api import sync_playwright

import config
import gm

def login_linkedin(pw):
    auth = config.site_auth("linkedin")
    email, _ = gm._read_account(auth["account"])
    print(f"[LinkedIn] {email}")
    login_google(pw=pw, account_file=auth["account"], profile=auth["profile"])
    ctx = gm.launch_site(pw, "linkedin")
    page = ctx.new_page()
    page.goto("https://www.linkedin.com/", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(3000)

    logged_in = page.locator("input#session_key").count() == 0
    if not logged_in:
        print("  [!] Belum login browsing. Coba SSO Google dari halaman login ...")
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        try:
            page.locator("button:has-text('Sign in with Google'), a:has-text('Sign in with Google')").first.click()
            page.wait_for_timeout(3000)
        except Exception:
            pass

        for _ in range(60):
            if "linkedin.com/feed" in page.url or ("linkedin.com" in page.url and page.locator("input#session_key").count() == 0):
                logged_in = True
                break
            page.wait_for_timeout(2000)
    print(f"  [{'OK' if logged_in else 'GAGAL'}] login browsing LinkedIn")
    ctx.close()

def login_google(pw, account_file, profile, verbose=True):
    try:
        gm.login_google(account_file=account_file, profile=profile, verbose=verbose, pw=pw)
    except Exception as e:
        if verbose:
            print(f"  [i] login google skip: {e}")

def login_indeed(pw):
    auth = config.site_auth("indeed")
    email, _ = gm._read_account(auth["account"])
    print(f"[Indeed] {email}")
    login_google(pw=pw, account_file=auth["account"], profile=auth["profile"], verbose=False)
    ctx = gm.launch_site(pw, "indeed")
    page = ctx.new_page()
    page.goto("https://secure.indeed.com/account/login", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(3000)
    if "login" in page.url.lower() and page.locator("input[type=email]").count():
        print("  [..] login via SSO Google ...")
        try:
            page.locator("button:has-text('Continue with Google'), a:has-text('Continue with Google')").first.click()
            page.wait_for_timeout(4000)
        except Exception:
            pass
        for _ in range(60):
            if "secure.indeed.com" in page.url and "login" not in page.url.lower():
                break
            page.wait_for_timeout(2000)
    print(f"  [{'OK' if 'login' not in page.url.lower() else 'GAGAL'}] Indeed")
    ctx.close()

def login_jobstreet(pw):
    auth = config.site_auth("jobstreet")
    email, _ = gm._read_account(auth["account"])
    print(f"[JobStreet] {email}")
    login_google(pw=pw, account_file=auth["account"], profile=auth["profile"], verbose=False)
    ctx = gm.launch_site(pw, "jobstreet")
    page = ctx.new_page()
    gm.login_jobstreet(page)
    page.wait_for_timeout(2000)

    logged = page.locator("button:has-text('Masuk'), a:has-text('Masuk')").count() == 0
    print(f"  [{'OK' if logged else 'GAGAL'}] JobStreet")
    ctx.close()

def login_glints(pw):
    auth = config.site_auth("glints")
    email, _ = gm._read_account(auth["account"])
    print(f"[Glints] {email}")
    login_google(pw=pw, account_file=auth["account"], profile=auth["profile"], verbose=False)
    ctx = gm.launch_site(pw, "glints")
    page = ctx.new_page()
    gm.login_glints(page)
    page.wait_for_timeout(2000)
    logged = gm._glints_logged_in(page)
    print(f"  [{'OK' if logged else 'GAGAL'}] Glints")
    ctx.close()

def main():
    print("=" * 50)
    print("LOGIN SEMUA SITUS (headless=False). Bila ada captcha,")
    print("selesaikan manual di browser yang terbuka. Script menunggu.")
    print("=" * 50)
    with sync_playwright() as pw:
        steps = [
            ("LinkedIn", lambda: login_linkedin(pw)),
            ("Indeed", lambda: login_indeed(pw)),
            ("JobStreet", lambda: login_jobstreet(pw)),
            ("Glints", lambda: login_glints(pw)),
        ]
        for name, fn in steps:
            try:
                fn()
            except Exception as e:
                print(f"  [!] {name} gagal: {e}")
    print("\nSelesai. Session tersimpan di browser_profile/. Selanjutnya `apply` tidak perlu login ulang.")

if __name__ == "__main__":
    main()
