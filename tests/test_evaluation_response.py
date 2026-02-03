import pytest
from pydantic import ValidationError

from main import EvaluationResponse


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
