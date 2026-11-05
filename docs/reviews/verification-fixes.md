# Повторная проверка исправлений F1–F6 — этап 04b

Дата: **2026-11-06**, Europe/Chisinau.

**Результат:** исходные сценарии F1–F6 исправлены на проверенном SHA. Подтверждён
**один новый дефект P2: G1 — неверный язык отказа для английского вопроса с русским
именем/цитатой**. Полностью зелёная проверка регрессий **не заявляется**:
обычный EN-ответ с источниками не получен из-за реальных Gemini HTTP 503
(четыре запуска, три разных вопроса). RU-ответ с проверенными источниками,
идемпотентность, обновление реального документа и доставка traces подтверждены.

## Объект, независимость и границы

- Проверяемый SHA: `e366b6eea031d9e75782569a02926115bc56f148`.
- Исходная ветка: `stage-03-vertical-slice`; указанный в задании PR — #14.
  Актуальное состояние PR/CI в GitHub в этой проверке не запрашивалось.
- Предыдущий отчёт: `docs/reviews/verification.md`, проверка `a54a5c5`.
  Прочитан diff `git diff a54a5c5 e366b6e -- lab1/src lab1/tests`.
- Проверяющий: **Codex, GPT-6**, согласно идентификации текущей сессии.
  Более точный служебный идентификатор модели сессия не предоставляет.
  В этой сессии проверяемая реализация не создавалась и не исправлялась;
  написаны только внешние проверочные scripts и этот отчёт. Субагенты не запускались.
  Gemini API ниже — модель самого проверяемого приложения, не независимый ревьюер.
- Применён `.agents/skills/independent-review/SKILL.md`. Прочитаны AGENTS.md,
  PROJECT_BRIEF/PROJECT_STATE, handoff, evidence stage04, архитектура §3.1/§5/§10,
  матрица требований и относящиеся к срезу разделы README_PAD.
- Чистый отдельный worktree в detached HEAD:
  `/Users/aroslavdavydov/Documents/Codex/2026-10-23/4-github-education-benefits-2026-google/outputs/flutter-docs-rag-verify-e366b6e`.
  Команда из исходного checkout:
  `git worktree add --detach ../flutter-docs-rag-verify-e366b6e e366b6eea031d9e75782569a02926115bc56f148`
  — exit 0. Начальный `git status --porcelain=v1` пуст; `git symbolic-ref -q HEAD`
  — exit 1 без вывода, что ожидаемо для detached HEAD.
- До записи отчёта дерево также чистое; `git diff --exit-code e366b6eea031d9e75782569a02926115bc56f148 -- .`
  — exit 0. После записи единственный новый файл — этот отчёт; tracked-файлы не менялись.
  Реализация, prompts, конфиги и lockfile сохранены. Коммиты, merge и внешние сообщения
  не создавались. PROJECT_STATE и handoff оставлены интегратору: allowed_paths этапа
  разрешает проверяющему только этот отчёт.
- Исходный checkout уже имел два untracked-файла
  (`lab1/2026-11-04-213321-projectstate-latest-handoff.txt`, `prompts/04b-codex-reverify.md`).
  Их состояние сохранено; исходный checkout не объявляется чистым.

## Среда и воспроизводимость

macOS 26.6.2, arm64; uv **0.13.5** (Homebrew); Python **3.12.15**.
В новом worktree создана собственная `.venv`; `uv sync` установил 91 пакет
по существующему lockfile. Среди установленных версий: langfuse 5.0.4,
qdrant-client 1.20.0, google-genai 2.33.0, pytest 9.1.1, ruff 0.17.2.

| Артефакт | SHA-256 / идентификатор |
|---|---|
| `lab1/uv.lock` | `d57e3ffd4ac567de2ad402802242f59dba83a8996677c7a6bd7edaf411b35e7c` |
| `lab1/configs/slice.yaml` | `31b4af00617bad4fefb652ef3dc3c4c39560eff5ddc62f2f0dab1ba830d6b619` |
| `lab1/prompts/answer/v1.2.md` | `f78187d8a28ab3c83675f5bcb17a62a66fb9041086da0e22560ae16c864185c8` |
| Config / fingerprint | `slice-v1` / `e39f698c6ecd` |
| Основной реальный snapshot | `flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb` |
| Embeddings / размерность | `gemini-embedding-001` / 768 |
| LLM / prompt | `gemini-3.5-flash-lite` / `answer/v1.2`, temperature 0 |
| Dataset version | не применяется: ручные smoke-вопросы; evaluation dataset не использовался |

`corpus.ref: main` разрешился в указанный выше SHA. Snapshot из evidence исполнителя
не подставлялся вместо фактически полученного. Модели, провайдеры и prompt не менялись.

Все временные scripts, YAML-копии, результаты и runtime находятся вне репозитория.
Далее **R** обозначает `/private/tmp/flutter-rag-reverify-e366b6e-20261106`:

```text
UV_CACHE_DIR=/private/tmp/flutter-rag-reverify-e366b6e-20261106/uv-cache
DATA_DIR=/private/tmp/flutter-rag-reverify-e366b6e-20261106/live-data
QDRANT_PATH=/private/tmp/flutter-rag-reverify-e366b6e-20261106/live-data/qdrant
```

До первого реального ingest live-data отсутствовал. Для F3 использован отдельный
ранее не существовавший `R/empty-http`; fault harness использует собственные временные
каталоги. Исходные raw/cache/index не использовались.
Ключи прочитаны локально через `dotenv_values` из `.env` исходного checkout и переданы
процессам через environment. `.env` в worktree отсутствует. Значения ключей не записывались
во вспомогательные scripts; экспортированные observations очищены от значений ключей,
включая служебный `scope.attributes.public_key` Langfuse.

## Статус исправлений

Здесь `fixed` означает воспроизведённый **исходный сценарий** из предыдущего отчёта,
а не отсутствие любых других дефектов или гарантию поведения всех внешних сервисов.

| Finding | Статус | Доказательство | Вид проверки |
|---|---|---|---|
| F1, P1 | **fixed** | Исходный harness: include failed → 0 точек; повтор скачал 1 include, переиндексировал `ui/layout`, создал 3 chunks; уникальный текст найден в Qdrant. Дополнительно восстановились вложенный include и обновление include поверх прежней полной версии. | Офлайн, **инъекция** UpstreamError; настоящие grabber/preprocessing/cache/embedded Qdrant |
| F2, P1 | **fixed** | При failed-обновлении 2 → 2 точки, payload и успешный state структурно сохранены, removed=[]; успешный повтор заменяет текст. Массовый сбой 2 документов: 3 → 3 точки. Исчезновение страницы из fake tree удаляет точки, в том числе после failed-manifest. | Офлайн, **инъекция**; удаление в fake tree, не удаление в настоящем flutter/website |
| F3, P2 | **fixed** | Настоящий `flutter-rag serve`, новый пустой DATA_DIR: /health=200, /ready=503, POST /ask=503, Content-Type application/json, status=not_ready. Исходный ASGI harness также даёт 503 вместо 500. | Реальный процесс и HTTP localhost; внешняя LLM не вызывается |
| F4, P2 | **fixed** | Пустые и пробельные обязательные ключи: env-check MISSING ×3 / exit 0; ingest exit 2 с подсказкой, без traceback. | Реальный CLI, без внешних API |
| F5, P2 | **fixed** | У чистого ingest root и preprocess metadata содержат фактический SHA. При реальном переходе `602492c…` → `5ce3d6a…` corpus_commit новый, previous_corpus_commit старый. Все значения прочитаны отдельным процессом из Langfuse API. | Реальные GitHub/Gemini/Langfuse |
| F6, P2 | **fixed** для исходных RU-вопросов | 5/5 реальных RU-запусков вне корпуса: русский структурный отказ и sources=[]. В двух raw LLM outputs отказ английский; пользовательский текст всё равно русский. Общий детектор языка имеет новый дефект G1 ниже. | Реальные Gemini/Langfuse + отдельное чтение raw output; причинность G1 также проверена офлайн |

## F1/F2: восстановление и удаление

Из приложения старого отчёта извлечён **тот же** harness, без замены кода приложения.
Изменены только три assertions на ожидаемое исправленное поведение и путь вывода:

```python
assert first.points_total > 0 and failed.points_total == first.points_total
assert second.downloaded_files == 1 and not second.failed and second_has
assert ready.status_code == 503 and response.status_code == 503
```

Запуск `uv run python R/original-harness-fixed.py` — exit 0. Существенные результаты:

```json
{
  "failed_document_update": {
    "points_before": 2, "points_after": 2,
    "removed_documents": [], "points_after_recovery": 2,
    "diff": {"added": 0, "modified": 0, "deleted": 0, "unchanged": 0, "failed": 1}
  },
  "include_retry": {
    "first_has_fragment": false,
    "retry_downloaded_files": 1,
    "retry_indexed_documents": ["ui/layout"],
    "retry_chunks_upserted": 3,
    "retry_failed": [], "retry_has_fragment": true
  },
  "empty_index_api": {"ready_status": 503, "ask_status": 503}
}
```

Дополнительный `uv run python R/reverify_faults.py` — exit 0:

- Две последовательные failed-загрузки и переоткрытие Runtime не потеряли прежний state.
  После успешного повтора старого текста нет, новый присутствует; следующий ingest
  не индексирует ничего, stale_documents=[]. Документ не остаётся stale навсегда.
- Вложенный include сначала недоступен через failed родительский include: первая загрузка
  не индексирует неполную страницу; повтор скачивает оба фрагмента, 3 точки содержат
  оба маркера. Ошибка последующего обновления вложенного include сохраняет 3 прежние
  точки; успешный повтор заменяет маркер; ещё один ingest идемпотентен.
- Массовый сбой: обе страницы changed и обе загрузки failed; все 3 прежние точки и их
  payload сохранены. Затем одна страница удалена из fake tree, другая всё ещё failed:
  removed_documents=[ui/layout], остаётся 1 точка tools/reload. Успешный повтор второй
  страницы очищает stale_documents и переиндексирует её.

В последнем сценарии `diff.deleted=0`, а removed_documents содержит ui/layout:
diff сравнивает два manifest, в предыдущем эта страница уже была failed; удаление
индексированного state учитывается отдельно. Это не потеря сохранённой страницы
при сетевой ошибке и не препятствие реальному удалению из индекса.

Сбой в этих проверках **инъецирован** в fake GitHub-клиент после условного исчерпания
повторов. Реальный GitHub 503/429/403 не наблюдался и не заявляется проверенным.

## F3/F4: реальные HTTP и CLI

`uv run flutter-rag serve --host 127.0.0.1 --port 18764` запущен как отдельный
процесс с `DATA_DIR=R/empty-http`, `QDRANT_PATH=R/empty-http/qdrant`.
Настоящие HTTP-запросы дали:

```json
{
  "health_status": 200,
  "ready_status": 503,
  "ask_status": 503,
  "content_type": "application/json",
  "ask": {
    "status": "not_ready",
    "reason": "индекс flutter__slice8__gemini-embedding-001-768__section-512-o0 пуст или не создан — сначала `flutter-rag ingest`"
  }
}
```

HTTP harness — exit 0. Сервер остановлен проверяющим через SIGTERM после запросов;
код процесса 143, в логе есть штатные shutdown complete / finished server process.
Это не падение сервера. Trace этого HTTP-запроса отдельно по ID не читалась;
F3 подтверждён ответом HTTP, а не заявлением о доставке его trace.

Для F4 фактически исполнены env-check и ingest с каждым из двух наборов environment:
`GEMINI_API_KEY='' LANGFUSE_PUBLIC_KEY='' LANGFUSE_SECRET_KEY=''` и теми же ключами,
равными трём пробелам. В обоих случаях env-check показывает все три как MISSING,
exit 0; ingest печатает MissingSecretError-подсказку про .env/SETUP_ACCOUNTS и
завершается exit 2. Traceback приложения отсутствует.

## F5: реальный snapshot в Langfuse

Чтение выполнялось **отдельным от ingest процессом** через
`api.observations.get_many(trace_id=..., fields="core,basic,metadata,io,model,usage")`.
Доставка и metadata проверялись по реально возвращённым observations, не по факту
получения ID/URL из CLI.

| Запуск | Report / root corpus_commit | Root previous_corpus_commit | Observations |
|---|---|---|---|
| Чистый slice8 | `4fee0255ef9f0c85f6dd37513bf659613f57e5eb` | отсутствует, предыдущего нет | 3 |
| Повтор slice8 | `4fee0255ef9f0c85f6dd37513bf659613f57e5eb` | `4fee0255ef9f0c85f6dd37513bf659613f57e5eb` | 3 |
| Первый hot-reload | `602492ca8d616c0ef768dbe28d61c097e0570d9d` | отсутствует, предыдущего нет | 3 |
| Обновлённый hot-reload | `5ce3d6a03a22ae4738b49aafd24423e030e0fcf9` | `602492ca8d616c0ef768dbe28d61c097e0570d9d` | 3 |

У root и последующего `preprocess_embed_upsert` metadata совпадает с текущим snapshot;
config_id/fingerprint, prompt_version и git_sha при annotate не потерялись.
`git_sha=e366b6eea031d9e75782569a02926115bc56f148`, `git_dirty=False`
(в Langfuse значение сериализовано строкой `"False"`). У завершённого до annotate
span `grab` corpus_commit не требуется: правильный SHA записан в его output.
Это соответствует обновлённому контракту §10.

Обновление выполнялось настоящим grabber по двум настоящим версиям tools/hot-reload,
с временными копиями slice.yaml **в R**, общей проверочной embedding cache и отдельной
коллекцией. Изменены config_id/corpus.name на `verify-real-update-04b`, pages на
`[tools/hot-reload]` и ref на соответствующий SHA. Config fingerprints:
`ccbb2f4aceda` → `f23037b0bdcc`; SHA-256 YAML соответственно
`7f09c773f379fde86d31fc4fdce61788f7a72c80fa1859b15886e935740a97db` и
`049ddb5d8c3f651d6e96ee7c4e52c1bdabcf9b589384507fdc655d7310244690`.

Оба ingest exit 0: added=1, затем modified=1; **15 → 15** точек, по 15 upserted.
Blob страницы изменился с `a56e01ff1794b2450742ca6ee86758715f708652` на
`ffffb83334e2b20f8ca270fc2eb024505a9a7b93`. После каждого запуска Qdrant открыт
отдельно: у всех 15 payload правильный source_commit; наборы текстов старой и новой
версий различаются. Первый запуск: 1 embedding text + 14 cache hits; второй:
15 cache hits и 0 API calls. Это реальное обновление исходника, а не ручное редактирование raw.

## F6: финальный отказ и raw output

Все пять запусков ниже выполнены с настоящей Gemini и одним config/snapshot/prompt.
Для каждого прочитана LLM-observation из Langfuse: status=insufficient_context,
citations=[], а финальный ответ имеет sources=[] и один и тот же русский текст:
«В проиндексированной документации нет информации для ответа на этот вопрос.»

| Вопрос вне корпуса | Raw язык модели | Финальный язык | Trace, прочитанная из API |
|---|---|---|---|
| Firebase Cloud Messaging / push во Flutter | EN | RU | `43952276d5c821a2bc92749e01c28697` |
| Публикация в Apple App Store через App Store Connect | RU | RU | `ff06bf69576602e704e6a29c7c810ebe` |
| Google Maps / API-ключ | RU | RU | `7813ae205fc650e9e1769e2c9931a214` |
| Приём платежей Stripe | RU | RU | `3d0df9d1665f1182c63523714c5befcb` |
| Точный повтор вопроса FCM | EN | RU | `9d6ce8b98bf92698d47fc7de278c983f` |

Например, raw output первого FCM-запуска прочитан именно из LLM GENERATION:

```json
{
  "status": "insufficient_context",
  "answer": "The provided documentation does not contain information about setting up Firebase Cloud Messaging for push notifications.",
  "citations": []
}
```

**Оценка достаточности:** локальный текст — достаточное исправление исходного дефекта
пользовательского RU-отказа: статус уже структурирован, код выбирает готовую фразу
и не зависит от языка сгенерированного отказа. Prompt и поведение модели не исправлены:
в текущей небольшой выборке два отказа модели всё ещё английские. Это не оценка частоты
и не доказательство общей устойчивости генерации. Ответы status=answered код не переводит;
для RU добавляется лишь warning при отсутствии кириллицы. Кроме того, эвристика выбора
языка для локального текста требует исправления G1.

## Новый finding

### G1 — P2: русское имя внутри английского вопроса переключает отказ на русский

**Место:** `lab1/src/flutter_rag/pipeline.py:434`–440, применение к отказу на строке 453;
вторая ветка без контекста использует тот же детектор на строке 383.
Это новое поведение введено diff исправлений F6. Контракт prompt v1.2 — язык вопроса,
а не язык любого встретившегося имени. Это контракт проекта, не отдельное требование курса.

**Сценарий:** английский пользователь задаёт английский вопрос, содержащий название
приложения на русском:

```text
How do I publish a Flutter app named "Привет" to the Apple App Store?
```

`question_language` возвращает ru из-за одной русской цитаты. В реальном CLI-запуске:
exit 0, status=insufficient_context, sources=[], warnings=[], текст отказа русский.
Trace `19d8a935f41c79d9cbf4c774e8b94137` прочитана из Langfuse. В этом реальном
запуске raw output модели тоже русский; поэтому сам по себе он не доказывает,
что модель дала правильный EN-текст, а код его испортил.

**Изолированное доказательство регрессии кода:** дополнительный офлайн harness
подал этот вопрос настоящему pipeline с FakeLLM, возвращающей явно английский
insufficient_context. Pipeline заменил его на REFUSAL_TEXT[ru]. На прежней реализации
эта ветка сохраняла parsed.answer; теперь даже правильный английский отказ модели
не может дойти до пользователя. Условие срабатывает детерминированно.

```python
q = 'How do I publish a Flutter app named "Привет" to the Apple App Store?'
assert question_language(q) == "ru"  # фактическая неверная классификация
# FakeLLM: status=insufficient_context, answer="The indexed documentation has no App Store publishing instructions."
# ask(...).text: "В проиндексированной документации нет информации для ответа на этот вопрос."
```

**Минимальное исправление:** позволить UI/CLI явно передавать целевой язык ru/en
и использовать его при локализации отказа; для автоматического режима определять язык
окружающего вопроса, не позволяя цитатам/кодовым литералам единолично переключать его.
Покрыть парой регрессий: EN-вопрос с русским именем и RU-вопрос с длинными латинскими
названиями Flutter/Firebase. Реализация в рамках этой проверки не менялась.

## Команды и регрессии

Команды выполнялись из `lab1/` через внешний `R/review_exec.py`/`review_support.py`,
которые передают environment, сохраняют stdout/stderr и фактический exit code.
В таблицах R — сокращение указанного абсолютного пути, не буквальный аргумент команды.

| Команда / проверка | Фактический результат |
|---|---|
| `uv sync` с новым UV_CACHE_DIR | sandbox exit 2: DNS files.pythonhosted.org; повтор с разрешённой сетью exit 0; lockfile сохранён |
| `uv run pytest` | exit 0, **63 passed in 13.54s** |
| `uv run ruff check .` | exit 0, All checks passed |
| `uv run ruff format --check .` | exit 0, 41 files already formatted |
| `uv run python R/original-harness-fixed.py` | exit 0, исходные F1–F3 с обратными assertions |
| `uv run python R/reverify_faults.py` | exit 0, вложенные includes, повторные сбои/восстановление, массовый сбой, удаление, G1 |
| `uv run python R/annotate_cleanup.py` | exit 0: настоящий propagate_attributes SDK + stub exporter; контекст очищен после успешного ingest и injected embedding error после annotate |
| Пустые / пробельные ключи, `env-check` и `ingest` | exit 0 / 2, MISSING ×3, без traceback |
| `uv run python R/reverify_http.py` → настоящий serve + HTTP | harness exit 0, 200/503/503 JSON; сервер завершён проверяющим, exit 143 |
| `uv run flutter-rag ingest --save R/ingest-1.json` | exit 0; 8 ok, 11 downloads, 144 points, 9 embedding calls/144 texts, 0 retries, limiter wait 55.34s, duration 67.96s |
| `uv run flutter-rag ingest --save R/ingest-2.json` | exit 0; 8 unchanged, 0 downloads/upserts/API calls, **144 points**, duration 0.97s |
| `uv run flutter-rag ingest --config R/update-old.yaml --save R/update-old.json` | exit 0, added=1, 15 points |
| `uv run flutter-rag ingest --config R/update-new.yaml --save R/update-new.json` | exit 0, modified=1, 15 points; тексты и provenance заменены |
| `uv run flutter-rag ask <RU constraints> --json --save R/ask-ru.json` | сначала exit 4/503, повтор exit 0/answered, RU, один проверенный источник, warnings=[] |
| `uv run flutter-rag ask <RU вне корпуса> --json --save R/<label>.json` ×5 | все exit 0, insufficient_context/RU, sources=[]; raw output прочитан отдельно |
| `uv run flutter-rag ask <EN с русским именем> --json --save R/language-en-cyrillic.json` | exit 0, русский отказ — G1 |
| Неверный Gemini key, `ask <новый вопрос> --json --save R/invalid-key.json` | exit 4, upstream_error/auth, HTTP 400, retryable=false; 2 observations, ошибка на query embedding |
| Четыре обычных EN `ask` (вопросы ниже) | все exit 4/HTTP 503; EN answered/источники **не подтверждены** |
| `uv run flutter-rag trace-show b3fdf6eee8a8c701f5cfbf2019c04047 --wait 0` | exit 0, 3 observations прочитаны штатной CLI-командой |
| `uv run python R/read_langfuse.py <labels>` | после исправления вспомогательного сериализатора exit 0; суммарно **17 разных traces** прочитаны обратно |
| `uv run python R/audit_sources.py` | exit 0, 144 точки по 768 dims, 8 живых HTML-страниц, 0 битых якорей; RU source сверена с Qdrant; EN помечен unverified |

`annotate_cleanup.py` использует настоящие Tracer.trace/annotate, ExitStack и контекст
OpenTelemetry из установленного SDK; экспортёр заменён локальным stub, провайдеры —
fakes. Проверено отсутствие утечки corpus_commit в следующий запуск и восстановление
контекста при исключении после annotate. Это **офлайн-инъекция**, не тест отказа
живого Langfuse. В реальных ingest metadata root/дочернего span дополнительно прочитана
из API. Нового подтверждённого дефекта annotate/ExitStack в этих сценариях не найдено.

RU-вопрос: `Почему во Flutter говорят «Constraints go down. Sizes go up. Parent sets position»? Объясни правило с источниками.`
После временной ошибки получен answered по-русски, источник [1]:
`https://docs.flutter.dev/ui/layout/constraints`, chunk_id
`f16a6629-ec3b-546b-893b-ce3de31b9973`, score 0.8002. Точка существует в Qdrant,
URL совпадает, payload содержит правило и описание обмена ограничениями/размером
между родителем и детьми. Страница доступна по HTTP 200. Проверены также URL/якоря
всех 144 chunks. Грамматическая неудачность одной фразы RU-ответа не выдаётся за
отдельную регрессию исправлений: основное правило и происхождение подтверждены.

EN-проверки: вопрос про JSON → Album выполнен дважды; вопросы про layout rule и
`What does hot reload preserve in Flutter? Answer in one sentence with a citation.`
выполнены по одному разу. Все четыре запуска дошли до LLM и после встроенных повторов
получили настоящий HTTP 503 с сообщением модели о high demand. Это проверка корректного
upstream_error, но **не** успешного английского ответа. Подмены модели/провайдера не было.

## Доставка Langfuse: только прочитанные обратно ID

Каждая строка ниже подтверждена возвращёнными API observations. Ссылки требуют доступа
к приватному Langfuse-проекту пользователя. У успешных ask — 6 observations, ingest — 3,
неверного ключа — 2, исчерпанного LLM 503 — 5. У всех 17 root observations проверены
ожидаемый git_sha и git_dirty=False.

| Запуск | CLI exit | Trace |
|---|---|---|
| Чистый ingest | 0 | [b3fdf6eee8a8c701f5cfbf2019c04047](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/b3fdf6eee8a8c701f5cfbf2019c04047) |
| Повтор ingest | 0 | [9530d4fb721ec0b5d5535523d5bf3b38](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/9530d4fb721ec0b5d5535523d5bf3b38) |
| RU answered | 0 | [9a7a47d7e1e8db3e42532ad202ce3b5b](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/9a7a47d7e1e8db3e42532ad202ce3b5b) |
| FCM | 0 | [43952276d5c821a2bc92749e01c28697](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/43952276d5c821a2bc92749e01c28697) |
| App Store | 0 | [ff06bf69576602e704e6a29c7c810ebe](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/ff06bf69576602e704e6a29c7c810ebe) |
| Maps | 0 | [7813ae205fc650e9e1769e2c9931a214](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/7813ae205fc650e9e1769e2c9931a214) |
| Stripe | 0 | [3d0df9d1665f1182c63523714c5befcb](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/3d0df9d1665f1182c63523714c5befcb) |
| FCM повтор | 0 | [9d6ce8b98bf92698d47fc7de278c983f](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/9d6ce8b98bf92698d47fc7de278c983f) |
| G1: EN с «Привет» | 0 | [19d8a935f41c79d9cbf4c774e8b94137](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/19d8a935f41c79d9cbf4c774e8b94137) |
| Неверный ключ | 4 | [8432e43a00d3ff8b03c0186019ae0609](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/8432e43a00d3ff8b03c0186019ae0609) |
| Hot-reload старый | 0 | [8b100ea5b5d4b5b931c3b7af28a559e3](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/8b100ea5b5d4b5b931c3b7af28a559e3) |
| Hot-reload новый | 0 | [83ddcffb6a853ce44b482a838581f0aa](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/83ddcffb6a853ce44b482a838581f0aa) |
| RU: первоначальный 503 | 4 | [662995050af0f7abde46d6794ba55e67](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/662995050af0f7abde46d6794ba55e67) |
| EN JSON: 503 №1 | 4 | [e679a3f1a33dcc220fe35b1ba0677b2f](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/e679a3f1a33dcc220fe35b1ba0677b2f) |
| EN JSON: 503 №2 | 4 | [8d3438b6bb8e80895ff0fbe165226acd](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/8d3438b6bb8e80895ff0fbe165226acd) |
| EN layout: 503 | 4 | [d8dcbbadab4f435d2c3194949cd2ecad](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/d8dcbbadab4f435d2c3194949cd2ecad) |
| EN hot reload: 503 | 4 | [484e4c56e2d41471edcb039b00835276](https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/484e4c56e2d41471edcb039b00835276) |

## Непроверенное и ошибки среды/проверяющего

- **EN answered с проверенными источниками не подтверждён:** четыре реальных попытки
  закончились временным Gemini 503. Это ограничение текущей регрессии, а не pass и не
  доказанный дефект кода исправлений. Предыдущие evidence исполнителя не заменяют
  независимый успешный запуск.
- Настоящие GitHub 5xx/403/429, физическое удаление страницы в upstream, Gemini 429,
  недоступность/неверные ключи Langfuse и Qdrant server не проверялись. F1/F2 — инъекция.
  Наблюдались настоящие Gemini 503 и auth HTTP 400; это не переносится на другие сервисы.
- Не проверялись SIGKILL/сбой диска между delete/upsert/save_state, повреждённые локальные
  файлы, весь корпус, reranker, вторая embedding-модель, evaluation/метрики и CI/PR approvals.
- Срез включает восемь страниц; корректные отказы по пяти ручным RU-вопросам не дают
  статистической оценки refusal accuracy и не доказывают отсутствие hallucination.
- Первый uv sync в sandbox завершился exit 2 из-за DNS; повтор с сетевым доступом
  завершился exit 0. Это устранённое ограничение среды, не finding проекта.
- Два первых вызова вспомогательного reader завершились exit 1/KeyError: режим JSON
  установленного Langfuse SDK сериализует поля в camelCase вопреки ожиданию reader.
  Исправлен **только внешний script**: mode=python/by_alias=False и последующая JSON-
  сериализация. Дальнейшее чтение 17 traces успешно. Штатный trace-show также exit 0.
- Вспомогательные scripts с assertion «ожидается answered» завершались exit 1 при
  Gemini 503; сам CLI возвращал управляемый exit 4/JSON без traceback. Эти ошибки
  ожидания harness не относятся к F4 и не скрыты как успешные EN-проверки.

Полные локальные результаты, command records, raw LLM observations после очистки ключей
и scripts сохранены в R. Это временное локальное evidence; существенные факты и ссылки
включены в этот отчёт, чтобы не зависеть только от сохранности /private/tmp.

## Передача интегратору

Исходные F1–F6 можно считать закрытыми в перечисленных сценариях. Требуется отдельно
разобрать **G1 P2** и повторить обычный EN-ответ с источниками при доступной Gemini;
последний пункт сейчас не принят. Не считать этот отчёт безусловным подтверждением
«регрессий нет». После решения этих двух пунктов интегратор обновляет PROJECT_STATE/
handoff и самостоятельно решает вопрос слияния PR. Проверяющий ветки не сливал,
коммиты и сообщения в PR не создавал.

Для студента: временная ошибка скачивания теперь сохраняет рабочие данные, а повтор
восстанавливает обновление; незагруженный индекс даёт понятный 503. Русский отказ
больше не зависит от языка модели. Осталась ошибка распознавания языка смешанного
текста, а обычный английский ответ в этой сессии не удалось проверить из-за занятости API.
