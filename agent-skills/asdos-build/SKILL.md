---
name: asdos-build
description: Implementasikan fitur ASDOS dari issue sampai verifikasi. Gunakan untuk API, UI review, upload PDF, job worker, storage, autentikasi, dan integrasi ekspor pada proyek koreksi jawaban tulisan tangan ini.
---

# Kerjakan Fitur ASDOS

Baca [AGENTS](../../AGENTS.md), [arsitektur](../../docs/03-system-architecture.md), dan acceptance issue dari [roadmap](../../docs/11-implementation-roadmap.md). Pastikan source/manifest yang tersedia; repository mungkin baru berisi rencana. Jangan mengklaim perintah setup atau hasil tes yang belum ada.

## Alur kerja

1. Nyatakan trigger/perilaku yang harus berubah, batas scope, dan bukti selesai. Cari komponen/kontrak yang bertanggung jawab.
2. Baca [data/state](../../docs/06-data-model-and-state.md) dan [API](../../docs/07-api-contracts.md) saat mengubah kontrak. Pertahankan versioning, ownership dan optimistic concurrency.
3. Bangun satu irisan utuh dengan dependensi minimum. Untuk awal proyek, utamakan jalur manual sampai Excel sebelum model lengkap.
4. Letakkan komputasi berat pada worker. Terapkan DB canonical status, fingerprint/idempotency, lease dan recovery untuk job yang berpengaruh pada nilai.
5. Gunakan adapter sempit untuk model/file/render/export. Jangan menambah provider, microservice, RAG, Kubernetes atau fine-tuning tanpa kebutuhan acceptance.
6. Uji jalur normal dan kegagalan relevan dengan fixture sintetik/berizin. Jalankan lint/type/test yang sudah dikonfigurasi; catat bila tes belum dapat dijalankan.
7. Perbarui docs yang berubah. Laporkan hasil nyata, bukti, dan blocker.

## Pengaman domain

Jangan mengubah nilai final in-place, mengubah null menjadi 0, mengekspos artefak tanpa otorisasi, atau mengirim scan eksternal sebagai fallback. Untuk angka/rubrik gunakan [penilaian](../../docs/05-grading-and-scoring.md) dan panduan asdos-grading. Untuk koordinat/OCR gunakan panduan asdos-vision.

Jika tugas hanya meminta rencana/review, hasilkan rencana/temuan tanpa mengimplementasikan aplikasi. Jangan membuat data atau hasil benchmark seolah sudah diukur.

## Bukti selesai

Acceptance teruji, recovery aman, data sensitif tidak masuk Git/log, kontrak terdokumentasi, dan tidak ada klaim fitur di luar implementasi. Gunakan [testing](../../docs/15-testing-and-release.md) untuk memilih pengujian relevan, lalu berhenti ketika scope selesai.
