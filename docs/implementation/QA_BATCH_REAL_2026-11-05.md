# Uji batch dengan model nyata — 5 November 2026

Website utama dinyalakan dengan database workspace yang sebelumnya digunakan. Uji inferensi memakai database, penyimpanan, antrean Redis dan worker terpisah; dua PDF sintetis masing-masing berisi satu identitas sintetis dan satu jawaban cetak tentang RAM. Rubrik disetujui untuk fixture sintetis. Tidak ada data atau nilai mahasiswa sebenarnya yang diubah.

Kedua PDF dikirim melalui API yang sama dengan alur batch. Render selesai untuk dua dokumen. Model Qwen lokal membaca nama dan NIM sesuai nilai sintetis pada kedua dokumen sebagai usulan; identitas tetap memerlukan konfirmasi. **Locator mengembalikan `no_answer_regions` pada kedua halaman padahal ada jawaban.** Jadi pemetaan otomatis gagal pada uji ini dan alur sepenuhnya otomatis belum lulus.

Area yang diketahui dari fixture ditambahkan dan dipetakan manual untuk masing-masing dokumen, kemudian OCR model nyata berhasil membaca kedua kalimat jawaban. Setelah identitas dikonfirmasi dan pemetaan manual disimpan, job `grade_answer` otomatis berhasil pada kedua dokumen dan menghasilkan usulan per kriteria; tidak ada snapshot nilai final. Browser memperlihatkan transkripsi, bukti dan usulan untuk satu dokumen. Pemeriksaan hanya memakai dua PDF cetak sintetis, bukan tulisan tangan, bukan benchmark akurasi, dan bukan uji throughput 50 berkas.

Uji menemukan pesan UI yang masih menyatakan area belum ada setelah pemetaan manual; pesan diperbaiki agar hanya muncul saat halaman benar-benar belum memiliki region. Label progres pemetaan dibuat netral agar tidak menyebut pemetaan manual sebagai otomatis. Model aktif tidak diganti untuk menutupi kegagalan locator. Worker dan server uji terpisah dihentikan; website utama tetap berjalan.
