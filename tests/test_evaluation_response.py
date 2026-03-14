import pytest
from pydantic import ValidationError

from main import EvaluationResponse, SystemDesignEvaluationResponse


class TestEvaluationResponse:
    def test_valid_pass_response(self) -> None:
        resp = EvaluationResponse(
            result="PASS",
            explanation="The answer correctly identifies the concept.",
            answer="Polymorphism allows objects of different types to be treated uniformly.",
        )
        assert resp.result == "PASS"
        assert resp.explanation == "The answer correctly identifies the concept."

    def test_valid_fail_response(self) -> None:
        resp = EvaluationResponse(
            result="FAIL",
            explanation="The answer confuses inheritance with composition.",
            answer="Inheritance is an is-a relationship between classes.",
        )
        assert resp.result == "FAIL"

    def test_missing_result_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            EvaluationResponse(
                explanation="Some explanation.",
                answer="Some answer.",
            )  # type: ignore[call-arg]

    def test_missing_explanation_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            EvaluationResponse(
                result="PASS",
                answer="Some answer.",
            )  # type: ignore[call-arg]

    def test_missing_answer_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            EvaluationResponse(
                result="PASS",
                explanation="Some explanation.",
            )  # type: ignore[call-arg]

    def test_from_json(self) -> None:
        json_str = '{"result": "PASS", "explanation": "Correct.", "answer": "The GIL."}'
        resp = EvaluationResponse.model_validate_json(json_str)
        assert resp.result == "PASS"
        assert resp.answer == "The GIL."

    def test_invalid_json_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            EvaluationResponse.model_validate_json('{"result": "PASS"}')


class TestSystemDesignEvaluationResponse:
    def test_valid_high_score(self) -> None:
        resp = SystemDesignEvaluationResponse(
            score=9,
            explanation="Excellent coverage of scalability and trade-offs.",
            answer="A comprehensive reference answer.",
        )
        assert resp.score == 9
        assert resp.explanation == "Excellent coverage of scalability and trade-offs."

    def test_valid_low_score(self) -> None:
        resp = SystemDesignEvaluationResponse(
            score=2,
            explanation="Major gaps in understanding.",
            answer="The correct approach involves...",
        )
        assert resp.score == 2

    def test_score_below_minimum_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            SystemDesignEvaluationResponse(
                score=0,
                explanation="Some explanation.",
                answer="Some answer.",
            )

    def test_score_above_maximum_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            SystemDesignEvaluationResponse(
                score=11,
                explanation="Some explanation.",
                answer="Some answer.",
            )

    def test_missing_score_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            SystemDesignEvaluationResponse(
                explanation="Some explanation.",
                answer="Some answer.",
            )  # type: ignore[call-arg]

    def test_missing_explanation_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            SystemDesignEvaluationResponse(
                score=7,
                answer="Some answer.",
            )  # type: ignore[call-arg]

    def test_missing_answer_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            SystemDesignEvaluationResponse(
                score=7,
                explanation="Some explanation.",
            )  # type: ignore[call-arg]

    def test_from_json(self) -> None:
        json_str = '{"score": 8, "explanation": "Good coverage.", "answer": "Reference answer."}'
        resp = SystemDesignEvaluationResponse.model_validate_json(json_str)
        assert resp.score == 8
        assert resp.answer == "Reference answer."

    def test_invalid_json_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            SystemDesignEvaluationResponse.model_validate_json('{"score": 5}')
