# Контракт handoff


Каждый агент получает небольшой пакет актуальных файлов, а не всю историю разговоров. Перед новой сессией проверить, что SHA и состояние рабочей директории соответствуют пакету.

```yaml
task_id: LAB1-00X
sender_role: data-engineer
receiver_role: retrieval-engineer
status: ready_for_next_step
goal: "Одно конкретное ожидаемое изменение"
repository: "URL репозитория"
branch: "feature/issue-X-short-name"
commit_sha: "Фактический SHA"
worktree: "Путь, если применимо"
working_tree_clean: true
requirements:
  - "Ссылки на критерии задания"
read_first:
  - AGENTS.md
  - docs/PROJECT_STATE.md
  - docs/architecture.md
  - "Только необходимые файлы задачи"
allowed_paths:
  - "Разрешённые для изменения модули"
do_not_edit:
  - "Файлы параллельных задач"
decisions:
  - "Принятое решение + ADR"
completed:
  - "Реально выполненная работа"
verification:
  - command: "Фактически запущенная команда"
    result: "Результат и код выхода"
    artifact: "Файл или ссылка"
not_verified:
  - "Оставшиеся проверки"
experiment:
  dataset_version: "Если применимо"
  corpus_snapshot: "Если применимо"
  config_id: "Если применимо"
  langfuse_run_id: "Только фактический ID"
blockers: []
next_action: "Один следующий шаг"
acceptance_criteria:
  - "Объективно проверяемый результат"
student_explanation: "Что студент должен понять"
```

Не включать в пакет секреты и полные логи с чувствительными значениями. Если есть незакоммиченные изменения, перечислить их и приложить diff; не писать `working_tree_clean: true` по умолчанию.
