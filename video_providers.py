"""HTTP-клиенты видео-провайдеров (Zveno, EvoLink, MashaGPT, fal.ai).

Вынесено из SirNike.py в рамках фазы 1 разбора монолита (см.
docs/briefs/backend.md). Чисто структурный рефакторинг — поведение не менялось.

Модуль не должен импортировать ничего из SirNike.py (иначе циклический импорт:
SirNike.py импортирует функции отсюда). Функции здесь не знают про Telegram
Update/context/UserState/биллинг изюминок — это уровень провайдера, а не бота.

Немногие места, где провайдер-клиентам всё же нужны бот-уровневые хелперы
(резолв __img__-рефов из in-memory кэша фото, сборка reference sheet картинки,
загрузка байтов на freeimage/catbox — всё это НЕ провайдер-специфично и
используется в SirNike.py далеко за пределами видео-провайдеров), решены через
инъекцию зависимостей: SirNike.py вызывает configure(...) один раз при
старте (сразу после определения нужных хелперов), передавая туда свои функции.
До первого configure() эти хуки — no-op заглушки, которые ведут себя так же,
как если бы фото-рефов/reference sheet просто не было (не должно случаться в
проде, т.к. SirNike.py вызывает configure() при импорте модуля).
"""

import asyncio
import base64
import io
import json
import logging
import re
from typing import Awaitable, Callable, List, Optional
from urllib.parse import urlsplit

import aiohttp
from PIL import Image

from config import (
    EVOLINK_API_BASE,
    EVOLINK_API_KEY,
    FAL_API_BASE,
    FAL_API_KEY,
    GEMINI_OMNI_DURATION,
    GEMINI_OMNI_DURATION_OPTIONS,
    GEMINI_OMNI_MODEL,
    KLING3_DURATION_OPTIONS,
    KLING3_MODEL,
    KLING_MOTION_DURATION,
    KLING_MOTION_ENDPOINT,
    KLING_MOTION_MODE,
    KLING_MOTION_ORIENTATION,
    MASHAGPT_API_BASE,
    MASHAGPT_API_KEY,
    SEEDANCE_DURATION,
    SEEDANCE_DURATION_OPTIONS,
    SEEDANCE_ENDPOINT,
    SEEDANCE_FAST_DURATION_OPTIONS,
    SEEDANCE_FAST_MODE,
    SEEDANCE_MODE,
    SEEDANCE_PROVIDER,
    VEO31_DURATION_OPTIONS,
    VEO31_MODEL,
    WAN27_DURATION_OPTIONS,
    WAN27_MODEL,
    MAX_SEEDANCE_IMAGE_REFERENCES,
    SEEDANCE_VIDEO_REFERENCE_MODE,
    ZVENO_API_BASE,
    ZVENO_API_KEY,
)

logger = logging.getLogger(__name__)

# Свежий os для чтения тех же переменных окружения, что раньше читались через
# SirNike.py-локальные os.getenv (SEEDANCE_MODE_OPTIONS/SEEDANCE_FAST_MODE_OPTIONS
# не заведены в config.py константами — оставляем как есть, ноль изменений
# поведения).
import os


# ----------------------------------------------------------------------------
# Инъекция бот-уровневых зависимостей (см. докстринг модуля)
# ----------------------------------------------------------------------------

def _default_resolve_image_ref_to_data_url(_ref: str) -> Optional[str]:
    return None


def _default_resolve_image_bytes(_ref: str) -> Optional[bytes]:
    return None


async def _default_build_reference_sheet_url(_urls: List[str]) -> Optional[str]:
    return None


async def _default_upload_bytes(_image_bytes: bytes, _filename: str = "image.jpg") -> Optional[str]:
    return None


_is_img_ref_hook: Callable[[str], bool] = lambda value: (
    isinstance(value, str) and value.startswith("__img_") and value.endswith("__")
)
_ref_to_data_url_hook: Callable[[str], Optional[str]] = _default_resolve_image_ref_to_data_url
_resolve_image_bytes_hook: Callable[[str], Optional[bytes]] = _default_resolve_image_bytes
_build_reference_sheet_url_hook: Callable[[List[str]], Awaitable[Optional[str]]] = _default_build_reference_sheet_url
_upload_bytes_to_freeimage_hook: Callable[[bytes, str], Awaitable[Optional[str]]] = _default_upload_bytes
_upload_bytes_to_catbox_hook: Callable[[bytes, str], Awaitable[Optional[str]]] = _default_upload_bytes

# EVOLINK_API_KEY/SEEDANCE_PROVIDER читаются через геттеры (не как голые
# константы) — так тесты, которые патчат `S.EVOLINK_API_KEY = "..."`/
# `S.SEEDANCE_PROVIDER = "evolink"` (переприсваивание имени в namespace
# SirNike.py), продолжают работать: дефолтный геттер читает config.*, а
# SirNike.py через configure() подменяет его на `lambda: EVOLINK_API_KEY`,
# который резолвит имя в СВОЁМ модуле в момент вызова (а не в момент импорта) —
# ровно то место, которое тест патчит.
_get_evolink_api_key_hook: Callable[[], str] = lambda: EVOLINK_API_KEY
_get_seedance_provider_hook: Callable[[], str] = lambda: SEEDANCE_PROVIDER


def configure(
    *,
    is_img_ref: Optional[Callable[[str], bool]] = None,
    ref_to_data_url: Optional[Callable[[str], Optional[str]]] = None,
    resolve_image_bytes: Optional[Callable[[str], Optional[bytes]]] = None,
    build_reference_sheet_url: Optional[Callable[[List[str]], Awaitable[Optional[str]]]] = None,
    upload_bytes_to_freeimage: Optional[Callable[[bytes, str], Awaitable[Optional[str]]]] = None,
    upload_bytes_to_catbox: Optional[Callable[[bytes, str], Awaitable[Optional[str]]]] = None,
    get_evolink_api_key: Optional[Callable[[], str]] = None,
    get_seedance_provider: Optional[Callable[[], str]] = None,
) -> None:
    """Вызывается из SirNike.py один раз при импорте — прокидывает сюда
    бот-уровневые хелперы (кэш загруженных фото, аплоад на freeimage/catbox,
    сборку reference sheet), которые сами по себе не провайдер-специфичны и
    остаются в SirNike.py."""
    global _is_img_ref_hook, _ref_to_data_url_hook, _resolve_image_bytes_hook
    global _build_reference_sheet_url_hook, _upload_bytes_to_freeimage_hook, _upload_bytes_to_catbox_hook
    global _get_evolink_api_key_hook, _get_seedance_provider_hook
    if is_img_ref is not None:
        _is_img_ref_hook = is_img_ref
    if ref_to_data_url is not None:
        _ref_to_data_url_hook = ref_to_data_url
    if get_evolink_api_key is not None:
        _get_evolink_api_key_hook = get_evolink_api_key
    if get_seedance_provider is not None:
        _get_seedance_provider_hook = get_seedance_provider
    if resolve_image_bytes is not None:
        _resolve_image_bytes_hook = resolve_image_bytes
    if build_reference_sheet_url is not None:
        _build_reference_sheet_url_hook = build_reference_sheet_url
    if upload_bytes_to_freeimage is not None:
        _upload_bytes_to_freeimage_hook = upload_bytes_to_freeimage
    if upload_bytes_to_catbox is not None:
        _upload_bytes_to_catbox_hook = upload_bytes_to_catbox


# ----------------------------------------------------------------------------
# Общие хелперы (режим/длительность/URL-билдеры)
# ----------------------------------------------------------------------------

def seedance_uses_evolink(model_code: str) -> bool:
    """Провайдер-флаг из docs/specs/2026-07-31_evolink_video_provider.md — только
    Seedance 2.0/2.0-fast умеют переключаться на EvoLink; Kling 3.0/Veo 3.1/
    Wan 2.7 всегда идут через Zveno вне зависимости от SEEDANCE_PROVIDER.
    Дефолт SEEDANCE_PROVIDER="zveno" всегда возвращает False — ноль изменений
    поведения, пока владелец явно не переключит env-переменную."""
    return model_code in ("seedance2", "seedance2_fast") and _get_seedance_provider_hook() == "evolink"


def get_seedance_duration_bounds(model_code: Optional[str] = None) -> tuple[int, int]:
    if model_code == "veo31":
        return 4, 8
    if model_code == "kling3":
        return 3, 15
    if model_code == "wan27":
        return 2, 10
    if model_code == "gemini_omni":
        return 3, 10
    if model_code in ("seedance2", "seedance2_fast") and seedance_uses_evolink(model_code):
        # EvoLink Seedance 2.0/2.0-fast: 4–15 сек (Zveno — 5–15).
        return 4, 15
    return 5, 15


def normalize_seedance_duration(value: int, model_code: Optional[str] = None) -> int:
    min_sec, max_sec = get_seedance_duration_bounds(model_code)
    clamped = max(min_sec, min(int(value), max_sec))
    if model_code == "veo31":
        # Veo 3.1 принимает только 4/6/8 секунд — прижимаем к ближайшему допустимому.
        clamped = min((4, 6, 8), key=lambda sec: abs(sec - clamped))
    return clamped


def normalize_seedance_mode(value: str) -> str:
    raw = str(value or "").strip().lower()
    # Normalize Cyrillic "р" -> Latin "p" in case env/UI text was typed in RU layout.
    raw = raw.replace("р", "p")
    if raw in ("480", "480p"):
        return "480p"
    if raw in ("1080", "1080p"):
        return "1080p"
    return "720p"


def seedance_mode_ui_label(mode: str) -> str:
    normalized = normalize_seedance_mode(mode)
    if normalized == "480p":
        return "480"
    if normalized == "1080p":
        return "1080"
    return "720"


def get_seedance_mode_options(model_code: Optional[str] = None) -> List[str]:
    if model_code == "seedance2_fast":
        raw_options = os.getenv("SEEDANCE_FAST_MODE_OPTIONS", "720,1080")
        parsed: List[str] = []
        for raw in str(raw_options).split(","):
            mode = normalize_seedance_mode(raw)
            if mode not in parsed:
                parsed.append(mode)
        default_mode = normalize_seedance_mode(SEEDANCE_FAST_MODE)
        if default_mode not in parsed:
            parsed.append(default_mode)
        if seedance_uses_evolink(model_code):
            # EvoLink Seedance 2.0-fast не поддерживает 1080p (только обычный
            # тариф умеет) — не даём выбрать несуществующую комбинацию.
            parsed = [m for m in parsed if m != "1080p"] or ["720p"]
        return parsed
    if model_code == "kling3":
        # Zveno: kling-v3.0 теперь умеет и 720p, и 1080p.
        return ["720p", "1080p"]
    if model_code == "veo31":
        # Zveno: veo-3.1-fast поддерживает только 720p.
        return ["720p"]

    raw_options = os.getenv("SEEDANCE_MODE_OPTIONS", "480,720,1080")
    parsed: List[str] = []
    for raw in str(raw_options).split(","):
        mode = normalize_seedance_mode(raw)
        if mode not in parsed:
            parsed.append(mode)
    default_mode = normalize_seedance_mode(SEEDANCE_MODE)
    if default_mode not in parsed:
        parsed.append(default_mode)
    # Seedance 2 supports 480p/720p/1080p. Keep all visible unless explicitly restricted.
    for fallback_mode in ("480p", "720p", "1080p"):
        if fallback_mode not in parsed:
            parsed.append(fallback_mode)
    return parsed


def get_seedance_duration_options(model_code: Optional[str] = None) -> List[int]:
    if model_code == "kling3":
        raw_options = KLING3_DURATION_OPTIONS
    elif model_code == "veo31":
        raw_options = VEO31_DURATION_OPTIONS
    elif model_code == "wan27":
        raw_options = WAN27_DURATION_OPTIONS
    elif model_code == "seedance2_fast":
        raw_options = SEEDANCE_FAST_DURATION_OPTIONS
    elif model_code == "gemini_omni":
        raw_options = GEMINI_OMNI_DURATION_OPTIONS
    else:
        raw_options = SEEDANCE_DURATION_OPTIONS
    parsed: List[int] = []
    for raw in str(raw_options).split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            sec = int(raw)
        except ValueError:
            continue
        sec = normalize_seedance_duration(sec, model_code)
        if sec not in parsed:
            parsed.append(sec)

    default_sec = normalize_seedance_duration(int(SEEDANCE_DURATION), model_code)
    if default_sec not in parsed:
        parsed.append(default_sec)
    if model_code != "seedance2_fast" and len(parsed) <= 1:
        # Guardrail: if env accidentally left only "5", keep normal Seedance 2 controls available.
        for fallback_sec in (5, 10, 15):
            sec = normalize_seedance_duration(fallback_sec, model_code)
            if sec not in parsed:
                parsed.append(sec)
    parsed.sort()
    return parsed


def build_mashagpt_url(base: str, path: str) -> str:
    b = (base or "").strip()
    p = "/" + path.strip("/")

    parsed = urlsplit(b)
    if parsed.scheme and parsed.netloc:
        # Always keep only origin from base URL to avoid duplicated path segments.
        b = f"{parsed.scheme}://{parsed.netloc}"
    else:
        b = b.rstrip("/")

    return f"{b}{p}"


def build_zveno_url(base: str, path: str) -> str:
    b = (base or "").strip().rstrip("/")
    p = "/" + path.strip("/")
    if b.endswith("/v1") and p.startswith("/v1/"):
        return f"{b}{p[3:]}"
    return f"{b}{p}"


def build_seedance_prompt_with_refs(prompt_text: str, refs_count: int, tag_format: str = "bracket") -> str:
    """tag_format различается по провайдеру: Zveno понимает [Image1]/[Image2]
    (везде в этом файле), EvoLink требует @image1/@image2 в нижнем регистре
    (доки EvoLink, video-series/seedance2.0/*-reference-to-video: "Tag numbers
    follow the order of the corresponding URL array... the first image_urls
    item is @image1"). Разный формат — разные плейсхолдеры, иначе автотекст
    привязки ссылается на теги, которых модель не узнаёт."""
    text = (prompt_text or "").strip()
    if not text:
        text = "Cinematic video with coherent action and stable character identity."

    if refs_count <= 0:
        return text

    tag = (lambda i: f"[Image{i}]") if tag_format == "bracket" else (lambda i: f"@image{i}")
    placeholders = ", ".join([tag(i) for i in range(1, refs_count + 1)])

    if refs_count == 1:
        binding = (
            f"Use {tag(1)} as the main character identity reference. "
            "Preserve face, body, hair, clothes, and style."
        )
    else:
        binding = (
            f"Reference images: {placeholders}. "
            "If they show the same person from different angles, treat them as ONE character — "
            "do not create twins or duplicates. "
            "If they show different people, treat them as separate characters. "
            "Preserve each character's face, body, hair, clothes, and style."
        )

    return f"{binding}\n{text}"


def _data_url_to_jpeg_rgb(data_url: str) -> str:
    """Перекодирует data: URL картинки в JPEG RGB (без альфа-канала).

    Kling/Veo принимают картинку как первый кадр видео и отклоняют
    кадры с прозрачностью («Image pixel is invalid»)."""
    try:
        comma = data_url.find(",")
        if comma == -1:
            return data_url
        raw = base64.b64decode(data_url[comma + 1:])
        img = Image.open(io.BytesIO(raw))
        if img.mode != "RGB":
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92)
        return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()
    except Exception:
        logger.warning("_data_url_to_jpeg_rgb: conversion failed, sending original")
        return data_url


def is_seedance_privacy_moderation_error(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    keys = [
        "inputimagesensitivecontentdetected.privacyinformation",
        "inputimagesensitivecontentdetected",
        "privacyinformation",
        "real person",
        "may contain real person",
    ]
    return any(key in lowered for key in keys)


def extract_task_video_url(task_data: dict) -> Optional[str]:
    output = task_data.get("output")
    keys = ("url", "videoUrl", "video_url", "resultUrl", "result_url")

    for key in keys:
        value = task_data.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value

    if isinstance(output, str) and output.startswith("http"):
        return output

    if isinstance(output, dict):
        for key in keys:
            value = output.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        videos = output.get("videos")
        if isinstance(videos, list):
            for item in videos:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    value = item.get("url") or item.get("videoUrl") or item.get("video_url")
                    if isinstance(value, str) and value.startswith("http"):
                        return value

    if isinstance(output, list):
        for item in output:
            if isinstance(item, str) and item.startswith("http"):
                return item
            if isinstance(item, dict):
                value = item.get("url") or item.get("videoUrl") or item.get("video_url")
                if isinstance(value, str) and value.startswith("http"):
                    return value

    return None


def extract_task_reference_count(task_like: dict) -> int:
    if not isinstance(task_like, dict):
        return 0

    source = task_like.get("input") if isinstance(task_like.get("input"), dict) else task_like

    def _count(value) -> int:
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return 1
        if isinstance(value, str) and value.strip():
            return 1
        return 0

    for key in ("frame_images", "input_references", "image_urls", "reference_images"):
        count = _count(source.get(key))
        if count:
            return count

    return _count(source.get("image_url"))


# ----------------------------------------------------------------------------
# MashaGPT (Kling Motion Control) — HTTP-клиент
# ----------------------------------------------------------------------------

async def start_kling_motion_control(
    image_url: str,
    motion_video_url: str,
    prompt: str,
    user_id: int,
    api_base: str = MASHAGPT_API_BASE,
    api_key: str = MASHAGPT_API_KEY,
) -> str:
    """Kling Motion Control (kling-2-6-motion-control) — сейчас всегда зовётся с
    дефолтами MashaGPT (не переключено на EvoLink, нет API-ключа). api_base/
    api_key параметризованы заранее, чтобы включение EvoLink-провайдера потом
    было одной правкой вызова (новый base/key), без переписывания тела функции —
    см. docs/specs/2026-07-31_evolink_video_provider.md. Формат запроса EvoLink
    ещё не сверен с MashaGPT — до этого функция реально работает только с
    MashaGPT.
    """
    if not KLING_MOTION_ENDPOINT:
        raise Exception("Эндпоинт видео-генерации не настроен (KLING_MOTION_ENDPOINT).")

    if not api_key:
        raise Exception("API key is empty (MASHAGPT_API_KEY/api_key)")

    endpoint_path = (KLING_MOTION_ENDPOINT or "").strip()
    if "kling-v2-6-motion-control" in endpoint_path:
        endpoint_path = endpoint_path.replace(
            "kling-v2-6-motion-control",
            "kling-2-6-motion-control",
        )
    endpoint_candidates = [endpoint_path]
    if "kling-2-6-motion-control" in endpoint_path:
        endpoint_candidates.append(endpoint_path.replace("kling-2-6-motion-control", "kling-v2-6-motion-control"))
    elif "kling-v2-6-motion-control" in endpoint_path:
        endpoint_candidates.append(endpoint_path.replace("kling-v2-6-motion-control", "kling-2-6-motion-control"))

    mode = "1080p" if str(KLING_MOTION_MODE).lower() == "1080p" else "720p"
    orientation = "image" if str(KLING_MOTION_ORIENTATION).lower() == "image" else "video"
    safe_duration = max(3, min(int(KLING_MOTION_DURATION), 30))
    if orientation == "image":
        safe_duration = min(safe_duration, 10)

    async with aiohttp.ClientSession() as session:
        last_error = None
        for endpoint in endpoint_candidates:
            request_url = build_mashagpt_url(api_base, endpoint)
            logger.info(f"Video endpoint: {request_url}")
            async with session.post(
                request_url,
                headers={
                    "x-api-key": api_key,
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "inputUrls": [image_url],
                    "videoUrls": [motion_video_url],
                    "characterOrientation": orientation,
                    "duration": safe_duration,
                    "prompt": prompt or "",
                    "mode": mode,
                },
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                response_text = await resp.text()
                if not (200 <= resp.status < 300):
                    last_error = f"{resp.status}. {response_text}"
                    logger.warning(f"Video start failed for {request_url}: {last_error}")
                    continue

                data = json.loads(response_text)
                task_id = data.get("id")
                if not task_id:
                    last_error = f"Task id missing in response: {data}"
                    continue
                return str(task_id)

        raise Exception(f"Video start error: {last_error}")


async def poll_kling_animation_custom(animation_id: str, max_attempts: int, poll_interval: int) -> str:
    if not MASHAGPT_API_KEY:
        raise Exception("MASHAGPT_API_KEY is empty")

    def extract_video_url(task_data: dict) -> Optional[str]:
        output = task_data.get("output")
        keys = ("url", "videoUrl", "video_url", "resultUrl", "result_url")

        for key in keys:
            value = task_data.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value

        if isinstance(output, str) and output.startswith("http"):
            return output

        if isinstance(output, dict):
            for key in keys:
                value = output.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
            videos = output.get("videos")
            if isinstance(videos, list):
                for item in videos:
                    if isinstance(item, str) and item.startswith("http"):
                        return item
                    if isinstance(item, dict):
                        value = item.get("url") or item.get("videoUrl") or item.get("video_url")
                        if isinstance(value, str) and value.startswith("http"):
                            return value

        if isinstance(output, list):
            for item in output:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    value = item.get("url") or item.get("videoUrl") or item.get("video_url")
                    if isinstance(value, str) and value.startswith("http"):
                        return value

        return None

    poll_paths = [
        f"/v1/tasks/{animation_id}",
        f"/api/v1/tasks/{animation_id}",
        f"/v1/tasks/kling-2-6-motion-control/{animation_id}",
        f"/v1/tasks/kling-v2-6-motion-control/{animation_id}",
    ]
    poll_urls = [build_mashagpt_url(MASHAGPT_API_BASE, p) for p in poll_paths]
    for url in poll_urls:
        logger.info(f"Video poll endpoint: {url}")
    running_urls = [
        build_mashagpt_url(MASHAGPT_API_BASE, "/v1/tasks/running"),
        build_mashagpt_url(MASHAGPT_API_BASE, "/api/v1/tasks/running"),
        build_mashagpt_url(MASHAGPT_API_BASE, "/tasks/running"),
    ]

    unknown_model_hits = 0

    def find_task_in_running(payload: object) -> Optional[dict]:
        candidates = []
        if isinstance(payload, list):
            candidates = payload
        elif isinstance(payload, dict):
            for key in ("data", "items", "tasks", "results"):
                block = payload.get(key)
                if isinstance(block, list):
                    candidates = block
                    break
        for item in candidates:
            if isinstance(item, dict) and str(item.get("id")) == str(animation_id):
                return item
        return None

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_attempts):
            await asyncio.sleep(poll_interval)

            data = None
            had_unknown_model_error = False
            for poll_url in poll_urls:
                async with session.get(
                    poll_url,
                    headers={
                        "x-api-key": MASHAGPT_API_KEY,
                        "Authorization": f"Bearer {MASHAGPT_API_KEY}",
                    },
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    response_text = await resp.text()
                    if resp.status == 200:
                        data = json.loads(response_text)
                        break
                    if "Unknown task model" in response_text:
                        had_unknown_model_error = True
                    logger.warning(
                        f"Video status check failed: {resp.status}, url={poll_url}, body: {response_text}"
                    )

            if data is None:
                try:
                    for running_url in running_urls:
                        async with session.get(
                            running_url,
                            headers={
                                "x-api-key": MASHAGPT_API_KEY,
                                "Authorization": f"Bearer {MASHAGPT_API_KEY}",
                            },
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as running_resp:
                            running_text = await running_resp.text()
                            if running_resp.status == 200:
                                logger.info(f"Video running endpoint ok: {running_url}")
                                running_payload = json.loads(running_text)
                                task_obj = find_task_in_running(running_payload)
                                if task_obj:
                                    data = task_obj
                                    break
                            else:
                                logger.warning(
                                    f"Video running check failed: {running_resp.status}, "
                                    f"url={running_url}, body: {running_text}"
                                )
                except Exception:
                    pass

            if data is not None:
                status = str(data.get("status", "")).upper()
                status_description = data.get("message") or ""

                logger.info(
                    f"Video task {animation_id}: "
                    f"attempt={attempt + 1}/{max_attempts}, "
                    f"status={status}, "
                    f"status_description={status_description}"
                )

                if status == "COMPLETED":
                    result_url = extract_video_url(data)
                    if not result_url:
                        raise Exception(f"Video task completed but video URL missing: {data}")
                    return result_url

                if status in ("FAILED", "CANCELLED", "ERROR"):
                    raise Exception(
                        data.get("message")
                        or data.get("error")
                        or data.get("details")
                        or f"Video task failed with status {status}"
                    )
            else:
                # Provider-side routing/model issue: avoid waiting for full timeout.
                # If we repeatedly see "Unknown task model", fail fast and refund.
                if had_unknown_model_error:
                    unknown_model_hits += 1
                else:
                    unknown_model_hits = 0
                if unknown_model_hits >= 3:
                    raise Exception(
                        "Провайдер вернул Unknown task model при проверке статуса. "
                        "Это ошибка на стороне API, поэтому задачу остановили."
                    )

        raise Exception("Превышено время ожидания анимации")


# ----------------------------------------------------------------------------
# EvoLink — общий клиент (Seedance 2.0/2.0-fast, Gemini Omni Flash, Kling
# Motion Control) — единая точка создания/поллинга задач.
# ----------------------------------------------------------------------------

# Слаги моделей Seedance 2.0/2.0-fast на стороне EvoLink (отличаются от Zveno-
# слагов bytedance/seedance-2.0[-fast] — см. docs/specs/2026-07-31_evolink_video_provider.md).
# *-reference-to-video, НЕ *-image-to-video: у EvoLink (в отличие от Zveno,
# где один эндпоинт ест что угодно) это два разных API — image-to-video
# принимает строго 2 фото (первый+последний кадр), а reference-to-video —
# мультиреференс до 9 фото, ровно то, что нужно боту (multi-character
# промты вида «[Image1] — персонаж А, [Image2] — персонаж Б, ...»). Живой
# прод 2026-08-02: юзер загрузил 4 фото на image-to-video, EvoLink ответил
# 400 invalid_parameter ("only supports 2 image(s)... first and last frame
# images only") — переключение модели, а не обрезка списка, полный фикс.
EVOLINK_SEEDANCE_MODEL_MAP = {
    "seedance2": "seedance-2.0-reference-to-video",
    "seedance2_fast": "seedance-2.0-fast-reference-to-video",
}
# Доки EvoLink (seedance2.0/*-reference-to-video): "0–9 images" — тот же
# потолок, что у Zveno-Seedance (MAX_SEEDANCE_IMAGE_REFERENCES).
EVOLINK_SEEDANCE_MAX_IMAGES = 9


def build_evolink_url(path: str) -> str:
    """EvoLink base уже включает /v1 (EVOLINK_API_BASE) — переиспользуем логику
    build_zveno_url (совпадающий формат: origin + /v1/... без дублирования)."""
    return build_zveno_url(EVOLINK_API_BASE, path)


def _resolve_evolink_image_urls(
    image_url: Optional[str],
    image_urls: Optional[List[str]],
    max_count: int,
) -> List[str]:
    """Общая логика подготовки картинок для EvoLink: собрать, обрезать до лимита,
    резолвнуть __img__-рефы в data: URL (как в start_seedance_task)."""
    combined: List[str] = []
    for item in (image_urls or []):
        if isinstance(item, str):
            candidate = item.strip()
            if candidate and candidate not in combined:
                combined.append(candidate)
    if image_url:
        candidate = image_url.strip()
        if candidate and candidate not in combined:
            combined.append(candidate)
    if len(combined) > max_count:
        logger.warning(
            "EvoLink: обрезано %s фото-референсов до лимита модели %s",
            len(combined) - max_count, max_count,
        )
    combined = combined[:max_count]
    resolved: List[str] = []
    for u in combined:
        if _is_img_ref_hook(u):
            data_url = _ref_to_data_url_hook(u)
            if data_url:
                resolved.append(data_url)
            else:
                logger.warning("EvoLink: dropping stale __img__ ref %s (cache miss)", u[:30])
        else:
            resolved.append(u)
    return resolved


async def _evolink_create_task(payload: dict, log_label: str, user_id: int) -> str:
    """POST /v1/videos/generations — общая точка создания задачи для всех
    моделей серии EvoLink (Seedance/Gemini Omni/Kling Motion Control).
    Возвращает task_id с префиксом __EVOLINK__: (единая точка поллинга —
    poll_seedance_task/poll_evolink_task)."""
    evolink_api_key = _get_evolink_api_key_hook()
    if not evolink_api_key:
        raise Exception("EVOLINK_API_KEY is empty")
    url = build_evolink_url("/v1/videos/generations")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers={
                "Authorization": f"Bearer {evolink_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            response_text = await resp.text()
            if not (200 <= resp.status < 300):
                raise Exception(f"{log_label} create failed: {resp.status}. {response_text[:500]}")
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                raise Exception(f"{log_label}: non-JSON response: {response_text[:200]}")
            task_id = data.get("id")
            if not task_id:
                raise Exception(f"{log_label}: task id missing in response: {data}")
            usage = data.get("usage") or {}
            # credits_reserved — сырая единица EvoLink, НЕ наша изюминка/₽. Логируем
            # для будущей сверки цены по реальному счёту (ТЗ прямо запрещает
            # выводить формулу цены из этого числа сейчас).
            logger.info(
                "%s task created: task_id=%s model=%s credits_reserved(raw)=%s billing_rule=%s user_id=%s",
                log_label, task_id, payload.get("model"),
                usage.get("credits_reserved"), usage.get("billing_rule"), user_id,
            )
            return f"__EVOLINK__:{task_id}"


async def poll_evolink_task(
    task_id: str,
    max_attempts: int,
    poll_interval: int,
    status_callback=None,
) -> str:
    """Универсальный поллер EvoLink: GET /v1/tasks/{id} — один и тот же формат
    для Seedance/Gemini Omni/Kling Motion Control (см. docs/specs/2026-07-31_evolink_video_provider.md).
    task_id — «голый» id EvoLink, БЕЗ префикса __EVOLINK__: (снимает его вызывающий,
    см. poll_seedance_task)."""
    evolink_api_key = _get_evolink_api_key_hook()
    if not evolink_api_key:
        raise Exception("EVOLINK_API_KEY is empty")
    url = build_evolink_url(f"/v1/tasks/{task_id}")
    headers = {"Authorization": f"Bearer {evolink_api_key}"}
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_attempts):
            if status_callback and attempt > 0 and attempt % 8 == 0:
                elapsed_min = (attempt * poll_interval) // 60
                try:
                    await status_callback(f"⏳ Генерация видео... прошло ~{elapsed_min} мин.")
                except Exception:
                    pass
            await asyncio.sleep(poll_interval)
            try:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    response_text = await resp.text()
                    if resp.status != 200:
                        logger.warning(
                            "EvoLink poll failed: status=%s task_id=%s body=%s",
                            resp.status, task_id, response_text[:300],
                        )
                        continue
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.warning("EvoLink poll: non-JSON response: %s", response_text[:200])
                        continue
            except Exception as e:
                logger.warning("EvoLink poll request error: task_id=%s error=%s", task_id, e)
                continue

            status = str(data.get("status", "")).lower()
            logger.info(
                "EvoLink task %s: attempt=%s/%s status=%s progress=%s",
                task_id, attempt + 1, max_attempts, status, data.get("progress"),
            )

            if status == "completed":
                results = data.get("results")
                video_url = None
                if isinstance(results, list):
                    for item in results:
                        if isinstance(item, str) and item.strip().startswith("http"):
                            video_url = item.strip()
                            break
                if not video_url:
                    raise Exception(f"EvoLink task completed but results URL missing: {data}")
                return video_url

            if status in ("failed", "cancelled", "error"):
                error = data.get("error")
                code = None
                message = None
                if isinstance(error, dict):
                    code = error.get("code")
                    message = error.get("message")
                detail_parts = [p for p in (code, message) if p]
                detail = ": ".join(detail_parts) if detail_parts else f"EvoLink task failed with status {status}"
                raise Exception(detail)

            # "pending" / другие промежуточные статусы — просто ждём следующий тик.

    raise Exception("Превышено время ожидания генерации видео (EvoLink)")


async def start_seedance_task_evolink(
    prompt: str,
    image_url: Optional[str],
    user_id: int,
    duration: Optional[int] = None,
    endpoint: Optional[str] = None,
    mode: Optional[str] = None,
    model_slug: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
    model_code: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> str:
    """EvoLink-клиент для Seedance 2.0/2.0-fast (reference-to-video —
    мультиреференс до 9 фото, не image-to-video с потолком в 2).

    Тот же контракт возврата, что и start_seedance_task (строка task_id,
    здесь — с префиксом __EVOLINK__:, который poll_seedance_task умеет
    распознавать и делегировать в poll_evolink_task — вызывающий код
    (run_seedance/_studio_generate_clip) не меняется).
    """
    resolved_model_code = model_code if model_code in EVOLINK_SEEDANCE_MODEL_MAP else "seedance2"
    model_value = EVOLINK_SEEDANCE_MODEL_MAP[resolved_model_code]

    combined_image_urls = _resolve_evolink_image_urls(image_url, image_urls, EVOLINK_SEEDANCE_MAX_IMAGES)
    if not combined_image_urls:
        raise Exception("EvoLink Seedance: нет ни одного фото-референса (reference-to-video требует минимум 1 фото)")

    duration_val = normalize_seedance_duration(
        int(duration if duration is not None else SEEDANCE_DURATION), resolved_model_code,
    )
    quality = normalize_seedance_mode(mode or SEEDANCE_MODE)
    if resolved_model_code == "seedance2_fast" and quality == "1080p":
        # EvoLink Seedance 2.0-fast не умеет 1080p (только обычный тариф) —
        # фолбэк на 720p вместо отправки заведомо невалидного запроса.
        logger.warning("EvoLink seedance2_fast: 1080p не поддержан, фолбэк на 720p")
        quality = "720p"

    # EvoLink требует @image1/@image2 (нижний регистр), не [Image1] — доки
    # video-series/seedance2.0/*-reference-to-video, см. комментарий у
    # build_seedance_prompt_with_refs.
    prompt_text = build_seedance_prompt_with_refs((prompt or "").strip(), len(combined_image_urls), tag_format="at")

    payload = {
        "model": model_value,
        "prompt": prompt_text,
        "image_urls": combined_image_urls,
        "duration": duration_val,
        "aspect_ratio": aspect_ratio,
        "quality": quality,
        "generate_audio": True,
    }
    return await _evolink_create_task(payload, "EvoLink Seedance", user_id)


async def start_gemini_omni_task_evolink(
    prompt: str,
    image_url: Optional[str],
    user_id: int,
    duration: Optional[int] = None,
    endpoint: Optional[str] = None,
    mode: Optional[str] = None,
    model_slug: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
    model_code: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> str:
    """Gemini Omni Flash (EvoLink) — новый продукт, которого нет у Zveno.

    Одно фото (не мультиреференс, не reference-to-video) — image-to-video.
    Сигнатура совпадает с start_seedance_task/start_seedance_task_evolink,
    чтобы run_seedance мог вызывать её как drop-in для model_code=gemini_omni."""
    combined_image_urls = _resolve_evolink_image_urls(image_url, image_urls, max_count=1)
    if not combined_image_urls:
        raise Exception("Gemini Omni: нужно фото (image-to-video)")

    duration_val = normalize_seedance_duration(
        int(duration if duration is not None else GEMINI_OMNI_DURATION), "gemini_omni",
    )
    aspect = aspect_ratio if aspect_ratio in ("16:9", "9:16", "auto") else "16:9"
    prompt_text = (prompt or "").strip() or "Animate this photo naturally with subtle camera movement."

    payload = {
        "model": GEMINI_OMNI_MODEL,
        "prompt": prompt_text,
        "image_urls": combined_image_urls,
        "duration": duration_val,
        "aspect_ratio": aspect,
    }
    return await _evolink_create_task(payload, "EvoLink Gemini Omni", user_id)


async def start_kling_motion_control_evolink(
    image_url: str,
    motion_video_url: str,
    prompt: str,
    user_id: int,
) -> str:
    """Kling Motion Control через EvoLink (kling-v3-motion-control) — см.
    docs/specs/2026-07-31_evolink_video_provider.md. Переключается флагом
    MOTION_CONTROL_PROVIDER=evolink, независимым от SEEDANCE_PROVIDER."""
    quality = "1080p" if str(KLING_MOTION_MODE).lower() == "1080p" else "720p"
    payload: dict = {
        "model": "kling-v3-motion-control",
        "image_urls": [image_url],
        "video_urls": [motion_video_url],
        "model_params": {
            # "image": персонаж/внешность берётся с фото — у нас всегда есть и
            # фото, и референс-видео, это и есть наш флоу «своё фото + чужое движение».
            "character_orientation": "image",
            "keep_sound": True,
        },
        "quality": quality,
    }
    prompt_clean = (prompt or "").strip()
    if prompt_clean:
        payload["prompt"] = prompt_clean[:2500]
    return await _evolink_create_task(payload, "EvoLink Kling Motion Control", user_id)


# ----------------------------------------------------------------------------
# Zveno — основной видео-провайдер (Seedance 2.0/2.0-fast, Kling 3.0, Veo 3.1,
# Wan 2.7), с фоллбэком на fal.ai при 402/503 для Seedance-слагов.
# ----------------------------------------------------------------------------

async def start_seedance_task(
    prompt: str,
    image_url: Optional[str],
    user_id: int,
    duration: Optional[int] = None,
    endpoint: Optional[str] = None,
    mode: Optional[str] = None,
    model_slug: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
    model_code: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> str:
    if not ZVENO_API_KEY:
        raise Exception("ZVENO_API_KEY is empty")
    endpoint_value = str(endpoint or SEEDANCE_ENDPOINT).strip()
    if not endpoint_value:
        raise Exception("SEEDANCE endpoint is empty")

    endpoint_path = "/" + endpoint_value.strip("/")
    create_paths = [endpoint_path]
    is_video_jobs_endpoint = endpoint_path in ("/v1/videos", "/videos")
    if is_video_jobs_endpoint:
        create_paths = ["/v1/videos", "/videos"]
    elif endpoint_path.startswith("/v1/tasks/"):
        create_paths.append("/tasks/" + endpoint_path.split("/v1/tasks/", 1)[1])

    create_urls = []
    for path in create_paths:
        url = build_zveno_url(ZVENO_API_BASE, path)
        if url not in create_urls:
            create_urls.append(url)

    mode_value = normalize_seedance_mode(mode or SEEDANCE_MODE)
    model_value = str(model_slug or "bytedance/seedance-2.0-fast").strip()
    legacy_model_map = {
        "seedance-2-0": "bytedance/seedance-2.0",
        "seedance-2.0": "bytedance/seedance-2.0",
        "seedance-2-0-fast": "bytedance/seedance-2.0-fast",
        "seedance-2.0-fast": "bytedance/seedance-2.0-fast",
        "bytedance/seedance-2.0/reference-to-video": "bytedance/seedance-2.0",
        "bytedance/seedance-2.0/image-to-video": "bytedance/seedance-2.0",
        "bytedance/seedance-2.0/fast/reference-to-video": "bytedance/seedance-2.0-fast",
        "bytedance/seedance-2.0/fast/image-to-video": "bytedance/seedance-2.0-fast",
    }
    model_value = legacy_model_map.get(model_value.lower(), model_value)
    model_value_lower = model_value.lower()
    # Hard bind UI model choices to actual backend model slugs.
    # This avoids accidental .env substitutions (e.g. wan-2.7 under "Seedance 2" button).
    if model_code == "seedance2":
        model_value = "bytedance/seedance-2.0"
        model_value_lower = model_value.lower()
    elif model_code == "seedance2_fast":
        model_value = "bytedance/seedance-2.0-fast"
        model_value_lower = model_value.lower()
    elif model_code == "kling3":
        model_value = KLING3_MODEL
        model_value_lower = model_value.lower()
    elif model_code == "veo31":
        model_value = VEO31_MODEL
        model_value_lower = model_value.lower()
    elif model_code == "wan27":
        model_value = WAN27_MODEL
        model_value_lower = model_value.lower()
    duration = normalize_seedance_duration(
        int(duration if duration is not None else SEEDANCE_DURATION),
        model_code,
    )
    if model_code in ("veo31", "wan27") and aspect_ratio not in ("16:9", "9:16"):
        aspect_ratio = "16:9"
    is_wan_model = "wan-2.7" in model_value_lower or model_value_lower.startswith("alibaba/wan")
    is_seedance2_model = model_value_lower in ("bytedance/seedance-2.0", "bytedance/seedance-2.0-fast")
    combined_image_urls: List[str] = []
    if image_urls:
        for item in image_urls:
            if isinstance(item, str):
                candidate = item.strip()
                if candidate and candidate not in combined_image_urls:
                    combined_image_urls.append(candidate)
    if image_url:
        candidate = image_url.strip()
        if candidate and candidate not in combined_image_urls:
            combined_image_urls.append(candidate)
    combined_image_urls = combined_image_urls[:MAX_SEEDANCE_IMAGE_REFERENCES]
    # Resolve __img__ cache refs to data: URLs; drop refs that can't be resolved
    resolved = []
    for u in combined_image_urls:
        if _is_img_ref_hook(u):
            data_url = _ref_to_data_url_hook(u)
            if data_url:
                resolved.append(data_url)
            else:
                logger.warning("start_seedance_task: dropping stale __img__ ref %s (cache miss)", u[:30])
        else:
            resolved.append(u)
    combined_image_urls = resolved
    if model_code in ("kling3", "veo31"):
        combined_image_urls = [
            _data_url_to_jpeg_rgb(u) if u.startswith("data:") else u
            for u in combined_image_urls
        ]

    prompt_text = build_seedance_prompt_with_refs((prompt or "").strip(), len(combined_image_urls))
    if len(combined_image_urls) > 1 and SEEDANCE_VIDEO_REFERENCE_MODE == "timeline":
        prompt_text = (
            "Use [Image1] as the START frame and [Image2] as the END frame. "
            "Keep identity continuity between both frames. "
            + prompt_text
        )

    payload_base = {
        "prompt": prompt_text,
        "duration": duration,
        "mode": mode_value,
    }
    if is_video_jobs_endpoint:
        payload_base = {
            "model": model_value,
            "prompt": prompt_text,
            "duration": duration,
            "resolution": mode_value,
            "aspect_ratio": aspect_ratio,
        }
        if model_code in ("kling3", "veo31"):
            # Обе модели реально умеют нативный синхронный звук (диалоги/эффекты/
            # фон по содержанию промта), и Zveno не берёт за это доплату — включаем
            # всегда. Раньше было принудительно False + safety-суффикс "silent
            # video" в run_seedance, который теперь применяется только при
            # авто-рестарте после реального отказа модерации по аудио.
            payload_base["generate_audio"] = True
    payload_variants = []
    if combined_image_urls:
        primary_image_url = combined_image_urls[0]
        reference_sheet_url = None
        if (
            is_video_jobs_endpoint
            and is_wan_model
            and len(combined_image_urls) > 1
            and SEEDANCE_VIDEO_REFERENCE_MODE != "timeline"
        ):
            reference_sheet_url = await _build_reference_sheet_url_hook(combined_image_urls)
        primary_frame_reference_url = reference_sheet_url or primary_image_url
        if is_video_jobs_endpoint:
            refs_payload = [
                {
                    "type": "image_url",
                    "image_url": {"url": url},
                }
                for url in combined_image_urls
            ]

            if model_code in ("kling3", "veo31"):
                # Kling 3.0: first(+last) кадры; Veo 3.1: только first.
                clean_frames = [
                    {
                        "type": "image_url",
                        "image_url": {"url": primary_image_url},
                        "frame_type": "first_frame",
                    }
                ]
                if model_code == "kling3" and len(combined_image_urls) > 1:
                    clean_frames.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": combined_image_urls[1]},
                            "frame_type": "last_frame",
                        }
                    )
                payload_variants.append({**payload_base, "frame_images": clean_frames})

            if SEEDANCE_VIDEO_REFERENCE_MODE == "timeline":
                # 1 image -> first_frame, 2 images -> first+last interpolation
                frame_images = [
                    {
                        "type": "image_url",
                        "image_url": {"url": primary_image_url},
                        "frame_type": "first_frame",
                    }
                ]
                if len(combined_image_urls) > 1:
                    frame_images.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": combined_image_urls[1]},
                            "frame_type": "last_frame",
                        }
                    )
                payload_variants.append({**payload_base, "frame_images": frame_images})
            else:
                if is_seedance2_model:
                    logger.info(
                        "Seedance 2 refs prepared: refs_count=%s, strategy=input_references-first",
                        len(combined_image_urls),
                    )
                    payload_variants.append({**payload_base, "input_references": refs_payload})
                else:
                    frame_anchor = [
                        {
                            "type": "image_url",
                            "image_url": {"url": primary_frame_reference_url},
                            "frame_type": "first_frame",
                        }
                    ]

                    if is_wan_model:
                        payload_variants.append(
                            {
                                **payload_base,
                                "frame_images": frame_anchor,
                                "image_urls": combined_image_urls,
                            }
                        )
                        payload_variants.append(
                            {
                                **payload_base,
                                "frame_images": frame_anchor,
                                "input_references": refs_payload,
                            }
                        )
                    else:
                        payload_variants.append(
                            {
                                **payload_base,
                                "frame_images": frame_anchor,
                                "input_references": refs_payload,
                            }
                        )
                        payload_variants.append(
                            {
                                **payload_base,
                                "frame_images": frame_anchor,
                                "image_urls": combined_image_urls,
                            }
                        )
                    payload_variants.append({**payload_base, "input_references": refs_payload})
                    payload_variants.append({**payload_base, "image_urls": combined_image_urls})

                    payload_variants.append(
                        {
                            **payload_base,
                            "input_references": [{"type": "image", "url": u} for u in combined_image_urls],
                        }
                    )
        else:
            payload_variants.append({**payload_base, "inputUrls": combined_image_urls})
            payload_variants.append({**payload_base, "imageUrls": combined_image_urls})
            payload_variants.append({**payload_base, "inputUrl": primary_image_url})
            payload_variants.append({**payload_base, "imageUrl": primary_image_url})
            payload_variants.append({**payload_base, "inputUrls": combined_image_urls, "imageUrls": combined_image_urls})
    else:
        if is_video_jobs_endpoint:
            payload_variants.append(payload_base)
        else:
            payload_variants.append(payload_base)

    last_error = "unknown"
    privacy_blocked = False
    async with aiohttp.ClientSession() as session:
        for create_url in create_urls:
            logger.info(f"Video create task endpoint: {create_url}")
            for payload in payload_variants:
                ref_keys = [k for k in ("frame_images", "input_references", "image_url", "image_urls", "reference_images") if k in payload]
                logger.info(
                    f"Video create payload: model={payload.get('model')}, model_code={model_code}, duration={payload.get('duration') or payload.get('seconds')}, refs={ref_keys}, refs_count={len(combined_image_urls)}"
                )
                async with session.post(
                    create_url,
                    headers={
                        "x-api-key": ZVENO_API_KEY,
                        "Authorization": f"Bearer {ZVENO_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as resp:
                    response_text = await resp.text()
                    logger.info(f"Video create response: status={resp.status}, endpoint={create_url}")
                    if not (200 <= resp.status < 300):
                        logger.warning(
                            "Video create rejected: status=%s, body=%s",
                            resp.status,
                            response_text[:500],
                        )
                        last_error = f"{resp.status}. {response_text}"
                        if is_seedance_privacy_moderation_error(response_text):
                            privacy_blocked = True
                            break
                        continue
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        last_error = f"Non-JSON response: {response_text}"
                        continue
                    task_id = data.get("id")
                    polling_url = data.get("polling_url")
                    if is_video_jobs_endpoint and isinstance(polling_url, str) and polling_url.strip():
                        logger.info(f"Video create accepted: polling_url={polling_url.strip()}")
                        return "__POLL_URL__:" + polling_url.strip()
                    if task_id:
                        logger.info(f"Video create accepted: task_id={task_id}")
                        return str(task_id)
                    last_error = f"Task id missing in response: {data}"
            if privacy_blocked:
                break

    # Fallback to fal.ai when zveno.ai fails with 402 (no funds) or 503 (no provider)
    zveno_retriable = (
        "402" in last_error
        or "503" in last_error
        or "insufficient funds" in last_error.lower()
        or "no available" in last_error.lower()
    )
    if FAL_API_KEY and zveno_retriable and not privacy_blocked and model_code not in ("kling3", "veo31", "wan27"):
        # fal-фоллбэк замаплен только на Seedance-слаги — Kling/Veo/Wan не подменяем.
        logger.info("Zveno.ai unavailable (%s), falling back to fal.ai Seedance", last_error[:80])
        return await _start_seedance_task_fal(
            prompt=prompt,
            combined_image_urls=combined_image_urls,
            duration=duration,
            mode=mode_value,
            model_code=model_code,
            aspect_ratio=aspect_ratio,
        )

    raise Exception(f"Video create task error: {last_error}")


async def _start_seedance_task_fal(
    prompt: str,
    combined_image_urls: List[str],
    duration: int,
    mode: str,
    model_code: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> str:
    """Submit a Seedance 2.0 reference-to-video task via fal.ai queue API."""
    if not FAL_API_KEY:
        raise Exception("FAL_API_KEY is not set")
    model_path = (
        "bytedance/seedance-2.0/fast/reference-to-video"
        if model_code == "seedance2_fast"
        else "bytedance/seedance-2.0/reference-to-video"
    )
    # fal.ai uses @Image1..@ImageN syntax instead of [Image1]..[ImageN]
    fal_prompt = re.sub(r'\[Image(\d+)\]', r'@Image\1', prompt)
    resolution = mode if mode in ("480p", "720p", "1080p") else "720p"
    payload: dict = {
        "prompt": fal_prompt,
        "resolution": resolution,
        "duration": str(duration),
        "aspect_ratio": aspect_ratio,
        "generate_audio": False,
    }
    if combined_image_urls:
        # fal.ai requires public HTTP URLs — upload data: base64 refs to catbox first
        http_image_urls: List[str] = []
        for url in combined_image_urls:
            if url.startswith("data:") or _is_img_ref_hook(url):
                try:
                    img_bytes = _resolve_image_bytes_hook(url)
                    if img_bytes is None:
                        logger.warning("fal.ai: could not resolve image ref, skipping")
                        continue
                    uploaded = await _upload_bytes_to_freeimage_hook(img_bytes, "ref.jpg")
                    if not uploaded:
                        uploaded = await _upload_bytes_to_catbox_hook(img_bytes, "ref.jpg")
                    if uploaded:
                        http_image_urls.append(uploaded)
                    else:
                        logger.warning("fal.ai: catbox upload failed for data: ref, skipping")
                except Exception:
                    logger.exception("fal.ai: failed to upload data: ref to catbox, skipping")
            else:
                http_image_urls.append(url)
        if http_image_urls:
            payload["image_urls"] = http_image_urls
    submit_url = f"{FAL_API_BASE.rstrip('/')}/{model_path}"
    headers = {
        "Authorization": f"Key {FAL_API_KEY}",
        "Content-Type": "application/json",
    }
    logger.info(
        "fal.ai Seedance submit: url=%s model=%s duration=%s refs=%s",
        submit_url, model_path, duration, len(combined_image_urls),
    )
    async with aiohttp.ClientSession() as session:
        async with session.post(
            submit_url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            response_text = await resp.text()
            logger.info("fal.ai Seedance submit response: status=%s body=%s", resp.status, response_text[:500])
            if not (200 <= resp.status < 300):
                raise Exception(f"fal.ai Seedance submit failed: {resp.status}. {response_text[:300]}")
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                raise Exception(f"fal.ai Seedance: non-JSON response: {response_text[:200]}")
            request_id = data.get("request_id")
            status_url = data.get("status_url") or ""
            response_url = data.get("response_url") or ""
            if not request_id:
                raise Exception(f"fal.ai Seedance: request_id missing: {data}")
            # Build fallback URLs if fal.ai doesn't return them
            base = FAL_API_BASE.rstrip("/")
            if not status_url:
                status_url = f"{base}/{model_path}/requests/{request_id}/status"
            if not response_url:
                response_url = f"{base}/{model_path}/requests/{request_id}"
            logger.info(
                "fal.ai Seedance queued: request_id=%s status_url=%s response_url=%s",
                request_id, status_url, response_url,
            )
            # Use | as separator since URLs contain colons
            return f"__FAL__|{status_url}|{response_url}"


async def _poll_seedance_fal(
    status_url: str,
    response_url: str,
    max_attempts: int,
    poll_interval: int,
    status_callback=None,
) -> str:
    """Poll fal.ai queue for Seedance 2.0 result."""
    result_url = response_url
    headers = {"Authorization": f"Key {FAL_API_KEY}"}
    logger.info(
        "fal.ai Seedance polling: status_url=%s max_attempts=%s interval=%ss",
        status_url, max_attempts, poll_interval,
    )
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_attempts):
            if status_callback and attempt > 0 and attempt % 8 == 0:
                elapsed_min = (attempt * poll_interval) // 60
                try:
                    await status_callback(f"⏳ Генерация видео... прошло ~{elapsed_min} мин.")
                except Exception:
                    pass
            await asyncio.sleep(poll_interval)
            logger.info("fal.ai poll tick: attempt=%s/%s", attempt + 1, max_attempts)
            try:
                async with session.get(
                    status_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        logger.warning("fal.ai status check failed: %s body=%s", resp.status, body[:200])
                        continue
                    data = json.loads(body)
            except Exception as e:
                logger.warning("fal.ai status request error: %s", e)
                continue
            status = str(data.get("status", "")).upper()
            logger.info("fal.ai task status=%s url=%s", status, status_url)
            if status == "COMPLETED":
                try:
                    async with session.get(
                        result_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as res:
                        result_data = json.loads(await res.text())
                except Exception as e:
                    raise Exception(f"fal.ai result fetch error: {e}")
                video = result_data.get("video") or {}
                video_url = video.get("url") if isinstance(video, dict) else None
                if not video_url:
                    raise Exception(f"fal.ai Seedance: video URL missing in result: {result_data}")
                logger.info("fal.ai Seedance completed: %s", video_url)
                return video_url
            if status in ("FAILED", "ERROR"):
                error_msg = (
                    data.get("error")
                    or data.get("detail")
                    or f"fal.ai task failed with status {status}"
                )
                raise Exception(str(error_msg))
    raise Exception("Превышено время ожидания генерации видео (fal.ai)")


async def poll_seedance_task(
    task_id: str,
    max_attempts: int,
    poll_interval: int,
    expected_refs_count: int = 0,
    status_callback=None,
) -> str:
    # fal.ai task — delegate to fal.ai poller
    if task_id.startswith("__FAL__|"):
        parts = task_id.split("|", 3)
        fal_status_url = parts[1] if len(parts) > 1 else ""
        fal_response_url = parts[2] if len(parts) > 2 else ""
        return await _poll_seedance_fal(fal_status_url, fal_response_url, max_attempts, poll_interval, status_callback)

    if task_id.startswith("__EVOLINK__:"):
        raw_task_id = task_id.split("__EVOLINK__:", 1)[1].strip()
        return await poll_evolink_task(raw_task_id, max_attempts, poll_interval, status_callback)

    if not ZVENO_API_KEY:
        raise Exception("ZVENO_API_KEY is empty")

    poll_urls = []
    if task_id.startswith("__POLL_URL__:"):
        raw_poll_url = task_id.split("__POLL_URL__:", 1)[1].strip()
        if raw_poll_url.startswith("http://") or raw_poll_url.startswith("https://"):
            poll_urls = [raw_poll_url]
        else:
            poll_urls = [build_zveno_url(ZVENO_API_BASE, raw_poll_url)]
    else:
        poll_paths = [
            f"/v1/tasks/{task_id}",
            f"/tasks/{task_id}",
            f"/api/v1/tasks/{task_id}",
        ]
        poll_urls = [build_zveno_url(ZVENO_API_BASE, path) for path in poll_paths]

    logger.info(
        f"Video polling started: task_ref={task_id}, max_attempts={max_attempts}, interval={poll_interval}s, urls={poll_urls}"
    )

    content_probe_urls: List[str] = []
    for poll_url in poll_urls:
        normalized = poll_url.strip()
        if not normalized:
            continue
        if normalized.endswith("/content"):
            if normalized not in content_probe_urls:
                content_probe_urls.append(normalized)
            continue
        if "/v1/videos/" in normalized:
            candidate = normalized.rstrip("/") + "/content"
            if candidate not in content_probe_urls:
                content_probe_urls.append(candidate)

    def _extract_video_url_from_task(task_data: dict) -> Optional[str]:
        video_url = None
        unsigned_urls = task_data.get("unsigned_urls")
        if isinstance(unsigned_urls, list):
            for item in unsigned_urls:
                if isinstance(item, str) and item.startswith("http"):
                    video_url = item
                    break
        if not video_url:
            video_url = extract_task_video_url(task_data)
        return video_url

    async def _probe_content_url(session: aiohttp.ClientSession, url: str) -> bool:
        headers = {
            "x-api-key": ZVENO_API_KEY,
            "Authorization": f"Bearer {ZVENO_API_KEY}",
        }
        try:
            async with session.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    return False
                content_type = (resp.headers.get("Content-Type") or "").lower()
                if content_type.startswith("video/") or "octet-stream" in content_type:
                    return True
                # Fallback: if status is 200 and body is non-empty, treat as ready content.
                body = await resp.read()
                return bool(body)
        except Exception:
            return False

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_attempts):
            logger.info(f"Video poll tick: attempt={attempt + 1}/{max_attempts}")
            if status_callback and attempt > 0 and attempt % 8 == 0:
                elapsed_min = (attempt * poll_interval) // 60
                try:
                    await status_callback(f"⏳ Генерация видео... прошло ~{elapsed_min} мин.")
                except Exception:
                    pass
            await asyncio.sleep(poll_interval)

            data = None
            for poll_url in poll_urls:
                headers_variants = [
                    {
                        "x-api-key": ZVENO_API_KEY,
                        "Authorization": f"Bearer {ZVENO_API_KEY}",
                    },
                    None,
                ]
                for headers in headers_variants:
                    async with session.get(
                        poll_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as resp:
                        response_text = await resp.text()
                        if resp.status != 200:
                            logger.warning(
                                f"Video status check failed: {resp.status}, url={poll_url}, auth={'yes' if headers else 'no'}, body={response_text}"
                            )
                            continue
                        try:
                            data = json.loads(response_text)
                            break
                        except json.JSONDecodeError:
                            logger.warning(f"Video status non-JSON response: {response_text}")
                            continue
                if data:
                    break

            if not data:
                continue

            status_raw = str(data.get("status", ""))
            status = status_raw.upper()
            logger.info(f"Video task {task_id}: attempt={attempt + 1}/{max_attempts}, status={status}")

            task_id_from_data = str(data.get("id") or "").strip()
            if task_id_from_data.startswith("vj_"):
                candidate = build_zveno_url(ZVENO_API_BASE, f"/v1/videos/{task_id_from_data}/content")
                if candidate not in content_probe_urls:
                    content_probe_urls.append(candidate)

            video_url_any_status = _extract_video_url_from_task(data)
            if video_url_any_status and status not in ("FAILED", "CANCELLED", "ERROR"):
                logger.info(
                    "Video poll early-finish: video url is already available at status=%s",
                    status or "unknown",
                )
                return video_url_any_status

            if status in ("IN_PROGRESS", "PROCESSING", "PENDING", ""):
                # Some providers keep status stale while content is already downloadable.
                if attempt >= 6 and (attempt % 2 == 0):
                    for probe_url in content_probe_urls:
                        ready = await _probe_content_url(session, probe_url)
                        if ready:
                            logger.info(
                                "Video content probe ready: status=%s, url=%s",
                                status or "unknown",
                                probe_url,
                            )
                            return probe_url

            if status in ("COMPLETED", "SUCCEEDED", "DONE", "FINISHED", "SUCCESS"):
                if expected_refs_count > 1:
                    accepted_refs = extract_task_reference_count(data)
                    # Some providers do not echo reference fields in poll responses.
                    # Fail only when provider explicitly reports fewer refs than expected.
                    if accepted_refs > 0 and accepted_refs < expected_refs_count:
                        raise Exception(
                            f"Референсы применились не полностью: ожидалось {expected_refs_count}, подтверждено {accepted_refs}."
                        )
                video_url = _extract_video_url_from_task(data)
                if not video_url:
                    raise Exception(f"Video task completed but video URL missing: {data}")
                return video_url

            if status in ("FAILED", "CANCELLED", "ERROR"):
                # Provider can report FAILED due to internal polling timeout while
                # content is already available. Probe content once more before hard fail.
                for probe_url in content_probe_urls:
                    ready = await _probe_content_url(session, probe_url)
                    if ready:
                        logger.info(
                            "Video failed status but content is ready: status=%s, url=%s",
                            status,
                            probe_url,
                        )
                        return probe_url
                raise Exception(
                    data.get("error")
                    or data.get("message")
                    or data.get("details")
                    or f"Video task failed with status {status}"
                )

    raise Exception("Превышено время ожидания генерации видео Seedance")
