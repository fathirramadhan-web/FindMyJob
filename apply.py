import json
import re
from pathlib import Path

import config

FIELD_MAP = {
    "nama": r"(nama[\s_-]*lengkap|full[\s_-]*name|^name$|applicant[_-]?name|full[_-]?name)",
    "first": r"(first[\s_-]*name|given[\s_-]*name|nama[\s_-]*depan|nama[\s_-]*depan|firstname)",
    "last": r"(last[\s_-]*name|family[\s_-]*name|surname|nama[\s_-]*belakang|lastname)",
    "email": r"(email|e[_-]?mail)",
    "telepon": r"(phone|telepon|telp|hp|mobile|whatsapp|wa|kontak|contact[_-]?number|phone[_-]?number)",
    "linkedin": r"(linkedin|profil[_-]?linkedin)",
    "portfolio": r"(portfolio|github|website|url|link[^s]|site)",
}

PROFIL_FILE = config.BASE / "profil.json"

def load_profil() -> dict:
    if not PROFIL_FILE.exists():
        raise FileNotFoundError(f"{PROFIL_FILE} tidak ada — isi data pribadi untuk autofill")
    return json.loads(PROFIL_FILE.read_text(encoding="utf-8"))

def _label(page, input_el) -> str:
    for attr in ("name", "id", "placeholder", "aria-label", "data-qa", "data-test"):
        try:
            v = input_el.get_attribute(attr) or ""
            if v.strip():
                return v.lower()
        except Exception:
            pass

    try:
        fid = input_el.get_attribute("id")
        if fid:
            lab = page.locator(f"label[for='{fid}']").first
            if lab.count():
                return (lab.inner_text() or "").lower()
    except Exception:
        pass
    return ""

def _match_field(label: str) -> str | None:
    for field, pat in FIELD_MAP.items():
        if re.search(pat, label, re.I):
            return field
    return None

def _split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split()
    if len(parts) <= 1:
        return full, ""
    return parts[0], " ".join(parts[1:])

def _fill_text(page, input_el, value: str) -> bool:
    try:
        input_el.click(); page.wait_for_timeout(200)
        input_el.fill(value); page.wait_for_timeout(200)
        return True
    except Exception:
        try:
            input_el.evaluate("(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); }", value)
            return True
        except Exception:
            return False

def autofill(page, cv_path: Path | None = None, verbose: bool = True) -> dict:
    prof = load_profil()
    cv_path = cv_path or (config.BASE / prof.get("cv_file", "cv.pdf"))
    stat = {"filled": [], "skipped": [], "uploaded": False}

    inputs = page.locator("input:visible, textarea:visible")
    n = inputs.count()
    seen_names = set()
    for i in range(n):
        el = inputs.nth(i)
        try:
            etype = (el.get_attribute("type") or "").lower()
        except Exception:
            etype = ""
        if etype in ("hidden", "submit", "button", "checkbox", "radio"):
            continue

        label = _label(page, el)
        if not label:
            continue
        key = label[:80]
        if key in seen_names:
            continue
        seen_names.add(key)

        if etype == "file":
            if cv_path.exists():
                try:
                    el.set_input_files(str(cv_path))
                    stat["uploaded"] = True
                    stat["filled"].append(f"[CV]{cv_path.name}")
                except Exception as ex:
                    stat["skipped"].append(f"[CV] {ex}")
            continue

        field = _match_field(label)
        if not field:
            stat["skipped"].append(label[:40])
            continue

        if field in ("first", "last"):
            first, last = _split_name(prof.get("nama", ""))
            value = first if field == "first" else last
        else:
            value = prof.get(field, "")
        if not value:
            stat["skipped"].append(label[:40])
            continue

        if _fill_text(page, el, value):
            stat["filled"].append(f"{field} <- '{label[:30]}'")

    if verbose:
        print(f"  [autofill] terisi: {len(stat['filled'])}, dilewati: {len(stat['skipped'])}, CV: {stat['uploaded']}")
        for f in stat["filled"]:
            print(f"    + {f}")
    return stat

def cover_letter(page, prof: dict | None = None) -> int:
    prof = prof or load_profil()
    text = prof.get("cover_letter", "")
    if not text:
        return 0
    tas = page.locator("textarea:visible")
    n = tas.count()
    filled = 0
    for i in range(n):
        el = tas.nth(i)
        try:
            label = _label(page, el)
        except Exception:
            label = ""
        if re.search(r"cover|motivation|message|why|tell|describe|additional|ringkasan|alasan|ceritakan", label, re.I) or not label:
            try:
                el.fill(text); filled += 1
            except Exception:
                pass
    return filled

_GLINTS_TECH_MID = "INTERMEDIATE"
_GLINTS_TECH_HIGH = "ADVANCED"
_GLINTS_LANG_MID = "CONVERSATIONAL"
_GLINTS_LANG_HIGH = "PROFESSIONAL"
_GLINTS_LANG_NONE = "NONE"
_GLINTS_EXP_LT1Y = "LESS_THAN_ONE_YEAR"

_KNOWN_LANGUAGES = {"indonesian", "bahasa indonesia", "indonesia", "id",
                    "english", "inggris", "bahasa inggris", "en"}

_CV_TEXT_CACHE: str | None = None

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def fill_glints_skill_ratings(page, cv_text: str | None = None, verbose: bool = True) -> dict:
    stat = {"filled": 0, "in_cv": [], "menengah": []}
    global _CV_TEXT_CACHE
    if cv_text is None:
        if _CV_TEXT_CACHE is None:
            try:
                from cv import extract_text
                cv_path = config.CV_DEFAULT if hasattr(config, "CV_DEFAULT") else (config.BASE / "cv.pdf")
                _CV_TEXT_CACHE = extract_text(cv_path)
            except Exception as e:
                if verbose:
                    print(f"    [skill] gagal baca CV: {e}")
                _CV_TEXT_CACHE = ""
        cv_text = _CV_TEXT_CACHE
    cv_norm = {_norm(w) for w in re.findall(r"[A-Za-z][A-Za-z0-9.+#/\- ]{1,30}", cv_text or "")}
    cv_low = (cv_text or "").lower()

    def _in_cv(skill_name: str) -> bool:
        name = (skill_name or "").strip()
        if not name:
            return False
        n = _norm(name)
        if n in cv_norm:
            return True

        tokens = [t.strip() for t in re.split(r"[\s,/]+", name) if t.strip()]
        if len(tokens) > 1:

            words = [w for w in (_norm(t) for t in tokens) if w and w not in {"bahasa", "the", "of"}]
            return bool(words) and all(w in cv_low for w in words)

        if name.lower() in cv_low:
            return True
        base = name.split(".")[0].strip()
        return len(base) >= 3 and base.lower() in cv_low

    groups = page.evaluate("""() => {
        const radios = [...document.querySelectorAll('input[type=radio]')].filter(el => el.offsetParent);
        const byName = new Map();
        for (const r of radios) {
            const nm = r.name || '';
            if (!byName.has(nm)) byName.set(nm, {name: nm, label: '', values: []});
            const g = byName.get(nm);
            g.values.push(r.value);
            if (!g.label) {
                // label skill biasanya muncul sbg teks di sekitar grup radio
                let p = r.closest('div, section, fieldset, li');
                for (let i = 0; i < 4 && p; i++) {
                    const t = (p.innerText || '').trim().split('\\n')[0] || '';
                    if (t && t.length <= 40 && !/^(Tidak|Dasar|Menengah|Ahli|Profesional|Mahir|NONE|BASIC|INTERMEDIATE|ADVANCED|NO_EXPERIENCE|CONVERSATIONAL|PROFESSIONAL|NATIVE)/i.test(t)) {
                        g.label = t; break;
                    }
                    p = p.parentElement;
                }
            }
        }
        return [...byName.values()];
    }""")

    for g in groups:
        name, label = g["name"], g["label"]
        values = g["values"]
        if not values:
            continue

        if name == "WORK_EXPERIENCE_DURATION":
            target = _GLINTS_EXP_LT1Y if _GLINTS_EXP_LT1Y in values else values[-1]
            try:
                page.locator(f"input[type=radio][name='{name}'][value='{target}']").first.check(force=True)
                stat["filled"] += 1
                if verbose:
                    print(f"    [pengalaman] -> {target}")
            except Exception as e:
                if verbose:
                    print(f"    [pengalaman] GAGAL -> {target}: {e}")
            continue

        is_tech = "INTERMEDIATE" in values and "ADVANCED" in values

        is_lang = (not is_tech) and (len(name) <= 3 or "NONE" in values
                                    or "bahasa" in (label or "").lower())


        if is_tech and "bahasa" in (label or "").lower():
            lbl_low = (label or "").lower()
            known = any(kw in lbl_low for kw in _KNOWN_LANGUAGES)
            target = _GLINTS_TECH_HIGH if known else "BASIC"
            if target not in values:
                target = _GLINTS_TECH_MID if _GLINTS_TECH_MID in values else values[-1]
            try:
                page.locator(f"input[type=radio][name='{name}'][value='{target}']").first.check(force=True)
                stat["filled"] += 1
                (stat["in_cv"] if known else stat["menengah"]).append(label or name)
                if verbose:
                    print(f"    [bahasa-scale] {label or name} -> {target}")
            except Exception as e:
                if verbose:
                    print(f"    [bahasa-scale] GAGAL {label or name}: {e}")
            continue
        if is_tech:
            target = _GLINTS_TECH_HIGH if (label and _in_cv(label)) else _GLINTS_TECH_MID
            if target not in values:
                target = _GLINTS_TECH_MID if _GLINTS_TECH_MID in values else values[-1]
            try:
                page.locator(f"input[type=radio][name='{name}'][value='{target}']").first.check(force=True)
                stat["filled"] += 1
                (stat["in_cv"] if target == _GLINTS_TECH_HIGH else stat["menengah"]).append(label or name)
                if verbose:
                    print(f"    [skill] {label or name} -> {target}{' (dari CV)' if target == _GLINTS_TECH_HIGH else ' (menengah)'}")
            except Exception as e:
                if verbose:
                    print(f"    [skill] GAGAL {label or name} -> {target}: {e}")
            continue
        if is_lang:

            lbl_low = (label or "").strip().lower()
            known = any(kw in lbl_low for kw in _KNOWN_LANGUAGES) if lbl_low else False
            target = _GLINTS_LANG_MID if known else _GLINTS_LANG_NONE
            if target not in values:
                target = values[0]
            try:
                page.locator(f"input[type=radio][name='{name}'][value='{target}']").first.check(force=True)
                stat["filled"] += 1
                (stat["in_cv"] if target == _GLINTS_LANG_MID else stat["menengah"]).append(label or name)
                if verbose:
                    ket = "Menengah" if known else "Tidak bisa"
                    print(f"    [bahasa] {label or name} -> {target} ({ket})")
            except Exception as e:
                if verbose:
                    print(f"    [bahasa] GAGAL {label or name} -> {target}: {e}")
            continue
    return stat
