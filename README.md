# IMC-MASK Muallaf Bot RAG

Repositori ini adalah versi publik untuk kebutuhan dokumentasi skripsi. Isi repo difokuskan pada alur penelitian:

© 2026 Copyright by Muhammad Wildan Kamil, Afrida Helen, Mira Suryani.

- halaman Muallaf Bot sebagai halaman utama;
- backend FastAPI;
- pipeline Retrieval-Augmented Generation berbasis LangChain;
- guardrail dan fallback;
- login, sesi, dan histori percakapan lintas perangkat;
- retensi data 30 hari serta kontrol privasi;
- PostgreSQL eksternal untuk data aplikasi;
- script build knowledge base;
- script evaluasi dan contoh output CLI.

Fitur admin dashboard dan aset privat tidak disertakan dalam versi publik ini.

## Deployment tanpa komputer menyala

Panduan produksi Google Cloud Run + Neon tersedia di
[`deploy/cloud-run/README.md`](deploy/cloud-run/README.md). Deployment tersebut
tidak memerlukan Ubuntu atau server pribadi: proses build dan deployment dapat
dijalankan seluruhnya melalui Google Cloud Shell di browser. Konfigurasi memakai
scale-to-zero dan maksimum satu instance untuk menekan penggunaan free tier.

## Struktur

```text
backend/
  app/                         # FastAPI, RAG pipeline, preprocessing, vector store
  scripts/                     # build knowledge base, evaluasi RAGAS, contoh CLI
  data/
    raw_pdfs/                  # PDF rujukan publik yang sudah diizinkan
    processed/                 # chunks.json hasil build, belum ikut Git
    vector_db/                 # embeddings/vector store, belum ikut Git
frontend/
  src/                         # Halaman Muallaf Bot
docs/
  ragas_evaluation_questions_template.csv
```

## Catatan Keamanan

File berikut tidak disertakan ke GitHub:

- `.env`;
- API key Gemini;
- `chunks.json`;
- embeddings/vector DB;
- log;
- file evaluasi `.xlsx`;
- artefak model besar.

Gunakan `backend/.env.example` sebagai template konfigurasi lokal.

Endpoint chat dan histori memerlukan token login. Password disimpan sebagai
hash PBKDF2-SHA256 dengan salt unik; token browser hanya dipertahankan selama
tab aktif. Endpoint debug nonaktif secara default dan, jika sengaja diaktifkan,
hanya dapat dibuka oleh akun berperan admin.

Riwayat percakapan disimpan di database dan kedaluwarsa 30 hari setelah
aktivitas terakhir. Pengguna dapat memulai serta menghapus sesi sendiri.
Pemberitahuan privasi tersedia di `GET /api/privacy` dan ditampilkan sebelum
pendaftaran akun.

## Menjalankan Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
Copy-Item .env.example .env
```

Isi `GEMINI_API_KEY` di `backend/.env` jika memakai Gemini. Mode `auto` hanya
menggunakan Gemini yang dikonfigurasi; bila gagal sistem beralih ke jawaban
ekstraktif deterministik dari dokumen, bukan ke model lokal yang belum lolos
evaluasi. Provider Ollama tetap tersedia hanya untuk eksperimen lokal eksplisit.

Untuk pengembangan lokal, gunakan `DATABASE_URL=sqlite:///data/app.db`. Untuk
produksi, gunakan connection string PostgreSQL eksternal dan ganti `JWT_SECRET`.

Jalankan FastAPI:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Build Knowledge Base

PDF rujukan sudah tersedia di:

```text
backend/data/raw_pdfs/
```

Lalu jalankan:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\build_knowledge_base.py
```

Output lokal yang terbentuk:

- `backend/data/processed/chunks.json`;
- `backend/data/vector_db/embeddings.npy`;
- metadata embeddings.

File output ini tidak diunggah ke GitHub karena berisi hasil ekstraksi dokumen rujukan.
Untuk saat ini proses uji coba tetap difokuskan di repo utama `imc-mask`; `processed` dan `vector_db` akan dimasukkan ke versi publik setelah hasilnya stabil.

### Penyimpanan PDF publik

PDF rujukan publik disimpan di `backend/data/raw_pdfs/` dan ikut tercatat di
Git. Empat PDF saat ini berukuran total sekitar 16 MB, sehingga masih layak
dibawa bersama deployment backend. Endpoint berikut digunakan oleh viewer:

```text
GET /api/documents/files/{nama-file.pdf}
GET /api/documents/download/{nama-file.pdf}
```

Tautan rujukan PDF membuka viewer internal Muallaf Bot. Viewer menyediakan
tombol kembali tanpa menghapus riwayat chat, tombol buka pada tab baru, dan
tombol unduh. Rujukan Website IMC-MASK hanya ditampilkan sebagai teks dan belum
dapat dibuka. Jika jumlah atau ukuran PDF bertambah besar, pindahkan berkas ke
object storage permanen dan pertahankan nama atau ID dokumen pada metadata
knowledge base.

### Troubleshooting build knowledge base

Jika proses menghasilkan `chunks.json` tetapi menampilkan pesan berikut:

```text
The paging file is too small for this operation to complete. (os error 1455)
```

ekstraksi PDF sudah berhasil, tetapi Windows tidak memiliki RAM/virtual memory
yang cukup untuk memuat model embedding. Tutup aplikasi yang banyak memakai
memori atau tambah ukuran paging file Windows, buka terminal baru, lalu jalankan
ulang `scripts\build_knowledge_base.py`. Peringatan `HF_TOKEN` bukan penyebab
kegagalan; token hanya memengaruhi rate limit dan kecepatan unduhan model.

## Menjalankan Frontend

```powershell
cd frontend
npm install
npm run dev
```

Buka halaman chatbot:

```text
http://localhost:5173
```

Frontend memulihkan riwayat chat dari database setelah pengguna login. Request
yang masih diproses dipulihkan setelah halaman dimuat ulang dalam tab yang sama.
Indikator berpikir ditampilkan sekurang-kurangnya
sekitar 5 detik, sedangkan request yang belum selesai setelah 90 detik dihentikan
dengan pesan kesalahan agar antarmuka tidak menggantung tanpa batas.

## Pengamanan Produksi

Deployment produksi wajib menggunakan Cloudflare Worker sebagai gateway,
Turnstile, Modal Proxy Auth, origin secret, dan rate limit berlapis. Ikuti
prosedur pada [`docs/SECURITY_DEPLOYMENT.md`](docs/SECURITY_DEPLOYMENT.md)
sebelum push atau deploy perubahan keamanan.

Tombol `Kirim Feedback` membuka formulir bawaan. Identitas bersifat opsional,
sedangkan email dan isi feedback wajib diisi. Feedback dikirim ke
`mwildankamil@gmail.com` dengan subjek `Feedback Muallaf Bot`, lalu disimpan
sebagai cadangan JSON Lines di `backend/data/feedback/feedback.jsonl`.
Direktori tersebut diabaikan Git agar data pengguna tidak ikut terpublikasi.

Aktifkan pengiriman email melalui `backend/.env`:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=alamat-pengirim@gmail.com
SMTP_PASSWORD=app_password_gmail
SMTP_FROM_EMAIL=alamat-pengirim@gmail.com
FEEDBACK_RECIPIENT=mwildankamil@gmail.com
FEEDBACK_SUBJECT=Feedback Muallaf Bot
FEEDBACK_RATE_LIMIT_SECONDS=900
TRUST_PROXY_HEADERS=false
```

Untuk Gmail, aktifkan verifikasi dua langkah lalu buat App Password. Jangan
memasukkan password akun Gmail biasa dan jangan commit file `.env`. Backend
membatasi satu percobaan feedback per alamat IP setiap 15 menit. Frontend juga
menyimpan cooldown 15 menit di browser. Setelah berhasil, form berubah menjadi
konfirmasi ringkas dan menutup otomatis setelah lima detik. Aktifkan `TRUST_PROXY_HEADERS=true`
hanya jika deployment berada di belakang reverse proxy tepercaya yang mengatur
header `X-Forwarded-For`.

## Dokumentasi Respons

Tangkapan layar kondisi awal serta contoh respons substantif, klarifikasi
ambigu, personal legal/religious, krisis keselamatan, dan pertanyaan di luar
konteks tersedia di:

```text
docs/screenshots/
```

Lihat `docs/screenshots/README.md` untuk pertanyaan, mode respons, dan cara
membuat ulang screenshot dari endpoint chatbot yang sedang berjalan.

## Contoh CLI Untuk Skripsi

Contoh retrieval konteks:

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\print_retrieval_context_examples.py --question "Saya ingin syahadat di Masjid Agung Sunda Kelapa, prosesnya bagaimana?" --top-k 4
```

Contoh fallback di luar konteks:

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\print_chat_cli_examples.py --case out_of_scope --static
```

Evaluasi guardrail per kategori (hasil JSON dapat dipakai untuk tabel skripsi):

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\evaluate_guardrails.py --output docs\guardrail_results.json
```

Laporan memisahkan support, precision, recall, dan F1 untuk setiap kategori;
angka rata-rata tidak digunakan sebagai pengganti rincian kategori. Script
menolak laporan final jika dataset kurang dari 100 kasus. Dataset bawaan hanya
contoh smoke test; jalankan dengan `--minimum-cases 1` untuk memeriksa mekanisme,
lalu perluas dan validasi labelnya bersama pembina sebelum dipakai dalam skripsi.

## Keamanan dan lisensi

Laporkan kerentanan secara privat mengikuti [`SECURITY.md`](SECURITY.md). Jangan
memasukkan API key, password, connection string, token, atau data pengguna ke
issue, pull request, log, dan commit.

Kode sumber dan dokumentasi proyek tersedia berdasarkan [Lisensi MIT](LICENSE).
PDF knowledge base, logo, identitas organisasi, serta materi pihak ketiga tidak
dilisensikan ulang berdasarkan MIT. Rincian pengecualian tersedia di
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Publikasi

Panduan deployment manual gratis dengan Cloudflare Pages, Oracle Cloud, Neon,
Caddy, Docker Compose, dan timer retensi tersedia di `deploy/README.md`.

Repo ini sudah terhubung ke remote GitHub. Untuk publish perubahan public saat ini:

```powershell
cd chatbot-public
git status --short
git add -A
git restore --staged -- backend/data/processed backend/data/vector_db
git add backend/data/processed/.gitkeep backend/data/vector_db/.gitkeep
git commit -m "Update public Muallaf Bot research version"
git push origin HEAD:master
```

Perintah `git restore --staged` menjaga agar `processed` dan `vector_db` belum
ikut dipublish. Raw PDF publik tetap masuk commit.
