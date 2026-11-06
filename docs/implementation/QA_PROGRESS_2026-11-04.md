# Indikator upload, pemetaan dan OCR

Tanggal: 4 November 2026.

Masalah: banner job kecil tidak memperlihatkan tahapan dengan jelas, status hilang ketika lembar dibuka kembali, dan pengguna sulit membedakan proses yang masih berjalan dari pemetaan yang memerlukan tindakan dosen.

Perubahan: panel progres empat tahap, spinner pada proses aktif dan tombol OCR/upload, status per nomor, counter aktual, serta error/retry/cancel. GET submission menyertakan job terbaru per jenis/jawaban untuk dokumen aktif. Polling memulihkan hasil tanpa mengganti objek jawaban yang tidak berubah; state form juga mengikuti revisi sumbernya sendiri agar pembaruan job tidak menghapus draf pengguna. Pemetaan tetap manual, identitas tetap perlu konfirmasi, dan tidak ada perubahan penilaian/model/prompt.

## Verifikasi

- Backend: 50 tes lulus. Regression API membuktikan job terbaru/retry dipilih, job dokumen lama tidak tercampur, serta status/counter tersedia saat membuka detail submission.
- Frontend: 13 tes lulus, termasuk upload sebelum respons HTTP, render indeterminate, pemetaan manual tanpa spinner, OCR queued/running per jawaban, unreadable, failed/cancelled, counter terukur, koneksi status gagal, dan pelestarian objek jawaban pada polling.
- TypeScript/Vite production build lulus.
- Browser memakai API/SQLite privat pada port 8015, broker Redis database 5, worker solo terpisah, akun dan PDF sintetis. Tidak memakai atau mengubah data mahasiswa pada workspace pengguna.
- Diamati di browser: queued render → preview siap secara otomatis; setelah reload dan membuka ulang lembar, antrean OCR per nomor tetap muncul; setelah worker dijalankan, indikator berubah menjadi sedang membaca → transkripsi tersedia, spinner berhenti dan teks muncul otomatis. OCR pada langkah ini memakai Qwen nyata atas teks sintetis; bukan pengukuran akurasi tulisan tangan.
- Inspeksi visual panel pada browser dilakukan. Indikator dekat tombol tetap terlihat saat panel utama berada di atas viewport. Lembar yang dibuka menggulir ke panel progres.

Tidak ada persentase/waktu tersisa yang dikarang. Worker saat ini belum melaporkan progres token OCR; karena itu OCR dapat tampil indeterminate sepanjang inferensi. Pemetaan otomatis tidak ditambahkan dan tidak dinyatakan sedang berjalan.
