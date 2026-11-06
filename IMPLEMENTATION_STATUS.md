# Status Implementasi ASDOS

Pemeriksaan: 3 November 2026.

## Terverifikasi pada pass ini

- pytest: 22 tes lulus tanpa warning. Source dipasang read-only ke container terisolasi dengan network none; database/artefak tes berada di /tmp. E2E API memakai PDF satu halaman sintetis, SQLite, dan antrean eager.
- E2E sintetis mencakup asesmen, unggah/render, identitas, mapping, transkripsi/review manual, finalisasi 79.00, workbook, penolakan mutasi tanpa CSRF, dan penolakan akses submission/ekspor lintas pemilik.
- Tes frontend Vitest: 1 lulus. tsc -b dan Vite production build lulus di container; output build hanya di scratch container.
- uv lock --check --offline, konfigurasi Compose default dan profil test, serta bash -n scripts/run_compose_e2e.sh lulus.
- Harness evaluasi, recovery lease, dan purge ekspor memiliki fixture/tabel tes sintetis. Tidak ada file PDF pengguna yang dibaca atau disalin.

## Perubahan development

- httpx2 menggantikan test client lama yang menimbulkan deprecation warning Starlette; startup API memakai lifespan FastAPI.
- Worker hanya boleh mempromosikan hasil saat masih memegang lease. Pembaruan hasil dan status sukses transkripsi/grading menjadi satu transaksi. Reconciler menghindari event berulang, mengakhiri job batal, dan menandai retry habis.
- scripts.evaluate_handwriting menghitung CER/WER, coverage, mapping, MAE/p95, serta error identitas/halaman dari manifest privat. Manifest dicek untuk hash/provenance dan kebocoran writer/dokumen antarsplit. Laporan tidak memuat teks mentah dan keputusan gate tetap not_assessed.
- Purge ekspor memiliki retention yang default-nya nonaktif, dry-run default, tombstone sebelum penghapusan file, retry cleanup, dan HTTP 410 setelah purge. PDF, transkripsi, submission, dan nilai final tidak termasuk cakupan perintah ini.
- make compose-test kini tersedia dengan project Compose dan volume sementara, serta hanya memakai PDF sintetis. Konfigurasinya lolos validasi; runner belum dijalankan.
- Repository Git lokal diinisialisasi agar perubahan dan baseline tercatat.

## Gate yang masih terbuka

- Checkpoint Qwen tidak ada di models/; belum ada dataset tulisan tangan berizin, split terkunci, benchmark visual, hasil akurasi, atau uji kapasitas. Harness belum dijalankan pada data/model manusia. Gate handwriting tetap tertutup sampai Anda menyediakan dan menguji PDF/data yang berizin.
- E2E pada PostgreSQL/Redis/Celery Compose belum dijalankan. Runner terisolasi siap dicoba dengan make compose-test.
- Full security review, backup/restore drill, ledger tombstone untuk backup lama, purge seluruh data submission, pilot, dan deployment belum dilakukan.
- Tes web baru memeriksa server-render layar login. Interaksi browser untuk alur review belum memiliki automated test.
- Di Docker Desktop/macOS workspace ini, port Compose pada network internal belum dapat diakses dari host. Jalur Compose dipertahankan tanpa egress; gunakan server native untuk UI sampai batas ingress ditangani pada host yang sesuai.

E2E sintetis dan unit tests membuktikan perilaku kode deterministik yang diuji; keduanya tidak membuktikan kualitas handwriting, keamanan menyeluruh, atau kesiapan rilis.
