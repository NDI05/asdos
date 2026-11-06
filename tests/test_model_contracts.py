"""Model protocol checks with explicit fake output, not inference accuracy."""
from pathlib import Path
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.api.asdos_api.model_adapters import Qwen3VLAdapter, transcription_flags, checkpoint_complete
from apps.api.asdos_api.rubric_generation import merge_generated
from packages.asdos_domain.scoring import DomainError


@pytest.mark.parametrize("text", ["[tidak terbaca]", "RAM [unreadable] SSD", "", " [ILLEGIBLE] "])
def test_uncertainty_is_not_a_successful_unflagged_transcript(text):
    adapter = Qwen3VLAdapter()
    with patch.object(adapter, "_load"), patch.object(adapter, "_provenance", return_value=None), patch.object(
            adapter, "_generate_independent_messages", return_value=[text]):
        segments, _ = adapter.transcribe([Path("tests/fixtures/synthetic_region.png").read_bytes()], "id")
    assert segments[0].flags
    assert segments[0].text == text.strip()


def test_normal_literal_text_has_no_uncertainty_flag():
    assert transcription_flags("RAM bersifat sementara; data hilang saat daya mati.") == ()


def test_identity_is_a_literal_unconfirmed_proposal_and_rejects_extra_fields():
    adapter = Qwen3VLAdapter()
    with patch.object(adapter, '_generate_independent_messages', return_value=['{"name":"Test","student_id":"00123"}']) as generate, \
         patch.object(adapter, '_provenance', return_value=None):
        result,_ = adapter.propose_identity(Path('tests/fixtures/synthetic_region.png').read_bytes())
        assert result == {'name':'Test','student_id':'00123'}
        assert 'rubrik' not in str(generate.call_args)
    with patch.object(adapter, '_generate_independent_messages', return_value=['{"name":"Test","student_id":"1","confirmed":true}']):
        with pytest.raises(ValueError):
            adapter.propose_identity(Path('tests/fixtures/synthetic_region.png').read_bytes())


@pytest.mark.parametrize("second_valid", [True, False])
def test_locator_retries_invalid_format_once_without_accepting_partial_boxes(second_valid):
    from apps.api.asdos_api.model_adapters import ModelUnavailable
    adapter = Qwen3VLAdapter()
    invalid = '{"regions":[{"label":"2","bbox":[47,],"continuation":false,"flags":[]}],"flags":[]}'
    valid = '{"regions":[{"label":"2","bbox":[47,200,957,400],"continuation":false,"flags":[]}],"flags":[]}'
    with patch.object(adapter, '_generate_independent_messages', side_effect=[[invalid],[valid if second_valid else invalid]]) as generate, \
         patch.object(adapter, '_provenance', return_value=None):
        if second_valid:
            result,_ = adapter.locate_answers(Path('tests/fixtures/synthetic_region.png').read_bytes(), 'id')
            assert result.regions[0].bbox == (47,200,957,400)
            assert 'localization_repair_review' in result.flags
        else:
            with pytest.raises(ModelUnavailable, match='Format area') as error:
                adapter.locate_answers(Path('tests/fixtures/synthetic_region.png').read_bytes(), 'id')
            assert error.value.code == 'LOCATOR_OUTPUT_INVALID'
        assert generate.call_count == 2
        assert 'data tidak tepercaya' in generate.call_args_list[1].args[0][0]['content']


def test_locator_does_not_accept_empty_retry_as_proof_page_is_blank():
    from apps.api.asdos_api.model_adapters import ModelUnavailable
    adapter = Qwen3VLAdapter()
    with patch.object(adapter, '_generate_independent_messages', side_effect=[['{"regions":['],['{"regions":[],"flags":["no_answer_regions"]}']]), \
         patch.object(adapter, '_provenance', return_value=None):
        with pytest.raises(ModelUnavailable) as error:
            adapter.locate_answers(Path('tests/fixtures/synthetic_region.png').read_bytes(), 'id')
        assert error.value.code == 'LOCATOR_OUTPUT_INVALID'


def test_manifest_is_not_equivalent_to_complete_weights(tmp_path):
    assert not checkpoint_complete(tmp_path, {"files": {"config.json": "hash"}})
    assert not checkpoint_complete(tmp_path, {"files": ["model.safetensors"]})
    assert not checkpoint_complete(tmp_path, {"files": {"model.safetensors": "hash"}})
    (tmp_path / "model.safetensors").write_bytes(b"test-only-fixture")
    assert checkpoint_complete(tmp_path, {"files": {"model.safetensors": "hash"}})
    assert not checkpoint_complete(tmp_path, {"files": {"../model.safetensors": "hash"}})


def test_generated_rubric_cannot_change_question_or_weight():
    seed = {"stable_question_id": "q1", "label": "1", "order": 1, "text": "Apa fungsi RAM?",
            "answer_type": "essay", "weight": "25"}
    rubric = {"reference_answer": "Menyimpan data kerja sementara.", "alternatives": [], "criteria": [
        {"id": "fungsi", "description": "Fungsi dan volatilitas", "max_points": "10",
         "credit_levels": ["0", "0.5", "1"], "anchors": {"0": "Salah", "0.5": "Sebagian", "1": "Lengkap"}}]}
    result = merge_generated([seed], [rubric])[0]
    assert result["weight"] == "25"
    assert result["text"] == seed["text"]
    with pytest.raises(ValueError):
        merge_generated([seed], [{**rubric, "weight": "100"}])
    with pytest.raises(ValueError):
        merge_generated([seed], [])


def test_generation_sees_questions_only_and_validates_schema():
    adapter = Qwen3VLAdapter()
    value = '{"reference_answer":"Data kerja sementara.","alternatives":[],"criteria":[{"id":"ram","description":"Fungsi","max_points":"10","credit_levels":["0","1"],"anchors":{"0":"Salah","1":"Benar"}}]}'
    with patch.object(adapter, "_generate_independent_messages", return_value=[value]) as call, patch.object(
            adapter, "_provenance", return_value=SimpleNamespace(device="test")):
        output, _ = adapter.generate_rubrics([{"text": "Apa RAM?", "student_answer": "PRIVATE_SHOULD_NOT_PASS"}], "id")
    assert output[0]["reference_answer"]
    assert "PRIVATE_SHOULD_NOT_PASS" not in str(call.call_args)


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_grader_repairs_schema_once_without_relaxing_evidence(repair_succeeds):
    adapter = Qwen3VLAdapter()
    valid = {"schema_version": "grade-proposal.v1", "question_id": "q1", "status": "proposed",
             "criteria": [{"criterion_id": "ram", "credit": "1", "label": "met", "evidence_refs": [
                 {"segment_id": "s1", "region_id": "r1", "start": 0, "end": 3}], "rationale": "Bukti sintetis."}],
             "flags": []}
    invalid = {**valid, "criteria": [{**valid["criteria"][0], "evidence_refs": ["s1"]}]}
    outputs = [json.dumps(invalid), json.dumps(valid if repair_succeeds else invalid)]
    with patch.object(adapter, "_load"), patch.object(adapter, "_provenance", return_value=None), patch.object(
            adapter, "_generate_independent_messages", side_effect=[[o] for o in outputs]) as generate:
        kwargs = dict(question_id="q1", question={"question_id": "q1", "text": "Apa RAM?"},
                      rubric={"criteria": [{"criterion_id": "ram", "description": "Fungsi", "max_points": "1",
                                            "credit_levels": ["0", "1"], "anchors": {"0": "Salah", "1": "Benar"}}]},
                      transcript="RAM", segments={"s1": "RAM"}, valid_region_ids=["r1"],
                      evidence_catalog=[{"segment_id": "s1", "region_id": "r1", "text": "RAM"}])
        if repair_succeeds:
            proposal, _ = adapter.grade(**kwargs)
            assert proposal == valid
        else:
            with pytest.raises(DomainError, match="after one schema repair"):
                adapter.grade(**kwargs)
        assert generate.call_count == 2
        data = json.loads(generate.call_args_list[0].args[0][1]["content"])["data"]
        assert data["evidence_catalog"][0]["full_segment_ref"]["end"] == 3
