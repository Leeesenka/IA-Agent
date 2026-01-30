# KB Support Agent

AI-powered support agent with function/tool calling capabilities. Searches knowledge base for answers and creates tickets when needed.

## Technical Overview

- **Backend**: FastAPI, endpoint `POST /chat`, tool calling через OpenAI Chat Completions API
- **Tools**: 
  - `search_kb(query, limit)` — keyword-based search (word matching + scoring, RU→EN mapping)
  - `create_ticket(title, description, priority)` — MVP stub для создания тикетов
- **Observability**: `runs.db` (SQLite) — логирование tool calls (args/results) + финальный ответ для отладки/QA
- **KB**: `kb_seed.json` — 5 статей (Password reset, Payment failed, API rate limits, Account deletion, Two-factor authentication)

## Features

- **Knowledge Base Search**: Search internal KB articles using `search_kb` tool
- **Ticket Creation**: Automatically create support tickets via `create_ticket` tool when KB doesn't have answers
- **Run Logging**: All tool calls, inputs, and outputs are logged to SQLite for debugging and QA
- **OpenAI Function Calling**: Uses Chat Completions API with tool calling for reliable function execution

## Setup

1. **Create virtual environment**:
```bash
python -m venv .venv
source .venv/bin/activate  # mac/linux
# или
.venv\Scripts\activate  # windows
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure environment**:
```bash
# Создайте файл .env и добавьте ваш OPENAI_API_KEY:
echo "OPENAI_API_KEY=your_api_key_here" > .env
# Или отредактируйте .env вручную
```

4. **Run server**:
```bash
uvicorn main:app --reload --port 8000
```

5. **Open in browser**:
   - Web Interface: http://127.0.0.1:8000
   - API Documentation: http://127.0.0.1:8000/docs

## Usage

### Web Interface

Откройте http://127.0.0.1:8000 в браузере для использования веб-интерфейса. Интерфейс включает:
- Чат с AI-ассистентом
- Отображение истории сообщений
- Управление thread ID
- Статус запросов

### API Endpoint

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "У пользователя логин через Google. Как ему сменить пароль?",
    "thread_id": "t1"
  }'
```

### Example Response

```json
{
  "answer": "Based on the knowledge base, if a user signed up with Google OAuth, password reset is not available. They should use Google sign-in instead.\n\nSources:\n- https://kb.local/password-reset\n\nNext steps: If the user needs to change their Google account password, they should do so through their Google account settings."
}
```

## Project Structure

- `main.py` - FastAPI server with agent logic and tool implementations
- `kb_seed.json` - **База знаний** (knowledge base) — 5 статей с информацией для ответов
- `runs.db` - **Логи/трассировка** (SQLite) — логирование per tool invocation (одна запись на каждый tool call: args/results) + финальный ответ (создается автоматически)
- `.env` - Environment variables (not in git)
- `static/` - Web interface files
  - `index.html` - Main HTML page
  - `style.css` - Styles
  - `script.js` - Frontend JavaScript

## How It Works

### Откуда берутся данные

Данные для ответа берутся из базы знаний `kb_seed.json`.

**Процесс:**

1. **Retrieval (поиск)**
   - Модель GPT решает, нужно ли вызвать tool `search_kb(query)` на основе запроса пользователя
   - Приложение выполняет функцию `search_kb()` и возвращает список релевантных статей (title/snippet/url)
   - *Примечание: Keyword-based search (word matching + scoring) with basic RU→EN mapping (MVP). Для продакшена рекомендуется RAG с embeddings*

2. **Generation (формирование ответа)**
   - Модель получает найденные материалы из KB и генерирует ответ на языке пользователя
   - Ответ включает ссылки на источники из базы знаний

3. **Fallback**
   - Если релевантной информации нет, модель вызывает tool `create_ticket(...)` для создания тикета поддержки

**Где что хранится:**
- **База знаний**: `kb_seed.json` — статьи с информацией для ответов
- **Логи/трассировка**: `runs.db` (SQLite) — логирование per tool invocation (одна запись на каждый tool call: args/results) + финальный ответ для observability и отладки

### Технические детали

- **Tool Calling**: Модель GPT сама решает, когда вызывать tools через OpenAI Function Calling API
- **Поиск**: Keyword-based search (word matching + scoring) with basic RU→EN mapping (MVP). Для мультиязычности и семантического поиска рекомендуется использовать embeddings/RAG
- **Логирование**: Все вызовы tools логируются в `runs.db` (одна запись на каждый tool invocation) для отладки и анализа качества ответов

## Tools

### `search_kb(query, limit=3)`
Tool для поиска в базе знаний. Модель вызывает его через tool calling, когда нужно найти информацию. Возвращает топ совпадений с заголовками, сниппетами и URL.

**Реализация (MVP)**: Keyword-based search (word matching + scoring) с базовым RU→EN mapping. Для продакшена рекомендуется заменить на semantic search с embeddings.

### `create_ticket(title, description, priority="P2")`
Tool для создания тикета поддержки. Модель вызывает его, когда не может найти релевантную информацию в KB. Возвращает ticket ID и статус.

## Checking Logs / Tracing

Все вызовы tools логируются в SQLite базу (`runs.db`) для observability и отладки. Это не хранилище знаний, а трассировка выполнения. Логирование идет per tool invocation (одна запись на каждый tool call: args/results) + финальный ответ.

### Просмотр истории через SQLite:

```bash
# Последние 10 записей с форматированием
sqlite3 runs.db -header -column "SELECT id, thread_id, user_message, tool_name, substr(final_answer, 1, 100) as answer_preview FROM runs ORDER BY id DESC LIMIT 10;"

# История конкретного thread
sqlite3 runs.db "SELECT * FROM runs WHERE thread_id='demo-thread' ORDER BY id DESC;"
```

### Просмотр истории через Python скрипт:

```bash
# Показать все thread ID
python3 view_history.py --threads

# Последние 10 записей
python3 view_history.py 10

# История конкретного thread (последние 20 записей)
python3 view_history.py --thread=demo-thread 20
```

Скрипт `view_history.py` показывает полную информацию: вопрос, вызванный tool, аргументы, результаты и финальный ответ.

## Future Improvements

1. **RAG/Embeddings**: Заменить keyword-based search на semantic search с embeddings для мультиязычности и лучшей релевантности
2. **Translation Layer**: Расширить RU→EN mapping / заменить на полноценный переводчик или embeddings-based multilingual retrieval
3. **Cyclic Tool Loop**: Уже реализовано — поддержка нескольких раундов tool calling до получения финального ответа
4. **Evaluation Cases**: Добавить `eval_cases.json` с 10-20 тестовыми сценариями для оценки качества
5. **Tracing**: Интегрировать Agents SDK для нативной поддержки трассировки

## Resume Bullets

- Built an AI agent with function/tool calling to retrieve answers from a knowledge base and create tickets when confidence is low
- Implemented run logging (tool calls, inputs/outputs) for debugging and QA; prepared evaluation scenarios to reduce hallucinations

