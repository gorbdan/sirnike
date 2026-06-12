# -*- coding: utf-8 -*-
"""Дотошный локальный тест новых функций Сырника (без сети и без Telegram).

Прогоняет: выбор модели картинок, цены, видео-модели Kling 3.0 / Veo 3.1,
клавиатуры, payload Zveno Videos API (мок aiohttp), fallback при
IMAGE_PROHIBITED_CONTENT, кнопку «Оживить», JPEG-конверсию кадров.
"""
import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import types
from unittest.mock import AsyncMock

os.environ.setdefault("AI_PROVIDER", "ZVENO")
os.environ.setdefault("ZVENO_API_KEY", "test-key")
os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("PROVIDER_TOKEN", "test")
os.environ.setdefault("DATA_DIR", os.path.join(tempfile.gettempdir(), "sirnike_test"))
os.environ.setdefault("BOT_LOG_DIR", os.path.join(tempfile.gettempdir(), "sirnike_test"))
os.makedirs(os.environ["DATA_DIR"], exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import SirNike as S  # noqa: E402
from PIL import Image  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
    else:
        FAIL.append((name, detail))
        print(f"  !! FAIL: {name} {detail}")


def png_data_url(mode="RGBA", size=(64, 64), color=(255, 0, 0, 128)):
    img = Image.new(mode, size, color if mode == "RGBA" else color[:3])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ════════════════ БЛОК 1: модель картинок ════════════════
print("Блок 1: модель картинок")
st = S.UserState()
check("1.1 дефолт image_model=gemini", S.get_image_model(st) == "gemini")
st.image_model = "gpt5"
check("1.2 выбор gpt5 работает", S.get_image_model(st) == "gpt5")
_orig_gpt5_enabled = S.GPT5_IMAGE_ENABLED
S.GPT5_IMAGE_ENABLED = False
check("1.3 gpt5 при выключенном флаге -> gemini", S.get_image_model(st) == "gemini")
S.GPT5_IMAGE_ENABLED = _orig_gpt5_enabled

check("1.4 label gpt5", S.get_image_model_label("gpt5") == "GPT-5 Image")
check("1.5 label gemini (env 3.1-flash) = Nano Banana 2",
      S.get_image_model_label("gemini") == "Nano Banana 2",
      f"got={S.get_image_model_label('gemini')!r} env={S.ZVENO_IMAGE_MODEL}")

check("1.6 базовая цена gemini", S.get_image_model_base_cost("gemini") == S.BASE_GENERATION_COST)
check("1.7 базовая цена gpt5 = 10", S.get_image_model_base_cost("gpt5") == 10,
      f"got={S.get_image_model_base_cost('gpt5')}")
check("1.8 calc_generation_cost gemini без рефов", S.calc_generation_cost(None, "gemini") == 5)
check("1.9 calc_generation_cost gpt5 без рефов", S.calc_generation_cost(None, "gpt5") == 10)
_orig_ref_cost = S.REFERENCE_COST
S.REFERENCE_COST = 2
check("1.10 надбавка за рефы складывается", S.calc_generation_cost(["x"], "gpt5") == 12)
S.REFERENCE_COST = _orig_ref_cost

st.image_model = "gemini"
kb = S.image_model_menu_kb(st)
flat = [b for row in kb.inline_keyboard for b in row]
cbs = [b.callback_data for b in flat]
texts = [b.text for b in flat]
check("1.11 меню: есть set_gemini и set_gpt5",
      "image_model_set_gemini" in cbs and "image_model_set_gpt5" in cbs, str(cbs))
check("1.12 меню: маркер ● на выбранной gemini",
      any(t.startswith("● ") and "Nano Banana 2" in t for t in texts), str(texts))
check("1.13 меню: цены в кнопках", any("5 изюминок" in t for t in texts) and any("10 изюминок" in t for t in texts), str(texts))
check("1.14 текст меню упоминает обе модели",
      "Nano Banana 2" in S.image_model_menu_text(st) and "GPT-5 Image" in S.image_model_menu_text(st))

# ════════════════ БЛОК 2: видео-хелперы ════════════════
print("Блок 2: видео-модели")
st2 = S.UserState()
for code, expected in [("seedance2", "seedance2"), ("seedance2_fast", "seedance2_fast"),
                       ("kling3", "kling3"), ("veo31", "veo31"), ("мусор", "seedance2")]:
    st2.motion_model = code
    check(f"2.1 get_motion_model({code})={expected}", S.get_motion_model(st2) == expected)

_k, _v = S.KLING3_ENABLED, S.VEO31_ENABLED
S.KLING3_ENABLED = False
st2.motion_model = "kling3"
check("2.2 kling3 при выключенном флаге -> seedance2", S.get_motion_model(st2) == "seedance2")
S.KLING3_ENABLED = _k
S.VEO31_ENABLED = False
st2.motion_model = "veo31"
check("2.3 veo31 при выключенном флаге -> seedance2", S.get_motion_model(st2) == "seedance2")
S.VEO31_ENABLED = _v

check("2.4 label kling3", S.get_motion_model_label("kling3") == "Kling 3.0 🆕")
check("2.5 label veo31", S.get_motion_model_label("veo31") == "Veo 3.1 (Google) 🆕")
check("2.6 цена kling3 = 8.0", S.get_motion_model_cost_per_second("kling3") == 8.0)
check("2.7 цена veo31 = 8.0", S.get_motion_model_cost_per_second("veo31") == 8.0)
check("2.8 цена seedance2 не сломана", S.get_motion_model_cost_per_second("seedance2") == S.SEEDANCE_COST_PER_SECOND)

check("2.9 bounds kling3=(3,15)", S.get_seedance_duration_bounds("kling3") == (3, 15))
check("2.10 bounds veo31=(4,8)", S.get_seedance_duration_bounds("veo31") == (4, 8))
check("2.11 bounds seedance=(5,15)", S.get_seedance_duration_bounds("seedance2") == (5, 15))

for raw, exp in [(5, (4, 6)), (7, (6, 8)), (10, (8,)), (3, (4,)), (4, (4,)), (8, (8,))]:
    got = S.normalize_seedance_duration(raw, "veo31")
    check(f"2.12 veo31 normalize {raw} -> {got} in {exp}", got in exp, f"got={got}")
check("2.13 kling3 normalize 2->3", S.normalize_seedance_duration(2, "kling3") == 3)
check("2.14 kling3 normalize 20->15", S.normalize_seedance_duration(20, "kling3") == 15)
check("2.15 kling3 normalize 7->7 (без снэпа)", S.normalize_seedance_duration(7, "kling3") == 7)

opts_v = S.get_seedance_duration_options("veo31")
check("2.16 veo31 duration options только 4/6/8", set(opts_v) <= {4, 6, 8} and len(opts_v) >= 2, str(opts_v))
opts_k = S.get_seedance_duration_options("kling3")
check("2.17 kling3 duration options валидны (3..15)", all(3 <= x <= 15 for x in opts_k) and opts_k, str(opts_k))
check("2.18 mode kling3 = [720p]", S.get_seedance_mode_options("kling3") == ["720p"])
check("2.19 mode veo31 = [720p]", S.get_seedance_mode_options("veo31") == ["720p"])

st3 = S.UserState(); st3.motion_model = "veo31"; st3.motion_mode = "480p"
check("2.20 selected mode veo31 принудительно 720p", S.get_selected_seedance_mode(st3) == "720p")
st3.motion_duration = 15
check("2.21 selected duration veo31 при 15 -> из options", S.get_selected_seedance_duration(st3) in (4, 6, 8))

check("2.22 стоимость 5с kling3 = 40 изюм", S.calc_seedance_cost(5, 8.0) == 40)
check("2.23 стоимость 8с veo31 = 64 изюм", S.calc_seedance_cost(8, 8.0) == 64)

# ════════════════ БЛОК 3: клавиатуры ════════════════
print("Блок 3: клавиатуры")
st4 = S.UserState(); st4.motion_model = "kling3"
kb4 = S.video_control_kb(st4)
flat4 = [b for row in kb4.inline_keyboard for b in row]
cbs4 = [b.callback_data for b in flat4 if b.callback_data]
check("3.1 есть кнопка video_model_kling3", "video_model_kling3" in cbs4)
check("3.2 есть кнопка video_model_veo31", "video_model_veo31" in cbs4)
check("3.3 маркер ● на Kling 3.0", any(b.text.startswith("● ") and "Kling" in b.text for b in flat4))
check("3.4 у kling3 нет кнопок качества video_mode_", not any(c.startswith("video_mode_") for c in cbs4), str(cbs4))
check("3.5 у kling3 есть 1:1 аспект", any(c == "video_aspect_1x1" for c in cbs4))
dur_btns = [b.text for b in flat4 if (b.callback_data or "").startswith("video_duration_")]
check("3.6 цена в кнопке 5с = 40 изюминок", any("5с · 40 изюминок" in t for t in dur_btns), str(dur_btns))

st5 = S.UserState(); st5.motion_model = "veo31"
kb5 = S.video_control_kb(st5)
cbs5 = [b.callback_data for row in kb5.inline_keyboard for b in row if b.callback_data]
check("3.7 у veo31 НЕТ 1:1 аспекта", "video_aspect_1x1" not in cbs5, str(cbs5))
check("3.8 у veo31 есть 16:9 и 9:16", "video_aspect_16x9" in cbs5 and "video_aspect_9x16" in cbs5)
durs5 = [c for c in cbs5 if c.startswith("video_duration_")]
check("3.9 duration кнопки veo31 только 4/6/8", set(durs5) <= {"video_duration_4", "video_duration_6", "video_duration_8"}, str(durs5))

stxt = S.video_control_status_text(st4)
check("3.10 статус-текст содержит Kling 3.0 и стоимость", "Kling 3.0" in stxt and "изюминок" in stxt)

kb6 = S.result_actions_kb(user_id=123, bot_username="TestBot")
cbs6 = [b.callback_data for row in kb6.inline_keyboard for b in row if b.callback_data]
check("3.11 result_actions с user_id содержит animate_last", "animate_last" in cbs6, str(cbs6))
kb7 = S.result_actions_kb()
cbs7 = [b.callback_data for row in kb7.inline_keyboard for b in row if b.callback_data]
check("3.12 result_actions без user_id БЕЗ animate_last (фейл-кейс)", "animate_last" not in cbs7, str(cbs7))
_se = S.SEEDANCE_ENABLED
S.SEEDANCE_ENABLED = False
kb8 = S.result_actions_kb(user_id=123, bot_username="TestBot")
cbs8 = [b.callback_data for row in kb8.inline_keyboard for b in row if b.callback_data]
check("3.13 animate_last скрыт при выключенном видео", "animate_last" not in cbs8)
S.SEEDANCE_ENABLED = _se

mkb = S.main_menu_kb()
mcbs = [b.callback_data for row in mkb.inline_keyboard for b in row if b.callback_data]
check("3.14 в главном меню есть image_model_menu", "image_model_menu" in mcbs, str(mcbs))

# ════════════════ БЛОК 4: JPEG-конверсия кадров ════════════════
print("Блок 4: JPEG-конверсия")
rgba_url = png_data_url("RGBA")
out = S._data_url_to_jpeg_rgb(rgba_url)
check("4.1 RGBA PNG -> data:image/jpeg", out.startswith("data:image/jpeg;base64,"))
raw = base64.b64decode(out.split(",", 1)[1])
img = Image.open(io.BytesIO(raw))
check("4.2 результат RGB без альфы", img.mode == "RGB" and img.format == "JPEG")
check("4.3 мусор возвращается как есть", S._data_url_to_jpeg_rgb("data:image/png;base64,@@@@") == "data:image/png;base64,@@@@")
check("4.4 не-data URL не трогается", S._data_url_to_jpeg_rgb("abc") == "abc")

# ════════════════ БЛОК 5: payload Zveno Videos (мок aiohttp) ════════════════
print("Блок 5: payload видео")
captured = []


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


_orig_cs = S.aiohttp.ClientSession
S.aiohttp.ClientSession = FakeSession


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


# 5.1 kling3, одно фото
task = run_start("kling3", [rgba_url])
p = captured[0]["payload"]
check("5.1 kling3: модель в payload", p.get("model") == S.KLING3_MODEL, str(p.get("model")))
check("5.2 kling3: generate_audio=False", p.get("generate_audio") is False)
check("5.3 kling3: первый вариант — чистый frame_images",
      "frame_images" in p and "input_references" not in p and "image_urls" not in p, str(list(p.keys())))
check("5.4 kling3: frame_type=first_frame", p["frame_images"][0].get("frame_type") == "first_frame")
check("5.5 kling3: кадр перекодирован в JPEG", p["frame_images"][0]["image_url"]["url"].startswith("data:image/jpeg"))
check("5.6 kling3: вернулся polling url", task.startswith("__POLL_URL__:"))
check("5.7 kling3: resolution=720p, aspect=16:9", p.get("resolution") == "720p" and p.get("aspect_ratio") == "16:9")

# 5.8 kling3, два фото -> first+last
run_start("kling3", [png_data_url("RGB"), png_data_url("RGB", color=(0, 255, 0, 255))])
p = captured[0]["payload"]
fts = [f.get("frame_type") for f in p.get("frame_images", [])]
check("5.8 kling3 два фото: first+last", fts == ["first_frame", "last_frame"], str(fts))

# 5.9 veo31: 1:1 -> 16:9, только first
run_start("veo31", [png_data_url("RGB"), png_data_url("RGB")], aspect="1:1", duration=5)
p = captured[0]["payload"]
check("5.9 veo31: модель", p.get("model") == S.VEO31_MODEL)
check("5.10 veo31: аспект 1:1 заменён на 16:9", p.get("aspect_ratio") == "16:9")
check("5.11 veo31: только first frame (без last)",
      [f.get("frame_type") for f in p.get("frame_images", [])] == ["first_frame"])
check("5.12 veo31: duration снэпнут к 4/6/8", p.get("duration") in (4, 6, 8), str(p.get("duration")))
check("5.13 veo31: generate_audio=False", p.get("generate_audio") is False)

# 5.14 seedance2: старое поведение не сломано
run_start("seedance2", [png_data_url("RGB")])
p = captured[0]["payload"]
check("5.14 seedance2: модель", p.get("model") == "bytedance/seedance-2.0")
check("5.15 seedance2: БЕЗ generate_audio", "generate_audio" not in p, str(list(p.keys())))
check("5.16 seedance2: рефы через input_references", "input_references" in p)
check("5.17 seedance2: кадр НЕ перекодирован (PNG остался)",
      p["input_references"][0]["image_url"]["url"].startswith("data:image/png"))

# 5.18 kling3 text-to-video (без фото)
run_start("kling3", [])
p = captured[0]["payload"]
check("5.18 kling3 без фото: нет frame_images, есть prompt", "frame_images" not in p and p.get("prompt"))

S.aiohttp.ClientSession = _orig_cs

# ════════════════ БЛОК 6: fallback картинок при PROHIBITED ════════════════
print("Блок 6: fallback картинок")
ok_png_b64 = png_data_url("RGB").split(",", 1)[1]


def make_resp_for(payload):
    model = payload.get("model", "")
    if model == S.ZVENO_IMAGE_MODEL:  # banana 2 -> фильтр
        body = {"choices": [{"message": {"content": "blocked"},
                             "finish_reason": "stop", "native_finish_reason": "IMAGE_PROHIBITED_CONTENT"}]}
    else:  # fallback Pro -> картинка
        body = {"choices": [{"message": {"images": [
            {"url": "data:image/png;base64," + ok_png_b64}]}, "finish_reason": "stop"}]}
    return FakeResp(status=200, body=body)


img_calls = []


class FakeImgSession(FakeSession):
    def post(self, url, headers=None, json=None, timeout=None, **kw):
        img_calls.append(json)
        return make_resp_for(json)


async def fake_persist(ref):
    return "https://example.com/x.png"

_orig = {}
for name in ("_persist_image_ref", "send_generation_result_by_url", "add_generation_history",
             "log_generation_event", "add_izyminki", "restore_free_generation", "maybe_send_avatar_nudge"):
    _orig[name] = getattr(S, name)

S._persist_image_ref = fake_persist
S.send_generation_result_by_url = AsyncMock()
S.add_generation_history = lambda **kw: None
S.log_generation_event = lambda **kw: None
S.add_izyminki = lambda *a, **kw: None
S.restore_free_generation = lambda *a, **kw: None
S.aiohttp.ClientSession = FakeImgSession
_orig_channel = S.RESULTS_CHANNEL_ID
S.RESULTS_CHANNEL_ID = ""

app = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: c.close() if hasattr(c, "close") else None)
job = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=5, image_model="gemini")
img_calls.clear()
asyncio.run(S.generate_image_by_job(app, job))
models_called = [c.get("model") for c in img_calls]
check("6.1 banana отказала -> запрошен fallback", len(img_calls) >= 2, str(models_called))
check("6.2 banana вызвана ровно 1 раз (не ретраится после фильтра)",
      models_called.count(S.ZVENO_IMAGE_MODEL) == 1, str(models_called))
check("6.3 fallback = gemini-3-pro", any("3-pro-image" in (m or "") for m in models_called), str(models_called))
check("6.4 итог — успех (картинка отправлена)", S.send_generation_result_by_url.await_count == 1)

# 6.5: всё PROHIBITED -> рефанд и сообщение об ошибке
class FakeAllBlockedSession(FakeSession):
    def post(self, url, headers=None, json=None, timeout=None, **kw):
        img_calls.append(json)
        body = {"choices": [{"message": {"content": "no"},
                             "finish_reason": "stop", "native_finish_reason": "IMAGE_PROHIBITED_CONTENT"}]}
        return FakeResp(status=200, body=body)


refunds = []
S.add_izyminki = lambda uid, amount: refunds.append((uid, amount))
S.aiohttp.ClientSession = FakeAllBlockedSession
S.send_generation_result_by_url.reset_mock()
app2 = types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None)
job2 = S.GenerationJob(chat_id=1, user_id=42, prompt="тест", references=[], cost=5, image_model="gemini")
img_calls.clear()
asyncio.run(S.generate_image_by_job(app2, job2))
check("6.5 при полном отказе картинка НЕ отправлена", S.send_generation_result_by_url.await_count == 0)
check("6.6 изюминки возвращены", refunds == [(42, 5)], str(refunds))
check("6.7 пользователю отправлено сообщение об ошибке", app2.bot.send_message.await_count >= 1)

# 6.8: gpt5 в job -> первая модель gpt-5-image
class FakeOkSession(FakeSession):
    def post(self, url, headers=None, json=None, timeout=None, **kw):
        img_calls.append(json)
        body = {"choices": [{"message": {"images": [{"url": "data:image/png;base64," + ok_png_b64}]}}]}
        return FakeResp(status=200, body=body)


S.aiohttp.ClientSession = FakeOkSession
S.send_generation_result_by_url.reset_mock()
job3 = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=10, image_model="gpt5")
img_calls.clear()
asyncio.run(S.generate_image_by_job(types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None), job3))
check("6.8 job.image_model=gpt5 -> модель openai/gpt-5-image",
      img_calls and img_calls[0].get("model") == S.ZVENO_GPT5_IMAGE_MODEL, str(img_calls[0].get("model") if img_calls else None))
check("6.9 gpt5 успех с первой попытки", S.send_generation_result_by_url.await_count == 1)

# 6.10: non-2xx (400) на 1-й попытке -> continue -> успех на 2-й
attempt_counter = {"n": 0}


class FakeFlakySession(FakeSession):
    def post(self, url, headers=None, json=None, timeout=None, **kw):
        attempt_counter["n"] += 1
        if attempt_counter["n"] == 1:
            return FakeResp(status=400, body={"error": {"message": "bad image_config"}})
        body = {"choices": [{"message": {"images": [{"url": "data:image/png;base64," + ok_png_b64}]}}]}
        return FakeResp(status=200, body=body)


S.aiohttp.ClientSession = FakeFlakySession
S.send_generation_result_by_url.reset_mock()
job4 = S.GenerationJob(chat_id=1, user_id=1, prompt="тест", references=[], cost=5, image_model="gemini")
asyncio.run(S.generate_image_by_job(types.SimpleNamespace(bot=AsyncMock(), create_task=lambda c: None), job4))
check("6.10 HTTP 400 на 1-й попытке не валит генерацию", S.send_generation_result_by_url.await_count == 1,
      f"attempts={attempt_counter['n']}")

for name, fn in _orig.items():
    setattr(S, name, fn)
S.aiohttp.ClientSession = _orig_cs
S.RESULTS_CHANNEL_ID = _orig_channel

# ════════════════ БЛОК 7: кнопка «Оживить» (callback) ════════════════
print("Блок 7: animate_last")


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


# 7.1 нет последней генерации
update, context, query = make_update_context("animate_last", user_id=701)
S.last_generated_image_url.pop(701, None)
asyncio.run(S.button_handler(update, context))
msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
check("7.1 без генерации — мягкое сообщение", any("Не нашла" in m for m in msgs), str(msgs))

# 7.2 есть генерация -> буфер заполняется, меню открывается
update, context, query = make_update_context("animate_last", user_id=702)
S.last_generated_image_url[702] = "https://example.com/gen.png"
asyncio.run(S.button_handler(update, context))
st7 = context.user_data.get("state")
check("7.2 картинка попала в видео-буфер", st7 and st7.animation_source_urls == ["https://example.com/gen.png"],
      str(getattr(st7, "animation_source_urls", None)))
check("7.3 видео-сессия активирована", st7 and st7.motion_session_active is True)
msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
check("7.4 показано видео-меню (статус-текст)", any("Модель:" in m for m in msgs), str(msgs)[:200])

# 7.5 стейлый __img__ ref
update, context, query = make_update_context("animate_last", user_id=703)
S.last_generated_image_url[703] = "__img_deadbeef00__"
asyncio.run(S.button_handler(update, context))
msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
check("7.5 стейлый __img__ -> мягкое сообщение", any("Не нашла" in m for m in msgs), str(msgs)[:200])

# 7.6 переключение видео-модели через callback
update, context, query = make_update_context("video_model_kling3", user_id=704)
asyncio.run(S.button_handler(update, context))
st8 = context.user_data.get("state")
check("7.6 callback video_model_kling3 ставит модель", st8 and st8.motion_model == "kling3")

update, context, query = make_update_context("video_model_veo31", user_id=705)
context.user_data["state"] = S.UserState(motion_aspect_ratio="1:1")
asyncio.run(S.button_handler(update, context))
st9 = context.user_data["state"]
check("7.7 veo31 сбрасывает аспект 1:1 -> 16:9", st9.motion_model == "veo31" and st9.motion_aspect_ratio == "16:9",
      f"model={st9.motion_model} aspect={st9.motion_aspect_ratio}")

# 7.8 выбор модели картинок через callback
update, context, query = make_update_context("image_model_set_gpt5", user_id=706)
asyncio.run(S.button_handler(update, context))
st10 = context.user_data.get("state")
check("7.8 image_model_set_gpt5 ставит gpt5", st10 and st10.image_model == "gpt5")

update, context, query = make_update_context("image_model_menu", user_id=707)
asyncio.run(S.button_handler(update, context))
msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
check("7.9 image_model_menu показывает меню", any("Модель генерации картинок" in m for m in msgs), str(msgs)[:200])

# ════════════════ ИТОГ ════════════════
print()
print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
for name, detail in FAIL:
    print(f"  FAIL {name}: {detail}")
sys.exit(1 if FAIL else 0)
