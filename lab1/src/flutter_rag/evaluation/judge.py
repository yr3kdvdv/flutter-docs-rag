"""LLM-as-a-Judge: correctness and faithfulness 1-5 with a short reason (contract §5.2).

Gemini structured output at temperature 0, prompt lab1/prompts/judge/<version>.md (versioned
like answer prompts). The judge model is separate from the generator and is recorded in
meta.json. Review [L3]: a judge of the same model family may be lenient, so these scores only
complement the deterministic checks and a manual review.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

from flutter_rag.errors import UpstreamError
from flutter_rag.gemini_errors import to_upstream
from flutter_rag.generation import Prompt, load_prompt
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.retry import call_with_retries

DEFAULT_JUDGE_MODEL = "gemini-3.1-flash-lite"  # reachable by a real request on 2026-11-06
DEFAULT_JUDGE_PROMPT = "v1"

_PLACEHOLDER = re.compile(r"\{(question|expected_answer|must_include|context|answer)\}")


class JudgeVerdict(BaseModel):
    """Response schema. Field order makes the model write the reason before the scores."""

    reason: str
    correctness: int
    faithfulness: int


@dataclass
class JudgeResult:
    correctness: int
    faithfulness: int
    reason: str
    model: str
    model_version: str | None
    usage: dict[str, int]
    raw_text: str
    user_text: str


class Judge(Protocol):
    model_id: str
    prompt: Prompt

    def judge(
        self,
        *,
        question: str,
        expected_answer: str,
        must_include: list[str],
        context: str,
        answer: str,
    ) -> JudgeResult: ...


def load_judge_prompt(version: str = DEFAULT_JUDGE_PROMPT) -> Prompt:
    return load_prompt("judge", version)


def render_judge_input(
    prompt: Prompt,
    *,
    question: str,
    expected_answer: str,
    must_include: list[str],
    context: str,
    answer: str,
) -> str:
    """Single-pass substitution: text inside the answer can't inject another placeholder."""
    values = {
        "question": question,
        "expected_answer": expected_answer,
        "must_include": "\n".join(f"- {m}" for m in must_include) or "(none)",
        "context": context or "(no excerpts)",
        "answer": answer,
    }
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], prompt.user_template)


def parse_verdict(text: str) -> JudgeVerdict:
    try:
        v = JudgeVerdict.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise UpstreamError(
            "gemini", "bad_request", f"judge returned invalid JSON: {text[:120]!r}"
        ) from exc
    for name in ("correctness", "faithfulness"):
        if not 1 <= getattr(v, name) <= 5:
            raise UpstreamError(
                "gemini", "bad_request", f"judge {name} out of range 1-5: {text[:120]!r}"
            )
    return v


class GeminiJudge:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_JUDGE_MODEL,
        prompt_version: str = DEFAULT_JUDGE_PROMPT,
        *,
        limiter: RateLimiter | None = None,
        timeout_s: float = 60.0,
        max_output_tokens: int = 512,
    ):
        from google import genai
        from google.genai import types

        self._types = types
        self.model_id = model
        self.prompt = load_judge_prompt(prompt_version)
        self.max_output_tokens = max_output_tokens
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000))
        )
        self._limiter = limiter or RateLimiter(max_rpm=12, max_tpm=None)  # free tier: 15 RPM

    def judge(
        self,
        *,
        question: str,
        expected_answer: str,
        must_include: list[str],
        context: str,
        answer: str,
    ) -> JudgeResult:
        types = self._types
        user_text = render_judge_input(
            self.prompt,
            question=question,
            expected_answer=expected_answer,
            must_include=must_include,
            context=context,
            answer=answer,
        )
        config = types.GenerateContentConfig(
            system_instruction=self.prompt.system,
            temperature=0.0,
            max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json",
            response_schema=JudgeVerdict,
        )

        def call():
            self._limiter.acquire()
            return self._client.models.generate_content(
                model=self.model_id, contents=user_text, config=config
            )

        resp = call_with_retries(call, translate=to_upstream, attempts=3)
        text = resp.text or ""
        v = parse_verdict(text)
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
        return JudgeResult(
            v.correctness,
            v.faithfulness,
            v.reason,
            self.model_id,
            resp.model_version,
            usage,
            text,
            user_text,
        )
