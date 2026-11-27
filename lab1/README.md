# Lab 1 — Flutter Docs RAG

## Описание проекта

Система отвечает на вопросы по официальной документации Flutter и указывает
источники. Если собранных фрагментов недостаточно, она сообщает об этом.
Полный корпус исследования содержит 647 страниц из одного снимка
`flutter/website`. В лабораторной сравниваются варианты поиска и генерации.

## Архитектура

```text
GitHub → grabber → очистка Markdown → chunks → embeddings → Qdrant
Вопрос → embedding → Top-K → фильтры → rerank (опция)
       → ограниченный контекст → LLM → проверка ответа и ссылок
                                └────→ Langfuse
```

Grabber сохраняет сырой Markdown и манифест снимка, повторно скачивает
изменившиеся файлы. Размер и overlap фрагмента влияют на поиск. Фильтры
применяют порог similarity, убирают дубли и ограничивают контекст. Judge
использует эталон только во время оценки. Пакет `src/flutter_rag/` разделён
по этапам пайплайна, конфиги лежат в `configs/`, протоколы и сохранённые
прогоны — в `experiments/`. [Архитектура](../docs/architecture.md) ·
[Матрица требований](../docs/requirements.md)

## Используемые технологии

| Компонент | Реализация |
|---|---|
| Сбор и API | Python 3.12, GitHub API, Markdown, FastAPI |
| Embeddings | Gemini `gemini-embedding-001` (768) и Voyage `voyage-4-lite` (1024) |
| Хранилище и rerank | Qdrant embedded или серверный, Voyage `rerank-2.5` |
| Генерация | `gemini-3.5-flash-lite` и `gemma-4-31b-it` через Gemini API |
| Evaluation | `flutter-qa-v1`, метрики поиска и отказа, `gemini-3.1-flash-lite` с `judge/v1` |
| Трассировка | Langfuse, версии промптов в Git |

## Установка

На macOS или Linux нужны Git и [uv](https://docs.astral.sh/uv/). `uv` установит Python 3.12
и зависимости из `uv.lock`.

```sh
git clone https://github.com/yr3kdvdv/flutter-docs-rag.git
cd flutter-docs-rag
test -f .env || cp .env.example .env
cd lab1
uv sync --locked
uv run --locked flutter-rag env-check
```

Заполните `.env` в корне репозитория. `env-check` печатает только наличие
секретов. [Настройка аккаунтов](../docs/SETUP_ACCOUNTS.md)

## Запуск

### Команды

Быстрый запуск из `lab1/` использует две страницы зафиксированного снимка.
Запускайте `serve` после завершения ingest.

```sh
uv run --locked flutter-rag ingest --config configs/demo.yaml
uv run --locked flutter-rag ask --config configs/demo.yaml "Как Flutter выбирает размер виджета?"
uv run --locked flutter-rag serve --config configs/demo.yaml
```

### Полный корпус

Для исследования на полном корпусе используйте один конфиг для всех команд.
Первый полный ingest скачивает корпус и векторизует его через Gemini API,
поэтому нужны квота и время. Последующие запуски используют локальный кэш.

```sh
final_config=experiments/configs/s06-final.yaml
uv run --locked flutter-rag ingest --config "$final_config"
uv run --locked flutter-rag dataset-check --config "$final_config"
uv run --locked flutter-rag evaluate --config "$final_config" --split dev --mode retrieval
uv run --locked flutter-rag ask --config "$final_config" "Как Flutter выбирает размер виджета?"
```

В полном режиме оценки добавьте `--mode full`, чтобы вызвать генератор и
judge. Прерванную оценку возобновляют с тем же `--run-id` и теми же входами.
Исторический `test` анализируется по сохранённым данным. Для локальной
проверки изменённого поведения используется `dev` или демонстрационные
вопросы. [Сценарий защиты](../docs/defense/demo-script.md)

## Конфигурация

| Переменная | Назначение |
|---|---|
| `GEMINI_API_KEY` | Embeddings, генератор или judge Gemini |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Трассировка и чтение трасс |
| `LANGFUSE_BASE_URL` | Адрес Langfuse, по умолчанию `https://cloud.langfuse.com` |
| `VOYAGE_API_KEY` | Нужен при embeddings или rerank Voyage |
| `GITHUB_TOKEN` | Необязательный токен для квоты чтения GitHub API |
| `DATA_DIR`, `QDRANT_PATH` | Каталог данных и путь embedded Qdrant. Для изолированного демо задайте оба |
| `QDRANT_URL` | Адрес Qdrant в серверном режиме. Пустое значение включает embedded |

Серверному режиму нужны метаданные коллекций, доступные с Qdrant 1.16.
Для одной серверной коллекции запускайте ingest из одного процесса за раз.
[Документация Qdrant](https://qdrant.tech/documentation/manage-data/collections/#collection-metadata)

`corpus.ref` закрепляет документный снимок. `chunking`, `embedding`
определяют подготовку и коллекцию. `retrieval.top_k`, `filtering`,
`reranking` и `generation` задают поиск, бюджет контекста, модель и промпт.
Конфиги `configs/full.yaml`, `configs/full-voyage.yaml` и
`configs/full-gemma.yaml` сохранены для сравнения. Без явного конфига
`ingest`, `ask` и `serve` используют `configs/slice.yaml`, а `evaluate` —
`configs/full.yaml`.

Коды CLI: `0` — успех или корректный отказ, `2` — конфигурация или индекс
не готов, `3` — локальный Qdrant занят, `4` — ошибка внешнего сервиса или
незавершённая оценка. Для восстановления после прерванного ingest повторите
команду с тем же конфигом. При `3` остановите локальный `serve` перед
CLI-командами, которые обращаются к тому же embedded Qdrant. При `4`
проверьте указанный сервис или квоту и повторите операцию после восстановления.
Сырые документы, индекс и кэш хранятся локально в `data/`.

## API

`serve` по умолчанию слушает `127.0.0.1:8000`, схема OpenAPI доступна на
`/docs`.

| Запрос | Ответ |
|---|---|
| `GET /health` | `200`, `{"status":"ok"}` |
| `GET /ready` | `200` с `collection` и числом точек или `503`, если индекс недоступен |
| `POST /ask` с `{"question":"..."}` | `200`, статус `answered` или `insufficient_context`, поля `text`, `sources`, `warnings`, `trace_id`, `trace_url`. `422` для недопустимого запроса, `429` при ограничении провайдера, `503` при недоступности индекса или другой ошибке провайдера. |

Если ответ не проходит проверку ссылок или языка, генератор получает
одну попытку исправления с тем же контекстом. Повторное нарушение
возвращается как `upstream_error` с HTTP 503, а обе попытки видны в трассе.

## Примеры использования

При запущенном `serve` отправьте вопрос через HTTP.

```sh
curl --fail-with-body http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"How do constraints, sizes and position flow in Flutter layout?"}'
```

В удачном ответе поле `sources` связывает числовые ссылки с документами
контекста. Для запроса вне корпуса ожидается `insufficient_context` с
пустым `sources`. Отдельно Trace ID можно проверить командой
`uv run --locked flutter-rag trace-show <trace_id>`.
[Сохранённые ответы и трассы](../docs/evidence/stage03/README.md)

## Тестирование

```sh
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python experiments/analyze.py --final \
  experiments/runs/s06-*-dev experiments/runs/s06-final-test
```

Pytest использует заглушки провайдеров и локальный Qdrant. Офлайн-анализатор
читает сохранённые попытки и агрегаты. Реальные ответы и доставка в Langfuse
проверяются сценарием демонстрации. [Доказательства выпуска](../docs/evidence/stage08/README.md)

## Результаты экспериментов

Сравнили chunking и overlap, Gemini и Voyage embeddings, Top-K, пороги,
rerank, два генератора и два промпта на `dev`. До единственной финальной
оценки зафиксировали fixed 512, overlap 15%, K=10, порог 0,65, Flash-Lite
и `answer/v1.2`.

| Исторический результат этапа 06 на `test` | Значение |
|---|---:|
| Вопросы с ответом, на которые система дала ответ | 24/24 |
| Правильные отказы | 6/6 |
| Correctness и faithfulness одновременно ≥4/5 | 21/24 |
| Micro Recall@5 по gold-секциям | 32/33 |

[Отчёт и сырые прогоны](experiments/report.md) ·
[Зафиксированный выбор](experiments/selection.md) ·
[Разметка датасета](evaluation/datasets/flutter-qa-v1/README.md)

## Выводы

На секционном baseline rerank добавил одну gold-секцию в первые пять
результатов. Эффект rerank на выбранном fixed-индексе отдельно не измерялся.
В финальном прогоне нужная секция была в первых пяти для всех 24 вопросов
с ответом, однако три ответа не прошли порог judge. Поэтому качество
поиска и полноту ответа оценивали отдельно. Выводы ограничены размером
набора и родством judge с основным генератором.

Документация Flutter — © Flutter project authors, CC BY 3.0. Примеры кода — BSD.
