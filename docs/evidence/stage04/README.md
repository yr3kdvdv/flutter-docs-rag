# Этап 04 — исправления по отчёту Codex и повторные проверки

Дата: 2026-11-04. Исполнитель: Claude Code (Opus 5.5). Отчёт проверяющего:
[docs/reviews/verification.md](../../reviews/verification.md) (Codex, GPT-6, SHA `a54a5c5`).

Код исправлений: коммит `b6bc723` (`fix(lab1): address Codex verification findings F1-F6`).
Все реальные запуски ниже сделаны на этом SHA с `git_dirty=False` (подтверждено metadata в Langfuse).
Runtime изолирован: `DATA_DIR`/`QDRANT_PATH` во временном каталоге сессии, versioned manifests
репозитория не менялись. Snapshot основного среза: `flutter/website@b017c8c937343e82170ead7b4aa9e3bde4fd69f6`
(`ref: main` на 2026-11-04). Модели и prompt не менялись: `gemini-embedding-001@768`,
`gemini-3.5-flash-lite`, `answer/v1.2`.

## Что исправлено и чем подтверждено

| # | Что было | Исправление | Подтверждение | Вид проверки |
|---|---|---|---|---|
| F1 P1 | include не скачался → страница проиндексирована без фрагмента навсегда | страница с найденным в tree, но не скачанным include получает `failed`; успешный повтор её индексирует | `test_failed_include_is_indexed_after_successful_retry`, `test_failed_new_include_keeps_previous_complete_version` | офлайн, **инъекция** сбоя (fake GitHub) + настоящие grabber/Qdrant |
| F2 P1 | ошибка скачивания обновления удаляла прежние точки | `failed` ≠ удаление: прежняя версия и state сохраняются, отчёт `stale_documents`; `diff.failed` | `test_failed_update_download_keeps_previous_points`, `test_mass_download_failure_does_not_empty_the_index`; старый тест реального удаления проходит | офлайн, **инъекция** сбоя |
| F3 P2 | `POST /ask` до ingest → HTTP 500 | пустой/несозданный индекс → `IndexNotReadyError`; API → 503 `{"status":"not_ready"}`; CLI → exit 2 | [f3-ask-before-ingest.txt](f3-ask-before-ingest.txt) — настоящий uvicorn + curl; `test_api_ask_before_ingest_returns_503_json` | **реально** (HTTP), внешние API не нужны |
| F4 P2 | `KEY=` из `.env.example` считался заданным → traceback, exit 1 | пустые/пробельные секреты = не заданы | [f4-blank-keys.txt](f4-blank-keys.txt): env-check MISSING, ingest exit 2 с подсказкой | **реально** (CLI) |
| F5 P2 | metadata ingest trace содержала SHA прошлого snapshot | после grab SHA пишется в root и все последующие observations; прошлый — `previous_corpus_commit` | [f5-ingest-trace-metadata.json](f5-ingest-trace-metadata.json) — прочитано из Langfuse API | **реально**: GitHub, Gemini, Langfuse |
| F6 P2 | отказ на русский вопрос иногда по-английски | текст `insufficient_context` формирует код по языку вопроса; английский ответ на русский вопрос → warning `answer_language_mismatch` | [ask/](ask/) и [f6-ask-traces-from-langfuse.json](f6-ask-traces-from-langfuse.json) | **реально**: Gemini, Langfuse |

Регрессионные тесты — `lab1/tests/test_review_regressions.py` (12). На старом коде (`a54a5c5`)
11 из 12 падают; проходит только `test_ask_before_ingest_is_not_ready_not_insufficient_context`
(несозданная коллекция и раньше давала ошибку; HTTP 500 ловит API-тест).

## Реальные запуски (b6bc723)

| Запуск | Результат | Trace |
|---|---|---|
| `ingest` с нуля | exit 0; 8 ok, 11 downloads, 144 chunks/points, 9 embedding calls, limiter 55.8 s, 0 retries | `25cc8630b9ad968a34691a8b83ddca0d` |
| `ingest` повтор | exit 0; 0 downloads, 0 embedding calls, 144 points, 2.06 s | `013ce2046e8e1ec6065583ecc06cbff7` |
| `ingest` hot-reload @602492c (временный конфиг) | exit 0; added=1, 15 points | `049e77768ca8b499e36465adae166a01` |
| `ingest` hot-reload @5ce3d6a | exit 0; modified=1, 15 → 15 points | `64f521d134a92458f5ddabf8d6f3975d` |
| ask RU FCM ×3 (вне корпуса) | insufficient_context, текст по-русски, sources=[] | `c43dcf15…`, `0992be01…`, `9c8fd657…` |
| ask RU App Store / Google Maps (вне корпуса) | insufficient_context, по-русски | `26e7f03c…`, `d3ce3c7c…` |
| ask RU constraints | answered по-русски, источник [1], warnings=[] | `992e30c62e691e7f4f92a1f33b2ea1e0` |
| ask EN JSON → Dart | answered, источники [6, 5], код `Album.fromJson` | `963301bf89f6cce0a7867f4b9b740ecf` |
| ask с `GEMINI_API_KEY=invalid…` | exit 4, upstream_error/auth | `fea36698625597151444716199794f3f` |

F5 в Langfuse: у root `rag.ingest` и `preprocess_embed_upsert` `corpus_commit` = фактический SHA
(`b017c8c…`; затем `602492c…` → `5ce3d6a…`), `previous_corpus_commit` = прошлый (у первого запуска
отсутствует). У span `grab` поля `corpus_commit` нет: он завершается до того, как SHA известен
(propagation Langfuse не меняет завершённые observations); SHA есть в его output.

**Важное наблюдение F6.** В LLM-observation всех трёх FCM-запусков сама модель отказала
**по-английски** (см. `llm_model_output` в f6-ask-traces-from-langfuse.json); App Store / Google Maps —
по-русски. Пользователь получает русский текст только потому, что отказ теперь формирует код.
Дефект модели при prompt v1.2 не устранён, устранено его влияние на ответ. Для `answered` язык не
переписывается: добавлено только предупреждение. 5 запусков — не статистическая оценка частоты.

## Не проверено

- Реальные GitHub 5xx/403/429 и сетевые сбои: F1/F2 подтверждены только инъекцией
  `UpstreamError` в fake-клиент; живой сбой спровоцировать нельзя.
- Реальное удаление страницы во flutter/website — только офлайн-тест.
- Недоступность Langfuse, Qdrant server, Gemini 429 — как и в отчёте Codex, не проверялись.
- Повторная независимая проверка Codex исправлений не выполнялась.
