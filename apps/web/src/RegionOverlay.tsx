import type { AutoRegion } from './AutoMappingReview';
type Props={regions:AutoRegion[]; selected:string[]; answers:{label:string;region_ids:string[]}[]; onToggle:(id:string)=>void};
export default function RegionOverlay({regions,selected,answers,onToggle}:Props) {
  return <>{regions.map(region=>{
    const xs=region.polygon.map(p=>p[0]),ys=region.polygon.map(p=>p[1]);
    const left=Math.min(...xs),top=Math.min(...ys),width=Math.max(...xs)-left,height=Math.max(...ys)-top;
    const labels=answers.filter(a=>a.region_ids.includes(region.id)).map(a=>a.label);
    const name=labels.length?`Soal ${labels.join(', ')}`:region.analysis?.label?`Usulan ${region.analysis.label}`:'Belum dipetakan';
    return <button key={region.id} type="button" className={`region-box ${selected.includes(region.id)?'selected':''} ${region.excluded_from_mapping?'excluded':''}`}
      style={{left:`${left*100}%`,top:`${top*100}%`,width:`${width*100}%`,height:`${height*100}%`}}
      aria-label={`${name} · ${selected.includes(region.id)?'dipilih':'tidak dipilih'}`} aria-pressed={selected.includes(region.id)}
      onPointerDown={e=>e.stopPropagation()} onClick={()=>onToggle(region.id)}><span className="region-label">{name}</span></button>;
  })}</>;
}
