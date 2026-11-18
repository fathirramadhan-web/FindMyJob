# JobBot — otomasi lamaran kerja

Alur: analisis CV -> cari lowongan (headless=False) -> catat & skor di spreadsheet
-> ACC manual di Google Sheet -> apply manual (cek sebelum submit).

## Setup

```bash
cd C:/Users/fathi/jobbot
python -c "import playwright, pdfplumber, openpyxl; print('deps ok')"
python -m playwright install chromium
```

Letakkan CV sebagai `cv.pdf` (atau `--cv file.txt`).

## Kredensial

File `account.txt` / `account2.txt` (sudah di .gitignore):

```
email=alamat@gmail.com
password=secret
```

Satu kali login Google supaya session tersimpan di `browser_profile/`:

```bash
python main.py open --site glints
```

Script mengisi email+password dari file kredensial. Kena 2FA/challenge ->
selesaikan MANUAL di browser yang terbuka (headless=False).

## Perintah

```
python main.py profil [--cv file]            # ringkasan skill dari CV
python main.py cari [--site indeed|linkedin|jobstreet|glints] \
                    [--q "react developer"] [--loc jakarta,bandung]
python main.py review                        # daftar lowongan + skor
python main.py acc <id-prefix> ya|tidak      # setujui / tolak
python main.py rapikan                       # gabung duplikat
python main.py reskor                        # hitung ulang skor dgn CV
python main.py sinkron / tarik               # Google Sheet <-> lokal
python main.py open --site <situs>           # login manual
python main.py jalankan                      # tarik + 4 situs + reskor + sinkron + cek ACC
```

Query dan role diturunkan dari CV, bukan hardcode (lihat `cv.py`).

## Spreadsheet

Sumber data: `jobs-pipeline.xlsx`. Tampilan + input ACC: Google Sheet
(`GSHEET_SHEET_URL` di config.py). `sinkron` = clear+paste TSV via browser;
`tarik` = export CSV lalu merge kolom acc/tahap/catatan. Tanpa API key.

Kolom: id, perusahaan, posisi, sumber, lokasi, gaji, ditemukan, deskripsi, link,
skor, skill_cocok, skill_kurang, acc (ya/tidak), tahap, tanggal_apply, catatan.

Tahap: perlu-review -> disetujui/ditolak -> siap-apply -> terkirim -> interview ->
ditolak-perusahaan / ditutup.

## Catatan

- Scraping & apply DISUAIKAN dengan syarat situs; LinkedIn, Indeed, JobStreet
  membatasi otomasi. Tidak ada bypass CAPTCHA. Kena anti-bot -> script berhenti,
  minta solve manual.
- Apply TIDAK otomatis submit. Script buka lowongan, kamu isi & cek dulu.
- Selector situs bisa berubah; kalau `cari` hasil 0, probe layout baru dulu
  (skill playwright-scraping -> references/jobbot-layout.md).
- Dedup = sha1(perusahaan|posisi ternormalisasi), lintas situs & lintas bentuk
  link. `rapikan` membersihkan duplikat yang sudah masuk.

## Otomasi (Windows Task Scheduler)

```
schtasks /query | findstr JobBot
```

- **JobBot Scraping** — tiap 2 jam, jalankan `jalankan.bat` (scraping 4 situs + sinkron)
- **JobBot CekACC** — tiap 10 menit, jalankan `cek_acc.bat` (tarik editan dari Google Sheet + notifikasi Windows bila ada lowongan di-ACC)

Hapus task:
```
schtasks /delete /tn "JobBot Scraping" /f
schtasks /delete /tn "JobBot CekACC" /f
```

Alur: analisis CV → scraping (otomatis, tiap 2 jam) → simpan di Sheet (otomatis) → kamu ACC manual di Google Sheet → notifikasi (otomatis, tiap 10 menit) → apply manual (`apply-semua`). Satu-satunya langkah manual: ACC di Sheet + isi form apply.

## File

```
config.py   lokasi, batas, aturan tiap situs
gm.py       login Google/SSO (headless=False, profile persisten)
list_acc.py cetak baris ACC (dipakai notify_acc.ps1)
cek_acc.bat + notify_acc.ps1  cron: tarik ACC + notifikasi Windows
jalankan.bat                  cron: scraping penuh
cv.py       ekstrak teks CV + profil + skor
hunt.py     scraping listing + deskripsi (infinite scroll, guest API)
sheet.py    spreadsheet xlsx + dedup
gsheet.py   sinkron Google Sheet via browser
main.py     CLI
```
