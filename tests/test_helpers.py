# -*- coding: utf-8 -*-
"""Общий сетап и шаред-хелперы для pytest-миграции test_new_features.py (ФАЗА 5).

Импортируется каждым test_block_*.py файлом. Всё, что было "до Блока 1" в
исходном самодельном раннере (env, sys.path, импорт SirNike/studio_worker/PIL,
и хелперы, которыми пользуется больше одного блока) — здесь.

НЕ переносить сюда хелперы, нужные только одному блоку (они остаются в файле
своего блока) — так проще проверять эквивалентность со старым файлом.
"""
import asyncio  # noqa: F401
import base64
import io
import json  # noqa: F401
import os
import sys
import tempfile
import time  # noqa: F401
import types
from unittest.mock import AsyncMock

os.environ.setdefault("AI_PROVIDER", "ZVENO")
os.environ.setdefault("ZVENO_API_KEY", "test-key")
os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("PROVIDER_TOKEN", "test")
os.environ.setdefault("DATA_DIR", os.path.join(tempfile.gettempdir(), "sirnike_test"))
os.environ.setdefault("BOT_LOG_DIR", os.path.join(tempfile.gettempdir(), "sirnike_test"))
os.makedirs(os.environ["DATA_DIR"], exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import SirNike as S  # noqa: E402
import studio_worker  # noqa: E402
from PIL import Image  # noqa: E402


def png_data_url(mode="RGBA", size=(64, 64), color=(255, 0, 0, 128)):
    img = Image.new(mode, size, color if mode == "RGBA" else color[:3])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# Используется блоками 6 (fallback картинок), 11 (баг-баунти), 14 (EvoLink UI) —
# один и тот же валидный PNG-байтстринг для мок-ответов провайдера/скачивания фото.
OK_PNG_B64 = png_data_url("RGB").split(",", 1)[1]


class FakeResp:
    def __init__(self, status=202, body=None):
        self.status = status
        self._body = body or {"id": "vj_test", "polling_url": "https://api.zveno.ai/v1/videos/vj_test"}

    async def text(self):
        return json.dumps(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


# Общий "captured" список — оригинал: блок 5 (payload видео) шлёт сюда каждый
# POST, block 6 (fallback картинок) наследует FakeSession, но всегда
# переопределяет post() своими подклассами (не трогает этот список).
captured = []


class FakeSession:
    def __init__(self, *a, **kw):
        pass

    def post(self, url, headers=None, json=None, timeout=None, **kw):
        captured.append({"url": url, "payload": json})
        return FakeResp()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def make_update_context(data, user_id=777):
    query = types.SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        message=types.SimpleNamespace(reply_text=AsyncMock(), edit_text=AsyncMock(),
                                      date=None),
        edit_message_text=AsyncMock(),
    )
    update = types.SimpleNamespace(
        callback_query=query,
        effective_user=types.SimpleNamespace(id=user_id, username="test"),
        effective_chat=types.SimpleNamespace(id=user_id),
        effective_message=None,
    )
    context = types.SimpleNamespace(user_data={}, application=None, bot=AsyncMock())
    return update, context, query


def make_text_update(text, user_id=900, state=None):
    context = types.SimpleNamespace(user_data={}, application=None, bot=AsyncMock())
    if state is not None:
        context.user_data["state"] = state
    message = types.SimpleNamespace(
        text=text, caption=None, reply_text=AsyncMock(), photo=None,
    )
    update = types.SimpleNamespace(
        message=message,
        effective_user=types.SimpleNamespace(id=user_id, username="test"),
        effective_chat=types.SimpleNamespace(id=user_id),
        effective_message=message,
    )
    return update, context, message


def make_run_generation_context(state, user_id):
    message = types.SimpleNamespace(reply_text=AsyncMock())
    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=user_id, username="tester"),
        effective_message=message,
        effective_chat=types.SimpleNamespace(id=user_id),
        callback_query=None,
    )
    context = types.SimpleNamespace(user_data={"state": state}, bot=AsyncMock())
    return update, context, message


def make_webapp_update_context(user_id=9501):
    message = types.SimpleNamespace(reply_text=AsyncMock())
    update = types.SimpleNamespace(
        effective_message=message,
        effective_user=types.SimpleNamespace(id=user_id, username="test"),
        effective_chat=types.SimpleNamespace(id=user_id),
    )
    context = types.SimpleNamespace(user_data={}, application=None, bot=AsyncMock())
    return update, context, message
