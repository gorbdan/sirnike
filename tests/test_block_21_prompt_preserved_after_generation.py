# -*- coding: utf-8 -*-
"""Блок 21: промт (обычно из библиотеки стилей) не сбрасывается после
генерации (просьба Ани 2026-08-03) — юзер шлёт новое фото и получает тот
же стиль без повторного похода в библиотеку."""
import asyncio

from test_helpers import S, png_data_url, make_run_generation_context


def test_block_21_prompt_kept_after_successful_generation():
    _orig = {
        name: getattr(S, name)
        for name in ("create_user_if_not_exists", "get_avatar_urls", "get_active_avatar_kind",
                     "try_use_free_generation")
    }
    S.create_user_if_not_exists = lambda *a, **k: None
    S.get_avatar_urls = lambda uid: {}
    S.get_active_avatar_kind = lambda uid: None
    S.try_use_free_generation = lambda uid, max_per_day: True

    ref = png_data_url(color=(30, 30, 30, 255))
    st = S.UserState(prompt="Стиль «Кино-портрет» из библиотеки", references=[ref], image_model="gpt5")
    update, context, message = make_run_generation_context(st, user_id=960)
    while not S.generation_queue.empty():
        S.generation_queue.get_nowait()

    try:
        asyncio.run(S.run_generation(update, context))
    finally:
        S.queued_user_ids.discard(960)
        for name, fn in _orig.items():
            setattr(S, name, fn)

    job = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
    assert job is not None, "21.1 генерация реально поставлена в очередь"

    new_state = context.user_data["state"]
    assert new_state is not st, "21.2 состояние пересоздано (черновик-референсы очищены)"
    assert new_state.prompt == "Стиль «Кино-портрет» из библиотеки", (
        f"21.3 промт СОХРАНЁН после генерации (не сброшен в ''): {new_state.prompt!r}"
    )
    assert new_state.references == [], "21.4 фото-референсы всё же очищены (не копим старые кадры)"
    assert new_state.image_model == "gpt5", "21.5 выбранная модель картинок по-прежнему сохраняется"
