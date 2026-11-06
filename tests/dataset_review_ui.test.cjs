const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
class Element {
 constructor(){this.value='';this.checked=false;this.width=100;this.height=80;this.complete=true;this.naturalWidth=100;this.handlers={};this.style={};this.children=[];this.textContent=''}
 addEventListener(k,fn){this.handlers[k]=fn}
 replaceChildren(...c){this.children=c}
 setAttribute(k,v){this[k]=v}
 append(e){this.children.push(e)}
 getContext(){return {drawImage(){}}}
 getBoundingClientRect(){return {left:0,top:0,width:200,height:160}}
 setPointerCapture(){}
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('line editor transforms display coordinates, invalidates confirmation and saves separately',async()=>{
 const elements=new Map();const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
 const lines={revision:0,page_review_revision:1,split:'train',coverage_confirmed:true,lines:[{line_id:'l0',text:'abc',bbox_pixels:[1,2,90,40],kind:'answer',confirmed:true,reason:''}]};
 let saved;
 const context={location:{hash:'#token',pathname:'/'},history:{replaceState(){}},window:{addEventListener(){}},crypto:{randomUUID:()=> 'new'},confirm:()=>true,
 document:{getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element()},
 fetch:async(url,options)=>{let data;
 if(url==='/api/pages')data=[{page_id:'p0',reviewed:false}];
 else if(url==='/api/page/p0')data={page:{image_width_px:100,image_height_px:80},review:{revision:1,writer_id:'w1',submission_id:'s1',student_name:'',student_id:'001',transcript:'',notes:'',identity_confirmed:true,transcript_reviewed:false}};
 else if(options?.method==='POST'){saved=JSON.parse(options.body);data={...saved,revision:1}}
 else data=structuredClone(lines);
 return {ok:true,json:async()=>data};}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('scripts/dataset_review.js','utf8'),context);
 await flush();await flush();
 assert.equal(get('line_text').value,'abc');
 get('overlay').onpointerdown({clientX:20,clientY:40,pointerId:1});
 get('overlay').onpointerup({clientX:180,clientY:100,pointerId:1});
 assert.equal(get('left').value,10);assert.equal(get('top').value,20);
 assert.equal(get('right').value,90);assert.equal(get('bottom').value,50);
 assert.equal(get('line_confirmed').checked,false);assert.equal(get('coverage').checked,false);
 get('line_text').value='corrected';get('line_text').handlers.change();
 get('line_confirmed').checked=true;get('line_confirmed').onchange();
 get('coverage').checked=true;get('coverage').onchange();
 await get('save_lines').onclick();
 assert.deepEqual(saved.lines[0].bbox_pixels,[10,20,90,50]);assert.equal(saved.lines[0].text,'corrected');
 assert.equal(saved.page_review_revision,1);assert.equal(saved.lines[0].confirmed,true);
 assert.match(get('line_status').textContent,/tersimpan/);
 get('add_line').onclick();assert.equal(get('line_kind').value,'unreviewed');
});
