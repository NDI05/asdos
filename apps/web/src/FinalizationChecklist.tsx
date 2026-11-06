type Answer = { question_id: string; label: string; mapping_status: string; transcript_stale: boolean;
  review: { status: string } | null };
type Props = { answers: Answer[]; unassignedCount: number; onQuestion: (id: string) => void; onRegions: () => void };

const pendingStatuses = new Set(['needs_review', 'unreadable', 'unsupported', 'unmapped']);

export default function FinalizationChecklist({answers, unassignedCount, onQuestion, onRegions}: Props) {
  const pending = answers.filter(a => !a.review || pendingStatuses.has(a.review.status)
    || a.mapping_status === 'auto_mapped'
    || (a.review.status !== 'verified_blank' && (a.transcript_stale || a.mapping_status === 'unmapped')));
  if (!pending.length && !unassignedCount) return null;
  return <section className="finalization-checklist" aria-label="Yang perlu diselesaikan sebelum pengesahan">
    <h3>Selesaikan sebelum mengesahkan nilai</h3>
    {unassignedCount > 0 && <div><p>{unassignedCount} area belum dipetakan atau dikecualikan. Periksa apakah area tersebut jawaban, duplikat, atau bukan jawaban.</p>
      <button className="text-button" type="button" onClick={onRegions}>Tinjau area yang belum dipetakan</button></div>}
    {pending.length > 0 && <div><p>Periksa pemetaan dan transkripsi, lalu simpan keputusan dosen untuk setiap nomor berikut.</p>
      <div className="finalization-question-links">{pending.map(a=><button className="button secondary compact" type="button" key={a.question_id}
        onClick={()=>onQuestion(a.question_id)}>Tinjau soal {a.label}</button>)}</div></div>}
  </section>;
}
