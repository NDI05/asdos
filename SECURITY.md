# Pelaporan Keamanan ASDOS

ASDOS masih berupa prototipe; belum ada versi produksi yang didukung. Untuk kerentanan, gunakan [pelaporan kerentanan privat](https://github.com/NDI05/asdos/security/advisories/new) atau tab **Security → Report a vulnerability**. Jangan membuka issue publik yang memuat detail eksploit atau data mahasiswa. Jangan mengirim scan, NIM, nilai, atau secret.

Jangan membuka issue publik berisi PDF mahasiswa, identitas, nilai, token akses, atau langkah eksploitasi terhadap instalasi yang masih rentan. Gunakan kanal privat yang tercantum pada repository setelah tersedia. Sertakan versi, dampak, langkah reproduksi dengan data sintetik, dan perbaikan yang disarankan.

Lingkup perhatian utama: akses silang assessment, unduhan artefak, parser PDF, resource exhaustion, prompt injection melalui jawaban mahasiswa, perubahan nilai tanpa izin, dan formula/tautan berbahaya di Excel. Rencana kontrol dan respons ada pada [keamanan dan privasi](docs/10-security-and-privacy.md).

Target respons: triage awal dalam 3 hari kerja, koordinasi perbaikan serta pengungkapan dengan pelapor, dan advisori versi terdampak setelah perbaikan tersedia. Ini target sukarela, bukan SLA.
