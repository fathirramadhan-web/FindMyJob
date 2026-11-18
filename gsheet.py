import csv
import io
import time

import config
import sheet as sheetmod

EDITABLE = ("acc", "tahap", "catatan")

def _session():
    import gm
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    return pw, gm.launch(pw)

def _paste(page, text: str) -> None:
    page.evaluate("(t) => navigator.clipboard.writeText(t)", text)
    page.wait_for_timeout(800)
    page.keyboard.press("Control+v")
    page.wait_for_timeout(4500)

def _clear(page) -> None:
    page.keyboard.press("Control+Home")
    page.wait_for_timeout(1200)
    page.keyboard.press("Control+a")
    page.wait_for_timeout(1500)
    page.keyboard.press("Delete")
    page.wait_for_timeout(3000)

def push(rows: list[dict]) -> int:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n", delimiter="\t")
    w.writerow(sheetmod.COLUMNS)
    for r in rows:
        w.writerow([str(r.get(c, "") or "") for c in sheetmod.COLUMNS])

    pw, ctx = _session()
    try:
        page = ctx.new_page()
        page.bring_to_front()
        page.goto(config.GSHEET_SHEET_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        for s in ["text=Lewati", "text=Skip", "button[aria-label='Tutup']"]:
            el = page.locator(s).first
            if el.count():
                el.click()
                page.wait_for_timeout(1200)
        _clear(page)
        _paste(page, buf.getvalue())
    finally:
        pw.stop()
    return len(rows)

def pull() -> list[dict]:
    key = config.GSHEET_SHEET_URL.split("/edit")[0]
    for attempt in range(3):
        pw, ctx = _session()
        try:
            resp = ctx.request.get(f"{key}/export?format=csv")
            text = resp.text() if resp.status == 200 else ""
            if not text:
                print(f"[pull] percobaan {attempt+1}: status={resp.status}, kosong — tunggu 5s, ulang")
                time.sleep(5)
                continue
            return list(csv.DictReader(io.StringIO(text)))
        finally:
            pw.stop()
    return []

def merge_edits(local: list[dict], remote: list[dict]) -> tuple[list[dict], int]:
    by_id = {r.get("id", ""): r for r in local}
    changed = 0
    for r in remote:
        rid = str(r.get("id", "")).strip()
        tgt = by_id.get(rid)
        if not tgt:
            continue
        for k in EDITABLE:
            v = str(r.get(k, "") or "").strip()
            if v and v != tgt.get(k, ""):
                tgt[k] = v
                changed += 1
    return local, changed

if __name__ == "__main__":
    local = [{"id": "a1", "acc": "", "tahap": "perlu-review", "catatan": ""}]
    remote = [{"id": "a1", "acc": "ya", "tahap": "disetujui", "catatan": "ok"},
            {"id": "zz", "acc": "ya"}]
    rows, n = merge_edits(local, remote)
    assert rows[0]["acc"] == "ya" and rows[0]["tahap"] == "disetujui" and n == 3, rows
    assert len(rows) == 1, "baris asing tidak boleh ditambah"
    print("gsheet merge self-check ok")
