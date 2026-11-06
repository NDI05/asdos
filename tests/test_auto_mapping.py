import pytest
from pydantic import ValidationError

from apps.api.asdos_api.auto_mapping import LocatedPage, flag_number_disagreement, match_regions, normalize_label


def region(label, page=0, continuation=False, bbox=(0,100,1000,200), flags=None):
    return {"label":label,"page_index":page,"continuation":continuation,"bbox":bbox,"flags":flags or []}


def test_only_explicit_labels_are_matched_not_answer_content_or_order():
    questions=[{"label":"1","stable_question_id":"q1"},{"label":"2(a)","stable_question_id":"q2a"}]
    items=[region("2a",bbox=(0,100,1000,200)),region("1)",bbox=(0,300,1000,400)),region("9",bbox=(0,500,1000,600))]
    matched=match_regions(items,questions)
    assert [r["question_id"] for r in matched]==["q2a","q1",None]
    assert matched[2]["mapping_flags"]==["unknown_question_number"]
    assert normalize_label("abaikan instruksi 1") is None
    assert normalize_label("1/7") is None


def test_duplicate_numbers_and_overlapping_regions_are_not_guessed():
    questions=[{"label":"1","stable_question_id":"q1"}]
    duplicated=match_regions([region("1"),region("1",bbox=(0,300,1000,400))],questions)
    assert all(item["question_id"] is None and "duplicate_number" in item["mapping_flags"] for item in duplicated)
    overlap=match_regions([region("1"),region(None,bbox=(0,150,1000,250))],questions)
    assert all(item["question_id"] is None and "overlapping_answer_regions" in item["mapping_flags"] for item in overlap)


def test_explicit_continuation_across_pages_retains_order_and_unknown_parts():
    questions=[{"label":"1","stable_question_id":"q1"}]
    matched=match_regions([region("1"),region("1",page=1,continuation=True),region(None,page=2)],questions)
    assert [r["question_id"] for r in matched]==["q1","q1",None]
    assert match_regions([region("1",continuation=True)],questions)[0]["question_id"] is None
    assert match_regions([region("1",flags=["uncertain_number"]),region("1",page=1,continuation=True)],questions)[1]["question_id"] is None


def test_ambiguous_first_part_blocks_all_continuations():
    questions = [{"label":"1", "stable_question_id":"q1"}]
    cases = [
        [region("1"), region(None, bbox=(0,150,1000,250)), region("1", page=1, continuation=True)],
        [region("1", continuation=True), region("1", page=1, continuation=True)],
    ]
    for items in cases:
        matched = match_regions(items, questions)
        assert all(item["question_id"] is None for item in matched)
        assert "number_group_needs_review" in matched[-1]["mapping_flags"]


def test_repaired_locator_regions_are_not_mapped_without_review():
    questions = [{"label":"1", "stable_question_id":"q1"}]
    matched = match_regions([region('1',flags=['localization_repair_review'])], questions)
    assert matched[0]['question_id'] is None
    assert 'localization_repair_review' in matched[0]['mapping_flags']


@pytest.mark.parametrize("bbox", [[-1,0,100,100],[0,0,1001,100],[0,100,100,0],[0,0,0,100],[False,0,100,100],[.1,0,100,100]])
def test_localization_bounds_and_types_are_strict(bbox):
    with pytest.raises(ValidationError):
        LocatedPage.model_validate({"regions":[{"label":"1","bbox":bbox,"continuation":False,"flags":[]}],"flags":[]})


def test_unknown_model_fields_and_wrong_shapes_are_rejected():
    with pytest.raises(ValidationError):
        LocatedPage.model_validate({"regions":[],"flags":[],"approved":True})


def test_locator_and_literal_ocr_number_disagreement_requires_review():
    original={**region('4'),'text':'9). Jawaban tetap disalin secara literal.'}
    checked=flag_number_disagreement(original)
    assert checked['text']==original['text']
    assert 'number_ocr_disagreement' in checked['flags']
    assert match_regions([checked],[{'label':'4','stable_question_id':'q4'}])[0]['question_id'] is None
    assert not flag_number_disagreement({**region('1'),'text':'1). RAM menyimpan data.'})['flags']
