# Состояние проекта

27 ноября 2026. **Выпуск этапа 08 подготовлен в ветке `stage-08-release`.**
Остаётся пробная защита с участием студента. Исследования этапа 06 сохранены
в отдельном [PR #16](https://github.com/yr3kdvdv/flutter-docs-rag/pull/16),
для ревизии `1ac7e09` [CI прошёл](https://github.com/yr3kdvdv/flutter-docs-rag/actions/runs/45956621140).
[Проверки выпуска](evidence/stage08/README.md) ·
[GitHub Release `lab1-v1.0.1`](https://github.com/yr3kdvdv/flutter-docs-rag/releases/tag/lab1-v1.0.1) ·
[Финальный аудит](reviews/final-audit.md) · [Текущий handoff](handoffs/latest.md)

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

- Этап 04: Codex (GPT-6) воспроизвёл срез на `a54a5c5` и нашёл 6 дефектов. Исправлены в `b6bc723`:
  ошибка загрузки страницы/include больше не удаляет и не закрепляет неполную версию (F1/F2),
  `/ask` до ingest → 503 not_ready (F3), пустые ключи = не заданы (F4), верный `corpus_commit`
  в ingest-trace (F5), отказ на языке вопроса (F6). 63 теста; реальные ingest/ask/serve повторены.

- Этап 04b: Codex на `e366b6e` подтвердил исправление F1–F6 и нашёл G1 (русское имя в кавычках
  переключало отказ на русский). Исправлено в `b6c32e1`, 73 теста; реальные G1/RU/EN ask повторены,
  EN answered получен со второй попытки (первая — Gemini 503).

- Этап 05: контракты (`docs/contracts/stage05.md`), chunking section/fixed/paragraph, Voyage
  embeddings + rerank-2.5, Gemma 4 как LLM #2, prompt answer/v2, dataset flutter-qa-v1 (45, draft),
  метрики/judge/runner. Полный корпус 647 страниц: индекс Gemini 5815 точек. Gemini переведён на
  платный Tier 1 (free tier = 1000 текстов embeddings в день). Runner проверен на dev (retrieval + full).

- Этап 05b: Codex независимо проверил `af6ab74`, затем применил рекомендации к 29 вопросам.
  Валидатор подтвердил `verified: 45`, 82 дословные цитаты и 51 секцию. Все секции присутствуют
  в обеих коллекциях. Пройден 151 тест, включая буквальные проверки эталонов, и Ruff.
  [Отчёт аудита](reviews/dataset-check.md) · [SHA-256 принятой версии](../lab1/evaluation/datasets/flutter-qa-v1/README.md#accepted-revision)

- Этап 06: 21 поисковый и 3 генеративных dev-прогона, 1 финальный прогон по фиксированному
  конфигу. На test — 24/24 ответов там, где есть ответ, 6/6 верных отказов,
  21/24 ответов с обеими оценками judge ≥4. В итоговом конфиге fixed 512,
  overlap 15%, K=10, порог 0,65, Flash-Lite и answer/v1.2. Артефакты пересчитаны
  из сырых строк, из Langfuse прочитаны все 391 трасса оценки.

- Этап 07: Gemini/Antigravity завершил независимый аудит `1ac7e09`.
  Повторно прошли 152 теста, Ruff, проверка lockfile и датасета.
  Все 25 прогонов пересчитаны из сохранённых попыток. Сверены 391 ID трасс Langfuse,
  2694 точки финального Qdrant, 51 gold-секция и все 39 структурированных ссылок.
  В аудите воспроизведён риск неверной привязки оценки к снимку коллекции.
  Также зафиксированы замечания к цитатам, языку ответа, отказам сетевого Qdrant
  и сценарию запуска.
  [Доказательства и минимальные исправления](reviews/final-audit.md)

- Этап 08: готовность и SHA корпуса проверяются по конкретной коллекции
  Qdrant. Прерванный ingest требует завершения перед запросами к изменённому
  индексу. Ошибка сетевого Qdrant возвращается как HTTP 503. Генерация
  проверяет язык и ссылки, судья получает только выдержки в поле контекста.
  Повторно прошли тесты и демонстрация в чистом checkout. Сохранённые
  эксперименты и итоговый показатель этапа 06 воспроизводятся из сырых строк.
  [Доказательства](evidence/stage08/README.md)

## Не выполнено
- Пробная защита с ответами студента.
- Повторный живой smoke G1 и реальные частичные сбои GitHub F1/F2. Офлайн-регрессии прошли в аудите.
- Проверка всех проектных skills в Antigravity.

## Наблюдения о среде (проверено 2026-10-23 в этой сессии)
- macOS 26.6.2, arm64. Системный python3 3.9.6 — не используется и не изменён.
- Claude Code 2.1.309: loggedIn=true, подписка pro.
- gh 2.103.0: вход yr3kdvdv, scopes gist/read:org/repo/workflow.
- Codex CLI 0.163.0, agy, node v26.9.0 есть в PATH; их работа не проверялась.
- Docker/podman/colima не найдены → Qdrant в embedded-режиме.
- Ключи Gemini/Langfuse/Voyage: set на дату первичной настройки. Реальные вызовы Voyage подтверждены этапами 05–06.
- Лимиты Gemini free tier (AI Studio, проект «Project RAG»): Embedding 100 RPM / 30K TPM / 1K RPD;
  3.5/3.1 Flash Lite 15 RPM / 500 RPD; Flash-модели 5 RPM / 20 RPD; Gemma 4 31B 30 RPM / 14.4K RPD; Pro — 0.

## Следующее действие
Провести пробную защиту по [сценарию](defense/demo-script.md) и
[вопросам](defense/questions.md), начиная с embeddings.
