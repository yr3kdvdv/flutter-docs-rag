# Handoff — этап 02 (аудит) → этап 03 (вертикальный срез)

```yaml
task_id: LAB1-002
sender_role: "Claude Code (Opus 5.5, CLI 2.1.309) — исполнитель, разбор аудита"
receiver_role: "Claude Code — этап 03 (prompts/03-claude-vertical-slice.md)"
status: ready_for_next_step
goal: "Первый сквозной RAG на 5–10 страницах с реальным API и trace Langfuse"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-02-audit-response (PR в main; см. PROJECT_STATE / gh pr list)"
commit_sha: "см. `git log -1` ветки; аудит проверял 45cc5a6"
working_tree_clean: "проверить `git status` — handoff коммитится вместе с изменениями"
requirements:
  - "docs/requirements.md R01, R03, R06, R08, R12, R14, R16, R19, R23, R25–R27, P01–P04"
read_first:
  - AGENTS.md
  - docs/PROJECT_STATE.md
  - docs/architecture.md   # ревизия 2
  - docs/reviews/architecture.md
  - docs/reviews/architecture-response.md
  - lab1/configs/base.yaml
decisions:
  - "Аудит: B1 батчинг, B2 один процесс на embedded Qdrant, B3 исключить _*.md и noindex/sitemap:false"
  - "Dedupe только по content_hash; embed_text с префиксом страницы; код > 1024 токенов режется по строкам"
  - "Промпты — файлы lab1/prompts/ в Git; Langfuse — копия и метка"
  - "Tarball как основной способ загрузки отклонён; пул из 8 потоков"
completed:
  - "Отчёт Gemini сохранён без изменения содержания с метаданными"
  - "Каждое замечание проверено: снапшот корпуса, исходники SDK, эксперимент с Qdrant, документация"
  - "architecture.md ревизия 2, base.yaml, RESEARCH_PLAN.md, requirements.md"
verification:
  - command: "git rev-parse HEAD до изменений"
    result: "45cc5a69a247… — совпадает с SHA аудита, дерево чистое"
  - command: "curl docs.flutter.dev/add-to-app/android/_initial-route-cached-engine"
    result: "404 (B3 подтверждён); 30 обычных URL по схеме пути — все 200 (A-1 подтверждено)"
  - command: "два процесса QdrantClient(path=…) одновременно"
    result: "второй: RuntimeError Storage folder … already accessed (B2 подтверждён)"
  - command: "загрузка 761 .md с raw.githubusercontent.com, 8 потоков"
    result: "36 с, 0 ошибок (H5)"
  - command: "анализ снапшота 3eb87869bb0d"
    result: "708 .md в content, 11 _*.md, <Tabs> на 36 страницах, {% render %} ×249, 3220 блоков кода (51 > 512, 16 > 1024 ток.), 638 индексируемых страниц"
  - command: "cd lab1 && uv run pytest && uv run ruff check ."
    result: "см. описание PR / CI"
not_verified:
  - "Квоты Gemini free tier и учёт батча в квоте (документация не публикует цифры)"
  - "Повреждение embedded Qdrant при аварийном завершении"
  - "fastembed на M4"
  - "Все API-вызовы — ключей нет"
blockers:
  - "Ключи в .env не заполнены — нужны для этапа 03"
next_action: "Пользователь заполняет .env и присылает вывод env-check; затем этап 03"
acceptance_criteria:
  - "Вопрос → ответ с реальными источниками → настоящая trace Langfuse; вопрос вне корпуса → отказ"
student_explanation: "Аудит — это проверка чертежа до стройки. Мы не приняли замечания на веру: каждое проверили запуском, чтением кода библиотеки или документации. 3 блокера подтвердились, одно замечание (M1) оказалось неточным, и в двух местах мы нашли проблемы, которых аудитор не заметил ({% render %} и страницы noindex)."
```
