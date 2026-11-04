# Независимая проверка Codex — этап 04

Дата: **2026-11-04**, Europe/Chisinau.

**Результат:** основной срез этапа 03 воспроизводится с настоящими GitHub, Gemini,
embedded Qdrant и Langfuse. Подтверждены **6 дефектов: 2 × P1, 4 × P2**.
Офлайн-тесты проходят, но не покрывают найденные сценарии восстановления после ошибок.
Перед интеграцией следует исправить P1 и повторить проверки соответствующих сценариев.

## Объект и границы проверки

- Проверяемый SHA: `a54a5c5f56a7546dcc9da0295a151471039cc5bd`.
- Исходная ветка: `stage-03-vertical-slice`.
- Отдельный worktree, detached HEAD:
  `/Users/aroslavdavydov/Documents/Codex/2026-10-23/4-github-education-benefits-2026-google/outputs/flutter-docs-rag-verify-a54a5c5`.
- Команда создания из исходного репозитория:
  `git worktree add --detach ../flutter-docs-rag-verify-a54a5c5 a54a5c5f56a7546dcc9da0295a151471039cc5bd` — exit 0.
- В начале проверки `git status --porcelain` пустой. После проверок и до написания
  отчёта дерево также чистое; `git diff --exit-code <SHA> -- .` — exit 0.
- Проверяющий: **Codex, GPT-6**. В этой сессии проверяемый код не создавался.
  Claude Code и Gemini в ходе этой проверки не запускались; субагенты не использовались.
- Применён проектный skill `.agents/skills/independent-review/SKILL.md`.
- Прочитаны AGENTS.md, задание этапа, паспорт, состояние, handoff, оба README,
  матрица требований, исходное задание лабораторной №1, архитектура и evidence этапа 03.
- Реализация, prompts, конфигурация и lockfile не изменены. Единственный новый файл
  worktree — этот отчёт. Ветки не сливались, коммиты и внешние сообщения не создавались.
  `PROJECT_STATE.md` и handoff оставлены интегратору: задание этапа и allowed_paths
  разрешают проверяющему только `docs/reviews/verification.md`.

Проверяется этап 03, а не готовность всей лабораторной. Reranker, эксперименты,
dataset и вторая embedding-модель запланированы далее; их отсутствие само по себе
не включено в findings. Обязательность требований сверялась с исходным заданием,
дополнением преподавателя и маркировкой О/П/Р/Н в `docs/requirements.md`.

## Среда и воспроизводимость

macOS 26.6.2, arm64; uv 0.13.5; Python 3.12.15. Зависимости установлены заново
в `.venv` проверочного worktree по существующему `uv.lock`.

| Артефакт | SHA-256 / идентификатор |
|---|---|
| `lab1/uv.lock` | `d57e3ffd4ac567de2ad402802242f59dba83a8996677c7a6bd7edaf411b35e7c` |
| `lab1/configs/slice.yaml` | `31b4af00617bad4fefb652ef3dc3c4c39560eff5ddc62f2f0dab1ba830d6b619` |
| `lab1/prompts/answer/v1.2.md` | `f78187d8a28ab3c83675f5bcb17a62a66fb9041086da0e22560ae16c864185c8` |
| Config / fingerprint | `slice-v1` / `e39f698c6ecd` |
| Snapshot реального корпуса | `flutter/website@5ce3d6a03a22ae4738b49aafd24423e030e0fcf9` |
| Embeddings / размерность | `gemini-embedding-001` / 768 |
| LLM / prompt | `gemini-3.5-flash-lite` / `answer/v1.2` |
| Dataset version | не применяется: ручные smoke-вопросы, evaluation dataset ещё нет |

`slice.yaml` содержит `ref: main`, поэтому snapshot отличается от evidence от 23 октября.
В отчёте фиксируется фактически разрешённый SHA, а не прежний `3eb87869...`.
Провайдер и модели не заменялись.

Для реальных CLI-запусков заполненный `.env` исходного репозитория прочитан локально
через `dotenv_values`, значения переданы процессам через environment. Секреты в
worktree не копировались и в отчёт не включались. В чистом worktree без environment
`env-check` честно показал MISSING.

Изолированные runtime-пути:

```text
UV_CACHE_DIR=/private/tmp/flutter-rag-verify-uv-cache
DATA_DIR=/private/tmp/flutter-rag-verify-a54a5c5/live-data
QDRANT_PATH=/private/tmp/flutter-rag-verify-a54a5c5/live-data/qdrant
```

Перед первым ingest каталог live-data отсутствовал: проверка не использовала исходные
raw/cache/index и не перезаписывала versioned manifests в worktree. После первых двух
ingest отдельная коллекция `verify-real-update` использовала общий проверочный embedding
cache; поэтому в проверке обновления есть ожидаемые cache hits.

## Подтверждённые дефекты

### F1 — P1: повтор загрузки include не восстанавливает содержимое индекса

**Место:** `lab1/src/flutter_rag/grabber/__init__.py:185` и
`lab1/src/flutter_rag/pipeline.py:149` (выбор to_index на строке 150).
Связанные требования: R05, R07, R10; архитектура §3.1.

**Сценарий:** страница с `{% render "docs/fragment.md" %}` загружается, но загрузка
фрагмента завершается UpstreamError после исчерпания попыток. В `doc.includes` уже
записан ожидаемый blob SHA, статус родителя остаётся `ok`. Pipeline индексирует страницу
без фрагмента и сохраняет эту версию. Следующий запуск успешно скачивает фрагмент,
но version_key родителя не меняется; переиндексация пропускается.

**Доказательство:** отдельный исполняемый harness с FakeGitHub/FakeEmbedder/FakeLLM,
настоящими grabber, preprocessing, cache и embedded Qdrant; tracing отключён.
Сетевой сбой инъецирован, это **не наблюдение реального GitHub 503**.

```json
{
  "first_failed": ["sites/docs/src/_includes/docs/fragment.md"],
  "first_missing_renders": {"ui/layout": ["docs/fragment.md"]},
  "first_has_fragment": false,
  "retry_downloaded_files": 1,
  "retry_failed": [],
  "retry_indexed_documents": [],
  "retry_chunks_upserted": 0,
  "retry_missing_renders": {},
  "retry_has_fragment": false
}
```

Проверка искала уникальный текст успешно скачанного include в payload всех точек.
Его нет; повторный ingest при этом уже сообщает об отсутствии ошибок. Потерянная часть
документа остаётся недоступной до изменения исходника либо ручной переиндексации.

**Минимальное исправление:** не считать версию родителя успешно проиндексированной,
пока обязательные найденные в tree includes не загружены. Например, помечать такого
родителя `failed`/incomplete и повторять его после успешной загрузки зависимостей.
Сохранение прежней версии при failed должно учитывать F2. Добавить регрессионный
сценарий «include failed → retry succeeds → текст появился в Qdrant».

### F2 — P1: ошибка скачивания обновления удаляет последнюю рабочую версию страницы

**Место:** `lab1/src/flutter_rag/pipeline.py:149`–151 и удаление на строке 193;
сопутствующая классификация `lab1/src/flutter_rag/grabber/manifest.py:60`–64.
Связанные требования: R07, R10, R27; R11 — наше дополнительное решение.

**Сценарий:** сначала документ успешно проиндексирован. В новом snapshot его blob SHA
изменился, но download обновления завершился ошибкой. Документ всё ещё существует
в source tree, однако из-за статуса `failed` исчезает из ok_docs. Pipeline принимает
его за удалённый и удаляет прежние векторы вместе с state.

**Доказательство:** тот же harness, fake-сбой скачивания и настоящий embedded Qdrant.

```json
{
  "points_before": 2,
  "points_after": 0,
  "removed_documents": ["ui/layout"],
  "failed": ["sites/docs/src/content/ui/layout.md"],
  "diff": {"added": 0, "modified": 0, "deleted": 1, "unchanged": 0},
  "points_after_recovery": 2
}
```

Последующая успешная загрузка восстанавливает документ. До неё transient upstream error
убирает доступный ранее контекст; при массовом сбое загрузок можно опустошить индекс.

**Минимальное исправление:** отличать `failed` от отсутствующего/намеренно исключённого
документа. Для failed сохранить прежние точки и успешный state, явно отразить устаревание
в отчёте. Удалять точки по реальному отсутствию страницы в новом tree или принятому
правилу исключения. Регрессия: ошибка обновления не меняет прежние точки, успешный
повтор заменяет их; отдельный тест реального удаления продолжает проходить.

### F3 — P2: POST /ask к ещё не созданному индексу возвращает необработанный HTTP 500

**Место:** `lab1/src/flutter_rag/api/__init__.py:61`;
`lab1/src/flutter_rag/vectorstore/__init__.py:109` (IndexNotReadyError).
Связанное требование: R27; архитектура §5 обещает управляемую ошибку недоступного индекса.

**Сценарий:** runtime создан, но ingest ещё не выполнялся. `/ready` корректно отвечает
503. `/ask` всё же выполняет retrieval; IndexNotReadyError не перехватывается ни
`ask()` (там ловится только UpstreamError), ни HTTP-обработчиком.

**Доказательство:** настоящий FastAPI через TestClient с `raise_server_exceptions=False`,
fake embeddings/LLM и пустой embedded Qdrant:

```json
{
  "ready_status": 503,
  "ready": {"status": "not_ready", "reason": "index is empty"},
  "ask_status": 500,
  "ask_body": "Internal Server Error"
}
```

Это именно запрос к приложению; реальный внешний API в этой проверке не вызывается.

**Минимальное исправление:** до retrieval проверять готовность индекса либо обработать
IndexNotReadyError и вернуть HTTP 503 с понятным JSON. Не превращать отсутствие индекса
в `insufficient_context`. Добавить проверку `/ask` до первого ingest.

### F4 — P2: пустые ключи из .env.example считаются заданными

**Место:** `lab1/src/flutter_rag/config.py:45`.
Связанное требование: fail-fast M4 из архитектуры §5 и documented setup.

**Сценарий:** пользователь скопировал `.env.example`, но оставил обязательный ключ
пустым. Проверяется только `is not None`, поэтому SecretStr("") считается присутствующим.
Равнозначная проверка без записи `.env`:

```bash
GEMINI_API_KEY='' LANGFUSE_PUBLIC_KEY='' LANGFUSE_SECRET_KEY='' \
  uv run flutter-rag env-check
GEMINI_API_KEY='' LANGFUSE_PUBLIC_KEY='' LANGFUSE_SECRET_KEY='' \
  uv run flutter-rag ingest
```

**Фактически:** env-check выводит `set` для всех трёх пустых ключей, exit 0.
ingest проходит require_secrets и заканчивается traceback от SDK:
`ValueError: No API key was provided...`, **exit 1**, вместо сообщения MissingSecretError
и документированного exit 2. Сетевые вызовы не нужны.

**Минимальное исправление:** нормализовать пустые/пробельные secret-значения в None
или проверять непустой `.get_secret_value().strip()` единообразно в secret_status и
require_secrets. Проверить поведение на незаполненном `.env.example`.

### F5 — P2: metadata ingest trace содержит SHA предыдущего корпуса

**Место:** `lab1/src/flutter_rag/pipeline.py:125`–137;
`Runtime.run_metadata()` на строках 87–94.
Связанное требование: N02, обязательная для проекта фиксация snapshot в AGENTS.md.

**Сценарий:** metadata формируется из latest manifest **до** grab нового snapshot.
При первом запуске corpus_commit отсутствует; при обновлении остаётся предыдущий SHA.
Ни root metadata, ни распространяемые атрибуты после grab не обновляются.

**Доказательство:** реальные ingest и последующее независимое чтение observations
через Langfuse API. В trace `a865be9822ac18e670e70fd24d764258`:

```text
ingest report corpus_commit = 5ce3d6a03a22ae4738b49aafd24423e030e0fcf9
root metadata corpus_commit = 602492ca8d616c0ef768dbe28d61c097e0570d9d
```

В первом чистом ingest `474a242141b2cb5b45417c74dbe0a85e` поле corpus_commit в root
metadata отсутствует. В output grab/report правильный SHA есть, поэтому происхождение
можно восстановить вручную, но фильтрация/сопоставление runs по metadata неверны.

**Минимальное исправление:** после разрешения snapshot записать фактический SHA в root
metadata и атрибуты дальнейших observations. Если нужен previous snapshot, хранить его
отдельным явно названным полем. Проверить первый ingest и смену двух SHA чтением из Langfuse.

### F6 — P2: prompt v1.2 всё ещё иногда выдаёт английский отказ на русский вопрос

**Место:** `lab1/prompts/answer/v1.2.md:6`–15;
`lab1/src/flutter_rag/pipeline.py:399`–402 без проверки языка результата.
Контракт: правила prompt v1.2 и заявленное исправление языка в handoff/architecture §9.

**Сценарий и реальное доказательство:**

```text
question: Как настроить Firebase Cloud Messaging для push-уведомлений во Flutter?
status: insufficient_context
text: The provided documentation does not contain information on how to configure
      Firebase Cloud Messaging for push notifications in Flutter.
sources: []
warnings: []
trace: 198ca0445a468cf5b190b841b9ba44f1
```

Повтор того же вопроса с теми же config/snapshot/prompt/model при temperature 0 дал
русский отказ (trace `2a1bd0a5bcd426d6c89247839f6cee3b`). Поэтому это подтверждённый
**непостоянный** дефект: 1 английский отказ в 2 целевых запусках, а не утверждение о
постоянной ошибке или оценка её статистической частоты. Семантический отказ и отсутствие
источников в обоих случаях корректны.

**Минимальное исправление:** для русского интерфейса формировать текст структурного
`insufficient_context` локально по языку вопроса; альтернативно явно передавать язык
и валидировать результат с ограниченным повтором. Новую версию prompt проверять
несколькими реальными RU-вопросами; одной инструкции в prompt уже оказалось недостаточно.

## Выполненные проверки

Команды ниже запускались из `lab1/`; runtime environment описан выше. Каждый exit code
приведён по фактическому результату. `--save` писал JSON в `/private/tmp`, не в исходный Git.

| Проверка / команда | Результат |
|---|---|
| `uv sync --cache-dir /private/tmp/flutter-rag-verify-uv-cache` | exit 0 после разрешения сети; новая venv, lockfile не изменился |
| `uv run pytest` | exit 0, **51 passed in 12.43s**; это офлайн-тесты с fakes |
| `uv run ruff check .` | exit 0, All checks passed |
| `uv run ruff format --check .` | exit 0, 40 files already formatted |
| `uv run flutter-rag env-check` в чистом worktree | exit 0; ключи MISSING; Python 3.12.15 |
| `uv run flutter-rag ingest --save <ingest-1.json>` | exit 0; 8 ok, 11 raw downloads, 144 chunks/points; 9 embedding calls, 144 texts; 0 retries; limiter wait 55.84 s; wall 67.45 s |
| Второй такой же ingest | exit 0; 8 unchanged, 0 downloads, 0 chunks upserted, 0 embedding calls; **144 points**; wall 2.08 s |
| `ask` по constraints, RU | exit 0; answered на русском, 2 источника, warnings=[] |
| `ask` о FCM вне восьми страниц | exit 0; insufficient_context, sources=[]; дефект языка F6 |
| Повтор вопроса о FCM | exit 0; insufficient_context по-русски, sources=[] |
| `GEMINI_API_KEY=invalid-review-key ... ask <новый вопрос>` | exit 4; реальный Gemini HTTP 400 → upstream_error/auth, retryable=false; отказ не маскируется как отсутствие ответа |
| Реальная смена версии hot-reload | оба ingest exit 0; added=1, затем modified=1; 15 points → 15 points, старый контент заменён по версии |
| `flutter-rag trace-show <ingest_trace> --wait 0` | exit 0; прочитаны 3 observations из Langfuse отдельным процессом |
| Чтение observations/metadata восьми traces через SDK | все 8 найдены; ask=6 observations, ingest=3, invalid-key=2; подтверждён F5 |
| `flutter-rag serve --host 127.0.0.1 --port 18763` + настоящие HTTP-запросы | /health=200, /ready=200 (144 points), /docs=200; пустой question=422; валидный POST /ask=200/answered |
| Параллельный CLI ask при работающем serve | exit 3, понятное сообщение о занятом embedded Qdrant |
| `trace-show` для ответа HTTP-сервера, отдельный процесс | exit 0; 6 observations, включая LLM GENERATION |
| Проверка всех точек и источников | 144 points, вектор 768 dims; 8 живых HTML-страниц, проверены URL/якоря всех 144 chunks, **0 битых** |
| Проверка источников конкретного RU-ответа | оба chunk_id существуют, URL совпадают с payload; фрагменты Example 2 и Example 9 содержат соответствующие ограничения размеров |
| Дополнительный fault harness | exit 0; выполнены assertions F1, F2, F3; настоящие локальные pipeline/Qdrant/ASGI, внешние провайдеры — fakes |
| Пустые обязательные ключи | env-check exit 0/set; ingest exit 1 с traceback — F4 |

В реальной проверке обновления использовались две временные YAML-копии slice.yaml,
расположенные вне репозитория. Изменены только `config_id=verify-real-update`,
`corpus.name=verify-real-update`, `corpus.pages=[tools/hot-reload]` и `corpus.ref`.
Обе версии взяты из настоящего GitHub: сначала
`602492ca8d616c0ef768dbe28d61c097e0570d9d`, затем
`5ce3d6a03a22ae4738b49aafd24423e030e0fcf9`. Последний изменивший страницу commit,
возвращённый GitHub history, — `b11d153818774d8fa5b1cb66b332c9c7e7ae9d86`.
Fingerprints временных конфигов: `6f74dbd3fd77` и `24238bba2170`.
Старый ingest: 1 raw download, 1 новый embedding text + 14 cache hits.
Новый: 0 raw downloads (blob уже скачан основным ingest), 15 cache hits,
`indexed_documents=[tools/hot-reload]`, 15 upserted. Это проверка изменения версии
документа и переиндексации с реальными snapshots, а не ручное редактирование raw.

### Доказательства доставки Langfuse

Все ссылки относятся к существующему приватному проекту пользователя; для просмотра
нужен его вход. Каждая перечисленная trace прочитана обратно из API, одного создания
ID/URL за подтверждение доставки не принималось.

| Запуск | Trace |
|---|---|
| Чистый ingest | [474a242141b2cb5b45417c74dbe0a85e](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/474a242141b2cb5b45417c74dbe0a85e) |
| Повтор ingest | [ce5ac3f3f13fba65f323b1d80675e98a](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/ce5ac3f3f13fba65f323b1d80675e98a) |
| RU-ответ | [9b71ad407669394d53c2ea0c66589154](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/9b71ad407669394d53c2ea0c66589154) |
| Отказ на английском | [198ca0445a468cf5b190b841b9ba44f1](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/198ca0445a468cf5b190b841b9ba44f1) |
| Повтор отказа на русском | [2a1bd0a5bcd426d6c89247839f6cee3b](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/2a1bd0a5bcd426d6c89247839f6cee3b) |
| Неверный ключ Gemini | [e5a4a8e68385c21d2e8d0859b5d7d514](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/e5a4a8e68385c21d2e8d0859b5d7d514) |
| Старая версия hot-reload | [0ca103139ff8371ac2b2f3d82e66c1fc](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/0ca103139ff8371ac2b2f3d82e66c1fc) |
| Обновлённая hot-reload | [a865be9822ac18e670e70fd24d764258](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/a865be9822ac18e670e70fd24d764258) |
| Настоящий POST /ask | [8c025e8de7ff1c276d284c9a96168db1](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/8c025e8de7ff1c276d284c9a96168db1) |

У CLI ask metadata подтверждены проверяемый git_sha, `git_dirty=False`, модели,
config fingerprint, prompt version/hash и актуальный corpus_commit. Исключение —
описанная в F5 metadata ingest. Trace HTTP-запроса прочитана documented trace-show;
проверка полной metadata этого девятого запуска отдельно не выполнялась.

## Непроверенные пункты и ограничения

- Реальные GitHub 403/429, Gemini 429, 5xx и timeout не провоцировались.
  Повторы/таймауты/лимиты частично покрыты существующими офлайн-тестами; F1/F2 —
  инъекция финального UpstreamError. Это не доказательство реакции живых сервисов
  на каждый вариант их ответа.
- Недоступность/неверные ключи **Langfuse** не проверялись; подтверждена успешная доставка.
- Qdrant server через QDRANT_URL и его отключение во время запроса не проверялись.
  Проверены embedded-режим и межпроцессная блокировка.
- Реальное удаление страницы из upstream не выполнялось. Офлайн-тест изменения/удаления
  выполнен в составе 51 теста. Реальная смена содержимого страницы проверена отдельно.
- Не проверялись SIGKILL/отключение питания между delete/upsert/save_state и восстановление
  после повреждения локальных файлов.
- Полный корпус (~638 страниц по документации проекта) не загружался.
- Reranker, вторая embedding-модель, другие chunking-стратегии, calibrated min_score,
  evaluation dataset, Recall/MRR/faithfulness и финальная исследовательская часть не
  реализованы на проверяемом этапе. Проверка их качества не заявляется.
- Два запуска вопроса об FCM показывают возможность смены языка при temperature 0,
  но не дают статистической оценки частоты. Полная оценка hallucination и устойчивости
  к prompt injection не выполнялась.
- GitHub Actions/PR approvals заново не запускались и не подтверждались: этот отчёт о
  локальной воспроизводимости конкретного SHA. Работа skills в других клиентах также
  не проверялась.

### Ограничения доступа и служебные ошибки проверки

Первый `uv sync` в sandbox завершился exit 2: DNS lookup files.pythonhosted.org был
запрещён средой. Повтор с разрешённой сетью завершился exit 0. Реальные внешние проверки
после этого выполнены с сетевым доступом. Это **не дефект проекта** и не оставшийся blocker.

Первый дополнительный скрипт чтения metadata ошибочно использовал отсутствующий в SDK
v5 метод `api.trace.get`. Скрипт проверки исправлен вне репозитория: metadata прочитана
через поддерживаемый `api.observations.get_many(fields=...)`. Проектный `trace-show`
не изменялся и выполнен успешно. Ошибка вспомогательного скрипта не включена в findings.

## Передача интегратору

Артефакт передачи — этот файл в отдельном worktree. Исходный checkout оставлен чистым.
Временные скрипты и локальные результаты сохранены в `/private/tmp` для разбора текущей
проверки; это не долговременное хранилище evidence и не замена включённым здесь фактам
и ссылкам на traces.

Следующий шаг: интегратор разбирает F1–F6 в отдельной задаче исправлений, в первую очередь
F1/F2, и затем повторяет только затронутые регрессии и обязательные проверки этапа.
После принятия отчёта он обновляет PROJECT_STATE/handoff. Проверяющий не переносил
изменения между ветками.

Для студента: обычный путь «скачать → найти → ответить с источником» работает.
Главные найденные проблемы относятся к восстановлению после ошибок: система может
выкинуть рабочую страницу или не заметить восстановленный фрагмент. Поэтому зелёные
unit-тесты и один успешный ответ ещё не подтверждают надёжность обновления корпуса.


## Приложение: воспроизведение F1–F3 без внешних API

При проверке выполнен `/private/tmp/flutter-rag-review-faults.py`, exit 0.
Ниже его исходник (единственная адаптация — определение worktree относительно CWD).
Можно сохранить вне репозитория и выполнить из `lab1/` командой
`uv run python /private/tmp/flutter-rag-review-faults.py`. Код приложения не подменяется;
используются предусмотренные Runtime зависимости и существующие test fakes.

```python
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

wt = Path.cwd().resolve().parent  # запускать из lab1 проверяемого worktree
sys.path.insert(0, str(wt/'lab1/tests'))
from fakes import CONTENT, INCLUDES, FakeGitHub, FakeEmbedder, FakeLLM
from test_pipeline import make_cfg, LAYOUT
from flutter_rag.config import Settings
from flutter_rag.errors import UpstreamError
from flutter_rag.observability import Tracer
from flutter_rag.pipeline import Runtime, ingest, ask
from flutter_rag.api import create_app
from fastapi.testclient import TestClient

class FailingGitHub(FakeGitHub):
    fail = None
    def fetch_raw(self, commit, path):
        if path == self.fail:
            raise UpstreamError('github', 'unavailable', 'injected exhausted retries', 503)
        return super().fetch_raw(commit, path)

def runtime(folder, gh):
    return Runtime(make_cfg(), Settings(_env_file=None, data_dir=folder, qdrant_path=folder/'q'), embedder=FakeEmbedder(), llm=FakeLLM(), tracer=Tracer(None, enabled=False), github_factory=lambda:gh)

def texts(rt):
    return '\n'.join(p.payload['text'] for p in rt.client.scroll(rt.store.collection, limit=1000)[0])

results = {}
with tempfile.TemporaryDirectory(prefix='review-page-failure-') as folder:
    path=CONTENT+'ui/layout.md'
    gh=FailingGitHub({path:LAYOUT})
    rt=runtime(Path(folder),gh)
    try:
        first=ingest(rt)
        gh.files[path]=LAYOUT.replace('Sizes go up.', 'Sizes move upward.')
        gh.commit='c2'
        gh.fail=path
        failed=ingest(rt)
        results['failed_document_update']={'points_before':first.points_total,'points_after':failed.points_total,'removed_documents':failed.removed_documents,'failed':failed.failed,'diff':failed.diff}
        assert first.points_total > 0 and failed.points_total == 0
        gh.fail=None
        repaired=ingest(rt)
        assert repaired.points_total > 0
        results['failed_document_update']['points_after_recovery']=repaired.points_total
    finally: rt.close()

with tempfile.TemporaryDirectory(prefix='review-include-failure-') as folder:
    path=CONTENT+'ui/layout.md'
    inc=INCLUDES+'docs/fragment.md'
    fragment='## Fragment\n\nUNIQUE_FRAGMENT_CONTENT: Hot reload preserves application state while updating code.\n'
    gh=FailingGitHub({path:LAYOUT+'\n{% render "docs/fragment.md" %}\n',inc:fragment})
    gh.fail=inc
    rt=runtime(Path(folder),gh)
    try:
        first=ingest(rt)
        first_has='UNIQUE_FRAGMENT_CONTENT' in texts(rt)
        gh.fail=None
        second=ingest(rt)
        second_has='UNIQUE_FRAGMENT_CONTENT' in texts(rt)
        results['include_retry_stays_stale']={'first_failed':first.failed,'first_missing_renders':first.missing_renders,'first_has_fragment':first_has,'retry_downloaded_files':second.downloaded_files,'retry_failed':second.failed,'retry_indexed_documents':second.indexed_documents,'retry_chunks_upserted':second.chunks_upserted,'retry_missing_renders':second.missing_renders,'retry_has_fragment':second_has}
        assert second.downloaded_files == 1 and not second.failed and not second_has
    finally: rt.close()

with tempfile.TemporaryDirectory(prefix='review-empty-api-') as folder:
    gh=FakeGitHub({CONTENT+'ui/layout.md':LAYOUT})
    rt=runtime(Path(folder),gh)
    with TestClient(create_app('unused', runtime=rt), raise_server_exceptions=False) as client:
        ready=client.get('/ready')
        response=client.post('/ask',json={'question':'What are constraints?'})
        results['empty_index_api']={'ready_status':ready.status_code,'ready':ready.json(),'ask_status':response.status_code,'ask_body':response.text}
        assert ready.status_code == 503 and response.status_code == 500

out=Path('/private/tmp/flutter-rag-verify-a54a5c5')
out.mkdir(exist_ok=True)
(out/'faults.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(results,ensure_ascii=False,indent=2))
```
