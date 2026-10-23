# Архитектура Flutter Docs RAG (лабораторная №1)

Статус: **проектная архитектура этапа 01**, до независимого аудита (этап 02).
Здесь нет измеренных результатов: все числа — стартовые значения или оценки.
Факты, проверенные 2026-10-23, помечены «проверено»; предположения — «A-n».

## 1. Контекст и границы

- Корпус: репозиторий `flutter/website`, ветка `main`
  (проверено: HEAD `3eb87869bb0d…`, ~761 `.md` в `sites/docs/src`, лицензия CC BY 3.0 + BSD для кода).
  Страницы — Markdown с YAML front matter, Liquid-подобными `{% include %}`,
  директивами `<?code-excerpt ...?>`, admonitions `:::note` и reference-ссылками.
- В репозитории Flutter есть `AGENTS.md`, `.agents/skills/` — это **данные корпуса**, они
  исключаются из индекса и никогда не исполняются как инструкции (защита от prompt injection).
- URL страницы: `sites/docs/src/content/<p>.md` → `https://docs.flutter.dev/<p>`
  (`index.md` → каталог). A-1: схема совпадает для всех страниц — проверить на этапе 03.
- Однопроцессное приложение на Mac mini M4. Микросервисы — лабораторная №2.

## 2. Модули

| Модуль `flutter_rag.*` | Ответственность | Вход → выход | Внешние зависимости |
|---|---|---|---|
| `grabber` | Получить snapshot корпуса, вычислить diff | repo, ref, include/exclude → `CorpusManifest`, файлы в `data/raw/<sha>/` | GitHub REST (trees), raw.githubusercontent.com |
| `preprocessing` | Очистка, нормализация, chunking | `SourceDocument` → `list[Chunk]` | — |
| `embeddings` | Векторизация документов и запросов | `list[str]`, `task` → `list[vector]` | Gemini API, Voyage API |
| `vectorstore` | Коллекции, upsert/delete/search | `Chunk`+vector → точки Qdrant | qdrant-client (embedded или сервер) |
| `retrieval` | Query embedding + Top-K | `Query` → `list[Candidate]` | embeddings, vectorstore |
| `filtering` | Порог score, dedupe, min length, metadata, бюджет контекста | candidates → candidates | — |
| `reranking` | Переупорядочить кандидатов | query + candidates → candidates | Voyage rerank (вкл/выкл) |
| `generation` | Prompt + LLM, проверка ссылок, отказ | query + context → `Answer` | Gemini API |
| `observability` | Trace/span/generation, prompt version | события pipeline → Langfuse | Langfuse SDK v5 |
| `evaluation` | Dataset, метрики, runner, raw results | config + dataset → `RunResult` | все выше |
| `api` / `cli` | Точки входа | HTTP/CLI → pipeline | FastAPI |
| `config` | Настройки, секреты (SecretStr) | env/.env + YAML → `Settings`, `RunConfig` | pydantic-settings |

Правило зависимостей: внешние SDK вызываются только из `embeddings`, `reranking`,
`generation`, `grabber`, `vectorstore`, `observability`. Остальные модули — чистая логика,
тестируются без сети. Провайдеры скрыты за `Protocol`, чтобы замена модели была явной
сменой конфигурации, а не правкой кода.

## 3. Потоки

### 3.1 Ingestion

```text
flutter-rag ingest --config configs/base.yaml
 1. grabber: GET /repos/flutter/website/commits/main → commit_sha (фиксируем snapshot)
 2. grabber: GET /git/trees/<sha>?recursive=1 → пути + blob_sha (1 запрос на весь корпус)
 3. diff с прошлым manifest по blob_sha: added / modified / deleted / unchanged
 4. скачать только added+modified с raw.githubusercontent.com/<owner>/<repo>/<sha>/<path>
 5. записать data/raw/<sha>/..., data/manifests/<sha>.json (+ latest.json)
 6. preprocessing: front matter → title/description; resolve или удалить include;
    удалить HTML/директивы; сохранить fenced code; секции по заголовкам
 7. chunking по стратегии из конфига → Chunk с provenance
 8. embeddings: только chunks с новым content_hash (кэш по model+dims+task+hash)
 9. vectorstore: upsert по детерминированным ID; delete точек deleted/изменённых документов
10. отчёт ingest: counts, ошибки по файлам, длительность; trace в Langfuse
```

Идемпотентность: повторный запуск при том же SHA → 0 загрузок, 0 embedding-вызовов,
число точек не меняется. Ошибка одного файла не роняет весь запуск: файл помечается
`failed` в manifest и повторяется в следующий раз; manifest пишется атомарно (tmp + rename).

### 3.2 Query

```text
ask(question, config)
 trace "rag.ask" (config_id, corpus_sha, prompt_version, model ids)
 ├─ span embed_query      (task = query)
 ├─ span vector_search    top_k кандидатов + scores
 ├─ span filter           threshold → dedupe (по document_id+section) → min_chars → metadata
 ├─ span rerank           (если включён) → top_n
 ├─ span build_context    бюджет max_context_tokens, порядок, нумерация источников [1..n]
 ├─ если кандидатов нет → status=insufficient_context БЕЗ вызова LLM
 ├─ generation llm        system prompt (версия) + context + question
 └─ span validate         цитаты [n] ⊆ переданных источников; иначе пометка/отказ
→ Answer
```

### 3.3 Evaluation

```text
flutter-rag evaluate --config configs/<exp>.yaml --split dev
 1. загрузить dataset (version, split); test доступен только с флагом --final
 2. retrieval-only режим: Recall@K, Hit@K, MRR по размеченным document/section IDs
 3. full режим: ответы → faithfulness/correctness (LLM-as-a-Judge + ручная выборка), refusal accuracy
 4. сохранить experiments/runs/<run_id>/{config.yaml, raw.jsonl, metrics.json, meta.json}
    meta: git SHA, corpus SHA, dataset version, model IDs, prompt version, Langfuse trace IDs
 5. scores в Langfuse как scores к trace/dataset run
```

Сравнение chunking-стратегий идёт по документам/секциям (стабильны между стратегиями),
а не по ID chunks.

## 4. Контракты данных

```python
class SourceDocument:           # результат grabber
    document_id: str            # путь в репо относительно content/, напр. "ui/layout/constraints"
    path: str                   # полный путь в репо
    url: str                    # https://docs.flutter.dev/...
    title: str
    blob_sha: str               # git blob SHA — детектор изменений
    source_commit: str          # commit snapshot
    fetched_at: datetime
    raw_markdown: str

class Chunk:
    chunk_id: str               # uuid5(NS, f"{strategy_id}|{document_id}|{ordinal}")
    document_id: str
    strategy_id: str            # напр. "section-512-o0"
    ordinal: int
    section_path: list[str]     # ["Understanding constraints", "Examples", "Example 3"]
    anchor: str | None          # #example-3 для ссылки
    text: str                   # то, что эмбеддится (с заголовком секции)
    has_code: bool
    token_count: int            # оценка (A-2)
    content_hash: str           # sha256(text)

class Candidate:  chunk: Chunk; score: float; rerank_score: float | None; stage_rank: dict[str,int]

class Answer:
    status: Literal["answered", "insufficient_context", "upstream_error"]
    text: str | None
    sources: list[Source]       # только реально переданные в контекст chunks
    trace_id: str | None
    config_id: str; prompt_version: str; llm_model: str; embedding_model: str
    usage: dict | None; latency_ms: dict[str, float]
    error: ErrorInfo | None     # kind, provider, retryable — без stack trace
```

Payload точки Qdrant (= metadata §5 методички, расширенная):
`source="flutter-docs"`, `url`, `title`, `section` (строка из section_path), `document_id`,
`updated_at` (= fetched_at; A-3: дата последнего commit файла не запрашивается ради квоты),
`source_commit`, `blob_sha`, `strategy_id`, `ordinal`, `has_code`, `content_hash`, `text`.

Коллекции: `flutter__<embedding-slug>-<dims>__<strategy_id>` — разные модели и размерности
**никогда** не смешиваются в одной коллекции; метрика cosine.

### HTTP API (этап 03)

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` — процесс жив |
| GET | `/ready` | проверка коллекции и наличия ключей; 503 + причина, если не готово |
| POST | `/ask` | вход `{question, config_id?, top_k?, rerank?}` → `Answer` |

HTTP-коды: 200 для `answered` и `insufficient_context`; 422 неверный ввод;
429 исчерпан лимит провайдера после повторов; 503 внешний сервис недоступен.

## 5. Обработка ошибок

| Ситуация | Поведение | Пользователь видит |
|---|---|---|
| GitHub 403/429 rate limit | Ждать до `X-RateLimit-Reset`/`Retry-After` (ограничено), затем fail с понятным сообщением; `GITHUB_TOKEN` опционален | «лимит GitHub, повторите позже / задайте токен» |
| Ошибка загрузки одного файла | 3 повтора с backoff, затем `failed` в manifest | итог ingest: N failed |
| Embedding/LLM 429 | tenacity: экспоненциальный backoff + jitter, ≤3–5 попыток, уважать retry-delay | `upstream_error` (429) |
| Embedding/LLM 5xx / timeout | таймаут на запрос (A-4: 30 с LLM, 20 с embeddings), ≤3 повтора | `upstream_error` (503) |
| 400 / превышение контекста | без повторов; бюджет контекста считается заранее | `upstream_error`, kind=bad_request |
| Нет кандидатов выше порога | LLM не вызывается | `insufficient_context` |
| LLM ответила без цитат или с чужими [n] | пометка `unsupported_citation`, в строгом режиме — отказ | ответ с предупреждением |
| Qdrant недоступен / нет коллекции | `/ready` = 503 | `upstream_error` |
| Langfuse недоступен | ответ всё равно выдаётся, `trace_id=null`, warning в лог; в evaluation запуск помечается `trace_missing` | ответ |

Принцип: «в корпусе нет ответа» (`insufficient_context`) и «сервис недоступен»
(`upstream_error`) — разные статусы и не смешиваются в метриках. Fallback на другую модель
**не** делается молча: если он включён, модель в `Answer`/trace меняется явно.

## 6. Начальные решения (ADR-черновики)

| # | Решение | Почему | Альтернативы | Как проверим |
|---|---|---|---|---|
| D1 | Python 3.12 + uv, lockfile | Системный 3.9.6 не поддерживается SDK (проверено: google-genai, fastapi требуют ≥3.10); uv даёт воспроизводимый lock и свой Python | pyenv+pip, Homebrew python, conda | `uv sync` на чистом checkout в CI |
| D2 | Источник — GitHub `flutter/website` Markdown, а не HTML-сайт | Чистая структура, заголовки, код, front matter; commit SHA = точный snapshot; diff по blob SHA за 1 запрос | Crawler docs.flutter.dev (шум навигации, нет версии), `git clone` (≈3 ГБ репо; sparse checkout — вариант) | Повторный ingest, diff между SHA |
| D3 | Qdrant, embedded local mode на этапе 03 | Нет Docker на Mac (проверено); embedded не требует сервера, API тот же, что у сервера; payload-фильтры, именованные коллекции | Qdrant binary/Docker (позже для `/ready`), FAISS (нет metadata-фильтров и upsert из коробки), Chroma | Тест upsert/delete/search; переход на сервер одной переменной `QDRANT_URL` |
| D4 | Embeddings #1: Gemini `gemini-embedding-001`, 768 dims, task RETRIEVAL_DOCUMENT/RETRIEVAL_QUERY | Тот же ключ, что и LLM; явное разделение query/document; MRL позволяет 768 (проверено в docs: 128–3072) | `gemini-embedding-2` (8192 токенов, инструкция в тексте) | Smoke-запрос, проверка длины вектора |
| D5 | Embeddings #2: Voyage `voyage-4-lite` (кандидат) | Другая архитектура/провайдер; 200M бесплатных токенов (проверено на pricing) | Открытая модель локально (BGE/E5 через sentence-transformers) — ближе к букве §7, но тянет torch | Решение после аудита и ответа преподавателя (вопрос 2 в requirements) |
| D6 | Reranker: Voyage `rerank-2.5` | Бесплатная квота (проверено), простой API | Локальный cross-encoder (bge-reranker), LLM-rerank | Сравнение on/off при одинаковом числе кандидатов |
| D7 | LLM: Gemini через `google-genai`; конкретный ID — после реального запроса | Подписка ≠ API: доступность и квоту подтверждаем маленьким запросом (AGENTS.md) | Другие модели Gemini как 2-я модель/режим (thinking on/off) | Smoke + фиксация model ID в trace |
| D8 | Langfuse Cloud (EU), SDK v5, `flush()` в конце CLI | Обязателен; Cloud не требует Docker; env: `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL` (проверено в docs) | Self-hosted Langfuse (нужен Docker+Postgres+ClickHouse) | Trace видна в UI после короткого скрипта |
| D9 | Prompts версионируются (`v1`, `v2`) и пишутся в trace | Требование преподавателя, воспроизводимость | Langfuse Prompt Management как источник правды — решить на этапе 03 | prompt_version в каждой trace |
| D10 | Стартовый chunking: секции по заголовкам ≤512 токенов, fenced code неделим | Документация структурирована заголовками; код важен для ответов | fixed 256/512/1024, overlap 15%, paragraph — как варианты эксперимента | Эксперимент R15 |
| D11 | Отказ двухуровневый: порог до LLM + инструкция в prompt | Экономит квоту и снижает галлюцинации | Только prompt | Вопросы «нет в базе» в dataset |
| D12 | src-layout `src/flutter_rag/<module>` | Однозначные импорты, тесты против установленного пакета | Плоский `src/<module>` из примера методички | — |

## 7. Предположения и риски

- A-1 URL-схема docs.flutter.dev совпадает с путями content/ — проверить выборкой.
- A-2 Токены считаются приближённо (символы/4 или `count_tokens` Gemini); для бюджета
  контекста берём запас 20%.
- A-3 `updated_at` = время получения, а не дата изменения страницы.
- A-4 Таймауты — стартовые значения, уточняются по реальной задержке.
- A-5 Бесплатных квот Gemini/Voyage хватит на 45 вопросов × несколько конфигураций при
  кэшировании embeddings. Риск: лимиты RPM/RPD free tier — runner обязан уметь пауза/продолжение.
- A-6 Включаемые фрагменты `{% include %}` из `sites/docs/src/_includes` нужно либо подставлять,
  либо удалять; решение по результатам анализа на этапе 03.
- Риск: страницы `release/breaking-changes` (189 шт.) могут доминировать в поиске —
  кандидат на metadata-фильтр/отдельный эксперимент. Release notes исключены из корпуса в base.yaml.
- Риск: free tier Gemini может использовать данные запросов для улучшения продуктов — корпус
  публичный, личные данные не отправляем.

## 8. Что сознательно не делаем в lab1

Микросервисы, аутентификация, очереди, Docker/Kubernetes, полный декартов перебор параметров,
UI сложнее одной страницы/CLI.
