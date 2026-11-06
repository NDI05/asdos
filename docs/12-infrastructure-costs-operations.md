# 12 — Infrastruktur, Biaya, dan Operasional

## Profil pengembangan dan deployment

| Profil | Kegunaan | Rencana awal dan batas |
| --- | --- | --- |
| CPU development | Domain, API, UI, renderer, Excel, unit tests | Laptop/desktop 4–8 core dan 16 GB RAM sebagai titik mulai; bukan hasil load test |
| Lokal Apple Silicon | Prototipe CV/inferensi bila backend kompatibel | Uji PyTorch MPS/runtime terpilih; Docker Linux tidak otomatis meneruskan akselerasi Apple |
| Linux NVIDIA | Worker inferensi lokal | Uji GPU yang tersedia dahulu; 12–16 GB VRAM adalah calon profil eksperimen 4B, bukan jaminan muat |
| CPU-only full inference | Validasi fungsional dataset kecil | Mungkin jauh lebih lambat; ukur sebelum menyatakan layak batch |
| Server privat satu host | Pilot kelas | API, DB, queue, worker dan storage privat; satu slot model dahulu |

Kebutuhan model bukan hanya ukuran bobot. Estimasi kasar bobot model 4 miliar parameter: 16-bit sekitar 8 GB desimal, 4-bit ideal sekitar 2 GB **sebelum** metadata quantization, vision encoder, activation, KV cache, runtime, input image dan output tokens. Angka ini hanya aritmetika kapasitas; ukuran checkpoint dan peak memory sebenarnya harus diukur. GPU 4 GB tidak boleh diasumsikan cukup hanya karena bobot 4-bit tampak kecil.

Default concurrency inferensi 1; batch size 1; crop per jawaban dengan batas image token/output token; pemuatan model sekali per worker. Jalankan transkripsi dan grading berurutan untuk menghindari dua salinan model bila memakai checkpoint sama. Bila engine Paddle/PyTorch mengalokasikan memori bersamaan, atur fase/proses dan ukur efeknya.

## Profil kapasitas

Catat per eksperimen: CPU/RAM/GPU/VRAM, OS/driver, versi runtime, precision/quantization, resolusi, jumlah crop, input/output tokens, warm/cold start, p50/p95, peak memory, OOM dan retry. Jangan menyimpulkan kapasitas dari satu halaman rapi.

Contoh kapasitas **hipotetis**: 100 mahasiswa × 5 halaman = 500 halaman, 10 jawaban/mahasiswa = 1.000 jawaban. Jika pengukuran kelak menunjukkan transkripsi 12 detik/halaman dan grading 4 detik/jawaban, waktu inferensi serial = `(500×12 + 1000×4)/3600 = 2.78 jam`, belum render, IO, antrean, review, atau retry. Angka 12/4 bukan benchmark dan tidak menjadi SLA.

## Perhitungan penyimpanan

Ukuran = PDF asli + render canonical + varian yang dipakai + crops + hasil terstruktur + ekspor + cadangan. Gunakan ukuran aktual sampel, jangan mengalikan jumlah PDF saja. Contoh hipotetis: 100 PDF × 5 MB = 500 MB; 500 halaman × 2 MB render = 1 GB; varian dan crop dapat menambah beberapa kali lipat. Sisakan headroom untuk temp render dan backup. Dedup hanya bila menjaga scope izin dan lineage.

File asli read-only pada level aplikasi; file sementara per job; cleanup berdasarkan job state/retention dan jangan menghapus file yang masih dipakai. Alarm pada disk tersisa dan antrean gagal penting sebelum meningkatkan batch.

## Anggaran

| Komponen | Cara estimasi | Catatan |
| --- | --- | --- |
| Model lokal | Provisioning + daya + penyusutan/perangkat | Open weights tidak berarti tanpa biaya operasional |
| Listrik | daya rata-rata kW × jam × tarif aktual | Ukur watt perangkat; tarif tidak diasumsikan |
| Server/cloud GPU opsional | jam pemakaian × harga provider terkini | Cari penawaran saat membeli; paket ini tidak memuat harga pasar |
| Anotasi/review | jumlah sampel × menit × tarif/jam | Sering lebih dominan dari biaya inferensi |
| Storage/backup | GB-bulan + transfer bila ada | Termasuk retensi turunan dan biaya pemulihan |
| Maintenance | patching, evaluasi model, support | Pisahkan dari biaya development awal |

Biaya API cloud jika dipilih: `image tokens × rate + text input tokens × rate + output tokens × rate + storage/egress`, sesuai ketentuan provider saat itu. Tidak ada provider berbayar yang diwajibkan oleh rancangan ini; jangan mengutip biaya lama sebagai harga saat implementasi.

## Operasional minimum

- `/health/live` memeriksa proses; `/health/ready` memeriksa dependency yang dibutuhkan API. Status model worker dilaporkan terpisah agar API tetap dapat melayani review saat model offline.
- Structured logs: request/job/stage IDs, durasi, outcome, error class. Tanpa isi scan/transkripsi/identitas di log rutin.
- Metrik: antrean, umur job tertua, heartbeat worker, success/failure/retry, p95 per stage, RAM/VRAM, disk, export failures dan finalization conflicts.
- Timeout dan retry dikonfigurasi berdasarkan M0, disimpan versi konfigurasi; retry storm dicegah oleh backoff dan kuota.
- Cancel job menghentikan tahap baru, mencoba menghentikan inferensi secara kooperatif, lalu membersihkan temp. Hasil selesai sebelum cancel tetap terarsip dan tidak otomatis dipromosikan jika input sudah stale.

## Backup dan restore

Backup PostgreSQL dan artefak harus merujuk titik konsistensi yang sama atau memiliki manifest untuk rekonsiliasi. Usulan pilot: backup harian terenkripsi, retention berjenjang sesuai kebijakan institusi, target RPO 24 jam dan RTO 4 jam. Ini target yang perlu diuji, bukan jaminan layanan.

Restore drill: pulihkan ke lingkungan terisolasi → verifikasi hash/foreign refs → terapkan purge tombstones → nonaktifkan outbox lama yang tidak boleh diputar ulang → jalankan reconciler terhadap job pending → uji akses dan satu ekspor → baru buka layanan. Redis tidak menjadi satu-satunya cadangan status job.

## Upgrade dan rollback

Pin release aplikasi, migrasi, image digest, model revision/hash dan prompt. Uji upgrade dengan snapshot data sintetik. Migrasi DB mengikuti expand/contract jika ada client lama; backup sebelum perubahan yang berisiko. Rollback aplikasi tidak menurunkan DB secara destruktif. Model/prompt baru diaktifkan untuk run baru setelah benchmark; snapshot nilai lama tetap menunjuk versi sebelumnya.
