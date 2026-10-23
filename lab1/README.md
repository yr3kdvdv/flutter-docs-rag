# Lab 1 — Flutter Docs RAG

RAG-система, отвечающая на вопросы по официальной документации Flutter
(`flutter/website`, Markdown) с указанием источников и трассировкой в Langfuse.

**Статус: этап 03 — работает сквозной срез на 8 страницах документации** (реальные Gemini API,
Qdrant, Langfuse). Эксперименты, reranker, вторая embedding-модель и dataset — этапы 05–06.
Архитектура: [../docs/architecture.md](../docs/architecture.md).
Матрица требований: [../docs/requirements.md](../docs/requirements.md).

## Технологии (план)

Python 3.12 (через uv), Gemini API (LLM + embeddings), Voyage AI (вторая
embedding-модель и reranker), Qdrant (embedded/локальный режим), Langfuse Cloud,
FastAPI. Обоснование и альтернативы — в architecture.md.

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

### Работают (проверено на этапе 03)

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
| `uv export --no-header --no-hashes --no-dev --no-emit-project -o requirements.txt` | Обновить requirements.txt из lock |

По умолчанию используется `configs/slice.yaml` (8 страниц); другой конфиг — `--config`.

Коды выхода: 0 — успех (в том числе корректный отказ `insufficient_context`), 2 — конфигурация
или нет ключей, 3 — локальная база Qdrant занята другим процессом, 4 — внешний сервис недоступен.

**Важно:** встроенный Qdrant допускает один процесс. Пока работает `serve`, команды `ingest`/`ask`
в другом терминале завершатся с кодом 3 и подсказкой. Это ограничение embedded-режима (аудит B2).

### Ещё не реализованы

| Команда / функция | Этап |
|---|---|
| `uv run flutter-rag evaluate` (возвращает код 2) | 05 |
| Reranker (Voyage), вторая embedding-модель, другие стратегии chunking | 05 |
| Полный корпус (`configs/base.yaml`, 638 страниц) — код готов, но не запускался | 04–05 |

## Пример (реальный запуск 2026-10-23, prompt answer/v1.2)

```text
$ uv run flutter-rag ask "Почему виджет с width: 100 может оказаться не шириной 100 пикселей?"
status: answered

Виджет с width: 100 может оказаться не шириной 100 пикселей, потому что его размер
ограничивается родителем. Например, если экран заставляет корневой Container быть точно
такого же размера, как экран, то Container заполнит весь экран и проигнорирует заданную ширину [5].

Источники:
  [5] Understanding constraints — Examples > Example 2
      https://docs.flutter.dev/ui/layout/constraints#example-2  (score 0.6955)
```

Сохранённые ответы, отчёты ingest и trace — в `docs/evidence/stage03/`.

## Структура

```text
lab1/
├── pyproject.toml, uv.lock   # зависимости (requirements.txt экспортируется из lock)
├── src/flutter_rag/
│   ├── grabber/ preprocessing/ embeddings/ vectorstore/
│   ├── retrieval/ reranking/ filtering/ generation/
│   ├── evaluation/ observability/ api/
│   ├── config.py  cli.py
├── configs/      # slice.yaml (этап 03), base.yaml (полный корпус)
├── prompts/      # версионируемые промпты (answer/v1, v1.1, v1.2 + CHANGELOG)
├── data/         # manifests/ в Git; raw/, cache/, index/ — локально, git-ignored
├── experiments/  # результаты (пока пусто)
└── tests/
```

Отличие от примерной структуры методички: модули лежат внутри пакета
`src/flutter_rag/` (src-layout), чтобы импорты были однозначными, и добавлены
`vectorstore/`, `filtering/`, `observability/`, `api/` как отдельные зоны ответственности.

## Результаты экспериментов, выводы

Появятся на этапах 05–06. Сейчас экспериментов нет: этап 03 — работающий срез.

## Лицензия корпуса

Документация Flutter — © Flutter project authors, CC BY 3.0; примеры кода — BSD.
