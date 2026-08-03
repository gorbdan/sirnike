# -*- coding: utf-8 -*-
"""Блок 18: P2-пачка баг-ресерча 2026-08-02.

18a. Kling 3.0/Veo 3.1: промт считает [ImageN]-теги по числу РЕАЛЬНО
     отправляемых кадров (1-2), а не по числу загруженных фото.
18b. classify_generation_error знает RPOINTS-ошибку YesAPI (no_balance).
18c. Легаси v1 apply_webapp_prompt_payload (видео-ветка) сбрасывает
     style_extract — правило AGENT_NOTES [2026-07-16].
18d. Вход в видео-флоу гасит незавершённый аватарный флоу (generating_avatar).
18e. Фолбэк-скан библиотеки по промту: коллизия первых 80 символов больше
     не отдаёт чужой стиль — сравнение по всей доступной длине.
18f. Витрина /start (shc_) пишет использование шаблона в статистику.
"""
import asyncio
import types
from unittest.mock import AsyncMock

from test_helpers import S, FakeSession, captured, png_data_url, \
    make_update_context, make_webapp_update_context


def test_block_18a_prompt_refs_match_sent_frames():
    _orig_cs = S.aiohttp.ClientSession
    S.aiohttp.ClientSession = FakeSession
    try:
        photos = [png_data_url("RGB"), png_data_url("RGB", color=(0, 255, 0, 255)),
                  png_data_url("RGB", color=(0, 0, 255, 255))]

        captured.clear()
        asyncio.run(S.start_seedance_task(
            prompt="три человека танцуют", image_url=photos[0], image_urls=photos,
            user_id=1, duration=5, endpoint="/v1/videos", mode="720p",
            model_code="kling3", aspect_ratio="16:9",
        ))
        p = captured[0]["payload"]
        assert len(p.get("frame_images", [])) == 2, "18a.1 kling3: уходит ровно 2 кадра"
        assert "[Image3]" not in p.get("prompt", ""), (
            f"18a.2 kling3: промт не ссылается на неотправленный [Image3]: {p.get('prompt')!r}"
        )

        captured.clear()
        asyncio.run(S.start_seedance_task(
            prompt="двое идут по улице", image_url=photos[0], image_urls=photos[:2],
            user_id=1, duration=5, endpoint="/v1/videos", mode="720p",
            model_code="veo31", aspect_ratio="16:9",
        ))
        p2 = captured[0]["payload"]
        assert len(p2.get("frame_images", [])) == 1, "18a.3 veo31: уходит ровно 1 кадр"
        assert "[Image2]" not in p2.get("prompt", ""), (
            f"18a.4 veo31: промт не ссылается на неотправленный [Image2]: {p2.get('prompt')!r}"
        )
    finally:
        S.aiohttp.ClientSession = _orig_cs


def test_block_18b_rpoints_is_no_balance():
    assert S.classify_generation_error(Exception("NOT_ENOUGH_RPOINTS")) == "no_balance", (
        "18b.1 NOT_ENOUGH_RPOINTS -> no_balance"
    )
    assert S.classify_generation_error(Exception("Not enough RPoints on account")) == "no_balance", (
        "18b.2 текстовый вариант rpoints -> no_balance"
    )


def test_block_18c_v1_video_payload_resets_style_extract():
    update, context, msg = make_webapp_update_context()
    state = S.UserState()
    state.style_extract = True
    context.user_data["state"] = state
    applied = asyncio.run(S.apply_webapp_prompt_payload(update, context, {
        "action": "set_video_prompt",
        "title": "Видео-шаблон",
        "prompt": "cinematic dance video",
    }))
    assert applied is True, "18c.1 v1-payload применился"
    assert context.user_data["state"].style_extract is False, (
        "18c.2 видео-ветка v1 сбрасывает style_extract (правило AGENT_NOTES 2026-07-16)"
    )


def test_block_18d_video_entry_clears_avatar_flow():
    for handler_name in ("_cb_video_open", "_cb_video_set_prompt", "_cb_video_set_image"):
        update, context, query = make_update_context("video_open")
        state = S.UserState()
        state.generating_avatar = True
        state.avatar_photos = ["__img_x__"]
        context.user_data["state"] = state
        user = types.SimpleNamespace(id=777, username="test")
        asyncio.run(getattr(S, handler_name)(update, context, query, user))
        assert context.user_data["state"].generating_avatar is False, (
            f"18d {handler_name}: вход в видео гасит аватарный флоу"
        )


def test_block_18e_prompt_scan_survives_80char_collision():
    # Два стиля с ОДИНАКОВЫМИ первыми 80+ символами промта, расходятся дальше —
    # реальная ситуация в prompt_library.json (пары (0,1)/(0,3) и (5,6)/(13,1)).
    common = "Ultra realistic cinematic portrait photo of a person standing on a rooftop at golden hour, "
    lib = [{"title": "Тест-категория", "items": [
        {"title": "Стиль А", "prompt": common + "wearing a red dress", "kind": "image",
         "upload_hint": "Фото лица"},
        {"title": "Стиль Б", "prompt": common + "wearing a black tuxedo, male model", "kind": "image",
         "upload_hint": "Фото лица мужчины"},
    ]}]
    _orig_lib = S.PROMPT_LIBRARY
    S.PROMPT_LIBRARY = lib
    try:
        update, context, msg = make_webapp_update_context()
        applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update, context, {
            "action": "set_prompt",
            "prompt": lib[0]["items"][1]["prompt"],  # полный промт стиля Б
            "cat_idx": 99, "item_idx": 99,  # индексы заведомо мимо -> фолбэк-скан
        }))
        texts = [c.args[0] for c in msg.reply_text.await_args_list]
        assert applied is True and any("Стиль Б" in t or "мужчины" in t for t in texts), (
            f"18e.1 скан находит стиль Б, а не соседний А с тем же 80-префиксом: {texts}"
        )
        assert not any("Стиль А" in t or ("Фото лица\n" in t) for t in texts), (
            f"18e.2 подсказка чужого стиля А не показана: {texts}"
        )
    finally:
        S.PROMPT_LIBRARY = _orig_lib


def test_block_18f_showcase_logs_template_usage():
    logged = []
    _orig_log = S._log_template_usage_safe
    S._log_template_usage_safe = lambda uid, label, kind, cat_idx=None, item_idx=None: logged.append(
        (uid, label, kind, cat_idx, item_idx)
    )
    try:
        update, context, query = make_update_context("shc_0_0", user_id=778)
        asyncio.run(S.button_handler(update, context))
        assert logged and logged[0][0] == 778 and logged[0][3:] == (0, 0), (
            f"18f.1 клик по витрине /start попадает в статистику шаблонов: {logged}"
        )
    finally:
        S._log_template_usage_safe = _orig_log
