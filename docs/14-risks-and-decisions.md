# 14 — Risiko, Keputusan, dan Asumsi Terbuka

## Register risiko

| ID | Risiko | Peluang / dampak | Mitigasi dan pemilik | Trigger tindakan |
| --- | --- | --- | --- | --- |
| R01 | Tulisan tangan lokal tidak terbaca baik | Tinggi / tinggi | CV engineer: gold dataset, crop, abstain, edit manual | CER/error nilai melewati gate |
| R02 | Nomor/mahasiswa tertukar | Sedang / kritis | Backend/CV: identity confirmation, mapping evidence | Satu mismatch memblokir rilis |
| R03 | Halusinasi OCR atau grader | Tinggi / tinggi | ML/domain: OCR tanpa kunci, schema, evidence, review | Bukti tidak ada atau credit tidak sah |
| R04 | Rubrik ambigu/tidak konsisten | Tinggi / tinggi | Dosen: anchors, double grading, adjudikasi | Evaluator oracle/human disagreement tinggi |
| R05 | Model tidak muat atau terlalu lambat | Sedang / tinggi | Ops/ML: ukur memori, crop, slot tunggal, kandidat kecil | OOM/latensi membuat pilot tidak layak |
| R06 | Bias akibat kualitas tulisan/bahasa | Sedang / tinggi | Evaluasi per strata; pisahkan keterbacaan dari kebenaran | Gap besar atau null menjadi 0 |
| R07 | Data ujian bocor | Sedang / kritis | Backend/Ops: lokal default, ACL, purge, log minimal | Scan/nilai dapat diakses lintas scope |
| R08 | Lisensi/model/dataset tidak cocok | Sedang / tinggi | Maintainer: provenance dan izin per artefak | Hak redistribusi tidak jelas |
| R09 | Human review lebih lama dari manual | Sedang / tinggi | Produk/dosen: ukur waktu, sederhanakan panel | Tidak ada penghematan pada pilot |
| R10 | Nilai double-weight atau rounding salah | Sedang / tinggi | Domain engineer: formula tunggal, Decimal, property tests | Workbook berbeda dari snapshot |
| R11 | Job ganda/hasil basi menimpa baru | Sedang / tinggi | Backend: fingerprint, lease, transaksi, optimistic lock | Retry/restart mengubah nilai aktif |
| R12 | Scope melebar ke semua tipe ujian | Tinggi / sedang | Maintainer: milestone dan non-goals | Fitur tanpa acceptance/dataset masuk MVP |
| R13 | Overfitting benchmark atau leakage | Sedang / tinggi | ML reviewer: writer-disjoint split, locked test | Peningkatan hanya pada contoh tuning |

Peran adalah tanggung jawab, bukan kebutuhan jumlah orang; satu pengembang dapat memegang beberapa peran, sementara persetujuan akademik tetap milik dosen.

## ADR-001 — Pisahkan pengenalan, penilaian, dan kalkulasi

Status: dipilih untuk rancangan. Satu panggilan VLM langsung mengeluarkan nilai memang sederhana, tetapi sulit membedakan error baca dari error nilai dan sulit diaudit. Gunakan transkripsi literal, evaluator per kriteria, validator dan kalkulator terpisah. Konsekuensi: lebih banyak artefak/versi, tetapi sumber salah dapat dilacak. Tinjau ulang hanya jika eksperimen menunjukkan jalur lain lebih baik tanpa kehilangan bukti dan pengujian.

## ADR-002 — Rubrik disetujui dan pengesahan manusia

Status: dipilih untuk MVP. Soal tidak selalu memiliki satu jawaban tunggal; nilai parsial memerlukan keputusan dosen. AI menyusun usulan, dosen menyetujui rubrik dan nilai akhir. Konsekuensi: tidak ada klaim penilaian otonom, dan UI review termasuk fitur inti. Pengurangan approval manusia baru dibahas sebagai versi produk baru setelah bukti dan kebijakan tersedia.

## ADR-003 — Lokal dahulu, model pemenang melalui benchmark

Status: lokal dipilih, model default pending M0. Bandingkan PP-OCRv5 dan Qwen3-VL-4B; TrOCR line baseline bila perlu. Model lokal menjaga kontrol data dan tidak mewajibkan API berbayar, tetapi membutuhkan kapasitas dan maintenance. Model yang lebih baru/lebih besar tidak otomatis menggantikan default. Cloud tidak menjadi fallback tersembunyi.

## ADR-004 — Modular monolith dengan worker

Status: dipilih untuk rancangan. Python domain/API/worker dalam satu codebase, React UI, PostgreSQL, Celery/Redis, file store privat. BackgroundTasks in-process tidak cukup sebagai satu-satunya pemrosesan ujian berat yang harus pulih saat restart. Konsekuensi: perlu queue/outbox/reconciler, tetapi tidak perlu Kubernetes atau microservices.

## ADR-005 — Nilai snapshot dan ekspor deterministik

Status: dipilih. Finalisasi menghasilkan snapshot immutable dan versi kebijakan angka. Ekspor hanya membacanya. Konsekuensi: pengubahan rubrik membuat revisi baru; rerun tidak mengubah Excel final sebelumnya. Ini menghindari nilai bergeser saat model/prompt berganti.

## ADR-006 — Satu PDF per mahasiswa untuk MVP

Status: asumsi dipilih untuk membatasi risiko. Banyak halaman dan urutan jawaban bebas tetap didukung. PDF gabungan kelas meningkatkan risiko boundary/identitas, sehingga perlu workflow pemisahan dan dataset tersendiri. Konsekuensi: pengguna memisahkan file sebelum MVP; kelak QR/template opsional dapat membantu.

## ADR-007 — Kontribusi bobot tunggal dan nilai null eksplisit

Status: dipilih. `S=100×Σ((r_i/R_i)×w_i)/Σw_i`. Null berbeda dari nol dan memblokir finalisasi. Konsekuensi: setiap layar/export harus membawa status, bukan hanya kolom angka. Penggunaan bobot yang tidak berjumlah 100 tetap sah.

## ADR-008 — Belum fine-tuning atau vector database

Status: dipilih untuk MVP. Tugas awal dapat diuji dengan model pretrained dan rubrik dalam konteks; data lokal masih perlu dikumpulkan. Konsekuensi: baseline cepat diuji, pengelolaan lisensi/data lebih sederhana. Fine-tuning hanya dibuka bila error analysis dan data berizin menunjukkan manfaat; RAG hanya bila materi acuan terlalu besar untuk konteks dan retrieval punya acceptance jelas.

## Keputusan yang perlu dipastikan kemudian

| Keputusan | Default kerja saat ini | Waktu dibutuhkan |
| --- | --- | --- |
| Mata kuliah/jenis soal awal | Narasi/esai TI, Indonesia/Inggris | Sebelum anotasi M0 |
| Sampel dan izin | Belum tersedia di paket | Sebelum benchmark nyata |
| Hardware target | Pengukuran lokal; satu slot inferensi | M0 sebelum pemilihan default |
| Jumlah soal/mahasiswa nyata | Pilot 100 mahasiswa, 5–20 soal | Sebelum capacity test M5 |
| Lisensi publik | Usulan Apache-2.0 | Sebelum menerima kontribusi/publikasi |
| Kebijakan nilai manual/retensi | Ditetapkan dosen/institusi | Sebelum pilot data nyata |
| Nama repo/kontak keamanan | Belum ditetapkan | Sebelum publikasi |
| Bahasa/rumus/diagram lanjutan | Di luar MVP | Saat ada dataset dan issue khusus |

Tidak perlu menghentikan penyusunan dokumentasi atau skeleton untuk semua keputusan ini. Namun benchmark, data nyata, publikasi, dan klaim akurasi tidak boleh dilanjutkan dengan asumsi yang belum terpenuhi.
