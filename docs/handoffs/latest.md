# Handoff этапа 07 → этап 08

```yaml
task_id: LAB1-007
sender_role: "Codex (GPT-6), проверка кода, воспроизводимости и консолидация аудита"
receiver_role: "Исполнитель этапа 08 и координатор защиты"
status: ready_for_next_step
goal: "Исправить подтверждённые замечания и подготовить воспроизводимую сдачу лабораторной №1"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-06-research"
commit_sha: "1ac7e090faf566ba508ff0ae77a99245994056f3"
worktree: "Основной checkout outputs/flutter-docs-rag. SHA фиксирует проверенный код и доказательства. Отчёт этапа 07 записан поверх него в рабочей папке."
working_tree_clean: false
untracked:
  - "docs/reviews/final-audit.md"
  - "lab1/2026-11-04-213321-projectstate-latest-handoff.txt"
  - "lab1/claude_pad_last_dialog.txt"
requirements:
  - "docs/requirements.md, прежде всего R25/R26/R34/R36/R37, P01, N02/N03"
  - "prompts/08-release-defense.md"
read_first:
  - AGENTS.md
  - docs/PROJECT_BRIEF.md
  - docs/PROJECT_STATE.md
  - docs/reviews/final-audit.md
  - lab1/experiments/report.md
  - lab1/experiments/selection.md
  - docs/DEFENSE_PLAN.md
allowed_paths:
  - "Код и целевые регрессии по финальному аудиту, README и материалы сдачи из prompts/08-release-defense.md"
do_not_edit:
  - "Принятые dev.jsonl, test.jsonl, замороженный конфиг и сохранённые артефакты этапа 06"
  - "Два существующих экспорта диалогов в lab1"
decisions:
  - "В отчёте проверенная ревизия отделена от заморозки финального конфига 1e030da."
  - "Аудит подтвердил дефект метаданных при смене снимка между коллекциями. В сохранённой финальной коллекции подтверждён один верный снимок."
  - "Замечания по языку и цитатам проверять на dev или демонстрационных вопросах. На этапе 07 финальный test использован для чтения уже сохранённых ответов."
completed:
  - "Независимый статический аудит Gemini/Antigravity завершён со статусом SUCCESS. Выводы сверены Codex."
  - "Проверены требования лабораторной, код, эксперименты, сохранённые данные и CI на 1ac7e09."
  - "Зафиксированы приоритизированные замечания, минимальные исправления и checklist сдачи."
verification:
  - command: "pytest -o addopts= -q, Ruff, экспорт и diff requirements.txt"
    result: "152 теста прошли локально и в чистом архиве; линт, формат и lockfile сверены. CI Ubuntu также прошёл."
  - command: "flutter-rag dataset-check и Qdrant scroll/retrieve на копии коллекции этапа 06"
    result: "45 verified, 82 excerpts, 51 gold-секция, 2694 точки pinned snapshot; все 39 структурированных ссылок совпали с payload."
  - command: "python experiments/analyze.py --final experiments/runs/s06-*-dev experiments/runs/s06-final-test"
    result: "Побайтовое совпадение analysis.json по 25 прогонам. 391 trace ID сопоставлен с сохранёнными экспортами Langfuse, содержащими 2131 оценку."
    artifact: "lab1/experiments/evidence/stage06/analysis.json"
  - command: "Офлайн-сценарии с FakeGitHub/FakeLLM и embedded Qdrant"
    result: "Воспроизведены неверный SHA оценки и текст с неразрешённой цитатой при answered."
  - command: "FastAPI TestClient с инъекцией исключения клиента Qdrant после подключения"
    result: "Воспроизведён HTTP 500 для /ready и /ask. Живой сервер в этом сценарии не использован."
not_verified:
  - "Новый запуск на холодном индексе через внешние API, актуальность всех публичных якорей и живые частичные сбои GitHub."
  - "Недоступность Langfuse/Qdrant server; эффект rerank на fixed и широкая калибровка judge."
experiment:
  dataset_version: "flutter-qa-v1"
  dev_sha256: "df6fb5d791a9b7889591d71d65b33a1e9f1ea49ea89dedc97e3e21f240d1100a"
  test_sha256: "680ba531b37b71ba725796a75ea541ac8092845a59de704110cf15794426f2eb"
  corpus_snapshot: "flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb"
  config_id: "s06-final"
  freeze_commit: "1e030daeb47c0b30726756e744700404027b0584"
  langfuse_run_id: "s06-final-test"
integration: "https://github.com/yr3kdvdv/flutter-docs-rag/pull/16 — открыт; CI на 1ac7e09 завершился успешно."
blockers: []
next_action: "Исправить A1: сверять provenance оценки с фактическим снимком коллекции Qdrant и добавить регрессию для двух снимков и прерывания ingest."
acceptance_criteria:
  - "Закрыты подтверждённые замечания отчёта. Затронутые проверки и сценарий чистого запуска воспроизведены."
  - "README соответствует методичке, подготовлены демонстрация, источники и трасса Langfuse."
student_explanation: "Сохранённая итоговая оценка использовала правильный индекс. При будущем обновлении корпуса код может перепутать метаданные двух коллекций. Исправление нужно до сдачи, чтобы демонстрацию можно было воспроизвести на нужном снимке."
```

[Handoff этапа 06](https://github.com/yr3kdvdv/flutter-docs-rag/blob/1ac7e090faf566ba508ff0ae77a99245994056f3/docs/handoffs/latest.md)
