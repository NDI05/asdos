import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import FinalizationChecklist from './FinalizationChecklist';
import { finalizationMessage } from './workflow';

const noop=()=>{};
describe('finalization guidance',()=>{
  it('separates unresolved regions from questions that still need a decision',()=>{
    const html=renderToStaticMarkup(<FinalizationChecklist answers={[
      {question_id:'q1',label:'1',mapping_status:'mapped',transcript_stale:false,review:{status:'needs_review'}},
      {question_id:'q2',label:'2',mapping_status:'mapped',transcript_stale:false,review:{status:'correct'}}
    ]} unassignedCount={2} onQuestion={noop} onRegions={noop}/>);
    expect(html).toContain('2 area belum dipetakan');
    expect(html).toContain('Tinjau soal 1');
    expect(html).not.toContain('Tinjau soal 2');
  });
  it('turns raw blockers into a short message without exposing IDs or duplicate reasons',()=>{
    const message=finalizationMessage(['1:missing_answer','1:needs_review','region:abc-123:unassigned']);
    expect(message).toContain('soal 1');
    expect(message).toContain('1 area');
    expect(message).not.toContain('abc-123');
    expect(message).not.toContain('missing_answer');
  });
});
