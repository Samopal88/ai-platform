# DATA_MODEL
## AI Workspace Platform

---

# 1. Общая логика

База данных хранит:

- пользователей
- проекты
- чаты
- сообщения
- файлы
- версии файлов
- память
- summaries
- usage токенов
- задачи агентов
- лимиты тарифов

СУБД: PostgreSQL

расширение:

pgvector (для embeddings)

---

# 2. Основные таблицы

## users

id (uuid)
email
password_hash
created_at
plan_type
token_limit_month
storage_limit_total
storage_used
tokens_used_month

---

## projects

id (uuid)
user_id
name
description
created_at
updated_at

storage_used
file_count

---

## chats

id
project_id
model
created_at
updated_at

context_tokens
summary

---

## messages

id
chat_id
role

user
assistant
system

content

tokens_used

created_at

---

## files

id
project_id
name
type
size
mode

read_only
editable
generated

path

versioning_enabled

created_at
updated_at

---

## file_versions

id
file_id
version_number
path
size
created_at

максимум 3 версии

---

## embeddings

id
project_id
file_id
chunk_text
embedding vector

pgvector

---

## memories

id
project_id
content
type

fact
rule
decision

created_at

---

## summaries

id
chat_id
summary_text
created_at

---

## tasks

id
project_id
status

created
running
waiting_approval
completed
failed

task_type

claude_patch
analysis
generation

created_at
updated_at

result

json

---

## usage

id
user_id

tokens_input
tokens_output
tokens_embeddings
tokens_images
tokens_web

total_tokens

period

month

---

# 3. Связи

user → projects

project → chats

chat → messages

project → files

file → versions

project → embeddings

project → memories

project → tasks

user → usage

---

# 4. Лимиты тарифов

plan_type

starter
medium
pro

---

medium

30 проектов
1 GB storage
1M tokens

---

pro

50 проектов
3 GB storage
2M tokens

---

# 5. Файловая структура

/storage

/projects

/project_id

/files

/file_id

/versions

---

# 6. Индексация файлов

после загрузки:

извлечение текста

chunking

создание embeddings

сохранение в pgvector

---

# 7. токены

учитываются:

чат
embeddings
web search
images
agents

---

END OF DOCUMENT
