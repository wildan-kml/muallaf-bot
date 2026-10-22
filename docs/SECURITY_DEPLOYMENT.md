# Pengamanan Produksi Muallaf Bot (Tanpa Layanan Berbayar)

Dokumen ini adalah prosedur wajib sebelum perubahan keamanan dipush ke branch
produksi. Jangan menaruh nilai secret di Git, `wrangler.jsonc`, tangkapan layar,
atau percakapan publik.

## Arsitektur aman

Browser hanya memanggil `/api/*` pada domain Cloudflare yang sama. Cloudflare
Worker menerapkan security header, batas ukuran request, rate limit, dan
verifikasi Turnstile. Worker kemudian meneruskan request ke Modal menggunakan:

1. Modal Proxy Token, yang diperiksa oleh infrastruktur Modal sebelum container
   dinyalakan; dan
2. `ORIGIN_SHARED_SECRET`, yang diperiksa lagi oleh FastAPI.

Request langsung ke URL `modal.run` ditolak sebelum menggunakan container.
Backend juga memiliki rate limit kedua karena limiter Cloudflare bersifat
per-lokasi dan permisif.

## 1. Pastikan semua layanan tetap pada paket gratis

- Cloudflare: **Workers Free**. Jangan mengaktifkan Workers Paid.
- Turnstile: **Free**.
- Modal: **Starter**, lalu atur Workspace spend limit ke `US$0` jika dashboard
  mengizinkan. Jika tidak, pilih nilai minimum dan jangan menambahkan metode
  pembayaran/auto-upgrade.
- Gemini: gunakan project **Free Tier** tanpa billing. Jika project sekarang
  berstatus Paid, buat project Free terpisah atau lepaskan billing.
- Neon: gunakan project **Free** dan aktifkan suspend saat tidak aktif.

## 2. Buat dua secret acak

Jalankan PowerShell. Perintah ini tidak menulis secret ke repository.

```powershell
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()

$originBytes = New-Object byte[] 48
$rng.GetBytes($originBytes)
$originSecret = [Convert]::ToBase64String($originBytes)

$humanBytes = New-Object byte[] 48
$rng.GetBytes($humanBytes)
$humanSecret = [Convert]::ToBase64String($humanBytes)

$rng.Dispose()
```

Simpan sementara kedua nilai di password manager:

- `$originSecret` menjadi `ORIGIN_SHARED_SECRET` di Modal dan Cloudflare.
- `$humanSecret` menjadi `HUMAN_SESSION_SECRET` hanya di Cloudflare.

Jangan memakai nilai yang sama untuk JWT, origin, dan cookie manusia.

## 3. Buat Modal Proxy Token

Cara termudah:

1. Buka Modal Dashboard.
2. Buka **Workspace settings** → **Proxy Tokens**.
3. Pilih **Create proxy token**.
4. Simpan Token ID berawalan `wk-` dan Token Secret berawalan `ws-` di password
   manager.
5. Jangan memakai API token (`ak-`/`as-`) untuk kebutuhan ini.

Alternatif CLI:

```powershell
modal workspace proxy-tokens create
```

## 4. Tambahkan origin secret ke Modal

Buka file lokal yang sudah diabaikan Git:

```text
deploy/modal-secrets.env
```

Tambahkan atau ganti baris berikut tanpa menghapus secret lain:

```dotenv
ORIGIN_SHARED_SECRET=<nilai $originSecret>
```

Jika memang perlu memperbarui secret runtime, terbitkan ulang seluruh isi file
sebagai Modal Secret. Jangan jalankan perintah ini dengan file yang tidak memuat
semua nilai runtime yang sebelumnya tersimpan, karena `--force` mengganti secret:

```powershell
modal secret create muallaf-bot-secrets --from-dotenv deploy/modal-secrets.env --force
```

Simpan `GEMINI_API_KEY` dalam secret Modal terpisah agar pembaruan model tidak
menimpa secret database, origin, atau SMTP. Dari root repository, jalankan:

```powershell
$geminiLine = Get-Content backend/.env |
  Where-Object { $_ -match '^GEMINI_API_KEY=' } |
  Select-Object -First 1

if (-not $geminiLine) {
  throw 'GEMINI_API_KEY tidak ditemukan di backend/.env'
}

$geminiKey = $geminiLine.Substring('GEMINI_API_KEY='.Length).Trim()
if (-not $geminiKey) {
  throw 'GEMINI_API_KEY kosong'
}

& .\backend\.venv\Scripts\python.exe -m modal secret create `
  muallaf-bot-gemini "GEMINI_API_KEY=$geminiKey" --force

Remove-Variable geminiKey, geminiLine
```

`GEMINI_API_KEY` wajib tersedia agar `/api/chat/model-status` menghasilkan
`llm_ready: true`. Jangan menampilkan nilainya melalui chat, menulisnya ke
dokumentasi, atau memasukkannya ke Git.

Pastikan file tetap tidak tercatat Git:

```powershell
git status --short
git check-ignore deploy/modal-secrets.env
```

## 5. Buat Turnstile gratis

1. Buka Cloudflare Dashboard → **Turnstile** → **Add widget**.
2. Nama: `Muallaf Bot Production`.
3. Mode: **Managed**.
4. Tambahkan hostname `muallaf-bot.mwildankamil.workers.dev`.
5. Tambahkan domain kustom juga bila nanti digunakan.
6. Salin Site Key dan Secret Key ke password manager.

Jangan menambahkan `localhost` pada widget produksi. Untuk pengujian lokal,
gunakan test key resmi Turnstile.

## 6. Pasang enam secret pada Cloudflare Worker

Masuk ke folder frontend:

```powershell
cd frontend
```

Jalankan satu per satu dan tempel nilai yang diminta:

```powershell
npx wrangler secret put ORIGIN_SHARED_SECRET
npx wrangler secret put MODAL_PROXY_TOKEN_ID
npx wrangler secret put MODAL_PROXY_TOKEN_SECRET
npx wrangler secret put TURNSTILE_SITE_KEY
npx wrangler secret put TURNSTILE_SECRET_KEY
npx wrangler secret put HUMAN_SESSION_SECRET
```

Nilai yang digunakan:

- `ORIGIN_SHARED_SECRET`: `$originSecret` yang sama dengan Modal.
- `MODAL_PROXY_TOKEN_ID`: nilai `wk-...`.
- `MODAL_PROXY_TOKEN_SECRET`: nilai `ws-...`.
- `TURNSTILE_SITE_KEY`: Site Key dari widget.
- `TURNSTILE_SECRET_KEY`: Secret Key dari widget.
- `HUMAN_SESSION_SECRET`: `$humanSecret`.

## 7. Hapus konfigurasi frontend yang mem-bypass Worker

Di Cloudflare Worker → **Settings** → **Builds** → **Variables and secrets**,
hapus variable build `VITE_API_URL` bila nilainya menunjuk langsung ke
`modal.run`. Build produksi sekarang sengaja memakai `/api` pada domain yang
sama agar seluruh request melewati proteksi Worker.

Untuk preview lokal, Vite tetap otomatis memakai `http://127.0.0.1:8000`.

## 8. Deploy dengan urutan yang aman

Setelah semua secret tersedia:

```powershell
cd frontend
npm run build
npx wrangler deploy
```

Lalu aktifkan Modal Proxy Auth dan backend baru:

```powershell
cd ..
modal deploy deploy/modal_app.py
```

`deploy/modal_app.py` menetapkan `GEMINI_MODEL=gemini-3.5-flash-lite`.
Jangan menambahkan `GEMINI_MODEL=gemini-2.5-flash` ke
`deploy/modal-secrets.env`, karena nilai secret dapat menimpa konfigurasi image.

Terakhir commit dan push agar deployment Git selanjutnya konsisten:

```powershell
git add backend deploy frontend tests docs README.md
git commit -m "security: lindungi API dari spam brute force dan akses langsung"
git push origin master
```

## 9. Verifikasi produksi

1. Buka aplikasi di jendela Incognito.
2. Pastikan pendaftaran dan akses tamu meminta Turnstile.
3. Pastikan login akun lama tetap berfungsi.
4. Coba URL Modal langsung tanpa header. Hasil yang benar adalah `401` dari
   Modal Proxy Auth dan tidak ada container baru pada log Modal.
5. Verifikasi model melalui domain Cloudflare:

```powershell
$status = Invoke-RestMethod `
  -Uri "https://muallaf-bot.mwildankamil.workers.dev/api/chat/model-status"
$status | ConvertTo-Json -Depth 5
```

Hasil yang benar setelah deploy:

```text
llm_model     : auto: gemini-3.5-flash-lite -> deterministic extractive fallback
llm_ready     : true
langchain_ready: true
```

Jika `llm_ready` tetap `false`, periksa bahwa `GEMINI_API_KEY` masih aktif di
Modal Secret `muallaf-bot-secrets`, lalu deploy ulang. Jangan memasukkan API key
ke Git atau ke konfigurasi Cloudflare frontend.
5. Kirim pertanyaan berulang lebih dari batas. Hasil yang benar adalah `429`.
6. Periksa Network browser: request chat harus menuju domain Cloudflare
   `/api/chat`, bukan `modal.run`.
7. Pastikan response halaman memiliki CSP, HSTS, `X-Frame-Options: DENY`, dan
   `X-Content-Type-Options: nosniff`.

## 10. Batas yang diterapkan

- Cloudflare global: 120 request API/menit per lokasi Cloudflare.
- Cloudflare chat: 10 request/menit per akun atau jaringan tamu.
- Cloudflare login/daftar: 5 request/menit per jalur dan jaringan.
- Backend chat tamu: 6/menit.
- Backend chat akun: 15/menit.
- Backend chat global: 30/menit.
- Backend login: 10 percobaan/10 menit per nama pengguna dan jaringan.
- Backend pendaftaran: 3/jam per jaringan.
- Request body: maksimal 64 KiB.
- Riwayat yang dapat dikirim client: maksimal 6 pesan.
- Modal: satu container, dua input bersamaan, timeout 120 detik.

## 11. Pemeliharaan rutin gratis

Setiap bulan:

1. Periksa Cloudflare Analytics untuk response `429` dan lonjakan trafik.
2. Periksa Modal Usage; pastikan spend limit tetap aktif.
3. Periksa AI Studio; pastikan project masih Free Tier.
4. Jalankan `npm audit --omit=dev` dan seluruh pengujian.
5. Rotasi segera semua secret jika pernah tampil pada screenshot, commit, log,
   atau chat. Setelah rotasi, perbarui kedua sisi sebelum menghapus nilai lama.

