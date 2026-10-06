# -*- coding: utf-8 -*-
"""Блок 27: Kling 3.0 / Veo 3.1 / Wan 2.7 на EvoLink (решение Ани 2026-09-11,
«отказались от Zveno») — независимые флаги KLING3_PROVIDER/VEO31_PROVIDER/
WAN27_PROVIDER (дефолт "zveno", ноль изменений поведения), выключены до
живого теста. Контракт EvoLink для этих трёх ОТЛИЧАЕТСЯ от общего
/v1/videos/generations, которым уже пользуются Seedance/Gemini Omni:
image_start(+image_end) вместо произвольного image_urls-массива у
Kling3/Wan27, обязательный generation_type у Veo31."""
import asyncio

from test_helpers import S


def test_block_27a_provider_flags_default_to_zveno():
    assert S.KLING3_PROVIDER == "zveno", f"27a.1 дефолт KLING3_PROVIDER=zveno: {S.KLING3_PROVIDER}"
    assert S.VEO31_PROVIDER == "zveno", f"27a.2 дефолт VEO31_PROVIDER=zveno: {S.VEO31_PROVIDER}"
    assert S.WAN27_PROVIDER == "zveno", f"27a.3 дефолт WAN27_PROVIDER=zveno: {S.WAN27_PROVIDER}"


def _patch_evolink_create(captured):
    async def fake_create(payload, log_label, user_id, endpoint_path="/v1/videos/generations"):
        captured["payload"] = payload
        captured["log_label"] = log_label
        captured["endpoint_path"] = endpoint_path
        return "__EVOLINK__:task-fake"
    return fake_create


def test_block_27b_kling3_text_to_video_payload():
    captured = {}
    _orig = S.video_providers._evolink_create_task
    S.video_providers._evolink_create_task = _patch_evolink_create(captured)
    try:
        task_id = asyncio.run(S.start_kling3_task_evolink(
            prompt="кот-космонавт летит к звёздам", image_url=None, user_id=1, duration=5, aspect_ratio="9:16",
        ))
        assert task_id == "__EVOLINK__:task-fake", f"27b.1 task_id прокинут: {task_id!r}"
        payload = captured["payload"]
        assert payload["model"] == S.video_providers.EVOLINK_KLING3_TEXT_MODEL, (
            f"27b.2 text-to-video model id: {payload}"
        )
        assert "image_start" not in payload, f"27b.3 без фото — нет image_start: {payload}"
        assert payload["aspect_ratio"] == "9:16", f"27b.4 aspect_ratio передан для t2v: {payload}"
        assert payload["sound"] == "on", f"27b.5 звук включён (паритет с Zveno): {payload}"
        assert payload["quality"] == "720p", f"27b.6 без mode -> дефолт 720p: {payload}"
    finally:
        S.video_providers._evolink_create_task = _orig


def test_block_27b2_kling3_honors_mode_1080p():
    # Живой баг 2026-10-06: quality был захардкожен в "720p" независимо от
    # mode — тумблер «🔥 Pro» в конструкторе вебаппа показывал выбор 1080p
    # (после фикса modes.length>1 на фронте), но реальная генерация молча
    # всегда уходила на 720p. Проверяем, что mode="1080p" теперь реально
    # попадает в payload.
    captured = {}
    _orig = S.video_providers._evolink_create_task
    S.video_providers._evolink_create_task = _patch_evolink_create(captured)
    try:
        asyncio.run(S.start_kling3_task_evolink(
            prompt="кот-космонавт", image_url=None, user_id=1, duration=5, mode="1080p",
        ))
        assert captured["payload"]["quality"] == "1080p", (
            f"27b2.1 mode=1080p реально доходит до payload: {captured['payload']}"
        )
    finally:
        S.video_providers._evolink_create_task = _orig


def test_block_27c_kling3_image_to_video_first_last_frame():
    captured = {}
    _orig = S.video_providers._evolink_create_task
    S.video_providers._evolink_create_task = _patch_evolink_create(captured)
    try:
        asyncio.run(S.start_kling3_task_evolink(
            prompt="переход", image_url=None, user_id=1, duration=5,
            image_urls=["https://i.ibb.co/a.jpg", "https://i.ibb.co/b.jpg"],
        ))
        payload = captured["payload"]
        assert payload["model"] == S.video_providers.EVOLINK_KLING3_IMAGE_MODEL, (
            f"27c.1 image-to-video model id: {payload}"
        )
        assert payload["image_start"] == "https://i.ibb.co/a.jpg", f"27c.2 первый кадр: {payload}"
        assert payload["image_end"] == "https://i.ibb.co/b.jpg", f"27c.3 последний кадр: {payload}"
        assert "aspect_ratio" not in payload, f"27c.4 aspect_ratio не нужен при фото-кадрах: {payload}"
    finally:
        S.video_providers._evolink_create_task = _orig


def test_block_27d_veo31_text_vs_reference_generation_type():
    captured = {}
    _orig = S.video_providers._evolink_create_task
    S.video_providers._evolink_create_task = _patch_evolink_create(captured)
    try:
        asyncio.run(S.start_veo31_task_evolink(prompt="закат над городом", image_url=None, user_id=1, duration=8))
        assert captured["payload"]["generation_type"] == "TEXT", (
            f"27d.1 без фото -> TEXT: {captured['payload']}"
        )
        assert captured["payload"]["model"] == S.video_providers.EVOLINK_VEO31_MODEL

        asyncio.run(S.start_veo31_task_evolink(
            prompt="оживи это фото", image_url="https://i.ibb.co/c.jpg", user_id=1, duration=8,
        ))
        payload2 = captured["payload"]
        assert payload2["generation_type"] == "REFERENCE", f"27d.2 с фото -> REFERENCE: {payload2}"
        assert payload2["image_urls"] == ["https://i.ibb.co/c.jpg"], f"27d.3 image_urls-массив: {payload2}"
        assert "aspect_ratio" not in payload2, "27d.4 aspect_ratio не нужен в REFERENCE-режиме"
    finally:
        S.video_providers._evolink_create_task = _orig


def test_block_27e_wan27_single_image_no_reference_sheet():
    captured = {}
    _orig = S.video_providers._evolink_create_task
    S.video_providers._evolink_create_task = _patch_evolink_create(captured)
    try:
        asyncio.run(S.start_wan27_task_evolink(
            prompt="прогулка", image_url="https://i.ibb.co/d.jpg", user_id=1, duration=5, aspect_ratio="16:9",
        ))
        payload = captured["payload"]
        assert payload["model"] == S.video_providers.EVOLINK_WAN27_IMAGE_MODEL, f"27e.1: {payload}"
        assert payload["image_start"] == "https://i.ibb.co/d.jpg", f"27e.2 одно фото — без сборки листа: {payload}"
    finally:
        S.video_providers._evolink_create_task = _orig


def test_block_27f_wan27_multi_image_builds_reference_sheet():
    captured = {}
    _orig_create = S.video_providers._evolink_create_task
    _orig_sheet = S.video_providers._build_reference_sheet_url_hook
    S.video_providers._evolink_create_task = _patch_evolink_create(captured)

    async def fake_sheet(urls):
        captured["sheet_input"] = urls
        return "https://i.ibb.co/sheet.jpg"
    S.video_providers._build_reference_sheet_url_hook = fake_sheet
    try:
        asyncio.run(S.start_wan27_task_evolink(
            prompt="два персонажа", image_url=None, user_id=1, duration=5,
            image_urls=["https://i.ibb.co/e.jpg", "https://i.ibb.co/f.jpg"],
        ))
        assert captured["sheet_input"] == ["https://i.ibb.co/e.jpg", "https://i.ibb.co/f.jpg"], (
            f"27f.1 reference sheet собран из обоих фото: {captured.get('sheet_input')}"
        )
        assert captured["payload"]["image_start"] == "https://i.ibb.co/sheet.jpg", (
            f"27f.2 в image_start ушёл собранный лист, не первое фото по отдельности: {captured['payload']}"
        )
    finally:
        S.video_providers._evolink_create_task = _orig_create
        S.video_providers._build_reference_sheet_url_hook = _orig_sheet


