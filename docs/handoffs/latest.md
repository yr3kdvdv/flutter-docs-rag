# Handoff — этап 04b (G1 и EN-ответ после повторной проверки Codex) → решение о слиянии PR #14

```yaml
task_id: LAB1-004b-fixes
sender_role: "Claude Code (Opus 5.5) — основной исполнитель и интегратор"
receiver_role: "Пользователь (решение о слиянии PR #14); опционально Codex — проверка G1"
status: ready_for_next_step
goal: "Закрыть G1 P2 и непроверенный EN answered из docs/reviews/verification-fixes.md"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-03-vertical-slice (PR #14 в main, ещё не влит)"
commit_sha: "код G1: b6c32e1; evidence/handoff — следующий коммит (git log)"
worktree: "основной checkout; worktrees проверяющего (…-verify-a54a5c5, …-verify-e366b6e) не менялись"
working_tree_clean: "после коммита остаётся untracked lab1/2026-11-04-213321-projectstate-latest-handoff.txt (экспорт разговора /export) — не коммитится, его стоит перенести из репозитория"
requirements:
  - "docs/reviews/verification-fixes.md — G1 и раздел «Непроверенное»"
read_first:
  - AGENTS.md
  - docs/reviews/verification-fixes.md
  - docs/evidence/stage04b/README.md
  - docs/architecture.md   # §10
allowed_paths:
  - "проверяющему: только docs/reviews/verification-g1.md в своём worktree"
do_not_edit:
  - "docs/reviews/verification.md, docs/reviews/verification-fixes.md — отчёты Codex, сохранены без изменений"
decisions:
  - "Язык вопроса: текст вне кавычек/кода; есть кириллица → ru; полностью в кавычках → весь текст"
  - "Явный параметр языка в CLI/API не вводится (минимальное исправление); ограничение задокументировано"
completed:
  - "G1 исправлен (b6c32e1), 11 новых регрессионных случаев; на e366b6e 5 из 11 падают"
  - "EN answered с проверенными источниками получен реально (2 вопроса)"
  - "Отчёт Codex и промпт 04b сохранены в репозитории"
verification:
  - command: "cd lab1 && uv run pytest && uv run ruff check . && uv run ruff format --check ."
    result: "73 passed; lint/format ok; exit 0"
  - command: "pytest G1-кейсов против src из e366b6e"
    result: "5 failed (EN с кириллицей в кавычках), RU-кейсы passed"
  - command: "uv run flutter-rag ingest (snapshot 4fee025)"
    result: "exit 0; 8 unchanged, 144 points; trace 2de73a48…"
  - command: "uv run flutter-rag ask: 2 × G1, RU FCM, RU с цитатой, EN hot reload, EN JSON ×2"
    result: "G1 → EN отказ; RU FCM → RU отказ; RU/EN answered с источниками; EN JSON: 1-я попытка Gemini 503 (exit 4), 2-я answered"
    artifact: "docs/evidence/stage04b/ask/"
  - command: "проверка источников в Qdrant и якорей на живых страницах"
    result: "6/6 источников найдены, URL совпадают, якоря существуют"
    artifact: "docs/evidence/stage04b/sources-check.txt"
  - command: "чтение 8 traces из Langfuse API отдельным процессом"
    result: "все найдены, git_sha b6c32e1"
    artifact: "docs/evidence/stage04b/traces-from-langfuse.json"
not_verified:
  - "Независимая проверка исправления G1"
  - "Русское имя без кавычек в EN-вопросе всё ещё даёт ru (известное ограничение)"
  - "Реальные сбои GitHub (F1/F2 — инъекция), Gemini 429, недоступность Langfuse, Qdrant server, удаление страницы upstream"
  - "CI на последнем SHA — см. PR #14"
blockers: []
next_action: "Пользователь решает: влить PR #14 сейчас или после короткой проверки G1 Codex"
acceptance_criteria:
  - "PR #14 влит в main с зелёным CI, либо отчёт docs/reviews/verification-g1.md"
student_explanation: "Язык отказа теперь определяется по самому вопросу, а не по цитатам и именам в кавычках; английский ответ с проверенными источниками подтверждён реальным запуском."
```
