# -*- coding: utf-8 -*-
"""Блок 5: payload Zveno Videos (мок aiohttp)."""
import asyncio

from test_helpers import S, FakeSession, captured, png_data_url


def test_block_05_seedance_payload():
    rgba_url = png_data_url("RGBA")

    def run_start(model_code, images, aspect="16:9", duration=5):
        captured.clear()
        return asyncio.run(S.start_seedance_task(
            prompt="девушка улыбается и машет рукой",
            image_url=images[0] if images else None,
            image_urls=images,
            user_id=1,
            duration=duration,
            endpoint="/v1/videos",
            mode="720p",
            model_code=model_code,
            aspect_ratio=aspect,
        ))

    _orig_cs = S.aiohttp.ClientSession
    S.aiohttp.ClientSession = FakeSession

    # 5.1 kling3, одно фото
    task = run_start("kling3", [rgba_url])
    p = captured[0]["payload"]
    assert p.get("model") == S.KLING3_MODEL, f"5.1 kling3: модель в payload: {p.get('model')}"
    assert p.get("generate_audio") is True, "5.2 kling3: generate_audio=True"
    assert "frame_images" in p and "input_references" not in p and "image_urls" not in p, (
        f"5.3 kling3: первый вариант — чистый frame_images: {list(p.keys())}"
    )
    assert p["frame_images"][0].get("frame_type") == "first_frame", "5.4 kling3: frame_type=first_frame"
    assert p["frame_images"][0]["image_url"]["url"].startswith("data:image/jpeg"), (
        "5.5 kling3: кадр перекодирован в JPEG"
    )
    assert task.startswith("__POLL_URL__:"), "5.6 kling3: вернулся polling url"
    assert p.get("resolution") == "720p" and p.get("aspect_ratio") == "16:9", (
        "5.7 kling3: resolution=720p, aspect=16:9"
    )

    # 5.8 kling3, два фото -> first+last
    run_start("kling3", [png_data_url("RGB"), png_data_url("RGB", color=(0, 255, 0, 255))])
    p = captured[0]["payload"]
    fts = [f.get("frame_type") for f in p.get("frame_images", [])]
    assert fts == ["first_frame", "last_frame"], f"5.8 kling3 два фото: first+last: {fts}"

    # 5.9 veo31: 1:1 -> 16:9, только first
    run_start("veo31", [png_data_url("RGB"), png_data_url("RGB")], aspect="1:1", duration=5)
    p = captured[0]["payload"]
    assert p.get("model") == S.VEO31_MODEL, "5.9 veo31: модель"
    assert p.get("aspect_ratio") == "16:9", "5.10 veo31: аспект 1:1 заменён на 16:9"
    assert [f.get("frame_type") for f in p.get("frame_images", [])] == ["first_frame"], (
        "5.11 veo31: только first frame (без last)"
    )
    assert p.get("duration") in (4, 6, 8), f"5.12 veo31: duration снэпнут к 4/6/8: {p.get('duration')}"
    assert p.get("generate_audio") is True, "5.13 veo31: generate_audio=True"

    # 5.14 seedance2: старое поведение не сломано
    run_start("seedance2", [png_data_url("RGB")])
    p = captured[0]["payload"]
    assert p.get("model") == "bytedance/seedance-2.0", "5.14 seedance2: модель"
    assert "generate_audio" not in p, f"5.15 seedance2: БЕЗ generate_audio: {list(p.keys())}"
    assert "input_references" in p, "5.16 seedance2: рефы через input_references"
    assert p["input_references"][0]["image_url"]["url"].startswith("data:image/png"), (
        "5.17 seedance2: кадр НЕ перекодирован (PNG остался)"
    )

    # 5.18 kling3 text-to-video (без фото)
    run_start("kling3", [])
    p = captured[0]["payload"]
    assert "frame_images" not in p and p.get("prompt"), (
        "5.18 kling3 без фото: нет frame_images, есть prompt"
    )

    S.aiohttp.ClientSession = _orig_cs
