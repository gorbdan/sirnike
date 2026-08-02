# -*- coding: utf-8 -*-
"""Блок 12: причёсывание экранов 2026-07-20 (макет утверждён Аней) —
видео-панель, отмена репорта, аватар."""
import asyncio
import inspect
import types
from unittest.mock import AsyncMock

from test_helpers import S


def test_block_13_ui_polish_2026_07_20():
    st12 = S.UserState()
    vtxt = S.video_status_text(st12)
    assert vtxt.startswith("🎬 Видео для Reels"), (
        f"12.1 видео-панель озаглавлена разделом, не моделью: {vtxt.splitlines()[0]}"
    )
    assert "http" not in vtxt and "Фото в буфере" not in vtxt and "1. Напиши" not in vtxt, (
        f"12.2 видео-панель не показывает сырые URL и старую инструкцию: {vtxt}"
    )
    assert "Хватит одного: описание или фото" in vtxt, (
        f"12.3 пустой видео-черновик подсказывает, с чего начать: {vtxt}"
    )
    st12.video_prompt = "кошка прыгает"
    vtxt2 = S.video_status_text(st12)
    assert "Хватит одного" not in vtxt2 and "Описание: есть ✅" in vtxt2, (
        f"12.4 заполненный черновик: подсказки нет, статус ✅: {vtxt2}"
    )

    # report_cancel: кнопка отмены репорта не на reset, отмена не трогает черновик
    _rp_src = inspect.getsource(S.report_problem_command)
    _bb_src = inspect.getsource(S.bug_bounty_command)
    assert 'callback_data="report_cancel"' in _rp_src, f"12.5 отмена «Проблемы» не на reset: {_rp_src[-200:]}"
    assert 'callback_data="report_cancel"' in _bb_src, f"12.6 отмена «Баг-баунти» не на reset: {_bb_src[-200:]}"

    st12r = S.UserState(waiting_for_bug_report=True)
    st12r.prompt = "мой черновик"
    st12r.references = ["https://example.com/ref.jpg"]
    _q12 = types.SimpleNamespace(
        data="report_cancel",
        message=types.SimpleNamespace(reply_text=AsyncMock()),
        answer=AsyncMock(),
        from_user=types.SimpleNamespace(id=9712),
    )
    _u12 = types.SimpleNamespace(
        callback_query=_q12,
        effective_user=types.SimpleNamespace(id=9712, username="test"),
        effective_chat=types.SimpleNamespace(id=9712),
    )
    _c12 = types.SimpleNamespace(user_data={"state": st12r}, application=None, bot=AsyncMock())
    asyncio.run(S.button_handler(_u12, _c12))
    assert st12r.waiting_for_bug_report is False, "12.7 report_cancel снимает режим репорта"
    assert st12r.prompt == "мой черновик" and st12r.references == ["https://example.com/ref.jpg"], (
        f"12.8 report_cancel НЕ трогает черновик: {st12r.prompt!r} {st12r.references!r}"
    )

    kb12 = S.avatar_actions_kb()
    labels12 = [b.text for row in kb12.inline_keyboard for b in row]
    assert any(t.startswith("🪄") for t in labels12) and not any("🎨" in t for t in labels12), (
        f"12.9 кнопка аватара с 🪄 по словарю (не 🎨): {labels12}"
    )

    _help_src = inspect.getsource(S.help_command)
    assert "🖼️ Улучшить фото" in _help_src and "Seedance 2, Kling" not in _help_src, (
        "12.10 справка знает про «Улучшить фото» и без списка моделей"
    )
