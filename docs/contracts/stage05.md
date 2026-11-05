# Контракты этапа 05 — полный pipeline и evaluation

Ревизия 1, 2026-11-06, интегратор — Claude Code (Opus 5.5). Код контрактов: ветка
`stage-05-full-pipeline` (схема `runconfig.py`, `Chunk.section_ids`, `Candidate.rerank_score`,
`pipeline.search()`, протоколы `make_embedder` / `Reranker`). Изменение контракта — только через
интегратора; исполнитель модуля сообщает о нужном изменении, а не правит чужой модуль.

## 0. Решения, подтверждённые реальными запросами (2026-11-06)

| Роль | Модель | Факт |
|---|---|---|
| Embeddings #1 | `gemini-embedding-001`, 768 | этапы 03–04; 100 RPM / 30K TPM / 1K RPD (AI Studio) |
| Embeddings #2 | Voyage `voyage-4-lite`, 1024 (по умолчанию) | HTTP 200, document и query, 1024 dims; заголовков rate limit нет |
| Reranker | Voyage `rerank-2.5` | HTTP 200, relevance_score; 17 токенов на тестовый вызов |
| LLM #1 | `gemini-3.5-flash-lite` | этапы 03–04; 15 RPM / 500 RPD; частые 503 high demand |
| LLM #2 | `gemma-4-31b-it` (открытая модель, через Gemini API) | HTTP 200, system_instruction + JSON schema работают; ~18 с; 30 RPM / 14.4K RPD |
| Режим (резерв) | flash-lite c `thinking_budget` | не подтверждён: 3 × 503 |

Лимиты Voyage free tier без способа оплаты — 3 RPM / 10K TPM: это подтверждает заголовок
`x-api-warning` каждого ответа аккаунта (smoke retrieval-engineer, `docs/evidence/stage05/voyage-smoke.txt`;
наблюдались реальные 429 при серии запросов). В конфигах `max_rpm: 3`, `max_tpm: 9000` для embeddings и rerank.
Вопрос 2 к преподавателю («бесплатные квоты API = бесплатные модели?») не закрыт; `gemma-4-31b-it`
— открытая модель и закрывает §12 при отрицательном ответе.

## 1. Корпус

Фиксированный snapshot: `flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb`
(`configs/full.yaml`, `corpus.ref` = этот SHA, `corpus.name: full`). Все include/exclude как в base.yaml.
Dataset размечается на этом же snapshot.
Manifest хранится по `corpus.name` (`data/manifests/<corpus.name>/`), как и коллекция: конфиги,
отличающиеся только LLM/prompt/top_k/rerank, делят один snapshot и один индекс. Поле manifest
`config_id` с этой ревизии содержит имя корпуса (историческое имя поля).

## 2. Chunking (corpus-engineer)

`chunk_document(document_id, title, url, body, cfg) -> list[Chunk]` — сигнатура не меняется.

| strategy | Правило | overlap |
|---|---|---|
| `section` | как этап 03: не пересекает заголовок, блоки до max_tokens, код по D10/H4 | 0 |
| `fixed` | окна по `max_tokens` по всему очищенному телу, без учёта структуры; разрез по границе строки (не посреди строки), длинная строка — по словам; код может разрезаться, тогда `code_split=True` | 0 ≤ o < 0.5, шаг = max_tokens·(1−o) |
| `paragraph` | абзацы (fenced-блок = один абзац) упаковываются до max_tokens, могут пересекать заголовки; абзац > max_tokens режется как в section | 0 |

Для всех стратегий:
- `strategy_id = f"{strategy}-{max_tokens}-o{int(overlap*100)}"`; `chunk_id = uuid5(NS, f"{strategy_id}|{document_id}|{ordinal}")`;
- `section_ids`: **все** секции, которые пересекает текст chunk, в порядке появления,
  формат `"<document_id>#<anchor>"`, до первого заголовка — `"<document_id>#"`; anchors те же,
  что у section (`_parse_sections`, `slugify`, `{:#id}`, дубли `-1`);
- `section_path` и `anchor` — первой секции chunk; `embed_text` = `"Page: {title} > {path}\n\n{text}"` (H1);
- `token_count` = `estimate_tokens(embed_text)`; детерминизм: одинаковый вход → одинаковые chunks.

Варианты эксперимента (этап 06): fixed 256/512/1024 × o0, fixed 512 o15, paragraph 512, section 512.

## 3. Embeddings, reranker, filtering (retrieval-engineer)

- `make_embedder(cfg: EmbeddingConfig, settings) -> EmbeddingProvider`: `gemini` (есть) и `voyage`.
  Voyage: `input_type` = `document`/`query`, `output_dimension = cfg.dimensions`, батчи с учётом
  лимитов провайдера и `max_tpm`, `RateLimiter(cfg.max_rpm, cfg.max_tpm)`, повторы через
  `flutter_rag.retry`, ошибки → `UpstreamError(provider="voyage", kind=...)` (401/403 → auth,
  429 → rate_limited, 5xx/timeout → unavailable/timeout), без утечки ключа. `model_id`, `dimensions`, `max_batch`.
- `make_reranker(cfg: RerankingConfig, settings) -> Reranker | None` (None при `enabled: false`).
  `rerank(query, candidates, top_n)`: возвращает ≤ top_n **тех же** объектов Candidate, лучшие
  первыми, с `rerank_score`; документы — `chunk.embed_text`; повторы/ошибки как у embeddings.
- Ключ Voyage обязателен только если `embedding.provider == voyage` или `reranking.enabled`
  (`pipeline.required_secrets`, уже сделано).
- Коллекции не смешиваются: имя включает `embedding.slug` (модель+dims) и `strategy_id`.
- `filtering.min_score` калибруется на dev **отдельно для каждой embedding-модели** (этап 06).

## 4. Поиск и ответ (интегратор, сделано)

`pipeline.search(rt, question) -> SearchResult(retrieved, kept, ranked, context, dropped)`:
retrieve (top_k) → filter → rerank (если включён) → build_context. Каждая стадия — observation
в текущей trace. `ask()` использует `search()`; `Answer.retrieved` (порядок вектора) и
`Answer.ranked` (после filter+rerank) — строки с `rank, score, rerank_score, document_id,
section, section_ids, chunk_id`. Пустой индекс → `IndexNotReadyError`, сбой провайдера → `UpstreamError`.

Prompts: `answer/v1.2` (основной) и `answer/v2` (вариант: сначала выписать опорные факты,
строже правило цитирования) — интегратор. LLM: `generation.model` + `thinking_budget`.

## 5. Evaluation (evaluation-engineer)

### 5.1 Dataset `lab1/evaluation/datasets/flutter-qa-v1/{dev,test}.jsonl`

45 вопросов: **15 dev + 30 test**; 5 типов × (3 dev + 6 test); язык ≈ поровну ru/en в каждом типе.
Одна строка JSON:

```json
{
  "id": "dev-001", "split": "dev", "dataset_version": "flutter-qa-v1",
  "type": "factoid | multi_doc | lookup | contextual | unanswerable",
  "language": "ru | en",
  "question": "...",
  "answerable": true,
  "expected_answer": "краткий эталон",
  "must_include": ["ключевые факты/идентификаторы, проверяемые детерминированно"],
  "expected_code": "фрагмент кода или null",
  "gold_documents": ["ui/layout/constraints"],
  "gold_sections": ["ui/layout/constraints#example-3"],
  "supporting_excerpts": [{"section_id": "...", "text": "дословная цитата из очищенного текста"}],
  "corpus_commit": "4fee0255ef9f0c85f6dd37513bf659613f57e5eb",
  "status": "draft | agent_checked | verified",
  "notes": "..."
}
```

- `unanswerable`: `answerable=false`, gold пустые; тема правдоподобна для Flutter, но в корпусе её нет
  (проверяется поиском по корпусу, а не догадкой). `multi_doc` — ≥ 2 разных `gold_documents`.
- Валидатор (`flutter-rag dataset-check`): схема, распределение 15/30 и типов, уникальные id,
  каждая `supporting_excerpts.text` дословно есть в очищенном тексте документа на snapshot,
  каждый `gold_sections` существует среди anchors документа, отсутствие вопросов test в dev.
- Статусы: `draft` — составлено; `agent_checked` — проверено отдельным субагентом Claude по
  исходному тексту (не независимая проверка); `verified` — Codex/Gemini или студент. До этапа 06
  ни один вопрос не помечается `verified` без такой проверки.
- Dataset не индексируется: корпус берётся только из GitHub `flutter/website`; тест проверяет,
  что `corpus.include` не может совпасть с путями `lab1/evaluation/**` (N04).

### 5.2 Метрики (чистые функции, `evaluation/metrics.py`)

Ранжированный список = `SearchResult.ranked` (после filter + rerank). Совпадение chunk с gold —
пересечение `chunk.section_ids` с `gold_sections` (секционный уровень) или `document_id` с
`gold_documents` (документный уровень). Для каждого K ∈ {1,3,5,10,20}: Hit@K, Recall@K
(доля покрытых gold_sections), Precision@K, MRR. Только для `answerable`.
Генерация: refusal accuracy (по `status`, отдельно answerable/unanswerable), upstream_error
отдельно (не смешивается с отказом), citation precision (цитированные источники ∈ gold),
`must_include` / `expected_code` presence, LLM-as-a-Judge (correctness, faithfulness 1–5,
structured output, temperature 0, prompt `judge/v1`, модель — отдельная от генератора,
фиксируется в meta). В отчёте — абсолютные числа k/n ([2.5]).

### 5.3 Runner `flutter-rag evaluate --config <yaml> --split dev [--final] --mode retrieval|full`

- `--split test` без `--final` запрещён (N03); final-запуск записывает это в meta.
- Каждый вопрос — trace `eval.retrieval` / `eval.full` (session = run_id), scores в Langfuse.
- Результат: `lab1/experiments/runs/<run_id>/{config.yaml, raw.jsonl, metrics.json, meta.json}`;
  meta: git SHA + dirty, corpus commit, dataset version + sha256, config fingerprint, model IDs,
  prompt version/sha, judge model, Langfuse trace IDs, ошибки.
- Возобновление: повторный запуск с тем же `--run-id` пропускает вопросы, уже записанные в raw без
  ошибки (квоты, 503). Ошибочные строки сохраняются и не исчезают из raw.

## 6. Владение файлами и порядок

| Исполнитель | Разрешённые пути | Волна |
|---|---|---|
| corpus-engineer (субагент Claude, worktree) | `src/flutter_rag/preprocessing/`, `tests/test_preprocessing.py`, новые `tests/test_chunking_*.py` | 1 |
| retrieval-engineer (субагент Claude, worktree) | `src/flutter_rag/{embeddings,reranking,retrieval,filtering,vectorstore}/`, их тесты | 1 |
| evaluation-engineer (субагент Claude, worktree) | `src/flutter_rag/evaluation/`, `lab1/evaluation/`, `lab1/experiments/`, `lab1/prompts/judge/`, `cmd_evaluate`/`dataset-check` в `cli.py`, их тесты | 2 |
| интегратор | `runconfig.py`, `pipeline.py`, `generation/`, `prompts/answer/`, `configs/`, lockfile, docs | все |

Одновременно — не более двух субагентов (AGENTS.md). Волна 2 стартует после слияния волны 1.
