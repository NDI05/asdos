# 09 — Dataset, Benchmark, dan Pemilihan Model

## Pertanyaan eksperimen

Apakah model dapat membaca jawaban Indonesia pada folio/HVS tanpa mengubah makna? Apakah region dipetakan ke nomor yang tepat? Apakah evaluator memberi kredit sesuai rubrik pada teks yang sudah benar? Berapa kesalahan nilai ketika seluruh pipeline digabung? Berapa waktu dosen yang benar-benar dihemat setelah koreksi dan pengesahan?

Tidak ada dataset maupun benchmark yang dijalankan dalam paket perencanaan ini. Semua threshold berikut adalah **gate usulan** yang harus dikaji dosen/maintainer pada M0 dan dibekukan sebelum locked test dibuka.

## Harness evaluasi lokal

`uv run --locked python -m scripts.evaluate_handwriting` membaca satu manifest JSON privat, bukan PDF. Manifest memuat teks gold yang sudah diadjudikasi, prediksi dari run yang telah selesai, ID penulis pseudonim, hash sumber, split, dan provenance. Validator memeriksa hash/versi wajib, ID sampel unik, serta mencegah writer atau hash dokumen yang sama muncul pada split berbeda. Laporan agregat memuat CER/WER literal, coverage abstention, mapping accuracy, MAE/p95 skor bila disertakan, error identitas/halaman kritis, dan provenance tanpa mengeluarkan teks mentah.

Contoh kerangka manifest (isi data nyata tetap di lokasi privat dan tidak masuk Git):

```json
{
  "schema_version": "asdos-evaluation.v1",
  "dataset": {
    "manifest_id": "uji-lokal-v1",
    "consent_status": "approved",
    "retention_policy": "sesuai-persetujuan-institusi",
    "split_manifest_sha256": "<sha256-manifest-split>"
  },
  "provenance": {
    "model_id": "Qwen/Qwen3-VL-4B-Instruct",
    "model_revision": "<revision-tetap>",
    "checkpoint_sha256": "<sha256-checkpoint>",
    "prompt_version": "literal-transcription.v1",
    "preprocessing_version": "region-crop.v1",
    "runtime": "<versi-runtime>",
    "device": "<perangkat>",
    "code_revision": "<commit-atau-versi-source>",
    "dependency_lock_sha256": "<sha256-uv.lock>"
  },
  "samples": [
    {
      "sample_id": "anon-001-region-01",
      "writer_id": "writer-acak-01",
      "split": "development",
      "source_sha256": "<sha256-dokumen-sumber>",
      "gold_text": "teks literal hasil adjudikasi",
      "predicted_text": "teks prediksi",
      "gold_question_id": "q1",
      "predicted_question_id": "q1",
      "status": "proposed",
      "critical_error": false,
      "identity_error": false,
      "missing_page_count": 0
    }
  ]
}
```

Nilai placeholder hash harus diganti string 64 digit hex. Jalankan satu split secara eksplisit, misalnya `uv run --locked python -m scripts.evaluate_handwriting --manifest /path/privat/eval.json --split development`. `--output /path/privat/report.json` menyimpan laporan lokal. Harness selalu memberi `gate_decision: not_assessed`: ia menghitung metrik dan mencegah kebocoran split, tetapi tidak mengesahkan izin, kualitas anotasi, pembekuan gate, atau kelayakan model. Locked test baru dipakai setelah prompt/preprocessing/gate dibekukan dan harus dilaporkan apa adanya.

## Pengumpulan bertahap

| Tahap | Target data | Tujuan |
| --- | --- | --- |
| Feasibility M0 | ≥40 PDF, ≥20 penulis, ≥80 halaman, ≥200 jawaban | Menemukan failure mode, biaya anotasi, dan kelayakan awal |
| Pilot rilis | ≥100 PDF, ≥50 penulis, ≥300 halaman, ≥1.000 jawaban | Uji end-to-end, distribusi kesalahan dan beban review |
| Perluasan | Data lintas mata kuliah/perangkat scan | Mengukur generalisasi, bukan menambah klaim dari test lama |

Target jumlah tersebut dapat memerlukan pengumpulan beberapa tugas/ujian dan bukan prasyarat memulai code skeleton. Waktu mendapatkan izin/anotasi dipisahkan dari estimasi coding. Jika target tidak tercapai, laporkan jumlah aktual dan keterbatasan; jangan mengganti sampel nyata dengan augmentasi lalu menghitungnya sebagai penulis baru.

Strata: folio/HVS, tulisan rapi/sulit menurut label annotator, tinta/pensil, pencahayaan/rotasi/blur, Bahasa Indonesia/Inggris/campuran istilah teknis, jawaban pendek/panjang, halaman tunggal/lintas halaman, nomor berurutan/tidak, coretan dan kosong. Tag strata dipakai untuk analisis, bukan atribut untuk menghukum mahasiswa.

## Izin dan ground truth

Simpan sumber, dasar izin penggunaan, batas penggunaan, retention, dan hak publikasi terpisah. Dataset mahasiswa privat tidak otomatis boleh dipublikasikan karena aplikasinya open source. Redaksi identitas dari salinan anotasi, periksa nama/NIM di margin, dan gunakan ID pseudonim. Jangan meminta model menebak identitas yang sudah dihapus.

Ground truth mencakup halaman/identitas yang sudah diverifikasi, region polygon dan reading order, mapping question ID, transkripsi literal, bagian tidak terbaca, serta skor per kriteria berdasarkan rubrik dosen. Setidaknya 20% sampel dipilih acak untuk anotasi ganda; semua ketidaksepakatan dan kasus sulit juga diperiksa dua penilai. Ukur agreement sebelum adjudikasi, lalu adjudikator menetapkan gold. Penilaian manusia tidak dianggap bebas kesalahan.

## Split dan pencegahan leakage

Usulan split berbasis **penulis**: train/adaptation 40%, development 20%, calibration 20%, locked test 20%. Pada 50 penulis berarti 20/10/10/10 penulis; pertahankan distribusi strata bila memungkinkan. Bila tidak melakukan fine-tuning, train dipakai untuk prototipe, bukan menambah test secara oportunistis.

Halaman dari satu mahasiswa, duplicate scan, potongan/augmentasi, dan jawaban yang disalin dari sumber sama harus masuk split yang sama. Hash exact + pemeriksaan near-duplicate pada gambar mencegah kebocoran. Bekukan daftar ID dan hash manifest. Untuk klaim lintas soal/mata kuliah, buat test terpisah dengan soal/rubrik yang tidak dipakai saat tuning, bukan hanya penulis baru pada soal yang sama.

Threshold quality/review dipilih di calibration set. Prompt/preprocess/hyperparameter dipilih di development set. Locked test tidak dipakai memperbaiki prompt; kegagalan dilaporkan lalu evaluasi berikutnya memakai test versi baru bila diperlukan.

## Metrik per lapisan

| Lapisan | Metrik | Definisi penting |
| --- | --- | --- |
| Intake | Halaman hilang, salah identity, file gagal terisolasi | Laporkan count absolut; salah identity kritis |
| Layout | Region precision/recall/IoU dan mapping accuracy | Ukur jawaban lintas halaman serta area unassigned |
| HTR | CER dan WER micro + median per jawaban | Edit distance / panjang gold; gold kosong ditangani terpisah |
| Makna OCR | Error angka/negasi/satuan kritis | CER rendah dapat tetap membalik jawaban |
| Grader oracle | MAE rasio skor, agreement kriteria, quadratic weighted kappa bila cocok | Pakai transkripsi manusia untuk mengisolasi evaluator |
| End-to-end | MAE final pada skala 0–100, p95 absolute error, signed bias | Sebelum koreksi manusia, dibanding gold |
| Abstention | Proposal coverage dan error pada subset berproposal | Keduanya dilaporkan bersama; null tidak dianggap prediksi benar |
| Review | Mandatory approval rate, substantive intervention rate, review minutes | Pengesahan MVP selalu 100%; intervensi mengukur edit bermakna |
| Operasional | p50/p95 latensi, peak RAM/VRAM, failure/retry rate | Cantumkan perangkat, batch, resolusi, token limit |
| Produk | Waktu koreksi manual vs ASDOS | Gunakan crossover/randomisasi tugas untuk menekan efek hafalan |

Laporkan CER literal dan versi normalisasi ringan secara terpisah. Jangan menghapus angka, tanda negasi, simbol, atau error bermakna saat normalisasi. Skor baseline/manual dan model harus menggunakan rubrik/split yang sama. Kappa tidak memadai bila distribusi kelas degenerat; tampilkan confusion matrix dan agreement mentah.

## Gate usulan MVP

| Gate | Sasaran awal | Bila gagal |
| --- | --- | --- |
| Integritas | 0 salah identity, 0 halaman hilang tanpa flag pada benchmark | Blok rilis pemrosesan otomatis; perbaiki intake/mapping |
| Mapping | ≥95% jawaban dipetakan benar sebelum koreksi, strata dilaporkan | Wajib mapping manual untuk pola yang gagal |
| HTR | CER micro ≤15% pada subset terbaca; error kritis dilaporkan | Jangan lolos hanya dari CER; utamakan intervensi dan error nilai |
| Semantik oracle | MAE rasio skor ≤0.10 | Perbaiki rubrik/evaluator sebelum mengoptimalkan OCR |
| Nilai usulan end-to-end | MAE ≤5/100, p95 absolute error ≤10 pada subset berproposal | Turunkan cakupan atau batasi tipe soal; jangan klaim autonomous |
| Coverage | ≥70% jawaban mendapat proposal tervalidasi | Hindari “akurasi tinggi” dari model yang abstain hampir semua |
| Review substantif | Target ≤40% jawaban perlu edit mapping/teks/nilai | Evaluasi kembali manfaat produk; approval tetap wajib |
| Kalkulasi/ekspor | 100% cocok pada fixture deterministik dan seluruh pilot export | Blok rilis |
| Waktu dosen | Target pengurangan median ≥30% pada pilot berpasangan | Jangan mengklaim hemat waktu bila belum terbukti |

Gate end-to-end dilaporkan bersama coverage, jumlah abstention, dan kesalahan pada strata. Jawaban abstain tidak diisi skor 0 untuk membuat MAE tampak baik. Untuk metrik total ujian sebelum review, laporkan hanya submission yang lengkap beserta coverage submission; tambahkan evaluasi all-submission setelah review sebagai metrik produk terpisah.

Gunakan confidence interval dengan bootstrap berkelompok pada penulis/submission, bukan menganggap semua crop independen. Untuk strata kecil, tampilkan count dan ketidakpastian; jangan menyimpulkan kesetaraan kinerja dari beberapa contoh. Target rilis tidak otomatis terpenuhi hanya karena point estimate lolos jika hasil tidak stabil atau ada kegagalan kritis.

## Matriks eksperimen minimum

E1: PP-OCRv5 tanpa/berikut deskew. E2: line suppression on/off pada folio serta HVS untuk mendeteksi kerusakan teks. E3: VLM transkripsi per crop vs per halaman dengan batas image token tercatat. E4: evaluator pada gold text vs OCR text. E5: rubrik tanpa/dengan anchors parsial. E6: quantization kandidat vs precision acuan pada split yang sama. E7: end-to-end dengan human review dan pengukuran waktu.

Jangan menggabungkan banyak perubahan dalam satu eksperimen karena sulit mengetahui penyebab peningkatan. Seed ditetapkan bila didukung; gunakan deterministic decoding untuk baseline dan beberapa pengulangan bila nondeterminisme masih bermakna. Simpan keluaran nyata, bukan sekadar rerun script.

## Laporan model

Laporan mencantumkan tanggal, git commit, dependency lock, checkpoint/revision/license, perangkat, konfigurasi preprocessing/inferensi, split/hash, jumlah data/penulis, metrik seluruh strata, interval, coverage, contoh gagal yang telah dianonimkan, biaya dan keputusan. Catat bila eksperimen tidak selesai/OOM. Model card rilis harus menyatakan batas bahasa, tipe jawaban, dan kebutuhan pengesahan dosen.

## Jalur pengembangan model setelah baseline

Latih/adaptasi model hanya setelah analisis menunjukkan sumber error yang konsisten dan perbaikan preprocessing/rubrik belum cukup. Dataset feasibility bukan otomatis dataset training yang memadai. Tambah anotasi sesuai learning curve dan keragaman penulis; jangan membuat klaim kebutuhan data yang pasti dari jumlah parameter saja.

Jika error dominan karakter/baris, eksperimen adaptasi HTR dengan pasangan crop–transkripsi literal. Jika VLM sering menghilangkan bagian/menulis ulang makna, bandingkan prompt/crop dan model khusus sebelum LoRA/fine-tuning. Jika evaluator gagal pada gold text, perbaiki anchors dan kumpulkan contoh penilaian dosen/adjudikasi; tuning OCR tidak menyelesaikan error penilaian tersebut.

Protokol training opsional: verifikasi izin turunan/training → bekukan train/dev/calibration/test writer-disjoint → buat config optimizer/learning-rate/batch/epoch/seed dan batas GPU-hour → simpan checkpoint berkala → early stopping pada dev → pilih threshold pada calibration → evaluasi locked test → terbitkan laporan/model card serta hak bobot turunan → aktifkan hanya untuk run baru dengan rollback ke versi lama. Simpan augmentasi hanya pada train dan jangan membuat versi “gold” dari label AI yang belum ditinjau.

Bobot transcriber dan evaluator sebaiknya dievaluasi terpisah; jangan memasukkan kunci ke training input transkripsi sehingga model belajar membetulkan jawaban mahasiswa. Quantization/LoRA tidak boleh dianggap mempertahankan akurasi tanpa ablation pada split yang sama. Tahap ini di luar estimasi MVP dan memerlukan issue/anggaran tersendiri.
