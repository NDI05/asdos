# ASDOS — Asisten Koreksi Tulisan Tangan

ASDOS adalah aplikasi lokal untuk membantu dosen menyusun asesmen, memetakan jawaban pada PDF scan, membuat transkripsi literal, meninjau usulan berbasis rubrik, menghitung nilai secara deterministik, mengesahkan snapshot, dan mengekspor `.xlsx`.

**Status implementasi (3 November 2026):** source API, worker, UI, adapter model lokal, skema, migrasi, dan exporter sudah tersedia. Jalur development manual memakai SQLite/eager queue dan bisa berjalan tanpa model. Evaluator dataset lokal, tes frontend awal, pemeriksaan recovery job, dan purge terbatas artefak ekspor tersedia di source. Checkpoint Qwen belum tersedia dan belum ada dataset tulisan tangan berizin atau benchmark; kesiapan model belum terbukti. E2E Compose PostgreSQL/Redis/worker, security/restore drill dan pilot juga belum terverifikasi. Pada Docker Desktop/macOS di workspace ini, port Compose internal tidak dapat diakses dari host; untuk mencoba alur aplikasi gunakan development native. Lihat [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) dan [TEST_REPORT.md](TEST_REPORT.md) untuk bukti hasil setelah perubahan terakhir.

Tidak ada training dari nol, fine-tuning, API berbayar, atau layanan OCR eksternal yang diwajibkan. Model awal yang diintegrasikan adalah [Qwen/Qwen3-VL-4B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) pada revision tetap. Model hanya aktif jika runtime lokal dan berkas checkpoint tersedia. Jalur review/transkripsi manual tetap ada tanpa model.

## Alur MVP

1. Dosen membuat asesmen, soal, bobot, jawaban acuan, kriteria dan anchor kredit; rubrik harus disahkan sebelum submission dibuat.
2. Dosen membuat satu submission untuk satu mahasiswa, mengunggah satu PDF, lalu mengonfirmasi NIM/nama terhadap hash dokumen.
3. PDF dirender menjadi gambar halaman dengan lineage; dosen menandai region, memetakan region ke soal, lalu memasukkan atau meminta transkripsi literal.
4. Model lokal dapat mengusulkan kredit per kriteria dengan referensi bukti. Dosen dapat mengedit atau mengisi keputusan manual.
5. Kode domain memvalidasi kredit, menghitung kontribusi berbobot dengan `Decimal`, memblokir nilai yang belum selesai, lalu dosen mengesahkan snapshot immutable.
6. Ekspor membuat snapshot input sendiri dan workbook delapan sheet; pembuatan Excel tidak memanggil model.

## Menjalankan lokal

Gunakan Python 3.12, Node.js 22, `uv`, dan `make`. Dari root proyek:

```bash
cp .env.example .env
uv sync --locked --extra test
make migrate
make create-owner
```

Setelah dependency berhasil dipasang, jalankan API dan UI pada dua terminal:

```bash
make dev-api
```

```bash
make install-web
make dev-web
```

Buka `http://127.0.0.1:5173`. API lokal memakai SQLite, artefak privat di `data/private`, dan antrean eager untuk memudahkan pengembangan satu mesin. `make create-owner` meminta username, nama tampilan, dan password melalui terminal. Akun awal tidak dibuat dengan password default. Target Make memakai `.venv` yang dikelola uv; `make install-web` memakai `npm ci` dari `apps/web/package-lock.json`.

`make migrate` menjalankan migrasi Alembic. Mode development juga memiliki `ASDOS_AUTO_CREATE=true`; untuk lingkungan bersama gunakan migrasi dan konfigurasi yang eksplisit. `make dev-api` dan `make dev-web` adalah server pengembangan, bukan konfigurasi produksi.

## Model pretrained lokal

Jika mesin memiliki backend PyTorch MPS atau CUDA yang didukung, siapkan runtime model dan checkpoint secara terpisah:

```bash
uv sync --locked --extra model --extra test
uv run python -m scripts.provision_model
uv run python -m scripts.model_smoke
```

Provisioning mengunduh checkpoint pada revision yang dipatok dan menulis manifest/hash lokal. Langkah ini membutuhkan akses ke Hugging Face dan ruang disk yang cukup; unduhan model tidak mengirim PDF mahasiswa. Runtime inferensi mengaktifkan `local_files_only`, tidak memakai remote code, dan tidak punya fallback API. CPU inference hanya diizinkan secara eksplisit pada host dengan RAM minimal 64 GiB; default-nya off. Kelayakan 4B belum dibuktikan pada perangkat tertentu.

## Compose lokal

Compose menyediakan PostgreSQL, Redis, API, worker, scheduler, dan UI. Salin `.env.example`, ganti `ASDOS_DB_PASSWORD` dengan hex acak yang tidak berisi karakter URL, lalu jalankan:

```bash
make compose-up
```

Compose mengonfigurasi UI pada `127.0.0.1:4173` dan API pada `127.0.0.1:8000`; DB/Redis berada di network internal. Pada Docker Desktop/macOS di workspace ini, network `internal` mencegah port publish mencapai host. Network itu dipertahankan agar service tidak mendapat egress; untuk membuka UI di mesin ini jalankan server native development seperti di atas. Jangan mengganti network menjadi bridge terbuka untuk mengatasi port tanpa menilai kembali batas egress. Model perlu diprovisikan di host atau memakai konfigurasi perangkat tersendiri. Buat akun dosen setelah layanan database dan API sehat:

```bash
docker compose --env-file .env -f deploy/compose.yaml run --rm api python -m scripts.create_owner
```

Jalur E2E PostgreSQL/Redis/worker tersedia melalui `make compose-test`. Ia membuat project Compose, kredensial, database, volume artefak, dan port API sementara; lalu menghapus stack/volume itu saat selesai. Tes memakai satu PDF sintetis yang dibuat dari kode, tidak memakai file Anda, dan tidak membutuhkan model. Jalur ini belum dijalankan pada sesi ini.

Compose ini konfigurasi development satu host. Ganti secret, aktifkan Secure cookies/HTTPS, atur backup, retensi, logging, sandboxing dan kebijakan akses sebelum penggunaan data nyata. PDFium dijalankan sebagai proses terpisah berbatas waktu dan environment minimal; isolasi ini **belum merupakan sandbox OS penuh**.

## Tes dan workbook contoh

Tes dan pemeriksaan yang tersedia:

```bash
make test
make check
make build-web
```

Suite `make test` mencakup skor, geometri, workbook, dan alur API manual dengan PDF sintetis: upload, mapping, transkripsi, review, finalisasi `79.00`, dan workbook. Tes itu tidak menjalankan model. Hasil aktual dan gate yang masih terbuka dirinci di [TEST_REPORT.md](TEST_REPORT.md).

Harness metrik untuk dataset berizin menerima manifest privat, tidak membaca PDF, dan tidak menyalin teks mentah ke laporan:

```bash
uv run --locked python -m scripts.evaluate_handwriting --manifest /path/privat/eval.json --split development
```

Purge ekspor dikonfigurasi terpisah (`ASDOS_EXPORT_RETENTION_DAYS`, default `0`/nonaktif). Perintah tanpa `--apply` hanya dry-run:

```bash
uv run --locked python -m scripts.purge_expired_exports
uv run --locked python -m scripts.purge_expired_exports --apply
```

Workbook berisi data sepenuhnya sintetis, termasuk NIM pengujian `0012345678`:

- [Unduh workbook contoh final](examples/ASDOS_ujian_sintetis_final.xlsx)
- Buat ulang: `make example-xlsx`

## Struktur source

- `apps/api/asdos_api/`: API, auth, persistence, storage, review, finalisasi dan export snapshot.
- `apps/worker/`: PDFium subprocess, rendering, worker Celery, retry/recovery.
- `apps/web/`: React/Vite UI Indonesia untuk alur dosen.
- `packages/asdos_domain/`: scoring `Decimal`, validasi proposal, dan transform koordinat tanpa dependency model.
- `migrations/`: baseline skema Alembic.
- `scripts/`: buat akun, provisi/smoke-test model, dan workbook sintetis.
- `docs/`: kontrak domain, privasi, model dan evaluasi.

Semua file PDF, teks/OCR, nama file, dan jawaban diperlakukan sebagai data tak tepercaya. Jangan mengaktifkan akses data mahasiswa nyata sebelum dependency lock penuh, migrasi, sandboxing, backup, dan review keamanan operasional diselesaikan. Gunakan fixture sintetis atau data berizin.
