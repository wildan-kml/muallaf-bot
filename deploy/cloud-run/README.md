# Deployment Google Cloud Run + Neon (tanpa Ubuntu lokal)

Arsitektur:

```text
Cloudflare Pages -> Cloud Run (FastAPI, scale-to-zero) -> Neon PostgreSQL + pgvector
```

Cloud Run memakai `min-instances=0`, maksimum satu instance, satu CPU, dan RAM
2 GiB. Konfigurasi ini ditujukan untuk demo skripsi serta trafik ringan, bukan
jaminan biaya absolut Rp0. Free tier adalah jatah penggunaan; budget Google
Cloud hanya memberi peringatan dan **tidak otomatis menghentikan biaya**.
Container machine-learning kemungkinan lebih besar dari jatah gratis Artifact
Registry 0,5 GiB, sehingga komponen penyimpanan image dapat menghasilkan biaya
kecil walaupun pemakaian Cloud Run masih di dalam free tier.

Semua perintah berikut dijalankan melalui **Google Cloud Shell** di browser.
Komputer pribadi tidak perlu menyala setelah deployment.

## 1. Prasyarat

1. Buat project Google Cloud dan hubungkan billing account.
2. Buat project Neon, aktifkan ekstensi `vector`, lalu salin connection string
   pooled yang berakhiran `sslmode=require`.
3. Siapkan URL frontend Cloudflare Pages dan API key Gemini.
4. Fork/push repository ke GitHub milik Anda agar Cloud Shell dapat mengambilnya.

## 2. Isi variabel Cloud Shell

Jangan menempelkan secret ke dalam repository. Ganti nilai contoh berikut:

```bash
export PROJECT_ID="project-google-cloud-anda"
export REGION="asia-southeast2"
export REPOSITORY="muallaf-bot"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/api:latest"
export FRONTEND_ORIGIN="https://nama-proyek.pages.dev"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

Region `asia-southeast2` berada di Jakarta. Jika layanan tidak tersedia pada
akun Anda, gunakan `asia-southeast1` (Singapura). Jakarta dan Singapura memakai
harga Cloud Run Tier 2; free tier tetap diperhitungkan sebagai diskon berdasarkan
harga Tier 1, sehingga trafik harus tetap dipantau.

## 3. Buat registry dan build satu image

Dari root repository:

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker --location="$REGION" \
  --description="Muallaf Bot Cloud Run images"

gcloud builds submit backend --tag "$IMAGE"
```

Model embedding ikut disimpan di image agar cold start tidak perlu mengunduh
model lagi. Build memakai wheel PyTorch CPU dan requirements khusus Cloud Run;
dependensi Ollama dan FAISS lokal tidak ikut dimasukkan. Pertahankan hanya versi
image yang masih dipakai untuk membatasi penyimpanan Artifact Registry.

## 4. Simpan secret

Perintah berikut meminta nilai secara tersembunyi dan mengirimkannya langsung
ke Secret Manager:

```bash
read -rsp "DATABASE_URL Neon: " VALUE && echo && printf %s "$VALUE" | \
  gcloud secrets create muallaf-database-url --data-file=-
unset VALUE

read -rsp "JWT secret (minimal 32 karakter): " VALUE && echo && printf %s "$VALUE" | \
  gcloud secrets create muallaf-jwt-secret --data-file=-
unset VALUE

read -rsp "Gemini API key: " VALUE && echo && printf %s "$VALUE" | \
  gcloud secrets create muallaf-gemini-key --data-file=-
unset VALUE
```

Izinkan runtime Cloud Run membaca secret:

```bash
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
for SECRET in muallaf-database-url muallaf-jwt-secret muallaf-gemini-key; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

## 5. Bangun knowledge base sebagai Cloud Run Job

Job membaca PDF dari image dan menulis index secara transaksional ke Neon.
Jalankan kembali job hanya setelah PDF atau model embedding berubah.

```bash
gcloud run jobs deploy muallaf-kb-build \
  --image="$IMAGE" --region="$REGION" \
  --command=python --args=scripts/build_knowledge_base.py \
  --set-env-vars="APP_ENV=production,VECTOR_DB_TYPE=pgvector,EMBEDDING_BATCH_SIZE=8" \
  --set-secrets="DATABASE_URL=muallaf-database-url:latest" \
  --cpu=2 --memory=4Gi --task-timeout=30m --max-retries=1

gcloud run jobs execute muallaf-kb-build --region="$REGION" --wait
```

Perintah kedua harus berakhir sukses sebelum API dideploy. Jika gagal, index
lama tetap dipertahankan.

## 6. Deploy API dengan scale-to-zero

```bash
gcloud run deploy muallaf-bot-api \
  --image="$IMAGE" --region="$REGION" --allow-unauthenticated \
  --cpu=1 --memory=2Gi --concurrency=4 --min-instances=0 --max-instances=1 \
  --timeout=300 --cpu-throttling \
  --set-env-vars="APP_ENV=production,VECTOR_DB_TYPE=pgvector,RAG_ENGINE=langchain,LLM_PROVIDER=auto,GEMINI_MODEL=gemini-3.5-flash-lite,CHAT_RETENTION_DAYS=30,ALLOW_REGISTRATION=true,DEBUG_ENDPOINT_ENABLED=false,TRUST_PROXY_HEADERS=true,FRONTEND_ORIGIN=$FRONTEND_ORIGIN,CORS_ORIGINS=$FRONTEND_ORIGIN" \
  --set-secrets="DATABASE_URL=muallaf-database-url:latest,JWT_SECRET=muallaf-jwt-secret:latest,GEMINI_API_KEY=muallaf-gemini-key:latest"

export API_URL="$(gcloud run services describe muallaf-bot-api \
  --region="$REGION" --format='value(status.url)')"
curl "$API_URL/api/health"
```

`min=0` memungkinkan instance tidur ketika tidak digunakan. Permintaan pertama
setelah idle dapat lebih lambat, tetapi URL tetap tersedia tanpa komputer
pribadi yang menyala.

## 7. Hubungkan frontend

Di Cloudflare Pages, ubah environment variable berikut lalu deploy ulang:

```text
VITE_API_URL=<nilai API_URL dari langkah 6>
```

Pastikan `FRONTEND_ORIGIN` pada Cloud Run sama persis dengan URL Pages. Jika URL
frontend berubah, perbarui Cloud Run melalui dashboard atau deploy ulang.

## 8. Kontrol biaya

1. Buka **Billing > Budgets & alerts**, buat peringatan pada 50%, 90%, dan 100%.
2. Pertahankan `min instances = 0` dan `max instances = 1`.
3. Jangan mengaktifkan instance-based billing atau minimum instance.
4. Hapus image lama yang tidak dipakai dari Artifact Registry.
5. Pantau pemakaian Cloud Run, Cloud Build, Artifact Registry, Neon, dan Gemini.
6. Periksa ukuran image: Artifact Registry hanya menggratiskan 0,5 GiB pertama
   per billing account; image yang lebih besar dikenai tarif penyimpanan.

Tidak ada hard spending cap bawaan Cloud Run. Jika syarat utama adalah mustahil
ditagih, jangan menghubungkan payment method; konsekuensinya Cloud Run tidak
dapat digunakan. Untuk proyek dengan billing aktif, alert dan pembatasan
instance di atas mengurangi risiko tetapi tidak menghapusnya sepenuhnya.

## 9. Verifikasi

```bash
curl "$API_URL/api/health"
curl "$API_URL/api/chat/model-status"
curl "$API_URL/api/documents"
```

Lalu uji dari browser: daftar dengan persetujuan privasi, login, buat dua sesi,
muat ulang, pastikan histori kembali, dan hapus salah satu sesi.
