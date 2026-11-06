# 01 — Produk dan Kebutuhan

## Masalah dan tujuan

Dosen menerima jawaban tulisan tangan sebagai PDF scan. Koreksi manual menghabiskan waktu untuk membaca, mencocokkan nomor, menilai dengan standar konsisten, dan merekap nilai. ASDOS membantu proses tersebut dengan bukti visual dan kontrol dosen. Sistem harus menunjukkan ketidakpastian, mendukung jawaban yang maknanya benar walaupun berbeda kata, dan menghitung bobot secara transparan.

Keberhasilan produk berarti waktu koreksi berkurang tanpa mengorbankan keterlacakan atau meningkatkan kesalahan nilai. Klaim keberhasilan hanya boleh dibuat setelah pilot berlabel dan pengukuran waktu dosen.

## Asumsi kerja

| Topik | Default perencanaan | Dampak bila berbeda |
| --- | --- | --- |
| Pengguna | Dosen/asisten yang diberi akses oleh pemilik assessment | SSO/LMS dan student portal ditunda |
| Bahasa | Indonesia dan Inggris, aksara Latin | Bahasa/aksara lain perlu benchmark terpisah |
| Jawaban | Narasi, esai, daftar, tabel sederhana | Matematika kompleks/diagram masuk v1.x |
| Scan | Folio bergaris atau HVS, 200–300 DPI disarankan | Scan rendah kualitas tetap dapat diunggah lalu ditandai |
| Pengelompokan | Satu PDF untuk satu mahasiswa, dapat banyak halaman | PDF gabungan kelas perlu pemisahan manual sebelum MVP |
| Beban pilot | 100 mahasiswa, 1–10 halaman/PDF, 5–20 nomor | Beban lebih besar perlu pengujian tambahan |
| Penyimpanan | Instalasi lokal privat, tanpa upload cloud default | Provider cloud perlu kontrol persetujuan dan data |
| Penilaian | Rubrik/kunci disetujui dosen sebelum proses | Tanpa rubrik hanya boleh menyiapkan transkripsi/usulan |

Asumsi ini bukan batas permanen. Catat perubahan sebelum mengubah acceptance dan biaya.

## Pengguna dan otorisasi

Pemilik assessment membuat soal, rubrik, anggota, dan kebijakan nilai; mengesahkan hasil serta mengekspor. Reviewer hanya mengakses assessment yang ditugaskan, memperbaiki pemetaan/transkripsi dan mengusulkan nilai. Reviewer tidak mengubah bobot atau mengesahkan final tanpa wewenang pemilik. Admin instalasi mengelola akun dan operasional; akses administratif ke data harus tercatat. MVP dapat diawali akun pemilik tunggal pada deployment privat; model data tetap menyediakan assignment untuk tahap kolaborasi.

## Kebutuhan fungsional

| ID | Kebutuhan | Prioritas | Acceptance yang dapat diamati |
| --- | --- | --- | --- |
| FR-01 | Buat assessment dan daftar soal bernomor | P0 | ID stabil dan label seperti 1, 2a, 2b tersimpan tanpa ambigu |
| FR-02 | Input soal manual/terstruktur dan impor PDF soal | P0 | Hasil ekstraksi diperiksa dosen; soal belum disetujui tidak dapat dinilai |
| FR-03 | Input kunci, kriteria, kredit parsial, bobot per nomor | P0 | Validasi jumlah bobot, skor maksimum, dan duplikasi kriteria |
| FR-04 | Buat/konfirmasi identitas submission | P0 | PDF terhubung ke mahasiswa yang dikonfirmasi; NIM disimpan string |
| FR-05 | Upload PDF batch, validasi dan progres | P0 | File invalid terisolasi, file lain tetap diproses |
| FR-06 | Render, orientasi, quality check, preprocessing | P0 | Asli dan turunan dapat dibandingkan; kegagalan tidak merusak asli |
| FR-07 | Pemetaan jawaban per nomor, lintas halaman | P0 | Satu jawaban dapat memiliki beberapa region berurutan |
| FR-08 | Transkripsi tulisan tangan literal | P0 | Teks dikaitkan dengan region; tidak terbaca ditandai |
| FR-09 | Usulan penilaian per kriteria | P0 | Kredit, bukti, status, dan alasan ringkas tersedia |
| FR-10 | Visualisasi PDF + overlay + panel jawaban | P0 | Klik nomor membuka region yang benar, termasuk hasil rotasi |
| FR-11 | Review/edit/override dengan jejak audit | P0 | Nilai lama, baru, alasan dan aktor dapat dilacak |
| FR-12 | Finalisasi dan kalkulasi berbobot | P0 | Finalisasi ditolak jika identitas/nomor/nilai belum terselesaikan |
| FR-13 | Ekspor Excel draft/final | P0 | Workbook konsisten dengan snapshot, status draft terlihat jelas |
| FR-14 | Rerun tahap gagal dan pembatalan | P0 | Tidak membuat nilai ganda atau menimpa revisi baru |
| FR-15 | Dashboard progres/distribusi nilai | P1 | Filter status dan grafik hanya memakai populasi berlabel jelas |
| FR-16 | Multi-reviewer, adjudikasi dan banding | P1 | Konflik revisi terdeteksi; keputusan baru tidak menghapus final lama |
| FR-17 | PDF campuran kelas, template QR | P2 | Identitas dan boundary dipastikan sebelum penilaian |
| FR-18 | Rumus kompleks, diagram, jawaban kode | P2 | Per jenis punya metrik dan gate sendiri |

P0 berarti perlu untuk MVP utuh, bukan harus dibangun sekaligus. Urutan pekerjaan mengikuti milestone.

## Kebutuhan nonfungsional dan batas awal

| ID | Target awal | Cara pembuktian |
| --- | --- | --- |
| NFR-01 | Semua perubahan nilai dapat ditelusuri | Audit atas seluruh fixture finalisasi |
| NFR-02 | Nilai backend dan Excel sama sampai 2 desimal | Uji golden workbook + perhitungan independen |
| NFR-03 | Satu file gagal tidak menghentikan batch | Fault injection parser, OCR, timeout |
| NFR-04 | Worker dapat pulih setelah restart | Uji kill/restart + job lease/idempotency |
| NFR-05 | Tidak ada pengiriman scan eksternal pada profil lokal | Audit egress runtime setelah model diprovisi |
| NFR-06 | UI tetap responsif selama inferensi | Pengujian browser dengan job berjalan |
| NFR-07 | Default batas 50 MiB/PDF, 100 halaman/PDF, 25 megapiksel/render | Uji boundary; pilot normal tetap 1–10 halaman |
| NFR-08 | 100 submission pilot selesai tanpa data tertukar | Rekonsiliasi count, hash dan identitas tiap tahap |

Target waktu inferensi ditetapkan setelah M0 pada perangkat nyata. Jangan menjanjikan jumlah detik per halaman sebelum pengukuran. Beri batas CPU/RAM/waktu dan antrean meskipun ukuran file kecil.

## Bukan scope MVP

Penetapan nilai akademik tanpa dosen, deteksi plagiarisme, identifikasi kepribadian dari tulisan, proctoring, plagiarism/AI-writing score, pelatihan model dari nol, integrasi seluruh LMS, aplikasi mobile, dan SaaS multiinstitusi.

## User stories utama

Sebagai dosen, saya menyetujui soal/rubrik sekali lalu menerapkannya konsisten ke satu kelas. Sebagai reviewer, saya melihat bagian gambar yang menjadi dasar skor dan dapat memperbaiki transkripsi tanpa mengubah asli. Sebagai pemilik, saya hanya menyahkan hasil yang sudah lengkap dan dapat mengekspor rekap Excel untuk digunakan di luar aplikasi.
