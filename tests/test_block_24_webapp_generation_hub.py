# -*- coding: utf-8 -*-
"""Блок 24: хаб генерации в вебаппе, MVP — экран «Конструктор» для видео
(docs/specs/2026-08-13_webapp_generation_hub.md). Вебапп собирает все
настройки одним экраном и шлёт один payload `start_generation`/`sg` —
бот резолвит его в UserState (те же поля, что заполняет video_kb) и
показывает карточку подтверждения с кнопкой video_start. Сам запуск/
списание/очередь/доставка результата не меняются — это тот же
_cb_video_start/run_seedance, что и всегда."""
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
        assert state.video_mode == "720p", "24b.5 quality=pro -> 720p"
        assert state.video_duration == 10, "24b.6 длительность сохранена"
        assert state.video_face_grid is True, "24b.7 детектор лиц сохранён"
        assert state.video_prompt == "девушка на закате, кино", "24b.8 описание сохранено"
        assert S.get_video_image_urls(state) == refs, f"24b.9 фото легли в те же поля, что и ручная загрузка: {state.animation_source_urls}"

        text = message.reply_text.await_args_list[0].args[0]
        assert text.startswith("🎬 Готово к запуску"), f"24b.10 заголовок карточки подтверждения: {text!r}"
        assert "Seedance 2" in text and "9:16" in text and "10 сек" in text, f"24b.11 параметры видны в карточке: {text!r}"

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
