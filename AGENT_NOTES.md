# Agent Notes — Сырник

Этот файл читается агент-ботом при анализе кода.
Обновляй его после каждого цикла правок.

---

## ✅ Исправленные баги (не репортить повторно)

<!-- Формат:
### [дата] Название бага
Что было исправлено и где.
-->

---

## 🚫 Ложные срабатывания (false positives)

### asyncio race condition в run_generation / queued_user_ids
**Статус:** false_positive  
queued_user_ids.add(user.id) стоит сразу после проверки без await между ними.
В однопоточном asyncio это атомарно — race condition физически невозможен.
Не репортить как баг.

---

## 📝 Заметки для агента

- Бот работает в однопоточном asyncio event loop
- Провайдеры генерации: Zveno (Gemini), MashaGPT, YesAPI, Seedance
- Внутренняя валюта: изюминки
- Деплой: BotHost + Docker + SQLite
