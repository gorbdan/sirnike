# -*- coding: utf-8 -*-
"""Блок 22: доски (mood-борды), MVP — «Доска = коллекция референсов»
(docs/specs/2026-08-09_mood_boards.md). Вебапп хранит доски сам
(localStorage), бот только принимает новый payload-экшен `board_refs`/`br`
и грузит уже захостенные URL фото доски в state.references тем же кодом,
что и ручная загрузка фото (SirNike.py, _append_reference_url)."""
import asyncio

from test_helpers import S, make_webapp_update_context


def test_block_22_board_refs_applied_to_state_and_confirmation_text():
    urls = [f"https://i.ibb.co/board/{i}.jpg" for i in range(3)]
    update, context, message = make_webapp_update_context()
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "board_refs",
        "title": "Вечерний гламур",
        "board_refs": urls,
    }))
    assert applied is True, "22.1 payload распознан и применён"

    state = context.user_data["state"]
    assert state.references == urls, f"22.2 фото доски легли в state.references: {state.references}"

    texts = [c.args[0] for c in message.reply_text.await_args_list]
    assert len(texts) == 1, f"22.3 ровно одно сообщение-подтверждение: {texts}"
    text = texts[0]
    assert "Доска «Вечерний гламур» подключена" in text, f"22.4 название доски в тексте: {text!r}"
    assert "загружено 3/8" in text, f"22.5 счётчик N/8 верный: {text!r}"
    assert "Теперь выбери стиль в библиотеке" in text, f"22.6 призыв к действию дословно: {text!r}"

    kb = message.reply_text.await_args_list[0].kwargs.get("reply_markup")
    btn_texts = [b.text for row in kb.inline_keyboard for b in row]
    assert S.MENU_BTN_LIBRARY in btn_texts, f"22.7 кнопка «Библиотека стилей» под сообщением: {btn_texts}"


def test_block_22b_board_refs_short_action_and_field_aliases():
    # Короткие алиасы (`a`/`br`/`t`) — тот же стиль именования, что у
    # существующих полей p/t/ci/ii/n.
    urls = [f"https://i.ibb.co/short/{i}.jpg" for i in range(2)]
    update, context, message = make_webapp_update_context()
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "a": "br",
        "t": "Свадебный стиль",
        "br": urls,
    }))
    assert applied is True, "22b.1 короткий формат экшена/полей распознан"
    state = context.user_data["state"]
    assert state.references == urls, "22b.2 фото легли в references через алиасы"
    text = message.reply_text.await_args_list[0].args[0]
    assert "Свадебный стиль" in text and "2/8" in text, f"22b.3 текст верный: {text!r}"


def test_block_22c_board_refs_capped_at_8_silently():
    # Спека: «если фото больше 8 — в референс уходят первые 8, остальные
    # молча не идут» — это ожидаемое поведение, не баг.
    urls = [f"https://i.ibb.co/cap/{i}.jpg" for i in range(10)]
    update, context, message = make_webapp_update_context()
    asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "board_refs",
        "title": "Большая доска",
        "board_refs": urls,
    }))
    state = context.user_data["state"]
    assert state.references == urls[:8], f"22c.1 только первые 8 фото ушли в референс: {len(state.references)}"
    text = message.reply_text.await_args_list[0].args[0]
    assert "загружено 8/8" in text, f"22c.2 счётчик показывает потолок: {text!r}"


def test_block_22d_board_refs_resets_stale_style_extract_and_old_refs():
    # AGENT_NOTES 2026-07-16: залежавшийся style_extract=True/старые references
    # с прошлой несвязанной сессии не должны просочиться в новую доску.
    update, context, message = make_webapp_update_context()
    state = S.get_or_init_state(context)
    state.style_extract = True
    state.references = ["https://stale.example/old.jpg"]

    urls = ["https://i.ibb.co/fresh/1.jpg", "https://i.ibb.co/fresh/2.jpg"]
    asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "board_refs",
        "title": "Свежая доска",
        "board_refs": urls,
    }))
    new_state = context.user_data["state"]
    assert new_state.style_extract is False, "22d.1 style_extract сброшен"
    assert new_state.references == urls, f"22d.2 старые референсы не подмешаны: {new_state.references}"


def test_block_22e_board_refs_does_not_touch_note_override_logic():
    # Доски НЕ должны трогать note/n («свои пожелания» юзера,
    # docs/specs/2026-07-17_note_override_weak.md) — это отдельная сущность.
    update, context, message = make_webapp_update_context()
    asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "board_refs",
        "title": "Доска",
        "board_refs": ["https://i.ibb.co/note-check/1.jpg"],
        "note": "это поле должно быть проигнорировано board_refs-веткой",
    }))
    state = context.user_data["state"]
    assert state.prompt == "", f"22e.1 board_refs не трогает prompt: {state.prompt!r}"


def test_block_22f_board_refs_empty_list_no_crash():
    update, context, message = make_webapp_update_context()
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
        "action": "board_refs",
        "title": "Пустая доска",
        "board_refs": [],
    }))
    assert applied is True, "22f.1 пустой список фото не роняет обработчик"
    state = context.user_data["state"]
    assert state.references == [], "22f.2 references остаются пустыми"
    text = message.reply_text.await_args_list[0].args[0]
    assert "загружено 0/8" in text, f"22f.3 честный счётчик 0/8: {text!r}"
