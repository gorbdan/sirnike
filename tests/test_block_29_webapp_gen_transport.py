# -*- coding: utf-8 -*-
"""Блок 29: генерация из вебаппа по HTTP-очереди вместо tg.sendData
(docs/specs/2026-11-16_webapp_gen_transport.md). Воркер webapp_gen.py берёт
payload из очереди, гонит через существующий apply_webapp_prompt_payload_v2 с
синтетическим Update; кнопка «Создать» в вебаппе пропускает карточку-
подтверждение в чате (is_autostart)."""
import asyncio
import json
from unittest.mock import AsyncMock, patch

from telegram.ext import Application

from test_helpers import S
import webapp_gen as W


def _fake_db(store):
    def get(job_id):
        return store.get(job_id)

    def rec(job_id, user_id, charged, cost, status, error="", result_json="{}"):
        store[job_id] = {"job_id": job_id, "status": status, "error": error, "result": result_json}
    return get, rec


def _run(job, apply_hook, store=None):
    store = {} if store is None else store
    get, rec = _fake_db(store)
    completes = []

    async def fake_api(path, payload, timeout=20):
        if path == "complete":
            completes.append(payload)
        return {"ok": True}

    W.configure(apply_payload=apply_hook, ensure_user=lambda uid, uname: None)
    with patch.object(W, "get_studio_done_job", get), patch.object(W, "record_studio_done_job", rec), \
            patch.object(W, "_api", fake_api), patch.object(W, "_build_update", lambda app, uid, un: ("U", "C")):
        asyncio.run(W._handle_job(object(), job))
    return completes, store


def test_block_29a_launched_job_completes_done_with_progress_id():
    seen = {}

    async def hook(update, context, payload):
        seen["autostart"] = W.is_autostart()
        seen["job_id"] = W.current_job_id()
        W.mark_launched()
        return True

    completes, store = _run({"id": "j1", "user_id": 5, "payload": {"action": "sg", "product": "video"}}, hook)
    assert seen == {"autostart": True, "job_id": "j1"}, f"29a.1 {seen}"
    assert len(completes) == 1 and completes[0]["status"] == "done", f"29a.2 {completes}"
    res = completes[0]["result"]
    assert res["launched"] is True and res["progress_id"] == "j1" and res["product"] == "video", f"29a.3 {res}"
    assert store["j1"]["status"] == "done", "29a.4 результат записан в журнал"


def test_block_29b_validation_refusal_returns_chat_text_to_webapp():
    async def hook(update, context, payload):
        W._replies.get().append("Нужно описание или хотя бы одно фото")
        return True  # как у реальных обработчиков: отказ = reply + return True

    completes, _ = _run({"id": "j2", "user_id": 5, "payload": {"action": "sg"}}, hook)
    c = completes[0]
    assert c["status"] == "error" and c["error"] == "not_started", f"29b.1 {c}"
    assert c["result"]["messages"] == ["Нужно описание или хотя бы одно фото"], f"29b.2 {c}"
    assert c["result"]["progress_id"] == "", "29b.3 прогресса нет, раз не запустилось"


def test_block_29c_redelivered_job_is_not_run_twice():
    calls = []

    async def hook(update, context, payload):
        calls.append(1)
        W.mark_launched()
        return True

    store = {}
    job = {"id": "j3", "user_id": 5, "payload": {"action": "sg"}}
    _run(job, hook, store)
    completes, _ = _run(job, hook, store)
    assert len(calls) == 1, f"29c.1 обработчик (и списание) не должен выполниться второй раз: {calls}"
    assert completes[0]["status"] == "done", "29c.2 повторно доставлен прежний результат"


def test_block_29d_job_interrupted_by_restart_is_refused_not_rerun():
    calls = []

    async def hook(update, context, payload):
        calls.append(1)
        return True

    store = {"j4": {"job_id": "j4", "status": "started", "error": "", "result": "{}"}}
    completes, store = _run({"id": "j4", "user_id": 5, "payload": {"action": "sg"}}, hook, store)
    assert not calls, "29d.1 после рестарта бот не запускает генерацию повторно"
    assert completes[0]["status"] == "error" and completes[0]["error"] == "interrupted", f"29d.2 {completes}"


def test_block_29e_bad_job_rejected():
    completes, _ = _run({"id": "j5", "user_id": 5, "payload": {}}, AsyncMock())
    assert completes[0]["error"] == "bad_job", f"29e.1 {completes}"


def test_block_29f_autostart_off_outside_queue():
    assert W.is_autostart() is False, "29f.1 sendData-путь карточку не пропускает"
    assert W.current_job_id() == ""


def test_block_29g_real_update_and_context_reply_to_chat():
    app = Application.builder().token("123456:TESTTOKEN").build()
    update, context = W._build_update(app, 4242, "anya")
    assert update.effective_user.id == 4242 and update.effective_message is update.message
    assert context.application is app, "29g.1 контекст привязан к приложению"
    sent = []

    async def fake_send(self, chat_id, text, *a, **kw):
        sent.append((chat_id, text))

    async def _go():
        W._replies.set([])
        await update.effective_message.reply_text("привет")
        return W._replies.get()

    with patch("telegram.Bot.send_message", fake_send):
        copies = asyncio.run(_go())
    assert sent == [(4242, "привет")], f"29g.2 ответ ушёл в чат юзера: {sent}"
    assert copies == ["привет"], f"29g.3 копия текста для вебаппа: {copies}"


def test_block_29h_video_autostart_launches_without_confirmation_card():
    import types
    launched = []

    async def fake_launch(update, context):
        launched.append(update.effective_user.id)
        return None

    reply = AsyncMock()
    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=31001, username="t"),
        effective_message=types.SimpleNamespace(reply_text=reply),
        effective_chat=types.SimpleNamespace(id=31001),
    )
    context = types.SimpleNamespace(user_data={}, application=None, bot=AsyncMock())
    payload = {"action": "sg", "product": "video", "prompt": "кот", "refs": ["https://i.ibb.co/a.jpg"],
               "video_model": "seedance2_fast"}
    orig = S._launch_video_generation
    S._launch_video_generation = fake_launch
    _flags = (S.VIDEO_CONSTRUCTOR_ENABLED, S.SEEDANCE_ENABLED)
    S.VIDEO_CONSTRUCTOR_ENABLED = S.SEEDANCE_ENABLED = True

    async def _go():
        W._autostart.set(True)
        flag = []
        W._launched.set(flag)
        ok = await S._apply_webapp_generation_video(update, context, payload)
        return ok, flag

    try:
        ok, flag = asyncio.run(_go())
    finally:
        S._launch_video_generation = orig
        S.VIDEO_CONSTRUCTOR_ENABLED, S.SEEDANCE_ENABLED = _flags
    assert ok is True and flag == [True], f"29h.1 запущено и помечено: {ok} {flag}"
    assert launched == [31001], f"29h.2 run_seedance запущен: {launched}"
    reply.assert_not_awaited()  # 29h.3 карточка «Запустить» в чат не отправлялась


def test_block_29i_video_without_autostart_still_shows_card():
    import types
    reply = AsyncMock()
    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=31002, username="t"),
        effective_message=types.SimpleNamespace(reply_text=reply),
        effective_chat=types.SimpleNamespace(id=31002),
    )
    context = types.SimpleNamespace(user_data={}, application=None, bot=AsyncMock())
    payload = {"action": "sg", "product": "video", "prompt": "кот", "refs": ["https://i.ibb.co/a.jpg"]}
    _flags = (S.VIDEO_CONSTRUCTOR_ENABLED, S.SEEDANCE_ENABLED)
    S.VIDEO_CONSTRUCTOR_ENABLED = S.SEEDANCE_ENABLED = True
    try:
        ok = asyncio.run(S._apply_webapp_generation_video(update, context, payload))
    finally:
        S.VIDEO_CONSTRUCTOR_ENABLED, S.SEEDANCE_ENABLED = _flags
    assert ok is True
    kb = reply.await_args.kwargs.get("reply_markup")
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "video_start" in datas, f"29i.1 sendData-путь без изменений, карточка с кнопкой: {datas}"


def _photo_ctx(uid):
    import types
    reply = AsyncMock()
    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=uid, username="t"),
        effective_message=types.SimpleNamespace(reply_text=reply),
        effective_chat=types.SimpleNamespace(id=uid),
    )
    context = types.SimpleNamespace(user_data={}, application=None, bot=AsyncMock())
    return update, context, reply


def _run_photo_autostart(uid, fake_run_generation, preload=None):
    update, context, reply = _photo_ctx(uid)
    orig = S.run_generation
    S.run_generation = fake_run_generation
    _flag = S.PHOTO_CONSTRUCTOR_ENABLED
    S.PHOTO_CONSTRUCTOR_ENABLED = True
    if preload:
        S.queued_user_ids.add(uid)

    async def _go():
        W._autostart.set(True)
        flag = []
        W._launched.set(flag)
        ok = await S._apply_webapp_generation_photo(update, context, {"action": "sg", "product": "photo", "description": "кот"})
        return ok, flag

    try:
        ok, flag = asyncio.run(_go())
    finally:
        S.run_generation = orig
        S.PHOTO_CONSTRUCTOR_ENABLED = _flag
        S.queued_user_ids.discard(uid)
    return ok, flag, reply


def test_block_29j_photo_autostart_marks_launched_when_enqueued():
    uid = 31010

    async def fake_run_generation(update, context):
        S.queued_user_ids.add(update.effective_user.id)  # как настоящий run_generation при успешной постановке

    ok, flag, reply = _run_photo_autostart(uid, fake_run_generation)
    assert ok is True and flag == [True], f"29j.1 {ok} {flag}"
    reply.assert_not_awaited()  # 29j.2 карточка «Запустить генерацию» не показывается


def test_block_29k_photo_autostart_refusal_not_marked_launched():
    async def refusing(update, context):
        await update.effective_message.reply_text("Не хватает изюминок")  # слот не резервируется

    ok, flag, _ = _run_photo_autostart(31011, refusing)
    assert ok is True and flag == [], f"29k.1 отказ run_generation = не запущено: {flag}"


def test_block_29l_photo_autostart_busy_user_not_marked_launched():
    async def noop_busy(update, context):
        return None  # слот уже был занят прежним заданием — новое не встало

    ok, flag, _ = _run_photo_autostart(31012, noop_busy, preload=True)
    assert flag == [], f"29l.1 занятый юзер: чужой слот не считается запуском: {flag}"


def test_block_29m_generation_job_progress_defaults():
    job = S.GenerationJob(chat_id=1, user_id=1, prompt="p", references=[])
    assert job.progress_id == "" and job.succeeded is False, "29m.1 по умолчанию зеркала прогресса нет"


def _autostart_call(handler_name, payload, patch_name, patched, flag_names, uid):
    update, context, reply = _photo_ctx(uid)
    orig = getattr(S, patch_name)
    setattr(S, patch_name, patched)
    saved = {n: getattr(S, n) for n in flag_names}
    for n in flag_names:
        setattr(S, n, True)

    async def _go():
        W._autostart.set(True)
        flag, replies = [], []
        W._launched.set(flag)
        W._replies.set(replies)
        ok = await getattr(S, handler_name)(update, context, payload)
        return ok, flag, replies

    try:
        return (*asyncio.run(_go()), reply)
    finally:
        setattr(S, patch_name, orig)
        for n, v in saved.items():
            setattr(S, n, v)
        S.queued_user_ids.discard(uid)
        S.processing_user_ids.discard(uid)


def test_block_29n_avatar_autostart_launches_and_refusal_goes_to_webapp():
    uid = 31020

    async def ok_start(update, context, query, user):
        S.queued_user_ids.add(user.id)

    ok, flag, replies, reply = _autostart_call(
        "_apply_webapp_generation_avatar",
        {"action": "sg", "product": "avatar", "avatar_type": "female", "refs": ["https://i.ibb.co/a.jpg"]},
        "_cb_avatar_gen_start", ok_start, ["AVATAR_CONSTRUCTOR_ENABLED"], uid)
    assert ok is True and flag == [True], f"29n.1 {ok} {flag}"
    reply.assert_not_awaited()  # 29n.2 карточки в чате нет

    async def refuse(update, context, query, user):
        await query.answer("Сырник уже занят другой задачей. Подожди.", show_alert=True)

    ok, flag, replies, _ = _autostart_call(
        "_apply_webapp_generation_avatar",
        {"action": "sg", "product": "avatar", "avatar_type": "female", "refs": ["https://i.ibb.co/a.jpg"]},
        "_cb_avatar_gen_start", refuse, ["AVATAR_CONSTRUCTOR_ENABLED"], uid + 1)
    assert flag == [] and replies == ["Сырник уже занят другой задачей. Подожди."], f"29n.3 {flag} {replies}"


def test_block_29o_midjourney_autostart_launches():
    uid = 31030

    async def ok_start(update, context, query, user):
        S.processing_user_ids.add(user.id)

    ok, flag, _, reply = _autostart_call(
        "_apply_webapp_generation_midjourney",
        {"action": "sg", "product": "midjourney", "description": "замок на облаке"},
        "_cb_mj_generate", ok_start, ["MIDJOURNEY_CONSTRUCTOR_ENABLED", "MIDJOURNEY_ENABLED"], uid)
    assert ok is True and flag == [True], f"29o.1 {ok} {flag}"
    reply.assert_not_awaited()


def test_block_29p_enhance_autostart_runs_generation():
    uid = 31040

    async def fake_run_generation(update, context):
        S.queued_user_ids.add(update.effective_user.id)

    ok, flag, _, reply = _autostart_call(
        "_apply_webapp_generation_enhance",
        {"action": "sg", "product": "enhance", "refs": ["https://i.ibb.co/a.jpg", "https://i.ibb.co/b.jpg"]},
        "run_generation", fake_run_generation, ["ENHANCE_CONSTRUCTOR_ENABLED"], uid)
    assert ok is True and flag == [True], f"29p.1 {ok} {flag}"
    reply.assert_not_awaited()


def test_block_29q_progress_attached_only_for_webapp_jobs():
    created = []

    async def fake_create(pid, uid, product, meta):
        created.append((pid, product))
        return True

    orig, orig_flag = S.gen_progress_create, S.GEN_PROGRESS_ENABLED
    S.gen_progress_create, S.GEN_PROGRESS_ENABLED = fake_create, True
    try:
        job = S.GenerationJob(chat_id=1, user_id=1, prompt="p", references=[], cost=3)
        asyncio.run(S._attach_webapp_progress(job, 1, "avatar"))
        assert job.progress_id == "" and created == [], "29q.1 вне очереди вебаппа зеркала нет"

        async def _go():
            W._job_id.set("jobX")
            await S._attach_webapp_progress(job, 1, "avatar")
        asyncio.run(_go())
        assert job.progress_id == "jobX" and created == [("jobX", "avatar")], f"29q.2 {job.progress_id} {created}"
    finally:
        S.gen_progress_create, S.GEN_PROGRESS_ENABLED = orig, orig_flag
