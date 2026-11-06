export type PipelineJob = {
  id: string; kind: string; status: string; answer_id: string | null; document_id: string;
  attempt: number; error_code: string | null; retryable: boolean; cancel_requested: boolean;
  progress: { completed: number; total: number; unit: string };
  stage?: string;
};
export type PendingAction = { kind: 'upload' | 'mapping' | 'transcribe' | 'propose' | 'auto'; questionId?: string };
export type ProcessingAnswer = {
  id: string; question_id: string; label: string; mapping_revision_id: string | null;
  transcript_revision_id: string | null; transcript_status: string; transcript_stale: boolean;
  mapping_status?: string;
};
export const jobIsActive = (job: Pick<PipelineJob, 'status'>) => ['queued', 'running'].includes(job.status);

export function answerProgress(answer: ProcessingAnswer, jobs: PipelineJob[], pending: PendingAction | null) {
  const job = jobs.find(j => j.answer_id === answer.id && j.kind === 'transcribe_answer');
  const local = pending?.questionId === answer.question_id ? pending.kind : null;
  if (local === 'mapping') return { label: 'Menyimpan pemetaan…', state: 'active' };
  if (local === 'transcribe') return { label: 'Mengirim permintaan OCR…', state: 'active' };
  const analysis = jobs.find(j => j.kind === 'analyze_answers' && jobIsActive(j));
  if (analysis && !answer.mapping_revision_id) return { label: analysis.stage === 'transcribe_regions' ? 'Sedang membaca area jawaban…' : 'Sedang mencari nomor dan area…', state:'active' };
  if (job && jobIsActive(job)) return {
    label: job.cancel_requested ? 'Menunggu pembatalan OCR…' : job.status === 'queued' ? 'Menunggu antrean OCR' : 'Sedang membaca tulisan…',
    state: 'active',
  };
  if (answer.transcript_status === 'verified_blank') return { label: 'Kosong terverifikasi', state: 'done' };
  if (answer.mapping_status === 'auto_mapped') return { label:'Pemetaan otomatis · perlu ditinjau',state:'review' };
  if (answer.transcript_revision_id && !answer.transcript_stale) return {
    label: answer.transcript_status === 'unreadable' ? 'Perlu tinjauan keterbacaan' : 'Transkripsi tersedia',
    state: answer.transcript_status === 'unreadable' ? 'review' : 'done',
  };
  if (!answer.mapping_revision_id || answer.mapping_status === 'unmapped') return { label: 'Menunggu pemetaan Anda', state: 'waiting' };
  if (job?.status === 'failed') return { label: 'OCR gagal', state: 'failed' };
  if (job?.status === 'cancelled') return { label: 'OCR dibatalkan', state: 'waiting' };
  return { label: answer.transcript_stale ? 'Pemetaan berubah · baca ulang' : 'Siap dibaca · pilih Baca tulisan', state: 'waiting' };
}

// Polling must not replace unchanged answer objects and erase unsaved form edits.
export function preserveUnchangedAnswers<T extends { answers: { id: string }[] }>(previous: T, incoming: T): T {
  return { ...incoming, answers: incoming.answers.map(answer => {
    const old = previous.answers.find(item => item.id === answer.id);
    return old && JSON.stringify(old) === JSON.stringify(answer) ? old : answer;
  }) };
}
