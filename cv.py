import re
from pathlib import Path

import config

_SKILL_HEADING = re.compile(
    r"^(skills?|technical skills?|hard skills?|soft skills?|tools?\s*&?\s*technolog\w*"
    r"|tech(?:nical)?\s*stack|core competencies|areas? of expertise|competencies)\s*[:\-]?\s*$",
    re.I)

_TECH_LINE = re.compile(r"^(tech|tools?|technolog\w*|stack)\s*[:\-]\s*(.+)$", re.I)
_STOP = {"dan", "and", "atau", "or", "the", "of", "untuk", "for", "with", "dengan",
        "skill", "skills", "tools", "technologies", "tech", "stack", "dasar", "basic",
        "lainnya", "dll", "etc", "others", "hard", "soft"}

def extract_text(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    if suf in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suf == ".docx":
        import zipfile
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        return re.sub(r"<[^>]+>", " ", xml)
    raise ValueError(f"Format CV tidak didukung: {suf} (pakai pdf/txt/docx)")

def _clean(tok: str) -> str:
    tok = re.sub(r"\((?:[^()]*)\)", " ", tok)
    tok = re.sub(r"[^\w\s.+#/\-]", " ", tok)
    tok = re.sub(r"\s+", " ", tok).strip(" -,;")
    return tok

def _is_skill(tok: str) -> bool:
    if not (2 <= len(tok) <= 40):
        return False
    words = tok.lower().split()
    if len(words) > 4 or not words:
        return False
    if all(w in _STOP for w in words):
        return False
    if re.fullmatch(r"[\d\s.]+", tok):
        return False
    return True

def extract_skills(text: str) -> dict[str, int]:
    low = text.lower()
    skills: set[str] = set()
    in_block = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if _SKILL_HEADING.match(s):
            in_block = True
            continue
        if re.match(r"^[A-Z][A-Za-z ]{2,30}$", s) and len(s.split()) <= 3 and ":" not in s:
            in_block = False
        m = _TECH_LINE.match(s)
        if m:
            in_block = False
            for t in re.split(r"[,;|]", m.group(2)):
                t = _clean(t)
                if _is_skill(t):
                    skills.add(t.lower())
            continue
        if in_block:
            for t in re.split(r"[,;|]", s):
                t = _clean(t)
                if _is_skill(t):
                    skills.add(t.lower())

    weights = {}
    for sk in skills:
        n = len(re.findall(re.escape(sk), low))
        weights[sk] = max(1, n)

    if weights:
        mx = max(weights.values())
        weights = {k: max(1, round(12 * v / mx)) for k, v in weights.items()}
    return dict(sorted(weights.items(), key=lambda kv: -kv[1]))

def derive_queries(text: str) -> list[str]:
    queries: list[str] = []

    def add(q: str):
        q = re.sub(r"\s+", " ", q).strip(" ,;-|")
        if not q:
            return
        q = re.sub(r"engineering$", "engineer", q, flags=re.I)
        if re.search(r"(engineer|developer|scientist|analyst|programmer|architect"
                    r"|specialist|manager|designer|administrator)", q, re.I):
            queries.append(q)

    m = re.search(r"seek(?:ing)?\s+(?:an?\s+)?([A-Z][\w\- /&]{3,40}?)\s+(?:role|position|job)", text)
    if m:
        for part in re.split(r",| and ", m.group(1)):
            add(part)

    for m in re.finditer(r"^\s*role\s*:\s*(.+)$", text, re.M | re.I):
        for part in re.split(r"&|,", m.group(1)):
            add(part)

    for line in text.splitlines()[:8]:
        if line.count("|") >= 2:
            for part in line.split("|"):
                add(part)

    seen, out = set(), []
    for q in queries:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out[:config.MAX_QUERIES]

def profile(cv_text: str) -> dict:
    low = cv_text.lower()
    skills = extract_skills(cv_text)

    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", cv_text)
    phone = re.search(r"(?:\+62|0)8\d[\d\s-]{7,13}", cv_text)
    years = re.search(r"(\d{1,2})\+?\s*(?:tahun|years?)\s*(?:pengalaman|experience|of exp)", low)
    return {
        "skills": skills,
        "queries": derive_queries(cv_text),
        "email": email.group(0) if email else "",
        "phone": re.sub(r"\s", "", phone.group(0)) if phone else "",
        "years": int(years.group(1)) if years else None,
        "chars": len(cv_text),
    }

def score(job: dict, prof: dict) -> tuple[int, list[str], list[str]]:
    core = list(prof["skills"].items())[:15]
    total = sum(w for _, w in core) or 1
    hay = f"{job.get('title','')} {job.get('description','')} {job.get('company','')}".lower()

    matched = [k for k, _ in core if k in hay]
    gained = sum(dict(core)[k] for k in matched)

    title = job.get("title", "").lower()
    bonus = min(20, sum(4 for k in prof["skills"] if k in title))
    base = int(70 * gained / total) + bonus

    cv_skills = set(prof["skills"])
    wanted = []
    for line in (job.get("description") or "").splitlines():
        if line.count(",") >= 3:
            for t in re.split(r"[,;|]", line):
                t = _clean(t).lower()
                if _is_skill(t) and t not in cv_skills and not any(t in m for m in matched):
                    wanted.append(t)
    seen, miss = set(), []
    for t in wanted:
        if t not in seen:
            seen.add(t)
            miss.append(t)
    return min(100, base), matched, miss[:8]

def summarize(prof: dict) -> str:
    top = list(prof["skills"])[:10]
    return (f"Target role: {'; '.join(prof['queries']) or '-'}\n"
            f"Skill dominan: {', '.join(top) or '-'}\n"
            f"Kontak: {prof['email'] or '-'} {prof['phone'] or ''}\n"
            f"Pengalaman: {prof['years'] if prof['years'] else '?'} tahun\n"
            f"Panjang teks CV: {prof['chars']} karakter")

if __name__ == "__main__":
    import sys

    sample =    p = profile(sample)
    assert "machine learning engineer" in [q.lower() for q in p["queries"]], p["queries"]
    assert "python" in p["skills"], p["skills"]
    assert p["skills"]["python"] > 1
    s, m, w = score({"title": "ML Engineer",
                    "description": "Butuh Python, XGBoost, pandas, Git, English fluent, FastAPI, React"}, p)
    assert 0 <= s <= 100, s
    assert "python" in m and "xgboost" in m, m
    assert any("english" in k or "react" in k for k in w), w

    if len(sys.argv) > 1:
        prof = profile(extract_text(Path(sys.argv[1])))
        print(summarize(prof))
    print("cv self-check ok")
