# Этап 04b — исправление G1 и закрытие непроверенного EN-ответа

Дата: 2026-11-06. Исполнитель: Claude Code (Opus 5.5). Отчёт повторной проверки:
[docs/reviews/verification-fixes.md](../../reviews/verification-fixes.md) (Codex, GPT-6, SHA `e366b6e`):
F1–F6 закрыты; новый **G1 P2**; EN answered с источниками не подтверждён (Gemini 503).

Код: `b6c32e1`. Реальные запуски — на этом SHA (git_sha в metadata всех traces, прочитано из Langfuse).
Runtime изолирован (DATA_DIR во временном каталоге сессии). Snapshot:
`flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb` (`ref: main` на 2026-11-06; тот же,
что у Codex). Модели/prompt без изменений: `gemini-embedding-001@768`, `gemini-3.5-flash-lite`, `answer/v1.2`.

## G1: исправление

`question_language` больше не учитывает текст в кавычках и коде: `"…"`, `«…»`, `“…”`, `„…“`,
`` `…` ``, блоки ```` ``` ````, парные `'…'` вне слов (апостроф в `don't` не считается кавычкой).
Если вне кавычек букв нет (вопрос целиком в кавычках) — решает весь текст. Явный параметр языка
в CLI/API не вводился (минимальное исправление).

**Известное ограничение:** русское имя без кавычек внутри английского вопроса по-прежнему даёт `ru`.

Регрессии: `test_question_language` (10 случаев, в том числе пара из отчёта: EN с русским именем
и RU с длинными латинскими названиями/цитатой) и `test_english_refusal_kept_english_for_quoted_russian_name`.
На `e366b6e` падают 5 из 11 (все EN-с-кириллицей), RU-случаи проходят на обеих версиях.
Всего: **73 passed**, ruff ok.

## Реальные запуски (b6c32e1)

| Запуск | Результат | Trace |
|---|---|---|
| `ingest` (повтор на 4fee025) | exit 0; 8 unchanged, 0 embedding calls, 144 points | `2de73a48b7adbc0c3cf14de61e027a48` |
| G1: `How do I publish a Flutter app named "Привет"…` | insufficient_context, **EN** текст, sources=[] | `54e8ad8e2e7c00b335c205934199cd3b` |
| G1: `…an app called «Магазин»?` | insufficient_context, **EN** текст | `de76030f7cd380768d070097c8b37f69` |
| RU FCM (регрессия F6) | insufficient_context, RU текст | `a52e682bfcbae47803885eb059257789` |
| RU с цитатой «Constraints go down…» | answered по-русски, источники [1], [8] | `2e892c1e1e6d26e24d9918019e875ba2` |
| EN hot reload | **answered**, источники [2], [6] | `406f5edc8cd1a745e6f271d6a389d448` |
| EN JSON → Dart, попытка 1 | exit 4, upstream_error, Gemini HTTP 503 | `7e992574ac7f9c62ff5cc5bec58954c2` |
| EN JSON → Dart, попытка 2 (через 60 с) | **answered**, источники [5], [6] (`Album.fromJson`) | `75a1ae1df3709f430172a5f3652ce653` |

- [sources-check.txt](sources-check.txt): все 6 источников трёх answered-ответов существуют в Qdrant
  по `chunk_id`, URL совпадает с payload, якорь есть на живой странице docs.flutter.dev.
- [traces-from-langfuse.json](traces-from-langfuse.json): 8 traces прочитаны отдельным процессом;
  answered/отказы — 6 observations, ingest — 3, 503 — 5 (root level ERROR).
- Raw output модели: на оба G1-вопроса модель сама отказала **по-русски**, на RU FCM — **по-английски**.
  Пользователь в обоих случаях получил текст на языке вопроса. Это подтверждает, что текст отказа
  из кода нужен, и что G1 был именно в детекторе языка.
- Gemini 503 наблюдался снова (1 из 4 LLM-вызовов с ответом answered/503); приложение вернуло
  управляемый `upstream_error`. Это нагрузка провайдера, не дефект кода.

## Не проверено

- Повторная независимая проверка G1 (Codex) не проводилась.
- Как и раньше: реальные сбои GitHub (F1/F2 — инъекция), Gemini 429, недоступность Langfuse,
  Qdrant server, реальное удаление страницы upstream.
