---
name: asdos-verify
description: Verifikasi acceptance ASDOS dan kesiapan rilis berdasarkan bukti. Gunakan untuk review diff, regression, audit kontrak OCR dan grading, finalisasi nilai, keamanan PDF/Excel, benchmark, serta pemeriksaan dokumentasi proyek.
---

# Verifikasi ASDOS

Baca [AGENTS](../../AGENTS.md), acceptance issue/milestone, dan [testing](../../docs/15-testing-and-release.md). Untuk gate model baca [evaluasi](../../docs/09-evaluation-and-dataset.md); untuk angka baca [penilaian](../../docs/05-grading-and-scoring.md).

## Prosedur

1. Tentukan yang benar-benar tersedia: rencana, source, fixture, model runtime, atau hasil eksperimen. Dokumen bukan bukti fitur sudah bekerja.
2. Turunkan acceptance menjadi pemeriksaan teramati. Periksa producer/consumer contract, versi, null, provenance dan hak akses.
3. Jalankan pemeriksaan relevan yang tersedia. Untuk dokumentasi, periksa link relatif, JSON, rumus, state dan scope. Jangan mengklaim pengujian aplikasi jika aplikasi belum ada.
4. Untuk scoring/export, hitung oracle independen dan periksa tipe sel. Untuk CV, periksa mapping/transform dan benchmark per strata; screenshot tidak cukup.
5. Periksa failure path yang relevan: input invalid, timeout, retry/duplicate, stale result, concurrent edit, final revision dan akses silang. Jangan menjalankan load test mahal tanpa kebutuhan.
6. Bedakan pass, fail dan blocked/not_run. Skipped test/data tidak ada bukan pass. Bedakan target dari accuracy aktual.
7. Laporkan temuan dengan lokasi, dampak, bukti dan saran. Pada review-only, jangan mengubah source.

## Stop condition

Berhenti setelah acceptance diperiksa dan statusnya jelas. Jangan menambah fitur atau mengganti model untuk menyembunyikan temuan. Salah mahasiswa, null menjadi 0, perubahan final diam-diam, kebocoran, atau angka workbook tidak cocok memblokir gate terkait.

Format hasil: ringkasan status, temuan prioritas, bukti, dan batas pemeriksaan. Jika tidak ada temuan, sebutkan apa yang diverifikasi dan belum diuji; jangan memberi jaminan umum tanpa batas.
