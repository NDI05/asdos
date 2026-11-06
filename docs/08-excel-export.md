# 08 — Spesifikasi Output Excel

## Catatan implementasi MVP

Exporter source ada di `apps/api/asdos_api/exporter.py` dan dipanggil melalui endpoint export yang terlebih dahulu menyimpan `ExportSnapshot` immutable. Workbook memiliki delapan sheet kontrak. Bila teks melebihi 32.767 karakter, teks lengkap dipindah per bagian ke `Teks_Lanjutan`; tidak dipotong diam-diam. Writer menggunakan string eksplisit untuk konten tak tepercaya, menulis skor sebagai numerik, dan tidak membuat formula/hyperlink otomatis. Tes ZIP/XML sintetik dan workbook contoh tersedia; kompatibilitas visual Excel/LibreOffice dan export kelas besar belum diuji. Hasil aktual dicatat pada `TEST_REPORT.md`.

## Tujuan dan sumber data

Output wajib `.xlsx`, dapat dibuka di Excel dan diuji kompatibilitasnya di LibreOffice. Workbook dibuat dari **export snapshot immutable**; tidak menjalankan OCR/grading ulang. Semua lembar memakai assessment revision yang sama. Export final menolak jika ada submission terpilih yang belum disahkan atau memiliki draft pengganti yang perlu keputusan pemilik.

Pemilik dapat memilih subset mahasiswa secara eksplisit. Jangan mengecualikan yang gagal/belum selesai secara diam-diam. Simpan requested scope, daftar terpilih, jumlah tidak terpilih, dan snapshot ID dalam metadata. Ekspor draft dapat mencakup null dan penghalang; judul serta sheet Informasi harus menampilkan “DRAFT — BELUM DISAHKAN”.

## Workbook kontrak v1

| Sheet | Grain/baris | Kolom wajib |
| --- | --- | --- |
| Informasi | Key/value + catatan | project, assessment, kelas, mode, revision, waktu, skala, W, aturan pembulatan, cakupan, jumlah final/pending |
| Rekap_Nilai | Satu mahasiswa/attempt aktif | submission_id, NIM, Nama, Attempt, Q1_Kontribusi ... Qn_Kontribusi, Total_Kontribusi, Nilai_Akhir, Status, Snapshot_ID |
| Detail_Nomor | Satu mahasiswa × nomor | submission_id, NIM, question_id, Nomor, Raw, Max_Raw, Bobot, Kontribusi, Status_Jawaban, Sumber_Nilai, Review_Status, Alasan_Override, Revision_ID |
| Detail_Kriteria | Satu mahasiswa × nomor × kriteria | submission_id, question_id, criterion_id, Kredit, Max_Poin, Poin, Evidence_Refs, Alasan, Source |
| Transkripsi | Satu segment jawaban | submission_id, question_id, segment_id, region_id, Halaman, Urutan, Teks, Flags, Transcript_Revision_ID |
| Rubrik | Satu kriteria | assessment_revision_id, question_id, Nomor, Soal, Bobot, Max_Raw, criterion_id, Deskripsi, Max_Poin, Level_dan_Anchor, Kunci, Alternatif |
| Riwayat | Satu perubahan yang relevan | event_id, resource_id, action, actor_display, waktu, previous_revision, new_revision, reason |
| Metadata | Key/value atau manifest rows | schema, scoring policy, software commit/release, model/prompt/preprocess versions, export snapshot/hash, input refs/hashes |

Gunakan stable ID untuk hubungan antarsheet. Label soal bukan key relasi karena dapat berubah. Sheet per nomor dinamis tidak diperlukan; format long pada Detail_Nomor/Kriteria mendukung pivot dan banyak soal. Jika ada override nomor tanpa detail kriteria, sheet Kriteria mempertahankan hasil model/asal dengan label bahwa override final berada di Detail_Nomor; jangan mengarang pembagian poin.

Untuk nilai berbasis kriteria, Detail_Kriteria memakai keputusan yang diterima/diedit reviewer, bukan sekadar proposal model awal. Mode final membaca grade_snapshot_criteria; mode draft membaca salinan review_criterion_results/proposal berlabel sumber dalam export_snapshot_items. Seluruh teks/rubrik/riwayat juga diambil dari payload/refs yang dibekukan saat snapshot dibuat.

## Tipe sel dan tampilan

- NIM, UUID, nomor seperti `2a`, hash, dan kode kelas ditulis sebagai **string**, termasuk leading zero.
- Skor dan kontribusi ditulis numerik. Konversi ke angka Excel dilakukan setelah perhitungan Decimal selesai; gunakan batas presisi yang memadai untuk skala 0–100, lalu format `0.00`.
- Null menjadi sel kosong dengan status/alasan di kolom terpisah; nilai 0 valid ditulis angka 0.00.
- Header tebal, freeze top row, filter, border, lebar kolom terukur, wrap pada alasan/teks, tanpa merge pada area tabel.
- Warna membantu membedakan final/draft/needs_review, disertai teks agar tidak hanya mengandalkan warna.
- Nama file aman: `ASDOS_<assessment-slug>_<draft|final>_<timestamp>.xlsx`; nama mahasiswa tidak digunakan sebagai path file server.

## Sumber angka

Nilai_Akhir adalah nilai numerik yang sudah dihitung server dari snapshot. Hindari formula Excel sebagai sumber kebenaran karena engine kalkulasi dan locale dapat berbeda. Total_Kontribusi berasal dari penjumlahan presisi penuh, bukan menjumlah nilai tampilan yang telah dibulatkan. Boleh menambah formula transparansi pada versi lanjut, tetapi tidak mengganti angka otoritatif; simpan cached values dan uji engine bila fitur ditambahkan.

Contoh [assessment](18-example-assessment.md): kontribusi Q1/Q2/Q3 = 16/18/45, total kontribusi 79, Nilai_Akhir = 79.00. Untuk bobot 2/3/5, kontribusi 1.6/1.8/4.5 berjumlah 7.9 dan Nilai_Akhir tetap 79.00; kolom Informasi wajib menunjukkan W=10.

## Keamanan isi

Semua teks pengguna/model memakai `write_string()` atau writer setara dengan tipe eksplisit. Nonaktifkan konversi otomatis `strings_to_formulas` dan `strings_to_urls`. Jangan mengandalkan awalan apostrof sebagai satu-satunya pengaman. Uji string yang diawali `=`, `+`, `-`, `@`, tab dan newline agar tetap string pada XML workbook; tautan dari OCR tidak otomatis menjadi hyperlink. Tidak ada macro, external workbook link, DDE, atau executable attachment.

Tidak menyertakan signed URL sementara atau path host di workbook. Bukti direferensikan dengan submission/page/region ID; pengguna membuka gambar melalui aplikasi dengan autentikasi. Menyematkan gambar/PDF asli ke Excel ditunda untuk menjaga ukuran dan privasi.

## Batas dan data panjang

Excel memiliki batas panjang sel 32.767 karakter dan batas jumlah baris/kolom; writer wajib memeriksanya. Transkripsi panjang dibagi deterministik menjadi segment/part berurutan dengan ID induk; tidak boleh terpotong diam-diam. Teks soal/alasan panjang juga dibagi atau dialihkan ke sheet lanjutan dengan manifest, bukan sekadar truncate. Jika baris melebihi kapasitas sheet, buat part sheet dengan header sama dan rekam di Informasi.

Ekspor besar diproses worker dengan batas RAM dan temporary file privat. Artefak baru hanya berstatus succeeded setelah workbook berhasil ditutup, hash dihitung, dan manifest sesuai snapshot. Hapus file sementara jika gagal.

## Acceptance ekspor

1. Delapan sheet hadir dengan schema konsisten; jumlah baris dapat direkonsiliasi dengan mahasiswa, nomor, dan kriteria pada snapshot.
2. Backend dan workbook identik sampai dua desimal; leading-zero NIM utuh; Unicode Indonesia/Inggris terbaca.
3. Workbook draft tidak memiliki total final untuk submission yang masih memiliki null; skor sementara tidak diberi label final.
4. Semua untrusted text disimpan sebagai string; tidak ada formula/URL tersembunyi dari input.
5. Dua ekspor dari snapshot yang sama memiliki isi nilai dan manifest identik meskipun timestamp/ZIP bytes dapat berbeda.
6. File dibuka tanpa repair warning dan diverifikasi dengan pembaca independen. Uji visual awal dilakukan pada Excel atau LibreOffice ketika runtime tersedia.

Rujukan S09 menjelaskan perilaku konversi string, tipe angka, dan batas sel XlsxWriter.
