# -*- coding: utf-8 -*-
"""Блок 8: видео-воронка (длиннее / апгрейд)."""
import asyncio
import types

from test_helpers import S, make_update_context


def test_block_08_video_funnel():
    # 8.1 seedance2_fast 5с: длиннее 10с (5.4*10=54) + апгрейд (6.75*5=33.75->34)
    S.last_video_params[801] = {"model": "seedance2_fast", "duration": 5, "mode": "720p",
                                "aspect": "9:16", "prompt": "тест", "refs": ["https://example.com/a.png"]}
    kbu, has_up = S.video_upsell_kb(801)
    btns = [b for row in kbu.inline_keyboard for b in row]
    cbs = [b.callback_data for b in btns]
    texts = [b.text for b in btns]
    assert "video_longer_10" in cbs, f"8.1 fast 5с: есть «длиннее 10 сек»: {cbs}"
    assert any("10с · 54 🍇" in t for t in texts), f"8.2 fast 5с: цена длиннее = 54 изюм: {texts}"
    assert "video_upgrade_seedance2" in cbs, "8.3 fast 5с: есть апгрейд в Seedance 2"
    assert any("Seedance 2 — 34 🍇" in t for t in texts), f"8.4 fast 5с: цена апгрейда = 34 изюм: {texts}"
    assert has_up is True, "8.5 fast 5с: has_upsell=True"
    assert "video" in cbs, "8.6 есть кнопка «Ещё видео»"

    # 8.7 fast 10с -> длиннее 15с
    S.last_video_params[802] = {"model": "seedance2_fast", "duration": 10, "mode": "720p",
                                "aspect": "16:9", "prompt": "", "refs": []}
    kbu, _ = S.video_upsell_kb(802)
    cbs = [b.callback_data for row in kbu.inline_keyboard for b in row]
    assert "video_longer_15" in cbs, f"8.7 fast 10с: длиннее = 15: {cbs}"

    # 8.8 kling3 на максимуме (15с): нет длиннее, нет апгрейда
    S.last_video_params[803] = {"model": "kling3", "duration": 15, "mode": "720p",
                                "aspect": "16:9", "prompt": "", "refs": []}
    kbu, has_up = S.video_upsell_kb(803)
    cbs = [b.callback_data for row in kbu.inline_keyboard for b in row]
    assert not any(c.startswith("video_longer_") for c in cbs), f"8.8 kling3 15с: нет «длиннее»: {cbs}"
    assert "video_upgrade_seedance2" not in cbs, "8.9 kling3: нет апгрейда (не fast)"
    assert has_up is False, "8.10 kling3 15с: has_upsell=False"

    # 8.11 veo31 4с -> длиннее 6с
    S.last_video_params[804] = {"model": "veo31", "duration": 4, "mode": "720p",
                                "aspect": "16:9", "prompt": "", "refs": []}
    kbu, _ = S.video_upsell_kb(804)
    cbs = [b.callback_data for row in kbu.inline_keyboard for b in row]
    assert "video_longer_6" in cbs, f"8.11 veo31 4с: длиннее = 6: {cbs}"

    # 8.12 нет параметров
    S.last_video_params.pop(805, None)
    kbu, has_up = S.video_upsell_kb(805)
    assert kbu is None and has_up is False, "8.12 нет параметров -> (None, False)"

    # 8.13 колбэк video_longer_10 восстанавливает параметры и запускает генерацию
    started = []
    _orig_run_seedance = S.run_seedance

    async def fake_run_seedance(update, context):
        started.append(True)

    S.run_seedance = fake_run_seedance
    S.last_video_params[806] = {"model": "seedance2_fast", "duration": 5, "mode": "720p",
                                "aspect": "9:16", "prompt": "кот танцует",
                                "refs": ["https://example.com/cat.png"]}
    update, context, query = make_update_context("video_longer_10", user_id=806)
    context.application = types.SimpleNamespace(create_task=lambda c: (started.append("task"), c.close()))
    asyncio.run(S.button_handler(update, context))
    st11 = context.user_data.get("state")
    assert st11 and st11.video_duration == 10, (
        f"8.13 длиннее: duration=10: dur={getattr(st11, 'video_duration', None)}"
    )
    assert st11.video_model == "seedance2_fast", "8.14 длиннее: модель сохранена (fast)"
    assert st11.animation_source_urls == ["https://example.com/cat.png"], "8.15 длиннее: реф восстановлен"
    assert st11.video_prompt == "кот танцует", "8.16 длиннее: промт восстановлен"
    assert "task" in started, f"8.17 длиннее: генерация запущена: {started}"
    S.processing_user_ids.discard(806)

    # 8.18 колбэк video_upgrade_seedance2: модель меняется, длительность та же
    S.last_video_params[807] = {"model": "seedance2_fast", "duration": 10, "mode": "720p",
                                "aspect": "16:9", "prompt": "пёс бежит",
                                "refs": ["https://example.com/dog.png"]}
    update, context, query = make_update_context("video_upgrade_seedance2", user_id=807)
    context.application = types.SimpleNamespace(create_task=lambda c: c.close())
    asyncio.run(S.button_handler(update, context))
    st12 = context.user_data.get("state")
    assert st12 and st12.video_model == "seedance2", (
        f"8.18 апгрейд: модель seedance2: model={getattr(st12, 'video_model', None)}"
    )
    assert st12.video_duration == 10, "8.19 апгрейд: длительность сохранена (10)"
    assert st12.animation_source_urls == ["https://example.com/dog.png"], "8.20 апгрейд: реф восстановлен"
    S.processing_user_ids.discard(807)

    # 8.21 колбэк без параметров — мягкое сообщение
    S.last_video_params.pop(808, None)
    update, context, query = make_update_context("video_longer_10", user_id=808)
    asyncio.run(S.button_handler(update, context))
    msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("Не нашла параметры" in m for m in msgs), (
        f"8.21 без параметров — мягкое сообщение: {str(msgs)[:200]}"
    )

    # 8.22 стейлый __img__ реф — мягкое сообщение
    S.last_video_params[809] = {"model": "seedance2", "duration": 5, "mode": "720p",
                                "aspect": "16:9", "prompt": "", "refs": ["__img_dead00beef__"]}
    update, context, query = make_update_context("video_longer_10", user_id=809)
    asyncio.run(S.button_handler(update, context))
    msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
    assert any("устарело" in m for m in msgs), f"8.22 стейлый реф — мягкое сообщение: {str(msgs)[:200]}"

    # 8.23 занятый пользователь — alert, генерация не стартует
    S.last_video_params[810] = {"model": "seedance2_fast", "duration": 5, "mode": "720p",
                                "aspect": "16:9", "prompt": "", "refs": []}
    S.processing_user_ids.add(810)
    update, context, query = make_update_context("video_longer_10", user_id=810)
    asyncio.run(S.button_handler(update, context))
    assert any("другая задача" in str(c) for c in query.answer.await_args_list), (
        f"8.23 занят — query.answer с предупреждением: {query.answer.await_args_list}"
    )
    S.processing_user_ids.discard(810)

    S.run_seedance = _orig_run_seedance
