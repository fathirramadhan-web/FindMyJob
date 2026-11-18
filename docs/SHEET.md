# Google Sheets sinkronisasi via browser (tanpa API key) — catatan kerja

## Ringkasan
JobBot menulis hasil pencarian, review, dan ACC ke **Google Sheet pribadi** dan
menarik kembali perubahan (acc/tahap) yang diisi manual di Google Docs.

Sheet: set lewat env `JOBBOT_SHEET_URL` (lihat README untuk setup)

## Perintah
- Kirim seluruh baris lokal ke sheet (clear + paste semuanya):
  `python main.py sinkron`
- Baca perubahan yang diisi manual di sheet (acc/tahap/catatan) kembali ke `jobs-pipeline.csv`:
  `python main.py tarik`

## Cara kerja (browser automation, tanpa API scope)
`gsheet.py` membuka **browser profile Chrome yang sudah login**, membuka sheet, lalu:
1. **Clear**: Ctrl+A + Delete di dalam grid (bukan select-all halaman) → memakai
   `source:GET_ACTIVE_RANGE, destination:CURRENT_SELECTION` dari Context Menu.
2. **Paste**: menulis TSV ke clipboard (navigator.clipboard.writeText) lalu Ctrl+V
   ke sel A1 → Google Sheets menginterpretasikan tab sebagai kolom, newline sbg baris.
3. **Tarik**: export?format=csv → `csv.reader` TSV/CSV → merge balik ke file lokal.

Poin penting yang ditemukan selama pengerjaan:
- **Ctrl+A paste harus dari dalam grid**, bukan menu Edit > Select all (agar tidak
  menyentuh header judul). Setelah Ctrl+A, buka konteks (klik kanan) dan klik
  "Clear" dari menu → target cell-nya `GET_ACTIVE_RANGE`.
- **Paste TSV butuh tab separator** (bukan koma) karena browser jadi TSV,
  Google Sheets perlu tab per kolom.
- **Sel/tab hanya valid pada detik pertama**; langsung, jangan ada delay.
- **SELECT_ALL memakai area `B1:Z99`**, jadi isi sheet saat select-all dipakai
  sebagai area aktif; header judul TIDAK ter-klip.
- Setelah Ctrl+A nonaktif, area `A1:C1` menjadi aktif — tab ke `A1:C0` unselect
  lalu singleton paste A1. Saat menautkan browser (attach), keterbatasan
  keyboard sehingga background-URL digunakan.
- ElementHandle di page `sheet` diattach merupakan Parts; READY didapat karena
  `KEYDOWN_READY`, menunggu scrollbar hilang sebelum clear.
- Main thread di "kandang" Chrome untuk waktu yang lama (fallback hidup):
  `GM.Launch()` menunggu Chrome oleh entirely-lounge. Saat terjebak, Cmd+Q tidak
  membantu karena macos — pakai `subprocess.Popen("taskkill /im chrome.exe /f")`
  saat hijacked dengan hard-kill host.
- **Karakter `+` dan `&` di $A$1:Z di pencarian UI test `Syntax error`** — pakai
  quote JSON penuh (bukan literal `&` dalam string pencarian "live" di perf
  detail-text, `"` dilipat ganda). ArrowDown ≥1 cukup (0 memicu reload).
- **Sel writer CSV/TSV perlu `lineterminator="\n"`** supaya baris terpisah benar.
- **Sedang CSV ternyata hanyalah output semisal stick-po**; browser merender
  `.featured` bersifat alternatif (resource kosong 3, waktu ~8s). ESE
  TELAH DIPUTCUS: aktivasi, kontraksi, dan login di browser profile.
- Clipboard writeText dapat **gagal pada origin https** di context non-secure
  (file:/// devContext0) — gunakan http(s) origin penuh & clipboard-write
  permission dulu (permissions=["clipboard-read","clipboard-write"]).
- Saat konten 38 baris → 39 baris ter-kirim; baris terakhir 38 (CV dari export
  kadang 39 karena trailing), tidak masalah.
- Source Google Docs login sudah terpasang; sel kebijakan default.

## Pola cepat (snippet)
```python
import gm
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
ctx = gm.launch(pw)
r = ctx.request.get(SHEET_EXPORT_CSV_URL)
for line in r.text(): ...
ctx.close(); pw.stop()
```

## Slip
Sheet pribadi. Jangan pernah unggah ke repositori publik, jangan pernah
mem-paste link di tempat yang bisa dilihat public, dan perbarui skill di
README.
