# Демонстрация Flutter Docs RAG

## Подготовка

Запустите команды из `lab1/` проверенного checkout. Настройте API-ключи
в корневом `.env`, сохраните рабочий каталог демонстрации и укажите адрес
локального Qdrant. Если в `.env` задан серверный `QDRANT_URL`, пустое
значение в окружении выбирает встроенное хранилище для демонстрации.
[Установка и переменные](../../lab1/README.md#установка)

```sh
uv sync --locked
uv run --locked flutter-rag env-check
demo_dir=$(mktemp -d)
export DATA_DIR="$demo_dir/data"
export QDRANT_PATH="$DATA_DIR/index/qdrant"
export QDRANT_URL=""
demo_config=configs/demo.yaml
```

## Две минуты об архитектуре

1. **Корпус и индекс, 35 секунд.** GitHub grabber берёт Markdown из заданного
   коммита Flutter. Очистка убирает разметку сайта, сохраняет код и связывает
   фрагменты с заголовками. Embedding-модель превращает фрагменты в векторы.
   Qdrant хранит эти векторы и метаданные источников. Повторный ingest
   обрабатывает изменения, а идентификаторы не дают накапливаться дублям.
2. **Запрос и ответ, 45 секунд.** Вопрос кодируется той же embedding-моделью
   для выбранной коллекции. Top-K даёт ближайшие фрагменты. Порог similarity
   отсеивает слабые совпадения, затем удаляются дубли и при необходимости
   Voyage меняет порядок. LLM получает ограниченный контекст с номерами.
   Ответ проходит проверку языка и ссылок. При нехватке данных система
   возвращает отказ. Langfuse показывает этапы, токены и ошибки.
3. **Исследование, 40 секунд.** Настройки сравнивались на 15 dev-вопросах.
   Выбраны fixed 512, overlap 15%, K=10, порог 0,65, Flash-Lite и
   `answer/v1.2`. После фиксации вариант оценили один раз на 30 test.
   Получили 24/24 ответов, 6/6 верных отказов и 21/24 ответов с обеими
   оценками judge ≥4/5. Нужная секция вошла в первые пять по всем 24
   вопросам с ответом. Три ответа при этом остались неполными или неточными.
   [Отчёт экспериментов](../../lab1/experiments/report.md)

## Живой запуск

**Сбор и повтор.** Используйте один закреплённый двухстраничный конфиг.
На первом проходе покажите `corpus_commit`, число точек и вызовы embeddings.
На втором сравните `points_total`, `downloaded_files` и `chunks_upserted`.

```sh
uv run --locked flutter-rag ingest --config "$demo_config" --save "$demo_dir/ingest-1.json"
uv run --locked flutter-rag ingest --config "$demo_config" --save "$demo_dir/ingest-2.json"
```

**Ответ и отказ.** Покажите текст ответа, кликабельный источник и отказ
с пустым списком источников. В этих вопросах есть ответ в документации
по layout и отсутствует ответ об устройстве PostgreSQL в двухстраничном
корпусе.

```sh
uv run --locked flutter-rag ask --config "$demo_config" \
  "How do constraints, sizes and position flow in Flutter layout?" \
  --save "$demo_dir/answered.json"
uv run --locked flutter-rag ask --config "$demo_config" \
  "Как PostgreSQL выполняет VACUUM?" --save "$demo_dir/refused.json"
demo_trace=$(uv run --locked python -c 'import json,sys; print(json.load(open(sys.argv[1]))["trace_id"])' "$demo_dir/answered.json")
uv run --locked flutter-rag trace-show "$demo_trace"
```

В Langfuse откройте `trace_url` из сохранённого ответа. Объясните
`retrieve`, `filter`, `build_context`, `llm` и `validate`.
Демонстрационный конфиг работает без rerank.

**HTTP.** В одном терминале запустите сервер с теми же значениями
`DATA_DIR`, `QDRANT_PATH` и `QDRANT_URL`. Во втором выполните запросы. Для
embedded Qdrant остановите сервер перед следующим ingest или CLI ask.

```sh
uv run --locked flutter-rag serve --config "$demo_config"
```

```sh
curl --fail-with-body http://127.0.0.1:8000/health
curl --fail-with-body http://127.0.0.1:8000/ready
curl --fail-with-body http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Как Flutter выбирает размер дочернего виджета?"}'
```

## Показ исследования

- Откройте два прогона `section-512` на одном пуле `K=20`. Без rerank
  micro Recall@5 составил 13/18, с Voyage — 14/18. В сохранённом отдельном
  запросе Voyage перенёс третьего кандидата на первое место.
  [Сравнение](../../lab1/experiments/report.md#rerank-на-одном-пуле) ·
  [Пример запроса](../evidence/stage05/ask-full-rerank.json)
- Покажите точный SHA заморозки `1e030da` и метаданные тестового прогона.
  Холодный или демонстрационный запуск выпуска подтверждает работу кода
  на своей ревизии. Числа качества относятся к сохранённому этапу 06.
  [Выбор конфигурации](../../lab1/experiments/selection.md) ·
  [Финальные артефакты](../../lab1/experiments/runs/s06-final-test/meta.json)
- Покажите сценарий отказа внешнего сервиса. Ошибка LLM или Qdrant
  возвращает статус недоступности. Потеря Langfuse не останавливает
  генерацию, но trace нужно проверить обратным чтением. Отказ из-за
  отсутствия ответа имеет статус `insufficient_context`.

При сбое внешнего API откройте сохранённые артефакты и обозначьте,
когда был сделан каждый запуск. [Набор этапа 03](../evidence/stage03/README.md) ·
[Доказательства этапа 08](../evidence/stage08/README.md)
