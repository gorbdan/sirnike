# -*- coding: utf-8 -*-
"""Блок 24: Хаб генерации — Конструктор видео для Reels
(docs/specs/2026-08-13_webapp_generation_hub.md). Бэкенд-часть (пункты 1-6
раздела «Что нужно от бэкенда»):

- Новый парсер `apply_webapp_generation_payload` (action=`start_generation`/
  `sg`), диспетчеризуется из `apply_webapp_prompt_payload_v2`.
- Серверная валидация фичефлагов видео-модели с откатом на дефолт.
- Карточка подтверждения (Экран V2) с ценой, пересчитанной
  calc_seedance_cost/get_video_model_cost_per_second на момент показа.
- `VIDEO_CONSTRUCTOR_ENABLED` kill-switch на обоих входах («🎬 Видео для
  Reels» — reply-кнопка/persistent_menu_kb и инлайн video_cb=="video").
- `get_video_constructor_config`/`get_video_constructor_webapp_url` — cfg,
  синхронизированный со схемой уже смёрженного constructor.js в репо вебаппа
  (docs/BOT_CONTRACT.md, раздел «Конструктор видео (Хаб генерации)»).

Формат payload в тестах — ровно тот, что реально шлёт constructor.js
(buildStartGenerationPayload): полные ключи (`product`, `video_model`,
`aspect`, `duration`, `description`, `quality`, `face_grid`, `refs`,
`board_id`), НЕ короткие алиасы — короткие алиасы (`pr`/`vm`/…) проверяются
отдельно (24j) как часть контракта на будущее, но не то, что шлёт вебапп
сегодня.
"""
import asyncio

from test_helpers import S, make_update_context, make_webapp_update_context


def test_block_24a_basic_apply_sets_state_and_sends_confirm_card():
    update, context, message = make_webapp_update_context(user_id=9701)
    applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
        "action": "start_generation",
        "product": "video",
        "video_model": "seedance2",
        "aspect": "9:16",
        "quality": "pro",
        "duration": 10,
        "face_grid": True,
        "description": "Кот танцует брейк-данс на кухне",
        "refs": [f"https://i.ibb.co/gen/{i}.jpg" for i in range(3)],
    }))
    assert applied is True, "24a.1 payload распознан"

    state = context.user_data["state"]
    assert state.video_model == "seedance2", "24a.2 модель сохранена"
    assert state.video_aspect_ratio == "9:16", "24a.3 формат сохранён"
    assert state.video_mode == "1080p", f"24a.4 quality=pro -> самый качественный режим: {state.video_mode}"
    assert state.video_duration == 10, "24a.5 длительность сохранена"
    assert state.video_face_grid is True, "24a.6 детектор лиц сохранён"
    assert state.video_prompt == "Кот танцует брейк-данс на кухне", "24a.7 описание сохранено"
    assert len(state.animation_source_urls) == 3, f"24a.8 фото сохранены: {state.animation_source_urls}"
    assert state.video_session_active is True, "24a.9 видео-сессия активна (для дальнейшего video_start)"

    assert message.reply_text.await_args_list, "24a.10 карточка отправлена"
    text = message.reply_text.await_args_list[-1].args[0]
    assert text.startswith("🎬 Готово к запуску"), f"24a.11 заголовок карточки: {text!r}"
    assert "Модель: Seedance 2 — максимум качества и движения, наш выбор" in text, f"24a.12 модель: {text!r}"
    assert "Формат: 9:16 (вертикаль, Reels)" in text, f"24a.13 формат: {text!r}"
    assert "Качество: Pro" in text, f"24a.14 качество: {text!r}"
    assert "Длительность: 10с" in text, f"24a.15 длительность (формат «10с», не «10 сек»): {text!r}"
    assert "Детектор лиц: вкл 🟢 (защита от отказа модерации)" in text, f"24a.16 детектор лиц: {text!r}"
    assert "Фото: 3 шт." in text, f"24a.17 фото: {text!r}"
    assert "Описание: есть" in text, f"24a.18 описание: {text!r}"

    expected_cost = S.calc_seedance_cost(10, S.get_video_model_cost_per_second("seedance2", "1080p"))
    assert f"Стоимость: {expected_cost} 🍇" in text, f"24a.19 цена пересчитана бэкендом: {text!r} (ждали {expected_cost})"

    kb = message.reply_text.await_args_list[-1].kwargs.get("reply_markup")
    btns = [b for row in kb.inline_keyboard for b in row]
    launch_btn = [b for b in btns if b.text == "🚀 Запустить видео"][0]
    assert launch_btn.callback_data == "video_start", (
        f"24a.20 запуск переиспользует существующий пайплайн: {launch_btn.callback_data}"
    )
    restart_btn = [b for b in btns if b.text == "🔁 Начать заново"][0]
    assert restart_btn is not None, "24a.21 кнопка «Начать заново» есть"


def test_block_24b_disabled_model_flag_falls_back_to_default_with_warning():
    _orig = S.KLING3_ENABLED
    try:
        S.KLING3_ENABLED = False
        update, context, message = make_webapp_update_context(user_id=9702)
        applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
            "action": "start_generation",
            "product": "video",
            "video_model": "kling3",
            "description": "Плывущий город в тумане",
        }))
        assert applied is True, "24b.1 обработчик не падает на выключенной модели"
        state = context.user_data["state"]
        assert state.video_model == "seedance2", f"24b.2 откат на дефолт: {state.video_model}"

        texts = [c.args[0] for c in message.reply_text.await_args_list]
        assert any("недоступна" in t for t in texts), f"24b.3 понятное сообщение о недоступности: {texts}"
        assert any(t.startswith("🎬 Готово к запуску") for t in texts), (
            f"24b.4 карточка всё равно показана — с дефолтной моделью: {texts}"
        )
        assert any("Seedance 2" in t for t in texts if t.startswith("🎬")), "24b.5 карточка содержит Seedance 2"
    finally:
        S.KLING3_ENABLED = _orig


def test_block_24c_quality_fast_alias_maps_to_lowest_mode():
    update, context, message = make_webapp_update_context(user_id=9703)
    applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
        "action": "start_generation",
        "product": "video",
        "video_model": "seedance2",
        "quality": "fast",
        "duration": 5,
        "description": "Морской пейзаж на закате",
    }))
    assert applied is True
    state = context.user_data["state"]
    assert state.video_mode == "480p", f"24c.1 quality=fast -> самый лёгкий режим: {state.video_mode}"
    text = message.reply_text.await_args_list[-1].args[0]
    assert "Качество: Fast" in text, f"24c.2 карточка показывает Fast: {text!r}"


def test_block_24d_wan27_custom_duration_no_quality_line_per_second_price():
    update, context, message = make_webapp_update_context(user_id=9704)
    applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
        "action": "start_generation",
        "product": "video",
        "video_model": "wan27",
        "duration": 7,
        "description": "Танцовщица на крыше небоскрёба",
    }))
    assert applied is True
    state = context.user_data["state"]
    assert state.video_model == "wan27", "24d.1 модель Wan 2.7"
    assert state.video_duration == 7, f"24d.2 произвольная длительность в границах модели сохранена: {state.video_duration}"

    text = message.reply_text.await_args_list[-1].args[0]
    assert "Длительность: 7с" in text, f"24d.3 длительность в карточке: {text!r}"
    assert "Качество:" not in text, f"24d.4 у Wan 2.7 в Конструкторе нет строки качества: {text!r}"
    assert "Детектор лиц:" not in text, f"24d.5 у Wan 2.7 нет детектора лиц: {text!r}"

    expected_cost = S.calc_seedance_cost(7, S.get_video_model_cost_per_second("wan27"))
    assert f"Стоимость: {expected_cost} 🍇" in text, f"24d.6 цена по per-second тарифу: {text!r}"


def test_block_24e_empty_description_and_refs_asks_to_go_back_no_confirm_card():
    update, context, message = make_webapp_update_context(user_id=9705)
    applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
        "action": "start_generation",
        "product": "video",
        "video_model": "seedance2",
    }))
    assert applied is True, "24e.1 обработчик не падает на пустом payload"
    texts = [c.args[0] for c in message.reply_text.await_args_list]
    assert any("описание" in t.lower() and "фото" in t.lower() for t in texts), (
        f"24e.2 просит вернуться и добавить описание/фото: {texts}"
    )
    assert not any(t.startswith("🎬 Готово к запуску") for t in texts), (
        f"24e.3 карточка подтверждения НЕ отправляется без описания/фото: {texts}"
    )


def test_block_24f_refs_capped_at_max_seedance_image_references():
    update, context, message = make_webapp_update_context(user_id=9706)
    urls = [f"https://i.ibb.co/cap/{i}.jpg" for i in range(12)]
    applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
        "action": "start_generation",
        "product": "video",
        "video_model": "seedance2",
        "refs": urls,
    }))
    assert applied is True
    state = context.user_data["state"]
    assert len(state.animation_source_urls) == S.MAX_SEEDANCE_IMAGE_REFERENCES, (
        f"24f.1 потолок фото — существующий MAX_SEEDANCE_IMAGE_REFERENCES: {len(state.animation_source_urls)}"
    )
    text = message.reply_text.await_args_list[-1].args[0]
    assert f"Фото: {S.MAX_SEEDANCE_IMAGE_REFERENCES} шт." in text, f"24f.2 карточка отражает капнутое число: {text!r}"


def test_block_24g_non_video_product_honest_message_not_silent():
    update, context, message = make_webapp_update_context(user_id=9707)
    applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
        "action": "start_generation",
        "product": "midjourney",
        "description": "что угодно",
    }))
    assert applied is True, "24g.1 обработчик не падает на product вне MVP"
    texts = [c.args[0] for c in message.reply_text.await_args_list]
    assert texts, "24g.2 юзер получает объяснение, не тишину"
    assert any("скоро" in t.lower() or "недоступ" in t.lower() for t in texts), (
        f"24g.3 честное сообщение, не generic ошибка: {texts}"
    )
    assert "state" not in context.user_data, "24g.4 состояние видео не создаётся зря для неподдержанного продукта"


def test_block_24h_missing_product_returns_false():
    update, context, message = make_webapp_update_context(user_id=9708)
    applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
        "action": "start_generation",
        "description": "без product",
    }))
    assert applied is False, "24h.1 отсутствие product — сигнал вызывающему коду попробовать другой парсер/дефолт"


def test_block_24i_seedance_disabled_shows_unavailable_text():
    _orig = S.SEEDANCE_ENABLED
    try:
        S.SEEDANCE_ENABLED = False
        update, context, message = make_webapp_update_context(user_id=9709)
        applied = asyncio.run(S.apply_webapp_generation_payload(update, context, {
            "action": "start_generation",
            "product": "video",
            "description": "тест",
        }))
        assert applied is True, "24i.1 обработчик не падает"
        texts = [c.args[0] for c in message.reply_text.await_args_list]
        assert any(t == S.video_unavailable_text() for t in texts), f"24i.2 честное «видео недоступно»: {texts}"
    finally:
        S.SEEDANCE_ENABLED = _orig


def test_block_24j_dispatch_from_v2_router_full_and_short_action_alias():
    update, context, message = make_webapp_update_context(user_id=9710)
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "start_generation",
        "product": "video",
        "video_model": "seedance2",
        "description": "полный алиас экшена",
    }))
    assert applied is True, "24j.1 apply_webapp_prompt_payload_v2 диспетчеризует start_generation"
    text = message.reply_text.await_args_list[-1].args[0]
    assert text.startswith("🎬 Готово к запуску"), f"24j.2: {text!r}"

    update2, context2, message2 = make_webapp_update_context(user_id=9711)
    applied2 = asyncio.run(S.apply_webapp_prompt_payload_v2(update2, context2, {
        "a": "sg",
        "pr": "video",
        "vm": "seedance2",
        "p": "короткий алиас экшена и полей",
    }))
    assert applied2 is True, "24j.3 короткие алиасы a=sg/pr/vm/p тоже распознаются"
    text2 = message2.reply_text.await_args_list[-1].args[0]
    assert text2.startswith("🎬 Готово к запуску"), f"24j.4: {text2!r}"
    assert context2.user_data["state"].video_prompt == "короткий алиас экшена и полей", "24j.5 описание из p"


def test_block_24k_video_constructor_enabled_killswitch_both_entry_points():
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    try:
        S.PROMPT_WEBAPP_URL = "https://sirnike.pages.dev"

        # Флаг выключен (дефолт) — persistent_menu_kb отдаёт обычную текстовую
        # кнопку видео (ноль изменений поведения).
        S.VIDEO_CONSTRUCTOR_ENABLED = False
        kb_off = S.persistent_menu_kb(9712)
        video_btn_off = [b for row in kb_off.keyboard for b in row if b.text == S.MENU_BTN_VIDEO][0]
        assert video_btn_off.web_app is None, "24k.1 флаг выкл — кнопка видео остаётся обычной текстовой"

        # Инлайн-путь при выключенном флаге — старое поведение (пикер модели).
        update, context, query = make_update_context("video", user_id=9712)
        asyncio.run(S.button_handler(update, context))
        kb_texts_off = [
            c.kwargs.get("reply_markup") for c in query.message.reply_text.await_args_list
        ]
        sent_texts_off = [c.args[0] for c in query.message.reply_text.await_args_list]
        assert any("Выбери модель" in t for t in sent_texts_off), (
            f"24k.2 флаг выкл — старый пикер модели: {sent_texts_off}"
        )

        # Флаг включён — обе точки входа ведут в Конструктор.
        S.VIDEO_CONSTRUCTOR_ENABLED = True
        kb_on = S.persistent_menu_kb(9713)
        video_btn_on = [b for row in kb_on.keyboard for b in row if b.text == S.MENU_BTN_VIDEO][0]
        assert video_btn_on.web_app is not None, "24k.3 флаг вкл — кнопка видео открывает вебапп напрямую"
        assert "tab=videoConstructor" in video_btn_on.web_app.url, (
            f"24k.4 URL ведёт в Конструктор: {video_btn_on.web_app.url}"
        )

        update2, context2, query2 = make_update_context("video", user_id=9713)
        asyncio.run(S.button_handler(update2, context2))
        sent_texts_on = [c.args[0] for c in query2.message.reply_text.await_args_list]
        assert any("Конструктор" in t for t in sent_texts_on), (
            f"24k.5 флаг вкл — инлайн-путь тоже предлагает Конструктор: {sent_texts_on}"
        )
        kb_msgs_on = [c.kwargs.get("reply_markup") for c in query2.message.reply_text.await_args_list]
        webapp_btns = [
            b for kb in kb_msgs_on if kb for row in kb.inline_keyboard for b in row if b.web_app is not None
        ]
        assert webapp_btns, "24k.6 инлайн-путь отдаёт web_app-кнопку Конструктора"
        assert "tab=videoConstructor" in webapp_btns[0].web_app.url, (
            f"24k.7 та же цель — Конструктор: {webapp_btns[0].web_app.url}"
        )
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24l_config_shape_matches_frontend_contract():
    _flags = {
        "SEEDANCE_FAST_ENABLED": S.SEEDANCE_FAST_ENABLED,
        "KLING3_ENABLED": S.KLING3_ENABLED,
        "VEO31_ENABLED": S.VEO31_ENABLED,
        "WAN27_ENABLED": S.WAN27_ENABLED,
        "GEMINI_OMNI_ENABLED": S.GEMINI_OMNI_ENABLED,
        "SEEDANCE25_ENABLED": S.SEEDANCE25_ENABLED,
    }
    try:
        S.SEEDANCE_FAST_ENABLED = True
        S.KLING3_ENABLED = True
        S.VEO31_ENABLED = True
        S.WAN27_ENABLED = True
        S.GEMINI_OMNI_ENABLED = True
        S.SEEDANCE25_ENABLED = True

        cfg = S.get_video_constructor_config()
        assert isinstance(cfg.get("models"), list) and cfg["models"], "24l.1 models — непустой список"
        assert cfg.get("default_model") == "seedance2", "24l.2 default_model = seedance2"
        ids = [m["id"] for m in cfg["models"]]
        assert set(ids) == {
            "seedance2", "seedance2_fast", "kling3", "veo31", "wan27", "gemini_omni", "seedance25",
        }, f"24l.3 все включённые модели присутствуют: {ids}"

        by_id = {m["id"]: m for m in cfg["models"]}

        sd2 = by_id["seedance2"]
        assert sd2["quality"] == ["pro", "fast"], f"24l.4 seedance2 — бинарный pro/fast: {sd2.get('quality')}"
        assert isinstance(sd2["prices"], dict) and "pro" in sd2["prices"] and "fast" in sd2["prices"], (
            f"24l.5 seedance2 prices вложены по качеству: {sd2['prices']}"
        )
        assert sd2["face_grid"] is True, "24l.6 seedance2 поддерживает детектор лиц"
        assert set(sd2["formats"]) == {"16:9", "9:16", "1:1", "4:3"}, f"24l.7 seedance2 формат: {sd2['formats']}"

        wan = by_id["wan27"]
        assert wan["durations"] == {"custom": [2, 10]}, f"24l.8 wan27 — свободный диапазон: {wan['durations']}"
        assert "quality" not in wan, "24l.9 wan27 — качество не предлагается (упрощённый UI)"
        assert "per_second" in wan["prices"], f"24l.10 wan27 — тариф за секунду: {wan['prices']}"

        veo = by_id["veo31"]
        assert "quality" not in veo, "24l.11 veo31 — фиксированное качество, поле опущено"
        assert set(veo["formats"]) == {"16:9", "9:16"}, f"24l.12 veo31 без квадрата/4:3: {veo['formats']}"

        for m in cfg["models"]:
            assert m.get("badge") in (None, m.get("badge")), "24l.13 badge опционален"
            if m["id"] in ("seedance2", "seedance2_fast"):
                assert m.get("badge") is None or "badge" not in m, f"24l.14 {m['id']} без бейджа: {m}"
    finally:
        S.SEEDANCE_FAST_ENABLED = _flags["SEEDANCE_FAST_ENABLED"]
        S.KLING3_ENABLED = _flags["KLING3_ENABLED"]
        S.VEO31_ENABLED = _flags["VEO31_ENABLED"]
        S.WAN27_ENABLED = _flags["WAN27_ENABLED"]
        S.GEMINI_OMNI_ENABLED = _flags["GEMINI_OMNI_ENABLED"]
        S.SEEDANCE25_ENABLED = _flags["SEEDANCE25_ENABLED"]
