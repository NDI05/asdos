# Feedback Pengujian ASDOS — 3 November 2026

## Kesimpulan

**Alur koreksi manual dan ekspor pada fixture sintetis berjalan. Koreksi otomatis tulisan tangan belum dapat digunakan pada runtime yang diperiksa karena checkpoint Qwen belum diprovisikan.** Belum ada hasil OCR, nilai, atau ukuran akurasi atas scan jawaban pengguna dari pengujian ini.

Pengujian ini adalah review sistem yang sudah dibuat; source aplikasi tidak diperbaiki atau diganti. Perubahan pengguna pada App.tsx dan styles.css dipertahankan. Pengujian memakai database/akun/artefak sintetis sementara, bukan data kelas yang sedang digunakan.

## Contoh yang ditemukan

| File | Yang berhasil dibaca |
| --- | --- |
| Pretest Pertemuan Keenam (dragged).pdf | Satu halaman soal, dua nomor; teks soal berhasil diambil dari dokumen |
| Dokumen Pindaian.pdf | Terdeteksi sebagai PDF scan satu halaman; isi tulisan belum ditranskripsikan/ditinjau secara visual pada pass ini |

Nomor1 meminta analisis sistem berkas disk dibanding /proc, /sys dan /dev serta pemanfaatannya oleh top/free. Nomor2 meminta alur resolusi nama domain Linux dan fungsi /etc/hosts, /etc/resolv.conf, /etc/nsswitch.conf. Kedua nomor cocok untuk menguji narasi dan token teknis yang harus dipertahankan OCR.

File dikenali melalui sumber dokumen. Upaya mengambil byte PDF ke runtime lokal gagal pada resolusi DNS endpoint unduhan. Oleh karena itu, **kedua PDF asli belum diunggah ke API aplikasi** dalam pengujian ini. Tidak ada scan asli yang dikirim ke layanan OCR eksternal. Rubrik/kunci dan bobot resmi untuk contoh ini juga belum ditetapkan bersama dosen; laporan tidak mengarang nilai mahasiswa.

## Pemeriksaan yang benar-benar dijalankan

| Pemeriksaan | Bukti/hasil | Batas |
| --- | --- | --- |
| Backend pytest | 22 passed in 1.69s | Fixture sintetis; tidak menjalankan model |
| Frontend Vitest | 1 passed | Hanya server-render form login, bukan interaksi browser |
| TypeScript + Vite build | tsc -b dan build berhasil; 29 modul ditransformasi | Build bukan bukti seluruh tombol/alur browser benar |
| Runtime model | available=false; reason=checkpoint_not_provisioned | Tidak membuktikan kualitas OCR atau kapasitas GPU |
| Checkpoint lokal | 0 file .safetensors pada direktori models | Adapter source tersedia, bobot belum tersedia |
| E2E API manual ulang | Assessment, PDF sintetis, mapping, transkripsi/review manual, final79.00 dan workbook delapan sheet lulus | Angka79.00 milik fixture, bukan nilai mahasiswa |
| Permintaan transkripsi nyata melalui endpoint pada fixture | HTTP202, job kemudian failed, error_code=MODEL_UNAVAILABLE | Tidak ada inference pretrained yang berhasil |
| Integritas setelah AI gagal | Snapshot final dan transkripsi fixture tetap sama | Positif: gagal model tidak menimpa hasil manual yang diperiksa |
| Simulasi output tidak terbaca | Adapter diberi keluaran [tidak terbaca]; hasil text sama, flags=[] dan confidence=null | Probe kontrak dengan mock; bukan hasil model atas scan pengguna |
| Compose | Interpolasi config gagal karena ASDOS_DB_PASSWORD belum diset pada pemanggilan; akses Docker socket juga ditolak izin lingkungan | Stack PostgreSQL/Redis/Celery tidak diuji pada pass ini |

Perintah aktual: `.venv/bin/python -m pytest -q -p no:cacheprovider`, `npm test -- --reporter=dot`, dan `npm run build`. Probe tambahan menjalankan TestManualWorkflow pada DB sementara, memanggil endpoint transcribe, lalu memeriksa job dan integritas snapshot. Tidak ada pengujian browser end-to-end pada sesi ini.

## Temuan prioritas

### P1 — Model utama belum siap di runtime

API model_status mengembalikan checkpoint_not_provisioned. Permintaan transcribe yang sudah memiliki dokumen, identitas dan mapping berakhir MODEL_UNAVAILABLE. Ini penghalang utama tujuan membaca tulisan mahasiswa dan mengoreksi otomatis; keberadaan adapter dan tes manual tidak menyelesaikan kebutuhan tersebut.

Tindak lanjut: provisikan checkpoint resmi pada revision yang dikunci, pasang runtime kompatibel, buktikan backend perangkat yang tersedia, lakukan smoke inference dan kemudian tes dua PDF asli. Jangan menyebut model aktif hanya karena manifest/config hadir; harus ada bukti load dan inference. Flag MPS/CUDA false pada runtime tidak cukup untuk menyimpulkan perangkat fisik tidak mendukung GPU karena pemeriksaan juga bergantung dependency runtime.

### P1 — Tulisan tidak terbaca belum otomatis menjadi penghalang penilaian

Pada `apps/api/asdos_api/model_adapters.py:215`, prompt meminta marker [tidak terbaca], tetapi hasil transcribe pada baris223 membungkus teks sebagai TranscriptSegment dengan flags kosong. Probe terkontrol mereproduksi hasil tersebut. `apps/worker/tasks.py:354` dan baris363 kemudian menyimpan status transcribed, dengan flags transcript kosong.

Dampak: teks yang mengandung ketidakpastian dapat masuk sebagai transkripsi biasa ke tahap proposal, bukan otomatis diarahkan ke review karena unreadable. Pengesahan manusia masih ada, tetapi pengaman domain yang dimaksud belum diterapkan pada titik ini. Uji ini tidak membuktikan bahwa sistem otomatis memfinalisasi nilai nol; risiko ada pada salah klasifikasi input penilaian.

Tindak lanjut: deteksi ketidakpastian secara terstruktur, simpan flags/span unreadable dan blok proposal/finalisasi yang bergantung bagian ambigu sampai reviewer menyelesaikannya. Tambahkan regression untuk teks seluruhnya tidak terbaca dan sebagian tidak terbaca, termasuk angka/negasi penting.

### P1 — UI mengonfirmasi identitas saat upload tanpa langkah pemeriksaan terpisah

`apps/web/src/App.tsx:199` memanggil confirm-identity langsung setelah upload dan mengambil state submission. Pesan pada baris204 menyatakan identitas dikonfirmasi; tidak ada kesempatan pada urutan ini untuk memeriksa halaman yang baru dirender sebelum aksi konfirmasi tersebut.

Dampak: unggahan PDF salah dapat dikaitkan ke NIM/nama yang sudah diketik dan ditandai confirmed tanpa inspeksi dokumen oleh pengguna. Backend mengikat konfirmasi ke hash, tetapi panggilan otomatis UI mengurangi fungsi pengaman manusia yang direncanakan. Ini temuan inspeksi source, belum reproduksi klik pada browser.

Tindak lanjut: pisahkan upload dan konfirmasi identitas, tampilkan preview/header dokumen, lalu minta aksi konfirmasi eksplisit. Penggantian PDF harus kembali pending.

### P2 — Impor soal scan belum memiliki fallback OCR

Jalur question_import menggunakan PDF text layer melalui `apps/worker/render_pdf.py:47`. Gambar halaman dirender tetapi tidak otomatis ditranskripsikan sebagai soal bila text layer kosong. PDF soal contoh memiliki teks yang berhasil dibaca dari sumber dokumen; kesimpulan tentang importer berasal dari source, bukan dari upload file asli yang belum berhasil.

Tindak lanjut: deteksi text layer kosong/meragukan dan sediakan OCR lokal atau input manual dengan status yang jelas. Soal hasil impor tetap draft sampai diperiksa dosen.

### P2 — Cakupan tes UI masih sangat tipis

`apps/web/src/App.test.tsx` memeriksa form login melalui renderToStaticMarkup. Build dan tes tersebut belum membuktikan upload, pemetaan region, pemilihan nomor, koreksi nilai, finalisasi atau unduhan bekerja melalui browser.

Tindak lanjut: tambahkan E2E browser untuk satu assessment dua nomor, termasuk gagal AI, unresolved/unreadable, revisi dan verifikasi workbook. Pisahkan hasil fake/manual dari inference nyata.

## Urutan uji lanjutan pada contoh pengguna

1. Sediakan byte kedua PDF pada runtime dan verifikasi hash/halamannya.
2. Pastikan checkpoint/runtime benar-benar bisa inference.
3. Masukkan dua soal sebagai draft; dosen menyetujui kunci, kriteria, kredit parsial dan bobot.
4. Unggah scan, tinjau identitas dan petakan jawaban ke nomor1/2.
5. Jalankan transkripsi literal tanpa memberikan soal/kunci ke transcriber.
6. Bandingkan tulisan asli dengan transkripsi; catat kata/angka/token teknis yang salah atau hilang.
7. Jalankan proposal penilaian, tinjau bukti dan kredit per kriteria, lalu bandingkan dengan penilaian manusia.
8. Sahkan hanya setelah penghalang selesai; ekspor Excel dan cocokkan seluruh angka dengan snapshot.

**Status saat ini: fungsi manual teruji; AI belum siap; pengujian PDF asli dan ketepatan penilaian contoh masih terhalang.** Tidak ada persentase akurasi atau nilai mahasiswa yang sah untuk dilaporkan dari sesi ini.
