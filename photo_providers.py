"""HTTP-клиенты фото-провайдеров (Zveno, MashaGPT).

Вынесено из SirNike.py (generate_image_by_job) в рамках фазы 2 разбора
монолита (см. docs/briefs/backend.md, фаза 1 — video_providers.py, тот же
паттерн). Чисто структурный рефакторинг — поведение не менялось.

YesAPI/Nano Banana 2 (дефолтная ветка generate_image_by_job, когда
AI_PROVIDER не ZVENO и не MASHAGPT) намеренно ОСТАВЛЕНА в SirNike.py и
НЕ вынесена сюда: в отличие от Zveno/MashaGPT (запрос -> чистый image_url
-> общий success-путь в SirNike.py), YesAPI-ветка не возвращает "чистый"
результат — у неё свой внешний 2-попыточный retry с промежуточными
Telegram-сообщениями пользователю ("Сервис генерации дал сбой... Пробую
ещё раз"), собственная JPEG-конвертация байт и прямая отправка через
app.bot.send_photo/send_document в обход общего send_generation_result_by_url
(другой caption, другая клавиатура, дополнительный send_document с файлом).
Вынос провайдер-клиента отдельно от этой Telegram-логики потребовал бы
либо тащить наружу байты через новый контракт, которого нет у двух других
провайдеров, либо разрывать retry-цикл с сообщениями пользователю на две
половины — в обоих случаях код стал бы сложнее читать, чем сейчас, без
структурной выгоды. Решение: оставить как есть.

Как и video_providers.py: модуль не импортирует SirNike.py (иначе
циклический импорт). Недостающие бот-уровневые зависимости (резолв
__img__-рефов из in-memory кэша фото, запись новой картинки в этот кэш)
прокинуты через configure(...), вызываемый из SirNike.py один раз при
импорте, сразу после того как нужные хелперы там определены.

MASHAGPT_API_KEY читается через геттер-хук (не голая константа) — так
тест `S.MASHAGPT_API_KEY = "..."` (переприсваивание имени в namespace
SirNike.py) продолжает работать: дефолтный геттер читает config.py,
а SirNike.py через configure() подменяет его на lambda, резолвящую имя
в СВОЁМ модуле в момент вызова — ровно то место, которое тест патчит
(тот же трюк, что у _get_evolink_api_key_hook в video_providers.py).
"""

import asyncio
import base64
import json
import logging
import os
from typing import Callable, List, Optional

import aiohttp

from config import (
    ZVENO_API_BASE,
    ZVENO_API_KEY,
    ZVENO_IMAGE_MODEL,
    ZVENO_GPT5_IMAGE_MODEL,
    GPT5_IMAGE_ENABLED,
    MASHAGPT_API_BASE,
    MASHAGPT_API_KEY,
    MASHAGPT_IMAGE_MODEL,
    MAX_POLL_ATTEMPTS,
    POLL_INTERVAL,
    EVOLINK_IMAGE_MODEL,
    EVOLINK_IMAGE_QUALITY,
    EVOLINK_IMAGE_MAX_POLL_ATTEMPTS,
    EVOLINK_IMAGE_POLL_INTERVAL,
)
from video_providers import (
    build_zveno_url,
    build_mashagpt_url,
    _evolink_create_task,
    poll_evolink_task,
    _resolve_evolink_image_urls,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Инъекция бот-уровневых зависимостей (см. докстринг модуля)
# ----------------------------------------------------------------------------

def _default_is_img_ref(value: str) -> bool:
    return isinstance(value, str) and value.startswith("__img_") and value.endswith("__")


def _default_ref_to_data_url(_ref: str) -> Optional[str]:
    return None


def _default_cache_image(_image_bytes: bytes) -> str:
    # Заглушка до первого configure() не должна случаться в проде (SirNike.py
    # вызывает configure() при импорте) — но на всякий случай не роняем процесс,
    # просто теряем возможность закэшировать inline-байты.
    return ""


_is_img_ref_hook: Callable[[str], bool] = _default_is_img_ref
_ref_to_data_url_hook: Callable[[str], Optional[str]] = _default_ref_to_data_url
_cache_image_hook: Callable[[bytes], str] = _default_cache_image
_get_mashagpt_api_key_hook: Callable[[], str] = lambda: MASHAGPT_API_KEY


def configure(
    *,
    is_img_ref: Optional[Callable[[str], bool]] = None,
    ref_to_data_url: Optional[Callable[[str], Optional[str]]] = None,
    cache_image: Optional[Callable[[bytes], str]] = None,
    get_mashagpt_api_key: Optional[Callable[[], str]] = None,
) -> None:
    """Вызывается из SirNike.py один раз при импорте — прокидывает сюда
    бот-уровневые хелперы (кэш загруженных фото), которые сами по себе не
    провайдер-специфичны и остаются в SirNike.py."""
    global _is_img_ref_hook, _ref_to_data_url_hook, _cache_image_hook, _get_mashagpt_api_key_hook
    if is_img_ref is not None:
        _is_img_ref_hook = is_img_ref
    if ref_to_data_url is not None:
        _ref_to_data_url_hook = ref_to_data_url
    if cache_image is not None:
        _cache_image_hook = cache_image
    if get_mashagpt_api_key is not None:
        _get_mashagpt_api_key_hook = get_mashagpt_api_key


def _is_image_url_like(value: str) -> bool:
    if not isinstance(value, str):
        return False
    raw = value.strip()
    return raw.startswith("http://") or raw.startswith("https://") or raw.startswith("data:image") or _is_img_ref_hook(raw)


# ----------------------------------------------------------------------------
# Zveno — основной фото-провайдер (Gemini/GPT-5-image через chat/completions)
# ----------------------------------------------------------------------------

async def generate_image_zveno(
    prompt: str,
    references: Optional[List[str]],
    user_id: int,
    image_model: str = "gemini",
) -> str:
    """Возвращает готовый image_url (http(s)/data: URL или __img_xxx__ ref
    на закэшированные байты) либо бросает Exception с тем же текстом, что и
    раньше (classify_generation_error/messaging завязаны на дословный текст)."""
    if not ZVENO_API_KEY:
        raise Exception("ZVENO_API_KEY is empty")

    def extract_zveno_image_url(response_data: dict) -> Optional[str]:
        choices = response_data.get("choices")
        if not isinstance(choices, list):
            return None

        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue

            images = message.get("images")
            if isinstance(images, list):
                for image_item in images:
                    if isinstance(image_item, dict):
                        url = image_item.get("url")
                        if isinstance(url, str):
                            url = url.strip()
                            if _is_image_url_like(url):
                                return url
                    elif isinstance(image_item, str):
                        image_item = image_item.strip()
                        if _is_image_url_like(image_item):
                            return image_item

            content = message.get("content")
            if isinstance(content, str) and content.strip():
                content = content.strip()
                if _is_image_url_like(content):
                    return content
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    image_url = part.get("image_url")
                    if isinstance(image_url, dict):
                        url = image_url.get("url")
                        if isinstance(url, str):
                            url = url.strip()
                            if _is_image_url_like(url):
                                return url
                    elif isinstance(image_url, str):
                        image_url = image_url.strip()
                        if _is_image_url_like(image_url):
                            return image_url
                    url = part.get("url")
                    if isinstance(url, str):
                        url = url.strip()
                        if _is_image_url_like(url):
                            return url
        return None

    def extract_zveno_image_bytes(response_data: dict) -> Optional[bytes]:
        choices = response_data.get("choices")
        if not isinstance(choices, list):
            return None

        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue

            images = message.get("images")
            if isinstance(images, list):
                for image_item in images:
                    if isinstance(image_item, dict):
                        url = image_item.get("url")
                        if isinstance(url, str) and url.startswith("data:image"):
                            comma_idx = url.find(",")
                            if comma_idx != -1:
                                try:
                                    return base64.b64decode(url[comma_idx + 1:])
                                except Exception:
                                    continue
                    elif isinstance(image_item, str) and image_item.startswith("data:image"):
                        comma_idx = image_item.find(",")
                        if comma_idx != -1:
                            try:
                                return base64.b64decode(image_item[comma_idx + 1:])
                            except Exception:
                                continue

            content = message.get("content")
            parts = content if isinstance(content, list) else []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                b64 = part.get("b64_json") or part.get("data")
                if isinstance(b64, str) and b64:
                    if b64.startswith("data:image"):
                        comma_idx = b64.find(",")
                        if comma_idx != -1:
                            b64 = b64[comma_idx + 1:]
                    try:
                        return base64.b64decode(b64)
                    except Exception:
                        continue
        return None

    def extract_zveno_error_text(response_data: dict) -> str:
        error = response_data.get("error")
        if isinstance(error, dict):
            msg = error.get("message") or error.get("details") or error.get("code")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()

        choices = response_data.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                native_finish_reason = choice.get("native_finish_reason")
                if isinstance(native_finish_reason, str) and native_finish_reason.strip():
                    native_code = native_finish_reason.strip().upper()
                    if "IMAGE_PROHIBITED_CONTENT" in native_code:
                        return (
                            "Запрос отклонён фильтром безопасности модели "
                            "(IMAGE_PROHIBITED_CONTENT). "
                            "Измени описание и/или замени фото."
                        )
                    if "PROHIBITED" in native_code or "SAFETY" in native_code or "BLOCK" in native_code:
                        return (
                            "Запрос отклонён фильтром безопасности модели. "
                            "Измени описание или фото и попробуй снова."
                        )
                message = choice.get("message")
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict):
                            text = part.get("text")
                            if isinstance(text, str) and text.strip():
                                text_parts.append(text.strip())
                    if text_parts:
                        return " ".join(text_parts)

        compact = json.dumps(response_data, ensure_ascii=False)
        if len(compact) > 500:
            compact = compact[:500] + "..."
        return f"Zveno response without image URL. {compact}"

    def extract_zveno_finish_reason(response_data: dict) -> str:
        choices = response_data.get("choices")
        if not isinstance(choices, list):
            return "unknown"
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            value = (
                choice.get("finish_reason")
                or choice.get("native_finish_reason")
                or choice.get("finishReason")
            )
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "unknown"

    def extract_zveno_native_finish_reason(response_data: dict) -> str:
        choices = response_data.get("choices")
        if not isinstance(choices, list):
            return "unknown"
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            value = choice.get("native_finish_reason") or choice.get("nativeFinishReason")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "unknown"

    user_content = []
    if prompt and prompt.strip():
        user_content.append({"type": "text", "text": prompt})
    for ref_url in (references or [])[:8]:
        if not isinstance(ref_url, str):
            continue
        resolved = _ref_to_data_url_hook(ref_url) if _is_img_ref_hook(ref_url) else ref_url
        if resolved and (resolved.startswith("http") or resolved.startswith("data:")):
            user_content.append({"type": "image_url", "image_url": {"url": resolved}})

    zveno_image_model = (
        ZVENO_GPT5_IMAGE_MODEL
        if image_model == "gpt5" and GPT5_IMAGE_ENABLED
        else ZVENO_IMAGE_MODEL
    )

    base_payload = {
        "model": zveno_image_model,
        "messages": [
            {
                "role": "user",
                "content": user_content if user_content else prompt,
            }
        ],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": "9:16"},
    }
    fallback_payload = {
        "model": zveno_image_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Generate exactly one image result. "
                    "Do not return reasoning-only output."
                ),
            },
            {
                "role": "user",
                "content": user_content if user_content else prompt,
            },
        ],
        "modalities": ["image"],
        "image_config": {"aspect_ratio": "9:16"},
        "max_completion_tokens": 512,
        "temperature": 0.2,
    }
    strict_payload = {
        "model": zveno_image_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Generate exactly one final image. "
                    "Return only image output."
                ),
            },
            {
                "role": "user",
                "content": user_content if user_content else prompt,
            },
        ],
        "modalities": ["image"],
        "image_config": {"aspect_ratio": "9:16"},
        # 256 токенов душило reasoning-модели: они тратят бюджет на
        # внутренние "раздумья" ДО картинки и обрывались на середине
        # рассуждения, так и не дойдя до image-вывода (см. AGENT_NOTES,
        # gemini-3-pro-image-preview, 2026-07-12). 1024 оставляет запас
        # на reasoning + сам результат.
        "max_completion_tokens": 1024,
        "temperature": 0,
        "reasoning_effort": "low",
    }
    payload_variants = [base_payload, fallback_payload, strict_payload]

    fallback_model = os.getenv("ZVENO_IMAGE_FALLBACK_MODEL", "google/gemini-3-pro-image-preview").strip()
    if fallback_model and fallback_model != zveno_image_model:
        payload_variants.append(
            {
                "model": fallback_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Generate exactly one final image. "
                            "Return only image output."
                        ),
                    },
                    {
                        "role": "user",
                        "content": user_content if user_content else prompt,
                    },
                ],
                "modalities": ["image"],
                "image_config": {"aspect_ratio": "9:16"},
                # Тот же фикс, что и strict_payload — этой модели реально
                # не хватало 256 токенов на reasoning + картинку.
                "max_completion_tokens": 1024,
                "temperature": 0,
                "reasoning_effort": "low",
            }
        )

    request_url = build_zveno_url(ZVENO_API_BASE, "/v1/chat/completions")
    logger.info("Zveno image start: user=%s refs=%s endpoint=%s model=%s", user_id, len(references or []), request_url, zveno_image_model)

    response_data = None
    image_url = None
    blocked_models: set = set()
    moderation_blocked = False
    async with aiohttp.ClientSession() as session:
        for attempt_idx, payload in enumerate(payload_variants, start=1):
            if payload.get("model") in blocked_models:
                continue
            async with session.post(
                request_url,
                headers={
                    "Authorization": f"Bearer {ZVENO_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                response_text = await resp.text()
                logger.info("Zveno image response: status=%s attempt=%s/%s", resp.status, attempt_idx, len(payload_variants))
                if not (200 <= resp.status < 300):
                    if attempt_idx < len(payload_variants):
                        logger.warning(
                            "Zveno image attempt %s/%s rejected: status=%s body=%s — trying next variant",
                            attempt_idx, len(payload_variants), resp.status, response_text[:300],
                        )
                        await asyncio.sleep(0.7)
                        continue
                    raise Exception(f"Zveno image error: {resp.status}. {response_text}")
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    raise Exception(f"Zveno non-JSON response: {response_text}")

            image_url = extract_zveno_image_url(response_data)
            if image_url and image_url.startswith("data:image"):
                try:
                    comma_idx = image_url.find(",")
                    raw_bytes = base64.b64decode(image_url[comma_idx + 1:]) if comma_idx != -1 else None
                    if raw_bytes:
                        image_url = _cache_image_hook(raw_bytes)
                except Exception:
                    image_url = None
            if not image_url:
                image_bytes_direct = extract_zveno_image_bytes(response_data)
                if image_bytes_direct:
                    image_url = _cache_image_hook(image_bytes_direct)
            if image_url:
                break

            finish_reason = extract_zveno_finish_reason(response_data)
            native_finish_reason = extract_zveno_native_finish_reason(response_data)
            msg_diag = {}
            try:
                choices = response_data.get("choices")
                if isinstance(choices, list) and choices:
                    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                    if isinstance(msg, dict):
                        images = msg.get("images")
                        msg_diag = {
                            "images_type": type(images).__name__,
                            "images_len": len(images) if isinstance(images, list) else -1,
                            "content_type": type(msg.get("content")).__name__,
                            "has_reasoning_details": isinstance(msg.get("reasoning_details"), list) and len(msg.get("reasoning_details")) > 0,
                        }
            except Exception:
                msg_diag = {}
            logger.warning(
                "Zveno image attempt %s/%s returned no image (finish_reason=%s, native_finish_reason=%s, model=%s, diag=%s)",
                attempt_idx,
                len(payload_variants),
                finish_reason,
                native_finish_reason,
                payload.get("model"),
                msg_diag,
            )
            native_upper = native_finish_reason.upper() if isinstance(native_finish_reason, str) else ""
            if "IMAGE_PROHIBITED_CONTENT" in native_upper:
                # Контент-фильтр: повторять ту же модель бессмысленно, но
                # fallback-модель (Pro) часто пропускает то, что флагает flash.
                blocked_models.add(payload.get("model"))
                # Запоминаем факт блокировки — иначе если fallback-модель
                # потом молча откажет БЕЗ явного кода (finish_reason=stop,
                # пустой content, как у gemini-3-pro-image-preview), итоговая
                # ошибка потеряет настоящую причину и покажет бесполезное
                # "Zveno response without image URL" вместо "фильтр
                # безопасности отклонил фото/промт".
                moderation_blocked = True
                continue
            if attempt_idx < len(payload_variants):
                await asyncio.sleep(0.7)
    if not image_url:
        if moderation_blocked:
            # Формулировка специально содержит "content_filter" — под это
            # ключевое слово classify_generation_error() заводит событие в
            # категорию moderation в статистике (см. log_generation_event в
            # SirNike.py).
            raise Exception(
                "Запрос отклонён фильтром безопасности модели "
                "(content_filter/IMAGE_PROHIBITED_CONTENT). "
                "Измени описание и/или замени фото."
            )
        raise Exception(extract_zveno_error_text(response_data))

    logger.info("Zveno image success: user=%s image_ref=%s", user_id, str(image_url)[:60])
    return image_url


# ----------------------------------------------------------------------------
# EvoLink — Nano Banana 2 (гибридная миграция 2026-08-25, см. комментарий
# PHOTO_PROVIDER в config.py). GPT-5 Image остаётся на Zveno — эта функция
# только для обычной модели.
# ----------------------------------------------------------------------------

async def generate_image_evolink(
    prompt: str,
    references: Optional[List[str]],
    user_id: int,
) -> str:
    """Nano Banana 2 через EvoLink — снаружи тот же контракт, что у
    generate_image_zveno (await -> готовый image_url либо Exception), но
    сам EvoLink асинхронный (create задачи -> поллинг), в отличие от
    синхронного chat/completions у Zveno — create+poll сведены в один вызов,
    вызывающему коду (generate_image_by_job) без разницы, какой провайдер.
    Референсы — тот же резолвер __img__ -> data: URL, что уже используют
    Seedance/Gemini Omni (video_providers._resolve_evolink_image_urls)."""
    prompt_clean = (prompt or "").strip()
    if not prompt_clean:
        raise Exception("EvoLink Nano Banana 2: пустой промт")
    image_urls = _resolve_evolink_image_urls(None, references, 8)
    payload = {
        "model": EVOLINK_IMAGE_MODEL,
        "prompt": prompt_clean[:8192],
        "quality": EVOLINK_IMAGE_QUALITY,
    }
    if image_urls:
        payload["image_urls"] = image_urls
    raw_task_id = await _evolink_create_task(
        payload, "EvoLink Nano Banana 2", user_id, endpoint_path="/v1/images/generations",
    )
    task_id = raw_task_id.split(":", 1)[1] if raw_task_id.startswith("__EVOLINK__:") else raw_task_id
    image_url = await poll_evolink_task(task_id, EVOLINK_IMAGE_MAX_POLL_ATTEMPTS, EVOLINK_IMAGE_POLL_INTERVAL)
    logger.info("EvoLink Nano Banana 2 image success: user=%s image_url=%s", user_id, str(image_url)[:80])
    return image_url


# ----------------------------------------------------------------------------
# MashaGPT — фото-провайдер (create+poll задачи)
# ----------------------------------------------------------------------------

async def generate_image_mashagpt(
    prompt: str,
    references: Optional[List[str]],
    user_id: int,
) -> str:
    """Возвращает готовый image_url либо бросает Exception с тем же текстом,
    что и раньше (см. докстринг generate_image_zveno)."""
    api_key = _get_mashagpt_api_key_hook()
    if not api_key:
        raise Exception("MASHAGPT_API_KEY is empty")

    def extract_mashagpt_image_url(task_data: dict) -> Optional[str]:
        output = task_data.get("output")
        top_level_candidates = ("url", "imageUrl", "image_url", "resultUrl", "result_url")
        for key in top_level_candidates:
            value = task_data.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value

        if isinstance(output, str) and output.startswith("http"):
            return output

        if isinstance(output, dict):
            for key in top_level_candidates:
                value = output.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value

            images = output.get("images")
            if isinstance(images, list):
                for item in images:
                    if isinstance(item, str) and item.startswith("http"):
                        return item
                    if isinstance(item, dict):
                        for key in ("url", "imageUrl", "image_url"):
                            value = item.get(key)
                            if isinstance(value, str) and value.startswith("http"):
                                return value

        if isinstance(output, list):
            for item in output:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    for key in top_level_candidates:
                        value = item.get(key)
                        if isinstance(value, str) and value.startswith("http"):
                            return value

        return None

    def extract_mashagpt_error_text(task_data: dict, status: str) -> str:
        candidates = []
        for key in ("message", "error", "details", "reason", "errorMessage"):
            value = task_data.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
            elif isinstance(value, dict):
                nested = value.get("message") or value.get("error") or value.get("details")
                if isinstance(nested, str) and nested.strip():
                    candidates.append(nested.strip())
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        candidates.append(item.strip())
                    elif isinstance(item, dict):
                        nested = item.get("message") or item.get("error") or item.get("details")
                        if isinstance(nested, str) and nested.strip():
                            candidates.append(nested.strip())

        output = task_data.get("output")
        if isinstance(output, dict):
            for key in ("message", "error", "details", "reason"):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())

        seen = set()
        uniq = []
        for item in candidates:
            if item not in seen:
                seen.add(item)
                uniq.append(item)

        if uniq:
            return " | ".join(uniq)

        compact = json.dumps(task_data, ensure_ascii=False)
        if len(compact) > 500:
            compact = compact[:500] + "..."
        return f"MashaGPT task failed with status {status}. Response: {compact}"

    safe_prompt = (prompt or "").encode("utf-8", errors="replace").decode("utf-8")
    payload = {
        "prompt": safe_prompt,
        "resolution": "1K",
        "aspectRatio": "9:16",
        "outputFormat": "jpg",
    }
    if references:
        resolved_refs = [
            _ref_to_data_url_hook(r) if _is_img_ref_hook(r) else r for r in references[:8]
        ]
        payload["imageUrls"] = [r for r in resolved_refs if r]
    create_paths = [
        f"/v1/tasks/{MASHAGPT_IMAGE_MODEL}",
        f"/tasks/{MASHAGPT_IMAGE_MODEL}",
    ]
    create_urls = [build_mashagpt_url(MASHAGPT_API_BASE, p) for p in create_paths]
    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    async with aiohttp.ClientSession() as session:
        task_data = None
        create_errors = []
        for create_url in create_urls:
            logger.info(f"MashaGPT create task endpoint: {create_url}")
            async with session.post(
                create_url,
                headers={
                    "x-api-key": api_key,
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                data=request_body,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                response_text = await resp.text()
                if not (200 <= resp.status < 300):
                    create_errors.append(f"url={create_url} status={resp.status} body={response_text}")
                    continue

                try:
                    task_data = json.loads(response_text)
                    break
                except json.JSONDecodeError:
                    create_errors.append(f"url={create_url} status={resp.status} non-json={response_text}")
                    continue

        if not task_data:
            raise Exception("MashaGPT create task error. " + " || ".join(create_errors))

        task_id = task_data.get("id")
        if not task_id:
            raise Exception(f"MashaGPT did not return task id: {task_data}")

        poll_paths = [
            f"/v1/tasks/{task_id}",
            f"/tasks/{task_id}",
        ]
        poll_urls = [build_mashagpt_url(MASHAGPT_API_BASE, p) for p in poll_paths]
        poll_attempts = max(MAX_POLL_ATTEMPTS, 40)
        poll_interval = min(max(POLL_INTERVAL, 5), 15)

        for attempt in range(poll_attempts):
            await asyncio.sleep(poll_interval)
            try:
                status_data = None
                for poll_url in poll_urls:
                    async with session.get(
                        poll_url,
                        headers={
                            "x-api-key": api_key,
                            "Authorization": f"Bearer {api_key}",
                        },
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as status_resp:
                        status_text = await status_resp.text()
                        if status_resp.status != 200:
                            logger.warning(
                                f"MashaGPT task status check failed ({attempt + 1}/{poll_attempts}): "
                                f"url={poll_url} status={status_resp.status} body={status_text}"
                            )
                            continue

                        try:
                            status_data = json.loads(status_text)
                            break
                        except json.JSONDecodeError:
                            logger.warning(
                                f"MashaGPT task status non-JSON response ({attempt + 1}/{poll_attempts}) "
                                f"url={poll_url}: {status_text}"
                            )
                            continue

                if not status_data:
                    continue

                status = str(status_data.get("status", "")).upper()
                logger.info(
                    f"MashaGPT task {task_id}: attempt={attempt + 1}/{poll_attempts}, status={status}"
                )

                if status == "COMPLETED":
                    image_url = extract_mashagpt_image_url(status_data)
                    if not image_url:
                        raise Exception(f"MashaGPT task completed but image url not found: {status_data}")
                    return image_url

                if status in ("FAILED", "CANCELLED", "ERROR"):
                    error_text = extract_mashagpt_error_text(status_data, status)
                    raise Exception(str(error_text))
            except asyncio.TimeoutError:
                logger.warning(
                    f"MashaGPT task status timeout ({attempt + 1}/{poll_attempts}) for task_id={task_id}"
                )
                continue

        raise Exception("MashaGPT task polling timeout")
