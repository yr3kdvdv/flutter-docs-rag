# Handoff этапа 08 — выпуск и пробная защита

```yaml
task_id: LAB1-008
sender_role: "Codex (GPT-6), интеграция и проверка выпуска"
receiver_role: "Координатор пробной защиты"
status: waiting_for_student
goal: "Показать рабочую систему и проверить понимание основных архитектурных решений"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-08-release"
release: "https://github.com/yr3kdvdv/flutter-docs-rag/releases/tag/lab1-v1.0.1"
commit_sha: "35ba4cc23b64f2e066054c50c8d1fa93f21166fc"
worktree: "SHA закрепляет код и сценарий, проверенный живым запуском. Документальные результаты в последующем коммите ветки."
working_tree_clean: false
untracked:
  - "lab1/2026-11-04-213321-projectstate-latest-handoff.txt"
  - "lab1/claude_pad_last_dialog.txt"
requirements:
  - "docs/requirements.md, прежде всего R34/R36/R37, P01, N02/N03"
  - "prompts/08-release-defense.md"
read_first:
  - docs/PROJECT_BRIEF.md
  - docs/PROJECT_STATE.md
  - docs/defense/demo-script.md
  - docs/defense/questions.md
  - docs/evidence/stage08/README.md
  - lab1/experiments/report.md
do_not_edit:
  - "Принятые dev.jsonl, test.jsonl, замороженный конфиг и сохранённые артефакты этапа 06"
  - "Два экспорта диалогов в lab1"
decisions:
  - "Для живого демо закреплены две страницы на том же SHA корпуса. Полный индекс восстановлен отдельно из ранее полученных данных."
  - "После фиксации исследования технические проверки выполнялись на демо и dev. Числа качества относятся к неизменённым результатам этапа 06."
completed:
  - "Исправлены привязка Qdrant к снимку, возврат HTTP 503 при сетевой ошибке, язык и цитаты. Уточнены вход и знаменатель judge."
  - "Обновлены README и матрица требований. Подготовлены демонстрация, вопросы и доказательства."
verification:
  - command: "uv sync --locked --offline, pytest, Ruff, экспорт зависимостей и пересчёт"
    result: "Установка из кэша в чистом checkout, 172 теста, Ruff, побайтовое совпадение всех 25 исторических агрегатов."
  - command: "ingest ×2, ask EN, отказ RU, curl к FastAPI и trace-show"
    result: "Живой старт на пустом data dir, 73 точки, ноль вызовов embeddings при повторе, успешно прочитаны 6 наблюдений одной трассы."
    artifact: "docs/evidence/stage08/live-demo.json"
  - command: "Офлайн-реконструкция полного индекса и retrieval на dev"
    result: "647 страниц, 2694 точки, результаты всех 15 dev-вопросов совпали с этапом 06."
    artifact: "docs/evidence/stage08/full-index-rehearsal.json"
  - command: "evaluate --config experiments/configs/s06-final.yaml --split dev --mode full --limit 1"
    result: "Реальный ответ и judge на dev-001. CLI сообщил о преднамеренно ограниченном запуске."
    artifact: "docs/evidence/stage08/dev-judge-smoke.json"
  - command: "Регрессия API для русского ответа с Markdown-ссылкой и полный pytest"
    result: "В исправлении v1.0.1 ответ проходит валидацию с первой попытки. 173 теста и Ruff прошли."
not_verified:
  - "Полная загрузка и векторизация всех 647 страниц с нуля в этапе 08 и отключение живого сетевого Qdrant. Соответственно проверены кэшированный сценарий и инъекция ошибки."
  - "Устная защита требует ответов студента."
experiment:
  dataset_version: "flutter-qa-v1"
  corpus_snapshot: "flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb"
  historical_config_id: "s06-final"
  historical_freeze_commit: "1e030daeb47c0b30726756e744700404027b0584"
  demo_config_id: "defense-demo"
next_action: "Задать первый вопрос про embeddings, дождаться ответа и разобрать его. Затем переходить по одному вопросу за раз."
acceptance_criteria:
  - "Студент может объяснить embeddings, chunking, Top-K, rerank, промпты, отказы и Langfuse своими словами."
  - "Студент может связать выбор конфигурации с dev-сравнениями и объяснить границы исторической оценки."
student_explanation: "Embeddings помогают найти подходящие фрагменты Flutter, а LLM формулирует ответ со ссылками только после поиска. Качество найденных источников и качество текста оцениваются отдельно."
```

[Финальный аудит предыдущего этапа](../reviews/final-audit.md)
