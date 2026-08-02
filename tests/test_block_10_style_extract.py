# -*- coding: utf-8 -*-
"""Блок 10: style_extract — двухшаговый пайплайн «Образ с референса»."""
import asyncio
from unittest.mock import AsyncMock

from test_helpers import S, png_data_url, make_run_generation_context


def test_block_10_style_extract():
    _rg_orig = {
        name: getattr(S, name)
        for name in (
            "create_user_if_not_exists", "get_avatar_urls", "get_active_avatar_kind",
            "try_use_free_generation", "extract_style_description_from_reference",
        )
    }
    S.create_user_if_not_exists = lambda *a, **k: None
    S.get_avatar_urls = lambda uid: {}
    S.get_active_avatar_kind = lambda uid: None
    S.try_use_free_generation = lambda uid, max_per_day: True

    _ref1 = png_data_url(color=(10, 10, 10, 255))
    _ref2 = png_data_url(color=(20, 20, 20, 255))

    # 10.1: успешная экстракция — второе фото не попадает в references job'а,
    # его текстовое описание дописывается в промт
    S.extract_style_description_from_reference = AsyncMock(return_value="каре, блонд, нюдовая помада")
    st10 = S.UserState(prompt="базовый промт стиля", references=[_ref1, _ref2], style_extract=True)
    update, context, message = make_run_generation_context(st10, user_id=951)
    while not S.generation_queue.empty():
        S.generation_queue.get_nowait()
    asyncio.run(S.run_generation(update, context))
    S.queued_user_ids.discard(951)
    job10 = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
    assert job10 is not None and job10.references == [_ref1], (
        f"10.1 второе фото не попадает в references job'а: {job10.references if job10 else None}"
    )
    assert job10 is not None and "каре, блонд, нюдовая помада" in job10.prompt, (
        f"10.2 описание стиля дописано в промт: {job10.prompt if job10 else None}"
    )
    assert context.user_data["state"].style_extract is False, (
        "10.3 style_extract сброшен после использования (one-shot)"
    )

    # 10.4: extract вернул None (сбой vision-вызова) — откат на старое поведение,
    # оба фото уходят в job, юзер предупреждён
    S.extract_style_description_from_reference = AsyncMock(return_value=None)
    st10b = S.UserState(prompt="базовый промт стиля", references=[_ref1, _ref2], style_extract=True)
    update, context, message = make_run_generation_context(st10b, user_id=952)
    while not S.generation_queue.empty():
        S.generation_queue.get_nowait()
    asyncio.run(S.run_generation(update, context))
    S.queued_user_ids.discard(952)
    job10b = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
    assert job10b is not None and job10b.references == [_ref1, _ref2], (
        f"10.4 сбой vision-вызова -> оба фото в job (откат на старое поведение): "
        f"{job10b.references if job10b else None}"
    )
    warn_texts = [c.args[0] for c in message.reply_text.await_args_list]
    assert any("не удалось разобрать референс" in t.lower() for t in warn_texts), (
        f"10.5 юзер предупреждён о сбое разбора референса: {warn_texts}"
    )

    # 10.6: флаг не выставлен (обычный стиль) — оба фото уходят как обычно, vision не вызывается
    S.extract_style_description_from_reference = AsyncMock(return_value="не должно вызваться")
    st10c = S.UserState(prompt="базовый промт стиля", references=[_ref1, _ref2], style_extract=False)
    update, context, message = make_run_generation_context(st10c, user_id=953)
    while not S.generation_queue.empty():
        S.generation_queue.get_nowait()
    asyncio.run(S.run_generation(update, context))
    S.queued_user_ids.discard(953)
    job10c = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
    assert (job10c is not None and job10c.references == [_ref1, _ref2]
            and not S.extract_style_description_from_reference.await_args_list), (
        f"10.6 style_extract=False -> vision не вызывается, оба фото в job: "
        f"{job10c.references if job10c else None}"
    )

    # 10.7: гейт — style_extract=True, 0 фото -> генерация не запускается,
    # job в очередь не попадает, юзер получает понятный запрос на 2 фото
    S.extract_style_description_from_reference = AsyncMock(return_value="не должно вызваться")
    st10d = S.UserState(prompt="базовый промт стиля", references=[], style_extract=True)
    update, context, message = make_run_generation_context(st10d, user_id=954)
    while not S.generation_queue.empty():
        S.generation_queue.get_nowait()
    asyncio.run(S.run_generation(update, context))
    S.queued_user_ids.discard(954)
    job10d = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
    assert job10d is None, "10.7 гейт: 0 фото -> job не создаётся"
    gate_texts_d = [c.args[0] for c in message.reply_text.await_args_list]
    assert any("нужны 2 фото" in t for t in gate_texts_d), (
        f"10.8 гейт: 0 фото -> просит 2 фото по порядку: {gate_texts_d}"
    )

    # 10.9: гейт — style_extract=True, 1 фото -> тоже блокируется
    st10e = S.UserState(prompt="базовый промт стиля", references=[_ref1], style_extract=True)
    update, context, message = make_run_generation_context(st10e, user_id=955)
    while not S.generation_queue.empty():
        S.generation_queue.get_nowait()
    asyncio.run(S.run_generation(update, context))
    S.queued_user_ids.discard(955)
    job10e = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
    assert job10e is None, "10.9 гейт: 1 фото -> job не создаётся"
    gate_texts_e = [c.args[0] for c in message.reply_text.await_args_list]
    assert any("есть только 1 фото" in t.lower() for t in gate_texts_e), (
        f"10.10 гейт: 1 фото -> просит второе фото: {gate_texts_e}"
    )
    assert not S.extract_style_description_from_reference.await_args_list, (
        "10.11 гейт не вызывает vision (не тратим на неполный набор фото)"
    )

    for _name, _fn in _rg_orig.items():
        setattr(S, _name, _fn)

    # 10.12: _set_style_extract чистит буфер референсов при включении (P0
    # 2026-07-17 — персистентный буфер путал лицо с рефом стиля)
    st10f = S.UserState(references=["старое-фото-с-прошлого-теста"])
    S._set_style_extract(st10f, True)
    assert st10f.references == [] and st10f.style_extract is True, (
        f"10.12 _set_style_extract(True) очищает старый буфер references: {st10f.references}"
    )
    S._set_style_extract(st10f, False)
    assert st10f.style_extract is False, (
        "10.13 _set_style_extract(False) не трогает буфер (не режим style_extract)"
    )

    # 10.14: photo_draft_text/kb — статус по слотам и кнопка «Запустить» только при 2/2
    st10g = S.UserState(prompt="стиль", references=[], style_extract=True)
    assert "0/2" in S.photo_draft_text(st10g, 956), "10.15 photo_draft_text 0/2"
    kb_0 = S.photo_draft_kb(st10g, 956)
    cbs_0 = [b.callback_data for row in kb_0.inline_keyboard for b in row]
    assert "generate" not in cbs_0, f"10.16 кнопки: 0/2 -> нет 'generate': {cbs_0}"

    st10g.references = [_ref1]
    assert "1/2" in S.photo_draft_text(st10g, 956), "10.17 photo_draft_text 1/2"
    cbs_1 = [b.callback_data for row in S.photo_draft_kb(st10g, 956).inline_keyboard for b in row]
    assert "generate" not in cbs_1, f"10.18 кнопки: 1/2 -> нет 'generate': {cbs_1}"

    st10g.references = [_ref1, _ref2]
    assert "2/2" in S.photo_draft_text(st10g, 956), "10.19 photo_draft_text 2/2"
    cbs_2 = [b.callback_data for row in S.photo_draft_kb(st10g, 956).inline_keyboard for b in row]
    assert "generate" in cbs_2, f"10.20 кнопки: 2/2 -> есть 'generate': {cbs_2}"
