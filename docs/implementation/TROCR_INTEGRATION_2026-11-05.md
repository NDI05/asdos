# Integrasi TrOCR lokal — 5 November 2026

## Perilaku

ASDOS kini dapat memakai checkpoint fine-tuned lokal sebagai transcriber pada pekerjaan **Baca tulisan** dan tahap transkripsi di **Baca dan petakan jawaban otomatis**. Pemilihan dilakukan lewat `ASDOS_TRANSCRIBER=trocr`; nilai `qwen` mempertahankan jalur transcriber sebelumnya. Konfigurasi lokal workspace ini mengarah ke `data/private/trocr-all-2348-v1/model-final` melalui `.env`, yang tidak masuk Git. `.env.example` tetap memilih Qwen.

TrOCR hanya menangani transkripsi. Qwen tetap diperlukan untuk lokalisasi area, usulan identitas, pembuatan acuan, dan usulan penilaian. `make start` tetap memeriksa checkpoint Qwen karena beberapa alur ASDOS memerlukannya.

TrOCR menerima crop area jawaban, memisahkan baris secara lokal dengan profil proyeksi horizontal, lalu mengenali setiap baris dan menyatukan teks dengan jeda baris. Piksel gambar asal tetap digunakan; profil proyeksi hanya menentukan kotak crop. Jika segmentasi tidak pasti, adapter memakai crop asli dan menambahkan flag `line_segmentation_fallback`. Versi preprocessing tercatat sebagai `region-line-segmentation.v1`.

## Review wajib

Setiap keluaran membawa flag `experimental_transcriber_review_required`. Status ini tetap dibedakan dari tulisan yang kosong atau tidak terbaca. ASDOS menampilkan peringatan, menonaktifkan **Minta usulan**, dan tidak menjadwalkan penilaian otomatis sampai dosen membandingkan scan, mengoreksi teks, lalu memilih **Simpan transkripsi**. Penyimpanan manual membuat revisi berlabel human dan membersihkan flag model.

Setiap `ModelRun` menyimpan ID/revision model, hash bobot, runtime, prompt/schema, preprocessing, perangkat, dan fingerprint input. Loader hanya membaca direktori lokal, memverifikasi hash dari `asdos-trocr-manifest.json`, menonaktifkan akses Hugging Face jaringan, dan menolak checkpoint dengan provenance atau hash yang tidak cocok. Checkpoint privat tidak disalin ke repository.

Status `/api/v1/health/model` mempertahankan status Qwen pada field utama dan menambahkan rincian adapter terpilih pada `transcriber`. Field `available` pada akar tetap berarti Qwen siap, karena Qwen masih dipakai oleh fungsi lain.

## Konfigurasi

Pada `.env` lokal:

```dotenv
ASDOS_TRANSCRIBER=trocr
ASDOS_TROCR_DIR=./data/private/trocr-all-2348-v1/model-final
```

Runtime tersedia lewat extra `model` yang sudah dipakai `make start`. Untuk checkpoint salinan, simpan laporan training bersama artefaknya dan buat manifest lokal:

```bash
uv run --locked --extra model python -m scripts.register_trained_trocr \
  --checkpoint /path/private/model-final \
  --training-report /path/private/run/report.json
```

Manifest lokal mengikat hash bobot dan provenance dataset untuk mencegah checkpoint yang berubah dipakai tanpa terdeteksi. Nilainya tidak dipublikasikan karena mengidentifikasi artefak turunan dari dataset privat.

## Batas bukti

Training eksperimen menggunakan pseudo-label AI tanpa split held-out yang tervalidasi manusia. CER/WER yang diukur hanya menunjukkan fit terhadap label tersebut, bukan akurasi manusia atau generalisasi. Tidak ada klaim bahwa segmentasi baris baru atau inferensi end-to-end ASDOS telah meningkatkan akurasi. Transcriber ini aktif untuk eksperimen review lokal, bukan default model rilis. Bobot, manifest, dan laporan rinci tetap lokal karena berasal dari dataset privat.

Pembaruan ini belum menjalankan suite test. Tes dan benchmark tulisan tangan manusia lintas penulis tetap menjadi gate sebelum promosi model.
