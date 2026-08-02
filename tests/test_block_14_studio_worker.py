# -*- coding: utf-8 -*-
"""Блок 13: студия мультиков — воркер D1-очереди (Ф1)."""
import asyncio
import io
import json
import os
import shutil
import tempfile
import time
import types
from unittest.mock import AsyncMock

from test_helpers import S, studio_worker


def test_block_14_studio_worker():
    # 13.1 цены: кадр без рефов = BASE_GENERATION_COST, клип = секунды × тариф
    assert S._studio_compute_cost("frame", {}) == S.BASE_GENERATION_COST, "13.1 цена кадра без рефов"
    _clip_cost = S._studio_compute_cost("clip", {"model": "seedance2_fast", "duration": 5})
    assert _clip_cost == S.calc_seedance_cost(5, S.SEEDANCE_FAST_COST_PER_SECOND), (
        f"13.2 цена клипа seedance2_fast 5с: {_clip_cost}"
    )
    try:
        S._studio_compute_cost("clip", {"model": "несуществующая"})
        assert False, "13.3 неизвестная модель клипа -> исключение"
    except ValueError:
        assert True, "13.3 неизвестная модель клипа -> исключение"
    assert S._studio_compute_cost("scenario", {}) == 0 and S._studio_compute_cost("stitch", {}) == 0, (
        "13.4 scenario/stitch бесплатны"
    )

    # 13.5 парсер сцен: терпит ```json-забор и болтовню вокруг
    _scenes = S._studio_parse_scenes(
        'Вот сцены:\n```json\n[{"frame_prompt": "cat on roof", "video_prompt": "cat jumps"},'
        '{"frame_prompt": "cat lands", "video_prompt": ""}]\n```\nГотово!'
    )
    assert len(_scenes) == 2 and _scenes[0]["frame_prompt"] == "cat on roof", (
        f"13.5 парсер сцен достаёт JSON из забора: {_scenes}"
    )
    try:
        S._studio_parse_scenes("никакого json тут нет")
        assert False, "13.6 мусор без JSON -> исключение"
    except ValueError:
        assert True, "13.6 мусор без JSON -> исключение"
    _many = json.dumps([{"frame_prompt": f"scene {i}"} for i in range(20)])
    assert len(S._studio_parse_scenes(_many)) == S.STUDIO_MAX_SCENES, "13.7 парсер режет по STUDIO_MAX_SCENES"

    # Обвязка для _studio_handle_job: мокаем сеть (complete) и генерацию
    studio_worker._studio_semaphore = asyncio.Semaphore(3)
    _studio_api_orig = studio_worker._studio_api
    _studio_exec_orig = studio_worker._studio_execute_job

    _bb_uid = 9701
    _run_tag = str(int(time.time() * 1000))  # уникальные job-id: тестовая SQLite переживает прогоны
    S.create_user_if_not_exists(_bb_uid, "studio_user", 0)
    S.add_izyminki(_bb_uid, 100)
    _bal0 = S.get_balance(_bb_uid)

    # 13.8 happy path: списание, генерация, complete
    studio_worker._studio_api = AsyncMock(return_value={})
    studio_worker._studio_execute_job = AsyncMock(return_value={"frame_url": "https://i.ibb.co/x.png"})
    _job = {"id": f"job-1-{_run_tag}", "user_id": _bb_uid, "type": "frame",
            "payload": json.dumps({"frame_prompt": "cat", "expected_cost": S.BASE_GENERATION_COST})}
    asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job))
    assert S.get_balance(_bb_uid) == _bal0 - S.BASE_GENERATION_COST, (
        f"13.8 happy path: списано ровно по цене: bal={S.get_balance(_bb_uid)}"
    )
    _complete_calls = [c for c in studio_worker._studio_api.await_args_list if c.args[0] == "complete"]
    assert _complete_calls and _complete_calls[-1].args[1]["status"] == "done", (
        f"13.9 happy path: complete со status=done: {_complete_calls}"
    )

    # 13.10 идемпотентность: тот же job снова -> без генерации и денег, только complete
    studio_worker._studio_api = AsyncMock(return_value={})
    studio_worker._studio_execute_job = AsyncMock(return_value={"frame_url": "another"})
    _bal1 = S.get_balance(_bb_uid)
    asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job))
    assert S.get_balance(_bb_uid) == _bal1, "13.10 повторный job: баланс не тронут"
    assert not studio_worker._studio_execute_job.await_args_list, "13.11 повторный job: генерация НЕ вызвана"
    assert any(c.args[0] == "complete" for c in studio_worker._studio_api.await_args_list), (
        "13.12 повторный job: complete переотправлен"
    )

    # 13.13 price_changed: ожидаемая цена не сошлась -> отказ без списания
    studio_worker._studio_api = AsyncMock(return_value={})
    studio_worker._studio_execute_job = AsyncMock(return_value={})
    _bal2 = S.get_balance(_bb_uid)
    _job_pc = {"id": f"job-2-{_run_tag}", "user_id": _bb_uid, "type": "frame",
               "payload": json.dumps({"frame_prompt": "cat", "expected_cost": 1})}
    asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_pc))
    _c = [c for c in studio_worker._studio_api.await_args_list if c.args[0] == "complete"]
    assert S.get_balance(_bb_uid) == _bal2 and _c and _c[-1].args[1]["error"] == "price_changed", (
        f"13.13 price_changed: error без списания: {_c}"
    )

    # 13.14 not_enough_funds: пустой баланс -> отказ, генерация не запущена
    _poor_uid = 9702
    S.create_user_if_not_exists(_poor_uid, "poor", 0)
    while S.get_balance(_poor_uid) > 0:
        S.spend_izyminki(_poor_uid, S.get_balance(_poor_uid))
    studio_worker._studio_api = AsyncMock(return_value={})
    studio_worker._studio_execute_job = AsyncMock(return_value={})
    _job_nf = {"id": f"job-3-{_run_tag}", "user_id": _poor_uid, "type": "frame",
               "payload": json.dumps({"frame_prompt": "cat"})}
    asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_nf))
    _c = [c for c in studio_worker._studio_api.await_args_list if c.args[0] == "complete"]
    assert (_c and _c[-1].args[1]["error"] == "not_enough_funds"
            and not studio_worker._studio_execute_job.await_args_list), (
        f"13.14 not_enough_funds: error и генерация не вызвана: {_c}"
    )

    # 13.15 возврат при ошибке генерации
    studio_worker._studio_api = AsyncMock(return_value={})
    studio_worker._studio_execute_job = AsyncMock(side_effect=Exception("provider exploded: server 500"))
    _bal3 = S.get_balance(_bb_uid)
    _job_fail = {"id": f"job-4-{_run_tag}", "user_id": _bb_uid, "type": "frame",
                 "payload": json.dumps({"frame_prompt": "cat", "expected_cost": S.BASE_GENERATION_COST})}
    asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_fail))
    _c = [c for c in studio_worker._studio_api.await_args_list if c.args[0] == "complete"]
    assert S.get_balance(_bb_uid) == _bal3, f"13.15 сбой генерации: деньги возвращены: bal={S.get_balance(_bb_uid)}"
    assert _c and _c[-1].args[1]["status"] == "error" and _c[-1].args[1]["error"] == "provider", (
        f"13.16 сбой генерации: complete с error=provider: {_c}"
    )

    # 13.17 модерация классифицируется отдельно
    studio_worker._studio_api = AsyncMock(return_value={})
    studio_worker._studio_execute_job = AsyncMock(side_effect=Exception("blocked by content filter / moderation"))
    _job_mod = {"id": f"job-5-{_run_tag}", "user_id": _bb_uid, "type": "frame",
                "payload": json.dumps({"frame_prompt": "cat", "expected_cost": S.BASE_GENERATION_COST})}
    asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_mod))
    _c = [c for c in studio_worker._studio_api.await_args_list if c.args[0] == "complete"]
    assert _c and _c[-1].args[1]["error"] == "moderation", f"13.17 модерация -> error=moderation: {_c}"

    # 13.20 крэш между списанием и генерацией: запись status='charged' в журнале —
    # повторное взятие job'а НЕ списывает второй раз, но генерацию повторяет
    studio_worker._studio_api = AsyncMock(return_value={})
    studio_worker._studio_execute_job = AsyncMock(return_value={"frame_url": "https://i.ibb.co/retry.png"})
    _job6_id = f"job-6-{_run_tag}"
    S.record_studio_done_job(_job6_id, _bb_uid, True, S.BASE_GENERATION_COST, "charged", "", "{}")
    _bal4 = S.get_balance(_bb_uid)
    _job_crash = {"id": _job6_id, "user_id": _bb_uid, "type": "frame",
                  "payload": json.dumps({"frame_prompt": "cat", "expected_cost": S.BASE_GENERATION_COST})}
    asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_crash))
    assert S.get_balance(_bb_uid) == _bal4, (
        f"13.20 после крэша: повторное взятие не списывает второй раз: bal={S.get_balance(_bb_uid)}"
    )
    assert (studio_worker._studio_execute_job.await_args_list != []
            and any(c.args[0] == "complete" and c.args[1]["status"] == "done"
                    for c in studio_worker._studio_api.await_args_list)), (
        f"13.21 после крэша: генерация повторена и complete=done: {studio_worker._studio_api.await_args_list}"
    )

    # 13.18 прайс-фид: модели с длительностями и тарифами
    _feed = S._studio_price_feed()
    assert (_feed["models"]
            and all("durations" in m and "cost_per_second" in m for m in _feed["models"].values())), (
        f"13.18 прайс-фид: есть модели и у каждой durations+cost_per_second: {_feed}"
    )
    assert _feed["frame_cost"] == S.BASE_GENERATION_COST and _feed["max_scenes"] == S.STUDIO_MAX_SCENES, (
        "13.19 прайс-фид: frame_cost и max_scenes на месте"
    )
    assert all(m["resolutions"] == S.get_seedance_mode_options(code) for code, m in _feed["models"].items()), (
        f"13.19b прайс-фид: у каждой модели resolutions совпадает со снэпом бота: {_feed['models']}"
    )

    studio_worker._studio_api = _studio_api_orig
    studio_worker._studio_execute_job = _studio_exec_orig

    # 13.19c студия: 4:3 добавлен в допустимые форматы стежка/кадра
    assert S.STUDIO_STITCH_RESOLUTION.get("4:3") == "1440x1080", (
        f"13.19c STUDIO_STITCH_RESOLUTION знает 4:3: {S.STUDIO_STITCH_RESOLUTION}"
    )

    # 13.22 stitch: меньше 2 клипов -> ValueError, без обращения к ffmpeg
    try:
        asyncio.run(S._studio_generate_stitch(types.SimpleNamespace(bot=AsyncMock()), _bb_uid, {"clips": ["only-one"]}))
        assert False, "13.22 stitch <2 клипов -> исключение"
    except ValueError:
        assert True, "13.22 stitch <2 клипов -> исключение"

    # 13.23-13.24 stitch: реальный ffmpeg — склейка клипа со звуком и без звука
    # в один файл (ревизия ТЗ п.8: тихая дорожка для клипов без звука)
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        _stitch_dir = tempfile.mkdtemp(prefix="test_stitch_src_")
        _clip_silent = os.path.join(_stitch_dir, "silent.mp4")
        _clip_audio = os.path.join(_stitch_dir, "audio.mp4")
        asyncio.run(S._studio_ffmpeg_run(
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=1",
            "-c:v", "libx264", "-t", "1", _clip_silent,
        ))
        asyncio.run(S._studio_ffmpeg_run(
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", _clip_audio,
        ))

        async def _fake_download_stitch(url):
            with open(url, "rb") as f:
                return f.read()

        _orig_download = S.download_video_bytes_with_fallback
        S.download_video_bytes_with_fallback = _fake_download_stitch
        _fake_app = types.SimpleNamespace(bot=AsyncMock())
        _stitch_result = asyncio.run(S._studio_generate_stitch(
            _fake_app, _bb_uid, {"clips": [_clip_silent, _clip_audio], "aspect": "16:9"},
        ))
        S.download_video_bytes_with_fallback = _orig_download
        assert "final_url" in _stitch_result and _fake_app.bot.send_video.await_args is not None, (
            f"13.23 stitch: результат содержит final_url, финал отправлен в чат: {_stitch_result}"
        )
        _sent_kwargs = _fake_app.bot.send_video.await_args.kwargs
        assert (isinstance(_sent_kwargs.get("video"), io.BytesIO)
                and _sent_kwargs["video"].getbuffer().nbytes > 0), (
            f"13.24 stitch: send_video получил непустые байты финального ролика: {_sent_kwargs.get('video')}"
        )
        shutil.rmtree(_stitch_dir, ignore_errors=True)
    else:
        assert True, "13.23 stitch: ffmpeg недоступен локально, склейка не проверена"
