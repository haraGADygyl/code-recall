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


def test_length_imbalance_measures_gap_to_longest_distractor() -> None:
    question = make_question(
        correct_answer="x" * 60,
        distractors=["y" * 40, "z" * 45, "w" * 30],
    )

    assert question.length_imbalance == 15


def test_length_imbalance_is_negative_when_correct_answer_is_short() -> None:
    question = make_question(
        correct_answer="x" * 20,
        distractors=["y" * 40, "z" * 45, "w" * 30],
    )

    assert question.length_imbalance == -25


def test_conspicuously_long_correct_answer_is_unbalanced() -> None:
    question = make_question(
        correct_answer="x" * 114,
        distractors=["y" * 71, "z" * 61, "w" * 57],
    )

    assert not question.has_balanced_answers


def test_similar_length_answers_are_balanced() -> None:
    question = make_question(
        correct_answer="x" * 84,
        distractors=["y" * 85, "z" * 76, "w" * 65],
    )

    assert question.has_balanced_answers


def test_terse_answers_are_never_penalized() -> None:
    """Short token answers such as PUT versus POST must not trip the length check."""
    question = make_question(correct_answer="PUT", distractors=["POST", "PATCH", "GET"])

    assert question.has_balanced_answers


def test_long_answers_are_judged_on_relative_difference() -> None:
    """A 12-character gap is a giveaway among short answers but noise among long ones."""
    question = make_question(
        correct_answer="x" * 131,
        distractors=["y" * 119, "z" * 110, "w" * 85],
    )

    assert question.has_balanced_answers
