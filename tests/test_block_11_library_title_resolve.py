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
