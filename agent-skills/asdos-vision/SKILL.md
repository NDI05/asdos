---
name: asdos-vision
description: Kembangkan dan evaluasi pipeline PDF scan serta handwriting recognition ASDOS. Gunakan untuk folio bergaris, HVS, rendering, rotasi, transform koordinat, segmentasi nomor, transkripsi OCR/VLM, dan benchmark pengenalan tulisan.
---

# Kerjakan Computer Vision ASDOS

Baca [AGENTS](../../AGENTS.md), [spesifikasi CV](../../docs/04-vision-and-handwriting.md), [evaluasi](../../docs/09-evaluation-and-dataset.md), dan [state](../../docs/06-data-model-and-state.md). Gunakan detail dari dokumen tersebut, jangan menduplikasi seluruh spec dalam prompt.

## Prosedur

1. Tetapkan lapisan: render, quality, transform, layout/mapping, atau transkripsi. Pisahkan error baca dari error grading.
2. Verifikasi izin data, manifest/hash dan split berbasis penulis. Jika hanya ada PDF sintetik, nyatakan handwriting manusia belum diuji.
3. Pertahankan asli dan provenance semua turunan. Simpan page dimensions, origin, polygon, transform/invers dan urutan region. Isolasi proses PDFium; jangan mengasumsikan thread-safe.
4. Mulai baseline yang ada. Ubah satu faktor per eksperimen, misalnya deskew/line suppression. Bandingkan folio/HVS dan error angka/negasi, bukan hanya gambar tampak bersih.
5. Pisahkan identitas/header. Petakan question ID eksplisit, pertahankan unassigned dan lanjutan lintas halaman. Jangan menebak mahasiswa atau nomor ambigu.
6. Transkripsikan literal tanpa soal/kunci/rubrik sebagai konteks OCR. Jangan melengkapi kata/angka yang tidak terlihat. Simpan flags dan confidence null bila tidak tersedia.
7. Validasi schema, refs, resource limit dan lineage sebelum mempromosikan hasil. Input berubah membuat hasil lama stale.
8. Laporkan CER/WER, mapping, coverage, critical errors, strata, perangkat, latensi dan memori. Ikuti calibration/locked-test policy; jangan tuning test.

## Keputusan dan batas

Jangan menetapkan pemenang dari deskripsi produsen atau satu contoh. Catat OOM sebagai gagal kapasitas. Line removal dapat menghapus simbol/huruf; aktifkan hanya setelah ablation. Tidak terbaca memerlukan review, bukan skor 0.

Untuk rencana/review, berikan desain eksperimen dan acceptance; jangan mengklaim metrik aktual. Untuk source, sertakan regression fixture koordinat/mapping dan benchmark yang benar-benar dijalankan. Jika data/perangkat tidak tersedia, gate model blocked; tes transform sintetik tetap dapat dilakukan.
