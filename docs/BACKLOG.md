# Backlog

Все задачи пока запланированы, GitHub Issues не созданы.


| Issue | Результат | Проверка завершения |
|---|---|---|
| 01. Requirements и roadmap | Матрица требований, роли, архитектура | Каждый пункт привязан к deliverable |
| 02. Среда и GitHub | Зависимости, структура, CI, шаблоны | Чистый checkout проходит базовые проверки |
| 03. Сквозной RAG + Langfuse | Маленький корпус, настоящий API, trace | Вопрос -> ответ -> источник -> trace |
| 04. Incremental grabber | Автоматический corpus snapshot | Повторный запуск, обновление, удаление, ошибка |
| 05. Chunking | Несколько стратегий и metadata | Сохраняются заголовки, код и provenance |
| 06. Embeddings и Qdrant | 2 модели, раздельные индексы | Корректные query/document embeddings и размеры |
| 07. Retrieval/reranking/filtering | Настраиваемый поиск | Top-K, rerank on/off, дедупликация и thresholds |
| 08. Generation и prompts | 2 prompt variants, 2 модели/режима | Источники, отказ, API errors, ограничение контекста |
| 09. Evaluation dataset | 45 проверенных вопросов | 15 dev, 30 final, эталоны со ссылками |
| 10. Experiments | Запуски и таблицы результатов | Raw results, configs, metrics, trace/run IDs |
| 11. Independent audit | Исправления замечаний | Повторная проверка исправленного SHA |
| 12. Release и защита | README, report, demo, evidence | Воспроизведение и пробная защита |

Часть задач выполняется параллельно после согласования схем. Нумерация не означает запрет раннего создания evaluation dataset: его нужно подготовить до настройки параметров.
