"""Stage 01 checks: the environment and project skeleton, not RAG behaviour."""

import importlib
import re
from pathlib import Path

import pytest

from flutter_rag import cli
from flutter_rag.config import REPO_ROOT, SECRET_VARS, Settings

MODULES = [
    "grabber",
    "preprocessing",
    "embeddings",
    "vectorstore",
    "retrieval",
    "reranking",
    "filtering",
    "generation",
    "evaluation",
    "observability",
    "api",
]


@pytest.mark.parametrize("module", MODULES)
def test_pipeline_packages_import(module):
    importlib.import_module(f"flutter_rag.{module}")


@pytest.mark.parametrize(
    "sdk", ["google.genai", "voyageai", "qdrant_client", "langfuse", "fastapi"]
)
def test_sdks_import(sdk):
    importlib.import_module(sdk)


def test_env_example_lists_every_secret():
    names = set(re.findall(r"^([A-Z_]+)=", (REPO_ROOT / ".env.example").read_text(), re.M))
    assert set(SECRET_VARS) <= names


def test_env_example_has_no_values_for_secrets():
    for line in (REPO_ROOT / ".env.example").read_text().splitlines():
        name, _, value = line.partition("=")
        if name in SECRET_VARS:
            assert value == "", f"{name} must be empty in .env.example"


def test_secret_status_hides_values(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-not-a-real-key")
    settings = Settings(_env_file=None)
    status = settings.secret_status()
    assert status["GEMINI_API_KEY"] is True
    assert "dummy-not-a-real-key" not in repr(settings)


def test_unimplemented_commands_fail_honestly(capsys):
    assert cli.main(["evaluate"]) == 2
    assert "not implemented" in capsys.readouterr().err


def test_env_check_runs(capsys):
    assert cli.main(["env-check"]) == 0
    out = capsys.readouterr().out
    for name in SECRET_VARS:
        assert name in out


def test_gitignore_excludes_env():
    assert ".env" in (Path(REPO_ROOT) / ".gitignore").read_text().splitlines()
