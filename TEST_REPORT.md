# Laporan Verifikasi ASDOS

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
