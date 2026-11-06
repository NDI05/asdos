import { useState } from 'react';

export type AutoRegion = {
  id:string; polygon:[number,number][]; region_type:string; excluded_from_mapping?:boolean;
  analysis?:{source?:string;label?:string|null;text?:string;mapping_flags?:string[];transcription_flags?:string[]};
};
type Props = {
  regions:AutoRegion[]; unassignedIds:string[]; autoCount:number; identityConfirmed:boolean;
  canStart:boolean; analysisDone:boolean; busy:boolean;
  questions:{question_id:string;label:string}[];
  onStart:()=>void; onConfirm:()=>void; onSelect:(id:string)=>void;
  onAssign:(id:string,questionId:string)=>void;
  onExclude:(id:string,excluded:boolean,reason:string)=>void;
};
const reasonLabels:Record<string,string> = {unknown_question_number:'Nomor tidak ada dalam daftar soal',duplicate_number:'Nomor muncul lebih dari sekali',
  number_unreadable_or_missing:'Nomor belum terbaca',uncertain_number:'Nomor belum pasti',
  overlapping_answer_regions:'Area bertumpang tindih',continuation_without_start:'Awal jawaban lanjutan belum ditemukan',
  number_ocr_disagreement:'Nomor dari pencarian area dan OCR berbeda',
  number_group_needs_review:'Urutan atau nomor perlu diperiksa',
  localization_repair_review:'Format deteksi diperbaiki; periksa semua area dan celah pada halaman'};
const reasonLabel = (flag:string) => reasonLabels[flag]??'Perlu ditinjau';

export default function AutoMappingReview(props:Props) {
  const [reasons,setReasons] = useState<Record<string,string>>({});
  const [targets,setTargets] = useState<Record<string,string>>({});
  const remaining = props.regions.filter(r=>props.unassignedIds.includes(r.id) || r.excluded_from_mapping);
  const repairNeedsReview = props.regions.some(r=>r.analysis?.mapping_flags?.includes('localization_repair_review'));
  if (!props.canStart && !props.analysisDone && !props.autoCount && !remaining.length) return null;
  return <section className="auto-mapping-review" aria-label="Tinjau pemetaan otomatis">
    <div className="auto-mapping-heading"><div><h2>Tinjau pemetaan jawaban</h2>
      <p>Area dan teks dari Qwen adalah draf. Periksa nomor dan gambar; perbaiki pemetaan yang tidak sesuai.</p></div>
      {props.canStart&&<button className="button secondary" disabled={props.busy} onClick={props.onStart}>Baca dan petakan otomatis</button>}
    </div>
    {repairNeedsReview&&<p className="warning-note">Deteksi diperbaiki setelah format gagal. Periksa seluruh halaman dan celah di antara kotak; tambahkan area yang terlewat sebelum memetakan jawaban.</p>}
    {props.autoCount>0&&<div className="auto-mapping-confirm"><span>{props.autoCount} nomor sudah diusulkan otomatis.</span>
      <button className="button primary" disabled={props.busy||!props.identityConfirmed} onClick={props.onConfirm}>Pemetaan sudah sesuai</button>
      {!props.identityConfirmed&&<small>Konfirmasikan identitas pada scan sebelum menyetujui pemetaan.</small>}
    </div>}
    {props.analysisDone&&props.regions.length===0&&<p className="warning-note">Area jawaban belum ditemukan. Tandai area secara manual pada preview.</p>}
    {remaining.filter(r=>!r.excluded_from_mapping).length>0&&<p>Area di bawah belum terhubung ke soal. Petakan ke nomor yang sesuai, atau kecualikan dengan alasan jika area tersebut duplikat atau bukan jawaban. Area yang dikecualikan tetap tersimpan dan bisa dikembalikan.</p>}
    {remaining.length>0&&<details id="unassigned-region-details" className="unassigned-region-details"><summary>{remaining.filter(r=>!r.excluded_from_mapping).length} area perlu dipetakan · tinjau area</summary>
    <div className="unassigned-region-list">{remaining.map((region,index)=><article key={region.id} className={region.excluded_from_mapping?'region-draft excluded':'region-draft'}>
      <div><b>{region.excluded_from_mapping?'Area dikecualikan':`Area belum dipetakan ${index+1}`}</b>
        <span>{region.analysis?.label?`Nomor terbaca: ${region.analysis.label}`:'Nomor belum dikenali'}</span></div>
      {region.analysis?.mapping_flags?.length? <p className="warning-note">{Array.from(new Set(region.analysis.mapping_flags.map(reasonLabel))).join(' · ')}</p>:null}
      {region.analysis?.text&&<p className="region-draft-text">{region.analysis.text}</p>}
      <button className="text-button" disabled={props.busy} onClick={()=>props.onSelect(region.id)}>Lihat dan pilih area ini</button>
      {!region.excluded_from_mapping&&<div className="region-assignment"><label>Petakan ke nomor<select
        value={targets[region.id]??''}
        onChange={e=>setTargets(old=>({...old,[region.id]:e.target.value}))}>
        <option value="">Pilih nomor soal</option>
        {props.questions.map(q=><option key={q.question_id} value={q.question_id}>{q.label}</option>)}</select></label>
        <button className="button secondary compact" disabled={props.busy||!props.identityConfirmed||!targets[region.id]}
          onClick={()=>props.onAssign(region.id,targets[region.id])}>Petakan area</button></div>}
      <label>Alasan peninjauan area<input value={reasons[region.id]??''} onChange={e=>setReasons(old=>({...old,[region.id]:e.target.value}))}
        placeholder="Contoh: duplikat area yang sudah dipetakan"/></label>
      <button className="quiet-button" disabled={props.busy||(reasons[region.id]??'').trim().length<3}
        onClick={()=>props.onExclude(region.id,!region.excluded_from_mapping,reasons[region.id].trim())}>
        {region.excluded_from_mapping?'Kembalikan sebagai area jawaban':'Kecualikan area'}</button>
    </article>)}</div></details>}
  </section>;
}
