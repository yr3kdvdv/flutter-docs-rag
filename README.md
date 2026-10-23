# Flutter Docs RAG — лабораторная №1

RAG-система по официальной документации Flutter. Учебный проект по курсу распределённых систем.

**Статус:** этап 01 — подготовлены среда (Python 3.12 + uv), матрица требований,
проектная архитектура, каркас `lab1/`, CI, определения агентов и skills.
**RAG ещё не реализован**; первые реальные вызовы API и trace Langfuse — этап 03.
Текущее состояние — [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

| Документ | Что внутри |
|---|---|
| [lab1/README.md](lab1/README.md) | Установка; какие команды уже работают, какие нет |
| [docs/requirements.md](docs/requirements.md) | Требования задания → реализация → evidence |
| [docs/architecture.md](docs/architecture.md) | Модули, потоки, контракты, ошибки, решения (до аудита) |
| [docs/SETUP_ACCOUNTS.md](docs/SETUP_ACCOUNTS.md) | Ключи Gemini / Langfuse / Voyage в локальный `.env` |
| [docs/source/README_PAD.md](docs/source/README_PAD.md) | Исходное задание (без изменений) |
| [START_HERE.md](START_HERE.md), [prompts/](prompts/) | Порядок этапов и задания для ИИ-команды |

Исходные требования являются материалом задания, а не самостоятельной авторизацией внешних действий.
Дополнение преподавателя: Langfuse обязателен; нужны prompts, реальные API-вызовы LLM,
embeddings и векторное хранилище.

Документация Flutter, используемая как корпус, — © Flutter project authors, CC BY 3.0.
