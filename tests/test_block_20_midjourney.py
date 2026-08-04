# -*- coding: utf-8 -*-
"""Блок 20: Midjourney (EvoLink) — отдельный мини-флоу (сетка -> апскейл).

Покрывает: фича-флаг, сброс чужих флоу при входе, сбор промта/фото-референса
(handle_text/handle_photo), биллинг сетки (хостинг референса ДО списания,
как у Kling Motion Control), доставку сетки с 4 кнопками, TTL протухания
сетки, биллинг и доставку апскейла.
"""
import asyncio
import types
from unittest.mock import AsyncMock

from test_helpers import S, make_update_context, make_text_update


def _make_photo_update_context(state, user_id=201):
    photo_message = types.SimpleNamespace(
        photo=[types.SimpleNamespace(file_id="ph_mj")],
        caption=None, media_group_id=None, reply_text=AsyncMock(),
    )
    update = types.SimpleNamespace(
        message=photo_message,
        effective_user=types.SimpleNamespace(id=user_id, username="test"),
        effective_chat=types.SimpleNamespace(id=user_id),
        effective_message=photo_message,
    )
    context = types.SimpleNamespace(user_data={"state": state}, bot=AsyncMock())
    context.bot.get_file = AsyncMock(return_value=types.SimpleNamespace(
        download_to_memory=AsyncMock(side_effect=lambda out: out.write(b"\x89PNG\r\n\x1a\n fake"))
    ))
    return update, context, photo_message


def test_block_20a_feature_flag_gates_menu_and_entry():
    _orig = S.MIDJOURNEY_ENABLED
    try:
        S.MIDJOURNEY_ENABLED = False
        cbs = [b.callback_data for row in S.photo_menu_kb().inline_keyboard for b in row]
        assert "menu_midjourney" not in cbs, f"20a.1 флаг выкл -> кнопки нет в меню: {cbs}"

        update, context, query = make_update_context("menu_midjourney", user_id=201)
        asyncio.run(S._cb_menu_midjourney(update, context, query, types.SimpleNamespace(id=201, username="t")))
        texts = [c.args[0] for c in query.message.reply_text.await_args_list]
        assert any("недоступен" in t for t in texts), f"20a.2 флаг выкл -> честный отказ: {texts}"

        S.MIDJOURNEY_ENABLED = True
        cbs_on = [b.callback_data for row in S.photo_menu_kb().inline_keyboard for b in row]
        assert "menu_midjourney" in cbs_on, f"20a.3 флаг вкл -> кнопка в меню: {cbs_on}"
    finally:
        S.MIDJOURNEY_ENABLED = _orig


def test_block_20b_entry_resets_other_flows():
    _orig = S.MIDJOURNEY_ENABLED
    S.MIDJOURNEY_ENABLED = True
    try:
        state = S.UserState()
        state.generating_avatar = True
        state.video_session_active = True
        state.waiting_for_video_image = True
        update, context, query = make_update_context("menu_midjourney", user_id=202)
        context.user_data["state"] = state
        asyncio.run(S._cb_menu_midjourney(update, context, query, types.SimpleNamespace(id=202, username="t")))
        assert state.mj_active is True and state.waiting_for_mj_prompt is True, "20b.1 mj-флоу включён"
        assert state.generating_avatar is False, "20b.2 аватарный флоу погашен"
        assert state.video_session_active is False and state.waiting_for_video_image is False, (
            "20b.3 видео-флоу погашен"
        )

        # Симметрия: вход в видео гасит mj_active
        update2, context2, query2 = make_update_context("video", user_id=202)
        context2.user_data["state"] = state
        asyncio.run(S._cb_video_open(update2, context2, query2, types.SimpleNamespace(id=202, username="t")))
        assert state.mj_active is False, "20b.4 вход в видео гасит mj_active"
    finally:
        S.MIDJOURNEY_ENABLED = _orig


def test_block_20c_text_then_photo_collect_draft():
    state = S.UserState(mj_active=True, waiting_for_mj_prompt=True)
    update, context, message = make_text_update("cinematic portrait, golden hour", user_id=203, state=state)
    asyncio.run(S.handle_text(update, context))
    assert state.mj_prompt == "cinematic portrait, golden hour", f"20c.1 промт сохранён: {state.mj_prompt}"
    assert state.waiting_for_mj_prompt is False and state.waiting_for_mj_image is True, (
        "20c.2 переход в ожидание (необязательного) фото"
    )
    kb_texts = [b.callback_data for row in message.reply_text.await_args_list[-1].kwargs["reply_markup"].inline_keyboard
                for b in row]
    assert "mj_generate" in kb_texts, f"20c.3 кнопка «Сгенерировать» появилась: {kb_texts}"

    update_p, context_p, photo_message = _make_photo_update_context(state, user_id=203)
    asyncio.run(S.handle_photo(update_p, context_p))
    assert state.mj_reference, f"20c.4 фото-референс сохранён: {state.mj_reference}"
    assert S._is_img_ref(state.mj_reference), "20c.5 референс — это __img__-реф (in-memory кэш)"


def test_block_20d_generate_hosts_reference_before_charge_and_delivers_grid():
    state = S.UserState(mj_active=True, mj_prompt="a portrait", mj_reference="__img_deadbeef__")
    update, context, query = make_update_context("mj_generate", user_id=204)
    context.user_data["state"] = state
    context.application = types.SimpleNamespace(create_task=lambda c: c)
    user = types.SimpleNamespace(id=204, username="test")

    _orig = {}
    for name in ("_persist_image_ref", "spend_izyminki", "add_izyminki", "get_balance",
                 "start_midjourney_task_evolink", "poll_evolink_task"):
        _orig[name] = getattr(S, name)

    persist_calls = []
    charges = []

    async def fake_persist(ref):
        persist_calls.append(ref)
        return "https://iili.io/mjref.jpg"

    S._persist_image_ref = fake_persist
    S.get_balance = lambda uid: 999
    S.spend_izyminki = lambda uid, amount: charges.append((uid, amount)) or True
    S.add_izyminki = lambda uid, amount: charges.append(("refund", uid, amount))

    evolink_calls = []

    async def fake_start(prompt, image_url, user_id):
        evolink_calls.append((prompt, image_url))
        return "__EVOLINK__:mj-task-1"

    S.start_midjourney_task_evolink = fake_start
    S.poll_evolink_task = AsyncMock(return_value="https://cdn.example/grid.jpg")

    update.effective_chat = types.SimpleNamespace(id=204)
    update.callback_query = query
    query.message.reply_text = AsyncMock()

    try:
        asyncio.run(S.run_midjourney_grid(update, context))
    finally:
        for name, fn in _orig.items():
            setattr(S, name, fn)
        S.processing_user_ids.discard(204)

    assert persist_calls == ["__img_deadbeef__"], f"20d.1 референс захостился до вызова EvoLink: {persist_calls}"
    assert charges == [(204, S.MIDJOURNEY_GRID_COST)], f"20d.2 списание после хостинга: {charges}"
    assert evolink_calls == [("a portrait", "https://iili.io/mjref.jpg")], (
        f"20d.3 EvoLink получил захостенный URL: {evolink_calls}"
    )
    assert context.bot.send_photo.await_count == 1, "20d.4 сетка отправлена юзеру"
    sent_kwargs = context.bot.send_photo.await_args.kwargs
    assert sent_kwargs.get("photo") == "https://cdn.example/grid.jpg", "20d.5 фото — реальный grid_url"
    kb = sent_kwargs["reply_markup"].inline_keyboard
    cbs = [b.callback_data for row in kb for b in row]
    assert cbs == ["mj_pick_0", "mj_pick_1", "mj_pick_2", "mj_pick_3"], f"20d.6 4 кнопки выбора: {cbs}"
    grid = S.last_mj_grid.get(204)
    assert grid and grid["task_id"] == "mj-task-1" and grid["grid_url"] == "https://cdn.example/grid.jpg", (
        f"20d.7 сетка сохранена в last_mj_grid: {grid}"
    )
    assert state.mj_active is False, "20d.8 черновик-состояние сброшено после запуска"


def test_block_20e_hosting_failure_no_charge_no_evolink_call():
    state = S.UserState(mj_active=True, mj_prompt="a portrait", mj_reference="__img_deadbeef__")
    update, context, query = make_update_context("mj_generate", user_id=205)
    context.user_data["state"] = state
    update.effective_chat = types.SimpleNamespace(id=205)
    update.callback_query = query
    query.message.reply_text = AsyncMock()

    _orig = {}
    for name in ("_persist_image_ref", "spend_izyminki", "get_balance", "start_midjourney_task_evolink"):
        _orig[name] = getattr(S, name)

    charges = []

    async def fake_persist_fail(ref):
        return ""

    S._persist_image_ref = fake_persist_fail
    S.get_balance = lambda uid: 999
    S.spend_izyminki = lambda uid, amount: charges.append((uid, amount)) or True
    evolink_calls = []
    S.start_midjourney_task_evolink = AsyncMock(side_effect=lambda **kw: evolink_calls.append(kw))

    try:
        asyncio.run(S.run_midjourney_grid(update, context))
    finally:
        for name, fn in _orig.items():
            setattr(S, name, fn)
        S.processing_user_ids.discard(205)

    assert charges == [], f"20e.1 хостинг не удался -> изюминки НЕ списаны: {charges}"
    assert evolink_calls == [], "20e.2 EvoLink вообще не вызывается"
    texts = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("не списаны" in t for t in texts), f"20e.3 честный отказ: {texts}"


def test_block_20f_pick_expired_grid_no_charge():
    S.last_mj_grid.pop(206, None)
    update, context, query = make_update_context("mj_pick_0", user_id=206)
    context.user_data["state"] = S.UserState()
    asyncio.run(S._cb_mj_pick(update, context, query, types.SimpleNamespace(id=206, username="t")))
    texts = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("устарела" in t for t in texts), f"20f.1 протухшей/отсутствующей сетки -> честное сообщение: {texts}"
    assert 206 not in S.processing_user_ids, "20f.2 processing_user_ids не тронут при отказе"


def test_block_20g_upscale_charges_and_delivers():
    grid = {
        "task_id": "mj-task-2", "grid_url": "https://cdn.example/grid2.jpg",
        "prompt": "a portrait", "chat_id": 207, "created_at": __import__("time").time(),
    }
    S.last_mj_grid[207] = grid
    update, context, query = make_update_context("mj_pick_1", user_id=207)
    context.user_data["state"] = S.UserState()
    context.application = types.SimpleNamespace(bot=AsyncMock())
    update.callback_query = query
    update.effective_chat = types.SimpleNamespace(id=207)

    _orig = {}
    for name in ("spend_izyminki", "add_izyminki", "get_balance", "start_midjourney_upscale_evolink",
                 "poll_evolink_task", "send_generation_result_by_url"):
        _orig[name] = getattr(S, name)

    charges = []
    S.get_balance = lambda uid: 999
    S.spend_izyminki = lambda uid, amount: charges.append((uid, amount)) or True
    S.add_izyminki = lambda uid, amount: charges.append(("refund", uid, amount))

    upscale_calls = []

    async def fake_upscale(task_id, image_number, user_id):
        upscale_calls.append((task_id, image_number))
        return "__EVOLINK__:mj-upscale-2"

    S.start_midjourney_upscale_evolink = fake_upscale
    S.poll_evolink_task = AsyncMock(return_value="https://cdn.example/final.jpg")
    delivered = []
    S.send_generation_result_by_url = AsyncMock(side_effect=lambda app, chat_id, user_id, url, job=None: delivered.append(
        (chat_id, user_id, url)
    ))

    try:
        asyncio.run(S.run_midjourney_upscale(update, context, grid=grid, image_number=1))
    finally:
        for name, fn in _orig.items():
            setattr(S, name, fn)
        S.processing_user_ids.discard(207)

    assert charges == [(207, S.MIDJOURNEY_UPSCALE_COST)], f"20g.1 списание за апскейл: {charges}"
    assert upscale_calls == [("mj-task-2", 1)], f"20g.2 апскейл вызван с task_id сетки и номером варианта: {upscale_calls}"
    assert delivered == [(207, 207, "https://cdn.example/final.jpg")], (
        f"20g.3 финальное фото доставлено через send_generation_result_by_url: {delivered}"
    )


def test_block_20h_upscale_failure_refunds():
    grid = {
        "task_id": "mj-task-3", "grid_url": "https://cdn.example/grid3.jpg",
        "prompt": "a portrait", "chat_id": 208, "created_at": __import__("time").time(),
    }
    update, context, query = make_update_context("mj_pick_2", user_id=208)
    context.user_data["state"] = S.UserState()
    update.callback_query = query
    update.effective_chat = types.SimpleNamespace(id=208)

    _orig = {}
    for name in ("spend_izyminki", "add_izyminki", "get_balance", "start_midjourney_upscale_evolink"):
        _orig[name] = getattr(S, name)
    charges = []
    S.get_balance = lambda uid: 999
    S.spend_izyminki = lambda uid, amount: charges.append((uid, amount)) or True
    S.add_izyminki = lambda uid, amount: charges.append(("refund", uid, amount))
    S.start_midjourney_upscale_evolink = AsyncMock(side_effect=Exception("EvoLink 500"))

    try:
        asyncio.run(S.run_midjourney_upscale(update, context, grid=grid, image_number=2))
    finally:
        for name, fn in _orig.items():
            setattr(S, name, fn)
        S.processing_user_ids.discard(208)

    assert charges == [(208, S.MIDJOURNEY_UPSCALE_COST), ("refund", 208, S.MIDJOURNEY_UPSCALE_COST)], (
        f"20h.1 списание, затем рефанд при сбое: {charges}"
    )
    texts = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("возвращены" in t for t in texts), f"20h.2 честное сообщение об ошибке: {texts}"
