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
