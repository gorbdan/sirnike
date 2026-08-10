# -*- coding: utf-8 -*-
"""Блок 23: Доски — Full, AI-анализ стиля доски
(docs/specs/2026-08-09_mood_boards_full.md). Расширяет MVP (блок 22,
`board_refs`) новым payload-экшеном `board_style_analyze`/`bsa`:
vision-описание общего стиля ПОДБОРКИ фото (extract_board_style_description)
сохраняется в ПЕРСИСТЕНТНОЕ state.board_style_note (НЕ references/style_extract
— те one-shot) после подтверждения юзером в чате («✅ Всё верно» /
«✏️ Поправить»), подмешивается в промт КАЖДОЙ следующей генерации, пока
доска активна (не одна), отключается отдельной чат-нативной инлайн-кнопкой.
"""
import asyncio
from unittest.mock import AsyncMock

from test_helpers import S, make_update_context, make_text_update, make_webapp_update_context


def test_block_23a_analyze_success_sends_confirmation_with_buttons():
    orig = S.extract_board_style_description
    try:
        S.extract_board_style_description = AsyncMock(
            return_value="Тёплая палитра, мягкий свет, романтичное настроение."
        )
        update, context, message = make_webapp_update_context(user_id=9601)
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "board_style_analyze",
            "board_id": "11111111-1111-1111-1111-111111111111",
            "title": "Вечерний гламур",
            "board_refs": [f"https://i.ibb.co/full/{i}.jpg" for i in range(4)],
        }))
        assert applied is True, "23a.1 payload распознан"

        state = context.user_data["state"]
        assert state.board_style_note is None, "23a.2 доска ещё НЕ активна до подтверждения"
        assert state.board_style_pending_note == "Тёплая палитра, мягкий свет, романтичное настроение.", (
            f"23a.3 описание легло в pending: {state.board_style_pending_note!r}"
        )
        assert state.board_style_pending_board_id == "11111111-1111-1111-1111-111111111111", (
            "23a.4 board_id сохранён в pending"
        )

        text = message.reply_text.await_args_list[0].args[0]
        assert "Доска «Вечерний гламур»" in text, f"23a.5 название доски в тексте: {text!r}"
        assert "Тёплая палитра" in text, f"23a.6 описание в тексте: {text!r}"
        assert "подмешиваться в промт КАЖДОЙ генерации" in text, f"23a.7 текст про каждую генерацию: {text!r}"

        kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
        btns = [b for row in kb.inline_keyboard for b in row]
        btn_texts = [b.text for b in btns]
        assert "✅ Всё верно" in btn_texts and "✏️ Поправить" in btn_texts, f"23a.8 кнопки: {btn_texts}"
        confirm_cb = [b.callback_data for b in btns if b.text == "✅ Всё верно"][0]
        edit_cb = [b.callback_data for b in btns if b.text == "✏️ Поправить"][0]
        assert confirm_cb.startswith("bsc_") and edit_cb.startswith("bse_"), (
            f"23a.9 callback_data-префиксы: {confirm_cb}, {edit_cb}"
        )
        assert confirm_cb.split("_", 1)[1] == edit_cb.split("_", 1)[1] == state.board_style_pending_short_id, (
            "23a.10 обе кнопки несут один и тот же short_id этой карточки"
        )
    finally:
        S.extract_board_style_description = orig


def test_block_23b_short_alias_and_field_aliases():
    orig = S.extract_board_style_description
    try:
        S.extract_board_style_description = AsyncMock(return_value="Пастельная гамма, спокойное настроение.")
        update, context, message = make_webapp_update_context(user_id=9602)
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "a": "bsa",
            "board_id": "board-short",
            "t": "Свадебный стиль",
            "br": [f"https://i.ibb.co/short/{i}.jpg" for i in range(2)],
        }))
        assert applied is True, "23b.1 короткий алиас экшена/полей распознан"
        state = context.user_data["state"]
        assert state.board_style_pending_note == "Пастельная гамма, спокойное настроение.", "23b.2 через алиасы"
        text = message.reply_text.await_args_list[0].args[0]
        assert "Свадебный стиль" in text, f"23b.3 название доски: {text!r}"
    finally:
        S.extract_board_style_description = orig


def test_block_23c_too_few_photos_no_vision_call():
    orig = S.extract_board_style_description
    try:
        S.extract_board_style_description = AsyncMock(return_value="не должно вызваться")
        update, context, message = make_webapp_update_context(user_id=9603)
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "board_style_analyze",
            "board_id": "board-few",
            "title": "Маленькая доска",
            "board_refs": ["https://i.ibb.co/one/1.jpg"],
        }))
        assert applied is True, "23c.1 обработчик не падает"
        assert not S.extract_board_style_description.await_args_list, "23c.2 vision не вызывается на 1 фото"
        state = context.user_data.get("state")
        assert state is None or state.board_style_pending_note is None, "23c.3 pending не выставлен"
        text = message.reply_text.await_args_list[0].args[0]
        assert "2 фото" in text, f"23c.4 честное сообщение про минимум 2 фото: {text!r}"
    finally:
        S.extract_board_style_description = orig


def test_block_23d_vision_failure_honest_error_no_half_connected_state():
    orig = S.extract_board_style_description
    try:
        S.extract_board_style_description = AsyncMock(return_value=None)
        state = S.UserState()
        state.board_style_note = "Уже подключённый стиль другой доски."
        state.board_style_board_id = "already-active"
        state.board_style_short_id = "already1"
        update, context, message = make_webapp_update_context(user_id=9604)
        context.user_data["state"] = state
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "board_style_analyze",
            "board_id": "board-fail",
            "title": "Проблемная доска",
            "board_refs": [f"https://i.ibb.co/fail/{i}.jpg" for i in range(3)],
        }))
        assert applied is True, "23d.1 обработчик не падает"
        text = message.reply_text.await_args_list[0].args[0]
        assert "Не получилось разобрать стиль доски" in text, f"23d.2 понятная ошибка: {text!r}"

        after = context.user_data["state"]
        assert after.board_style_pending_note is None, "23d.3 доска НЕ помечена наполовину подключённой"
        # Ошибка анализа ДРУГОЙ доски не гасит уже активный стиль текущей.
        assert after.board_style_note == "Уже подключённый стиль другой доски.", (
            f"23d.4 ранее подключённый стиль не тронут при неудачной попытке подключить другую доску: "
            f"{after.board_style_note!r}"
        )
        assert after.board_style_board_id == "already-active", "23d.5 board_id тоже не тронут"
    finally:
        S.extract_board_style_description = orig


def test_block_23e_confirm_activates_note_and_shows_disable_button():
    state = S.UserState()
    state.board_style_pending_note = "Пастельная палитра, мягкий боке."
    state.board_style_pending_board_id = "board-b"
    state.board_style_pending_title = "Доска Б"
    state.board_style_pending_short_id = "shortb1234567"
    update, context, query = make_update_context("bsc_shortb1234567", user_id=9605)
    context.user_data["state"] = state
    asyncio.run(S.button_handler(update, context))

    assert state.board_style_note == "Пастельная палитра, мягкий боке.", "23e.1 note активирован"
    assert state.board_style_board_id == "board-b", "23e.2 board_id перенесён из pending"
    assert state.board_style_short_id == "shortb1234567", "23e.3 short_id перенесён из pending"
    assert state.board_style_pending_note is None, "23e.4 pending очищен"
    assert state.board_style_pending_short_id == "", "23e.5 pending short_id очищен"

    texts = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("Стиль доски подключён" in t for t in texts), f"23e.6 подтверждение: {texts}"
    kb = query.message.reply_text.await_args_list[0].kwargs.get("reply_markup")
    off_btn = kb.inline_keyboard[0][0]
    assert off_btn.callback_data == "bsoff_shortb1234567", f"23e.7 кнопка отключения несёт short_id: {off_btn.callback_data}"
    assert "Отключить стиль доски" in off_btn.text, f"23e.8 текст кнопки отключения: {off_btn.text!r}"


def test_block_23f_confirm_stale_card_does_not_activate():
    state = S.UserState()
    state.board_style_pending_note = "Свежий анализ другой доски."
    state.board_style_pending_short_id = "freshid123456"
    update, context, query = make_update_context("bsc_oldstaleid0000", user_id=9606)
    context.user_data["state"] = state
    asyncio.run(S.button_handler(update, context))

    assert state.board_style_note is None, "23f.1 устаревшая карточка не активирует стиль"
    assert state.board_style_pending_note == "Свежий анализ другой доски.", "23f.2 текущий pending не тронут"
    texts = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("устарела" in t for t in texts), f"23f.3 честное сообщение об устаревшей карточке: {texts}"


def test_block_23g_edit_flow_saves_custom_text_via_free_text_message():
    state = S.UserState()
    state.board_style_pending_note = "AI-текст, который юзер хочет поправить."
    state.board_style_pending_board_id = "board-c"
    state.board_style_pending_short_id = "shortc7654321"
    update, context, query = make_update_context("bse_shortc7654321", user_id=9607)
    context.user_data["state"] = state
    asyncio.run(S.button_handler(update, context))
    assert state.waiting_for_board_style_correction is True, "23g.1 режим ожидания свободного текста включён"
    ask_texts = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert ask_texts, "23g.2 бот попросил прислать текст"

    update2, context2, message2 = make_text_update(
        "Мой собственный текст стиля доски.", user_id=9607, state=state,
    )
    S.init_db()
    asyncio.run(S.handle_text(update2, context2))

    assert state.waiting_for_board_style_correction is False, "23g.3 режим ожидания снят"
    assert state.board_style_note == "Мой собственный текст стиля доски.", "23g.4 свой текст сохранён как note"
    assert state.board_style_board_id == "board-c", "23g.5 board_id перенесён из pending"
    assert state.board_style_pending_note is None, "23g.6 pending очищен"
    texts2 = [c.args[0] for c in message2.reply_text.await_args_list]
    assert any("Стиль доски подключён" in t for t in texts2), f"23g.7 подтверждение: {texts2}"


def test_block_23h_note_applied_to_two_consecutive_different_styles():
    # Критерий приёмки: описание доски участвует в промте КАЖДОЙ следующей
    # генерации, а не только первой — проверяем на 2 подряд разных стилях
    # из настоящей PROMPT_LIBRARY (без монкипатча — как блок 11).
    item_a = S.PROMPT_LIBRARY[0]["items"][0]
    item_b = S.PROMPT_LIBRARY[0]["items"][1]
    prompt_a = item_a.get("prompt") or item_a.get("title")
    prompt_b = item_b.get("prompt") or item_b.get("title")

    state = S.UserState()
    state.board_style_note = "Warm golden palette, cozy evening mood, soft backlight."
    update, context, message = make_webapp_update_context(user_id=9608)
    context.user_data["state"] = state

    asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "set_prompt", "cat_idx": 0, "item_idx": 0,
    }))
    st1 = context.user_data["state"]
    assert "Warm golden palette" in st1.prompt and prompt_a[:60] in st1.prompt, (
        f"23h.1 note + стиль A в промте: {st1.prompt!r}"
    )

    asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "set_prompt", "cat_idx": 0, "item_idx": 1,
    }))
    st2 = context.user_data["state"]
    assert "Warm golden palette" in st2.prompt and prompt_b[:60] in st2.prompt, (
        f"23h.2 note + ВТОРОЙ ПОДРЯД другой стиль (та же доска): {st2.prompt!r}"
    )
    assert st2.board_style_note == "Warm golden palette, cozy evening mood, soft backlight.", (
        "23h.3 note не one-shot — не сброшен после первого применения"
    )


def test_block_23i_note_applied_via_pl_use_prefix_path_too():
    # Второе место наложения (button_handler, pl_use_/pl_usen_) — тот же
    # контракт, что и apply_webapp_prompt_payload_v2 выше.
    item = S.PROMPT_LIBRARY[0]["items"][0]
    item_prompt = item.get("prompt") or item.get("title")

    state = S.UserState()
    state.board_style_note = "Moody teal-and-orange cinematic palette."
    update, context, query = make_update_context("pl_use_0_0", user_id=9609)
    context.user_data["state"] = state
    asyncio.run(S.button_handler(update, context))

    st_after = context.user_data["state"]
    assert "Moody teal-and-orange" in st_after.prompt and item_prompt[:60] in st_after.prompt, (
        f"23i.1 board_style_note применён и в pl_use_-пути: {st_after.prompt!r}"
    )


def test_block_23j_disable_button_clears_note():
    state = S.UserState()
    state.board_style_note = "Активный стиль доски."
    state.board_style_board_id = "board-active"
    state.board_style_short_id = "activeid12345"
    update, context, query = make_update_context("bsoff_activeid12345", user_id=9610)
    context.user_data["state"] = state
    asyncio.run(S.button_handler(update, context))

    assert state.board_style_note is None, "23j.1 note очищен"
    assert state.board_style_board_id is None, "23j.2 board_id очищен"
    texts = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("Стиль доски отключён" in t for t in texts), f"23j.3 подтверждение отключения: {texts}"

    # После отключения доска больше не подмешивается в новый промт.
    update2, context2, message2 = make_webapp_update_context(user_id=9610)
    context2.user_data["state"] = state
    asyncio.run(S.apply_webapp_prompt_payload_v2(update2, context2, {
        "action": "set_prompt", "cat_idx": 0, "item_idx": 0,
    }))
    st_after = context2.user_data["state"]
    assert "Активный стиль доски" not in st_after.prompt, (
        f"23j.4 отключённый стиль больше не в промте: {st_after.prompt!r}"
    )


def test_block_23k_switching_to_another_board_resets_previous_style_note():
    # Критерий приёмки: активация ДРУГОЙ доски (board_refs ИЛИ
    # board_style_analyze) автоматически снимает предыдущий board_style_note.
    state = S.UserState()
    state.board_style_note = "Стиль первой доски."
    state.board_style_board_id = "board-1"
    state.board_style_short_id = "board1id12345"

    # (a) переключение через MVP board_refs
    update, context, message = make_webapp_update_context(user_id=9611)
    context.user_data["state"] = state
    asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "board_refs",
        "title": "Другая доска",
        "board_refs": ["https://i.ibb.co/other/1.jpg"],
    }))
    st_after_refs = context.user_data["state"]
    assert st_after_refs.board_style_note is None, "23k.1 board_refs на другую доску снимает предыдущий стиль"
    assert st_after_refs.board_style_board_id is None, "23k.2 board_id тоже снят"

    # (b) переключение через board_style_analyze — тоже сбрасывает (проверяем
    # отдельным состоянием, чтобы не зависеть от порядка (a)).
    orig = S.extract_board_style_description
    try:
        S.extract_board_style_description = AsyncMock(return_value="Стиль совсем другой доски.")
        state2 = S.UserState()
        state2.board_style_note = "Стиль первой доски (для теста b)."
        state2.board_style_board_id = "board-1b"
        state2.board_style_short_id = "board1bid1234"
        update2, context2, message2 = make_webapp_update_context(user_id=9612)
        context2.user_data["state"] = state2
        asyncio.run(S.apply_webapp_prompt_payload_v2(update2, context2, {
            "action": "board_style_analyze",
            "board_id": "board-2b",
            "title": "Третья доска",
            "board_refs": [f"https://i.ibb.co/third/{i}.jpg" for i in range(2)],
        }))
        st_after_analyze = context2.user_data["state"]
        # Новый анализ ещё не подтверждён (pending), но старый стиль уже снят —
        # «одна активная доска одновременно».
        assert st_after_analyze.board_style_note is None, (
            "23k.3 board_style_analyze на другую доску снимает предыдущий стиль"
        )
        assert st_after_analyze.board_style_pending_note == "Стиль совсем другой доски.", (
            "23k.4 новый анализ лёг в pending"
        )
    finally:
        S.extract_board_style_description = orig
