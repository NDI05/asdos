type Evidence = { segment_id: string; region_id: string; start: number; end: number };
type CriterionProposal = { criterion_id: string; credit: string; rationale: string; evidence_refs: Evidence[] };
type Props = { criteria: CriterionProposal[]; rubric: { id: string; description: string }[];
  segments: { segment_id: string; region_id: string; text: string }[]; stale: boolean };

export default function GradeProposalView({criteria, rubric, segments, stale}: Props) {
  return <div className="proposal-note" aria-label="Rincian usulan penilaian">
    <b>{stale ? 'Usulan kedaluwarsa · buat usulan baru' : 'Usulan tersedia untuk ditinjau'}</b>
    <p>Periksa kriteria dan bukti sebelum menyimpan keputusan dosen.</p>
    {criteria.map(item => <div className="proposal-criterion" key={item.criterion_id}>
      <strong>{rubric.find(c => c.id === item.criterion_id)?.description || item.criterion_id}</strong>
      <span> Kredit: {item.credit}</span>
      <p>{item.rationale}</p>
      {item.evidence_refs.map((ref, index) => {
        const segment = segments.find(s => s.segment_id === ref.segment_id && s.region_id === ref.region_id);
        const excerpt = segment ? Array.from(segment.text).slice(ref.start, ref.end).join('') : '';
        return <blockquote key={`${ref.segment_id}-${index}`}>{excerpt || 'Bukti tidak tersedia pada transkripsi aktif.'}</blockquote>;
      })}
    </div>)}
  </div>;
}
