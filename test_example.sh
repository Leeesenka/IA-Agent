#!/bin/bash
# Пример тестового запроса к API

curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "У пользователя логин через Google. Как ему сменить пароль?",
    "thread_id": "test-1"
  }'

