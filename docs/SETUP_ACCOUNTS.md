# Настройка аккаунтов API и локального `.env`

Проверено по официальной документации 2026-10-23. Формы и лимиты в вашем аккаунте
могут отличаться — ориентируйтесь на то, что видите на экране.

> **Главное правило.** Ключи вводятся только в локальный файл `.env` на вашем Mac.
> Не вставляйте их в чаты ИИ, Issues, commits, скриншоты. `.env` уже в `.gitignore`.
> Подписки Claude Pro / Google AI Pro / ChatGPT Plus **не дают** API-ключей: API —
> отдельный доступ со своими квотами. Платный режим (billing) не включайте без решения.

## 0. Создать локальный `.env`

```bash
cd ~/Documents/Codex/2026-10-23/4-github-education-benefits-2026-google/outputs/flutter-docs-rag
cp .env.example .env
open -e .env        # откроется TextEdit; вставьте значения после "=" без кавычек и пробелов
```

Проверка (печатает только `set`/`MISSING`, не значения):

```bash
cd lab1 && uv run flutter-rag env-check
```

## 1. Gemini API — нужен к этапу 03

1. Откройте https://aistudio.google.com/apikey и войдите Google-аккаунтом.
2. «Create API key» → выберите/создайте проект Google Cloud (AI Studio предложит сам).
3. Скопируйте ключ в `.env`: `GEMINI_API_KEY=...`
4. Не задавайте одновременно `GOOGLE_API_KEY`: по документации SDK `google-genai`
   при наличии обеих переменных приоритет у `GOOGLE_API_KEY`, это запутает проверку.
5. Не включайте billing: на этапе 03 мы маленьким запросом проверим, какие модели и
   квоты доступны на бесплатном уровне.

## 2. Langfuse — обязателен, нужен к этапу 03

1. Откройте https://cloud.langfuse.com (регион EU) и зарегистрируйтесь
   (план Hobby, бесплатный). Если выберете регион US — https://us.cloud.langfuse.com.
2. Создайте Organization → Project, например `flutter-docs-rag`.
3. Project → Settings → API Keys → «Create new API keys».
4. В `.env`:
   - `LANGFUSE_PUBLIC_KEY=pk-lf-...`
   - `LANGFUSE_SECRET_KEY=sk-lf-...` (показывается один раз)
   - `LANGFUSE_BASE_URL=https://cloud.langfuse.com` (или US-адрес, если выбрали US)
5. Имена переменных взяты из документации Python SDK v5 (`LANGFUSE_BASE_URL`).

## 3. Voyage AI — нужен к этапу 05 (вторая embedding-модель и reranker)

1. Откройте https://dashboard.voyageai.com и зарегистрируйтесь.
2. Organization → API keys → «Create new secret key».
3. В `.env`: `VOYAGE_API_KEY=...`
4. По странице pricing: первые 200M токенов `voyage-4*` и `rerank-2.5*` бесплатны на аккаунт.
   Лимиты запросов без привязанной карты документация не указывает — проверим запросом.
   Карту без отдельного решения не добавляйте.

## 4. Необязательно

- `GITHUB_TOKEN` — повышает лимит GitHub API для grabber (без токена 60 запросов/час,
  grabber тратит ~2 запроса на snapshot, обычно хватает). Если понадобится:
  fine-grained token без прав (public repositories, read-only).
- `QDRANT_URL` — оставьте пустым: используется локальное хранилище в `lab1/data/index/`.

## Что сообщить ИИ после заполнения

Только результат `uv run flutter-rag env-check` (там нет значений ключей) и
выбранный регион Langfuse.
