# Lab 1 — Flutter Docs RAG

RAG-система, отвечающая на вопросы по официальной документации Flutter
(`flutter/website`, Markdown) с указанием источников и трассировкой в Langfuse.

**Статус: этап 06 — сравнения и финальная оценка завершены** (647 страниц, snapshot
`flutter/website@4fee025`): 3 стратегии chunking, 2 embedding-модели (Gemini, Voyage), reranker
Voyage, 2 LLM (Gemini Flash-Lite, открытая Gemma 4), 2 версии prompt, dataset из 45 вопросов
(`verified`) и runner экспериментов. [Отчёт](experiments/report.md) ·
[Версия датасета](evaluation/datasets/flutter-qa-v1/README.md)
Архитектура: [../docs/architecture.md](../docs/architecture.md).
Матрица требований: [../docs/requirements.md](../docs/requirements.md).

## Технологии

| Компонент | Что используется (проверено реальными запросами) |
|---|---|
| Embeddings | `gemini-embedding-001` (768 dims, платный tier с 2026-11-19), Voyage `voyage-4-lite` (1024 dims, free tier 3 RPM / 10K TPM) |
| Reranker | Voyage `rerank-2.5` |
| LLM | `gemini-3.5-flash-lite` (основная), `gemma-4-31b-it` (открытая, через Gemini API) |
| Judge | `gemini-3.1-flash-lite`, prompt `judge/v1` |
| Хранилище | Qdrant embedded (одна коллекция на модель+dims+стратегию) |
| Трассировка | Langfuse Cloud (trace на каждый ingest/ask/вопрос evaluation, scores) |

Python 3.12 (через uv), FastAPI. Обоснование и альтернативы — в architecture.md, контракты этапа 05 —
[../docs/contracts/stage05.md](../docs/contracts/stage05.md).

## Установка

Нужны macOS/Linux, [uv](https://docs.astral.sh/uv/) (`brew install uv`).
Системный Python не используется: uv скачивает Python 3.12 для проекта.

```bash
cd lab1
uv sync                 # создаёт .venv по uv.lock
cp ../.env.example ../.env   # затем заполнить локально, см. docs/SETUP_ACCOUNTS.md
```

## Команды

Все команды запускаются из `lab1/`. Ключи берутся из `../.env` (см. docs/SETUP_ACCOUNTS.md).

### Работают (проверено на этапах 03–05)

| Команда | Что делает |
|---|---|
| `uv sync` | Ставит зависимости из `uv.lock` |
| `uv run pytest` | Офлайн-тесты (fake-провайдеры; **не** являются проверкой API) |
| `uv run ruff check .` | Линтер |
| `uv run flutter-rag env-check` | Наличие ключей: `set`/`MISSING`, без значений |
| `uv run flutter-rag ingest` | GitHub → очистка → chunks → Gemini embeddings → Qdrant; повторный запуск качает и векторизует только изменённое |
| `uv run flutter-rag ask "вопрос"` | Ответ + источники + ссылка на trace Langfuse (`--json`, `--save file`) |
| `uv run flutter-rag trace-show <trace_id>` | Читает trace обратно из Langfuse API (доказательство доставки) |
| `uv run flutter-rag serve` | FastAPI: `GET /health`, `GET /ready`, `POST /ask {"question": "..."}`; Swagger на `/docs` |
| `uv run flutter-rag dataset-check` | Проверяет dataset: схему, 15/30, дословность цитат и существование gold-секций на snapshot |
| `uv run flutter-rag evaluate --config configs/full.yaml --split dev --mode retrieval\|full` | Метрики на dev; результат в `experiments/runs/<run_id>/`; `--run-id` продолжает прерванный запуск; test — только с `--final` |
| `uv export --no-header --no-hashes --no-dev --no-emit-project -o requirements.txt` | Обновить requirements.txt из lock |

По умолчанию `ingest`/`ask`/`serve` используют `configs/slice.yaml` (8 страниц), `evaluate` — `configs/full.yaml`.
Конфиги полного корпуса: `full.yaml` (Gemini), `full-voyage.yaml` (Voyage), `full-gemma.yaml` (LLM Gemma).
Без `GITHUB_TOKEN` GitHub разрешает 60 запросов в час (реальный 403 наблюдался 2026-11-19) — задайте
токен, например `GITHUB_TOKEN=$(gh auth token) uv run flutter-rag ingest ...`.

Коды выхода: 0 — успех (в том числе корректный отказ `insufficient_context`), 2 — конфигурация
или нет ключей, 3 — локальная база Qdrant занята другим процессом, 4 — внешний сервис недоступен.

**Важно:** встроенный Qdrant допускает один процесс. Пока работает `serve`, команды `ingest`/`ask`
в другом терминале завершатся с кодом 3 и подсказкой. Это ограничение embedded-режима (аудит B2).

## Пример (реальный запуск на commit 7cac4ca, prompt answer/v1.2)

```text
$ uv run flutter-rag ask "Почему виджет с width: 100 может оказаться не шириной 100 пикселей?"
status: answered

Виджет с width: 100 может не быть шириной 100 пикселей, потому что родительский виджет или экран может навязывать ему другие ограничения (например, экран заставляет контейнер занять весь экран целиком) [1][5].

Источники:
  [1] Understanding constraints
      https://docs.flutter.dev/ui/layout/constraints  (score 0.6954)
  [5] Understanding constraints — Examples > Example 2
      https://docs.flutter.dev/ui/layout/constraints#example-2  (score 0.6955)

trace: e2c97be2c40fe72b5fe6a5034d945e16
```

Сохранённые ответы, отчёты ingest и trace — в `docs/evidence/stage03/` (см. README там).

## Структура

```text
lab1/
├── pyproject.toml, uv.lock   # зависимости (requirements.txt экспортируется из lock)
├── src/flutter_rag/
│   ├── grabber/ preprocessing/ embeddings/ vectorstore/
│   ├── retrieval/ reranking/ filtering/ generation/
│   ├── evaluation/ observability/ api/
│   ├── config.py  cli.py
├── configs/      # slice.yaml (этап 03), full*.yaml (полный корпус), base.yaml (черновик)
├── prompts/      # answer/v1…v2, judge/v1 + CHANGELOG
├── evaluation/   # datasets/flutter-qa-v1/{dev,test}.jsonl (не индексируются)
├── data/         # manifests/ в Git; raw/, cache/, index/ — локально, git-ignored
├── experiments/  # runs/<run_id>/{config.yaml, raw.jsonl, metrics.json, meta.json}
└── tests/
```

Отличие от примерной структуры методички: модули лежат внутри пакета
`src/flutter_rag/` (src-layout), чтобы импорты были однозначными, и добавлены
`vectorstore/`, `filtering/`, `observability/`, `api/` как отдельные зоны ответственности.

## Результаты экспериментов, выводы

На проверенном `dev` сопоставлены варианты разбиения, embeddings, размер пула,
порог, rerank, промпты и генераторы. Выбраны fixed 512 с overlap 15%, K=10,
порог 0,65, Flash-Lite и answer/v1.2. Единственная итоговая оценка на 30 `test`
дала 24/24 ответов на вопросы с ответом, 6/6 правильных отказов и 21/24 ответов
с оценкой ≥4/5 по корректности и обоснованности одновременно.
[Отчёт экспериментов](experiments/report.md) · [Конфиг](experiments/configs/s06-final.yaml)

## Лицензия корпуса

Документация Flutter — © Flutter project authors, CC BY 3.0; примеры кода — BSD.
