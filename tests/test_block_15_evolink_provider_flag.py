# -*- coding: utf-8 -*-
"""Блок 14: EvoLink провайдер-флаг + Motion Control UI."""
import asyncio
import base64
import types
from unittest.mock import AsyncMock

from test_helpers import S, make_update_context, OK_PNG_B64


def test_block_15_evolink_provider_flag():
    ok_png_b64 = OK_PNG_B64

    # 14.1 дефолт SEEDANCE_PROVIDER="zveno" — ноль изменений поведения
    assert S.SEEDANCE_PROVIDER == "zveno", f"14.1 дефолт SEEDANCE_PROVIDER = zveno: {S.SEEDANCE_PROVIDER}"
    assert S.seedance_uses_evolink("seedance2") is False, "14.2 seedance2 на zveno -> use_evolink=False"
    assert S.seedance_uses_evolink("seedance2_fast") is False, (
        "14.3 seedance2_fast на zveno -> use_evolink=False"
    )

    _orig_seedance_provider = S.SEEDANCE_PROVIDER
    S.SEEDANCE_PROVIDER = "evolink"
    assert S.seedance_uses_evolink("seedance2") is True, "14.4 seedance2 на evolink -> use_evolink=True"
    assert S.seedance_uses_evolink("seedance2_fast") is True, (
        "14.5 seedance2_fast на evolink -> use_evolink=True"
    )
    assert S.seedance_uses_evolink("kling3") is False, "14.6 kling3 игнорирует SEEDANCE_PROVIDER даже на evolink"
    assert S.seedance_uses_evolink("veo31") is False, "14.7 veo31 игнорирует SEEDANCE_PROVIDER даже на evolink"
    assert S.seedance_uses_evolink("wan27") is False, "14.8 wan27 игнорирует SEEDANCE_PROVIDER даже на evolink"
    S.SEEDANCE_PROVIDER = _orig_seedance_provider
    assert S.SEEDANCE_PROVIDER == "zveno", "14.9 SEEDANCE_PROVIDER восстановлен в zveno после теста"

    # 14.10 EvoLink-клиент теперь реальный (см. Блок 15) — без фото image-to-video
    # честно падает с понятной ошибкой, а не молчаливым noop/NotImplementedError.
    try:
        asyncio.run(S.start_seedance_task_evolink(
            prompt="тест", image_url=None, user_id=1, model_code="seedance2",
        ))
        assert False, "14.10 start_seedance_task_evolink без фото кидает исключение"
    except Exception as e:
        assert "фото" in str(e).lower() or "image" in str(e).lower(), (
            f"14.10 start_seedance_task_evolink без фото кидает исключение: {e}"
        )

    # 14.11 MOTION_CONTROL_ENABLED=0 по умолчанию — кнопка скрыта в video_menu_kb
    assert S.MOTION_CONTROL_ENABLED is False, (
        f"14.11 MOTION_CONTROL_ENABLED выключен по умолчанию: {S.MOTION_CONTROL_ENABLED}"
    )
    kb_video_menu = S.video_menu_kb(user_id=1)
    cbs_vm = [b.callback_data for row in kb_video_menu.inline_keyboard for b in row]
    assert "motion_start" not in cbs_vm, f"14.12 кнопка motion_start скрыта при выключенном флаге: {cbs_vm}"

    # 14.13 при включённом флаге кнопка появляется
    _orig_motion_flag = S.MOTION_CONTROL_ENABLED
    S.MOTION_CONTROL_ENABLED = True
    kb_video_menu2 = S.video_menu_kb(user_id=1)
    cbs_vm2 = [b.callback_data for row in kb_video_menu2.inline_keyboard for b in row]
    assert "motion_start" in cbs_vm2, f"14.13 кнопка motion_start видна при включённом флаге: {cbs_vm2}"

    # 14.14 motion_start запускает waiting_for_motion_video, сбрасывая обычный видео-режим
    update, context, query = make_update_context("motion_start", user_id=1401)
    context.user_data["state"] = S.UserState(video_session_active=True, waiting_for_video_image=True)
    asyncio.run(S.button_handler(update, context))
    st14 = context.user_data.get("state")
    assert st14 and st14.waiting_for_motion_video is True, (
        f"14.14 motion_start взводит waiting_for_motion_video: {st14}"
    )
    assert st14 and st14.motion_control_active is True, "14.15 motion_start взводит motion_control_active"
    assert st14 and st14.video_session_active is False, (
        "14.16 motion_start гасит обычный видео-режим (video_session_active)"
    )

    # 14.17 handle_video: референс-видео добавлен -> просит фото (не video_kb Seedance)
    video_message = types.SimpleNamespace(
        video=types.SimpleNamespace(file_id="vid1"),
        reply_text=AsyncMock(),
    )
    update = types.SimpleNamespace(
        message=video_message,
        effective_user=types.SimpleNamespace(id=1402, username="test"),
        effective_chat=types.SimpleNamespace(id=1402),
        effective_message=video_message,
    )
    st14b = S.UserState(motion_control_active=True, waiting_for_motion_video=True)
    context = types.SimpleNamespace(user_data={"state": st14b}, application=None, bot=AsyncMock())
    context.bot.get_file = AsyncMock(return_value=types.SimpleNamespace(file_path="videos/file1.mp4"))
    asyncio.run(S.handle_video(update, context))
    assert st14b.waiting_for_motion_video is False, "14.18 waiting_for_motion_video сброшен после видео"
    assert st14b.waiting_for_motion_image is True, (
        "14.19 waiting_for_motion_image взведён (ждём фото следующим шагом)"
    )
    assert bool(st14b.motion_video_url), f"14.20 motion_video_url сохранён: {st14b.motion_video_url}"
    video_texts = [c.args[0] for c in video_message.reply_text.await_args_list]
    assert any("фото" in t.lower() for t in video_texts), (
        f"14.21 просит прислать фото (не показывает video_kb): {video_texts}"
    )

    # 14.22 handle_photo: фото после видео с движением запускает run_kling_motion_control
    started_motion = []

    async def fake_run_motion(update, context):
        started_motion.append(True)

    _orig_run_motion = S.run_kling_motion_control
    S.run_kling_motion_control = fake_run_motion
    st14c = S.UserState(waiting_for_motion_image=True, motion_video_url="https://example.com/motion.mp4")
    photo_message_motion = types.SimpleNamespace(
        photo=[types.SimpleNamespace(file_id="ph_motion")],
        caption=None, media_group_id=None, reply_text=AsyncMock(),
    )
    update = types.SimpleNamespace(
        message=photo_message_motion,
        effective_user=types.SimpleNamespace(id=1403, username="test"),
        effective_chat=types.SimpleNamespace(id=1403),
        effective_message=photo_message_motion,
    )
    context = types.SimpleNamespace(
        user_data={"state": st14c},
        application=types.SimpleNamespace(create_task=lambda c: (started_motion.append("task"), c.close())),
        bot=AsyncMock(),
    )
    context.bot.get_file = AsyncMock(return_value=types.SimpleNamespace(
        download_to_memory=AsyncMock(side_effect=lambda out: out.write(base64.b64decode(ok_png_b64)))
    ))
    asyncio.run(S.handle_photo(update, context))
    assert st14c.waiting_for_motion_image is False, "14.23 waiting_for_motion_image сброшен после фото"
    assert bool(st14c.motion_image_url), f"14.24 motion_image_url сохранён: {st14c.motion_image_url}"
    assert "task" in started_motion, f"14.25 run_kling_motion_control запущен (create_task): {started_motion}"
    S.processing_user_ids.discard(1403)
    S.run_kling_motion_control = _orig_run_motion

    # 14.26 deactivate_video_session гасит motion-состояние вместе с обычным видео
    st14d = S.UserState(
        motion_control_active=True, waiting_for_motion_video=True,
        waiting_for_motion_image=True, motion_video_url="x", motion_image_url="y",
    )
    S.deactivate_video_session(st14d)
    assert st14d.motion_control_active is False, "14.27 deactivate_video_session гасит motion_control_active"
    assert st14d.waiting_for_motion_image is False, "14.28 deactivate_video_session гасит waiting_for_motion_image"
    assert st14d.motion_video_url is None and st14d.motion_image_url is None, (
        "14.29 deactivate_video_session чистит motion_video_url/motion_image_url"
    )

    S.MOTION_CONTROL_ENABLED = _orig_motion_flag
