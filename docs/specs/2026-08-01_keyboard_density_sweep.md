# ТЗ: причесать плотность клавиатур — сводный проход, не по одной находке

Дата: 2026-08-01. Автор: фронтенд-сессия. Адресат: бэкенд. Повод: живой
скриншот Ани — `video_menu_kb` разрослась в 3 полноширинных ряда после
добавления «Видео с движением» (Motion Control, EvoLink). Аня справедливо
спросила, почему за каждой такой находкой надо обращаться отдельно — этот
файл закрывает проактивный аудит ВСЕХ 25 `def *_kb(...)` в SirNike.py на
тот же паттерн («всё по одной кнопке в ряд», хотя короткие кнопки можно
парами), а не только ту, что попала на скриншот.

Правило (docs/UI_STYLE.md, п.5): главный CTA и «◀️ В меню» — на всю ширину;
остальные короткие кнопки — парами/тройками; условная кнопка БЕЗ пары
(фиче-флаг) — одна в ряду, чтобы сетка не дёргалась при выключении флага.

## 1. `video_menu_kb` (SirNike.py:1383) — сама находка со скриншота

Сейчас: `video_label` (всегда) → `MOTION_CONTROL_ENABLED`-ряд (условно) →
`STUDIO_ENABLED`-ряд (условно) → назад. Каждая — отдельным рядом.

Формально это НЕ нарушение п.5 (условная кнопка без пары — одна в ряду,
именно чтобы не дёргалась сетка) — но правило написано для ОДНОЙ условной
кнопки; здесь их ДВЕ независимых, и когда включены ОБЕ (ровно случай на
скриншоте Ани — Motion Control и Студия одновременно), они должны делить
один ряд между собой, а не занимать по отдельному.

```python
def video_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    video_label = "🎬 Видео для Reels" if SEEDANCE_ENABLED else "🎬 Видео для Reels 🚧"
    rows = [[InlineKeyboardButton(video_label, callback_data="video")]]
    extra_buttons = []
    if MOTION_CONTROL_ENABLED:
        extra_buttons.append(InlineKeyboardButton("🕺 Видео с движением 🆕", callback_data="motion_start"))
    if STUDIO_ENABLED and PROMPT_WEBAPP_URL and user_id is not None:
        extra_buttons.append(InlineKeyboardButton(
            "🎬 Студия мультиков",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id) + "&tab=studio"),
        ))
    if extra_buttons:
        rows.append(extra_buttons)  # 1 или 2 кнопки в одном ряду — по факту включённых флагов
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="avatar_back_menu")])
    return InlineKeyboardMarkup(rows)
```

`video_label` остаётся отдельным полноширинным рядом — это главный вход
раздела (аналог главного CTA), не короткая опция наравне с остальными.
Результат: оба флага выключены (прод по умолчанию) — 2 ряда как сейчас
(было и остаётся); один флаг — 2 ряда с этой кнопкой (как сейчас); оба
флага включены (кейс со скриншота) — 3 ряда вместо 4.

## 2. `image_model_menu_kb` (SirNike.py:1452-1469)

Две модели (Gemini/GPT-5 Image) — взаимоисключающий выбор с маркером «●»,
сейчас каждая в своём ряду. Объединить в один ряд, «◀️ В меню» оставить
полноширинной (недеструктивный возврат — уже так, не трогать):

```python
def image_model_menu_kb(state: UserState) -> InlineKeyboardMarkup:
    selected = get_image_model(state)
    gemini_cost = calc_generation_cost(None, "gemini")
    gpt5_cost = calc_generation_cost(None, "gpt5")
    rows = [
        [
            InlineKeyboardButton(
                ("● " if selected == "gemini" else "") + f"{get_image_model_label('gemini')} · {gemini_cost} 🍇",
                callback_data="image_model_set_gemini",
            ),
            InlineKeyboardButton(
                ("● " if selected == "gpt5" else "") + f"GPT-5 Image 🆕 · {gpt5_cost} 🍇",
                callback_data="image_model_set_gpt5",
            ),
        ],
        [InlineKeyboardButton("◀️ В меню", callback_data="avatar_back_menu")],
    ]
    return InlineKeyboardMarkup(rows)
```

## 3. `bug_bounty_admin_kb` (SirNike.py:1501-1505) — низкий приоритет, админ-экран

«🎁 Наградить N 🍇» и «💬 Ответить пользователю» — оба короткие, не CTA/нав.
Объединить в один ряд:

```python
def bug_bounty_admin_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"🎁 Наградить {BUG_BOUNTY_REWARD} 🍇", callback_data=f"reward_bug_{user_id}"),
        InlineKeyboardButton("💬 Ответить пользователю", callback_data=f"support_reply_{user_id}"),
    ]])
```

## Проверено и НЕ трогать (чтобы не переделывать зря)

- **`video_kb`** — шаги «1️⃣ Добавить описание»/«2️⃣ Добавить фото» тоже по
  одному в ряду, но это пронумерованные шаги мастера (правило 1: 1️⃣/2️⃣ —
  маркер состояния, не равноценные опции), а не пара для объединения —
  оставить как есть.
- **`main_menu_kb`, `photo_menu_kb`, `video_model_picker_kb`,
  `avatar_actions_kb`, `prompt_library_menu_kb`, `result_actions_kb`** и
  ещё ~10 других — уже парят короткие кнопки корректно, без находок.
- **`prompt_library_admin_kb_legacy`** (SirNike.py:1692) — да, тот же
  паттерн («по одной в ряду»), НО это мёртвый код: ни одного вызова во
  всём файле (заменена на `prompt_library_admin_kb`, которая уже
  причёсана). Не тратить время на UI-фикс мёртвого кода — отдельным
  тикетом можно просто удалить функцию, если бэкенд подтвердит, что она
  правда нигде не используется (не проверяла вызовы из других файлов/веток).

## Критерий готовности

- `video_menu_kb`: оба фичефлага (Motion Control, Студия) включены → одна
  общая строка на двоих под «🎬 Видео для Reels», не два отдельных ряда.
  Один флаг / оба выключены → поведение не меняется (уже корректно).
- `image_model_menu_kb`: обе модели в одном ряду, «●»-маркер и переключение
  работают как раньше.
- `bug_bounty_admin_kb`: «Наградить»/«Ответить» в одном ряду.
- `.venv/bin/python3 test_new_features.py` — 0 FAIL (если есть тесты на
  структуру этих клавиатур — поправить под новые ряды, не удалять проверку).
