"""FAKE providers for offline tests.

Nothing here calls a real API. Tests that use these fakes check our pipeline logic
(idempotency, filtering, citation validation, error mapping); they are NOT API smoke
tests and do not prove that Gemini, GitHub or Langfuse work.
"""

from __future__ import annotations

import hashlib
import math

from flutter_rag.embeddings import EmbedStats
from flutter_rag.errors import UpstreamError
from flutter_rag.generation import LLMAnswer, LLMResult
from flutter_rag.grabber.github import TreeEntry

CONTENT = "sites/docs/src/content/"
INCLUDES = "sites/docs/src/_includes/"


def blob(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


class FakeGitHub:
    """In-memory repository: {path: text}. Counts raw downloads."""

    def __init__(self, files: dict[str, str], commit: str = "c1"):
        self.files = dict(files)
        self.commit = commit
        self.downloads = 0
        self.requests = 0

    def resolve_commit(self, ref: str) -> str:
        return self.commit

    def list_tree(self, commit_sha: str) -> list[TreeEntry]:
        return [TreeEntry(p, blob(t), len(t)) for p, t in self.files.items()]

    def fetch_raw(self, commit_sha: str, path: str) -> str:
        self.downloads += 1
        return self.files[path]

    def close(self) -> None:
        pass


class FakeEmbedder:
    """Deterministic bag-of-words vectors: texts sharing words get similar vectors."""

    def __init__(self, dims: int = 64):
        self.model_id = "fake-embedding"
        self.dimensions = dims
        self.stats = EmbedStats()

    def embed(self, texts, task):
        self.stats.api_calls += 1
        self.stats.texts_sent += len(texts)
        out = []
        for t in texts:
            v = [0.0] * self.dimensions
            for w in t.lower().split():
                h = int(hashlib.md5(w.strip(".,:;!?()[]`").encode()).hexdigest(), 16)
                v[h % self.dimensions] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class FakeLLM:
    """Returns a scripted LLMAnswer; can raise an UpstreamError instead."""

    def __init__(self, answer: LLMAnswer | None = None, error: UpstreamError | None = None):
        self.answer = answer or LLMAnswer(status="answered", answer="Answer [1].", citations=[1])
        self.error = error
        self.calls = 0
        self.model_id = "fake-llm"

    def generate(self, prompt, user_text):
        self.calls += 1
        self.last_user_text = user_text
        if self.error:
            raise self.error
        return LLMResult(self.answer, "fake-llm-v", {"input": 1, "output": 1, "total": 2}, "{}")
