# -*- coding: utf-8 -*-
"""Блок 1: модель картинок."""
from test_helpers import S


def test_block_01_image_model():
    st = S.UserState()
    assert S.get_image_model(st) == "gemini", "1.1 дефолт image_model=gemini"
    st.image_model = "gpt5"
    assert S.get_image_model(st) == "gpt5", "1.2 выбор gpt5 работает"
    _orig_gpt5_enabled = S.GPT5_IMAGE_ENABLED
    S.GPT5_IMAGE_ENABLED = False
    assert S.get_image_model(st) == "gemini", "1.3 gpt5 при выключенном флаге -> gemini"
    S.GPT5_IMAGE_ENABLED = _orig_gpt5_enabled

    assert S.get_image_model_label("gpt5") == "GPT-5 Image", "1.4 label gpt5"
    assert S.get_image_model_label("gemini") == "Nano Banana 2", (
        f"1.5 label gemini (env 3.1-flash) = Nano Banana 2: "
        f"got={S.get_image_model_label('gemini')!r} env={S.ZVENO_IMAGE_MODEL}"
    )

    assert S.get_image_model_base_cost("gemini") == S.BASE_GENERATION_COST, "1.6 базовая цена gemini"
    assert S.get_image_model_base_cost("gpt5") == 25, (
        f"1.7 базовая цена gpt5 = 25: got={S.get_image_model_base_cost('gpt5')}"
    )
    assert S.calc_generation_cost(None, "gemini") == 5, "1.8 calc_generation_cost gemini без рефов"
    assert S.calc_generation_cost(None, "gpt5") == 25, "1.9 calc_generation_cost gpt5 без рефов"
    _orig_ref_cost = S.REFERENCE_COST
    S.REFERENCE_COST = 2
    assert S.calc_generation_cost(["x"], "gpt5") == 27, "1.10 надбавка за рефы складывается"
    S.REFERENCE_COST = _orig_ref_cost

    st.image_model = "gemini"
    kb = S.image_model_menu_kb(st)
    flat = [b for row in kb.inline_keyboard for b in row]
    cbs = [b.callback_data for b in flat]
    texts = [b.text for b in flat]
    assert "image_model_set_gemini" in cbs and "image_model_set_gpt5" in cbs, (
        f"1.11 меню: есть set_gemini и set_gpt5: {cbs}"
    )
    assert any(t.startswith("● ") and "Nano Banana 2" in t for t in texts), (
        f"1.12 меню: маркер ● на выбранной gemini: {texts}"
    )
    assert any("5 🍇" in t for t in texts) and any("25 🍇" in t for t in texts), (
        f"1.13 меню: цены в кнопках: {texts}"
    )
    assert "Nano Banana 2" in S.image_model_menu_text(st) and "GPT-5 Image" in S.image_model_menu_text(st), (
        "1.14 текст меню упоминает обе модели"
    )
