# -*- coding: utf-8 -*-
"""Блок 15: EvoLink реальный HTTP-клиент (Seedance/Gemini Omni/Kling Motion Control)."""
import asyncio
import json
import logging

from test_helpers import S, make_update_context


def test_block_16_evolink_http_client():
    evo_calls = []
    _evo_poll_queue = []

    class FakeEvoResp:
        def __init__(self, status=200, body=None):
            self.status = status
            self._body = body if body is not None else {}

        async def text(self):
            return json.dumps(self._body)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class FakeEvoSession:
        def __init__(self, *a, **kw):
            pass

        def post(self, url, headers=None, json=None, timeout=None, **kw):
            evo_calls.append({"method": "POST", "url": url, "payload": json, "headers": headers})
            return FakeEvoResp(status=200, body={
                "id": "task-unified-1774857405-abc123",
                "status": "pending",
                "model": (json or {}).get("model"),
                "usage": {"billing_rule": "per_second", "credits_reserved": 50},
            })

        def get(self, url, headers=None, timeout=None, **kw):
            evo_calls.append({"method": "GET", "url": url, "headers": headers})
            body = _evo_poll_queue.pop(0) if _evo_poll_queue else {"status": "pending", "progress": 10}
            return FakeEvoResp(status=200, body=body)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    _orig_evo_key = S.EVOLINK_API_KEY
    S.EVOLINK_API_KEY = "test-evolink-key"
    _orig_evo_cs = S.aiohttp.ClientSession
    S.aiohttp.ClientSession = FakeEvoSession
    _orig_sleep = S.asyncio.sleep

    async def _fast_sleep(_secs):
        return None

    S.asyncio.sleep = _fast_sleep

    # 15.1 start_seedance_task_evolink: payload корректный (модель/duration/quality/aspect)
    evo_calls.clear()
    task_ref = asyncio.run(S.start_seedance_task_evolink(
        prompt="девушка танцует", image_url="https://example.com/ref.jpg", user_id=1,
        duration=5, mode="720p", model_code="seedance2", aspect_ratio="9:16",
    ))
    assert task_ref.startswith("__EVOLINK__:"), (
        f"15.1 start_seedance_task_evolink возвращает __EVOLINK__: префикс: {task_ref}"
    )
    p15_1 = evo_calls[0]["payload"]
    assert p15_1.get("model") == "seedance-2.0-reference-to-video", (
        f"15.2 payload.model = seedance-2.0-reference-to-video: {p15_1}"
    )
    assert p15_1.get("image_urls") == ["https://example.com/ref.jpg"], (
        f"15.3 payload.image_urls содержит фото: {p15_1}"
    )
    assert p15_1.get("duration") == 5, "15.4 payload.duration = 5"
    assert p15_1.get("aspect_ratio") == "9:16", "15.5 payload.aspect_ratio = 9:16"
    assert p15_1.get("quality") == "720p", "15.6 payload.quality = 720p"
    assert p15_1.get("generate_audio") is True, "15.7 payload.generate_audio=True"
    assert evo_calls[0]["headers"].get("Authorization") == "Bearer test-evolink-key", (
        "15.8 заголовок Authorization Bearer"
    )

    # 15.9 seedance2_fast + evolink + 1080p -> фолбэк на 720p (EvoLink не умеет 1080p у fast)
    evo_calls.clear()
    asyncio.run(S.start_seedance_task_evolink(
        prompt="тест", image_url="https://example.com/ref.jpg", user_id=1,
        duration=5, mode="1080p", model_code="seedance2_fast", aspect_ratio="16:9",
    ))
    p15_9 = evo_calls[0]["payload"]
    assert p15_9.get("model") == "seedance-2.0-fast-reference-to-video", (
        f"15.9 seedance2_fast: модель seedance-2.0-fast-reference-to-video: {p15_9}"
    )
    assert p15_9.get("quality") == "720p", f"15.10 seedance2_fast: 1080p сфолбэчен на 720p: {p15_9.get('quality')}"

    # 15.11 без фото — понятная ошибка, не молчаливый провал
    try:
        asyncio.run(S.start_seedance_task_evolink(prompt="x", image_url=None, user_id=1, model_code="seedance2"))
        assert False, "15.11 start_seedance_task_evolink без фото падает"
    except Exception as e:
        assert "фото" in str(e).lower(), "15.11 start_seedance_task_evolink без фото падает"

    # 15.11b живой прод-баг 2026-08-02: изначальный фикс (обрезка до 2 фото)
    # был неполным — EvoLink *-image-to-video действительно берёт только
    # первый+последний кадр, НО у EvoLink есть отдельная *-reference-to-video
    # модель с мультиреференсом до 9 фото (ровно как у Zveno-Seedance) — её и
    # нужно было использовать вместо обрезки списка. 4 фото должны дойти ВСЕ.
    evo_calls.clear()
    asyncio.run(S.start_seedance_task_evolink(
        prompt="тест", image_url=None, user_id=1, model_code="seedance2",
        image_urls=[f"https://example.com/ref{i}.jpg" for i in range(4)],
    ))
    p15_11b = evo_calls[0]["payload"]
    assert p15_11b.get("image_urls") == [f"https://example.com/ref{i}.jpg" for i in range(4)], (
        f"15.11b EvoLink Seedance: reference-to-video принимает все 4 фото (не обрезано): {p15_11b.get('image_urls')}"
    )
    assert S.EVOLINK_SEEDANCE_MAX_IMAGES == 9, "15.11c EVOLINK_SEEDANCE_MAX_IMAGES = 9 (как у Zveno, а не 2)"
    assert "@image1" in p15_11b.get("prompt", "") and "[Image1]" not in p15_11b.get("prompt", ""), (
        f"15.11d автопривязка референсов для EvoLink использует @imageN, не [ImageN]: {p15_11b.get('prompt')}"
    )

    # 15.11e build_seedance_prompt_with_refs: Zveno-путь (start_seedance_task)
    # по-прежнему шлёт [ImageN] — tag_format="bracket" не должен был затронуть
    # существующий провайдер.
    assert ("[Image1]" in S.build_seedance_prompt_with_refs("x", 1)
            and "@image1" not in S.build_seedance_prompt_with_refs("x", 1)), (
        "15.11e build_seedance_prompt_with_refs дефолт = bracket ([ImageN])"
    )
    assert "@image1" in S.build_seedance_prompt_with_refs("x", 1, tag_format="at"), (
        "15.11f build_seedance_prompt_with_refs tag_format=at -> @imageN"
    )

    # 15.12 poll_seedance_task делегирует __EVOLINK__: в poll_evolink_task -> completed -> results[0]
    _evo_poll_queue.clear()
    _evo_poll_queue.append({"status": "pending", "progress": 20})
    _evo_poll_queue.append({"status": "completed", "progress": 100, "results": ["http://example.com/video.mp4"]})
    video_url = asyncio.run(S.poll_seedance_task(task_ref, max_attempts=5, poll_interval=1))
    assert video_url == "http://example.com/video.mp4", (
        f"15.13 poll_seedance_task(__EVOLINK__:) вернул results[0]: {video_url}"
    )

    # 15.14 poll: content_policy_violation классифицируется как moderation
    _evo_poll_queue.clear()
    _evo_poll_queue.append({
        "status": "failed",
        "error": {"code": "content_policy_violation", "message": "blocked content", "type": "task_error"},
    })
    try:
        asyncio.run(S.poll_seedance_task(task_ref, max_attempts=3, poll_interval=1))
        assert False, "15.14 poll: failed кидает исключение"
    except Exception as e:
        assert True, "15.14 poll: failed кидает исключение"
        assert S.classify_generation_error(e) == "moderation", (
            f"15.15 classify_generation_error -> moderation (content_policy_violation): {e}"
        )

    # 15.15b classify_generation_error знает EvoLink-специфичные коды (docs/en/
    # api-manual/task-management/error-codes) — с подчёркиванием, а не пробелом,
    # старые keyword'ы ("service unavailable") их не ловили.
    for _code, _bucket in (
        ("service_unavailable", "provider_error"),
        ("service_error", "provider_error"),
        ("resource_exhausted", "provider_error"),
        ("generation_failed_no_content", "provider_error"),
        ("resource_not_found", "provider_error"),
        ("image_processing_error", "download_error"),
        ("image_dimension_mismatch", "download_error"),
        ("quota_exceeded", "no_balance"),
    ):
        got = S.classify_generation_error(Exception(_code))
        assert got == _bucket, f"15.15c classify_generation_error({_code}) -> {_bucket}: got={got}"

    # 15.16 Gemini Omni: payload — одно фото, model=gemini-omni-flash-reference-to-video
    # (живой прод-баг 2026-08-02: image-to-video берёт строго 1 фото,
    # reference-to-video — до 6, тот же класс бага/фикса, что у Seedance).
    evo_calls.clear()
    gomni_ref = asyncio.run(S.start_gemini_omni_task_evolink(
        prompt="оживи фото", image_url="https://example.com/photo.jpg", user_id=1,
        duration=25, aspect_ratio="16:9",
    ))
    assert gomni_ref.startswith("__EVOLINK__:"), f"15.17 gemini omni возвращает __EVOLINK__: префикс: {gomni_ref}"
    p15_16 = evo_calls[0]["payload"]
    assert p15_16.get("model") == "gemini-omni-flash-reference-to-video", f"15.18 gemini omni: модель: {p15_16}"
    assert p15_16.get("image_urls") == ["https://example.com/photo.jpg"], (
        "15.19 gemini omni: одно фото в image_urls"
    )
    assert p15_16.get("duration") == 10, (
        f"15.20 gemini omni: duration клампится к 10 (макс): {p15_16.get('duration')}"
    )
    assert p15_16.get("aspect_ratio") == "16:9", "15.21 gemini omni: aspect_ratio 16:9"

    # 15.22 Gemini Omni: неподдержанный aspect -> фолбэк на 16:9
    evo_calls.clear()
    asyncio.run(S.start_gemini_omni_task_evolink(
        prompt="x", image_url="https://example.com/photo.jpg", user_id=1, duration=5, aspect_ratio="4:3",
    ))
    p15_22 = evo_calls[0]["payload"]
    assert p15_22.get("aspect_ratio") == "16:9", f"15.23 gemini omni: 4:3 не поддержан -> фолбэк 16:9: {p15_22}"

    # 15.24 Kling Motion Control (EvoLink): image_urls + video_urls + model_params
    evo_calls.clear()
    kmc_ref = asyncio.run(S.start_kling_motion_control_evolink(
        image_url="https://example.com/character.jpg",
        motion_video_url="https://example.com/motion.mp4",
        prompt="повтори движение",
        user_id=1,
    ))
    assert kmc_ref.startswith("__EVOLINK__:"), (
        f"15.25 kling motion control evolink возвращает __EVOLINK__: префикс: {kmc_ref}"
    )
    p15_24 = evo_calls[0]["payload"]
    assert p15_24.get("model") == "kling-v3-motion-control", (
        f"15.26 kling motion control: model=kling-v3-motion-control: {p15_24}"
    )
    assert p15_24.get("image_urls") == ["https://example.com/character.jpg"], (
        "15.27 kling motion control: image_urls = [character]"
    )
    assert p15_24.get("video_urls") == ["https://example.com/motion.mp4"], (
        "15.28 kling motion control: video_urls = [motion]"
    )
    assert p15_24.get("model_params", {}).get("character_orientation") == "image", (
        f"15.29 kling motion control: character_orientation=image: {p15_24.get('model_params')}"
    )
    assert p15_24.get("prompt") == "повтори движение", "15.30 kling motion control: prompt передан"

    S.EVOLINK_API_KEY = _orig_evo_key
    S.aiohttp.ClientSession = _orig_evo_cs
    S.asyncio.sleep = _orig_sleep

    # 15.31 EvoLink duration bounds: seedance2/2_fast на evolink -> 4–15 (не 5–15 как на zveno)
    _orig_seedance_provider = S.SEEDANCE_PROVIDER
    S.SEEDANCE_PROVIDER = "evolink"
    assert S.get_seedance_duration_bounds("seedance2") == (4, 15), (
        "15.31 evolink seedance2 duration bounds = (4, 15)"
    )
    assert S.get_seedance_duration_bounds("kling3") == (3, 15), (
        "15.32 zveno kling3 duration bounds не затронуты (3, 15)"
    )
    assert "1080p" not in S.get_seedance_mode_options("seedance2_fast"), (
        f"15.33 evolink seedance2_fast: mode options без 1080p: {S.get_seedance_mode_options('seedance2_fast')}"
    )
    S.SEEDANCE_PROVIDER = _orig_seedance_provider
    assert S.get_seedance_duration_bounds("seedance2") == (5, 15), (
        "15.34 zveno (дефолт) seedance2 duration bounds = (5, 15)"
    )
    assert "1080p" in S.get_seedance_mode_options("seedance2_fast"), (
        f"15.35 zveno seedance2_fast: 1080p доступен: {S.get_seedance_mode_options('seedance2_fast')}"
    )

    # 15.36 Gemini Omni как модель — кнопка живёт в ПИКЕРЕ моделей (после ТЗ
    # video_panel_declutter полная панель кнопок-моделей не держит вовсе),
    # и только когда флаг включён.
    _orig_gemini_enabled = S.GEMINI_OMNI_ENABLED
    S.GEMINI_OMNI_ENABLED = False
    cbs15_off = [b.callback_data for row in S.video_model_picker_kb().inline_keyboard for b in row]
    assert "video_model_gemini_omni" not in cbs15_off, (
        f"15.36 gemini omni выключен -> кнопки нет в пикере: {cbs15_off}"
    )

    S.GEMINI_OMNI_ENABLED = True
    cbs15_on = [b.callback_data for row in S.video_model_picker_kb().inline_keyboard for b in row]
    assert "video_model_gemini_omni" in cbs15_on, f"15.37 gemini omni включён -> кнопка есть в пикере: {cbs15_on}"

    # 15.38 выбор gemini_omni через callback ставит модель и форсит аспект 16:9/9:16
    update, context, query = make_update_context("video_model_gemini_omni", user_id=1501)
    context.user_data["state"] = S.UserState(video_aspect_ratio="1:1")
    asyncio.run(S.button_handler(update, context))
    st15 = context.user_data["state"]
    assert st15.video_model == "gemini_omni", f"15.39 video_model_gemini_omni ставит модель: {st15.video_model}"
    assert st15.video_aspect_ratio == "16:9", (
        f"15.40 gemini_omni сбрасывает несовместимый аспект 1:1 -> 16:9: {st15.video_aspect_ratio}"
    )

    # 15.41 get_video_model возвращает gemini_omni только когда флаг включён
    assert S.get_video_model(S.UserState(video_model="gemini_omni")) == "gemini_omni", (
        "15.41 get_video_model(gemini_omni, enabled) -> gemini_omni"
    )
    S.GEMINI_OMNI_ENABLED = False
    assert S.get_video_model(S.UserState(video_model="gemini_omni")) == "seedance2", (
        "15.42 get_video_model(gemini_omni, disabled) -> seedance2 (фолбэк)"
    )
    S.GEMINI_OMNI_ENABLED = True

    # 15.43 _studio_video_models включает gemini_omni, только когда флаг включён
    assert "gemini_omni" in S._studio_video_models(), (
        "15.43 _studio_video_models содержит gemini_omni при включённом флаге"
    )
    S.GEMINI_OMNI_ENABLED = False
    assert "gemini_omni" not in S._studio_video_models(), (
        "15.44 _studio_video_models НЕ содержит gemini_omni при выключенном флаге"
    )
    S.GEMINI_OMNI_ENABLED = _orig_gemini_enabled

    # 15.45 MOTION_CONTROL_PROVIDER дефолт — mashagpt (ноль изменений поведения)
    assert S.MOTION_CONTROL_PROVIDER == "mashagpt", (
        f"15.45 дефолт MOTION_CONTROL_PROVIDER = mashagpt: {S.MOTION_CONTROL_PROVIDER}"
    )

    # 15.46 log_provider_config: громкая сводка провайдеров при старте, с warning
    # на рассинхроне AI_PROVIDER/ключа (прод-инцидент 2026-08-01: AI_PROVIDER
    # потерялся в BotHost, фото неделю молча шли через YesAPI вместо Zveno).
    class _ListLogHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(record)

    _log_handler = _ListLogHandler()
    S.logger.addHandler(_log_handler)
    _orig_ai_provider = S.AI_PROVIDER
    _orig_zveno_key = S.ZVENO_API_KEY

    S.AI_PROVIDER = "MASHAGPT"
    S.log_provider_config()
    _warnings46 = [r.getMessage() for r in _log_handler.records if r.levelno >= logging.WARNING]
    assert any("MASHAGPT" in w and "ключ" in w for w in _warnings46), (
        f"15.46 AI_PROVIDER без ключа -> warning про пустой ключ: {_warnings46}"
    )

    _log_handler.records.clear()
    S.AI_PROVIDER = _orig_ai_provider
    S.ZVENO_API_KEY = ""
    S.log_provider_config()
    _warnings46b = [r.getMessage() for r in _log_handler.records if r.levelno >= logging.WARNING]
    assert any("ZVENO_API_KEY" in w for w in _warnings46b), (
        f"15.47 пустой ZVENO_API_KEY -> warning про недоступное видео: {_warnings46b}"
    )
    S.ZVENO_API_KEY = _orig_zveno_key
    S.logger.removeHandler(_log_handler)
