# Deployment manual: Cloudflare Pages + Oracle Cloud + Neon

Arsitektur produksi yang direkomendasikan:

- frontend React di Cloudflare Pages;
- backend FastAPI dan Caddy di VM Oracle Cloud Always Free;
- akun serta histori percakapan di PostgreSQL Neon;
- berkas PDF dan index RAG berada pada volume Docker VM.

## 1. Siapkan Neon

1. Buat project PostgreSQL di Neon.
2. Salin connection string dengan `sslmode=require`.
3. Jangan menaruh connection string di Git. Masukkan hanya ke `deploy/.env.production`.

Tabel akun/histori dibuat otomatis ketika API pertama kali hidup. Script build
knowledge base mengaktifkan ekstensi `vector` dan mengganti tabel embedding
secara transaksional. Aplikasi juga mendukung
`sqlite:///data/app.db` untuk pengembangan lokal, tetapi deployment produksi
harus menggunakan PostgreSQL eksternal.

## 2. Siapkan VM Oracle Cloud

Gunakan Ubuntu pada Ampere A1, buka port 22, 80, dan 443, lalu arahkan DNS
subdomain API ke IP publik VM. Pasang Git dan Docker Engine beserta plugin
Docker Compose.

```bash
sudo mkdir -p /opt/muallaf-bot
sudo chown "$USER":"$USER" /opt/muallaf-bot
git clone https://github.com/wildan-kml/muallaf-bot /opt/muallaf-bot
cd /opt/muallaf-bot/deploy
cp .env.production.example .env.production
```

Isi `API_DOMAIN`, `DATABASE_URL`, `JWT_SECRET`, origin frontend, Gemini, dan SMTP.
Buat secret minimal 32 byte dengan `openssl rand -hex 32`.

```bash
docker compose up -d --build
docker compose exec api python scripts/build_knowledge_base.py
docker compose restart api
curl https://api.example.com/api/health
```

Build knowledge base bersifat atomik: bila satu PDF gagal diekstrak atau model
embedding gagal, index aktif sebelumnya tidak diganti.

## 3. Aktifkan pembersihan histori harian

```bash
sudo cp muallaf-bot-retention.service /etc/systemd/system/
sudo cp muallaf-bot-retention.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now muallaf-bot-retention.timer
systemctl list-timers muallaf-bot-retention.timer
```

Pembersihan berjalan pukul 02.00 WIB. API juga melakukan lazy purge saat daftar
sesi dibuka dan melakukan purge saat startup, sehingga retensi tetap berjalan
meskipun timer sempat terlewat.

## 4. Deploy frontend ke Cloudflare Pages

1. Hubungkan repository di dashboard Cloudflare Pages.
2. Root directory: `frontend`.
3. Build command: `npm ci && npm run build`.
4. Output directory: `dist`.
5. Tambahkan `VITE_API_URL=https://api.example.com`.
6. Ganti `https://api.example.com` pada `frontend/public/_headers` dengan domain API sebenarnya sebelum build.
7. Tambahkan URL Pages yang final ke `FRONTEND_ORIGIN` dan `CORS_ORIGINS`, lalu restart API.

## 5. Pemeriksaan setelah deployment

```bash
curl https://api.example.com/api/health
docker compose ps
docker compose logs --tail=100 api
docker compose exec api python scripts/purge_expired_chats.py
```

Uji dari browser: daftar akun dengan persetujuan privasi, login, buat dua sesi,
muat ulang halaman, pastikan histori kembali, hapus satu sesi, serta pastikan
`/api/debug/runtime` menghasilkan 404 pada konfigurasi produksi.

## Rollback

Sebelum memperbarui kode, catat commit aktif dengan `git rev-parse HEAD`.
Rollback dilakukan dengan checkout commit stabil sebelumnya lalu
`docker compose up -d --build`. Jangan menghapus volume karena berisi index RAG.
