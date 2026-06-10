# Сырник — Telegram-бот генерации изображений и видео

Python-бот на [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v22.7.  
Внутренняя валюта: **изюминки**. Деплой: Docker + BotHost.

---

## Быстрый старт

```bash
# Локально
cp .env.example .env   # заполни переменные
python SirNike.py

# Docker
docker build -t sirnike .
docker run --env-file .env -v $(pwd)/data:/app/data sirnike
```

Деплой на BotHost: подключи репозиторий и нажми **Update from Git**.

---

## Переменные окружения

### Обязательные

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather |
| `PROVIDER_TOKEN` | Токен платёжного провайдера (Telegram Payments) |
| `NANO_API_KEY` | API-ключ для провайдера YESAPI (если `AI_PROVIDER=YESAPI`) |

### Провайдеры генерации изображений

Выбирается переменной `AI_PROVIDER` (значение по умолчанию: `YESAPI`).

**YESAPI (по умолчанию)**
```env
AI_PROVIDER=YESAPI
NANO_API_BASE=https://api.yesai.su/v2/google/nanobanana
NANO_API_KEY=your_key
```

**MashaGPT**
```env
AI_PROVIDER=MASHAGPT
MASHAGPT_API_BASE=https://api.mashagpt.ru
MASHAGPT_API_KEY=your_key
MASHAGPT_IMAGE_MODEL=nano-banana-pro
MASHAGPT_CHAT_MODEL=gpt-4o-mini
```

**ZvenoAI**
```env
AI_PROVIDER=ZVENO
ZVENO_API_BASE=https://api.zveno.ai/v1
ZVENO_API_KEY=your_key
ZVENO_IMAGE_MODEL=google/gemini-3-pro-image-preview
ZVENO_CHAT_MODEL=google/gemini-2.5-flash
```

### Видеогенерация (Seedance)

```env
SEEDANCE_ENABLED=1              # включить Seedance 2.0
SEEDANCE_FAST_ENABLED=1         # включить Seedance 2.0 Fast
SEEDANCE_COST_PER_SECOND=2      # изюминок за секунду видео
SEEDANCE_DURATION_OPTIONS=5,10,15
SEEDANCE_FAST_DURATION_OPTIONS=5,10,15
```

### Прочее

```env
ADMIN_IDS=123456789,987654321   # ID администраторов через запятую
START_BONUS=5                   # изюминки новому пользователю
FREE_GENERATIONS_PER_DAY=1      # бесплатных генераций в день
BASE_GENERATION_COST=5          # стоимость генерации изображения
REFERRAL_BONUS_REFERRER=10      # изюминки за приглашённого
REFERRAL_BONUS_NEW_USER=5       # изюминки новому по рефералке
RESULTS_CHANNEL_ID=@channel     # канал для публикации результатов (опционально)
PROMPT_LIBRARY_REMOTE_URL=...   # URL удалённой библиотеки промтов (Cloudflare)
PROMPT_WEBAPP_URL=...           # URL WebApp библиотеки промтов (опционально)
IMGBB_API_KEY=...               # для хостинга изображений (опционально)
DATA_DIR=/app/data              # папка для SQLite и логов
TEST_MODE=0                     # тестовый режим (платежи не списываются)
```

---

## Пользовательские команды

| Команда | Описание |
|---|---|
| `/start` | Главное меню |
| `/balance` | Баланс изюминок и бесплатные генерации |
| `/buy` | Купить изюминки |
| `/ref` | Реферальная ссылка |
| `/ai <вопрос>` | Текстовый AI-ассистент |
| `/report` | Сообщить о проблеме |

---

## Генерация

**Изображения** — отправь промпт текстом или выбери шаблон из библиотеки.  
Стоимость: `BASE_GENERATION_COST` изюминок. Можно прикреплять референсы (до 8 фото).

**Видео (Seedance)** — оживи фото. Включается кнопкой «Видео» в главном меню.  
Стоимость считается за секунду: `SEEDANCE_COST_PER_SECOND × длительность`.

**Аватары** — загрузи фото и получи AI-портрет в разных стилях.

Очередь генерации — до 100 задач одновременно. При переполнении — сообщение с предложением попробовать позже.

---

## Пакеты изюминок

| Изюминок | Цена (⭐ Stars) |
|---|---|
| 10 | 60 |
| 20 | 100 |
| 50 | 250 |
| 120 | 600 |
| 300 | 1500 |

---

## Админ-команды

### Рассылки

| Команда | Описание |
|---|---|
| `/broadcast_text <текст>` | Текстовая рассылка всем пользователям |
| `/broadcast_promo <промпт>` | Промо-рассылка: фото из реплая + кнопка «Попробовать» |
| `/broadcast_hide_keyboard` | Убрать клавиатуру у всех пользователей |
| `/promo_stats <promo_id>` | Статистика по промо-рассылке |
| `/audience_stats [days]` | Метрики аудитории за период |

### Управление

| Команда | Описание |
|---|---|
| `/admin_add <user_id> <amount>` | Начислить изюминки пользователю |
| `/previewrefs` | Предпросмотр референсов последнего запроса |

---

## Библиотека промтов

### Пользователю

| Команда | Описание |
|---|---|
| `/pl_save [название]` | Сохранить последнюю генерацию в библиотеку |
| `/pl_import <название> \| <промпт>` | Сохранить шаблон из фото в реплае |
| `/pl_import_video <название> \| <промпт>` | Сохранить шаблон видео из реплая |
| `/pl_history` | История генераций — выбрать и сохранить в библиотеку |

### Администратору

| Команда | Описание |
|---|---|
| `/pl_admin` | Кнопочный редактор библиотеки |
| `/pl_list` | Список категорий и количество шаблонов |
| `/pl_newcat <название>` | Создать категорию |
| `/pl_renamecat <старое> \| <новое>` | Переименовать категорию |
| `/pl_delcat <название>` | Удалить категорию |
| `/pl_export` | Скачать текущий `prompt_library.json` |
| `/pl_sync` | Загрузить библиотеку с Cloudflare (перезаписывает локальную) |
| `/pl_backups` | Список последних автобэкапов |
| `/pl_where` | Показать путь к файлу библиотеки на сервере |

### Как используются шаблоны

1. **Последняя генерация** → `/pl_save` → выбрать категорию.
2. **Из истории** → `/pl_history` → выбрать запись → «Сохранить в библиотеку».
3. **Из старого фото** → ответить на фото командой `/pl_import Название | промпт`.

При нажатии «Использовать промпт» в библиотеке промпт подставляется автоматически.

---

## Структура данных

```
/app/data/
  sirnike.db              # SQLite: пользователи, баланс, история, платежи
  prompt_library.json     # библиотека промтов (основная копия)
  pl_backups/             # автобэкапы библиотеки (хранятся последние 20)
  sirnike.log             # лог бота
```

---

## Стек

- Python 3.12
- python-telegram-bot 22.7 (asyncio, single-threaded event loop)
- SQLite (через стандартный `sqlite3`)
- aiohttp 3.13
- Pillow 12.2
- Docker + BotHost
