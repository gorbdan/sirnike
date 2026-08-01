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
import time
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
check("1.7 базовая цена gpt5 = 25", S.get_image_model_base_cost("gpt5") == 25,
      f"got={S.get_image_model_base_cost('gpt5')}")
check("1.8 calc_generation_cost gemini без рефов", S.calc_generation_cost(None, "gemini") == 5)
check("1.9 calc_generation_cost gpt5 без рефов", S.calc_generation_cost(None, "gpt5") == 25)
_orig_ref_cost = S.REFERENCE_COST
S.REFERENCE_COST = 2
check("1.10 надбавка за рефы складывается", S.calc_generation_cost(["x"], "gpt5") == 27)
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
check("1.13 меню: цены в кнопках", any("5 🍇" in t for t in texts) and any("25 🍇" in t for t in texts), str(texts))
check("1.14 текст меню упоминает обе модели",
      "Nano Banana 2" in S.image_model_menu_text(st) and "GPT-5 Image" in S.image_model_menu_text(st))

# ════════════════ БЛОК 2: видео-хелперы ════════════════
print("Блок 2: видео-модели")
st2 = S.UserState()
for code, expected in [("seedance2", "seedance2"), ("seedance2_fast", "seedance2_fast"),
                       ("kling3", "kling3"), ("veo31", "veo31"), ("мусор", "seedance2")]:
    st2.video_model = code
    check(f"2.1 get_video_model({code})={expected}", S.get_video_model(st2) == expected)

_k, _v = S.KLING3_ENABLED, S.VEO31_ENABLED
S.KLING3_ENABLED = False
st2.video_model = "kling3"
check("2.2 kling3 при выключенном флаге -> seedance2", S.get_video_model(st2) == "seedance2")
S.KLING3_ENABLED = _k
S.VEO31_ENABLED = False
st2.video_model = "veo31"
check("2.3 veo31 при выключенном флаге -> seedance2", S.get_video_model(st2) == "seedance2")
S.VEO31_ENABLED = _v

check("2.4 label kling3", S.get_video_model_label("kling3") == "Kling 3.0 🆕")
check("2.5 label veo31", S.get_video_model_label("veo31") == "Veo 3.1 (Google) 🆕")
check("2.6 цена kling3 = 8.0", S.get_video_model_cost_per_second("kling3") == 8.0)
check("2.7 цена veo31 = 8.0", S.get_video_model_cost_per_second("veo31") == 8.0)
check("2.8 цена seedance2 не сломана", S.get_video_model_cost_per_second("seedance2") == S.SEEDANCE_COST_PER_SECOND)

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
check("2.18 mode kling3 = [720p, 1080p]", S.get_seedance_mode_options("kling3") == ["720p", "1080p"])
check("2.19 mode veo31 = [720p]", S.get_seedance_mode_options("veo31") == ["720p"])

st3 = S.UserState(); st3.video_model = "veo31"; st3.video_mode = "480p"
check("2.20 selected mode veo31 принудительно 720p", S.get_selected_seedance_mode(st3) == "720p")
st3.video_duration = 15
check("2.21 selected duration veo31 при 15 -> из options", S.get_selected_seedance_duration(st3) in (4, 6, 8))

check("2.22 стоимость 5с kling3 = 40 изюм", S.calc_seedance_cost(5, 8.0) == 40)
check("2.23 стоимость 8с veo31 = 64 изюм", S.calc_seedance_cost(8, 8.0) == 64)

# ════════════════ БЛОК 3: клавиатуры ════════════════
print("Блок 3: клавиатуры")
st4 = S.UserState(); st4.video_model = "kling3"
kb4 = S.video_kb(st4)
flat4 = [b for row in kb4.inline_keyboard for b in row]
cbs4 = [b.callback_data for b in flat4 if b.callback_data]
# Блок кнопок-моделей убран из полной панели (ТЗ video_panel_declutter):
# модель видна текстом в шапке, вместо переключателей — одна кнопка смены.
check("3.1 в полной панели НЕТ кнопок video_model_*", not any(c.startswith("video_model_") for c in cbs4), str(cbs4))
check("3.2 есть кнопка «Сменить модель»", "video_change_model" in cbs4)
check("3.3 модель в пикере: маркеров ● на моделях в панели нет",
      not any(b.text.startswith("● ") and "Kling" in b.text for b in flat4))
check("3.4 у kling3 есть кнопки качества 720/1080", "video_mode_720" in cbs4 and "video_mode_1080" in cbs4, str(cbs4))
check("3.5 у kling3 есть 1:1 и 4:3 аспект",
      any(c == "video_aspect_1x1" for c in cbs4) and any(c == "video_aspect_4x3" for c in cbs4))
dur_btns = [b.text for b in flat4 if (b.callback_data or "").startswith("video_duration_")]
check("3.6 цена в кнопке 5с = 40 🍇", any("5с · 40 🍇" in t for t in dur_btns), str(dur_btns))

st5 = S.UserState(); st5.video_model = "veo31"
kb5 = S.video_kb(st5)
cbs5 = [b.callback_data for row in kb5.inline_keyboard for b in row if b.callback_data]
check("3.7 у veo31 НЕТ 1:1 и 4:3 аспекта",
      "video_aspect_1x1" not in cbs5 and "video_aspect_4x3" not in cbs5, str(cbs5))
check("3.8 у veo31 есть 16:9 и 9:16", "video_aspect_16x9" in cbs5 and "video_aspect_9x16" in cbs5)
durs5 = [c for c in cbs5 if c.startswith("video_duration_")]
check("3.9 duration кнопки veo31 только 4/6/8", set(durs5) <= {"video_duration_4", "video_duration_6", "video_duration_8"}, str(durs5))

# Кнопка есть ⇔ действие возможно (docs/UI_STYLE.md, правило 0)
st_e = S.UserState()
cbs_e = [b.callback_data for row in S.video_kb(st_e).inline_keyboard for b in row if b.callback_data]
check("3.30 пустой видео-черновик: НЕТ video_start", "video_start" not in cbs_e, str(cbs_e))
st_f = S.UserState(); st_f.video_prompt = "закат"
cbs_f = [b.callback_data for row in S.video_kb(st_f).inline_keyboard for b in row if b.callback_data]
check("3.31 видео с описанием: есть video_start", "video_start" in cbs_f)
pd_e = S.UserState()
cbs_pd = [b.callback_data for row in S.photo_draft_kb(pd_e).inline_keyboard for b in row if b.callback_data]
check("3.32 пустой фото-черновик: НЕТ generate, есть библиотека и меню",
      "generate" not in cbs_pd and any(c in cbs_pd for c in ("pl_open_webapp", "pl_open")) and "reset" in cbs_pd, str(cbs_pd))
pd_f = S.UserState(); pd_f.prompt = "девушка на фоне заката"
cbs_pf = [b.callback_data for row in S.photo_draft_kb(pd_f).inline_keyboard for b in row if b.callback_data]
check("3.33 фото-черновик с описанием: есть generate", "generate" in cbs_pf, str(cbs_pf))
check("3.34 текст пустого фото-черновика зовёт выбрать стиль",
      "Стиль или описание: пока нет" in S.photo_draft_text(pd_e))
check("3.35 текст заполненного фото-черновика показывает описание ✅",
      "Описание: «девушка на фоне заката» ✅" in S.photo_draft_text(pd_f), S.photo_draft_text(pd_f))

stxt = S.video_status_text(st4)
check("3.10 статус-текст содержит Kling 3.0 и стоимость", "Kling 3.0" in stxt and "изюминок" in stxt)

# Экран выбора модели видео (первый шаг «🎬 Видео для Reels», решение Ани
# 2026-07-31) — только модели + назад, БЕЗ длительности/формата/качества,
# которые появляются лишь после выбора (та же панель video_kb, редактированием).
pkb = S.video_model_picker_kb()
pcbs = [b.callback_data for row in pkb.inline_keyboard for b in row if b.callback_data]
check("3.36 пикер модели видео: только модели + назад, без настроек",
      all(c.startswith("video_model_") or c == "avatar_back_menu" for c in pcbs)
      and "video_model_seedance2" in pcbs, str(pcbs))
check("3.37 пикер модели видео: нет кнопок длительности/формата/качества",
      not any(c.startswith(("video_duration_", "video_aspect_", "video_mode_")) for c in pcbs), str(pcbs))
# ТЗ 2026-08-01: сетка 2 в ряд — не по одной модели на всю ширину. Последний
# ряд — «В меню» отдельно; ряды моделей не шире 2 кнопок.
_prow_sizes = [len(r) for r in pkb.inline_keyboard]
check("3.37b пикер: ряды моделей по 2 кнопки, «В меню» отдельным рядом",
      all(n <= 2 for n in _prow_sizes[:-1]) and _prow_sizes[-1] == 1
      and any(n == 2 for n in _prow_sizes[:-1]), str(_prow_sizes))

# ТЗ video_panel_declutter: пикер не показывается повторно, если модель уже
# выбиралась в этой сессии; «Сменить модель» возвращает в пикер; reset
# переносит выбор как липкую настройку.
st_vp = S.UserState()
check("3.38 свежий стейт: video_model_picked=False", st_vp.video_model_picked is False)

kb6 = S.result_actions_kb(user_id=123, bot_username="TestBot")
cbs6 = [b.callback_data for row in kb6.inline_keyboard for b in row if b.callback_data]
check("3.11 result_actions с user_id содержит animate_last", "animate_last" in cbs6, str(cbs6))
check("3.11a result_actions содержит image_model_menu (настройка модели под результатом)",
      "image_model_menu" in cbs6, str(cbs6))
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
check("3.14 главное меню: только входы в разделы «Фото»/«Видео», без прямых продуктовых кнопок",
      "menu_photo" in mcbs and "menu_video" in mcbs
      and not any(c in mcbs for c in ("generate", "video", "avatar_actions", "enhance_photo", "image_model_menu")),
      str(mcbs))

pkb = S.photo_menu_kb()
pcbs = [b.callback_data for row in pkb.inline_keyboard for b in row if b.callback_data]
check("3.14a раздел «Фото»: генерация/улучшение/аватар/модель картинок + назад",
      all(c in pcbs for c in ("generate", "enhance_photo", "avatar_actions", "image_model_menu", "avatar_back_menu")),
      str(pcbs))

vkb = S.video_menu_kb()
vcbs = [b.callback_data for row in vkb.inline_keyboard for b in row if b.callback_data]
check("3.14b раздел «Видео»: запуск видео + назад",
      "video" in vcbs and "avatar_back_menu" in vcbs, str(vcbs))

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
check("5.2 kling3: generate_audio=True", p.get("generate_audio") is True)
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
check("5.13 veo31: generate_audio=True", p.get("generate_audio") is True)

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
check("7.3 видео-сессия активирована", st7 and st7.video_session_active is True)
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
check("7.6 callback video_model_kling3 ставит модель", st8 and st8.video_model == "kling3")

update, context, query = make_update_context("video_model_veo31", user_id=705)
context.user_data["state"] = S.UserState(video_aspect_ratio="1:1")
asyncio.run(S.button_handler(update, context))
st9 = context.user_data["state"]
check("7.7 veo31 сбрасывает аспект 1:1 -> 16:9", st9.video_model == "veo31" and st9.video_aspect_ratio == "16:9",
      f"model={st9.video_model} aspect={st9.video_aspect_ratio}")

# 7.7b kling3: выбор 1080p через video_mode_ callback теперь применяется
update, context, query = make_update_context("video_model_kling3", user_id=7041)
asyncio.run(S.button_handler(update, context))
update.callback_query.data = "video_mode_1080"
asyncio.run(S.button_handler(update, context))
st8b = context.user_data["state"]
check("7.7b kling3: video_mode_1080 переключает режим",
      st8b.video_model == "kling3" and st8b.video_mode == "1080p", f"mode={st8b.video_mode}")

# 7.7c 4:3 принимается как валидный аспект
update, context, query = make_update_context("video_aspect_4x3", user_id=7042)
context.user_data["state"] = S.UserState(video_model="seedance2")
asyncio.run(S.button_handler(update, context))
st8c = context.user_data["state"]
check("7.7c video_aspect_4x3 ставит 4:3", st8c.video_aspect_ratio == "4:3", f"aspect={st8c.video_aspect_ratio}")

# 7.7d ТЗ video_panel_declutter: выбор модели ставит video_model_picked;
# повторный вход в «видео» пропускает пикер (сразу полная панель);
# «Сменить модель» возвращает пикер; reset переносит выбор.
update, context, query = make_update_context("video_model_kling3", user_id=7043)
asyncio.run(S.button_handler(update, context))
st8d = context.user_data["state"]
check("7.7d выбор модели ставит video_model_picked", st8d.video_model_picked is True)

update.callback_query.data = "video"
asyncio.run(S.button_handler(update, context))
_texts8d = [c.args[0] for c in update.callback_query.message.reply_text.await_args_list]
check("7.7e повторный вход: пикер пропущен, сразу статус-панель",
      any("Модель:" in t for t in _texts8d) and not any("Выбери модель" in t for t in _texts8d), str(_texts8d))

update.callback_query.data = "video_change_model"
asyncio.run(S.button_handler(update, context))
_edit8d = update.callback_query.message.edit_text.await_args_list
check("7.7f «Сменить модель» рисует пикер тем же сообщением",
      any("Выбери модель" in (c.args[0] if c.args else c.kwargs.get("text", "")) for c in _edit8d), str(_edit8d))

update.callback_query.data = "reset"
asyncio.run(S.button_handler(update, context))
st8r = context.user_data["state"]
check("7.7g reset переносит video_model и video_model_picked",
      st8r.video_model == "kling3" and st8r.video_model_picked is True,
      f"model={st8r.video_model} picked={st8r.video_model_picked}")

# 7.8 выбор модели картинок через callback
update, context, query = make_update_context("image_model_set_gpt5", user_id=706)
asyncio.run(S.button_handler(update, context))
st10 = context.user_data.get("state")
check("7.8 image_model_set_gpt5 ставит gpt5", st10 and st10.image_model == "gpt5")

update, context, query = make_update_context("image_model_menu", user_id=707)
asyncio.run(S.button_handler(update, context))
msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
check("7.9 image_model_menu показывает меню", any("Модель генерации картинок" in m for m in msgs), str(msgs)[:200])

# ════════════════ БЛОК 8: видео-воронка (длиннее / апгрейд) ════════════════
print("Блок 8: видео-воронка")

# 8.1 seedance2_fast 5с: длиннее 10с (5.4*10=54) + апгрейд (6.75*5=33.75->34)
S.last_video_params[801] = {"model": "seedance2_fast", "duration": 5, "mode": "720p",
                            "aspect": "9:16", "prompt": "тест", "refs": ["https://example.com/a.png"]}
kbu, has_up = S.video_upsell_kb(801)
btns = [b for row in kbu.inline_keyboard for b in row]
cbs = [b.callback_data for b in btns]
texts = [b.text for b in btns]
check("8.1 fast 5с: есть «длиннее 10 сек»", "video_longer_10" in cbs, str(cbs))
check("8.2 fast 5с: цена длиннее = 54 изюм", any("10с · 54 🍇" in t for t in texts), str(texts))
check("8.3 fast 5с: есть апгрейд в Seedance 2", "video_upgrade_seedance2" in cbs)
check("8.4 fast 5с: цена апгрейда = 34 изюм", any("Seedance 2 — 34 🍇" in t for t in texts), str(texts))
check("8.5 fast 5с: has_upsell=True", has_up is True)
check("8.6 есть кнопка «Ещё видео»", "video" in cbs)

# 8.7 fast 10с -> длиннее 15с
S.last_video_params[802] = {"model": "seedance2_fast", "duration": 10, "mode": "720p",
                            "aspect": "16:9", "prompt": "", "refs": []}
kbu, _ = S.video_upsell_kb(802)
cbs = [b.callback_data for row in kbu.inline_keyboard for b in row]
check("8.7 fast 10с: длиннее = 15", "video_longer_15" in cbs, str(cbs))

# 8.8 kling3 на максимуме (15с): нет длиннее, нет апгрейда
S.last_video_params[803] = {"model": "kling3", "duration": 15, "mode": "720p",
                            "aspect": "16:9", "prompt": "", "refs": []}
kbu, has_up = S.video_upsell_kb(803)
cbs = [b.callback_data for row in kbu.inline_keyboard for b in row]
check("8.8 kling3 15с: нет «длиннее»", not any(c.startswith("video_longer_") for c in cbs), str(cbs))
check("8.9 kling3: нет апгрейда (не fast)", "video_upgrade_seedance2" not in cbs)
check("8.10 kling3 15с: has_upsell=False", has_up is False)

# 8.11 veo31 4с -> длиннее 6с
S.last_video_params[804] = {"model": "veo31", "duration": 4, "mode": "720p",
                            "aspect": "16:9", "prompt": "", "refs": []}
kbu, _ = S.video_upsell_kb(804)
cbs = [b.callback_data for row in kbu.inline_keyboard for b in row]
check("8.11 veo31 4с: длиннее = 6", "video_longer_6" in cbs, str(cbs))

# 8.12 нет параметров
S.last_video_params.pop(805, None)
kbu, has_up = S.video_upsell_kb(805)
check("8.12 нет параметров -> (None, False)", kbu is None and has_up is False)

# 8.13 колбэк video_longer_10 восстанавливает параметры и запускает генерацию
started = []
_orig_run_seedance = S.run_seedance


async def fake_run_seedance(update, context):
    started.append(True)

S.run_seedance = fake_run_seedance
S.last_video_params[806] = {"model": "seedance2_fast", "duration": 5, "mode": "720p",
                            "aspect": "9:16", "prompt": "кот танцует",
                            "refs": ["https://example.com/cat.png"]}
update, context, query = make_update_context("video_longer_10", user_id=806)
context.application = types.SimpleNamespace(create_task=lambda c: (started.append("task"), c.close()))
asyncio.run(S.button_handler(update, context))
st11 = context.user_data.get("state")
check("8.13 длиннее: duration=10", st11 and st11.video_duration == 10,
      f"dur={getattr(st11, 'video_duration', None)}")
check("8.14 длиннее: модель сохранена (fast)", st11.video_model == "seedance2_fast")
check("8.15 длиннее: реф восстановлен", st11.animation_source_urls == ["https://example.com/cat.png"])
check("8.16 длиннее: промт восстановлен", st11.video_prompt == "кот танцует")
check("8.17 длиннее: генерация запущена", "task" in started, str(started))
S.processing_user_ids.discard(806)

# 8.18 колбэк video_upgrade_seedance2: модель меняется, длительность та же
S.last_video_params[807] = {"model": "seedance2_fast", "duration": 10, "mode": "720p",
                            "aspect": "16:9", "prompt": "пёс бежит",
                            "refs": ["https://example.com/dog.png"]}
update, context, query = make_update_context("video_upgrade_seedance2", user_id=807)
context.application = types.SimpleNamespace(create_task=lambda c: c.close())
asyncio.run(S.button_handler(update, context))
st12 = context.user_data.get("state")
check("8.18 апгрейд: модель seedance2", st12 and st12.video_model == "seedance2",
      f"model={getattr(st12, 'video_model', None)}")
check("8.19 апгрейд: длительность сохранена (10)", st12.video_duration == 10)
check("8.20 апгрейд: реф восстановлен", st12.animation_source_urls == ["https://example.com/dog.png"])
S.processing_user_ids.discard(807)

# 8.21 колбэк без параметров — мягкое сообщение
S.last_video_params.pop(808, None)
update, context, query = make_update_context("video_longer_10", user_id=808)
asyncio.run(S.button_handler(update, context))
msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
check("8.21 без параметров — мягкое сообщение", any("Не нашла параметры" in m for m in msgs), str(msgs)[:200])

# 8.22 стейлый __img__ реф — мягкое сообщение
S.last_video_params[809] = {"model": "seedance2", "duration": 5, "mode": "720p",
                            "aspect": "16:9", "prompt": "", "refs": ["__img_dead00beef__"]}
update, context, query = make_update_context("video_longer_10", user_id=809)
asyncio.run(S.button_handler(update, context))
msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
check("8.22 стейлый реф — мягкое сообщение", any("устарело" in m for m in msgs), str(msgs)[:200])

# 8.23 занятый пользователь — alert, генерация не стартует
S.last_video_params[810] = {"model": "seedance2_fast", "duration": 5, "mode": "720p",
                            "aspect": "16:9", "prompt": "", "refs": []}
S.processing_user_ids.add(810)
update, context, query = make_update_context("video_longer_10", user_id=810)
asyncio.run(S.button_handler(update, context))
check("8.23 занят — query.answer с предупреждением",
      any("другая задача" in str(c) for c in query.answer.await_args_list), str(query.answer.await_args_list))
S.processing_user_ids.discard(810)

S.run_seedance = _orig_run_seedance

# ════════════════ БЛОК 9: кнопка есть ⇔ действие возможно (фиксы 2, 3, 4) ════════════════
print("Блок 9: улучшить фото / аватар / видео-модели без жаргона")
S.init_db()  # handle_text вызывает create_user_if_not_exists — нужны таблицы


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


# 9.1 текст в режиме «Улучшить фото» — не перезаписывает промт молча
st_enh = S.UserState()
st_enh.prompt = S.ENHANCE_PHOTO_PROMPT
update, context, message = make_text_update("сделай поярче", user_id=901, state=st_enh)
asyncio.run(S.handle_text(update, context))
msgs = [c.args[0] for c in message.reply_text.await_args_list]
check("9.1 текст в enhance-режиме не меняет state.prompt",
      context.user_data["state"].prompt == S.ENHANCE_PHOTO_PROMPT, context.user_data["state"].prompt)
check("9.2 текст в enhance-режиме предлагает выбор, не молчит",
      any("жду фото" in m for m in msgs), str(msgs))
check("9.3 pending text сохранён для enhance_use_pending_text",
      context.user_data.get("enhance_pending_text") == "сделай поярче")

# 9.4 enhance_use_pending_text превращает сохранённый текст в обычный промт
update, context, query = make_update_context("enhance_use_pending_text", user_id=902)
context.user_data["state"] = S.UserState(prompt=S.ENHANCE_PHOTO_PROMPT)
context.user_data["enhance_pending_text"] = "кот в космосе"
asyncio.run(S.button_handler(update, context))
st_after = context.user_data["state"]
check("9.4 промт стал обычным описанием", st_after.prompt == "кот в космосе", st_after.prompt)
check("9.5 pending text очищен после использования", "enhance_pending_text" not in context.user_data)

# 9.6 avatar_gen_refsheet включает приём фото сразу, без выбора типа
update, context, query = make_update_context("avatar_gen_refsheet", user_id=903)
asyncio.run(S.button_handler(update, context))
st_av = context.user_data["state"]
check("9.6 generating_avatar включён сразу", st_av.generating_avatar is True)
check("9.7 pending_avatar_kind ещё не выбран", st_av.pending_avatar_kind == "")

# 9.8 avatar_gen_start без выбранного типа — alert, генерация не стартует
update, context, query = make_update_context("avatar_gen_start", user_id=904)
st_av2 = S.UserState(generating_avatar=True)
st_av2.avatar_photos = ["https://example.com/face.png"]
context.user_data["state"] = st_av2
asyncio.run(S.button_handler(update, context))
check("9.9 без типа — alert «выбери тип аватара»",
      any("тип аватара" in str(c) for c in query.answer.await_args_list), str(query.answer.await_args_list))

# 9.10 выбор типа не стирает уже загруженные фото
update, context, query = make_update_context("avatar_gen_kind_male", user_id=905)
st_av3 = S.UserState(generating_avatar=True)
st_av3.avatar_photos = ["https://example.com/a.png", "https://example.com/b.png"]
context.user_data["state"] = st_av3
asyncio.run(S.button_handler(update, context))
st_av3_after = context.user_data["state"]
check("9.10 тип выбран", st_av3_after.pending_avatar_kind == "male")
check("9.11 фото не стёрлись при выборе типа", len(st_av3_after.avatar_photos) == 2, st_av3_after.avatar_photos)

# 9.12 видео-панель: пояснение модели вместо жаргона «для Seedance»
st_blurb = S.UserState(video_model="seedance2")
blurb_text = S.video_status_text(st_blurb)
check("9.12 статус видео содержит пояснение модели",
      "максимум качества" in blurb_text, blurb_text[:200])
update, context, query = make_update_context("video_set_image", user_id=906)
asyncio.run(S.button_handler(update, context))
msgs = [c.args[0] for c in query.message.reply_text.await_args_list]
check("9.13 без жаргона «для Seedance»", not any("для Seedance" in m for m in msgs), str(msgs))

# 9.14 via_bot-заглушка (answerWebAppQuery, docs/specs/2026-07-17_via_bot_message_leak.md)
# не затирает уже выбранный стиль в state.prompt
st_leak = S.UserState(prompt="реальный промт выбранного стиля")
update, context, message = make_text_update(
    "📚 Стиль подобран — жми ниже 👇", user_id=907, state=st_leak,
)
context.bot.id = 999999
message.via_bot = types.SimpleNamespace(id=999999)
asyncio.run(S.handle_text(update, context))
check("9.14 via_bot-заглушка не трогает state.prompt",
      context.user_data["state"].prompt == "реальный промт выбранного стиля",
      context.user_data["state"].prompt)
check("9.15 via_bot-заглушка не шлёт ответных сообщений",
      message.reply_text.await_args_list == [], str(message.reply_text.await_args_list))

# 9.16 обычный текст от юзера (via_bot=None) по-прежнему работает как раньше
st_normal = S.UserState()
update, context, message = make_text_update("кот в шляпе", user_id=908, state=st_normal)
context.bot.id = 999999
message.via_bot = None
asyncio.run(S.handle_text(update, context))
check("9.16 обычный текст всё ещё сохраняется в state.prompt",
      context.user_data["state"].prompt == "кот в шляпе", context.user_data["state"].prompt)

# 9.17 pl_use_ на inline-сообщении (answerWebAppQuery, query.message=None) —
# docs/specs/2026-07-15_webapp_inline_1tap.md: Bot API гарантирует ровно одно
# из полей message/inline_message_id у callback_query. Раньше query.message.
# reply_text() падал AttributeError молча (state успевал выставиться, юзер
# не видел подтверждения) — живой баг 2026-07-17.
update, context, query = make_update_context("pl_use_0_0", user_id=909)
query.message = None
asyncio.run(S.button_handler(update, context))
st917 = context.user_data.get("state")
check("9.17 pl_use_ на inline-сообщении не падает и выставляет state.prompt",
      isinstance(st917, S.UserState) and bool(st917.prompt), getattr(st917, "prompt", None))
check("9.18 pl_use_ на inline-сообщении шлёт подтверждение через bot.send_message",
      context.bot.send_message.await_args_list != [], str(context.bot.send_message.await_args_list))

# 9.19 pl_usen_ — «свои пожелания» из инлайн-1-тапа (base64url в callback_data,
# docs/specs/2026-07-17_inline_note_passthrough.md)
_note = "каре, блонд"
_enc = base64.urlsafe_b64encode(_note.encode("utf-8")).decode("ascii").rstrip("=")
update, context, query = make_update_context(f"pl_usen_0_0_{_enc}", user_id=910)
asyncio.run(S.button_handler(update, context))
st919 = context.user_data.get("state")
check("9.19 pl_usen_ дописывает note в state.prompt",
      isinstance(st919, S.UserState) and _note in st919.prompt, getattr(st919, "prompt", None))
sent_texts = [c.args[0] for c in query.message.reply_text.await_args_list]
check("9.20 pl_usen_ показывает «Учла твои пожелания» вместо статичного описания",
      any(_note in t and "Учла твои пожелания" in t for t in sent_texts), str(sent_texts))

# 9.21 apply_user_note_override — усиленный override вместо слабой приписки
# (docs/specs/2026-07-17_note_override_weak.md: «follow this instead of the
# generic description above» проигрывала плотному дефолтному описанию образа)
_base = "Soft glam makeup: warm bronze eyeshadow, nude-pink lips."
_overridden = S.apply_user_note_override(_base, "ярко-красная помада, стрелки")
check("9.21 override содержит явный маркер MOST IMPORTANT OVERRIDE",
      "MOST IMPORTANT OVERRIDE" in _overridden, _overridden)
check("9.22 override сохраняет и дефолтный текст, и note (для контекста лица/фото)",
      _base in _overridden and "ярко-красная помада, стрелки" in _overridden, _overridden)
check("9.23 override с пустым note не трогает base_prompt",
      S.apply_user_note_override(_base, "") == _base)

# ════════════════ БЛОК 10: style_extract — двухшаговый пайплайн «Образ с референса» ════════════════
print("Блок 10: style_extract (двух-референсные стили)")


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


_rg_orig = {
    name: getattr(S, name)
    for name in (
        "create_user_if_not_exists", "get_avatar_urls", "get_active_avatar_kind",
        "try_use_free_generation", "extract_style_description_from_reference",
    )
}
S.create_user_if_not_exists = lambda *a, **k: None
S.get_avatar_urls = lambda uid: {}
S.get_active_avatar_kind = lambda uid: None
S.try_use_free_generation = lambda uid, max_per_day: True

_ref1 = png_data_url(color=(10, 10, 10, 255))
_ref2 = png_data_url(color=(20, 20, 20, 255))

# 10.1: успешная экстракция — второе фото не попадает в references job'а,
# его текстовое описание дописывается в промт
S.extract_style_description_from_reference = AsyncMock(return_value="каре, блонд, нюдовая помада")
st10 = S.UserState(prompt="базовый промт стиля", references=[_ref1, _ref2], style_extract=True)
update, context, message = make_run_generation_context(st10, user_id=951)
while not S.generation_queue.empty():
    S.generation_queue.get_nowait()
asyncio.run(S.run_generation(update, context))
S.queued_user_ids.discard(951)
job10 = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
check("10.1 второе фото не попадает в references job'а",
      job10 is not None and job10.references == [_ref1], str(job10.references if job10 else None))
check("10.2 описание стиля дописано в промт",
      job10 is not None and "каре, блонд, нюдовая помада" in job10.prompt, str(job10.prompt if job10 else None))
check("10.3 style_extract сброшен после использования (one-shot)",
      context.user_data["state"].style_extract is False)

# 10.4: extract вернул None (сбой vision-вызова) — откат на старое поведение,
# оба фото уходят в job, юзер предупреждён
S.extract_style_description_from_reference = AsyncMock(return_value=None)
st10b = S.UserState(prompt="базовый промт стиля", references=[_ref1, _ref2], style_extract=True)
update, context, message = make_run_generation_context(st10b, user_id=952)
while not S.generation_queue.empty():
    S.generation_queue.get_nowait()
asyncio.run(S.run_generation(update, context))
S.queued_user_ids.discard(952)
job10b = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
check("10.4 сбой vision-вызова -> оба фото в job (откат на старое поведение)",
      job10b is not None and job10b.references == [_ref1, _ref2], str(job10b.references if job10b else None))
warn_texts = [c.args[0] for c in message.reply_text.await_args_list]
check("10.5 юзер предупреждён о сбое разбора референса",
      any("не удалось разобрать референс" in t.lower() for t in warn_texts), str(warn_texts))

# 10.6: флаг не выставлен (обычный стиль) — оба фото уходят как обычно, vision не вызывается
S.extract_style_description_from_reference = AsyncMock(return_value="не должно вызваться")
st10c = S.UserState(prompt="базовый промт стиля", references=[_ref1, _ref2], style_extract=False)
update, context, message = make_run_generation_context(st10c, user_id=953)
while not S.generation_queue.empty():
    S.generation_queue.get_nowait()
asyncio.run(S.run_generation(update, context))
S.queued_user_ids.discard(953)
job10c = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
check("10.6 style_extract=False -> vision не вызывается, оба фото в job",
      job10c is not None and job10c.references == [_ref1, _ref2] and not S.extract_style_description_from_reference.await_args_list,
      str(job10c.references if job10c else None))

# 10.7: гейт — style_extract=True, 0 фото -> генерация не запускается,
# job в очередь не попадает, юзер получает понятный запрос на 2 фото
S.extract_style_description_from_reference = AsyncMock(return_value="не должно вызваться")
st10d = S.UserState(prompt="базовый промт стиля", references=[], style_extract=True)
update, context, message = make_run_generation_context(st10d, user_id=954)
while not S.generation_queue.empty():
    S.generation_queue.get_nowait()
asyncio.run(S.run_generation(update, context))
S.queued_user_ids.discard(954)
job10d = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
check("10.7 гейт: 0 фото -> job не создаётся", job10d is None)
gate_texts_d = [c.args[0] for c in message.reply_text.await_args_list]
check("10.8 гейт: 0 фото -> просит 2 фото по порядку",
      any("нужны 2 фото" in t for t in gate_texts_d), str(gate_texts_d))

# 10.9: гейт — style_extract=True, 1 фото -> тоже блокируется
st10e = S.UserState(prompt="базовый промт стиля", references=[_ref1], style_extract=True)
update, context, message = make_run_generation_context(st10e, user_id=955)
while not S.generation_queue.empty():
    S.generation_queue.get_nowait()
asyncio.run(S.run_generation(update, context))
S.queued_user_ids.discard(955)
job10e = S.generation_queue.get_nowait() if not S.generation_queue.empty() else None
check("10.9 гейт: 1 фото -> job не создаётся", job10e is None)
gate_texts_e = [c.args[0] for c in message.reply_text.await_args_list]
check("10.10 гейт: 1 фото -> просит второе фото",
      any("есть только 1 фото" in t.lower() for t in gate_texts_e), str(gate_texts_e))
check("10.11 гейт не вызывает vision (не тратим на неполный набор фото)",
      not S.extract_style_description_from_reference.await_args_list)

for _name, _fn in _rg_orig.items():
    setattr(S, _name, _fn)

# 10.12: _set_style_extract чистит буфер референсов при включении (P0
# 2026-07-17 — персистентный буфер путал лицо с рефом стиля)
st10f = S.UserState(references=["старое-фото-с-прошлого-теста"])
S._set_style_extract(st10f, True)
check("10.12 _set_style_extract(True) очищает старый буфер references",
      st10f.references == [] and st10f.style_extract is True, str(st10f.references))
S._set_style_extract(st10f, False)
check("10.13 _set_style_extract(False) не трогает буфер (не режим style_extract)",
      st10f.style_extract is False)

# 10.14: photo_draft_text/kb — статус по слотам и кнопка «Запустить» только при 2/2
st10g = S.UserState(prompt="стиль", references=[], style_extract=True)
check("10.15 photo_draft_text 0/2", "0/2" in S.photo_draft_text(st10g, 956))
kb_0 = S.photo_draft_kb(st10g, 956)
cbs_0 = [b.callback_data for row in kb_0.inline_keyboard for b in row]
check("10.16 кнопки: 0/2 -> нет 'generate'", "generate" not in cbs_0, str(cbs_0))

st10g.references = [_ref1]
check("10.17 photo_draft_text 1/2", "1/2" in S.photo_draft_text(st10g, 956))
cbs_1 = [b.callback_data for row in S.photo_draft_kb(st10g, 956).inline_keyboard for b in row]
check("10.18 кнопки: 1/2 -> нет 'generate'", "generate" not in cbs_1, str(cbs_1))

st10g.references = [_ref1, _ref2]
check("10.19 photo_draft_text 2/2", "2/2" in S.photo_draft_text(st10g, 956))
cbs_2 = [b.callback_data for row in S.photo_draft_kb(st10g, 956).inline_keyboard for b in row]
check("10.20 кнопки: 2/2 -> есть 'generate'", "generate" in cbs_2, str(cbs_2))

# ════════════════ БЛОК 10b: «Новинки» с рассинхроном cat_idx/item_idx ════════
print("Блок 10b: библиотека — резолв title по промту при неверных индексах")


def make_webapp_update_context(user_id=9501):
    message = types.SimpleNamespace(reply_text=AsyncMock())
    update = types.SimpleNamespace(
        effective_message=message,
        effective_user=types.SimpleNamespace(id=user_id, username="test"),
        effective_chat=types.SimpleNamespace(id=user_id),
    )
    context = types.SimpleNamespace(user_data={}, application=None, bot=AsyncMock())
    return update, context, message


# Реальный стиль из PROMPT_LIBRARY, но с индексами, указывающими на ДРУГОЙ
# (несуществующий на этой позиции) стиль — воспроизводит «Новинки», которые
# шлют позицию в отфильтрованном списке, а не в реальной категории (аудиты
# 07-02/07-07/07-31). Раньше title откатывался к литералу «шаблон».
_real_item = S.PROMPT_LIBRARY[0]["items"][0]
_real_prompt = _real_item["prompt"]
update10b, context10b, msg10b = make_webapp_update_context()
asyncio.run(S.apply_webapp_prompt_payload_v2(update10b, context10b, {
    "action": "set_prompt",
    "prompt": _real_prompt,
    "cat_idx": 999, "item_idx": 999,  # заведомо не существует
}))
_texts10b = [c.args[0] for c in msg10b.reply_text.await_args_list]
check("10b.1 title резолвится по промту, а не остаётся «шаблон»",
      any("шаблон»" not in t and ("Стиль «" in t or "Готово" in t) for t in _texts10b), str(_texts10b))
check("10b.2 промт сохранён в состояние", context10b.user_data["state"].prompt == _real_prompt)

# ════════════════ БЛОК 11: баг-баунти (reward_bug_) ════════════════
print("Блок 11: баг-баунти")

_bb_target_id = 9601
S.create_user_if_not_exists(_bb_target_id, "bugfinder", S.START_BONUS)
_bal_before = S.get_balance(_bb_target_id)

# 11.1: не-админ жмёт "Наградить" -> нет доступа, баланс не меняется
update, context, query = make_update_context(f"reward_bug_{_bb_target_id}", user_id=9602)
query.edit_message_reply_markup = AsyncMock()
_orig_admin_ids = list(S.ADMIN_IDS)
if 9602 in S.ADMIN_IDS:
    S.ADMIN_IDS.remove(9602)
asyncio.run(S.button_handler(update, context))
check("11.1 не-админ: доступ запрещён", query.answer.await_args_list and "доступ" in query.answer.await_args_list[-1].args[0].lower(),
      str(query.answer.await_args_list))
check("11.2 не-админ: баланс не изменился", S.get_balance(_bb_target_id) == _bal_before)

# 11.3: админ жмёт "Наградить" -> баланс +BUG_BOUNTY_REWARD, уведомление юзеру,
# клавиатура заменена на "Награждено"
_admin_id = 9603
S.ADMIN_IDS.append(_admin_id)
update, context, query = make_update_context(f"reward_bug_{_bb_target_id}", user_id=_admin_id)
query.edit_message_reply_markup = AsyncMock()
asyncio.run(S.button_handler(update, context))
check("11.3 админ: баланс увеличен на BUG_BOUNTY_REWARD",
      S.get_balance(_bb_target_id) == _bal_before + S.BUG_BOUNTY_REWARD,
      f"before={_bal_before} after={S.get_balance(_bb_target_id)}")
notify_calls = [c for c in context.bot.send_message.await_args_list if c.kwargs.get("chat_id") == _bb_target_id]
check("11.4 админ: юзер получил уведомление о награде",
      bool(notify_calls) and "🎉" in notify_calls[-1].kwargs.get("text", ""), str(notify_calls))
check("11.5 админ: клавиатура заменена на 'Награждено'",
      query.edit_message_reply_markup.await_args_list != [], str(query.edit_message_reply_markup.await_args_list))

S.ADMIN_IDS[:] = _orig_admin_ids

# 11.6: bug_bounty_command выставляет waiting_for_bug_report и шлёт инструкцию
update, context, message = make_text_update("/bugbounty", user_id=9604)
asyncio.run(S.bug_bounty_command(update, context))
st11 = context.user_data.get("state")
check("11.6 bug_bounty_command взводит waiting_for_bug_report",
      isinstance(st11, S.UserState) and st11.waiting_for_bug_report is True)
sent11 = [c.args[0] for c in message.reply_text.await_args_list]
check("11.7 bug_bounty_command упоминает награду в тексте",
      any(str(S.BUG_BOUNTY_REWARD) in t and "🍇" in t for t in sent11), str(sent11))

# 11.8: текст после /bugbounty -> репорт уходит админам с bug_bounty_admin_kb
_orig_admin_ids2 = list(S.ADMIN_IDS)
S.ADMIN_IDS[:] = [9605]
update, context, message = make_text_update("кнопка X не открывается", user_id=9606, state=st11)
update.effective_user.full_name = "Bug Finder"
context.bot.send_message = AsyncMock()
asyncio.run(S.handle_text(update, context))
check("11.9 репорт улетел админу с кнопкой 'Наградить'",
      context.bot.send_message.await_args_list != [] and
      "Наградить" in str(context.bot.send_message.await_args_list[-1].kwargs.get("reply_markup")),
      str(context.bot.send_message.await_args_list))
check("11.10 waiting_for_bug_report сброшен после отправки", st11.waiting_for_bug_report is False)
check("11.11 текст репорта выставляет pending_report_kind='bug' (для скриншота вторым сообщением)",
      st11.pending_report_kind == "bug", st11.pending_report_kind)
S.ADMIN_IDS[:] = _orig_admin_ids2

# 11.12: живой баг 2026-07-19 — скриншот вторым сообщением после текста
# репорта раньше тихо утекал в обычные references генерации вместо репорта.
_orig_admin_ids3 = list(S.ADMIN_IDS)
S.ADMIN_IDS[:] = [9607]
st11b = S.UserState(pending_report_kind="bug", pending_report_kind_at=time.time())
photo_message = types.SimpleNamespace(
    photo=[types.SimpleNamespace(file_id="ph1")],
    caption=None, media_group_id=None, reply_text=AsyncMock(),
)
update = types.SimpleNamespace(
    message=photo_message,
    effective_user=types.SimpleNamespace(id=9608, username="test"),
    effective_chat=types.SimpleNamespace(id=9608),
    effective_message=photo_message,
)
context = types.SimpleNamespace(user_data={"state": st11b}, application=None, bot=AsyncMock())
asyncio.run(S.handle_photo(update, context))
check("11.12 скриншот к репорту НЕ попадает в references генерации",
      st11b.references == [], str(st11b.references))
check("11.13 скриншот к репорту пересылается админу через send_photo",
      context.bot.send_photo.await_args_list != [] and
      context.bot.send_photo.await_args_list[-1].kwargs.get("photo") == "ph1",
      str(context.bot.send_photo.await_args_list))
check("11.14 pending_report_kind сброшен после пересылки скриншота",
      st11b.pending_report_kind == "")
photo_texts = [c.args[0] for c in photo_message.reply_text.await_args_list]
check("11.15 юзер получил подтверждение 'скриншот добавлен'",
      any("скриншот добавлен" in t.lower() for t in photo_texts), str(photo_texts))
S.ADMIN_IDS[:] = _orig_admin_ids3

# 11.16: TTL истёк -> фото уходит по обычному пути (в references), не как скриншот
st11c = S.UserState(pending_report_kind="bug", pending_report_kind_at=time.time() - S.PENDING_REPORT_SCREENSHOT_TTL_SECONDS - 10)
photo_message2 = types.SimpleNamespace(
    photo=[types.SimpleNamespace(file_id="ph2")],
    caption=None, media_group_id=None, reply_text=AsyncMock(),
)
update = types.SimpleNamespace(
    message=photo_message2,
    effective_user=types.SimpleNamespace(id=9609, username="test"),
    effective_chat=types.SimpleNamespace(id=9609),
    effective_message=photo_message2,
)
context = types.SimpleNamespace(user_data={"state": st11c}, application=None, bot=AsyncMock())
context.bot.get_file = AsyncMock(return_value=types.SimpleNamespace(
    download_to_memory=AsyncMock(side_effect=lambda out: out.write(base64.b64decode(ok_png_b64)))
))
asyncio.run(S.handle_photo(update, context))
check("11.17 TTL истёк -> pending_report_kind не мешает обычной загрузке фото",
      len(st11c.references) == 1, str(st11c.references))

# 11.18: живой баг 2026-07-19 (второй за день) — текст+фото ОДНИМ сообщением
# (caption) во время ожидания репорта раньше уходило как обычный промт+реф
_orig_admin_ids4 = list(S.ADMIN_IDS)
S.ADMIN_IDS[:] = [9610]
st11d = S.UserState(waiting_for_bug_report=True)
photo_message3 = types.SimpleNamespace(
    photo=[types.SimpleNamespace(file_id="ph3")],
    caption="кнопка X не открывается", media_group_id=None, reply_text=AsyncMock(),
)
update = types.SimpleNamespace(
    message=photo_message3,
    effective_user=types.SimpleNamespace(id=9611, username="test", full_name="Bug Finder"),
    effective_chat=types.SimpleNamespace(id=9611),
    effective_message=photo_message3,
)
context = types.SimpleNamespace(user_data={"state": st11d}, application=None, bot=AsyncMock())
asyncio.run(S.handle_photo(update, context))
check("11.18 текст+фото одним сообщением НЕ становится обычным промтом",
      st11d.prompt == "", st11d.prompt)
check("11.19 текст+фото одним сообщением НЕ попадает в references",
      st11d.references == [], str(st11d.references))
check("11.20 waiting_for_bug_report сброшен", st11d.waiting_for_bug_report is False)
sent_calls = context.bot.send_message.await_args_list
check("11.21 репорт (текст) ушёл админу с кнопкой 'Наградить'",
      sent_calls != [] and "кнопка X не открывается" in sent_calls[-1].kwargs.get("text", "")
      and "Наградить" in str(sent_calls[-1].kwargs.get("reply_markup")),
      str(sent_calls))
photo_calls = context.bot.send_photo.await_args_list
check("11.22 фото из этого же сообщения тоже переслано админу",
      photo_calls != [] and photo_calls[-1].kwargs.get("photo") == "ph3", str(photo_calls))
S.ADMIN_IDS[:] = _orig_admin_ids4

# ── Блок 12: причёсывание экранов 2026-07-20 (макет утверждён Аней) ──
print("Блок 12: экраны по UI-гайду (видео-панель, отмена репорта, аватар)")

st12 = S.UserState()
vtxt = S.video_status_text(st12)
check("12.1 видео-панель озаглавлена разделом, не моделью",
      vtxt.startswith("🎬 Видео для Reels"), vtxt.splitlines()[0])
check("12.2 видео-панель не показывает сырые URL и старую инструкцию",
      "http" not in vtxt and "Фото в буфере" not in vtxt and "1. Напиши" not in vtxt, vtxt)
check("12.3 пустой видео-черновик подсказывает, с чего начать",
      "Хватит одного: описание или фото" in vtxt, vtxt)
st12.video_prompt = "кошка прыгает"
vtxt2 = S.video_status_text(st12)
check("12.4 заполненный черновик: подсказки нет, статус ✅",
      "Хватит одного" not in vtxt2 and "Описание: есть ✅" in vtxt2, vtxt2)

# report_cancel: кнопка отмены репорта не на reset, отмена не трогает черновик
import inspect as _inspect
_rp_src = _inspect.getsource(S.report_problem_command)
_bb_src = _inspect.getsource(S.bug_bounty_command)
check("12.5 отмена «Проблемы» не на reset", 'callback_data="report_cancel"' in _rp_src, _rp_src[-200:])
check("12.6 отмена «Баг-баунти» не на reset", 'callback_data="report_cancel"' in _bb_src, _bb_src[-200:])

st12r = S.UserState(waiting_for_bug_report=True)
st12r.prompt = "мой черновик"
st12r.references = ["https://example.com/ref.jpg"]
_q12 = types.SimpleNamespace(
    data="report_cancel",
    message=types.SimpleNamespace(reply_text=AsyncMock()),
    answer=AsyncMock(),
    from_user=types.SimpleNamespace(id=9712),
)
_u12 = types.SimpleNamespace(
    callback_query=_q12,
    effective_user=types.SimpleNamespace(id=9712, username="test"),
    effective_chat=types.SimpleNamespace(id=9712),
)
_c12 = types.SimpleNamespace(user_data={"state": st12r}, application=None, bot=AsyncMock())
asyncio.run(S.button_handler(_u12, _c12))
check("12.7 report_cancel снимает режим репорта", st12r.waiting_for_bug_report is False)
check("12.8 report_cancel НЕ трогает черновик",
      st12r.prompt == "мой черновик" and st12r.references == ["https://example.com/ref.jpg"],
      f"{st12r.prompt!r} {st12r.references!r}")

kb12 = S.avatar_actions_kb()
labels12 = [b.text for row in kb12.inline_keyboard for b in row]
check("12.9 кнопка аватара с 🪄 по словарю (не 🎨)",
      any(t.startswith("🪄") for t in labels12) and not any("🎨" in t for t in labels12), str(labels12))

_help_src = _inspect.getsource(S.help_command)
check("12.10 справка знает про «Улучшить фото» и без списка моделей",
      "🖼️ Улучшить фото" in _help_src and "Seedance 2, Kling" not in _help_src)

# ════════ БЛОК 13: студия мультиков — воркер D1-очереди (Ф1) ════════
print("Блок 13: студия мультиков (Ф1)")

# 13.1 цены: кадр без рефов = BASE_GENERATION_COST, клип = секунды × тариф
check("13.1 цена кадра без рефов", S._studio_compute_cost("frame", {}) == S.BASE_GENERATION_COST)
_clip_cost = S._studio_compute_cost("clip", {"model": "seedance2_fast", "duration": 5})
check("13.2 цена клипа seedance2_fast 5с",
      _clip_cost == S.calc_seedance_cost(5, S.SEEDANCE_FAST_COST_PER_SECOND), str(_clip_cost))
try:
    S._studio_compute_cost("clip", {"model": "несуществующая"})
    check("13.3 неизвестная модель клипа -> исключение", False)
except ValueError:
    check("13.3 неизвестная модель клипа -> исключение", True)
check("13.4 scenario/stitch бесплатны",
      S._studio_compute_cost("scenario", {}) == 0 and S._studio_compute_cost("stitch", {}) == 0)

# 13.5 парсер сцен: терпит ```json-забор и болтовню вокруг
_scenes = S._studio_parse_scenes(
    'Вот сцены:\n```json\n[{"frame_prompt": "cat on roof", "video_prompt": "cat jumps"},'
    '{"frame_prompt": "cat lands", "video_prompt": ""}]\n```\nГотово!'
)
check("13.5 парсер сцен достаёт JSON из забора", len(_scenes) == 2 and _scenes[0]["frame_prompt"] == "cat on roof", str(_scenes))
try:
    S._studio_parse_scenes("никакого json тут нет")
    check("13.6 мусор без JSON -> исключение", False)
except ValueError:
    check("13.6 мусор без JSON -> исключение", True)
_many = json.dumps([{"frame_prompt": f"scene {i}"} for i in range(20)])
check("13.7 парсер режет по STUDIO_MAX_SCENES",
      len(S._studio_parse_scenes(_many)) == S.STUDIO_MAX_SCENES)

# Обвязка для _studio_handle_job: мокаем сеть (complete) и генерацию
S._studio_semaphore = asyncio.Semaphore(3)
_studio_api_orig = S._studio_api
_studio_exec_orig = S._studio_execute_job

_bb_uid = 9701
_run_tag = str(int(time.time() * 1000))  # уникальные job-id: тестовая SQLite переживает прогоны
S.create_user_if_not_exists(_bb_uid, "studio_user", 0)
S.add_izyminki(_bb_uid, 100)
_bal0 = S.get_balance(_bb_uid)

# 13.8 happy path: списание, генерация, complete
S._studio_api = AsyncMock(return_value={})
S._studio_execute_job = AsyncMock(return_value={"frame_url": "https://i.ibb.co/x.png"})
_job = {"id": f"job-1-{_run_tag}", "user_id": _bb_uid, "type": "frame",
        "payload": json.dumps({"frame_prompt": "cat", "expected_cost": S.BASE_GENERATION_COST})}
asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job))
check("13.8 happy path: списано ровно по цене", S.get_balance(_bb_uid) == _bal0 - S.BASE_GENERATION_COST,
      f"bal={S.get_balance(_bb_uid)}")
_complete_calls = [c for c in S._studio_api.await_args_list if c.args[0] == "complete"]
check("13.9 happy path: complete со status=done",
      _complete_calls and _complete_calls[-1].args[1]["status"] == "done", str(_complete_calls))

# 13.10 идемпотентность: тот же job снова -> без генерации и денег, только complete
S._studio_api = AsyncMock(return_value={})
S._studio_execute_job = AsyncMock(return_value={"frame_url": "another"})
_bal1 = S.get_balance(_bb_uid)
asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job))
check("13.10 повторный job: баланс не тронут", S.get_balance(_bb_uid) == _bal1)
check("13.11 повторный job: генерация НЕ вызвана", not S._studio_execute_job.await_args_list)
check("13.12 повторный job: complete переотправлен",
      any(c.args[0] == "complete" for c in S._studio_api.await_args_list))

# 13.13 price_changed: ожидаемая цена не сошлась -> отказ без списания
S._studio_api = AsyncMock(return_value={})
S._studio_execute_job = AsyncMock(return_value={})
_bal2 = S.get_balance(_bb_uid)
_job_pc = {"id": f"job-2-{_run_tag}", "user_id": _bb_uid, "type": "frame",
           "payload": json.dumps({"frame_prompt": "cat", "expected_cost": 1})}
asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_pc))
_c = [c for c in S._studio_api.await_args_list if c.args[0] == "complete"]
check("13.13 price_changed: error без списания",
      S.get_balance(_bb_uid) == _bal2 and _c and _c[-1].args[1]["error"] == "price_changed", str(_c))

# 13.14 not_enough_funds: пустой баланс -> отказ, генерация не запущена
_poor_uid = 9702
S.create_user_if_not_exists(_poor_uid, "poor", 0)
while S.get_balance(_poor_uid) > 0:
    S.spend_izyminki(_poor_uid, S.get_balance(_poor_uid))
S._studio_api = AsyncMock(return_value={})
S._studio_execute_job = AsyncMock(return_value={})
_job_nf = {"id": f"job-3-{_run_tag}", "user_id": _poor_uid, "type": "frame",
           "payload": json.dumps({"frame_prompt": "cat"})}
asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_nf))
_c = [c for c in S._studio_api.await_args_list if c.args[0] == "complete"]
check("13.14 not_enough_funds: error и генерация не вызвана",
      _c and _c[-1].args[1]["error"] == "not_enough_funds" and not S._studio_execute_job.await_args_list, str(_c))

# 13.15 возврат при ошибке генерации
S._studio_api = AsyncMock(return_value={})
S._studio_execute_job = AsyncMock(side_effect=Exception("provider exploded: server 500"))
_bal3 = S.get_balance(_bb_uid)
_job_fail = {"id": f"job-4-{_run_tag}", "user_id": _bb_uid, "type": "frame",
             "payload": json.dumps({"frame_prompt": "cat", "expected_cost": S.BASE_GENERATION_COST})}
asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_fail))
_c = [c for c in S._studio_api.await_args_list if c.args[0] == "complete"]
check("13.15 сбой генерации: деньги возвращены", S.get_balance(_bb_uid) == _bal3, f"bal={S.get_balance(_bb_uid)}")
check("13.16 сбой генерации: complete с error=provider",
      _c and _c[-1].args[1]["status"] == "error" and _c[-1].args[1]["error"] == "provider", str(_c))

# 13.17 модерация классифицируется отдельно
S._studio_api = AsyncMock(return_value={})
S._studio_execute_job = AsyncMock(side_effect=Exception("blocked by content filter / moderation"))
_job_mod = {"id": f"job-5-{_run_tag}", "user_id": _bb_uid, "type": "frame",
            "payload": json.dumps({"frame_prompt": "cat", "expected_cost": S.BASE_GENERATION_COST})}
asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_mod))
_c = [c for c in S._studio_api.await_args_list if c.args[0] == "complete"]
check("13.17 модерация -> error=moderation", _c and _c[-1].args[1]["error"] == "moderation", str(_c))

# 13.20 крэш между списанием и генерацией: запись status='charged' в журнале —
# повторное взятие job'а НЕ списывает второй раз, но генерацию повторяет
S._studio_api = AsyncMock(return_value={})
S._studio_execute_job = AsyncMock(return_value={"frame_url": "https://i.ibb.co/retry.png"})
_job6_id = f"job-6-{_run_tag}"
S.record_studio_done_job(_job6_id, _bb_uid, True, S.BASE_GENERATION_COST, "charged", "", "{}")
_bal4 = S.get_balance(_bb_uid)
_job_crash = {"id": _job6_id, "user_id": _bb_uid, "type": "frame",
              "payload": json.dumps({"frame_prompt": "cat", "expected_cost": S.BASE_GENERATION_COST})}
asyncio.run(S._studio_handle_job(types.SimpleNamespace(bot=AsyncMock()), _job_crash))
check("13.20 после крэша: повторное взятие не списывает второй раз",
      S.get_balance(_bb_uid) == _bal4, f"bal={S.get_balance(_bb_uid)}")
check("13.21 после крэша: генерация повторена и complete=done",
      S._studio_execute_job.await_args_list != [] and
      any(c.args[0] == "complete" and c.args[1]["status"] == "done" for c in S._studio_api.await_args_list),
      str(S._studio_api.await_args_list))

# 13.18 прайс-фид: модели с длительностями и тарифами
_feed = S._studio_price_feed()
check("13.18 прайс-фид: есть модели и у каждой durations+cost_per_second",
      _feed["models"] and all("durations" in m and "cost_per_second" in m for m in _feed["models"].values()),
      str(_feed))
check("13.19 прайс-фид: frame_cost и max_scenes на месте",
      _feed["frame_cost"] == S.BASE_GENERATION_COST and _feed["max_scenes"] == S.STUDIO_MAX_SCENES)
check("13.19b прайс-фид: у каждой модели resolutions совпадает со снэпом бота",
      all(m["resolutions"] == S.get_seedance_mode_options(code) for code, m in _feed["models"].items()),
      str(_feed["models"]))

S._studio_api = _studio_api_orig
S._studio_execute_job = _studio_exec_orig

# 13.19c студия: 4:3 добавлен в допустимые форматы стежка/кадра
check("13.19c STUDIO_STITCH_RESOLUTION знает 4:3",
      S.STUDIO_STITCH_RESOLUTION.get("4:3") == "1440x1080", str(S.STUDIO_STITCH_RESOLUTION))

# 13.22 stitch: меньше 2 клипов -> ValueError, без обращения к ffmpeg
try:
    asyncio.run(S._studio_generate_stitch(types.SimpleNamespace(bot=AsyncMock()), _bb_uid, {"clips": ["only-one"]}))
    check("13.22 stitch <2 клипов -> исключение", False)
except ValueError:
    check("13.22 stitch <2 клипов -> исключение", True)

# 13.23-13.24 stitch: реальный ffmpeg — склейка клипа со звуком и без звука
# в один файл (ревизия ТЗ п.8: тихая дорожка для клипов без звука)
import shutil as _shutil  # noqa: E402
if _shutil.which("ffmpeg") and _shutil.which("ffprobe"):
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
    check("13.23 stitch: результат содержит final_url, финал отправлен в чат",
          "final_url" in _stitch_result and _fake_app.bot.send_video.await_args is not None, str(_stitch_result))
    _sent_kwargs = _fake_app.bot.send_video.await_args.kwargs
    check("13.24 stitch: send_video получил непустые байты финального ролика",
          isinstance(_sent_kwargs.get("video"), io.BytesIO) and _sent_kwargs["video"].getbuffer().nbytes > 0,
          str(_sent_kwargs.get("video")))
    _shutil.rmtree(_stitch_dir, ignore_errors=True)
else:
    check("13.23 stitch: ffmpeg недоступен локально, склейка не проверена", True)

# ════════════════ БЛОК 14: EvoLink провайдер-флаг + Motion Control UI ════════════════
print("Блок 14: EvoLink провайдер-флаг + Motion Control UI")

# 14.1 дефолт SEEDANCE_PROVIDER="zveno" — ноль изменений поведения
check("14.1 дефолт SEEDANCE_PROVIDER = zveno", S.SEEDANCE_PROVIDER == "zveno", S.SEEDANCE_PROVIDER)
check("14.2 seedance2 на zveno -> use_evolink=False", S.seedance_uses_evolink("seedance2") is False)
check("14.3 seedance2_fast на zveno -> use_evolink=False", S.seedance_uses_evolink("seedance2_fast") is False)

_orig_seedance_provider = S.SEEDANCE_PROVIDER
S.SEEDANCE_PROVIDER = "evolink"
check("14.4 seedance2 на evolink -> use_evolink=True", S.seedance_uses_evolink("seedance2") is True)
check("14.5 seedance2_fast на evolink -> use_evolink=True", S.seedance_uses_evolink("seedance2_fast") is True)
check("14.6 kling3 игнорирует SEEDANCE_PROVIDER даже на evolink",
      S.seedance_uses_evolink("kling3") is False)
check("14.7 veo31 игнорирует SEEDANCE_PROVIDER даже на evolink",
      S.seedance_uses_evolink("veo31") is False)
check("14.8 wan27 игнорирует SEEDANCE_PROVIDER даже на evolink",
      S.seedance_uses_evolink("wan27") is False)
S.SEEDANCE_PROVIDER = _orig_seedance_provider
check("14.9 SEEDANCE_PROVIDER восстановлен в zveno после теста", S.SEEDANCE_PROVIDER == "zveno")

# 14.10 EvoLink-клиент теперь реальный (см. Блок 15) — без фото image-to-video
# честно падает с понятной ошибкой, а не молчаливым noop/NotImplementedError.
try:
    asyncio.run(S.start_seedance_task_evolink(
        prompt="тест", image_url=None, user_id=1, model_code="seedance2",
    ))
    check("14.10 start_seedance_task_evolink без фото кидает исключение", False)
except Exception as e:
    check("14.10 start_seedance_task_evolink без фото кидает исключение",
          "фото" in str(e).lower() or "image" in str(e).lower(), str(e))

# 14.11 MOTION_CONTROL_ENABLED=0 по умолчанию — кнопка скрыта в video_menu_kb
check("14.11 MOTION_CONTROL_ENABLED выключен по умолчанию", S.MOTION_CONTROL_ENABLED is False, S.MOTION_CONTROL_ENABLED)
kb_video_menu = S.video_menu_kb(user_id=1)
cbs_vm = [b.callback_data for row in kb_video_menu.inline_keyboard for b in row]
check("14.12 кнопка motion_start скрыта при выключенном флаге", "motion_start" not in cbs_vm, str(cbs_vm))

# 14.13 при включённом флаге кнопка появляется
_orig_motion_flag = S.MOTION_CONTROL_ENABLED
S.MOTION_CONTROL_ENABLED = True
kb_video_menu2 = S.video_menu_kb(user_id=1)
cbs_vm2 = [b.callback_data for row in kb_video_menu2.inline_keyboard for b in row]
check("14.13 кнопка motion_start видна при включённом флаге", "motion_start" in cbs_vm2, str(cbs_vm2))

# 14.14 motion_start запускает waiting_for_motion_video, сбрасывая обычный видео-режим
update, context, query = make_update_context("motion_start", user_id=1401)
context.user_data["state"] = S.UserState(video_session_active=True, waiting_for_video_image=True)
asyncio.run(S.button_handler(update, context))
st14 = context.user_data.get("state")
check("14.14 motion_start взводит waiting_for_motion_video",
      st14 and st14.waiting_for_motion_video is True, str(st14))
check("14.15 motion_start взводит motion_control_active",
      st14 and st14.motion_control_active is True)
check("14.16 motion_start гасит обычный видео-режим (video_session_active)",
      st14 and st14.video_session_active is False)

# 14.17 handle_video: референс-видео добавлен -> просит фото (не video_kb Seedance)
video_message = types.SimpleNamespace(
    video=types.SimpleNamespace(file_id="vid1"),
    reply_text=AsyncMock(),
)
update = types.SimpleNamespace(
    message=video_message,
    effective_user=types.SimpleNamespace(id=1402, username="test"),
    effective_chat=types.SimpleNamespace(id=1402),
    effective_message=video_message,
)
st14b = S.UserState(motion_control_active=True, waiting_for_motion_video=True)
context = types.SimpleNamespace(user_data={"state": st14b}, application=None, bot=AsyncMock())
context.bot.get_file = AsyncMock(return_value=types.SimpleNamespace(file_path="videos/file1.mp4"))
asyncio.run(S.handle_video(update, context))
check("14.18 waiting_for_motion_video сброшен после видео", st14b.waiting_for_motion_video is False)
check("14.19 waiting_for_motion_image взведён (ждём фото следующим шагом)",
      st14b.waiting_for_motion_image is True)
check("14.20 motion_video_url сохранён", bool(st14b.motion_video_url), st14b.motion_video_url)
video_texts = [c.args[0] for c in video_message.reply_text.await_args_list]
check("14.21 просит прислать фото (не показывает video_kb)",
      any("фото" in t.lower() for t in video_texts), str(video_texts))

# 14.22 handle_photo: фото после видео с движением запускает run_kling_motion_control
started_motion = []


async def fake_run_motion(update, context):
    started_motion.append(True)


_orig_run_motion = S.run_kling_motion_control
S.run_kling_motion_control = fake_run_motion
st14c = S.UserState(waiting_for_motion_image=True, motion_video_url="https://example.com/motion.mp4")
photo_message_motion = types.SimpleNamespace(
    photo=[types.SimpleNamespace(file_id="ph_motion")],
    caption=None, media_group_id=None, reply_text=AsyncMock(),
)
update = types.SimpleNamespace(
    message=photo_message_motion,
    effective_user=types.SimpleNamespace(id=1403, username="test"),
    effective_chat=types.SimpleNamespace(id=1403),
    effective_message=photo_message_motion,
)
context = types.SimpleNamespace(user_data={"state": st14c}, application=types.SimpleNamespace(create_task=lambda c: (started_motion.append("task"), c.close())), bot=AsyncMock())
context.bot.get_file = AsyncMock(return_value=types.SimpleNamespace(
    download_to_memory=AsyncMock(side_effect=lambda out: out.write(base64.b64decode(ok_png_b64)))
))
asyncio.run(S.handle_photo(update, context))
check("14.23 waiting_for_motion_image сброшен после фото", st14c.waiting_for_motion_image is False)
check("14.24 motion_image_url сохранён", bool(st14c.motion_image_url), st14c.motion_image_url)
check("14.25 run_kling_motion_control запущен (create_task)", "task" in started_motion, str(started_motion))
S.processing_user_ids.discard(1403)
S.run_kling_motion_control = _orig_run_motion

# 14.26 deactivate_video_session гасит motion-состояние вместе с обычным видео
st14d = S.UserState(
    motion_control_active=True, waiting_for_motion_video=True,
    waiting_for_motion_image=True, motion_video_url="x", motion_image_url="y",
)
S.deactivate_video_session(st14d)
check("14.27 deactivate_video_session гасит motion_control_active", st14d.motion_control_active is False)
check("14.28 deactivate_video_session гасит waiting_for_motion_image", st14d.waiting_for_motion_image is False)
check("14.29 deactivate_video_session чистит motion_video_url/motion_image_url",
      st14d.motion_video_url is None and st14d.motion_image_url is None)

S.MOTION_CONTROL_ENABLED = _orig_motion_flag

# ════════════════ БЛОК 15: EvoLink реальный HTTP-клиент (Seedance/Gemini Omni/Kling Motion Control) ════════════════
print("Блок 15: EvoLink реальный HTTP-клиент")

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
check("15.1 start_seedance_task_evolink возвращает __EVOLINK__: префикс",
      task_ref.startswith("__EVOLINK__:"), task_ref)
p15_1 = evo_calls[0]["payload"]
check("15.2 payload.model = seedance-2.0-image-to-video", p15_1.get("model") == "seedance-2.0-image-to-video", str(p15_1))
check("15.3 payload.image_urls содержит фото", p15_1.get("image_urls") == ["https://example.com/ref.jpg"], str(p15_1))
check("15.4 payload.duration = 5", p15_1.get("duration") == 5)
check("15.5 payload.aspect_ratio = 9:16", p15_1.get("aspect_ratio") == "9:16")
check("15.6 payload.quality = 720p", p15_1.get("quality") == "720p")
check("15.7 payload.generate_audio=True", p15_1.get("generate_audio") is True)
check("15.8 заголовок Authorization Bearer", evo_calls[0]["headers"].get("Authorization") == "Bearer test-evolink-key")

# 15.9 seedance2_fast + evolink + 1080p -> фолбэк на 720p (EvoLink не умеет 1080p у fast)
evo_calls.clear()
asyncio.run(S.start_seedance_task_evolink(
    prompt="тест", image_url="https://example.com/ref.jpg", user_id=1,
    duration=5, mode="1080p", model_code="seedance2_fast", aspect_ratio="16:9",
))
p15_9 = evo_calls[0]["payload"]
check("15.9 seedance2_fast: модель seedance-2.0-fast-image-to-video",
      p15_9.get("model") == "seedance-2.0-fast-image-to-video", str(p15_9))
check("15.10 seedance2_fast: 1080p сфолбэчен на 720p", p15_9.get("quality") == "720p", str(p15_9.get("quality")))

# 15.11 без фото — понятная ошибка, не молчаливый провал
try:
    asyncio.run(S.start_seedance_task_evolink(prompt="x", image_url=None, user_id=1, model_code="seedance2"))
    check("15.11 start_seedance_task_evolink без фото падает", False)
except Exception as e:
    check("15.11 start_seedance_task_evolink без фото падает", "фото" in str(e).lower())

# 15.12 poll_seedance_task делегирует __EVOLINK__: в poll_evolink_task -> completed -> results[0]
_evo_poll_queue.clear()
_evo_poll_queue.append({"status": "pending", "progress": 20})
_evo_poll_queue.append({"status": "completed", "progress": 100, "results": ["http://example.com/video.mp4"]})
video_url = asyncio.run(S.poll_seedance_task(task_ref, max_attempts=5, poll_interval=1))
check("15.13 poll_seedance_task(__EVOLINK__:) вернул results[0]",
      video_url == "http://example.com/video.mp4", video_url)

# 15.14 poll: content_policy_violation классифицируется как moderation
_evo_poll_queue.clear()
_evo_poll_queue.append({
    "status": "failed",
    "error": {"code": "content_policy_violation", "message": "blocked content", "type": "task_error"},
})
try:
    asyncio.run(S.poll_seedance_task(task_ref, max_attempts=3, poll_interval=1))
    check("15.14 poll: failed кидает исключение", False)
except Exception as e:
    check("15.14 poll: failed кидает исключение", True)
    check("15.15 classify_generation_error -> moderation (content_policy_violation)",
          S.classify_generation_error(e) == "moderation", str(e))

# 15.16 Gemini Omni: payload — одно фото, model=gemini-omni-flash-image-to-video, duration клампится 3-10
evo_calls.clear()
gomni_ref = asyncio.run(S.start_gemini_omni_task_evolink(
    prompt="оживи фото", image_url="https://example.com/photo.jpg", user_id=1,
    duration=25, aspect_ratio="16:9",
))
check("15.17 gemini omni возвращает __EVOLINK__: префикс", gomni_ref.startswith("__EVOLINK__:"), gomni_ref)
p15_16 = evo_calls[0]["payload"]
check("15.18 gemini omni: модель", p15_16.get("model") == "gemini-omni-flash-image-to-video", str(p15_16))
check("15.19 gemini omni: одно фото в image_urls", p15_16.get("image_urls") == ["https://example.com/photo.jpg"])
check("15.20 gemini omni: duration клампится к 10 (макс)", p15_16.get("duration") == 10, str(p15_16.get("duration")))
check("15.21 gemini omni: aspect_ratio 16:9", p15_16.get("aspect_ratio") == "16:9")

# 15.22 Gemini Omni: неподдержанный aspect -> фолбэк на 16:9
evo_calls.clear()
asyncio.run(S.start_gemini_omni_task_evolink(
    prompt="x", image_url="https://example.com/photo.jpg", user_id=1, duration=5, aspect_ratio="4:3",
))
p15_22 = evo_calls[0]["payload"]
check("15.23 gemini omni: 4:3 не поддержан -> фолбэк 16:9", p15_22.get("aspect_ratio") == "16:9", str(p15_22))

# 15.24 Kling Motion Control (EvoLink): image_urls + video_urls + model_params
evo_calls.clear()
kmc_ref = asyncio.run(S.start_kling_motion_control_evolink(
    image_url="https://example.com/character.jpg",
    motion_video_url="https://example.com/motion.mp4",
    prompt="повтори движение",
    user_id=1,
))
check("15.25 kling motion control evolink возвращает __EVOLINK__: префикс", kmc_ref.startswith("__EVOLINK__:"), kmc_ref)
p15_24 = evo_calls[0]["payload"]
check("15.26 kling motion control: model=kling-v3-motion-control", p15_24.get("model") == "kling-v3-motion-control", str(p15_24))
check("15.27 kling motion control: image_urls = [character]", p15_24.get("image_urls") == ["https://example.com/character.jpg"])
check("15.28 kling motion control: video_urls = [motion]", p15_24.get("video_urls") == ["https://example.com/motion.mp4"])
check("15.29 kling motion control: character_orientation=image",
      p15_24.get("model_params", {}).get("character_orientation") == "image", str(p15_24.get("model_params")))
check("15.30 kling motion control: prompt передан", p15_24.get("prompt") == "повтори движение")

S.EVOLINK_API_KEY = _orig_evo_key
S.aiohttp.ClientSession = _orig_evo_cs
S.asyncio.sleep = _orig_sleep

# 15.31 EvoLink duration bounds: seedance2/2_fast на evolink -> 4–15 (не 5–15 как на zveno)
S.SEEDANCE_PROVIDER = "evolink"
check("15.31 evolink seedance2 duration bounds = (4, 15)", S.get_seedance_duration_bounds("seedance2") == (4, 15))
check("15.32 zveno kling3 duration bounds не затронуты (3, 15)", S.get_seedance_duration_bounds("kling3") == (3, 15))
check("15.33 evolink seedance2_fast: mode options без 1080p",
      "1080p" not in S.get_seedance_mode_options("seedance2_fast"), str(S.get_seedance_mode_options("seedance2_fast")))
S.SEEDANCE_PROVIDER = _orig_seedance_provider
check("15.34 zveno (дефолт) seedance2 duration bounds = (5, 15)", S.get_seedance_duration_bounds("seedance2") == (5, 15))
check("15.35 zveno seedance2_fast: 1080p доступен",
      "1080p" in S.get_seedance_mode_options("seedance2_fast"), str(S.get_seedance_mode_options("seedance2_fast")))

# 15.36 Gemini Omni как модель — кнопка живёт в ПИКЕРЕ моделей (после ТЗ
# video_panel_declutter полная панель кнопок-моделей не держит вовсе),
# и только когда флаг включён.
_orig_gemini_enabled = S.GEMINI_OMNI_ENABLED
S.GEMINI_OMNI_ENABLED = False
cbs15_off = [b.callback_data for row in S.video_model_picker_kb().inline_keyboard for b in row]
check("15.36 gemini omni выключен -> кнопки нет в пикере", "video_model_gemini_omni" not in cbs15_off, str(cbs15_off))

S.GEMINI_OMNI_ENABLED = True
cbs15_on = [b.callback_data for row in S.video_model_picker_kb().inline_keyboard for b in row]
check("15.37 gemini omni включён -> кнопка есть в пикере", "video_model_gemini_omni" in cbs15_on, str(cbs15_on))

# 15.38 выбор gemini_omni через callback ставит модель и форсит аспект 16:9/9:16
update, context, query = make_update_context("video_model_gemini_omni", user_id=1501)
context.user_data["state"] = S.UserState(video_aspect_ratio="1:1")
asyncio.run(S.button_handler(update, context))
st15 = context.user_data["state"]
check("15.39 video_model_gemini_omni ставит модель", st15.video_model == "gemini_omni", st15.video_model)
check("15.40 gemini_omni сбрасывает несовместимый аспект 1:1 -> 16:9", st15.video_aspect_ratio == "16:9",
      st15.video_aspect_ratio)

# 15.41 get_video_model возвращает gemini_omni только когда флаг включён
check("15.41 get_video_model(gemini_omni, enabled) -> gemini_omni",
      S.get_video_model(S.UserState(video_model="gemini_omni")) == "gemini_omni")
S.GEMINI_OMNI_ENABLED = False
check("15.42 get_video_model(gemini_omni, disabled) -> seedance2 (фолбэк)",
      S.get_video_model(S.UserState(video_model="gemini_omni")) == "seedance2")
S.GEMINI_OMNI_ENABLED = True

# 15.43 _studio_video_models включает gemini_omni, только когда флаг включён
check("15.43 _studio_video_models содержит gemini_omni при включённом флаге",
      "gemini_omni" in S._studio_video_models())
S.GEMINI_OMNI_ENABLED = False
check("15.44 _studio_video_models НЕ содержит gemini_omni при выключенном флаге",
      "gemini_omni" not in S._studio_video_models())
S.GEMINI_OMNI_ENABLED = _orig_gemini_enabled

# 15.45 MOTION_CONTROL_PROVIDER дефолт — mashagpt (ноль изменений поведения)
check("15.45 дефолт MOTION_CONTROL_PROVIDER = mashagpt", S.MOTION_CONTROL_PROVIDER == "mashagpt", S.MOTION_CONTROL_PROVIDER)

# 15.46 log_provider_config: громкая сводка провайдеров при старте, с warning
# на рассинхроне AI_PROVIDER/ключа (прод-инцидент 2026-08-01: AI_PROVIDER
# потерялся в BotHost, фото неделю молча шли через YesAPI вместо Zveno).
import logging as _logging  # noqa: E402


class _ListLogHandler(_logging.Handler):
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
_warnings46 = [r.getMessage() for r in _log_handler.records if r.levelno >= _logging.WARNING]
check("15.46 AI_PROVIDER без ключа -> warning про пустой ключ",
      any("MASHAGPT" in w and "ключ" in w for w in _warnings46), str(_warnings46))

_log_handler.records.clear()
S.AI_PROVIDER = _orig_ai_provider
S.ZVENO_API_KEY = ""
S.log_provider_config()
_warnings46b = [r.getMessage() for r in _log_handler.records if r.levelno >= _logging.WARNING]
check("15.47 пустой ZVENO_API_KEY -> warning про недоступное видео",
      any("ZVENO_API_KEY" in w for w in _warnings46b), str(_warnings46b))
S.ZVENO_API_KEY = _orig_zveno_key
S.logger.removeHandler(_log_handler)

# ════════════════ ИТОГ ════════════════
print()
print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
for name, detail in FAIL:
    print(f"  FAIL {name}: {detail}")
sys.exit(1 if FAIL else 0)
