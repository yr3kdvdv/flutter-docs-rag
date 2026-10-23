"""Minimal GitHub client: resolve a ref to a commit, list the tree, download raw files."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from flutter_rag.errors import UpstreamError, kind_from_status

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MAX_RATE_LIMIT_WAIT_S = 60


@dataclass(frozen=True)
class TreeEntry:
    path: str
    blob_sha: str
    size: int


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, UpstreamError) and exc.retryable


class GitHubClient:
    def __init__(self, repo: str, token: str | None = None, timeout_s: float = 20.0):
        self.repo = repo
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "flutter-docs-rag"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._api = httpx.Client(base_url=API, headers=headers, timeout=timeout_s)
        self._raw = httpx.Client(
            base_url=RAW,
            headers={"User-Agent": "flutter-docs-rag"},
            timeout=timeout_s,
            limits=httpx.Limits(max_connections=16),
        )
        self.requests = 0

    def close(self) -> None:
        self._api.close()
        self._raw.close()

    @retry(
        retry=retry_if_exception(_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    def _get(self, client: httpx.Client, url: str) -> httpx.Response:
        self.requests += 1
        try:
            resp = client.get(url)
        except httpx.TimeoutException as exc:
            raise UpstreamError("github", "timeout", str(exc)) from exc
        except httpx.TransportError as exc:
            raise UpstreamError("github", "unavailable", str(exc)) from exc
        if resp.status_code == 200:
            return resp
        rate_limited = resp.status_code == 429 or (
            resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0"
        )
        if rate_limited:
            wait = _rate_limit_wait(resp)
            if wait is not None and wait <= MAX_RATE_LIMIT_WAIT_S:
                time.sleep(wait)
            raise UpstreamError(
                "github",
                "rate_limited",
                "GitHub rate limit; повторите позже или задайте GITHUB_TOKEN",
                resp.status_code,
            )
        raise UpstreamError(
            "github", kind_from_status(resp.status_code), f"GET {url}", resp.status_code
        )

    def resolve_commit(self, ref: str) -> str:
        return self._get(self._api, f"/repos/{self.repo}/commits/{ref}").json()["sha"]

    def list_tree(self, commit_sha: str) -> list[TreeEntry]:
        data = self._get(self._api, f"/repos/{self.repo}/git/trees/{commit_sha}?recursive=1").json()
        if data.get("truncated"):
            raise UpstreamError("github", "bad_request", "tree listing truncated by GitHub")
        return [
            TreeEntry(e["path"], e["sha"], e.get("size", 0))
            for e in data["tree"]
            if e["type"] == "blob"
        ]

    def fetch_raw(self, commit_sha: str, path: str) -> str:
        return self._get(self._raw, f"/{self.repo}/{commit_sha}/{path}").text


def _rate_limit_wait(resp: httpx.Response) -> float | None:
    if "retry-after" in resp.headers:
        return float(resp.headers["retry-after"])
    reset = resp.headers.get("x-ratelimit-reset")
    if reset:
        return max(0.0, float(reset) - time.time())
    return None
