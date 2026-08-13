# -*- coding: utf-8 -*-
"""Блок 2: видео-модели."""
from test_helpers import S


def test_block_02_video_helpers():
    st2 = S.UserState()
    for code, expected in [("seedance2", "seedance2"), ("seedance2_fast", "seedance2_fast"),
                           ("kling3", "kling3"), ("veo31", "veo31"), ("мусор", "seedance2")]:
        st2.video_model = code
        assert S.get_video_model(st2) == expected, f"2.1 get_video_model({code})={expected}"

    _k, _v = S.KLING3_ENABLED, S.VEO31_ENABLED
    S.KLING3_ENABLED = False
    st2.video_model = "kling3"
    assert S.get_video_model(st2) == "seedance2", "2.2 kling3 при выключенном флаге -> seedance2"
    S.KLING3_ENABLED = _k
    S.VEO31_ENABLED = False
    st2.video_model = "veo31"
    assert S.get_video_model(st2) == "seedance2", "2.3 veo31 при выключенном флаге -> seedance2"
    S.VEO31_ENABLED = _v

    assert S.get_video_model_label("kling3") == "Kling 3.0 🆕", "2.4 label kling3"
    assert S.get_video_model_label("veo31") == "Veo 3.1 (Google) 🆕", "2.5 label veo31"
    assert S.get_video_model_cost_per_second("kling3") == 8.0, "2.6 цена kling3 = 8.0"
    assert S.get_video_model_cost_per_second("veo31") == 8.0, "2.7 цена veo31 = 8.0"
    assert S.get_video_model_cost_per_second("seedance2") == S.SEEDANCE_COST_PER_SECOND, (
        "2.8 цена seedance2 не сломана"
    )

    assert S.get_seedance_duration_bounds("kling3") == (3, 15), "2.9 bounds kling3=(3,15)"
    assert S.get_seedance_duration_bounds("veo31") == (4, 8), "2.10 bounds veo31=(4,8)"
    assert S.get_seedance_duration_bounds("seedance2") == (5, 15), "2.11 bounds seedance=(5,15)"

    for raw, exp in [(5, (4, 6)), (7, (6, 8)), (10, (8,)), (3, (4,)), (4, (4,)), (8, (8,))]:
        got = S.normalize_seedance_duration(raw, "veo31")
        assert got in exp, f"2.12 veo31 normalize {raw} -> {got} in {exp}: got={got}"
    assert S.normalize_seedance_duration(2, "kling3") == 3, "2.13 kling3 normalize 2->3"
    assert S.normalize_seedance_duration(20, "kling3") == 15, "2.14 kling3 normalize 20->15"
    assert S.normalize_seedance_duration(7, "kling3") == 7, "2.15 kling3 normalize 7->7 (без снэпа)"

    opts_v = S.get_seedance_duration_options("veo31")
    assert set(opts_v) <= {4, 6, 8} and len(opts_v) >= 2, (
        f"2.16 veo31 duration options только 4/6/8: {opts_v}"
    )
    opts_k = S.get_seedance_duration_options("kling3")
    assert all(3 <= x <= 15 for x in opts_k) and opts_k, (
        f"2.17 kling3 duration options валидны (3..15): {opts_k}"
    )
    assert S.get_seedance_mode_options("kling3") == ["720p", "1080p"], "2.18 mode kling3 = [720p, 1080p]"
    assert S.get_seedance_mode_options("veo31") == ["720p"], "2.19 mode veo31 = [720p]"

    st3 = S.UserState(); st3.video_model = "veo31"; st3.video_mode = "480p"
    assert S.get_selected_seedance_mode(st3) == "720p", "2.20 selected mode veo31 принудительно 720p"
    st3.video_duration = 15
    assert S.get_selected_seedance_duration(st3) in (4, 6, 8), (
        "2.21 selected duration veo31 при 15 -> из options"
    )

    assert S.calc_seedance_cost(5, 8.0) == 40, "2.22 стоимость 5с kling3 = 40 изюм"
    assert S.calc_seedance_cost(8, 8.0) == 64, "2.23 стоимость 8с veo31 = 64 изюм"


def test_block_02b_seedance25_premium_video():
    # Seedance 2.5 — отдельный премиум-продукт (P1 бриф от аналитика рынка,
    # docs/ai-market/2026-08-08-creator-candidates.md), НЕ подмена дефолтной
    # Seedance 2.0. Единственная видео-модель с ЦЕНОЙ, ЗАВИСЯЩЕЙ ОТ КАЧЕСТВА
    # (480p дешевле, 720p дороже) — остальные модели игнорируют mode в цене.
    _orig_enabled = S.SEEDANCE25_ENABLED
    st = S.UserState()

    S.SEEDANCE25_ENABLED = False
    st.video_model = "seedance25"
    assert S.get_video_model(st) == "seedance2", "2b.1 seedance25 при выключенном флаге -> seedance2 (фолбэк)"

    S.SEEDANCE25_ENABLED = True
    assert S.get_video_model(st) == "seedance25", "2b.2 seedance25 при включённом флаге выбирается"
    assert S.get_video_model_label("seedance25") == "Seedance 2.5 💎", "2b.3 label seedance25"

    assert S.get_seedance_duration_bounds("seedance25") == (5, 30), (
        "2b.4 bounds seedance25=(5,30) — нативно до 30 сек без склейки"
    )
    assert S.get_seedance_mode_options("seedance25") == ["480p", "720p"], (
        "2b.5 seedance25: оба качества доступны юзеру, не одно на выбор"
    )
    opts_25 = S.get_seedance_duration_options("seedance25")
    assert all(5 <= x <= 30 for x in opts_25) and 30 in opts_25, (
        f"2b.6 seedance25 duration options валидны (5..30), включают 30: {opts_25}"
    )

    cps_480 = S.get_video_model_cost_per_second("seedance25", "480p")
    cps_720 = S.get_video_model_cost_per_second("seedance25", "720p")
    assert cps_480 == S.SEEDANCE25_COST_PER_SECOND_480P, f"2b.7 цена 480p из конфига: {cps_480}"
    assert cps_720 == S.SEEDANCE25_COST_PER_SECOND_720P, f"2b.8 цена 720p из конфига: {cps_720}"
    assert cps_720 > cps_480, f"2b.9 720p дороже 480p: {cps_720} vs {cps_480}"
    # Без явного mode -> дефолт SEEDANCE25_MODE (480p) — не падает и не путает с 720p.
    cps_default = S.get_video_model_cost_per_second("seedance25")
    assert cps_default == cps_480, f"2b.10 без mode -> дефолтное качество (480p): {cps_default}"

    S.SEEDANCE25_ENABLED = _orig_enabled
