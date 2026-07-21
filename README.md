# IMC-MASK Muallaf Bot RAG

Repositori ini adalah versi publik untuk kebutuhan dokumentasi skripsi. Isi repo difokuskan pada alur penelitian:

- halaman Beranda IMC-MASK;
- halaman penuh Muallaf Bot;
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
    raw_pdfs/                  # tempat PDF rujukan lokal, tidak ikut Git
    processed/                 # chunks.json hasil build, tidak ikut Git
    vector_db/                 # embeddings/vector store, tidak ikut Git
frontend/
  src/                         # Beranda dan halaman Muallaf Bot
docs/
  ragas_evaluation_questions_template.csv
```

## Catatan Keamanan

File berikut tidak disertakan ke GitHub:

- `.env`;
- API key Gemini;
- PDF rujukan;
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

Letakkan PDF rujukan di:

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

## Menjalankan Frontend

```powershell
cd frontend
npm install
npm run dev
```

Buka:

```text
http://localhost:5173
```

Halaman chatbot tersedia di:

```text
http://localhost:5173/bot
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

Folder ini dapat dijadikan repo GitHub terpisah:

```powershell
cd chatbot-public
git init
git add .
git commit -m "Initial public research version of IMC-MASK Muallaf Bot"
git branch -M main
git remote add origin https://github.com/USERNAME/imc-mask-muallaf-bot-rag.git
git push -u origin main
```
