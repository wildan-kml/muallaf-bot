# Panduan Screenshot Skripsi Muallaf Bot

Panduan ini memakai kode dan artefak terbaru di `D:\imc-mask\chatbot-public`.
Jangan tampilkan `.env`, API key, URL Neon, JWT secret, atau secret Cloudflare di
dalam screenshot.

## Persiapan tampilan

- Gunakan zoom terminal dan editor 110-125% agar teks terbaca setelah masuk Word.
- Maksimalkan jendela dan tutup panel yang tidak relevan.
- Gunakan tema yang sama untuk seluruh screenshot.
- Potong gambar hanya pada area penting, tetapi sisakan nama berkas atau perintah.
- Simpan sebagai PNG, bukan hasil kompresi aplikasi pesan.

## A. Pembangunan knowledge base di terminal

Jalankan dari PowerShell:

```powershell
cd D:\imc-mask\chatbot-public
.\backend\.venv\Scripts\python.exe .\backend\scripts\build_knowledge_base.py
```

Ambil screenshot setelah baris `knowledge base build complete` muncul. Bagian
yang sebaiknya terlihat adalah daftar dokumen, jumlah halaman, jumlah chunk,
model embedding, dan status embeddings. Perintah ini benar-benar membangun
ulang indeks. Gunakan hanya ketika ingin memperbarui knowledge base.

Untuk screenshot bukti tanpa mengubah indeks atau database, jalankan:

```powershell
cd D:\imc-mask\chatbot-public
.\backend\.venv\Scripts\python.exe .\backend\scripts\print_knowledge_base_evidence.py
```

Caption yang disarankan:

> Proses verifikasi pembangunan knowledge base Muallaf Bot yang menampilkan
> dokumen sumber, jumlah halaman, jumlah chunk, model embedding, dan konsistensi
> matriks embedding.

## B. Kode ekstraksi dokumen dan transaction-safe build

Buka berkas berikut di VS Code:

- `backend/app/document_loader.py`, fungsi `load_pdf_pages()`;
- `backend/scripts/build_knowledge_base.py`, fungsi `main()`.

Tampilkan bagian fallback PyMuPDF ke pdfplumber serta staging directory sebelum
indeks aktif diganti.

Caption:

> Implementasi ekstraksi dokumen PDF dengan fallback extractor dan mekanisme
> transactional build untuk mencegah knowledge base parsial digunakan aplikasi.

## C. Kode pembentukan chunk

Buka `backend/app/preprocessing.py`, lalu tampilkan:

- kelas `TextChunk`;
- fungsi `chunk_text_spans()`;
- fungsi `chunk_pages()`.

Pastikan metadata `chunk_id`, `document_title`, `page_number`, dan `file_name`
terlihat. Konfigurasi default berada di `backend/app/config.py`: ukuran chunk 900
karakter dan overlap 120 karakter.

Caption:

> Pembentukan chunk berbasis batas kalimat beserta metadata sumber dan halaman
> untuk mendukung retrieval dan penayangan rujukan.

## D. Kode pembuatan embedding

Buka `backend/app/vector_store.py`, fungsi `build_vector_index()`. Tampilkan
bagian berikut dalam satu screenshot:

```python
texts = [f"passage: {chunk.content}" for chunk in chunks]
embeddings = model.encode(...)
embeddings = _normalize_matrix(embeddings)
np.save(settings.embeddings_path, embeddings)
```

Caption:

> Proses transformasi seluruh chunk menjadi embedding menggunakan model
> multilingual E5, normalisasi vektor, dan penyimpanan matriks embedding.

## E. Isi chunk dan embedding

Gunakan keluaran `print_knowledge_base_evidence.py`. Ambil dua screenshot bila
teks terlalu kecil:

1. bagian **SAMPLE CHUNK AND METADATA**;
2. bagian **EMBEDDING MATRIX**.

Embedding adalah data numerik berdimensi banyak. Untuk dokumentasi, cukup
menampilkan dimensi, norm, dan 12 nilai pertama. Jangan menampilkan seluruh
matriks karena tidak membantu pembaca.

Caption chunk:

> Contoh hasil chunking yang mempertahankan identitas dokumen dan nomor halaman
> sebagai metadata rujukan.

Caption embedding:

> Contoh representasi vektor suatu chunk dan verifikasi kesesuaian jumlah chunk
> dengan baris matriks embedding.

## F. Retrieval dan pembentukan jawaban RAG

Buka `backend/app/vector_store.py`, fungsi `retrieve()`, kemudian
`backend/app/rag_pipeline.py`. Tampilkan alur query embedding, semantic score,
lexical score, reranking, dan konteks yang diberikan kepada model bahasa.

Caption:

> Proses retrieval hibrida yang menggabungkan kemiripan semantik, kecocokan
> leksikal, dan reranking sebelum konteks diberikan kepada model bahasa.

## G. Halaman aplikasi

Screenshot otomatis tersedia di `docs/screenshots`. Untuk membuat ulang dari
frontend terbaru, jalankan backend pada port 8000 dan preview frontend pada port
4173, kemudian jalankan:

```powershell
cd D:\imc-mask\chatbot-public
node .\scripts\capture_chat_screenshots.mjs
```

Gambar yang disarankan untuk skripsi:

1. `00-introduction.png` — halaman pengenalan;
2. `00-desktop-initial.png` — halaman utama chat;
3. `02-desktop-substantive.png` — jawaban RAG dan rujukan;
4. `10-desktop-document-viewer.png` — penampil dokumen sumber;
5. `01-mobile-initial.png` — tampilan responsif pada perangkat seluler;
6. `00-feedback.png` — halaman/form feedback;
7. halaman masuk, daftar, dan pengaturan akun dapat diambil manual bila belum
   termasuk dalam skrip otomatis.

## Urutan gambar dalam Bab Implementasi

1. Dokumen sumber.
2. Ekstraksi PDF.
3. Pembersihan dan chunking.
4. Contoh chunk dan metadata.
5. Pembuatan embedding.
6. Contoh matriks embedding.
7. Penyimpanan pada vector database.
8. Retrieval dan reranking.
9. Halaman autentikasi.
10. Halaman utama chatbot.
11. Jawaban RAG beserta rujukan.
12. Penampil dokumen sumber.
13. Pengaturan akun dan riwayat percakapan.
14. Tampilan mobile.

Dengan urutan ini, gambar membentuk satu alur implementasi dan tidak terlihat
seperti kumpulan screenshot antarmuka yang terpisah.
