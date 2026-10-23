# Handoff — этап 03 (вертикальный срез) → этап 04 (проверка Codex)

```yaml
task_id: LAB1-003
sender_role: "Claude Code (Opus 5.5, CLI 2.1.309) — основной исполнитель"
receiver_role: "Codex — независимая проверка воспроизводимости (prompts/04-codex-verify.md)"
status: ready_for_next_step
goal: "Проверить сквозной срез на конкретном SHA: setup, тесты, ingest x2, ask, отказ, ошибки API, trace"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-03-vertical-slice (PR в main)"
commit_sha: "код: 7cac4ca; коммит с evidence/handoff — следующий в ветке (git log)"
working_tree_clean: "true после коммита handoff — проверить git status"
requirements:
  - "docs/requirements.md — раздел «Статус выполнения после этапа 03»"
read_first:
  - AGENTS.md
  - lab1/README.md
  - docs/architecture.md   # §9 — факты этапа 03
  - docs/evidence/stage03/README.md
allowed_paths:
  - "проверяющему: только docs/reviews/verification.md в своём worktree"
decisions:
  - "LLM gemini-3.5-flash-lite, embeddings gemini-embedding-001@768 — подтверждены реальными запросами"
  - "Лимиты из AI Studio пользователя: embeddings 100 RPM/30K TPM/1K RPD; LLM 15 RPM/500 RPD; в конфиге 80 RPM/24K TPM и 12 RPM"
  - "Коллекция включает имя корпуса; состояние индекса включает PREPROCESS_VERSION"
  - "Промпт answer/v1.2 (v1, v1.1 — дефекты языка, сохранены)"
completed:
  - "grabber, preprocessing, embeddings, vectorstore, retrieval, filtering, generation, observability, CLI, FastAPI"
  - "51 офлайн-тест (fakes явно помечены)"
verification:
  - command: "cd lab1 && uv run pytest && uv run ruff check . && uv run ruff format --check ."
    result: "51 passed; lint/format ok"
  - command: "rm -rf data/raw data/cache data/index && uv run flutter-rag ingest"
    result: "8 docs, 144 chunks, 9 embedding API calls, limiter 54 s, 0 retries; trace d966b328f8f7854fa85929f59d750b6c"
  - command: "uv run flutter-rag ingest (повтор)"
    result: "0 downloads, 2 GitHub requests, 0 embedding calls, 144 points; trace 47b77ddcde745237265e8f881f8ca2d5"
  - command: "uv run flutter-rag ask (RU, в корпусе)"
    result: "answered, источники constraints; trace e2c97be2c40fe72b5fe6a5034d945e16"
  - command: "uv run flutter-rag ask (RU, FCM — вне корпуса)"
    result: "insufficient_context, без источников; trace b0fef497d5e85746a59c6c94dbfdefaa"
  - command: "uv run flutter-rag ask (EN, JSON → Dart)"
    result: "answered, код Album.fromJson, 3 источника; trace 9411244585f659726f4db21a06afa493"
  - command: "GEMINI_API_KEY=invalid… uv run flutter-rag ask …"
    result: "upstream_error/auth, exit 4, без повторов; trace e646547efc489a60cc41745bf292f274"
  - command: "uv run flutter-rag trace-show <id> (отдельный процесс, для всех 6)"
    result: "все trace получены из Langfuse API; metadata git_sha 7cac4ca, git_dirty False"
  - command: "проверка всех 144 url#anchor по docs.flutter.dev"
    result: "0 битых (до исправления slug — 6)"
    artifact: "docs/evidence/stage03/dev-runs/source-links-check.txt"
  - command: "flutter-rag serve + curl /health /ready /ask + параллельный ask"
    result: "200/200/answered, пустой вопрос 422; параллельный CLI — exit 3 с подсказкой (B2)"
not_verified:
  - "GitHub 403/429 и сетевые сбои grabber — только офлайн-тесты логики, в реальности не наблюдались"
  - "Gemini 429 и подсказка retryDelay — только офлайн-тест, реальных 429 не было"
  - "Реальное удаление/изменение страницы во flutter/website между снапшотами — только офлайн-тест"
  - "Детерминизм ответов: при temperature 0 формулировка ответа на один вопрос различалась между запусками"
  - "Полный корпус (638 страниц): ~150K токенов ≈ 6+ мин из-за 30K TPM — не запускался"
  - "Reranker, вторая embedding-модель, калибровка min_score, evaluation"
  - "Поведение при недоступности Langfuse (код не падает по замыслу, но вживую не проверено)"
blockers: []
next_action: "Codex по prompts/04-codex-verify.md проверяет PR этапа 03 в отдельном worktree"
acceptance_criteria:
  - "Отчёт docs/reviews/verification.md с SHA, повторёнными командами и findings"
student_explanation: "См. docs/PROJECT_STATE.md и объяснение в чате: путь одного вопроса от ввода до ответа"
```
