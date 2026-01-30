#!/usr/bin/env python3
"""
Скрипт для просмотра истории диалогов из runs.db
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "runs.db"

def view_history(limit=10, thread_id=None):
    """Просмотр истории диалогов"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    if thread_id:
        query = """
            SELECT * FROM runs 
            WHERE thread_id = ? 
            ORDER BY id DESC 
            LIMIT ?
        """
        rows = cur.execute(query, (thread_id, limit)).fetchall()
    else:
        query = """
            SELECT * FROM runs 
            ORDER BY id DESC 
            LIMIT ?
        """
        rows = cur.execute(query, (limit,)).fetchall()
    
    if not rows:
        print("История пуста.")
        return
    
    print(f"\n{'='*80}")
    print(f"История диалогов (последние {len(rows)} записей)")
    print(f"{'='*80}\n")
    
    for row in rows:
        print(f"ID: {row['id']}")
        print(f"Thread ID: {row['thread_id']}")
        print(f"Вопрос: {row['user_message']}")
        print(f"Tool: {row['tool_name']}")
        
        # Парсим аргументы и результаты
        try:
            tool_args = json.loads(row['tool_args']) if row['tool_args'] else {}
            tool_result = json.loads(row['tool_result']) if row['tool_result'] else {}
            
            print(f"Аргументы tool: {json.dumps(tool_args, ensure_ascii=False, indent=2)}")
            print(f"Результат tool: {json.dumps(tool_result, ensure_ascii=False, indent=2)}")
        except:
            print(f"Аргументы tool: {row['tool_args']}")
            print(f"Результат tool: {row['tool_result']}")
        
        print(f"\nОтвет ассистента:")
        print(f"{row['final_answer']}")
        print(f"\n{'-'*80}\n")
    
    conn.close()

def view_threads():
    """Показать все thread_id"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    rows = cur.execute("""
        SELECT thread_id, COUNT(*) as count, MAX(id) as last_id
        FROM runs 
        GROUP BY thread_id 
        ORDER BY last_id DESC
    """).fetchall()
    
    print("\nДоступные Thread ID:")
    print("-" * 50)
    for row in rows:
        print(f"  {row[0]:20s} - {row[1]} записей")
    print()
    
    conn.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--threads":
            view_threads()
        elif sys.argv[1].startswith("--thread="):
            thread_id = sys.argv[1].split("=")[1]
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            view_history(limit=limit, thread_id=thread_id)
        else:
            limit = int(sys.argv[1])
            view_history(limit=limit)
    else:
        view_threads()
        view_history(limit=10)

