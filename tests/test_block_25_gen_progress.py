# -*- coding: utf-8 -*-
"""Блок 25: живой прогресс генерации в вебаппе (docs/specs/
2026-08-13_webapp_generation_hub_full.md) — тонкое write-only зеркало в
Cloudflare D1 (НЕ очередь, в отличие от studio_worker.py). Fire-and-forget
по тому же паттерну, что _studio_api/_studio_complete: недоставленная запись
не блокирует и не проваливает саму генерацию."""
import asyncio
from unittest.mock import AsyncMock

from test_helpers import S


def test_block_25a_api_noop_when_disabled():
    _orig = S.GEN_PROGRESS_ENABLED
    S.GEN_PROGRESS_ENABLED = False
    try:
        result = asyncio.run(S._gen_progress_api("progress.create", {"id": "x"}))
        assert result is None, "25a.1 выключенный флаг -> сразу None, без HTTP-запроса"
    finally:
        S.GEN_PROGRESS_ENABLED = _orig


def test_block_25b_create_returns_true_only_on_confirmed_response():
    _orig = S._gen_progress_api
    try:
        S._gen_progress_api = AsyncMock(return_value={"ok": True})
        created = asyncio.run(S.gen_progress_create("pid-1", 42, "video", {"model_label": "Seedance 2"}))
        assert created is True, "25b.1 подтверждённый ответ Cloudflare -> True"
        call = S._gen_progress_api.await_args_list[0]
        assert call.args[0] == "progress.create", f"25b.2 путь верный: {call.args[0]!r}"
        assert call.args[1] == {
            "id": "pid-1", "user_id": 42, "product": "video", "meta": {"model_label": "Seedance 2"},
        }, f"25b.3 payload верный: {call.args[1]!r}"

        S._gen_progress_api = AsyncMock(return_value=None)
        created2 = asyncio.run(S.gen_progress_create("pid-2", 42, "video", {}))
        assert created2 is False, (
            "25b.4 недоступный Cloudflare -> False (спека: не показываем нерабочую кнопку прогресса)"
        )
    finally:
        S._gen_progress_api = _orig


def test_block_25c_update_never_sends_fake_percent():
    _orig = S._gen_progress_api
    try:
        S._gen_progress_api = AsyncMock(return_value={})
        asyncio.run(S.gen_progress_update("pid-1", "processing", "Генерируем…"))
        call = S._gen_progress_api.await_args_list[0]
        assert call.args[0] == "progress.update"
        assert call.args[1]["progress_pct"] == 0, (
            f"25c.1 progress_pct всегда 0 — никогда не выдумываем точность, которой нет: {call.args[1]}"
        )
        assert call.args[1]["stage"] == "Генерируем…", f"25c.2 стадийный текст передан как есть: {call.args[1]}"
    finally:
        S._gen_progress_api = _orig


def test_block_25d_complete_passes_status_and_stage():
    _orig = S._gen_progress_api
    try:
        S._gen_progress_api = AsyncMock(return_value={})
        asyncio.run(S.gen_progress_complete("pid-1", "done", "Готово!"))
        call = S._gen_progress_api.await_args_list[0]
        assert call.args == ("progress.complete", {"id": "pid-1", "status": "done", "stage": "Готово!"}), (
            f"25d.1 payload завершения: {call.args}"
        )
    finally:
        S._gen_progress_api = _orig


def test_block_25e_kb_builds_inline_webapp_button_with_job_and_product():
    _orig_url = S.PROMPT_WEBAPP_URL
    S.PROMPT_WEBAPP_URL = "https://example.pages.dev/"
    try:
        kb = S.gen_progress_kb(101, "pid-xyz", "video")
        btn = kb.inline_keyboard[0][0]
        assert btn.text == "👀 Смотреть прогресс", f"25e.1 текст кнопки дословно: {btn.text!r}"
        assert btn.web_app is not None, "25e.2 обязательно инлайн web_app (не callback, не reply) — нужен initData"
        assert "tab=progress" in btn.web_app.url, f"25e.3 экран прогресса: {btn.web_app.url}"
        assert "job_id=pid-xyz" in btn.web_app.url, f"25e.4 id задания в URL: {btn.web_app.url}"
        assert "product=video" in btn.web_app.url, f"25e.5 продукт в URL: {btn.web_app.url}"
    finally:
        S.PROMPT_WEBAPP_URL = _orig_url


def test_block_25f_flag_requires_secret_and_api_base_like_studio():
    # config.py: GEN_PROGRESS_ENABLED — И явный env-флаг, И оба секрета/URL
    # настроены (тот же принцип безопасного деплоя, что STUDIO_ENABLED).
    import importlib
    import config as _config
    _orig_env = dict(__import__("os").environ)
    try:
        __import__("os").environ["GEN_PROGRESS_ENABLED"] = "1"
        __import__("os").environ["GEN_PROGRESS_SECRET"] = ""
        importlib.reload(_config)
        assert _config.GEN_PROGRESS_ENABLED is False, (
            "25f.1 флаг=1, но пустой секрет -> фича всё равно выключена (нечего деплоить наполовину)"
        )
    finally:
        __import__("os").environ.clear()
        __import__("os").environ.update(_orig_env)
        importlib.reload(_config)
