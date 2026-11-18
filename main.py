import argparse
from pathlib import Path

import apply
import config
import cv
import gm
import hunt
import sheet

def _profile_or_exit(cv_path: Path | None) -> dict:
    cv_path = cv_path or config.CV_DEFAULT
    if not cv_path.exists():
        raise SystemExit(f"CV tidak ditemukan: {cv_path} (letakkan pdf/txt/docx atau pakai --cv)")
    return cv.profile(cv.extract_text(cv_path))

def cmd_profil(args):
    prof = _profile_or_exit(Path(args.cv) if args.cv else None)
    print(cv.summarize(prof))

def cmd_cari(args):
    prof = _profile_or_exit(Path(args.cv) if args.cv else None)
    queries = [args.q] if args.q else prof["queries"]
    if not queries:
        raise SystemExit('CV tidak menyebut target role. Pakai --q "nama role".')
    locs = [x.strip() for x in (args.loc or "").split(",") if x.strip()] or config.LOCATIONS

    pairs = list(dict.fromkeys((queries[i % len(queries)], locs[i % len(locs)])
                            for i in range(config.MAX_SEARCHES)))
    total_added = 0
    for q, loc in pairs:
        jobs = hunt.search(args.site, q, loc)

        new = [j for j in jobs
            if sheet.dedupe_key(j.get("company", ""), j.get("title", "")) not in
            {sheet.dedupe_key(r["perusahaan"], r["posisi"]) for r in sheet.load()}]
        hunt.enrich(new, args.site, config.DESC_LIMIT)
        added = sum(sheet.add(j, prof) for j in jobs)
        total_added += added
        print(f"[OK] '{q}' @ {loc}: {len(jobs)} ditemukan, {len(new)} baru, {added} ditambah")
    print(f"Total baru: {total_added}. File: {config.SHEET_FILE}")
    print("Sinkronkan ke Google Sheet: python main.py sinkron")

def cmd_review(args):
    rows = sorted(sheet.load(), key=lambda r: -int(r["skor"] or 0))
    if not rows:
        print("Belum ada lowongan. Jalankan: python main.py cari")
        return
    for r in rows:
        acc = r["acc"] or "-"
        print(f"[{r['skor']:>3}] {r['id']} | {acc:>5} | {r['tahap']:<13} | "
            f"{r['perusahaan'][:24]:<24} | {r['posisi'][:36]:<36} | {r['sumber']}")
    print("\nACC:  python main.py acc <id> ya|tidak")

def cmd_acc(args):
    if args.value not in ("ya", "tidak"):
        raise SystemExit("Nilai acc harus 'ya' atau 'tidak'")

    try:
        import gsheet
        if config.GSHEET_SHEET_URL:
            fetched = gsheet.pull()
            if fetched:
                cur, _ = gsheet.merge_edits(sheet.load(), fetched)
                sheet.save(cur)
    except Exception:
        pass
    n = sheet.set_acc(args.id, args.value, args.note or "")
    print(f"[OK] {n} baris di-update ke '{args.value}'")

def cmd_apply(args):
    rows = [r for r in sheet.approved() if r["id"].startswith(args.id)]
    if not rows:
        raise SystemExit("Lowongan tidak ditemukan / belum di-ACC. Lihat: python main.py review")
    r = rows[0]
    site = r["sumber"] if r["sumber"] in config.SITES else "indeed"
    print(f"Apply: {r['perusahaan']} — {r['posisi']}\n{r['link']}\n")
    ctx, page, pw = gm.login_site_standalone(site)
    try:
        page.goto(r["link"], wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(3000)

        kind = _open_apply_form(page, site)
        if kind.startswith("external"):
            ext = kind.split(":", 1)[1]
            print(f"[!] Lamar diarahkan ke situs eksternal (ATS perusahaan). Tidak bisa di-apply otomatis.")
            print(f"    Link eksternal: {ext}")
            sheet.update_fields(r["id"], catatan=f"apply manual di situs eksternal: {ext}")
            sheet.set_stage(r["id"], "manual-eksternal")
            print("    Catatan + tahap 'manual-eksternal' tersimpan. Skip.")
            return
        _close_popups(page)
        page.wait_for_timeout(1500)
        print("[..] Mengisi form otomatis ...")
        try:
            apply.autofill(page)
            n_cover = apply.cover_letter(page)
            if n_cover:
                print(f"  [autofill] cover letter diisi di {n_cover} textarea")
        except Exception as e:
            print(f"  [!] autofill gagal: {e} — lanjut manual")
        print("\nBrowser terbuka di lowongan. CEK SEBELUM submit — script TIDAK mengklik submit.")
        try:
            input("Tekan Enter kalau lamaran sudah terkirim (s=skip) ... ")
        except EOFError:
            print("[cron] stdin tertutup — biarkan browser terbuka, tutup manual setelah submit.")
            return
    finally:
        ctx.close()
        pw.stop()
    sheet.set_stage(r["id"], "terkirim")
    print("[OK] tahap = terkirim")

def _close_popups(page):
    for sel in ("button[aria-label='Tutup']", "button[aria-label='Close']",
                "[data-dismiss='modal']"):
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible():
                loc.click(force=True); page.wait_for_timeout(800)
        except Exception:
            pass
    try:
        page.evaluate("""
            () => {
                // popup promosi Glints: teks 'Unduh App' / 'Cepat Dapat Kerja'
                document.querySelectorAll('[class*="ModalStyle__StyledModalWrapper"]').forEach(el => {
                    if (!el.innerText.includes('Lamar') && !el.innerText.match(/\\d\\/\\d/)) {
                        el.remove();
                    }
                });
                // backdrop z-index tinggi TANPA teks form apply
                document.querySelectorAll('div').forEach(el => {
                    const s = getComputedStyle(el);
                    if ((s.position === 'fixed' || s.position === 'absolute')
                        && parseInt(s.zIndex) > 500 && el.clientWidth > 400 && el.clientHeight > 200) {
                        const t = el.innerText || '';
                        if (!t.includes('Lamar') && !t.includes('Apply') && !t.match(/\\d\\/\\d/)) {
                            el.remove();
                        }
                    }
                });
                document.body.style.overflow = 'auto';
            }
        """)
        page.wait_for_timeout(500)
    except Exception:
        pass

def _click_apply_button(page) -> bool:
    for sel in ("[data-testid='job-detail-apply']", "[data-automation='job-detail-apply-button']",
                "[data-automation='apply-button']", "[data-automation='quick-apply-button']",
                "button:has-text('Lamaran Cepat')", "a:has-text('Lamaran Cepat')",
                "button:has-text('Lamar')", "a:has-text('Lamar')",
                "a[aria-label^='Lamar']", "a[data-testid='apply-button']",
                "button:has-text('Apply')", "a:has-text('Apply')",
                "button:has-text('Apply now')",
                "button:has-text('Quick apply')", "a:has-text('Quick apply')"):
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible():
                loc.click(force=True, timeout=5000)
                return True
        except Exception:
            continue
    return False

def _open_apply_form(page, site: str) -> str:
    start_url = page.url
    start_host = page.url.split("/")[2] if "//" in page.url else ""

    def has_apply_ui() -> bool:
        try:
            body = page.locator("body").inner_text()[:4000]
        except Exception:
            return False
        return ("Lamar posisi" in body or "Lamar kerja" in body
                or bool(__import__("re").search(r"\b[1-5]/5\b", body)))

    def has_form_fields() -> bool:

        return page.locator("input:visible, textarea:visible").count() >= 2

    def external_apply_href() -> str | None:
        try:
            anchors = page.evaluate("""() => {
                return [...document.querySelectorAll('a')].filter(a => {
                    const t = (a.innerText || '').trim();
                    return (t === 'Lamar' || t === 'Apply' || t.includes('Easy Apply'))
                        && a.href;
                }).map(a => ({href: a.href, txt: a.innerText, target: a.target}));
            }""")
        except Exception:
            return None
        for a in anchors:
            href = a["href"] or ""

            if "/safety/go/" in href:
                from urllib.parse import urlparse, parse_qs, unquote
                q = parse_qs(urlparse(href).query)
                real = q.get("url", [""])[0]
                if real and "linkedin.com" not in real:
                    return unquote(real)

            elif href.startswith("http"):
                a_host = href.split("/")[2] if "//" in href else ""
                if a_host and a_host != start_host:
                    return href
        return None

    _click_apply_button(page)
    page.wait_for_timeout(2500)
    if has_apply_ui() or has_form_fields():
        return "modal" if has_apply_ui() else "form"

    ext = external_apply_href()
    if ext:
        return f"external:{ext}"

    if page.url != start_url:
        host = page.url.split("/")[2] if "//" in page.url else ""
        if host and host != start_host:
            return f"external:{page.url}"

    try:
        page.locator("button:has-text('Lamar'), a:has-text('Lamar')").last.click(force=True, timeout=3000)
        page.wait_for_timeout(2500)
    except Exception:
        pass
    _close_popups(page)
    page.wait_for_timeout(800)
    if has_apply_ui():
        return "modal"
    if has_form_fields():
        return "form"

    if page.url != start_url:
        host = page.url.split("/")[2] if "//" in page.url else ""
        if host and host != start_host:
            return f"external:{page.url}"
    return "none"

def _glints_advance_fill(page, max_steps: int = 15, verbose: bool = True) -> None:
    import re as _re
    for _ in range(max_steps):
        vals = page.evaluate(
            "() => [...document.querySelectorAll('input[type=radio]')]"
            ".filter(el => el.offsetParent).map(el => el.value)"
        )

        skill_vals = {"INTERMEDIATE", "ADVANCED", "CONVERSATIONAL",
                    "PROFESSIONAL", "LESS_THAN_ONE_YEAR"}
        if any(v in skill_vals for v in vals):
            stat = apply.fill_glints_skill_ratings(page, verbose=verbose)
            if verbose and stat["filled"]:
                print(f"    [skill] {stat['filled']} keahlian diisi "
                    f"({len(stat['in_cv'])} Ahli/Profesional, {len(stat['menengah'])} Menengah)")

        nxt = page.locator("button:has-text('Selanjutnya'):visible")
        if nxt.count():
            nxt.first.click(force=True)
            page.wait_for_timeout(2500)
            continue

        break

def cmd_apply_semua(args):
    rows = sheet.approved()
    if not rows:
        print("Tidak ada lowongan di-ACC. Tandai di Google Sheet kolom M atau:")
        print("  python main.py acc <id> ya")
        return
    print(f"{len(rows)} lowongan di-ACC siap diproses.\n")
    from playwright.sync_api import sync_playwright
    submitted = 0
    with sync_playwright() as pw:
        ctx_by_site = {}
        try:
            for r in rows:
                site = r["sumber"] if r["sumber"] in config.SITES else "indeed"
                if site not in ctx_by_site:
                    ctx, page = gm.login_site(pw, site)
                    ctx_by_site[site] = (ctx, page)
                ctx, page = ctx_by_site[site]
                print(f"==> {r['perusahaan']} — {r['posisi']}\n    {r['link']}")
                page.goto(r["link"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                kind = _open_apply_form(page, site)
                if kind.startswith("external"):
                    ext = kind.split(":", 1)[1]
                    print(f"    [!] External ATS: {ext}")
                    sheet.update_fields(r["id"], catatan=f"apply manual di situs eksternal: {ext}")
                    sheet.set_stage(r["id"], "manual-eksternal")
                    print("    Catatan + tahap 'manual-eksternal' tersimpan di sheet. Skip.\n")
                    continue
                _close_popups(page)
                page.wait_for_timeout(1500)
                print("    [..] autofill ...")
                try:
                    apply.autofill(page, verbose=True)
                    n = apply.cover_letter(page)
                    if n:
                        print(f"    [autofill] cover letter: {n} textarea")
                except Exception as e:
                    print(f"    [!] autofill gagal: {e}")


                if site == "glints":
                    try:
                        _glints_advance_fill(page, verbose=True)
                    except Exception as e:
                        print(f"    [!] glints advance gagal: {e}")
                try:
                    ans = "y" if getattr(args, "auto", False) else input(
                        "    CEK form. Enter=submit ok (t=tandai terkirim tanpa submit, s=skip) ... ")
                except EOFError:
                    if getattr(args, "auto", False):
                        ans = "y"
                    else:
                        print("    [cron] stdin tertutup — browser dibiarkan terbuka, tutup manual setelah submit.")
                        break
                if ans.strip().lower() == "s":
                    print("    [skip]\n")
                    continue
                sheet.set_stage(r["id"], "terkirim")
                submitted += 1
                print("    [OK] tahap = terkirim\n")
        finally:
            for ctx, _ in ctx_by_site.values():
                ctx.close()
    print(f"Selesai: {submitted} ditandai terkirim.")

def cmd_perbarui(args):
    from playwright.sync_api import sync_playwright
    from collections import defaultdict
    rows = sheet.load()
    targets = [r for r in rows
            if (not r["gaji"] or (args.desc and not r["deskripsi"]))
            and (args.site in (None, "", r["sumber"]))
            and r["sumber"] in config.SITES]
    if args.limit:
        targets = targets[:args.limit]
    if not targets:
        print("Tidak ada baris yang perlu diperbarui.")
        return
    per_site = defaultdict(list)
    for r in targets:
        per_site[r["sumber"]].append(r)
    print(f"[..] {len(targets)} baris akan diperbarui ({dict((k, len(v)) for k, v in per_site.items())})")
    updated = 0
    with sync_playwright() as pw:
        for site, group in per_site.items():
            ctx = gm.launch_site(pw, site)
            page = ctx.new_page()
            try:
                for r in group:
                    det = hunt.fetch_details(page, site, r["link"])
                    vals = {}
                    if det["salary"] and not r["gaji"]:
                        vals["gaji"] = det["salary"]
                    if args.desc and det["description"] and not r["deskripsi"]:
                        vals["deskripsi"] = det["description"][:4000]
                    if vals:
                        sheet.update_fields(r["id"], **vals)
                        updated += 1
                        print(f"  + [{site}] {r['perusahaan'][:24]:<24} | {vals.get('gaji', 'desc')[:32]}")
            finally:
                ctx.close()
    print(f"[OK] {updated} baris diperbarui")

def cmd_reskor(args):
    prof = _profile_or_exit(Path(args.cv) if args.cv else None)
    from cv import score as score_job
    rows = sheet.load()
    n = 0
    for r in rows:
        job = {"title": r["posisi"], "description": r["deskripsi"], "company": r["perusahaan"]}
        s, matched, missing = score_job(job, prof)
        if str(s) != str(r["skor"]) or ", ".join(matched) != r["skill_cocok"]:
            n += 1
        r["skor"], r["skill_cocok"], r["skill_kurang"] = s, ", ".join(matched), ", ".join(missing)
    sheet.save(rows)
    rows.sort(key=lambda r: -int(r["skor"] or 0))
    print(f"[OK] {n}/{len(rows)} baris di-rescore. Top 5:")
    for r in rows[:5]:
        print(f"  [{r['skor']:>3}] {r['perusahaan'][:26]:<26} | {r['posisi'][:34]}")

def cmd_jalankan(args):
    import datetime
    t0 = datetime.datetime.now()
    print(f"===== jalankan mulai {t0:%Y-%m-%d %H:%M} =====")

    print("[1/5] tarik editan dari Google Sheet ...")
    try:
        cmd_tarik(argparse.Namespace())
    except Exception as e:
        print(f"[!] tarik gagal: {e}")

    for i, site in enumerate(("jobstreet", "indeed", "linkedin", "glints"), 2):
        print(f"[{i}/7] cari di {site} (query dari CV) ...")
        try:
            cmd_cari(argparse.Namespace(site=site, q=None, loc=None, cv=None, desc=True))
        except SystemExit:
            raise
        except Exception as e:
            print(f"[!] cari {site} gagal: {e}")

    print("[6/7] reskor dengan CV ...")
    try:
        cmd_reskor(argparse.Namespace(cv=None))
    except Exception as e:
        print(f"[!] reskor gagal: {e}")

    print("[7a/7] perbarui gaji/deskripsi yang bolong ...")
    try:
        cmd_perbarui(argparse.Namespace(site=None, desc=True, limit=args.limit or 10))
    except Exception as e:
        print(f"[!] perbarui gagal: {e}")

    print("[7b/7] sinkron ke Google Sheet ...")
    try:
        cmd_sinkron(argparse.Namespace())
    except Exception as e:
        print(f"[!] sinkron gagal: {e}")

    print("[8/7] cek lowongan yang sudah di-ACC ...")
    ready = sheet.approved()
    if ready:
        print(f"[!] {len(ready)} lowongan menunggu apply. Buka browser manual:")
        for r in ready[:10]:
            print(f"     {r['id']} | {r['perusahaan'][:30]:<30} | {r['posisi'][:36]:<36} | {r['link'][:60]}")
        print("Proses satu-satu: python main.py apply <id>")
        print("Proses semua    : python main.py apply-semua")
    else:
        print("[i] Belum ada yang di-ACC. Tandai di Google Sheet kolom M (acc=ya).")

    dt = (datetime.datetime.now() - t0)
    print(f"===== jalankan selesai dalam {int(dt.total_seconds())}s =====")

def cmd_rapikan(args):
    rows, removed = sheet.dedupe_rows()
    print(f"[OK] {removed} duplikat digabung. Sisa {len(rows)} baris.")
    if removed:
        print("Sinkronkan balik: python main.py sinkron")

def cmd_open(args):
    ctx, page, pw = gm.login_site_standalone(args.site)
    print(f"[OK] {args.site} siap. URL: {page.url[:80]}")
    input("Tekan Enter untuk menutup browser ...")
    ctx.close()
    pw.stop()

def cmd_sinkron(args):
    import gsheet
    rows = sheet.load()
    n = gsheet.push(rows)
    print(f"[OK] {n} baris terkirim ke Google Sheet")

def cmd_tarik(args):
    import gsheet
    rows = sheet.load()
    fetched = gsheet.pull()
    if not fetched:
        print("[!] Sheet kosong / gagal dibaca. Cek koneksi & login Google.")
        return
    rows, n = gsheet.merge_edits(rows, fetched)
    sheet.save(rows)
    print(f"[OK] {len(fetched)} baris dibaca, {n} kolom ter-update di lokal")

def main():
    p = argparse.ArgumentParser(prog="FindMyJob")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("profil"); c.add_argument("--cv"); c.set_defaults(fn=cmd_profil)
    c = sub.add_parser("cari"); c.add_argument("--site", default=config.DEFAULT_SITE,
                                            choices=list(config.SITES))
    c.add_argument("--q", default=None,
                help="query manual; kosong = ambil target role dari CV")
    c.add_argument("--loc", default=None,
                help="lokasi, pisah koma; kosong = pakai config.LOCATIONS")
    c.add_argument("--cv"); c.add_argument("--desc", action="store_true"); c.set_defaults(fn=cmd_cari)
    c = sub.add_parser("review"); c.set_defaults(fn=cmd_review)
    c = sub.add_parser("acc"); c.add_argument("id"); c.add_argument("value")
    c.add_argument("--note"); c.set_defaults(fn=cmd_acc)
    c = sub.add_parser("apply"); c.add_argument("id"); c.set_defaults(fn=cmd_apply)
    c = sub.add_parser("apply-semua"); c.set_defaults(fn=cmd_apply_semua)
    c = sub.add_parser("open"); c.add_argument("--site", default=config.DEFAULT_SITE,
                                            choices=list(config.SITES)); c.set_defaults(fn=cmd_open)
    c = sub.add_parser("perbarui"); c.add_argument("--site"); c.add_argument("--desc", action="store_true")
    c.add_argument("--limit", type=int, default=0); c.set_defaults(fn=cmd_perbarui)
    c = sub.add_parser("sinkron"); c.set_defaults(fn=cmd_sinkron)
    c = sub.add_parser("tarik"); c.set_defaults(fn=cmd_tarik)
    c = sub.add_parser("reskor"); c.add_argument("--cv"); c.set_defaults(fn=cmd_reskor)
    c = sub.add_parser("jalankan"); c.add_argument("--limit", type=int, default=0)
    c.set_defaults(fn=cmd_jalankan)
    c = sub.add_parser("rapikan"); c.set_defaults(fn=cmd_rapikan)
    args = p.parse_args()
    args.fn(args)

if __name__ == "__main__":
    main()
