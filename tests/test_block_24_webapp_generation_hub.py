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
    S.VIDEO_CONSTRUCTOR_ENABLED = True
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
        restart_btn = rows[1][0]
        assert restart_btn.text == "🔁 Начать заново", "24b.14 кнопка сброса — не «Изменить» (нет префилла в MVP)"
        assert restart_btn.web_app is not None, "24b.15 сброс снова открывает конструктор в вебаппе"
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
