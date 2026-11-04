# Handoff — исправления по проверке Codex (этап 04) → повторная проверка / слияние PR #14

```yaml
task_id: LAB1-004-fixes
sender_role: "Claude Code (Opus 5.5) — основной исполнитель и интегратор"
receiver_role: "Codex — повторная проверка исправлений F1–F6 (затем интегратор вливает PR #14)"
status: ready_for_next_step
goal: "Подтвердить, что F1–F6 из docs/reviews/verification.md исправлены и регрессий нет"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-03-vertical-slice (PR #14 в main, ещё не влит)"
commit_sha: "код исправлений: b6bc723; evidence: 29f9afc; handoff — следующий коммит (git log)"
worktree: "основной checkout; worktree проверяющего ../flutter-docs-rag-verify-a54a5c5 не менялся"
working_tree_clean: "true после коммита handoff — проверить git status"
requirements:
  - "docs/reviews/verification.md — F1–F6"
  - "docs/requirements.md — раздел «Статус после исправлений этапа 04»"
read_first:
  - AGENTS.md
  - docs/reviews/verification.md
  - docs/evidence/stage04/README.md
  - docs/architecture.md   # §3.1, §5, §10
  - lab1/tests/test_review_regressions.py
allowed_paths:
  - "проверяющему: только docs/reviews/verification-fixes.md в своём worktree"
do_not_edit:
  - "docs/reviews/verification.md — сохранён без изменений как отчёт Codex"
decisions:
  - "failed-загрузка (страницы или её include) ≠ удаление: прежняя версия остаётся, отчёт stale_documents, diff.failed"
  - "Страница с найденным в tree, но не скачанным include — failed (не индексируется неполной)"
  - "Пустой/несозданный индекс — IndexNotReadyError: /ask 503 {status: not_ready}, CLI exit 2; не insufficient_context"
  - "Пустые/пробельные секреты = не заданы"
  - "ingest trace: corpus_commit пишется после grab; прошлый SHA — previous_corpus_commit"
  - "Текст отказа формирует код по языку вопроса (кириллица → ru); prompt answer/v1.2 не менялся"
completed:
  - "F1–F6 исправлены (b6bc723), 12 регрессионных тестов; на старом коде 11 из 12 падают"
  - "Отчёт Codex сохранён в docs/reviews/verification.md"
  - "architecture §3.1/§5/§10, requirements, prompts CHANGELOG, evidence stage04 обновлены"
verification:
  - command: "cd lab1 && uv run pytest && uv run ruff check . && uv run ruff format --check ."
    result: "63 passed; lint/format ok; exit 0"
  - command: "pytest новых тестов против src из a54a5c5 (временная копия с мягкими импортами)"
    result: "11 failed, 1 passed — тесты ловят исходные дефекты"
  - command: "GEMINI_API_KEY= LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= uv run flutter-rag env-check / ingest"
    result: "MISSING ×3, exit 0 / MissingSecretError, exit 2"
    artifact: "docs/evidence/stage04/f4-blank-keys.txt"
  - command: "flutter-rag serve (пустой DATA_DIR) + curl /health /ready POST /ask"
    result: "200 / 503 / 503 {status: not_ready}"
    artifact: "docs/evidence/stage04/f3-ask-before-ingest.txt"
  - command: "uv run flutter-rag ingest (с нуля, затем повтор), snapshot b017c8c"
    result: "exit 0: 144 points, 9 embedding calls; повтор 0 downloads/0 calls/144 points; traces 25cc8630…, 013ce204…"
  - command: "ingest tools/hot-reload @602492c → @5ce3d6a (временные конфиги вне репозитория)"
    result: "exit 0: added=1, затем modified=1, 15→15 points; traces 049e7776…, 64f521d1…"
  - command: "чтение observations metadata 4 ingest-traces из Langfuse API"
    result: "root corpus_commit = фактический SHA, previous_corpus_commit = прошлый; git_sha b6bc723, git_dirty False"
    artifact: "docs/evidence/stage04/f5-ingest-trace-metadata.json"
  - command: "uv run flutter-rag ask × 7 (5 RU вне корпуса, RU и EN в корпусе) + 1 с неверным ключом"
    result: "5/5 RU отказов по-русски; RU answered по-русски; EN answered с кодом; неверный ключ exit 4 auth"
    artifact: "docs/evidence/stage04/ask/, f6-ask-traces-from-langfuse.json"
not_verified:
  - "F1/F2 при реальном сбое GitHub — только инъекция UpstreamError в fake-клиент; живой 5xx/403/429 не наблюдался"
  - "Сама модель (answer/v1.2) в 3/3 FCM-запусках отказала по-английски — исправлен вывод, не поведение модели"
  - "Язык ответов status=answered не исправляется, только warning answer_language_mismatch"
  - "Реальное удаление страницы upstream, недоступность Langfuse, Qdrant server, Gemini 429"
  - "CI GitHub Actions на новом SHA — см. PR #14 после push"
  - "Независимая повторная проверка исправлений (Codex) не проводилась"
blockers: []
next_action: "Codex повторно проверяет исправления F1–F6 на последнем SHA ветки по docs/evidence/stage04/README.md"
acceptance_criteria:
  - "Отчёт docs/reviews/verification-fixes.md с SHA, повторёнными сценариями F1–F6 и статусом каждого"
student_explanation: "Ошибка сети при обновлении больше не стирает рабочую страницу из индекса и не закрепляет неполную; пустой индекс — понятная ошибка 503, а не «нет ответа»; отказ всегда на языке вопроса."
```
