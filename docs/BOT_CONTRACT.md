# Контракт бот ↔ вебапп «Библиотека стилей»

Вебапп живёт в отдельном репо (Cloudflare Pages, https://sirnike.pages.dev).
Бот синкает `prompt_library.json` из вебаппа при старте — **source of truth = репо вебаппа**.
Парсер на стороне бота: `apply_webapp_prompt_payload_v2` (SirNike.py, ~строка 3096).

## prompt_library.json

Массив категорий:

```json
[
  {
    "title": "Название категории",
    "emoji": "🎬",
    "items": [
      {
        "title": "Название стиля",        // у ФОТО-стилей отсутствует НАМЕРЕННО — не дописывать!
        "prompt": "полный промт",
        "type": "video",                   // отсутствует = фото
        "video_url": "...", "poster_url": "...",   // для видео
        "example_url": "...",              // для фото
        "image_prompt": "...",             // опц.: промт стилизации кадра перед видео
        "description": "описание для карточки",
        "upload_hint": "Фото лица + 5 фото одежды", // что загрузить юзеру
        "input_hint": "Опиши свои пожелания (необязательно)", // опц.: показывает в модалке текстовое поле,
                                                                // введённый текст уходит в payload как note/n
        "added_at": "ISO-дата"
      }
    ]
  }
]
```

⚠️ У фото-стилей `title` отсутствует намеренно (решение владельца, карточки фото
без подписей — НЕ дописывать). Бот берёт fallback-лейбл (`_showcase_item_label`)
по `cat_idx`/`item_idx`, которые вебапп шлёт в каждом payload. У видео `title` заполняется.

**Исключение (2026-07-15, решение владельца):** у категории **💄 Бьюти** `title`
заполнен у всех фото-стилей — по её отдельной просьбе, специально для этой
категории. Остальные категории — правило «без title» остаётся в силе.

## Payload web_app_data (вебапп → бот)

JSON строкой. Полные и короткие ключи равнозначны:

| Поле | Кратко | Значение |
|---|---|---|
| `action` | `a` | `set_prompt` \| `set_video_prompt` \| `set_prompt_ref` \| `set_video_prompt_ref` \| `topup` (+ алиасы `apply_prompt`, `use_prompt`, `apply_template`…) |
| `title` | `t` | название стиля (показывается юзеру) |
| `prompt` | `p` | полный промт |
| `image_prompt` | — | опц., промт стилизации кадра для видео |
| `cat_idx` | `ci` | fallback: индексы вместо промта, |
| `item_idx` | `ii` | если payload не влезает — бот резолвит промт локально |
| `note` | `n` | опц., свободный текст юзера из поля `input_hint` — бот дописывает его в конец промта после резолва (см. `apply_webapp_prompt_payload_v2`), пусто = промт уходит как есть |

Правила:
- Payload > лимита Telegram → слать только `ci`/`ii` + `a` (+ `note`, если заполнен), без `p`.
- `topup` открывает у бота экран пополнения.
- Менять формат payload или структуру JSON — только синхронно с правкой парсера в боте
  (бриф бэкенду в `docs/briefs/backend.md` в репо бота).

## Инлайн-путь «Использовать» в 1 тап (Cloudflare Function, вариант B)

Решение по [docs/specs/2026-07-15_webapp_inline_1tap.md](specs/2026-07-15_webapp_inline_1tap.md)
принято 2026-07-16: **вариант B**. `sendData()` работает только для вебаппа,
открытого с reply-клавиатуры (`persistent_menu_kb`) — это НЕ меняется,
остаётся основным путём. Для вебаппа, открытого с ИНЛАЙН-кнопки (`main_menu_kb`,
`result_actions_kb` — там, где сейчас 2-таповый обход через `pl_open_webapp`),
добавляется отдельный путь через `answerWebAppQuery`:

1. Вебапп открыт с инлайн-кнопки → `tg.initDataUnsafe.query_id` присутствует.
2. Тап «Использовать» → вместо `tg.sendData()` вебапп шлёт `POST` на Cloudflare
   Function (репо вебаппа, `/functions/answer-webapp-query` или аналогично —
   путь фронтенд выбирает сам) с телом:
   ```json
   {"init_data": "<tg.initData как есть>", "cat_idx": 3, "item_idx": 7, "note": ""}
   ```
3. Function проверяет HMAC-подпись `init_data` секретом `BOT_TOKEN` (алгоритм
   — офиц. доки Telegram, "Validating data received via the Mini App"), достаёт
   `query_id`, отклоняет запрос при невалидной подписи.
4. Function вызывает Telegram Bot API напрямую (`fetch`, без SDK):
   ```
   POST https://api.telegram.org/bot<BOT_TOKEN>/answerWebAppQuery
   {
     "web_app_query_id": "<query_id из initData>",
     "result": {
       "type": "article",
       "id": "pl_use_3_7",
       "title": "Использовать стиль",
       "input_message_content": {"message_text": "📚 Стиль подобран — жми ниже 👇"},
       "reply_markup": {"inline_keyboard": [[
         {"text": "🚀 Использовать", "callback_data": "pl_use_3_7"}
       ]]}
     }
   }
   ```
5. Telegram сам вставляет это сообщение в чат юзера с ботом. Тап по кнопке —
   обычный `callback_query` с `callback_data=pl_use_{cat_idx}_{item_idx}`,
   бот обрабатывает его существующим хэндлером `button_handler` → ветка
   `pl_use_` (SirNike.py) — тот же код, что у инлайн-каталога библиотеки
   внутри бота. Дублировать логику применения стиля не пришлось.
6. Вебапп после успешного ответа Function вызывает `tg.close()`. При сетевой
   ошибке — показать тост, `tg.close()` не звать (см. критерий приёмки в спеке).

Секреты: `BOT_TOKEN` заводится вторым секретом в Cloudflare Pages (тот же
токен, что в BotHost) — секретами занимается Аня, не бэкенд-сессия.
Со стороны бота изменений не требуется — `pl_use_{cat_idx}_{item_idx}`
уже штатный формат callback_data.
