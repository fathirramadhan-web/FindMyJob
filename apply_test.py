import sys
from pathlib import Path

import gm
import sheet
import apply as A
from main import _open_apply_form

def main():
    if len(sys.argv) < 2:
        print("pakai: python apply_test.py <id-prefix>")
        return
    rows = [r for r in sheet.approved() if r["id"].startswith(sys.argv[1])]
    if not rows:
        print("lowongan tidak ditemukan / belum ACC")
        return
    r = rows[0]
    site = r["sumber"] if r["sumber"] in (A.config.SITES) else "indeed"
    print(f"Test: {r['perusahaan']} — {r['posisi']} ({site})")
    print(r["link"])
    ctx, page, pw = gm.login_site_standalone(site)
    try:
        page.goto(r["link"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        _open_apply_form(page, site)
        page.wait_for_timeout(2500)
        print("[..] autofill ...")
        A.autofill(page, verbose=True)
        n = A.cover_letter(page)
        print(f"[..] cover letter: {n} textarea diisi")
        page.screenshot(path=str(A.config.BASE / "apply_test.png"))
        print("[OK] screenshot: apply_test.png — form TIDAK disubmit")
    finally:
        ctx.close()
        pw.stop()

if __name__ == "__main__":
    main()
