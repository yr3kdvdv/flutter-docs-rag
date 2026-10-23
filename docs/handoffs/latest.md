# Handoff — этап 01 → этап 02 (аудит архитектуры)

```yaml
task_id: LAB1-001
sender_role: "Claude Code (Opus 5.5, CLI 2.1.309) — основной исполнитель"
receiver_role: "Gemini / Antigravity — независимый архитектор (prompts/02-gemini-architecture.md)"
status: ready_for_next_step
goal: "Независимо проверить docs/requirements.md и docs/architecture.md до реализации RAG"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag (public)"
branch: main
commit_sha: "f1f00ab — проверенный код этапа 01 (CI зелёный). Коммит с этим handoff идёт следом; git log покажет его SHA"
worktree: "не используется"
working_tree_clean: "true на момент коммита handoff; проверить `git status` перед аудитом"
requirements:
  - "docs/source/README_PAD.md, раздел «Лабораторная работа №1»"
  - "Дополнение преподавателя: Langfuse обязателен (docs/PROJECT_BRIEF.md)"
read_first:
  - AGENTS.md
  - docs/PROJECT_BRIEF.md
  - docs/requirements.md
  - docs/architecture.md
  - docs/RESEARCH_PLAN.md
allowed_paths:
  - "для аудитора: ничего (только чтение); отчёт возвращается в чат"
do_not_edit:
  - "весь репозиторий во время аудита"
decisions:
  - "D1 Python 3.12 через uv + uv.lock (системный Python 3.9.6 не трогаем)"
  - "D2 Корпус: Markdown из GitHub flutter/website, snapshot по commit SHA, diff по blob SHA"
  - "D3 Qdrant embedded local mode (Docker нет), сервер через QDRANT_URL позже"
  - "D4/D5/D6/D7 Кандидаты: gemini-embedding-001 (768), voyage-4-lite, rerank-2.5, LLM Gemini — ID подтверждаются реальным запросом на этапе 03"
  - "D8 Langfuse Cloud EU, SDK v5, flush() в CLI"
  - "GitHub: owner yr3kdvdv, repo flutter-docs-rag, public — выбор пользователя 2026-10-23"
  - "Skills: общая методика .agents/skills/*, адаптеры Claude в .claude/skills/*"
completed:
  - "uv 0.13.5 установлен через Homebrew; Python 3.12.15 (uv-managed); lab1/.venv из uv.lock"
  - "lab1: src/flutter_rag (11 модулей-заготовок), config.py, cli.py (env-check работает), configs/base.yaml, tests/test_setup.py"
  - "docs/requirements.md (R01–R37, P01–P04, N01–N05), docs/architecture.md, docs/SETUP_ACCOUNTS.md, .env.example"
  - "4 субагента в .claude/agents, 7 skills"
  - "GitHub: repo, 12 Issues (#1–#12), labels, PR/Issue шаблоны, CI"
verification:
  - command: "cd lab1 && uv sync --locked (чистый git clone)"
    result: "OK, exit 0"
  - command: "uv run pytest"
    result: "22 passed, exit 0 (локально и в чистом клоне)"
    artifact: "lab1/tests/test_setup.py"
  - command: "uv run ruff check . && uv run ruff format --check ."
    result: "All checks passed; 18 files already formatted"
  - command: "uv run flutter-rag env-check"
    result: "exit 0; python 3.12.15; все 4 ключа MISSING (.env ещё не создан)"
  - command: "uv run flutter-rag ask"
    result: "exit 2, 'not implemented yet' — честная заглушка"
  - command: "GitHub Actions CI"
    result: "run 39931908428 FAILED (тег setup-uv@v10 не существует) → исправлено → run 39932006368 success на f1f00ab"
    artifact: "https://github.com/yr3kdvdv/flutter-docs-rag/actions/runs/39932006368"
  - command: "echo '...' | claude -p --tools Agent --max-turns 1"
    result: "видны code-reviewer, corpus-engineer, evaluation-engineer, retrieval-engineer"
    artifact: "docs/evidence/stage01-agents-visible.txt"
  - command: "echo '...' | claude -p --tools Skill --max-turns 1"
    result: "видны все 7 project skills; текущая сессия тоже подхватила их автоматически"
    artifact: "docs/evidence/stage01-skills-visible.txt"
  - command: "gh auth status"
    result: "logged in as yr3kdvdv, scopes gist, read:org, repo, workflow"
  - command: "claude auth status"
    result: "loggedIn true, subscription pro"
not_verified:
  - "Любые вызовы Gemini / Voyage / Langfuse API — ключей нет"
  - "Доступность конкретных model ID и квот бесплатного уровня"
  - "Загрузка skills в Codex и Antigravity (.agents/skills) — проверять в этих клиентах"
  - "Реальный запуск субагентов (только видимость определений; запуск — с этапа 03/05)"
  - "Работоспособность agy/Antigravity в этой среде"
  - "`claude plugin validate .claude` вернул success, но с пустым contents — как проверку не считаем"
experiment:
  dataset_version: "нет"
  corpus_snapshot: "нет (наблюдался HEAD flutter/website 3eb87869bb0d, не зафиксирован как snapshot)"
  config_id: "baseline-draft (не запускался)"
  langfuse_run_id: "нет"
blockers:
  - "Ключи API не созданы — блокирует этап 03, но не этап 02"
next_action: "Запустить аудит архитектуры в Antigravity по prompts/02-gemini-architecture.md (команда в START_HERE.md §3); параллельно пользователь заполняет .env по docs/SETUP_ACCOUNTS.md"
acceptance_criteria:
  - "Отчёт аудитора с SHA, приоритетами и блокерами сохранён в docs/reviews/architecture.md"
student_explanation: "См. раздел ниже"
```

## Объяснение для студента

Этап 01 — это «фундамент и чертёж», а не сама RAG-система. Мы:
1. Сделали **отдельную среду Python 3.12** для проекта (uv + lock-файл). Lock-файл фиксирует
   точные версии 93 пакетов (87 runtime в requirements.txt), поэтому у преподавателя и в CI ставится ровно то же самое.
2. Составили **матрицу требований**: каждая строка задания → как мы её реализуем → чем докажем.
   Разделили «обязательно по заданию», «сказал преподаватель», «рекомендация» и «наше решение».
3. Нарисовали **архитектуру**: какие модули, как идёт документ (ingestion) и как идёт вопрос
   (query), какие ошибки как обрабатываются. Это план, его сейчас проверит другой ИИ (Gemini).
4. Подготовили **команду агентов** и инструкции-skills и проверили, что Claude Code их видит.
5. Создали **публичный репозиторий**, 12 задач и CI, который на каждом push проверяет проект.

Вопрос для самопроверки: почему CI сначала упал, и почему это хорошо, что мы это увидели,
а не написали «CI работает»?
