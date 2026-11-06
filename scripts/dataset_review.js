'use strict';
const token=location.hash.slice(1);history.replaceState(null,'',location.pathname);
const fields=['writer_id','submission_id','student_name','student_id','transcript','notes'];
const checks=['identity_confirmed','transcript_reviewed'];
const el=id=>document.getElementById(id);
let pages=[],current=0,revision=0,dirty=false,lineDirty=false,lineData=null,selected=0,pageInfo=null,busy=false,aiData=null;
const api=async(url,options={})=>{const r=await fetch(url,{...options,headers:{'X-Review-Token':token,...options.headers}});const d=await r.json();if(!r.ok)throw Error(d.error||'Permintaan gagal');return d};
const pageId=()=>pages[current].page_id;
const flagLabels={possible_identity:'Kemungkinan memuat identitas',inspect_header_privacy:'Periksa privasi header',very_small_crop:'Kotak sangat kecil',readers_disagree:'Dua pembaca memberi teks berbeda',second_reader_failed:'Pembaca pembanding gagal',empty_second_reader:'Pembaca pembanding tidak menghasilkan teks',overlapping_boxes:'Kotak saling bertumpang tindih',possible_same_line_fragment:'Potongan mungkin satu baris yang sama',unreadable:'Tulisan mungkin tidak terbaca'};

function show(e){el('status').textContent=e.message}
async function refresh(){pages=await api('/api/pages');el('page').replaceChildren(...pages.map(p=>{const o=document.createElement('option');o.value=p.page_id;o.textContent=p.page_id+(p.reviewed?' ✓':p.review_line_count?' ['+p.confirmed_lines+'/'+p.review_line_count+']':'');return o}))}
async function load(index){
 if(busy||index<0||index>=pages.length)return;
 if((dirty||lineDirty)&&!confirm('Perubahan belum disimpan. Pindah halaman?')){el('page').value=pageId();return}
 busy=true;
 try{
 const id=pages[index].page_id;const [d,l]=await Promise.all([api('/api/page/'+id),api('/api/lines/'+id)]);
 current=index;pageInfo=d.page;aiData=d.ai_review;lineData=l;selected=0;el('page').value=id;
 el('image').src='/image/'+id+'?token='+encodeURIComponent(token);
 const r=d.review;revision=r?r.revision:0;
 for(const f of fields)el(f).value=r?r[f]:'';
 for(const f of checks)el(f).checked=r?r[f]:false;
 if(!r&&d.draft)el('transcript').value=(d.draft.lines||[]).map(l=>l.text).join('\n');
 el('status').textContent=r?'Revisi identitas '+revision+' tersimpan.':'Draf belum ditinjau.';
 const identityChanged=l.page_review_revision!==revision;
 if(identityChanged){l.lines.forEach(v=>v.confirmed=false);l.coverage_confirmed=false;lineDirty=true}else lineDirty=false;
 el('line_status').textContent=identityChanged?'Identitas berubah. Periksa ulang konfirmasi baris.':'';
 el('coverage').checked=l.coverage_confirmed;el('split').value=l.split;
 dirty=false;renderLines();
 }finally{busy=false}
}
function active(){return lineData?.lines[selected]}
function activeAI(){const l=active();const ai=aiData?.lines.find(v=>v.line_id===l?.line_id);return ai&&l&&ai.bbox_pixels.every((v,i)=>v===l.bbox_pixels[i])?ai:null}
function renderLines(){
 el('line_list').replaceChildren(...lineData.lines.map((l,i)=>{const o=document.createElement('option');o.value=i;o.textContent=(i+1)+'. '+(l.confirmed?'✓ ':'')+l.kind+' — '+l.text.slice(0,55);return o}));
 el('line_list').value=selected;renderActive();draw();
}
function renderActive(){const l=active();const ai=activeAI();el('ai_text').textContent=ai?.second_reader_text??'Belum tersedia untuk baris ini.';el('ai_flags').textContent=ai?'Perlu diperiksa: '+ai.flags.map(f=>flagLabels[f]||f).join('; '):'';el('adopt_ai').disabled=!ai?.second_reader_text;if(!l){el('line_text').value='';el('crop').width=0;return}
 el('line_text').value=l.text;el('line_kind').value=l.kind;el('line_reason').value=l.reason;el('line_confirmed').checked=l.confirmed;
 ['left','top','right','bottom'].forEach((k,i)=>el(k).value=l.bbox_pixels[i]);crop();}
function crop(){const l=active(),im=el('image');if(!l||!im.complete||!im.naturalWidth)return;
 const [x,y,r,b]=l.bbox_pixels;const c=el('crop');c.width=Math.max(1,r-x);c.height=Math.max(1,b-y);c.getContext('2d').drawImage(im,x,y,r-x,b-y,0,0,r-x,b-y);}
function draw(){if(!pageInfo)return;const svg=el('overlay');svg.setAttribute('viewBox',`0 0 ${pageInfo.image_width_px} ${pageInfo.image_height_px}`);svg.replaceChildren();
 lineData.lines.forEach((l,i)=>{const [x,y,r,b]=l.bbox_pixels;const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');for(const [k,v] of Object.entries({x,y,width:r-x,height:b-y,fill:i===selected?'#13877622':'transparent',stroke:i===selected?'#d75416':l.kind==='identity'?'#d21342':'#18796e','stroke-width':i===selected?4:1.5}))rect.setAttribute(k,v);svg.append(rect)});}
function changeLine(){const l=active();if(!l)return;l.text=el('line_text').value;l.kind=el('line_kind').value;l.reason=el('line_reason').value;l.confirmed=false;
 l.bbox_pixels=['left','top','right','bottom'].map(k=>Number(el(k).value));lineDirty=true;el('coverage').checked=false;lineData.coverage_confirmed=false;renderLines();}
for(const id of ['line_text','line_kind','line_reason','left','top','right','bottom'])el(id).addEventListener('change',changeLine);
for(const id of ['line_text','line_reason','left','top','right','bottom'])el(id).addEventListener('input',()=>{if(active()){active().confirmed=false;el('line_confirmed').checked=false;lineData.coverage_confirmed=false;el('coverage').checked=false;lineDirty=true}});
el('line_confirmed').onchange=()=>{if(active()){active().confirmed=el('line_confirmed').checked;lineDirty=true;renderLines()}};
el('adopt_ai').onclick=()=>{const ai=activeAI();if(ai?.second_reader_text){el('line_text').value=ai.second_reader_text;changeLine()}};
el('line_list').onchange=()=>{selected=Number(el('line_list').value);renderActive();draw()};
el('coverage').onchange=()=>{lineData.coverage_confirmed=el('coverage').checked;lineDirty=true};
el('split').onchange=()=>{lineData.split=el('split').value;lineDirty=true};
el('add_line').onclick=()=>{if(!lineData)return;lineData.lines.push({line_id:'manual-'+crypto.randomUUID(),text:'',bbox_pixels:[0,0,Math.min(100,Number(pageInfo.image_width_px)),Math.min(40,Number(pageInfo.image_height_px))],kind:'unreviewed',confirmed:false,reason:''});selected=lineData.lines.length-1;lineDirty=true;lineData.coverage_confirmed=false;el('coverage').checked=false;renderLines()};
let drag=null;
function point(e){const b=el('overlay').getBoundingClientRect();return [Math.max(0,Math.min(Number(pageInfo.image_width_px),Math.round((e.clientX-b.left)/b.width*pageInfo.image_width_px))),Math.max(0,Math.min(Number(pageInfo.image_height_px),Math.round((e.clientY-b.top)/b.height*pageInfo.image_height_px)))];}
el('overlay').onpointerdown=e=>{if(!active())return;drag=point(e);el('overlay').setPointerCapture(e.pointerId)};
el('overlay').onpointerup=e=>{if(!drag)return;const end=point(e),start=drag;drag=null;const box=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.max(start[0],end[0]),Math.max(start[1],end[1])];if(box[0]===box[2]||box[1]===box[3])return;['left','top','right','bottom'].forEach((k,i)=>el(k).value=box[i]);changeLine()};
el('overlay').onpointercancel=()=>drag=null;
el('image').onload=()=>{draw();crop()};
for(const f of [...fields,...checks])el(f).addEventListener('input',()=>{dirty=true;if(['writer_id','submission_id','student_name','student_id'].includes(f))el('identity_confirmed').checked=false;if(f==='transcript')el('transcript_reviewed').checked=false});
el('prev').onclick=()=>load(current-1).catch(show);el('next').onclick=()=>load(current+1).catch(show);el('page').onchange=()=>load(pages.findIndex(p=>p.page_id===el('page').value)).catch(show);
el('zoom').oninput=e=>el('stage').style.width=e.target.value+'%';
el('save').onclick=async()=>{if(busy)return;try{const data={revision};for(const f of fields)data[f]=el(f).value;for(const f of checks)data[f]=el(f).checked;const r=await api('/api/page/'+pageId(),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});revision=r.revision;dirty=false;
 lineData.lines.forEach(l=>l.confirmed=false);lineData.coverage_confirmed=false;el('coverage').checked=false;lineDirty=true;renderLines();
 await refresh();el('page').value=pageId();el('status').textContent='Revisi '+revision+' tersimpan. Periksa kembali baris setelah perubahan identitas.'}catch(e){show(e)}};
el('save_lines').onclick=async()=>{if(dirty){el('line_status').textContent='Simpan identitas halaman terlebih dahulu.';return}try{const body={revision:lineData.revision,page_review_revision:revision,split:lineData.split,coverage_confirmed:el('coverage').checked,lines:lineData.lines};const r=await api('/api/lines/'+pageId(),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});lineData={...r};lineDirty=false;el('line_status').textContent='Review baris revisi '+r.revision+' tersimpan.'}catch(e){el('line_status').textContent=e.message}};
window.addEventListener('beforeunload',e=>{if(dirty||lineDirty){e.preventDefault();e.returnValue=''}});
refresh().then(()=>load(0)).catch(show);
