# -*- coding: utf-8 -*-
"""Блок 26: гибридная миграция фото-генерации на EvoLink (решение Ани
2026-08-25) — только обычная модель (Nano Banana 2/gemini) может идти через
EvoLink (PHOTO_PROVIDER=evolink, выключено по умолчанию), GPT-5 Image
ЦЕЛЕНАПРАВЛЕННО всегда остаётся на Zveno (у EvoLink другой модели под этой
нишей — gpt-image-2/gpt-image-1.5, требует отдельного живого теста)."""
import asyncio
import types
from unittest.mock import AsyncMock

from test_helpers import S


def test_block_26a_generate_image_evolink_builds_payload_and_polls():
    _orig_create = S.photo_providers._evolink_create_task
    _orig_poll = S.photo_providers.poll_evolink_task
    captured = {}

    async def fake_create(payload, log_label, user_id, endpoint_path="/v1/videos/generations"):
        captured["payload"] = payload
        captured["endpoint_path"] = endpoint_path
        return "__EVOLINK__:task123"

    async def fake_poll(task_id, max_attempts, poll_interval, status_callback=None, return_all=False):
        captured["task_id"] = task_id
        return "https://cdn.evolink.ai/result.jpg"

    S.photo_providers._evolink_create_task = fake_create
    S.photo_providers.poll_evolink_task = fake_poll
    try:
        url = asyncio.run(S.photo_providers.generate_image_evolink(
            prompt="кот-космонавт", references=["https://i.ibb.co/ref.jpg"], user_id=555,
        ))
        assert url == "https://cdn.evolink.ai/result.jpg", f"26a.1 итоговый URL: {url!r}"
        assert captured["endpoint_path"] == "/v1/images/generations", "26a.2 правильный эндпоинт"
        assert captured["payload"]["model"] == S.photo_providers.EVOLINK_IMAGE_MODEL, "26a.3 model id из конфига"
        assert captured["payload"]["prompt"] == "кот-космонавт", "26a.4 промт передан как есть"
        assert captured["payload"]["image_urls"] == ["https://i.ibb.co/ref.jpg"], (
            f"26a.5 референс передан в image_urls: {captured['payload']}"
        )
        assert captured["task_id"] == "task123", f"26a.6 префикс __EVOLINK__: снят перед поллингом: {captured['task_id']!r}"
    finally:
        S.photo_providers._evolink_create_task = _orig_create
        S.photo_providers.poll_evolink_task = _orig_poll


def test_block_26b_generate_image_evolink_empty_prompt_raises():
    try:
        asyncio.run(S.photo_providers.generate_image_evolink(prompt="  ", references=None, user_id=1))
        assert False, "26b.1 пустой промт обязан бросить Exception"
    except Exception as e:
        assert "промт" in str(e), f"26b.2 текст ошибки про пустой промт: {e!r}"


def test_block_26c_generate_image_evolink_no_references_omits_image_urls():
    _orig_create = S.photo_providers._evolink_create_task
    _orig_poll = S.photo_providers.poll_evolink_task
    captured = {}

    async def fake_create(payload, log_label, user_id, endpoint_path="/v1/videos/generations"):
        captured["payload"] = payload
        return "task456"

    async def fake_poll(task_id, max_attempts, poll_interval, status_callback=None, return_all=False):
        return "https://cdn.evolink.ai/no-refs.jpg"

    S.photo_providers._evolink_create_task = fake_create
    S.photo_providers.poll_evolink_task = fake_poll
    try:
        asyncio.run(S.photo_providers.generate_image_evolink(prompt="просто текст", references=None, user_id=2))
        assert "image_urls" not in captured["payload"], (
            f"26c.1 без референсов поле image_urls не отправляется: {captured['payload']}"
        )
    finally:
        S.photo_providers._evolink_create_task = _orig_create
        S.photo_providers.poll_evolink_task = _orig_poll


def _setup_generate_image_by_job_mocks():
    _orig = {}
    for name in ("_persist_image_ref", "send_generation_result_by_url", "add_generation_history",
                 "log_generation_event", "add_izyminki", "restore_free_generation", "maybe_send_avatar_nudge"):
        _orig[name] = getattr(S, name)
    S._persist_image_ref = AsyncMock(return_value="https://example.com/x.png")
    S.send_generation_result_by_url = AsyncMock()
    S.add_generation_history = lambda **kw: None
    S.log_generation_event = lambda **kw: None
    S.add_izyminki = lambda *a, **kw: None
    S.restore_free_generation = lambda *a, **kw: None
    _orig_channel = S.RESULTS_CHANNEL_ID
    S.RESULTS_CHANNEL_ID = ""
    return _orig, _orig_channel


def _teardown_generate_image_by_job_mocks(_orig, _orig_channel):
    for name, fn in _orig.items():
        setattr(S, name, fn)
    S.RESULTS_CHANNEL_ID = _orig_channel


def test_block_26d_photo_provider_evolink_routes_gemini_to_evolink():
    _orig_photo_provider = S.PHOTO_PROVIDER
    _orig_evolink_fn = S.generate_image_evolink
    _orig_zveno_fn = S.generate_image_zveno
    S.PHOTO_PROVIDER = "evolink"
    calls = {"evolink": 0, "zveno": 0}

    async def fake_evolink(prompt, references, user_id):
        calls["evolink"] += 1
        return "https://cdn.evolink.ai/photo.jpg"

    async def fake_zveno(prompt, references, user_id, image_model="gemini"):
        calls["zveno"] += 1
        return "https://cdn.zveno.ai/photo.jpg"

    S.generate_image_evolink = fake_evolink
    S.generate_image_zveno = fake_zveno
    mocks, channel = _setup_generate_image_by_job_mocks()
    try:
        app = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
        job = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=5, image_model="gemini")
        asyncio.run(S.generate_image_by_job(app, job))
        assert calls == {"evolink": 1, "zveno": 0}, f"26d.1 gemini + PHOTO_PROVIDER=evolink -> EvoLink: {calls}"
        assert S.send_generation_result_by_url.await_count == 1, "26d.2 результат доставлен"
    finally:
        S.PHOTO_PROVIDER = _orig_photo_provider
        S.generate_image_evolink = _orig_evolink_fn
        S.generate_image_zveno = _orig_zveno_fn
        _teardown_generate_image_by_job_mocks(mocks, channel)


def test_block_26e_gpt5_image_always_stays_on_zveno_even_with_evolink_flag():
    # Ключевая гарантия гибридной схемы: PHOTO_PROVIDER=evolink НЕ трогает
    # премиум-модель — у EvoLink нет gpt-5-image, только другие модели.
    _orig_photo_provider = S.PHOTO_PROVIDER
    _orig_evolink_fn = S.generate_image_evolink
    _orig_zveno_fn = S.generate_image_zveno
    S.PHOTO_PROVIDER = "evolink"
    calls = {"evolink": 0, "zveno": 0}

    async def fake_evolink(prompt, references, user_id):
        calls["evolink"] += 1
        return "https://cdn.evolink.ai/photo.jpg"

    async def fake_zveno(prompt, references, user_id, image_model="gemini"):
        calls["zveno"] += 1
        assert image_model == "gpt5", f"26e.1 модель прокинута верно: {image_model!r}"
        return "https://cdn.zveno.ai/photo.jpg"

    S.generate_image_evolink = fake_evolink
    S.generate_image_zveno = fake_zveno
    mocks, channel = _setup_generate_image_by_job_mocks()
    try:
        app = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
        job = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=25, image_model="gpt5")
        asyncio.run(S.generate_image_by_job(app, job))
        assert calls == {"evolink": 0, "zveno": 1}, f"26e.2 gpt5 остаётся на Zveno даже при флаге evolink: {calls}"
    finally:
        S.PHOTO_PROVIDER = _orig_photo_provider
        S.generate_image_evolink = _orig_evolink_fn
        S.generate_image_zveno = _orig_zveno_fn
        _teardown_generate_image_by_job_mocks(mocks, channel)


def test_block_26f_photo_provider_zveno_default_unchanged():
    # Регресс: дефолт (флаг выключен) — обе модели идут через Zveno, как
    # до этой миграции, поведение не меняется вообще.
    assert S.PHOTO_PROVIDER == "zveno", f"26f.1 дефолт флага — zveno (выключено): {S.PHOTO_PROVIDER!r}"
    _orig_evolink_fn = S.generate_image_evolink
    _orig_zveno_fn = S.generate_image_zveno
    calls = {"evolink": 0, "zveno": 0}

    async def fake_evolink(prompt, references, user_id):
        calls["evolink"] += 1
        return "https://cdn.evolink.ai/photo.jpg"

    async def fake_zveno(prompt, references, user_id, image_model="gemini"):
        calls["zveno"] += 1
        return "https://cdn.zveno.ai/photo.jpg"

    S.generate_image_evolink = fake_evolink
    S.generate_image_zveno = fake_zveno
    mocks, channel = _setup_generate_image_by_job_mocks()
    try:
        app = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
        job = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=5, image_model="gemini")
        asyncio.run(S.generate_image_by_job(app, job))
        assert calls == {"evolink": 0, "zveno": 1}, f"26f.2 флаг выключен -> всё на Zveno: {calls}"
    finally:
        S.generate_image_evolink = _orig_evolink_fn
        S.generate_image_zveno = _orig_zveno_fn
        _teardown_generate_image_by_job_mocks(mocks, channel)
