import pytest
from pydantic import ValidationError

from code_recall.domain import MultipleChoiceQuestion


def make_question(**overrides: object) -> MultipleChoiceQuestion:
    data: dict[str, object] = {
        "question": "What does an event loop do?",
        "correct_answer": "It schedules and runs asynchronous tasks.",
        "distractors": [
            "It compiles Python into machine code.",
            "It creates one process for every function.",
            "It replaces all blocking operations with threads.",
        ],
        "explanation": "The event loop coordinates ready asynchronous tasks and callbacks.",
    }
    data.update(overrides)
    return MultipleChoiceQuestion.model_validate(data)


def test_valid_question_normalizes_and_exposes_answers() -> None:
    question = make_question(question="  What is asyncio?  ")

    assert question.question == "What is asyncio?"
    assert len(question.all_answers) == 4
    assert question.all_answers[0] == question.correct_answer


@pytest.mark.parametrize(
    "distractors",
    [["One", "Two"], ["One", "Two", "Three", "Four"]],
)
def test_requires_exactly_three_distractors(distractors: list[str]) -> None:
    with pytest.raises(ValidationError):
        make_question(distractors=distractors)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("question", "   "),
        ("correct_answer", "   "),
        ("distractors", ["One", "   ", "Three"]),
        ("explanation", "   "),
    ],
)
def test_rejects_blank_content(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        make_question(**{field: value})


def test_rejects_duplicate_answers_case_insensitively() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        make_question(
            correct_answer="The event loop schedules tasks.",
            distractors=["the event loop schedules tasks.", "It compiles code.", "It creates processes."],
        )


@pytest.mark.parametrize("answer", ["All of the above", "None of the above."])
def test_rejects_catch_all_answers(answer: str) -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        make_question(distractors=[answer, "First", "Second"])


def test_rejects_excessively_long_content() -> None:
    with pytest.raises(ValidationError):
        make_question(question="x" * 501)
