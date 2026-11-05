"""Prompt templates and LLM calls that return answers with cited sources or a refusal.

Prompts are versioned files in lab1/prompts/<name>/<version>.md (audit M2); the version and
sha256 of the exact text are recorded in every trace.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from flutter_rag.config import LAB1_DIR
from flutter_rag.errors import UpstreamError
from flutter_rag.gemini_errors import to_upstream
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.retry import call_with_retries
from flutter_rag.runconfig import GenerationConfig

USER_SEPARATOR = "---USER---"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    user_template: str
    sha256: str

    def render_user(self, *, context: str, question: str) -> str:
        return self.user_template.replace("{context}", context).replace("{question}", question)


def load_prompt(name: str, version: str) -> Prompt:
    text = (LAB1_DIR / "prompts" / name / f"{version}.md").read_text(encoding="utf-8")
    system, _, user = text.partition(USER_SEPARATOR)
    if not user:
        raise ValueError(f"prompt {name}/{version} has no {USER_SEPARATOR} section")
    return Prompt(
        name, version, system.strip(), user.strip(), hashlib.sha256(text.encode()).hexdigest()
    )


class LLMAnswer(BaseModel):
    status: Literal["answered", "insufficient_context"]
    answer: str
    citations: list[int]


@dataclass
class LLMResult:
    parsed: LLMAnswer
    model_version: str | None
    usage: dict[str, int]
    raw_text: str


class GeminiLLM:
    def __init__(self, api_key: str, cfg: GenerationConfig, limiter: RateLimiter | None = None):
        self.cfg = cfg
        self.model_id = cfg.model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(cfg.timeout_s * 1000)),
        )
        self._limiter = limiter or RateLimiter(max_rpm=None, max_tpm=None)

    def generate(self, prompt: Prompt, user_text: str) -> LLMResult:
        config = types.GenerateContentConfig(
            system_instruction=prompt.system,
            temperature=self.cfg.temperature,
            max_output_tokens=self.cfg.max_output_tokens,
            response_mime_type="application/json",
            response_schema=LLMAnswer,
        )

        def call() -> types.GenerateContentResponse:
            self._limiter.acquire()
            return self._client.models.generate_content(
                model=self.model_id, contents=user_text, config=config
            )

        resp = call_with_retries(call, translate=to_upstream, attempts=3)
        text = resp.text or ""
        try:
            parsed = LLMAnswer.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise UpstreamError(
                "gemini", "bad_request", f"model returned invalid JSON: {text[:120]!r}"
            ) from exc
        u = resp.usage_metadata
        usage = (
            {
                "input": u.prompt_token_count or 0,
                "output": u.candidates_token_count or 0,
                "total": u.total_token_count or 0,
            }
            if u
            else {}
        )
        return LLMResult(parsed, resp.model_version, usage, text)
