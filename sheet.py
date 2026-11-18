import csv
import hashlib
import re
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import config

COLUMNS = [
    "id", "perusahaan", "posisi", "sumber", "lokasi", "gaji",
    "ditemukan", "deskripsi", "link",
    "skor", "skill_cocok", "skill_kurang",
    "acc", "tahap", "tanggal_apply", "catatan",
]

STATUSES = ["perlu-review", "disetujui", "ditolak", "siap-apply", "terkirim",
            "interview", "ditolak-perusahaan", "ditutup"]

_WIDTHS = {"A": 13, "B": 24, "C": 26, "D": 9, "E": 18, "F": 26, "G": 16,
        "H": 60, "I": 52, "J": 6, "K": 34, "L": 34, "M": 7, "N": 15,
        "O": 15, "P": 30}
_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(color="FFFFFF", bold=True)

def _path() -> Path:
    return config.SHEET_FILE

def _migrate_from_csv() -> list[dict]:
    p = config.CSV_FILE
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    save(rows)
    return rows

def load() -> list[dict]:
    p = _path()
    if not p.exists():
        return _migrate_from_csv()
    wb = openpyxl.load_workbook(p, data_only=True)
    ws = wb.active
    headers = [c.value for c in ws[1]]
    if not headers or headers[0] != COLUMNS[0]:
        return _migrate_from_csv()
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        d = {}
        for h, v in zip(headers, row):
            if v is None:
                v = ""
            elif isinstance(v, (int, float)) and h in ("skor",):
                v = int(v)
            d[h] = str(v)
        rows.append(d)
    return rows

def _cell(value, col: str):
    if col == "skor":
        try:
            return int(value)
        except (TypeError, ValueError):
            return ""
    return value

def save(rows: list[dict]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "pipeline"
    ws.append(COLUMNS)

    for r in rows:
        ws.append([_cell(r.get(c, ""), c) for c in COLUMNS])

    for i, col in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=i)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(vertical="center")
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = _WIDTHS.get(letter, 18)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:P{len(rows) + 1}"
    ws.row_dimensions[1].height = 20

    dv_acc = DataValidation(type="list", formula1='"ya,tidak,belum"', allow_blank=True)
    dv_acc.error = "Isi ya / tidak / belum"
    dv_acc.showErrorMessage = True
    ws.add_data_validation(dv_acc)
    dv_acc.add(f"M2:M{len(rows) + 1}")

    dv_stage = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"',
                            allow_blank=True)
    ws.add_data_validation(dv_stage)
    dv_stage.add(f"N2:N{len(rows) + 1}")

    wb.save(_path())

    if not config.CSV_FILE.exists():
        with config.CSV_FILE.open("w", newline="", encoding="utf-8-sig") as f:
            f.write("File ini sudah tidak dipakai. Buka jobs-pipeline.xlsx.\n")

_LEGAL = re.compile(r"\b(pt|cv|pte|ltd|limited|inc|llc|tbk|persero|group|company)\b", re.I)

def _norm_txt(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()

def dedupe_key(company: str, title: str) -> str:
    comp = _norm_txt(_LEGAL.sub(" ", company or ""))
    title = _norm_txt(title or "")
    return hashlib.sha1(f"{comp}|{title}".encode()).hexdigest()[:12]

def job_id(link: str, company: str, title: str) -> str:

    link = (link or "").split("?")[0].split("#")[0]
    return hashlib.sha1(f"{link}|{company}|{title}".lower().encode()).hexdigest()[:12]

def add(job: dict, prof: dict) -> bool:
    from cv import score as score_job
    rows = load()
    seen = {dedupe_key(r["perusahaan"], r["posisi"]) for r in rows}
    key = dedupe_key(job.get("company", ""), job.get("title", ""))
    if key in seen:
        return False
    jid = job_id(job.get("link", ""), job.get("company", ""), job.get("title", ""))

    s, matched, missing = score_job(job, prof)
    rows.append({
        "id": jid,
        "perusahaan": job.get("company", "").strip(),
        "posisi": job.get("title", "").strip(),
        "sumber": job.get("source", ""),
        "lokasi": job.get("location", "").strip(),
        "gaji": job.get("salary", ""),
        "ditemukan": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "deskripsi": (job.get("description", "") or "").strip()[:4000],
        "link": job.get("link", ""),
        "skor": s,
        "skill_cocok": ", ".join(matched),
        "skill_kurang": ", ".join(missing),
        "acc": "",
        "tahap": "perlu-review",
        "tanggal_apply": "",
        "catatan": "",
    })
    save(rows)
    return True

def set_acc(jid_prefix: str, acc: str, note: str = "") -> int:
    rows, n = load(), 0
    for r in rows:
        if r["id"].startswith(jid_prefix):
            r["acc"] = acc
            r["tahap"] = "disetujui" if acc == "ya" else "ditolak"
            if note:
                r["catatan"] = note
            n += 1
    save(rows)
    return n

def approved() -> list[dict]:
    skip = {"terkirim", "ditolak", "ditutup", "ditolak-perusahaan", "manual-eksternal"}
    return [r for r in load() if r["acc"] == "ya" and r["tahap"] not in skip]

def update_fields(jid: str, **fields) -> None:
    rows = load()
    for r in rows:
        if r["id"] == jid:
            for k, v in fields.items():
                if v:
                    r[k] = v
    save(rows)

def set_stage(jid: str, stage: str) -> None:
    rows = load()
    for r in rows:
        if r["id"] == jid or r["id"].startswith(jid):
            r["tahap"] = stage
            if stage == "terkirim":
                r["tanggal_apply"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save(rows)

def dedupe_rows() -> tuple[list[dict], int]:
    rows = load()
    kept: dict[str, dict] = {}
    removed = 0
    for r in rows:
        k = dedupe_key(r["perusahaan"], r["posisi"])
        if k in kept:
            old = kept[k]
            for c in ("gaji", "deskripsi", "acc", "tahap", "catatan",
                    "skill_cocok", "skill_kurang", "ditemukan"):
                if not old.get(c) and r.get(c):
                    old[c] = r[c]
            removed += 1
        else:
            kept[k] = r
    keep_ids = {r["id"] for r in kept.values()}
    out = [r for r in rows if r["id"] in keep_ids]
    if removed:
        save(out)
    return out, removed

if __name__ == "__main__":
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    config.SHEET_FILE = tmp / "t.xlsx"
    config.CSV_FILE = tmp / "none.csv"
    prof = {"skills": {"react": 10, "python": 8}}
    assert add({"link": "http://x/1", "company": "PT A", "title": "React Dev",
                "description": "react python", "source": "indeed"}, prof)
    assert not add({"link": "http://x/1", "company": "PT A", "title": "React Dev"}, prof), "duplikat lolos"
    rows = load()
    assert len(rows) == 1 and rows[0]["tahap"] == "perlu-review"
    assert str(rows[0]["skor"]).lstrip("-").isdigit()
    assert set_acc(rows[0]["id"], "ya") == 1
    assert len(approved()) == 1
    update_fields(rows[0]["id"], gaji="Rp 5.000.000")
    assert load()[0]["gaji"] == "Rp 5.000.000"
    set_stage(rows[0]["id"], "terkirim")
    assert load()[0]["tanggal_apply"]

    assert not add({"link": "http://y/2", "company": "A", "title": "react dev"}, prof), "dup beda link lolos"
    assert not add({"link": "http://z/3", "company": "PT. A", "title": "React   Dev"}, prof), "dup beda situs lolos"
    out, removed = dedupe_rows()
    assert len(out) == 1 and removed == 0

    wb = openpyxl.load_workbook(config.SHEET_FILE)
    ws = wb.active
    assert ws.max_row == 2 and [c.value for c in ws[1]][0] == "id"
    assert ws.freeze_panes == "A2"
    print("sheet xlsx self-check ok")
