# 20 — Pemilihan Model Pralatih Terbuka dan Gratis

Tanggal: 3 November 2026. Dokumen ini memperjelas keputusan awal berdasarkan arahan pemilik proyek: **gunakan model yang sudah terlatih untuk MVP, tanpa melatih model dari nol dan tanpa fine-tuning terlebih dahulu**. Tidak ada model yang diunduh atau dijalankan dalam pekerjaan riset ini.

## Keputusan awal

Gunakan **Qwen/Qwen3-VL-4B-Instruct sebagai model pertama untuk eksperimen prototipe**. Bandingkan transkripsinya dengan PP-OCRv5 Latin/Indonesia dan, bila perlu, PaddleOCR-VL serta TrOCR handwritten. Ini urutan eksperimen, bukan klaim Qwen telah menjadi pemenang benchmark atau memenuhi gate rilis.

Model pralatih sudah memiliki bobot hasil pelatihan pengembangnya. ASDOS memuat bobot itu untuk inferensi, memberi instruksi transkripsi/penilaian, lalu memvalidasi hasilnya. Memasukkan soal dan rubrik ke konteks penilaian tidak sama dengan melatih ulang model. Pembuatan dataset uji lokal tetap diperlukan untuk mengukur kesalahan, walaupun tidak melakukan training.

## Model yang diperiksa

| Model dan tautan resmi | Lisensi pada model card | Peran yang direncanakan | Batas penting |
| --- | --- | --- | --- |
| [Qwen/Qwen3-VL-4B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) | Apache-2.0 | Kandidat pertama transkripsi gambar; checkpoint yang sama diuji sebagai evaluator jawaban pada konteks terpisah | Model umum visual/teks; kemampuan grading sesuai rubrik dan handwriting Indonesia belum teruji pada ASDOS |
| [PaddlePaddle/PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL) | Apache-2.0 | Pembanding khusus document parsing dan pembacaan isi halaman/crop | Core dipasarkan sebagai 0.9B; parameter lebih sedikit tidak otomatis menjamin akurasi/memori tertentu; bukan penilai akademik |
| [microsoft/trocr-base-handwritten](https://huggingface.co/microsoft/trocr-base-handwritten) | MIT | Pembanding pengenalan tulisan tangan pada crop per baris | Fine-tuned IAM; raw model untuk satu baris, bukan PDF penuh. Generalisasi Indonesia/folio wajib diuji |
| [PaddlePaddle/latin_PP-OCRv5_mobile_rec](https://huggingface.co/PaddlePaddle/latin_PP-OCRv5_mobile_rec) | Apache-2.0 | Baseline OCR Latin/Indonesia, dipasangkan dengan detector terpisah | Recognizer menerima crop teks; tidak menemukan semua region sendiri dan tidak menentukan benar/salah |

Seluruh nama di tabel adalah checkpoint tertentu, bukan semua produk dengan merek yang sama. Lisensi detector, runtime, dependency dan checkpoint tambahan juga diperiksa saat versi implementasi dikunci. Model card Latin PP-OCRv5 memuat beberapa deskripsi yang tampak tersalin dari model lain; dukungan Indonesia merujuk [dokumentasi multilingual resmi](https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html), yang menyertakan Indonesia pada jalur Latin. Jangan menjadikan angka akurasi pada card tersebut sebagai akurasi handwriting mahasiswa.

Model card PaddleOCR-VL membahas handwriting sebagai salah satu skenario dan menawarkan parsing teks/tabel/formula/chart. Itu alasan untuk mengujinya, bukan bukti bahwa semua tulisan buruk dapat dibaca. Ketersediaan versi lain/lebih baru tidak mengubah default otomatis; perubahan checkpoint harus dibandingkan pada protokol yang sama.

Istilah yang paling tepat untuk daftar ini adalah model pralatih dengan **bobot tersedia dan lisensi terbuka**. Jangan menyimpulkan bahwa seluruh data pelatihan atau proses pelatihan pengembangnya turut tersedia hanya karena bobot berlisensi Apache-2.0/MIT.

## Mengapa mulai dengan Qwen3-VL-4B

Dokumentasi Qwen3-VL menyediakan kemampuan OCR, pemahaman gambar, dan pemahaman teks. Karena ASDOS membutuhkan transkripsi serta usulan penilaian semantik, satu checkpoint menjadi titik awal eksperimen yang sederhana. Penilaian kelayakan ini adalah keputusan engineering; belum ada bukti bahwa checkpoint ini paling akurat pada dataset pengguna.

Jalankan dua tugas secara terpisah:

1. **Transkripsi:** input gambar potongan jawaban dan instruksi literal. Jangan berikan soal, kunci atau rubrik agar model tidak tergoda membetulkan jawaban mahasiswa.
2. **Penilaian:** input transkripsi yang dipilih, soal, rubrik approved dan referensi bukti. Minta keputusan kredit per kriteria, bukan nilai total bebas.

Konteks kedua tidak memakai riwayat percakapan transkripsi dan tidak mencampur identitas mahasiswa. Simpan versi prompt/input/model untuk masing-masing run. Penggunaan satu checkpoint pada dua tugas tidak menjamin independensi error; evaluasi oracle-text dan end-to-end tetap diperlukan. Model khusus OCR pembanding cukup menghasilkan teks; penilaian semantik tetap memakai evaluator terpisah.

## Alur komputasi yang dibangun sendiri

Yang dikembangkan oleh proyek adalah integrasi aplikasi, bukan bobot model baru:

| Langkah | Komponen |
| --- | --- |
| PDF menjadi gambar | Renderer pypdfium2/PDFium; bukan model bahasa |
| Pemeriksaan kualitas dan orientasi | Praolah terkontrol dan, jika perlu, komponen pretrained |
| Potongan dan nomor jawaban | Layout/mapping yang dapat dikoreksi dosen |
| Tulisan menjadi transkripsi | Model pralatih terpilih, awal eksperimen Qwen3-VL-4B |
| Pemenuhan rubrik | Evaluator pralatih dengan output terstruktur dan validasi |
| Bobot dan nilai akhir | Kode Decimal deterministik sesuai dokumen05 |
| Pengesahan dan Excel | Review manusia, snapshot, lalu exporter; tidak menilai ulang |

Model tidak diberi shell/tools, hak menulis nilai final, atau akses bebas jaringan. Instruksi yang tertulis pada lembar jawaban tetap diperlakukan sebagai isi jawaban, bukan perintah sistem.

## Menghadapi tulisan yang bagus sampai sangat sulit

Uji tiga kelompok keterbacaan yang dianotasi manusia: mudah, sedang, dan sulit; tambahkan flag tidak terbaca bila penilai tidak dapat menentukan teks dengan cukup pasti. Kelompok bukan dasar pengurangan nilai. Laporkan juga folio/HVS, tinta/pensil, rotasi, coretan, bahasa campuran dan angka/negasi yang bisa membalik makna.

Untuk scan bermasalah: perbaiki orientasi/kontras secara non-destruktif, tampilkan crop dengan resolusi memadai, dan bandingkan hasil dengan gambar asli. Penghapusan garis folio tidak otomatis diaktifkan karena dapat menghapus simbol atau bagian huruf. Perbesar tampilan untuk review, tetapi jangan menganggap upscaling menciptakan detail yang tidak ada.

Jika teks masih meragukan, simpan bagian ambigu/unreadable dan arahkan ke dosen. Kesepakatan dua model bukan bukti pasti benar; ketidaksepakatan bisa menjadi sinyal review bila eksperimen pembanding digunakan. Jangan memberi skor0 hanya karena OCR gagal. Jangan membuat klaim “pasti bisa membaca tulisan sejelek apa pun”.

## Arti gratis pada rancangan ini

Bobot berlisensi Apache-2.0/MIT pada tabel dapat digunakan tanpa biaya lisensi/per halaman ketika dijalankan sendiri, mengikuti syarat lisensinya. ASDOS tidak mewajibkan API komersial untuk alur MVP.

Tetap ada kebutuhan komputasi, listrik, penyimpanan, dan waktu review. Menjalankan bobot di laptop/server sendiri berbeda dari memakai hosted API atau menyewa GPU; layanan hosting dapat berbayar atau memiliki kuota. Rencana ini tidak bergantung pada free tier yang sewaktu-waktu berubah. Kapasitas RAM/VRAM dan kecepatan belum diukur, sehingga tidak dijanjikan model4B akan muat/cepat pada perangkat tertentu.

## Eksperimen awal dan syarat keputusan

1. Bekukan manifest sampel berizin dan split berbasis penulis sebelum tuning prompt/preprocessing.
2. Bandingkan Qwen3-VL-4B dengan baseline PP-OCRv5 Latin pada subset development yang sama. Tambahkan PaddleOCR-VL/TrOCR bila analisis error dan perangkat membenarkan eksperimen tersebut; jangan memuat semua model sekaligus.
3. Ukur CER/WER, pemetaan nomor, error angka/negasi, abstention/coverage, p50/p95 waktu dan peak RAM/VRAM per kelompok keterbacaan.
4. Uji evaluator pada transkripsi manusia dahulu, lalu pada hasil OCR. Ukur error skor per kriteria dan nilai berbobot, bukan text similarity saja.
5. Pilih konfigurasi pada development, threshold pada calibration, lalu uji locked test sesuai dokumen09. Tetap wajib pengesahan dosen untuk nilai final MVP.

Hasil dapat berupa model yang cukup baik untuk proposal nilai, model yang hanya membantu transkripsi, atau workflow manual pada pola tulisan tertentu. Training/fine-tuning baru dibahas sebagai pekerjaan lanjutan melalui keputusan baru jika pretrained belum cukup dan pemilik proyek menghendakinya. Tidak ada training tersembunyi atau pengiriman data mahasiswa untuk training otomatis.

## Hubungan dengan rencana sebelumnya

Dokumen ini melengkapi [pipeline CV](04-vision-and-handwriting.md), [penilaian](05-grading-and-scoring.md), [evaluasi](09-evaluation-and-dataset.md), [biaya/perangkat](12-infrastructure-costs-operations.md), dan ADR-003/008 pada [keputusan](14-risks-and-decisions.md). Pemenang/default rilis tetap menunggu benchmark; keputusan yang sudah pasti adalah memakai pretrained tanpa training/fine-tuning pada MVP.

Sumber kemampuan Qwen: [repository resmi](https://github.com/QwenLM/Qwen3-VL). Tautan model pada tabel menjadi sumber checkpoint/lisensi; keterbatasan TrOCR merujuk bagian Intended uses & limitations model card. Seluruh rekomendasi ASDOS di sini adalah rancangan, bukan hasil uji model.
