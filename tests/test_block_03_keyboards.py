# -*- coding: utf-8 -*-
"""Блок 3: клавиатуры."""
from test_helpers import S


def test_block_03_keyboards():
    st4 = S.UserState(); st4.video_model = "kling3"
    kb4 = S.video_kb(st4)
    flat4 = [b for row in kb4.inline_keyboard for b in row]
    cbs4 = [b.callback_data for b in flat4 if b.callback_data]
    # Блок кнопок-моделей убран из полной панели (ТЗ video_panel_declutter):
    # модель видна текстом в шапке, вместо переключателей — одна кнопка смены.
    assert not any(c.startswith("video_model_") for c in cbs4), (
        f"3.1 в полной панели НЕТ кнопок video_model_*: {cbs4}"
    )
    assert "video_change_model" in cbs4, "3.2 есть кнопка «Сменить модель»"
    assert not any(b.text.startswith("● ") and "Kling" in b.text for b in flat4), (
        "3.3 модель в пикере: маркеров ● на моделях в панели нет"
    )
    assert "video_mode_720" in cbs4 and "video_mode_1080" in cbs4, (
        f"3.4 у kling3 есть кнопки качества 720/1080: {cbs4}"
    )
    assert (any(c == "video_aspect_1x1" for c in cbs4) and any(c == "video_aspect_4x3" for c in cbs4)), (
        "3.5 у kling3 есть 1:1 и 4:3 аспект"
    )
    dur_btns = [b.text for b in flat4 if (b.callback_data or "").startswith("video_duration_")]
    assert any("5с · 40 🍇" in t for t in dur_btns), f"3.6 цена в кнопке 5с = 40 🍇: {dur_btns}"

    st5 = S.UserState(); st5.video_model = "veo31"
    kb5 = S.video_kb(st5)
    cbs5 = [b.callback_data for row in kb5.inline_keyboard for b in row if b.callback_data]
    assert "video_aspect_1x1" not in cbs5 and "video_aspect_4x3" not in cbs5, (
        f"3.7 у veo31 НЕТ 1:1 и 4:3 аспекта: {cbs5}"
    )
    assert "video_aspect_16x9" in cbs5 and "video_aspect_9x16" in cbs5, (
        "3.8 у veo31 есть 16:9 и 9:16"
    )
    durs5 = [c for c in cbs5 if c.startswith("video_duration_")]
    assert set(durs5) <= {"video_duration_4", "video_duration_6", "video_duration_8"}, (
        f"3.9 duration кнопки veo31 только 4/6/8: {durs5}"
    )

    # Кнопка есть ⇔ действие возможно (docs/UI_STYLE.md, правило 0)
    st_e = S.UserState()
    cbs_e = [b.callback_data for row in S.video_kb(st_e).inline_keyboard for b in row if b.callback_data]
    assert "video_start" not in cbs_e, f"3.30 пустой видео-черновик: НЕТ video_start: {cbs_e}"
    st_f = S.UserState(); st_f.video_prompt = "закат"
    cbs_f = [b.callback_data for row in S.video_kb(st_f).inline_keyboard for b in row if b.callback_data]
    assert "video_start" in cbs_f, "3.31 видео с описанием: есть video_start"
    pd_e = S.UserState()
    cbs_pd = [b.callback_data for row in S.photo_draft_kb(pd_e).inline_keyboard for b in row if b.callback_data]
    assert ("generate" not in cbs_pd
            and any(c in cbs_pd for c in ("pl_open_webapp", "pl_open"))
            and "reset" in cbs_pd), (
        f"3.32 пустой фото-черновик: НЕТ generate, есть библиотека и меню: {cbs_pd}"
    )
    pd_f = S.UserState(); pd_f.prompt = "девушка на фоне заката"
    cbs_pf = [b.callback_data for row in S.photo_draft_kb(pd_f).inline_keyboard for b in row if b.callback_data]
    assert "generate" in cbs_pf, f"3.33 фото-черновик с описанием: есть generate: {cbs_pf}"
    assert "Стиль или описание: пока нет" in S.photo_draft_text(pd_e), (
        "3.34 текст пустого фото-черновика зовёт выбрать стиль"
    )
    assert "Описание: «девушка на фоне заката» ✅" in S.photo_draft_text(pd_f), (
        f"3.35 текст заполненного фото-черновика показывает описание ✅: {S.photo_draft_text(pd_f)}"
    )

    stxt = S.video_status_text(st4)
    assert "Kling 3.0" in stxt and "изюминок" in stxt, "3.10 статус-текст содержит Kling 3.0 и стоимость"

    # Экран выбора модели видео (первый шаг «🎬 Видео для Reels», решение Ани
    # 2026-07-31) — только модели + назад, БЕЗ длительности/формата/качества,
    # которые появляются лишь после выбора (та же панель video_kb, редактированием).
    pkb = S.video_model_picker_kb()
    pcbs = [b.callback_data for row in pkb.inline_keyboard for b in row if b.callback_data]
    assert (all(c.startswith("video_model_") or c == "avatar_back_menu" for c in pcbs)
            and "video_model_seedance2" in pcbs), (
        f"3.36 пикер модели видео: только модели + назад, без настроек: {pcbs}"
    )
    assert not any(c.startswith(("video_duration_", "video_aspect_", "video_mode_")) for c in pcbs), (
        f"3.37 пикер модели видео: нет кнопок длительности/формата/качества: {pcbs}"
    )
    # ТЗ 2026-08-01: сетка 2 в ряд — не по одной модели на всю ширину. Последний
    # ряд — «В меню» отдельно; ряды моделей не шире 2 кнопок.
    _prow_sizes = [len(r) for r in pkb.inline_keyboard]
    assert (all(n <= 2 for n in _prow_sizes[:-1]) and _prow_sizes[-1] == 1
            and any(n == 2 for n in _prow_sizes[:-1])), (
        f"3.37b пикер: ряды моделей по 2 кнопки, «В меню» отдельным рядом: {_prow_sizes}"
    )

    # ТЗ video_panel_declutter: пикер не показывается повторно, если модель уже
    # выбиралась в этой сессии; «Сменить модель» возвращает в пикер; reset
    # переносит выбор как липкую настройку.
    st_vp = S.UserState()
    assert st_vp.video_model_picked is False, "3.38 свежий стейт: video_model_picked=False"

    kb6 = S.result_actions_kb(user_id=123, bot_username="TestBot")
    cbs6 = [b.callback_data for row in kb6.inline_keyboard for b in row if b.callback_data]
    assert "animate_last" in cbs6, f"3.11 result_actions с user_id содержит animate_last: {cbs6}"
    assert "image_model_menu" in cbs6, (
        f"3.11a result_actions содержит image_model_menu (настройка модели под результатом): {cbs6}"
    )
    kb7 = S.result_actions_kb()
    cbs7 = [b.callback_data for row in kb7.inline_keyboard for b in row if b.callback_data]
    assert "animate_last" not in cbs7, (
        f"3.12 result_actions без user_id БЕЗ animate_last (фейл-кейс): {cbs7}"
    )
    _se = S.SEEDANCE_ENABLED
    S.SEEDANCE_ENABLED = False
    kb8 = S.result_actions_kb(user_id=123, bot_username="TestBot")
    cbs8 = [b.callback_data for row in kb8.inline_keyboard for b in row if b.callback_data]
    assert "animate_last" not in cbs8, "3.13 animate_last скрыт при выключенном видео"
    S.SEEDANCE_ENABLED = _se

    mkb = S.main_menu_kb()
    mcbs = [b.callback_data for row in mkb.inline_keyboard for b in row if b.callback_data]
    assert ("menu_photo" in mcbs and "menu_video" in mcbs
            and not any(c in mcbs for c in
                        ("generate", "video", "avatar_actions", "enhance_photo", "image_model_menu"))), (
        f"3.14 главное меню: только входы в разделы «Фото»/«Видео», без прямых продуктовых кнопок: {mcbs}"
    )

    pkb = S.photo_menu_kb()
    pcbs = [b.callback_data for row in pkb.inline_keyboard for b in row if b.callback_data]
    assert all(c in pcbs for c in
               ("generate", "enhance_photo", "avatar_actions", "image_model_menu", "avatar_back_menu")), (
        f"3.14a раздел «Фото»: генерация/улучшение/аватар/модель картинок + назад: {pcbs}"
    )

    vkb = S.video_menu_kb()
    vcbs = [b.callback_data for row in vkb.inline_keyboard for b in row if b.callback_data]
    assert "video" in vcbs and "avatar_back_menu" in vcbs, (
        f"3.14b раздел «Видео»: запуск видео + назад: {vcbs}"
    )
