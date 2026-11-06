# 11 — Roadmap dan Backlog Implementasi

## Strategi

Buktikan kelayakan tulisan tangan sebelum berinvestasi besar pada UI. Setelah eksperimen awal, bangun jalur manual utuh soal → jawaban → skor → Excel dengan satu mahasiswa. Ganti bagian manual dengan otomatisasi bertahap. Setiap milestone punya keluaran, gate, dan batas berhenti; jangan membuka fase berikutnya dengan hasil evaluasi yang belum ada.

Estimasi untuk satu pengembang berpengalaman: **194–296 jam kerja teknis**, atau sekitar **235–355 jam dengan buffer 20%**. Pada 20 jam/minggu, kira-kira **12–18 minggu**. Ini estimasi perencanaan, tidak mencakup waktu tunggu izin dataset, anotasi dosen, pembelian hardware, dan review eksternal. Jika model gagal feasibility, lakukan re-scope sebelum mengunci jadwal.

## Status source pada 3 November 2026

Implementasi source untuk jalur M1–M5 tersedia sebagai satu potongan MVP: API/domain, skema/migrasi, UI, worker, adapter model lokal, finalisasi dan Excel. Pada environment lokal, dependency Python/web sudah terkunci, 10 tes termasuk E2E API manual sintetis lulus, build web dan migrasi lulus, serta server native API/UI sedang berjalan. Enam layanan Compose juga sempat dibangun dan di-health-check; Compose kini dihentikan dan network dikembalikan ke `internal` setelah ingress terbukti memberi API egress internet dan tidak bisa diblokir dengan opsi masquerading pada host ini. Bukti ini mendukung jalur manual dasar M1 dan sebagian intake/review/export; belum membuktikan semua acceptance M1–M5. M0 dan M6 tetap terbuka: belum ada tulisan tangan nyata, evaluasi model, uji recovery penuh, security/restore drill, pilot, atau release readiness. Bukti aktual dicatat di [TEST_REPORT.md](../TEST_REPORT.md), dan rincian source/gate di [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md).

## Milestone

| Milestone | Jam | Dependensi | Keluaran dan gate |
| --- | --- | --- | --- |
| M0 — Feasibility dan dataset | 20–32 | Sampel berizin, dosen | Protokol, anotasi awal, baseline OCR/VLM, profil hardware; keputusan go/no-go |
| M1 — Skeleton dan jalur manual | 18–26 | Kontrak inti; M0 dapat berjalan paralel secara jadwal | API/domain/DB/UI minimal, satu jawaban manual sampai Excel; dependency lock terbukti |
| M2 — Assessment dan intake | 24–36 | M1 | Rubrik approved, PDF soal draft import, upload/identitas, job progres, keamanan parser |
| M3 — CV dan transkripsi | 40–64 | M0, M2 | Render/transform, mapping/edit, OCR terpilih, provenance, benchmark M3 |
| M4 — Evaluator dan scoring | 32–48 | M0, M1, input contract M3 | Evaluator oracle-text dan end-to-end, validation, abstention, deterministic calculator |
| M5 — Review, batch, ekspor lengkap | 36–54 | M3, M4 | UI bukti, revision lock, final snapshot, delapan sheet Excel, recovery batch |
| M6 — Pilot dan rilis | 24–36 | M5 dan dataset pilot | Gate evaluasi, E2E/security/restore, model card, lisensi, demo berizin |

M1 tidak berarti sistem bisa membaca tulisan. M4 boleh mengembangkan evaluator pada gold transcript sebelum M3 selesai, tetapi integrasi end-to-end tetap menunggu kontrak bukti yang valid. Pemilik proyek memutuskan cakupan jika dataset/hardware membatasi model.

## Backlog siap dijadikan issue

| ID | Pekerjaan | Dependensi | Acceptance |
| --- | --- | --- | --- |
| M0.1 | Tetapkan soal/rubrik dan izin sampel | — | Manifest sumber/izin/retensi tersedia; tanpa data privat di Git |
| M0.2 | Anotasi gold dan bekukan split berbasis penulis sebelum eksperimen | M0.1 | Schema tervalidasi, double annotation/adjudikasi, manifest split/hash terkunci |
| M0.3 | Jalankan baseline PP-OCRv5 vs VLM crop pada development split | M0.2 | CER/mapping/latensi/memori serta contoh gagal tersimpan privat; test belum dibuka |
| M0.4 | Uji evaluator pada gold text development split | M0.2 | MAE/agreement dan error rubric terukur; test belum dibuka |
| M0.5 | Kalibrasi threshold, bekukan gate dan ADR model awal | M0.3, M0.4 | Konfigurasi/gate dibekukan sebelum locked test; model belum lolos tidak dijadikan default |
| M1.1 | Scaffold API, worker, web, CI dasar | — | Checkout bersih bisa menjalankan health smoke dengan lockfile |
| M1.2 | Implementasi domain scoring | — | Contoh 79.00, null, rounding dan property tests lulus |
| M1.3 | Migrasi DB minimum dan file store privat | M1.1 | Relasi inti dan scope ownership diuji |
| M1.4 | Jalur input manual → snapshot → Excel minimum | M1.2, M1.3 | Satu mahasiswa/tiga soal menghasilkan workbook 79.00 |
| M2.1 | Editor/import draft soal dan rubrik | M1.3 | Field lengkap, invalid rubric ditolak, approval immutable |
| M2.2 | Intake PDF dan batas resource | M1.3 | PDF invalid/terenkripsi ditangani per file; original hash tersimpan |
| M2.3 | Submission identity/attempt | M2.2 | Leading-zero NIM dan duplikasi terdeteksi, active attempt eksplisit |
| M2.4 | Queue/outbox/idempotency/reconciler | M1.1, M1.3 | Pesan duplikat/restart tidak menggandakan hasil |
| M2.5 | Session dan resource authorization | M1.3 | Akses salah assessment/file ditolak; mutasi punya CSRF protection |
| M3.1 | Renderer dan transform canonical | M2.2 | Rotasi/zoom/polygon round-trip dan clipping diuji |
| M3.2 | Quality flags dan ablation preprocessing | M0.3, M3.1 | Threshold berbasis calibration, line removal tidak menurunkan gate |
| M3.3 | Region/mapping lintas halaman + editor | M3.1 | Jawaban tidak berurutan dan unassigned dapat diselesaikan |
| M3.4 | Adapter transcriber literal | M0.5, M3.3 | Tidak menerima rubrik, refs sah, confidence null jika tidak tersedia |
| M3.5 | OCR benchmark dan regression fixtures | M3.4 | Metrik per strata + coverage + manifest dapat direproduksi |
| M4.1 | Schema proposal dan validator evidence | M1.2, M3.4 contract | Unknown criterion/span invalid ditolak, tidak clamp nilai |
| M4.2 | Adapter evaluator satu nomor | M0.4, M4.1 | Rubrik approved, tanpa PII/tools, output tervalidasi |
| M4.3 | Review flags, unsupported dan null handling | M4.2 | Tidak terbaca/model gagal tidak menjadi 0 |
| M4.4 | Oracle vs end-to-end benchmark | M3.5, M4.2 | Error OCR dan grader dapat dipisahkan; tidak tuning test |
| M5.1 | Panel review gambar/teks/rubrik | M3.3, M4.2 | Klik evidence membuka crop yang tepat; edit menghasilkan revision |
| M5.2 | Concurrent edits dan manual override | M5.1 | Konflik terdeteksi; alasan override dan histori utuh |
| M5.3 | Finalisasi/superseding snapshot | M5.2 | Blocker dicek atomik, final lama tidak berubah |
| M5.4 | Excel delapan sheet dan export snapshot | M5.3 | Schema, tipe sel, null, formula injection dan nilai lulus tes |
| M5.5 | Batch/resume/cancel dan dashboard | M2.4, M5.1 | 100 submission uji; file gagal terisolasi, progres akurat |
| M6.1 | Pilot dosen dan pengukuran waktu | M5.4, M5.5 | Waktu manual/ASDOS, intervensi, error dan keterbatasan dilaporkan |
| M6.2 | Security, purge, backup/restore drill | M5 | Uji otorisasi/parser/export dan restore dengan tombstone lulus |
| M6.3 | Legal/dependency/model provenance dan model card | M0.5 | Lisensi final dan notices tersedia, data demo sah |
| M6.4 | Release candidate reproducibility | M6.1–M6.3 | Setup bersih, E2E, rollback, gate rilis dan known issues terdokumentasi |

## Definisi siap dikerjakan

Issue memuat perilaku yang dapat diamati, input/output, invarian terkait, fixture yang boleh dipakai, metode verifikasi, dan non-goals. Contoh: “Saat OCR memberi nilai null, finalisasi ditolak dengan question ID yang perlu review” lebih siap daripada “buat AI akurat”.

## Definisi selesai milestone

Acceptance terbukti oleh hasil nyata, data tidak bocor, docs/schema sesuai implementasi, kegagalan dapat dipulihkan, dan kebutuhan berikutnya bisa dikerjakan tanpa menebak kontrak. Tidak perlu coverage angka tinggi untuk kosmetik; utamakan seluruh cabang kalkulasi, status, akses, dan recovery yang memengaruhi nilai.

## Tahap setelah MVP

v0.2: multi-reviewer terkontrol, batch approval tanpa bypass blocker, export analytics. v0.3: ingestion PDF gabungan kelas dengan verifikasi boundary/identitas. v1.x: numerik/satuan, rumus/diagram per jenis, integrasi LMS, object store multi-host, dan fine-tuning berizin bila evidence menunjukkan manfaat. Jadwal tahap tersebut belum diestimasi; jangan memasukkannya diam-diam ke MVP.

## Titik berhenti/re-scope

Jika keterbacaan nyata terlalu rendah, fokus pada transkripsi/review manual dan rekap berbobot. Jika model tidak muat, ukur kandidat lebih kecil/quantized atau sediakan runtime server yang kompatibel; jangan menyatakan CPU fallback sama cepatnya. Jika evaluator oracle gagal, perbaiki rubrik/penilaian sebelum mengejar UI lebih lengkap. Jika waktu dosen tidak berkurang, evaluasi ulang tujuan otomatisasi sebelum memperluas produk.
