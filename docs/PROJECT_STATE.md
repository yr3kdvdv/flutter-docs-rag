# Состояние проекта

Дата: 23 октября 2026. Этап: **03 завершён** — работает сквозной RAG на 8 страницах с реальными API
и trace Langfuse. Следующий — 04 (независимая проверка Codex).
Подробно: [docs/handoffs/latest.md](handoffs/latest.md).

## Сделано
- Подготовительный пакет координатора (задание, инструкции, prompts) — в Git.
- Среда: uv 0.13.5 (Homebrew), Python 3.12.15 (uv-managed), `lab1/uv.lock`, `requirements.txt` из lock.
- Каркас `lab1/` (src-layout), `flutter-rag env-check`, 22 теста, ruff.
- docs/requirements.md, docs/architecture.md (до аудита), docs/SETUP_ACCOUNTS.md, `.env.example`.
- 4 субагента (`.claude/agents`), 7 skills (`.agents/skills` + адаптеры `.claude/skills`);
  видимость в Claude Code подтверждена (docs/evidence/).
- GitHub: https://github.com/yr3kdvdv/flutter-docs-rag (public), Issues #1–#12, labels,
  шаблоны PR/Issue, CI — зелёный на `f1f00ab`.
- Аудит архитектуры Gemini сохранён (docs/reviews/architecture.md, SHA 45cc5a6) и разобран
  (docs/reviews/architecture-response.md): B1–B3, H1–H4, M2–M4, L1–L3 приняты; H5 частично; M1 отклонён как дефект.
  Архитектура → ревизия 2, base.yaml обновлён.

- Этап 03: grabber → очистка → chunks → Gemini embeddings → Qdrant → retrieval → Gemini LLM →
  ответ с проверенными источниками → trace Langfuse. Идемпотентный повторный ingest, отказ вне корпуса,
  различение insufficient_context / upstream_error, FastAPI. Доказательства: docs/evidence/stage03/.

## Не выполнено
- Полный корпус, reranker, вторая embedding-модель, калибровка порога, dataset, эксперименты.
- Проверка skills в Codex/Antigravity; реальный запуск субагентов.

## Наблюдения о среде (проверено 2026-10-23 в этой сессии)
- macOS 26.6.2, arm64. Системный python3 3.9.6 — не используется и не изменён.
- Claude Code 2.1.309: loggedIn=true, подписка pro.
- gh 2.103.0: вход yr3kdvdv, scopes gist/read:org/repo/workflow.
- Codex CLI 0.163.0, agy, node v26.9.0 есть в PATH; их работа не проверялась.
- Docker/podman/colima не найдены → Qdrant в embedded-режиме.
- Ключи Gemini/Langfuse/Voyage: set (`.env` заполнен пользователем); Voyage ещё не использовался.
- Лимиты Gemini free tier (AI Studio, проект «Project RAG»): Embedding 100 RPM / 30K TPM / 1K RPD;
  3.5/3.1 Flash Lite 15 RPM / 500 RPD; Flash-модели 5 RPM / 20 RPD; Gemma 4 31B 30 RPM / 14.4K RPD; Pro — 0.

## Следующее действие
1. Влить PR этапа 03 после зелёного CI.
2. Независимая проверка Codex по prompts/04-codex-verify.md (START_HERE.md §6).
