# -*- coding: utf-8 -*-
"""Блок 19: Kling Motion Control — фото-референс хостится в публичный URL
до вызова EvoLink и до списания изюминок (живой прод-баг 2026-08-03).

EvoLink Kling Motion Control требует настоящий абсолютный HTTP(S) URL для
image_urls — сырой __img__-реф (in-memory кэш, не URL вообще) отбивался
invalid_media_url на КАЖДОМ запуске. Фикс: резолвим __img__-реф в публичный
URL через _persist_image_ref ДО списания, как уже делаем для аватара.
"""
import asyncio
import types
from unittest.mock import AsyncMock

from test_helpers import S


def _make_update_context(user_id=191):
    message = types.SimpleNamespace(reply_text=AsyncMock())
    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=user_id, username="test"),
        effective_chat=types.SimpleNamespace(id=user_id),
        effective_message=message,
        callback_query=None,
        message=message,
    )
    context = types.SimpleNamespace(user_data={}, bot=AsyncMock())
    return update, context, message


def test_block_19a_stale_img_ref_hosted_before_charge():
    state = S.UserState()
    state.motion_image_url = "__img_deadbeef__"
    state.motion_video_url = "https://api.telegram.org/file/bot123/video.mp4"
    state.video_prompt = "повтори движение"
    update, context, message = _make_update_context()
    context.user_data["state"] = state

    _orig = {}
    for name in ("_persist_image_ref", "spend_izyminki", "start_kling_motion_control_evolink",
                 "poll_evolink_task", "get_balance", "MOTION_CONTROL_PROVIDER"):
        _orig[name] = getattr(S, name)
    S.MOTION_CONTROL_PROVIDER = "evolink"

    persist_calls = []

    async def fake_persist(ref):
        persist_calls.append(ref)
        return "https://iili.io/hosted.jpg"

    charges = []
    S._persist_image_ref = fake_persist
    S.get_balance = lambda uid: 999
    S.spend_izyminki = lambda uid, amount: charges.append((uid, amount)) or True

    evolink_calls = []

    async def fake_start(image_url, motion_video_url, prompt, user_id):
        evolink_calls.append(image_url)
        return "__EVOLINK__:task123"

    S.start_kling_motion_control_evolink = fake_start
    S.poll_evolink_task = AsyncMock(side_effect=Exception("stub: не проверяем доставку в этом тесте"))

    try:
        asyncio.run(S.run_kling_motion_control(update, context))
    finally:
        for name, fn in _orig.items():
            setattr(S, name, fn)

    assert persist_calls == ["__img_deadbeef__"], (
        f"19a.1 _persist_image_ref вызван с исходным __img__-рефом: {persist_calls}"
    )
    assert charges and charges[0][0] == 191, f"19a.2 списание произошло ПОСЛЕ успешного хостинга: {charges}"
    assert evolink_calls == ["https://iili.io/hosted.jpg"], (
        f"19a.3 EvoLink получает захостенный публичный URL, не __img__-реф: {evolink_calls}"
    )


def test_block_19b_hosting_failure_no_charge():
    state = S.UserState()
    state.motion_image_url = "__img_deadbeef__"
    state.motion_video_url = "https://api.telegram.org/file/bot123/video.mp4"
    state.video_prompt = "повтори движение"
    update, context, message = _make_update_context(user_id=192)
    context.user_data["state"] = state

    _orig = {}
    for name in ("_persist_image_ref", "spend_izyminki", "start_kling_motion_control_evolink",
                 "get_balance", "MOTION_CONTROL_PROVIDER"):
        _orig[name] = getattr(S, name)
    S.MOTION_CONTROL_PROVIDER = "evolink"

    async def fake_persist_fail(ref):
        return ""  # все 4 фотохостинга недоступны

    charges = []
    S._persist_image_ref = fake_persist_fail
    S.get_balance = lambda uid: 999
    S.spend_izyminki = lambda uid, amount: charges.append((uid, amount)) or True
    evolink_calls = []
    S.start_kling_motion_control_evolink = AsyncMock(side_effect=lambda **kw: evolink_calls.append(kw))

    try:
        asyncio.run(S.run_kling_motion_control(update, context))
    finally:
        for name, fn in _orig.items():
            setattr(S, name, fn)

    assert charges == [], f"19b.1 хостинг не удался -> изюминки НЕ списаны: {charges}"
    assert evolink_calls == [], "19b.2 хостинг не удался -> EvoLink вообще не вызывается"
    texts = [c.args[0] for c in message.reply_text.await_args_list]
    assert any("не списаны" in t or "хостинг" in t.lower() for t in texts), (
        f"19b.3 юзеру честно объяснили и успокоили про баланс: {texts}"
    )
