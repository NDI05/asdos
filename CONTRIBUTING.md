# Berkontribusi ke ASDOS

ASDOS adalah prototipe lokal yang sedang dievaluasi. Mulai dari [roadmap](docs/11-implementation-roadmap.md), baca [aturan proyek](AGENTS.md), lalu pilih issue dengan acceptance yang bisa diperiksa.

## Sebelum mengubah source

- Jelaskan masalah, perilaku yang diharapkan, acceptance criteria, dan milestone terkait.
- Periksa apakah fungsi yang diperlukan sudah ada. Ajukan ADR jika mengubah rumus nilai, trust boundary, kontrak data publik, atau default model.
- Pakai data sintetik atau data yang izin penggunaannya terdokumentasi. Jangan menempelkan scan asli, NIM, nilai, dan API key ke issue/PR publik.

## Pull request

Satu PR menyelesaikan satu perilaku yang utuh. Sertakan ringkasan perubahan, alasan, verifikasi yang benar-benar dijalankan, migrasi/rollback jika diperlukan, dan keterbatasan. Perubahan model wajib menyertakan identitas checkpoint, split evaluasi, metrik per kelompok, biaya, latensi, dan kegagalan. Jangan hanya melaporkan screenshot atau satu contoh yang berhasil.

Untuk perubahan kontrak, perbarui dokumen serta tes konsumen. Untuk koreksi penilaian, berikan contoh yang menunjukkan angka sebelum/sesudah dan bukti bahwa nilai yang sudah disahkan tidak berubah diam-diam.

## Tooling dan pemeriksaan

Backend menggunakan Python 3.12 dan `uv`; frontend menggunakan TypeScript/React dan npm. Nama simbol dan API berbahasa Inggris, dokumentasi produk utama berbahasa Indonesia. Dependensi dipatok di `pyproject.toml` dan `uv.lock`.

Sebelum mengirim perubahan, jalankan pemeriksaan yang relevan:

```bash
make test
make check
make build-web
```

Laporkan perintah yang benar-benar dijalankan beserta hasilnya. Tes sintetik tidak membuktikan akurasi pada tulisan tangan nyata.

## Lisensi kontribusi

Kontribusi kode dan dokumentasi diterima di bawah Apache-2.0 sebagaimana dinyatakan dalam [LICENSE](LICENSE). Saat ini proyek tidak mensyaratkan DCO atau CLA. Kontributor harus memiliki hak untuk menyerahkan perubahan tersebut. Jangan menambahkan kode, model, dataset, atau aset yang lisensinya tidak kompatibel atau tidak jelas. Lisensi kode tidak otomatis melisensikan data mahasiswa atau bobot model.
