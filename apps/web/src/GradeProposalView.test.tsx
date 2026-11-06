import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import GradeProposalView from './GradeProposalView';

describe('grade proposal review', () => {
  it('shows the proposed credit, rationale and exact Unicode evidence as text', () => {
    const html = renderToStaticMarkup(<GradeProposalView criteria={[{criterion_id:'c1',credit:'0.5',rationale:'Sebagian & aman',
      evidence_refs:[{segment_id:'s1',region_id:'r1',start:1,end:3}]}]}
      rubric={[{id:'c1',description:'Fungsi RAM'}]} segments={[{segment_id:'s1',region_id:'r1',text:'A😀B<skrip>'}]} stale={false}/>);
    expect(html).toContain('Fungsi RAM'); expect(html).toContain('0.5');
    expect(html).toContain('Sebagian &amp; aman'); expect(html).toContain('😀B');
    expect(html).not.toContain('<skrip>');
  });
});
