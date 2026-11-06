# 13 — Strategi Open Source dan Tata Kelola

## Identitas dan lisensi

ASDOS adalah nama kerja; maintainer memeriksa nama repository, merek, dan deskripsi publik sebelum peluncuran. Deskripsi awal: “Asisten koreksi jawaban tulisan tangan dengan rubrik berbobot, bukti visual, review dosen, dan ekspor Excel.” Jangan menjanjikan penilaian otomatis sempurna atau menyebut kemampuan yang belum melewati benchmark.

Usulan lisensi kode/dokumentasi proyek: Apache-2.0 karena izin penggunaan/modifikasi/distribusi dan ketentuan patent grant yang eksplisit. Keputusan akhir pemegang hak belum diambil. Sebelum publikasi: pastikan kepemilikan kontribusi, tambahkan teks LICENSE resmi lengkap, pernyataan hak cipta yang benar, dan NOTICE bila diwajibkan dependensi. Paket perencanaan ini tidak mengklaim bahwa repository sudah berlisensi Apache-2.0.

## Pisahkan empat jenis hak

| Artefak | Kebijakan |
| --- | --- |
| Kode aplikasi | Lisensi proyek setelah disetujui |
| Bobot model | Lisensi checkpoint masing-masing; verifikasi revision aktual |
| Dataset/scan mahasiswa | Izin/data policy tersendiri; tidak ikut lisensi kode |
| Hasil penilaian/ekspor | Data pemilik instalasi, bukan otomatis materi publik |

Qwen3-VL-4B-Instruct pada model card yang diperiksa berlabel Apache-2.0; TrOCR checkpoint yang diperiksa berlabel MIT. Lisensi library/runtime dan transitive component tetap perlu diperiksa terpisah. pypdfium2/PDFium memerlukan perhatian pada pilihan lisensi dan notices PDFium/dependency. Jangan menganggap “pip install berhasil” berarti seluruh redistribusi aman. Lihat sumber primer S01–S05/S12.

Versi/distribusi Redis juga harus melalui pemeriksaan lisensi tersendiri (S14), terutama bila image broker disertakan dalam paket. Usulan Apache-2.0 untuk kode ASDOS tidak berarti seluruh layanan pihak ketiga berubah menjadi Apache-2.0. Jika ketentuan broker tidak sesuai tujuan distribusi, buat ADR pengganti kompatibel yang lisensinya jelas lalu uji transport Celery dan recovery sebelum menetapkan default.

## Struktur pengelolaan

Pemilik awal proyek menjadi maintainer; domain reviewer untuk rubrik/penilaian dapat dosen pendamping. Perubahan rumus nilai, finalisasi, dan default evaluator memerlukan review domain dan engineering. Perubahan lisensi, pengiriman data eksternal, serta cakupan klaim model dicatat sebagai keputusan baru.

Gunakan issue template bug/feature/model regression dan PR template sederhana setelah repo publik tersedia. Label awal: `area:vision`, `area:grading`, `area:export`, `area:security`, `type:bug`, `type:docs`, `good-first-issue`, dan `milestone:m0`–`m6`. Ini rencana label; belum ada issue/PR yang dibuat.

## Kontribusi dan komunitas

Baca [CONTRIBUTING.md](../CONTRIBUTING.md). Kontributor menyatakan hak atas kontribusinya dan mengikuti kebijakan DCO yang diputuskan sebelum menerima PR eksternal. Tambahkan kode perilaku dan kontak moderator sebelum mengundang komunitas luas; jangan mencantumkan alamat/email yang belum dikonfirmasi.

Good first issues cocok untuk dokumentasi, fixture sintetik, layout workbook, dan UX yang tidak mengubah keputusan nilai. Perubahan parser, scoring, dan otorisasi butuh konteks serta reviewer yang sesuai. Demo publik memakai data sintetik; jangan meminta pengguna mengunggah ujian nyata ke layanan demo terbuka.

## Artefak rilis

Rilis memuat source, lockfile, petunjuk setup yang sudah diuji, contoh konfigurasi tanpa secret, schema API, migrasi, model manifest/checksum, daftar dependency/lisensi atau SBOM, model card, known issues, dan laporan gate. Bobot model tidak perlu dibundel dalam repository; provisioning harus eksplisit, dapat diverifikasi, dan menyebut kebutuhan ruang/perangkat.

Dataset publik opsional harus melalui review izin dan redaksi tersendiri. Benchmark privat dapat dipublikasikan sebagai agregat, manifest tanpa PII, dan contoh sintetik yang merepresentasikan failure mode; jangan membuka hash/NIM yang dapat dikaitkan tanpa pertimbangan konteks data.

## Versioning dan kompatibilitas

Gunakan SemVer untuk aplikasi setelah kontrak publik stabil. Schema export, API, scoring policy, dataset split, prompt dan model memiliki version ID sendiri. Perubahan prompt yang memengaruhi skor adalah perubahan perilaku dan perlu evaluasi, walaupun API tidak berubah. Changelog rilis menjelaskan dampak pada run baru dan apakah penilaian ulang diperlukan.

Tidak ada telemetry pengumpulan jawaban secara default. Rencana monetisasi, hosting publik, atau sponsor tidak boleh mengubah hak data pemilik instalasi tanpa keputusan dan komunikasi yang jelas.
