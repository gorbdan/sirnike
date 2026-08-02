"""Воркер очереди D1 «Студии нейромультиков» (docs/specs/2026-07-20_cartoon_studio.md).

Вынесено из SirNike.py в рамках фазы 3 разбора монолита (см.
docs/briefs/backend.md, фазы 1/2 — video_providers.py/photo_providers.py,
тот же общий подход). Чисто структурный рефакторинг — поведение не менялось.

В отличие от video_providers.py/photo_providers.py (где вынесен только
провайдер-клиент, а биллинг и отправка в чат остаются в SirNike.py) — здесь
вынесен ВЕСЬ воркер целиком, включая списание/возврат изюминок
(`spend_izyminki`/`add_izyminki`) и доставку результата пользователю
(`app.bot.send_video`). Это самодостаточная подсистема (свой journaling
идемпотентности в `studio_done_jobs`, свой поллинг-цикл), а не переиспользуемый
клиент чужого API — разрывать биллинг и генерацию на два модуля было бы
искусственно.

У бота нет HTTP-входа, поэтому он сам поллит очередь заданий в Cloudflare D1
(Pages Functions вебаппа). Модуль не импортирует SirNike.py (иначе
циклический импорт — SirNike.py импортирует функции отсюда).

Недостающие бот-уровневые зависимости (функции, которые физически остаются
в SirNike.py — конвертация ошибок в категории, аплоад на imgbb, скачивание
видео с фолбэком и т.п.) прокидываются через configure(...), вызываемый из
SirNike.py один раз при импорте, сразу после того как нужные хелперы там
определены.

`download_video_bytes_with_fallback` инжектируется через lambda с ленивым
резолвом имени в SirNike.py (тот же трюк, что у `_get_evolink_api_key_hook`
в video_providers.py) — это единственная из инжектируемых функций, которую
тест переприсваивает (`S.download_video_bytes_with_fallback = ...`) уже
после импорта, и лямбда продолжает подхватывать подмену. `_studio_api`,
`_studio_execute_job` и `_studio_semaphore` — внутреннее состояние ЭТОГО
модуля; тесты, которым нужно их подменить для изоляции `_studio_handle_job`,
патчат `studio_worker._studio_api` и т.п. напрямую (не через `S.`), потому
что переприсваивание имени в namespace SirNike.py не meняет то, что видит
LOAD_GLOBAL внутри функций, определённых в этом модуле.

`aiohttp` импортирован как модуль (не `from aiohttp import ...`), чтобы
`S.aiohttp.ClientSession = FakeSession` в тестах продолжал работать — то же
самое соглашение, что в video_providers.py/photo_providers.py.
"""

import asyncio
import base64
import io
import json
import logging
import os
import shutil
import tempfile
from typing import Callable, Dict, List, Optional

import aiohttp
from telegram.ext import Application

from config import (
    BASE_GENERATION_COST,
    GEMINI_OMNI_COST_PER_SECOND,
    GEMINI_OMNI_ENABLED,
    KLING3_COST_PER_SECOND,
    KLING3_ENABLED,
    REFERENCE_COST,
    SEEDANCE_COST_PER_SECOND,
    SEEDANCE_DURATION,
    SEEDANCE_ENABLED,
    SEEDANCE_FAST_COST_PER_SECOND,
    SEEDANCE_FAST_ENABLED,
    SEEDANCE_MAX_POLL_ATTEMPTS,
    SEEDANCE_POLL_INTERVAL,
    STUDIO_API_BASE,
    STUDIO_CONCURRENCY,
    STUDIO_ENABLED,
    STUDIO_MAX_SCENES,
    STUDIO_POLL_INTERVAL,
    STUDIO_POLL_SECRET,
    VEO31_COST_PER_SECOND,
    VEO31_ENABLED,
    WAN27_COST_PER_SECOND,
    WAN27_ENABLED,
    ZVENO_API_BASE,
    ZVENO_API_KEY,
    ZVENO_CHAT_MODEL,
    ZVENO_IMAGE_MODEL,
)
from db import (
    add_izyminki,
    get_active_avatar_kind,
    get_avatar_urls,
    get_balance,
    get_studio_done_job,
    record_studio_done_job,
    spend_izyminki,
)
from video_providers import (
    build_zveno_url,
    get_seedance_duration_options,
    get_seedance_mode_options,
    normalize_seedance_duration,
    normalize_seedance_mode,
    poll_seedance_task,
    seedance_uses_evolink,
    start_gemini_omni_task_evolink,
    start_seedance_task,
    start_seedance_task_evolink,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Инъекция бот-уровневых зависимостей (см. докстринг модуля)
# ----------------------------------------------------------------------------

def _default_studio_video_models_raw() -> Dict[str, dict]:
    return {
        "seedance2_fast": {"enabled": SEEDANCE_FAST_ENABLED, "cost_per_second": SEEDANCE_FAST_COST_PER_SECOND},
        "seedance2": {"enabled": SEEDANCE_ENABLED, "cost_per_second": SEEDANCE_COST_PER_SECOND},
        "kling3": {"enabled": KLING3_ENABLED, "cost_per_second": KLING3_COST_PER_SECOND},
        "veo31": {"enabled": VEO31_ENABLED, "cost_per_second": VEO31_COST_PER_SECOND},
        "wan27": {"enabled": WAN27_ENABLED, "cost_per_second": WAN27_COST_PER_SECOND},
        "gemini_omni": {"enabled": GEMINI_OMNI_ENABLED, "cost_per_second": GEMINI_OMNI_COST_PER_SECOND},
    }


def _default_get_video_model_label(model_code: str) -> str:
    return model_code


def _default_calc_generation_cost(references: Optional[List[str]] = None, image_model: str = "gemini") -> int:
    return BASE_GENERATION_COST


def _default_calc_seedance_cost(duration_sec: int, cost_per_second: Optional[float] = None) -> int:
    return int(duration_sec * (cost_per_second or 0))


def _default_classify_generation_error(error: object) -> str:
    return "provider"


def _default_is_admin(user_id: int) -> bool:
    return False


def _default_extract_chat_completion_text(data: dict) -> str:
    return ""


def _default_extract_zveno_image_result(rd: dict) -> Optional[str]:
    return None


async def _default_upload_image_bytes_to_imgbb(image_bytes: bytes, filename: str = "import.jpg") -> Optional[str]:
    return None


async def _default_upload_image_url_to_imgbb(image_url: str) -> Optional[str]:
    return None


async def _default_download_video_bytes_with_fallback(video_url: str) -> bytes:
    raise Exception("studio_worker: download_video_bytes_with_fallback not configured")


_studio_video_models_raw_hook: Callable[[], Dict[str, dict]] = _default_studio_video_models_raw
_get_video_model_label_hook: Callable[[str], str] = _default_get_video_model_label
_calc_generation_cost_hook: Callable[..., int] = _default_calc_generation_cost
_calc_seedance_cost_hook: Callable[..., int] = _default_calc_seedance_cost
_classify_generation_error_hook: Callable[[object], str] = _default_classify_generation_error
_is_admin_hook: Callable[[int], bool] = _default_is_admin
_extract_chat_completion_text_hook: Callable[[dict], str] = _default_extract_chat_completion_text
_extract_zveno_image_result_hook: Callable[[dict], Optional[str]] = _default_extract_zveno_image_result
_upload_image_bytes_to_imgbb_hook: Callable[..., "asyncio.Future"] = _default_upload_image_bytes_to_imgbb
_upload_image_url_to_imgbb_hook: Callable[..., "asyncio.Future"] = _default_upload_image_url_to_imgbb
_download_video_bytes_with_fallback_hook: Callable[[str], "asyncio.Future"] = _default_download_video_bytes_with_fallback


def configure(
    *,
    get_studio_video_models_raw: Optional[Callable[[], Dict[str, dict]]] = None,
    get_video_model_label: Optional[Callable[[str], str]] = None,
    calc_generation_cost: Optional[Callable[..., int]] = None,
    calc_seedance_cost: Optional[Callable[..., int]] = None,
    classify_generation_error: Optional[Callable[[object], str]] = None,
    is_admin: Optional[Callable[[int], bool]] = None,
    extract_chat_completion_text: Optional[Callable[[dict], str]] = None,
    extract_zveno_image_result: Optional[Callable[[dict], Optional[str]]] = None,
    upload_image_bytes_to_imgbb: Optional[Callable] = None,
    upload_image_url_to_imgbb: Optional[Callable] = None,
    download_video_bytes_with_fallback: Optional[Callable] = None,
) -> None:
    global _studio_video_models_raw_hook
    global _get_video_model_label_hook, _calc_generation_cost_hook, _calc_seedance_cost_hook
    global _classify_generation_error_hook, _is_admin_hook, _extract_chat_completion_text_hook
    global _extract_zveno_image_result_hook, _upload_image_bytes_to_imgbb_hook
    global _upload_image_url_to_imgbb_hook, _download_video_bytes_with_fallback_hook
    if get_studio_video_models_raw is not None:
        _studio_video_models_raw_hook = get_studio_video_models_raw
    if get_video_model_label is not None:
        _get_video_model_label_hook = get_video_model_label
    if calc_generation_cost is not None:
        _calc_generation_cost_hook = calc_generation_cost
    if calc_seedance_cost is not None:
        _calc_seedance_cost_hook = calc_seedance_cost
    if classify_generation_error is not None:
        _classify_generation_error_hook = classify_generation_error
    if is_admin is not None:
        _is_admin_hook = is_admin
    if extract_chat_completion_text is not None:
        _extract_chat_completion_text_hook = extract_chat_completion_text
    if extract_zveno_image_result is not None:
        _extract_zveno_image_result_hook = extract_zveno_image_result
    if upload_image_bytes_to_imgbb is not None:
        _upload_image_bytes_to_imgbb_hook = upload_image_bytes_to_imgbb
    if upload_image_url_to_imgbb is not None:
        _upload_image_url_to_imgbb_hook = upload_image_url_to_imgbb
    if download_video_bytes_with_fallback is not None:
        _download_video_bytes_with_fallback_hook = download_video_bytes_with_fallback


# ══════════════════════════════════════════════════════════════
# СТУДИЯ НЕЙРОМУЛЬТИКОВ — воркер очереди D1 (Ф1)
# docs/specs/2026-07-20_cartoon_studio.md. У бота нет HTTP-входа, поэтому
# он сам поллит очередь заданий в Cloudflare D1 (Pages Functions вебаппа).
# Биллинг и генерация — только здесь; идемпотентность — studio_done_jobs
# в SQLite бота (ревизия п.2 в ТЗ: complete может не дойти, job вернётся —
# без журнала это повторная генерация и повторное списание).
# ══════════════════════════════════════════════════════════════

_studio_user_locks: Dict[int, asyncio.Lock] = {}
_studio_semaphore: Optional[asyncio.Semaphore] = None
_studio_active_job_ids: set = set()

# Модели клипов, доступные в студии: код → (enabled, cost/sec)


def _studio_video_models() -> Dict[str, dict]:
    models = _studio_video_models_raw_hook()
    return {code: m for code, m in models.items() if m["enabled"]}


def _studio_price_feed() -> dict:
    """Прайс для корзины вебаппа. Источник правды — config.py бота; вебапп
    считает смету по этим числам, финальное списание ВСЕГДА по боту (при
    расхождении job получает error=price_changed, ревизия п.5)."""
    models = {}
    for code, m in _studio_video_models().items():
        models[code] = {
            "label": _get_video_model_label_hook(code),
            "cost_per_second": m["cost_per_second"],
            # Допустимые длительности обязаны совпадать со снэпом бота —
            # иначе корзина посчитает «7с для Veo» и цена разойдётся.
            "durations": get_seedance_duration_options(code),
            # Качество (разрешение) — тот же принцип: список кнопок в
            # вебаппе строго из снэпа бота, иначе можно выбрать несуществующее.
            "resolutions": get_seedance_mode_options(code),
        }
    return {
        "frame_cost": BASE_GENERATION_COST,
        "reference_cost": REFERENCE_COST,
        "max_scenes": STUDIO_MAX_SCENES,
        "models": models,
    }


async def _studio_api(path: str, payload: dict, timeout: int = 30) -> Optional[dict]:
    """POST на Pages Function студии с секретом бота. None = не дошло/ошибка."""
    if not STUDIO_ENABLED:
        return None
    url = f"{STUDIO_API_BASE}/{path.lstrip('/')}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={"X-Studio-Secret": STUDIO_POLL_SECRET, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if not (200 <= resp.status < 300):
                    body = await resp.text()
                    logger.warning("studio api %s: status=%s body=%s", path, resp.status, body[:200])
                    return None
                return await resp.json()
    except Exception as e:
        logger.warning("studio api %s exception: %s", path, e)
        return None


async def _studio_complete(job_id: str, status: str, error: str = "", result: Optional[dict] = None) -> bool:
    """Доставка результата в D1 с ретраями. Недоставка не фатальна: job
    вернётся в очередь по таймауту, бот увидит его в studio_done_jobs и
    просто повторит complete (без генерации и денег)."""
    payload = {"job_id": job_id, "status": status, "error": error, "result": result or {}}
    for attempt in range(3):
        if await _studio_api("complete", payload) is not None:
            return True
        await asyncio.sleep(2 * (attempt + 1))
    logger.warning("studio complete undelivered for job=%s (will self-heal on requeue)", job_id)
    return False


def _studio_compute_cost(job_type: str, payload: dict) -> int:
    """Пересчёт цены по тарифам бота (единственный источник правды)."""
    if job_type == "frame":
        refs = []
        if payload.get("use_avatar"):
            refs.append("avatar")
        refs.extend(payload.get("ref_urls") or [])
        return _calc_generation_cost_hook(refs, "gemini")
    if job_type == "clip":
        model_code = str(payload.get("model") or "seedance2_fast")
        duration = normalize_seedance_duration(int(payload.get("duration") or SEEDANCE_DURATION), model_code)
        models = _studio_video_models()
        cps = models.get(model_code, {}).get("cost_per_second")
        if cps is None:
            raise ValueError(f"studio: unknown/disabled clip model {model_code}")
        return _calc_seedance_cost_hook(duration, cps)
    return 0  # scenario | stitch — бесплатно


def _studio_parse_scenes(text: str) -> List[dict]:
    """Достаёт список сцен из ответа чат-модели. Терпит ```json-заборы и
    болтовню вокруг JSON."""
    raw = (text or "").strip()
    if "```" in raw:
        # берём содержимое первого fenced-блока
        parts = raw.split("```")
        for part in parts[1:]:
            candidate = part.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("[") or candidate.startswith("{"):
                raw = candidate
                break
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("studio scenario: JSON array not found in model reply")
    scenes_raw = json.loads(raw[start:end + 1])
    scenes = []
    for item in scenes_raw:
        if not isinstance(item, dict):
            continue
        frame_prompt = str(item.get("frame_prompt") or "").strip()
        video_prompt = str(item.get("video_prompt") or "").strip()
        if frame_prompt:
            scenes.append({"frame_prompt": frame_prompt, "video_prompt": video_prompt})
    if not scenes:
        raise ValueError("studio scenario: no valid scenes in model reply")
    return scenes[:STUDIO_MAX_SCENES]


async def _studio_generate_scenario(payload: dict) -> dict:
    idea = str(payload.get("idea") or "").strip()
    if not idea:
        raise ValueError("studio scenario: empty idea")
    max_scenes = min(int(payload.get("max_scenes") or STUDIO_MAX_SCENES), STUDIO_MAX_SCENES)
    aspect = str(payload.get("aspect") or "9:16")
    system = (
        "Ты — режиссёр коротких AI-мультиков. Разбей идею пользователя на "
        f"{max_scenes} или меньше сцен. Верни СТРОГО JSON-массив объектов "
        '[{"frame_prompt": "...", "video_prompt": "..."}] без пояснений. '
        "frame_prompt — детальный промт для генерации КАРТИНКИ первого кадра "
        f"сцены (на английском, стиль мультфильма, кадр {aspect}); "
        "video_prompt — краткое описание ДВИЖЕНИЯ в сцене для image-to-video "
        "(на английском). Сцены должны складываться в связную историю."
    )
    request_url = build_zveno_url(ZVENO_API_BASE, "/v1/chat/completions")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            request_url,
            headers={"Authorization": f"Bearer {ZVENO_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": ZVENO_CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": idea},
                ],
                "temperature": 0.7,
            },
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            body = await resp.text()
            if not (200 <= resp.status < 300):
                raise Exception(f"studio scenario provider error: {resp.status} {body[:200]}")
            data = json.loads(body)
    return {"scenes": _studio_parse_scenes(_extract_chat_completion_text_hook(data))}


async def _studio_generate_frame(user_id: int, payload: dict) -> dict:
    """Кадр раскадровки: Zveno image → перезалив на imgbb → браузерный URL.
    БЕЗ отправки в чат (кадры в чате = спам, ревизия/ТЗ «Конкурентность»)."""
    prompt = str(payload.get("frame_prompt") or "").strip()
    if not prompt:
        raise ValueError("studio frame: empty prompt")
    aspect = str(payload.get("aspect") or "9:16")
    if aspect not in ("9:16", "16:9", "4:3"):
        aspect = "9:16"

    ref_urls: List[str] = []
    if payload.get("use_avatar"):
        avatars = get_avatar_urls(user_id)
        active = get_active_avatar_kind(user_id)
        order = ([active] if active else []) + ["female", "male", "child"]
        avatar_url = next((avatars.get(k) for k in order if avatars.get(k)), None)
        if avatar_url:
            ref_urls.append(avatar_url)
    for u in (payload.get("ref_urls") or [])[:4]:
        if isinstance(u, str) and (u.startswith("http") or u.startswith("data:")):
            ref_urls.append(u)

    user_content: list = [{"type": "text", "text": prompt}]
    for u in ref_urls[:4]:
        user_content.append({"type": "image_url", "image_url": {"url": u}})

    request_url = build_zveno_url(ZVENO_API_BASE, "/v1/chat/completions")
    last_error = "no image in response"
    for model in (ZVENO_IMAGE_MODEL, "google/gemini-3-pro-image-preview"):
        req = {
            "model": model,
            "messages": [{"role": "user", "content": user_content}],
            "modalities": ["image", "text"],
            "image_config": {"aspect_ratio": aspect},
            "max_completion_tokens": 1024,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                request_url,
                headers={"Authorization": f"Bearer {ZVENO_API_KEY}", "Content-Type": "application/json"},
                json=req,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                body = await resp.text()
                if not (200 <= resp.status < 300):
                    last_error = f"status {resp.status}: {body[:200]}"
                    continue
                data = json.loads(body)
        image_ref = _extract_zveno_image_result_hook(data)
        if not image_ref:
            # native_finish_reason с модерацией должен долететь до classify
            last_error = f"no image (body: {body[:300]})"
            continue
        # Перезалив на imgbb — браузерный URL для вебаппа
        if image_ref.startswith("data:") and "," in image_ref:
            frame_url = await _upload_image_bytes_to_imgbb_hook(
                base64.b64decode(image_ref.split(",", 1)[1]), filename="studio_frame.png"
            )
        else:
            frame_url = await _upload_image_url_to_imgbb_hook(image_ref)
        if not frame_url:
            raise Exception("studio frame: imgbb upload failed (download_error)")
        return {"frame_url": frame_url}
    raise Exception(f"studio frame generation failed: {last_error}")


async def _studio_generate_clip(app: Application, user_id: int, payload: dict) -> dict:
    """Клип сцены (i2v от кадра). Готовый клип дублируется юзеру в чат —
    вечный бэкап, т.к. Zveno-URL протухают (ТЗ «Хранение медиа»)."""
    video_prompt = str(payload.get("video_prompt") or "").strip()
    frame_url = str(payload.get("frame_url") or "").strip()
    if not frame_url:
        raise ValueError("studio clip: no frame_url")
    model_code = str(payload.get("model") or "seedance2_fast")
    if model_code not in _studio_video_models():
        raise ValueError(f"studio clip: unknown/disabled model {model_code}")
    aspect = str(payload.get("aspect") or "9:16")
    duration = normalize_seedance_duration(int(payload.get("duration") or SEEDANCE_DURATION), model_code)
    resolution = normalize_seedance_mode(payload.get("resolution") or "720p")
    if resolution not in get_seedance_mode_options(model_code):
        resolution = get_seedance_mode_options(model_code)[0]

    # Провайдер-диспетчинг такой же, как в run_seedance: gemini_omni всегда
    # EvoLink (нет у Zveno), seedance2/2_fast — по SEEDANCE_PROVIDER, остальные
    # модели студии (kling3/veo31/wan27) — всегда Zveno. poll_seedance_task сам
    # распознаёт префикс __EVOLINK__: — вызов ниже не меняется.
    if model_code == "gemini_omni":
        _studio_start_fn = start_gemini_omni_task_evolink
    elif seedance_uses_evolink(model_code):
        _studio_start_fn = start_seedance_task_evolink
    else:
        _studio_start_fn = start_seedance_task
    task_id = await _studio_start_fn(
        prompt=video_prompt or "Animate this frame naturally, cartoon style",
        image_url=frame_url,
        user_id=user_id,
        duration=duration,
        mode=resolution,
        model_code=model_code,
        aspect_ratio=aspect,
    )
    clip_url = await poll_seedance_task(
        task_id, SEEDANCE_MAX_POLL_ATTEMPTS, SEEDANCE_POLL_INTERVAL, expected_refs_count=1,
    )
    if not clip_url:
        raise Exception("studio clip: empty result url (download_error)")
    # Бэкап в чат ФАЙЛОМ, не URL: прод-аудит 2026-07-28 показал, что
    # send_video(video=<zveno_url>) молча падает (Telegram не может скачать
    # Zveno-URL — редиректы/размер), и ни один клип-бэкап юзерам не доехал.
    # Обычный видео-путь бота всегда качает байты — делаем так же.
    try:
        clip_bytes = await _download_video_bytes_with_fallback_hook(clip_url)
        clip_buffer = io.BytesIO(clip_bytes)
        clip_buffer.name = "studio_clip.mp4"
        await app.bot.send_video(
            chat_id=user_id, video=clip_buffer, supports_streaming=True,
            caption="🎬 Клип из студии мультиков готов — смотри в студии или здесь.",
        )
    except Exception:
        logger.warning("studio clip: failed to send backup to chat user=%s", user_id)
    return {"clip_url": clip_url, "duration": duration}


STUDIO_STITCH_RESOLUTION = {"9:16": "1080x1920", "16:9": "1920x1080", "4:3": "1440x1080"}


async def _studio_ffmpeg_run(*args: str, timeout: int = 300) -> None:
    """Запускает ffmpeg/ffprobe, кидает исключение с хвостом stderr при ошибке."""
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise Exception(f"studio stitch: ffmpeg timeout ({args[0]})")
    if proc.returncode != 0:
        raise Exception(f"studio stitch: {args[0]} failed: {stderr.decode(errors='replace')[-500:]}")


async def _studio_clip_has_audio(path: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
        "-of", "csv=p=0", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    return bool(stdout.decode(errors="replace").strip())


async def _studio_normalize_clip(src: str, dst: str, aspect: str) -> None:
    """Единый формат под concat: одно разрешение/fps/кодеки + звуковая
    дорожка обязательна (тихая, если в исходнике её нет — ревизия ТЗ п.8,
    иначе ffmpeg concat падает на смеси клипов со звуком и без)."""
    res = STUDIO_STITCH_RESOLUTION.get(aspect, STUDIO_STITCH_RESOLUTION["9:16"])
    w, h = res.split("x")
    scale_filter = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
    )
    has_audio = await _studio_clip_has_audio(src)
    args = ["ffmpeg", "-y", "-i", src]
    if not has_audio:
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    args += ["-vf", scale_filter, "-map", "0:v:0"]
    args += ["-map", "1:a:0" if not has_audio else "0:a:0"]
    args += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        dst,
    ]
    await _studio_ffmpeg_run(*args)


async def _studio_generate_stitch(app: Application, user_id: int, payload: dict) -> dict:
    """Склейка готовых клипов сцен в один ролик. Хостинга видео у нас нет
    (ревизия ТЗ), поэтому итог живёт в чате — файлом, как и клип-бэкапы;
    в D1 final_url не пишем (Function помечает проект done без плеера в
    вебаппе, только ссылка «смотри в чате»)."""
    clip_urls = [u for u in (payload.get("clips") or []) if isinstance(u, str) and u.strip()]
    if len(clip_urls) < 2:
        raise ValueError("studio stitch: need at least 2 clips")
    aspect = str(payload.get("aspect") or "9:16")
    if aspect not in STUDIO_STITCH_RESOLUTION:
        aspect = "9:16"

    workdir = tempfile.mkdtemp(prefix="studio_stitch_")
    try:
        normalized = []
        for i, url in enumerate(clip_urls):
            raw_path = os.path.join(workdir, f"raw_{i}.mp4")
            with open(raw_path, "wb") as f:
                f.write(await _download_video_bytes_with_fallback_hook(url))
            norm_path = os.path.join(workdir, f"norm_{i}.mp4")
            await _studio_normalize_clip(raw_path, norm_path, aspect)
            normalized.append(norm_path)

        list_path = os.path.join(workdir, "concat.txt")
        with open(list_path, "w") as f:
            for p in normalized:
                f.write(f"file '{p}'\n")

        final_path = os.path.join(workdir, "final.mp4")
        await _studio_ffmpeg_run(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", final_path,
        )

        with open(final_path, "rb") as f:
            final_bytes = f.read()
        final_buffer = io.BytesIO(final_bytes)
        final_buffer.name = "studio_final.mp4"
        await app.bot.send_video(
            chat_id=user_id, video=final_buffer, supports_streaming=True,
            caption="🎬 Мультик из студии склеен — готов!",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return {"final_url": "", "clips_count": len(clip_urls)}


async def _studio_execute_job(app: Application, job: dict) -> dict:
    """Генерация без биллинга. Возвращает result-dict, кидает исключения."""
    job_type = str(job.get("type") or "")
    payload = job.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload or "{}")
    user_id = int(job.get("user_id"))
    if job_type == "scenario":
        return await _studio_generate_scenario(payload)
    if job_type == "frame":
        return await _studio_generate_frame(user_id, payload)
    if job_type == "clip":
        return await _studio_generate_clip(app, user_id, payload)
    if job_type == "stitch":
        return await _studio_generate_stitch(app, user_id, payload)
    raise ValueError(f"studio: unknown job type {job_type}")


async def _studio_handle_job(app: Application, job: dict) -> None:
    job_id = str(job.get("id") or "")
    user_id = int(job.get("user_id") or 0)
    if not job_id or not user_id:
        return
    payload = job.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload or "{}")
        except json.JSONDecodeError:
            payload = {}
    job["payload"] = payload

    lock = _studio_user_locks.setdefault(user_id, asyncio.Lock())
    async with _studio_semaphore:
        async with lock:
            # Идемпотентность: уже сделан (complete не дошёл в прошлый раз) —
            # только повторная доставка, без генерации и денег. Запись со
            # status='charged' — бот упал МЕЖДУ списанием и завершением
            # генерации: деньги уже взяты, генерацию надо повторить, но
            # списывать второй раз нельзя.
            done = get_studio_done_job(job_id)
            if done and done["status"] in ("done", "error"):
                await _studio_complete(job_id, done["status"], done["error"], json.loads(done["result"] or "{}"))
                return
            already_charged = bool(done and done["status"] == "charged" and done["charged"])

            job_type = str(job.get("type") or "")
            # Цена: пересчёт по боту + сверка с корзиной (ревизия п.5)
            try:
                cost = _studio_compute_cost(job_type, payload)
            except Exception as e:
                record_studio_done_job(job_id, user_id, False, 0, "error", "internal", "{}")
                await _studio_complete(job_id, "error", "internal", {"detail": str(e)[:200]})
                return
            expected = payload.get("expected_cost")
            if cost > 0 and expected is not None and int(expected) != cost:
                record_studio_done_job(job_id, user_id, False, 0, "error", "price_changed", "{}")
                await _studio_complete(job_id, "error", "price_changed", {"actual_cost": cost})
                return

            charged = already_charged
            if cost > 0 and not _is_admin_hook(user_id) and not already_charged:
                if not spend_izyminki(user_id, cost):
                    record_studio_done_job(job_id, user_id, False, cost, "error", "not_enough_funds", "{}")
                    await _studio_complete(
                        job_id, "error", "not_enough_funds",
                        {"cost": cost, "balance": get_balance(user_id)},
                    )
                    return
                charged = True
                # Журналируем списание ДО генерации: упадём во время генерации —
                # при повторном взятии job'а не спишем второй раз.
                record_studio_done_job(job_id, user_id, True, cost, "charged", "", "{}")

            try:
                result = await _studio_execute_job(app, job)
                status, error = "done", ""
            except Exception as e:
                if charged:
                    add_izyminki(user_id, cost)  # возврат при ошибке генерации
                    charged = False
                kind = _classify_generation_error_hook(e)
                error = "moderation" if kind == "moderation" else "provider"
                status, result = "error", {"detail": str(e)[:200]}
                logger.warning("studio job %s (%s) failed: %s", job_id, job.get("type"), e)

            record_studio_done_job(job_id, user_id, charged, cost, status, error, json.dumps(result, ensure_ascii=False))
            await _studio_complete(job_id, status, error, result)


async def _studio_run_job(app: Application, job: dict) -> None:
    try:
        await _studio_handle_job(app, job)
    except Exception:
        logger.exception("studio job crashed: %s", job.get("id"))
    finally:
        _studio_active_job_ids.discard(str(job.get("id") or ""))


async def _studio_poll_loop(app: Application) -> None:
    global _studio_semaphore
    _studio_semaphore = asyncio.Semaphore(STUDIO_CONCURRENCY)
    # Прайс — источник правды по тарифам (ревизия п.5). Пуш при старте может
    # упасть на разовом сбое Cloudflare (живой прод 2026-08-01: status=500 с
    # HTML-страницей ошибки CF) — раньше это значило «корзина студии живёт со
    # старым прайсом до следующего рестарта бота». Теперь ретраим в поллинг-
    # цикле, пока пуш не пройдёт.
    prices_pushed = await _studio_api("prices.push", {"prices": _studio_price_feed()}) is not None
    if not prices_pushed:
        logger.warning("studio prices.push failed on startup — will retry in poll loop")
    logger.info("studio poll loop started: %s (every %ss)", STUDIO_API_BASE, STUDIO_POLL_INTERVAL)
    _prices_retry_backoff = 0  # тиков до следующей попытки (растёт до ~2 мин)
    while True:
        try:
            if not prices_pushed:
                if _prices_retry_backoff <= 0:
                    prices_pushed = await _studio_api("prices.push", {"prices": _studio_price_feed()}) is not None
                    if prices_pushed:
                        logger.info("studio prices.push succeeded on retry")
                    else:
                        _prices_retry_backoff = min(_prices_retry_backoff * 2 + 4, 30)
                else:
                    _prices_retry_backoff -= 1
            data = await _studio_api("poll", {"limit": STUDIO_CONCURRENCY * 2})
            for job in (data or {}).get("jobs") or []:
                jid = str(job.get("id") or "")
                if jid and jid not in _studio_active_job_ids:
                    _studio_active_job_ids.add(jid)
                    asyncio.create_task(_studio_run_job(app, job))
        except Exception:
            logger.exception("studio poll loop error")
        await asyncio.sleep(STUDIO_POLL_INTERVAL)
