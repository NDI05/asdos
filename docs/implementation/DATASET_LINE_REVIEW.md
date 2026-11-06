# Review baris dan eksperimen TrOCR lokal

## Mulai review

Dari root proyek:

```bash
.venv/bin/python -m scripts.dataset_review
```

Buka alamat lengkap yang dicetak terminal. Token ada dalam fragment URL lalu dihapus dari address bar, sehingga reload perlu alamat awal dari terminal. Server hanya mendengarkan 127.0.0.1. Nama/NIM, gambar dan revisi tetap privat; tidak ada upload model/data. Stop dengan Ctrl+C. Restart server review lama agar memakai source baru.

1. Pilih halaman. Cocokkan nama/NIM, ID penulis pseudonim konsisten lintas pertemuan, dan ID submission untuk kelompok halaman satu tugas. Simpan identitas terlebih dahulu.
2. Di **Review per baris**, pilih satu baris. Kotaknya disorot pada scan; preview crop ditampilkan di formulir.
3. Koreksi teks literal. Ganti kotak dengan menarik pada scan atau mengisi kiri/atas/kanan/bawah dalam piksel. Kotak memakai origin kiri atas dan skala raster asli, bukan ukuran tampilan. Zoom tidak mengubah koordinat.
4. Pilih jenis: jawaban bebas identitas, identitas, tidak terbaca, atau bukan bahan training. Bagian tidak terbaca/pengecualian membutuhkan alasan. Identitas tidak menjadi label atau crop training. Tandai seluruh area identitas; gunakan tambah baris jika belum terdeteksi.
5. Centang konfirmasi hanya sesudah teks, kotak, dan jenis diperiksa. Perubahan teks/kotak/jenis membatalkan konfirmasi. Tambahkan baris yang dilewatkan OCR. Pengecualian mempertahankan anotasi asli, tidak menghapus bukti.
6. Isi split penulis: train, development, calibration, atau locked_test. Seluruh pertemuan/halaman penulis yang sama harus memiliki split sama. Pastikan setiap split mempunyai penulis sesuai rencana sebelum membekukan snapshot.
7. Periksa seluruh halaman dan centang konfirmasi cakupan/identitas. Simpan review baris. Konfirmasi ini termasuk pemeriksaan tidak ada identitas dalam crop jawaban. Perubahan revisi identitas membatalkan keterkaitan konfirmasi lama dan memerlukan review baris ulang.

Review tingkat halaman lama tetap tersimpan; tidak otomatis dianggap konfirmasi per baris. Baris baru/manual memakai ID tersendiri. Revisi disimpan immutable dan stale writes ditolak. Navigasi memperingatkan jika ada perubahan yang belum disimpan.

## Bekukan snapshot

```bash
.venv/bin/python -m scripts.export_reviewed_lines \
  --dataset data/private/handwriting-dataset-v1 \
  --output data/private/reviewed-lines-v1
```

Ekspor menolak halaman belum lengkap, identitas stale, baris belum dikonfirmasi, split kosong, penulis/gambar yang melintasi split dan kotak jawaban yang memotong area identitas. Semua halaman dalam inventaris harus ditinjau. Tidak terbaca/identity/exclude tidak dilatih. Snapshot mencatat revisi dan hash, teks literal, bbox, serta pseudonim; tidak menyalin nama/NIM. Gambar sumber tetap mengandung identitas privat, sehingga jangan membagikan direktori snapshot/sumber. Runtime hanya memberi model crop jawaban yang dikonfirmasi. Review manusia bukan jaminan bebas salah: near-duplicate, anotasi ganda dan adjudikasi masih perlu pemeriksaan sesuai docs/09.

Output tidak ditimpa. Jika review berubah, gunakan direktori versi baru. Loader training/evaluasi juga memeriksa hash gambar, bbox, status, split serta exact duplicate crop melintasi split.

## Checkpoint lokal

```bash
.venv/bin/python -m scripts.provision_trocr
```

Mengunduh `microsoft/trocr-base-handwritten` revision `eaacaf452b06415df8f10bb6fad3a4c11e609406` (MIT), hanya safetensors dan konfigurasi/tokenizer. Hash file tersimpan di `models/trocr-base-handwritten/asdos-trocr-manifest.json`. Tidak membaca atau mengunggah scan. Download yang terputus dapat dilanjutkan dengan perintah yang sama.

## Ukur baseline, latih, dan bandingkan

```bash
.venv/bin/python -m scripts.evaluate_trocr \
  --manifest data/private/reviewed-lines-v1/annotations.jsonl \
  --model-dir models/trocr-base-handwritten \
  --split development --output data/private/trocr-baseline-v1

.venv/bin/python -m scripts.train_handwriting_local \
  --manifest data/private/reviewed-lines-v1/annotations.jsonl \
  --model-dir models/trocr-base-handwritten \
  --epochs 3 --output data/private/trocr-training-v1

.venv/bin/python -m scripts.evaluate_trocr \
  --manifest data/private/reviewed-lines-v1/annotations.jsonl \
  --model-dir data/private/trocr-training-v1/best \
  --split development --output data/private/trocr-after-v1
```

Training memakai batch satu, AdamW 5e-5, clipping 1, seed 42, dan checkpoint terbaik berdasarkan development CER. Ia menghitung baseline serta CER/WER tiap epoch; berhenti jika development CER tidak membaik. Calibration/test tidak diberikan pada optimizer. Report mencatat hash input/bobot, loss, metrics dan delta development CER. Nilai delta positif berarti CER development turun; bukan bukti generalisasi ke locked test. Model tidak otomatis mengganti default aplikasi. Jika OOM/inference gagal, run dilaporkan gagal; jangan menafsirkan sebagian hasil sebagai keberhasilan.

CER literal adalah edit karakter dibagi jumlah karakter referensi; WER memakai token whitespace. Tidak ada normalisasi ejaan/huruf besar/angka. Keduanya dapat melebihi 1 jika banyak insertions. Report memuat numerator/denominator, coverage, gagal inference, serta generasi yang mencapai batas token. Referensi kosong dilaporkan terpisah dan denominator nol menjadi null. Prediksi teks tersimpan hanya pada file privat. Trainer menolak run baseline/development yang gagal atau mencapai batas generasi; evaluasi terpisah tetap melaporkan kondisi itu secara eksplisit.

Locked test hanya boleh dibuka setelah model/prompt/preprocessing/gate dibekukan. Gunakan manifest snapshot yang sama untuk base dan fine-tuned, `--split locked_test --allow-locked-test`, dan direktori output berbeda. Jangan memperbaiki model berdasarkan test yang sama. Tool tidak mengesahkan pembekuan atau gate model, dan tidak mengimplementasikan anotasi ganda/adjudikasi otomatis.

## Smoke perangkat tanpa mahasiswa

```bash
.venv/bin/python -m scripts.trocr_checkpoint_smoke \
  --output data/private/trocr-checkpoint-smoke-v1
```

Ini hanya inference dan satu langkah backward pada gambar cetak sintetis. Tidak menyimpan model hasil langkah tersebut dan tidak mengukur akurasi tulisan tangan mahasiswa.
