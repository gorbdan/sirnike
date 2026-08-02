# -*- coding: utf-8 -*-
"""Блок 10b: «Новинки» с рассинхроном cat_idx/item_idx — резолв title по промту."""
import asyncio

from test_helpers import S, make_webapp_update_context


def test_block_11_library_title_resolve():
    # Реальный стиль из PROMPT_LIBRARY, но с индексами, указывающими на ДРУГОЙ
    # (несуществующий на этой позиции) стиль — воспроизводит «Новинки», которые
    # шлют позицию в отфильтрованном списке, а не в реальной категории (аудиты
    # 07-02/07-07/07-31). Раньше title откатывался к литералу «шаблон».
    _real_item = S.PROMPT_LIBRARY[0]["items"][0]
    _real_prompt = _real_item["prompt"]
    update10b, context10b, msg10b = make_webapp_update_context()
    asyncio.run(S.apply_webapp_prompt_payload_v2(update10b, context10b, {
        "action": "set_prompt",
        "prompt": _real_prompt,
        "cat_idx": 999, "item_idx": 999,  # заведомо не существует
    }))
    _texts10b = [c.args[0] for c in msg10b.reply_text.await_args_list]
    assert any("шаблон»" not in t and ("Стиль «" in t or "Готово" in t) for t in _texts10b), (
        f"10b.1 title резолвится по промту, а не остаётся «шаблон»: {_texts10b}"
    )
    assert context10b.user_data["state"].prompt == _real_prompt, "10b.2 промт сохранён в состояние"


def test_block_11b_empty_prompt_no_template_fallback():
    # Живой прод-баг 2026-08-02: индексы не резолвятся И payload не прислал
    # prompt вообще (prompt_len=0 в логе WEB_APP_DATA) — раньше это молча
    # уходило В САМУ ГЕНЕРАЦИЮ как промт "шаблон" (video_prompt='шаблон' в
    # проде), тратя изюминки на бессмысленный запрос. Теперь честный отказ.
    update10c, context10c, msg10c = make_webapp_update_context()
    applied = asyncio.run(S.apply_webapp_prompt_payload_v2(update10c, context10c, {
        "action": "set_video_prompt",
        "prompt": "",
        "cat_idx": 999, "item_idx": 999,  # заведомо не существует, resolve не найдёт
    }))
    state = context10c.user_data.get("state")
    assert "state" not in context10c.user_data or state.video_prompt != "шаблон", (
        f"10b.3 пустой prompt + неверные индексы -> НЕ применяется как 'шаблон': "
        f"{getattr(state, 'video_prompt', None)}"
    )
    texts = [c.args[0] for c in msg10c.reply_text.await_args_list]
    assert applied is True and any(
        "Библиотек" in t or "не удалось" in t.lower() for t in texts
    ), f"10b.4 юзер получает честный отказ, не тишину: {texts}"
