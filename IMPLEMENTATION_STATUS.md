# Status Implementasi ASDOS

## 5 November 2026: batch PDF dan perbaikan preview

Batch hingga 100 PDF dipisah per submission; identitas OCR adalah usulan dan usulan nilai otomatis menunggu konfirmasi identitas/pemetaan. Preview memberi label nomor, umpan balik pilihan, dan hapus pemetaan. Catatan historis menyebut 77 tes backend, 22 tes frontend, build, serta batch sintetis dengan publikasi job dimock. Benchmark tulisan tangan nyata dan akurasi identitas belum tersedia. Artefak run yang menggunakan data privat tidak disertakan.

## 4 November 2026: pemetaan jawaban otomatis

Upload baru dapat menghasilkan draf area, OCR literal dan pemetaan nomor untuk ditinjau. Catatan run lokal menunjukkan hasil perlu ditinjau pengguna sebelum dipakai. Backend 67 tes, frontend 17 tes dan build lulus pada pass tersebut; benchmark akurasi belum tersedia. Dokumen dan artefak dari pengujian privat tidak disertakan.

## 4 November 2026: indikator progres upload dan OCR

Panel progres dan status per nomor tersedia; job dipulihkan dari API saat lembar dibuka kembali. Pemetaan manual dibedakan dari proses worker yang masih berjalan. Backend 50 tes, frontend 13 tes dan build lulus; transisi queued → running → hasil tersedia diperiksa di browser dengan PDF sintetis dan Qwen nyata pada lingkungan terpisah. Lihat [QA_PROGRESS_2026-11-04.md](docs/implementation/QA_PROGRESS_2026-11-04.md).

## 4 November 2026: model nyata dan pemulihan PDF_PIXEL_LIMIT

Qwen3-VL-4B sudah diprovisikan dan tiga smoke inference sintetis lulus pada MPS. Runtime model kini mencakup torchvision yang dibutuhkan processor; kontrak grader v2 memakai bentuk JSON eksplisit dan maksimum satu schema repair dengan validasi tetap ketat. Jalur native `make start` menjalankan API, worker solo dan scheduler dengan Redis lokal di Docker.

Renderer menyesuaikan DPI dalam batas piksel. Pada validasi lokal, render dan transkripsi Qwen selesai, tetapi hasil OCR memerlukan review; retry unggahan gagal juga dipulihkan. Backend 49 tes, frontend 5 tes dan build lulus pada pass tersebut, dan preview browser diperiksa. Benchmark akurasi belum tersedia; catatan rinci uji dokumen privat tidak disertakan.

## Riwayat 3 November: soal dan bobot saja

Backend 38 tes lulus; frontend 5 tes lulus; TypeScript/Vite build, compileall dan diff check lulus. Alur acuan otomatis, konfirmasi identitas terpisah dan guard unreadable sudah diperbaiki. E2E API soal+bobot hingga Excel memakai fake model berlabel; bukan inference Qwen. Migrasi SQLite 0002 telah diuji dan DB development dibackup sebelum dimigrasikan.

Qwen nyata masih blocked: pemasangan extra model gagal DNS files.pythonhosted.org, checkpoint belum tersedia, smoke mengembalikan MODEL_UNAVAILABLE. Percobaan bind server native ditolak izin socket; browser E2E belum dijalankan. Detail: [QA_REPAIR_2026-11-03.md](docs/implementation/QA_REPAIR_2026-11-03.md).

## Catatan pass sebelumnya

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
