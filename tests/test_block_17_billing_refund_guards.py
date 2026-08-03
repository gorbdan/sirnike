# -*- coding: utf-8 -*-
"""Блок 17: денежные гварды генерации (баг-ресерч 2026-08-02).

Три прод-бага одной зоны:
  17a. generation_succeeded ставился ДО доставки фото (ZVENO/MASHAGPT) —
       сбой скачивания/отправки после ответа провайдера оставлял юзера
       без фото и без рефанда.
  17b. Успешная доставка + сбой пост-доставочного хвоста НЕ должны слать
       юзеру «что-то пошло не так» и рефандить (двойное начисление).
  17c. YesAPI: сбой хвоста после успешного send_photo запускал ВСЮ
       генерацию заново (дубль фото, повторный расход RPOINTS), а при
       неудаче ретрая — рефанд за уже доставленный результат.
  17d. Аватар: списание шло ДО проверки живости __img__-рефов — после
       рестарта бота запрос уходил без фото юзера, «успех» без рефанда.
"""
import asyncio
import base64
import json
import types
from unittest.mock import AsyncMock

from test_helpers import S, FakeResp, FakeSession, OK_PNG_B64


def _patch(names):
    return {name: getattr(S, name) for name in names}


def _restore(saved):
    for name, fn in saved.items():
        setattr(S, name, fn)


def test_block_17a_delivery_failure_refunds():
    saved = _patch(("generate_image_zveno", "send_generation_result_by_url",
                    "add_generation_history", "log_generation_event",
                    "add_izyminki", "restore_free_generation", "_persist_image_ref"))
    _orig_provider = S.AI_PROVIDER
    refunds = []
    try:
        S.AI_PROVIDER = "ZVENO"
        S.generate_image_zveno = AsyncMock(return_value="https://cdn.example/gone.png")
        S.send_generation_result_by_url = AsyncMock(side_effect=Exception("Не удалось скачать изображение: 404"))
        S.add_generation_history = lambda **kw: None
        S.log_generation_event = lambda **kw: None
        S.add_izyminki = lambda uid, amount: refunds.append((uid, amount))
        S.restore_free_generation = lambda uid: refunds.append((uid, "free"))

        app = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
        job = S.GenerationJob(chat_id=1, user_id=171, prompt="тест", references=[], cost=6, image_model="gemini")
        asyncio.run(S.generate_image_by_job(app, job))

        assert refunds == [(171, 6)], (
            f"17a.1 провайдер дал URL, но доставка упала -> изюминки ВОЗВРАЩЕНЫ: {refunds}"
        )
        texts = [c.kwargs.get("text") or (c.args[1] if len(c.args) > 1 else "")
                 for c in app.bot.send_message.await_args_list]
        assert any("не списаны" in (t or "") or "возвращ" in (t or "") for t in texts), (
            f"17a.2 юзеру сказано, что баланс не пострадал: {texts}"
        )
    finally:
        _restore(saved)
        S.AI_PROVIDER = _orig_provider


def test_block_17b_post_delivery_tail_no_refund_no_scare():
    # Прямой юнит на _handle_generation_failure: флаг «доставлено» -> ни
    # рефанда, ни пугающего сообщения поверх полученного фото.
    saved = _patch(("add_izyminki", "restore_free_generation", "log_generation_event"))
    refunds = []
    try:
        S.add_izyminki = lambda uid, amount: refunds.append((uid, amount))
        S.restore_free_generation = lambda uid: refunds.append((uid, "free"))
        S.log_generation_event = lambda **kw: None

        app = types.SimpleNamespace(bot=AsyncMock())
        job = S.GenerationJob(chat_id=1, user_id=172, prompt="т", references=[], cost=5, image_model="gemini")

        out = asyncio.run(S._handle_generation_failure(
            app, chat_id=1, user_id=172, job=job, error=Exception("хвост упал"),
            provider_label="ZVENO", references=[], refunded=False,
            generation_succeeded=True,
        ))
        assert refunds == [] and out is False, f"17b.1 доставлено -> рефанда нет: {refunds}"
        assert app.bot.send_message.await_count == 0, (
            "17b.2 доставлено -> НЕТ сообщения «что-то пошло не так» поверх фото"
        )

        out2 = asyncio.run(S._handle_generation_failure(
            app, chat_id=1, user_id=172, job=job, error=Exception("реальный сбой"),
            provider_label="ZVENO", references=[], refunded=False,
            generation_succeeded=False,
        ))
        assert refunds == [(172, 5)] and out2 is True, f"17b.3 НЕ доставлено -> рефанд: {refunds}"
        assert app.bot.send_message.await_count == 1, "17b.4 НЕ доставлено -> сообщение об ошибке есть"
    finally:
        _restore(saved)


def test_block_17c_yesapi_no_retry_after_delivered():
    saved = _patch(("add_izyminki", "restore_free_generation", "log_generation_event",
                    "add_generation_history", "maybe_send_avatar_nudge", "_persist_image_ref"))
    _orig_provider = S.AI_PROVIDER
    _orig_cs = S.aiohttp.ClientSession
    _orig_sleep = S.asyncio.sleep
    _orig_channel = S.RESULTS_CHANNEL_ID
    refunds = []
    start_posts = []
    png_bytes = base64.b64decode(OK_PNG_B64)

    class YesapiResp(FakeResp):
        def __init__(self, status=200, body=None, raw=None):
            super().__init__(status=status, body=body)
            self._raw = raw

        async def json(self):
            return self._body

        async def read(self):
            return self._raw or b""

    class YesapiSession(FakeSession):
        def post(self, url, headers=None, json=None, timeout=None, **kw):
            start_posts.append(url)
            return YesapiResp(body={"success": True, "results": {"generation_data": {"id": "gen1"}}})

        def get(self, url, headers=None, timeout=None, **kw):
            if "/generations/" in url:
                return YesapiResp(body={"results": {"generation_data": {
                    "status": 2, "result_url": "https://cdn.example/ok.png"}}})
            return YesapiResp(raw=png_bytes)

    try:
        S.AI_PROVIDER = "YESAPI"
        S.aiohttp.ClientSession = YesapiSession
        S.asyncio.sleep = AsyncMock(return_value=None)
        S.RESULTS_CHANNEL_ID = ""
        S.add_izyminki = lambda uid, amount: refunds.append((uid, amount))
        S.restore_free_generation = lambda uid: refunds.append((uid, "free"))
        S.log_generation_event = lambda **kw: None
        S.add_generation_history = lambda **kw: None
        S.maybe_send_avatar_nudge = AsyncMock()

        async def _persist_ok(ref):
            return ref
        S._persist_image_ref = _persist_ok

        app = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
        # Фото уходит успешно, а документ-вложение падает — раньше это
        # перезапускало всю генерацию с попытки 0.
        app.bot.send_document = AsyncMock(side_effect=Exception("Telegram timeout"))
        job = S.GenerationJob(chat_id=1, user_id=173, prompt="тест", references=[], cost=8, image_model="gemini")
        asyncio.run(S.generate_image_by_job(app, job))

        assert len(start_posts) == 1, (
            f"17c.1 после доставленного фото генерация НЕ перезапускается: posts={len(start_posts)}"
        )
        assert app.bot.send_photo.await_count == 1, "17c.2 фото отправлено ровно один раз"
        assert refunds == [], f"17c.3 рефанда за доставленное фото нет: {refunds}"
        texts = [c.kwargs.get("text") or "" for c in app.bot.send_message.await_args_list]
        assert not any("Пробую ещё раз" in t or "пошло не так" in t for t in texts), (
            f"17c.4 нет ни «пробую ещё раз», ни «что-то пошло не так»: {texts}"
        )
    finally:
        _restore(saved)
        S.AI_PROVIDER = _orig_provider
        S.aiohttp.ClientSession = _orig_cs
        S.asyncio.sleep = _orig_sleep
        S.RESULTS_CHANNEL_ID = _orig_channel


def test_block_17d_avatar_stale_refs_no_charge():
    saved = _patch(("try_use_free_generation", "spend_izyminki", "get_balance"))
    charges = []
    try:
        S.try_use_free_generation = lambda uid, n: charges.append(("free", uid)) or False
        S.spend_izyminki = lambda uid, amount: charges.append(("spend", uid, amount)) or True
        S.get_balance = lambda uid: 999

        # 17d.1-3: протухший __img__-реф (кэш пуст после «рестарта») -> отказ ДО списания
        query = types.SimpleNamespace(
            answer=AsyncMock(),
            message=types.SimpleNamespace(reply_text=AsyncMock()),
        )
        update = types.SimpleNamespace(effective_chat=types.SimpleNamespace(id=174))
        state = S.UserState()
        state.avatar_photos = ["__img_deadbeef__"]
        state.pending_avatar_kind = "female"
        state.generating_avatar = True
        context = types.SimpleNamespace(user_data={"state": state})
        user = types.SimpleNamespace(id=174, username="test")
        assert S._is_img_ref("__img_deadbeef__"), "sanity: тестовый реф распознаётся как __img__"
        assert S._resolve_image_bytes("__img_deadbeef__") is None, "sanity: рефа нет в кэше"

        asyncio.run(S._cb_avatar_gen_start(update, context, query, user))

        assert charges == [], f"17d.1 протухшие фото -> списания НЕТ: {charges}"
        texts = [c.args[0] for c in query.message.reply_text.await_args_list]
        assert any("не списаны" in t for t in texts), f"17d.2 юзеру объяснили и успокоили про баланс: {texts}"
        assert state.avatar_photos == [], "17d.3 мёртвые рефы вычищены — юзер шлёт фото заново"

        # 17d.4: живое фото (data:-URL, кэш не нужен) -> валидация пропускает к списанию
        query2 = types.SimpleNamespace(
            answer=AsyncMock(),
            message=types.SimpleNamespace(reply_text=AsyncMock()),
        )
        state2 = S.UserState()
        state2.avatar_photos = ["data:image/png;base64," + OK_PNG_B64]
        state2.pending_avatar_kind = "female"
        state2.generating_avatar = True
        context2 = types.SimpleNamespace(user_data={"state": state2})
        user2 = types.SimpleNamespace(id=175, username="test")
        asyncio.run(S._cb_avatar_gen_start(update, context2, query2, user2))
        assert ("free", 175) in charges, f"17d.4 живые фото проходят валидацию к списанию: {charges}"
    finally:
        _restore(saved)
        # Дренаж очереди/флагов, если 17d.4 успел поставить job
        S.queued_user_ids.discard(175)
        try:
            while True:
                S.generation_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
