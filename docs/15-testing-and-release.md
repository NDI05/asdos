# 15 — Pengujian dan Syarat Rilis

## Strategi verifikasi

Bedakan tes deterministik aplikasi dari evaluasi model probabilistik. Unit test yang lulus tidak membuktikan tulisan tangan terbaca akurat; benchmark yang bagus tidak membuktikan otorisasi atau Excel benar. Source aplikasi dan test suite MVP tersedia. E2E manual sintetis sudah lulus dengan SQLite dan antrean eager; Compose API/worker/UI juga lulus smoke test terpisah. Hasil aktual dicatat dalam [TEST_REPORT.md](../TEST_REPORT.md); kesiapan rilis tetap memerlukan evaluasi data/model, E2E pada Compose, keamanan, recovery, dan restore.

## Matriks pengujian

| Area | Kasus minimum | Bukti lulus |
| --- | --- | --- |
| Rubrik | max=0, bobot negatif/nol, kriteria duplikat, kredit tanpa anchor | Input invalid ditolak sebelum run |
| Scoring | 20/30/50, 2/3/5, full/zero, null, raw>max, NaN/Infinity | Oracle Decimal independen dan property tests |
| Pembulatan | Half-up seperti 79.005 → 79.01, presisi kontribusi | Pembulatan final sekali, tampilan tidak mengubah agregasi |
| Intake | PDF image-only, text-layer stale, rusak, encrypted, bukan PDF | Tidak menerima text-layer sebagai gold tanpa verifikasi visual |
| Identitas pengganti | Konfirmasi PDF A, ganti dengan PDF B pada submission yang sama | Status kembali pending; finalisasi perlu konfirmasi doc/hash baru; final lama tetap nama/ID lama |
| Render | Rotasi, CropBox, dua sisi, folio panjang, dimensi ekstrem | Count/hash stabil, piksel/resource limits, transform round-trip |
| Mapping | Nomor berulang, 1/7, subnomor, lintas halaman, angka dalam jawaban | Correct mapping atau blocker; tidak silent drop |
| HTR | Pensil, tinta warna, blur, coretan, negasi/angka | Metrik per strata dan critical error review |
| Grading | Sinonim, parafrasa, sebagian benar, jawaban kontradiktif | Kredit sesuai anchor, bukti valid |
| Injection | Instruksi beri nilai penuh, URL, role text di scan | Tidak menjalankan instruksi, tidak ada egress/tool execution |
| Revision | Edit teks/rubrik/bobot setelah proposal/final | Hasil stale ditandai, snapshot lama utuh |
| Concurrency | Dua reviewer/save, retry job, duplicate message | Konflik eksplisit, satu hasil aktif per fingerprint |
| Recovery | Kill worker, Redis message loss, lease lama, job dibatalkan | DB reconciler memulihkan satu kali atau memberi status terminal; lease lama tak boleh mempromosikan hasil |
| Auth | Akses langsung ID file/job/export orang lain | Ditolak pada setiap resource |
| Excel | Leading zero, Unicode, null vs0, string formula, teks panjang | Delapan sheet valid dan nilai sama snapshot |
| Retensi | Purge saat job jalan dan sesudah backup | Tidak muncul lagi setelah restore + tombstone |

## Fixture sintetik minimum

Sediakan PDF HVS satu halaman, folio miring, jawaban lintas dua halaman, scan 90/180 derajat, halaman kosong di tengah, NIM `0012345678`, label `2a`, dua attempt mahasiswa sama, serta teks berawalan formula/URL. Untuk handwriting nyata, gunakan salinan berizin pada penyimpanan privat dan manifest terpisah. PDF sintetik tidak menggantikan benchmark handwriting manusia.

Golden scoring fixture ada pada [contoh](18-example-assessment.md). Golden Excel harus memeriksa nilai, tipe sel dan relasi sheet melalui pembaca independen; jangan membandingkan byte ZIP karena metadata waktu dapat berubah. Uji serangan string dengan pemeriksaan XML `<f>` dan relationship eksternal, bukan hanya tampilan sel.

## Skenario E2E prioritas

Unit test mencakup expired/live lease, retry exhaustion, cancellation, recovery outbox duplikat, evaluasi CER/WER + writer/document leakage, dan purge ekspor dry-run/tombstone. Tes frontend server-render memeriksa formulir login awal. Pemeriksaan ini sintetis; tidak memakai PDF pengguna dan belum menggantikan E2E pada Compose PostgreSQL/Redis/worker, restore drill, browser interaction test, atau benchmark handwriting.

`make compose-test` menyediakan E2E penuh pada PostgreSQL/Redis/worker dalam project dan volume sementara. Tes tetap memakai PDF sintetis. Jalur ini belum dijalankan; pass SQLite/eager tidak boleh dianggap sebagai pass Compose.

**E2E-01 normal:** buat 3 soal/rubrik → approve → upload PDF sintetik → konfirmasi identitas → mapping/transcript → reviewer setuju → finalize → download Excel 79.00. Alur ini lulus pada SQLite dengan antrean eager dan PDF sintetis. Dalam CI tanpa model gunakan adapter manual/deterministik; hasil ini membuktikan jalur manual aplikasi, bukan akurasi model. Smoke test PostgreSQL/Redis/Celery Compose dicatat terpisah; full flow belum dijalankan pada stack tersebut.

**E2E-02 tidak terbaca:** satu nomor unreadable → proposal null → finalisasi 409 → dosen menyelesaikan lewat koreksi/manual override dengan alasan → finalize → export. Pastikan unreadable tidak pernah otomatis menjadi 0.

**E2E-03 revisi final:** export final versi1 → ubah bobot/rubrik menjadi draft2 → final lama tetap 79.00 → pengesahan versi2 menghasilkan snapshot baru → export menyebut revision yang benar. Mencampur versi dalam satu final export ditolak.

**E2E-04 kegagalan batch:** 3 file dengan satu parser gagal → dua lainnya selesai → worker restart saat satu stage berjalan → tidak ada hasil ganda → retry file gagal tidak mengubah submission lain.

**E2E-05 akses:** reviewer hanya melihat assessment yang ditugaskan → copy artifact/job/export ID dari assessment lain → akses ditolak → percobaan finalisasi tanpa hak juga ditolak dan diaudit.

## Gate CI dan evaluasi

PR biasa: formatter/type/lint yang relevan, domain unit tests, API contract/integration, keamanan input/akses yang terpengaruh. PR perubahan export: tambahkan golden workbook. PR model/preprocess/prompt: jalankan benchmark pada split development/calibration terversi dan simpan laporan, bukan mengunduh dataset privat di CI publik.

Release candidate: integration/E2E penuh, locked test sesuai protokol, dependency/license scan, restore drill, dan setup bersih. GPU benchmark dapat dijalankan manual pada mesin terverifikasi dengan laporan signed/checksum; jangan menganggap skipped test sebagai pass. Evaluasi model yang mahal tidak wajib diulang untuk perubahan typo dokumentasi.

## Checklist rilis MVP

- Semua P0 memiliki acceptance yang terbukti atau scope rilis dikurangi secara eksplisit.
- Tidak ada salah identitas/halaman hilang tanpa flag, kesalahan kalkulasi, bypass finalisasi, akses silang, atau formula injection yang diketahui.
- Gate [evaluasi](09-evaluation-and-dataset.md) disertai data aktual, jumlah sampel/penulis, coverage, interval dan kegagalan; belum ada data berarti gate belum selesai.
- Setup pada environment sasaran dari checkout bersih telah dijalankan, versi dependency/model terkunci, perangkat minimum diukur.
- Backup/restore, purge, job recovery dan rollback telah diuji dengan bukti.
- README/model card menyatakan bahasa/tipe jawaban, kebutuhan review, dan batas kemampuan.
- LICENSE/NOTICE, izin demo, kontak keamanan dan alur kontribusi sudah aktif.
- Changelog serta manifest rilis mencatat commit, image/model hashes dan scoring policy version.

Maintainer engineering menilai kesiapan teknis; dosen menilai rubrik dan penggunaan akademik. Kehadiran dua peran tidak boleh diganti dengan “tes AI bilang benar”. Jika gate gagal, rilis sebagai prototipe dengan batas jelas atau tunda rilis; jangan menghapus tes agar pipeline hijau.
