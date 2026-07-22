import asyncio
import logging
import subprocess
import time
from typing import Any, Protocol

import httpx
from ollama import AsyncClient as OllamaClient
from ollama import ResponseError as OllamaResponseError
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from code_recall.config import Settings
from code_recall.domain import ConfigurationError, MultipleChoiceQuestion, ProviderError

logger = logging.getLogger(__name__)
ChatMessage = dict[str, str]


class QuestionProvider(Protocol):
    async def prepare(self) -> None: ...

    async def generate(self, messages: list[ChatMessage]) -> MultipleChoiceQuestion: ...


class OpenAIQuestionProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AsyncOpenAI | None = None

    async def prepare(self) -> None:
        if not self.settings.OPENAI_API_KEY:
            raise ConfigurationError(
                "OPENAI_API_KEY is required for the OpenAI provider. Add it to .env or switch to Ollama."
            )

    async def generate(self, messages: list[ChatMessage]) -> MultipleChoiceQuestion:
        await self.prepare()
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.settings.OPENAI_MODEL_NAME,
            "messages": messages,
            "response_format": MultipleChoiceQuestion,
        }
        try:
            response = await client.chat.completions.parse(**kwargs)
        except AuthenticationError as error:
            raise ConfigurationError("OpenAI rejected the API key. Check OPENAI_API_KEY.") from error
        except PermissionDeniedError as error:
            raise ConfigurationError("OpenAI denied access to the configured model.") from error
        except RateLimitError as error:
            raise ProviderError("OpenAI rate or quota limit reached. Try again later or switch to Ollama.") from error
        except APITimeoutError as error:
            raise ProviderError("OpenAI did not respond before the request timeout.") from error
        except APIConnectionError as error:
            raise ProviderError("Could not connect to OpenAI. Check the network connection.") from error
        except APIStatusError as error:
            logger.warning("OpenAI request failed with status %s", error.status_code)
            raise ProviderError(f"OpenAI request failed with status {error.status_code}.") from error
        except LengthFinishReasonError as error:
            raise ProviderError("OpenAI reached its output limit. Retry with a shorter question.") from error
        except ContentFilterFinishReasonError as error:
            raise ProviderError("OpenAI blocked this question with its content filter.") from error
        except ValidationError as error:
            raise ProviderError("OpenAI returned an invalid multiple-choice question.") from error

        if not response.choices:
            raise ProviderError("OpenAI returned no completion choices.")
        message = response.choices[0].message
        parsed: MultipleChoiceQuestion | None = message.parsed
        if parsed is not None:
            return parsed
        if message.refusal:
            raise ProviderError("OpenAI refused to generate this question.")
        raise ProviderError("OpenAI returned no structured question.")

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.settings.OPENAI_API_KEY,
                timeout=self.settings.OPENAI_TIMEOUT_SECONDS,
                max_retries=self.settings.OPENAI_MAX_RETRIES,
            )
        return self._client


class OllamaQuestionProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        timeout = httpx.Timeout(settings.OLLAMA_TIMEOUT_SECONDS, connect=settings.OLLAMA_PROBE_TIMEOUT_SECONDS)
        self._client = OllamaClient(timeout=timeout)
        self._probe_client = OllamaClient(timeout=settings.OLLAMA_PROBE_TIMEOUT_SECONDS)
        self._started_process: subprocess.Popen[bytes] | None = None

    async def prepare(self) -> None:
        try:
            response = await self._probe_client.list()
        except (ConnectionError, httpx.ConnectError, httpx.TimeoutException):
            self._start_server()
            response = await self._wait_for_server()
        except OllamaResponseError as error:
            logger.warning("Ollama list request failed with status %s", error.status_code)
            raise ProviderError("Ollama rejected the model-list request.") from error

        model_names = {model.model for model in response.models if model.model}
        if self.settings.MODEL_NAME not in model_names:
            try:
                await self._client.pull(self.settings.MODEL_NAME)
            except (ConnectionError, httpx.HTTPError, OllamaResponseError) as error:
                raise ProviderError(f"Could not pull Ollama model {self.settings.MODEL_NAME}.") from error

    async def generate(self, messages: list[ChatMessage]) -> MultipleChoiceQuestion:
        try:
            response = await self._client.chat(
                model=self.settings.MODEL_NAME,
                messages=messages,
                format=MultipleChoiceQuestion.model_json_schema(),
                options={"temperature": 0},
                keep_alive=self.settings.OLLAMA_KEEP_ALIVE,
            )
            return MultipleChoiceQuestion.model_validate_json(response.message.content or "")
        except httpx.TimeoutException as error:
            raise ProviderError("Ollama did not respond before the request timeout.") from error
        except (ConnectionError, httpx.ConnectError) as error:
            raise ProviderError("Could not connect to Ollama. Start the Ollama service and try again.") from error
        except OllamaResponseError as error:
            logger.warning("Ollama request failed with status %s", error.status_code)
            raise ProviderError("Ollama could not generate the question.") from error
        except ValidationError as error:
            raise ProviderError("Ollama returned an invalid multiple-choice question.") from error

    def _start_server(self) -> None:
        try:
            self._started_process = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError as error:
            raise ConfigurationError("Ollama is not installed or is not available in PATH.") from error
        except OSError as error:
            raise ProviderError("Could not start the Ollama service.") from error

    async def _wait_for_server(self) -> Any:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            try:
                return await self._probe_client.list()
            except (ConnectionError, httpx.ConnectError, httpx.TimeoutException):
                continue
            except OllamaResponseError as error:
                raise ProviderError("Ollama rejected the model-list request.") from error
        raise ProviderError("Timed out while starting the Ollama service.")
