# Berkontribusi ke ASDOS

Status awal proyek adalah perencanaan. Mulai dari [roadmap](docs/11-implementation-roadmap.md), baca [aturan agent](AGENTS.md), lalu pilih issue dengan keluaran yang bisa diuji.

## Sebelum mengubah source

- Jelaskan masalah, perilaku yang diharapkan, acceptance criteria, dan milestone terkait.
- Periksa apakah fungsi yang diperlukan sudah ada. Ajukan ADR jika mengubah rumus nilai, trust boundary, kontrak data publik, atau default model.
- Pakai data sintetik atau data yang izin penggunaannya terdokumentasi. Jangan menempelkan scan asli, NIM, nilai, dan API key ke issue/PR publik.

## Pull request

Satu PR menyelesaikan satu perilaku yang utuh. Sertakan ringkasan perubahan, alasan, verifikasi yang benar-benar dijalankan, migrasi/rollback jika diperlukan, dan keterbatasan. Perubahan model wajib menyertakan identitas checkpoint, split evaluasi, metrik per kelompok, biaya, latensi, dan kegagalan. Jangan hanya melaporkan screenshot atau satu contoh yang berhasil.

Untuk perubahan kontrak, perbarui dokumen serta tes konsumen. Untuk koreksi penilaian, berikan contoh yang menunjukkan angka sebelum/sesudah dan bukti bahwa nilai yang sudah disahkan tidak berubah diam-diam.

## Standar source yang direncanakan

Python dengan type hints, formatter/linter dan unit/integration tests; TypeScript strict dengan komponen UI teruji untuk alur kritis. Nama simbol dan API berbahasa Inggris, dokumentasi produk utama berbahasa Indonesia. Dependensi dikunci setelah proof of compatibility M1. Perintah setup resmi baru ditambahkan setelah dapat dijalankan pada checkout bersih.

## Lisensi kontribusi

Usulan: kontribusi kode di bawah Apache-2.0 dengan DCO/sign-off; maintainer menyelesaikan kebijakan ini sebelum menerima kontribusi eksternal. Jangan menambahkan kode/model/dataset yang lisensinya tidak kompatibel atau tidak jelas. Lisensi kode tidak otomatis melisensikan data mahasiswa atau bobot model.
