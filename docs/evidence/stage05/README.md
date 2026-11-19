# Этап 05 — полный pipeline и evaluation: доказательства

Исполнитель-интегратор: Claude Code (Opus 5.5). Субагенты Claude (отдельные worktrees, ≤ 2 одновременно):
corpus-engineer (chunking), retrieval-engineer (Voyage), evaluation-engineer (dataset, метрики, runner).
Контракты: [docs/contracts/stage05.md](../../contracts/stage05.md). Snapshot корпуса:
`flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb`.

## Что сделано

| Часть | Результат | Проверка |
|---|---|---|
| Chunking | `section` / `fixed` (+overlap) / `paragraph`, `section_ids` для всех | 20 офлайн-тестов; на 4 реальных страницах — детерминизм, совпадение `section` с этапом 03 |
| Voyage embeddings + rerank | `voyage-4-lite` 1024 dims, `rerank-2.5`, httpx, повторы, лимитер | 30 офлайн-тестов; реальный smoke [voyage-smoke.txt](voyage-smoke.txt) (лимит 3 RPM / 10K TPM подтверждён заголовком, реальные 429 с успешным повтором) |
| Pipeline | `search()`: retrieve → filter → rerank → context; ключ Voyage только для Voyage-конфигов | тесты контрактов; реальные ask ниже |
| LLM #2, prompt v2 | `gemma-4-31b-it`; `answer/v2` (вариант для R29) | реальный ask через Gemma ниже; v2 реально не запускался (сравнение — этап 06) |
| Dataset `flutter-qa-v1` | 45 вопросов: 15 dev + 30 test, 5 типов × ru/en, 34 документа | `dataset-check` на реальном корпусе: 80 цитат, 50 gold-секций, 30 «отсутствующих» терминов — OK; **все 45 — draft** |
| Метрики, judge, runner | Hit/Recall/Precision/MRR@K (секции и документы), refusal accuracy, citation precision, must_include, judge; resume, `--final` | офлайн-тесты; реальные прогоны ниже |

Тестов: 150 passed, ruff ok (на `85d06c6`).

## Индексы полного корпуса (647 ok, 19 skipped)

| Индекс | Результат | Доказательство |
|---|---|---|
| Gemini section-512 | **5815 точек**, 0 failed; 513 запросов, 4834 текста + 132 из кэша, 334 с | [ingest-full-gemini-section512.json](ingest-full-gemini-section512.json), trace `d3b5cb44ec56db0082d9f22f0873e95c` |
| Gemini, повтор | 0 загрузок, 0 embedding-вызовов, 5815 точек, 2,8 с | [ingest-full-gemini-section512-rerun.json](ingest-full-gemini-section512-rerun.json), trace `c46f3f6474aeb9f6d42fa16cdd2083a2` |
| Voyage section-512 | строится на free tier (3 RPM / 10K TPM), см. раздел «Не завершено» | — |

**Квота Gemini embeddings (реальный факт).** Free tier — 1000 текстов в день: batch считается по числу
текстов (`EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier`, quotaValue 1000, 429 на
batch из 20 при успешном одиночном запросе). Полный корпус = 5815 текстов ≈ 6 дней. Это подтвердило
риск A-7 архитектуры. 2026-11-19 пользователь подключил billing (Tier 1); после этого batch из 50 —
200 OK. Лимитер: `max_tpm` 24000 давал реальный 429 по минутной квоте на страницах с кодом
(оценка chars/4 занижает токены кода) — для free tier снижено до 15000, на Tier 1 — 200000.

**GitHub 403 (первое реальное наблюдение).** Без `GITHUB_TOKEN` лимит 60 запросов/час был исчерпан;
ingest вывел понятную ошибку и exit 4 — [github-403-unauthenticated.txt](github-403-unauthenticated.txt).
С токеном `gh auth token` — 2 запроса на ingest.

## Проверка runner на dev (не эксперимент)

Конфиг `full.yaml` (Gemini section-512, top_k 20, min_score null, без rerank, `gemini-3.5-flash-lite`,
`answer/v1.2`), git `71ab3d5` clean, dataset sha256 `04b5fe8c…`.

| Run | Результат |
|---|---|
| `20261119T210351Z-full-gemini-section512-retrieval-dev` | 15/15 без ошибок; секции: Hit@1 11/12, Hit@5 12/12, Recall@5 micro 15/18, MRR 0.958 |
| `20261119T210404Z-full-gemini-section512-full-dev` | 15/15 без ошибок; отказы: answerable 12/12, unanswerable 3/3; upstream_error 0/15; judge correctness 4.75, faithfulness 5.0 (n=12) |

Langfuse (прочитано отдельным процессом, [eval-full-dev-readback.json](eval-full-dev-readback.json)):
15/15 traces `eval.full`, все в session = run_id (`observations.get_many(session_id=…)`), 124 scores
11 видов (sec/doc hit@5, recall@5, mrr, refusal_correct, must_include, expected_code_present,
judge_correctness, judge_faithfulness).

**Осторожно с числами.** 12 answerable dev-вопросов: один вопрос = 8 п.п. Hit@1 11/12 подозрительно
высок: вопросы составлены по тексту страниц и могут быть лексически близки к ним; это вопрос к
независимой проверке dataset. Judge той же семьи (Gemini) может завышать оценки (L3).

## Другие реальные проверки

| Проверка | Результат | Trace |
|---|---|---|
| ask через Gemma (`full-gemma.yaml`), RU | answered по-русски, 2 источника `deployment/obfuscate` | `5c29c43436b570eb59b82954f3d61775` |
| ask с reranker Voyage (временный конфиг: `full.yaml` + `reranking.enabled`) | answered; кандидат с 3-го места вектора стал первым (rerank 0.913) | `ad4873c3187f3c12a74af3e57a5c70fd` |

Сохранено: [ask-full-gemma.json](ask-full-gemma.json), [ask-full-rerank.json](ask-full-rerank.json).

## Не завершено / не проверено

- Индекс Voyage полного корпуса (free tier ≈ 2–2,5 ч); после него — retrieval-прогон dev на Voyage.
- Независимая проверка эталонов: все 45 вопросов `draft`; промпт для Codex — `prompts/05b-codex-dataset-check.md`.
- Индексы `fixed`/`paragraph` на полном корпусе, `answer/v2`, режим `thinking_budget`, калибровка
  `min_score`, перебор конфигураций — этап 06.
- Точные лимиты Tier 1 Gemini (видны только в кабинете AI Studio); в конфиге осторожные 100 RPM / 200K TPM.
- Отказ Langfuse, Qdrant server, реальный сбой GitHub 5xx и удаление страницы upstream.
