# Kebijakan keamanan

## Versi yang didukung

Perbaikan keamanan diterapkan pada commit terbaru di branch `master`. Versi
lama, fork, dan deployment yang tidak mengikuti branch tersebut tidak didukung.

## Melaporkan kerentanan

Jangan membuka issue publik untuk kerentanan yang belum diperbaiki, kebocoran
credential, akses tanpa izin, atau paparan data pengguna.

Laporkan secara privat melalui **Security** → **Advisories** →
**Report a vulnerability** pada repository GitHub ini. Sertakan:

- komponen dan endpoint yang terdampak;
- langkah reproduksi minimum;
- dampak yang teramati;
- bukti secukupnya tanpa menyertakan data pribadi atau secret aktif;
- saran perbaikan jika tersedia.

Pemelihara akan mengonfirmasi penerimaan, menilai dampak, menyiapkan perbaikan,
dan memublikasikan informasi setelah pengguna yang terdampak memperoleh waktu
yang wajar untuk memperbarui sistem.

## Jika credential terpapar

Credential yang pernah masuk commit, log, tangkapan layar, atau issue dianggap
telah bocor meskipun kemudian dihapus. Cabut atau rotasi credential tersebut,
perbarui secret pada layanan produksi, lalu periksa riwayat Git dan log
deployment. Jangan hanya menghapus file dari commit terbaru.

## Batas pengujian

Pengujian keamanan tidak boleh mengakses data pengguna lain, mengganggu
layanan, mengirim trafik berlebihan, atau menimbulkan biaya layanan. Gunakan
akun dan data uji milik sendiri.
