from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class Provider(StrEnum):
    OPENAI = "openai"
    OLLAMA = "ollama"


class QuestionMode(StrEnum):
    ARTICLES = "articles"
    REST_API = "rest-api"
    FASTAPI = "fastapi"
    SYSTEM_DESIGN = "system-design"


MODE_LABELS: dict[QuestionMode, str] = {
    QuestionMode.ARTICLES: "Articles",
    QuestionMode.REST_API: "REST API Design",
    QuestionMode.FASTAPI: "FastAPI",
    QuestionMode.SYSTEM_DESIGN: "System Design",
}


class CodeRecallError(Exception):
    """Base class for errors that can be shown safely to the user."""


class ConfigurationError(CodeRecallError):
    """The application configuration cannot support the requested action."""


class ContentError(CodeRecallError):
    """Question source content could not be loaded safely."""


class ProviderError(CodeRecallError):
    """An LLM provider could not generate a question."""


class MultipleChoiceQuestion(BaseModel):
    question: str = Field(..., max_length=500, description="A concise technical question")
    correct_answer: str = Field(..., max_length=500, description="The single correct answer")
    distractors: list[str] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Three plausible wrong answers",
    )
    explanation: str = Field(
        ...,
        max_length=2_000,
        description="A concise explanation of why the correct answer is correct",
    )

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        """Normalize generated content and require four distinct answers."""
        self.question = self.question.strip()
        self.correct_answer = self.correct_answer.strip()
        self.distractors = [answer.strip() for answer in self.distractors]
        self.explanation = self.explanation.strip()

        if not self.question or not self.explanation or any(not answer for answer in self.all_answers):
            raise ValueError("Question, answers, and explanation must not be blank")

        normalized_answers = [answer.casefold() for answer in self.all_answers]
        if len(set(normalized_answers)) != 4:
            raise ValueError("The correct answer and distractors must be unique")

        forbidden_answers = {"all of the above", "none of the above"}
        if any(answer.casefold().rstrip(".") in forbidden_answers for answer in self.all_answers):
            raise ValueError("All/none-of-the-above answers are not allowed")

        return self

    @property
    def all_answers(self) -> list[str]:
        return [self.correct_answer, *self.distractors]


@dataclass(frozen=True, slots=True)
class SourceMaterial:
    mode: QuestionMode
    title: str
    content: str
    category: str | None = None


@dataclass(frozen=True, slots=True)
class QuestionSession:
    question: str
    answers: tuple[str, str, str, str]
    correct_index: int
    explanation: str
    source_title: str
    mode: QuestionMode
    provider: Provider
