# 05 — Rubrik, Koreksi, dan Pembobotan

## Input pengguna yang disederhanakan

Keputusan terbaru: pengguna cukup memasukkan soal dan bobot. Model pralatih menyusun jawaban acuan, alternatif dan kriteria sebagai draft; pengguna tidak diwajibkan mengetik kunci per nomor. Acuan disusun tanpa akses jawaban mahasiswa, divalidasi di server, dan ditampilkan untuk ditinjau/disahkan. Draft yang belum sah tidak dipakai menilai. Penilaian serta finalisasi tidak berubah menjadi otonom.

## Standar penilaian

Soal menetapkan apa yang ditanyakan; rubrik menetapkan apa yang diberi kredit. Keduanya perlu versi dan persetujuan dosen. AI boleh mengusulkan kunci/kriteria dari soal, tetapi usulan harus berstatus draft sampai diverifikasi. Bila soal ambigu atau kunci bertentangan, hentikan penilaian nomor tersebut dan minta penyelesaian rubrik.

Rubrik per nomor berisi question ID, pertanyaan dan lampiran, jawaban acuan, alternatif jawaban yang sah, kriteria, kredit parsial, maksimum skor mentah, bobot, aturan kosong/coretan, tipe jawaban, dan bahasa. Untuk narasi, persamaan kata bukan satu-satunya dasar; cocokkan konsep dan bukti. Tata bahasa/tulisan rapi tidak mengurangi nilai kecuali menjadi kriteria yang dinyatakan.

## Kontrak kriteria

Setiap kriteria punya ID, deskripsi yang terukur, maksimum poin mentah `m_ij`, level kredit yang diizinkan beserta anchor, bukti yang diharapkan, dan aturan kontradiksi. Jumlah maksimum kriteria harus sama dengan `R_i`. Gunakan level diskret berjangkar bila memungkinkan; misalnya 0 = tidak ada/salah, 0.5 = sebagian, 1 = lengkap. Kredit parsial bukan angka bebas yang dipilih model tanpa definisi.

Untuk setiap kriteria, evaluator mengusulkan `credit` pada level sah, evidence refs, label `met/partial/not_met/insufficient_evidence`, serta alasan singkat yang menghubungkan bukti dengan rubrik. Kode memetakan credit ke poin `p_ij = credit × m_ij`. Bukti yang dirujuk harus ada pada revisi transkripsi/region yang dinilai. Tidak adanya konsep dapat dijelaskan sebagai konsep yang belum ditemukan; jangan mengarang kutipan untuk membuktikan ketidakadaan.

## Rumus tunggal

Untuk pertanyaan `i`, definisikan:

- `r_i = Σ_j p_ij`: skor mentah yang diperoleh.
- `R_i = Σ_j m_ij > 0`: skor mentah maksimum.
- `w_i > 0`: bobot/poin nomor yang dimasukkan dosen.
- `W = Σ_i w_i > 0`: total bobot seluruh nomor yang wajib dinilai.
- `S_max = 100`: skala nilai akhir MVP.

Kontribusi nomor adalah `c_i = (r_i / R_i) × w_i`. Nilai akhir adalah `S = S_max × Σ_i c_i / W`.

Bobot tidak wajib berjumlah 100. Bila bobot 20/30/50, kontribusi langsung berjumlah pada skala 100. Bila bobot 2/3/5, nilai akhir tetap sama setelah normalisasi. `R_i` adalah skala rubrik internal, sedangkan `w_i` adalah pengaruh nomor terhadap ujian; jangan mengalikan bobot lagi saat ekspor.

| Nomor | r_i | R_i | w_i | c_i |
| --- | --- | --- | --- | --- |
| 1 | 8 | 10 | 20 | 16 |
| 2 | 6 | 10 | 30 | 18 |
| 3 | 9 | 10 | 50 | 45 |
| Total | — | — | 100 | 79 |

Nilai akhir `100 × 79/100 = 79.00`. Lihat [contoh lengkap](18-example-assessment.md).

## Angka, pembulatan, dan validasi

Gunakan `Decimal` dari string di Python, NUMERIC di PostgreSQL, dan string desimal pada JSON. Tolak NaN/Infinity, nilai negatif, `R_i = 0`, bobot nol, criterion ID tidak dikenal, kredit di luar level, duplikasi hasil kriteria, atau jumlah kriteria tidak cocok. Model yang menghasilkan angka di luar batas harus dianggap output invalid; jangan clamp lalu menyatakan sukses.

Simpan pecahan rasional atau Decimal dengan presisi perhitungan memadai, misalnya context precision 28. Jangan membulatkan `c_i` sebelum agregasi. Bulatkan **nilai akhir** dua desimal dengan `ROUND_HALF_UP`. Tampilan kontribusi per nomor dapat dua desimal, tetapi Excel memakai nilai numerik dengan presisi tersimpan; tampilkan catatan bahwa penjumlahan angka yang terlihat dapat berbeda 0.01 dari agregasi presisi penuh. Simpan `scoring_policy_version` agar perhitungan dapat direproduksi.

MVP tidak memakai nilai minus, bonus, drop-lowest, pengurangan karena terlambat, atau konversi A/B/C. Jika diperlukan, tambahkan kebijakan terpisah yang terversi dan diuji; jangan menyelipkannya ke prompt model.

## Status yang tidak boleh dicampur

| Status jawaban | Skor usulan | Dapat final? |
| --- | --- | --- |
| correct | r_i = R_i | Setelah diterima dosen |
| partially_correct | 0 < r_i < R_i | Setelah diterima dosen |
| incorrect | r_i = 0 dengan bukti evaluasi lengkap | Setelah diterima dosen |
| verified_blank | 0 setelah reviewer memastikan benar-benar kosong | Ya, dengan aksi verifikasi |
| needs_review | null atau usulan berpenghalang | Tidak |
| unreadable | null | Tidak, sampai dosen menyelesaikan keputusan |
| unsupported | null | Tidak, perlu koreksi manual |
| missing_mapping/model_failed | null | Tidak |

Nilai parsial sementara boleh ditampilkan sebagai “kontribusi yang sudah dinilai”, bukan nilai akhir; penyebut ujian tetap W. Jangan menormalisasi hanya terhadap soal yang terbaca karena menghasilkan nilai terinflasi. Mahasiswa tidak hadir dicatat sebagai status submission, bukan disamakan dengan PDF kosong.

Jika sumber asli memang tidak terbaca, dosen dapat memasukkan nilai manual sesuai kebijakan institusi, dengan alasan dan bukti/rujukan keputusan. Sistem tidak menetapkan kebijakan akademik untuk kasus tersebut.

## Strategi evaluator

Input: satu nomor, versi soal/rubrik yang disetujui, transkripsi aktif, refs visual/flags yang relevan, dan schema output. Hilangkan nama, NIM, kelas, nilai mahasiswa lain, dan skor total dari konteks model. Jangan mengirim jawaban seluruh kelas dalam satu prompt.

Urutan: validasi input → cek blocking flags → cocokkan konsep per kriteria → keluaran terstruktur → validasi schema dan bukti → kalkulasi deterministik → simpan usulan. Alasan cukup singkat dan dapat diperiksa; jangan meminta atau menyimpan chain-of-thought privat. Kesetaraan sinonim/urutan kalimat diterima selama makna memenuhi rubrik. Jawaban panjang, gaya bahasa akademik, dan menyalin kata soal tidak otomatis mendapat nilai.

Untuk jawaban numerik sederhana di tahap lanjutan, validator deterministik memeriksa toleransi absolut/relatif dan satuan sesuai rubrik. Jangan menjalankan `eval`/kode mahasiswa. Kesetaraan aljabar/diagram kompleks belum termasuk MVP. Similarity embedding/cosine boleh menjadi sinyal retrieval/analisis eksperimen, bukan satu-satunya penentu benar/salah.

## Review, revisi, dan pengesahan

Simpan hasil model sebagai proposal immutable. Reviewer menerima/mengubah skor per kriteria; override nilai nomor secara langsung diperbolehkan bila alasan dicatat dan tetap dalam `[0,R_i]`. Jika override tidak dapat dipecah ke kriteria, tandai `manual_question_override`, tampilkan terpisah, dan gunakan r_i override sekali saja.

Finalisasi memerlukan identitas terkonfirmasi, semua nomor terselesaikan, versi input konsisten, tanpa job relevan yang masih mengubah hasil aktif, dan aktor yang berwenang. Buat snapshot seluruh nomor dan total dalam satu transaksi. Perubahan rubrik/transkripsi/mapping setelah final membuat revisi baru dengan status draft; final lama tetap dapat diaudit dan hanya digantikan melalui pengesahan revisi baru.

## Uji wajib

Bobot 20/30/50 dan 2/3/5 memberi 79.00 pada contoh. Bobot semua sama setara rata-rata rasio. Skor penuh menghasilkan 100.00; semua salah/kosong terverifikasi menghasilkan 0.00. Null memblokir finalisasi. Monotonisitas berlaku: menaikkan kredit satu kriteria tidak menurunkan nilai. Urutan soal tidak mengubah total. Mengubah tampilan rounding tidak mengubah skor tersimpan. Output model invalid tidak masuk buku nilai.
