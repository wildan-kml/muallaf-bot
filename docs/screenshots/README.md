# Dokumentasi Screenshot Respons

Screenshot pada folder ini diambil dari frontend `chatbot-public` dan respons
aktual endpoint `/api/chat`. Backend yang dipakai adalah repo utama karena
pipeline-nya identik dan knowledge base hasil build belum dipublikasikan ke
`chatbot-public`.

| File | Skema | Pertanyaan | Perilaku yang Ditampilkan |
| --- | --- | --- | --- |
| `00-introduction.png` | Pengenalan | - | Dialog pengenalan yang tampil saat halaman dibuka atau dimuat ulang. |
| `00-feedback.png` | Form feedback | - | Form feedback bawaan pada viewport desktop. |
| `00-feedback-success.png` | Feedback berhasil | - | Konfirmasi ringkas setelah feedback berhasil dikirim. |
| `00-reset-notice.png` | Reset chat | - | Popup lima detik saat percakapan diperbarui. |
| `00-desktop-initial.png` | Kondisi awal desktop | - | Chatbot langsung menjadi halaman utama. |
| `01-mobile-initial.png` | Kondisi awal mobile | - | Layout mobile setelah perbaikan. |
| `01b-mobile-sidebar.png` | Sidebar mobile | - | Daftar pertanyaan acak dalam panel yang dapat dibuka dan ditutup. |
| `01c-mobile-introduction-short.png` | Pengenalan layar pendek | - | Dialog pengenalan pada viewport 390 x 520. |
| `01d-mobile-feedback-short.png` | Feedback layar pendek | - | Form feedback pada viewport 390 x 520. |
| `01e-mobile-narrow.png` | Chat mobile sempit | - | Seluruh chat dan footer pada viewport 320 x 700. |
| `01f-mobile-narrow-sidebar.png` | Sidebar mobile sempit | - | Seluruh sidebar pada viewport 320 x 700. |
| `02-desktop-substantive.png` | Substantif | Apa makna dua kalimat syahadat bagi seorang Muslim? | Jawaban RAG dan sumber. |
| `03-mobile-substantive.png` | Substantif mobile | Apa makna dua kalimat syahadat bagi seorang Muslim? | Jawaban RAG dan sumber pada viewport 390 x 844. |
| `04-mobile-ambiguous-clarification.png` | Ambigu | Bagaimanacaranya | Klarifikasi tanpa retrieval substantif. |
| `05-mobile-personal-legal.png` | Personal legal/religious | Kasus hak atas harta peninggalan | Eskalasi tanpa keputusan personal. |
| `06-mobile-crisis.png` | Krisis keselamatan | Tidak ingin melanjutkan hidup | Respons keselamatan khusus krisis. |
| `07-mobile-out-of-scope.png` | Di luar konteks | Rekomendasi hotel di Bali | Penolakan singkat sesuai cakupan bot. |
| `08-desktop-structured-content.png` | Fixture tampilan | Ayat Arab dan urutan ibadah | Pemisahan blok Arab RTL dan daftar bernomor pada desktop. |
| `09-mobile-structured-content.png` | Fixture tampilan mobile | Ayat Arab dan urutan ibadah | Pemisahan blok Arab RTL dan daftar bernomor pada viewport 390 x 844. |
| `10-desktop-document-viewer.png` | Viewer PDF desktop | Modul Pembinaan Mualaf halaman 47 | Viewer internal dengan tombol kembali, buka tab baru, dan unduh. |
| `11-mobile-document-viewer.png` | Viewer PDF mobile | Modul Pembinaan Mualaf halaman 47 | Viewer internal pada viewport 390 x 844. |

`responses.json` mencatat mode, escalation, dan jumlah sumber dari setiap
respons agar dokumentasi visual dapat dicocokkan dengan keluaran API.

## Membuat Ulang

Jalankan backend pada port 8000 dan frontend production preview pada port 4173,
lalu dari root `chatbot-public` jalankan:

```powershell
node scripts\capture_chat_screenshots.mjs
```

Script juga memverifikasi bahwa pesan intro baru muncul lima detik setelah popup
ditutup, rekomendasi menyusul setelah jeda tiga detik, popup reset berlangsung
lima detik, dan dialog pengenalan maupun feedback dapat ditutup melalui backdrop.
Script memerlukan Google Chrome lokal. Tidak ada API key atau rahasia yang
ditulis ke screenshot maupun `responses.json`.
