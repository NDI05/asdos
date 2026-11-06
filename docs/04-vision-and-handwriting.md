# 04 — PDF, Computer Vision, dan Tulisan Tangan

## Tujuan dan batas pembuktian

Tugas ini memerlukan document understanding, handwriting recognition, dan layout analysis. PDF scan sering hanya berisi gambar, sehingga ekstraksi text layer saja tidak memadai. Jangan menganggap dukungan bahasa pada OCR berarti akurasi tulisan tangan Indonesia sudah terbukti.

## Pipeline per tahap

| Tahap | Input → output | Pemeriksaan/kegagalan |
| --- | --- | --- |
| Intake | PDF → metadata/hash dan hasil validasi | Signature, ukuran, halaman, terenkripsi, parser timeout |
| Render | Halaman PDF → RGB image | Resolusi, batas piksel/RAM, page index stabil |
| Quality | Image → flags dan metrik | Blur, kontras, pencahayaan, clipping, halaman miring/kosong |
| Transform | Image → corrected image + transform | Orientasi/deskew; asli selalu tersedia |
| Layout | Image → region/line kandidat | Reading order, nomor soal, header identitas, margin |
| Mapping | Region → question ID dan urutan | Nomor tidak pasti, lanjutan, subnomor, overlap |
| Transcribe | Region images → literal text | Karakter ambigu, coretan, omission, schema invalid |
| Validate | Transcript + mapping → artifact tervalidasi | Evidence ID harus berasal dari region nyata |
| Review | Artefak → revisi manusia | Koreksi tidak menghapus hasil asli |

## Rendering dan koordinat

Default render awal 250 DPI; 200–300 DPI menjadi rentang uji, bukan janji angka optimal. Gunakan gambar warna sebagai master turunan agar tinta merah/biru dan coretan tidak hilang. Upscaling tidak mengembalikan detail yang sudah hilang.

PDFium tidak thread-safe; gunakan proses render terisolasi dan tutup document/page/bitmap secara eksplisit. Jangan menjalankan render paralel lewat beberapa thread dalam proses yang berbagi PDFium state. Jika menambah proses paralel, pastikan batas total RAM/piksel seluruh proses tetap terkendali.

Gunakan origin kiri atas, `page_index` mulai 0, dan bounding polygon dalam koordinat normalisasi `[0,1]` pada gambar canonical setelah orientasi. Simpan juga lebar/tinggi piksel, PDF CropBox/MediaBox, rotasi asli, versi render, serta matriks/homography dari original render ke canonical dan inversnya. PDF memiliki konvensi koordinat berbeda; satu modul transform harus menangani konversi backend ↔ PDF.js ↔ layar.

Untuk deskew affine, simpan matriks dan perubahan canvas/padding. Untuk perspective correction, simpan homography dan titik referensi. Bila dewarping nonlinier ditambahkan, matriks saja tidak cukup; simpan displacement map atau jangan aktifkan fitur tersebut. Uji round-trip koordinat pada rotasi 0/90/180/270 dan zoom layar. Overlay salah adalah masalah penilaian, bukan kosmetik.

## Folio bergaris dan HVS

Folio: garis horizontal dapat menutupi huruf, garis margin terlihat seperti karakter, folio ganda punya lipatan/bayangan. HVS: baris tidak konsisten, nomor dapat di margin atau menyatu dengan paragraf. Scan fotokopi dapat memuat bleed-through, pensil tipis, noise, atau clipping.

Praolah kandidat: crop tepi, orientation detection, deskew berbasis projection/Hough, normalisasi pencahayaan, denoise ringan, dan line suppression. Semua bersifat opsional per eksperimen. Jangan menerapkan penghapusan garis sebagai default tanpa ablation: garis pecahan, minus, underscore dan bagian huruf dapat ikut hilang. Simpan varian `original_render`, `deskewed`, dan `line_suppressed` hanya jika memang digunakan; catat parameter dan hash masing-masing.

Quality score menjadi sinyal antrean review. Threshold ditentukan dari calibration set, bukan angka blur yang dikarang. Halaman yang diduga kosong harus dibandingkan dengan isi/rangkaian halaman dan dikonfirmasi sebelum jawaban dianggap tidak ada.

## Segmentasi dan pemetaan nomor

M0 membandingkan pemetaan manual, heuristik numbering dari teks/posisi, dan pemetaan berbantuan VLM. Mulai MVP dengan deteksi kandidat yang bisa dikoreksi manusia. Model harus dapat abstain alih-alih menebak nomor.

- Normalisasi label nomor menjadi question ID stabil; label tampilan `2.a`, `2a`, dan `2(a)` dapat dipetakan setelah verifikasi.
- Jangan memakai setiap angka sebagai nomor soal: angka pada isi jawaban, tanggal, formula dan enumerasi internal berbeda.
- Satu jawaban terdiri dari satu atau banyak region, termasuk region lintas halaman yang tidak bersebelahan.
- Reading order region disimpan eksplisit; soal yang dijawab tidak berurutan tetap sah.
- Satu region tidak boleh diam-diam dihitung dua kali. Jika dua pertanyaan sengaja berbagi bukti, simpan relasi eksplisit dan alasan reviewer.
- Area tidak terpetakan tetap disimpan dan memblokir finalisasi bila mungkin mengandung jawaban.
- Header nama/NIM dipisahkan dari isi yang dikirim ke evaluator.

## Kandidat model dan eksperimen

| Kandidat | Peran dalam eksperimen | Keterbatasan yang harus diuji |
| --- | --- | --- |
| PP-OCRv5 detector + Latin recognizer | Baseline OCR teks/nomor dan layout berbasis boxes | Dukungan Indonesia terdokumentasi, kualitas handwriting lokal belum terbukti |
| Qwen/Qwen3-VL-4B-Instruct | Transkripsi potongan dan usulan mapping; juga kandidat evaluator terpisah | Halusinasi, omission, perubahan kata, biaya image tokens dan RAM |
| Qwen3-VL varian lebih besar | Pembanding jika 4B gagal gate dan perangkat tersedia | Jangan menganggap ukuran lebih besar pasti lebih baik |
| microsoft/trocr-base-handwritten | Baseline tambahan pada crop baris | Fine-tuned IAM; raw model untuk satu baris, bukan PDF multi-layout; domain Indonesia perlu pengujian |

Paket tidak menetapkan pemenang. Sumber S01–S04 menjelaskan kemampuan dan keterbatasan resmi; hasil benchmark produsen tidak menggantikan dataset ujian lokal. Kandidat OCR lain boleh ditambahkan melalui ADR bila matriks di atas gagal acceptance. Fine-tuning baru dipertimbangkan setelah ada dataset berizin dan analisis kesalahan yang menunjukkan kebutuhan.

## Kontrak transkripsi literal

Input transcriber hanya gambar region, petunjuk bahasa, dan aturan format. Jangan kirim soal/kunci/rubrik; ini mengurangi risiko menormalkan jawaban salah menjadi benar. Keluaran memiliki `region_id`, teks, span/line refs, penanda bagian tidak terbaca, language, model revision, dan flags. Jika engine tidak menyediakan confidence yang dapat dikalibrasi, isi confidence `null`; jangan membuat angka keyakinan palsu.

Tanda ketidakpastian terstruktur tidak dianggap isi tulisan. Simpan alternatif seperti `0/O`, `1/l`, `5/S` atau simbol minus yang meragukan dengan referensi crop. Jangan memilih alternatif berdasarkan kunci. Kata/angka yang tidak terlihat tidak boleh dilengkapi karena konteks terdengar masuk akal.

Untuk coretan, simpan apakah teks tampak dibatalkan dan bukti visual. Kebijakan “pakai jawaban terakhir” harus berada di rubrik/aturan ujian, bukan asumsi OCR. Tabel sederhana mempertahankan urutan baris/kolom. Rumus/diagram yang belum didukung diberi flag dan dialihkan ke reviewer.

## Protokol pemilihan jalur

Bandingkan A: OCR biasa → mapping → evaluator; B: VLM transkripsi → evaluator; C: mapping/transkripsi manual → evaluator sebagai pembanding oracle. Pada masing-masing jalur ukur error OCR, error mapping, error nilai, biaya, waktu, dan review burden. Pemrosesan campuran hanya ditambahkan jika peningkatannya mengalahkan kompleksitas operasional.

Jalankan OCR tanpa kunci, ukur evaluator dengan teks manusia terlebih dahulu, kemudian ukur seluruh pipeline. Pemisahan ini menunjukkan apakah kegagalan terjadi pada pembacaan atau penalaran penilaian. Jangan memperbaiki prompt berdasarkan locked test; gunakan validation set lalu evaluasi test sekali untuk keputusan.

## Exit criteria CV untuk MVP

Tidak ada halaman/region yang hilang tanpa flag, semua transkripsi terhubung ke bukti, identity dan mapping ambigu memicu review, transform teruji, dan kandidat memenuhi gate M0/M3 di [evaluasi](09-evaluation-and-dataset.md). Bila tidak, rilis hanya alur koreksi berbantuan/manual dengan keterbatasan eksplisit; jangan mengiklankan autonomous grading.
