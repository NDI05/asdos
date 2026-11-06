import { answerProgress, jobIsActive, type PendingAction, type PipelineJob, type ProcessingAnswer } from './processing';
import { jobError } from './workflow';

type Props = {
  document: { status: string; page_count: number; auto_process?:boolean; analysis_result?:{job_id?:string} } | null;
  identityStatus: string; answers: ProcessingAnswer[]; jobs: PipelineJob[];
  pending: PendingAction | null; selectedQuestion: string; pollingError: boolean;
  unassignedCount?:number;
  onSelect: (id: string) => void; onRetry: (job: PipelineJob) => void; onCancel: (job: PipelineJob) => void;
};

export function Spinner() { return <span className="processing-spinner" aria-hidden="true"/>; }

export default function SubmissionProgress(props: Props) {
  const { document, identityStatus, answers, jobs, pending, selectedQuestion, pollingError } = props;
  const renderJob = jobs.find(j => j.kind === 'document_render');
  const renderCancelled = renderJob?.status === 'cancelled';
  const activeJob = jobs.find(jobIsActive);
  const autoJob = jobs.find(j=>j.kind==='analyze_answers'&&jobIsActive(j));
  const autoMode = Boolean(document?.auto_process||document?.analysis_result?.job_id||autoJob||pending?.kind==='auto');
  const autoCount = answers.filter(a=>a.mapping_status==='auto_mapped').length;
  const failedJob = jobs.find(j => j.status === 'failed' && (j.kind === 'document_render' || j.kind==='analyze_answers' || j.kind === 'grade_answer' || answers.some(a =>
    a.id === j.answer_id && (!a.transcript_revision_id || a.transcript_stale))));
  const statuses = answers.map(answer => answerProgress(answer, jobs, pending));
  const mapped = answers.filter(a => (a.mapping_revision_id && a.mapping_status !== 'unmapped') || a.transcript_status === 'verified_blank').length;
  const completed = statuses.filter(s => s.state === 'done' || s.state === 'review').length;
  const renderDone = document?.status === 'valid' && pending?.kind !== 'upload';
  let title = 'Unggah lembar jawaban';
  let detail = 'PDF akan disiapkan menjadi preview halaman sebelum jawaban dipetakan.';
  if (pending?.kind === 'upload') {
    title = 'Mengunggah PDF…'; detail = 'Berkas sedang dikirim ke penyimpanan lokal. Tunggu sampai upload selesai.';
  } else if (activeJob?.kind === 'document_render' || (document && !renderDone && !failedJob && !renderCancelled)) {
    title = activeJob?.status === 'queued' ? 'PDF menunggu antrean render' : 'Sedang menyiapkan halaman PDF…';
    detail = 'Preview akan tampil otomatis setelah render selesai. Belum menjalankan OCR.';
  } else if (failedJob?.kind === 'document_render') {
    title = 'Halaman PDF belum berhasil diproses'; detail = jobError(failedJob.error_code ?? undefined);
  } else if (renderCancelled && !renderDone) {
    title = 'Render PDF dibatalkan'; detail = 'Unggah kembali PDF jika ingin melanjutkan persiapan halaman.';
  } else if (autoJob||pending?.kind==='auto') {
    title = autoJob?.status==='queued'?'OCR dan pemetaan otomatis menunggu antrean'
      :autoJob?.stage==='transcribe_regions'?'Membaca bagian jawaban…'
      :autoJob?.stage==='map_answers'?'Menyusun usulan pemetaan nomor…':'Mencari area dan nomor jawaban…';
    detail = 'Diproses otomatis oleh Qwen lokal tanpa kunci/rubrik. Hasil dan nomor yang meragukan akan ditampilkan untuk ditinjau.';
  } else if (failedJob?.kind==='analyze_answers') {
    title = 'Proses otomatis belum berhasil';detail=jobError(failedJob.error_code??undefined);
  } else if (renderDone && identityStatus !== 'confirmed') {
    title = 'Preview siap · periksa identitas'; detail = 'Cocokkan nama dan NIM pada scan, lalu konfirmasikan identitas di bawah.';
  } else if (activeJob || pending) {
    const activeAnswer = answers.find(a => a.id === activeJob?.answer_id || a.question_id === pending?.questionId);
    title = pending?.kind === 'mapping' ? `Menyimpan pemetaan soal ${activeAnswer?.label ?? ''}…`
      : activeJob?.kind === 'grade_answer' || pending?.kind === 'propose' ? 'Sedang menyiapkan usulan penilaian…'
      : `OCR soal ${activeAnswer?.label ?? ''} ${activeJob?.status === 'queued' ? 'menunggu antrean' : 'sedang berjalan…'}`;
    detail = activeJob?.cancel_requested ? 'Pembatalan diminta. Hasil tidak akan dipromosikan setelah job dibatalkan.'
      : activeJob?.status === 'queued' ? 'Permintaan sudah diterima dan menunggu giliran worker lokal. Status akan berubah otomatis saat proses dimulai.'
      : 'Model lokal sedang memproses jawaban. Hasil akan tampil otomatis; waktu proses bergantung pada panjang jawaban.';
  } else if (autoCount||Boolean(props.unassignedCount)) {
    title='Tinjau pemetaan jawaban';detail='Periksa nomor yang diusulkan otomatis dan selesaikan area yang belum dipetakan. Koreksi dapat memakai teks OCR yang sudah tersedia.';
  } else if (renderDone && completed === answers.length && answers.length) {
    title = 'Transkripsi siap ditinjau'; detail = 'Periksa teks terhadap gambar sebelum meminta atau menerima usulan nilai.';
  } else if (renderDone) {
    title = mapped < answers.length ? 'Menunggu pemetaan jawaban Anda' : 'Area jawaban siap dibaca';
    detail = 'Pilih nomor soal, tandai dan petakan areanya, lalu pilih Baca tulisan. Pemetaan masih dilakukan oleh Anda.';
  }
  const spinning = Boolean(pending || activeJob || (document && !renderDone && !failedJob && !renderCancelled));
  const mappingStep = {label:'Pemetaan jawaban',done:mapped===answers.length&&answers.length>0&&!autoCount&&!props.unassignedCount,
    active:Boolean(autoJob?.stage==='map_answers'||(renderDone&&!autoJob&&(mapped<answers.length||autoCount||props.unassignedCount)))};
  const ocrStep = {label:'Transkripsi OCR',done:completed===answers.length&&answers.length>0,
    active:Boolean(autoJob?.stage==='transcribe_regions'||jobs.some(j=>j.kind==='transcribe_answer'&&jobIsActive(j))||pending?.kind==='transcribe')};
  const steps = [
    { label: 'Upload PDF', done: Boolean(document) && pending?.kind !== 'upload', active: pending?.kind === 'upload' },
    { label: 'Preview halaman', done: renderDone, active: !renderDone && Boolean(document) && !failedJob && !renderCancelled && pending?.kind !== 'upload' },
    ...(autoMode?[ocrStep,mappingStep]:[mappingStep,ocrStep]),
  ];
  return <section className="submission-progress" aria-label="Progres lembar jawaban">
    <div className="processing-heading" role="status" aria-live="polite" aria-atomic="true">
      {spinning ? <Spinner/> : <span className={`processing-marker ${failedJob ? 'failed' : ''}`} aria-hidden="true"/>}
      <div><h2>{title}</h2><p>{detail}</p></div>
    </div>
    <ol className="processing-steps" aria-label="Tahap pemrosesan">
      {steps.map((step, index) => <li key={step.label} className={step.done ? 'done' : step.active ? 'current' : ''}
        aria-current={step.active ? 'step' : undefined}><span aria-hidden="true">{step.done ? '✓' : index + 1}</span>{step.label}
        <small>{step.done ? 'Selesai' : step.active ? step===mappingStep&&!autoJob ? 'Perlu tindakan Anda' : 'Berlangsung' : 'Menunggu'}</small></li>)}
    </ol>
    {spinning && <div className="processing-meter">
      {activeJob && activeJob.progress.total > 0
        ? <><progress max={activeJob.progress.total} value={activeJob.progress.completed} aria-label="Progres proses aktif"/>
          <small>{activeJob.progress.completed} dari {activeJob.progress.total} {activeJob.progress.unit === 'pages' ? 'halaman' : activeJob.progress.unit==='regions'?'area jawaban':'jawaban'} selesai</small></>
        : <><progress aria-label="Proses masih berlangsung"/><small>Masih diproses · progres diperbarui otomatis</small></>}
    </div>}
    {pollingError && <p className="processing-error" role="alert">Pembaruan status terputus. Mencoba terhubung kembali; hasil belum dinyatakan selesai.</p>}
    {document && <div className="processing-counts"><span>{mapped}/{answers.length} nomor dipetakan</span><span>{completed}/{answers.length} transkripsi tersedia</span></div>}
    {renderDone && answers.length > 0 && <div className="answer-progress-list" aria-label="Status per nomor">
      {answers.map((answer, index) => <button type="button" key={answer.id}
        className={`answer-progress-item ${statuses[index].state}`} aria-pressed={selectedQuestion === answer.question_id}
        onClick={() => props.onSelect(answer.question_id)}>
        <b>Soal {answer.label}</b>{statuses[index].state === 'active' && <Spinner/>}<span>{statuses[index].label}</span>
      </button>)}
    </div>}
    {activeJob && !activeJob.cancel_requested && <button type="button" className="quiet-button" onClick={() => props.onCancel(activeJob)}>Batalkan proses aktif</button>}
    {!activeJob && failedJob && <div className="processing-error"><span>{jobError(failedJob.error_code ?? undefined)}</span>
      {failedJob.retryable && <button type="button" className="text-button" onClick={() => props.onRetry(failedJob)}>Coba lagi</button>}</div>}
  </section>;
}
