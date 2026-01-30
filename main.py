import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI

load_dotenv()
client = OpenAI()

app = FastAPI(title="KB Support Agent")

KB_PATH = "kb_seed.json"
DB_PATH = "runs.db"


# ---------- storage / logging ----------
def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          thread_id TEXT,
          user_message TEXT,
          tool_name TEXT,
          tool_args TEXT,
          tool_result TEXT,
          final_answer TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def log_run(
    thread_id: str,
    user_message: str,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
    final_answer: str,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO runs (thread_id, user_message, tool_name, tool_args, tool_result, final_answer)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            user_message,
            tool_name,
            json.dumps(tool_args, ensure_ascii=False),
            json.dumps(tool_result, ensure_ascii=False),
            final_answer,
        ),
    )
    conn.commit()
    conn.close()


# ---------- "tools" implementation ----------
def load_kb() -> List[Dict[str, str]]:
    with open(KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def search_kb(query: str, limit: int = 3) -> List[Dict[str, str]]:
    # Keyword-based search (word matching + scoring) with basic RU→EN mapping (MVP).
    # Для продакшена рекомендуется заменить на semantic search с embeddings/RAG.
    kb = load_kb()
    
    # Простой словарь переводов ключевых слов (RU -> EN)
    # Это позволяет находить статьи на английском по русским запросам
    # Примечание: слова короче 3 символов фильтруются, поэтому короткие слова не добавляем
    translations = {
        'пароль': 'password',
        'сброс': 'reset',
        'платеж': 'payment',
        'оплата': 'payment',
        'не прошел': 'failed',  # Фраза целиком, а не отдельные слова
        'удаление': 'deletion',
        'аккаунт': 'account',
        'двухфакторная': 'two',
        'двухфакторная аутентификация': 'two factor authentication',
        'аутентификация': 'authentication',
        'лимит': 'limit',
        'ограничение': 'limit',
        'api': 'api',
    }
    
    # Нормализуем запрос: убираем знаки препинания, приводим к нижнему регистру
    query_normalized = re.sub(r'[^\w\s]', ' ', query.lower())
    query_words_raw = [w.strip() for w in query_normalized.split() if len(w.strip()) > 2]
    
    # Переводим слова из русского в английский
    query_words = []
    for word in query_words_raw:
        # Проверяем переводы отдельных слов
        if word in translations:
            query_words.append(translations[word])
        else:
            # Также добавляем оригинальное слово (на случай если оно уже на английском)
            query_words.append(word)
    
    # Проверяем фразы (например, "двухфакторная аутентификация")
    query_lower = query.lower()
    for phrase_ru, phrase_en in translations.items():
        if len(phrase_ru.split()) > 1 and phrase_ru in query_lower:
            # Добавляем переведенную фразу как отдельные слова
            query_words.extend(phrase_en.split())
    
    if not query_words:
        return []
    
    scored = []
    for item in kb:
        # Объединяем title и content для поиска
        text = (item["title"] + " " + item["content"]).lower()
        
        # Подсчитываем совпадения каждого слова из запроса
        score = 0
        matched_words = 0
        
        for word in query_words:
            # Ищем слово как отдельное слово (с границами слов), а не как подстроку
            word_pattern = r'\b' + re.escape(word) + r'\b'
            matches = len(re.findall(word_pattern, text))
            if matches > 0:
                score += matches * 2  # Бонус за точное совпадение слова
                matched_words += 1
            else:
                # Если точного совпадения нет, ищем как подстроку (для частичных совпадений)
                if word in text:
                    score += 1
        
        # Бонус за совпадение в title (важнее, чем в content)
        title_lower = item["title"].lower()
        for word in query_words:
            if word in title_lower:
                score += 3
        
        # Добавляем только если найдено хотя бы одно совпадение
        if score > 0:
            # Нормализуем score: учитываем процент совпавших слов
            match_ratio = matched_words / len(query_words) if query_words else 0
            final_score = score * (1 + match_ratio)  # Бонус за большее количество совпавших слов
            scored.append((final_score, item))
    
    # Сортируем по убыванию score
    scored.sort(key=lambda x: x[0], reverse=True)
    
    results = []
    for score, it in scored[:limit]:
        results.append(
            {
                "id": it["id"],
                "title": it["title"],
                "snippet": it["content"][:220] + ("..." if len(it["content"]) > 220 else ""),
                "url": it["url"],
                "score": score,  # Сохраняем score для использования в confidence
            }
        )
    return results


def create_ticket(title: str, description: str, priority: str = "P2") -> Dict[str, str]:
    # MVP: просто "фейковый" тикет id. В реальном проекте подключишь Jira/Linear/Zendesk API.
    ticket_id = f"TCK-{abs(hash(title + description)) % 100000:05d}"
    return {"ticket_id": ticket_id, "status": "created", "priority": priority}


def calculate_relevance_score(query: str, kb_item: Optional[Dict]) -> float:
    """Вычисляет relevance score для KB результата (0-1)"""
    if not kb_item:
        return 0.0
    
    # Простой расчет на основе совпадений ключевых слов
    query_words = set(re.findall(r'\b\w+\b', query.lower()))
    item_text = (kb_item.get('title', '') + ' ' + kb_item.get('snippet', '')).lower()
    item_words = set(re.findall(r'\b\w+\b', item_text))
    
    if not query_words:
        return 0.0
    
    # Процент совпавших слов
    common_words = query_words.intersection(item_words)
    match_ratio = len(common_words) / len(query_words) if query_words else 0
    
    # Бонус если title содержит ключевые слова
    title_bonus = 0.3 if any(word in kb_item.get('title', '').lower() for word in query_words) else 0
    
    score = min(match_ratio + title_bonus, 1.0)
    return score


# ---------- OpenAI tool schemas ----------
# Примечание: search_kb больше не в TOOLS, так как retrieval теперь обязательный и выполняется в backend
# Модель получает результаты KB автоматически в промпте
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": (
                "Create a support ticket ONLY when:\n"
                "1. The Knowledge Base results (provided above) contain no relevant information for the user's question, AND\n"
                "2. The user's question is clear and complete (not vague or ambiguous).\n"
                "\n"
                "IMPORTANT:\n"
                "- Knowledge Base has already been searched automatically - you have the results above\n"
                "- If KB has relevant information, use it to answer - DO NOT create a ticket\n"
                "- Only create a ticket if KB results are empty or completely irrelevant\n"
                "- If the question is unclear, provide basic steps from KB first, then ask 1-2 clarifying questions\n"
                "- For repeated payment failures, use priority P1"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "default": "P2"},
                },
                "required": ["title", "description"],
            },
        },
    },
]


def tool_dispatch(name: str, args: Dict[str, Any]) -> Any:
    if name == "search_kb":
        return search_kb(query=args["query"], limit=int(args.get("limit", 3)))
    if name == "create_ticket":
        return create_ticket(
            title=args["title"],
            description=args["description"],
            priority=args.get("priority", "P2"),
        )
    raise ValueError(f"Unknown tool: {name}")


def build_structured_response(
    final_answer: str,
    all_tool_calls: List[tuple],
    user_message: str,
    kb_results: Optional[List[Dict]] = None,
    top_score: float = 0.0
) -> Dict[str, Any]:
    """Строит структурированный ответ для API"""
    
    # Используем переданные kb_results или собираем из tool_calls
    if kb_results is None:
        kb_results = []
        for name, args, result in all_tool_calls:
            if name == "search_kb" and isinstance(result, list):
                kb_results.extend(result)
    
    # Собираем sources из результатов search_kb
    sources = []
    ticket_info = None
    actions_taken = []
    
    for name, args, result in all_tool_calls:
        actions_taken.append(name)
        
        if name == "create_ticket" and isinstance(result, dict) and "ticket_id" in result:
            ticket_info = result
    
    # Формируем sources с relevance на основе позиции и score
    for idx, item in enumerate(kb_results):
        # Определяем relevance на основе позиции и score
        if idx == 0 and top_score > 0.5:
            relevance = "high"
        elif idx == 0 or (idx == 1 and top_score > 0.3):
            relevance = "medium"
        else:
            relevance = "low"
        
        sources.append({
            "title": item.get("title", "Untitled"),
            "url": item.get("url", ""),
            "relevance": relevance
        })
    
    # Проверяем, является ли ответ уточняющим вопросом
    is_clarifying = is_clarifying_question(final_answer)
    
    # Если есть KB sources - генерируем next_steps из KB, а не парсим из текста
    # Это избегает вытаскивания случайных фраз из ответа модели
    if sources and kb_results:
        # Генерируем next_steps на основе найденной KB статьи
        next_steps = []
        kb_id = kb_results[0].get("id", "") if kb_results else ""
        
        if kb_id == "pw_reset":
            next_steps = [
                "Use \"Sign in with Google\" on the login page",
                "If you still can't access the account, send the exact error message (and when it happens)",
                "If you lost access to Google, use Google Account Recovery (we can't reset Google passwords)"
            ]
        elif kb_id == "billing_failed":
            next_steps = [
                "Check payment gateway status page",
                "Verify invoice ID and last 4 digits of payment method",
                "Try payment again after 10-15 minutes"
            ]
        elif kb_id == "two_factor_auth":
            next_steps = [
                "Open Settings → Security",
                "Choose Authenticator app or SMS",
                "Save backup codes in a secure place"
            ]
        elif kb_id == "api_rate_limit":
            next_steps = [
                "Check your API usage in dashboard",
                "Wait 1 hour for rate limit reset",
                "Consider upgrading to Pro tier if needed"
            ]
        elif kb_id == "account_deletion":
            next_steps = [
                "Go to Settings → Account → Delete Account",
                "Confirm deletion request",
                "Note: data deleted within 30 days"
            ]
        else:
            # Fallback для других статей
            next_steps = [
                "Follow the steps provided above",
                "Check the knowledge base article for details"
            ]
        
        # Добавляем уточняющий вопрос в конец, если есть
        if is_clarifying:
            if kb_id == "pw_reset":
                next_steps.append("Are you trying to log in, or did you lose access to Google account?")
            elif kb_id == "billing_failed":
                next_steps.append("Provide invoice ID and last 4 digits of payment method")
            elif kb_id == "two_factor_auth":
                next_steps.append("Reply with your preferred 2FA method (app or SMS)")
            else:
                next_steps.append("Answer the clarifying question above")
    else:
        # Если KB не найдена - пытаемся извлечь из текста или генерируем общие
        next_steps = extract_next_steps(final_answer)
        
        # Если не нашли next_steps в ответе, генерируем на основе контекста
        if not next_steps:
            if ticket_info:
                next_steps = [
                    f"Wait for response on ticket {ticket_info.get('ticket_id')}",
                    "Check your email for updates",
                    "Contact support if urgent"
                ]
            elif is_clarifying:
                # Если нет KB, но есть уточняющий вопрос
                next_steps = [
                    "Answer the clarifying questions above",
                    "Provide more details about your issue",
                    "We'll help you once we have more information"
                ]
            else:
                next_steps = [
                    "Try rephrasing your question",
                    "Check if your issue matches common problems",
                    "Create a support ticket for assistance"
                ]
    
    # Определяем confidence на основе retrieval score
    confidence = determine_confidence_from_score(top_score, sources, all_tool_calls, final_answer)
    
    # Формируем краткий answer (убираем sources и next_steps если они есть в тексте)
    clean_answer = clean_answer_text(final_answer)
    
    # Убираем дубликаты из actions_taken с сохранением порядка
    actions_unique = []
    for a in actions_taken:
        if a not in actions_unique:
            actions_unique.append(a)
    
    # Формируем структурированный ответ
    response = {
        "answer": clean_answer,
        "sources": sources[:2],  # Максимум 2 источника (уже отфильтрованы по релевантности)
        "next_steps": next_steps[:4],  # Максимум 4 шага
        "actions_taken": actions_unique,  # Уникальные actions с сохранением порядка
        "confidence": confidence,
    }
    
    # Добавляем ticket если был создан
    if ticket_info:
        response["ticket"] = {
            "ticket_id": ticket_info.get("ticket_id"),
            "priority": ticket_info.get("priority", "P2"),
            "status": ticket_info.get("status", "created")
        }
    
    return response


def extract_next_steps(text: str) -> List[str]:
    """Извлекает next steps из текста ответа"""
    next_steps = []
    
    # Если это уточняющий вопрос, не извлекаем next_steps из текста
    if is_clarifying_question(text):
        return []
    
    # Ищем секцию "Next steps:" с bullet list форматом
    patterns = [
        r"(?:5\.\s*)?Next steps[:\-]?\s*\n((?:[-•]\s*[^\n]+\n?)+)",  # Bullet list после "Next steps:"
        r"Next steps[:\-]?\s*\n((?:[-•]\s*[^\n]+\n?)+)",  # Просто bullet list
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            steps_text = match.group(1).strip()
            # Разбиваем по строкам с маркерами - или •
            lines = re.split(r'\n', steps_text)
            for line in lines:
                line = line.strip()
                # Ищем строки начинающиеся с - или •
                bullet_match = re.match(r'^[-•]\s*(.+)$', line)
                if bullet_match:
                    step = bullet_match.group(1).strip()
                    # Фильтруем слишком короткие и вопросы
                    if len(step) > 10 and not step.endswith('?'):
                        next_steps.append(step)
            if next_steps:
                break
    
    # Если не нашли через паттерны, не генерируем next_steps из текста
    # (лучше пусть будет пусто, чем обрезанные куски)
    
    return next_steps[:4]


def clean_answer_text(text: str) -> str:
    """Очищает текст ответа от sources и next_steps, оставляя только основной ответ"""
    # Убираем секции Sources и Next steps если они есть
    text = re.sub(r'\(2\)\s*(?:Sources|Источники)[:\-]?.*?(?=\n\(3\)|\n\n|\Z)', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\(3\)\s*(?:Next steps|Следующие шаги)[:\-]?.*', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Sources[:\-]?.*?(?=Next steps|\Z)', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Next steps[:\-]?.*', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Убираем маркеры "(1) Answer:", "(1)", "(2)", "(3)" если они остались
    text = re.sub(r'^\(1\)\s*(?:Answer[:\-]?\s*)?', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\n\([123]\)\s*(?:Answer|Sources|Next steps)[:\-]?\s*', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'\n\([123]\)\s*', '\n', text)
    text = re.sub(r'^\([123]\)\s*', '', text, flags=re.MULTILINE)
    
    # Убираем лишние переносы строк
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def is_clarifying_question(text: str) -> bool:
    """Определяет, является ли ответ уточняющим вопросом"""
    # Считаем уточняющим только если вопросов много или ответ почти весь вопросами
    q_count = text.count("?")
    if q_count >= 2:
        return True
    
    # Если один вопрос, но он занимает большую часть ответа
    if q_count == 1:
        # Проверяем, что вопрос не в конце короткого ответа после предоставления информации
        text_lower = text.lower()
        clarifying_patterns = [
            r"to help (?:you|better|more|precisely)",
            r"could you (?:please )?(?:clarify|specify|tell me|provide)",
            r"which (?:one|method|way|option)",
            r"what (?:error|message|method|happened|did you)",
            r"are you (?:trying|using|getting)",
            r"do you (?:have|see|use|get)",
            r"please (?:clarify|specify|provide|tell)",
            r"чтобы помочь",
            r"уточните",
            r"какой|какая|какое",
        ]
        
        # Если есть паттерны уточняющих вопросов И ответ короткий (< 50 слов)
        # то это уточняющий вопрос
        for pattern in clarifying_patterns:
            if re.search(pattern, text_lower):
                if len(text.split()) < 50:
                    return True
        
        # Если ответ очень короткий и состоит в основном из вопроса
        if len(text.split()) < 20:
            return True
    
    return False


def determine_confidence_from_score(
    top_score: float,
    sources: List[Dict],
    all_tool_calls: List[tuple],
    answer: str
) -> str:
    """Определяет confidence на основе retrieval score"""
    
    # Если есть источники из KB и score нормальный — это НЕ Low, даже если есть 1 вопрос в конце
    if sources and top_score >= 0.3:
        if top_score > 0.6:
            return "High"
        return "Medium"
    
    # Дальше — только если источников нет, тогда уточнения = Low
    if is_clarifying_question(answer):
        return "Low"
    
    # Если создан тикет и нет sources - Low
    if any(name == "create_ticket" for name, _, _ in all_tool_calls) and not sources:
        return "Low"
    
    # Если есть sources, но низкий score - Medium
    if sources:
        return "Medium"
    
    # По умолчанию Low
    return "Low"


# ---------- API ----------
class ChatIn(BaseModel):
    message: str
    thread_id: Optional[str] = "demo-thread"


class CreateTicketIn(BaseModel):
    title: str
    description: str
    priority: str = "P2"
    thread_id: Optional[str] = "demo-thread"


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/")
def read_root():
    return FileResponse("static/index.html")


# Подключение статических файлов (после определения маршрутов)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/history")
def get_history(thread_id: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Получить историю диалогов"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    if thread_id:
        query = """
            SELECT id, thread_id, user_message, tool_name, tool_args, tool_result, final_answer
            FROM runs 
            WHERE thread_id = ? 
            ORDER BY id DESC 
            LIMIT ?
        """
        rows = cur.execute(query, (thread_id, limit)).fetchall()
    else:
        query = """
            SELECT id, thread_id, user_message, tool_name, tool_args, tool_result, final_answer
            FROM runs 
            ORDER BY id DESC 
            LIMIT ?
        """
        rows = cur.execute(query, (limit,)).fetchall()
    
    history = []
    for row in rows:
        history.append({
            "id": row["id"],
            "thread_id": row["thread_id"],
            "user_message": row["user_message"],
            "tool_name": row["tool_name"],
            "tool_args": json.loads(row["tool_args"]) if row["tool_args"] else {},
            "tool_result": json.loads(row["tool_result"]) if row["tool_result"] else {},
            "final_answer": row["final_answer"],
        })
    
    conn.close()
    return {"history": history}


@app.get("/threads")
def get_threads() -> Dict[str, Any]:
    """Получить список всех thread ID"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    rows = cur.execute("""
        SELECT thread_id, COUNT(*) as count, MAX(id) as last_id
        FROM runs 
        GROUP BY thread_id 
        ORDER BY last_id DESC
    """).fetchall()
    
    threads = [{"thread_id": row[0], "count": row[1]} for row in rows]
    conn.close()
    return {"threads": threads}


@app.post("/create-ticket")
def create_ticket_endpoint(payload: CreateTicketIn) -> Dict[str, Any]:
    """Создать тикет через API"""
    try:
        ticket_info = create_ticket(
            title=payload.title,
            description=payload.description,
            priority=payload.priority
        )
        
        # Логируем создание тикета
        log_run(
            thread_id=payload.thread_id or "demo-thread",
            user_message=payload.description,
            tool_name="create_ticket",
            tool_args={"title": payload.title, "description": payload.description, "priority": payload.priority},
            tool_result=ticket_info,
            final_answer=f"Ticket {ticket_info['ticket_id']} created"
        )
        
        return {
            "ticket_id": ticket_info.get("ticket_id"),
            "priority": ticket_info.get("priority", "P2"),
            "status": ticket_info.get("status", "created")
        }
    except Exception as e:
        return {"error": str(e), "ticket_id": None}


@app.post("/chat")
def chat(payload: ChatIn) -> Dict[str, Any]:
    user_msg = payload.message
    thread_id = payload.thread_id or "demo-thread"

    # ВАЖНО: Retrieval теперь обязательный - всегда сначала ищем в KB
    kb_results = search_kb(user_msg, limit=5)
    
    # Фильтруем KB результаты по порогу релевантности
    # Показываем только релевантные источники (score >= 0.25) и максимум 2 источника
    KB_SCORE_THRESHOLD_RAW = 2.5  # Порог в raw score (примерно соответствует 0.25 в нормализованном)
    kb_results_filtered = [x for x in kb_results if x.get("score", 0) >= KB_SCORE_THRESHOLD_RAW]
    kb_results = kb_results_filtered[:2]  # Показываем максимум 2 источника
    
    # Определяем top score для confidence из результатов search_kb
    # Используем score, который уже учитывает переводы RU→EN и правильную логику подсчета
    top_score = 0.0
    if kb_results:
        # Берем score из первого (лучшего) результата
        top_score_raw = kb_results[0].get("score", 0.0)
        # Нормализуем score (примерно: score обычно от 0 до ~20-30, нормализуем к 0-1)
        # Можно настроить коэффициент нормализации в зависимости от реальных значений score
        top_score = min(top_score_raw / 10.0, 1.0)
    
    # КОНТРОЛЬ TICKET CREATION: определяем, может ли модель создавать тикеты
    # Если KB найдена и score нормальный → отключаем tools (модель не может создать тикет)
    # Если KB не найдена или низкий score → включаем tools (модель может вызвать create_ticket)
    KB_SCORE_THRESHOLD = 0.2  # Порог релевантности (можно настроить)
    can_create_ticket = not kb_results or top_score < KB_SCORE_THRESHOLD
    
    # Проверяем на повторяющиеся проблемы для автоматической эскалации
    escalation_keywords = ["still", "again", "second time", "repeated", "still failing", "still not working"]
    is_repeated_issue = any(keyword in user_msg.lower() for keyword in escalation_keywords)

    # Формируем промпт с результатами KB
    kb_context = ""
    if kb_results:
        kb_context = "\n\nKnowledge Base Results:\n"
        for idx, item in enumerate(kb_results[:3]):  # Показываем топ-3
            kb_context += f"{idx + 1}. [{item['title']}]\n"
            kb_context += f"   {item['snippet']}\n"
            kb_context += f"   URL: {item['url']}\n\n"
        
        # Если это повторяющаяся проблема с оплатой, добавляем информацию об эскалации
        if is_repeated_issue and any("payment" in item.get("id", "") or "billing" in item.get("id", "") for item in kb_results):
            kb_context += "\n⚠️ REPEATED ISSUE DETECTED: User mentioned 'still', 'again', or 'repeated'. "
            kb_context += "According to KB, repeated payment failures should be escalated to P1 priority ticket.\n"
    else:
        kb_context = "\n\nKnowledge Base Results: No relevant articles found.\n"

    # Обновленный system prompt с ограничением домена
    ticket_control_note = (
        "⚠️ TICKET CREATION CONTROL: " +
        ("You CAN create tickets via create_ticket tool (KB not found or low relevance)." if can_create_ticket 
         else "You CANNOT create tickets - KB has relevant information, use it to answer the user.")
    )
    
    system_content = (
        "You are a product support assistant. You ONLY answer questions about:\n"
        "- Password reset\n"
        "- Payment failures\n"
        "- API rate limits\n"
        "- Account deletion\n"
        "- Two-factor authentication\n"
        "\n"
        "If the question is NOT about these topics, politely say: 'I can only help with product support topics "
        "(password reset, payment issues, rate limits, account deletion, 2FA). "
        "For other questions, I'm not the right assistant.'\n"
        "\n"
        "Your response structure:\n"
        "1. Summary (1 sentence)\n"
        "2. Steps (3-5 actionable steps from KB as numbered list 1-5)\n"
        "3. What I need from you (1 clarifying question ONLY if truly needed after providing steps)\n"
        "4. Sources (list KB URLs)\n"
        "5. Next steps (ONLY if needed, use bullet list with '- ' prefix, one step per line, do NOT repeat Steps section)\n"
        "\n"
        "IMPORTANT FOR NEXT STEPS:\n"
        "- Use ONLY bullet list format: '- Step description'\n"
        "- One step per line\n"
        "- Do NOT use numbered lists\n"
        "- Do NOT repeat content from Steps section\n"
        "- Only include if you need to suggest additional actions beyond the main Steps\n"
        "\n"
        "IMPORTANT FOR CLARIFYING QUESTIONS:\n"
        "- Don't ask generic 'anything else?' or 'do you need assistance?' questions\n"
        "- Ask only one question that helps solve the current issue\n"
        "- Be specific: 'Are you trying to log in, or did you lose access?' not 'Do you need help?'\n"
        "\n"
        "CRITICAL RULES FOR KB-BASED RESPONSES:\n"
        "IF Knowledge Base Results contain relevant content:\n"
        "- Provide steps from KB IMMEDIATELY - do this FIRST\n"
        "- Ask at most ONE clarifying question, only if KB explicitly requires specific information\n"
        "- Do NOT ask generic questions like 'what payment method' unless KB says it matters\n"
        "- Do NOT ask multiple questions - maximum ONE question if absolutely necessary\n"
        "- If KB has all the information needed, provide it without asking questions\n"
        "\n"
        "GENERAL RULES:\n"
        "- ALWAYS provide actionable steps from KB FIRST, then ask clarifying questions if needed\n"
        "- Never ask clarifying questions before providing basic steps from KB\n"
        "- If KB has relevant info, use it immediately\n"
        f"\n{ticket_control_note}\n"
    )

    messages = [
        {
            "role": "system",
            "content": system_content,
        },
        {
            "role": "user",
            "content": f"User question: {user_msg}{kb_context}\n\n"
                      f"CRITICAL: Based on the KB results above:\n"
                      f"- If KB results are NOT empty: Provide steps from KB IMMEDIATELY. Ask at most ONE clarifying question ONLY if KB explicitly requires specific information.\n"
                      f"- If KB results are empty: You can ask clarifying questions or create a ticket.\n"
                      f"- NEVER ask multiple questions when KB has relevant content - give steps first, then maximum ONE question if truly needed."
        },
    ]

    # Определяем, какие tools передавать модели
    # Если KB найдена с хорошим score → отключаем tools (модель не может создать тикет)
    # Если KB не найдена или низкий score → включаем tools (модель может создать тикет)
    tools_for_model = TOOLS if can_create_ticket else None
    tool_choice_for_model = "auto" if can_create_ticket else None
    
    # Логируем запрос к OpenAI
    print("\n" + "="*80)
    print("📤 REQUEST TO OPENAI API")
    print("="*80)
    print(f"Model: gpt-4o-mini")
    print(f"KB Results: {len(kb_results)} found, top_score: {top_score:.2f}")
    print(f"Can create ticket: {can_create_ticket} (threshold: {KB_SCORE_THRESHOLD})")
    print(f"Messages ({len(messages)}):")
    for i, msg in enumerate(messages):
        print(f"  [{i+1}] {msg['role']}: {msg['content'][:100]}...")
    print(f"Tools: {len(tools_for_model) if tools_for_model else 0} tools available")
    print(f"Tool choice: {tool_choice_for_model or 'disabled (KB found)'}")
    print("="*80 + "\n")

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools_for_model,
            tool_choice=tool_choice_for_model,
        )
        
        # Логируем ответ от OpenAI
        print("\n" + "="*80)
        print("📥 RESPONSE FROM OPENAI API")
        print("="*80)
        print(f"Response ID: {resp.id}")
        print(f"Model: {resp.model}")
        print(f"Finish reason: {resp.choices[0].finish_reason}")
        print(f"Content: {resp.choices[0].message.content or '(empty)'}")
        print(f"Tool calls: {len(resp.choices[0].message.tool_calls or [])}")
        if resp.choices[0].message.tool_calls:
            for i, tc in enumerate(resp.choices[0].message.tool_calls):
                print(f"  Tool call {i+1}: {tc.function.name}({tc.function.arguments[:100]}...)")
        print("="*80 + "\n")

        # Теперь KB результаты уже получены, модель может вызвать только create_ticket
        # (search_kb уже выполнен в backend)
        message = resp.choices[0].message
        tool_calls = message.tool_calls or []

        final_answer = message.content or ""
        all_tool_calls = []
        max_iterations = 3  # Уменьшаем, так как search_kb уже выполнен
        iteration = 0

        # Обрабатываем tool calls (только create_ticket доступен, search_kb больше не в TOOLS)
        while tool_calls and iteration < max_iterations:
            iteration += 1
            
            # Добавляем ответ модели с tool calls в историю
            messages.append(message)
            
            # Выполняем tool calls (только create_ticket доступен, search_kb больше не в TOOLS)
            for tc in tool_calls:
                name = tc.function.name
                # search_kb больше не должен вызываться через tool calling (retrieval обязательный в backend)
                if name == "search_kb":
                    # Это не должно происходить, но на всякий случай используем уже полученные результаты
                    print(f"⚠️  Warning: Model tried to call search_kb, but it's no longer a tool. Using pre-fetched results.")
                    all_tool_calls.append(("search_kb", {"query": user_msg}, kb_results))
                    continue
                
                args = json.loads(tc.function.arguments)
                result = tool_dispatch(name, args)
                all_tool_calls.append((name, args, result))
                
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

            # Получаем ответ после выполнения tool calls
            # На последней итерации отключаем tools, чтобы модель обязательно вернула текст
            print(f"\n🔄 ITERATION {iteration + 1}: Sending tool results back to OpenAI")
            print(f"Messages in context: {len(messages)}")
            print(f"Tool results: {len(all_tool_calls)} tools executed")
            
            if iteration >= max_iterations - 1:
                print("⚠️  Last iteration - disabling tools to force text response")
                resp2 = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    tools=None,  # Отключаем tools, чтобы получить текстовый ответ
                )
            else:
                resp2 = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    tools=tools_for_model,  # Используем те же tools, что и в первом запросе
                    tool_choice=tool_choice_for_model,
                )
            
            print(f"✅ Got response: {resp2.choices[0].message.content or '(empty)'}")
            print(f"   Tool calls: {len(resp2.choices[0].message.tool_calls or [])}")

            message = resp2.choices[0].message
            final_answer = message.content or ""
            tool_calls = message.tool_calls or []
            
            # Если получили текстовый ответ, выходим из цикла
            if final_answer:
                break

        # Если ответ все еще пустой после всех итераций, формируем ответ на основе KB результатов
        if not final_answer:
            ticket_info = None
            for name, args, result in all_tool_calls:
                if name == "create_ticket" and isinstance(result, dict) and "ticket_id" in result:
                    ticket_info = result
            
            if kb_results:
                final_answer = f"Found {len(kb_results)} relevant articles in knowledge base:\n\n"
                for item in kb_results[:3]:
                    final_answer += f"**{item.get('title', 'Untitled')}**\n"
                    final_answer += f"{item.get('snippet', '')}\n"
                    final_answer += f"📎 {item.get('url', '')}\n\n"
            elif ticket_info:
                final_answer = f"✅ Created support ticket **{ticket_info.get('ticket_id', 'N/A')}** with priority {ticket_info.get('priority', 'P2')}.\n\nOur support team will contact you soon."
            else:
                final_answer = "I couldn't find relevant information in the knowledge base. Please rephrase your question or create a support ticket."

        # Добавляем search_kb в all_tool_calls если его там нет
        if not any(name == "search_kb" for name, _, _ in all_tool_calls):
            all_tool_calls.insert(0, ("search_kb", {"query": user_msg}, kb_results))
        
        # логируем (для резюме это очень жирно)
        for name, args, result in all_tool_calls:
            log_run(thread_id, user_msg, name, args, result, final_answer)
        
        # Если tool calls не были вызваны, но ответ пустой
        if not all_tool_calls and not final_answer:
            final_answer = "Sorry, I couldn't form a response. Please try rephrasing your question."

        # Структурируем ответ с использованием KB результатов и top_score
        structured_response = build_structured_response(
            final_answer=final_answer,
            all_tool_calls=all_tool_calls,
            user_message=user_msg,
            kb_results=kb_results,
            top_score=top_score
        )

        print("\n" + "="*80)
        print("✅ FINAL RESULT")
        print("="*80)
        print(f"Answer: {structured_response['answer'][:100]}...")
        print(f"Sources: {len(structured_response['sources'])}")
        print(f"Actions: {structured_response['actions_taken']}")
        print(f"Confidence: {structured_response['confidence']}")
        print("="*80 + "\n")
        
        return structured_response
    
    except Exception as e:
        print("\n" + "="*80)
        print("❌ ERROR")
        print("="*80)
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        print("="*80 + "\n")
        
        error_msg = f"Ошибка при обработке запроса: {str(e)}"
        return {
            "answer": error_msg,
            "sources": [],
            "next_steps": ["Try again", "Check your connection", "Contact support"],
            "actions_taken": [],
            "confidence": "Low",
            "error": True
        }

