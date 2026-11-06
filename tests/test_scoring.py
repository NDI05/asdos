import unittest
from decimal import Decimal

from packages.asdos_domain.scoring import (
    AnswerGrade,
    CriterionSpec,
    DomainError,
    QuestionSpec,
    calculate_grade,
    decimal_value,
    validate_criterion_proposal,
)


def one_criterion_question(question_id, label, order, weight):
    criterion = CriterionSpec("concept", "Key concept", Decimal("10"),
        (Decimal("0"), Decimal("0.5"), Decimal("1")),
        {"0": "missing/wrong", "0.5": "partial", "1": "complete"})
    return QuestionSpec(question_id, label, order, Decimal(str(weight)), (criterion,))


class ScoringTests(unittest.TestCase):
    def test_reference_example_weights_20_30_50_is_79(self):
        questions = [one_criterion_question("q1", "1", 1, 20), one_criterion_question("q2", "2", 2, 30), one_criterion_question("q3", "3", 3, 50)]
        answers = {"q1": AnswerGrade("q1", "reviewed", override_raw=Decimal("8"), override_reason="synthetic example"),
                   "q2": AnswerGrade("q2", "reviewed", override_raw=Decimal("6"), override_reason="synthetic example"),
                   "q3": AnswerGrade("q3", "reviewed", override_raw=Decimal("9"), override_reason="synthetic example")}
        result = calculate_grade(questions, answers, final=True)
        self.assertEqual(result.contributions, {"q1": Decimal("16"), "q2": Decimal("18"), "q3": Decimal("45")})
        self.assertEqual(result.final_score, Decimal("79.00"))

    def test_reference_example_weights_2_3_5_and_raw_8_6_9_is_79(self):
        questions = [one_criterion_question("q1", "1", 1, 2), one_criterion_question("q2", "2", 2, 3), one_criterion_question("q3", "3", 3, 5)]
        answers = {"q1": AnswerGrade("q1", "reviewed", override_raw=Decimal("8"), override_reason="manual"),
                   "q2": AnswerGrade("q2", "reviewed", override_raw=Decimal("6"), override_reason="manual"),
                   "q3": AnswerGrade("q3", "reviewed", override_raw=Decimal("9"), override_reason="manual")}
        result = calculate_grade(questions, answers, final=True)
        self.assertEqual(result.contributions, {"q1": Decimal("1.6"), "q2": Decimal("1.8"), "q3": Decimal("4.5")})
        self.assertEqual(result.final_score, Decimal("79.00"))

    def test_all_wrong_and_verified_blank_are_zero(self):
        question = one_criterion_question("q1", "1", 1, 1)
        for status, reason in [("incorrect", None), ("verified_blank", "checked empty")]:
            result = calculate_grade([question], {"q1": AnswerGrade("q1", status, {"concept": Decimal("0")}, override_reason=reason)}, final=True)
            self.assertEqual(result.final_score, Decimal("0.00"))

    def test_null_and_unresolved_answers_block_final(self):
        question = one_criterion_question("q1", "1", 1, 1)
        result = calculate_grade([question], {"q1": AnswerGrade("q1", "unreadable")}, final=True)
        self.assertIsNone(result.final_score)
        self.assertTrue(result.blockers)

    def test_score_boundaries(self):
        question = one_criterion_question("q1", "1", 1, 7)
        full = calculate_grade([question], {"q1": AnswerGrade("q1", "correct", {"concept": Decimal("1")})}, final=True)
        self.assertEqual(full.final_score, Decimal("100.00"))
        rejected = calculate_grade([question], {"q1": AnswerGrade("q1", "reviewed", override_raw=Decimal("10.1"), override_reason="x")}, final=True)
        self.assertIsNone(rejected.final_score)
        self.assertTrue(rejected.blockers)
        with self.assertRaises(DomainError):
            decimal_value("NaN")

    def test_positive_proposal_must_cite_active_transcribed_evidence(self):
        question = one_criterion_question("q1", "1", 1, 1)
        payload = {"schema_version":"grade-proposal.v1", "question_id":"q1", "status":"proposed", "flags":[],
            "criteria":[{"criterion_id":"concept", "credit":"1", "label":"met", "evidence_refs":[{"segment_id":"s1", "start":0, "end":4, "region_id":"r1"}], "rationale":"Concept matches."}]}
        accepted = validate_criterion_proposal(payload, question_id="q1", criteria=question.criteria, segments={"s1":"Jawab"}, valid_region_ids={"r1"})
        self.assertEqual(accepted[0]["credit"], "1")
        with self.assertRaises(DomainError):
            validate_criterion_proposal(payload, question_id="q1", criteria=question.criteria, segments={"s1":"Jawab"}, valid_region_ids=set())


if __name__ == "__main__":
    unittest.main()
