# Petunjuk finalisasi — 4 November 2026

Finalisasi tetap menolak area yang belum dipetakan/dikecualikan dan keputusan per soal yang belum selesai. Sebelumnya error mencantumkan UUID region dan `missing_answer` untuk soal yang sebenarnya sudah memiliki blocker lebih spesifik seperti `needs_review`; ini membuat keadaan sulit dipahami. API kini menghilangkan `missing_answer` yang redundan jika soal tersebut sudah memiliki blocker spesifik, tanpa melonggarkan validasi atau rumus nilai.

Frontend menampilkan daftar area yang perlu ditinjau dan tombol menuju keputusan tiap nomor yang belum siap. Klik area membuka daftar area; reviewer dapat memetakan area atau mengecualikannya dengan alasan, termasuk bila area merupakan duplikat. Pengecualian tetap dapat dibatalkan dan tidak menghapus region. Indikator nomor tidak lagi menandai status `needs_review` sebagai selesai. Jawaban dan keputusan pengguna tidak diubah otomatis.

Uji integrasi sintetis memverifikasi bahwa soal `needs_review` tidak lagi dilaporkan ganda sebagai `missing_answer`, area yang belum ditangani tetap memblokir pengesahan, dan setelah keputusan serta pengecualian manusia yang valid disimpan, finalisasi berhasil. Uji frontend memverifikasi petunjuk per nomor, jumlah area, dan pesan tanpa UUID.

Verifikasi browser read-only pada lembar yang dilaporkan menunjukkan empat area belum terpetakan dan tombol menuju soal 1, 2 dan 3 yang masih perlu keputusan; navigasi ke soal dan pembukaan daftar area diperiksa tanpa menyimpan penilaian, mengecualikan area, atau mengesahkan nilai. Pilihan tujuan area kini dimulai kosong sehingga dosen harus memilih nomor secara eksplisit. 72 tes backend, 21 tes frontend, dan build frontend lulus.
