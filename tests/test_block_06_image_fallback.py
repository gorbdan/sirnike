# -*- coding: utf-8 -*-
"""Блок 6: fallback картинок при IMAGE_PROHIBITED_CONTENT."""
import asyncio
import types
from unittest.mock import AsyncMock

from test_helpers import S, FakeResp, FakeSession, OK_PNG_B64


def test_block_06_image_fallback():
    ok_png_b64 = OK_PNG_B64

    def make_resp_for(payload):
        model = payload.get("model", "")
        if model == S.ZVENO_IMAGE_MODEL:  # banana 2 -> фильтр
            body = {"choices": [{"message": {"content": "blocked"},
                                 "finish_reason": "stop", "native_finish_reason": "IMAGE_PROHIBITED_CONTENT"}]}
        else:  # fallback Pro -> картинка
            body = {"choices": [{"message": {"images": [
                {"url": "data:image/png;base64," + ok_png_b64}]}, "finish_reason": "stop"}]}
        return FakeResp(status=200, body=body)

    img_calls = []

    class FakeImgSession(FakeSession):
        def post(self, url, headers=None, json=None, timeout=None, **kw):
            img_calls.append(json)
            return make_resp_for(json)

    async def fake_persist(ref):
        return "https://example.com/x.png"

    _orig = {}
    for name in ("_persist_image_ref", "send_generation_result_by_url", "add_generation_history",
                 "log_generation_event", "add_izyminki", "restore_free_generation", "maybe_send_avatar_nudge"):
        _orig[name] = getattr(S, name)

    _orig_cs = S.aiohttp.ClientSession

    S._persist_image_ref = fake_persist
    S.send_generation_result_by_url = AsyncMock()
    S.add_generation_history = lambda **kw: None
    S.log_generation_event = lambda **kw: None
    S.add_izyminki = lambda *a, **kw: None
    S.restore_free_generation = lambda *a, **kw: None
    S.aiohttp.ClientSession = FakeImgSession
    _orig_channel = S.RESULTS_CHANNEL_ID
    S.RESULTS_CHANNEL_ID = ""

    app = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: c.close() if hasattr(c, "close") else None)
    job = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=5, image_model="gemini")
    img_calls.clear()
    asyncio.run(S.generate_image_by_job(app, job))
    models_called = [c.get("model") for c in img_calls]
    assert len(img_calls) >= 2, f"6.1 banana отказала -> запрошен fallback: {models_called}"
    assert models_called.count(S.ZVENO_IMAGE_MODEL) == 1, (
        f"6.2 banana вызвана ровно 1 раз (не ретраится после фильтра): {models_called}"
    )
    assert any("3-pro-image" in (m or "") for m in models_called), (
        f"6.3 fallback = gemini-3-pro: {models_called}"
    )
    assert S.send_generation_result_by_url.await_count == 1, "6.4 итог — успех (картинка отправлена)"

    # 6.5: всё PROHIBITED -> рефанд и сообщение об ошибке
    class FakeAllBlockedSession(FakeSession):
        def post(self, url, headers=None, json=None, timeout=None, **kw):
            img_calls.append(json)
            body = {"choices": [{"message": {"content": "no"},
                                 "finish_reason": "stop", "native_finish_reason": "IMAGE_PROHIBITED_CONTENT"}]}
            return FakeResp(status=200, body=body)

    refunds = []
    S.add_izyminki = lambda uid, amount: refunds.append((uid, amount))
    S.aiohttp.ClientSession = FakeAllBlockedSession
    S.send_generation_result_by_url.reset_mock()
    app2 = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
    job2 = S.GenerationJob(chat_id=1, user_id=42, prompt="тест", references=[], cost=5, image_model="gemini")
    img_calls.clear()
    asyncio.run(S.generate_image_by_job(app2, job2))
    assert S.send_generation_result_by_url.await_count == 0, "6.5 при полном отказе картинка НЕ отправлена"
    assert refunds == [(42, 5)], f"6.6 изюминки возвращены: {refunds}"
    assert app2.bot.send_message.await_count >= 1, "6.7 пользователю отправлено сообщение об ошибке"

    # 6.7b-d: MASHAGPT и YESAPI ветки generate_image_by_job — после рефакторинга
    # на общий _handle_generation_failure (дедуп ZVENO/MASHAGPT/YESAPI, 2026-08-01)
    # рефанд+сообщение+лог должны работать так же, как раньше по отдельности.
    _orig_ai_provider_b6 = S.AI_PROVIDER
    _orig_mashagpt_key = S.MASHAGPT_API_KEY

    # MASHAGPT: пустой ключ -> мгновенный Exception -> хвост отказа
    refunds.clear()
    S.AI_PROVIDER = "MASHAGPT"
    S.MASHAGPT_API_KEY = ""
    app_mg = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
    job_mg = S.GenerationJob(chat_id=1, user_id=43, prompt="тест", references=[], cost=7, image_model="gemini")
    asyncio.run(S.generate_image_by_job(app_mg, job_mg))
    assert refunds == [(43, 7)], f"6.7b MASHAGPT: изюминки возвращены при пустом ключе: {refunds}"
    assert app_mg.bot.send_message.await_count >= 1, "6.7c MASHAGPT: юзеру отправлено сообщение об ошибке"
    S.MASHAGPT_API_KEY = _orig_mashagpt_key

    # YESAPI: провайдер по умолчанию (не ZVENO/MASHAGPT) -> HTTP 500 -> хвост отказа
    refunds.clear()
    S.AI_PROVIDER = "YESAPI"

    class FakeYesapiFailSession(FakeSession):
        def post(self, url, headers=None, json=None, timeout=None, **kw):
            return FakeResp(status=500, body={"success": False, "message": "internal error"})

    S.aiohttp.ClientSession = FakeYesapiFailSession
    _orig_sleep_b6 = S.asyncio.sleep
    S.asyncio.sleep = AsyncMock(return_value=None)  # пропускаем реальные 5с между попытками
    app_ya = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
    job_ya = S.GenerationJob(chat_id=1, user_id=44, prompt="тест", references=[], cost=9, image_model="gemini")
    asyncio.run(S.generate_image_by_job(app_ya, job_ya))
    S.asyncio.sleep = _orig_sleep_b6
    assert refunds == [(44, 9)], "6.7d YESAPI: изюминки возвращены после 2 неудачных попыток"
    assert app_ya.bot.send_message.await_count >= 1, "6.7e YESAPI: юзеру отправлено сообщение об ошибке"

    S.AI_PROVIDER = _orig_ai_provider_b6

    # 6.8: gpt5 в job -> первая модель gpt-5-image
    class FakeOkSession(FakeSession):
        def post(self, url, headers=None, json=None, timeout=None, **kw):
            img_calls.append(json)
            body = {"choices": [{"message": {"images": [{"url": "data:image/png;base64," + ok_png_b64}]}}]}
            return FakeResp(status=200, body=body)

    S.aiohttp.ClientSession = FakeOkSession
    S.send_generation_result_by_url.reset_mock()
    job3 = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=10, image_model="gpt5")
    img_calls.clear()
    asyncio.run(S.generate_image_by_job(types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None), job3))
    assert img_calls and img_calls[0].get("model") == S.ZVENO_GPT5_IMAGE_MODEL, (
        f"6.8 job.image_model=gpt5 -> модель openai/gpt-5-image: "
        f"{img_calls[0].get('model') if img_calls else None}"
    )
    assert S.send_generation_result_by_url.await_count == 1, "6.9 gpt5 успех с первой попытки"

    # 6.10: non-2xx (400) на 1-й попытке -> continue -> успех на 2-й
    attempt_counter = {"n": 0}

    class FakeFlakySession(FakeSession):
        def post(self, url, headers=None, json=None, timeout=None, **kw):
            attempt_counter["n"] += 1
            if attempt_counter["n"] == 1:
                return FakeResp(status=400, body={"error": {"message": "bad image_config"}})
            body = {"choices": [{"message": {"images": [{"url": "data:image/png;base64," + ok_png_b64}]}}]}
            return FakeResp(status=200, body=body)

    S.aiohttp.ClientSession = FakeFlakySession
    S.send_generation_result_by_url.reset_mock()
    job4 = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=5, image_model="gemini")
    asyncio.run(S.generate_image_by_job(types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None), job4))
    assert S.send_generation_result_by_url.await_count == 1, (
        f"6.10 HTTP 400 на 1-й попытке не валит генерацию: attempts={attempt_counter['n']}"
    )

    for name, fn in _orig.items():
        setattr(S, name, fn)
    S.aiohttp.ClientSession = _orig_cs
    S.RESULTS_CHANNEL_ID = _orig_channel
