import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import SubmissionProgress from './SubmissionProgress';
import { answerProgress, preserveUnchangedAnswers, type PipelineJob, type ProcessingAnswer } from './processing';

const answer: ProcessingAnswer = { id:'a1', question_id:'q1', label:'1', mapping_revision_id:null,
  transcript_revision_id:null, transcript_status:'pending', transcript_stale:false };
const task = (status: string, kind='transcribe_answer'): PipelineJob => ({
  id:'job1', kind, status, answer_id:kind==='document_render'?null:'a1', document_id:'doc1', attempt:1,
  error_code:status==='failed'?'MODEL_UNAVAILABLE':null, retryable:status==='failed', cancel_requested:false,
  progress:{completed:0,total:0,unit:kind==='document_render'?'pages':'answers'},
});
const noop = () => {};
const view = (overrides: Partial<Parameters<typeof SubmissionProgress>[0]> = {}) => renderToStaticMarkup(
  <SubmissionProgress document={{status:'valid',page_count:1}} identityStatus="confirmed" answers={[answer]}
    jobs={[]} pending={null} selectedQuestion="q1" pollingError={false} onSelect={noop} onRetry={noop} onCancel={noop}
    {...overrides}/>);

describe('observable upload, mapping and OCR progress', () => {
  it('starts feedback while the upload request itself is pending', () => {
    const html = view({document:null,pending:{kind:'upload'}});
    expect(html).toContain('Mengunggah PDF');
    expect(html).toContain('processing-spinner');
    expect(html).toContain('role="status"');
    expect(html).not.toContain('value="'); // No fabricated upload percentage.
  });
  it('restores running render feedback from persisted job status without claiming a percentage', () => {
    const html = view({document:{status:'uploaded',page_count:0},jobs:[task('running','document_render')]});
    expect(html).toContain('Sedang menyiapkan halaman PDF');
    expect(html).toContain('<progress aria-label="Proses masih berlangsung"');
    expect(html).not.toContain('value="');
  });
  it('separates reviewer action from a running process', () => {
    const html = view();
    expect(html).toContain('Menunggu pemetaan jawaban Anda');
    expect(html).toContain('Perlu tindakan Anda');
    expect(html).not.toContain('class="processing-spinner"');
    expect(html).not.toContain('<progress');
    expect(view({identityStatus:'pending'})).toContain('periksa identitas');
  });
  it('shows queued versus running OCR for the right answer', () => {
    const mapped = {...answer,mapping_revision_id:'m1'};
    expect(answerProgress(mapped,[task('queued')],null).label).toBe('Menunggu antrean OCR');
    expect(answerProgress(mapped,[task('running')],null).label).toContain('Sedang membaca');
    expect(answerProgress({...mapped,id:'a2'},[task('running')],null).state).toBe('waiting');
    expect(view({answers:[mapped],jobs:[task('running')]})).toContain('Sedang membaca tulisan');
  });
  it('keeps unreadable OCR in review rather than declaring it ready for grading', () => {
    const unreadable = {...answer,mapping_revision_id:'m1',transcript_revision_id:'t1',transcript_status:'unreadable'};
    expect(answerProgress(unreadable,[],null).state).toBe('review');
    expect(view({answers:[unreadable]})).toContain('Perlu tinjauan keterbacaan');
  });
  it('treats a cleared mapping revision as unmapped', () => {
    const cleared = {...answer, mapping_revision_id:'empty-revision', mapping_status:'unmapped'};
    expect(answerProgress(cleared,[],null).label).toBe('Menunggu pemetaan Anda');
    expect(view({answers:[cleared]})).toContain('0/1 nomor dipetakan');
  });
  it('stops loading and offers retry on failure, including after reopening', () => {
    const failed = task('failed','document_render');
    const html = view({document:{status:'uploaded',page_count:0},jobs:[failed]});
    expect(html).toContain('belum berhasil diproses');
    expect(html).toContain('Coba lagi');
    expect(html).not.toContain('<progress');
    expect(html).not.toContain('class="processing-spinner"');
    expect(view({document:{status:'uploaded',page_count:0},jobs:[task('cancelled','document_render')]}))
      .toContain('Render PDF dibatalkan');
  });
  it('discloses a polling failure and only uses measured counters', () => {
    const render = {...task('running','document_render'),progress:{completed:2,total:5,unit:'pages'}};
    const html = view({document:{status:'uploaded',page_count:0},jobs:[render],pollingError:true});
    expect(html).toContain('value="2"');
    expect(html).toContain('max="5"');
    expect(html).toContain('Pembaruan status terputus');
  });
  it('preserves the selected answer object while only job status changes during polling', () => {
    const previous = {answers:[answer],pipeline_jobs:[task('queued')]};
    const next = {answers:[{...answer}],pipeline_jobs:[task('running')]};
    const merged = preserveUnchangedAnswers(previous,next);
    expect(merged.answers[0]).toBe(answer);
    expect(merged.pipeline_jobs[0].status).toBe('running');
    const completed = {...next,answers:[{...answer,transcript_revision_id:'t1'}]};
    expect(preserveUnchangedAnswers(previous,completed).answers[0]).not.toBe(answer);
  });
});
