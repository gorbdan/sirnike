# -*- coding: utf-8 -*-
"""Блок 7: кнопка «Оживить» (callback)."""
import asyncio

from test_helpers import S, make_update_context


def test_block_07_animate_last():
    # 7.1 нет последней генерации
    update, context, query = make_update_context("animate_last", user_id=701)
    S.last_generated_image_url.pop(701, None)
    asyncio.run(S.button_handler(update, context))
    msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("Не нашла" in m for m in msgs), f"7.1 без генерации — мягкое сообщение: {msgs}"

    # 7.2 есть генерация -> буфер заполняется, меню открывается
    update, context, query = make_update_context("animate_last", user_id=702)
    S.last_generated_image_url[702] = "https://example.com/gen.png"
    asyncio.run(S.button_handler(update, context))
    st7 = context.user_data.get("state")
    assert st7 and st7.animation_source_urls == ["https://example.com/gen.png"], (
        f"7.2 картинка попала в видео-буфер: {getattr(st7, 'animation_source_urls', None)}"
    )
    assert st7 and st7.video_session_active is True, "7.3 видео-сессия активирована"
    msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("Модель:" in m for m in msgs), f"7.4 показано видео-меню (статус-текст): {str(msgs)[:200]}"

    # 7.5 стейлый __img__ ref
    update, context, query = make_update_context("animate_last", user_id=703)
    S.last_generated_image_url[703] = "__img_deadbeef00__"
    asyncio.run(S.button_handler(update, context))
    msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("Не нашла" in m for m in msgs), f"7.5 стейлый __img__ -> мягкое сообщение: {str(msgs)[:200]}"

    # 7.6 переключение видео-модели через callback
    update, context, query = make_update_context("video_model_kling3", user_id=704)
    asyncio.run(S.button_handler(update, context))
    st8 = context.user_data.get("state")
    assert st8 and st8.video_model == "kling3", "7.6 callback video_model_kling3 ставит модель"

    update, context, query = make_update_context("video_model_veo31", user_id=705)
    context.user_data["state"] = S.UserState(video_aspect_ratio="1:1")
    asyncio.run(S.button_handler(update, context))
    st9 = context.user_data["state"]
    assert st9.video_model == "veo31" and st9.video_aspect_ratio == "16:9", (
        f"7.7 veo31 сбрасывает аспект 1:1 -> 16:9: model={st9.video_model} aspect={st9.video_aspect_ratio}"
    )

    # 7.7b kling3: выбор 1080p через video_mode_ callback теперь применяется
    update, context, query = make_update_context("video_model_kling3", user_id=7041)
    asyncio.run(S.button_handler(update, context))
    update.callback_query.data = "video_mode_1080"
    asyncio.run(S.button_handler(update, context))
    st8b = context.user_data["state"]
    assert st8b.video_model == "kling3" and st8b.video_mode == "1080p", (
        f"7.7b kling3: video_mode_1080 переключает режим: mode={st8b.video_mode}"
    )

    # 7.7c 4:3 принимается как валидный аспект
    update, context, query = make_update_context("video_aspect_4x3", user_id=7042)
    context.user_data["state"] = S.UserState(video_model="seedance2")
    asyncio.run(S.button_handler(update, context))
    st8c = context.user_data["state"]
    assert st8c.video_aspect_ratio == "4:3", f"7.7c video_aspect_4x3 ставит 4:3: aspect={st8c.video_aspect_ratio}"

    # 7.7d ТЗ video_panel_declutter: выбор модели ставит video_model_picked;
    # повторный вход в «видео» пропускает пикер (сразу полная панель);
    # «Сменить модель» возвращает пикер; reset переносит выбор.
    update, context, query = make_update_context("video_model_kling3", user_id=7043)
    asyncio.run(S.button_handler(update, context))
    st8d = context.user_data["state"]
    assert st8d.video_model_picked is True, "7.7d выбор модели ставит video_model_picked"

    update.callback_query.data = "video"
    asyncio.run(S.button_handler(update, context))
    _texts8d = [c.args[0] for c in update.callback_query.message.reply_text.await_args_list]
    assert any("Модель:" in t for t in _texts8d) and not any("Выбери модель" in t for t in _texts8d), (
        f"7.7e повторный вход: пикер пропущен, сразу статус-панель: {_texts8d}"
    )

    update.callback_query.data = "video_change_model"
    asyncio.run(S.button_handler(update, context))
    _edit8d = update.callback_query.message.edit_text.await_args_list
    assert any("Выбери модель" in (c.args[0] if c.args else c.kwargs.get("text", "")) for c in _edit8d), (
        f"7.7f «Сменить модель» рисует пикер тем же сообщением: {_edit8d}"
    )

    update.callback_query.data = "reset"
    asyncio.run(S.button_handler(update, context))
    st8r = context.user_data["state"]
    assert st8r.video_model == "kling3" and st8r.video_model_picked is True, (
        f"7.7g reset переносит video_model и video_model_picked: model={st8r.video_model} picked={st8r.video_model_picked}"
    )

    # 7.8 выбор модели картинок через callback
    update, context, query = make_update_context("image_model_set_gpt5", user_id=706)
    asyncio.run(S.button_handler(update, context))
    st10 = context.user_data.get("state")
    assert st10 and st10.image_model == "gpt5", "7.8 image_model_set_gpt5 ставит gpt5"

    update, context, query = make_update_context("image_model_menu", user_id=707)
    asyncio.run(S.button_handler(update, context))
    msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("Модель генерации картинок" in m for m in msgs), (
        f"7.9 image_model_menu показывает меню: {str(msgs)[:200]}"
    )
