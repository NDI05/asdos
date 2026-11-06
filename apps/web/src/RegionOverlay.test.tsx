import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import RegionOverlay from './RegionOverlay';

describe('answer area labels',()=>{
  it('labels mapped and proposed areas, and exposes the selection state',()=>{
    const html=renderToStaticMarkup(<RegionOverlay regions={[
      {id:'r1',region_type:'answer',polygon:[[0.1,0.2],[0.3,0.2],[0.3,0.4],[0.1,0.4]]},
      {id:'r2',region_type:'answer',polygon:[[0.1,0.5],[0.3,0.5],[0.3,0.6],[0.1,0.6]],analysis:{label:'7'}}
    ]} selected={['r1']} answers={[{label:'3',region_ids:['r1']}]} onToggle={()=>{}}/>);
    expect(html).toContain('Soal 3'); expect(html).toContain('Usulan 7');
    expect(html).toContain('aria-pressed="true"'); expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('class="region-box selected');
  });
});
