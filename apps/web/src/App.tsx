import { FormEvent, PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

type ApiError = Error & { code?: string; details?: unknown };
type User = { id: string; username: string; display_name: string; role: string };
type Assessment = { id: string; title: string; course_label: string; language: string; status: string; revision: null | { id: string; sequence: number; version: number; status: string }; submission_count: number };
type Criterion = { id: string; description: string; max_points: string; credit_levels: string[]; anchors: Record<string, string> };
type Question = { stable_question_id: string; label: string; order: number; text: string; answer_type: string; weight: string; reference_answer: string; alternatives: string[]; criteria: Criterion[] };
type Region = { id: string; polygon: [number, number][]; region_type: string };
type Page = { id: string; page_index: number; page_image_revision_id: string; width_px: number; height_px: number; rotation: number; image_url: string; regions: Region[] };
type Answer = { id: string; question_id: string; label: string; text: string; weight: string; rubric: Criterion[]; mapping_status: string; mapping_revision_id: string | null; region_ids: string[]; transcript_status: string; transcript: string; transcript_revision_id: string | null; transcript_revision_no: number; transcript_stale: boolean; segments: {segment_id: string; region_id: string; order: number; text: string}[]; proposal: {criteria: {criterion_id: string; credit: string; label: string; evidence_refs: {segment_id:string;start:number;end:number;region_id:string}[]; rationale:string}[]} | null; proposal_id: string | null; proposal_stale: boolean; review: {status:string; criteria: {criterion_id:string;credit:string;evidence_refs:unknown[];rationale:string;source:string}[] | null; override_raw:string|null; reason:string|null} | null };
type Submission = { id: string; assessment_id: string; assessment_revision_id: string; assessment_revision_status: string; external_student_id: string; display_name: string; attempt_no: number; identity_status: string; identity_confirmation_id: string | null; document: null | { id:string; sha256:string; status:string; page_count:number; layout_revision_id:string|null; original_url:string }; pages: Page[]; answers: Answer[]; review_revision: null|{id:string;sequence:number;version:number;status:string}; final_snapshot: null|{id:string;score:string;revision_id:string;approved_at:string}; status:string; version:number };

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
    if (Array.isArray(details.blockers)) return `${err.message}: ${details.blockers.join(', ')}`;
  }
  return err?.message || 'Terjadi kesalahan.';
}
function freshCriterion(): Criterion { return { id: 'konsep', description: 'Konsep inti dijelaskan dengan benar', max_points: '10', credit_levels: ['0', '0.5', '1'], anchors: { '0': 'Tidak ada atau keliru', '0.5': 'Sebagian tepat', '1': 'Lengkap dan tepat' } }; }
function freshQuestion(index: number): Question { return { stable_question_id: `q${index}`, label: String(index), order: index, text: '', answer_type: 'essay', weight: '1', reference_answer: '', alternatives: [], criteria: [freshCriterion()] }; }
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
  const [submissionRows, setSubmissionRows] = useState<{id:string;external_student_id:string;display_name:string;identity_status:string;status:string;final_score:string|null;document_status:string}[]>([]);
  const [selectedSubmissionIds, setSelectedSubmissionIds] = useState<string[]>([]);
  const [submission, setSubmission] = useState<Submission|null>(null);
  const [activeView, setActiveView] = useState<'overview'|'assessment'|'submission'>('overview');
  const [studentId, setStudentId] = useState('');
  const [studentName, setStudentName] = useState('');
  const [studentFile, setStudentFile] = useState<File|null>(null);
  const [questionPdf, setQuestionPdf] = useState<File|null>(null);
  const [selectedQuestion, setSelectedQuestion] = useState('');
  const [selectedRegions, setSelectedRegions] = useState<string[]>([]);
  const [transcriptText, setTranscriptText] = useState('');
  const [reviewCredits, setReviewCredits] = useState<Record<string,string>>({});
  const [reviewReason, setReviewReason] = useState('');
  const [overrideRaw, setOverrideRaw] = useState('');
  const [answerStatus, setAnswerStatus] = useState('partially_correct');
  const [job, setJob] = useState<{id:string;status:string;error_code?:string;attempt?:number;kind?:string}|null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [modelStatus, setModelStatus] = useState<{available:boolean;reason?:string;device?:string;model_id?:string}|null>(null);
  const [selectedPageId, setSelectedPageId] = useState('');
  const [questionImportDocId, setQuestionImportDocId] = useState('');
  const [questionImportText, setQuestionImportText] = useState('');
  const imageBox = useRef<HTMLDivElement>(null);
  const pointerStart = useRef<[number,number]|null>(null);

  const selectedAnswer = useMemo(() => submission?.answers.find(answer => answer.question_id === selectedQuestion) || submission?.answers[0] || null, [submission, selectedQuestion]);
  const selectedPage = submission?.pages.find(page=>page.id===selectedPageId) || submission?.pages[0] || null;

  const loadAssessments = useCallback(async () => {
    const data = await api<{items:Assessment[]}>('/api/v1/assessments');
    setAssessments(data.items);
  }, []);
  const loadSubmission = useCallback(async (id: string) => {
    const data = await api<Submission>(`/api/v1/submissions/${id}`);
    setSubmission(data);
    setSelectedPageId(current=>data.pages.some(page=>page.id===current)?current:(data.pages[0]?.id||''));
    if (!selectedQuestion && data.answers[0]) setSelectedQuestion(data.answers[0].question_id);
    const active = data.answers.find(answer => answer.question_id === selectedQuestion) || data.answers[0];
    if (active) {
      setTranscriptText(active.transcript || '');
      setReviewCredits(Object.fromEntries((active.review?.criteria || active.proposal?.criteria || active.rubric.map(c => ({criterion_id:c.id,credit:'0'}))).map((c:any) => [c.criterion_id, c.credit])));
      setSelectedRegions(active.region_ids || []);
      if (active.review?.reason) setReviewReason(active.review.reason);
    }
  }, [selectedQuestion]);
  const loadSubmissionList = useCallback(async (id:string) => {
    const data = await api<{items:any[]}>(`/api/v1/assessments/${id}/submissions`);
    setSubmissionRows(data.items);
    setSelectedSubmissionIds(data.items.map(item=>item.id));
  }, []);
  const loadAssessment = useCallback(async (item:Assessment) => {
    setAssessment(item); setSubmission(null); setError(''); setNotice('');
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
  useEffect(() => { if (selectedAnswer) { setTranscriptText(selectedAnswer.transcript || ''); setSelectedRegions(selectedAnswer.region_ids || []); setReviewCredits(Object.fromEntries((selectedAnswer.review?.criteria || selectedAnswer.proposal?.criteria || selectedAnswer.rubric.map(c => ({criterion_id:c.id,credit:'0'}))).map((c:any) => [c.criterion_id, c.credit]))); setReviewReason(selectedAnswer.review?.reason || ''); setOverrideRaw(selectedAnswer.review?.override_raw || ''); setAnswerStatus(selectedAnswer.review?.status || (selectedAnswer.transcript_status === 'verified_blank' ? 'verified_blank' : 'partially_correct')); } }, [selectedAnswer]);
  useEffect(() => {
    if (!job || !['queued','running'].includes(job.status)) return;
    const timer = window.setInterval(() => {
      api<{id:string;status:string;error_code?:string}>(`/api/v1/jobs/${job.id}`).then(async state => {
        setJob(state);
        if (state.status === 'succeeded' || state.status === 'failed' || state.status === 'cancelled') {
          if (questionImportDocId) { const doc = await api<any>(`/api/v1/documents/${questionImportDocId}`).catch(() => null); if (doc?.extracted_text) setQuestionImportText(doc.extracted_text); }
          if (submission) await loadSubmission(submission.id);
          if (assessment) await loadSubmissionList(assessment.id);
          setNotice(state.status === 'succeeded' ? 'Pekerjaan selesai.' : `Pekerjaan ${state.status}${state.error_code ? `: ${state.error_code}` : ''}.`);
        }
      }).catch(() => undefined);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status, submission?.id, assessment?.id, questionImportDocId, loadSubmission, loadSubmissionList]);
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
  function updateQuestion(index:number, change:Partial<Question>) { setQuestions(current=>current.map((q,i)=>i===index?{...q,...change}:q)); }
  async function saveQuestions() {
    if (!revision) return;
    const result = await act(()=>api<{version:number;questions:Question[]}>(`/api/v1/assessment-revisions/${revision.id}/questions`,{method:'PUT',body:json({expected_version:revision.version,questions})}),'Perubahan soal dan rubrik tersimpan.');
    if (result) { setRevision({...revision,version:result.version}); setQuestions(result.questions); if (assessment) { const next={...assessment,revision:{...assessment.revision!,version:result.version,status:'draft'}}; setAssessment(next); await loadAssessments(); } }
  }
  async function approveRevision() {
    if (!revision || !assessment?.revision) return;
    const result=await act(()=>api<{status:string;version:number}>(`/api/v1/assessment-revisions/${revision.id}/approve`,{method:'POST',body:json({expected_version:revision.version,confirmation:true})}),'Rubrik disahkan dan dikunci.');
    if (result && assessment) { const updated={...assessment,status:'approved',revision:{...assessment.revision!,status:result.status,version:result.version}};setAssessment(updated);await loadAssessments(); }
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
  async function addQuestion() { setQuestions(current=>[...current,freshQuestion(current.length+1)]); }
  async function addCriterion(questionIndex:number) { setQuestions(current=>current.map((q,i)=>i===questionIndex?{...q,criteria:[...q.criteria,{...freshCriterion(),id:`k${q.criteria.length+1}`,description:'Kriteria baru'}]}:q)); }
  async function importQuestionSource() {
    if (!questionPdf || !revision || !assessment) return;
    const form=new FormData();form.set('file',questionPdf);form.set('assessment_revision_id',revision.id);
    const result=await act(()=>api<any>(`/api/v1/assessments/${assessment.id}/question-imports`,{method:'POST',body:form}),'PDF soal dikirim untuk ekstraksi teks.');
    if (result) { setQuestionImportDocId(result.document_id); setQuestionImportText(result.extracted_text || ''); if (result.job) setJob({id:result.job.id,status:result.job.status,error_code:result.job.error_code}); }
  }
  async function createSubmission() {
    if (!assessment || !studentId.trim() || !studentName.trim()) return;
    const result=await act(()=>api<{id:string}>(`/api/v1/assessments/${assessment.id}/submissions`,{method:'POST',body:json({external_student_id:studentId,display_name:studentName,attempt_no:1})}),'Submission dibuat.');
    if (result) { const details=await api<any>(`/api/v1/submissions/${result.id}`); setSubmission(details); setActiveView('submission'); }
  }
  async function uploadStudentFile() {
    if (!submission || !studentFile) return;
    const data=new FormData();data.set('file',studentFile);
    const result=await act(()=>api<any>(`/api/v1/submissions/${submission.id}/documents`,{method:'POST',body:data}),'PDF jawaban diunggah.');
    if (result) {
      const current=await api<Submission>(`/api/v1/submissions/${submission.id}`);
      await api(`/api/v1/submissions/${submission.id}/confirm-identity`,{method:'POST',body:json({document_id:result.document_id,document_hash:result.sha256,external_student_id:studentId,display_name:studentName,expected_submission_version:current.version})});
      await loadSubmission(submission.id); if (assessment) await loadSubmissionList(assessment.id);
      if(result.job) setJob({id:result.job.id,status:result.job.status,error_code:result.job.error_code});
      setNotice('Identitas dikonfirmasi. Status PDF dan halaman akan diperbarui saat render selesai.');
    }
  }
  async function openSubmission(id:string) { if (assessment) { await loadSubmission(id);setActiveView('submission');setError(''); } }
  async function createRegion(event:PointerEvent<HTMLDivElement>) {
    if (event.type === 'pointerdown') {
      if (!imageBox.current) return;
      const rect=imageBox.current.getBoundingClientRect();
      pointerStart.current=[Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
      return;
    }
    if (event.type !== 'pointerup' || !pointerStart.current || !selectedPage) return;
    const rect=imageBox.current?.getBoundingClientRect(); if(!rect)return;
    const endPoint:[number,number]=[Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
    const start=pointerStart.current;pointerStart.current=null;
    const left=Math.min(start[0],endPoint[0]),right=Math.max(start[0],endPoint[0]),top=Math.min(start[1],endPoint[1]),bottom=Math.max(start[1],endPoint[1]);
    if(right-left<.01||bottom-top<.01)return;
    const region=await act(()=>api<any>(`/api/v1/page-image-revisions/${selectedPage.page_image_revision_id}/regions`,{method:'POST',body:json({polygon:[[left,top],[right,top],[right,bottom],[left,bottom]],region_type:'answer'})}),'Area jawaban ditambahkan.');
    if(region&&submission)await loadSubmission(submission.id);
  }
  async function rotatePage() {
    if(!submission?.document?.layout_revision_id||!selectedPage)return;
    const result=await act(()=>api<any>(`/api/v1/page-image-revisions/${selectedPage.page_image_revision_id}/rotate`,{method:'POST',body:json({degrees_clockwise:90,expected_layout_revision_id:submission.document!.layout_revision_id})}),'Halaman diputar. Mapping lama memerlukan revisi.');
    if(result&&submission)await loadSubmission(submission.id);
  }
  function toggleRegion(id:string) { setSelectedRegions(current=>current.includes(id)?current.filter(x=>x!==id):[...current,id]); }
  async function mapAnswer() {
    if(!submission||!selectedAnswer)return;
    const result=await act(()=>api<any>(`/api/v1/answers/${selectedAnswer.id}/mapping-revisions`,{method:'POST',body:json({region_ids:selectedRegions,expected_transcript_revision:selectedAnswer.transcript_revision_no,expected_mapping_revision_id:selectedAnswer.mapping_revision_id})}),'Region dipetakan ke nomor jawaban.');
    if(result)await loadSubmission(submission.id);
  }
  async function saveTranscript(status='transcribed') {
    if(!submission||!selectedAnswer)return;
    const result=await act(()=>api<any>(`/api/v1/submissions/${submission.id}/answers/${selectedAnswer.question_id}/transcription-revisions`,{method:'POST',body:json({literal_text:status==='verified_blank'?'':transcriptText,status,flags:[],expected_revision:selectedAnswer.transcript_revision_no,reason:status==='verified_blank'?reviewReason:null})}),status==='verified_blank'?'Jawaban ditandai kosong setelah verifikasi.':'Transkripsi literal tersimpan.');
    if(result)await loadSubmission(submission.id);
  }
  async function queueAnswerTask(kind:'transcribe'|'propose') {
    if(!submission||!selectedAnswer)return;
    const result=await act(()=>api<any>(`/api/v1/submissions/${submission.id}/answers/${selectedAnswer.question_id}/${kind}`,{method:'POST'}),kind==='transcribe'?'Transkripsi lokal dimasukkan antrean.':'Usulan penilaian dimasukkan antrean.');
    if(result?.job_id)setJob({id:result.job_id,status:result.status,error_code:result.error_code});
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
  async function cancelActiveJob() {
    if(!job)return;
    const result=await act(()=>api<any>(`/api/v1/jobs/${job.id}/cancel`,{method:'POST'}),'Permintaan pembatalan pekerjaan dikirim.');
    if(result)setJob({...job,status:result.status});
  }
  async function retryFailedJob() {
    if(!job)return;
    const attempt=job.attempt||1;
    const result=await act(()=>api<any>(`/api/v1/jobs/${job.id}/retry`,{method:'POST',body:json({expected_attempt:attempt,reason:'Percobaan ulang diminta dosen dari ruang review.'})}),'Pekerjaan dijadwalkan ulang.');
    if(result)setJob({id:result.id,status:result.status,error_code:result.error_code,attempt:result.attempt,kind:job.kind});
  }

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
      <header className="topbar"><div className="breadcrumbs"><span>Ruang kerja</span>{assessment&&<><span className="crumb-sep">/</span><b>{assessment.title}</b></>}</div><div className="topbar-right"><div className={`model-pill ${modelStatus?.available?'ready':''}`}><span className="status-dot"/><span>{modelStatus?.available?'Model lokal siap':'Model belum disiapkan'}</span></div><button className="avatar small" title={user.username}>{user.display_name.slice(0,1).toUpperCase()}</button></div></header>
      <div className="page-content">
        {(error||notice)&&<div className={`alert ${error?'alert-error':'alert-success'}`} role="status"><span>{error||notice}</span><button onClick={()=>{setError('');setNotice('');}} aria-label="Tutup">×</button></div>}
        {job&&<div className={`job-banner ${job.status==='failed'?'failed':job.status==='succeeded'?'finished':''}`}><span className="status-dot"/><div><b>{job.kind||'Pekerjaan'} · {job.status}</b><small>{job.error_code||'Pekerjaan diproses lokal; halaman akan diperbarui otomatis.'}</small></div><div className="job-actions">{['queued','running'].includes(job.status)&&<button className="quiet-button" onClick={cancelActiveJob}>Batalkan</button>}{job.status==='failed'&&(job.attempt||1)<3&&<button className="text-button" onClick={retryFailedJob}>Coba lagi</button>}</div></div>}
        {activeView==='overview'&&<section className="overview-page">
          <div className="welcome-row"><div><p className="eyebrow">DASHBOARD DOSEN</p><h1>Selamat bekerja, {user.display_name.split(' ')[0]}.</h1><p className="muted">Susun asesmen, tinjau jawaban, lalu sahkan nilai.</p></div><button className="button primary" onClick={()=>document.getElementById('new-assessment')?.scrollIntoView({behavior:'smooth'})}><Icon name="plus"/> Asesmen baru</button></div>
          <div className="stat-grid"><div className="stat-card"><span className="stat-icon"><Icon name="book"/></span><div><small>ASESMEN</small><b>{assessments.length}</b></div><span className="stat-note">di ruang kerja</span></div><div className="stat-card"><span className="stat-icon amber"><Icon name="file"/></span><div><small>LEMBAR JAWABAN</small><b>{assessments.reduce((n,a)=>n+a.submission_count,0)}</b></div><span className="stat-note">seluruh asesmen</span></div><div className="stat-card"><span className="stat-icon green"><Icon name="check"/></span><div><small>MODEL LOKAL</small><b>{modelStatus?.available?'Siap':'Manual'}</b></div><span className="stat-note">tanpa API berbayar</span></div></div>
          <div className="section-heading"><div><p className="eyebrow">RUANG KERJA</p><h2>Asesmen Anda</h2></div><button className="text-button" onClick={loadAssessments}>Muat ulang <Icon name="rotate"/></button></div>
          {assessments.length===0?<div className="empty-card"><div className="empty-art"><Icon name="book"/></div><h3>Belum ada asesmen</h3><p>Buat asesmen pertama, susun rubrik, lalu masukkan lembar jawaban.</p></div>:<div className="assessment-grid">{assessments.map(item=><button key={item.id} className="assessment-card" onClick={()=>loadAssessment(item)}><div className="assessment-card-top"><div className="course-avatar">{item.title.slice(0,1).toUpperCase()}</div><span className={`tag ${item.status==='approved'?'tag-green':'tag-amber'}`}>{item.status==='approved'?'Disahkan':'Draft'}</span></div><h3>{item.title}</h3><p>{item.course_label||'Mata kuliah belum diisi'}</p><div className="card-meta"><span>{item.revision?`Versi ${item.revision.sequence}`:'Belum ada versi'}</span><span>{item.submission_count} lembar</span></div><span className="card-arrow"><Icon name="arrow"/></span></button>)}</div>}
          <div className="create-panel" id="new-assessment"><div><p className="eyebrow">MULAI BARU</p><h2>Buat asesmen</h2><p className="muted">Mulai dari soal dan rubrik yang disetujui.</p></div><form className="create-form" onSubmit={createAssessment}><label>Nama asesmen<input name="title" required placeholder="Contoh: UTS Biologi Sel"/></label><div className="form-row"><label>Mata kuliah<input name="course_label" placeholder="Biologi Sel · 2026/2027"/></label><label>Bahasa<select name="language"><option value="id">Indonesia</option><option value="en">English</option></select></label></div><button className="button primary" disabled={busy}><Icon name="plus"/> Buat draft</button></form></div>
        </section>}

        {activeView==='assessment'&&assessment&&<section className="assessment-page">
          <div className="page-title-row"><div><p className="eyebrow">ASESMEN · VERSI {assessment.revision?.sequence||1}</p><h1>{assessment.title}</h1><p className="muted">{assessment.course_label||'Mata kuliah belum diisi'} <span className="dot-sep">·</span> Bahasa {assessment.language==='id'?'Indonesia':'Inggris'}</p></div><div className="title-actions">{revision?.status==='approved'&&<button className="button secondary" onClick={createRevision} disabled={busy}>Buat revisi rubrik</button>}<span className={`tag ${revision?.status==='approved'?'tag-green':'tag-amber'}`}>{revision?.status==='approved'?'Rubrik disahkan':'Draft — belum disahkan'}</span></div></div>
          <div className="tabs"><button className="selected">Soal & rubrik</button><button onClick={()=>document.getElementById('submissions')?.scrollIntoView({behavior:'smooth'})}>Lembar jawaban <span>{submissionRows.length}</span></button></div>
          <div className="import-source"><div className="import-icon"><Icon name="file"/></div><div className="import-copy"><b>Impor teks soal dari PDF</b><small>Ekstraksi teks lokal membantu mengisi draf. Periksa kembali setiap soal sebelum rubrik disahkan.</small></div><input type="file" accept="application/pdf" onChange={e=>setQuestionPdf(e.target.files?.[0]||null)} aria-label="PDF soal"/><button className="button secondary" disabled={!questionPdf||revision?.status!=='draft'||busy} onClick={importQuestionSource}><Icon name="upload"/> Impor PDF</button></div>{questionImportText&&<div className="extracted-source"><b>Teks hasil ekstraksi — draf, perlu diverifikasi</b><textarea value={questionImportText} onChange={e=>setQuestionImportText(e.target.value)} aria-label="Teks hasil ekstraksi PDF soal"/></div>}
          <div className="question-list">{questions.map((question,index)=><article className="question-card" key={question.stable_question_id}><div className="question-card-head"><div className="question-number">{question.label||index+1}</div><div className="question-heading"><span className="eyebrow">SOAL {index+1} · ID {question.stable_question_id}</span><strong>{question.text||'Soal belum ditulis'}</strong></div><label className="weight-field">Bobot<input type="number" min="0.01" step="0.01" disabled={revision?.status==='approved'} value={question.weight} onChange={e=>updateQuestion(index,{weight:e.target.value})}/></label></div><div className="question-edit-grid"><label>Pertanyaan<textarea disabled={revision?.status==='approved'} value={question.text} onChange={e=>updateQuestion(index,{text:e.target.value})} placeholder="Tulis pertanyaan yang akan dijawab mahasiswa."/></label><label>Kunci / jawaban acuan<textarea disabled={revision?.status==='approved'} value={question.reference_answer} onChange={e=>updateQuestion(index,{reference_answer:e.target.value})} placeholder="Tuliskan konsep inti dan jawaban yang dapat diterima."/></label></div><div className="rubric-header"><div><b>Rubrik penilaian</b><small>Bobot kriteria mentah dan level kredit harus eksplisit.</small></div><button className="text-button" disabled={revision?.status==='approved'} onClick={()=>addCriterion(index)}><Icon name="plus"/> Tambah kriteria</button></div><div className="criteria-table"><div className="criteria-head"><span>Kriteria</span><span>Poin maks.</span><span>Level kredit & anchor</span><span/></div>{question.criteria.map((criterion,ci)=><div className="criterion-row" key={criterion.id}><div className="criterion-desc"><input disabled={revision?.status==='approved'} aria-label="ID kriteria" value={criterion.id} onChange={e=>updateQuestion(index,{criteria:question.criteria.map((c,j)=>j===ci?{...c,id:e.target.value}:c)})}/><input disabled={revision?.status==='approved'} aria-label="Deskripsi kriteria" value={criterion.description} onChange={e=>updateQuestion(index,{criteria:question.criteria.map((c,j)=>j===ci?{...c,description:e.target.value}:c)})}/></div><input className="points-input" type="number" min="0.01" step="0.01" disabled={revision?.status==='approved'} value={criterion.max_points} onChange={e=>updateQuestion(index,{criteria:question.criteria.map((c,j)=>j===ci?{...c,max_points:e.target.value}:c)})}/><div className="anchors">{criterion.credit_levels.map(level=><label key={level}><span>{level}</span><input disabled={revision?.status==='approved'} value={criterion.anchors[level]||''} onChange={e=>updateQuestion(index,{criteria:question.criteria.map((c,j)=>j===ci?{...c,anchors:{...c.anchors,[level]:e.target.value}}:c)})}/></label>)}</div><button className="remove-button" disabled={revision?.status==='approved'||question.criteria.length<=1} title="Hapus kriteria" onClick={()=>updateQuestion(index,{criteria:question.criteria.filter((_,j)=>j!==ci)})}>×</button></div>)}</div></article>)}<button className="add-question" disabled={revision?.status==='approved'} onClick={addQuestion}><Icon name="plus"/> Tambahkan soal</button></div>
          <div className="action-bar"><div><span className={`status-dot ${revision?.status==='approved'?'green':'amber'}`}/><span>{revision?.status==='approved'?'Rubrik terkunci pada versi ini':'Simpan soal sebelum pengesahan'}</span></div><div>{revision?.status==='draft'?<><button className="button secondary" disabled={busy} onClick={saveQuestions}>Simpan perubahan</button><button className="button primary" disabled={busy||questions.length===0} onClick={approveRevision}><Icon name="check"/> Sahkan rubrik</button></>:<button className="button primary" disabled={busy} onClick={()=>document.getElementById('student-entry')?.scrollIntoView({behavior:'smooth'})}>Mulai unggah jawaban <Icon name="arrow"/></button>}</div></div>
          <div id="student-entry" className="submission-create-panel"><div className="section-heading"><div><p className="eyebrow">ALUR PENILAIAN</p><h2>Tambahkan lembar jawaban</h2><p className="muted">Satu PDF untuk satu mahasiswa. Identitas dikonfirmasi setelah berkas dimuat.</p></div></div><div className="student-form"><label>NIM<input value={studentId} onChange={e=>setStudentId(e.target.value)} placeholder="Contoh: 0012345678"/></label><label>Nama mahasiswa<input value={studentName} onChange={e=>setStudentName(e.target.value)} placeholder="Nama sesuai lembar jawaban"/></label><button className="button primary" disabled={!studentId.trim()||!studentName.trim()||assessment.revision?.status!=='approved'||busy} onClick={createSubmission}><Icon name="plus"/> Buat lembar</button></div>
            {submission&&submission.assessment_id===assessment.id&&!submission.document&&<div className="upload-inline"><label className="file-drop"><Icon name="upload"/><span><b>Pilih PDF hasil scan</b><small>{studentFile?.name||'PDF hingga 50 MiB · maksimal 100 halaman'}</small></span><input type="file" accept="application/pdf" onChange={e=>setStudentFile(e.target.files?.[0]||null)}/></label><button className="button primary" disabled={!studentFile||busy} onClick={uploadStudentFile}>Unggah & konfirmasi <Icon name="arrow"/></button></div>}
          </div>
          <div id="submissions" className="section-heading list-heading"><div><p className="eyebrow">KOREKSI</p><h2>Lembar jawaban <span className="count-badge">{submissionRows.length}</span></h2><small className="muted">{selectedSubmissionIds.length} dipilih untuk ekspor</small></div><div className="export-actions"><button className="button secondary" disabled={!selectedSubmissionIds.length||busy} onClick={()=>exportGrades('draft')}><Icon name="download"/> Ekspor draft</button><button className="button primary" disabled={!selectedSubmissionIds.length||busy} onClick={()=>exportGrades('final')}><Icon name="check"/> Ekspor final</button></div></div>
          <div className="submission-table-wrap"><table className="submission-table"><thead><tr><th><input type="checkbox" aria-label="Pilih semua submission" checked={submissionRows.length>0&&selectedSubmissionIds.length===submissionRows.length} onChange={e=>setSelectedSubmissionIds(e.target.checked?submissionRows.map(row=>row.id):[])}/></th><th>NIM</th><th>Nama mahasiswa</th><th>PDF</th><th>Status</th><th>Nilai akhir</th><th/></tr></thead><tbody>{submissionRows.map(row=><tr key={row.id}><td><input type="checkbox" aria-label={`Pilih ${row.display_name||row.id}`} checked={selectedSubmissionIds.includes(row.id)} onChange={e=>setSelectedSubmissionIds(current=>e.target.checked?[...current,row.id]:current.filter(id=>id!==row.id))}/></td><td className="mono">{row.external_student_id||<span className="muted">Belum dikonfirmasi</span>}</td><td>{row.display_name}</td><td>{row.document_status==='valid'?'Siap':row.document_status==='failed'?'Gagal':row.document_status}</td><td><span className={`tag ${row.final_score!==null?'tag-green':'tag-amber'}`}>{row.final_score!==null?'Final':'Perlu tinjauan'}</span></td><td className="score-cell">{row.final_score??'—'}</td><td><button className="text-button" onClick={()=>openSubmission(row.id)}>Buka <Icon name="arrow"/></button></td></tr>)}</tbody></table>{submissionRows.length===0&&<div className="table-empty">Belum ada lembar jawaban untuk asesmen ini.</div>}</div>
        </section>}

        {activeView==='submission'&&submission&&assessment&&<section className="grading-page">
          <div className="page-title-row"><div><button className="back-link" onClick={()=>setActiveView('assessment')}>← Kembali ke asesmen</button><p className="eyebrow">TINJAUAN DOSEN · {assessment.title}</p><h1>{submission.display_name||'Mahasiswa belum dikonfirmasi'}</h1><p className="muted">NIM {submission.external_student_id||'belum dikonfirmasi'} <span className="dot-sep">·</span> Berkas {submission.document?.status||'belum diunggah'}</p></div><div className="score-summary"><span className="eyebrow">NILAI FINAL</span><b>{submission.final_snapshot?.score??'—'}</b><small>{submission.final_snapshot?'Sudah disahkan':'Belum disahkan'}</small></div></div>
          {submission.document&&submission.identity_status!=='confirmed'&&<div className="alert alert-warning">Identitas dokumen belum dikonfirmasi. <button className="text-button" onClick={async()=>{const data=await api<any>(`/api/v1/submissions/${submission.id}`);await api(`/api/v1/submissions/${submission.id}/confirm-identity`,{method:'POST',body:json({document_id:submission.document!.id,document_hash:submission.document!.sha256,external_student_id:studentId||submission.external_student_id,display_name:studentName||submission.display_name,expected_submission_version:data.version})});await loadSubmission(submission.id);}}>Konfirmasi identitas</button></div>}
          <div className="grading-layout"><div className="visual-column"><div className="panel-head"><div><p className="eyebrow">DOKUMEN ASLI</p><b>Halaman jawaban</b></div><div className="panel-actions"><button className="icon-button" title="Putar halaman 90°" onClick={rotatePage}><Icon name="rotate"/></button><span className="page-counter">{selectedPage?`Halaman ${(selectedPage.page_index||0)+1} dari ${submission.document?.page_count||1}`:'Menunggu render'}</span></div></div><div className="document-stage">{selectedPage?<div className="annotatable-image" ref={imageBox} onPointerDown={e=>void createRegion(e)} onPointerUp={e=>void createRegion(e)}><img src={selectedPage.image_url} alt={`Halaman ${(selectedPage.page_index||0)+1} dari lembar jawaban`}/>{selectedPage.regions.map(region=>{const xs=region.polygon.map(p=>p[0]),ys=region.polygon.map(p=>p[1]);const left=Math.min(...xs),top=Math.min(...ys),width=Math.max(...xs)-left,height=Math.max(...ys)-top;return <button key={region.id} type="button" className={`region-box ${selectedRegions.includes(region.id)?'selected':''}`} style={{left:`${left*100}%`,top:`${top*100}%`,width:`${width*100}%`,height:`${height*100}%`}} onPointerDown={e=>e.stopPropagation()} onClick={()=>toggleRegion(region.id)} title={`Region ${region.id}`}/>})}<div className="drawing-hint">Tarik area pada halaman untuk menandai jawaban</div></div>:<div className="document-empty"><Icon name="file"/><b>{submission.document?'Halaman sedang diproses':'Unggah PDF untuk melihat halaman'}</b><span>{submission.document?`Status: ${submission.document.status}`:'PDF asli tetap tersimpan dan tidak diubah.'}</span></div>}</div><div className="region-tools"><div><b>Area jawaban</b><small>{selectedRegions.length} region dipilih · Klik kotak pada halaman untuk memilih</small></div><button className="button secondary compact" disabled={!selectedRegions.length||!selectedAnswer||busy} onClick={mapAnswer}>Petakan ke {selectedAnswer?.label||'soal'}</button></div>{selectedPage&&<div className="page-thumbnails">{submission.pages.map(page=><button key={page.id} className={`thumbnail ${selectedPage.id===page.id?'active':''}`} onClick={()=>setSelectedPageId(page.id)}><span>{page.page_index+1}</span><img src={page.image_url} alt={`Pratinjau halaman ${page.page_index+1}`}/></button>)}</div>}</div>
            <div className="review-column"><div className="answer-nav"><span className="eyebrow">NOMOR SOAL</span><div>{submission.answers.map(answer=><button key={answer.question_id} className={selectedAnswer?.question_id===answer.question_id?'selected':''} onClick={()=>setSelectedQuestion(answer.question_id)}>{answer.label}<i className={answer.review?'done':''}/></button>)}</div></div>{selectedAnswer&&<div className="answer-panel"><div className="answer-title"><div><p className="eyebrow">SOAL {selectedAnswer.label} · BOBOT {selectedAnswer.weight}</p><h2>{selectedAnswer.text||'Pertanyaan belum tersedia'}</h2></div><span className="tag tag-neutral">{selectedAnswer.transcript_status}</span></div><div className="transcript-block"><div className="block-title"><div><b>Transkripsi literal</b><small>Tanpa melihat kunci atau rubrik</small></div><button className="text-button" disabled={!selectedAnswer.mapping_revision_id||busy} onClick={()=>queueAnswerTask('transcribe')}><Icon name="spark"/> Baca tulisan</button></div><textarea value={transcriptText} onChange={e=>setTranscriptText(e.target.value)} placeholder="Ketik persis jawaban yang terlihat. Jangan memperbaiki isi jawaban."/><div className="inline-actions"><button className="button secondary compact" disabled={busy||!selectedAnswer.mapping_revision_id} onClick={()=>saveTranscript('transcribed')}>Simpan transkripsi</button><button className="quiet-button" disabled={busy} onClick={()=>saveTranscript('verified_blank')}>Tandai kosong</button></div>{selectedAnswer.transcript_stale&&<p className="warning-note">Mapping berubah. Simpan transkripsi baru sebelum memakai hasil lama.</p>}</div><div className="proposal-block"><div className="block-title"><div><b>Usulan penilaian</b><small>Model hanya mengusulkan kredit dan bukti, bukan total nilai.</small></div><button className="text-button" disabled={!selectedAnswer.transcript_revision_id||selectedAnswer.transcript_stale||busy} onClick={()=>queueAnswerTask('propose')}><Icon name="spark"/> Minta usulan</button></div>{selectedAnswer.proposal?.criteria?.length?<div className="proposal-note">Usulan tersedia untuk ditinjau. Periksa teks dan bukti visual sebelum menerima.</div>:<div className="proposal-empty">Belum ada usulan. Keputusan manual tetap dapat disimpan.</div>}</div><div className="criteria-review"><div className="block-title"><div><b>Keputusan dosen</b><small>Skor angka dihitung server dari kriteria dan bobot.</small></div></div><label>Status jawaban<select value={answerStatus} onChange={e=>setAnswerStatus(e.target.value)}><option value="correct">Benar</option><option value="partially_correct">Sebagian benar</option><option value="incorrect">Salah</option><option value="verified_blank">Kosong terverifikasi</option><option value="reviewed">Ditinjau</option><option value="unreadable">Tidak terbaca</option><option value="unsupported">Belum didukung</option><option value="unmapped">Belum dipetakan</option><option value="needs_review">Perlu tinjauan</option></select></label>{selectedAnswer.rubric.map(criterion=><div className="criterion-review-row" key={criterion.id}><div><b>{criterion.id} · {criterion.description}</b><small>Maksimum {criterion.max_points} poin</small></div><select value={reviewCredits[criterion.id]??'0'} disabled={Boolean(overrideRaw)} onChange={e=>setReviewCredits(c=>({...c,[criterion.id]:e.target.value}))}>{criterion.credit_levels.map(level=><option key={level} value={level}>{level} · {criterion.anchors[level]}</option>)}</select></div>)}<div className="override-fields"><label>Override raw (opsional)<input type="number" min="0" step="0.01" value={overrideRaw} onChange={e=>{setOverrideRaw(e.target.value);setAnswerStatus(e.target.value?'reviewed':'partially_correct');}} placeholder="Kosongkan untuk memakai kriteria"/></label><label>Alasan / catatan reviewer<textarea value={reviewReason} onChange={e=>setReviewReason(e.target.value)} placeholder="Wajib untuk override atau jawaban kosong."/></label></div><div className="review-footer"><span className="tiny muted">Tidak ada pembobotan di sini; nilai dihitung dari rubrik.</span><button className="button primary" disabled={busy} onClick={saveReview}>Simpan keputusan <Icon name="check"/></button></div></div></div>}</div>
          </div>
          <div className="finalize-panel"><div><p className="eyebrow">PENGESAHAN NILAI</p><h2>{submission.final_snapshot?'Snapshot final terkunci':'Semua keputusan siap?'}</h2><p className="muted">Finalisasi memeriksa identitas, PDF, bukti, setiap kriteria, dan pekerjaan yang masih berjalan.</p></div><div className="finalize-side">{submission.review_revision&&<span className={`tag ${submission.review_revision.status==='finalized'?'tag-green':'tag-amber'}`}>Review {submission.review_revision.status} · v{submission.review_revision.version}</span>}<button className="button primary" disabled={busy||!submission.review_revision||submission.review_revision.status!=='draft'||!submission.document||submission.document.status!=='valid'} onClick={finalize}><Icon name="check"/> Sahkan nilai final</button></div></div>
        </section>}
      </div>
    </main>
  </div>;
}
