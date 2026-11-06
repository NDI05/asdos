# Laporan Verifikasi ASDOS

## 5 November 2026: batch PDF dan perbaikan preview

Batch hingga 100 PDF dipisah per submission; identitas OCR adalah usulan dan usulan nilai otomatis menunggu konfirmasi identitas/pemetaan. Preview memberi label nomor, umpan balik pilihan, dan hapus pemetaan. Catatan historis menyebut 77 tes backend, 22 tes frontend, build, serta batch sintetis dengan publikasi job dimock. Benchmark tulisan tangan nyata dan akurasi identitas belum tersedia. Artefak run yang menggunakan data privat tidak disertakan.

## 4 November 2026: pemetaan jawaban otomatis

Upload baru dapat menghasilkan draf area, OCR literal dan pemetaan nomor untuk ditinjau. Catatan run lokal menunjukkan hasil perlu ditinjau pengguna sebelum dipakai. Backend 67 tes, frontend 17 tes dan build lulus pada pass tersebut; benchmark akurasi belum tersedia. Artefak uji dokumen privat tidak disertakan.

## 4 November 2026: verifikasi indikator progres

Backend 50 tes dan frontend 13 tes lulus; build TypeScript/Vite lulus. Browser pada lingkungan sintetis terpisah memverifikasi queued render, pembaruan otomatis ke preview, pemulihan antrean OCR setelah reload, indikator OCR berjalan, dan hilangnya loading ketika transkripsi nyata tersedia. Tes ini tidak mengubah identitas/data jawaban pengguna. Rincian: [QA_PROGRESS_2026-11-04.md](docs/implementation/QA_PROGRESS_2026-11-04.md).

## 4 November 2026: hasil terbaru

49 tes backend dan 5 tes frontend lulus; TypeScript/Vite build, compileall dan diff check lulus pada pass tersebut. Tiga smoke inference sintetis berhasil pada MPS. Validasi lokal renderer, transkripsi dan retry unggahan juga selesai. Guard identitas mengembalikan 409 pada permintaan OCR sebelum identitas dikonfirmasi.

Kesalahan OCR masih ditemukan; belum ada gold dataset atau metrik akurasi. Identitas dan pemetaan pada submission yang dipakai dalam validasi lokal tidak disahkan dan tidak ada nilai difinalisasi. Catatan rinci yang berasal dari dokumen privat tidak disertakan. Gate rilis penuh tetap belum selesai.

## Riwayat 3 November: soal dan bobot saja

Backend 38 tes lulus; frontend 5 tes lulus; TypeScript/Vite build, compileall dan diff check lulus. Alur acuan otomatis, konfirmasi identitas terpisah dan guard unreadable sudah diperbaiki. E2E API soal+bobot hingga Excel memakai fake model berlabel; bukan inference Qwen. Migrasi SQLite 0002 telah diuji dan DB development dibackup sebelum dimigrasikan.

Qwen nyata masih blocked: pemasangan extra model gagal DNS files.pythonhosted.org, checkpoint belum tersedia, smoke mengembalikan MODEL_UNAVAILABLE. Percobaan bind server native ditolak izin socket; browser E2E belum dijalankan. Detail: [QA_REPAIR_2026-11-03.md](docs/implementation/QA_REPAIR_2026-11-03.md).

## Catatan pass sebelumnya

Tanggal: 3 November 2026. Semua data tes menggunakan fixture sintetis; tidak memakai PDF pengguna.

| Pemeriksaan | Hasil |
| --- | --- |
| python -m pytest -q -p no:cacheprovider di container terisolasi | Lulus: 22 tes, tanpa warning. Network none, source read-only, DB dan artefak sementara di /tmp. |
| E2E API manual | Lulus. PDF sintetis → render → konfirmasi NIM berawalan nol → mapping/transkripsi/review manual → final 79.00 → workbook delapan sheet. |
| Kontrol akses E2E | Lulus. Mutasi tanpa CSRF ditolak; owner lain mendapat 404 saat membuka submission dan export. |
| Worker recovery | Lulus. Lease aktif/expired, satu kali requeue, pembatalan, dan retry exhaustion. Ini tes fungsi reconciler pada SQLite, bukan restart worker Compose. |
| Evaluasi dataset | Lulus. CER/WER, mapping, skor, hash dan pencegahan writer/document leakage diuji memakai string sintetis; belum memakai handwriting atau model. |
| Retensi ekspor | Lulus. Dry-run, tombstone, retention nonaktif, dan retry unlink diuji pada SQLite + store palsu; bukan backup/restore drill. |
| Vitest | Lulus: 1 tes server-render form login. Belum menguji browser interaction. |
| tsc -b + Vite build | Lulus. Build dibuat di scratch container. |
| uv lock --check --offline | Lulus. |
| Compose config + test profile | Lulus. Konfigurasi tervalidasi; service stack tidak dijalankan. |
| Runner shell bash -n | Lulus. |
| E2E Compose PostgreSQL/Redis/worker | Belum dijalankan. Tersedia lewat make compose-test; membutuhkan build image test. |
| Model/checkpoint dan benchmark tulisan | Belum tersedia / belum dijalankan. Tidak ada checkpoint atau dataset berizin di workspace. |
| Backup/restore dan full security review | Belum dilakukan. Purge saat ini hanya mencakup ekspor, dan restore backup lama belum menerapkan tombstone yang dibuat setelah backup. |
| Git | Repository lokal diinisialisasi; status dan perubahan kini dapat ditinjau. |

E2E manual lokal membuktikan hanya jalur no-model di SQLite/eager queue. Jangan menafsirkan hasil ini sebagai akurasi OCR/VLM atau kelulusan Compose, model, dan release gate.
