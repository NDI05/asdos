# 17 — Sumber Primer dan Batas Riset

Sumber berikut diperiksa pada **3 November 2026** untuk menyusun rancangan. Konten repository/dokumentasi dapat berubah; implementasi harus mengunci commit, checkpoint, versi dan lisensi yang benar-benar digunakan. Semua estimasi, threshold, arsitektur ASDOS dan keputusan scope adalah usulan engineering paket ini, bukan hasil eksperimen yang diklaim berasal dari sumber.

| ID | Sumber primer | Dipakai untuk | Batas interpretasi |
| --- | --- | --- | --- |
| S01 | [Qwen3-VL repository resmi](https://github.com/QwenLM/Qwen3-VL) | Kemampuan OCR/document parsing dan integrasi runtime sebagai kandidat | Klaim produsen tidak membuktikan akurasi jawaban mahasiswa Indonesia |
| S02 | [Qwen3-VL-4B-Instruct model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) | ID checkpoint kandidat dan label lisensi Apache-2.0 | VRAM, precision dan kualitas wajib diukur sendiri |
| S03 | [PaddleOCR — PP-OCRv5 multilingual](https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html) | Dukungan Latin termasuk Indonesia; baseline OCR | Tidak menyamakan daftar bahasa dengan akurasi handwriting lokal |
| S04 | [TrOCR handwritten model card](https://huggingface.co/microsoft/trocr-base-handwritten) | Baseline single-line, IAM, label MIT | Model card menyebut ditulis tim Hugging Face; bukan bukti PDF multi-layout/Indonesia |
| S05 | [pypdfium2 introduction/licensing](https://pypdfium2.readthedocs.io/en/stable/readme.html) | Renderer, lisensi, dependency notices, keterbatasan threading | PDFium tidak thread-safe; isolasi proses dan build actual harus diperiksa |
| S06 | [FastAPI — Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) | Pemisahan request ringan dari komputasi berat lewat worker | Pemilihan Celery tetap keputusan arsitektur ASDOS |
| S07 | [Python decimal](https://docs.python.org/3/library/decimal.html) dan [PostgreSQL numeric](https://www.postgresql.org/docs/current/datatype-numeric.html) | Aritmetika desimal dan penyimpanan exact numeric | Presisi/context/pembulatan ASDOS ditetapkan di kebijakan proyek |
| S08 | [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | Validasi berlapis, storage dan resource limits | Kontrol perlu diuji; bukan sertifikasi keamanan |
| S09 | [XlsxWriter Worksheet](https://xlsxwriter.readthedocs.io/worksheet.html) | write_string, konversi formula/URL, batas sel, numeric Excel | Writer tidak otomatis membuat semua input aman tanpa tipe eksplisit |
| S10 | [PDF.js repository resmi](https://github.com/mozilla/pdf.js) | Viewer PDF browser dan referensi integrasi | Overlay transform dan UX review tetap implementasi proyek |
| S11 | [OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) | Trust boundary, isolasi kemampuan, validasi output | Prompt tidak memberi jaminan kebal injection |
| S12 | [Apache License 2.0 resmi](https://www.apache.org/licenses/LICENSE-2.0) | Dasar usulan lisensi kode | Tidak otomatis diterapkan tanpa keputusan pemegang hak dan notices |
| S13 | [Celery — Using Redis](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html) | Transport broker, visibility timeout dan caveat redelivery | Lease/idempotency DB tetap dibutuhkan untuk efek samping |
| S14 | [Redis — Licenses](https://redis.io/legal/licenses/) | Review lisensi sesuai versi broker yang dipilih | Jangan menganggap semua versi Redis memakai lisensi sama |
| S15 | [PaddleOCR repository resmi](https://github.com/PaddlePaddle/PaddleOCR) | Provenance toolkit dan pemeriksaan dependency/version | Versi terbaru tidak otomatis menjadi versi benchmark ASDOS |

## Temuan yang memengaruhi rancangan

TrOCR raw handwritten ditujukan untuk gambar satu baris, sehingga tidak dipasang langsung untuk seluruh PDF. PP-OCRv5 menyediakan jalur Latin/Indonesia, namun perlu pengujian tulisan tangan domain lokal. Qwen3-VL menyediakan kemampuan visual/text yang layak diuji sebagai kandidat, bukan jawaban final atas pemilihan model. pypdfium2/PDFium perlu pengelolaan resource dan proses dengan hati-hati; jangan melakukan parallel rendering memakai thread pada PDFium tanpa isolasi yang didukung.

XlsxWriter dapat menginterpretasi string tertentu sebagai formula/tautan melalui generic write, sehingga ekspor memakai tipe eksplisit. Python Decimal dan PostgreSQL NUMERIC mendukung kebijakan angka yang dapat diuji. Celery/Redis dapat mengirim ulang task, sehingga idempotency dan snapshot DB tidak boleh dihilangkan.

## Yang belum diverifikasi

Akurasi ASDOS, kemampuan inferensi pada perangkat pengguna, biaya listrik/cloud aktual, versi dependency yang saling kompatibel, dataset kampus, kebijakan akademik/retensi, izin publikasi data, lisensi final proyek, dan kontak maintainer. Tidak ada benchmark produsen yang dipakai sebagai pengganti verifikasi tersebut.
