# Lab 1 — Flutter Docs RAG

RAG-система, отвечающая на вопросы по официальной документации Flutter
(`flutter/website`, Markdown) с указанием источников и трассировкой в Langfuse.

**Статус: этап 01 — подготовлены среда, каркас и документы. RAG ещё не реализован.**
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

### Работают сейчас (проверено на этапе 01)

| Команда | Что делает |
|---|---|
| `uv sync` | Воспроизводимо ставит зависимости из `uv.lock` |
| `uv run pytest` | Проверки среды и каркаса (не проверяют RAG) |
| `uv run ruff check .` | Линтер |
| `uv run flutter-rag env-check` | Версии и наличие ключей: `set`/`MISSING`, без значений |

### Ещё не реализованы (возвращают код 2 и сообщение `not implemented`)

| Команда | Этап |
|---|---|
| `uv run flutter-rag ingest` | 03: grabber → chunks → embeddings → Qdrant |
| `uv run flutter-rag ask "..."` | 03: ответ + источники + trace Langfuse |
| `uv run flutter-rag serve` | 03: FastAPI `/health`, `/ready`, `/ask` |
| `uv run flutter-rag evaluate` | 05: прогон эксперимента по dataset |

## Структура

```text
lab1/
├── pyproject.toml, uv.lock   # зависимости (requirements.txt экспортируется из lock)
├── src/flutter_rag/
│   ├── grabber/ preprocessing/ embeddings/ vectorstore/
│   ├── retrieval/ reranking/ filtering/ generation/
│   ├── evaluation/ observability/ api/
│   ├── config.py  cli.py
├── configs/      # конфигурации экспериментов (base.yaml — черновик)
├── data/         # снапшоты корпуса (сырые данные в git не попадают)
├── experiments/  # результаты (пока пусто)
└── tests/
```

Отличие от примерной структуры методички: модули лежат внутри пакета
`src/flutter_rag/` (src-layout), чтобы импорты были однозначными, и добавлены
`vectorstore/`, `filtering/`, `observability/`, `api/` как отдельные зоны ответственности.

## Конфигурация, API, примеры, тестирование, результаты, выводы

Появятся на этапах 03–06. Сейчас результатов экспериментов нет.

## Лицензия корпуса

Документация Flutter — © Flutter project authors, CC BY 3.0; примеры кода — BSD.
