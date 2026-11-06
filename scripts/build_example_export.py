from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from apps.api.asdos_api.exporter import build_workbook


def main() -> int:
    questions = [("q1", "1", "20", "8", "16"), ("q2", "2", "30", "6", "18"), ("q3", "3", "50", "9", "45")]
    payload = {
        "schema": "asdos-export.v1", "snapshot_id": "snapshot-synthetic-001", "mode": "final",
        "assessment": {"id": "assessment-synthetic-001", "title": "Ujian Sintetis — Contoh"},
        "revision_id": "revision-synthetic-001",
        "questions": [{"id": qid, "label": label, "order": idx, "text": f"Jelaskan konsep {label}.", "weight": weight, "max_raw": "10"}
                      for idx, (qid, label, weight, _, _) in enumerate(questions, start=1)],
        "summary": [["submission-synthetic-001", "0012345678", "Mahasiswa Contoh", 1, "16", "18", "45", "79", "79.00", "finalized", "snapshot-synthetic-001"]],
        "question_details": [], "criterion_details": [], "transcriptions": [], "rubric": [],
        "history": [["event-synthetic-001", "submission-synthetic-001", "submission.finalized", "Dosen Contoh", "2026-11-03T12:00:00+00:00", "review-synthetic-001", "snapshot-synthetic-001", None]],
        "info": {"project": "ASDOS", "assessment": "Ujian Sintetis — Contoh", "kelas": "Fixture sintetis", "mode": "FINAL",
                 "assessment_revision_id": "revision-synthetic-001", "assessment_revision_sequence": "1", "w_total": "100",
                 "skala": "0–100", "pembulatan": "ROUND_HALF_UP, 2 desimal", "cakupan": "1 submission sintetis",
                 "final_count": "1", "pending_count": "0", "dibuat_pada": datetime.now(timezone.utc).isoformat(),
                 "catatan_kontribusi": "Data sintetis; tidak berisi scan atau identitas mahasiswa nyata."},
        "metadata": {"schema":"asdos-export.v1", "scoring_policy":"asdos-weighted.v1", "software_release":"0.1.0",
                     "git_commit":"unavailable", "model_runs":[], "mode":"final",
                     "export_snapshot_id":"snapshot-synthetic-001", "sample_data":"synthetic"},
    }
    for index, (question_id, label, weight, raw, contribution) in enumerate(questions, start=1):
        credit = str(Decimal(raw) / Decimal("10"))
        region_id, segment_id = f"region-synthetic-{index:02d}", f"segment-synthetic-{index:02d}"
        transcript = f"Jawaban sintetis nomor {label} yang sesuai sebagian dengan konsep acuan."
        payload["question_details"].append(["submission-synthetic-001", "0012345678", question_id, label,
            raw, "10", weight, contribution, "partially_correct", "reviewed_criteria", "finalized", None, "review-synthetic-001"])
        payload["criterion_details"].append(["submission-synthetic-001", question_id, "concept", credit, "10", raw,
            [{"segment_id":segment_id,"start":0,"end":len(transcript),"region_id":region_id}], "Bukti sintetik memenuhi sebagian kriteria.", "human"])
        payload["transcriptions"].append(["submission-synthetic-001", question_id, segment_id, region_id, index, 1,
            transcript, [], f"transcription-synthetic-{index:02d}"])
        payload["rubric"].append(["revision-synthetic-001", question_id, label, f"Jelaskan konsep {label}.", weight, "10", "concept",
            "Konsep inti dijelaskan sesuai jawaban acuan.", "10", {"0":"Tidak ada atau keliru", "0.5":"Sebagian tepat", "1":"Lengkap dan tepat"},
            f"Jawaban acuan {label}.", []])
    output = Path(__file__).resolve().parents[1] / "examples" / "ASDOS_ujian_sintetis_final.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_workbook(payload))
    print(f"Workbook sintetis dibuat: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
