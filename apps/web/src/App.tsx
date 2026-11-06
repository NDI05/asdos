import RegionOverlay from './RegionOverlay';
import { questionSeeds, splitQuestionText, jobError, finalizationMessage } from './workflow';
import FinalizationChecklist from './FinalizationChecklist';
import SubmissionProgress, { Spinner } from './SubmissionProgress';
import AutoMappingReview, { type AutoRegion } from './AutoMappingReview';
import GradeProposalView from './GradeProposalView';
import { jobIsActive, preserveUnchangedAnswers, type PipelineJob, type PendingAction } from './processing';
import { FormEvent, PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

type ApiError = Error & { code?: string; details?: unknown };
type User = { id: string; username: string; display_name: string; role: string };
type Assessment = { id: string; title: string; course_label: string; language: string; status: string; revision: null | { id: string; sequence: number; version: number; status: string }; submission_count: number };
type Criterion = { id: string; description: string; max_points: string; credit_levels: string[]; anchors: Record<string, string> };
type ModelHealth = { available:boolean; reason?:string; model_id?:string; transcriber?:{backend:'qwen'|'trocr';available:boolean;reason?:string;model_id:string;revision:string;experimental:boolean;review_required:boolean;human_accuracy_measured?:boolean;held_out_evaluation?:boolean;device?:string|null} };
type Question = { stable_question_id: string; label: string; order: number; text: string; answer_type: string; weight: string; reference_answer: string; alternatives: string[]; criteria: Criterion[] };
type Region = AutoRegion;
type Page = { id: string; page_index: number; page_image_revision_id: string; width_px: number; height_px: number; rotation: number; image_url: string; regions: Region[] };
type Answer = { id: string; question_id: string; label: string; text: string; weight: string; rubric: Criterion[]; mapping_status: string; mapping_revision_id: string | null; region_ids: string[]; transcript_status: string; transcript: string; transcript_flags?:string[]; transcript_revision_id: string | null; transcript_revision_no: number; transcript_stale: boolean; segments: {segment_id: string; region_id: string; order: number; text: string}[]; proposal: {criteria: {criterion_id: string; credit: string; label: string; evidence_refs: {segment_id:string;start:number;end:number;region_id:string}[]; rationale:string}[]} | null; proposal_id: string | null; proposal_stale: boolean; review: {status:string; criteria: {criterion_id:string;credit:string;evidence_refs:unknown[];rationale:string;source:string}[] | null; override_raw:string|null; reason:string|null} | null };
type Submission = { id: string; assessment_id: string; assessment_revision_id: string; assessment_revision_status: string; external_student_id: string; display_name: string; attempt_no: number; identity_status: string; claimed_identity?:{external_student_id:string;display_name:string}; identity_confirmation_id: string | null; document: null | { id:string; sha256:string; status:string; page_count:number; layout_revision_id:string|null; auto_process?:boolean; analysis_result?:{job_id?:string;flags?:string[]}; original_url:string }; pages: Page[]; answers: Answer[]; pipeline_jobs?: PipelineJob[]; unassigned_region_ids?:string[]; review_revision: null|{id:string;sequence:number;version:number;status:string}; final_snapshot: null|{id:string;score:string;revision_id:string;approved_at:string}; status:string; version:number };

type AppError = { error?: { code?: string; message?: string; details?: unknown } };

let csrfToken = '';
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  const isForm = init.body instanceof FormData;
  if (init.body && !isForm && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');
  if (init.method && !['GET', 'HEAD', 'OPTIONS'].includes(init.method.toUpperCase()) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as AppError;
    const err = new Error(data.error?.message || `Permintaan gagal (${response.status})`) as ApiError;
    err.code = data.error?.code;
    err.details = data.error?.details;
    throw err;
  }
  if (response.status === 204) return undefined as T;
  const type = response.headers.get('content-type') || '';
  return (type.includes('application/json') ? await response.json() : undefined) as T;
}
function json(body: unknown): string { return JSON.stringify(body); }
function messageOf(error: unknown): string {
  const err = error as ApiError;
  if (err?.details && typeof err.details === 'object') {
    const details = err.details as {blockers?:string[]};
    if (Array.isArray(details.blockers)) return finalizationMessage(details.blockers);
  }
  return err?.message || 'Terjadi kesalahan.';
}
function freshQuestion(index: number): Question { return { stable_question_id: `q${index}`, label: String(index), order: index, text: '', answer_type: 'essay', weight: '1', reference_answer: '', alternatives: [], criteria: [] }; }
function Icon({name}:{name:string}) { const paths: Record<string,string> = {grid:'M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z',book:'M4 4.5A2.5 2.5 0 0 1 6.5 2H20v17H6.5A2.5 2.5 0 0 0 4 21zM4 4.5v16',upload:'M12 16V4m0 0L7 9m5-5 5 5M4 16v4h16v-4',check:'m5 12 4 4L19 6',download:'M12 4v12m0 0 5-5m-5 5-5-5M4 20h16',plus:'M12 5v14m-7-7h14',arrow:'M5 12h14m-6-6 6 6-6 6',file:'M6 2h8l5 5v15H6zM14 2v6h5',rotate:'M20 11a8 8 0 1 0 2 5m0-9v5h-5',spark:'m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7z'}; return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.file}/></svg>; }

export default function App() {
  const [user, setUser] = useState<User|null>(null);
  const [loginError, setLoginError] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [assessment, setAssessment] = useState<Assessment|null>(null);
  const [revision, setRevision] = useState<{id:string;version:number;status:string;questions:Question[]}|null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [submissionRows, setSubmissionRows] = useState<{id:string;external_student_id:string;display_name:string;identity_status:string;status:string;final_score:string|null;document_status:string;document_filename?:string|null;identity_candidate?:{name:string|null;student_id:string|null}|null;processing?:PipelineJob|null;grade_progress?:{succeeded:number;failed:number;scheduled:number;total:number}}[]>([]);
  const [selectedSubmissionIds, setSelectedSubmissionIds] = useState<string[]>([]);
  const [submission, setSubmission] = useState<Submission|null>(null);
  const [activeView, setActiveView] = useState<'overview'|'assessment'|'submission'>('overview');
  const [studentId, setStudentId] = useState('');
  const [studentName, setStudentName] = useState('');
  const [studentFile, setStudentFile] = useState<File|null>(null);
  const [batch, setBatch] = useState<{file:File;submissionId?:string;status:'waiting'|'uploading'|'done'|'attention'|'failed';error?:string}[]>([]);
  const [batchBusy,setBatchBusy]=useState(false);
  const [autoProcess, setAutoProcess] = useState(true);
  const [showReplacement, setShowReplacement] = useState(false);
  const [questionPdf, setQuestionPdf] = useState<File|null>(null);
  const [selectedQuestion, setSelectedQuestion] = useState('');
  const [selectedRegions, setSelectedRegions] = useState<string[]>([]);
  const [drawing, setDrawing] = useState<[number,number,number,number]|null>(null);
  const [transcriptText, setTranscriptText] = useState('');
  const [reviewCredits, setReviewCredits] = useState<Record<string,string>>({});
  const [reviewReason, setReviewReason] = useState('');
  const [overrideRaw, setOverrideRaw] = useState('');
  const [answerStatus, setAnswerStatus] = useState('partially_correct');
  const [job, setJob] = useState<{id:string;status:string;error_code?:string;attempt?:number;kind?:string}|null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction|null>(null);
  const [pollingError, setPollingError] = useState(false);
  const [draftDirty, setDraftDirty] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelHealth|null>(null);
  const [selectedPageId, setSelectedPageId] = useState('');
  const [questionImportDocId, setQuestionImportDocId] = useState('');
  const [questionImportText, setQuestionImportText] = useState('');
  const imageBox = useRef<HTMLDivElement>(null);
  const pointerStart = useRef<[number,number]|null>(null);

  const autoAnalysisBusy = (submission?.pipeline_jobs??[]).some(j=>j.kind==='analyze_answers'&&jobIsActive(j));
  const generationBusy = job?.kind === 'rubric_generate' && ['queued','running'].includes(job.status);
  const selectedAnswer = useMemo(() => submission?.answers.find(answer => answer.question_id === selectedQuestion) || submission?.answers[0] || null, [submission, selectedQuestion]);
  const selectedPage = submission?.pages.find(page=>page.id===selectedPageId) || submission?.pages[0] || null;
  const pipelineJobs = submission?.pipeline_jobs ?? [];
  const hasActiveSubmissionJobs = pipelineJobs.some(jobIsActive) || Boolean(submission?.document && submission.document.status !== 'valid' && !pipelineJobs.some(j => j.kind === 'document_render' && ['failed','cancelled'].includes(j.status)));
  const selectedOcrBusy = Boolean(selectedAnswer && (pipelineJobs.some(j => j.answer_id === selectedAnswer.id && j.kind === 'transcribe_answer' && jobIsActive(j)) || (pendingAction?.kind === 'transcribe' && pendingAction.questionId === selectedAnswer.question_id)));
  const selectedGradeBusy = Boolean(selectedAnswer && pipelineJobs.some(j => j.answer_id === selectedAnswer.id && j.kind === 'grade_answer' && jobIsActive(j)));

  const loadAssessments = useCallback(async () => {
    const data = await api<{items:Assessment[]}>('/api/v1/assessments');
    setAssessments(data.items);
  }, []);
  const loadSubmission = useCallback(async (id: string) => {
    const data = await api<Submission>(`/api/v1/submissions/${id}`);
    setSubmission(data);
    setPollingError(false);
    setStudentId(data.external_student_id || data.claimed_identity?.external_student_id || '');
    setStudentName(data.identity_status === 'confirmed' ? data.display_name : data.claimed_identity?.display_name || '');
    setSelectedPageId(current=>data.pages.some(page=>page.id===current)?current:(data.pages[0]?.id||''));
    if (!selectedQuestion && data.answers[0]) setSelectedQuestion(data.answers[0].question_id);
  }, [selectedQuestion]);
  const loadSubmissionList = useCallback(async (id:string) => {
    const data = await api<{items:any[]}>(`/api/v1/assessments/${id}/submissions`);
    setSubmissionRows(data.items);
    setSelectedSubmissionIds(data.items.map(item=>item.id));
  }, []);
  const batchHasActive = submissionRows.some(row=>row.processing&&jobIsActive(row.processing));
  useEffect(()=>{
    if(activeView!=='assessment'||!assessment?.id||!batchHasActive)return;
    let cancelled=false;
    const timer=window.setInterval(()=>{void api<{items:typeof submissionRows}>(`/api/v1/assessments/${assessment.id}/submissions`).then(data=>{if(!cancelled)setSubmissionRows(data.items);}).catch(()=>undefined);},4000);
    return ()=>{cancelled=true;window.clearInterval(timer);};
  },[activeView,assessment?.id,batchHasActive]);
  const loadAssessment = useCallback(async (item:Assessment) => {
    setAssessment(item); setSubmission(null); setError(''); setNotice('');
    setDraftDirty(false);
    if (item.revision) {
      const data = await api<{id:string;version:number;status:string;questions:Question[]}>(`/api/v1/assessment-revisions/${item.revision.id}`);
      setRevision(data); setQuestions(data.questions || []);
    } else { setRevision(null); setQuestions([]); }
    await loadSubmissionList(item.id);
    setActiveView('assessment');
  }, [loadSubmissionList]);

  useEffect(() => {
    api<{user:User;csrf_token:string}>('/api/v1/auth/session').then(data => {
      csrfToken = data.csrf_token; setUser(data.user); return loadAssessments();
    }).catch(() => undefined);
  }, [loadAssessments]);
  useEffect(() => {
    if (activeView === 'submission') window.scrollTo({top:0,behavior:'auto'});
  }, [activeView, submission?.id]);
  useEffect(()=>{ if(submission?.identity_status==='pending' && submission.claimed_identity){setStudentId(value=>value||submission.claimed_identity?.external_student_id||'');setStudentName(value=>value||submission.claimed_identity?.display_name||'');} },[submission?.id,submission?.claimed_identity?.external_student_id,submission?.claimed_identity?.display_name]);
  // Each form follows its own source revision; job polls must not erase local edits.
  const selectedReviewKey = JSON.stringify(selectedAnswer?.review ?? null);
  useEffect(() => {
    if (selectedAnswer) setTranscriptText(selectedAnswer.transcript || '');
  }, [selectedAnswer?.id, selectedAnswer?.transcript_revision_id, selectedAnswer?.transcript_stale]);
  useEffect(() => {
    if (selectedAnswer) {
      setSelectedRegions(selectedAnswer.region_ids || []);
      const page=submission?.pages.find(p=>p.regions.some(r=>selectedAnswer.region_ids.includes(r.id)));
      if(page)setSelectedPageId(page.id);
    }
  }, [selectedAnswer?.id, selectedAnswer?.mapping_revision_id]);
  useEffect(() => {
    if (!selectedAnswer) return;
    setReviewCredits(Object.fromEntries((selectedAnswer.review?.criteria || selectedAnswer.proposal?.criteria || selectedAnswer.rubric.map(c => ({criterion_id:c.id,credit:'0'}))).map((c:any) => [c.criterion_id,c.credit])));
    setReviewReason(selectedAnswer.review?.reason || '');
    setOverrideRaw(selectedAnswer.review?.override_raw || '');
    setAnswerStatus(selectedAnswer.review?.status || (selectedAnswer.transcript_status === 'verified_blank' ? 'verified_blank' : 'partially_correct'));
  }, [selectedAnswer?.id, selectedAnswer?.proposal_id, selectedReviewKey]);
  useEffect(() => {
    if (activeView === 'submission' || !job || !['queued','running'].includes(job.status)) return;
    const timer = window.setInterval(() => {
      api<{id:string;status:string;error_code?:string;kind?:string}>(`/api/v1/jobs/${job.id}`).then(async state => {
        setJob(state);
        if (state.status === 'succeeded' || state.status === 'failed' || state.status === 'cancelled') {
          if (questionImportDocId) { const doc = await api<any>(`/api/v1/documents/${questionImportDocId}`).catch(() => null); if (doc?.extracted_text) setQuestionImportText(doc.extracted_text); }
          if (state.kind === 'rubric_generate' && assessment) await loadAssessment(assessment);
          if (submission) await loadSubmission(submission.id);
          if (assessment) await loadSubmissionList(assessment.id);
          if(state.status === 'failed') { setError(jobError(state.error_code)); setNotice(''); }
          else setNotice(state.status === 'succeeded' ? 'Pekerjaan selesai. Periksa hasil sebelum melanjutkan.' : 'Pekerjaan dibatalkan.');
        }
      }).catch(() => undefined);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [activeView, job?.id, job?.status, submission?.id, assessment?.id, questionImportDocId, loadSubmission, loadSubmissionList]);
  useEffect(() => {
    if (activeView !== 'submission' || !submission || !hasActiveSubmissionJobs) return;
    const id = submission.id;
    let cancelled = false;
    let fetching = false;
    const timer = window.setInterval(async () => {
      if (fetching) return;
      fetching = true;
      try {
        const incoming = await api<Submission>(`/api/v1/submissions/${id}`);
        if (!cancelled) {
          setPollingError(false);
          setSubmission(previous => previous?.id === id ? preserveUnchangedAnswers(previous, incoming) : previous);
        }
      } catch {
        if (!cancelled) setPollingError(true);
      } finally { fetching = false; }
    }, 1600);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeView, submission?.id, submission?.document?.id, hasActiveSubmissionJobs]);
  useEffect(() => { api<any>('/api/v1/health/model').then(setModelStatus).catch(() => undefined); }, []);

  async function act<T>(work:()=>Promise<T>, success?:string):Promise<T|undefined> {
    setBusy(true); setError(''); setNotice('');
    try { const result = await work(); if (success) setNotice(success); return result; }
    catch (err) { setError(messageOf(err)); return undefined; }
    finally { setBusy(false); }
  }
  async function login(event:FormEvent) {
    event.preventDefault(); setLoginError('');
    try { const data = await api<{user:User;csrf_token:string}>('/api/v1/auth/login',{method:'POST',body:json({username,password})}); csrfToken=data.csrf_token; setUser(data.user); setPassword(''); await loadAssessments(); }
    catch(err) { setLoginError(messageOf(err)); }
  }
  async function logout() { await act(async()=>{await api('/api/v1/auth/logout',{method:'POST'}); setUser(null); setAssessment(null); setSubmission(null); csrfToken='';},''); }
  async function createAssessment(event:FormEvent) {
    event.preventDefault();
    const form = new FormData(event.currentTarget as HTMLFormElement);
    const data = await act(()=>api<Assessment>('/api/v1/assessments',{method:'POST',body:json({title:form.get('title'),course_label:form.get('course_label'),language:form.get('language')})}),'Asesmen dibuat sebagai draft.');
    if (data) { await loadAssessments(); await loadAssessment({...(data as any),course_label:String(form.get('course_label')||''),language:String(form.get('language')||'id'),revision:(data as any).revision,submission_count:0}); }
  }
  function updateQuestion(index:number, change:Partial<Question>) { setDraftDirty(true); setQuestions(current=>current.map((q,i)=>i===index?{...q,...change,...(change.text !== undefined && change.text !== q.text ? {reference_answer:'',criteria:[]} : {})}:q)); }
  async function saveQuestions() {
    if (!revision) return;
    const result = await act(()=>api<{version:number;questions:Question[]}>(`/api/v1/assessment-revisions/${revision.id}/question-seeds`,{method:'PUT',body:json({expected_version:revision.version,questions:questionSeeds(questions)})}),'Perubahan soal dan rubrik tersimpan.');
    if (result) { setDraftDirty(false); setRevision({...revision,version:result.version}); setQuestions(result.questions); if (assessment) { const next={...assessment,revision:{...assessment.revision!,version:result.version,status:'draft'}}; setAssessment(next); await loadAssessments(); } }
  }
  async function generateRubric() {
    if (!revision || !assessment) return;
    const result = await act(()=>api<{job_id:string;status:string;error_code?:string;revision_version:number}>(`/api/v1/assessment-revisions/${revision.id}/generate-rubric`, {
      method:'POST',body:json({expected_version:revision.version,questions:questionSeeds(questions)})}));
    if(result) {
      setDraftDirty(false);setRevision({...revision,version:result.revision_version});
      setJob({id:result.job_id,status:result.status,error_code:result.error_code,kind:'rubric_generate'});
      if(result.status==='succeeded') { await loadAssessment(assessment);setNotice('Acuan dibuat Qwen. Tinjau lalu klik Setujui acuan.'); }
      else if(result.status==='failed') setError(jobError(result.error_code));
      else setNotice('Qwen sedang menyusun acuan dari soal. Jawaban mahasiswa tidak digunakan.');
    }
  }
  function useExtractedQuestions() {
    try { setQuestions(splitQuestionText(questionImportText).map(q=>({...q,reference_answer:'',alternatives:[],criteria:[]})));setDraftDirty(true);setNotice('Soal dipisahkan menjadi draf. Periksa setiap nomor dan isi bobotnya.'); }
    catch(err) { setError(messageOf(err)); }
  }
  async function confirmIdentity() {
    if(!submission?.document) return;
    await act(async()=>{
      const data=await api<Submission>(`/api/v1/submissions/${submission.id}`);
      await api(`/api/v1/submissions/${submission.id}/confirm-identity`,{method:'POST',body:json({document_id:submission.document!.id,document_hash:submission.document!.sha256,external_student_id:studentId,display_name:studentName,expected_submission_version:data.version})});
      await loadSubmission(submission.id);
    },'Identitas pada PDF telah Anda konfirmasi. Lanjutkan pemetaan jawaban.');
  }
  async function approveRevision() {
    if (!revision || !assessment?.revision) return;
    const result=await act(()=>api<{status:string;version:number}>(`/api/v1/assessment-revisions/${revision.id}/approve`,{method:'POST',body:json({expected_version:revision.version,confirmation:true})}),'Rubrik disahkan dan dikunci.');
    if (result && assessment) { setRevision({...revision,status:result.status,version:result.version}); const updated={...assessment,status:'approved',revision:{...assessment.revision!,status:result.status,version:result.version}};setAssessment(updated);await loadAssessments(); }
  }
  async function createRevision() {
    if (!assessment?.revision) return;
    const created = await act(()=>api<{id:string}>(`/api/v1/assessments/${assessment.id}/revisions`,{method:'POST',body:json({base_revision_id:assessment.revision!.id})}),'Draft revisi dibuat. Snapshot dan submission lama tetap memakai versi rubriknya.');
    if (created && assessment) {
      const refreshed=await api<{items:Assessment[]}>(`/api/v1/assessments`);
      const item=refreshed.items.find(value=>value.id===assessment.id);
      if(item)await loadAssessment(item);
    }
  }
  async function addQuestion() { setDraftDirty(true); setQuestions(current=>[...current,freshQuestion(current.length+1)]); }
  async function importQuestionSource() {
    if (!questionPdf || !revision || !assessment) return;
    const form=new FormData();form.set('file',questionPdf);form.set('assessment_revision_id',revision.id);
    const result=await act(()=>api<any>(`/api/v1/assessments/${assessment.id}/question-imports`,{method:'POST',body:form}),'PDF soal dikirim untuk ekstraksi teks.');
    if (result) { if(result.job?.status==='failed'){setError(jobError(result.job.error_code));setNotice('');} setQuestionImportDocId(result.document_id); setQuestionImportText(result.extracted_text || ''); if (result.job) setJob({id:result.job.id,status:result.job.status,error_code:result.job.error_code}); }
  }
  async function uploadBatch() {
    if (!assessment || batchBusy) return;
    setBatchBusy(true); setError(''); setNotice('');
    const queue = batch.map(item=>({...item}));
    try {
      for (let index=0; index<queue.length; index++) {
        const item=queue[index]; if (item.status==='done'||item.status==='attention') continue;
        item.status='uploading'; item.error=undefined; setBatch([...queue]);
        try {
          if (!item.submissionId) {
            const created=await api<{id:string}>(`/api/v1/assessments/${assessment.id}/submissions/unidentified`,{method:'POST'});
            item.submissionId=created.id;
          }
          const data=new FormData(); data.set('file',item.file); data.set('auto_process','true'); data.set('auto_grade','true');
          const uploaded=await api<{job?:{status:string;error_code?:string}}>(`/api/v1/submissions/${item.submissionId}/documents`,{method:'POST',body:data});
          item.status=uploaded.job?.status==='failed'?'attention':'done';
          if(item.status==='attention')item.error='Berkas diterima, tetapi pemrosesan gagal. Buka lembar untuk memeriksa dan mencoba ulang.';
        } catch (err) {
          item.status='failed'; item.error=messageOf(err);
          if(item.submissionId){
            try { const existing=await api<{document:{id:string}|null}>(`/api/v1/submissions/${item.submissionId}`);
              if(existing.document){item.status='attention';item.error='Periksa lembar yang sudah diterima sebelum mengulang.';}
            } catch { item.status='attention';item.error='Status belum diketahui. Periksa lembar sebelum mengulang.'; }
          }
        }
        setBatch([...queue]);
      }
      await loadSubmissionList(assessment.id);
      setNotice('Unggahan selesai. Setiap PDF diproses dalam antrean tersendiri; periksa identitas dan hasilnya.');
    } finally { setBatchBusy(false); }
  }
  async function createSubmission() {
    if (!assessment || !studentId.trim() || !studentName.trim()) return;
    const result=await act(()=>api<{id:string}>(`/api/v1/assessments/${assessment.id}/submissions`,{method:'POST',body:json({external_student_id:studentId,display_name:studentName,attempt_no:1})}),'Submission dibuat.');
    if (result) { setStudentFile(null); await loadSubmission(result.id); setActiveView('submission'); }
  }
  async function uploadStudentFile() {
    if (!submission || !studentFile) return;
    setPendingAction({kind:'upload'});
    try {
    const uploaded=await act(async()=>{
      const data=new FormData();data.set('file',studentFile);data.set('auto_process',String(autoProcess));
      const result=await api<any>(`/api/v1/submissions/${submission.id}/documents`,{method:'POST',body:data});
      await loadSubmission(submission.id);
      if (assessment) await loadSubmissionList(assessment.id);
      if(result.job) setJob({id:result.job.id,status:result.job.status,error_code:result.job.error_code});
      return result;
    },'PDF diunggah. Tunggu halaman tampil, periksa identitas pada gambar, lalu konfirmasikan.');
    if (uploaded) { setStudentFile(null); setShowReplacement(false); if(uploaded.job?.status==='failed'){setError(jobError(uploaded.job.error_code));setNotice('');} }
    } finally { setPendingAction(null); }
  }
  async function openSubmission(id:string) { if (assessment) { await loadSubmission(id);setActiveView('submission');setError(''); } }
  async function createRegion(event:PointerEvent<HTMLDivElement>) {
    if (event.type === 'pointerdown') {
      if (!imageBox.current) return;
      const rect=imageBox.current.getBoundingClientRect();
      pointerStart.current=[Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId); setDrawing([pointerStart.current[0],pointerStart.current[1],pointerStart.current[0],pointerStart.current[1]]);
      return;
    }
    if (event.type === 'pointermove' && pointerStart.current && imageBox.current) { const r=imageBox.current.getBoundingClientRect();setDrawing([pointerStart.current[0],pointerStart.current[1],Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))]);return; }
    if (event.type !== 'pointerup' || !pointerStart.current || !selectedPage) return;
    setDrawing(null);
    const rect=imageBox.current?.getBoundingClientRect(); if(!rect)return;
    const endPoint:[number,number]=[Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
    const start=pointerStart.current;pointerStart.current=null;
    const left=Math.min(start[0],endPoint[0]),right=Math.max(start[0],endPoint[0]),top=Math.min(start[1],endPoint[1]),bottom=Math.max(start[1],endPoint[1]);
    if(right-left<.01||bottom-top<.01)return;
    const region=await act(()=>api<any>(`/api/v1/page-image-revisions/${selectedPage.page_image_revision_id}/regions`,{method:'POST',body:json({polygon:[[left,top],[right,top],[right,bottom],[left,bottom]],region_type:'answer'})}),'Area jawaban ditambahkan.');
    if(region&&submission){await loadSubmission(submission.id);setSelectedRegions(current=>[...current,region.id]);}
  }
  async function rotatePage() {
    if(!submission?.document?.layout_revision_id||!selectedPage)return;
    const result=await act(()=>api<any>(`/api/v1/page-image-revisions/${selectedPage.page_image_revision_id}/rotate`,{method:'POST',body:json({degrees_clockwise:90,expected_layout_revision_id:submission.document!.layout_revision_id})}),'Halaman diputar. Mapping lama memerlukan revisi.');
    if(result&&submission)await loadSubmission(submission.id);
  }
  function toggleRegion(id:string) { setSelectedRegions(current=>current.includes(id)?current.filter(x=>x!==id):[...current,id]); }
  async function mapAnswer(target:Answer|null=selectedAnswer,regionIds:string[]=selectedRegions) {
    if(!submission||!target)return;
    setPendingAction({kind:'mapping',questionId:target.question_id});
    try {
      const result=await act(()=>api<any>(`/api/v1/answers/${target.id}/mapping-revisions`,{method:'POST',body:json({region_ids:regionIds,expected_transcript_revision:target.transcript_revision_no,expected_mapping_revision_id:target.mapping_revision_id})}),regionIds.length?'Area dipetakan. Periksa teks OCR pada nomor tujuan.':'Pemetaan dikosongkan. Area tetap tersimpan untuk dipetakan ulang.');
      if(result){setSelectedQuestion(target.question_id);await loadSubmission(submission.id);}
    } finally {setPendingAction(null);}
  }
  async function startAutoMapping() {
    if(!submission?.document?.layout_revision_id)return;
    setPendingAction({kind:'auto'});
    try {
      const result=await act(()=>api<PipelineJob>(`/api/v1/submissions/${submission.id}/auto-map`,{method:'POST',body:json({expected_document_id:submission.document!.id,expected_layout_revision_id:submission.document!.layout_revision_id})}),'OCR dan pemetaan otomatis dijadwalkan.');
      if(result)await loadSubmission(submission.id);
    } finally {setPendingAction(null);}
  }
  async function confirmAutoMapping() {
    if(!submission?.document?.layout_revision_id)return;
    await act(async()=>{
      await api(`/api/v1/submissions/${submission.id}/confirm-mapping`,{method:'POST',body:json({expected_layout_revision_id:submission.document!.layout_revision_id,expected_submission_version:submission.version,mapping_revision_ids:submission.answers.filter(a=>a.mapping_status==='auto_mapped').map(a=>a.mapping_revision_id)})});
      await loadSubmission(submission.id);
    },'Pemetaan otomatis sudah Anda tinjau dan setujui.');
  }
  function selectDraftRegion(id:string) {
    const page=submission?.pages.find(p=>p.regions.some(r=>r.id===id));
    if(page)setSelectedPageId(page.id);
    setSelectedRegions([id]);
    document.getElementById('answer-document')?.scrollIntoView({behavior:'smooth',block:'start'});
  }
  async function excludeDraftRegion(id:string,excluded:boolean,reason:string) {
    if(!submission?.document?.layout_revision_id)return;
    await act(async()=>{
      await api(`/api/v1/regions/${id}/mapping-exclusion`,{method:'POST',body:json({excluded,reason,expected_layout_revision_id:submission.document!.layout_revision_id})});
      await loadSubmission(submission.id);
    },excluded?'Area dikecualikan dengan alasan Anda.':'Area dikembalikan untuk dipetakan.');
  }
  async function saveTranscript(status='transcribed') {
    if(!submission||!selectedAnswer)return;
    const result=await act(()=>api<any>(`/api/v1/submissions/${submission.id}/answers/${selectedAnswer.question_id}/transcription-revisions`,{method:'POST',body:json({literal_text:status==='verified_blank'?'':transcriptText,status,flags:[],expected_revision:selectedAnswer.transcript_revision_no,reason:status==='verified_blank'?reviewReason:null})}),status==='verified_blank'?'Jawaban ditandai kosong setelah verifikasi.':'Transkripsi literal tersimpan.');
    if(result)await loadSubmission(submission.id);
  }
  async function queueAnswerTask(kind:'transcribe'|'propose') {
    if(!submission||!selectedAnswer)return;
    setPendingAction({kind,questionId:selectedAnswer.question_id});
    try {
      const result=await act(()=>api<any>(`/api/v1/submissions/${submission.id}/answers/${selectedAnswer.question_id}/${kind}`,{method:'POST'}),kind==='transcribe'?'Transkripsi lokal dimasukkan antrean.':'Usulan penilaian dimasukkan antrean.');
      if(result?.job_id){setJob({id:result.job_id,status:result.status,error_code:result.error_code,kind:kind==='transcribe'?'transcribe_answer':'grade_answer'});await loadSubmission(submission.id);if(result.status==='failed'){setError(jobError(result.error_code));setNotice('');}}
    } finally { setPendingAction(null); }
  }
  function effectiveCriteria():{criterion_id:string;credit:string;evidence_refs:any[];rationale:string;source:string}[] {
    if(!selectedAnswer)return[];
    return selectedAnswer.rubric.map(criterion=>{
      const proposal=selectedAnswer.proposal?.criteria.find(item=>item.criterion_id===criterion.id);
      const credit=reviewCredits[criterion.id]??proposal?.credit??'0';
      const segment=selectedAnswer.segments.find(item=>item.text.length>0);
      const existing=proposal?.evidence_refs||[];
      const evidence=Number(credit)>0?(existing.length?existing:segment&&segment.region_id?[{segment_id:segment.segment_id,start:0,end:segment.text.length,region_id:segment.region_id}]:[]):[];
      const acceptedAsProposed=Boolean(proposal&&credit===proposal.credit&&JSON.stringify(evidence)===JSON.stringify(proposal.evidence_refs));
      return {criterion_id:criterion.id,credit,evidence_refs:evidence,rationale:proposal?.rationale||'Keputusan ditinjau oleh dosen.',source:acceptedAsProposed?'model_accepted':'human'};
    });
  }
  async function saveReview() {
    if(!submission||!selectedAnswer)return;
    const criteria=answerStatus==='verified_blank'&&selectedAnswer
      ? selectedAnswer.rubric.map(criterion=>({criterion_id:criterion.id,credit:'0',evidence_refs:[],rationale:'Dosen memastikan area jawaban benar-benar kosong.',source:'human'}))
      : effectiveCriteria();
    const raw=overrideRaw.trim();
    const body={expected_review_id:submission.review_revision?.status==='draft'?submission.review_revision.id:null,expected_version:submission.review_revision?.status==='draft'?submission.review_revision.version:1,
      answer_status:answerStatus,accepted_criteria:raw?null:criteria,override_raw:raw||null,reason:reviewReason||null};
    const result=await act(()=>api<any>(`/api/v1/submissions/${submission.id}/review/${selectedAnswer.question_id}`,{method:'PUT',body:json(body)}),'Keputusan review disimpan sebagai revisi draft.');
    if(result)await loadSubmission(submission.id);
  }
  async function finalize() {
    if(!submission?.review_revision)return;
    const result=await act(()=>api<any>(`/api/v1/submissions/${submission.id}/finalize`,{method:'POST',body:json({expected_review_id:submission.review_revision!.id,expected_version:submission.review_revision!.version})}),'Nilai disahkan ke snapshot immutable.');
    if(result&&submission)await loadSubmission(submission.id);
  }
  async function exportGrades(mode:'draft'|'final') {
    if(!assessment)return;
    const ids=selectedSubmissionIds;
    const result=await act(()=>api<any>(`/api/v1/assessments/${assessment.id}/exports`,{method:'POST',body:json({mode,submission_ids:ids})}),`Snapshot ekspor ${mode} dibuat.`);
    if(result) { const a=document.createElement('a');a.href=result.download_url;a.download=result.filename;document.body.appendChild(a);a.click();a.remove(); }
  }
  async function cancelActiveJob(target?:PipelineJob) {
    const chosen=target??job;
    if(!chosen)return;
    const result=await act(()=>api<any>(`/api/v1/jobs/${chosen.id}/cancel`,{method:'POST'}),'Permintaan pembatalan pekerjaan dikirim.');
    if(result){setJob({id:chosen.id,status:result.status,kind:chosen.kind});if(submission)await loadSubmission(submission.id);}
  }
  async function retryFailedJob(target?:PipelineJob) {
    const chosen=target??job;
    if(!chosen)return;
    if(chosen.kind==='analyze_answers'){await startAutoMapping();return;}
    const attempt=chosen.attempt||1;
    const result=await act(()=>api<any>(`/api/v1/jobs/${chosen.id}/retry`,{method:'POST',body:json({expected_attempt:attempt,reason:'Percobaan ulang diminta dosen dari ruang review.'})}),'Pekerjaan dijadwalkan ulang.');
    if(result){setJob({id:result.id,status:result.status,error_code:result.error_code,attempt:result.attempt,kind:chosen.kind});if(submission)await loadSubmission(submission.id);}
  }

  const activeTranscriber = modelStatus?.transcriber;
  const transcriberLabel = activeTranscriber?.backend === 'trocr' ? 'TrOCR eksperimen' : 'Qwen';
  const transcriptionReady = activeTranscriber?.available ?? modelStatus?.available ?? false;

  if(!user) return <main className="login-shell"><div className="login-card"><div className="brand-mark large">a.</div><p className="eyebrow">ASDOS · RUANG DOSEN</p><h1>Masuk untuk mulai mengoreksi.</h1><p className="muted">Ruang kerja lokal untuk meninjau tulisan, bukti visual, dan rubrik.</p><form onSubmit={login} className="stack"><label>Nama pengguna<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Kata sandi<input type="password" required autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>{loginError&&<p className="error-message">{loginError}</p>}<button className="button primary wide">Masuk <Icon name="arrow"/></button></form><p className="tiny muted">Akun awal dibuat oleh administrator deployment. Kata sandi tidak disediakan melalui UI.</p></div></main>;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand-lockup"><div className="brand-mark">a.</div><div><strong>asdos</strong><span>assessment desk</span></div></div>
      <div className="side-caption">WORKSPACE</div>
      <button className={`nav-link ${activeView==='overview'?'active':''}`} onClick={()=>{setActiveView('overview');setSubmission(null);}}><Icon name="grid"/> Ikhtisar</button>
      {assessment&&<button className={`nav-link ${activeView==='assessment'?'active':''}`} onClick={()=>setActiveView('assessment')}><Icon name="book"/> {assessment.title}</button>}
      <div className="sidebar-bottom"><div className="privacy-chip"><span className="status-dot green"/><div><b>Pemrosesan lokal</b><small>Data tetap di ruang kerja ini</small></div></div><div className="user-card"><div className="avatar">{user.display_name.slice(0,1).toUpperCase()}</div><div className="user-meta"><b>{user.display_name}</b><small>Dosen · pemilik</small></div><button className="icon-button" onClick={logout} aria-label="Keluar">↗</button></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs"><span>Ruang kerja</span>{assessment&&<><span className="crumb-sep">/</span><b>{assessment.title}</b></>}</div><div className="topbar-right"><div className={`model-pill ${transcriptionReady?'ready':''}`}><span className="status-dot"/><span>{transcriptionReady?`${transcriberLabel} siap dimuat`:`${transcriberLabel} belum siap`}</span></div><button className="avatar small" title={user.username}>{user.display_name.slice(0,1).toUpperCase()}</button></div></header>
      <div className="page-content">
        {(error||notice)&&<div className={`alert ${error?'alert-error':'alert-success'}`} role="status"><span>{error||notice}</span><button onClick={()=>{setError('');setNotice('');}} aria-label="Tutup">×</button></div>}
        {job&&activeView!=='submission'&&<div role="status" className={`job-banner ${job.status==='failed'?'failed':job.status==='succeeded'?'finished':''}`}>{jobIsActive(job)?<Spinner/>:<span className="status-dot"/>}<div><b>{job.kind||'Pekerjaan'} · {job.status}</b><small>{job.error_code?jobError(job.error_code):'Pekerjaan diproses lokal; halaman akan diperbarui otomatis.'}</small></div><div className="job-actions">{['queued','running'].includes(job.status)&&<button className="quiet-button" onClick={()=>void cancelActiveJob()}>Batalkan</button>}{job.status==='failed'&&(job.attempt||1)<3&&<button className="text-button" onClick={()=>void retryFailedJob()}>Coba lagi</button>}</div></div>}
        {activeView==='overview'&&<section className="overview-page">
          <div className="welcome-row"><div><p className="eyebrow">DASHBOARD DOSEN</p><h1>Selamat bekerja, {user.display_name.split(' ')[0]}.</h1><p className="muted">Susun asesmen, tinjau jawaban, lalu sahkan nilai.</p></div><button className="button primary" onClick={()=>document.getElementById('new-assessment')?.scrollIntoView({behavior:'smooth'})}><Icon name="plus"/> Asesmen baru</button></div>
          <div className="stat-grid"><div className="stat-card"><span className="stat-icon"><Icon name="book"/></span><div><small>ASESMEN</small><b>{assessments.length}</b></div><span className="stat-note">di ruang kerja</span></div><div className="stat-card"><span className="stat-icon amber"><Icon name="file"/></span><div><small>LEMBAR JAWABAN</small><b>{assessments.reduce((n,a)=>n+a.submission_count,0)}</b></div><span className="stat-note">seluruh asesmen</span></div><div className="stat-card"><span className="stat-icon green"><Icon name="check"/></span><div><small>MODEL LOKAL</small><b>{transcriptionReady?'Siap':'Manual'}</b></div><span className="stat-note">transkripsi: {transcriberLabel}</span></div></div>
          <div className="section-heading"><div><p className="eyebrow">RUANG KERJA</p><h2>Asesmen Anda</h2></div><button className="text-button" onClick={loadAssessments}>Muat ulang <Icon name="rotate"/></button></div>
          {assessments.length===0?<div className="empty-card"><div className="empty-art"><Icon name="book"/></div><h3>Belum ada asesmen</h3><p>Buat asesmen pertama, susun rubrik, lalu masukkan lembar jawaban.</p></div>:<div className="assessment-grid">{assessments.map(item=><button key={item.id} className="assessment-card" onClick={()=>loadAssessment(item)}><div className="assessment-card-top"><div className="course-avatar">{item.title.slice(0,1).toUpperCase()}</div><span className={`tag ${item.status==='approved'?'tag-green':'tag-amber'}`}>{item.status==='approved'?'Disahkan':'Draft'}</span></div><h3>{item.title}</h3><p>{item.course_label||'Mata kuliah belum diisi'}</p><div className="card-meta"><span>{item.revision?`Versi ${item.revision.sequence}`:'Belum ada versi'}</span><span>{item.submission_count} lembar</span></div><span className="card-arrow"><Icon name="arrow"/></span></button>)}</div>}
          <div className="create-panel" id="new-assessment"><div><p className="eyebrow">MULAI BARU</p><h2>Buat asesmen</h2><p className="muted">Unggah atau tulis soal, isi bobot, lalu biarkan Qwen menyusun acuan penilaian.</p></div><form className="create-form" onSubmit={createAssessment}><label>Nama asesmen<input name="title" required placeholder="Contoh: UTS Biologi Sel"/></label><div className="form-row"><label>Mata kuliah<input name="course_label" placeholder="Biologi Sel · 2026/2027"/></label><label>Bahasa<select name="language"><option value="id">Indonesia</option><option value="en">English</option></select></label></div><button className="button primary" disabled={busy}><Icon name="plus"/> Buat draft</button></form></div>
        </section>}

        {activeView==='assessment'&&assessment&&<section className="assessment-page">
          {modelStatus&&!modelStatus.available&&<div className="alert alert-warning" role="status"><b>Qwen belum siap digunakan.</b> Lokalisasi otomatis, pembuatan acuan, dan usulan penilaian memerlukan Qwen. Transkripsi terpisah memakai {transcriberLabel}{transcriptionReady?' yang tersedia':' yang belum siap'}. <button className="text-button" onClick={()=>void api<ModelHealth>('/api/v1/health/model').then(setModelStatus)}>Periksa kesiapan model</button></div>}
          {activeTranscriber?.backend==='trocr'&&<div className="alert alert-warning" role="status"><b>TrOCR eksperimental aktif.</b> Checkpoint ini dilatih pada label AI tanpa uji gold manusia atau data tertahan. Periksa seluruh teks terhadap scan; usulan penilaian tetap diblokir sampai transkripsi dikoreksi lalu disimpan.</div>}
          <div className="page-title-row"><div><p className="eyebrow">ASESMEN · VERSI {assessment.revision?.sequence||1}</p><h1>{assessment.title}</h1><p className="muted">{assessment.course_label||'Mata kuliah belum diisi'} <span className="dot-sep">·</span> Bahasa {assessment.language==='id'?'Indonesia':'Inggris'}</p></div><div className="title-actions">{revision?.status==='approved'&&<button className="button secondary" onClick={createRevision} disabled={busy}>Buat revisi rubrik</button>}<span className={`tag ${revision?.status==='approved'?'tag-green':'tag-amber'}`}>{revision?.status==='approved'?'Rubrik disahkan':'Draft — belum disahkan'}</span></div></div>
          <div className="tabs"><button className="selected">1. Soal dan bobot</button><button onClick={()=>document.getElementById('submissions')?.scrollIntoView({behavior:'smooth'})}>Lembar jawaban <span>{submissionRows.length}</span></button></div>
          <div className="import-source"><div className="import-icon"><Icon name="file"/></div><div className="import-copy"><b>Impor teks soal dari PDF</b><small>Ekstraksi teks lokal membantu mengisi draf. Periksa kembali setiap soal sebelum rubrik disahkan.</small></div><input type="file" accept="application/pdf" onChange={e=>setQuestionPdf(e.target.files?.[0]||null)} aria-label="PDF soal"/><button className="button secondary" disabled={!questionPdf||revision?.status!=='draft'||busy} onClick={importQuestionSource}><Icon name="upload"/> Impor PDF</button></div>{questionImportText&&<div className="extracted-source"><b>Teks hasil ekstraksi — draf, perlu diverifikasi</b><textarea value={questionImportText} onChange={e=>setQuestionImportText(e.target.value)} aria-label="Teks hasil ekstraksi PDF soal"/><button className="button secondary" disabled={busy||revision?.status!=='draft'} onClick={useExtractedQuestions}>Gunakan sebagai daftar soal</button></div>}
          <ol className="workflow-steps" aria-label="Tahapan koreksi"><li>Soal</li><li>Bobot</li><li>Acuan dari Qwen</li><li>Jawaban mahasiswa</li><li>Review dan Excel</li></ol>
          <p className="muted">Anda cukup memasukkan soal dan bobot. Qwen membuat jawaban acuan dan kriteria; Anda cukup meninjaunya sebelum digunakan.</p>
          <div className="question-list">{questions.map((question,index)=><article className="question-card" key={question.stable_question_id}>
            <div className="question-card-head"><div className="question-number">{question.label}</div><div className="question-heading"><strong>Soal {question.label}</strong></div><label className="weight-field">Bobot<input type="number" min="0.01" step="0.01" disabled={revision?.status==='approved'||generationBusy} value={question.weight} onChange={e=>updateQuestion(index,{weight:e.target.value})}/></label></div>
            <div className="question-content"><label>Pertanyaan<textarea disabled={revision?.status==='approved'||generationBusy} value={question.text} onChange={e=>updateQuestion(index,{text:e.target.value})} placeholder="Tulis soal atau gunakan hasil impor PDF."/></label>
            {question.reference_answer&&question.criteria.length>0?<details className="generated-reference"><summary>Tinjau acuan penilaian</summary><p className="warning-note">Periksa ketepatan acuan. Acuan otomatis bukan kunci resmi; nilai akhir tetap memerlukan review Anda.</p><p className="reference-answer">{question.reference_answer}</p><ul>{question.criteria.map(c=><li key={c.id}><b>{c.description}</b><small> Maksimum {c.max_points} poin · {c.anchors['1']}</small></li>)}</ul></details>:<p className="muted">Acuan belum tersedia. Isi bobot, lalu pilih Buat acuan otomatis.</p>}</div>
          </article>)}<button className="add-question" disabled={revision?.status==='approved'||generationBusy||busy} onClick={addQuestion}><Icon name="plus"/> Tambahkan soal</button></div>
          <div className="action-bar"><div><span className={`status-dot ${revision?.status==='approved'?'green':'amber'}`}/><span>{revision?.status==='approved'?'Rubrik terkunci pada versi ini':'Simpan soal dan bobot, buat acuan otomatis, lalu tinjau hasilnya'}</span></div><div>{revision?.status==='draft'?<><button className="button secondary" disabled={busy||generationBusy||!questions.length} onClick={saveQuestions}>Simpan soal dan bobot</button><button className="button secondary" disabled={busy||!questions.length||questions.some(q=>!q.text.trim())||Boolean(job&&['queued','running'].includes(job.status))} onClick={generateRubric}><Icon name="spark"/> Buat acuan otomatis</button><button className="button primary" disabled={busy||generationBusy||draftDirty||!questions.length||questions.some(q=>!q.reference_answer||!q.criteria.length)} onClick={approveRevision}><Icon name="check"/> Setujui acuan</button></>:<button className="button primary" disabled={busy} onClick={()=>document.getElementById('student-entry')?.scrollIntoView({behavior:'smooth'})}>Mulai unggah jawaban <Icon name="arrow"/></button>}</div></div>
          <div className="submission-create-panel batch-panel"><div className="section-heading"><div><p className="eyebrow">UNGGAH BANYAK PDF</p><h2>Proses satu kelas</h2><p className="muted">Pilih hingga 100 PDF. Jangan tutup halaman saat mengunggah; setelah selesai, pemrosesan berlanjut di antrean lokal. Satu PDF untuk satu mahasiswa; setiap berkas menjadi lembar terpisah. Periksa identitas dan pemetaan; usulan nilai akan disiapkan otomatis setelah konfirmasi, lalu tinjau sebelum mengesahkan.</p></div></div>
            <label className="batch-picker">Pilih PDF jawaban<input type="file" multiple accept="application/pdf,.pdf" disabled={batchBusy} onChange={e=>{const files=Array.from(e.target.files||[]);if(files.length>100){setError('Pilih paling banyak 100 PDF per unggahan.');return;}setBatch(files.map(file=>({file,status:'waiting'})));}}/></label>
            {batch.length>0&&<div className="batch-summary" role="status"><b>{batch.filter(item=>item.status==='done'||item.status==='attention').length} dari {batch.length} PDF diunggah</b><span>Unggahan selesai berarti berkas masuk antrean; OCR mungkin masih berjalan.</span><ul>{batch.map((item,index)=><li key={index}>{item.file.name} · {item.status==='done'?'Masuk antrean':(item.status==='failed'||item.status==='attention')?`${item.status==='failed'?'Gagal':'Perlu diperiksa'}: ${item.error}`:item.status==='uploading'?'Mengunggah…':'Menunggu'}</li>)}</ul></div>}
            <button className="button primary" disabled={!batch.length||batchBusy||assessment.revision?.status!=='approved'||batch.every(item=>item.status==='done'||item.status==='attention')} onClick={()=>void uploadBatch()}>{batchBusy?<><Spinner/> Mengunggah PDF…</>:batch.some(item=>item.status==='failed')?'Coba ulang yang gagal':'Unggah dan proses semua PDF'}</button></div>
          <div id="student-entry" className="submission-create-panel"><div className="section-heading"><div><p className="eyebrow">ALUR PENILAIAN</p><h2>Tambahkan lembar jawaban</h2><p className="muted">Satu PDF untuk satu mahasiswa. Identitas dikonfirmasi setelah berkas dimuat.</p></div></div><div className="student-form"><label>NIM<input value={studentId} onChange={e=>setStudentId(e.target.value)} placeholder="Contoh: 0012345678"/></label><label>Nama mahasiswa<input value={studentName} onChange={e=>setStudentName(e.target.value)} placeholder="Nama sesuai lembar jawaban"/></label><button className="button primary" disabled={!studentId.trim()||!studentName.trim()||assessment.revision?.status!=='approved'||busy} onClick={createSubmission}><Icon name="plus"/> Buat lembar</button></div>
          </div>
          <div id="submissions" className="section-heading list-heading"><div><p className="eyebrow">KOREKSI</p><h2>Lembar jawaban <span className="count-badge">{submissionRows.length}</span></h2><small className="muted">{selectedSubmissionIds.length} dipilih untuk ekspor</small></div><div className="export-actions"><button className="button secondary" disabled={!selectedSubmissionIds.length||busy} onClick={()=>exportGrades('draft')}><Icon name="download"/> Ekspor draft</button><button className="button primary" disabled={!selectedSubmissionIds.length||busy} onClick={()=>exportGrades('final')}><Icon name="check"/> Ekspor final</button></div></div>
          <div className="submission-table-wrap"><table className="submission-table"><thead><tr><th><input type="checkbox" aria-label="Pilih semua submission" checked={submissionRows.length>0&&selectedSubmissionIds.length===submissionRows.length} onChange={e=>setSelectedSubmissionIds(e.target.checked?submissionRows.map(row=>row.id):[])}/></th><th>NIM</th><th>Nama mahasiswa</th><th>PDF</th><th>Status</th><th>Nilai akhir</th><th/></tr></thead><tbody>{submissionRows.map(row=><tr key={row.id}><td><input type="checkbox" aria-label={`Pilih ${row.display_name||row.id}`} checked={selectedSubmissionIds.includes(row.id)} onChange={e=>setSelectedSubmissionIds(current=>e.target.checked?[...current,row.id]:current.filter(id=>id!==row.id))}/></td><td className="mono">{row.external_student_id||(row.identity_candidate?.student_id?<span>{row.identity_candidate.student_id} <small>(usulan)</small></span>:<span className="muted">Belum dikonfirmasi</span>)}</td><td>{row.identity_status!=='confirmed'&&row.identity_candidate?.name?`${row.identity_candidate.name} (usulan)`:row.display_name}</td><td>{row.document_filename||'Belum ada berkas'} · {row.processing?.status==='queued'?'Dalam antrean':row.processing?.status==='running'?'Sedang diproses':row.processing?.status==='failed'?'Proses gagal':row.document_status==='valid'?'Siap ditinjau':row.document_status==='failed'?'Gagal':row.document_status}</td><td><span className={`tag ${row.final_score!==null?'tag-green':'tag-amber'}`}>{row.final_score!==null?'Final':'Perlu tinjauan'}</span>{Boolean(row.grade_progress?.scheduled)&&<small> · Job usulan selesai {row.grade_progress!.succeeded}/{row.grade_progress!.total}{row.grade_progress!.failed?` · ${row.grade_progress!.failed} gagal`:''}</small>}</td><td className="score-cell">{row.final_score??'—'}</td><td><button className="text-button" onClick={()=>openSubmission(row.id)}>Buka <Icon name="arrow"/></button></td></tr>)}</tbody></table>{submissionRows.length===0&&<div className="table-empty">Belum ada lembar jawaban untuk asesmen ini.</div>}</div>
        </section>}

        {activeView==='submission'&&submission&&assessment&&<section className="grading-page">
          <div className="page-title-row"><div><button className="back-link" onClick={()=>setActiveView('assessment')}>← Kembali ke asesmen</button><p className="eyebrow">TINJAUAN DOSEN · {assessment.title}</p><h1>{submission.display_name||'Mahasiswa belum dikonfirmasi'}</h1><p className="muted">NIM {submission.external_student_id||'belum dikonfirmasi'} <span className="dot-sep">·</span> Berkas {submission.document?.status||'belum diunggah'}</p></div><div className="score-summary"><span className="eyebrow">NILAI FINAL</span><b>{submission.final_snapshot?.score??'—'}</b><small>{submission.final_snapshot?'Sudah disahkan':'Belum disahkan'}</small></div></div>
          <SubmissionProgress document={submission.document} identityStatus={submission.identity_status}
            answers={submission.answers} jobs={pipelineJobs} pending={pendingAction} pollingError={pollingError}
            selectedQuestion={selectedAnswer?.question_id??''} onSelect={setSelectedQuestion} unassignedCount={submission.unassigned_region_ids?.length??0}
            onRetry={target=>void retryFailedJob(target)} onCancel={target=>void cancelActiveJob(target)}/>
          {submission.document&&submission.identity_status!=='confirmed'&&<div className="identity-check"><h2>Periksa identitas pada PDF</h2><p>Nama dan NIM yang terbaca adalah usulan, bisa keliru. Bandingkan dengan halaman yang ditampilkan. Konfirmasi setelah render selesai.</p><div className="form-row"><label>NIM<input value={studentId} onChange={e=>setStudentId(e.target.value)}/></label><label>Nama mahasiswa<input value={studentName} onChange={e=>setStudentName(e.target.value)}/></label></div><button className="button primary" disabled={busy||!submission.pages.length||submission.document.status!=='valid'||!studentId.trim()||!studentName.trim()} onClick={confirmIdentity}>Identitas pada PDF sudah sesuai</button></div>}
          {submission.document?.status==='valid'&&!autoAnalysisBusy&&<AutoMappingReview
            regions={submission.pages.flatMap(p=>p.regions)} unassignedIds={submission.unassigned_region_ids??[]}
            autoCount={submission.answers.filter(a=>a.mapping_status==='auto_mapped').length}
            identityConfirmed={submission.identity_status==='confirmed'} busy={busy}
            analysisDone={Boolean(submission.document.analysis_result?.job_id)}
            questions={submission.answers.map(a=>({question_id:a.question_id,label:a.label}))}
            onAssign={(id,qid)=>{const answer=submission.answers.find(a=>a.question_id===qid);if(answer)void mapAnswer(answer,[...answer.region_ids,id]);}}
            canStart={!submission.document.analysis_result?.job_id&&!pipelineJobs.some(j=>j.kind==='analyze_answers'&&jobIsActive(j))&&!submission.answers.some(a=>a.mapping_revision_id)}
            onStart={()=>void startAutoMapping()} onConfirm={()=>void confirmAutoMapping()} onSelect={selectDraftRegion}
            onExclude={(id,excluded,reason)=>void excludeDraftRegion(id,excluded,reason)}/>}
          {submission.document&&<button className="quiet-button" disabled={busy} onClick={()=>setShowReplacement(value=>!value)}>{showReplacement?'Batal mengganti PDF':'Ganti PDF jawaban'}</button>}
          {(!submission.document||showReplacement)&&<div className="submission-upload-panel"><div><p className="eyebrow">BERKAS JAWABAN</p><h2>{showReplacement?'Ganti PDF dan konfirmasi ulang identitas':'Unggah lembar jawaban'}</h2><p className="muted">Satu PDF untuk {submission.external_student_id||studentId||'mahasiswa ini'} · {submission.display_name||studentName||'nama belum diisi'}. Maksimal 50 MiB dan 100 halaman.</p></div><label className="auto-process-toggle"><input type="checkbox" checked={autoProcess} disabled={busy} onChange={e=>setAutoProcess(e.target.checked)}/> Baca dan petakan jawaban otomatis setelah upload</label><div className="upload-inline"><label className="file-drop"><Icon name="upload"/><span><b>Pilih PDF hasil scan</b><small>{studentFile?.name||'Pilih satu berkas PDF'}</small></span><input type="file" accept="application/pdf" onChange={e=>setStudentFile(e.target.files?.[0]||null)}/></label><button className="button primary" disabled={!studentFile||busy} onClick={uploadStudentFile}>{pendingAction?.kind==='upload'?<><Spinner/> Mengunggah…</>:<>Unggah PDF <Icon name="arrow"/></>}</button></div></div>}
          <div className="grading-layout" id="answer-document"><div className="visual-column"><div className="panel-head"><div><p className="eyebrow">DOKUMEN ASLI</p><b>Halaman jawaban</b></div><div className="panel-actions"><button className="icon-button" title="Putar halaman 90°" onClick={rotatePage}><Icon name="rotate"/></button><span className="page-counter">{selectedPage?`Halaman ${(selectedPage.page_index||0)+1} dari ${submission.document?.page_count||1}`:'Menunggu render'}</span></div></div><div className="document-stage">{selectedPage?<div className="annotatable-image" ref={imageBox} onPointerDown={e=>void createRegion(e)} onPointerUp={e=>void createRegion(e)} onPointerMove={e=>void createRegion(e)} onPointerCancel={()=>{pointerStart.current=null;setDrawing(null);}}><img src={selectedPage.image_url} alt={`Halaman ${(selectedPage.page_index||0)+1} dari lembar jawaban`}/><RegionOverlay regions={selectedPage.regions} selected={selectedRegions} answers={submission.answers} onToggle={toggleRegion}/>{drawing&&<div className="region-drawing" style={{left:`${Math.min(drawing[0],drawing[2])*100}%`,top:`${Math.min(drawing[1],drawing[3])*100}%`,width:`${Math.abs(drawing[2]-drawing[0])*100}%`,height:`${Math.abs(drawing[3]-drawing[1])*100}%`}}/>}<div className="drawing-hint">Tarik area pada halaman untuk menandai jawaban</div></div>:<div className="document-empty">{submission.document&&hasActiveSubmissionJobs?<Spinner/>:<Icon name="file"/>}<b>{submission.document?'Halaman sedang diproses':'Unggah PDF untuk melihat halaman'}</b><span>{submission.document?`Status: ${submission.document.status}`:'PDF asli tetap tersimpan dan tidak diubah.'}</span></div>}</div><div className="region-tools"><div><b>Area jawaban</b><small>{selectedRegions.length} region dipilih · Klik kotak pada halaman untuk memilih</small></div><button className="button secondary compact" disabled={(!selectedRegions.length&&!selectedAnswer?.mapping_revision_id)||!selectedAnswer||busy||autoAnalysisBusy||submission.identity_status!=='confirmed'} onClick={()=>void mapAnswer()}>{selectedRegions.length?'Petakan ke':'Kosongkan pemetaan'} {selectedAnswer?.label||'soal'}</button></div>{selectedAnswer&&selectedAnswer.region_ids.length>0&&<button className="text-button unmap-button" disabled={busy||autoAnalysisBusy||submission.identity_status!=='confirmed'} onClick={()=>void mapAnswer(selectedAnswer,[])}>Hapus pemetaan soal {selectedAnswer.label}</button>}{selectedPage&&<div className="page-thumbnails">{submission.pages.map(page=><button key={page.id} className={`thumbnail ${selectedPage.id===page.id?'active':''}`} onClick={()=>setSelectedPageId(page.id)}><span>{page.page_index+1}</span><img src={page.image_url} alt={`Pratinjau halaman ${page.page_index+1}`}/></button>)}</div>}</div>
            <div className="review-column"><div className="answer-nav"><span className="eyebrow">NOMOR SOAL</span><div>{submission.answers.map(answer=><button key={answer.question_id} className={selectedAnswer?.question_id===answer.question_id?'selected':''} onClick={()=>setSelectedQuestion(answer.question_id)}>{answer.label}<i className={answer.review&&!['needs_review','unreadable','unsupported','unmapped'].includes(answer.review.status)?'done':''}/></button>)}</div></div>{selectedAnswer&&<div className="answer-panel"><div className="answer-title"><div><p className="eyebrow">SOAL {selectedAnswer.label} · BOBOT {selectedAnswer.weight}</p><h2>{selectedAnswer.text||'Pertanyaan belum tersedia'}</h2></div><span className="tag tag-neutral">{selectedAnswer.transcript_status}</span></div><div className="transcript-block">{!selectedAnswer.transcript_revision_id&&<p className="warning-note">{selectedOcrBusy?'OCR sedang dalam antrean atau membaca tulisan. Hasil akan tampil otomatis setelah proses selesai.':!submission.pages.length?'Transkripsi menunggu render PDF selesai. Jika render gagal, pilih Coba lagi pada pekerjaan di atas.':submission.identity_status!=='confirmed'?'Periksa halaman lalu konfirmasikan identitas terlebih dahulu.':(!selectedAnswer.mapping_revision_id||selectedAnswer.mapping_status==='unmapped')?'Tarik kotak pada area jawaban, pilih kotaknya, lalu klik Petakan. Setelah itu pilih Baca tulisan.':'Area jawaban sudah dipetakan. Pilih Baca tulisan untuk menjalankan transkripsi ' + transcriberLabel + '; atau periksa hasil OCR otomatis.'}</p>}{selectedAnswer.transcript_status==='unreadable'&&<p className="warning-note">Ada tulisan yang tidak terbaca. Perbaiki transkripsi berdasarkan gambar; penilaian otomatis ditahan.</p>}{selectedAnswer.transcript_flags?.includes('experimental_transcriber_review_required')&&<p className="warning-note">Hasil ini dibuat oleh TrOCR eksperimental. Bandingkan seluruh kata, angka, dan tanda dengan scan; koreksi lalu simpan transkripsi agar usulan nilai dapat diminta.</p>}<div className="block-title"><div><b>Transkripsi literal</b><small>Tanpa melihat kunci atau rubrik</small></div><button className="text-button" disabled={!transcriptionReady||!selectedAnswer.mapping_revision_id||selectedAnswer.mapping_status==='unmapped'||busy||selectedOcrBusy||autoAnalysisBusy||submission.identity_status!=='confirmed'} onClick={()=>queueAnswerTask('transcribe')}>{selectedOcrBusy?<><Spinner/> Membaca tulisan…</>:<><Icon name="spark"/> Baca tulisan</>}</button></div><textarea disabled={selectedOcrBusy} aria-busy={selectedOcrBusy} value={transcriptText} onChange={e=>setTranscriptText(e.target.value)} placeholder="Ketik persis jawaban yang terlihat. Jangan memperbaiki isi jawaban."/><div className="inline-actions"><button className="button secondary compact" disabled={busy||selectedOcrBusy||!selectedAnswer.mapping_revision_id||selectedAnswer.mapping_status==='unmapped'} onClick={()=>saveTranscript('transcribed')}>Simpan transkripsi</button><button className="quiet-button" disabled={busy||selectedOcrBusy} onClick={()=>saveTranscript('verified_blank')}>Tandai kosong</button></div>{selectedAnswer.transcript_stale&&<p className="warning-note">Mapping berubah. Simpan transkripsi baru sebelum memakai hasil lama.</p>}</div><div className="proposal-block"><div className="block-title"><div><b>Usulan penilaian</b><small>Model hanya mengusulkan kredit dan bukti, bukan total nilai.</small></div><button className="text-button" disabled={!selectedAnswer.transcript_revision_id||selectedAnswer.transcript_status!=='transcribed'||selectedAnswer.transcript_stale||busy||selectedOcrBusy||selectedGradeBusy||selectedAnswer.mapping_status==='auto_mapped'||Boolean(selectedAnswer.transcript_flags?.length)} onClick={()=>queueAnswerTask('propose')}>{selectedGradeBusy?<><Spinner/> Menyiapkan usulan…</>:<><Icon name="spark"/> Minta usulan</>}</button></div>{selectedAnswer.proposal?.criteria?.length?<GradeProposalView criteria={selectedAnswer.proposal.criteria} rubric={selectedAnswer.rubric} segments={selectedAnswer.segments} stale={selectedAnswer.proposal_stale}/>:<div className="proposal-empty">Belum ada usulan. Keputusan manual tetap dapat disimpan.</div>}</div><div className="criteria-review" id="review-decision"><div className="block-title"><div><b>Keputusan dosen</b><small>Skor angka dihitung server dari kriteria dan bobot.</small></div></div><label>Status jawaban<select value={answerStatus} onChange={e=>setAnswerStatus(e.target.value)}><option value="correct">Benar</option><option value="partially_correct">Sebagian benar</option><option value="incorrect">Salah</option><option value="verified_blank">Kosong terverifikasi</option><option value="reviewed">Ditinjau</option><option value="unreadable">Tidak terbaca</option><option value="unsupported">Belum didukung</option><option value="unmapped">Belum dipetakan</option><option value="needs_review">Perlu tinjauan</option></select></label>{selectedAnswer.rubric.map(criterion=><div className="criterion-review-row" key={criterion.id}><div><b>{criterion.id} · {criterion.description}</b><small>Maksimum {criterion.max_points} poin</small></div><select value={reviewCredits[criterion.id]??'0'} disabled={Boolean(overrideRaw)} onChange={e=>setReviewCredits(c=>({...c,[criterion.id]:e.target.value}))}>{criterion.credit_levels.map(level=><option key={level} value={level}>{level} · {criterion.anchors[level]}</option>)}</select></div>)}<div className="override-fields"><label>Override raw (opsional)<input type="number" min="0" step="0.01" value={overrideRaw} onChange={e=>{setOverrideRaw(e.target.value);setAnswerStatus(e.target.value?'reviewed':'partially_correct');}} placeholder="Kosongkan untuk memakai kriteria"/></label><label>Alasan / catatan reviewer<textarea value={reviewReason} onChange={e=>setReviewReason(e.target.value)} placeholder="Wajib untuk override atau jawaban kosong."/></label></div><div className="review-footer"><span className="tiny muted">Tidak ada pembobotan di sini; nilai dihitung dari rubrik.</span><button className="button primary" disabled={busy||selectedAnswer.mapping_status==='auto_mapped'} onClick={saveReview}>Simpan keputusan <Icon name="check"/></button></div></div></div>}</div>
          </div>
          {!submission.final_snapshot&&<FinalizationChecklist answers={submission.answers} unassignedCount={submission.unassigned_region_ids?.length??0}
            onQuestion={id=>{setSelectedQuestion(id);document.getElementById('review-decision')?.scrollIntoView({behavior:'smooth',block:'start'});}}
            onRegions={()=>{const details=document.getElementById('unassigned-region-details') as HTMLDetailsElement|null;if(details){details.open=true;details.scrollIntoView({behavior:'smooth',block:'start'});}}}/>}
          <div className="finalize-panel"><div><p className="eyebrow">PENGESAHAN NILAI</p><h2>{submission.final_snapshot?'Snapshot final terkunci':'Semua keputusan siap?'}</h2><p className="muted">Finalisasi memeriksa identitas, pemetaan yang ditinjau, area yang belum dipetakan, bukti, kriteria, dan proses aktif.</p></div><div className="finalize-side">{submission.review_revision&&<span className={`tag ${submission.review_revision.status==='finalized'?'tag-green':'tag-amber'}`}>Review {submission.review_revision.status} · v{submission.review_revision.version}</span>}<button className="button primary" disabled={busy||!submission.review_revision||submission.review_revision.status!=='draft'||!submission.document||submission.document.status!=='valid'} onClick={finalize}><Icon name="check"/> Sahkan nilai final</button></div></div>
        </section>}
      </div>
    </main>
  </div>;
}
