# SYSTEM ARCHITECTURE
## AI Workspace Platform

---

# 1. Общий принцип архитектуры

Система состоит из 4 основных уровней:

1. UI слой (чат)
2. Backend оркестратор
3. AI слой (модели)
4. Хранилище данных

Архитектура проектируется так, чтобы:

- поддерживать несколько моделей AI
- сохранять контекст проектов
- управлять задачами агентов
- работать с файлами
- масштабироваться
- контролировать расходы токенов

---

# 2. Высокоуровневая схема

User Interface  
↓  
API Backend  
↓  
Orchestrator (GPT-5.4)  
↓  
Tools Layer  
↓  
Models (Claude, GPT, Gemini)  
↓  
Storage  

---

# 3. Компоненты системы

## 3.1 Frontend (UI)

Минимальный web интерфейс.

Функции:

- чат
- список проектов
- список файлов
- загрузка файлов
- просмотр статуса задач
- выбор модели
- управление задачами (approve/reject)
- просмотр логов работы AI

Frontend может быть реализован позже, на первом этапе допустим простой интерфейс.

---

## 3.2 Backend API

Основной сервер приложения.

Отвечает за:

- авторизацию пользователей
- управление проектами
- управление файлами
- учёт токенов
- запуск задач AI
- хранение истории
- индексацию файлов
- взаимодействие с OpenCode
- взаимодействие с Claude Code
- взаимодействие с speech-to-text
- взаимодействие с image generation

Рекомендуемый стек:

Python FastAPI

---

## 3.3 Orchestrator (управляющий агент)

Главный логический слой системы.

Использует GPT-5.4.

Отвечает за:

- понимание задач пользователя
- планирование действий
- выбор модели
- разбиение задач на шаги
- вызов инструментов
- контроль выполнения задач
- проверку результатов
- сохранение памяти проекта

Оркестратор НЕ пишет код напрямую.

Он ставит задачи Claude Code.

---

## 3.4 Claude Code

Claude Code работает как исполнитель.

Он может:

- читать код проекта
- изменять файлы
- создавать файлы
- запускать команды
- исправлять ошибки
- выполнять refactoring

Claude Code работает через CLI на сервере.

Оркестратор передаёт ему задачи.

Claude возвращает:

- diff
- созданные файлы
- отчёт
- ошибки

---

## 3.5 OpenCode layer

OpenCode используется как единый интерфейс к моделям.

Поддерживаемые модели:

Claude  
GPT  
Gemini  

OpenCode позволяет:

использовать разные модели через единый API.

---

## 3.6 Memory system

Память разделена на уровни.

### short term context

последние сообщения чата.

используются напрямую в prompt.

---

### project memory

содержит:

факты проекта  
описание проекта  
важные решения  
настройки  

---

### summaries

сжатые версии старых сообщений.

используются при compaction контекста.

---

### embeddings index

индекс файлов проекта.

используется для поиска информации.

---

# 4. Хранилище данных

## 4.1 Database

PostgreSQL

хранит:

users  
projects  
chats  
messages  
files  
file_versions  
memories  
summaries  
usage  
tasks  

---

## 4.2 File storage

локальное хранилище или S3 совместимое.

структура:

/storage/projects/project_id/files/

---

## 4.3 Vector storage

хранит embeddings.

используется для поиска по файлам.

может быть:

pgvector  
qdrant  
weaviate  

для MVP можно pgvector.

---

# 5. File processing pipeline

после загрузки файла:

1. файл сохраняется
2. извлекается текст
3. файл разбивается на части
4. создаются embeddings
5. embeddings сохраняются
6. создаётся индекс

---

# 6. AI tools

система предоставляет AI инструменты:

read_file

edit_file

create_file

search_project

search_web

generate_image

speech_to_text

run_claude_task

list_files

save_memory

load_memory

---

# 7. Web search tool

отдельный инструмент.

используется когда:

информации нет в проекте.

агент может:

открывать страницы

извлекать текст

анализировать информацию

---

# 8. Speech to text

pipeline:

audio upload

↓

speech model

↓

text

↓

chat

---

# 9. Image generation

pipeline:

text prompt

↓

image model

↓

image file

↓

сохранение в проект

---

# 10. Token accounting

система считает:

все токены запросов

все токены ответов

embeddings

web search

image generation

Claude Code usage

счётчик сохраняется в usage table.

---

# 11. Ограничения тарифов

Backend проверяет:

количество проектов

объём файлов

количество токенов

при превышении лимита:

запрос блокируется.

---

# 12. Task system

каждая задача имеет статус:

created

running

waiting_approval

completed

failed

---

задачи могут включать:

несколько шагов.

пример:

создать backend

↓

создать модели

↓

создать API

↓

создать UI

---

# 13. Interaction GPT-5.4 → Claude Code

Оркестратор:

создаёт задачу

↓

передаёт Claude

↓

Claude выполняет

↓

возвращает результат

↓

GPT проверяет результат

↓

сохраняет изменения

---

# 14. Logs

система хранит:

логи задач

логи ошибок

логи действий AI

пользователь может видеть прогресс.

---

# 15. Security

ограничения:

Claude не имеет прямого доступа к системе без контроля оркестратора.

Claude не выполняет произвольные команды без разрешения.

опасные действия требуют approval.

---

# 16. Минимальный стек MVP

Backend:

FastAPI

Database:

PostgreSQL

Vector:

pgvector

Storage:

local storage

Queue:

Redis

AI:

OpenCode
Claude Code

---

# 17. масштабирование

в будущем:

можно добавить:

S3 storage

separate workers

kubernetes

distributed queue

---

# 18. итоговая схема

Frontend

↓

Backend API

↓

Orchestrator (GPT-5.4)

↓

Tools

↓

OpenCode

↓

Models

↓

Storage

---

END OF DOCUMENT
