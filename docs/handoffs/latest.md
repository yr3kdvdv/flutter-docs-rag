# Handoff этапа 06 → этап 07

```yaml
task_id: LAB1-006
sender_role: "Codex (GPT-6), исполнитель исследования и координатор независимых проверок"
receiver_role: "Gemini через Antigravity, аудитор этапа 07"
status: ready_for_next_step
goal: "Сверить соответствие лабораторной, воспроизводимость, качество и доказательства этапов 03–06"
repository: "https://github.com/yr3kdvdv/flutter-docs-rag"
branch: "stage-06-research"
commit_sha: "fdd529d9073e94a41e043572b786953a139025d8"
worktree: "Основной checkout outputs/flutter-docs-rag. SHA выше закрепляет код, отчёт и результаты. За ним следует обновление статуса проекта."
working_tree_clean: false
untracked:
  - "lab1/2026-11-04-213321-projectstate-latest-handoff.txt"
  - "lab1/claude_pad_last_dialog.txt"
requirements:
  - "docs/requirements.md, R15/R18/R20–R22/R28/R29/R32 и P01/N02/N03"
  - "prompts/07-gemini-final-audit.md"
read_first:
  - AGENTS.md
  - docs/PROJECT_STATE.md
  - docs/source/README_PAD.md
  - docs/requirements.md
  - docs/architecture.md
  - lab1/README.md
  - lab1/experiments/report.md
  - lab1/experiments/method-audit.md
  - lab1/experiments/selection.md
allowed_paths:
  - "docs/reviews/final-audit.md, результат отдельного этапа 07"
do_not_edit:
  - "Реализация, frozen config, dev.jsonl и test.jsonl во время аудита"
  - "Два существующих незакоммиченных экспорта диалогов"
decisions:
  - "На dev первичный показатель поиска — micro Recall@5, дальше контекст и MRR@8."
  - "Fixed 512 с overlap 15%, K=10, min_score 0,65, rerank выключен. Gemini embeddings, Flash-Lite и answer/v1.2."
  - "Финальный конфиг закреплён в 1e030da до единственного финального прогона. Test не использован для выбора."
  - "Judge той же семьи, что Flash-Lite. Claude вслепую проверил семь dev-примеров, Gemini сверил числа восьми прогонов."
completed:
  - "21 retrieval и 3 full dev-прогона. Один ретрай Gemma после HTTP 429 сохранён в raw."
  - "Один полный финальный прогон на 30 test. 24/24 answerable с ответом, 6/6 верных отказов, 21/24 с обеими оценками judge ≥4."
  - "Сохранены конфиги, raw, метрики, provenance, анализ и идентификаторы/оценки Langfuse."
verification:
  - command: "uv run flutter-rag dataset-check на pinned snapshot"
    result: "Exit 0; 45 verified, 82 excerpts, 51 gold section, 30 absent terms."
  - command: "pytest -o addopts= -q, ruff check ., ruff format --check ."
    result: "Все exit 0; 152 теста, 69 файлов уже отформатированы."
  - command: "uv export --locked --no-header --no-hashes --no-dev --no-emit-project и diff"
    result: "Exit 0, requirements.txt соответствует lockfile."
  - command: "python experiments/analyze.py --final experiments/runs/s06-*-dev experiments/runs/s06-final-test"
    result: "Exit 0, воспроизведены все 25 агрегатов из 391 строки попыток."
    artifact: "lab1/experiments/evidence/stage06/analysis.json"
  - command: "python experiments/export_langfuse.py в отдельном процессе"
    result: "Exit 0, прочитаны 391 трасса оценки и 2131 численная оценка. Отдельно подтверждены 11 трасс построения индексов и пакета финальных embeddings."
    artifact: "lab1/experiments/evidence/stage06/"
not_verified:
  - "Полный независимый аудит реализации по требованиям лабораторной (этап 07)."
  - "Перенос эффекта rerank с section-512 на fixed. Калибровка judge на более широком ручном наборе."
  - "Язык ответов и неполнота отдельных примеров отмечены в report.md и method-audit.md."
experiment:
  dataset_version: "flutter-qa-v1"
  dev_sha256: "df6fb5d791a9b7889591d71d65b33a1e9f1ea49ea89dedc97e3e21f240d1100a"
  test_sha256: "680ba531b37b71ba725796a75ea541ac8092845a59de704110cf15794426f2eb"
  corpus_snapshot: "flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb"
  config_id: "s06-final"
  freeze_commit: "1e030daeb47c0b30726756e744700404027b0584"
  langfuse_run_id: "s06-final-test"
blockers: []
next_action: "Провести независимый аудит этапа 07 по prompts/07-gemini-final-audit.md и вернуть findings с доказательствами."
acceptance_criteria:
  - "В docs/reviews/final-audit.md указан проверенный SHA и сверены критерии лабораторной."
  - "Есть приоритизированные findings, минимальные исправления, непроверенное и checklist сдачи."
student_explanation: "Сначала на dev отдельно поменяли настройки поиска и генерации. Затем зафиксировали конфиг и один раз проверили его на 30 тестовых вопросах. Три ответа оказались неполными или неточными даже при попадании в нужную секцию. Это примеры для независимого аудита."
```
