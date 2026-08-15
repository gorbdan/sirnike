# -*- coding: utf-8 -*-
"""Блок 24: хаб генерации в вебаппе (docs/specs/2026-08-13_webapp_generation_hub.md,
docs/specs/2026-08-13_webapp_generation_hub_navigation_full.md). Вебапп собирает все
настройки одним экраном («Конструктор» — видео/Midjourney/Аватар/фото) и шлёт один
payload `start_generation`/`sg` с полем `product` — бот резолвит его в UserState (те
же поля, что заполняют сегодняшние чат-панели/мини-флоу) и показывает карточку
подтверждения с существующей кнопкой запуска (`video_start`/`mj_generate`/
`avatar_gen_start`/`generate`). Сам запуск/списание/очередь/доставка результата НЕ
меняются — это тот же биллинг-путь, что и всегда."""
import asyncio
import types

from test_helpers import S, make_webapp_update_context, make_update_context


def test_block_24_flag_off_declines_payload():
    _orig = S.VIDEO_CONSTRUCTOR_ENABLED
    S.VIDEO_CONSTRUCTOR_ENABLED = False
    try:
        update, context, message = make_webapp_update_context()
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "start_generation",
            "product": "video",
            "video_model": "seedance2",
            "description": "кот в космосе",
        }))
        assert applied is True, "24.1 payload распознан (даже при выключенном флаге — честный отказ)"
        text = message.reply_text.await_args_list[0].args[0]
        assert "недоступна" in text.lower(), f"24.2 честный отказ, не крэш и не тихое игнорирование: {text!r}"
        assert "state" not in context.user_data, "24.3 UserState не создаётся при отказе"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig


def test_block_24b_full_payload_builds_state_and_confirmation_card():
    _orig = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        update, context, message = make_webapp_update_context()
        refs = ["https://i.ibb.co/vid/1.jpg", "https://i.ibb.co/vid/2.jpg"]
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "start_generation",
            "product": "video",
            "video_model": "seedance2",
            "aspect": "9:16",
            "quality": "pro",
            "duration": 10,
            "face_grid": True,
            "description": "девушка на закате, кино",
            "refs": refs,
        }))
        assert applied is True, "24b.1 payload применён"

        state = context.user_data["state"]
        assert state.video_model == "seedance2", "24b.2 модель сохранена"
        assert state.video_model_picked is True, "24b.3 model_picked, чтобы video_kb не показывал пикер повторно"
        assert state.video_aspect_ratio == "9:16", "24b.4 формат сохранён"
        # resolve_webapp_video_quality: "pro" -> самый качественный ДОСТУПНЫЙ режим
        # модели (последний в списке get_seedance_mode_options), не фиксированный
        # 720p — у seedance2 это 1080p (480p/720p/1080p по умолчанию).
        assert state.video_mode == "1080p", f"24b.5 quality=pro -> самый качественный режим: {state.video_mode}"
        assert state.video_duration == 10, "24b.6 длительность сохранена"
        assert state.video_face_grid is True, "24b.7 детектор лиц сохранён"
        assert state.video_prompt == "девушка на закате, кино", "24b.8 описание сохранено"
        assert S.get_video_image_urls(state) == refs, f"24b.9 фото легли в те же поля, что и ручная загрузка: {state.animation_source_urls}"

        text = message.reply_text.await_args_list[0].args[0]
        assert text.startswith("🎬 Готово к запуску"), f"24b.10 заголовок карточки подтверждения: {text!r}"
        # build_video_generation_confirm_text форматирует длительность «10с», не «10 сек».
        assert "Seedance 2" in text and "9:16" in text and "10с" in text, f"24b.11 параметры видны в карточке: {text!r}"
        assert "Качество: Pro" in text, f"24b.11b качество отражено в карточке: {text!r}"

        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        rows = kb.inline_keyboard
        launch_btn = rows[0][0]
        assert launch_btn.text == "🚀 Запустить видео", f"24b.12 кнопка запуска — дословно текст video_kb: {launch_btn.text!r}"
        assert launch_btn.callback_data == "video_start", "24b.13 переиспользует существующий коллбэк, не новый биллинг-путь"
        edit_btn = rows[1][0]
        assert edit_btn.text == "✏️ Изменить", f"24b.14 кнопка правки с сохранением черновика (Full, prefill): {edit_btn.text!r}"
        assert edit_btn.web_app is not None and "prefill=" in edit_btn.web_app.url, (
            f"24b.15 открывает конструктор с префиллом текущих настроек: {edit_btn.web_app.url if edit_btn.web_app else None}"
        )
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24b2_quality_fast_alias_maps_to_lowest_mode():
    # У seedance2 (480p/720p/1080p) fast/pro должны различаться — тест 24b уже
    # проверяет "pro", тут отдельно "fast" -> самый лёгкий режим (options[0]).
    _orig = S.VIDEO_CONSTRUCTOR_ENABLED
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "start_generation",
            "product": "video",
            "video_model": "seedance2",
            "quality": "fast",
            "duration": 5,
            "description": "морской пейзаж на закате",
        }))
        assert applied is True
        state = context.user_data["state"]
        assert state.video_mode == "480p", f"24b2.1 quality=fast -> самый лёгкий режим: {state.video_mode}"
        text = message.reply_text.await_args_list[0].args[0]
        assert "Качество: Fast" in text, f"24b2.2 карточка показывает Fast: {text!r}"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig


def test_block_24c_disabled_model_falls_back_with_warning():
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_kling = S.KLING3_ENABLED
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    S.KLING3_ENABLED = False
    try:
        update, context, message = make_webapp_update_context()
        asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "start_generation",
            "product": "video",
            "video_model": "kling3",
            "description": "тест",
        }))
        state = context.user_data["state"]
        assert state.video_model == "seedance2", (
            f"24c.1 отключённая флагом модель из устаревшего кэша вебаппа откатывается на дефолт: {state.video_model}"
        )
        text = message.reply_text.await_args_list[0].args[0]
        assert "недоступна" in text.lower(), f"24c.2 явное предупреждение о недоступной модели: {text!r}"
        assert text.count("🎬 Готово к запуску") == 1, "24c.3 карточка подтверждения всё равно показана (не отказ целиком)"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.KLING3_ENABLED = _orig_kling


def test_block_24c2_seedance_disabled_shows_unavailable_text():
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_seedance = S.SEEDANCE_ENABLED
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    S.SEEDANCE_ENABLED = False
    try:
        update, context, message = make_webapp_update_context()
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "start_generation",
            "product": "video",
            "video_model": "seedance2",
            "description": "тест",
        }))
        assert applied is True, "24c2.1 обработчик не падает, когда видео-продукт целиком выключен"
        text = message.reply_text.await_args_list[0].args[0]
        assert text == S.video_unavailable_text(), f"24c2.2 честное «видео недоступно»: {text!r}"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.SEEDANCE_ENABLED = _orig_seedance


def test_block_24d_unknown_product_declines_gracefully():
    update, context, message = make_webapp_update_context()
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "sg",
        "pr": "studio",
        "p": "что угодно",
    }))
    assert applied is True, "24d.1 неизвестный (пока не поддержанный вообще) продукт — не падаем"
    text = message.reply_text.await_args_list[0].args[0]
    assert "не поддержан" in text.lower(), f"24d.2 честное сообщение вместо тихой генерации по неверным полям: {text!r}"


def test_block_24j_midjourney_flag_off_declines():
    update, context, message = make_webapp_update_context()
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "sg", "pr": "midjourney", "p": "девушка в кафе",
    }))
    assert applied is True, "24j.1 payload распознан"
    text = message.reply_text.await_args_list[0].args[0]
    assert "недоступна" in text.lower(), f"24j.2 честный отказ при выключенном флаге: {text!r}"


def test_block_24k_midjourney_full_payload_builds_state_and_card():
    _orig_flag = S.MIDJOURNEY_CONSTRUCTOR_ENABLED
    _orig_mj = S.MIDJOURNEY_ENABLED
    S.MIDJOURNEY_CONSTRUCTOR_ENABLED = True
    S.MIDJOURNEY_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "sg", "pr": "midjourney",
            "p": "девушка в кафе, плёночная фотография",
            "refs": ["https://i.ibb.co/mj/1.jpg"],
        }))
        assert applied is True, "24k.1 payload применён"
        state = context.user_data["state"]
        assert state.mj_prompt == "девушка в кафе, плёночная фотография", "24k.2 текст сохранён в mj_prompt"
        assert state.mj_reference == "https://i.ibb.co/mj/1.jpg", "24k.3 первый референс сохранён"
        text = message.reply_text.await_args_list[0].args[0]
        assert text.startswith("🎨 Готово к запуску"), f"24k.4 карточка подтверждения: {text!r}"
        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.text == "🚀 Сгенерировать" and btn.callback_data == "mj_generate", (
            f"24k.5 переиспользует существующий коллбэк сетки: {btn.text!r}/{btn.callback_data!r}"
        )
    finally:
        S.MIDJOURNEY_CONSTRUCTOR_ENABLED = _orig_flag
        S.MIDJOURNEY_ENABLED = _orig_mj


def test_block_24l_midjourney_empty_description_declines():
    _orig_flag = S.MIDJOURNEY_CONSTRUCTOR_ENABLED
    _orig_mj = S.MIDJOURNEY_ENABLED
    S.MIDJOURNEY_CONSTRUCTOR_ENABLED = True
    S.MIDJOURNEY_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {"action": "sg", "pr": "midjourney"}))
        text = message.reply_text.await_args_list[0].args[0]
        assert "описание" in text.lower(), f"24l.1 пустой промт — честный отказ, Midjourney требует текст: {text!r}"
    finally:
        S.MIDJOURNEY_CONSTRUCTOR_ENABLED = _orig_flag
        S.MIDJOURNEY_ENABLED = _orig_mj


def test_block_24m_avatar_flag_off_declines():
    update, context, message = make_webapp_update_context()
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "sg", "pr": "avatar", "at": "male", "refs": ["https://i.ibb.co/av/1.jpg"],
    }))
    assert applied is True, "24m.1 payload распознан"
    text = message.reply_text.await_args_list[0].args[0]
    assert "недоступна" in text.lower(), f"24m.2 честный отказ при выключенном флаге: {text!r}"


def test_block_24n_avatar_full_payload_builds_state_and_card():
    _orig = S.AVATAR_CONSTRUCTOR_ENABLED
    S.AVATAR_CONSTRUCTOR_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        refs = [f"https://i.ibb.co/av/{i}.jpg" for i in range(3)]
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "sg", "pr": "avatar", "at": "male", "refs": refs,
        }))
        assert applied is True, "24n.1 payload применён"
        state = context.user_data["state"]
        assert state.pending_avatar_kind == "male", "24n.2 тип аватара сохранён"
        assert state.avatar_photos == refs, f"24n.3 фото легли в те же поля, что и ручная загрузка: {state.avatar_photos}"
        assert state.generating_avatar is True, "24n.4 флаг режима аватара включён — handle_photo не спутает с видео"
        text = message.reply_text.await_args_list[0].args[0]
        assert text.startswith("🪄 Готово к запуску") and "мужской" in text, f"24n.5 карточка подтверждения: {text!r}"
        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.callback_data == "avatar_gen_start", "24n.6 переиспользует существующий коллбэк запуска"
        assert "3 фото" in btn.text, f"24n.7 счётчик фото в кнопке: {btn.text!r}"
    finally:
        S.AVATAR_CONSTRUCTOR_ENABLED = _orig


def test_block_24o_avatar_no_photos_declines():
    _orig = S.AVATAR_CONSTRUCTOR_ENABLED
    S.AVATAR_CONSTRUCTOR_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {"action": "sg", "pr": "avatar", "at": "female"}))
        text = message.reply_text.await_args_list[0].args[0]
        assert "фото" in text.lower(), f"24o.1 без фото — честный отказ: {text!r}"
    finally:
        S.AVATAR_CONSTRUCTOR_ENABLED = _orig


def test_block_24p_avatar_default_kind_when_invalid():
    _orig = S.AVATAR_CONSTRUCTOR_ENABLED
    S.AVATAR_CONSTRUCTOR_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "sg", "pr": "avatar", "at": "not_a_real_kind", "refs": ["https://i.ibb.co/av/x.jpg"],
        }))
        state = context.user_data["state"]
        assert state.pending_avatar_kind == "female", f"24p.1 неизвестный тип -> дефолт female, не крэш: {state.pending_avatar_kind}"
    finally:
        S.AVATAR_CONSTRUCTOR_ENABLED = _orig


def test_block_24e_no_description_and_no_refs_declines_with_reopen_button():
    _orig = S.VIDEO_CONSTRUCTOR_ENABLED
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "start_generation",
            "product": "video",
            "video_model": "seedance2",
        }))
        assert applied is True, "24e.1 пустой черновик — честный отказ, не пустая генерация"
        text = message.reply_text.await_args_list[0].args[0]
        assert "описание или хотя бы одно фото" in text, f"24e.2 понятная причина отказа: {text!r}"
        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        assert kb.inline_keyboard[0][0].web_app is not None, "24e.3 кнопка ведёт обратно в конструктор"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig


def test_block_24f_refs_capped_at_max_seedance_image_references():
    _orig = S.VIDEO_CONSTRUCTOR_ENABLED
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        many_refs = [f"https://i.ibb.co/many/{i}.jpg" for i in range(20)]
        asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "start_generation",
            "product": "video",
            "video_model": "seedance2",
            "description": "тест потолка",
            "refs": many_refs,
        }))
        state = context.user_data["state"]
        assert len(S.get_video_image_urls(state)) == S.MAX_SEEDANCE_IMAGE_REFERENCES, (
            f"24f.1 тот же потолок, что и у ручной загрузки: {len(S.get_video_image_urls(state))}"
        )
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig


def test_block_24g_video_entry_points_route_to_constructor_when_enabled():
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        update, context, message = make_webapp_update_context()
        update.message = message
        applied = asyncio.run(S.handle_menu_button(update, context, S.MENU_BTN_VIDEO))
        assert applied is True, "24g.1 кнопка меню распознана"
        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.web_app is not None, "24g.2 сразу кнопка вебаппа, не пикер модели"
        assert "tab=video_constructor" in btn.web_app.url, f"24g.3 URL открывает нужный экран: {btn.web_app.url}"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24h_video_entry_unchanged_when_flag_off():
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.VIDEO_CONSTRUCTOR_ENABLED = False
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        update, context, message = make_webapp_update_context()
        update.message = message
        asyncio.run(S.handle_menu_button(update, context, S.MENU_BTN_VIDEO))
        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn_texts = [b.text for row in kb.inline_keyboard for b in row]
        assert "🎬 Открыть конструктор" not in btn_texts, "24h.1 kill-switch выключен — старый пикер модели, без регрессий"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24h2_inline_video_entry_point_parity():
    # AGENT_NOTES-правило проекта: оба входа в видео (reply-кнопка и инлайн
    # button_handler) обязаны переключаться синхронно — historically был
    # источник регрессий, когда чинили только один из двух.
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        update, context, query = make_update_context("video")
        user = types.SimpleNamespace(id=778, username="test")
        asyncio.run(S._cb_video_open(update, context, query, user))
        kb = query.message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.web_app is not None, "24h2.1 инлайн-вход тоже ведёт в конструктор, не в старый пикер"
        assert "tab=video_constructor" in btn.web_app.url, f"24h2.2 URL тот же, что у reply-входа: {btn.web_app.url}"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24h3_persistent_menu_video_button_uses_snake_case_tab():
    # get_video_constructor_webapp_url — персональный URL, зашитый в reply-кнопку
    # «🎬 Видео для Reels» (persistent_menu_kb). Реальный constructor.js
    # (репо вебаппа) сверяет query-параметр `tab` дословно со строкой
    # "video_constructor" (snake_case) — "videoConstructor" (camelCase) там
    # только внутреннее имя экрана для switchTab(), не значение параметра.
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        kb = S.persistent_menu_kb(9714)
        video_btn = [b for row in kb.keyboard for b in row if b.text == S.MENU_BTN_VIDEO][0]
        assert video_btn.web_app is not None, "24h3.1 флаг включён — прямая web_app-кнопка"
        assert "tab=video_constructor" in video_btn.web_app.url, (
            f"24h3.2 snake_case tab, дословно как ждёт constructor.js: {video_btn.web_app.url}"
        )
        assert "tab=videoConstructor" not in video_btn.web_app.url, (
            f"24h3.3 НЕ camelCase (то внутреннее имя экрана, не query-параметр): {video_btn.web_app.url}"
        )
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24i_cfg_appended_to_webapp_url_only_when_enabled():
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        S.VIDEO_CONSTRUCTOR_ENABLED = False
        url_off = S.get_prompt_webapp_url(1)
        assert "&cfg=" not in url_off, "24i.1 флаг выключен -> не раздуваем URL всем юзерам библиотеки"

        S.VIDEO_CONSTRUCTOR_ENABLED = True
        url_on = S.get_prompt_webapp_url(1)
        assert "&cfg=" in url_on, "24i.2 флаг включён -> конфигурация моделей/цен проброшена"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24i2_config_shape_matches_frontend_contract():
    # Схема СВЕРЕНА с реальным constructor.js в репо вебаппа (parseCfgFromUrl/
    # FALLBACK_CFG, vcModelFromCfgEntry) — `video_models` (не `models`), без
    # обёртки `default_model` (дефолт = первая модель списка, всегда seedance2,
    # т.к. он единственный без фичефлага), поля `code`/`aspects`/`modes`/
    # `prices` (не `id`/`formats`/`quality`), prices вложены по РЕАЛЬНОМУ
    # значению режима ("480p"/"720p"/"1080p"), а не по "pro"/"fast". Wan 2.7 —
    # обычная дискретная таблица длительностей/цен, как у всех моделей (не
    # {"custom":[min,max]}/{"per_second": N} — этот вариант ушёл из реального
    # webapp контракта, hasQualityToggle там смотрит на наличие "480p" в modes).
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
        assert isinstance(cfg, dict) and list(cfg.keys()) == ["video_models"], (
            f"24i2.1 корневой ключ — ровно video_models, без default_model: {cfg.keys()}"
        )
        models = cfg["video_models"]
        assert isinstance(models, list) and models, "24i2.2 video_models — непустой список"
        assert models[0]["code"] == "seedance2", "24i2.3 дефолт конструктора = первая модель списка = seedance2"
        codes = [m["code"] for m in models]
        assert set(codes) == {
            "seedance2", "seedance2_fast", "kling3", "veo31", "wan27", "gemini_omni", "seedance25",
        }, f"24i2.4 все включённые модели присутствуют: {codes}"

        by_code = {m["code"]: m for m in models}

        sd2 = by_code["seedance2"]
        assert sd2["modes"] == ["480p", "720p", "1080p"], f"24i2.5 seedance2 — все три режима: {sd2['modes']}"
        assert set(sd2["aspects"]) == {"16:9", "9:16", "1:1", "4:3"}, f"24i2.6 seedance2 форматы: {sd2['aspects']}"
        assert sd2["face_grid"] is True, "24i2.7 seedance2 поддерживает детектор лиц"
        assert set(sd2["prices"].keys()) == {"480p", "720p", "1080p"}, (
            f"24i2.8 prices вложены по реальному режиму, не pro/fast: {sd2['prices'].keys()}"
        )
        assert "label" in sd2 and "blurb" in sd2 and "durations" in sd2, f"24i2.9 обязательные поля: {sd2}"

        wan = by_code["wan27"]
        assert isinstance(wan["durations"], list) and wan["durations"], (
            f"24i2.10 wan27 — обычная дискретная таблица длительностей, не {{'custom':...}}: {wan['durations']}"
        )
        assert set(wan["prices"].keys()) == set(str(m) for m in (wan["modes"] or ["default"])), (
            f"24i2.11 wan27 prices по режиму/duration, не per_second: {wan['prices']}"
        )

        veo = by_code["veo31"]
        assert set(veo["aspects"]) == {"16:9", "9:16"}, f"24i2.12 veo31 без квадрата/4:3: {veo['aspects']}"
    finally:
        S.SEEDANCE_FAST_ENABLED = _flags["SEEDANCE_FAST_ENABLED"]
        S.KLING3_ENABLED = _flags["KLING3_ENABLED"]
        S.VEO31_ENABLED = _flags["VEO31_ENABLED"]
        S.WAN27_ENABLED = _flags["WAN27_ENABLED"]
        S.GEMINI_OMNI_ENABLED = _flags["GEMINI_OMNI_ENABLED"]
        S.SEEDANCE25_ENABLED = _flags["SEEDANCE25_ENABLED"]


def test_block_24j_midjourney_entry_routes_to_constructor_when_enabled():
    _orig_flag = S.MIDJOURNEY_CONSTRUCTOR_ENABLED
    _orig_mj = S.MIDJOURNEY_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.MIDJOURNEY_CONSTRUCTOR_ENABLED = True
    S.MIDJOURNEY_ENABLED = True
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        update, context, query = make_update_context("menu_midjourney")
        user = types.SimpleNamespace(id=901, username="test")
        asyncio.run(S._cb_menu_midjourney(update, context, query, user))
        kb = query.message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.web_app is not None, "24j.1 сразу кнопка вебаппа, не текстовый флоу"
        assert "tab=midjourney_constructor" in btn.web_app.url, f"24j.2 URL нужного экрана: {btn.web_app.url}"
    finally:
        S.MIDJOURNEY_CONSTRUCTOR_ENABLED = _orig_flag
        S.MIDJOURNEY_ENABLED = _orig_mj
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24k_midjourney_entry_unchanged_when_flag_off():
    _orig_flag = S.MIDJOURNEY_CONSTRUCTOR_ENABLED
    _orig_mj = S.MIDJOURNEY_ENABLED
    S.MIDJOURNEY_CONSTRUCTOR_ENABLED = False
    S.MIDJOURNEY_ENABLED = True
    try:
        update, context, query = make_update_context("menu_midjourney")
        user = types.SimpleNamespace(id=902, username="test")
        asyncio.run(S._cb_menu_midjourney(update, context, query, user))
        text = query.message.reply_text.await_args_list[0].args[0]
        assert "Опиши, что хочешь сгенерировать, одним текстовым сообщением" in text, (
            f"24k.1 kill-switch выключен — старый текстовый флоу без регрессий: {text!r}"
        )
    finally:
        S.MIDJOURNEY_CONSTRUCTOR_ENABLED = _orig_flag
        S.MIDJOURNEY_ENABLED = _orig_mj


def test_block_24l_avatar_entry_routes_to_constructor_when_enabled():
    _orig_flag = S.AVATAR_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.AVATAR_CONSTRUCTOR_ENABLED = True
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        update, context, query = make_update_context("avatar_gen_refsheet")
        user = types.SimpleNamespace(id=903, username="test")
        asyncio.run(S._cb_avatar_gen_refsheet(update, context, query, user))
        kb = query.message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.web_app is not None, "24l.1 сразу кнопка вебаппа, не сбор фото текстом"
        assert "tab=avatar_constructor" in btn.web_app.url, f"24l.2 URL нужного экрана: {btn.web_app.url}"
    finally:
        S.AVATAR_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24m_avatar_entry_unchanged_when_flag_off():
    _orig_flag = S.AVATAR_CONSTRUCTOR_ENABLED
    S.AVATAR_CONSTRUCTOR_ENABLED = False
    try:
        update, context, query = make_update_context("avatar_gen_refsheet")
        user = types.SimpleNamespace(id=904, username="test")
        asyncio.run(S._cb_avatar_gen_refsheet(update, context, query, user))
        text = query.message.reply_text.await_args_list[0].args[0]
        assert "Пришли 3–6 фото" in text, f"24m.1 kill-switch выключен — старый сбор фото без регрессий: {text!r}"
    finally:
        S.AVATAR_CONSTRUCTOR_ENABLED = _orig_flag


def test_block_24n2_photo_flag_off_declines():
    update, context, message = make_webapp_update_context()
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "sg", "pr": "photo", "p": "кот в космосе",
    }))
    assert applied is True, "24n2.1 payload распознан"
    text = message.reply_text.await_args_list[0].args[0]
    assert "недоступна" in text.lower(), f"24n2.2 честный отказ при выключенном флаге: {text!r}"


def test_block_24o2_photo_full_payload_builds_state_and_card():
    _orig = S.PHOTO_CONSTRUCTOR_ENABLED
    S.PHOTO_CONSTRUCTOR_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        refs = [f"https://i.ibb.co/photo/{i}.jpg" for i in range(2)]
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "sg", "pr": "photo", "p": "кот-космонавт, кинематографично", "refs": refs,
        }))
        assert applied is True, "24o2.1 payload применён"
        state = context.user_data["state"]
        assert state.prompt == "кот-космонавт, кинематографично", "24o2.2 описание сохранено"
        assert state.references == refs, f"24o2.3 фото легли в те же поля, что и ручная загрузка: {state.references}"
        assert state.image_model == "gemini", "24o2.4 дефолт модели — gemini (gpt5 не запрошен)"
        text = message.reply_text.await_args_list[0].args[0]
        assert text.startswith("✨ Готово к запуску"), f"24o2.5 карточка подтверждения: {text!r}"
        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.text == "🚀 Запустить генерацию" and btn.callback_data == "generate", (
            f"24o2.6 переиспользует существующий коллбэк запуска: {btn.text!r}/{btn.callback_data!r}"
        )
    finally:
        S.PHOTO_CONSTRUCTOR_ENABLED = _orig


def test_block_24p2_photo_gpt5_model_requires_flag():
    _orig = S.PHOTO_CONSTRUCTOR_ENABLED
    _orig_gpt5 = S.GPT5_IMAGE_ENABLED
    S.PHOTO_CONSTRUCTOR_ENABLED = True
    S.GPT5_IMAGE_ENABLED = False
    try:
        update, context, message = make_webapp_update_context()
        asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "sg", "pr": "photo", "p": "тест", "im": "gpt5",
        }))
        state = context.user_data["state"]
        assert state.image_model == "gemini", (
            f"24p2.1 gpt5 запрошен, но выключен флагом -> откат на gemini, не крэш: {state.image_model}"
        )
    finally:
        S.PHOTO_CONSTRUCTOR_ENABLED = _orig
        S.GPT5_IMAGE_ENABLED = _orig_gpt5


def test_block_24q2_photo_empty_description_declines():
    _orig = S.PHOTO_CONSTRUCTOR_ENABLED
    S.PHOTO_CONSTRUCTOR_ENABLED = True
    try:
        update, context, message = make_webapp_update_context()
        asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {"action": "sg", "pr": "photo"}))
        text = message.reply_text.await_args_list[0].args[0]
        assert "описание" in text.lower(), f"24q2.1 пустое описание — честный отказ: {text!r}"
    finally:
        S.PHOTO_CONSTRUCTOR_ENABLED = _orig


def test_block_24r2_photo_entry_points_route_to_constructor_when_enabled():
    _orig_flag = S.PHOTO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.PHOTO_CONSTRUCTOR_ENABLED = True
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        # Reply-вход
        update, context, message = make_webapp_update_context()
        update.message = message
        applied = asyncio.run(S.handle_menu_button(update, context, S.MENU_BTN_PHOTO))
        assert applied is True, "24r2.1 кнопка меню распознана"
        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.web_app is not None and "tab=photo_constructor" in btn.web_app.url, (
            f"24r2.2 reply-вход ведёт в конструктор: {btn.web_app.url if btn.web_app else None}"
        )

        # Инлайн-вход (photo_menu_kb)
        kb2 = S.photo_menu_kb(905)
        btn2 = kb2.inline_keyboard[0][0]
        assert btn2.web_app is not None and "tab=photo_constructor" in btn2.web_app.url, (
            f"24r2.3 инлайн-вход тоже ведёт в конструктор (оба входа синхронно)"
        )
    finally:
        S.PHOTO_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24s2_photo_entry_unchanged_when_flag_off():
    _orig_flag = S.PHOTO_CONSTRUCTOR_ENABLED
    S.PHOTO_CONSTRUCTOR_ENABLED = False
    try:
        kb = S.photo_menu_kb(906)
        btn = kb.inline_keyboard[0][0]
        assert btn.callback_data == "generate" and btn.web_app is None, (
            "24s2.1 kill-switch выключен — старый коллбэк без регрессий"
        )
    finally:
        S.PHOTO_CONSTRUCTOR_ENABLED = _orig_flag


def test_block_24t2_features_payload_reflects_all_four_flags():
    # Экран «Создать» (единая навигация, docs/specs/2026-08-13_webapp_generation_hub_navigation_full.md)
    # скрывает плитки продуктов по этому полю — независимо от &cfg=
    # (который несёт только тяжёлую таблицу цен видео и гейтится отдельно).
    _orig = (
        S.VIDEO_CONSTRUCTOR_ENABLED, S.MIDJOURNEY_CONSTRUCTOR_ENABLED,
        S.AVATAR_CONSTRUCTOR_ENABLED, S.PHOTO_CONSTRUCTOR_ENABLED, S.PROMPT_WEBAPP_URL,
    )
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        S.VIDEO_CONSTRUCTOR_ENABLED = False
        S.MIDJOURNEY_CONSTRUCTOR_ENABLED = True
        S.AVATAR_CONSTRUCTOR_ENABLED = False
        S.PHOTO_CONSTRUCTOR_ENABLED = True
        url = S.get_prompt_webapp_url(1)
        assert "&features=" in url, f"24t2.1 features всегда проброшены (не гейтятся видео-флагом): {url}"
        import base64 as b64, json as js
        raw = url.split("&features=", 1)[1].split("&", 1)[0]
        decoded = js.loads(b64.urlsafe_b64decode(raw.encode()).decode())
        assert decoded == {"video": False, "midjourney": True, "avatar": False, "photo": True}, (
            f"24t2.2 значения соответствуют реальным флагам: {decoded}"
        )
    finally:
        (S.VIDEO_CONSTRUCTOR_ENABLED, S.MIDJOURNEY_CONSTRUCTOR_ENABLED,
         S.AVATAR_CONSTRUCTOR_ENABLED, S.PHOTO_CONSTRUCTOR_ENABLED, S.PROMPT_WEBAPP_URL) = _orig


def _decode_prefill(url):
    import base64 as b64, json as js
    raw = url.split("&prefill=", 1)[1].split("&", 1)[0]
    return js.loads(b64.urlsafe_b64decode(raw.encode()).decode())


def test_block_24u_build_generation_prefill_roundtrips_all_four_products():
    st = S.UserState()
    st.video_model = "seedance2"
    st.video_aspect_ratio = "9:16"
    st.video_mode = "480p"
    st.video_duration = 10
    st.video_face_grid = True
    st.video_prompt = "кино"
    S.set_video_image_urls(st, ["https://i.ibb.co/v/1.jpg"])
    video_pf = S.build_generation_prefill("video", st)
    assert video_pf["video_model"] == "seedance2" and video_pf["aspect"] == "9:16"
    assert video_pf["quality"] == "fast", f"24u.1 480p -> quality fast: {video_pf}"
    assert video_pf["duration"] == 10 and video_pf["face_grid"] is True
    assert video_pf["description"] == "кино" and video_pf["refs"] == ["https://i.ibb.co/v/1.jpg"]

    st2 = S.UserState()
    st2.mj_prompt = "девушка"
    st2.mj_reference = "https://i.ibb.co/m/1.jpg"
    mj_pf = S.build_generation_prefill("midjourney", st2)
    assert mj_pf == {"product": "midjourney", "description": "девушка", "refs": ["https://i.ibb.co/m/1.jpg"]}

    st3 = S.UserState()
    st3.pending_avatar_kind = "child"
    st3.avatar_photos = ["https://i.ibb.co/a/1.jpg"]
    av_pf = S.build_generation_prefill("avatar", st3)
    assert av_pf == {"product": "avatar", "avatar_type": "child", "refs": ["https://i.ibb.co/a/1.jpg"]}

    st4 = S.UserState()
    st4.prompt = "кот"
    st4.references = ["https://i.ibb.co/p/1.jpg"]
    st4.image_model = "gemini"
    ph_pf = S.build_generation_prefill("photo", st4)
    assert ph_pf == {"product": "photo", "description": "кот", "refs": ["https://i.ibb.co/p/1.jpg"], "image_model": "gemini"}


def test_block_24v_library_video_style_redirects_to_constructor_with_prefill():
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    _orig_url = S.PROMPT_WEBAPP_URL
    S.VIDEO_CONSTRUCTOR_ENABLED = True
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        update, context, message = make_webapp_update_context()
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "set_video_prompt",
            "title": "Кино-стиль",
            "prompt": "cinematic dance video",
        }))
        assert applied is True, "24v.1 payload применён"
        assert len(message.reply_text.await_args_list) == 1, (
            "24v.2 ОДНО сообщение с кнопкой конструктора, не старая двухсообщенческая чат-панель"
        )
        text = message.reply_text.await_args_list[0].args[0]
        assert "Кино-стиль" in text, f"24v.3 название стиля в сообщении: {text!r}"
        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btn = kb.inline_keyboard[0][0]
        assert btn.web_app is not None and "tab=video_constructor" in btn.web_app.url, (
            f"24v.4 ведёт в конструктор видео: {btn.web_app.url if btn.web_app else None}"
        )
        prefill = _decode_prefill(btn.web_app.url)
        assert prefill["description"] == "cinematic dance video", (
            f"24v.5 промт стиля предзаполнен в конструкторе: {prefill}"
        )
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_24w_library_video_style_unchanged_when_flag_off():
    _orig_flag = S.VIDEO_CONSTRUCTOR_ENABLED
    S.VIDEO_CONSTRUCTOR_ENABLED = False
    try:
        update, context, message = make_webapp_update_context()
        asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "set_video_prompt",
            "title": "Кино-стиль",
            "prompt": "cinematic dance video",
        }))
        assert len(message.reply_text.await_args_list) == 2, (
            "24w.1 kill-switch выключен — старая двухсообщенческая чат-панель без регрессий"
        )
        second_kb = message.reply_text.await_args_list[1].kwargs.get("reply_markup")
        assert second_kb is not None and any(
            "Запустить видео" in b.text for row in second_kb.inline_keyboard for b in row
        ), "24w.2 второе сообщение — обычная video_kb-панель"
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED = _orig_flag


def test_block_24x_library_entry_points_get_explicit_tab_library():
    # Миграция дефолта Mini App на «Создать» (docs/specs/2026-08-13_webapp_
    # generation_hub_navigation_full.md, 1.4): get_prompt_webapp_url() без
    # &tab= сегодня открывает каталог Библиотеки неявным дефолтом, но Full
    # переключает дефолт на «Создать» — значит КАЖДЫЙ существующий вход
    # «Открыть библиотеку»/«Библиотека стилей» обязан получить явный
    # &tab=library, иначе кнопка перестанет открывать то, что называет.
    _orig_url = S.PROMPT_WEBAPP_URL
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        uid = 9601

        # webapp_open_kb / webapp_inline_kb — буквально названы в спеке
        # («📚 Открыть библиотеку», reply и inline).
        open_kb = S.webapp_open_kb(uid)
        open_btn = open_kb.keyboard[0][0]
        assert open_btn.web_app is not None and "&tab=library" in open_btn.web_app.url, (
            f"24x.1 webapp_open_kb (reply) открывает каталог: {open_btn.web_app.url if open_btn.web_app else None}"
        )

        inline_kb = S.webapp_inline_kb(uid)
        inline_btn = inline_kb.inline_keyboard[0][0]
        assert inline_btn.web_app is not None and "&tab=library" in inline_btn.web_app.url, (
            f"24x.2 webapp_inline_kb (inline) открывает каталог: {inline_btn.web_app.url if inline_btn.web_app else None}"
        )

        # persistent_menu_kb — постоянная reply-кнопка «📚 Библиотека стилей».
        menu_kb = S.persistent_menu_kb(uid)
        lib_btn = [b for row in menu_kb.keyboard for b in row if b.text == S.MENU_BTN_LIBRARY][0]
        assert lib_btn.web_app is not None and "&tab=library" in lib_btn.web_app.url, (
            f"24x.3 persistent_menu_kb библиотека: {lib_btn.web_app.url if lib_btn.web_app else None}"
        )

        # result_actions_kb — «📚 Библиотека стилей» под результатом генерации.
        result_kb = S.result_actions_kb(uid)
        result_btn = [b for row in result_kb.inline_keyboard for b in row if b.text == "📚 Библиотека стилей"][0]
        assert result_btn.web_app is not None and "&tab=library" in result_btn.web_app.url, (
            f"24x.4 result_actions_kb библиотека: {result_btn.web_app.url if result_btn.web_app else None}"
        )

        # broadcast_library_kb — рассылки.
        broadcast_kb = S.broadcast_library_kb(uid)
        broadcast_btn = broadcast_kb.inline_keyboard[0][0]
        assert broadcast_btn.web_app is not None and "&tab=library" in broadcast_btn.web_app.url, (
            f"24x.5 broadcast_library_kb: {broadcast_btn.web_app.url if broadcast_btn.web_app else None}"
        )

        # video_constructor_kb/get_video_constructor_webapp_url и
        # constructor_prefill_url НЕ трогаются — они уже несут собственный
        # явный &tab=video_constructor/&tab={tab}, миграция их не касается.
        video_url = S.get_video_constructor_webapp_url(uid)
        assert "&tab=video_constructor" in video_url and "&tab=library" not in video_url, (
            f"24x.6 конструктор видео не получает library вместо своего таба: {video_url}"
        )
    finally:
        S.PROMPT_WEBAPP_URL = _orig_url
