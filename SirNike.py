import asyncio
import base64
import collections as _collections
import io
import json
import logging
import os
import re
import time
from logging.handlers import RotatingFileHandler
from datetime import datetime
from urllib.parse import urlsplit
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import aiohttp
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.ext import ApplicationHandlerStop, PreCheckoutQueryHandler
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    LabeledPrice,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.error import BadRequest, Forbidden, RetryAfter

from config import (
    TOKEN,
    AI_PROVIDER,
    NANO_API_BASE,
    NANO_API_KEY,
    MASHAGPT_API_BASE,
    MASHAGPT_API_KEY,
    MASHAGPT_IMAGE_MODEL,
    ZVENO_API_BASE,
    ZVENO_API_KEY,
    ZVENO_IMAGE_MODEL,
    ZVENO_CHAT_MODEL,
    PROMPT_WEBAPP_URL,
    PROMPT_LIBRARY_REMOTE_URL,
    REMOVE_BG_API_KEY,
    PHOTOROOM_API_KEY,
    FAPIHUB_API_KEY,
    CLIPDROP_API_KEY,
    REMBG_LOCAL_ENABLED,
    FAL_API_KEY,
    FAL_API_BASE,
    IMGBB_API_KEY,
    START_BONUS,
    FREE_GENERATIONS_PER_DAY,
    BASE_GENERATION_COST,
    REFERENCE_COST,
    MAX_POLL_ATTEMPTS,
    POLL_INTERVAL,
    ADMIN_IDS,
    RESULTS_CHANNEL_ID,
    TEST_MODE,
    REFERRAL_BONUS_REFERRER,
    REFERRAL_BONUS_NEW_USER,
    BUY_PACKS,
    PROVIDER_TOKEN,
    KLING_MOTION_ENDPOINT,
    KLING_MOTION_COST,
    KLING_MOTION_MODE,
    KLING_MOTION_ORIENTATION,
    KLING_MOTION_DURATION,
    KLING_MOTION_MAX_POLL_ATTEMPTS,
    KLING_MOTION_POLL_INTERVAL,
    MOTION_CONTROL_ENABLED,
    SEEDANCE_ENDPOINT,
    SEEDANCE_MODEL,
    SEEDANCE_MODE,
    SEEDANCE_DURATION,
    SEEDANCE_DURATION_OPTIONS,
    SEEDANCE_FAST_DURATION_OPTIONS,
    SEEDANCE_COST_PER_SECOND,
    SEEDANCE_MAX_POLL_ATTEMPTS,
    SEEDANCE_POLL_INTERVAL,
    SEEDANCE_ATTEMPT_TIMEOUT_SECONDS,
    SEEDANCE_ENABLED,
    SEEDANCE_FAST_ENABLED,
    SEEDANCE_FAST_ENDPOINT,
    SEEDANCE_FAST_MODEL,
    SEEDANCE_FAST_MODE,
    SEEDANCE_FAST_COST_PER_SECOND,
    DATA_DIR,
    GITHUB_TOKEN,
    GITHUB_REPO,
    KLING3_ENABLED,
    KLING3_MODEL,
    KLING3_COST_PER_SECOND,
    KLING3_DURATION_OPTIONS,
    VEO31_ENABLED,
    VEO31_MODEL,
    VEO31_COST_PER_SECOND,
    VEO31_DURATION_OPTIONS,
    GPT5_IMAGE_ENABLED,
    ZVENO_GPT5_IMAGE_MODEL,
    GPT5_IMAGE_COST,
)

from db import (
    DB_NAME,
    SEED_DB_NAME,
    init_db,
    create_user_if_not_exists,
    get_balance,
    spend_izyminki,
    add_izyminki,
    get_free_info,
    use_free_generation,
    try_use_free_generation,
    has_referral_bonus,
    mark_referral_bonus,
    get_all_user_ids,
    create_promo_broadcast,
    get_promo_broadcast,
    register_promo_click,
    get_promo_stats,
    save_payment_once,
    set_avatar_url,
    get_avatar_url,
    get_avatar_urls,
    clear_avatar_url,
    purge_stale_avatar_refs,
    restore_free_generation,
    log_generation_event,
    count_success_image_generations,
    get_audience_overview,
    add_generation_history,
    get_generation_history,
    get_generation_history_item,
)

# ══════════════════════════════════════════════════════════════
# НАСТРОЙКА: пути, логи, константы
# ══════════════════════════════════════════════════════════════

BASE_DIR = os.path.dirname(__file__)
RUNTIME_DIR = DATA_DIR
OUTPUTS_DIR = os.path.join(RUNTIME_DIR, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
BUILD_ID = "2026-05-02-prompt-library-data-primary-v1"
BOT_START_TIME = datetime.now()
LOG_DIR = os.getenv("BOT_LOG_DIR", RUNTIME_DIR).strip() or RUNTIME_DIR
LOG_FILE_PATH = os.path.join(LOG_DIR, "bot.log")
LOG_FILE_ERROR: Optional[str] = None
PROMPT_WEBAPP_REV = os.getenv("PROMPT_WEBAPP_REV", "20260509v4").strip() or "20260509v4"

log_handlers = [logging.StreamHandler()]
try:
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    log_handlers.append(file_handler)
except Exception as e:
    # If file logging cannot be initialized, keep console logging alive.
    LOG_FILE_ERROR = str(e)

logging.basicConfig(
    level=logging.INFO,
    handlers=log_handlers,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# СОСТОЯНИЕ: глобальные переменные, кеш, модели данных
# ══════════════════════════════════════════════════════════════

photo_tasks = {}
photo_counts = {}
_IMAGE_CACHE_MAX_ENTRIES = 200
_IMAGE_CACHE_MAX_BYTES = 500 * 1024 * 1024  # 500 MB


class _BoundedImageCache:
    """LRU image cache capped by entry count and total bytes. Thread-safe for asyncio.to_thread use."""

    def __init__(self, max_entries: int, max_bytes: int) -> None:
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._data: "_collections.OrderedDict[str, bytes]" = _collections.OrderedDict()
        self._total_bytes = 0
        self._lock = __import__("threading").Lock()

    def __setitem__(self, key: str, value: bytes) -> None:
        with self._lock:
            if len(value) > self._max_bytes:
                logger.warning("Image too large for cache (%d bytes), skipping", len(value))
                return
            if key in self._data:
                self._total_bytes -= len(self._data[key])
                del self._data[key]
            self._data[key] = value
            self._total_bytes += len(value)
            self._evict()

    def __getitem__(self, key: str) -> bytes:
        with self._lock:
            self._data.move_to_end(key)
            return self._data[key]

    def get(self, key: str, default: Optional[bytes] = None) -> Optional[bytes]:
        with self._lock:
            if key not in self._data:
                return default
            self._data.move_to_end(key)
            return self._data[key]

    def _evict(self) -> None:
        while (len(self._data) > self._max_entries or self._total_bytes > self._max_bytes) and self._data:
            _, evicted = self._data.popitem(last=False)
            self._total_bytes -= len(evicted)


_image_cache: _BoundedImageCache = _BoundedImageCache(_IMAGE_CACHE_MAX_ENTRIES, _IMAGE_CACHE_MAX_BYTES)

# Serialize local rembg: U2Net inference is ~500MB RAM each. Refs are processed
# in parallel (asyncio.gather), so without this 5 photos = 5 concurrent inferences
# and an OOM kill. Paid bg-removal APIs stay parallel (they're network-bound).
_rembg_semaphore = asyncio.Semaphore(1)

_LAST_GEN_MAX = 1000  # max users to keep in per-user generation caches

def _bounded_set(d: dict, key, value, max_size: int = _LAST_GEN_MAX) -> None:
    """Insert key→value into d, evicting oldest entry when full."""
    if key not in d and len(d) >= max_size:
        d.pop(next(iter(d)))
    d[key] = value

last_generated_image_url: "_collections.OrderedDict" = _collections.OrderedDict()
last_generated_prompt: "_collections.OrderedDict" = _collections.OrderedDict()
last_generation_references: "_collections.OrderedDict" = _collections.OrderedDict()
# Параметры последнего успешного видео — для воронки «Сделать длиннее» / апгрейда модели.
last_video_params: "_collections.OrderedDict" = _collections.OrderedDict()
MEDIA_GROUP_CACHE: "_collections.OrderedDict[Tuple[int, str], List[Dict[str, Any]]]" = _collections.OrderedDict()
MAX_CACHED_MEDIA_GROUPS = 300
_MEDIA_GROUP_LAST_TTL_CHECK: float = 0.0
MAX_MEDIA_GROUP_CHUNK_SIZE = 10
MAX_AVATAR_PHOTOS = 20
try:
    MAX_SEEDANCE_IMAGE_REFERENCES = max(
        1,
        min(9, int(os.getenv("SEEDANCE_MAX_IMAGE_REFERENCES", "9")))
    )
except Exception:
    MAX_SEEDANCE_IMAGE_REFERENCES = 9
# Seedance behavior mode:
# - "character": use input_references to preserve characters from photos
# - "timeline": use frame_images as first/last frame interpolation
SEEDANCE_VIDEO_REFERENCE_MODE = os.getenv("SEEDANCE_VIDEO_REFERENCE_MODE", "character").strip().lower()


@dataclass
class UserState:
    prompt: str = ""
    references: List[str] = field(default_factory=list)
    animation_source_url: Optional[str] = None
    animation_source_urls: List[str] = field(default_factory=list)
    waiting_for_avatar_upload: bool = False
    pending_avatar_kind: str = "female"
    generating_avatar: bool = False
    avatar_photos: List[str] = field(default_factory=list)
    avatar_status_msg_id: Optional[int] = None
    waiting_for_problem_report: bool = False
    video_prompt: str = ""
    motion_video_url: Optional[str] = None
    video_duration: Optional[int] = None
    video_mode: Optional[str] = None
    video_model: str = "seedance2_fast"
    video_aspect_ratio: str = "16:9"
    video_session_active: bool = False
    waiting_for_video_prompt: bool = False
    waiting_for_video_image: bool = False
    waiting_for_motion_video: bool = False
    image_model: str = "gemini"  # gemini | gpt5
    image_prompt: str = ""

@dataclass
class GenerationJob:
    chat_id: int
    user_id: int
    prompt: str
    references: List[str]
    message_id: Optional[int] = None
    cost: int = 0
    was_free: bool = False
    save_as_avatar: bool = False
    avatar_kind: str = "female"
    username: Optional[str] = None
    aspect_ratio: str = "16:9"
    image_model: str = "gemini"  # gemini | gpt5

generation_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
queued_user_ids = set()
processing_user_ids = set()
# Hard single-execution guard for run_seedance, independent of callers' pre-add
# of processing_user_ids. Guarantees only one run_seedance runs per user even if
# a future caller forgets the pre-create_task guard (prevents double charge).
_seedance_executing = set()
queue_worker_task = None

DEFAULT_PROMPT_LIBRARY = [
    {
        "title": "Портреты",
        "emoji": "🧑",
        "items": [
            {
                "title": "Кино-портрет",
                "prompt": "cinematic portrait, soft key light, shallow depth of field, high detail skin texture, editorial look, natural colors",
                "example_url": "https://source.unsplash.com/960x1280/?cinematic,portrait",
            },
            {
                "title": "Бьюти-глянец",
                "prompt": "beauty close-up portrait, glossy magazine style, clean background, premium retouch look, sharp eyes, studio lighting",
                "example_url": "https://source.unsplash.com/960x1280/?beauty,portrait",
            },
            {
                "title": "Street style",
                "prompt": "street fashion portrait, city background, dynamic composition, natural daylight, modern outfit, high contrast",
                "example_url": "https://source.unsplash.com/960x1280/?street,fashion",
            },
            {
                "title": "Черно-белая классика",
                "prompt": "black and white portrait, classic film grain, dramatic light and shadow, timeless photography style",
                "example_url": "https://source.unsplash.com/960x1280/?blackandwhite,portrait",
            },
        ],
    },
    {
        "title": "Для бизнеса",
        "emoji": "💼",
        "items": [
            {
                "title": "Деловой аватар",
                "prompt": "professional business headshot, neutral background, confident expression, clean style, studio quality",
                "example_url": "https://source.unsplash.com/960x1280/?business,headshot",
            },
            {
                "title": "Эксперт в кадре",
                "prompt": "expert portrait in modern office, premium corporate aesthetic, natural skin tone, sharp focus",
                "example_url": "https://source.unsplash.com/960x1280/?office,portrait",
            },
            {
                "title": "LinkedIn стиль",
                "prompt": "linkedin profile photo style, soft studio light, minimal background, trustworthy and friendly look",
                "example_url": "https://source.unsplash.com/960x1280/?linkedin,portrait",
            },
            {
                "title": "Премиум бренд",
                "prompt": "premium brand portrait, luxury minimalism, elegant wardrobe, clean composition, crisp details",
                "example_url": "https://source.unsplash.com/960x1280/?luxury,portrait",
            },
        ],
    },
    {
        "title": "Креатив",
        "emoji": "🎨",
        "items": [
            {
                "title": "Неон future",
                "prompt": "futuristic neon portrait, cyberpunk color palette, cinematic glow, high detail, bold mood",
                "example_url": "https://source.unsplash.com/960x1280/?neon,cyberpunk",
            },
            {
                "title": "Арт-постер",
                "prompt": "art poster style portrait, graphic composition, bold colors, modern typography vibe, gallery look",
                "example_url": "https://source.unsplash.com/960x1280/?art,poster",
            },
            {
                "title": "Fantasy образ",
                "prompt": "fantasy character portrait, magical atmosphere, detailed costume, soft volumetric light, epic style",
                "example_url": "https://source.unsplash.com/960x1280/?fantasy,portrait",
            },
            {
                "title": "Anime mood",
                "prompt": "anime-inspired portrait, clean line style, expressive eyes, soft pastel palette, highly detailed",
                "example_url": "https://source.unsplash.com/960x1280/?anime,illustration",
            },
        ],
    },
]

# ══════════════════════════════════════════════════════════════
# БИБЛИОТЕКА ПРОМТОВ: загрузка, сохранение, пути
# ══════════════════════════════════════════════════════════════

# Primary runtime path: /app/data/prompt_library.json on Bothost, BASE_DIR locally.
# Source of truth is the webapp repo (Cloudflare Pages); bot syncs from it at startup.
PROMPT_LIBRARY_DATA_PATH = os.path.join(RUNTIME_DIR, "prompt_library.json")
PROMPT_LIBRARY_PRIMARY_PATH = os.getenv("PROMPT_LIBRARY_PRIMARY_PATH", "").strip() or PROMPT_LIBRARY_DATA_PATH


def _bootstrap_prompt_library_primary() -> None:
    """Ensure primary storage directory exists. Cloudflare Pages is source of truth."""
    try:
        primary_dir = os.path.dirname(PROMPT_LIBRARY_PRIMARY_PATH)
        if primary_dir:
            os.makedirs(primary_dir, exist_ok=True)
    except Exception:
        logger.exception("Failed to create prompt library storage directory")


def _sync_prompt_library_from_remote(force: bool = False) -> bool:
    """Download prompt_library.json from Cloudflare Pages.
    By default only on first boot (local file absent).
    With force=True — always overwrite (for /pl_sync admin command)."""
    if not PROMPT_LIBRARY_REMOTE_URL:
        return False
    if not force and os.path.exists(PROMPT_LIBRARY_PRIMARY_PATH):
        logger.info("Prompt library already exists locally — skipping remote sync")
        return False
    try:
        import urllib.request as _req
        req = _req.Request(
            PROMPT_LIBRARY_REMOTE_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SirNikeBot/1.0)"},
        )
        with _req.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        data = json.loads(raw)
        if not isinstance(data, list):
            logger.warning("Remote prompt library is not a list, skipping")
            return False
        primary_dir = os.path.dirname(PROMPT_LIBRARY_PRIMARY_PATH)
        if primary_dir:
            os.makedirs(primary_dir, exist_ok=True)
        with open(PROMPT_LIBRARY_PRIMARY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Prompt library synced from remote: %s (%d categories)", PROMPT_LIBRARY_REMOTE_URL, len(data))
        return True
    except Exception as e:
        logger.warning("Failed to sync prompt library from remote: %s", e)
        return False


def load_prompt_library() -> list:
    _bootstrap_prompt_library_primary()

    candidates: List[str] = []
    if os.path.exists(PROMPT_LIBRARY_PRIMARY_PATH):
        candidates.append(PROMPT_LIBRARY_PRIMARY_PATH)

    if not candidates:
        return DEFAULT_PROMPT_LIBRARY

    for source_path in candidates:
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list) or not data:
                logger.warning("prompt_library.json is empty or invalid list at %s", source_path)
                continue

            for cat in data:
                if not isinstance(cat, dict):
                    raise ValueError("Category item must be object")
                if "title" not in cat or "items" not in cat:
                    raise ValueError("Category must contain title and items")
                if not isinstance(cat["items"], list):
                    raise ValueError("Category items must be list")

            # Put video categories first, image categories after
            def _cat_sort_key(cat: dict) -> int:
                items = cat.get("items") or []
                for it in items:
                    raw = str(it.get("kind") or it.get("type") or it.get("target") or "").strip().lower()
                    if raw in {"video", "video_prompt"}:
                        return 0  # video category → front
                return 1  # image category → back

            data.sort(key=_cat_sort_key)
            return data
        except Exception as e:
            logger.exception(f"Failed to load prompt_library.json from {source_path}: {e}")

    return DEFAULT_PROMPT_LIBRARY


PROMPT_LIBRARY = load_prompt_library()
_prompt_library_lock: Optional[asyncio.Lock] = None  # initialised lazily after event loop starts


def _get_prompt_library_lock() -> asyncio.Lock:
    if _prompt_library_lock is None:
        raise RuntimeError("_prompt_library_lock used before post_init — call post_init first")
    return _prompt_library_lock


def _sort_prompt_library(data: list) -> list:
    """Sort items within each category: added_at newest-first, then items without date."""
    for cat in data:
        items = cat.get("items") or []
        with_date = [(i, it) for i, it in enumerate(items) if it.get("added_at")]
        without_date = [it for it in items if not it.get("added_at")]
        with_date.sort(key=lambda x: x[1]["added_at"], reverse=True)
        cat["items"] = [it for _, it in with_date] + without_date
    return data


def save_prompt_library(data: list) -> None:
    data = _sort_prompt_library(data)
    path = PROMPT_LIBRARY_PRIMARY_PATH
    dir_path = os.path.dirname(path)
    if dir_path and not os.path.isdir(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Автобэкап в /app/data/ при каждом изменении
    try:
        from datetime import datetime as _dt
        backup_dir = os.path.join(DATA_DIR, "pl_backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"prompt_library_{ts}.json")
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Оставляем только 20 последних бэкапов
        backups = sorted(os.listdir(backup_dir))
        for old in backups[:-20]:
            try:
                os.remove(os.path.join(backup_dir, old))
            except Exception:
                pass
    except Exception:
        pass


def refresh_prompt_library() -> None:
    global PROMPT_LIBRARY
    PROMPT_LIBRARY = load_prompt_library()


async def _locked_save_and_refresh(data: list) -> None:
    """Thread-safe save + reload of the prompt library. Use in async admin handlers."""
    async with _get_prompt_library_lock():
        await asyncio.to_thread(save_prompt_library, data)
        await asyncio.to_thread(refresh_prompt_library)


def _showcase_item_kind(item: dict) -> str:
    # Делегируем общему определителю (он же ловит видео по video_url)
    return get_prompt_item_kind(item)


def _safe_media_url(url: str) -> str:
    # Кириллица в путях (например .../videos/ДР.mp4) ломает выдачу медиа по URL
    from urllib.parse import quote
    return quote(str(url or "").strip(), safe=":/?&=%#")


def _showcase_item_label(item: dict) -> str:
    # У фото-промптов названий нет (намеренно) — берём начало описания
    title = str(item.get("title") or "").strip()
    if title:
        return title
    desc = str(item.get("description") or "").strip()
    if desc:
        short = re.split(r"[:.\n—]", desc, maxsplit=1)[0].strip()
        if len(short) > 30:
            short = short[:30].rsplit(" ", 1)[0]
        if short:
            return short
    return "Стиль"


def pick_showcase_items(limit_images: int = 2, limit_videos: int = 2) -> list:
    """Свежие стили с превью для витрины новичка: (cat_idx, item_idx, item).
    Фото-стили — по example_url, видео-стили — по video_url. Сначала фото, потом видео."""
    images, videos = [], []
    for cat_idx, cat in enumerate(PROMPT_LIBRARY):
        for item_idx, item in enumerate(cat.get("items") or []):
            if not isinstance(item, dict):
                continue
            if not str(item.get("prompt") or "").strip():
                continue
            if _showcase_item_kind(item) == "video":
                if str(item.get("video_url") or "").strip().startswith("http"):
                    videos.append((cat_idx, item_idx, item))
            else:
                if str(item.get("example_url") or "").strip().startswith("http"):
                    images.append((cat_idx, item_idx, item))

    def _freshness(pick):
        return str(pick[2].get("added_at") or "")

    images.sort(key=_freshness, reverse=True)
    videos.sort(key=_freshness, reverse=True)
    return images[:limit_images] + videos[:limit_videos]


# ══════════════════════════════════════════════════════════════
# УТИЛИТЫ: вспомогательные функции
# ══════════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_image_model(state: UserState) -> str:
    if state.image_model == "gpt5" and GPT5_IMAGE_ENABLED:
        return "gpt5"
    return "gemini"


def get_image_model_label(model_code: str) -> str:
    if model_code == "gpt5":
        return "GPT-5 Image"
    slug = (ZVENO_IMAGE_MODEL or "").lower()
    if "3.1-flash-image" in slug:
        return "Nano Banana 2"
    if "3-pro-image" in slug:
        return "Nano Banana Pro"
    if "2.5-flash-image" in slug:
        return "Nano Banana"
    return ZVENO_IMAGE_MODEL or "Gemini"


def get_image_model_base_cost(model_code: str) -> int:
    if model_code == "gpt5":
        return max(GPT5_IMAGE_COST, 1)
    return BASE_GENERATION_COST


def calc_generation_cost(references: Optional[List[str]] = None, image_model: str = "gemini") -> int:
    cost = get_image_model_base_cost(image_model)
    if references:
        cost += REFERENCE_COST
    return cost


def ru_plural(value: int, one: str, few: str, many: str) -> str:
    value = abs(int(value))
    if 11 <= value % 100 <= 14:
        return many
    if value % 10 == 1:
        return one
    if 2 <= value % 10 <= 4:
        return few
    return many


def get_seedance_duration_bounds(model_code: Optional[str] = None) -> tuple[int, int]:
    if model_code == "veo31":
        return 4, 8
    if model_code == "kling3":
        return 3, 15
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
    return "720p"


def seedance_mode_ui_label(mode: str) -> str:
    normalized = normalize_seedance_mode(mode)
    return "480" if normalized == "480p" else "720"


def get_seedance_mode_options(model_code: Optional[str] = None) -> List[str]:
    if model_code == "seedance2_fast":
        return [normalize_seedance_mode(SEEDANCE_FAST_MODE)]
    if model_code in ("kling3", "veo31"):
        # Zveno: kling-v3.0 и veo-3.1-fast поддерживают только 720p.
        return ["720p"]

    raw_options = os.getenv("SEEDANCE_MODE_OPTIONS", "480,720")
    parsed: List[str] = []
    for raw in str(raw_options).split(","):
        mode = normalize_seedance_mode(raw)
        if mode not in parsed:
            parsed.append(mode)
    default_mode = normalize_seedance_mode(SEEDANCE_MODE)
    if default_mode not in parsed:
        parsed.append(default_mode)
    # Seedance 2 supports 480p/720p. Keep both visible unless explicitly restricted.
    for fallback_mode in ("480p", "720p"):
        if fallback_mode not in parsed:
            parsed.append(fallback_mode)
    return parsed


def get_selected_seedance_mode(state: UserState) -> str:
    selected_model = get_video_model(state)
    options = get_seedance_mode_options(selected_model)
    if selected_model in ("seedance2_fast", "kling3", "veo31"):
        return options[0]
    picked = normalize_seedance_mode(state.video_mode or SEEDANCE_MODE)
    if picked not in options:
        picked = options[0]
    return picked


def get_seedance_duration_options(model_code: Optional[str] = None) -> List[int]:
    if model_code == "kling3":
        raw_options = KLING3_DURATION_OPTIONS
    elif model_code == "veo31":
        raw_options = VEO31_DURATION_OPTIONS
    elif model_code == "seedance2_fast":
        raw_options = SEEDANCE_FAST_DURATION_OPTIONS
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


def get_selected_seedance_duration(state: UserState) -> int:
    model_code = get_video_model(state)
    options = get_seedance_duration_options(model_code)
    default_sec = options[0] if options else normalize_seedance_duration(int(SEEDANCE_DURATION), model_code)
    selected = normalize_seedance_duration(state.video_duration, model_code) if isinstance(state.video_duration, int) else default_sec
    if selected not in options:
        selected = default_sec
    return selected


def get_video_image_urls(state: UserState) -> List[str]:
    urls: List[str] = []
    for item in state.animation_source_urls:
        if isinstance(item, str):
            candidate = item.strip()
            if candidate and candidate not in urls:
                urls.append(candidate)
    return urls[:MAX_SEEDANCE_IMAGE_REFERENCES]


def set_video_image_urls(state: UserState, image_urls: List[str]) -> None:
    clean_urls: List[str] = []
    for item in image_urls:
        if isinstance(item, str):
            candidate = item.strip()
            if candidate and candidate not in clean_urls:
                clean_urls.append(candidate)
    clean_urls = clean_urls[:MAX_SEEDANCE_IMAGE_REFERENCES]
    state.animation_source_urls = clean_urls
    state.animation_source_url = clean_urls[-1] if clean_urls else None


def add_video_image_url(state: UserState, image_url: str) -> int:
    current = get_video_image_urls(state)
    candidate = image_url.strip()
    if candidate and candidate not in current:
        if len(current) >= MAX_SEEDANCE_IMAGE_REFERENCES:
            current = current[-(MAX_SEEDANCE_IMAGE_REFERENCES - 1):]
        current.append(candidate)
    set_video_image_urls(state, current)
    return len(state.animation_source_urls)


def deactivate_video_session(state: UserState) -> None:
    state.video_session_active = False
    state.waiting_for_video_prompt = False
    state.waiting_for_video_image = False
    state.waiting_for_motion_video = False


def get_video_model(state: UserState) -> str:
    if state.video_model == "seedance2_fast" and SEEDANCE_FAST_ENABLED:
        return "seedance2_fast"
    if state.video_model == "kling3" and KLING3_ENABLED:
        return "kling3"
    if state.video_model == "veo31" and VEO31_ENABLED:
        return "veo31"
    return "seedance2"


def get_video_model_label(model_code: str) -> str:
    labels = {
        "seedance2_fast": "Seedance 2 Fast (бета)",
        "seedance2": "Seedance 2",
        "kling3": "Kling 3.0 🆕",
        "veo31": "Veo 3.1 (Google) 🆕",
    }
    return labels.get(model_code, "Seedance 2")


def get_video_model_cost_per_second(model_code: str) -> float:
    if model_code == "seedance2_fast":
        return max(SEEDANCE_FAST_COST_PER_SECOND, 0.01)
    if model_code == "kling3":
        return max(KLING3_COST_PER_SECOND, 0.01)
    if model_code == "veo31":
        return max(VEO31_COST_PER_SECOND, 0.01)
    return max(SEEDANCE_COST_PER_SECOND, 0.01)


def calc_seedance_cost(duration_sec: int, cost_per_second: Optional[float] = None) -> int:
    cps = max(
        cost_per_second if cost_per_second is not None else SEEDANCE_COST_PER_SECOND,
        0.01,
    )
    safe_duration = max(1, int(duration_sec))
    return max(1, int(round(safe_duration * cps)))


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


def get_or_init_state(context: ContextTypes.DEFAULT_TYPE) -> UserState:
    state = context.user_data.get("state")
    if not isinstance(state, UserState):
        state = UserState()
        context.user_data["state"] = state
    return state


def generation_failure_user_text(refunded: bool) -> str:
    refund_text = "\n\n✅ Изюминки не списаны (или возвращены) — баланс не пострадал, можешь попробовать снова." if refunded else ""
    return (
        "Что-то пошло не так при генерации 😔\n"
        "Попробуй, пожалуйста, ещё раз через пару минут."
        f"{refund_text}"
    )


def get_prompt_webapp_url(user_id: int = None) -> str:
    base = str(PROMPT_WEBAPP_URL or "").strip()
    if not base:
        return ""
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}rev={PROMPT_WEBAPP_REV}"
    if user_id is not None:
        bal = get_balance(user_id)
        url += f"&balance={bal}"
        try:
            history = get_generation_history(user_id, limit=10)
            if history:
                compact = [{"u": h["image_url"], "p": (h["prompt"] or "")[:60], "t": h["created_at"]} for h in history]
                raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
                encoded = base64.urlsafe_b64encode(raw.encode()).decode()
                if len(url) + len(encoded) + 3 < 2048:
                    url += f"&h={encoded}"
        except Exception as e:
            logger.warning("Failed to encode history for webapp URL: %s", e)
    return url


def video_unavailable_text() -> str:
    return "Видео в разработке 🚧\nСкоро включим эту функцию."

def schedule_photo_done_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    old_task = photo_tasks.pop(chat_id, None)  # pop сразу, чтобы finally старой задачи не удалил новую
    if old_task and not old_task.done():
        old_task.cancel()

    async def send_done_later():
        try:
            await asyncio.sleep(2.0)
            count = photo_counts.pop(chat_id, 0)
            if count > 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"Фото получены: {count} шт. ✅\n"
                        "Бот будет использовать их при генерации.\n\n"
                        "Теперь напиши описание картинки или выбери стиль из библиотеки 📚\n"
                        "и нажми «Запустить генерацию ⚡»"
                    ),
                    reply_markup=main_menu_kb()
                )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("send_done_later failed for chat_id=%s", chat_id)
        finally:
            photo_tasks.pop(chat_id, None)

    photo_tasks[chat_id] = asyncio.create_task(send_done_later())


# ══════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ: кнопки и меню
# ══════════════════════════════════════════════════════════════

def main_menu_kb() -> InlineKeyboardMarkup:
    if PROMPT_WEBAPP_URL:
        prompt_library_button = InlineKeyboardButton(
            "Библиотека стилей 📚",
            callback_data="pl_open_webapp",
        )
    else:
        prompt_library_button = InlineKeyboardButton(
            "Библиотека стилей 📚",
            callback_data="pl_open",
        )

    video_label = "Видео 🎬" if SEEDANCE_ENABLED else "Видео 🚧"
    rows = [
        # Главные действия
        [InlineKeyboardButton("⚡ Запустить генерацию", callback_data="generate")],
        [prompt_library_button],
        # Дополнительные инструменты в одну строку
        [
            InlineKeyboardButton(video_label, callback_data="video"),
            InlineKeyboardButton("🪄 Мой аватар", callback_data="avatar_actions"),
        ],
    ]
    if GPT5_IMAGE_ENABLED:
        rows.append([InlineKeyboardButton("🧠 Модель картинок", callback_data="image_model_menu")])
    rows.extend([
        # Служебные — на отдельных строках, понятнее
        [InlineKeyboardButton("🔄 Начать заново", callback_data="reset")],
        [InlineKeyboardButton("🚨 Сообщить о проблеме", callback_data="report_problem")],
    ])
    return InlineKeyboardMarkup(rows)


def image_model_menu_kb(state: UserState) -> InlineKeyboardMarkup:
    selected = get_image_model(state)
    gemini_cost = calc_generation_cost(None, "gemini")
    gpt5_cost = calc_generation_cost(None, "gpt5")
    rows = [
        [InlineKeyboardButton(
            ("● " if selected == "gemini" else "") + f"{get_image_model_label('gemini')} · {gemini_cost} изюминок",
            callback_data="image_model_set_gemini",
        )],
        [InlineKeyboardButton(
            ("● " if selected == "gpt5" else "") + f"GPT-5 Image 🆕 · {gpt5_cost} изюминок",
            callback_data="image_model_set_gpt5",
        )],
        [InlineKeyboardButton("В меню", callback_data="reset")],
    ]
    return InlineKeyboardMarkup(rows)


def image_model_menu_text(state: UserState) -> str:
    selected = get_image_model(state)
    return (
        "🧠 Модель генерации картинок\n\n"
        f"• {get_image_model_label('gemini')} — модель Google: быстрая, отлично работает с фото-референсами и аватарами.\n"
        "• GPT-5 Image — новинка от OpenAI: точнее следует описанию, лучше рисует текст на картинке.\n\n"
        f"Сейчас выбрана: {get_image_model_label(selected)}"
    )

def promo_try_kb(promo_id: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🚀 Сгенерировать", callback_data=f"promo_try_{promo_id}")]]
    if PROMPT_WEBAPP_URL:
        rows.append([InlineKeyboardButton("Библиотека стилей 📚", callback_data="pl_open_webapp")])
    else:
        rows.append([InlineKeyboardButton("Библиотека стилей 📚", callback_data="pl_open")])
    return InlineKeyboardMarkup(rows)


def support_report_admin_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Ответить пользователю 💬", callback_data=f"support_reply_{user_id}")]
    ])



def avatar_kind_label(kind: str) -> str:
    raw = str(kind or "").strip().lower()
    if raw == "male":
        return "мужской 👨"
    if raw == "child":
        return "детский 🧒"
    return "женский 👩"

AVATAR_REFSHEET_PROMPT = (
    "Using the person in this reference photo, generate a single square image containing a 2x2 character reference sheet (4 cells in one image): "
    "Top-left: FRONT VIEW (face straight at camera, neutral expression). "
    "Top-right: SIDE PROFILE (90° left profile view). "
    "Bottom-left: THREE-QUARTER VIEW (3/4 angle, slightly turned). "
    "Bottom-right: FULL BODY (head to toe, same person, same clothing). "
    "CRITICAL RULES: "
    "- Keep the EXACT same person: same face shape, hair color/style, skin tone, clothing, body proportions. "
    "- Each cell should have a clean, simple background (light gray or white). "
    "- Professional character sheet layout — clear separation between cells. "
    "- Realistic photographic style — looks like real studio photography. "
    "- Natural skin textures, real lighting, no cartoon/illustration effects. "
    "- Square output (1:1 aspect ratio). "
    "- High quality, detailed rendering. "
    "- Do NOT add any text labels, captions, or titles on the image. "
    "Output exactly ONE square image."
)

def avatar_actions_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    existing = {}
    if user_id is not None:
        try:
            existing = get_avatar_urls(user_id)
        except Exception:
            pass
    else:
        existing = {"female": True, "male": True, "child": True}

    rows = []
    if not any(existing.values()):
        rows.append([InlineKeyboardButton("❓ Что такое аватар?", callback_data="avatar_help")])
    rows.append([InlineKeyboardButton("🎨 Сгенерировать аватар", callback_data="avatar_gen_refsheet")])
    rows.append([
        InlineKeyboardButton("Загрузить женский 👩", callback_data="set_avatar_female"),
        InlineKeyboardButton("Загрузить мужской 👨", callback_data="set_avatar_male"),
    ])
    rows.append([InlineKeyboardButton("Загрузить детский 🧒", callback_data="set_avatar_child")])
    if any(existing.values()):
        rows.append([InlineKeyboardButton("Показать аватары 👀", callback_data="show_avatar")])
        del_row = []
        if existing.get("female"):
            del_row.append(InlineKeyboardButton("Удалить женский 🗑", callback_data="delete_avatar_female"))
        if existing.get("male"):
            del_row.append(InlineKeyboardButton("Удалить мужской 🗑", callback_data="delete_avatar_male"))
        if del_row:
            rows.append(del_row)
        if existing.get("child"):
            rows.append([InlineKeyboardButton("Удалить детский 🗑", callback_data="delete_avatar_child")])
        rows.append([InlineKeyboardButton("Удалить все аватары 🧹", callback_data="delete_avatar")])
    rows.append([InlineKeyboardButton("Назад в меню ↩️", callback_data="avatar_back_menu")])
    return InlineKeyboardMarkup(rows)

def webapp_open_kb(user_id: int = None) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Открыть библиотеку 📚", web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)))]],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
    )


def webapp_inline_kb(user_id: int = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Открыть библиотеку 📚", web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)))]
    ])


def prompt_library_menu_kb() -> InlineKeyboardMarkup:
    rows = []
    for idx, cat in enumerate(PROMPT_LIBRARY):
        rows.append([InlineKeyboardButton(f"{cat['emoji']} {cat['title']}", callback_data=f"pl_cat_{idx}")])
    rows.append([InlineKeyboardButton("В меню", callback_data="reset")])
    return InlineKeyboardMarkup(rows)


def prompt_library_category_kb(cat_idx: int) -> InlineKeyboardMarkup:
    rows = []
    items = PROMPT_LIBRARY[cat_idx]["items"]
    for item_idx, item in enumerate(items):
        rows.append([InlineKeyboardButton(_showcase_item_label(item), callback_data=f"pl_view_{cat_idx}_{item_idx}")])
    rows.append([InlineKeyboardButton("← К категориям", callback_data="pl_open")])
    return InlineKeyboardMarkup(rows)


def get_prompt_item_kind(item: dict) -> str:
    if not isinstance(item, dict):
        return "image"
    raw = str(item.get("kind") or item.get("type") or item.get("target") or "").strip().lower()
    if raw in {"video", "seedance", "seedance_video", "seedance2"}:
        return "video"
    if str(item.get("video_url") or "").strip():
        return "video"
    return "image"


def prompt_library_item_kb(cat_idx: int, item_idx: int, item_kind: str = "image") -> InlineKeyboardMarkup:
    use_text = "Использовать в видео ✅" if item_kind == "video" else "Использовать этот стиль ✅"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(use_text, callback_data=f"pl_use_{cat_idx}_{item_idx}")],
        [InlineKeyboardButton("← Назад к категории", callback_data=f"pl_cat_{cat_idx}")],
        [InlineKeyboardButton("К категориям", callback_data="pl_open")],
    ])


def prompt_library_save_category_kb() -> InlineKeyboardMarkup:
    rows = []
    for idx, cat in enumerate(PROMPT_LIBRARY):
        rows.append([InlineKeyboardButton(f"{cat['emoji']} {cat['title']}", callback_data=f"plsave_cat_{idx}")])
    rows.append([InlineKeyboardButton("Отмена", callback_data="plsave_cancel")])
    return InlineKeyboardMarkup(rows)


def prompt_library_admin_kb_legacy() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Показать категории", callback_data="pladm_list")],
        [InlineKeyboardButton("Создать категорию", callback_data="pladm_new")],
        [InlineKeyboardButton("Переименовать категорию", callback_data="pladm_rename")],
        [InlineKeyboardButton("Удалить категорию", callback_data="pladm_delete")],
        [InlineKeyboardButton("Экспорт JSON", callback_data="pladm_export")],
        [InlineKeyboardButton("Закрыть", callback_data="pladm_cancel")],
    ])


def prompt_history_kb(items: list, offset: int, page_size: int = 5) -> InlineKeyboardMarkup:
    rows = []
    for idx, item in enumerate(items, start=1):
        prompt_preview = (item.get("prompt") or "").strip().replace("\n", " ")
        if len(prompt_preview) > 32:
            prompt_preview = prompt_preview[:32] + "..."
        label = f"{idx + offset}. {prompt_preview or 'Без описания'}"
        rows.append([InlineKeyboardButton(label, callback_data=f"plhist_pick_{item['id']}")])

    nav = []
    if offset > 0:
        prev_offset = max(0, offset - page_size)
        nav.append(InlineKeyboardButton("← Назад", callback_data=f"plhist_open_{prev_offset}"))
    if len(items) >= page_size:
        next_offset = offset + page_size
        nav.append(InlineKeyboardButton("Вперед →", callback_data=f"plhist_open_{next_offset}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("В админ-меню", callback_data="pladm_open")])
    return InlineKeyboardMarkup(rows)


def prompt_history_preview_kb(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Сохранить в библиотеку ✅", callback_data=f"plhist_export_{item_id}")],
        [InlineKeyboardButton("Назад к истории", callback_data="plhist_open_0")],
    ])


def prompt_library_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Показать категории", callback_data="pladm_list")],
        [InlineKeyboardButton("История генераций", callback_data="plhist_open_0")],
        [InlineKeyboardButton("Создать категорию", callback_data="pladm_new")],
        [InlineKeyboardButton("Переименовать категорию", callback_data="pladm_rename")],
        [InlineKeyboardButton("Удалить категорию", callback_data="pladm_delete")],
        [InlineKeyboardButton("Экспорт JSON", callback_data="pladm_export")],
        [InlineKeyboardButton("Закрыть", callback_data="pladm_cancel")],
    ])


# Video control UI (single final implementation).
def video_kb(state: UserState) -> InlineKeyboardMarkup:
    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_video_model(state)
    selected_mode = get_selected_seedance_mode(state)
    cps = get_video_model_cost_per_second(selected_model)
    video_images = get_video_image_urls(state)

    duration_buttons = []
    for sec in get_seedance_duration_options(selected_model):
        cost = calc_seedance_cost(sec, cps)
        prefix = "● " if sec == selected_duration else ""
        duration_buttons.append(
            InlineKeyboardButton(
                f"{prefix}{sec}с · {cost} изюминок",
                callback_data=f"video_duration_{sec}",
            )
        )

    model_buttons = [
        InlineKeyboardButton(
            ("● " if selected_model == "seedance2" else "") + "Seedance 2",
            callback_data="video_model_seedance2",
        )
    ]
    if SEEDANCE_FAST_ENABLED:
        model_buttons.append(
            InlineKeyboardButton(
                ("● " if selected_model == "seedance2_fast" else "") + "Seedance 2 Fast (бета)",
                callback_data="video_model_seedance2_fast",
            )
        )
    model_buttons_extra = []
    if KLING3_ENABLED:
        model_buttons_extra.append(
            InlineKeyboardButton(
                ("● " if selected_model == "kling3" else "") + "Kling 3.0 🆕",
                callback_data="video_model_kling3",
            )
        )
    if VEO31_ENABLED:
        model_buttons_extra.append(
            InlineKeyboardButton(
                ("● " if selected_model == "veo31" else "") + "Veo 3.1 🆕",
                callback_data="video_model_veo31",
            )
        )

    rows = [
        # Основные параметры
        [InlineKeyboardButton("1️⃣ Описание ✍️", callback_data="video_set_prompt")],
        [InlineKeyboardButton("2️⃣ Изображение 🌄", callback_data="video_set_image")],
    ]
    # Загруженные фото — одна кнопка с количеством вместо кучи кнопок удаления
    if video_images:
        rows.append([
            InlineKeyboardButton(
                f"📸 Фото: {len(video_images)} шт. · Очистить 🧹",
                callback_data="video_clear_images",
            )
        ])
        # Кнопки удаления по одной — максимум 3 штуки чтобы не перегружать
        delete_buttons = [
            InlineKeyboardButton(f"✕ #{idx}", callback_data=f"video_delimg_{idx}")
            for idx, _ in enumerate(video_images, start=1)
        ]
        rows.append(delete_buttons[:3])
        if len(delete_buttons) > 3:
            rows.append(delete_buttons[3:6])
    # Модель
    rows.append(model_buttons)
    if model_buttons_extra:
        rows.append(model_buttons_extra)
    # Режим качества
    if selected_model == "seedance2":
        mode_buttons = []
        for mode in get_seedance_mode_options(selected_model):
            prefix = "● " if mode == selected_mode else ""
            mode_buttons.append(
                InlineKeyboardButton(
                    f"{prefix}{seedance_mode_ui_label(mode)}",
                    callback_data=f"video_mode_{seedance_mode_ui_label(mode)}",
                )
            )
        if mode_buttons:
            rows.append(mode_buttons)
    # Формат (aspect ratio)
    selected_aspect = getattr(state, "video_aspect_ratio", "16:9")
    aspect_options = [("16:9", "📺 16:9 (горизонталь)"), ("9:16", "📱 9:16 (вертикаль, Reels)"), ("1:1", "⬛ 1:1 (квадрат)")]
    if selected_model == "veo31":
        # Veo 3.1 не поддерживает квадрат.
        aspect_options = [(ar, label) for ar, label in aspect_options if ar != "1:1"]
    aspect_buttons = [
        InlineKeyboardButton(
            ("● " if ar == selected_aspect else "") + label,
            callback_data=f"video_aspect_{ar.replace(':', 'x')}",
        )
        for ar, label in aspect_options
    ]
    rows.append(aspect_buttons)
    # Длительность
    if duration_buttons:
        rows.append(duration_buttons[:3])
    if len(duration_buttons) > 3:
        rows.append(duration_buttons[3:])
    # Запуск
    rows.append([InlineKeyboardButton("⚡ Запустить видео", callback_data="video_start")])
    return InlineKeyboardMarkup(rows)


def video_status_text(state: UserState) -> str:
    prompt_state = "добавлен" if state.video_prompt.strip() else "необязательно"
    video_images = get_video_image_urls(state)
    image_state = (
        f"{len(video_images)} шт. (макс. {MAX_SEEDANCE_IMAGE_REFERENCES})"
        if video_images
        else "не добавлено"
    )
    refs_preview_lines: List[str] = []
    for idx, ref_url in enumerate(video_images, start=1):
        ref_text = str(ref_url or "").strip()
        if len(ref_text) > 96:
            ref_text = f"{ref_text[:60]}...{ref_text[-28:]}"
        refs_preview_lines.append(f"{idx}. {ref_text}")
    refs_preview_text = (
        "Рефы в буфере:\n" + "\n".join(refs_preview_lines)
        if refs_preview_lines
        else "Рефы в буфере: —"
    )
    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_video_model(state)
    model_label = get_video_model_label(selected_model)
    selected_mode = get_selected_seedance_mode(state)
    cps = get_video_model_cost_per_second(selected_model)
    selected_cost = calc_seedance_cost(selected_duration, cps)
    eta_min = max(2, int(selected_duration * 0.8))
    eta_max = max(eta_min + 1, int(selected_duration * 2.0))
    options_text = ", ".join([f"{sec}с" for sec in get_seedance_duration_options(selected_model)])
    quality_text = (
        f"{seedance_mode_ui_label(selected_mode)} (варианты: {', '.join([seedance_mode_ui_label(m) for m in get_seedance_mode_options(selected_model)])})"
        if selected_model == "seedance2"
        else f"{seedance_mode_ui_label(selected_mode)} (фиксировано)"
    )
    return (
        f"{model_label}\n"
        "Генерация видео с помощью нейросети.\n"
        "Можно сразу отправлять текст и фото без дополнительных кнопок.\n"
        "Фото фиксируют внешность персонажей в кадре.\n\n"
        "1. Напиши описание видео (необязательно)\n"
        "2. Отправь фото (бот запомнит внешность)\n"
        "3. Выбери длительность и качество\n"
        "4. Нажми «Запустить ⚡»\n\n"
        f"Модель: {model_label}\n"
        f"Описание: {prompt_state}\n"
        f"Изображение: {image_state}\n"
        f"{refs_preview_text}\n"
        f"Формат: {getattr(state, 'video_aspect_ratio', '16:9')}\n"
        f"Качество: {quality_text}\n"
        f"Длительность: {selected_duration} сек (варианты: {options_text})\n"
        f"Стоимость: {selected_cost} изюминок\n"
        f"Ожидание результата: обычно {eta_min}–{eta_max} минут"
    )


def video_upsell_kb(user_id: int) -> tuple:
    """Воронка под готовым видео: «Сделать длиннее» и апгрейд Fast → Seedance 2.

    Возвращает (markup | None, has_upsell)."""
    params = last_video_params.get(user_id)
    if not isinstance(params, dict) or not params.get("model"):
        return None, False
    model = params.get("model") or "seedance2"
    try:
        duration = int(params.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    rows = []
    longer = [d for d in get_seedance_duration_options(model) if d > duration]
    if longer:
        next_dur = longer[0]
        cost = calc_seedance_cost(next_dur, get_video_model_cost_per_second(model))
        rows.append([InlineKeyboardButton(
            f"📏 Сделать длиннее — {next_dur} сек · {cost} изюминок",
            callback_data=f"video_longer_{next_dur}",
        )])
    if model == "seedance2_fast":
        upgrade_cost = calc_seedance_cost(duration, get_video_model_cost_per_second("seedance2"))
        rows.append([InlineKeyboardButton(
            f"💎 Переделать в Seedance 2 — {upgrade_cost} изюминок",
            callback_data="video_upgrade_seedance2",
        )])
    has_upsell = bool(rows)
    rows.append([InlineKeyboardButton("🔁 Ещё видео", callback_data="video")])
    return InlineKeyboardMarkup(rows), has_upsell


# ----------------------------
# Commands
# ----------------------------

def seedance_retry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Повторить 🔁", callback_data="seedance_retry")],
        [InlineKeyboardButton("В меню", callback_data="reset")],
    ])


def broadcast_library_kb() -> InlineKeyboardMarkup:
    if PROMPT_WEBAPP_URL:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Библиотека стилей 📚", callback_data="pl_open_webapp")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Библиотека стилей 📚", callback_data="pl_open")]
    ])


def cache_media_group_message(message) -> None:
    if not message:
        return
    media_group_id = getattr(message, "media_group_id", None)
    if not media_group_id:
        return

    media_item: Optional[Dict[str, Any]] = None
    if getattr(message, "photo", None):
        media_item = {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": message.caption or "",
            "message_id": int(getattr(message, "message_id", 0) or 0),
            "added_at": time.time(),
        }
    elif getattr(message, "video", None):
        media_item = {
            "type": "video",
            "file_id": message.video.file_id,
            "caption": message.caption or "",
            "message_id": int(getattr(message, "message_id", 0) or 0),
            "added_at": time.time(),
        }

    if not media_item:
        return

    cache_key = (int(message.chat_id), str(media_group_id))
    # Move to end so OrderedDict insertion-order reflects recency
    if cache_key in MEDIA_GROUP_CACHE:
        MEDIA_GROUP_CACHE.move_to_end(cache_key)
    bucket = MEDIA_GROUP_CACHE.setdefault(cache_key, [])
    if any(item.get("message_id") == media_item["message_id"] for item in bucket):
        return
    if len(bucket) >= MAX_MEDIA_GROUP_CHUNK_SIZE:
        return  # bucket full — ignore extra items (prevents DoS)

    bucket.append(media_item)

    # TTL eviction — не чаще раз в 60 сек, чтобы не делать O(n) на каждый media item
    global _MEDIA_GROUP_LAST_TTL_CHECK
    _now = time.time()
    if _now - _MEDIA_GROUP_LAST_TTL_CHECK > 60:
        _MEDIA_GROUP_LAST_TTL_CHECK = _now
        _media_group_ttl = 600  # seconds
        stale_keys = [
            k for k, v in MEDIA_GROUP_CACHE.items()
            if v and (_now - float(v[0].get("added_at", _now))) > _media_group_ttl
        ]
        for k in stale_keys:
            MEDIA_GROUP_CACHE.pop(k, None)
    while len(MEDIA_GROUP_CACHE) > MAX_CACHED_MEDIA_GROUPS:
        MEDIA_GROUP_CACHE.popitem(last=False)


def get_cached_media_group(chat_id: int, media_group_id: Optional[str]) -> List[Dict[str, Any]]:
    if not media_group_id:
        return []
    cache_key = (int(chat_id), str(media_group_id))
    _now = time.time()
    _ttl = 600  # 10 minutes
    items = [
        i for i in MEDIA_GROUP_CACHE.get(cache_key, [])
        if (_now - float(i.get("added_at", 0))) < _ttl
    ]
    items.sort(key=lambda item: int(item.get("message_id", 0)))
    return items


def build_media_group_payload(items: List[Dict[str, Any]]) -> List[Any]:
    media_payload: List[Any] = []
    for item in items:
        file_id = str(item.get("file_id") or "").strip()
        if not file_id:
            continue
        caption = str(item.get("caption") or "").strip() or None
        if item.get("type") == "photo":
            media_payload.append(InputMediaPhoto(media=file_id, caption=caption))
        elif item.get("type") == "video":
            media_payload.append(
                InputMediaVideo(
                    media=file_id,
                    caption=caption,
                    supports_streaming=True,
                )
            )
    return media_payload


# Override label to keep retry wording consistent after failed image generation.
def result_actions_kb(user_id: int = 0, bot_username: str = "") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Повторить 🔁", callback_data="generate_again")],
    ]
    if user_id and SEEDANCE_ENABLED:
        rows.append([InlineKeyboardButton("Оживить 🎬 (сделать видео)", callback_data="animate_last")])
    if user_id and bot_username:
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        rows.append([InlineKeyboardButton("🎁 Пригласить друга (+10 изюминок)", url=ref_link)])
    rows.append([InlineKeyboardButton("В меню", callback_data="reset")])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════════════
# КОМАНДЫ ПОЛЬЗОВАТЕЛЯ: /start, /balance, /ref, /buy и т.д.
# ══════════════════════════════════════════════════════════════

async def _test_mode_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Block all non-admin users when TEST_MODE is on."""
    user = update.effective_user
    if user and user.id not in ADMIN_IDS:
        if update.message:
            await update.message.reply_text("Бот на техническом обслуживании. Скоро вернёмся!")
        elif update.callback_query:
            await update.callback_query.answer("Бот на техническом обслуживании.", show_alert=True)
        raise ApplicationHandlerStop


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    referrer_id = None
    if context.args:
        arg = context.args[0].strip()
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", ""))
                if referrer_id == user.id:
                    referrer_id = None
            except ValueError:
                referrer_id = None

    is_new_user = create_user_if_not_exists(user.id, user.username, START_BONUS, referrer_id=referrer_id)

    if referrer_id and is_new_user and mark_referral_bonus(user.id):
        try:
            add_izyminki(user.id, REFERRAL_BONUS_NEW_USER)
            try:
                add_izyminki(referrer_id, REFERRAL_BONUS_REFERRER)
            except Exception:
                # Откатываем бонус новому пользователю, если реферреру не начислилось
                add_izyminki(user.id, -REFERRAL_BONUS_NEW_USER)
                raise
            logger.info("Referral bonus credited: new_user=%s referrer=%s bonus_new=%s bonus_ref=%s",
                        user.id, referrer_id, REFERRAL_BONUS_NEW_USER, REFERRAL_BONUS_REFERRER)
        except Exception:
            logger.exception("Failed to credit referral bonuses for user_id=%s referrer_id=%s", user.id, referrer_id)
        referrer_balance = get_balance(referrer_id)
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    f"🎉 По твоей реферальной ссылке зарегистрировался новый пользователь!\n"
                    f"Тебе начислено +{REFERRAL_BONUS_REFERRER} изюминок 🧀\n"
                    f"Твой баланс: {referrer_balance} изюминок"
                ),
            )
        except Exception:
            logger.warning("Failed to notify referrer %s about bonus", referrer_id)

    bal = get_balance(user.id)
    free_date, free_count = get_free_info(user.id)
    state = get_or_init_state(context)
    deactivate_video_session(state)
    avatar_urls = get_avatar_urls(user.id)
    avatar_status = ", ".join([avatar_kind_label(k) for k, v in avatar_urls.items() if v]) or "нет"

    if is_new_user:
        bonus_photos = START_BONUS // BASE_GENERATION_COST
        free_photos_today = bonus_photos + FREE_GENERATIONS_PER_DAY
        text = (
            f"Привет! Я Сырник 🧀 — бот для создания AI-фото и видео.\n\n"
            f"🎁 Тебе доступно {free_photos_today} фото бесплатно уже сегодня:\n"
            f"  • подарок на старте — {START_BONUS} изюминок ({bonus_photos} фото)\n"
            f"  • ещё {FREE_GENERATIONS_PER_DAY} бесплатная генерация каждый день\n\n"
            f"⚡ Попробуй прямо сейчас:\n"
            f"  Нажми «Библиотека стилей 📚» → выбери стиль → «Запустить генерацию ⚡»\n\n"
            f"🪄 Чтобы не загружать своё фото каждый раз — создай «Мой аватар», "
            f"и бот запомнит твою внешность.\n"
            f"❓ Подробнее: /help"
        )
    else:
        free_left = max(0, FREE_GENERATIONS_PER_DAY - free_count)
        text = (
            f"С возвращением! 🧀\n\n"
            f"💰 Баланс: {bal} изюминок\n"
            f"🆓 Бесплатных сегодня: {free_left}\n"
            f"🪄 Аватары: {avatar_status}\n\n"
            f"Напиши описание картинки или выбери стиль из библиотеки 📚"
        )
    await update.message.reply_text(text, reply_markup=main_menu_kb())

    # Витрина для новичка: альбом примеров из библиотеки + кнопки "хочу так же"
    if is_new_user:
        try:
            showcase = pick_showcase_items()
            if showcase:
                media = []
                for _, _, item in showcase:
                    if _showcase_item_kind(item) == "video":
                        media.append(InputMediaVideo(
                            media=_safe_media_url(item.get("video_url")),
                            supports_streaming=True,
                        ))
                    else:
                        media.append(InputMediaPhoto(
                            media=_safe_media_url(item.get("example_url")),
                        ))
                if len(media) > 1:
                    await update.message.reply_media_group(media)
                elif isinstance(media[0], InputMediaVideo):
                    await update.message.reply_video(media[0].media)
                else:
                    await update.message.reply_photo(media[0].media)
                digits = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
                buttons = [
                    [InlineKeyboardButton(
                        f"{digits[i]} {_showcase_item_label(item)}"
                        + (" 🎬" if _showcase_item_kind(item) == "video" else ""),
                        callback_data=f"shc_{cat_idx}_{item_idx}",
                    )]
                    for i, (cat_idx, item_idx, item) in enumerate(showcase)
                ]
                await update.message.reply_text(
                    "Такие фото и видео делают пользователи Сырника 👆\n"
                    "Нравится стиль? Жми на него — я всё подготовлю:",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
        except Exception:
            logger.warning("Failed to send showcase to new user %s", user.id, exc_info=True)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    bal = get_balance(user.id)
    free_date, free_count = get_free_info(user.id)

    from datetime import timedelta
    _now_msk = datetime.utcnow() + timedelta(hours=3)
    _next_reset = _now_msk.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    _hours_left = int((_next_reset - _now_msk).total_seconds() / 3600)
    _mins_left = int(((_next_reset - _now_msk).total_seconds() % 3600) / 60)
    free_status = (
        f"✅ осталось {free_count}/{FREE_GENERATIONS_PER_DAY}"
        if free_count > 0
        else f"❌ исчерпаны (новые через ~{_hours_left}ч {_mins_left}мин)"
    )
    await update.message.reply_text(
        f"💰 Твой баланс\n\n"
        f"Изюминок: {bal} 🧀  (1 фото = {BASE_GENERATION_COST} изюминок)\n"
        f"Бесплатных генераций: {free_status}\n"
        f"Следующий сброс: завтра в 0:00 по московскому времени",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Купить изюминки", callback_data="show_buy")],
            [InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open_webapp")],
        ])
    )

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.message.chat.type != "private":
        await update.message.reply_text("Напиши мне эту команду в личный чат — там покажу ссылку.")
        return
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    import urllib.parse
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(link)}&text={urllib.parse.quote('Попробуй этот AI-бот для фото!')}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Поделиться с другом", url=share_url)],
    ])
    await update.message.reply_text(
        f"Приглашай друзей и получай изюминки 🎁\n\n"
        f"Твоя ссылка:\n`{link}`\n\n"
        f"Ты получишь +{REFERRAL_BONUS_REFERRER} изюминок за каждого друга.\n"
        f"Друг получит +{REFERRAL_BONUS_NEW_USER} изюминок в подарок.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)
    bal = get_balance(user.id)
    await update.message.reply_text(
        "🧀 Сырник — бот для создания AI-фото и видео\n\n"
        "Как пользоваться:\n"
        "1. Напиши описание картинки (например: «девушка на фоне заката»)\n"
        "   или выбери готовый стиль из библиотеки 📚\n"
        "2. Нажми «Запустить генерацию ⚡»\n"
        "3. Получи фото — готово!\n\n"
        "🪄 Аватар — загрузи свои фото, и бот поставит тебя в любой образ\n"
        "🎬 Видео — Seedance 2, Kling 3.0, Veo 3.1 (кнопка в меню)\n"
        f"🆓 {FREE_GENERATIONS_PER_DAY} бесплатная генерация каждый день\n"
        f"💰 Твой баланс: {bal} изюминок (1 фото = {BASE_GENERATION_COST} изюминок)\n\n"
        "Команды:\n"
        "/start — главное меню\n"
        "/balance — баланс и бесплатные генерации\n"
        "/buy — купить изюминки\n"
        "/ref — пригласить друга (+изюминки обоим)\n"
        "/report — сообщить о проблеме\n"
        "/help — эта справка",
        reply_markup=main_menu_kb(),
    )


async def hide_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    await message.reply_text(
        "Готово 👍",
        reply_markup=ReplyKeyboardRemove(),
    )


async def report_problem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)
    state = get_or_init_state(context)
    state.waiting_for_problem_report = True
    await update.message.reply_text(
        "📝 Опиши что не работает\n\n"
        "Примеры:\n"
        "• Генерация долго загружается\n"
        "• Фото выходит размытым\n"
        "• Не могу загрузить аватар\n\n"
        "Можешь добавить скриншот вторым сообщением.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data="reset")
        ]])
    )


def extract_chat_completion_text(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    message = (choices[0] or {}).get("message", {})
    content = message.get("content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()

    return ""


async def send_long_text(chat, text: str) -> None:
    max_len = 3900
    payload = (text or "").strip()
    if not payload:
        return

    while payload:
        if len(payload) <= max_len:
            await chat.reply_text(payload)
            return

        cut = payload.rfind("\n", 0, max_len)
        if cut < 1000:
            cut = max_len
        await chat.reply_text(payload[:cut].strip())
        new_payload = payload[cut:].strip()
        if new_payload == payload:  # guard against infinite loop on unsplittable text
            break
        payload = new_payload


async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.message.reply_text(
            "Использование:\n"
            "/ai <вопрос>\n\n"
            "Пример:\n"
            "/ai Придумай 5 идей промптов для портрета в стиле fashion."
        )
        return

    if not ZVENO_API_KEY:
        await update.message.reply_text(
            "Текстовый помощник /ai сейчас временно отключен.\n"
            "Генерация изображений работает в обычном режиме."
        )
        return

    request_url = build_zveno_url(ZVENO_API_BASE, "/v1/chat/completions")

    payload = {
        "model": ZVENO_CHAT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Ты полезный и дружелюбный ассистент. Отвечай кратко и по делу на русском языке.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                request_url,
                headers={
                    "x-api-key": ZVENO_API_KEY,
                    "Authorization": f"Bearer {ZVENO_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                response_text = await resp.text()
                if not (200 <= resp.status < 300):
                    lowered = response_text.lower()
                    quota_like = (
                        resp.status in (402, 429)
                        or "insufficient_quota" in lowered
                        or "недостаточно энергии" in lowered
                        or "not_enough" in lowered
                    )

                    if quota_like:
                        logger.warning(f"/ai quota exhausted: {resp.status}. {response_text}")
                        await update.message.reply_text(
                            "Баланс текстового /ai закончился, поэтому команда временно недоступна.\n"
                            "Генерация изображений продолжает работать."
                        )
                        return

                    logger.error(f"/ai request failed: {resp.status}. {response_text}")
                    await update.message.reply_text("Сервис /ai сейчас недоступен. Попробуй чуть позже.")
                    return

                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.error(f"/ai non-JSON response: {response_text}")
                    await update.message.reply_text("Сервис /ai вернул некорректный ответ. Попробуй позже.")
                    return

        answer = extract_chat_completion_text(data)
        if not answer:
            logger.error(f"/ai empty response: {json.dumps(data, ensure_ascii=False)}")
            await update.message.reply_text("Не удалось получить ответ от модели. Попробуй переформулировать запрос.")
            return

        await send_long_text(update.message, answer)

    except asyncio.TimeoutError:
        logger.warning("/ai request timeout")
        await update.message.reply_text("Сервис /ai отвечает слишком долго. Попробуй еще раз через минуту.")
    except Exception:
        logger.exception("/ai request error")
        await update.message.reply_text("Ошибка при обращении к /ai. Попробуй еще раз через минуту.")


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cost of one 5-second Seedance video (standard model)
    _video_10s_cost = calc_seedance_cost(10, SEEDANCE_COST_PER_SECOND)
    keyboard = []
    for pack in BUY_PACKS:
        photo_count = max(1, pack["count"] // BASE_GENERATION_COST)
        video_count = pack["count"] // _video_10s_cost
        photos_label = ru_plural(photo_count, "фото", "фото", "фото")
        if video_count > 0:
            videos_label = ru_plural(video_count, "видео", "видео", "видео")
            hint = f"≈ {photo_count} {photos_label} / {video_count}+ {videos_label} (зависит от длины видео)"
        else:
            hint = f"≈ {photo_count} {photos_label}"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{pack['count']} изюминок — {pack['price']} ₽ · {hint}",
                callback_data=f"buy_{pack['count']}_{pack['price']}"
            )
        ])

    await update.message.reply_text(
        f"💰 Пополнить баланс\n\n"
        f"• 1 фото = {BASE_GENERATION_COST} изюминок 🧀\n"
        f"• 1 видео 10 сек = {_video_10s_cost} изюминок 🎬\n"
        f"  (длиннее видео — дороже, короче — дешевле)\n\n"
        f"Выбери пакет:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    payload = query.invoice_payload
    try:
        parts = payload.split("_")
        if len(parts) < 3:
            raise ValueError("too few parts")
        count = int(parts[1])
        price = int(parts[2])
        if count <= 0:
            raise ValueError("non-positive count")
        valid_pack = next((p for p in BUY_PACKS if p["count"] == count and p["price"] == price), None)
        if valid_pack is None:
            raise ValueError(f"unknown pack count={count} price={price}")
    except Exception as e:
        logger.warning("Invalid precheckout payload %r from user %s: %s", payload, query.from_user.id, e)
        await query.answer(ok=False, error_message="Ошибка: неверный платёжный пакет.")
        return
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment = update.message.successful_payment

    payment_id = payment.telegram_payment_charge_id
    payload = payment.invoice_payload

    try:
        parts = payload.split("_")
        if len(parts) < 3:
            raise ValueError("too few parts")
        count = int(parts[1])
        price = int(parts[2])
        if count <= 0 or price <= 0:
            raise ValueError("non-positive count or price")
        valid_pack = next((p for p in BUY_PACKS if p["count"] == count and p["price"] == price), None)
        if valid_pack is None:
            raise ValueError(f"unknown pack count={count} price={price}")
    except Exception as e:
        logger.error("Invalid payment payload %r from user %s: %s", payload, user.id, e)
        await update.message.reply_text("Ошибка обработки платежа. Обратись в поддержку.")
        return

    if payment.total_amount != valid_pack["price"] * 100:
        logger.error("Payment amount mismatch: expected %d kopecks, got %d, user=%s",
                     valid_pack["price"] * 100, payment.total_amount, user.id)
        await update.message.reply_text("Ошибка: сумма платежа не совпадает. Обратись в поддержку.")
        return

    if not save_payment_once(user.id, payment_id, count):
        await update.message.reply_text("Платёж уже обработан.")
        return

    # add_izyminki is now done atomically inside save_payment_once
    new_balance = get_balance(user.id)

    await update.message.reply_text(
        f"Оплата прошла успешно ✅\n"
        f"Начислено {count} изюминок 🧀\n"
        f"Твой баланс: {new_balance} изюминок\n\n"
        f"Можешь запускать генерацию!",
        reply_markup=main_menu_kb(),
    )


async def send_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int, price: int):
    query = update.callback_query

    if not any(p["count"] == count and p["price"] == price for p in BUY_PACKS):
        await query.answer("Пакет не найден.", show_alert=True)
        return

    _video_10s_cost = calc_seedance_cost(10, SEEDANCE_COST_PER_SECOND)
    photo_count = max(1, count // BASE_GENERATION_COST)
    video_count = count // _video_10s_cost
    if video_count > 0:
        description = (
            f"{count} изюминок — это примерно {photo_count} фото "
            f"или {video_count} видео по 5 секунд."
        )
    else:
        description = f"{count} изюминок — это примерно {photo_count} фото."

    prices = [LabeledPrice(label=f"{count} изюминок", amount=price * 100)]

    _invoice_kwargs = dict(
        chat_id=query.message.chat_id,
        title="Покупка изюминок 🧀",
        description=description,
        payload=f"buy_{count}_{price}",
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=prices,
        start_parameter="buy-izuminki"
    )
    try:
        await context.bot.send_invoice(**_invoice_kwargs)
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        await context.bot.send_invoice(**_invoice_kwargs)
    except Exception:
        logger.exception("Failed to send invoice")
        await query.answer("Не удалось отправить счёт. Попробуй через минуту.", show_alert=True)

# ══════════════════════════════════════════════════════════════
# АДМИН: рассылки, статистика, управление
# ══════════════════════════════════════════════════════════════

_broadcast_running = False  # guard against parallel broadcasts


async def broadcast_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _broadcast_running
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Ответь этой командой на сообщение с фото.\n"
            "Пример:\n"
            "/broadcast_promo нужный промт"
        )
        return

    if not context.args:
        await update.message.reply_text("После команды нужно передать промт.")
        return

    replied = update.message.reply_to_message
    photo = replied.photo[-1] if replied.photo else None
    caption_text = replied.caption or replied.text or ""
    promo_prompt = " ".join(context.args).strip()

    if not photo:
        await update.message.reply_text("Нужно ответить на сообщение с фото.")
        return

    if not promo_prompt:
        await update.message.reply_text("Промт пустой.")
        return

    if _broadcast_running:
        await update.message.reply_text("⚠️ Рассылка уже запущена. Дождись её завершения.")
        return
    _broadcast_running = True
    try:
        promo_id = f"promo_{user.id}_{update.message.message_id}"

        create_promo_broadcast(
            promo_id=promo_id,
            admin_user_id=user.id,
            caption_text=caption_text,
            promo_prompt=promo_prompt,
            photo_file_id=photo.file_id,
        )

        users = get_all_user_ids()
        sent = 0
        failed = 0

        for target_user_id in users:
            try:
                await context.bot.send_photo(
                    chat_id=target_user_id,
                    photo=photo.file_id,
                    caption=caption_text,
                    reply_markup=promo_try_kb(promo_id),
                )
                sent += 1
                await asyncio.sleep(0.05)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await context.bot.send_photo(
                        chat_id=target_user_id,
                        photo=photo.file_id,
                        caption=caption_text,
                        reply_markup=promo_try_kb(promo_id),
                    )
                    sent += 1
                except Exception:
                    failed += 1
                    logger.warning(f"Повторная отправка не удалась для {target_user_id}")
            except (Forbidden, BadRequest):
                failed += 1
            except Exception:
                failed += 1
                logger.exception(f"Не удалось отправить рассылку пользователю {target_user_id}")

        await update.message.reply_text(
            f"Рассылка завершена.\n"
            f"Promo ID: {promo_id}\n"
            f"Отправлено: {sent}\n"
            f"Ошибок: {failed}"
        )
    finally:
        _broadcast_running = False

async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _broadcast_running
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    source_message = update.message.reply_to_message
    raw_text = update.message.text or ""
    text = ""
    entities = update.message.entities or []
    if entities and entities[0].type == "bot_command" and entities[0].offset == 0:
        cmd_len = entities[0].length
        if len(raw_text) > cmd_len:
            # Keep original formatting/newlines in the body; trim only command separator.
            text = raw_text[cmd_len:]
            if text.startswith(" "):
                text = text[1:]
            if text.startswith("\n"):
                text = text[1:]
    else:
        parts = raw_text.split(maxsplit=1)
        text = parts[1] if len(parts) > 1 else ""

    text = text.rstrip()
    if not source_message and not text:
        await update.message.reply_text(
            "Использование:\n"
            "1) Ответь командой /broadcast на любое сообщение (текст, фото, видео, опрос и т.д.)\n"
            "или\n"
            "2) /broadcast <текст сообщения>\n\n"
            "Пример:\n"
            "/broadcast Привет! Сегодня добавили новые стили генерации."
        )
        return

    if _broadcast_running:
        await update.message.reply_text("⚠️ Рассылка уже запущена. Дождись её завершения.")
        return
    _broadcast_running = True
    try:
        users = get_all_user_ids()
        sent = 0
        failed = 0
        library_kb = broadcast_library_kb()
        source_group_items: List[Dict[str, Any]] = []
        if source_message and getattr(source_message, "media_group_id", None):
            source_group_items = get_cached_media_group(
                chat_id=source_message.chat_id,
                media_group_id=source_message.media_group_id,
            )
            if not source_group_items:
                await update.message.reply_text(
                    "Я не вижу полный состав этого альбома (обычно после перезапуска бота).\n"
                    "Перешли фото/видео-альбом заново и снова ответь командой /broadcast."
                )
                return

        for target_user_id in users:
            try:
                if source_message:
                    if source_group_items:
                        for start_idx in range(0, len(source_group_items), MAX_MEDIA_GROUP_CHUNK_SIZE):
                            chunk = source_group_items[start_idx:start_idx + MAX_MEDIA_GROUP_CHUNK_SIZE]
                            media_payload = build_media_group_payload(chunk)
                            if not media_payload:
                                continue
                            await context.bot.send_media_group(
                                chat_id=target_user_id,
                                media=media_payload,
                            )
                            await asyncio.sleep(0.02)
                        await context.bot.send_message(
                            chat_id=target_user_id,
                            text="Библиотека стилей 👇",
                            reply_markup=library_kb,
                        )
                    else:
                        try:
                            await context.bot.copy_message(
                                chat_id=target_user_id,
                                from_chat_id=source_message.chat_id,
                                message_id=source_message.message_id,
                            )
                        except RetryAfter as e:
                            await asyncio.sleep(e.retry_after + 1)
                            await context.bot.copy_message(
                                chat_id=target_user_id,
                                from_chat_id=source_message.chat_id,
                                message_id=source_message.message_id,
                            )
                        except Exception:
                            await context.bot.forward_message(
                                chat_id=target_user_id,
                                from_chat_id=source_message.chat_id,
                                message_id=source_message.message_id,
                            )
                        await context.bot.send_message(
                            chat_id=target_user_id,
                            text="Библиотека стилей 👇",
                            reply_markup=library_kb,
                        )
                else:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=text,
                        reply_markup=library_kb,
                    )
                sent += 1
                await asyncio.sleep(0.05)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=text,
                        reply_markup=library_kb,
                    )
                    sent += 1
                except Exception:
                    failed += 1
                    logger.warning("Повторная отправка не удалась для %s", target_user_id)
            except (Forbidden, BadRequest):
                failed += 1
            except Exception:
                    failed += 1
                    logger.exception(f"Не удалось отправить рассылку пользователю {target_user_id}")
    
        await update.message.reply_text(
            "Рассылка завершена.\n"
            f"Отправлено: {sent}\n"
            f"Ошибок: {failed}"
        )
    finally:
        _broadcast_running = False


async def broadcast_hide_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _broadcast_running
    user = update.effective_user
    message = update.effective_message
    if not message:
        return

    if not is_admin(user.id):
        await message.reply_text("У тебя нет доступа к этой команде.")
        return

    if _broadcast_running:
        await message.reply_text("⚠️ Рассылка уже запущена. Дождись её завершения.")
        return
    _broadcast_running = True
    try:
        text = (
            "Обновили библиотеку стилей 📚\n"
            "Открывай через кнопку «Библиотека стилей» в меню бота."
        )
        users = get_all_user_ids()
        sent = 0
        failed = 0

        await message.reply_text(f"Начинаю убирать старую нижнюю кнопку у {len(users)} пользователей.")

        for target_user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=text,
                    reply_markup=ReplyKeyboardRemove(),
                )
                sent += 1
                await asyncio.sleep(0.05)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=text,
                        reply_markup=ReplyKeyboardRemove(),
                    )
                    sent += 1
                except Exception:
                    failed += 1
                    logger.warning("Повторная отправка не удалась для %s", target_user_id)
            except (Forbidden, BadRequest):
                failed += 1
            except Exception:
                failed += 1
                logger.exception("Не удалось убрать нижнюю клавиатуру у пользователя %s", target_user_id)

        await message.reply_text(
            "Готово.\n"
            f"Клавиатуру убрали: {sent}\n"
            f"Ошибок: {failed}"
        )
    finally:
        _broadcast_running = False


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Использование: /admin_add <user_id> <amount>")
        return

    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("user_id и amount должны быть числами.")
        return

    if amount <= 0:
        await update.message.reply_text("Сумма должна быть больше нуля.")
        return

    add_izyminki(target_user_id, amount)
    await update.message.reply_text(
        f"Пользователю {target_user_id} добавлено {amount} изюминок."
    )


# ----------------------------
# Input collection
# ----------------------------

# ══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ СООБЩЕНИЙ: текст, фото, видео, webapp
# ══════════════════════════════════════════════════════════════

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    text = update.message.text.strip()
    if not text:
        return

    # Fallback: sometimes WebApp payload can arrive as plain text.
    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            if await apply_webapp_prompt_payload(update, context, payload):
                return

    state = get_or_init_state(context)

    pending_support_reply_user_id = context.user_data.get("pending_support_reply_user_id")
    if pending_support_reply_user_id is not None:
        if not is_admin(user.id):
            context.user_data.pop("pending_support_reply_user_id", None)
            await update.message.reply_text("Нет доступа к режиму ответа пользователю.")
            return

        if text.lower() in {"отмена", "cancel", "/cancel"}:
            context.user_data.pop("pending_support_reply_user_id", None)
            await update.message.reply_text("Ок, отмена ответа пользователю.")
            return

        context.user_data.pop("pending_support_reply_user_id", None)
        try:
            target_user_id = int(pending_support_reply_user_id)
        except (TypeError, ValueError):
            await update.message.reply_text("Не удалось определить пользователя для ответа.")
            return
        support_text = (
            "Ответ от поддержки Сырника 💬\n\n"
            f"{text.strip()}"
        )
        try:
            await context.bot.send_message(chat_id=target_user_id, text=support_text)
            await update.message.reply_text(
                f"Ответ отправлен пользователю {target_user_id} ✅"
            )
        except Exception:
            logger.exception(f"Failed to send support reply to user_id={target_user_id}")
            await update.message.reply_text(
                "Не получилось отправить ответ пользователю.\n"
                "Возможно, пользователь заблокировал бота или чат недоступен."
            )
        return

    pl_admin_mode = context.user_data.get("pl_admin_mode")
    if pl_admin_mode:
        if not is_admin(user.id):
            context.user_data.pop("pl_admin_mode", None)
            context.user_data.pop("pl_admin_rename_old", None)
            await update.message.reply_text("У тебя нет доступа к этой операции.")
            return

        if text.lower() in {"отмена", "cancel", "/cancel"}:
            context.user_data.pop("pl_admin_mode", None)
            context.user_data.pop("pl_admin_rename_old", None)
            await update.message.reply_text(
                "Ок, отмена. Вернулась в админ-меню библиотеки.",
                reply_markup=prompt_library_admin_kb(),
            )
            return

        if pl_admin_mode == "new":
            context.user_data.pop("pl_admin_mode", None)
            try:
                if not is_admin(user.id):
                    await update.message.reply_text("У тебя нет доступа к этой операции.")
                    return
                _, message = await _create_prompt_library_category(text.strip())
                await update.message.reply_text(message, reply_markup=prompt_library_admin_kb())
            except Exception:
                logger.exception("Failed to create prompt category from admin text mode")
                await update.message.reply_text(
                    "Не удалось создать категорию. Попробуй еще раз.",
                    reply_markup=prompt_library_admin_kb(),
                )
            return

        if pl_admin_mode == "rename_old":
            context.user_data["pl_admin_rename_old"] = text.strip()
            context.user_data["pl_admin_mode"] = "rename_new"
            await update.message.reply_text("Теперь отправь новое название категории.")
            return

        if pl_admin_mode == "rename_new":
            old_title = (context.user_data.get("pl_admin_rename_old") or "").strip()
            new_title = text.strip()
            context.user_data.pop("pl_admin_mode", None)
            context.user_data.pop("pl_admin_rename_old", None)
            context.args = [f"{old_title} | {new_title}"]
            await prompt_library_rename_category(update, context)
            await update.message.reply_text("Готово. Что дальше?", reply_markup=prompt_library_admin_kb())
            return

        if pl_admin_mode == "delete":
            context.user_data.pop("pl_admin_mode", None)
            context.args = text.split()
            await prompt_library_delete_category(update, context)
            await update.message.reply_text("Удаление обработано. Что дальше?", reply_markup=prompt_library_admin_kb())
            return

    if state.waiting_for_problem_report:
        if text.lower() in {"отмена", "cancel", "/cancel"}:
            state.waiting_for_problem_report = False
            await update.message.reply_text(
                "Ок, отмена. Если что — кнопку «Сообщить о проблеме 🚨» можно нажать снова.",
                reply_markup=main_menu_kb(),
            )
            return

        state.waiting_for_problem_report = False
        username = f"@{user.username}" if user.username else "нет"
        full_name = (user.full_name or "").strip() or "нет"
        report_text = text.strip()
        admin_message = (
            "🚨 Сообщение о проблеме\n\n"
            f"user_id: {user.id}\n"
            f"username: {username}\n"
            f"name: {full_name}\n"
            f"chat_id: {update.effective_chat.id}\n\n"
            f"Текст:\n{report_text}"
        )

        delivered = 0
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_message,
                    reply_markup=support_report_admin_kb(user.id),
                )
                delivered += 1
            except Exception:
                logger.exception(f"Failed to forward problem report to admin_id={admin_id}")

        if delivered > 0:
            await update.message.reply_text(
                "Спасибо, отправила в поддержку ✅\n"
                "Если хочешь, можешь добавить скриншот следующим сообщением.",
                reply_markup=main_menu_kb(),
            )
        else:
            await update.message.reply_text(
                "Не получилось передать сообщение в поддержку прямо сейчас.\n"
                "Попробуй еще раз через минуту.",
                reply_markup=main_menu_kb(),
            )
        return

    if state.waiting_for_video_prompt or state.video_session_active:
        state.video_prompt = text
        state.waiting_for_video_prompt = False
        state.video_session_active = True
        await update.message.reply_text(
            "Описание для видео сохранено ✅\n"
            "Теперь можешь отправить фото, выбрать длительность/качество и нажать запуск.",
            reply_markup=video_kb(state),
        )
        return

    deactivate_video_session(state)
    state.prompt = text

    await update.message.reply_text(
        "Описание сохранено ✅\n"
        "Теперь нажми «Запустить генерацию ⚡» или отправь своё фото, чтобы быть на картинке.",
        reply_markup=main_menu_kb()
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    state = get_or_init_state(context)
    cache_media_group_message(update.effective_message)
    

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    bio = io.BytesIO()
    await file.download_to_memory(out=bio)
    bio.seek(0)

    try:
        image_bytes = bio.read()
        direct_url = _cache_image(image_bytes)

        if state.generating_avatar:
            if direct_url not in state.avatar_photos:
                if len(state.avatar_photos) >= MAX_AVATAR_PHOTOS:
                    await update.message.reply_text(
                        f"Максимум {MAX_AVATAR_PHOTOS} фото для аватара. Нажми «Готово» или начни заново."
                    )
                    return
                state.avatar_photos.append(direct_url)
            count = len(state.avatar_photos)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"Готово ({count} фото) ▶️", callback_data="avatar_gen_start")
            ]])
            status_text = (
                f"Получено фото: {count} ✅\n"
                "Можешь отправить ещё с других ракурсов или нажать «Готово»."
            )
            if state.avatar_status_msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=state.avatar_status_msg_id,
                        text=status_text,
                        reply_markup=kb,
                    )
                except Exception:
                    sent = await update.message.reply_text(status_text, reply_markup=kb)
                    state.avatar_status_msg_id = sent.message_id
            else:
                sent = await update.message.reply_text(status_text, reply_markup=kb)
                state.avatar_status_msg_id = sent.message_id
            return

        if state.waiting_for_avatar_upload:
            avatar_kind = str(getattr(state, "pending_avatar_kind", "female") or "female").strip().lower()
            persistent_url = await _persist_image_ref(direct_url)
            if persistent_url:
                set_avatar_url(user.id, persistent_url, avatar_kind)
                state.animation_source_url = persistent_url
                saved_msg = f"Аватар ({avatar_kind_label(avatar_kind)}) сохранён ✅\nТеперь просто пиши описание — бот сам подставит твою внешность."
            else:
                state.animation_source_url = direct_url  # keep in-memory for this session
                saved_msg = (
                    f"Фото получено, но сохранить аватар не удалось — все хостинги недоступны.\n"
                    "В этой сессии аватар работает, но после перезапуска бота его нужно загрузить снова."
                )
            state.waiting_for_avatar_upload = False
            state.pending_avatar_kind = "female"
            await update.message.reply_text(saved_msg, reply_markup=main_menu_kb())
            return

        if state.waiting_for_video_image:
            state.video_session_active = True
            current_refs = get_video_image_urls(state)
            if len(current_refs) >= MAX_SEEDANCE_IMAGE_REFERENCES and direct_url not in current_refs:
                await update.message.reply_text(
                    f"Уже загружено {MAX_SEEDANCE_IMAGE_REFERENCES} фото для видео.\n"
                    "Очисти референсы или замени одно из фото, затем запускай генерацию.",
                    reply_markup=video_kb(state),
                )
                return
            total_refs = add_video_image_url(state, direct_url)
            logger.info(
                "handle_photo: added video image for user=%s, total=%s, animation_source_urls=%s",
                user.id, total_refs, state.animation_source_urls,
            )
            await update.message.reply_text(
                f"Фото для видео добавлено ✅\n"
                f"Сейчас загружено: {total_refs}/{MAX_SEEDANCE_IMAGE_REFERENCES}\n"
                "Бот запомнит внешность с фото.\n"
                "Можешь отправить ещё фото или запускать генерацию.",
                reply_markup=video_kb(state),
            )
            return

        state.animation_source_url = direct_url
        if len(state.references) < 8:  # cap to max used in generation
            state.references.append(direct_url)

        chat_id = update.effective_chat.id
        photo_counts[chat_id] = photo_counts.get(chat_id, 0) + 1
        schedule_photo_done_message(context, chat_id)

    except asyncio.TimeoutError:
        logger.exception("IMGBB upload timeout")
        await update.message.reply_text("Загрузка фото заняла слишком много времени. Попробуй ещё раз чуть позже.")
    except Exception:
        logger.exception("handle_photo failed")
        await update.message.reply_text("Не удалось загрузить фото. Попробуй ещё раз.")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)
    state = get_or_init_state(context)
    cache_media_group_message(update.effective_message)

    if not state.waiting_for_motion_video:
        return

    video = update.message.video
    if not video:
        await update.message.reply_text("Пришли обычное видеофайл-сообщение для видео-режима.")
        return

    tg_file = await context.bot.get_file(video.file_id)
    state.motion_video_url = f"https://api.telegram.org/file/bot{TOKEN}/{tg_file.file_path}"
    state.waiting_for_motion_video = False

    await update.message.reply_text(
        "Видео с движением добавлено ✅",
        reply_markup=video_kb(state),
    )


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    raw_data = (update.message.web_app_data.data if update.message and update.message.web_app_data else "").strip()
    if not raw_data:
        await update.message.reply_text("Не удалось получить данные из мини-приложения.")
        return

    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        await update.message.reply_text("Данные мини-приложения повреждены. Попробуй еще раз.")
        return

    prompt = str(payload.get("prompt") or "").strip()
    title = str(payload.get("title") or "шаблон")

    if not prompt:
        await update.message.reply_text("В выбранном шаблоне нет описания.")
        return

    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.prompt = prompt

    await update.message.reply_text(
        f"Готово ✨\nСтиль «{title}» применён.\n"
        "Нажми «Запустить генерацию ⚡» или отправь своё фото.",
        reply_markup=main_menu_kb(),
    )


async def apply_webapp_prompt_payload(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    action = str(payload.get("action") or "").strip().lower()
    if action and action not in {"set_prompt", "set_video_prompt"}:
        return False

    prompt = str(payload.get("prompt") or "").strip()
    title = str(payload.get("title") or "шаблон").strip() or "шаблон"
    if not prompt:
        if update.effective_message:
            await update.effective_message.reply_text("В выбранном шаблоне нет описания.")
        return False

    state = get_or_init_state(context)
    if action == "set_video_prompt":
        state.video_prompt = prompt
        state.video_session_active = True
        state.waiting_for_video_image = True
    else:
        deactivate_video_session(state)
        state.prompt = prompt

    if update.effective_message:
        if action == "set_video_prompt":
            await update.effective_message.reply_text(
                f"Готово ✨\nСтиль «{title}» применён для видео.\n"
                "Теперь отправь фото и запускай видео.",
                reply_markup=video_kb(state),
            )
        else:
            await update.effective_message.reply_text(
                f"Готово ✨\nСтиль «{title}» применён.\nНажми «Запустить генерацию ⚡».",
                reply_markup=main_menu_kb(),
            )
    return True


async def apply_webapp_prompt_payload_v2(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    action = str(payload.get("action") or payload.get("a") or "").strip().lower()
    if action in {"apply_prompt", "use_prompt", "set_template", "apply_template"}:
        action = "set_prompt"
    if action in {"apply_video_prompt", "use_video_prompt", "set_video_template", "apply_video_template"}:
        action = "set_video_prompt"
    if action == "topup":
        if update.effective_message:
            await update.effective_message.reply_text(
                "Открываю меню пополнения 💰",
                reply_markup=ReplyKeyboardRemove(),
            )
            await buy(update, context)
        return True
    if action and action not in {"set_prompt", "set_video_prompt", "set_prompt_ref", "set_video_prompt_ref"}:
        return False

    title = str(payload.get("title") or payload.get("t") or "шаблон").strip() or "шаблон"
    prompt = str(payload.get("prompt") or payload.get("p") or "").strip()

    image_prompt = str(payload.get("image_prompt") or "").strip()

    # Fallback mode for oversized WebApp payload:
    # app sends only (category,item) indices and bot resolves prompt locally.
    if not prompt:
        try:
            cat_idx = int(payload.get("cat_idx") if payload.get("cat_idx") is not None else payload.get("ci"))
            item_idx = int(payload.get("item_idx") if payload.get("item_idx") is not None else payload.get("ii"))
            if not (0 <= cat_idx < len(PROMPT_LIBRARY)):
                raise ValueError(f"cat_idx out of range: {cat_idx}")
            cat_items = PROMPT_LIBRARY[cat_idx].get("items") or []
            if not (0 <= item_idx < len(cat_items)):
                raise ValueError(f"item_idx out of range: {item_idx}")
            item = cat_items[item_idx]
            resolved_title = str(item.get("title") or "").strip()
            resolved_prompt = str(item.get("prompt") or "").strip()
            if resolved_title:
                title = resolved_title
            prompt = resolved_prompt or resolved_title
            if not image_prompt:
                image_prompt = str(item.get("image_prompt") or "").strip()
        except Exception:
            prompt = ""

    prompt = prompt or title

    state = get_or_init_state(context)
    state.image_prompt = image_prompt
    if action in {"set_video_prompt", "set_video_prompt_ref"}:
        state.video_prompt = prompt
        state.video_session_active = True
        state.waiting_for_video_image = True
    else:
        deactivate_video_session(state)
        state.prompt = prompt

    if update.effective_message:
        if action in {"set_video_prompt", "set_video_prompt_ref"}:
            hint = "Теперь отправь фото и запускай видео."
            if image_prompt:
                hint = (
                    "Теперь отправь фото и запускай видео.\n"
                    "💡 Бот сначала стилизует фото через GPT Image, затем сгенерит видео."
                )
            await update.effective_message.reply_text(
                f"Готово ✨\nСтиль «{title}» применён для видео.\n" + hint,
                reply_markup=ReplyKeyboardRemove(),
            )
            await update.effective_message.reply_text(
                "Параметры видео:",
                reply_markup=video_kb(state),
            )
        else:
            await update.effective_message.reply_text(
                f"Готово ✨\nШаблон «{title}» применен.\nТеперь можно запускать генерацию.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await update.effective_message.reply_text(
                "Можно запускать:",
                reply_markup=main_menu_kb(),
            )
    return True


def parse_webapp_payload_loose(raw_data: str) -> Optional[dict]:
    """
    Best-effort parser for malformed/oversized WebApp payloads.
    Helps recover prompt/title when JSON got truncated by WebApp limits.
    """
    text = str(raw_data or "").strip()
    if not text:
        return None

    action_match = re.search(r'"(?:action|a)"\s*:\s*"([^"]+)"', text, flags=re.IGNORECASE)
    title_match = re.search(r'"(?:title|t)"\s*:\s*"([^"]*)"', text, flags=re.IGNORECASE)
    prompt_match = re.search(r'"(?:prompt|p)"\s*:\s*"([\s\S]*)"', text, flags=re.IGNORECASE)

    action = action_match.group(1).strip().lower() if action_match else "set_prompt"
    title = title_match.group(1) if title_match else "шаблон"
    prompt_raw = prompt_match.group(1) if prompt_match else ""

    if prompt_raw:
        cut_markers = ('","example_url"', '","video_url"', '","cat_idx"', '","item_idx"', '"}')
        cut_pos = len(prompt_raw)
        for marker in cut_markers:
            pos = prompt_raw.find(marker)
            if pos != -1 and pos < cut_pos:
                cut_pos = pos
        prompt_raw = prompt_raw[:cut_pos]
        prompt_raw = prompt_raw.replace('\\"', '"').replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")

    payload = {
        "action": action or "set_prompt",
        "title": title or "шаблон",
        "prompt": prompt_raw.strip(),
    }
    if not payload["prompt"] and not payload["title"]:
        return None
    return payload


async def handle_webapp_data_v2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    message = update.effective_message
    raw_data = (message.web_app_data.data if message and message.web_app_data else "").strip()
    if not raw_data:
        if message:
            await message.reply_text("Не удалось получить данные из WebApp.")
        return

    logger.info("WEB_APP_DATA received: %s", raw_data[:500])

    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        payload = parse_webapp_payload_loose(raw_data)
        if not payload:
            if message:
                await message.reply_text("Данные из WebApp не распознаны. Попробуй еще раз.")
            return
        logger.warning("WEB_APP_DATA malformed JSON recovered via loose parser")
    else:
        logger.info(
            "WEB_APP_DATA parsed: action=%s v=%s prompt_len=%s cat_idx=%s item_idx=%s",
            str(payload.get("action") or payload.get("a") or ""),
            str(payload.get("v") or ""),
            len(str(payload.get("prompt") or payload.get("p") or "")),
            str(payload.get("cat_idx") if payload.get("cat_idx") is not None else payload.get("ci") or ""),
            str(payload.get("item_idx") if payload.get("item_idx") is not None else payload.get("ii") or ""),
        )

    applied = await apply_webapp_prompt_payload_v2(update, context, payload)
    if False:
        await message.reply_text("Кнопка WebApp скрыта.", reply_markup=ReplyKeyboardRemove())
    if not applied and message:
        await message.reply_text("Не удалось применить шаблон.")


# ══════════════════════════════════════════════════════════════
# РАБОТА С МЕДИА: хостинг изображений, удаление фона, сетка для рефов
# ══════════════════════════════════════════════════════════════

async def _upload_bytes_to_telegraph(image_bytes: bytes, filename: str = "image.jpg") -> Optional[str]:
    """Upload image to telegra.ph — Telegram-owned, free, no API key, VPS-friendly."""
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("file", image_bytes, filename=filename, content_type="image/jpeg")
            async with session.post(
                "https://telegra.ph/upload",
                data=form,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.warning("telegra.ph upload failed: status=%s body=%s", resp.status, body[:100])
                    return None
                import json as _json
                data = _json.loads(body)
                if isinstance(data, list) and data and "src" in data[0]:
                    url = "https://telegra.ph" + data[0]["src"]
                    logger.info("telegra.ph upload ok: %s", url)
                    return url
                logger.warning("telegra.ph upload unexpected response: %s", body[:100])
                return None
    except Exception as e:
        logger.warning("telegra.ph upload exception: %s", e)
        return None


async def _upload_bytes_to_freeimage(image_bytes: bytes, filename: str = "image.jpg") -> Optional[str]:
    """Upload image to freeimage.host — free, permanent, no registration."""
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("key", "6d207e02198a847aa98d0a2a901485a5")
            form.add_field("action", "upload")
            form.add_field("source", image_bytes, filename=filename, content_type="image/jpeg")
            async with session.post(
                "https://freeimage.host/api/1/upload",
                data=form,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.warning("freeimage.host upload failed: status=%s", resp.status)
                    return None
                data = await resp.json()
                url = (data.get("image") or {}).get("url")
                if url:
                    logger.info("freeimage.host upload ok: %s", url)
                    return url
                logger.warning("freeimage.host upload: no url in response")
                return None
    except Exception as e:
        logger.warning("freeimage.host upload exception: %s", e)
        return None


async def _upload_bytes_to_catbox(image_bytes: bytes, filename: str = "image.jpg") -> Optional[str]:
    """Upload image to catbox.moe — free, permanent, no API key required."""
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("reqtype", "fileupload")
            form.add_field("fileToUpload", image_bytes, filename=filename, content_type="image/jpeg")
            async with session.post(
                "https://catbox.moe/user/api.php",
                data=form,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                body = await resp.text()
                if resp.status != 200 or not body.startswith("https://"):
                    logger.warning("catbox.moe upload failed: status=%s body=%s", resp.status, body[:100])
                    return None
                url = body.strip()
                logger.info("catbox.moe upload ok: %s", url)
                return url
    except Exception as e:
        logger.warning("catbox.moe upload exception: %s", e)
        return None


async def _upload_bytes_to_imgbb(image_bytes: bytes, filename: str = "image.jpg") -> Optional[str]:
    """Upload image to imgbb (fallback, requires IMGBB_API_KEY)."""
    if not IMGBB_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("image", image_bytes, filename=filename, content_type="image/jpeg")
            async with session.post(
                f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}",
                data=form,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.warning("imgbb upload failed: status=%s body=%s", resp.status, body[:100])
                    return None
                data = json.loads(body)
                imgbb_data = data.get("data", {})
                return (
                    imgbb_data.get("url")
                    or (imgbb_data.get("image", {}) or {}).get("url")
                    or imgbb_data.get("display_url")
                )
    except Exception as e:
        logger.warning("imgbb upload exception: %s", e)
        return None


async def upload_image_bytes_to_imgbb(image_bytes: bytes, filename: str = "import.jpg") -> Optional[str]:
    """Upload image bytes — tries freeimage.host → catbox.moe → imgbb."""
    url = await _upload_bytes_to_freeimage(image_bytes, filename)
    if url:
        return url
    url = await _upload_bytes_to_catbox(image_bytes, filename)
    if url:
        return url
    return await _upload_bytes_to_imgbb(image_bytes, filename)


async def upload_image_url_to_imgbb(image_url: str) -> Optional[str]:
    """Fetch image from URL and re-upload to hosting."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=120)) as src_resp:
                if src_resp.status != 200:
                    logger.warning("Failed to fetch source image: %s", src_resp.status)
                    return None
                image_bytes = await src_resp.read()
    except Exception as e:
        logger.warning("upload_image_url_to_imgbb fetch failed: %s", e)
        return None
    return await upload_image_bytes_to_imgbb(image_bytes, filename="image.jpg")


async def _fetch_image_for_sheet(session: aiohttp.ClientSession, url: str) -> Optional[Image.Image]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60), allow_redirects=True) as resp:
            if resp.status != 200:
                logger.warning("Seedance sheet source fetch failed: %s, url=%s", resp.status, url[:80])
                return None
            image_bytes = await resp.read()
        return Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        logger.warning("Seedance sheet source fetch/decode failed for url=%s", url[:80])
        return None


async def build_seedance_reference_sheet_url(image_urls: List[str]) -> Optional[str]:
    clean_urls: List[str] = []
    for item in image_urls:
        if isinstance(item, str):
            candidate = item.strip()
            if candidate and candidate not in clean_urls:
                clean_urls.append(candidate)
    if len(clean_urls) < 2:
        return None

    loaded_images: List[Image.Image] = []
    try:
        async with aiohttp.ClientSession() as session:
            tasks = [asyncio.ensure_future(_fetch_image_for_sheet(session, url)) for url in clean_urls[:MAX_SEEDANCE_IMAGE_REFERENCES]]
            try:
                results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=45)
            except asyncio.TimeoutError:
                for task in tasks:
                    task.cancel()
                logger.warning("build_seedance_reference_sheet_url: timeout after 45s")
                return None
            loaded_images = [img for img in results if img is not None]

        if len(loaded_images) < 2:
            return None

        slot_w, slot_h = 832, 1216
        gap = 16
        canvas_w = slot_w * 2 + gap * 3
        canvas_h = slot_h + gap * 2
        canvas = Image.new("RGB", (canvas_w, canvas_h), (20, 20, 24))

        for idx, src in enumerate(loaded_images[:2]):
            fitted = ImageOps.contain(src, (slot_w, slot_h), Image.Resampling.LANCZOS)
            x0 = gap + idx * (slot_w + gap)
            y0 = gap
            x = x0 + (slot_w - fitted.width) // 2
            y = y0 + (slot_h - fitted.height) // 2
            canvas.paste(fitted, (x, y))

        out = io.BytesIO()
        canvas.save(out, format="JPEG", quality=95, optimize=True)
        out.seek(0)
        sheet_url = await upload_image_bytes_to_imgbb(out.read(), filename="seedance_reference_sheet.jpg")
        if sheet_url:
            logger.info("Seedance reference sheet uploaded successfully")
        return sheet_url
    except Exception:
        logger.exception("build_seedance_reference_sheet_url failed")
        return None
    finally:
        for img in loaded_images:
            try:
                img.close()
            except Exception:
                pass
        
# ----------------------------
# Grid overlay for Seedance refs
# ----------------------------

async def _remove_background_api(image_bytes: bytes) -> bytes:
    """Remove background. Tries Clipdrop → FAPIhub → PhotoRoom → remove.bg in order."""
    png_bytes: Optional[bytes] = None
    last_error = "No background removal API key configured"

    if CLIPDROP_API_KEY and png_bytes is None:
        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("image_file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
                async with session.post(
                    "https://clipdrop-api.co/remove-background/v1",
                    data=form,
                    headers={"x-api-key": CLIPDROP_API_KEY},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        last_error = f"Clipdrop error {resp.status}: {body[:200]}"
                        logger.warning("Clipdrop bg removal failed: %s", last_error)
                    else:
                        png_bytes = await resp.read()
                        logger.info("Background removed via Clipdrop")
        except Exception as e:
            last_error = f"Clipdrop exception: {e}"
            logger.warning("Clipdrop bg removal exception: %s", e)

    if FAPIHUB_API_KEY and png_bytes is None:
        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("image", image_bytes, filename="photo.jpg", content_type="image/jpeg")
                async with session.post(
                    "https://fapihub.com/v2/rembg/",
                    data=form,
                    headers={"ApiKey": FAPIHUB_API_KEY},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        last_error = f"FAPIhub error {resp.status}: {body[:200]}"
                        logger.warning("FAPIhub bg removal failed: %s", last_error)
                    else:
                        png_bytes = await resp.read()
                        logger.info("Background removed via FAPIhub")
        except Exception as e:
            last_error = f"FAPIhub exception: {e}"
            logger.warning("FAPIhub bg removal exception: %s", e)

    if PHOTOROOM_API_KEY and png_bytes is None:
        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("image_file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
                async with session.post(
                    "https://sdk.photoroom.com/v1/segment",
                    data=form,
                    headers={"x-api-key": PHOTOROOM_API_KEY},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        last_error = f"PhotoRoom error {resp.status}: {body[:200]}"
                        logger.warning("PhotoRoom bg removal failed: %s", last_error)
                    else:
                        png_bytes = await resp.read()
                        logger.info("Background removed via PhotoRoom")
        except Exception as e:
            last_error = f"PhotoRoom exception: {e}"
            logger.warning("PhotoRoom bg removal exception: %s", e)

    if REMOVE_BG_API_KEY and png_bytes is None:
        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("image_file", image_bytes, filename="photo.jpg", content_type="image/jpeg")
                form.add_field("size", "auto")
                async with session.post(
                    "https://api.remove.bg/v1.0/removebg",
                    data=form,
                    headers={"X-Api-Key": REMOVE_BG_API_KEY},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        last_error = f"remove.bg error {resp.status}: {body[:200]}"
                        logger.warning("remove.bg bg removal failed: %s", last_error)
                    else:
                        png_bytes = await resp.read()
                        logger.info("Background removed via remove.bg")
        except Exception as e:
            last_error = f"remove.bg exception: {e}"
            logger.warning("remove.bg bg removal exception: %s", e)

    # Local fallback: rembg (free, runs on CPU, no API key needed).
    # Disabled by default — U2Net model needs ~500MB RAM, can OOM-kill the bot.
    # Enable via REMBG_LOCAL_ENABLED=1 on servers with enough memory.
    if png_bytes is None and REMBG_LOCAL_ENABLED:
        try:
            from rembg import remove as _rembg_remove

            def _run_rembg(data: bytes) -> bytes:
                return _rembg_remove(data)

            async with _rembg_semaphore:
                png_bytes = await asyncio.to_thread(_run_rembg, image_bytes)
            logger.info("Background removed via rembg (local)")
        except ImportError:
            logger.warning("rembg not installed, skipping local bg removal")
        except Exception as e:
            last_error = f"rembg local exception: {e}"
            logger.warning("rembg local bg removal failed: %s", e)

    if png_bytes is None:
        raise Exception(last_error)

    def _sync_png_to_jpg(data: bytes) -> bytes:
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        out = io.BytesIO()
        bg.convert("RGB").save(out, format="JPEG", quality=95)
        return out.getvalue()

    return await asyncio.to_thread(_sync_png_to_jpg, png_bytes)


def _extract_zveno_image_result(rd: dict) -> Optional[str]:
    """Pull an image (data: URL or http URL) out of a Zveno chat/completions reply."""
    for choice in (rd.get("choices") or []):
        if not isinstance(choice, dict):
            continue
        msg = choice.get("message")
        if not isinstance(msg, dict):
            continue
        for image_item in (msg.get("images") or []):
            u = image_item.get("url") if isinstance(image_item, dict) else image_item
            if isinstance(u, str) and u.strip():
                return u.strip()
        content = msg.get("content")
        if isinstance(content, str) and is_image_url_like(content.strip()):
            return content.strip()
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                iu = part.get("image_url")
                if isinstance(iu, dict) and isinstance(iu.get("url"), str):
                    return iu["url"].strip()
                if isinstance(iu, str) and iu.strip():
                    return iu.strip()
    return None


async def _run_image_prompt_pipeline(image_prompt: str, ref_urls: List[str]) -> Optional[str]:
    """Generate a stylized image via GPT Image before video generation.

    Returns an image URL (or data: URL) on success, None on failure.
    """
    user_content: list = [{"type": "text", "text": image_prompt}]
    for url in ref_urls[:4]:
        resolved = _ref_to_data_url(url) if _is_img_ref(url) else url
        if resolved and (resolved.startswith("http") or resolved.startswith("data:")):
            user_content.append({"type": "image_url", "image_url": {"url": resolved}})

    payload = {
        "model": ZVENO_GPT5_IMAGE_MODEL,
        "messages": [{"role": "user", "content": user_content}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": "16:9"},
    }
    request_url = build_zveno_url(ZVENO_API_BASE, "/v1/chat/completions")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                request_url,
                headers={
                    "Authorization": f"Bearer {ZVENO_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                if not (200 <= resp.status < 300):
                    body = await resp.text()
                    logger.warning("image_prompt pipeline failed: status=%s body=%s", resp.status, body[:300])
                    return None
                rd = await resp.json()
            result = _extract_zveno_image_result(rd)
            if not result:
                logger.warning("image_prompt pipeline: no image in response")
                return None
            return result
    except Exception as e:
        logger.warning("image_prompt pipeline exception: %s", e)
        return None


async def _seedance_aiportrait(image_bytes: bytes) -> Optional[bytes]:
    """Recreate a real selfie as an AI-generated portrait that keeps identity but
    passes Seedance's "real person" moderation.

    ByteDance's documented path: the detector flags photographic images of real
    people, NOT AI generations. So we run the selfie through Nano Banana (image
    edit) asking it to redraw the same person — same face, hair and clothing — as
    an AI portrait. The output is synthetic, so Seedance accepts it, but identity
    is preserved for the video. Returns JPEG bytes, or None on failure (caller
    falls back to the solid grid overlay).
    """
    if not ZVENO_API_KEY:
        return None

    data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
    # IMPORTANT: the portrait must NOT read as a real photograph — Seedance's
    # detector flags photographic real-person images. But too much stylization made
    # the video cartoonish, so aim for a HYPERREALISTIC 3D CGI render (digital human /
    # Unreal MetaHuman): looks realistic, yet is clearly a computer render, not a
    # photo. Keeps identity recognizable while passing moderation.
    prompt = (
        "Recreate this person as a hyperrealistic 3D CGI character render — a digital "
        "human like a high-end video game / Unreal Engine MetaHuman. Keep the face, "
        "facial features, eyes, nose, lips, eyebrows, face shape, hairstyle and outfit "
        "clearly recognizable as the same person. Realistic rendered skin and lighting, "
        "highly detailed, sharp — but clearly a polished 3D computer render, NOT a "
        "photograph, not a real photo, no camera grain, no photographic film look."
    )
    payload = {
        "model": ZVENO_IMAGE_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "modalities": ["image"],
        "image_config": {"aspect_ratio": "9:16"},
        "max_completion_tokens": 512,
        "temperature": 0.2,
    }
    request_url = build_zveno_url(ZVENO_API_BASE, "/v1/chat/completions")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                request_url,
                headers={
                    "Authorization": f"Bearer {ZVENO_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if not (200 <= resp.status < 300):
                    logger.warning("AI-portrait refify failed: status=%s", resp.status)
                    return None
                rd = await resp.json()

            result = _extract_zveno_image_result(rd)
            if not result:
                logger.warning("AI-portrait refify: no image in response")
                return None
            if result.startswith("data:"):
                comma = result.find(",")
                return base64.b64decode(result[comma + 1:]) if comma != -1 else None
            # http(s) URL — download the generated portrait
            async with session.get(
                result, timeout=aiohttp.ClientTimeout(total=60), allow_redirects=True
            ) as r2:
                if 200 <= r2.status < 300:
                    return await r2.read()
                logger.warning("AI-portrait refify: download failed status=%s", r2.status)
                return None
    except Exception as e:
        logger.warning("AI-portrait refify exception: %s", e)
        return None


def _apply_grid_overlay(
    image_bytes: bytes,
    rows: int = 6,
    cols: int = 6,
    line_color: tuple = (255, 255, 255),
    line_width: int = 12,
) -> bytes:
    """SOLID grid overlay — fallback when AI-portrait refify is unavailable.

    Per community testing of Seedance's face detector, the grid must be SOLID
    (100% opacity) and thick to reliably break face detection — semi-transparent
    or thin lines re-engage the detector. Standard reliable setting is 6×6 white
    lines at 12px. The grid breaks the pixel patterns the detector relies on while
    Seedance still reads the character/pose from the cells between lines.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Downscale to keep payload small; the grid does the disruption, not size.
    max_dim = 768
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    draw = ImageDraw.Draw(img)
    w, h = img.size
    lw = line_width if line_width > 0 else 12
    for i in range(1, cols):
        x = w * i // cols
        draw.line([(x, 0), (x, h)], fill=line_color, width=lw)
    for i in range(1, rows):
        y = h * i // rows
        draw.line([(0, y), (w, y)], fill=line_color, width=lw)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


async def _process_single_grid_ref(session: aiohttp.ClientSession, url: str) -> str:
    try:
        if _is_img_ref(url) or url.startswith("data:"):
            image_bytes = _resolve_image_bytes(url)
            if image_bytes is None:
                logger.warning("Grid overlay: image ref not found in cache: %s", url)
                return url
        else:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60), allow_redirects=True) as resp:
                if resp.status != 200:
                    logger.warning("Grid overlay: download failed status=%s url=%s", resp.status, url[:80])
                    return url
                image_bytes = await resp.read()

        # AI-portrait disabled: the hyperrealistic CGI render came out
        # indistinguishable from the real photo, so it didn't help moderation
        # (and looked like the original). Using the SOLID grid overlay instead —
        # 6×6 white 12px lines at 100% opacity (community-tested working params).
        # _seedance_aiportrait() is kept in the code for possible future use.
        grid_ref = await asyncio.to_thread(
            lambda ib: _cache_image(_apply_grid_overlay(ib)), image_bytes
        )
        logger.info("Grid overlay applied: %s", url[:60])
        return grid_ref
    except Exception:
        logger.exception("Ref processing failed for url=%s, using original", url[:60])
        return url


async def apply_grid_overlay_to_refs(image_urls: List[str]) -> List[str]:
    async with aiohttp.ClientSession() as session:
        tasks = [_process_single_grid_ref(session, url) for url in image_urls]
        return list(await asyncio.gather(*tasks))


# ----------------------------
# Generation
# ----------------------------

# ══════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ: очередь, запуск, результат
# ══════════════════════════════════════════════════════════════

async def run_generation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)
    reply_target = update.callback_query.message if update.callback_query else update.effective_message

    if user.id in queued_user_ids or user.id in processing_user_ids:
        await reply_target.reply_text(
            "Сырник уже работает над твоим запросом 🧀\n"
            "Подожди немного — результат придёт сюда автоматически.\n"
            "После этого можешь запускать следующую генерацию."
        )
        return

    # Reserve slot immediately — before any awaits — to prevent concurrent submissions
    queued_user_ids.add(user.id)

    state = get_or_init_state(context)

    if not state.prompt:
        queued_user_ids.discard(user.id)
        await reply_target.reply_text(
            "Сначала опиши, что хочешь увидеть на картинке 👇\n\n"
            "Например: «девушка на фоне заката», «кот в космосе», «портрет в стиле кино»\n\n"
            "Или выбери готовый стиль из библиотеки:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Библиотека стилей 📚", callback_data="pl_open_webapp")],
                [InlineKeyboardButton("❓ Как пользоваться", callback_data="show_help")],
            ])
        )
        return

    references = list(state.references)
    # Pick best available avatar: use the first non-None among female/male/child
    _all_avatars = get_avatar_urls(user.id)
    avatar_url = (
        _all_avatars.get("female")
        or _all_avatars.get("male")
        or _all_avatars.get("child")
    )
    if avatar_url and not references:
        references = [avatar_url]
    if AI_PROVIDER == "ZVENO" and references:
        original_refs_count = len(references)
        valid_refs: List[str] = []
        dropped_count = 0
        dropped_avatar_ref = False

        # Split refs into instant (no HTTP needed) and those requiring validation
        instant_refs: List[tuple] = []   # (original_index, ref_url)
        to_validate: List[tuple] = []    # (original_index, ref_url)
        for i, ref_url in enumerate(references[:8]):
            if not is_image_url_like(ref_url):
                dropped_count += 1
                if avatar_url and ref_url == avatar_url:
                    dropped_avatar_ref = True
            elif ref_url.startswith("data:"):
                instant_refs.append((i, ref_url))
            elif _is_img_ref(ref_url):
                if _resolve_image_bytes(ref_url) is not None:
                    instant_refs.append((i, ref_url))
                else:
                    dropped_count += 1
                    logger.warning("Dropped stale __img__ ref (cache miss after restart): user=%s", user.id)
            else:
                to_validate.append((i, ref_url))

        # Validate HTTP refs concurrently — shared session to avoid 8 separate handshakes
        if to_validate:
            async with aiohttp.ClientSession() as _val_session:
                results = await asyncio.gather(
                    *(validate_image_url(ref_url, _val_session) for _, ref_url in to_validate),
                    return_exceptions=True,
                )
            for (i, ref_url), result in zip(to_validate, results):
                if isinstance(result, Exception):
                    ok_ref, reason_ref = False, str(result)
                else:
                    ok_ref, reason_ref = result
                if ok_ref:
                    instant_refs.append((i, ref_url))
                else:
                    dropped_count += 1
                    if avatar_url and ref_url == avatar_url:
                        dropped_avatar_ref = True
                    logger.warning(
                        "Dropped invalid image reference before Zveno request: url=%s reason=%s user_id=%s",
                        ref_url[:80], reason_ref, user.id,
                    )

        # Rebuild valid_refs in original order
        instant_refs.sort(key=lambda x: x[0])
        valid_refs = [ref_url for _, ref_url in instant_refs]

        if dropped_count > 0:
            references = valid_refs
            state.references = list(valid_refs)
            if dropped_avatar_ref:
                clear_avatar_url(user.id)
            await reply_target.reply_text(
                f"Часть загруженных фото недоступна и исключена: {dropped_count} шт.\n"
                f"В работу взято: {len(valid_refs)} шт."
            )
            if dropped_avatar_ref:
                await reply_target.reply_text(
                    "Старый аватар-референс оказался битым и был удалён из профиля.\n"
                    "Загрузи новый аватар, если хочешь снова использовать авто-референс."
                )
            if original_refs_count > 0 and len(valid_refs) == 0:
                queued_user_ids.discard(user.id)
                await reply_target.reply_text(
                    "Все загруженные фото сейчас недоступны (битые или удалённые ссылки).\n"
                    "Перезагрузи фото и запусти генерацию снова."
                )
                return

    selected_image_model = get_image_model(state)
    cost = calc_generation_cost(references, selected_image_model)

    # Atomic free-slot check-and-consume to prevent TOCTOU double-use
    use_free = try_use_free_generation(user.id, FREE_GENERATIONS_PER_DAY)
    paid = False

    if not use_free:
        bal = get_balance(user.id)
        if bal < cost:
            queued_user_ids.discard(user.id)
            await reply_target.reply_text(
                f"Не хватает изюминок.\n"
                f"Нужно: {cost}\n"
                f"У тебя: {bal}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Купить изюминки", callback_data="show_buy")
                ]])
            )
            return

        if not spend_izyminki(user.id, cost):
            queued_user_ids.discard(user.id)
            await reply_target.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
            return

        paid = True

    try:
        _bounded_set(last_generated_prompt, user.id, state.prompt)
        # Keep all refs (incl. __img__) so "Повторить" works within the session.
        # __img__ refs live in _image_cache until restart; generate_again drops
        # the dead ones on replay, so stale refs after a restart are harmless.
        _bounded_set(last_generation_references, user.id, list(references))

        job = GenerationJob(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            prompt=state.prompt,
            references=references,
            cost=cost if paid else 0,
            was_free=use_free,
            username=user.username,
            image_model=selected_image_model,
        )
        try:
            generation_queue.put_nowait(job)
            # Алерт если очередь заполнена >80%
            if generation_queue.maxsize and generation_queue.qsize() / generation_queue.maxsize > 0.8:
                logger.critical("Queue near full: %d/%d", generation_queue.qsize(), generation_queue.maxsize)
                for admin_id in ADMIN_IDS:
                    try:
                        await update.get_bot().send_message(
                            chat_id=admin_id,
                            text=f"⚠️ Очередь генерации {generation_queue.qsize()}/{generation_queue.maxsize} — близко к лимиту!"
                        )
                    except Exception:
                        pass
        except asyncio.QueueFull:
            queued_user_ids.discard(user.id)
            if paid:
                add_izyminki(user.id, cost)
            elif use_free:
                restore_free_generation(user.id)
            logger.critical("Queue full: %d/%d", generation_queue.qsize(), generation_queue.maxsize)
            await reply_target.reply_text(
                "Сырник сейчас очень занят — очередь переполнена 😔 Попробуй через минуту."
            )
            return

        await reply_target.reply_text(
            "Сырник всё понял 🧀\n"
            "⏱️ Обработка займёт ~30 сек.\n"
            "Результат придёт сюда — не закрывай чат."
        )

        context.user_data["state"] = UserState()

    except BaseException as _enqueue_exc:
        queued_user_ids.discard(user.id)
        if paid:
            add_izyminki(user.id, cost)
        elif use_free:
            restore_free_generation(user.id)
        if not isinstance(_enqueue_exc, asyncio.CancelledError):
            logger.exception("Failed to enqueue generation job")
            try:
                await reply_target.reply_text("Не получилось взять задачу в работу. Попробуй ещё раз.")
            except Exception:
                pass
        raise



# ══════════════════════════════════════════════════════════════
# ОБРАБОТЧИК КНОПОК: button_handler и вся логика callback
# ══════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        err_text = str(e).lower()
        if "query is too old" in err_text or "query id is invalid" in err_text:
            logger.info("Ignoring stale callback query answer: %s", e)
        else:
            raise
    user = update.effective_user

    admin_only_callback_prefixes = ("pladm_", "plhist_", "plsave_")
    if query.data and query.data.startswith(admin_only_callback_prefixes) and not is_admin(user.id):
        await query.message.reply_text("У тебя нет доступа к этой операции.")
        return

    if query.data == "pladm_open":
        await query.message.reply_text(
            "Кнопочный админ-редактор библиотеки открыт.",
            reply_markup=prompt_library_admin_kb(),
        )
        return

    if query.data == "pladm_list":
        await prompt_library_list(update, context)
        return

    if query.data == "pladm_export":
        await prompt_library_export(update, context)
        return

    if query.data == "pladm_new":
        context.user_data["pl_admin_mode"] = "new"
        await query.message.reply_text("Отправь название новой категории одним сообщением.")
        return

    if query.data == "pladm_rename":
        context.user_data["pl_admin_mode"] = "rename_old"
        await query.message.reply_text("Отправь текущее название категории.")
        return

    if query.data == "pladm_delete":
        context.user_data["pl_admin_mode"] = "delete"
        await query.message.reply_text("Отправь название категории для удаления.")
        return

    if query.data == "pladm_cancel":
        context.user_data.pop("pl_admin_mode", None)
        context.user_data.pop("pl_admin_rename_old", None)
        await query.message.reply_text("Админ-режим закрыт.")
        return

    if query.data.startswith("shc_"):
        # Витрина новичка: применяем выбранный стиль из библиотеки по индексам
        try:
            _, cat_raw, item_raw = query.data.split("_", 2)
            cat_idx, item_idx = int(cat_raw), int(item_raw)
            if not (0 <= cat_idx < len(PROMPT_LIBRARY)):
                raise ValueError(f"cat_idx out of range: {cat_idx}")
            cat_items = PROMPT_LIBRARY[cat_idx].get("items") or []
            if not (0 <= item_idx < len(cat_items)):
                raise ValueError(f"item_idx out of range: {item_idx}")
            item = cat_items[item_idx]
            prompt = str(item.get("prompt") or "").strip()
            if not prompt:
                raise ValueError("showcase item has no prompt")
        except Exception as e:
            logger.warning("Showcase callback failed (%s): %s", query.data, e)
            await query.message.reply_text(
                "Этот стиль обновился — открой «Библиотека стилей 📚» и выбери оттуда.",
                reply_markup=main_menu_kb(),
            )
            return
        title = _showcase_item_label(item)
        state = get_or_init_state(context)
        if _showcase_item_kind(item) == "video":
            state.video_prompt = prompt
            state.video_session_active = True
            state.waiting_for_video_image = True
            hint = str(item.get("upload_hint") or "").strip()
            hint_line = f"Что прислать: {hint.lower()}" if hint else "Теперь пришли своё фото."
            await query.message.reply_text(
                f"Видео-стиль «{title}» применён для видео ✨\n"
                f"{hint_line}\n"
                "Дальше выбирай параметры и запускай видео.",
            )
            await query.message.reply_text(
                "Параметры видео:",
                reply_markup=video_kb(state),
            )
        else:
            deactivate_video_session(state)
            state.prompt = prompt
            await query.message.reply_text(
                f"Стиль «{title}» применён ✨\n"
                "Хочешь себя на этом фото? Сначала пришли своё фото обычным сообщением.\n"
                "А дальше жми «Запустить генерацию ⚡»",
                reply_markup=main_menu_kb(),
            )
        return

    if query.data.startswith("support_reply_"):
        if not is_admin(update.effective_user.id):
            await query.message.reply_text("У тебя нет доступа к этой кнопке.")
            return

        try:
            target_user_id = int(query.data.replace("support_reply_", "", 1))
        except ValueError:
            await query.message.reply_text("Не удалось открыть режим ответа: неверный user_id.")
            return

        context.user_data["pending_support_reply_user_id"] = target_user_id
        await query.message.reply_text(
            f"Напиши ответ пользователю {target_user_id} одним сообщением.\n"
            "Для отмены отправь: отмена"
        )
        return

    if query.data.startswith("plhist_open_"):
        try:
            offset = int(query.data.replace("plhist_open_", "", 1))
        except ValueError:
            offset = 0
        await prompt_library_history(update, context, offset=max(0, offset))
        return

    if query.data.startswith("plhist_export_"):
        try:
            item_id = int(query.data.replace("plhist_export_", "", 1))
        except ValueError:
            await query.message.reply_text("Не удалось экспортировать: неверный id записи.")
            return

        item = get_generation_history_item(update.effective_user.id, item_id)
        if not item:
            await query.message.reply_text("Запись истории не найдена.")
            return

        context.user_data["pending_pl_save"] = {
            "title": f"Шаблон из истории {item_id}",
            "prompt": (item.get("prompt") or "").strip() or "Опирайся на пример изображения и сохрани стиль.",
            "image_url": item.get("image_url") or "",
            "item_kind": "image",
        }
        await query.message.reply_text(
            f"Выбрано из истории: #{item_id}\nТеперь выбери категорию, куда сохранить шаблон:",
            reply_markup=prompt_library_save_category_kb(),
        )
        return

    if query.data.startswith("plhist_pick_"):
        try:
            item_id = int(query.data.replace("plhist_pick_", "", 1))
        except ValueError:
            await query.message.reply_text("Не удалось открыть запись истории.")
            return

        item = get_generation_history_item(update.effective_user.id, item_id)
        if not item:
            await query.message.reply_text("Запись истории не найдена.")
            return

        prompt_text = (item.get("prompt") or "").strip()
        if len(prompt_text) > 600:
            prompt_text = prompt_text[:600] + "..."
        preview_text = (
            f"Предпросмотр записи #{item_id}\n\n"
            f"Описание:\n{prompt_text or 'Без описания'}\n\n"
            "Если всё ок, нажми «Сохранить в библиотеку ✅»."
        )
        image_url = item.get("image_url") or ""
        if image_url:
            try:
                await query.message.reply_photo(
                    photo=image_url,
                    caption=preview_text,
                    reply_markup=prompt_history_preview_kb(item_id),
                )
                return
            except Exception:
                logger.exception("Failed to send history preview photo")

        await query.message.reply_text(
            preview_text,
            reply_markup=prompt_history_preview_kb(item_id),
        )
        return

    if query.data == "pl_open_webapp":
        logger.info(
            "Prompt WebApp open requested: user_id=%s chat_id=%s",
            update.effective_user.id if update.effective_user else "unknown",
            update.effective_chat.id if update.effective_chat else "unknown",
        )
        if not PROMPT_WEBAPP_URL:
            await query.message.reply_text(
                "WebApp пока не подключен. Используй встроенную библиотеку ниже.",
                reply_markup=prompt_library_menu_kb(),
            )
            return
        uid = update.effective_user.id if update.effective_user else None
        await query.message.reply_text(
            "Открывай библиотеку по кнопке ниже:",
            reply_markup=webapp_open_kb(uid),
        )
        return

    if query.data == "pl_open":
        await query.message.reply_text(
            "Выбери категорию. Покажу лучшие стили с примерами 👇",
            reply_markup=prompt_library_menu_kb(),
        )
        return

    if query.data.startswith("pl_cat_"):
        try:
            cat_idx = int(query.data.replace("pl_cat_", "", 1))
            category = PROMPT_LIBRARY[cat_idx]
        except Exception:
            await query.message.reply_text("Не удалось открыть категорию. Попробуй еще раз.")
            return

        await query.message.reply_text(
            f"{category['emoji']} {category['title']}\nВыбери шаблон:",
            reply_markup=prompt_library_category_kb(cat_idx),
        )
        return

    if query.data.startswith("pl_view_"):
        try:
            _, _, cat_raw, item_raw = query.data.split("_", 3)
            cat_idx = int(cat_raw)
            item_idx = int(item_raw)
            item = PROMPT_LIBRARY[cat_idx]["items"][item_idx]
            item_kind = get_prompt_item_kind(item)
        except Exception:
            await query.message.reply_text("Не удалось открыть шаблон. Попробуй еще раз.")
            return

        # Show human-readable description/instructions if available, not the raw prompt
        description_text = str(item.get("description") or item.get("hint") or "").strip()
        what_to_upload = str(item.get("upload_hint") or item.get("what_to_upload") or "").strip()
        if item_kind == "video":
            default_desc = "Видео-шаблон. Загрузи фото-референс и запусти видео."
        else:
            default_desc = "Фото-шаблон. Можно использовать как есть или добавить референс."
        body = description_text or default_desc
        if what_to_upload:
            body += f"\n\n📎 Что загрузить: {what_to_upload}"
        card_text = (
            f"✨ {_showcase_item_label(item)}\n\n"
            f"{body}\n\n"
            "Нажми «Использовать», чтобы применить шаблон."
        )

        if item_kind == "video":
            video_url = str(item.get("video_url") or item.get("preview_video_url") or "").strip()
            if video_url:
                try:
                    await query.message.reply_video(
                        video=video_url,
                        caption=card_text,
                        supports_streaming=True,
                        reply_markup=prompt_library_item_kb(cat_idx, item_idx, item_kind=item_kind),
                    )
                    return
                except Exception:
                    logger.exception("Failed to send prompt preview video")

        example_url = item.get("example_url") or item.get("poster_url")
        if example_url and item_kind != "video":
            try:
                await query.message.reply_photo(
                    photo=example_url,
                    caption=card_text,
                    reply_markup=prompt_library_item_kb(cat_idx, item_idx, item_kind=item_kind),
                )
                return
            except Exception:
                # Fallback: download image ourselves and send bytes to Telegram.
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            example_url,
                            timeout=aiohttp.ClientTimeout(total=30),
                            allow_redirects=True,
                        ) as img_resp:
                            if img_resp.status == 200:
                                img_bytes = await img_resp.read()
                                photo_buffer = io.BytesIO(img_bytes)
                                photo_buffer.name = "prompt_example.jpg"
                                await query.message.reply_photo(
                                    photo=photo_buffer,
                                    caption=card_text,
                                    reply_markup=prompt_library_item_kb(cat_idx, item_idx, item_kind=item_kind),
                                )
                                return
                except Exception:
                    logger.exception("Failed to send prompt example image with fallback")

        await query.message.reply_text(
            card_text,
            reply_markup=prompt_library_item_kb(cat_idx, item_idx, item_kind=item_kind),
        )
        return

    if query.data.startswith("pl_use_"):
        try:
            _, _, cat_raw, item_raw = query.data.split("_", 3)
            cat_idx = int(cat_raw)
            item_idx = int(item_raw)
            item = PROMPT_LIBRARY[cat_idx]["items"][item_idx]
            item_kind = get_prompt_item_kind(item)
        except Exception:
            await query.message.reply_text("Не удалось применить стиль. Попробуй ещё раз.")
            return

        state = get_or_init_state(context)
        if item_kind == "video":
            state.video_prompt = str(item.get("prompt") or item.get("title") or "").strip()
            state.video_session_active = True
            state.waiting_for_video_image = True
            await query.message.reply_text(
                f"Готово ✨\nСтиль «{_showcase_item_label(item)}» применён для видео.\n"
                "Теперь отправь фото и запускай видео.",
                reply_markup=video_kb(state),
            )
            return
        deactivate_video_session(state)
        state.prompt = item["prompt"]
        await query.message.reply_text(
            f"Готово ✨\nСтиль «{_showcase_item_label(item)}» применён.\n"
            "Нажми «Запустить генерацию ⚡» или отправь своё фото.",
            reply_markup=main_menu_kb(),
        )
        return

    if query.data == "plsave_cancel":
        context.user_data.pop("pending_pl_save", None)
        await query.message.reply_text("Сохранение в библиотеку отменено.", reply_markup=main_menu_kb())
        return

    if query.data.startswith("plsave_cat_"):
        pending = context.user_data.get("pending_pl_save")
        if not pending:
            await query.message.reply_text("Нет данных для сохранения. Сначала вызови /pl_save.")
            return

        try:
            cat_idx = int(query.data.replace("plsave_cat_", "", 1))
            data = load_prompt_library()
            if cat_idx < 0 or cat_idx >= len(data):
                raise ValueError("invalid category index")

            data[cat_idx].setdefault("items", [])
            item_kind = str(pending.get("item_kind") or "image").strip().lower()
            added_at_iso = datetime.utcnow().isoformat()
            # Auto-generate short description for webapp cards
            _desc = (pending.get("description") or "").strip()
            if not _desc:
                _raw_prompt = (pending.get("prompt") or "").strip()
                _desc = _raw_prompt[:120].replace("\n", " ").strip()
                if len(_raw_prompt) > 120:
                    _desc += "..."
            _hint = (pending.get("upload_hint") or "Фото лица").strip()

            if item_kind == "video":
                data[cat_idx]["items"].append(
                    {
                        "title": pending["title"],
                        "prompt": pending["prompt"],
                        "type": "video",
                        "video_url": pending["video_url"],
                        "poster_url": pending.get("poster_url") or "",
                        "added_at": added_at_iso,
                        "description": _desc,
                        "upload_hint": _hint,
                    }
                )
            else:
                image_url = pending["image_url"]
                stable_example_url = ""
                if _is_img_ref(image_url):
                    img_b = _resolve_image_bytes(image_url)
                    if img_b:
                        stable_example_url = await _upload_bytes_to_freeimage(img_b, "example.jpg")
                        if not stable_example_url:
                            stable_example_url = await _upload_bytes_to_catbox(img_b, "example.jpg")
                        if not stable_example_url:
                            stable_example_url = await _upload_bytes_to_imgbb(img_b, "example.jpg")
                    # Never save an __img__ ref as example_url — it won't survive a restart
                    if not stable_example_url:
                        await query.answer("Не удалось загрузить изображение на хостинг — сохранение без картинки.", show_alert=False)
                else:
                    stable_example_url = await upload_image_url_to_imgbb(image_url)
                    if not stable_example_url:
                        stable_example_url = image_url
                data[cat_idx]["items"].append(
                    {
                        "title": pending["title"],
                        "prompt": pending["prompt"],
                        "example_url": stable_example_url,
                        "added_at": added_at_iso,
                        "description": _desc,
                        "upload_hint": _hint,
                    }
                )

            await _locked_save_and_refresh(data)
            context.user_data.pop("pending_pl_save", None)

            await query.message.reply_text(
                f"Готово ✅\nШаблон «{pending['title']}» добавлен в категорию «{data[cat_idx].get('title', 'Без названия')}».",
                reply_markup=main_menu_kb(),
            )
            return
        except Exception:
            logger.exception("Failed to save prompt library item via category picker")
            context.user_data.pop("pending_pl_save", None)  # clear stale state on error
            await query.message.reply_text("Не удалось сохранить шаблон. Попробуй ещё раз.")
            return

    callback_data = query.data or ""
    video_cb = callback_data
    if callback_data.startswith("mc_"):
        video_cb = f"video_{callback_data[3:]}"
    elif callback_data == "seedance_control":
        video_cb = "video"

    video_callbacks = {
        "video",
        "video_set_prompt",
        "video_set_image",
        "video_clear_images",
        "video_set_video",
        "video_start",
        "seedance_retry",
    }
    is_video_callback = (
        video_cb in video_callbacks
        or video_cb.startswith("video_duration_")
        or video_cb.startswith("video_model_")
        or video_cb.startswith("video_mode_")
        or video_cb.startswith("video_delimg_")
        or video_cb.startswith("video_aspect_")
        or video_cb.startswith("video_longer_")
        or video_cb == "video_upgrade_seedance2"
    )

    if is_video_callback and not SEEDANCE_ENABLED:
        await query.message.reply_text(video_unavailable_text(), reply_markup=main_menu_kb())
        return

    if query.data == "generate":
        state = get_or_init_state(context)
        was_in_video = state.video_session_active
        deactivate_video_session(state)
        if was_in_video and not state.prompt:
            await query.message.reply_text(
                "Режим видео закрыт. Напиши описание и нажми «Запустить генерацию ⚡»."
            )
            return
        await run_generation(update, context)
        return

    if query.data == "image_model_menu":
        state = get_or_init_state(context)
        await query.message.reply_text(
            image_model_menu_text(state),
            reply_markup=image_model_menu_kb(state),
        )
        return

    if query.data in ("image_model_set_gemini", "image_model_set_gpt5"):
        state = get_or_init_state(context)
        picked = "gpt5" if query.data == "image_model_set_gpt5" else "gemini"
        if picked == "gpt5" and not GPT5_IMAGE_ENABLED:
            await query.answer("GPT-5 Image временно недоступна.", show_alert=True)
            return
        state.image_model = picked
        await query.answer(f"Модель: {get_image_model_label(picked)} ✅")
        try:
            await query.message.edit_text(
                image_model_menu_text(state),
                reply_markup=image_model_menu_kb(state),
            )
        except BadRequest:
            pass
        return

    if query.data == "generate_again":
        state = get_or_init_state(context)
        deactivate_video_session(state)
        user_id = update.effective_user.id
        saved_prompt = (last_generated_prompt.get(user_id) or "").strip()
        if not saved_prompt:
            await query.message.reply_text(
                "Не нашла прошлое описание. Напиши новый текст и нажми «Запустить генерацию ⚡»."
            )
            return

        state = get_or_init_state(context)
        deactivate_video_session(state)
        state.prompt = saved_prompt
        # Keep refs that are still usable: persistent URLs + __img__ refs still in cache.
        # __img__ refs evaporate on bot restart, so drop the ones that no longer resolve.
        saved_refs = [
            r for r in (last_generation_references.get(user_id) or [])
            if not _is_img_ref(r) or _resolve_image_bytes(r) is not None
        ]
        state.references = saved_refs
        if not saved_refs:
            avatar_url_repeat = get_avatar_url(user.id)
            if not avatar_url_repeat:
                await query.message.reply_text(
                    "ℹ️ Фото не сохранились (были загружены временно).\n"
                    "Генерирую без фото."
                )
        await run_generation(update, context)
        return

    if query.data == "animate_last":
        if not SEEDANCE_ENABLED:
            await query.message.reply_text(video_unavailable_text(), reply_markup=main_menu_kb())
            return
        state = get_or_init_state(context)
        last_img = last_generated_image_url.get(user.id)
        if last_img and _is_img_ref(last_img) and _resolve_image_bytes(last_img) is None:
            last_img = None
        if not last_img:
            await query.message.reply_text(
                "Не нашла свежую генерацию — она могла устареть.\n"
                "Сгенерируй картинку заново и нажми «Оживить 🎬» под результатом."
            )
            return
        state.video_session_active = True
        state.waiting_for_video_prompt = False
        state.waiting_for_video_image = True
        state.waiting_for_motion_video = False
        set_video_image_urls(state, [last_img])
        await query.message.reply_text(
            "Картинка добавлена в видео-буфер 🎬\n"
            "Можешь описать, что должно происходить в кадре, выбрать модель и длительность — "
            "или сразу жми «Запустить видео ⚡»."
        )
        await query.message.reply_text(
            video_status_text(state),
            reply_markup=video_kb(state),
        )
        return

    if video_cb.startswith("video_longer_") or video_cb == "video_upgrade_seedance2":
        user_u = update.effective_user
        if user_u.id in queued_user_ids or user_u.id in processing_user_ids:
            await query.answer("Уже выполняется другая задача. Подожди.", show_alert=False)
            return
        params = last_video_params.get(user_u.id)
        if not isinstance(params, dict) or not params.get("model"):
            await query.message.reply_text(
                "Не нашла параметры прошлого видео — возможно, бот перезапускался.\n"
                "Открой «Видео 🎬» и запусти заново.",
                reply_markup=main_menu_kb(),
            )
            return
        refs = [r for r in (params.get("refs") or []) if isinstance(r, str) and r.strip()]
        if any(_is_img_ref(r) and _resolve_image_bytes(r) is None for r in refs):
            await query.message.reply_text(
                "Исходное фото устарело (бот перезапускался).\n"
                "Открой «Видео 🎬», загрузи фото и запусти заново.",
                reply_markup=main_menu_kb(),
            )
            return
        state = get_or_init_state(context)
        state.video_model = params["model"]
        state.video_mode = params.get("mode")
        state.video_aspect_ratio = params.get("aspect") or "16:9"
        state.video_prompt = params.get("prompt") or ""
        set_video_image_urls(state, refs)
        if video_cb == "video_upgrade_seedance2":
            state.video_model = "seedance2"
            try:
                state.video_duration = int(params.get("duration") or SEEDANCE_DURATION)
            except (TypeError, ValueError):
                state.video_duration = int(SEEDANCE_DURATION)
        else:
            try:
                picked_longer = int(video_cb.replace("video_longer_", "", 1))
            except ValueError:
                picked_longer = int(SEEDANCE_DURATION)
            longer_options = get_seedance_duration_options(get_video_model(state))
            if picked_longer not in longer_options:
                picked_longer = max(longer_options)
            state.video_duration = picked_longer
        state.waiting_for_video_image = False
        state.video_session_active = False
        logger.info(
            "video_upsell: user=%s action=%s model=%s duration=%s",
            user_u.id, video_cb, state.video_model, state.video_duration,
        )
        # Add to processing_user_ids BEFORE create_task to close the race window
        processing_user_ids.add(user_u.id)
        try:
            context.application.create_task(run_seedance(update, context))
        except Exception:
            processing_user_ids.discard(user_u.id)
            logger.exception("create_task(run_seedance upsell) failed for user=%s", user_u.id)
            await query.answer("Не удалось запустить генерацию. Попробуй ещё раз.", show_alert=True)
        return

    if video_cb == "video":
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_prompt = False
        state.waiting_for_video_image = True
        state.waiting_for_motion_video = False

        await query.message.reply_text(
            "Режим видео включён 🎬\n"
            "Можно сразу отправлять текст описания и фото без дополнительных кнопок.\n"
            "Я сохраню всё в видео-буфер.\n\n"
            "Дальше выбери модель, длительность/качество и нажми «Запустить ⚡».",
        )
        await query.message.reply_text(
            video_status_text(state),
            reply_markup=video_kb(state),
        )
        return

    if video_cb == "video_set_prompt":
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_prompt = True
        await query.message.reply_text("Напиши описание для видео одним сообщением.")
        return

    if video_cb == "video_set_image":
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_image = True
        await query.message.reply_text(
            "Отправляй фото для Seedance (можно несколько подряд).\n"
            f"Лимит: до {MAX_SEEDANCE_IMAGE_REFERENCES} фото.\n"
            "Бот запомнит внешность с фото и перенесёт в видео.\n"
            "Когда всё загрузишь, нажми «Запустить ⚡»."
        )
        return

    if video_cb == "video_clear_images":
        state = get_or_init_state(context)
        set_video_image_urls(state, [])
        state.waiting_for_video_image = True
        state.video_session_active = True
        await query.message.reply_text(
            "Фото очищены ✅\n\n" + video_status_text(state),
            reply_markup=video_kb(state),
        )
        return

    if video_cb.startswith("video_aspect_"):
        state = get_or_init_state(context)
        state.video_session_active = True
        picked_ar = video_cb.replace("video_aspect_", "", 1).replace("x", ":")
        if picked_ar in {"16:9", "9:16", "1:1"}:
            state.video_aspect_ratio = picked_ar
        await query.message.reply_text(
            video_status_text(state),
            reply_markup=video_kb(state),
        )
        return

    if video_cb.startswith("video_delimg_"):
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_image = True
        video_images = get_video_image_urls(state)
        try:
            idx = int(video_cb.replace("video_delimg_", "", 1))
        except ValueError:
            idx = -1

        if idx < 1 or idx > len(video_images):
            await query.message.reply_text(
                "Не нашла этот референс в буфере.",
                reply_markup=video_kb(state),
            )
            return

        removed_url = video_images.pop(idx - 1)
        set_video_image_urls(state, video_images)
        removed_text = str(removed_url or "").strip()
        if len(removed_text) > 96:
            removed_text = f"{removed_text[:60]}...{removed_text[-28:]}"
        await query.message.reply_text(
            f"Удалён референс #{idx} ✅\n{removed_text}\n\n{video_status_text(state)}",
            reply_markup=video_kb(state),
        )
        return

    if video_cb == "video_set_video":
        await query.message.reply_text("Для этой модели этот шаг не нужен.")
        return

    if video_cb.startswith("video_model_"):
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_image = True
        picked_model = video_cb.replace("video_model_", "", 1)
        if picked_model == "seedance2_fast" and SEEDANCE_FAST_ENABLED:
            state.video_model = "seedance2_fast"
            state.video_mode = normalize_seedance_mode(SEEDANCE_FAST_MODE)
        elif picked_model == "kling3" and KLING3_ENABLED:
            state.video_model = "kling3"
            state.video_mode = "720p"
        elif picked_model == "veo31" and VEO31_ENABLED:
            state.video_model = "veo31"
            state.video_mode = "720p"
            if state.video_aspect_ratio == "1:1":
                state.video_aspect_ratio = "16:9"
        else:
            state.video_model = "seedance2"
            if not state.video_mode:
                state.video_mode = normalize_seedance_mode(SEEDANCE_MODE)
        await query.message.reply_text(
            video_status_text(state),
            reply_markup=video_kb(state),
        )
        return

    if video_cb.startswith("video_mode_"):
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_image = True
        selected_model = get_video_model(state)
        if selected_model != "seedance2":
            await query.message.reply_text(
                video_status_text(state),
                reply_markup=video_kb(state),
            )
            return
        picked_mode = normalize_seedance_mode(video_cb.replace("video_mode_", "", 1))
        if picked_mode not in get_seedance_mode_options(selected_model):
            picked_mode = get_selected_seedance_mode(state)
        state.video_mode = picked_mode
        await query.message.reply_text(
            video_status_text(state),
            reply_markup=video_kb(state),
        )
        return

    if video_cb.startswith("video_duration_"):
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_image = True
        try:
            picked = int(video_cb.replace("video_duration_", "", 1))
        except ValueError:
            picked = get_selected_seedance_duration(state)

        selected_model = get_video_model(state)
        if picked not in get_seedance_duration_options(selected_model):
            picked = get_selected_seedance_duration(state)

        state.video_duration = picked
        await query.message.reply_text(
            video_status_text(state),
            reply_markup=video_kb(state),
        )
        return

    if video_cb == "video_start":
        user_vs = update.effective_user
        if user_vs.id in queued_user_ids or user_vs.id in processing_user_ids:
            await query.answer("Уже выполняется другая задача. Подожди.", show_alert=False)
            return
        state = get_or_init_state(context)
        logger.info(
            "video_start: user=%s animation_source_urls=%s video_prompt=%r",
            user_vs.id, state.animation_source_urls, state.video_prompt,
        )
        if not state.animation_source_urls and not (state.video_prompt or "").strip():
            msg_date = getattr(query.message, "date", None)
            if msg_date and msg_date.replace(tzinfo=None) < BOT_START_TIME:
                await query.message.reply_text(
                    "Бот перезапускался и сессия сброшена.\n"
                    "Открой Seedance заново, добавь фото и описание — и запускай.",
                    reply_markup=main_menu_kb(),
                )
                return
        state.waiting_for_video_image = False
        state.video_session_active = False
        # Add to processing_user_ids BEFORE create_task to close the race window
        processing_user_ids.add(user_vs.id)
        try:
            context.application.create_task(run_seedance(update, context))
        except Exception:
            processing_user_ids.discard(user_vs.id)
            logger.exception("create_task(run_seedance) failed for user=%s", user_vs.id)
            await query.answer("Не удалось запустить генерацию. Попробуй ещё раз.", show_alert=True)
        return

    if query.data == "seedance_retry":
        user_r = update.effective_user
        if user_r.id in queued_user_ids or user_r.id in processing_user_ids:
            await query.answer("Уже выполняется другая задача. Подожди.", show_alert=False)
            return
        state = get_or_init_state(context)
        state.video_session_active = False
        processing_user_ids.add(user_r.id)
        try:
            context.application.create_task(run_seedance(update, context))
        except Exception:
            processing_user_ids.discard(user_r.id)
            logger.exception("create_task(run_seedance retry) failed for user=%s", user_r.id)
            await query.answer("Не удалось запустить генерацию. Попробуй ещё раз.", show_alert=True)
        return

    if query.data == "avatar_actions":
        await query.message.reply_text(
            "🪄 AI-аватар — это ты в любом образе\n\n"
            "Загрузи 3–10 своих фото, и нейросеть запомнит твою внешность.\n"
            "После этого в каждой генерации будешь появляться именно ты — "
            "хоть в образе киберпанк-воина, хоть на обложке журнала.\n\n"
            "Это то, чего нет у большинства конкурентов 💪",
            reply_markup=avatar_actions_kb(user.id),
        )
        return

    if query.data == "avatar_gen_refsheet":
        state = get_or_init_state(context)
        deactivate_video_session(state)
        state.prompt = AVATAR_REFSHEET_PROMPT
        state.references = []
        state.avatar_photos = []
        state.avatar_status_msg_id = None
        state.generating_avatar = True
        await query.message.reply_text(
            "Отправь фото для генерации аватара 📸\n\n"
            "Чем больше фото с разных ракурсов — тем лучше результат.\n"
            "Важно: на фото должно быть хорошо видно лицо.\n\n"
            "Когда загрузишь все фото — нажми «Готово».",
        )
        return

    if query.data == "avatar_gen_start":
        state = get_or_init_state(context)
        photos = list(state.avatar_photos)
        if not photos:
            await query.answer("Сначала отправь хотя бы одно фото.", show_alert=True)
            return

        if user.id in queued_user_ids or user.id in processing_user_ids:
            await query.answer("Сырник уже занят другой задачей. Подожди.", show_alert=True)
            return

        # Charge for avatar generation like a normal image
        avatar_cost = BASE_GENERATION_COST
        avatar_use_free = try_use_free_generation(user.id, FREE_GENERATIONS_PER_DAY)
        avatar_paid = False
        if not avatar_use_free:
            bal = get_balance(user.id)
            if bal < avatar_cost:
                await query.message.reply_text(
                    f"Не хватает изюминок для генерации аватара.\n"
                    f"Нужно: {avatar_cost}\nУ тебя: {bal}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("💳 Купить изюминки", callback_data="show_buy")
                    ]])
                )
                return
            if not spend_izyminki(user.id, avatar_cost):
                await query.message.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
                return
            avatar_paid = True

        state.generating_avatar = False
        state.avatar_photos = []
        job = GenerationJob(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            prompt=AVATAR_REFSHEET_PROMPT,
            references=photos,
            cost=avatar_cost if avatar_paid else 0,
            was_free=avatar_use_free,
            save_as_avatar=True,
            avatar_kind=getattr(state, "pending_avatar_kind", "female") or "female",
        )
        queued_user_ids.add(user.id)
        try:
            generation_queue.put_nowait(job)
        except asyncio.QueueFull:
            queued_user_ids.discard(user.id)
            if avatar_paid:
                add_izyminki(user.id, avatar_cost)
            elif avatar_use_free:
                restore_free_generation(user.id)
            await query.message.reply_text("Сырник сейчас очень занят — очередь переполнена 😔 Попробуй через минуту.")
            return
        except BaseException:
            queued_user_ids.discard(user.id)
            if avatar_paid:
                add_izyminki(user.id, avatar_cost)
            elif avatar_use_free:
                restore_free_generation(user.id)
            logger.exception("Failed to enqueue avatar job for user=%s", user.id)
            await query.message.reply_text("Не удалось запустить генерацию. Попробуй ещё раз.")
            raise
        context.user_data["state"] = UserState()
        await query.message.reply_text(
            f"Запускаю генерацию аватара по {len(photos)} фото… ✨",
            reply_markup=main_menu_kb(),
        )
        return

    if query.data == "avatar_help":
        await query.answer()
        await query.message.reply_text(
            "🪄 AI-аватар — это твоя внешность в боте.\n\n"
            "Загрузи 3–10 своих фото лица с разных ракурсов → "
            "бот запомнит как ты выглядишь → "
            "дальше ты будешь появляться в любом образе на каждой картинке.\n\n"
            "Аватар необязателен — без него тоже можно генерировать."
        )
        return

    if query.data == "avatar_back_menu":
        await query.message.reply_text(
            "Главное меню:",
            reply_markup=main_menu_kb(),
        )
        return

    if query.data == "show_help":
        user = update.effective_user
        bal = get_balance(user.id)
        await query.message.reply_text(
            "🧀 Как пользоваться Сырником\n\n"
            "1. Напиши описание картинки (например: «девушка на фоне заката»)\n"
            "   или выбери готовый стиль из библиотеки 📚\n"
            "2. Нажми «Запустить генерацию ⚡»\n"
            "3. Получи фото — готово!\n\n"
            "🪄 Аватар — загрузи свои фото, и бот поставит тебя в любой образ\n"
            "🎬 Видео — Seedance 2, Kling 3.0, Veo 3.1 (кнопка в меню)\n"
            f"💰 Баланс: {bal} изюминок (1 фото = {BASE_GENERATION_COST} изюминок)\n\n"
            "Изюминки — внутренняя валюта бота. Их можно купить или получить бесплатно, "
            "пригласив друга: /ref",
            reply_markup=main_menu_kb(),
        )
        return

    if query.data == "report_problem":
        state = get_or_init_state(context)
        state.waiting_for_problem_report = True
        await query.message.reply_text(
            "Опиши проблему одним сообщением.\n"
            "Я передам это в поддержку прямо сейчас.\n\n"
            "Если передумала, отправь: отмена"
        )
        return

    if query.data == "reset":
        context.user_data["state"] = UserState()
        await query.message.reply_text(
            "Готово — текущее описание и фото очищены.\n"
            "Баланс и аватары на месте. Можно начинать заново!",
            reply_markup=main_menu_kb(),
        )
        return
    
    if query.data.startswith("promo_try_"):
        promo_id = query.data.replace("promo_try_", "", 1)
        promo = get_promo_broadcast(promo_id)

        if not promo:
            await query.message.reply_text(
                "Этот стиль больше недоступен."
            )
            return

        state = get_or_init_state(context)
        deactivate_video_session(state)
        state.prompt = promo["promo_prompt"]

        register_promo_click(promo_id, update.effective_user.id)

        await query.message.reply_text(
            "Готово ✨\n"
            "Стиль применён ✅\n\n"
            "Нажми «Запустить генерацию ⚡» или отправь своё фото.",
            reply_markup=main_menu_kb()
        )
        return

    if query.data == "show_buy":
        await query.answer()
        await buy(update, context)
        return

    if query.data.startswith("buy_"):
        _, count_str, price_str = query.data.split("_")
        count = int(count_str)
        price = int(price_str)

        if not any(p["count"] == count and p["price"] == price for p in BUY_PACKS):
            await query.answer("Этот пакет больше не доступен.", show_alert=True)
            return

        # Debounce: prevent double-tap from sending two invoices
        buy_key = f"last_buy_invoice_{count}_{price}"
        now_ts = datetime.now().timestamp()
        last_sent = context.user_data.get(buy_key, 0)
        if now_ts - last_sent < 5:
            # Already sent an invoice for this pack in the last 5 seconds — skip silently
            return
        context.user_data[buy_key] = now_ts

        try:
            await send_invoice(update, context, count, price)
        except Exception:
            context.user_data.pop(buy_key, None)
            raise
        return
    
    if query.data in {"set_avatar", "set_avatar_female", "set_avatar_male", "set_avatar_child"}:
        state = get_or_init_state(context)
        kind_map = {
            "set_avatar": "female",
            "set_avatar_female": "female",
            "set_avatar_male": "male",
            "set_avatar_child": "child",
        }
        avatar_kind = kind_map.get(query.data, "female")
        state.waiting_for_avatar_upload = True
        state.pending_avatar_kind = avatar_kind

        await query.message.reply_text(
            f"Загрузи фото для аватара ({avatar_kind_label(avatar_kind)}) 📸\n\n"
            "Советы для лучшего результата:\n"
            "• Загрузи 3–10 фото лица с разных ракурсов\n"
            "• Фото должны быть чёткими, лицо хорошо видно\n"
            "• Разное освещение и выражение лица — плюс\n\n"
            "После сохранения аватар будет автоматически добавляться в каждую генерацию.",
        )
        return

    if query.data == "show_avatar":
        avatars = get_avatar_urls(update.effective_user.id)
        present = [(k, v) for k, v in avatars.items() if v]
        if not present:
            await query.message.reply_text("У тебя пока нет сохранённых аватаров.")
            return
        for kind, url in present:
            try:
                await query.message.reply_photo(
                    photo=url,
                    caption=f"Аватар: {avatar_kind_label(kind)}"
                )
            except Exception:
                logger.warning("show_avatar: failed to send photo url=%s kind=%s", url[:60], kind)
                clear_avatar_url(update.effective_user.id, kind)
                await query.message.reply_text(
                    f"Аватар «{avatar_kind_label(kind)}» недоступен (ссылка протухла) и удалён.\n"
                    "Загрузи новый аватар через меню."
                )
        return

    if query.data in {"delete_avatar", "delete_avatar_female", "delete_avatar_male", "delete_avatar_child"}:
        if query.data == "delete_avatar":
            clear_avatar_url(update.effective_user.id, "female")
            clear_avatar_url(update.effective_user.id, "male")
            clear_avatar_url(update.effective_user.id, "child")
            await query.message.reply_text("Все аватары удалены.")
            return
        kind_map = {
            "delete_avatar_female": "female",
            "delete_avatar_male": "male",
            "delete_avatar_child": "child",
        }
        avatar_kind = kind_map.get(query.data, "female")
        clear_avatar_url(update.effective_user.id, avatar_kind)
        await query.message.reply_text(f"Удалён {avatar_kind_label(avatar_kind)} аватар.")
        return

# ══════════════════════════════════════════════════════════════
# БИБЛИОТЕКА ПРОМТОВ: просмотр, редактирование, история
# ══════════════════════════════════════════════════════════════

async def promo_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /promo_stats <promo_id>")
        return

    promo_id = context.args[0]
    promo = get_promo_broadcast(promo_id)

    if not promo:
        await update.message.reply_text("Промо не найдено.")
        return

    stats = get_promo_stats(promo_id)

    await update.message.reply_text(
        f"Статистика промо\n\n"
        f"Promo ID: {promo_id}\n"
        f"Создано: {stats['created_at']}\n"
        f"Кликов по кнопке: {stats['clicks']}"
    )


async def audience_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    days = 30
    if context.args:
        try:
            days = max(1, min(int(context.args[0]), 365))
        except ValueError:
            await update.message.reply_text("Использование: /audience_stats [days]")
            return

    stats = get_audience_overview(days=days)

    top_lines = []
    for idx, row in enumerate(stats["top_generators"], start=1):
        username = row["username"] or "без username"
        top_lines.append(f"{idx}. {username} ({row['user_id']}) — {row['count']}")

    top_text = "\n".join(top_lines) if top_lines else "Пока нет данных за период."

    text = (
        f"Портрет аудитории за {stats['days']} дн.\n\n"
        f"Всего пользователей: {stats['total_users']}\n"
        f"Новые за 7 дней: {stats['new_users_7d']}\n"
        f"Новые за период: {stats['new_users_period']}\n"
        f"Пришли по рефералке: {stats['referred_users']} ({stats['referral_share']}%)\n\n"
        f"Активные (24ч): {stats['active_24h']}\n"
        f"Активные (7д): {stats['active_7d']}\n"
        f"Уникальные генераторы (за период): {stats['generators_period']}\n"
        f"Успешных генераций изображений: {stats['image_success_period']}\n"
        f"Среднее генераций на генератора: {stats['avg_per_generator']}\n\n"
        f"Платящих пользователей (за период): {stats['payers_period']}\n"
        f"Платежей (за период): {stats['payments_count_period']}\n"
        f"Куплено изюминок (за период): {stats['izyminki_sold_period']}\n\n"
        f"Топ-10 по генерациям:\n{top_text}"
    )

    await send_long_text(update.message, text)


async def prompt_library_save_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    image_url = last_generated_image_url.get(user.id)
    prompt_text = (last_generated_prompt.get(user.id) or "").strip()

    if not image_url:
        await update.message.reply_text(
            "Не нашла последнюю генерацию.\n"
            "Сначала сгенерируй картинку, потом вызови /pl_save."
        )
        return

    title = " ".join(context.args).strip()
    if not title:
        title = f"Мой шаблон {datetime.now().strftime('%d.%m %H:%M')}"

    context.user_data["pending_pl_save"] = {
        "title": title,
        "prompt": prompt_text or "Опирайся на пример изображения и сохрани стиль.",
        "image_url": image_url,
        "item_kind": "image",
    }

    await update.message.reply_text(
        f"Сохраняю шаблон «{title}».\n"
        "Теперь выбери категорию, куда добавить:",
        reply_markup=prompt_library_save_category_kb(),
    )


async def prompt_library_import_from_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    replied = update.message.reply_to_message
    if not replied:
        await update.message.reply_text(
            "Ответь командой /pl_import на сообщение с изображением.\n"
            "Формат: /pl_import <название> | <промпт>"
        )
        return

    raw = " ".join(context.args).strip()
    title = f"Импорт {datetime.now().strftime('%d.%m %H:%M')}"
    prompt_text = ""
    if raw:
        if "|" in raw:
            left, right = raw.split("|", 1)
            title = left.strip() or title
            prompt_text = right.strip()
        else:
            title = raw

    if not prompt_text:
        prompt_text = (replied.caption or replied.text or "").strip()
    if not prompt_text:
        prompt_text = (last_generated_prompt.get(user.id) or "").strip()
    if not prompt_text:
        prompt_text = "Опирайся на пример изображения и сохрани стиль."

    file_id = None
    filename = "import.jpg"
    if replied.photo:
        file_id = replied.photo[-1].file_id
    elif replied.document and (replied.document.mime_type or "").startswith("image/"):
        file_id = replied.document.file_id
        filename = replied.document.file_name or filename
    else:
        await update.message.reply_text("В реплае должно быть фото или документ-изображение.")
        return

    try:
        tg_file = await context.bot.get_file(file_id)
        bio = io.BytesIO()
        await tg_file.download_to_memory(out=bio)
        bio.seek(0)
        img_bytes = bio.read()
        stable_example_url = await upload_image_bytes_to_imgbb(img_bytes, filename=filename)
        if not stable_example_url:
            stable_example_url = _cache_image(img_bytes)
    except Exception:
        logger.exception("prompt_library_import_from_reply failed")
        await update.message.reply_text("Не удалось импортировать изображение из реплая.")
        return

    context.user_data["pending_pl_save"] = {
        "title": title,
        "prompt": prompt_text,
        "image_url": stable_example_url,
        "item_kind": "image",
    }

    await update.message.reply_text(
        f"Импорт готов ✅\nШаблон «{title}» подготовлен (с промптом).\nТеперь выбери категорию:",
        reply_markup=prompt_library_save_category_kb(),
    )


async def prompt_library_import_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    raw = " ".join(context.args).strip()
    if not raw and not update.message.reply_to_message:
        await update.message.reply_text(
            "Формат:\n"
            "/pl_import_video <название> | <промпт> | <video_url>\n\n"
            "Пример:\n"
            "/pl_import_video Эпик сцена | [Image1] и [Image2]... | https://site/video.mp4"
        )
        return

    title = f"Видео-шаблон {datetime.now().strftime('%d.%m %H:%M')}"
    prompt_text = ""
    video_url = ""

    if raw and "|" in raw:
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) >= 1 and parts[0]:
            title = parts[0]
        if len(parts) >= 2 and parts[1]:
            prompt_text = parts[1]
        if len(parts) >= 3 and parts[2]:
            video_url = parts[2]
    elif raw:
        title = raw

    replied = update.message.reply_to_message
    if replied:
        if not prompt_text:
            prompt_text = (replied.caption or replied.text or "").strip()
        if not video_url:
            video_url = _extract_first_http_url((replied.caption or "") + "\n" + (replied.text or ""))

    if not video_url:
        video_url = _extract_first_http_url(raw)

    if not prompt_text:
        prompt_text = "[Image1] и [Image2] — главные персонажи. Сохрани лица, стиль и детали внешности."

    if not (video_url.startswith("http://") or video_url.startswith("https://")):
        await update.message.reply_text(
            "Нужна публичная ссылка на видео-превью (http/https).\n"
            "Добавь её третьим параметром после второго «|»."
        )
        return

    context.user_data["pending_pl_save"] = {
        "title": title,
        "prompt": prompt_text,
        "item_kind": "video",
        "video_url": video_url,
        "poster_url": "",
    }
    await update.message.reply_text(
        f"Видео-шаблон «{title}» подготовлен ✅\n"
        "Теперь выбери категорию, куда добавить его в библиотеку.",
        reply_markup=prompt_library_save_category_kb(),
    )


def _extract_first_http_url(text: str) -> str:
    source = str(text or "")
    m = re.search(r"https?://\S+", source)
    if not m:
        return ""
    return m.group(0).rstrip(").,;]")


def _find_category_index_by_title(data: list, title: str) -> int:
    needle = (title or "").strip().lower()
    for idx, cat in enumerate(data):
        if str(cat.get("title", "")).strip().lower() == needle:
            return idx
    return -1


def _looks_like_emoji_token(token: str) -> bool:
    token = (token or "").strip()
    if not token or len(token) > 5:
        return False
    if any(ch.isalnum() for ch in token):
        return False
    return any(ord(ch) > 127 for ch in token)


def _parse_category_title_and_emoji(raw: str) -> tuple[str, str]:
    title = (raw or "").strip()
    emoji = "📁"
    parts = title.split(maxsplit=1)
    if len(parts) == 2:
        maybe_emoji = parts[0]
        if _looks_like_emoji_token(maybe_emoji):
            emoji = maybe_emoji
            title = parts[1].strip()
    return title, emoji


async def _create_prompt_library_category(raw_title: str) -> tuple[bool, str]:
    title, emoji = _parse_category_title_and_emoji(raw_title)
    if not title:
        return False, "Название категории пустое."

    data = load_prompt_library()
    if _find_category_index_by_title(data, title) >= 0:
        return False, f"Категория «{title}» уже существует."

    data.append({"title": title, "emoji": emoji, "items": []})
    await _locked_save_and_refresh(data)
    return True, f"Готово ✅ Категория «{title}» создана."


async def prompt_library_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    raw = " ".join(context.args).strip()
    if not raw:
        await update.message.reply_text(
            "Использование:\n"
            "/pl_newcat <название>\n\n"
            "Пример:\n"
            "/pl_newcat Женские образы"
        )
        return

    try:
        _, message = await _create_prompt_library_category(raw)
        await update.message.reply_text(message)
    except Exception:
        logger.exception("Failed to create prompt library category")
        await update.message.reply_text("Не удалось создать категорию. Попробуй еще раз.")


async def prompt_library_rename_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    raw = " ".join(context.args).strip()
    if "|" not in raw:
        await update.message.reply_text(
            "Использование:\n"
            "/pl_renamecat <старое название> | <новое название>\n\n"
            "Пример:\n"
            "/pl_renamecat Портреты | Портреты Pro"
        )
        return

    old_title, new_title = [x.strip() for x in raw.split("|", 1)]
    if not old_title or not new_title:
        await update.message.reply_text("Нужно указать и старое, и новое название.")
        return

    try:
        data = load_prompt_library()
        old_idx = _find_category_index_by_title(data, old_title)
        if old_idx < 0:
            await update.message.reply_text(f"Категория «{old_title}» не найдена.")
            return

        if _find_category_index_by_title(data, new_title) >= 0:
            await update.message.reply_text(f"Категория «{new_title}» уже существует.")
            return

        data[old_idx]["title"] = new_title
        await _locked_save_and_refresh(data)
        await update.message.reply_text(f"Готово ✅ Категория переименована в «{new_title}».")
    except Exception:
        logger.exception("Failed to rename prompt library category")
        await update.message.reply_text("Не удалось переименовать категорию. Попробуй еще раз.")


async def prompt_library_delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    title = " ".join(context.args).strip()
    if not title:
        await update.message.reply_text(
            "Использование:\n"
            "/pl_delcat <название>\n\n"
            "Пример:\n"
            "/pl_delcat Креатив"
        )
        return

    try:
        data = load_prompt_library()
        idx = _find_category_index_by_title(data, title)
        if idx < 0:
            await update.message.reply_text(f"Категория «{title}» не найдена.")
            return

        removed = data.pop(idx)
        await _locked_save_and_refresh(data)
        await update.message.reply_text(
            f"Готово ✅ Категория «{removed.get('title', title)}» удалена."
        )
    except Exception:
        logger.exception("Failed to delete prompt library category")
        await update.message.reply_text("Не удалось удалить категорию. Попробуй еще раз.")

async def prompt_library_admin_help_legacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    await update.message.reply_text(
        "Управление библиотекой:\n\n"
        "/pl_list — список категорий\n"
        "/pl_save [название] — сохранить последнюю генерацию\n"
        "/pl_import_video <название> | <промпт> | <video_url> — добавить видео-шаблон Seedance\n"
        "/pl_newcat <название> — новая категория\n"
        "/pl_renamecat <старое> | <новое> — переименовать категорию\n"
        "/pl_delcat <название> — удалить категорию\n"
        "/pl_export — выгрузить свежий prompt_library.json"
    )


async def prompt_library_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if not is_admin(user.id):
        await message.reply_text("У тебя нет доступа к этой команде.")
        return

    data = load_prompt_library()
    if not data:
        await message.reply_text("Библиотека пока пустая.")
        return

    lines = ["Категории библиотеки:\n"]
    for idx, cat in enumerate(data, start=1):
        title = str(cat.get("title") or f"Категория {idx}")
        emoji = str(cat.get("emoji") or "📁")
        items_count = len(cat.get("items") or [])
        lines.append(f"{idx}. {emoji} {title} — {items_count} шаблон(ов)")

    await send_long_text(message, "\n".join(lines))


async def prompt_library_where(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if not is_admin(user.id):
        await message.reply_text("У тебя нет доступа к этой команде.")
        return

    _bootstrap_prompt_library_primary()
    active_path = PROMPT_LIBRARY_PRIMARY_PATH if os.path.exists(PROMPT_LIBRARY_PRIMARY_PATH) else None

    if not active_path:
        await message.reply_text("Файл библиотеки не найден.")
        return

    mtime = datetime.fromtimestamp(os.path.getmtime(active_path)).strftime("%Y-%m-%d %H:%M:%S")
    cats = len(PROMPT_LIBRARY)
    items = sum(len(cat.get("items", [])) for cat in PROMPT_LIBRARY if isinstance(cat, dict))
    await message.reply_text(
        "Текущий источник библиотеки:\n"
        f"{active_path}\n\n"
        f"WebApp URL: {PROMPT_WEBAPP_URL or 'не задан'}\n\n"
        f"Обновлен: {mtime}\n"
        f"Категорий: {cats}\n"
        f"Шаблонов: {items}"
    )


async def prompt_library_sync_from_cloudflare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force-pull prompt_library.json from Cloudflare Pages, overwrite local copy."""
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if not is_admin(user.id):
        await message.reply_text("У тебя нет доступа к этой команде.")
        return

    if not PROMPT_LIBRARY_REMOTE_URL:
        await message.reply_text("PROMPT_LIBRARY_REMOTE_URL не задан в .env")
        return

    await message.reply_text("⏳ Синхронизирую с Cloudflare…")
    try:
        import urllib.request as _req
        req = _req.Request(
            PROMPT_LIBRARY_REMOTE_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SirNikeBot/1.0)"},
        )
        with _req.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        data = json.loads(raw)
        if not isinstance(data, list):
            await message.reply_text("❌ Ответ с Cloudflare не является списком категорий.")
            return
        primary_dir = os.path.dirname(PROMPT_LIBRARY_PRIMARY_PATH)
        if primary_dir:
            os.makedirs(primary_dir, exist_ok=True)
        async with _get_prompt_library_lock():
            with open(PROMPT_LIBRARY_PRIMARY_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            refresh_prompt_library()
        total = sum(len(c.get("items", [])) for c in data)
        await message.reply_text(
            f"✅ Библиотека обновлена с Cloudflare.\n"
            f"Категорий: {len(data)}, шаблонов: {total}"
        )
        logger.info("Prompt library force-synced from Cloudflare by admin %s", user.id)
    except Exception as e:
        logger.exception("Failed to force-sync prompt library from Cloudflare")
        await message.reply_text(f"❌ Ошибка синхронизации: {e}")


async def prompt_library_list_backups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available backup files and send the requested one."""
    user = update.effective_user
    message = update.effective_message
    if not message or not is_admin(user.id):
        return

    backup_dir = os.path.join(DATA_DIR, "pl_backups")
    args = (context.args or [])

    # If a number is passed — send that backup file
    if args and args[0].isdigit():
        idx = int(args[0])
        try:
            files = sorted(os.listdir(backup_dir), reverse=True)
            if idx < 1 or idx > len(files):
                await message.reply_text(f"Нет бэкапа №{idx}. Всего бэкапов: {len(files)}")
                return
            path = os.path.join(backup_dir, files[idx - 1])
            with open(path, encoding="utf-8") as _f:
                data = json.load(_f)
            total = sum(len(c.get("items", [])) for c in data)
            with open(path, "rb") as f:
                doc = io.BytesIO(f.read())
            doc.name = files[idx - 1]
            await message.reply_document(
                document=doc,
                caption=f"Бэкап №{idx}: {files[idx - 1]}\nКатегорий: {len(data)}, шаблонов: {total}",
            )
        except Exception:
            logger.exception("Failed to send backup")
            await message.reply_text("Не удалось отправить бэкап.")
        return

    # No args — list backups
    if not os.path.isdir(backup_dir):
        await message.reply_text("Папка бэкапов не найдена.")
        return
    files = sorted(os.listdir(backup_dir), reverse=True)
    if not files:
        await message.reply_text("Бэкапов нет.")
        return
    lines = []
    for i, name in enumerate(files[:20], 1):
        path = os.path.join(backup_dir, name)
        try:
            with open(path, encoding="utf-8") as _f:
                data = json.load(_f)
            total = sum(len(c.get("items", [])) for c in data)
            lines.append(f"{i}. {name} — {total} шаблонов")
        except Exception:
            lines.append(f"{i}. {name} — (ошибка чтения)")
    await message.reply_text(
        "Бэкапы (новые сверху):\n\n" + "\n".join(lines) +
        "\n\nЧтобы скачать: /pl_backups <номер>"
    )


async def prompt_library_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if not is_admin(user.id):
        await message.reply_text("У тебя нет доступа к этой команде.")
        return

    try:
        data = load_prompt_library()
        await _locked_save_and_refresh(data)

        with open(PROMPT_LIBRARY_PRIMARY_PATH, "rb") as f:
            payload = f.read()

        doc = io.BytesIO(payload)
        doc.name = "prompt_library.json"
        await message.reply_document(
            document=doc,
            caption=(
                "Готово ✅ Экспорт свежий.\n"
                "Файл синхронизирован с ботом. Для Netlify перезалей папку webapp."
            ),
        )
    except Exception:
        logger.exception("Failed to export prompt library")
        await message.reply_text("Не удалось сделать экспорт библиотеки.")


async def prompt_library_history(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0):
    user = update.effective_user
    if not is_admin(user.id):
        await update.effective_message.reply_text("У тебя нет доступа к этой команде.")
        return

    page_size = 5
    items = get_generation_history(user.id, limit=page_size, offset=max(0, offset))
    if not items:
        await update.effective_message.reply_text(
            "История генераций пока пустая. Сначала сделай несколько генераций.",
            reply_markup=prompt_library_admin_kb(),
        )
        return

    lines = ["Выбери генерацию для экспорта в библиотеку:"]
    for idx, item in enumerate(items, start=1):
        created_at = (item.get("created_at") or "").replace("T", " ")[:16]
        lines.append(f"{idx + offset}. {created_at}")

    await update.effective_message.reply_text(
        "\n".join(lines),
        reply_markup=prompt_history_kb(items, offset=offset, page_size=page_size),
    )


async def prompt_library_admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return
    await update.message.reply_text(
        "Открыла кнопочный админ-редактор библиотеки.",
        reply_markup=prompt_library_admin_kb(),
    )


async def prompt_library_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    offset = 0
    if context.args:
        try:
            offset = max(0, int(context.args[0]))
        except ValueError:
            offset = 0
    await prompt_library_history(update, context, offset=offset)


# ══════════════════════════════════════════════════════════════
# ОЧЕРЕДЬ И ЖИЗНЕННЫЙ ЦИКЛ БОТА: worker, post_init, shutdown
# ══════════════════════════════════════════════════════════════

_worker_current_job = None  # tracks the job being processed right now


async def _queue_worker_supervised(app: Application):
    """Wraps queue_worker with auto-restart on unexpected crash."""
    while True:
        try:
            await queue_worker(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("queue_worker crashed unexpectedly — restarting in 3s")
            processing_user_ids.clear()
            queued_user_ids.clear()

            # Refund the job that was actively being processed when the crash happened
            _crashed_job = _worker_current_job
            if _crashed_job is not None:
                try:
                    if getattr(_crashed_job, "cost", 0) > 0:
                        add_izyminki(_crashed_job.user_id, _crashed_job.cost)
                    if getattr(_crashed_job, "was_free", False):
                        restore_free_generation(_crashed_job.user_id)
                    await app.bot.send_message(
                        chat_id=_crashed_job.chat_id,
                        text="Сырник споткнулся и потерял твою задачу 😔 Изюминки возвращены — попробуй ещё раз."
                    )
                except Exception:
                    logger.exception("Failed to refund current job after crash user=%s", getattr(_crashed_job, "user_id", "?"))

            # Drain pending jobs and refund all waiting users
            drained = 0
            while not generation_queue.empty():
                try:
                    pending_job = generation_queue.get_nowait()
                    generation_queue.task_done()
                    drained += 1
                    try:
                        if getattr(pending_job, "cost", 0) > 0:
                            add_izyminki(pending_job.user_id, pending_job.cost)
                        if getattr(pending_job, "was_free", False):
                            restore_free_generation(pending_job.user_id)
                        await app.bot.send_message(
                            chat_id=pending_job.chat_id,
                            text="Сырник споткнулся и потерял твою задачу 😔 Изюминки возвращены — попробуй ещё раз."
                        )
                    except Exception:
                        logger.exception("Failed to refund drained job user=%s", getattr(pending_job, "user_id", "?"))
                except Exception:
                    break
            if drained:
                logger.warning("Drained %d pending jobs from queue after worker crash", drained)
            await asyncio.sleep(3)


def _push_log_to_github() -> None:
    """Пушит текущий лог-файл в GitHub logs/YYYY-MM-DD.log и удаляет файлы старше 7 дней."""
    if not GITHUB_TOKEN or not LOG_FILE_PATH or not os.path.exists(LOG_FILE_PATH):
        return
    import urllib.request as _req
    import base64 as _b64

    def _gh(method, path, body=None):
        url = f"https://api.github.com{path}"
        data = json.dumps(body).encode() if body else None
        req = _req.Request(url, data=data, method=method)
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "SirnikeBot/1.0")
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            with _req.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("GitHub log push error %s %s: %s", method, path, e)
            return None

    # Читаем последние 500KB лога
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 500 * 1024))
            content = f.read()
    except Exception as e:
        logger.warning("Failed to read log file: %s", e)
        return

    today = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = f"/repos/{GITHUB_REPO}/contents/logs/{today}.log"

    # Получаем sha если файл уже есть
    existing = _gh("GET", filepath)
    sha = existing.get("sha") if isinstance(existing, dict) else None

    body = {
        "message": f"logs: {today}",
        "content": _b64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        body["sha"] = sha
    _gh("PUT", filepath, body)

    # Удаляем логи старше 7 дней
    logs_list = _gh("GET", f"/repos/{GITHUB_REPO}/contents/logs")
    if isinstance(logs_list, list):
        cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0)
        from datetime import timedelta
        cutoff -= timedelta(days=7)
        for item in logs_list:
            name = item.get("name", "")
            if not name.endswith(".log"):
                continue
            try:
                file_date = datetime.strptime(name.replace(".log", ""), "%Y-%m-%d")
                if file_date < cutoff:
                    _gh("DELETE", f"/repos/{GITHUB_REPO}/contents/logs/{name}",
                        {"message": f"logs: cleanup {name}", "sha": item["sha"]})
                    logger.info("Deleted old log from GitHub: %s", name)
            except Exception:
                pass

    logger.info("Log pushed to GitHub: logs/%s.log", today)


def _cleanup_old_outputs(max_age_days: int = 3) -> int:
    """Delete video files in OUTPUTS_DIR older than max_age_days. Returns count deleted."""
    cutoff = time.time() - max_age_days * 86400
    deleted = 0
    try:
        for fname in os.listdir(OUTPUTS_DIR):
            fpath = os.path.join(OUTPUTS_DIR, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                deleted += 1
    except Exception:
        logger.exception("Failed to clean up OUTPUTS_DIR")
    if deleted:
        logger.info("Cleaned up %d old video file(s) from %s", deleted, OUTPUTS_DIR)
    return deleted


async def _daily_log_push_loop():
    """Каждые 24 часа пушит лог в GitHub."""
    while True:
        await asyncio.sleep(86400)  # 24 часа
        try:
            await asyncio.get_event_loop().run_in_executor(None, _push_log_to_github)
        except Exception:
            logger.exception("Daily log push failed")


async def post_init(app: Application):
    global queue_worker_task, _prompt_library_lock
    _prompt_library_lock = asyncio.Lock()  # created inside running event loop — safe
    # Seed prompt library from remote in a thread so we don't block the event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync_prompt_library_from_remote)
    refresh_prompt_library()
    queue_worker_task = asyncio.create_task(_queue_worker_supervised(app))
    _cleanup_old_outputs(max_age_days=3)
    asyncio.create_task(_daily_log_push_loop())


async def post_shutdown(app: Application):
    global queue_worker_task

    if queue_worker_task and not queue_worker_task.done():
        queue_worker_task.cancel()
        try:
            await queue_worker_task
        except asyncio.CancelledError:
            pass


async def queue_worker(app: Application):
    global _worker_current_job
    try:
        while True:
            job = await generation_queue.get()

            queued_user_ids.discard(job.user_id)
            processing_user_ids.add(job.user_id)
            _worker_current_job = job  # track for crash recovery in supervisor

            try:
                await generate_image_by_job(app, job)

            except BaseException as _job_exc:

                is_cancelled = isinstance(_job_exc, asyncio.CancelledError)
                if not is_cancelled:
                    logger.exception("Queue worker error for user=%s", job.user_id)
                try:
                    if getattr(job, "cost", 0) > 0:
                        add_izyminki(job.user_id, job.cost)
                        logger.info("Refunded %d izyminki to user %s after worker error", job.cost, job.user_id)
                    if getattr(job, "was_free", False):
                        restore_free_generation(job.user_id)
                except Exception:
                    logger.exception("Failed to refund after worker error for user=%s", job.user_id)
                if not is_cancelled:
                    try:
                        await app.bot.send_message(
                            chat_id=job.chat_id,
                            text="Ой, Сырник споткнулся на пути к магии. Попробуй ещё раз чуть позже.\n\nСписанные изюминки возвращены на баланс.",
                        )
                    except Exception:
                        pass
                if is_cancelled:
                    raise
            finally:
                # Don't clear _worker_current_job here — supervisor reads it after crash.
                # It gets overwritten at the start of the next iteration or stays set
                # until supervisor's drain loop runs (which is correct).
                processing_user_ids.discard(job.user_id)
                generation_queue.task_done()

            _worker_current_job = None  # clear only on clean completion of job
    except asyncio.CancelledError:
        logger.info("queue_worker stopped")
        raise

# ══════════════════════════════════════════════════════════════
# ВИДЕОГЕНЕРАЦИЯ: Seedance, Kling Motion Control
# ══════════════════════════════════════════════════════════════

async def start_kling_motion_control(
    image_url: str,
    motion_video_url: str,
    prompt: str,
    user_id: int,
) -> str:
    if not KLING_MOTION_ENDPOINT:
        raise Exception("Эндпоинт видео-генерации не настроен (KLING_MOTION_ENDPOINT).")

    if not MASHAGPT_API_KEY:
        raise Exception("MASHAGPT_API_KEY is empty")

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
            request_url = build_mashagpt_url(MASHAGPT_API_BASE, endpoint)
            logger.info(f"Video endpoint: {request_url}")
            async with session.post(
                request_url,
                headers={
                    "x-api-key": MASHAGPT_API_KEY,
                    "Authorization": f"Bearer {MASHAGPT_API_KEY}",
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


def build_seedance_prompt_with_refs(prompt_text: str, refs_count: int) -> str:
    text = (prompt_text or "").strip()
    if not text:
        text = "Cinematic video with coherent action and stable character identity."

    if refs_count <= 0:
        return text

    has_any_placeholder = any(f"[Image{i}]" in text for i in range(1, refs_count + 1))
    placeholders = ", ".join([f"[Image{i}]" for i in range(1, refs_count + 1)])

    if refs_count == 1:
        binding = (
            "Use [Image1] as the main character identity reference. "
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

    if has_any_placeholder:
        return f"{binding}\n{text}"

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
    duration = normalize_seedance_duration(
        int(duration if duration is not None else SEEDANCE_DURATION),
        model_code,
    )
    if model_code == "veo31" and aspect_ratio not in ("16:9", "9:16"):
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
        if _is_img_ref(u):
            data_url = _ref_to_data_url(u)
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
            # Модели умеют звук, но держим его выключенным: дешевле и совпадает
            # с safety-промтом "silent video" в run_seedance.
            payload_base["generate_audio"] = False
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
            reference_sheet_url = await build_seedance_reference_sheet_url(combined_image_urls)
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
    if FAL_API_KEY and zveno_retriable and not privacy_blocked and model_code not in ("kling3", "veo31"):
        # fal-фоллбэк замаплен только на Seedance-слаги — Kling/Veo не подменяем.
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
            if url.startswith("data:") or _is_img_ref(url):
                try:
                    img_bytes = _resolve_image_bytes(url)
                    if img_bytes is None:
                        logger.warning("fal.ai: could not resolve image ref, skipping")
                        continue
                    uploaded = await _upload_bytes_to_freeimage(img_bytes, "ref.jpg")
                    if not uploaded:
                        uploaded = await _upload_bytes_to_catbox(img_bytes, "ref.jpg")
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


async def validate_image_url(image_url: str, session: Optional[aiohttp.ClientSession] = None) -> tuple[bool, str]:
    _own_session = session is None
    if _own_session:
        session = aiohttp.ClientSession()
    try:
        async with session.get(
            image_url,
            timeout=aiohttp.ClientTimeout(total=12),
            allow_redirects=True,
        ) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if resp.status != 200:
                return False, f"HTTP {resp.status}"
            if not content_type.startswith("image/"):
                return False, f"Content-Type is not image: {content_type}"
            return True, "ok"
    except Exception as e:
        return False, str(e)
    finally:
        if _own_session:
            await session.close()        


def _cache_image(image_bytes: bytes) -> str:
    import hashlib
    key = hashlib.md5(image_bytes).hexdigest()[:10]
    _image_cache[key] = image_bytes
    return f"__img_{key}__"


def _is_img_ref(value: str) -> bool:
    return isinstance(value, str) and value.startswith("__img_") and value.endswith("__")


def _resolve_image_bytes(ref: str) -> Optional[bytes]:
    if _is_img_ref(ref):
        return _image_cache.get(ref[6:-2])
    if ref.startswith("data:") and "," in ref:
        return base64.b64decode(ref.split(",", 1)[1])
    return None


def _ref_to_data_url(ref: str) -> Optional[str]:
    if ref.startswith("data:"):
        return ref
    img_bytes = _resolve_image_bytes(ref)
    if img_bytes is None:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()


def is_image_url_like(value: str) -> bool:
    if not isinstance(value, str):
        return False
    raw = value.strip()
    return raw.startswith("http://") or raw.startswith("https://") or raw.startswith("data:image") or _is_img_ref(raw)


async def download_video_bytes_with_fallback(video_url: str) -> bytes:
    if not isinstance(video_url, str) or not video_url.strip():
        raise Exception("Пустой URL видео")

    raw_url = video_url.strip()
    candidate_urls = [raw_url]
    if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        candidate_urls.append(build_zveno_url(ZVENO_API_BASE, raw_url))

    auth_headers = {
        "x-api-key": ZVENO_API_KEY,
        "Authorization": f"Bearer {ZVENO_API_KEY}",
    }
    # Zveno /content usually requires auth; try authorized request first to avoid noisy 401.
    headers_variants = [auth_headers, None]

    last_error = "unknown"
    async with aiohttp.ClientSession() as session:
        for candidate_url in candidate_urls:
            for headers in headers_variants:
                try:
                    logger.info(
                        f"Video download attempt: url={candidate_url}, auth={'yes' if headers else 'no'}"
                    )
                    async with session.get(
                        candidate_url,
                        headers=headers,
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=180),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            if data:
                                return data
                            last_error = "empty body"
                            continue
                        body = await resp.text()
                        last_error = f"{resp.status}. {body[:500]}"
                        logger.warning(
                            f"Video download failed: status={resp.status}, url={candidate_url}, auth={'yes' if headers else 'no'}"
                        )
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        f"Video download exception: url={candidate_url}, auth={'yes' if headers else 'no'}, error={e}"
                    )

    raise Exception(f"Не удалось скачать видео: {last_error}")


def save_video_debug_copy(video_bytes: bytes, user_id: int, model_label: str) -> Optional[str]:
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_model = "".join(ch if ch.isalnum() else "_" for ch in (model_label or "seedance")).strip("_")
        filename = f"{timestamp}_u{user_id}_{safe_model}.mp4"
        path = os.path.join(OUTPUTS_DIR, filename)
        with open(path, "wb") as f:
            f.write(video_bytes)
        return path
    except Exception:
        logger.exception("Failed to save local video copy")
        return None
        
async def run_seedance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = None
    try:  # outer try/finally: guarantees processing_user_ids.discard runs from the very first line
        user = update.effective_user
        # Hard guard: if a generation for this user is already executing, bail out
        # without touching the running instance's markers. The check+add is atomic
        # (no await between them), so two concurrent run_seedance calls can't both pass.
        if user.id in _seedance_executing:
            logger.warning("run_seedance: double execution blocked for user=%s", user.id)
            user = None  # prevent finally from clearing the running instance's markers
            return
        _seedance_executing.add(user.id)
        create_user_if_not_exists(user.id, user.username, START_BONUS)
        reply_target = update.callback_query.message if update.callback_query else update.message
        state = get_or_init_state(context)

        # Snapshot state before clearing — used to restore on error so "Повторить" still works
        _saved_animation_source_urls = list(state.animation_source_urls or [])
        _saved_video_prompt = state.video_prompt
        _saved_image_prompt = state.image_prompt

        state.video_session_active = False

        if not SEEDANCE_ENABLED:
            await reply_target.reply_text(video_unavailable_text(), reply_markup=main_menu_kb())
            return

        # Caller (video_start / seedance_retry) already added us to processing_user_ids before
        # create_task to close the race window.  If we were called directly (future callers or
        # tests) we still do the check + add here as a safety net.
        if user.id not in processing_user_ids:
            if user.id in queued_user_ids:
                await reply_target.reply_text(
                    "Сейчас уже выполняется другая твоя задача. Дождись результата и запусти снова."
                )
                return
            processing_user_ids.add(user.id)

        video_images = get_video_image_urls(state)
        logger.info(
            "run_seedance: user=%s animation_source_urls=%s video_prompt=%r",
            user.id, state.animation_source_urls, state.video_prompt,
        )

        prompt_text = (state.video_prompt or "").strip()
        if not video_images and not prompt_text:
            await reply_target.reply_text(
                "Для видео нужно фото и/или описание. Добавь и запусти снова."
            )
            return

        for idx, img_url in enumerate(video_images, start=1):
            if img_url.startswith("data:") or _is_img_ref(img_url):
                continue
            ok_img, reason_img = await validate_image_url(img_url)
            if not ok_img:
                short_reason = reason_img[:120] if len(reason_img) > 120 else reason_img
                await reply_target.reply_text(f"Фото-референс #{idx} недоступен: {short_reason}")
                return

        selected_duration = get_selected_seedance_duration(state)
        selected_model = get_video_model(state)
        selected_model_label = get_video_model_label(selected_model)
        selected_cps = get_video_model_cost_per_second(selected_model)
        selected_cost = calc_seedance_cost(selected_duration, selected_cps)
        selected_endpoint = SEEDANCE_FAST_ENDPOINT if selected_model == "seedance2_fast" else SEEDANCE_ENDPOINT
        selected_mode = get_selected_seedance_mode(state)
        if selected_model == "kling3":
            selected_model_slug = KLING3_MODEL
        elif selected_model == "veo31":
            selected_model_slug = VEO31_MODEL
        elif selected_model == "seedance2_fast":
            selected_model_slug = SEEDANCE_FAST_MODEL
        else:
            selected_model_slug = SEEDANCE_MODEL

        # Seedance работает только от фото; Kling 3.0 и Veo 3.1 умеют text-to-video.
        if selected_model in {"seedance2", "seedance2_fast"} and len(video_images) < 1:
            await reply_target.reply_text(
                "Загрузи хотя бы 1 фото-ференс и запусти снова.",
                reply_markup=video_kb(state),
            )
            return

        # Check balance BEFORE heavy image processing
        bal = get_balance(user.id)
        if bal < selected_cost:
            await reply_target.reply_text(
                f"Не хватает изюминок.\nНужно: {selected_cost}\nУ тебя: {bal}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Купить изюминки", callback_data="show_buy")
                ]])
            )
            return

        # Two-step pipeline: if image_prompt is set, first generate a stylized
        # image via GPT Image, then use that as the video reference.
        if (state.image_prompt or "").strip() and video_images:
            await reply_target.reply_text("🎨 Стилизую фото через GPT Image…")
            stylized_url = await _run_image_prompt_pipeline(
                image_prompt=state.image_prompt,
                ref_urls=video_images,
            )
            if stylized_url:
                video_images = [stylized_url]
                state.animation_source_urls = [stylized_url]
            else:
                await reply_target.reply_text(
                    "Не удалось стилизовать фото. Попробуй ещё раз или выбери другой шаблон.",
                    reply_markup=video_kb(state),
                )
                return

        # Обработка рефа (сетка) нужна только Seedance (реф внешности).
        # Kling/Veo используют картинку как первый кадр видео — обработка ломает кадр.
        if video_images and selected_model not in ("kling3", "veo31"):
            video_images = await apply_grid_overlay_to_refs(video_images)

        if not spend_izyminki(user.id, selected_cost):
            await reply_target.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
            return

        eta_min = max(2, int(selected_duration * 0.8))
        eta_max = max(eta_min + 1, int(selected_duration * 2.0))
        try:
            await reply_target.reply_text(
                f"Запускаю {selected_model_label} 🎬\n"
                f"Обычно это занимает {eta_min}–{eta_max} минут."
            )
            expected_refs_count = len(video_images)
    
            per_attempt_max_polls = min(
                SEEDANCE_MAX_POLL_ATTEMPTS,
                max(1, SEEDANCE_ATTEMPT_TIMEOUT_SECONDS // max(1, int(SEEDANCE_POLL_INTERVAL))),
            )
            max_seedance_attempts = 3
            active_prompt = prompt_text
            safety_suffix = (
                "Generate a silent video only. No speech, no voice-over, no subtitles, "
                "no readable text, no letters, no logos, no captions."
            )
    
            # Single status message that gets edited in place — no chat spam
            status_msg = await reply_target.reply_text("⏳ Генерирую видео…")
    
            async def _edit_status(text: str) -> None:
                try:
                    await status_msg.edit_text(text)
                except Exception:
                    pass
    
            video_url = None
            last_seedance_error: Optional[Exception] = None
            for seedance_attempt in range(1, max_seedance_attempts + 1):
                task_id = await start_seedance_task(
                    prompt=active_prompt,
                    image_url=video_images[0] if video_images else None,
                    image_urls=video_images,
                    user_id=user.id,
                    duration=selected_duration,
                    endpoint=selected_endpoint,
                    mode=selected_mode,
                    model_slug=selected_model_slug,
                    model_code=selected_model,
                    aspect_ratio=getattr(state, "video_aspect_ratio", "16:9"),
                )
    
                try:
                    video_url = await poll_seedance_task(
                        task_id=task_id,
                        max_attempts=per_attempt_max_polls,
                        poll_interval=SEEDANCE_POLL_INTERVAL,
                        expected_refs_count=expected_refs_count,
                        status_callback=_edit_status,
                    )
                    break
                except Exception as e:
                    last_seedance_error = e
                    err_text = str(e).lower()
                    sensitive_audio_like = (
                        "output audio may contain sensitive information" in err_text
                        or "sensitive information" in err_text
                    )
                    if seedance_attempt < max_seedance_attempts and sensitive_audio_like:
                        logger.warning(
                            "Video moderation fail. Auto-restart with silent-safe prompt: attempt=%s/%s user_id=%s model=%s",
                            seedance_attempt,
                            max_seedance_attempts,
                            user.id,
                            selected_model,
                        )
                        if safety_suffix.lower() not in active_prompt.lower():
                            active_prompt = (active_prompt.strip() + "\n\n" + safety_suffix).strip()
                        await reply_target.reply_text(
                            "Провайдер отклонил аудио. Автоматически перезапускаю в беззвучном безопасном режиме..."
                        )
                        continue
                    raise
    
            if not video_url:
                if last_seedance_error:
                    raise last_seedance_error
                raise Exception("Video URL missing after retries")
    
            video_bytes = await download_video_bytes_with_fallback(video_url)
            saved_path = save_video_debug_copy(video_bytes, user.id, selected_model_label)
            if saved_path:
                logger.info(f"Video local copy saved: {saved_path}")
    
            video_buffer = io.BytesIO(video_bytes)
            video_buffer.name = "seedance.mp4"

            _bounded_set(last_video_params, user.id, {
                "model": selected_model,
                "duration": selected_duration,
                "mode": selected_mode,
                "aspect": getattr(state, "video_aspect_ratio", "16:9"),
                "prompt": prompt_text,
                "refs": list(_saved_animation_source_urls),
            })
            upsell_markup, has_upsell = video_upsell_kb(user.id)
            video_caption = f"Готово 🎬\n{selected_model_label} завершён."
            if has_upsell:
                video_caption += "\n\nПонравилось? Можно сделать ещё круче 👇"

            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_buffer,
                supports_streaming=True,
                caption=video_caption,
                reply_markup=upsell_markup,
            )
            log_generation_event(
                user_id=user.id,
                kind="video",
                status="success",
                provider="ZVENO",
                cost=selected_cost,
                was_free=False,
                references_count=len(video_images),
                prompt=prompt_text[:500] if prompt_text else None,
                username=user.username,
            )
            uname = f"@{user.username}" if user.username else f"id{user.id}"
            channel_caption = (
                f"🎬 Видео | {selected_model_label}\n"
                f"👤 {uname}\n"
                + (f"📝 {prompt_text[:950]}" if prompt_text else "")
            ).strip()
            context.application.create_task(
                _post_to_results_channel(context.application, "video", video_bytes, channel_caption, full_prompt=prompt_text)
            )
            logger.info(
                "Video send_video success: chat_id=%s, user_id=%s, model=%s",
                update.effective_chat.id,
                user.id,
                selected_model_label,
            )
        except BaseException as e:
            logger.exception("Video generation failed")
            add_izyminki(user.id, selected_cost)
            # Restore state so "Повторить" can reuse the same images/prompt
            state.animation_source_urls = _saved_animation_source_urls
            state.video_prompt = _saved_video_prompt
            state.image_prompt = _saved_image_prompt
            log_generation_event(
                user_id=user.id,
                kind="video",
                status="failed",
                provider="ZVENO",
                cost=selected_cost,
                was_free=False,
                references_count=len(video_images),
            )
            error_text = str(e).lower()
            if is_seedance_privacy_moderation_error(error_text):
                await reply_target.reply_text(
                    f"Не удалось выполнить {selected_model_label}.\n"
                    "Модель отклонила фото модерацией.\n"
                    "Это ограничение нейросети, а не сбой бота.\n"
                    "Попробуй другое фото (менее похожее на фото реального человека).\n\n"
                    "Списанные изюминки возвращены на баланс."
                )
                await reply_target.reply_text(
                    "Повторить попытку?",
                    reply_markup=seedance_retry_kb(),
                )
                return
            if "insufficient_funds" in error_text or "insufficient funds" in error_text:
                await reply_target.reply_text(
                    f"Не удалось выполнить {selected_model_label}.\n"
                    "У провайдера видео сейчас закончился баланс (insufficient funds).\n"
                    "Списанные изюминки возвращены на баланс."
                )
                await reply_target.reply_text(
                    "Попробовать еще раз?",
                    reply_markup=seedance_retry_kb(),
                )
                return
            await reply_target.reply_text(
                f"Не удалось выполнить {selected_model_label}.\n"
                "Временный технический сбой. Попробуй еще раз через минуту.\n\n"
                "Списанные изюминки возвращены на баланс."
            )
            if isinstance(e, asyncio.CancelledError):
                raise  # must re-raise so the task actually cancels
            await reply_target.reply_text(
                "Попробовать еще раз?",
                reply_markup=seedance_retry_kb(),
            )
    finally:
        if user is not None:
            processing_user_ids.discard(user.id)
            _seedance_executing.discard(user.id)

async def _persist_image_ref(ref: str) -> str:
    """Upload __img__ cache ref to permanent hosting. Returns persistent URL or empty string on failure."""
    if not _is_img_ref(ref):
        return ref
    img_bytes = _resolve_image_bytes(ref)
    if not img_bytes:
        logger.warning("_persist_image_ref: cache miss for ref %s", ref)
        return ""
    try:
        url = await _upload_bytes_to_freeimage(img_bytes, "avatar.jpg")
        if url:
            return url
        url = await _upload_bytes_to_catbox(img_bytes, "avatar.jpg")
        if url:
            return url
        url = await _upload_bytes_to_imgbb(img_bytes, "avatar.jpg")
        if url:
            return url
        url = await _upload_bytes_to_telegraph(img_bytes, "avatar.jpg")
        if url:
            return url
    except Exception:
        logger.exception("_persist_image_ref: all uploads failed")
    logger.error(
        "_persist_image_ref: could not upload avatar to any host — avatar will NOT be saved to DB"
    )
    return ""


async def _post_to_results_channel(
    app: Application,
    kind: str,
    media_bytes: bytes,
    caption: str,
    full_prompt: str = "",
) -> None:
    if not RESULTS_CHANNEL_ID:
        logger.warning("_post_to_results_channel: RESULTS_CHANNEL_ID is not set, skipping")
        return
    logger.info("_post_to_results_channel: posting %s to channel %s", kind, RESULTS_CHANNEL_ID)
    try:
        buf = io.BytesIO(media_bytes)
        if kind == "video":
            buf.name = "result.mp4"
            sent_msg = await app.bot.send_video(
                chat_id=RESULTS_CHANNEL_ID,
                video=buf,
                caption=caption,
                supports_streaming=True,
            )
        else:
            buf.name = "result.jpg"
            sent_msg = await app.bot.send_photo(
                chat_id=RESULTS_CHANNEL_ID,
                photo=buf,
                caption=caption,
            )
        # Caption ограничен 1024 символами — длинный промт досылаем целиком реплаем.
        if full_prompt and len(full_prompt) > 950:
            await app.bot.send_message(
                chat_id=RESULTS_CHANNEL_ID,
                text=f"📝 Полный промт:\n{full_prompt[:4000]}",
                reply_to_message_id=sent_msg.message_id,
            )
        logger.info("_post_to_results_channel: success kind=%s channel=%s", kind, RESULTS_CHANNEL_ID)
    except Exception:
        logger.exception("Failed to post result to channel %s", RESULTS_CHANNEL_ID)


async def maybe_send_avatar_nudge(app: Application, chat_id: int, user_id: int) -> None:
    # Однократная подсказка после первой удачной генерации: вызывается до
    # log_generation_event, поэтому счётчик успехов ещё равен нулю.
    try:
        if any(get_avatar_urls(user_id).values()):
            return
        if count_success_image_generations(user_id) > 0:
            return
        await app.bot.send_message(
            chat_id=chat_id,
            text=(
                "Кстати, можно не загружать своё фото каждый раз 🪄\n"
                "Нажми «Мой аватар» и загрузи несколько своих фото — бот сгенерирует "
                "твою модель и запомнит внешность. Дальше будешь появляться "
                "в любой идее автоматически.\n"
                f"Стоит как обычная генерация — {BASE_GENERATION_COST} изюминок."
            ),
        )
    except Exception:
        logger.warning("Failed to send avatar nudge to user %s", user_id)


async def send_generation_result_by_url(
    app: Application,
    chat_id: int,
    user_id: int,
    image_url: str,
    job=None,
) -> None:
    if image_url:
        _bounded_set(last_generated_image_url, user_id, image_url)

    await app.bot.send_message(
        chat_id=chat_id,
        text="Готово! Держи результат 🧀✨"
    )

    if _is_img_ref(image_url):
        image_bytes = _resolve_image_bytes(image_url)
        if not image_bytes:
            raise Exception("Изображение не найдено в кэше")
    else:
        async with aiohttp.ClientSession() as img_session:
            async with img_session.get(
                image_url,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as img_resp:
                if img_resp.status != 200:
                    raise Exception(f"Не удалось скачать изображение: {img_resp.status}")
                image_bytes = await img_resp.read()

    source_buffer = io.BytesIO(image_bytes)
    source_buffer.seek(0)

    try:
        image = Image.open(source_buffer)
        if image.mode != "RGB":
            image = image.convert("RGB")

        jpg_bytes_io = io.BytesIO()
        image.save(jpg_bytes_io, format="JPEG", quality=95)
        jpg_bytes = jpg_bytes_io.getvalue()
    except Exception as conv_error:
        raise Exception(f"Не удалось конвертировать изображение в JPG: {conv_error}")

    photo_buffer = io.BytesIO(jpg_bytes)
    photo_buffer.name = "result.jpg"

    doc_buffer = io.BytesIO(jpg_bytes)
    doc_buffer.name = "result.jpg"

    try:
        bot_me = await app.bot.get_me()
        bot_username = bot_me.username or ""
    except Exception:
        bot_username = ""
    _caption_parts = ["✨ Готово!"]
    if job and getattr(job, "image_model", "gemini") == "gpt5":
        _caption_parts.append("🧠 Модель: GPT-5 Image")
    if job:
        _cost = getattr(job, "cost", 0)
        _was_free = getattr(job, "was_free", False)
        if _was_free:
            _caption_parts.append("🆓 Бесплатная генерация")
        elif _cost:
            _caption_parts.append(f"💰 Потрачено: {_cost} изюминок")
    try:
        _bal = get_balance(user_id)
        _caption_parts.append(f"Баланс: {_bal} изюминок")
    except Exception:
        pass
    await app.bot.send_photo(
        chat_id=chat_id,
        photo=photo_buffer,
        reply_markup=result_actions_kb(user_id=user_id, bot_username=bot_username),
        caption="\n".join(_caption_parts),
    )

    await app.bot.send_document(
        chat_id=chat_id,
        document=doc_buffer,
        caption="Файл изображения в хорошем качестве JPG."
    )

    if not (job and getattr(job, "save_as_avatar", False)):
        await maybe_send_avatar_nudge(app, chat_id, user_id)

# ══════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ (ВОРКЕР): MashaGPT, Zveno, Nano
# ══════════════════════════════════════════════════════════════

async def generate_image_by_job(app: Application, job: GenerationJob) -> None:
    chat_id = job.chat_id
    user_id = job.user_id
    prompt = job.prompt
    references = job.references

    refunded = False
    generation_succeeded = False
    last_error_text = "Неизвестная ошибка"

    if AI_PROVIDER == "ZVENO":
        try:
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
                                    if is_image_url_like(url):
                                        return url
                            elif isinstance(image_item, str):
                                image_item = image_item.strip()
                                if is_image_url_like(image_item):
                                    return image_item

                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        content = content.strip()
                        if is_image_url_like(content):
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
                                    if is_image_url_like(url):
                                        return url
                            elif isinstance(image_url, str):
                                image_url = image_url.strip()
                                if is_image_url_like(image_url):
                                    return image_url
                            url = part.get("url")
                            if isinstance(url, str):
                                url = url.strip()
                                if is_image_url_like(url):
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
                resolved = _ref_to_data_url(ref_url) if _is_img_ref(ref_url) else ref_url
                if resolved and (resolved.startswith("http") or resolved.startswith("data:")):
                    user_content.append({"type": "image_url", "image_url": {"url": resolved}})

            job_image_model = getattr(job, "image_model", "gemini")
            zveno_image_model = (
                ZVENO_GPT5_IMAGE_MODEL
                if job_image_model == "gpt5" and GPT5_IMAGE_ENABLED
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
                "max_completion_tokens": 256,
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
                        "max_completion_tokens": 256,
                        "temperature": 0,
                    }
                )

            request_url = build_zveno_url(ZVENO_API_BASE, "/v1/chat/completions")
            logger.info("Zveno image start: user=%s refs=%s endpoint=%s model=%s", user_id, len(references or []), request_url, zveno_image_model)

            response_data = None
            image_url = None
            blocked_models: set = set()
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
                                image_url = _cache_image(raw_bytes)
                        except Exception:
                            image_url = None
                    if not image_url:
                        image_bytes_direct = extract_zveno_image_bytes(response_data)
                        if image_bytes_direct:
                            image_url = _cache_image(image_bytes_direct)
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
                        continue
                    if attempt_idx < len(payload_variants):
                        await asyncio.sleep(0.7)
            if not image_url:
                raise Exception(extract_zveno_error_text(response_data))

            logger.info("Zveno image success: user=%s image_ref=%s", user_id, str(image_url)[:60])
            generation_succeeded = True
            _bounded_set(last_generated_prompt, user_id, prompt)
            _hist_url = image_url
            if _is_img_ref(_hist_url):
                _hist_url = await _persist_image_ref(_hist_url) or _hist_url
            add_generation_history(user_id=user_id, prompt=prompt, image_url=_hist_url)
            await send_generation_result_by_url(app, chat_id, user_id, image_url, job=job)
            if getattr(job, "save_as_avatar", False):
                persistent_avatar_url = await _persist_image_ref(image_url)
                if persistent_avatar_url:
                    set_avatar_url(user_id, persistent_avatar_url, getattr(job, "avatar_kind", "female"))
                    await app.bot.send_message(chat_id=chat_id, text="Аватар сохранён ✅")
                else:
                    await app.bot.send_message(chat_id=chat_id, text="⚠️ Аватар сгенерирован, но сохранить не удалось — хостинг недоступен. Загрузи фото вручную через меню.")
            log_generation_event(
                user_id=user_id,
                kind="image",
                status="success",
                provider="ZVENO",
                cost=getattr(job, "cost", 0),
                was_free=getattr(job, "was_free", False),
                references_count=len(references or []),
                result_url=image_url,
                prompt=prompt[:500] if prompt else None,
                username=getattr(job, "username", None),
            )
            if RESULTS_CHANNEL_ID and image_url:
                uname = f"@{job.username}" if job.username else f"id{user_id}"
                # Лимит caption у фото — 1024 символа: короткий промт влезает целиком,
                # длинный досылаем полностью отдельным сообщением-реплаем (лимит 4096).
                _prompt_full = (prompt or "").strip()
                channel_caption = (
                    f"🖼 Изображение\n"
                    f"👤 {uname}\n"
                    + (f"📝 {_prompt_full[:950]}" if _prompt_full else "")
                ).strip()
                # Скачиваем байты сразу — URL Zveno может истечь к моменту выполнения task
                try:
                    if _is_img_ref(image_url):
                        _ch_bytes = _resolve_image_bytes(image_url)
                    else:
                        async with aiohttp.ClientSession() as _ch_sess:
                            async with _ch_sess.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as _ch_resp:
                                _ch_bytes = await _ch_resp.read() if _ch_resp.status == 200 else None
                except Exception:
                    _ch_bytes = None
                if _ch_bytes:
                    async def _send_img_to_channel(b=_ch_bytes, cap=channel_caption, full_prompt=_prompt_full):
                        try:
                            buf = io.BytesIO(b)
                            buf.name = "result.jpg"
                            sent_msg = await app.bot.send_photo(chat_id=RESULTS_CHANNEL_ID, photo=buf, caption=cap)
                            if len(full_prompt) > 950:
                                await app.bot.send_message(
                                    chat_id=RESULTS_CHANNEL_ID,
                                    text=f"📝 Полный промт:\n{full_prompt[:4000]}",
                                    reply_to_message_id=sent_msg.message_id,
                                )
                            logger.info("Posted image to channel %s", RESULTS_CHANNEL_ID)
                        except Exception:
                            logger.exception("Failed to post image to channel %s", RESULTS_CHANNEL_ID)
                    app.create_task(_send_img_to_channel())
            return
        except Exception as e:
            last_error_text = str(e) or repr(e)
            logger.exception("Zveno generation failed")
            logger.error(f"Generation debug | provider=ZVENO | user_id={user_id} | error={last_error_text}")

            if not generation_succeeded:
                if getattr(job, "cost", 0) > 0 and not refunded:
                    add_izyminki(job.user_id, job.cost)
                    refunded = True
                if getattr(job, "was_free", False) and not refunded:
                    restore_free_generation(job.user_id)
                    refunded = True

            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=generation_failure_user_text(refunded),
                    reply_markup=result_actions_kb(),
                )
            except Exception:
                logger.warning("Failed to send ZVENO failure message to user %s", user_id)
            log_generation_event(
                user_id=user_id,
                kind="image",
                status="failed",
                provider="ZVENO",
                cost=getattr(job, "cost", 0),
                was_free=getattr(job, "was_free", False),
                references_count=len(references or []),
            )
            return

    if AI_PROVIDER == "MASHAGPT":
        try:
            if not MASHAGPT_API_KEY:
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
                resolved_refs = [_ref_to_data_url(r) if _is_img_ref(r) else r for r in references[:8]]
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
                            "x-api-key": MASHAGPT_API_KEY,
                            "Authorization": f"Bearer {MASHAGPT_API_KEY}",
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
                                    "x-api-key": MASHAGPT_API_KEY,
                                    "Authorization": f"Bearer {MASHAGPT_API_KEY}",
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
                            generation_succeeded = True
                            _bounded_set(last_generated_prompt, user_id, prompt)
                            _hist_url = image_url
                            if _is_img_ref(_hist_url):
                                _hist_url = await _persist_image_ref(_hist_url) or _hist_url
                            add_generation_history(user_id=user_id, prompt=prompt, image_url=_hist_url)
                            await send_generation_result_by_url(app, chat_id, user_id, image_url, job=job)
                            if getattr(job, "save_as_avatar", False):
                                persistent_avatar_url = await _persist_image_ref(image_url)
                                if persistent_avatar_url:
                                    set_avatar_url(user_id, persistent_avatar_url, getattr(job, "avatar_kind", "female"))
                                    await app.bot.send_message(chat_id=chat_id, text="Аватар сохранён ✅")
                                else:
                                    await app.bot.send_message(chat_id=chat_id, text="⚠️ Аватар сгенерирован, но сохранить не удалось — хостинг недоступен. Загрузи фото вручную через меню.")
                            log_generation_event(
                                user_id=user_id,
                                kind="image",
                                status="success",
                                provider="MASHAGPT",
                                cost=getattr(job, "cost", 0),
                                was_free=getattr(job, "was_free", False),
                                references_count=len(references or []),
                            )
                            if RESULTS_CHANNEL_ID and image_url:
                                uname = f"@{getattr(job, 'username', None)}" if getattr(job, "username", None) else f"id{user_id}"
                                _masha_caption = (f"🖼 Изображение\n👤 {uname}\n" + (f"📝 {prompt[:200]}" if prompt else "")).strip()
                                async def _send_masha_to_channel(photo=image_url, cap=_masha_caption):
                                    try:
                                        await app.bot.send_photo(chat_id=RESULTS_CHANNEL_ID, photo=photo, caption=cap)
                                    except Exception:
                                        logger.exception("Failed to post MashaGPT result to channel")
                                app.create_task(_send_masha_to_channel())
                            return

                        if status in ("FAILED", "CANCELLED", "ERROR"):
                            error_text = extract_mashagpt_error_text(status_data, status)
                            raise Exception(str(error_text))
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"MashaGPT task status timeout ({attempt + 1}/{poll_attempts}) for task_id={task_id}"
                        )
                        continue

                raise Exception("MashaGPT task polling timeout")


        except Exception as e:
            last_error_text = str(e) or repr(e)
            logger.exception("MashaGPT generation failed")
            logger.error(f"Generation debug | provider=MASHAGPT | user_id={user_id} | error={last_error_text}")

            if not generation_succeeded:
                if getattr(job, "cost", 0) > 0 and not refunded:
                    add_izyminki(job.user_id, job.cost)
                    refunded = True
                if getattr(job, "was_free", False) and not refunded:
                    restore_free_generation(job.user_id)
                    refunded = True

            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=generation_failure_user_text(refunded),
                    reply_markup=result_actions_kb(),
                )
            except Exception:
                logger.warning("Failed to send MASHAGPT failure message to user %s", user_id)
            log_generation_event(
                user_id=user_id,
                kind="image",
                status="failed",
                provider="MASHAGPT",
                cost=getattr(job, "cost", 0),
                was_free=getattr(job, "was_free", False),
                references_count=len(references or []),
            )
            return

    for attempt in range(2):  # 2 попытки: первая + 1 повтор
        try:
            async with aiohttp.ClientSession() as session:
                start_payload = {
                    "version": "v.2",
                    "prompt": prompt,
                    "style": "0",
                    "dimensions": "9:16",
                    "references_urls": [_ref_to_data_url(r) if _is_img_ref(r) else r for r in (references or [])],
                    "customer_id": user_id,
                }

                try:
                    async with session.post(
                        f"{NANO_API_BASE}/generations",
                        headers={"Authorization": f"Bearer {NANO_API_KEY}"},
                        json=start_payload,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as resp:
                        response_text = await resp.text()

                        if resp.status != 200:
                            raise Exception(f"Ошибка запуска генерации: {resp.status}. {response_text}")

                        start_data = json.loads(response_text)

                        if not start_data.get("success"):
                            raise Exception(f"API вернул ошибку запуска: {start_data}")

                        gen_id = start_data["results"]["generation_data"]["id"]

                except asyncio.TimeoutError:
                    raise Exception("Сервер генерации слишком долго отвечает на запуск задачи")

                for _ in range(MAX_POLL_ATTEMPTS):
                    await asyncio.sleep(POLL_INTERVAL)

                    try:
                        async with session.get(
                            f"{NANO_API_BASE}/generations/{gen_id}",
                            headers={"Authorization": f"Bearer {NANO_API_KEY}"},
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as status_resp:
                            if status_resp.status != 200:
                                logger.warning(f"Status check failed: {status_resp.status}")
                                continue

                            status_data = await status_resp.json()
                            logger.info(f"{user_id} response \n {json.dumps(status_data, indent=4, ensure_ascii=False)}")

                            generation_data = status_data.get("results", {}).get("generation_data", {})
                            status = generation_data.get("status")
                            comment_ru = generation_data.get("comment_ru") or ""
                            comment_en = generation_data.get("comment_en") or ""
                            error_text = comment_ru or comment_en or f"Generation failed with status {status}"

                            if status == 2:
                                image_url = generation_data.get("result_url")
                                if image_url:
                                    _bounded_set(last_generated_image_url, user_id, image_url)
                                    _bounded_set(last_generated_prompt, user_id, prompt)
                                    _hist_url = image_url
                                    if _is_img_ref(_hist_url):
                                        _hist_url = await _persist_image_ref(_hist_url) or _hist_url
                                    add_generation_history(user_id=user_id, prompt=prompt, image_url=_hist_url)
                                if not image_url:
                                    raise Exception("Генерация завершилась, но result_url пустой")

                                await app.bot.send_message(
                                    chat_id=chat_id,
                                    text="Сырник довёл магию до финала — держи результат 🔥"
                                )

                                async with aiohttp.ClientSession() as img_session:
                                    async with img_session.get(
                                        image_url,
                                        timeout=aiohttp.ClientTimeout(total=120)
                                    ) as img_resp:
                                        if img_resp.status != 200:
                                            raise Exception(f"Не удалось скачать изображение: {img_resp.status}")

                                        image_bytes = await img_resp.read()

                                source_buffer = io.BytesIO(image_bytes)
                                source_buffer.seek(0)

                                try:
                                    image = Image.open(source_buffer)

                                    if image.mode != "RGB":
                                        image = image.convert("RGB")

                                    jpg_bytes_io = io.BytesIO()
                                    image.save(jpg_bytes_io, format="JPEG", quality=95)
                                    jpg_bytes = jpg_bytes_io.getvalue()

                                except Exception as conv_error:
                                    raise Exception(f"Не удалось конвертировать изображение в JPG: {conv_error}")

                                photo_buffer = io.BytesIO(jpg_bytes)
                                photo_buffer.name = "result.jpg"

                                doc_buffer = io.BytesIO(jpg_bytes)
                                doc_buffer.name = "result.jpg"

                                try:
                                    yesapi_bot_username = (await app.bot.get_me()).username or ""
                                except Exception:
                                    yesapi_bot_username = ""
                                await app.bot.send_photo(
                                    chat_id=chat_id,
                                    photo=photo_buffer,
                                    reply_markup=result_actions_kb(user_id=user_id, bot_username=yesapi_bot_username),
                                    caption="Сгенерировано: Nano Banana 2 ✨\nПовтори или измени описание — жми кнопки ниже"
                                )

                                await app.bot.send_document(
                                    chat_id=chat_id,
                                    document=doc_buffer,
                                    caption="Файл изображения в хорошем качестве JPG."
                                )
                                if not getattr(job, "save_as_avatar", False):
                                    await maybe_send_avatar_nudge(app, chat_id, user_id)
                                log_generation_event(
                                    user_id=user_id,
                                    kind="image",
                                    status="success",
                                    provider="YESAPI",
                                    cost=getattr(job, "cost", 0),
                                    was_free=getattr(job, "was_free", False),
                                    references_count=len(references or []),
                                )
                                if RESULTS_CHANNEL_ID and jpg_bytes:
                                    uname = f"@{getattr(job, 'username', None)}" if getattr(job, "username", None) else f"id{user_id}"
                                    _yes_caption = (f"🖼 Изображение\n👤 {uname}\n" + (f"📝 {prompt[:200]}" if prompt else "")).strip()
                                    _yes_bytes = jpg_bytes
                                    async def _send_yes_to_channel(b=_yes_bytes, cap=_yes_caption):
                                        try:
                                            buf = io.BytesIO(b)
                                            buf.name = "result.jpg"
                                            await app.bot.send_photo(chat_id=RESULTS_CHANNEL_ID, photo=buf, caption=cap)
                                        except Exception:
                                            logger.exception("Failed to post YesAPI result to channel")
                                    app.create_task(_send_yes_to_channel())
                                return

                            if status in (3, 4):
                                last_error_text = error_text
                                raise Exception(error_text)

                            # 0 = в очереди, 1 = в процессе
                            if status not in (0, 1, 2, 3, 4):
                                logger.warning(f"Неизвестный статус генерации: {status}")

                    except asyncio.TimeoutError:
                        logger.warning("Timeout while polling generation status")
                        continue

                raise Exception("Превышено время ожидания генерации")

        except Exception as e:
            last_error_text = str(e)
            logger.exception(f"Generation attempt {attempt + 1} failed")

            if attempt == 0:
                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text="Сервис генерации дал сбой. Пробую ещё раз…"
                    )
                except Exception:
                    pass

                await asyncio.sleep(5)
                continue

            break

    # Если дошли сюда — обе попытки не удались
    try:
        if getattr(job, "cost", 0) > 0 and not refunded:
            add_izyminki(job.user_id, job.cost)
            refunded = True
        if getattr(job, "was_free", False) and not refunded:
            restore_free_generation(job.user_id)
            refunded = True

        logger.error(f"Generation debug | provider=YESAPI | user_id={user_id} | error={last_error_text}")

        await app.bot.send_message(
            chat_id=chat_id,
            text=generation_failure_user_text(refunded),
            reply_markup=result_actions_kb(),
        )
        log_generation_event(
            user_id=user_id,
            kind="image",
            status="failed",
            provider="YESAPI",
            cost=getattr(job, "cost", 0),
            was_free=getattr(job, "was_free", False),
            references_count=len(references or []),
        )
    except Exception:
        logger.exception("Failed to send final generation error message")

# ══════════════════════════════════════════════════════════════
# ЗАПУСК: регистрация хендлеров, main()
# ══════════════════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Forbidden):
        logger.info("Telegram Forbidden ignored (user blocked bot or chat unavailable): %s", err)
        return
    if isinstance(err, BadRequest):
        err_text = str(err).lower()
        if "query is too old" in err_text or "query id is invalid" in err_text:
            logger.info("Telegram stale callback ignored: %s", err)
            return
    logger.exception("Ошибка во время обработки апдейта:", exc_info=err)

# ----------------------------
# Main
# ----------------------------

async def preview_refs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send back processed reference images (bg removal + grid) without launching generation."""
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    state = get_or_init_state(context)
    video_images = get_video_image_urls(state)
    if not video_images:
        await update.message.reply_text("Рефов нет. Добавь фото в Seedance-панели сначала.")
        return
    await update.message.reply_text(
        f"Обрабатываю {len(video_images)} реф(ов) — сетка…"
    )
    try:
        processed = await apply_grid_overlay_to_refs(video_images)
    except Exception:
        logger.exception("preview_refs: processing failed")
        await update.message.reply_text("Ошибка при обработке рефов.")
        return
    for i, (orig, url) in enumerate(zip(video_images, processed), start=1):
        # If the processed ref equals the original, both AI-portrait and grid
        # fallback failed and the raw photo is being sent to Seedance as-is.
        status = "⚠️ ОРИГИНАЛ (обработка не сработала!)" if url == orig else "✅ обработано"
        try:
            if url.startswith("data:") or _is_img_ref(url):
                photo_bytes = _resolve_image_bytes(url)
                if photo_bytes:
                    await update.message.reply_photo(photo_bytes, caption=f"Реф {i}/{len(processed)} — {status}")
                else:
                    await update.message.reply_text(f"Реф {i}: не найден в кэше")
            else:
                await update.message.reply_photo(url, caption=f"Реф {i}/{len(processed)} — {status}")
        except Exception:
            await update.message.reply_text(f"Реф {i}: не удалось отправить")


def main():
    init_db()
    purge_stale_avatar_refs()

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    if TEST_MODE:
        logger.warning("TEST MODE ENABLED — bot responds only to admins: %s", ADMIN_IDS)
        app.add_handler(TypeHandler(object, _test_mode_guard), group=-999)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("ref", referral))
    app.add_handler(CommandHandler("report", report_problem_command))
    app.add_handler(CommandHandler("ai", ai_chat))
    app.add_handler(CommandHandler("hide_keyboard", hide_keyboard))
    app.add_handler(CommandHandler("admin_add", admin_add))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("broadcast_promo", broadcast_promo))
    app.add_handler(CommandHandler("broadcast", broadcast_text))
    app.add_handler(CommandHandler("broadcast_text", broadcast_text))
    app.add_handler(CommandHandler("broadcast_hide_keyboard", broadcast_hide_keyboard))
    app.add_handler(CommandHandler("audience_stats", audience_stats))
    app.add_handler(CommandHandler("pl_save", prompt_library_save_last))
    app.add_handler(CommandHandler("ps_save", prompt_library_save_last))
    app.add_handler(CommandHandler("pl_import", prompt_library_import_from_reply))
    app.add_handler(CommandHandler("pl_import_video", prompt_library_import_video))
    app.add_handler(CommandHandler("pl_newcat", prompt_library_new_category))
    app.add_handler(CommandHandler("pl_renamecat", prompt_library_rename_category))
    app.add_handler(CommandHandler("pl_delcat", prompt_library_delete_category))
    app.add_handler(CommandHandler("pl_admin", prompt_library_admin_help))
    app.add_handler(CommandHandler("pl_list", prompt_library_list))
    app.add_handler(CommandHandler("pl_where", prompt_library_where))
    app.add_handler(CommandHandler("pl_history", prompt_library_history_command))
    app.add_handler(CommandHandler("pl_export", prompt_library_export))
    app.add_handler(CommandHandler("pl_sync", prompt_library_sync_from_cloudflare))
    app.add_handler(CommandHandler("pl_backups", prompt_library_list_backups))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data_v2))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CommandHandler("promo_stats", promo_stats))
    app.add_handler(CommandHandler("previewrefs", preview_refs))
    app.add_error_handler(error_handler)

    logger.info("Бот запускается...")
    logger.info("build=%s", BUILD_ID)
    logger.info("db path: %s", DB_NAME)
    if DB_NAME != SEED_DB_NAME and os.path.exists(SEED_DB_NAME):
        logger.info(
            "legacy seed db detected at %s (runtime uses %s)",
            SEED_DB_NAME,
            DB_NAME,
        )
    if LOG_FILE_ERROR:
        logger.warning("file logging disabled: %s", LOG_FILE_ERROR)
    else:
        logger.info("file logging enabled: %s", LOG_FILE_PATH)
    app.run_polling()


if __name__ == "__main__":
    main()
