# IMC-MASK Muallaf Bot RAG

Repositori ini adalah versi publik untuk kebutuhan dokumentasi skripsi. Isi repo difokuskan pada alur penelitian:

© 2026 Copyright by Muhammad Wildan Kamil, Afrida Helen, Mira Suryani.

- halaman Muallaf Bot sebagai halaman utama;
- backend FastAPI;
- pipeline Retrieval-Augmented Generation berbasis LangChain;
- guardrail dan fallback;
- script build knowledge base;
- script evaluasi dan contoh output CLI.

Fitur admin dashboard dan aset privat tidak disertakan dalam versi publik ini.

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

## Menjalankan Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
Copy-Item .env.example .env
```

Isi `GEMINI_API_KEY` di `backend/.env` jika memakai Gemini. Jika ingin offline, jalankan Ollama dan gunakan provider `ollama` atau `auto`.

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

Untuk menampilkan tombol feedback, buat Google Form lalu isi URL-nya di
`frontend/.env`:

```text
VITE_FEEDBACK_URL=https://forms.gle/ID_FORM_ANDA
```

## Contoh CLI Untuk Skripsi

Contoh retrieval konteks:

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\print_retrieval_context_examples.py --question "Saya ingin syahadat di Masjid Agung Sunda Kelapa, prosesnya bagaimana?" --top-k 4
```

Contoh fallback di luar konteks:

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\print_chat_cli_examples.py --case out_of_scope --static
```

## Publikasi

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
