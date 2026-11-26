# Handoff этапа 05b → этап 06

```yaml
task_id: LAB1-005B
sender_role: "Codex (GPT-6), независимый проверяющий черновика и исполнитель правок по отчёту"
receiver_role: "Координатор проекта, затем исполнитель этапа 06"
status: ready_for_next_step
goal: "Передать проверенный датасет для исследования влияния конфигураций RAG"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-05-full-pipeline"
commit_sha: "cafe488706a064465c7991e541847b99166af45d"
worktree: "Основной checkout outputs/flutter-docs-rag. SHA выше закрепляет датасет и тесты. Следующий коммит обновляет документацию."
working_tree_clean: false
untracked:
  - "lab1/2026-11-04-213321-projectstate-latest-handoff.txt"
  - "lab1/claude_pad_last_dialog.txt"
requirements:
  - "docs/requirements.md, R30/R31/R32 и N02/N03/N04"
  - "docs/contracts/stage05.md §5.1–5.3"
  - "prompts/06-research.md"
read_first:
  - AGENTS.md
  - docs/PROJECT_STATE.md
  - docs/architecture.md
  - docs/RESEARCH_PLAN.md
  - docs/reviews/dataset-check.md
  - lab1/evaluation/datasets/flutter-qa-v1/README.md
  - docs/evidence/stage05/README.md
allowed_paths:
  - "Экспериментальные конфигурации, артефакты и отчёт из prompts/06-research.md"
  - "docs/PROJECT_STATE.md и docs/handoffs/latest.md после этапа"
do_not_edit:
  - "Принятые dev.jsonl и test.jsonl при подборе конфигураций. Они закреплены контрольными суммами."
  - "Незакоммиченные экспорты диалогов из untracked"
decisions:
  - "Исходный dataset независимо проверен на af6ab74. Применены предложения для 29 вопросов, содержание 16 вопросов сохранено."
  - "flutter-qa-v1 сохраняет 15 dev и 30 test, пять типов и 23 ru / 22 en. Все записи verified."
  - "Настраивать конфигурации по dev. Использовать test с --final после выбора конфигурации."
  - "Исходные прогоны dev этапа 05 использовали черновик. Для сравнений этапа 06 запустить новый baseline."
  - "Baseline полного корпуса full-gemini-section512, prompt answer/v1.2. Judge gemini-3.1-flash-lite, prompt judge/v1."
completed:
  - "Сохранён независимый отчёт с решением по всем 45 ID и поправками к эталонам, вопросам и gold-секциям."
  - "Поправки интегрированы. Тест реального набора проверяет эталоны функциями must_include_found и code_present."
  - "На рабочей копии проверены два индекса по 5815 точек и присутствие всех 51 gold-секций."
verification:
  - command: "uv sync --locked --offline с временными UV_CACHE_DIR и UV_PROJECT_ENVIRONMENT"
    result: "Exit 0, Python 3.12.15."
  - command: "DATA_DIR=<изолированная копия>/data uv run --locked --no-sync flutter-rag dataset-check"
    result: "Exit 0, 82 excerpts, 51 gold sections, 30 absent terms, verified 45."
    artifact: "docs/evidence/stage05/README.md"
  - command: "uv run --locked --no-sync pytest -o addopts= -q"
    result: "Exit 0, 151 passed."
  - command: "uv run --locked --no-sync ruff check . и uv run --locked --no-sync ruff format --check ."
    result: "Обе команды exit 0. Проверка форматирования охватила 60 файлов."
  - command: "uv export --locked --no-header --no-hashes --no-dev --no-emit-project и diff с requirements.txt"
    result: "Exit 0, содержимое совпадает."
  - command: "Qdrant scroll по payload section_ids для configs/full.yaml и configs/full-voyage.yaml"
    result: "Exit 0, в каждой коллекции присутствуют все 51 gold-секция и 5815 точек."
not_verified:
  - "GitHub CI для коммита принятого набора. У открытого draft PR #15 на момент handoff head af6ab74."
  - "Результаты поиска и генерации на принятой версии, калибровка min_score, индексы fixed/paragraph и сравнение вариантов генерации."
experiment:
  dataset_version: "flutter-qa-v1"
  dev_sha256: "df6fb5d791a9b7889591d71d65b33a1e9f1ea49ea89dedc97e3e21f240d1100a"
  test_sha256: "680ba531b37b71ba725796a75ea541ac8092845a59de704110cf15794426f2eb"
  corpus_snapshot: "flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb"
  config_id: "full-gemini-section512"
  langfuse_run_id: null
blockers: []
next_action: "Обновить PR #15 локальными коммитами и проверить CI перед слиянием в main."
acceptance_criteria:
  - "В PR #15 опубликован принятый датасет с указанными SHA-256, CI на этом коммите зелёный."
  - "После слияния этап 06 начинает с гипотез и retrieval-only на dev, фиксируя SHA и конфигурацию в новых прогонах."
student_explanation: "Вопросы, эталоны и источники сверены с одной версией документации Flutter. Для настройки используем 15 dev-вопросов. На 30 test-вопросах оценим уже выбранную конфигурацию."
```
