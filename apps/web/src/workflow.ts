export type SeedQuestion = {
  stable_question_id: string; label: string; order: number; text: string;
  answer_type: string; weight: string;
};

export function questionSeeds(questions: SeedQuestion[]) {
  return questions.map(({stable_question_id, label, order, text, answer_type, weight}) =>
    ({stable_question_id, label, order, text, answer_type, weight}));
}

export function splitQuestionText(text: string): SeedQuestion[] {
  const questions: SeedQuestion[] = [];
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^\s*(\d+[a-z]?)\s*[.)]\s*(.*)$/i);
    if (match) {
      questions.push({stable_question_id: `q${questions.length + 1}`, label: match[1],
        order: questions.length + 1, text: match[2].trim(), answer_type: 'essay', weight: '1'});
    } else if (questions.length) {
      const last = questions[questions.length - 1];
      last.text = `${last.text}\n${line}`.trim();
    }
  }
  if (!questions.length && text.trim()) questions.push({stable_question_id: 'q1', label: '1',
    order: 1, text: text.trim(), answer_type: 'essay', weight: '1'});
  if (new Set(questions.map(q => q.label)).size !== questions.length)
    throw new Error('Nomor soal berulang. Perbaiki teks hasil ekstraksi sebelum memisahkan soal.');
  return questions;
}

export function jobError(code?: string): string {
  const messages: Record<string, string> = {
    AUTO_MAPPING_FAILED:'OCR atau pencarian area belum berhasil. Coba kembali atau petakan area secara manual.',
    LOCATOR_OUTPUT_INVALID:'Area jawaban belum dapat dibaca dengan aman. Coba lagi atau petakan area secara manual.',
    AUTO_MAPPING_EXISTING_WORK:'Pemetaan sudah pernah dibuat pada dokumen ini. Koreksi hasil yang ada; proses otomatis tidak menimpa pekerjaan Anda.',
    AUTO_MAPPING_REVIEW_REQUIRED:'Tinjau dan setujui pemetaan otomatis sebelum menilai jawaban.',
    STALE_AUTO_MAPPING_INPUT:'Dokumen, area, atau teks berubah saat proses otomatis berjalan. Hasil lama tidak diterapkan.',
    AUTO_REGION_LIMIT:'Terlalu banyak area jawaban untuk satu proses. Gunakan pemetaan manual atau PDF yang lebih kecil.',
    PDF_PIXEL_LIMIT: 'Ukuran render halaman melebihi batas piksel. Renderer terbaru menyesuaikan DPI; pilih Coba lagi setelah pembaruan aktif.',
    PDF_RENDER_TIMEOUT: 'Render PDF melewati batas waktu. Periksa PDF atau coba ulang berkas ini.',
    MODEL_UNAVAILABLE: 'Checkpoint model lokal belum disiapkan pada komputer ini.',
    MODEL_RUNTIME_MISSING: 'Paket runtime model belum terpasang. Jalankan penyiapan model lokal.',
    MODEL_DEVICE_UNAVAILABLE: 'Backend inferensi model lokal belum tersedia pada runtime ini.',
    TROCR_UNAVAILABLE: 'Checkpoint TrOCR eksperimen belum tersedia. Periksa ASDOS_TROCR_DIR pada komputer ini.',
    TROCR_MANIFEST_INVALID: 'Manifest checkpoint TrOCR tidak valid. Daftarkan ulang checkpoint eksperimen.',
    TROCR_CHECKPOINT_INCOMPLETE: 'Berkas checkpoint TrOCR belum lengkap.',
    TROCR_CHECKPOINT_HASH_MISMATCH: 'Hash checkpoint TrOCR berubah. Pulihkan checkpoint dari salinan yang tepercaya.',
    TROCR_LOAD_FAILED: 'Checkpoint TrOCR gagal dimuat pada runtime lokal.',
    TROCR_RUNTIME_INCOMPATIBLE: 'Runtime Transformers lokal tidak cocok dengan checkpoint TrOCR.',
    TROCR_LINE_SEGMENTATION_FAILED: 'Baris pada area jawaban tidak dapat dipisahkan. Periksa crop atau transkripsikan manual.',
    TRANSCRIBER_CONFIG_INVALID: 'Pilihan ASDOS_TRANSCRIBER harus qwen atau trocr.',
    QUESTION_TEXT_UNREADABLE: 'Sebagian teks soal tidak terbaca. Periksa PDF atau masukkan teks soal.',
    UNREADABLE_TRANSCRIPTION_REVIEW_REQUIRED: 'Perbaiki bagian tulisan yang tidak terbaca sebelum meminta penilaian.',
    TRANSCRIPT_EVIDENCE_INVALID: 'Bukti transkripsi tidak cocok dengan area dokumen aktif. Periksa pemetaan dan simpan ulang transkripsi sebelum meminta usulan.',
    MODEL_OUTPUT_INVALID: 'Model belum menghasilkan usulan yang valid. Coba lagi atau lakukan penilaian manual.',
    STALE_RUBRIC_INPUT: 'Soal berubah selama proses. Buat ulang acuan untuk versi soal terkini.',
    RUBRIC_GENERATION_INVALID: 'Acuan dari model belum valid. Periksa soal lalu coba buat acuan kembali.',
  };
  return messages[code || ''] || `Proses gagal${code ? ` (${code})` : ''}. Periksa masukan lalu coba kembali.`;
}

/** Describe finalization blockers without exposing internal region IDs. */
export function finalizationMessage(blockers: string[]): string {
  const questions = new Set<string>();
  let areas = 0, other = false;
  for (const blocker of blockers) {
    if (blocker.startsWith('region:') && blocker.endsWith(':unassigned')) { areas++; continue; }
    const match = blocker.match(/^([^:]+):(.+)$/);
    if (match && !['job', 'region'].includes(match[1])) questions.add(match[1]);
    else other = true;
  }
  const parts = [];
  if (questions.size) parts.push(`Periksa dan simpan keputusan untuk soal ${Array.from(questions).join(', ')}.`);
  if (areas) parts.push(`Tinjau ${areas} area yang belum dipetakan atau dikecualikan.`);
  if (other || !parts.length) parts.push('Periksa identitas, dokumen, dan proses yang masih berjalan.');
  return parts.join(' ');
}
