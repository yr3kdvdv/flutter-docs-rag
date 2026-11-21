# Handoff — этап 05 (полный pipeline и evaluation) → независимая проверка dataset, затем этап 06

```yaml
task_id: LAB1-005
sender_role: "Claude Code (Opus 5.5) — интегратор; субагенты Claude: corpus-engineer, retrieval-engineer, evaluation-engineer"
receiver_role: "Codex или Gemini — независимая проверка dataset (prompts/05b-codex-dataset-check.md); затем Claude Code — этап 06"
status: ready_for_next_step
goal: "Подтвердить эталоны flutter-qa-v1 до настройки параметров на dev"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-05-full-pipeline (PR в main — см. GitHub)"
commit_sha: "последний коммит ветки (git log); код этапа до 71ab3d5, далее docs/evidence"
worktree: "основной checkout; worktrees субагентов влиты и удалены (кроме ещё не удалённого evaluation, см. git worktree list)"
working_tree_clean: "после коммита — untracked lab1/2026-11-04-213321-projectstate-latest-handoff.txt (экспорт /export, не коммитится) и docs/evidence/stage05/.voyage-ingest.log (лог фонового ingest)"
requirements:
  - "docs/requirements.md — «Статус после этапа 05»"
  - "docs/contracts/stage05.md"
read_first:
  - AGENTS.md
  - docs/contracts/stage05.md
  - docs/evidence/stage05/README.md
  - lab1/evaluation/datasets/flutter-qa-v1/README.md
  - lab1/README.md
allowed_paths:
  - "проверяющему dataset: только docs/reviews/dataset-check.md в своём worktree"
decisions:
  - "Полный корпус: flutter/website@4fee025, 647 ok страниц; manifests и коллекции по corpus.name"
  - "Gemini embeddings: free tier = 1000 текстов/день → billing Tier 1 подключён пользователем 2026-11-19"
  - "Embeddings #2: Voyage voyage-4-lite 1024 (free tier 3 RPM / 10K TPM, подтверждено заголовком)"
  - "Reranker: Voyage rerank-2.5 после filter, top_n = max_chunks (одинаковый бюджет on/off)"
  - "LLM #2: gemma-4-31b-it (открытая, через Gemini API); prompt answer/v2 — вариант для сравнения"
  - "Judge: gemini-3.1-flash-lite, judge/v1, temperature 0"
  - "Dataset: 45 вопросов (15 dev + 30 test), все draft; test только с --final"
  - "Runner full-режима вызывает pipeline._ask_inner внутри своей trace eval.full (решение evaluation-engineer, принято; публичный ask(trace_name=) — кандидат на этап 06)"
completed:
  - "Chunking section/fixed/paragraph + section_ids; Voyage embeddings + rerank; pipeline.search(); Gemma; prompt v2"
  - "Dataset flutter-qa-v1, dataset-check, метрики, judge, runner evaluate"
  - "Индексы Gemini и Voyage полного корпуса (по 5815 точек), повтор Gemini идемпотентен; retrieval-прогон dev на обоих"
  - "Реальные прогоны runner на dev: retrieval и full (15/15, 0 ошибок), traces/session/scores прочитаны из Langfuse"
verification:
  - command: "cd lab1 && uv run pytest && uv run ruff check . && uv run ruff format --check ."
    result: "150 passed; lint/format ok"
  - command: "uv run flutter-rag ingest --config configs/full.yaml (+ повтор с GITHUB_TOKEN)"
    result: "exit 0: 5815 точек, 0 failed; повтор 0 загрузок/0 embedding-вызовов"
    artifact: "docs/evidence/stage05/ingest-full-gemini-section512*.json"
  - command: "повтор ingest без GITHUB_TOKEN"
    result: "реальный GitHub 403 (60/60), понятная ошибка, exit 4"
    artifact: "docs/evidence/stage05/github-403-unauthenticated.txt"
  - command: "uv run flutter-rag dataset-check"
    result: "OK: 80 цитат, 50 gold-секций, 30 absent terms; statuses draft 45"
  - command: "uv run flutter-rag evaluate --config configs/full.yaml --split dev --mode retrieval / full"
    result: "run 20261119T210351Z…retrieval-dev, 20261119T210404Z…full-dev: 15/15, 0 ошибок"
    artifact: "lab1/experiments/runs/, docs/evidence/stage05/eval-full-dev-readback.json"
  - command: "ask через full-gemma.yaml и с reranker Voyage"
    result: "оба answered с источниками; traces 5c29c434…, ad4873c3…"
not_verified:
  - "Эталоны dataset — независимой проверки нет; Hit@1 11/12 на dev подозрительно высок"
  - "answer/v2, thinking_budget, индексы fixed/paragraph, калибровка min_score — этап 06"
  - "Точные лимиты Tier 1 Gemini; отказ Langfuse; Qdrant server; GitHub 5xx; удаление страницы upstream"
blockers: []
next_action: "Независимая проверка dataset по prompts/05b-codex-dataset-check.md на последнем SHA ветки"
acceptance_criteria:
  - "docs/reviews/dataset-check.md со статусом ok/fix/drop по всем 45 id"
student_explanation: "Система теперь работает на всей документации Flutter и умеет сравнивать варианты: разные способы резки текста, две модели векторов, reranker, две LLM и два промпта. Есть набор из 45 вопросов и автоматический подсчёт метрик; но пока эталоны не проверены независимо, числа на dev — проверка работоспособности, а не результат исследования."
```
