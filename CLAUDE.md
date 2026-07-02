# Сырник — Telegram-бот AI-генерации фото и видео

Python-монолит: [SirNike.py](SirNike.py) (~8000 строк, python-telegram-bot 22.x) + [db.py](db.py) (SQLite).
Продукты: генерация фото по промту, видео (Seedance/Kling/Veo), AI-аватар, «Улучшить фото»,
библиотека стилей (Telegram WebApp в **отдельном репо**, Cloudflare Pages).
Валюта — «изюминки», оплата через Telegram Payments.

## Ключевые факты

- **Деплой**: BotHost пересобирает Docker-образ из Git и перезапускает контейнер.
  `.env` не деплоится — секреты в панели BotHost. Данные (SQLite, логи) — в `DATA_DIR`
  (`/app/data`). Детали: [BOTHOST_SETUP.md](BOTHOST_SETUP.md). Локальные правки видны в проде только после пуша + «Update from Git».
- **Библиотека стилей**: source of truth — репо вебаппа (Cloudflare Pages), бот синкает
  `prompt_library.json` при старте. Контракт бот↔вебапп: [docs/BOT_CONTRACT.md](docs/BOT_CONTRACT.md).
- **Админы** (`ADMIN_IDS`): генерируют бесплатно, использование шаблонов не пишется в статистику.
- **БД**: схема и правила миграций — [DB_GUIDE.md](DB_GUIDE.md). Только ALTER TABLE-совместимые изменения.
- **Грабли и ложные срабатывания**: [AGENT_NOTES.md](AGENT_NOTES.md) — читать перед багфиксом,
  обновлять после. Авто-аудиты отключены владельцем — не создавать.

## Локальная разработка

- `.venv` — Python 3.11 (Homebrew, `python@3.11`), requirements.txt ставится как есть
  (Pillow 12, PTB 22.7 — без обходных версий). Пересоздать: `brew install python@3.11`
  → `/opt/homebrew/bin/python3.11 -m venv .venv` → `.venv/bin/pip install -r requirements.txt`.
  Полноценная прод-среда — Docker (локально Docker не установлен).
- Тесты: `.venv/bin/python3 test_new_features.py` (без сети, мокает Telegram).
- Компиляция: `python3 -m py_compile SirNike.py`.

## Конвенции

- Ветки: фичи/фиксы в ветках от main, коммиты с понятным префиксом (`ux:`, `fix:`, `feat:`).
- UX-аудиты — в `audits/` с датой в имени файла.
- Релизные заметки — строка в [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) после каждого смёржённого изменения.
- Задачи между ролями — файлы в `docs/briefs/`, должностные инструкции — `docs/roles/`.
  Схема команды (роль → модель → стартовый промт): [docs/TEAM.md](docs/TEAM.md).
- Тексты кнопок и инструкций должны совпадать буква в букву (частый источник багов — см. audits/).
