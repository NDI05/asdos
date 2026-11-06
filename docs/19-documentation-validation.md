# 19 — Validasi Paket Dokumentasi

Laporan ini adalah pemeriksaan historis paket perencanaan pada 3 November 2026 **sebelum implementasi source dimulai pada sesi yang sama**. Klaim bahwa aplikasi belum diimplementasikan di bawah ini berlaku hanya pada waktu pemeriksaan awal. Status terbaru, file source, dan blocker ada di [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) serta [TEST_REPORT.md](../TEST_REPORT.md).

## Pemeriksaan yang dilakukan

| Pemeriksaan | Hasil |
| --- | --- |
| Tujuan tautan relatif antarfile | Lulus pada file yang diserahkan |
| Keseimbangan fenced code blocks | Lulus |
| Parsing empat contoh JSON kontrak | Lulus |
| Frontmatter empat panduan SKILL.md | name/description hadir, nama sesuai folder, body di bawah 500 baris |
| Span bukti contoh transkripsi | Offset akhir51 sesuai panjang51 code point |
| Hitung independen Decimal: bobot20/30/50 | Raw8/6/9 menghasilkan79.00 |
| Hitung independen Decimal: bobot2/3/5 | Menghasilkan79.00 |
| Null pada nomor2 | Nilai akhir tetap null, bukan61 atau skor ternormalisasi ulang |
| Kosong terverifikasi pada nomor2 | Nilai akhir61.00 |
| Full credit dan semua nol sah | 100.00 dan0.00 |
| Pembulatan HALF_UP | 79.005 menjadi79.01 |
| Uji instruksi grading pada agent terpisah | Perhitungan, null, injection sebagai data dan revisi setelah final sesuai spesifikasi |
| Review kontrak spesifikasi | Enam gap ditemukan, diperbaiki, lalu diperiksa ulang tanpa gap material tersisa pada lingkup tersebut |

Perhitungan di atas dijalankan sebagai pemeriksaan contoh spesifikasi, bukan sebagai unit test aplikasi ASDOS yang belum ada. Pemeriksaan SKILL.md membuktikan struktur dan beberapa skenario instruksi, bukan jaminan discovery otomatis pada seluruh runtime atau benchmark efektivitas agent terhadap baseline.

## Perbaikan dari review

1. Tambahkan payload export snapshot immutable untuk mode draft yang belum memiliki grade snapshot final.
2. Tambahkan penyimpanan keputusan reviewer per kriteria serta salinannya pada snapshot final.
3. Bekukan split penulis sebelum eksperimen; gate/calibration ditetapkan sebelum locked test dibuka.
4. Ikat konfirmasi identitas ke PDF document/hash; penggantian PDF memerlukan konfirmasi baru, sedangkan identitas final lama tetap dibekukan.
5. Tambahkan kontrak revisi layout/image/region agar editor visual memiliki lineage dan concurrency yang jelas.
6. Tambahkan scope assessment/draft revision untuk dokumen dan job impor soal sebelum submission tersedia.

## Batas pemeriksaan

Pada saat laporan historis ini dibuat, belum dijalankan: OCR tulisan tangan nyata, inference model, benchmark akurasi/VRAM/latensi, API/UI/E2E aplikasi, pembuatan workbook oleh aplikasi, uji keamanan runtime, atau deployment. Sesudah itu source MVP, tes domain/workbook, dan tes integrasi manual sintetis ditambahkan; laporan hasil terbaru memisahkan verifikasi yang sudah lulus dari gate yang masih terbuka.

Panduan agent disimpan sebagai file repository dalam `agent-skills/` dan dibaca melalui `AGENTS.md`. Lokasi konfigurasi `.agents` tidak dapat ditulis pada workspace ini; discovery/pemasangan personal tidak dilakukan. Inisialisasi Git juga tidak berhasil karena penulisan `.git` ditolak oleh izin workspace, sehingga belum ada commit atau sinkronisasi Git. Semua file perencanaan tetap diserahkan sebagai artefak tersendiri.
