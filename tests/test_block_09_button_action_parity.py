# -*- coding: utf-8 -*-
"""Блок 9: кнопка есть ⇔ действие возможно (фиксы 2, 3, 4) — улучшить фото /
аватар / видео-модели без жаргона."""
import asyncio
import base64
import types

from test_helpers import S, make_update_context, make_text_update


def test_block_09_button_action_parity():
    S.init_db()  # handle_text вызывает create_user_if_not_exists — нужны таблицы

    # 9.1 текст в режиме «Улучшить фото» — не перезаписывает промт молча
    st_enh = S.UserState()
    st_enh.prompt = S.ENHANCE_PHOTO_PROMPT
    update, context, message = make_text_update("сделай поярче", user_id=901, state=st_enh)
    asyncio.run(S.handle_text(update, context))
    msgs = [c.args[0] for c in message.reply_text.await_args_list]
    assert context.user_data["state"].prompt == S.ENHANCE_PHOTO_PROMPT, (
        f"9.1 текст в enhance-режиме не меняет state.prompt: {context.user_data['state'].prompt}"
    )
    assert any("жду фото" in m for m in msgs), f"9.2 текст в enhance-режиме предлагает выбор, не молчит: {msgs}"
    assert context.user_data.get("enhance_pending_text") == "сделай поярче", (
        "9.3 pending text сохранён для enhance_use_pending_text"
    )

    # 9.4 enhance_use_pending_text превращает сохранённый текст в обычный промт
    update, context, query = make_update_context("enhance_use_pending_text", user_id=902)
    context.user_data["state"] = S.UserState(prompt=S.ENHANCE_PHOTO_PROMPT)
    context.user_data["enhance_pending_text"] = "кот в космосе"
    asyncio.run(S.button_handler(update, context))
    st_after = context.user_data["state"]
    assert st_after.prompt == "кот в космосе", f"9.4 промт стал обычным описанием: {st_after.prompt}"
    assert "enhance_pending_text" not in context.user_data, "9.5 pending text очищен после использования"

    # 9.6 avatar_gen_refsheet включает приём фото сразу, без выбора типа
    update, context, query = make_update_context("avatar_gen_refsheet", user_id=903)
    asyncio.run(S.button_handler(update, context))
    st_av = context.user_data["state"]
    assert st_av.generating_avatar is True, "9.6 generating_avatar включён сразу"
    assert st_av.pending_avatar_kind == "", "9.7 pending_avatar_kind ещё не выбран"

    # 9.8 avatar_gen_start без выбранного типа — alert, генерация не стартует
    update, context, query = make_update_context("avatar_gen_start", user_id=904)
    st_av2 = S.UserState(generating_avatar=True)
    st_av2.avatar_photos = ["https://example.com/face.png"]
    context.user_data["state"] = st_av2
    asyncio.run(S.button_handler(update, context))
    assert any("тип аватара" in str(c) for c in query.answer.await_args_list), (
        f"9.9 без типа — alert «выбери тип аватара»: {query.answer.await_args_list}"
    )

    # 9.10 выбор типа не стирает уже загруженные фото
    update, context, query = make_update_context("avatar_gen_kind_male", user_id=905)
    st_av3 = S.UserState(generating_avatar=True)
    st_av3.avatar_photos = ["https://example.com/a.png", "https://example.com/b.png"]
    context.user_data["state"] = st_av3
    asyncio.run(S.button_handler(update, context))
    st_av3_after = context.user_data["state"]
    assert st_av3_after.pending_avatar_kind == "male", "9.10 тип выбран"
    assert len(st_av3_after.avatar_photos) == 2, f"9.11 фото не стёрлись при выборе типа: {st_av3_after.avatar_photos}"

    # 9.12 видео-панель: пояснение модели вместо жаргона «для Seedance»
    st_blurb = S.UserState(video_model="seedance2")
    blurb_text = S.video_status_text(st_blurb)
    assert "максимум качества" in blurb_text, f"9.12 статус видео содержит пояснение модели: {blurb_text[:200]}"
    update, context, query = make_update_context("video_set_image", user_id=906)
    asyncio.run(S.button_handler(update, context))
    msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert not any("для Seedance" in m for m in msgs), f"9.13 без жаргона «для Seedance»: {msgs}"

    # 9.14 via_bot-заглушка (answerWebAppQuery, docs/specs/2026-07-17_via_bot_message_leak.md)
    # не затирает уже выбранный стиль в state.prompt
    st_leak = S.UserState(prompt="реальный промт выбранного стиля")
    update, context, message = make_text_update(
        "📚 Стиль подобран — жми ниже 👇", user_id=907, state=st_leak,
    )
    context.bot.id = 999999
    message.via_bot = types.SimpleNamespace(id=999999)
    asyncio.run(S.handle_text(update, context))
    assert context.user_data["state"].prompt == "реальный промт выбранного стиля", (
        f"9.14 via_bot-заглушка не трогает state.prompt: {context.user_data['state'].prompt}"
    )
    assert message.reply_text.await_args_list == [], (
        f"9.15 via_bot-заглушка не шлёт ответных сообщений: {message.reply_text.await_args_list}"
    )

    # 9.16 обычный текст от юзера (via_bot=None) по-прежнему работает как раньше
    st_normal = S.UserState()
    update, context, message = make_text_update("кот в шляпе", user_id=908, state=st_normal)
    context.bot.id = 999999
    message.via_bot = None
    asyncio.run(S.handle_text(update, context))
    assert context.user_data["state"].prompt == "кот в шляпе", (
        f"9.16 обычный текст всё ещё сохраняется в state.prompt: {context.user_data['state'].prompt}"
    )

    # 9.17 pl_use_ на inline-сообщении (answerWebAppQuery, query.message=None) —
    # docs/specs/2026-07-15_webapp_inline_1tap.md: Bot API гарантирует ровно одно
    # из полей message/inline_message_id у callback_query. Раньше query.message.
    # reply_text() падал AttributeError молча (state успевал выставиться, юзер
    # не видел подтверждения) — живой баг 2026-07-17.
    update, context, query = make_update_context("pl_use_0_0", user_id=909)
    query.message = None
    asyncio.run(S.button_handler(update, context))
    st917 = context.user_data.get("state")
    assert isinstance(st917, S.UserState) and bool(st917.prompt), (
        f"9.17 pl_use_ на inline-сообщении не падает и выставляет state.prompt: {getattr(st917, 'prompt', None)}"
    )
    assert context.bot.send_message.await_args_list != [], (
        f"9.18 pl_use_ на inline-сообщении шлёт подтверждение через bot.send_message: {context.bot.send_message.await_args_list}"
    )

    # 9.19 pl_usen_ — «свои пожелания» из инлайн-1-тапа (base64url в callback_data,
    # docs/specs/2026-07-17_inline_note_passthrough.md)
    _note = "каре, блонд"
    _enc = base64.urlsafe_b64encode(_note.encode("utf-8")).decode("ascii").rstrip("=")
    update, context, query = make_update_context(f"pl_usen_0_0_{_enc}", user_id=910)
    asyncio.run(S.button_handler(update, context))
    st919 = context.user_data.get("state")
    assert isinstance(st919, S.UserState) and _note in st919.prompt, (
        f"9.19 pl_usen_ дописывает note в state.prompt: {getattr(st919, 'prompt', None)}"
    )
    sent_texts = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any(_note in t and "Учла твои пожелания" in t for t in sent_texts), (
        f"9.20 pl_usen_ показывает «Учла твои пожелания» вместо статичного описания: {sent_texts}"
    )

    # 9.21 apply_user_note_override — усиленный override вместо слабой приписки
    # (docs/specs/2026-07-17_note_override_weak.md: «follow this instead of the
    # generic description above» проигрывала плотному дефолтному описанию образа)
    _base = "Soft glam makeup: warm bronze eyeshadow, nude-pink lips."
    _overridden = S.apply_user_note_override(_base, "ярко-красная помада, стрелки")
    assert "MOST IMPORTANT OVERRIDE" in _overridden, (
        f"9.21 override содержит явный маркер MOST IMPORTANT OVERRIDE: {_overridden}"
    )
    assert _base in _overridden and "ярко-красная помада, стрелки" in _overridden, (
        f"9.22 override сохраняет и дефолтный текст, и note (для контекста лица/фото): {_overridden}"
    )
    assert S.apply_user_note_override(_base, "") == _base, "9.23 override с пустым note не трогает base_prompt"
