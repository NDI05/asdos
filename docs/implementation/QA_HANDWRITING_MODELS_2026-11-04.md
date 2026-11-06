# Investigasi awal model tulisan tangan — 4 November 2026

## Cakupan

Satu PDF foto satu halaman yang diberikan pengguna digunakan sebagai sampel pengembangan lokal, bukan benchmark terkunci. Halaman memiliki tulisan tangan Indonesia, garis, coretan, dan nomor yang tidak selalu jelas. PDF dan hasil mentah disimpan privat di `data/handwriting-investigation/`; identitas tidak ditulis di laporan. Tidak ada gambar jawaban yang dikirim ke provider eksternal. Tidak ada anotasi gold yang telah diadjudikasi dan tidak dihitung CER/WER.

## Baseline saat ini

Pada satu percobaan lokal Apple MPS dengan `Qwen/Qwen3-VL-4B-Instruct` revision `ebb281ec70b05090aa6165b016eac8ec08e71b17`, locator menghasilkan JSON tidak valid dan parser menolak hasil. Dengan demikian jalur otomatis tidak menghasilkan area/mapping pada percobaan ini; ini membuktikan kegagalan format pada satu run, bukan bahwa deteksi visual pasti mustahil. Tidak ada penilaian atau perubahan submission pengguna.

Untuk memisahkan pengenalan tulisan dari lokalisasi, dua baris dipotong manual dari halaman dan masing-masing diberikan sebagai gambar kepada transcriber. Qwen membaca baris pendek yang tampak sebagai “metode simbolis” dengan cukup dekat, sedangkan baris lain mengandung beberapa kesalahan kata. Waktu dua baris termasuk cold load 21,07 detik, bukan benchmark latensi.

## Pembanding

`microsoft/trocr-small-handwritten` revision `b4648cfa171985a6745f37ddd637e98c0da958ac` diuji lokal pada dua crop baris yang sama, tanpa soal/rubrik. Kedua hasil mengandung perubahan kata besar; model tidak dapat direkomendasikan menggantikan Qwen berdasarkan percobaan ini. Inference MPS termasuk cold load 13,62 detik, dan inisialisasi melaporkan parameter pooler hilang. TrOCR adalah recognizer baris, sehingga tidak menggantikan deteksi area/pemetaan. Model card menyatakan fine-tuning IAM dan penggunaan crop satu baris. Hasil ini hanya sampel eksplorasi, bukan perbandingan representatif antara keluarga model.

`PaddlePaddle/latin_PP-OCRv5_mobile_rec` revision `ab2cd5cc5fa6309be2e5acdfe66eca2c2c127d57` diuji pada dua crop yang sama di CPU menggunakan instalasi terpisah dan model lokal. Pada baris pertama hasilnya salah membaca beberapa huruf; pada baris kedua ada beberapa kata yang terbaca tetapi juga banyak kesalahan. Waktu kedua crop termasuk cold load adalah 7,28 detik, tetapi tidak dapat dibandingkan langsung dengan Qwen/TrOCR karena perangkat berbeda. PaddleOCR mengenali teks dari crop, bukan pemetaan nomor; deteksi area/baris belum diuji. Hasil ini tidak cukup untuk merekomendasikannya sebagai pengganti default.

## Langkah evaluasi

`latin_PP-OCRv5_mobile_rec` masih layak dievaluasi sebagai pembanding karena dokumentasi PaddleOCR mencantumkan dukungan bahasa Indonesia; dukungan bahasa bukan bukti kemampuan tulisan tangan pada sampel ini. Gunakan detector terpisah untuk baris/area dan ukur akurasinya. Varian resmi `Qwen/Qwen3-VL-8B-Instruct` juga kandidat lokal jika pengujian kapasitas memori memungkinkan. Ukur pemetaan, region yang hilang, CER/WER literal, angka/negasi, waktu dan penggunaan memori pada kumpulan berizin dengan penulis dan gold yang diverifikasi; pisahkan development dari locked test. Jangan aktifkan model sebagai default sebelum gate evaluasi proyek terpenuhi.

Sumber: [PaddleOCR model bahasa](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html), [TrOCR model card](https://huggingface.co/microsoft/trocr-small-handwritten), [Qwen3-VL-8B model card](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct), dan `docs/09-evaluation-and-dataset.md`.

## Uji lanjutan deteksi dan pemulihan

Pada foto yang sama, `PP-OCRv5_mobile_det` revision `0d63e78e2b680928f6b1747d76a08db6e645efb7` digabungkan dengan Latin recognizer pada CPU, dalam lingkungan eksperimen terpisah. Sebanyak 31 crop teks setelah area identitas dihasilkan dan dibaca; inspeksi overlay menunjukkan beberapa baris awal serta bagian lain terlewat dan banyak kesalahan karakter. Angka 31 adalah jumlah kotak, bukan tingkat keberhasilan. Model ini belum layak menggantikan jalur default berdasarkan pengamatan tersebut.

Pada Qwen 4B, keluaran awal locator di sampel memiliki bbox tidak lengkap. Prompt alternatif yang diuji dapat menghasilkan daftar kosong, menyalin contoh, atau hanya menemukan nomor, sehingga format JSON valid saja bukan bukti cakupan. Percobaan perbaikan dengan gambar dan keluaran lama sebagai data tak tepercaya menghasilkan empat kotak valid, namun inspeksi visual menunjukkan sebagian tulisan pada celah antara dua kotak tidak tercakup. Karena itu `answer-localization.v2` membatasi satu perbaikan dan menandai seluruh hasil perbaikan `localization_repair_review`; hasil tersebut tidak dipetakan otomatis dan reviewer harus memeriksa halaman penuh serta menambahkan area yang terlewat. Hasil kosong setelah kegagalan format tidak dianggap bukti halaman kosong. Bila perbaikan tetap invalid, proses gagal jelas dan alur manual tetap tersedia.

Ini adalah satu halaman development tanpa transkripsi gold dan tanpa locked test; tidak membuktikan akurasi atau bahwa semua jawaban ditemukan. Pengujian terkontrol lintas penulis tetap wajib sebelum promosi kandidat atau klaim generalisasi.

Re-run implementasi final pada gambar yang sama menghasilkan empat crop serta teks OCR di masing-masing crop dan flag `localization_repair_review`; penerapan matcher terhadap empat nomor sintetis meninggalkan keempatnya untuk review. Ini uji adapter + matcher secara lokal, bukan uji browser/worker end-to-end pada scan ini. Inspeksi sebelumnya menunjukkan satu bagian di celah tidak tercakup, sehingga hasil belum menyelesaikan pemetaan otomatis penuh untuk contoh ini. 72 tes backend, 19 tes frontend, dan build lulus.

### Qwen 8B thinking: percobaan awal

`qwen3-vl:8b` dari Ollama (8.2B Q4_K_M, digest `9cf69da2b16d`, 100% GPU lokal) ternyata varian thinking. Dua percobaan API chat, termasuk dengan `think=false`, menghabiskan batas token tanpa keluaran akhir; uji teks sintetis menunjukkan teks masih muncul di field thinking. Ini kegagalan runtime/konfigurasi, bukan hasil OCR yang dapat dibandingkan.

Percobaan eksplorasi `raw` menggunakan prefix penutup thinking secara eksplisit untuk memaksa jawaban langsung (bukan konfigurasi produksi) memerlukan sekitar 49 detik pada halaman dan dua crop. Locator menghasilkan empat kotak tetapi format akar berupa array, bukan objek kontrak; inspeksi koordinat juga menunjukkan area di celah sekitar jawaban bernomor 2 tidak tercakup. Kedua crop memiliki kesalahan kata. Hasil ini tidak membuktikan model lebih buruk atau lebih baik secara umum. Varian instruct diuji terpisah bila tersedia; jangan mengganti default berdasarkan hasil ini.

### Qwen 8B instruct

`qwen3-vl:8b-instruct` (8.2B Q4_K_M, digest `70e58e37beb1`, Ollama lokal GPU, tanpa thinking, context 8192) menghasilkan JSON yang lolos schema untuk empat kotak pada scan yang sama. Overlay menunjukkan kotak pertama mencakup sebuah blok lain yang juga bertanda nomor; pemisahan dan pengaitan nomor tersebut tetap ambigu dan perlu tinjauan. Dua crop baris menunjukkan kesalahan kata: satu baris pendek berubah menjadi kata lain, baris kedua masih mengandung kesalahan karakter. Jalur tiga inferensi termasuk muat model memerlukan sekitar 59 detik pada percobaan ini, bukan pengukuran performa yang terkontrol. Inference 8B dilakukan langsung pada Ollama terpisah, belum diintegrasikan ke worker ASDOS. Hasil satu halaman tanpa gold tidak membuktikan 8B lebih baik atau cukup aman sebagai default; model tetap kandidat untuk benchmark lintas penulis.
