import asyncio
import base64
import collections as _collections
import csv
import io
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
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
    PicklePersistence,
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
    EVOLINK_API_BASE,
    EVOLINK_API_KEY,
    SEEDANCE_PROVIDER,
    SEEDANCE_FACE_GRID,
    MOTION_CONTROL_PROVIDER,
    GEMINI_OMNI_ENABLED,
    GEMINI_OMNI_MODEL,
    GEMINI_OMNI_DURATION,
    GEMINI_OMNI_DURATION_OPTIONS,
    GEMINI_OMNI_COST_PER_SECOND,
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
    BUG_BOUNTY_REWARD,
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
    MAX_SEEDANCE_IMAGE_REFERENCES,
    SEEDANCE_VIDEO_REFERENCE_MODE,
    DATA_DIR,
    GITHUB_TOKEN,
    GITHUB_REPO,
    WEBAPP_GITHUB_REPO,
    KLING3_ENABLED,
    KLING3_MODEL,
    KLING3_COST_PER_SECOND,
    KLING3_DURATION_OPTIONS,
    VEO31_ENABLED,
    VEO31_MODEL,
    VEO31_COST_PER_SECOND,
    VEO31_DURATION_OPTIONS,
    WAN27_ENABLED,
    WAN27_MODEL,
    WAN27_COST_PER_SECOND,
    WAN27_DURATION_OPTIONS,
    SEEDANCE25_ENABLED,
    SEEDANCE25_MODEL,
    SEEDANCE25_MODE,
    SEEDANCE25_DURATION_OPTIONS,
    SEEDANCE25_MAX_IMAGES,
    SEEDANCE25_COST_PER_SECOND_480P,
    SEEDANCE25_COST_PER_SECOND_720P,
    VIDEO_CONSTRUCTOR_ENABLED,
    MIDJOURNEY_CONSTRUCTOR_ENABLED,
    AVATAR_CONSTRUCTOR_ENABLED,
    PHOTO_CONSTRUCTOR_ENABLED,
    GEN_PROGRESS_ENABLED,
    GEN_PROGRESS_API_BASE,
    GEN_PROGRESS_SECRET,
    GPT5_IMAGE_ENABLED,
    ZVENO_GPT5_IMAGE_MODEL,
    GPT5_IMAGE_COST,
    MIDJOURNEY_ENABLED,
    MIDJOURNEY_MODEL,
    MIDJOURNEY_UPSCALE_MODEL,
    MIDJOURNEY_GRID_COST,
    MIDJOURNEY_UPSCALE_COST,
    MIDJOURNEY_MAX_POLL_ATTEMPTS,
    MIDJOURNEY_POLL_INTERVAL,
    STUDIO_ENABLED,
    STUDIO_API_BASE,
    STUDIO_POLL_SECRET,
    STUDIO_MAX_SCENES,
    STUDIO_POLL_INTERVAL,
    STUDIO_CONCURRENCY,
)

# Видео-провайдер-клиенты (Zveno/EvoLink/MashaGPT/fal.ai) — вынесены из
# SirNike.py в video_providers.py (фаза 1 разбора монолита, см.
# docs/briefs/backend.md). video_providers.py НЕ импортирует SirNike.py
# (иначе циклический импорт) — недостающие бот-уровневые хелперы (резолв
# __img__-рефов, reference sheet, аплоад на freeimage/catbox) прокидываются
# туда через video_providers.configure(...) ниже, сразу после того как эти
# хелперы определены в этом файле.
import video_providers
from video_providers import (
    seedance_uses_evolink,
    get_seedance_duration_bounds,
    normalize_seedance_duration,
    normalize_seedance_mode,
    seedance_mode_ui_label,
    get_seedance_mode_options,
    get_seedance_duration_options,
    build_mashagpt_url,
    build_zveno_url,
    build_seedance_prompt_with_refs,
    _data_url_to_jpeg_rgb,
    is_seedance_privacy_moderation_error,
    extract_task_video_url,
    extract_task_reference_count,
    EVOLINK_SEEDANCE_MODEL_MAP,
    EVOLINK_SEEDANCE_MAX_IMAGES,
    GEMINI_OMNI_MAX_IMAGES,
    build_evolink_url,
    poll_evolink_task,
    start_seedance_task_evolink,
    start_gemini_omni_task_evolink,
    start_seedance25_task_evolink,
    start_kling_motion_control_evolink,
    start_seedance_task,
    poll_seedance_task,
    start_kling_motion_control,
    poll_kling_animation_custom,
    start_midjourney_task_evolink,
    start_midjourney_upscale_evolink,
)

# Фото-провайдер-клиенты (Zveno + MashaGPT) — вынесены из SirNike.py в
# photo_providers.py (фаза 2 разбора монолита, см. docs/briefs/backend.md),
# тот же паттерн, что и video_providers.py выше (нет циклического импорта,
# недостающие бот-уровневые хелперы прокидываются через
# photo_providers.configure(...) ниже). YesAPI/Nano Banana 2 намеренно
# осталась в этом файле — см. докстринг photo_providers.py.
import photo_providers
from photo_providers import (
    generate_image_zveno,
    generate_image_mashagpt,
)

# Воркер «Студии нейромультиков» (D1-очередь) — вынесен из SirNike.py в
# studio_worker.py целиком, включая биллинг и отправку в чат (фаза 3 разбора
# монолита, см. docs/briefs/backend.md — отличие от video/photo_providers.py
# объяснено в докстринге studio_worker.py). Недостающие бот-уровневые
# зависимости прокидываются через studio_worker.configure(...) ниже, сразу
# после того как нужные хелперы здесь определены.
import studio_worker
from studio_worker import (
    STUDIO_STITCH_RESOLUTION,
    _studio_video_models,
    _studio_price_feed,
    _studio_api,
    _studio_complete,
    _studio_compute_cost,
    _studio_parse_scenes,
    _studio_generate_scenario,
    _studio_generate_frame,
    _studio_generate_clip,
    _studio_ffmpeg_run,
    _studio_clip_has_audio,
    _studio_normalize_clip,
    _studio_generate_stitch,
    _studio_execute_job,
    _studio_handle_job,
    _studio_run_job,
    _studio_poll_loop,
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
    set_active_avatar_kind,
    get_active_avatar_kind,
    purge_stale_avatar_refs,
    restore_free_generation,
    log_generation_event,
    count_success_image_generations,
    get_audience_overview,
    get_pnl_report,
    log_template_usage,
    get_template_usage_counts,
    get_top_styles_by_index,
    add_generation_history,
    get_generation_history,
    get_generation_history_item,
    delete_user_for_test,
    get_error_breakdown,
    get_provider_comparison,
    get_studio_done_job,
    record_studio_done_job,
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
# Сетка Midjourney, ждущая выбора юзера (task_id/grid_url/prompt) — один слот
# на юзера, как last_video_params (queued_user_ids/processing_user_ids и так
# не дают параллелить генерации одного юзера). TTL ~23ч — с запасом от
# заявленных EvoLink 24ч жизни ссылок на картинки (_cleanup_stale_mj_grids).
last_mj_grid: "_collections.OrderedDict" = _collections.OrderedDict()
_MJ_GRID_TTL_SECONDS = 23 * 3600
_MJ_GRID_LAST_TTL_CHECK: float = 0.0


def _cleanup_stale_mj_grids() -> None:
    """Ленивая TTL-чистка last_mj_grid — не чаще раза в 60 сек (тот же
    rate-limit паттерн, что у MEDIA_GROUP_CACHE), чтобы не делать O(n) на
    каждую запись/чтение."""
    global _MJ_GRID_LAST_TTL_CHECK
    _now = time.time()
    if _now - _MJ_GRID_LAST_TTL_CHECK <= 60:
        return
    _MJ_GRID_LAST_TTL_CHECK = _now
    stale_keys = [
        k for k, v in last_mj_grid.items()
        if (_now - float(v.get("created_at", _now))) > _MJ_GRID_TTL_SECONDS
    ]
    for k in stale_keys:
        last_mj_grid.pop(k, None)


def _get_valid_mj_grid(user_id: int) -> Optional[dict]:
    """Читает last_mj_grid[user_id], но только если запись не протухла по TTL
    (страховка от заявленных EvoLink 24ч жизни ссылок на картинки)."""
    _cleanup_stale_mj_grids()
    entry = last_mj_grid.get(user_id)
    if not entry:
        return None
    if (time.time() - float(entry.get("created_at", 0))) > _MJ_GRID_TTL_SECONDS:
        last_mj_grid.pop(user_id, None)
        return None
    return entry


last_video_params: "_collections.OrderedDict" = _collections.OrderedDict()
MEDIA_GROUP_CACHE: "_collections.OrderedDict[Tuple[int, str], List[Dict[str, Any]]]" = _collections.OrderedDict()
MAX_CACHED_MEDIA_GROUPS = 300
_MEDIA_GROUP_LAST_TTL_CHECK: float = 0.0
MAX_MEDIA_GROUP_CHUNK_SIZE = 10
# Совпадает с лимитом референсов, реально уходящих в генерацию (references[:8]),
# чтобы лишние фото не собирались впустую и потом молча не отбрасывались.
MAX_AVATAR_PHOTOS = 8


@dataclass
class UserState:
    prompt: str = ""
    references: List[str] = field(default_factory=list)
    # Когда последний раз обновлялись references — используется, чтобы не
    # подмешивать в новую генерацию фото, забытые пользователем недели назад.
    references_updated_at: float = 0.0
    animation_source_url: Optional[str] = None
    animation_source_urls: List[str] = field(default_factory=list)
    # Тип аватара (female/male/child), выбранный перед генерацией — читается в avatar_gen_start.
    pending_avatar_kind: str = ""  # "" = ещё не выбран (см. avatar_gen_start)
    generating_avatar: bool = False
    avatar_photos: List[str] = field(default_factory=list)
    avatar_status_msg_id: Optional[int] = None
    waiting_for_problem_report: bool = False
    waiting_for_bug_report: bool = False
    # Скриншот "вторым сообщением" к репорту (проблема/баг-баунти) — "" | "problem" | "bug".
    # Живой баг 2026-07-19: раньше флаг ожидания текста сбрасывался сразу после
    # текста репорта, и следующий отправленный скриншот тихо утекал в обычные
    # references генерации вместо репорта. См. handle_photo.
    pending_report_kind: str = ""
    pending_report_kind_at: float = 0.0
    video_prompt: str = ""
    motion_video_url: Optional[str] = None
    video_duration: Optional[int] = None
    video_mode: Optional[str] = None
    video_model: str = "seedance2_fast"
    # Юзер уже выбирал модель в этой сессии — вход в «Видео для Reels» сразу
    # открывает полную панель, без повторного пикера (ТЗ video_panel_declutter).
    video_model_picked: bool = False
    video_aspect_ratio: str = "9:16"
    # Тумблер сетки «детектор лиц» (video_kb) — ломает ByteDance real-face
    # детектор Seedance ценой лёгкой сетки на кадре. Дефолт наследуется от env
    # SEEDANCE_FACE_GRID (по умолчанию выкл). См. run_seedance / get_face_grid.
    video_face_grid: bool = field(default_factory=lambda: SEEDANCE_FACE_GRID)
    video_session_active: bool = False
    waiting_for_video_prompt: bool = False
    waiting_for_video_image: bool = False
    waiting_for_video_duration: bool = False
    waiting_for_motion_video: bool = False
    # Kling Motion Control — отдельный мини-флоу (не Seedance): референс-видео
    # с движением + одно фото юзера, см. docs/specs/2026-07-31_evolink_video_provider.md.
    # Фича скрыта за MOTION_CONTROL_ENABLED (по умолчанию 0), но флоу должен
    # быть рабочим для локального QA с флагом=1.
    motion_control_active: bool = False
    waiting_for_motion_image: bool = False
    motion_image_url: Optional[str] = None
    image_model: str = "gemini"  # gemini | gpt5
    image_prompt: str = ""
    # Стиль помечен `style_extract` в prompt_library.json (сейчас — «Образ с
    # референса», 💄 Бьюти): второе загруженное фото не идёт в image-модель
    # как референс, а сначала описывается text-only vision-вызовом (см.
    # extract_style_description_from_reference), чтобы лицо со второго фото
    # физически не могло попасть в результат. One-shot: run_generation сбрасывает
    # флаг после использования, остальные пути установки state.prompt — тоже
    # (см. docs/briefs/backend.md, P1 «Образ с референса»).
    style_extract: bool = False
    # Midjourney (EvoLink) — отдельный мини-флоу: сетка 4 варианта -> апскейл.
    # Не переиспользует run_generation/GenerationJob (тот контракт — "один
    # клик, один результат", у Midjourney есть промежуточный шаг выбора).
    mj_active: bool = False
    waiting_for_mj_prompt: bool = False
    waiting_for_mj_image: bool = False
    mj_prompt: str = ""
    mj_reference: Optional[str] = None
    # Доски — Full, AI-анализ стиля (docs/specs/2026-08-09_mood_boards_full.md):
    # НЕ переиспользует references/style_extract — те one-shot (сбрасываются
    # после каждой генерации в десятке мест), а описание стиля доски должно
    # подмешиваться в промт КАЖДОЙ генерации, пока доска подключена. Поэтому
    # это отдельное персистентное поле — сознательно НЕ трогается в местах,
    # где чистится state.references.
    board_style_note: Optional[str] = None
    board_style_board_id: Optional[str] = None
    # Короткий id активной доски для callback_data кнопки «Отключить»
    # (board_id — UUID вебаппа, 36 символов, не влезает в лимит Telegram
    # вместе с префиксом callback_data — см. docs/specs/2026-08-09_mood_boards_full.md, п.2).
    board_style_short_id: str = ""
    # Черновик анализа, ждущий подтверждения юзером («✅ Всё верно» / «✏️ Поправить»).
    board_style_pending_note: Optional[str] = None
    board_style_pending_board_id: Optional[str] = None
    board_style_pending_title: str = ""
    board_style_pending_short_id: str = ""
    waiting_for_board_style_correction: bool = False

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

            # НЕ пересортировывать категории (было: видео-категории вперёд).
            # Контракт бот↔вебапп на cat_idx/item_idx завязан на СЫРОЙ порядок
            # категорий в prompt_library.json (вебапп считает индексы по
            # необработанному файлу, flattenLibrary() в app.js). Сортировка
            # здесь молча расходилась с вебаппом, как только не-видео
            # категория оказывалась в файле раньше видео-категории — «карточка
            # устарела»/пустой промт для ЛЮБОГО стиля после точки расхождения
            # (найдено 2026-08-02, живой лог: cat_idx=1 у вебаппа = «Seedance
            # 2», у бота после сортировки cat_idx=1 = «Руферы»). Если порядок
            # категорий для UI бота когда-нибудь понадобится другой — это
            # задача вебаппа (сортировать при отображении, не трогая индексы),
            # не бэкенда.
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


def style_applied_message(label: str, item: Optional[dict], kind: str, user_note: str = "") -> str:
    """Инструкция в чат после применения стиля: что получится + что загрузить.

    Карточка с этой инструкцией остаётся в закрывшемся вебаппе/каталоге —
    дублируем её в чате, чтобы юзер видел требования к фото (макет утверждён
    Аней 2026-07-15). Строки без данных опускаются целиком.

    user_note — «свои пожелания» из поля input_hint в вебаппе. Если заданы,
    статичное описание из библиотеки больше не гарантированно точное (юзер
    попросил другое) — вместо "Что получится: <дефолт>" показываем, что
    именно учтено, а не выдаём канцелярское описание за факт."""
    applied = f"Стиль «{label}» применён для видео." if kind == "video" else f"Стиль «{label}» применён."
    lines = ["Готово ✨", applied]
    description = str((item or {}).get("description") or "").strip()
    upload_hint = str((item or {}).get("upload_hint") or "").strip()
    if user_note:
        lines.append(f"✍️ Учла твои пожелания: «{user_note}»")
    elif description:
        emoji = "🎬" if kind == "video" else "🎨"
        lines.append(f"{emoji} Что получится: {description}")
    if upload_hint:
        lines.append(f"📎 Что загрузить: {upload_hint}")
    return "\n".join(lines)


def _resolve_prompt_style_label(prompt: str) -> str:
    """Лейбл применённого стиля по тексту промта — state хранит только промт,
    а в панели черновика хочется показывать «Стиль: Пикник ✅», а не простыню."""
    p = (prompt or "").strip()
    if not p:
        return ""
    for cat in PROMPT_LIBRARY:
        for it in cat.get("items") or []:
            if str(it.get("prompt") or "").strip() == p:
                return _showcase_item_label(it)
    return ""


_AVATAR_KIND_EMOJI = {"male": "👨", "child": "🧒", "female": "👩"}


def photo_draft_text(state: "UserState", user_id: Optional[int] = None) -> str:
    """Экран «✨ Сгенерировать фото»: статус черновика (макет утверждён Аней 2026-07-15)."""
    prompt = (state.prompt or "").strip()
    refs = len(state.references)
    if state.style_extract:
        # Этому стилю нужны РОВНО 2 фото по порядку: своё лицо, потом референс
        # причёски/макияжа — явный статус по слотам (P0 2026-07-17, брифу
        # нужно было "подтверждение, каких фото не хватает").
        if refs == 0:
            photo_line = "Фото: 0/2 — сначала своё фото (лицо), потом фото-референс причёски/макияжа"
        elif refs == 1:
            photo_line = "Фото: 1/2 ✅ своё — теперь пришли фото-референс причёски/макияжа"
        else:
            photo_line = "Фото: 2/2 ✅ своё + референс — можно запускать"
    elif refs:
        photo_line = f"Твоё фото: {refs} шт. ✅"
    else:
        # Без своего фото генерация молча подставляет сохранённый аватар
        # (run_generation) — юзер должен знать об этом ДО запуска, не только
        # догадываться по результату.
        avatar_line = None
        if user_id is not None:
            try:
                avatars = get_avatar_urls(user_id)
                active_kind = get_active_avatar_kind(user_id)
                kind = next((k for k in ([active_kind] if active_kind else []) + ["female", "male", "child"] if avatars.get(k)), None)
                if kind:
                    avatar_line = f"Твоё фото: не нужно — возьму твой аватар {_AVATAR_KIND_EMOJI.get(kind, '👤')} (или пришли новое)"
            except Exception:
                avatar_line = None
        photo_line = avatar_line or "Твоё фото: пока нет (не обязательно)"
    lines = ["✨ Сгенерировать фото", ""]
    if prompt:
        style_label = _resolve_prompt_style_label(prompt)
        if style_label:
            lines.append(f"Стиль: {style_label} ✅")
        else:
            preview = prompt if len(prompt) <= 50 else prompt[:47] + "…"
            lines.append(f"Описание: «{preview}» ✅")
        lines.append(photo_line)
        model = get_image_model(state)
        lines.append(f"Модель: {get_image_model_label(model)} · {calc_generation_cost(None, model)} 🍇")
    else:
        lines.append("Стиль или описание: пока нет 👇")
        lines.append(photo_line)
        lines.append("")
        lines.append(
            "Выбери стиль из библиотеки — или просто напиши сообщением, что хочешь увидеть. "
            "Хочешь себя на картинке — пришли своё фото."
        )
    return "\n".join(lines)


def photo_draft_kb(state: "UserState", user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Кнопки экрана фото. Правило UI_STYLE: кнопка есть ⇔ действие сейчас возможно,
    поэтому «🚀 Запустить генерацию» существует только при заполненном стиле/описании."""
    prompt = (state.prompt or "").strip()
    if PROMPT_WEBAPP_URL and user_id is not None:
        library_button = InlineKeyboardButton(
            "📚 Выбрать другой стиль" if prompt else "📚 Выбрать стиль",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)),
        )
    else:
        pl_cb = "pl_open_webapp" if PROMPT_WEBAPP_URL else "pl_open"
        library_button = InlineKeyboardButton(
            "📚 Выбрать другой стиль" if prompt else "📚 Выбрать стиль",
            callback_data=pl_cb,
        )
    rows = []
    ready = bool(prompt) and (not state.style_extract or len(state.references) == 2)
    if ready:
        rows.append([InlineKeyboardButton("🚀 Запустить генерацию", callback_data="generate")])
    rows.append([library_button])
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="reset")])
    return InlineKeyboardMarkup(rows)


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


# get_seedance_duration_bounds/normalize_seedance_duration/normalize_seedance_mode/
# seedance_mode_ui_label/get_seedance_mode_options — вынесены в video_providers.py
# (фаза 1 разбора монолита, см. docs/briefs/backend.md), импортированы выше.


def get_selected_seedance_mode(state: UserState) -> str:
    selected_model = get_video_model(state)
    options = get_seedance_mode_options(selected_model)
    if selected_model == "veo31":
        return options[0]
    picked = normalize_seedance_mode(state.video_mode or SEEDANCE_MODE)
    if picked not in options:
        picked = options[0]
    return picked


# get_seedance_duration_options — вынесена в video_providers.py (фаза 1
# разбора монолита), импортирована выше.


def get_selected_seedance_duration(state: UserState) -> int:
    model_code = get_video_model(state)
    options = get_seedance_duration_options(model_code)
    default_sec = options[0] if options else normalize_seedance_duration(int(SEEDANCE_DURATION), model_code)
    selected = normalize_seedance_duration(state.video_duration, model_code) if isinstance(state.video_duration, int) else default_sec
    if selected not in options:
        # Wan 2.7 принимает любое целое в границах модели (см. video_set_duration) —
        # значение, введённое вручную, не обязано входить в кнопки-пресеты.
        if model_code == "wan27":
            dur_min, dur_max = get_seedance_duration_bounds(model_code)
            if not (dur_min <= selected <= dur_max):
                selected = default_sec
        else:
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
    state.waiting_for_video_duration = False
    state.image_prompt = ""
    # Motion Control — свой мини-флоу, гасим вместе с обычным видео-режимом,
    # чтобы «В меню»/reset не оставляли юзера в подвешенном ожидании фото/видео.
    state.motion_control_active = False
    state.waiting_for_motion_image = False
    state.motion_video_url = None
    state.motion_image_url = None
    # Midjourney — свой мини-флоу, гасим по той же причине (см. выше).
    state.mj_active = False
    state.waiting_for_mj_prompt = False
    state.waiting_for_mj_image = False


def get_video_model(state: UserState) -> str:
    if state.video_model == "seedance2_fast" and SEEDANCE_FAST_ENABLED:
        return "seedance2_fast"
    if state.video_model == "kling3" and KLING3_ENABLED:
        return "kling3"
    if state.video_model == "veo31" and VEO31_ENABLED:
        return "veo31"
    if state.video_model == "wan27" and WAN27_ENABLED:
        return "wan27"
    if state.video_model == "gemini_omni" and GEMINI_OMNI_ENABLED:
        return "gemini_omni"
    if state.video_model == "seedance25" and SEEDANCE25_ENABLED:
        return "seedance25"
    return "seedance2"


def video_model_uses_face_grid(model_code: str) -> bool:
    """Сетка «детектор лиц» применима только к Seedance 2 / 2 Fast — только их
    режет ByteDance-детектор реальных лиц. Kling/Veo/Wan/Gemini Omni берут фото
    как первый кадр/референс-стиль, сетка им ломает кадр."""
    return model_code in ("seedance2", "seedance2_fast")


def get_face_grid(state: UserState) -> bool:
    """Per-user состояние тумблера сетки «детектор лиц». Дефолт — env
    SEEDANCE_FACE_GRID (getattr-фолбэк на случай старого состояния без поля)."""
    return bool(getattr(state, "video_face_grid", SEEDANCE_FACE_GRID))


def get_video_model_label(model_code: str) -> str:
    labels = {
        "seedance2_fast": "Seedance 2 Fast (бета)",
        "seedance2": "Seedance 2",
        "kling3": "Kling 3.0 🆕",
        "veo31": "Veo 3.1 (Google) 🆕",
        "wan27": "Wan 2.7 (Alibaba) 🆕",
        "gemini_omni": "Gemini Omni Flash 🆕",
        "seedance25": "Seedance 2.5 💎",
    }
    return labels.get(model_code, "Seedance 2")


def get_video_model_blurb(model_code: str) -> str:
    """Человеческое пояснение модели — без него выбор в video_kb был вслепую
    (5 моделей без единого слова разницы), особенно жаргонное «для Seedance»."""
    blurbs = {
        "seedance2": "максимум качества и движения, наш выбор",
        "seedance2_fast": "быстрее и дешевле, попроще картинка",
        "kling3": "оживляет фото, плавная камера",
        "veo31": "кинореализм, до 8 сек",
        "wan27": "живая мимика и жесты",
        "gemini_omni": "звук генерируется сам, быстрая генерация",
        "seedance25": "премиум: до 30 сек без склейки, 50 референсов",
    }
    return blurbs.get(model_code, "")


# seedance_uses_evolink — вынесена в video_providers.py (фаза 1 разбора
# монолита), импортирована выше.


def get_video_model_cost_per_second(model_code: str, mode: Optional[str] = None) -> float:
    if model_code == "seedance2_fast":
        return max(SEEDANCE_FAST_COST_PER_SECOND, 0.01)
    if model_code == "kling3":
        return max(KLING3_COST_PER_SECOND, 0.01)
    if model_code == "veo31":
        return max(VEO31_COST_PER_SECOND, 0.01)
    if model_code == "wan27":
        return max(WAN27_COST_PER_SECOND, 0.01)
    if model_code == "gemini_omni":
        return max(GEMINI_OMNI_COST_PER_SECOND, 0.01)
    if model_code == "seedance25":
        # Единственная модель с ценой, зависящей от качества (480p/720p) —
        # оба тарифа доступны юзеру, не одно качество на модель.
        normalized_mode = normalize_seedance_mode(mode or SEEDANCE25_MODE)
        cps = SEEDANCE25_COST_PER_SECOND_720P if normalized_mode == "720p" else SEEDANCE25_COST_PER_SECOND_480P
        return max(cps, 0.01)
    return max(SEEDANCE_COST_PER_SECOND, 0.01)


def calc_seedance_cost(duration_sec: int, cost_per_second: Optional[float] = None) -> int:
    cps = max(
        cost_per_second if cost_per_second is not None else SEEDANCE_COST_PER_SECOND,
        0.01,
    )
    safe_duration = max(1, int(duration_sec))
    return max(1, int(round(safe_duration * cps)))


def classify_generation_error(error: object) -> str:
    """Классифицировать ошибку провайдера для аналитики.

    Возвращает один из: timeout / moderation / no_balance / provider_error /
    download_error / unknown. Без чувствительных данных — только по тексту/типу.
    """
    if isinstance(error, asyncio.TimeoutError):
        return "timeout"
    text = (str(error) or "").lower()
    if not text:
        return "unknown"
    if any(k in text for k in ("timeout", "timed out", "слишком долго", "время ожидания", "deadline")):
        return "timeout"
    if any(k in text for k in (
        "moderation", "moderated", "модерац", "nsfw", "content filter", "content_filter",
        "safety", "flagged", "blocked", "policy", "приватн", "privacy",
    )):
        return "moderation"
    if any(k in text for k in (
        "insufficient_funds", "insufficient funds", "no_balance", "no balance",
        "недостаточно средств", "закончился баланс", "out of credits", "quota",
        # YesAPI: внутренняя валюта RPOINTS (NOT_ENOUGH_RPOINTS) — раньше
        # улетала в unknown и портила статистику ошибок (тот же класс
        # инцидента, из-за которого появился log_provider_config).
        "rpoints",
    )):
        return "no_balance"
    if any(k in text for k in (
        "download", "скачать изображение", "скачать видео", "не удалось скачать", "result_url пуст",
        "url missing", "url пустой", "image_processing_error", "image_dimension_mismatch",
    )):
        return "download_error"
    if any(k in text for k in (
        "api", "provider", "server", "сервер", "генерац", "status", "5xx",
        "500", "502", "503", "504", "bad gateway", "service unavailable",
        # EvoLink-специфичные коды (docs/en/api-manual/task-management/error-codes) —
        # с подчёркиванием, не пробелом, поэтому "service unavailable" их не ловит.
        "service_unavailable", "service_error", "resource_exhausted",
        "generation_failed_no_content", "resource_not_found",
    )):
        return "provider_error"
    return "unknown"


# build_mashagpt_url/build_zveno_url — вынесены в video_providers.py (фаза 1
# разбора монолита), импортированы выше.


# Сколько держим забытые reference-фото в state, прежде чем считать их
# устаревшими. Без этого «Фото на месте (N шт.) — запускай!» может тихо
# подмешать в генерацию фото, загруженные пользователем недели назад.
STALE_REFERENCES_TTL_SECONDS = 6 * 3600

# Окно, в течение которого следующее ФОТО после текста репорта (проблема/
# баг-баунти) считается "скриншотом к этому репорту", а не обычным
# reference-фото для генерации. См. state.pending_report_kind.
PENDING_REPORT_SCREENSHOT_TTL_SECONDS = 5 * 60


def get_or_init_state(context: ContextTypes.DEFAULT_TYPE) -> UserState:
    state = context.user_data.get("state")
    if not isinstance(state, UserState):
        state = UserState()
        context.user_data["state"] = state
    if state.references and state.references_updated_at:
        if time.time() - state.references_updated_at > STALE_REFERENCES_TTL_SECONDS:
            state.references = []
            state.references_updated_at = 0.0
    return state


def generation_failure_user_text(refunded: bool) -> str:
    refund_text = "\n\n✅ Изюминки не списаны (или возвращены) — баланс не пострадал, можешь попробовать снова." if refunded else ""
    return (
        "Что-то пошло не так при генерации 😔\n"
        "Попробуй, пожалуйста, ещё раз через пару минут."
        f"{refund_text}"
    )


def get_video_constructor_config() -> dict:
    """Конфигурация для экрана «Конструктор» вебаппа (docs/specs/
    2026-08-13_webapp_generation_hub.md, «Что нужно от бэкенда» п.3). У бота
    нет публичного HTTP-входа — вебапп не может ничего ЗАПРОСИТЬ у бота
    напрямую, поэтому список активных моделей/форматов/длительностей/цен
    пробрасывается единственным доступным каналом: персональным URL при
    открытии Mini App. Источник истины остаётся бэкенд — вебапп только
    отображает эти цифры, финальная цена в карточке подтверждения в чате
    всегда пересчитывается заново на момент показа.

    Схема — `{"video_models": [{"code","label","blurb","aspects","modes",
    "durations","face_grid","prices"}, ...]}`, СВЕРЕНО с реальным
    constructor.js в репо вебаппа (parseCfgFromUrl/FALLBACK_CFG,
    vcModelFromCfgEntry) — задокументирована в docs/BOT_CONTRACT.md. Менять
    форму — только синхронно с правкой parseCfgFromUrl там."""
    models = []
    for code, enabled in (
        ("seedance2", True),
        ("seedance2_fast", SEEDANCE_FAST_ENABLED),
        ("kling3", KLING3_ENABLED),
        ("veo31", VEO31_ENABLED),
        ("wan27", WAN27_ENABLED),
        ("gemini_omni", GEMINI_OMNI_ENABLED),
        ("seedance25", SEEDANCE25_ENABLED),
    ):
        if not enabled:
            continue
        aspects = get_video_aspect_options(code)
        modes = get_seedance_mode_options(code)
        durations = get_seedance_duration_options(code)
        prices = {}
        for mode in (modes or [None]):
            cps = get_video_model_cost_per_second(code, mode)
            prices[mode or "default"] = {str(d): calc_seedance_cost(d, cps) for d in durations}
        models.append({
            "code": code,
            "label": get_video_model_label(code),
            "blurb": get_video_model_blurb(code),
            "aspects": aspects,
            "modes": modes,
            "durations": durations,
            "face_grid": video_model_uses_face_grid(code),
            "prices": prices,
        })
    return {"video_models": models}


def _generation_hub_features_payload() -> dict:
    """Какие конструкторы хаба генерации сейчас включены (docs/specs/
    2026-08-13_webapp_generation_hub_navigation_full.md, раздел 5.2) —
    экран «Создать» использует это, чтобы скрывать плитки продуктов,
    которые ещё не готовы показывать юзерам, вместо «показываем все всегда»
    (которое молча ведёт на выключенный флагом конструктор). Отдельно от
    `get_video_constructor_config` (тяжёлая таблица цен видео-моделей,
    гейтится своим флагом) — эти четыре булевых значения нужны экрану
    «Создать» независимо от того, включён ли именно видео-конструктор."""
    return {
        "video": VIDEO_CONSTRUCTOR_ENABLED,
        "midjourney": MIDJOURNEY_CONSTRUCTOR_ENABLED,
        "avatar": AVATAR_CONSTRUCTOR_ENABLED,
        "photo": PHOTO_CONSTRUCTOR_ENABLED,
    }


def get_prompt_webapp_url(user_id: int = None) -> str:
    base = str(PROMPT_WEBAPP_URL or "").strip()
    if not base:
        return ""
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}rev={PROMPT_WEBAPP_REV}"
    try:
        features_raw = json.dumps(_generation_hub_features_payload(), separators=(",", ":"))
        url += f"&features={base64.urlsafe_b64encode(features_raw.encode()).decode()}"
    except Exception as e:
        logger.warning("Failed to encode generation hub features for webapp URL: %s", e)
    if VIDEO_CONSTRUCTOR_ENABLED:
        try:
            cfg_raw = json.dumps(get_video_constructor_config(), ensure_ascii=False, separators=(",", ":"))
            url += f"&cfg={base64.urlsafe_b64encode(cfg_raw.encode()).decode()}"
        except Exception as e:
            logger.warning("Failed to encode video constructor cfg for webapp URL: %s", e)
    if user_id is not None:
        bal = get_balance(user_id)
        url += f"&balance={bal}"
        try:
            history = get_generation_history(user_id, limit=10)
            if history:
                # Влезаем в лимит URL (~2048). Раньше при 10 записях весь блок
                # истории молча отбрасывался — теперь добираем столько свежих
                # записей (от новых к старым), сколько помещается.
                budget = 2048 - len(url) - len("&h=")
                compact = []
                for h in history:
                    compact.append({
                        "u": h["image_url"],
                        "p": (h["prompt"] or "")[:60],
                        "t": (h["created_at"] or "")[:19],  # без микросекунд — короче
                    })
                    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
                    encoded = base64.urlsafe_b64encode(raw.encode()).decode()
                    if len(encoded) > budget:
                        compact.pop()
                        break
                if compact:
                    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
                    encoded = base64.urlsafe_b64encode(raw.encode()).decode()
                    url += f"&h={encoded}"
        except Exception as e:
            logger.warning("Failed to encode history for webapp URL: %s", e)
    return url


def get_video_aspect_options(model_code: str) -> List[str]:
    """Допустимые aspect ratio для модели — вынесено в отдельную функцию из
    инлайн-фильтра в video_kb (та же логика: Veo 3.1/Wan 2.7/Gemini Omni/
    Seedance 2.5 не поддерживают квадрат и 4:3), чтобы её мог переиспользовать
    и Конструктор вебаппа (get_video_constructor_config/
    apply_webapp_generation_payload), не имеющий готового state с моделью на
    момент валидации формата."""
    aspects = ["16:9", "9:16", "1:1", "4:3"]
    if model_code in ("veo31", "wan27", "gemini_omni", "seedance25"):
        aspects = [a for a in aspects if a not in ("1:1", "4:3")]
    return aspects


# Модели, для которых Конструктор вебаппа/карточка подтверждения показывают
# бинарный переключатель качества «Pro»/«Fast». НЕ идентично условию в
# video_kb (там же список другой — включает wan27): Wan 2.7 в Конструкторе
# сознательно упрощён до одной свободной длительности без выбора качества
# (фронтенд, constructor.js — durations: {"custom":[min,max]}, prices:
# {"per_second": N}, quality: [] — уже смёржено в репо вебаппа), Veo 3.1/
# Gemini Omni физически имеют одно фиксированное качество (get_seedance_mode_
# options возвращает 1 значение или список нерелевантен). Старая полная
# панель video_kb эту константу не использует — ноль изменений её поведения.
VIDEO_QUALITY_TOGGLE_MODELS = ("seedance2", "seedance2_fast", "kling3", "seedance25")


def resolve_webapp_video_quality(model_code: str, quality_value: str) -> Optional[str]:
    """Конструктор вебаппа сознательно упрощает выбор качества до бинарного
    «Pro»/«Fast» (контракт `quality`/`q`, docs/specs/
    2026-08-13_webapp_generation_hub.md) поверх существующих числовых режимов
    Seedance (480p/720p/1080p, get_seedance_mode_options) — «Pro» = самый
    качественный доступный режим модели (последний в списке), «Fast» = самый
    лёгкий (первый). Средний режим (например 720p при 480/720/1080) через
    Конструктор недостижим — это сознательное упрощение UI, полная панель
    video_kb по-прежнему даёт доступ ко всем режимам. Пустое значение — не
    аргумент «пользователь не выбрал», а команда взять ДЕФОЛТ ПРОДУКТА (тот
    же, что у нового юзера в чате, а не автоматически «Pro» — иначе молчаливое
    удорожание генерации при неполном payload)."""
    options = get_seedance_mode_options(model_code)
    if not options:
        return None
    raw = str(quality_value or "").strip().lower()
    if not raw:
        default_source = (
            SEEDANCE_FAST_MODE if model_code == "seedance2_fast"
            else SEEDANCE25_MODE if model_code == "seedance25"
            else SEEDANCE_MODE
        )
        default_mode = normalize_seedance_mode(default_source)
        return default_mode if default_mode in options else options[0]
    if raw in ("fast", "low", "480", "480p"):
        return options[0]
    if raw in ("pro", "high", "best", "1080", "1080p"):
        return options[-1]
    normalized = normalize_seedance_mode(raw)
    return normalized if normalized in options else options[0]


def webapp_video_quality_label(model_code: str, resolved_mode: str) -> Optional[str]:
    """Текст строки «Качество:» в карточке подтверждения Конструктора (Экран
    V2) — «Pro»/«Fast» по бинарной упрощённой модели resolve_webapp_video_quality.
    None — модель не показывает качество вообще (см. VIDEO_QUALITY_TOGGLE_MODELS)."""
    if model_code not in VIDEO_QUALITY_TOGGLE_MODELS:
        return None
    options = get_seedance_mode_options(model_code)
    if len(options) <= 1:
        return None
    if resolved_mode == options[-1]:
        return "Pro"
    if resolved_mode == options[0]:
        return "Fast"
    # Средний режим достижим только через старую полную панель (video_kb),
    # не через Конструктор — честный числовой фолбэк вместо вымышленного Pro/Fast.
    return seedance_mode_ui_label(resolved_mode)


def get_video_constructor_webapp_url(user_id: int) -> str:
    """Персональный URL Конструктора видео — открытие «🎬 Видео для Reels»
    под VIDEO_CONSTRUCTOR_ENABLED и кнопка «🔁 Начать заново» на карточке
    подтверждения (обе точки входа, docs/specs/2026-08-13_webapp_generation_hub.md).
    `tab=video_constructor` (snake_case) — точный query-параметр, который
    реальный constructor.js в репо вебаппа сверяет напрямую из URL перед тем,
    как перевести UI на внутренний экран `switchTab("videoConstructor")`
    (camelCase — это внутреннее имя экрана, не значение query-параметра, см.
    комментарий в начале constructor.js). `cfg` уже пробрасывается
    get_prompt_webapp_url сама, пока VIDEO_CONSTRUCTOR_ENABLED — отдельно
    прокидывать его тут не нужно."""
    base_url = get_prompt_webapp_url(user_id)
    if not base_url:
        return ""
    return f"{base_url}&tab=video_constructor"


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
                state = context.user_data.get("state")
                in_enhance = isinstance(state, UserState) and state.prompt == ENHANCE_PHOTO_PROMPT
                if in_enhance:
                    msg_text = "Фото получено ✅\nМожно улучшать!"
                    markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🚀 Улучшить это фото", callback_data="generate")],
                    ])
                else:
                    # Единый экран фото: статусы черновика (описание/стиль, фото,
                    # модель) + только осмысленные кнопки. Проверка идёт в момент
                    # отправки (через 2с), так что текст, присланный сразу после
                    # фото, тоже успевает учесться в статусе.
                    draft_state = state if isinstance(state, UserState) else UserState()
                    # chat_id == user_id в личных чатах (единственный сценарий этого бота).
                    msg_text = photo_draft_text(draft_state, chat_id)
                    markup = photo_draft_kb(draft_state, chat_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg_text,
                    reply_markup=markup,
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

# Фиксированный промт для «Улучшить фото» — пользователь не редактирует
# описание, просто присылает фото. Модель не меняем (nano banana = gemini),
# черты лица должны остаться прежними.
ENHANCE_PHOTO_PROMPT = (
    "Сделай это фото более профессиональным, будто бы это работа профессионального "
    "фотографа, черты лица не меняй"
)

# Кнопка отмены сразу при входе в режим «Улучшить фото» — без неё юзер, передумав,
# мог только молча перезаписать режим текстом (см. ENHANCE_WAITING_KB чуть ниже).
ENHANCE_WAITING_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("✖️ Отмена", callback_data="reset")],
])


def _prompt_library_button(user_id: Optional[int] = None) -> InlineKeyboardButton:
    # web_app на инлайн-кнопке безопасен с 2026-07-16: вебапп отличает открытие
    # с инлайн-кнопки по query_id в initData и шлёт выбор через Cloudflare
    # Function → answerWebAppQuery → pl_use_{cat_idx}_{item_idx} (обычный
    # callback, обрабатывается ниже) вместо sendData (который для инлайн-кнопок
    # молча терял данные — живой аудит 2026-07-07, поэтому раньше был откат на
    # callback_data=pl_open_webapp). Без user_id — старый 2-кликовый fallback.
    if PROMPT_WEBAPP_URL and user_id is not None:
        return InlineKeyboardButton(
            "📚 Библиотека стилей",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)),
        )
    pl_cb = "pl_open_webapp" if PROMPT_WEBAPP_URL else "pl_open"
    return InlineKeyboardButton("📚 Библиотека стилей", callback_data=pl_cb)


def main_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    # Главное меню — только 2 входные точки в продукты (📸 Фото / 🎬 Видео,
    # каждая открывает свой экран через photo_menu_kb/video_menu_kb) + общие
    # разделы. Раньше все 6 продуктовых кнопок торчали прямо в главном меню —
    # Аня попросила разнести по этапам, фото отдельно от видео (2026-07-29).
    # «📚 Библиотека стилей» намеренно НЕ внутри «Фото»/«Видео» — там и
    # фото-, и видео-стили вперемешку, класть только в один раздел нечестно.
    rows = [
        [
            InlineKeyboardButton("📸 Фото", callback_data="menu_photo"),
            InlineKeyboardButton("🎬 Видео", callback_data="menu_video"),
        ],
        [_prompt_library_button(user_id)],
        [
            InlineKeyboardButton("💰 Баланс", callback_data="show_buy"),
            InlineKeyboardButton("🎁 Пригласить друга", callback_data="open_ref"),
        ],
        [InlineKeyboardButton("❓ Как пользоваться", callback_data="show_help")],
        [
            InlineKeyboardButton("🚨 Проблема", callback_data="report_problem"),
            InlineKeyboardButton("🐞 Баг-баунти", callback_data="bug_bounty"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def photo_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    if PHOTO_CONSTRUCTOR_ENABLED and PROMPT_WEBAPP_URL and user_id is not None:
        generate_button = InlineKeyboardButton(
            "✨ Сгенерировать фото",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id) + "&tab=photo_constructor"),
        )
    else:
        generate_button = InlineKeyboardButton("✨ Сгенерировать фото", callback_data="generate")
    rows = [
        [generate_button],
        [
            InlineKeyboardButton("🖼️ Улучшить фото", callback_data="enhance_photo"),
            InlineKeyboardButton("🪄 Аватар", callback_data="avatar_actions"),
        ],
    ]
    if GPT5_IMAGE_ENABLED:
        rows.append([InlineKeyboardButton("🧠 Модель картинок", callback_data="image_model_menu")])
    # Midjourney (EvoLink) — отдельный мини-флоу (сетка 4 варианта -> апскейл),
    # не третий пункт пикера "Модель картинок" (там контракт "один клик, один
    # результат", у Midjourney есть промежуточный выбор). Скрыт фичефлагом до
    # ручного теста качества (тот же порядок раскатки, что у EvoLink-видео).
    if MIDJOURNEY_ENABLED:
        rows.append([InlineKeyboardButton("🎨 Midjourney 🆕", callback_data="menu_midjourney")])
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="avatar_back_menu")])
    return InlineKeyboardMarkup(rows)


def video_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    video_label = "🎬 Видео для Reels" if SEEDANCE_ENABLED else "🎬 Видео для Reels 🚧"
    rows = [[InlineKeyboardButton(video_label, callback_data="video")]]
    # Kling Motion Control — новый продукт через EvoLink (см. docs/specs/
    # 2026-07-31_evolink_video_provider.md). Скрыт фичефлагом, пока не готов
    # к продакшену (нет API-ключа EvoLink) — но флоу за кнопкой рабочий.
    if MOTION_CONTROL_ENABLED:
        rows.append([InlineKeyboardButton("🕺 Видео с движением 🆕", callback_data="motion_start")])
    # Студия мультиков: ТОЛЬКО инлайн-кнопка (web_app) — вебапп, открытый
    # с нижней reply-кнопки, НЕ получает initData от Telegram (прод-аудит
    # 2026-07-28, platform=tdesktop: initData пуст всегда, initDataUnsafe
    # пустой объект), а студии initData обязателен для каждого запроса.
    # ?tab=studio — вебапп сразу открывает таб студии.
    if STUDIO_ENABLED and PROMPT_WEBAPP_URL and user_id is not None:
        rows.append([InlineKeyboardButton(
            "🎬 Студия мультиков",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id) + "&tab=studio"),
        )])
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="avatar_back_menu")])
    return InlineKeyboardMarkup(rows)


# Постоянная reply-клавиатура: всегда под полем ввода, не пропадает.
# Единственная постоянная навигация (docs/specs/2026-07-02_navigatsiya.md) —
# 7 кнопок, паритет с продуктами полного инлайн-меню (main_menu_kb), тексты
# буква в букву совпадают с одноимёнными кнопками там. «Модель картинок» —
# настройка, а не раздел, «Пригласить друга» — разовое действие: оба остаются
# только в полном инлайн-меню, на постоянную клавиатуру не выносим.
MENU_BTN_PHOTO = "✨ Сгенерировать фото"
MENU_BTN_VIDEO = "🎬 Видео для Reels"
MENU_BTN_AVATAR = "🪄 Аватар"
MENU_BTN_ENHANCE = "🖼️ Улучшить фото"
MENU_BTN_LIBRARY = "📚 Библиотека стилей"
MENU_BTN_BALANCE = "💰 Баланс"
MENU_BTN_HELP = "❓ Как пользоваться"
PERSISTENT_MENU_BUTTONS = {
    MENU_BTN_PHOTO,
    MENU_BTN_VIDEO,
    MENU_BTN_AVATAR,
    MENU_BTN_ENHANCE,
    MENU_BTN_LIBRARY,
    MENU_BTN_BALANCE,
    MENU_BTN_HELP,
}


def persistent_menu_kb(user_id: Optional[int] = None) -> ReplyKeyboardMarkup:
    # Если есть webapp-библиотека — делаем «Библиотека стилей» web_app-кнопкой,
    # чтобы открывалась сразу, без промежуточного тапа «Открыть библиотеку».
    if PROMPT_WEBAPP_URL and user_id is not None:
        library_btn = KeyboardButton(
            MENU_BTN_LIBRARY,
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)),
        )
    else:
        library_btn = KeyboardButton(MENU_BTN_LIBRARY)
    # Хаб генерации (docs/specs/2026-08-13_webapp_generation_hub.md) —
    # VIDEO_CONSTRUCTOR_ENABLED делает «🎬 Видео для Reels» web_app-кнопкой
    # (тот же приём, что уже у MENU_BTN_LIBRARY) — открывает Конструктор
    # напрямую, без похода в бота за пикером модели. Флаг=False (дефолт) —
    # ноль изменений, обычная текстовая кнопка (handle_menu_button её ловит).
    if VIDEO_CONSTRUCTOR_ENABLED and PROMPT_WEBAPP_URL and user_id is not None:
        video_btn = KeyboardButton(
            MENU_BTN_VIDEO,
            web_app=WebAppInfo(url=get_video_constructor_webapp_url(user_id)),
        )
    else:
        video_btn = KeyboardButton(MENU_BTN_VIDEO)
    rows = [
        [KeyboardButton(MENU_BTN_PHOTO), video_btn],
        [KeyboardButton(MENU_BTN_ENHANCE), KeyboardButton(MENU_BTN_AVATAR)],
        [library_btn, KeyboardButton(MENU_BTN_BALANCE)],
        [KeyboardButton(MENU_BTN_HELP)],
    ]
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def image_model_menu_kb(state: UserState) -> InlineKeyboardMarkup:
    selected = get_image_model(state)
    gemini_cost = calc_generation_cost(None, "gemini")
    gpt5_cost = calc_generation_cost(None, "gpt5")
    rows = [
        [InlineKeyboardButton(
            ("● " if selected == "gemini" else "") + f"{get_image_model_label('gemini')} · {gemini_cost} 🍇",
            callback_data="image_model_set_gemini",
        )],
        [InlineKeyboardButton(
            ("● " if selected == "gpt5" else "") + f"GPT-5 Image 🆕 · {gpt5_cost} 🍇",
            callback_data="image_model_set_gpt5",
        )],
        # Недеструктивный возврат: меню модели — это настройка, тут нельзя
        # сбрасывать описание/фото (иначе кнопка «В меню» чистила prompt).
        [InlineKeyboardButton("◀️ В меню", callback_data="avatar_back_menu")],
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

def promo_try_kb(promo_id: str, user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("✨ Хочу так же", callback_data=f"promo_try_{promo_id}")]]
    if PROMPT_WEBAPP_URL and user_id is not None:
        rows.append([InlineKeyboardButton(
            "📚 Библиотека стилей",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)),
        )])
    elif PROMPT_WEBAPP_URL:
        rows.append([InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open_webapp")])
    else:
        rows.append([InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open")])
    return InlineKeyboardMarkup(rows)


def support_report_admin_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Ответить пользователю", callback_data=f"support_reply_{user_id}")]
    ])


def bug_bounty_admin_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🎁 Наградить {BUG_BOUNTY_REWARD} 🍇", callback_data=f"reward_bug_{user_id}")],
        [InlineKeyboardButton("💬 Ответить пользователю", callback_data=f"support_reply_{user_id}")],
    ])



def avatar_kind_label(kind: str) -> str:
    raw = str(kind or "").strip().lower()
    if raw == "male":
        return "мужской 👨"
    if raw == "child":
        return "детский 🧒"
    return "женский 👩"

AVATAR_REFSHEET_PROMPT = (
    "Using the person in the reference photos, generate a single square image containing a 2x2 character reference sheet (4 cells in one image): "
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

    loaded_kinds = [k for k in ("female", "male", "child") if existing.get(k)]
    has_any = bool(loaded_kinds)

    # Активный аватар (тот, что подставляется в генерацию)
    active = None
    if user_id is not None and has_any:
        try:
            active = get_active_avatar_kind(user_id)
        except Exception:
            active = None
    if active not in loaded_kinds:
        active = loaded_kinds[0] if loaded_kinds else None

    short = {"female": "👩 Жен.", "male": "👨 Муж.", "child": "🧒 Дет."}

    rows = []
    if not has_any:
        rows.append([InlineKeyboardButton("❓ Что такое аватар?", callback_data="avatar_help")])
    # Единая кнопка: генерация и есть создание/замена аватара (загрузки фото нет).
    # 🪄 — эмодзи аватара по словарю UI_STYLE (🎨 в словаре нет).
    gen_label = "🪄 Создать / заменить аватар" if has_any else "🪄 Сгенерировать аватар"
    rows.append([InlineKeyboardButton(gen_label, callback_data="avatar_gen_refsheet")])
    if has_any:
        rows.append([InlineKeyboardButton("👀 Показать аватары", callback_data="show_avatar")])

    # Выбор активного аватара — только если загружено 2+ типа (● текущий)
    if len(loaded_kinds) >= 2:
        rows.append([
            InlineKeyboardButton(("● " if k == active else "") + short[k], callback_data=f"avatar_use_{k}")
            for k in loaded_kinds
        ])
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="avatar_back_menu")])
    return InlineKeyboardMarkup(rows)


def avatar_gen_kind_kb() -> InlineKeyboardMarkup:
    # Перед генерацией спрашиваем тип аватара, иначе он всегда сохранялся как женский.
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👩 Женский", callback_data="avatar_gen_kind_female"),
            InlineKeyboardButton("👨 Мужской", callback_data="avatar_gen_kind_male"),
            InlineKeyboardButton("🧒 Детский", callback_data="avatar_gen_kind_child"),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="avatar_actions")],
    ])


def webapp_open_kb(user_id: int = None) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📚 Открыть библиотеку", web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)))]],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
    )


def webapp_inline_kb(user_id: int = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Открыть библиотеку", web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)))]
    ])


def prompt_library_menu_kb() -> InlineKeyboardMarkup:
    # Пустые категории не показываем юзеру (тупик), индекс категории сохраняем для callback
    buttons = [
        InlineKeyboardButton(f"{cat['emoji']} {cat['title']}", callback_data=f"pl_cat_{idx}")
        for idx, cat in enumerate(PROMPT_LIBRARY)
        if (cat.get("items") or [])
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="reset")])
    return InlineKeyboardMarkup(rows)


def prompt_library_category_kb(cat_idx: int) -> InlineKeyboardMarkup:
    rows = []
    items = PROMPT_LIBRARY[cat_idx]["items"]
    for item_idx, item in enumerate(items):
        rows.append([InlineKeyboardButton(_showcase_item_label(item), callback_data=f"pl_view_{cat_idx}_{item_idx}")])
    rows.append([InlineKeyboardButton("◀️ К категориям", callback_data="pl_open")])
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


def _resolve_template_category(item_label: str, cat_idx: Optional[int] = None) -> Optional[str]:
    """Найти категорию шаблона по индексу (точно) или по отображаемому лейблу (best-effort —
    у items нет стабильного id, поэтому webapp-путь без cat_idx ищет по лейблу).
    Лейбл — как в _showcase_item_label: у фото-стилей часто нет "title", только description."""
    if cat_idx is not None and 0 <= cat_idx < len(PROMPT_LIBRARY):
        return str(PROMPT_LIBRARY[cat_idx].get("title") or "").strip() or None
    label = (item_label or "").strip()
    if not label:
        return None
    for cat in PROMPT_LIBRARY:
        for it in cat.get("items") or []:
            if _showcase_item_label(it) == label:
                return str(cat.get("title") or "").strip() or None
    return None


def _log_template_usage_safe(
    user_id: int,
    item_label: str,
    item_kind: str,
    cat_idx: Optional[int] = None,
    item_idx: Optional[int] = None,
) -> None:
    if user_id in ADMIN_IDS:
        return
    label = (item_label or "").strip()
    if not label:
        return
    category = _resolve_template_category(label, cat_idx)
    log_template_usage(user_id, label, item_kind or "image", category=category, cat_idx=cat_idx, item_idx=item_idx)


def prompt_library_item_kb(cat_idx: int, item_idx: int, item_kind: str = "image") -> InlineKeyboardMarkup:
    use_text = "🎬 Использовать в видео" if item_kind == "video" else "✨ Использовать этот стиль"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(use_text, callback_data=f"pl_use_{cat_idx}_{item_idx}")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"pl_cat_{cat_idx}"),
            InlineKeyboardButton("◀️ К категориям", callback_data="pl_open"),
        ],
    ])


def prompt_library_save_category_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(f"{cat['emoji']} {cat['title']}", callback_data=f"plsave_cat_{idx}")
        for idx, cat in enumerate(PROMPT_LIBRARY)
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("✖️ Отмена", callback_data="plsave_cancel")])
    return InlineKeyboardMarkup(rows)


def prompt_library_admin_kb_legacy() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Показать категории", callback_data="pladm_list")],
        [InlineKeyboardButton("➕ Создать категорию", callback_data="pladm_new")],
        [InlineKeyboardButton("✏️ Переименовать категорию", callback_data="pladm_rename")],
        [InlineKeyboardButton("🗑 Удалить категорию", callback_data="pladm_delete")],
        [InlineKeyboardButton("📤 Экспорт JSON", callback_data="pladm_export")],
        [InlineKeyboardButton("✖️ Закрыть", callback_data="pladm_cancel")],
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
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"plhist_open_{prev_offset}"))
    if len(items) >= page_size:
        next_offset = offset + page_size
        nav.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"plhist_open_{next_offset}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("◀️ В админ-меню", callback_data="pladm_open")])
    return InlineKeyboardMarkup(rows)


def prompt_history_preview_kb(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Сохранить в библиотеку", callback_data=f"plhist_export_{item_id}")],
        [InlineKeyboardButton("◀️ К истории", callback_data="plhist_open_0")],
    ])


def prompt_library_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Показать категории", callback_data="pladm_list")],
        [InlineKeyboardButton("🕘 История генераций", callback_data="plhist_open_0")],
        [
            InlineKeyboardButton("➕ Создать", callback_data="pladm_new"),
            InlineKeyboardButton("✏️ Переименовать", callback_data="pladm_rename"),
        ],
        [
            InlineKeyboardButton("🗑 Удалить категорию", callback_data="pladm_delete"),
            InlineKeyboardButton("📤 Экспорт JSON", callback_data="pladm_export"),
        ],
        [InlineKeyboardButton("✖️ Закрыть", callback_data="pladm_cancel")],
    ])


# Video control UI (single final implementation).
def video_model_picker_kb() -> InlineKeyboardMarkup:
    """Первый экран после «🎬 Видео для Reels» — только выбор модели, без
    остальных настроек сразу (решение Ани 2026-07-31). Кнопки — те же
    callback_data video_model_*, что и переключатель модели внутри полной
    панели: тап редактирует ЭТО ЖЕ сообщение в video_kb/video_status_text
    через update_video_panel (button_handler, ветка video_cb.startswith
    ("video_model_")) — новое сообщение не шлётся, ничего дублировать не
    пришлось."""
    buttons = [InlineKeyboardButton("Seedance 2", callback_data="video_model_seedance2")]
    if SEEDANCE_FAST_ENABLED:
        buttons.append(InlineKeyboardButton("Seedance 2 Fast (бета)", callback_data="video_model_seedance2_fast"))
    if KLING3_ENABLED:
        buttons.append(InlineKeyboardButton("Kling 3.0 🆕", callback_data="video_model_kling3"))
    if VEO31_ENABLED:
        buttons.append(InlineKeyboardButton("Veo 3.1 🆕", callback_data="video_model_veo31"))
    if WAN27_ENABLED:
        buttons.append(InlineKeyboardButton("Wan 2.7 🆕", callback_data="video_model_wan27"))
    if GEMINI_OMNI_ENABLED:
        buttons.append(InlineKeyboardButton("Gemini Omni 🆕", callback_data="video_model_gemini_omni"))
    if SEEDANCE25_ENABLED:
        buttons.append(InlineKeyboardButton("Seedance 2.5 💎", callback_data="video_model_seedance25"))
    # Сетка 2 в ряд, не по модели на всю ширину (ТЗ 2026-08-01: 6 полноширинных
    # кнопок подряд на живом скриншоте прода — «бардак»).
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="avatar_back_menu")])
    return InlineKeyboardMarkup(rows)


def video_kb(state: UserState) -> InlineKeyboardMarkup:
    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_video_model(state)
    selected_mode = get_selected_seedance_mode(state)
    cps = get_video_model_cost_per_second(selected_model, selected_mode)
    video_images = get_video_image_urls(state)

    duration_buttons = []
    for sec in get_seedance_duration_options(selected_model):
        cost = calc_seedance_cost(sec, cps)
        prefix = "● " if sec == selected_duration else ""
        duration_buttons.append(
            InlineKeyboardButton(
                f"{prefix}{sec}с · {cost} 🍇",
                callback_data=f"video_duration_{sec}",
            )
        )

    prompt_done = bool(str(getattr(state, "video_prompt", "") or "").strip())
    rows = [
        # Шаги: галочка, когда заполнено (счётчик фото живёт прямо в шаге)
        [InlineKeyboardButton("✅ Описание добавлено" if prompt_done else "1️⃣ Добавить описание", callback_data="video_set_prompt")],
        [InlineKeyboardButton(f"✅ Фото: {len(video_images)} шт." if video_images else "2️⃣ Добавить фото", callback_data="video_set_image")],
    ]
    # Загруженные фото — одна кнопка очистки вместо кучи кнопок удаления
    if video_images:
        rows.append([
            InlineKeyboardButton(
                "🧹 Очистить все фото",
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
    # Модель уже написана текстом в шапке (video_status_text, «Модель: …») —
    # вместо дублирующего блока кнопок-переключателей одна кнопка смены
    # (ТЗ video_panel_declutter, тап возвращает в пикер тем же сообщением).
    rows.append([InlineKeyboardButton("🔄 Сменить модель", callback_data="video_change_model")])
    # Режим качества
    if selected_model in ("seedance2", "seedance2_fast", "kling3", "wan27", "seedance25"):
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
    # Тумблер сетки «детектор лиц» — только Seedance 2/2 Fast (их режет
    # ByteDance-детектор реальных лиц). Вкл = защита от отказа модерации ценой
    # лёгкой сетки на кадре; выкл = чистый кадр, но реальное фото может резаться.
    if video_model_uses_face_grid(selected_model):
        face_grid_on = get_face_grid(state)
        rows.append([
            InlineKeyboardButton(
                "🟢 Детектор лиц: вкл" if face_grid_on else "⚪️ Детектор лиц: выкл",
                callback_data="video_facegrid_toggle",
            )
        ])
    # Формат (aspect ratio)
    selected_aspect = getattr(state, "video_aspect_ratio", "16:9")
    aspect_options = [
        ("16:9", "📺 16:9"), ("9:16", "📱 9:16"), ("1:1", "⬛ 1:1"), ("4:3", "🖼 4:3"),
    ]
    if selected_model in ("veo31", "wan27", "gemini_omni", "seedance25"):
        # Veo 3.1, Wan 2.7, Gemini Omni и Seedance 2.5 не поддерживают квадрат и 4:3.
        aspect_options = [(ar, label) for ar, label in aspect_options if ar not in ("1:1", "4:3")]
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
    if selected_model == "wan27":
        # У Wan 2.7 провайдер реально принимает любое целое 2–10, а не только
        # кнопки 5/10 — даём ввести точное число, не раздувая сетку кнопок.
        dur_min, dur_max = get_seedance_duration_bounds(selected_model)
        is_custom = selected_duration not in get_seedance_duration_options(selected_model)
        custom_label = (
            f"● ✏️ {selected_duration}с · {calc_seedance_cost(selected_duration, cps)} 🍇"
            if is_custom
            else f"✏️ Своя длительность ({dur_min}–{dur_max}с)"
        )
        rows.append([
            InlineKeyboardButton(custom_label, callback_data="video_set_duration"),
        ])
    # Запуск существует только когда есть из чего генерить (описание или фото) —
    # правило docs/UI_STYLE.md: кнопка есть ⇔ действие сейчас возможно.
    if prompt_done or video_images:
        rows.append([InlineKeyboardButton("🚀 Запустить видео", callback_data="video_start")])
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="menu_from_video")])
    return InlineKeyboardMarkup(rows)


def video_status_text(state: UserState) -> str:
    """Экран «🎬 Видео для Reels»: заголовок раздела + компактные статусы
    (макет утверждён Аней 2026-07-20). Шаги живут в кнопках-шагах 1️⃣ 2️⃣
    (video_kb) — нумерованная инструкция их дублировала и ссылалась на
    «🚀 Запустить видео», которой при пустом черновике ещё нет. Сырые URL
    фото юзеру не показываем — счётчика достаточно."""
    prompt_done = bool(state.video_prompt.strip())
    _cur_aspect = getattr(state, "video_aspect_ratio", "16:9")
    _aspect_names = {"16:9": "горизонталь", "9:16": "вертикаль, Reels", "1:1": "квадрат", "4:3": "классика"}
    _aspect_label = f"{_cur_aspect} ({_aspect_names[_cur_aspect]})" if _cur_aspect in _aspect_names else _cur_aspect
    video_images = get_video_image_urls(state)
    image_state = (
        f"{len(video_images)} шт. ✅ (можно до {MAX_SEEDANCE_IMAGE_REFERENCES})"
        if video_images
        else "пока нет"
    )
    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_video_model(state)
    model_label = get_video_model_label(selected_model)
    selected_mode = get_selected_seedance_mode(state)
    cps = get_video_model_cost_per_second(selected_model, selected_mode)
    selected_cost = calc_seedance_cost(selected_duration, cps)
    eta_min = max(2, int(selected_duration * 0.8))
    eta_max = max(eta_min + 1, int(selected_duration * 2.0))
    model_blurb = get_video_model_blurb(selected_model)
    model_line = f"Модель: {model_label} — {model_blurb}" if model_blurb else f"Модель: {model_label}"
    # Подсказка «с чего начать» — только пока черновик пуст (правило UI_STYLE:
    # не рассказывать про заполненные шаги).
    hint_line = "" if (prompt_done or video_images) else "Хватит одного: описание или фото 👇\n"
    # Строка тумблера «детектор лиц» — только у Seedance (у остальных моделей
    # сетка не применяется, строка бы вводила в заблуждение).
    face_grid_line = ""
    if video_model_uses_face_grid(selected_model):
        face_grid_line = f"Детектор лиц: {'вкл 🟢 (защита от отказа модерации)' if get_face_grid(state) else 'выкл ⚪️ (чистый кадр)'}\n"
    return (
        "🎬 Видео для Reels\n\n"
        f"{hint_line}"
        f"{model_line}\n"
        f"Описание: {'есть ✅' if prompt_done else 'пока нет'}\n"
        f"Фото: {image_state}\n"
        f"Формат: {_aspect_label}\n"
        f"Качество: {seedance_mode_ui_label(selected_mode)}\n"
        f"{face_grid_line}"
        f"Длительность: {selected_duration} сек\n"
        f"Стоимость: {selected_cost} изюминок\n"
        f"Результат: обычно через {eta_min}–{eta_max} мин"
    )


def build_video_generation_confirm_text(state: UserState) -> str:
    """Экран V2 «Хаба генерации» — карточка подтверждения в чате (docs/specs/
    2026-08-13_webapp_generation_hub.md, «Экран V2»). Сознательно НЕ
    переиспользует video_status_text — другой набор строк (без «Результат:
    через N мин», длительность форматируется «10с», а не «10 сек», Фото/
    Описание показываются, только если реально заполнены) — общий рефакторинг
    рискует затронуть уже проверенный текст старой чат-панели."""
    resolved_model = get_video_model(state)
    model_label = get_video_model_label(resolved_model)
    model_blurb = get_video_model_blurb(resolved_model)
    model_line = f"Модель: {model_label} — {model_blurb}" if model_blurb else f"Модель: {model_label}"

    aspect = getattr(state, "video_aspect_ratio", "9:16")
    aspect_names = {"16:9": "горизонталь", "9:16": "вертикаль, Reels", "1:1": "квадрат", "4:3": "классика"}
    aspect_label = f"{aspect} ({aspect_names[aspect]})" if aspect in aspect_names else aspect

    duration = get_selected_seedance_duration(state)
    resolved_mode = get_selected_seedance_mode(state)
    cps = get_video_model_cost_per_second(resolved_model, resolved_mode)
    cost = calc_seedance_cost(duration, cps)

    lines = [
        "🎬 Готово к запуску",
        "",
        model_line,
        f"Формат: {aspect_label}",
    ]

    quality_label = webapp_video_quality_label(resolved_model, resolved_mode)
    if quality_label:
        lines.append(f"Качество: {quality_label}")

    lines.append(f"Длительность: {duration}с")

    if video_model_uses_face_grid(resolved_model):
        face_grid_on = get_face_grid(state)
        lines.append(
            "Детектор лиц: " + ("вкл 🟢 (защита от отказа модерации)" if face_grid_on else "выкл ⚪️ (чистый кадр)")
        )

    photos_count = len(get_video_image_urls(state))
    if photos_count:
        lines.append(f"Фото: {photos_count} шт.")

    if (state.video_prompt or "").strip():
        lines.append("Описание: есть")

    lines.append("")
    lines.append(f"Стоимость: {cost} 🍇")
    return "\n".join(lines)


def video_generation_confirm_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Клавиатура карточки подтверждения (Экран V2) — «🚀 Запустить видео»
    переиспользует ровно существующий callback_data="video_start"/
    _cb_video_start/run_seedance (ноль нового кода в биллинге/очереди/доставке
    результата). «🔁 Начать заново» — сознательно НЕ «✏️ Изменить» (MVP не
    сохраняет черновик, см. спеку) — открывает пустой Конструктор заново
    прямым web_app URL, без похода в бота."""
    rows = [[InlineKeyboardButton("🚀 Запустить видео", callback_data="video_start")]]
    if PROMPT_WEBAPP_URL and user_id is not None:
        rows.append([InlineKeyboardButton(
            "🔁 Начать заново",
            web_app=WebAppInfo(url=get_video_constructor_webapp_url(user_id)),
        )])
    else:
        rows.append([InlineKeyboardButton("🔁 Начать заново", callback_data="video")])
    return InlineKeyboardMarkup(rows)


async def update_video_panel(query, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    """Переключатели видео-панели (модель/формат/качество/длительность) правят
    существующее сообщение, а не шлют новое — иначе каждый тап плодит спам
    из отдельных сообщений с почти одинаковым текстом."""
    try:
        await query.message.edit_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        await query.message.reply_text(text, reply_markup=reply_markup)


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
            f"📏 Сделать длиннее — {next_dur}с · {cost} 🍇",
            callback_data=f"video_longer_{next_dur}",
        )])
    if model == "seedance2_fast":
        upgrade_cost = calc_seedance_cost(duration, get_video_model_cost_per_second("seedance2"))
        rows.append([InlineKeyboardButton(
            f"💎 Переделать в Seedance 2 — {upgrade_cost} 🍇",
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
        [InlineKeyboardButton("🔁 Повторить", callback_data="seedance_retry")],
        [InlineKeyboardButton("◀️ В меню", callback_data="menu_from_video")],
    ])


def broadcast_library_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    if PROMPT_WEBAPP_URL and user_id is not None:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📚 Библиотека стилей",
                web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)),
            )]
        ])
    if PROMPT_WEBAPP_URL:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open_webapp")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open")]
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
    # Действия с результатом — одним рядом
    actions = [InlineKeyboardButton("🔁 Повторить", callback_data="generate_again")]
    if user_id and SEEDANCE_ENABLED:
        actions.append(InlineKeyboardButton("🎬 Оживить в видео", callback_data="animate_last"))
    # «Поменять что-то» — вторым рядом; настройка модели дублируется под
    # результатом, чтобы можно было быстро переключиться и повторить.
    switchers = []
    if GPT5_IMAGE_ENABLED:
        switchers.append(InlineKeyboardButton("🧠 Модель картинок", callback_data="image_model_menu"))
    # web_app на инлайн-кнопке безопасен с 2026-07-16 (answerWebAppQuery),
    # см. комментарий в main_menu_kb.
    if PROMPT_WEBAPP_URL and user_id:
        switchers.append(InlineKeyboardButton(
            "📚 Библиотека стилей",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id)),
        ))
    else:
        pl_cb = "pl_open_webapp" if PROMPT_WEBAPP_URL else "pl_open"
        switchers.append(InlineKeyboardButton("📚 Библиотека стилей", callback_data=pl_cb))
    return InlineKeyboardMarkup([
        actions,
        switchers,
        [InlineKeyboardButton("◀️ В меню", callback_data="reset")],
    ])


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
    source = None
    if context.args:
        # payload может быть: ref_<id> | s_<tag> | комбинация ref_<id>-s_<tag>.
        # Токены разделяются дефисом; теги санитизируются до [A-Za-z0-9_].
        for token in context.args[0].strip().split("-"):
            token = token.strip()
            if token.startswith("ref_"):
                try:
                    rid = int(token[4:])
                    if rid != user.id:
                        referrer_id = rid
                except ValueError:
                    pass
            elif token.startswith("s_"):
                tag = re.sub(r"[^A-Za-z0-9_]", "", token[2:])[:32]
                if tag:
                    source = tag

    is_new_user = create_user_if_not_exists(
        user.id, user.username, START_BONUS, referrer_id=referrer_id, source=source
    )

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
                    f"Тебе начислено +{REFERRAL_BONUS_REFERRER} изюминок 🍇\n"
                    f"Твой баланс: {referrer_balance} изюминок"
                ),
            )
        except Exception:
            logger.warning("Failed to notify referrer %s about bonus", referrer_id)
    elif referrer_id and not is_new_user:
        # Существующий пользователь перешёл по чужой реф-ссылке — бонус не положен
        # (защита от абуза), но молчать не стоит: поясняем мягко.
        try:
            await update.message.reply_text(
                "Ты уже зарегистрирован раньше, поэтому бонус за приглашение "
                "не начисляется — он только для новичков.\n"
                "Зато ты можешь сам приглашать друзей и получать изюминки: /ref"
            )
        except Exception:
            logger.warning("Failed to send existing-user referral note to %s", user.id)

    bal = get_balance(user.id)
    state = get_or_init_state(context)
    deactivate_video_session(state)
    avatar_urls = get_avatar_urls(user.id)
    avatar_status = ", ".join([avatar_kind_label(k) for k, v in avatar_urls.items() if v]) or "нет"

    if is_new_user:
        bonus_photos = START_BONUS // BASE_GENERATION_COST
        text = (
            f"Привет! Я Сырник 🧀 — бот для создания AI-фото и видео.\n\n"
            f"🎁 Подарок на старте — {START_BONUS} изюминок (хватит на ~{bonus_photos} фото).\n"
            f"   Изюминки — внутренняя валюта бота: 1 фото = {BASE_GENERATION_COST} изюминок\n\n"
            f"⚡ Попробуй прямо сейчас:\n"
            f"  Нажми «📚 Библиотека стилей» → выбери стиль → «✨ Сгенерировать фото»\n\n"
            f"🪄 Чтобы не загружать своё фото каждый раз — зайди в «🪄 Аватар», "
            f"и бот запомнит твою внешность.\n"
            f"❓ Подробнее: /help"
        )
    else:
        text = (
            f"С возвращением! 🧀\n\n"
            f"💰 Баланс: {bal} изюминок\n"
            f"🪄 Аватары: {avatar_status}\n\n"
            f"Напиши описание картинки или выбери стиль из библиотеки 📚"
        )
    await update.message.reply_text(text, reply_markup=main_menu_kb(user.id))

    # Постоянное нижнее меню — ставим один раз, дальше оно висит всегда.
    await update.message.reply_text(
        "📌 Меню всегда снизу — выбирай раздел в один тап.",
        reply_markup=persistent_menu_kb(user.id),
    )

    # Витрина для новичка: альбом примеров из библиотеки + кнопки "хочу так же".
    # Кнопки (callbacks shc_*) самодостаточны и не зависят от медиа, поэтому
    # битый пример-URL не должен ронять весь экран — показываем кнопки всегда.
    if is_new_user:
        try:
            showcase = pick_showcase_items()
        except Exception:
            showcase = None
            logger.warning("Failed to pick showcase for new user %s", user.id, exc_info=True)
        if showcase:
            media = []
            for _, _, item in showcase:
                try:
                    if _showcase_item_kind(item) == "video":
                        media.append(InputMediaVideo(
                            media=_safe_media_url(item.get("video_url")),
                            supports_streaming=True,
                        ))
                    else:
                        media.append(InputMediaPhoto(
                            media=_safe_media_url(item.get("example_url")),
                        ))
                except Exception:
                    logger.warning("Skipping broken showcase item for user %s", user.id, exc_info=True)
            album_sent = False
            try:
                if len(media) > 1:
                    await update.message.reply_media_group(media)
                    album_sent = True
                elif len(media) == 1 and isinstance(media[0], InputMediaVideo):
                    await update.message.reply_video(media[0].media)
                    album_sent = True
                elif len(media) == 1:
                    await update.message.reply_photo(media[0].media)
                    album_sent = True
            except Exception:
                logger.warning("Failed to send showcase album to new user %s", user.id, exc_info=True)
            digits = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
            buttons = [
                [InlineKeyboardButton(
                    f"{digits[i]} {_showcase_item_label(item)}"
                    + (" 🎬" if _showcase_item_kind(item) == "video" else ""),
                    callback_data=f"shc_{cat_idx}_{item_idx}",
                )]
                for i, (cat_idx, item_idx, item) in enumerate(showcase)
            ]
            header = (
                "Такие фото и видео делают пользователи Сырника 👆\n"
                "Нравится стиль? Жми на него — я всё подготовлю:"
            ) if album_sent else (
                "Готовые стили пользователей Сырника 👇\n"
                "Выбери понравившийся — я всё подготовлю:"
            )
            try:
                await update.message.reply_text(
                    header,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            except Exception:
                logger.warning("Failed to send showcase buttons to new user %s", user.id, exc_info=True)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    bal = get_balance(user.id)
    if PROMPT_WEBAPP_URL:
        library_button = InlineKeyboardButton(
            "📚 Библиотека стилей",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user.id)),
        )
    else:
        library_button = InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open")
    # Главный вопрос юзера — «на сколько хватит?», а не абстрактное число.
    _video_cps = SEEDANCE_FAST_COST_PER_SECOND if SEEDANCE_FAST_ENABLED else SEEDANCE_COST_PER_SECOND
    _video_10s = calc_seedance_cost(10, _video_cps)
    _photos = bal // BASE_GENERATION_COST
    if _photos > 0:
        _enough = f" — хватит на {_photos} фото"
    else:
        _enough = " — на фото пока не хватает"
    await update.message.reply_text(
        f"💰 Твой баланс\n\n"
        f"Изюминок: {bal} 🍇{_enough}\n"
        f"(1 фото = {BASE_GENERATION_COST} изюминок, 1 видео 10 сек = {_video_10s})",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Купить изюминки", callback_data="show_buy")],
            [library_button],
        ])
    )

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text("Напиши мне эту команду в личный чат — там покажу ссылку.")
        return
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    import urllib.parse
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(link)}&text={urllib.parse.quote('Попробуй этот AI-бот для фото!')}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Поделиться с другом", url=share_url)],
        [InlineKeyboardButton("◀️ В меню", callback_data="reset")],
    ])
    # Заголовок экрана = название кнопки «🎁 Пригласить друга» (UI_STYLE).
    await update.effective_message.reply_text(
        f"🎁 Пригласить друга\n\n"
        f"Приглашай друзей и получай изюминки.\n"
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
    await update.effective_message.reply_text(
        "🧀 Сырник — бот для создания AI-фото и видео\n\n"
        "Как пользоваться:\n"
        "1. Напиши описание картинки (например: «девушка на фоне заката»)\n"
        "   или выбери готовый стиль из библиотеки 📚\n"
        "2. Нажми «✨ Сгенерировать фото»\n"
        "3. Получи фото — готово!\n\n"
        "🪄 Аватар — создай аватар по своим фото, и бот поставит тебя в любой образ\n"
        "🖼️ Улучшить фото — качество как у профессионального фотографа, лицо не меняется\n"
        "🎬 Видео для Reels — оживи фото или сгенерируй ролик по описанию (4 модели на выбор)\n"
        f"💰 Твой баланс: {bal} изюминок (1 фото = {BASE_GENERATION_COST} изюминок)\n\n"
        "Изюминки — внутренняя валюта бота. Их можно купить или получить "
        "за приглашённых друзей.\n\n"
        "Команды:\n"
        "/start — главное меню\n"
        "/balance — твой баланс\n"
        "/buy — купить изюминки\n"
        "/ref — пригласить друга (+изюминки обоим)\n"
        "/report — сообщить о проблеме\n"
        f"/bugbounty — нашёл(а) реальный баг → {BUG_BOUNTY_REWARD} 🍇 в подарок\n"
        "/help — эта справка",
        reply_markup=main_menu_kb(user.id),
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
    # Заголовок экрана = название кнопки, с которой на него пришли (UI_STYLE).
    await update.effective_message.reply_text(
        "🚨 Проблема\n\n"
        "Опиши, что не работает.\n\n"
        "Примеры:\n"
        "• Генерация долго загружается\n"
        "• Фото выходит размытым\n"
        "• Не получается создать аватар\n\n"
        "Можешь добавить скриншот вторым сообщением.",
        # НЕ "reset": отмена репорта не должна стирать черновик фото/стиля,
        # который юзер готовил до того, как решил пожаловаться.
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✖️ Отмена", callback_data="report_cancel")
        ]])
    )


async def bug_bounty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """«🐞 Баг-баунти» — отдельно от «🚨 Проблема»: не жалоба на неудобство,
    а осознанный репорт реального бага в обмен на награду. Тот же транспорт
    (пересылка админу), но своя пометка в сообщении админу и кнопка
    «Наградить» — см. BUG_BOUNTY_REWARD, handle_text (waiting_for_bug_report),
    button_handler (reward_bug_)."""
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)
    state = get_or_init_state(context)
    state.waiting_for_bug_report = True
    await update.effective_message.reply_text(
        f"🐞 Баг-баунти\n\n"
        f"Нашёл(а) реальный баг — опиши его, и если подтвердится, "
        f"получишь {BUG_BOUNTY_REWARD} 🍇 в подарок. Награда за каждый "
        f"найденный баг, без ограничения по числу.\n\n"
        "Что считается багом: не работает как задумано, ошибка, зависание,"
        " не то, что написано в кнопке/тексте. Опиши, что делал(а) и что"
        " пошло не так — чем подробнее, тем быстрее проверю.\n\n"
        "Можешь добавить скриншот вторым сообщением.",
        # НЕ "reset" — см. комментарий в report_problem_command.
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✖️ Отмена", callback_data="report_cancel")
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
    # Cost of one 10-second video using the default model shown in the video panel (Fast).
    _default_video_cps = SEEDANCE_FAST_COST_PER_SECOND if SEEDANCE_FAST_ENABLED else SEEDANCE_COST_PER_SECOND
    _video_10s_cost = calc_seedance_cost(10, _default_video_cps)

    # Рублёвый эквивалент результата — по «честной середине» (пакет
    # «Контент-неделя»; если его нет — средний пакет списка).
    _mid_pack = next(
        (p for p in BUY_PACKS if p.get("name") == "Контент-неделя"),
        BUY_PACKS[len(BUY_PACKS) // 2] if BUY_PACKS else {"count": 1, "price": 0},
    )
    _rub_per_iz = _mid_pack["price"] / _mid_pack["count"] if _mid_pack["count"] else 0
    _photo_rub = round(BASE_GENERATION_COST * _rub_per_iz)
    _video_rub = round(_video_10s_cost * _rub_per_iz)

    # Самый выгодный пакет (мин. цена за изюминку) и его скидка к самому
    # дорогому за изюминку — считаем динамически из BUY_PACKS.
    _ppi = [(p, p["price"] / p["count"]) for p in BUY_PACKS if p["count"]]
    _best_pack = min(_ppi, key=lambda x: x[1])[0] if _ppi else None
    _base_ppi = max((ppi for _, ppi in _ppi), default=0)
    _best_ppi = min((ppi for _, ppi in _ppi), default=0)
    _best_discount = round((1 - _best_ppi / _base_ppi) * 100) if _base_ppi else 0

    keyboard = []
    for pack in BUY_PACKS:
        photo_count = max(1, pack["count"] // BASE_GENERATION_COST)
        video_count = pack["count"] // _video_10s_cost
        # Акцент на видео: 🎬 первым, где пакета хватает на видео. Иконки
        # компактнее слов — строка не обрезается на узком экране.
        if video_count > 0:
            hint = f"🎬 {video_count} · 📸 до {photo_count}"
        else:
            hint = f"📸 до {photo_count}"
        # Порядок важен: цена идёт сразу после названия, чтобы при узком
        # экране Telegram обрезал необязательную подсказку, а не цену.
        name = pack.get("name") or ""
        if pack is _best_pack and _best_discount > 0:
            name = f"{name} −{_best_discount}% 🔥".strip()
        parts = []
        if name:
            parts.append(name)
        parts.append(f"{pack['price']} ₽")
        parts.append(hint)
        keyboard.append([
            InlineKeyboardButton(
                text=" · ".join(parts),
                callback_data=f"buy_{pack['count']}_{pack['price']}",
            )
        ])

    keyboard.append([InlineKeyboardButton("◀️ В меню", callback_data="reset")])

    await update.effective_message.reply_text(
        f"💰 Пополнить баланс\n\n"
        f"• 📸 1 фото = {BASE_GENERATION_COST} изюминок 🍇 (≈ {_photo_rub} ₽)\n"
        f"• 🎬 1 видео 10 сек = {_video_10s_cost} изюминок (≈ {_video_rub} ₽)\n"
        f"  (длиннее видео — дороже, короче — дешевле)\n\n"
        f"Чем больше пакет — тем дешевле каждый образ.\n"
        f"Выбери пакет 👇",
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

    if not save_payment_once(user.id, payment_id, count, amount_rub=price):
        await update.message.reply_text("Платёж уже обработан.")
        return

    # add_izyminki is now done atomically inside save_payment_once
    new_balance = get_balance(user.id)

    await update.message.reply_text(
        f"Оплата прошла успешно ✅\n"
        f"Начислено {count} изюминок 🍇\n"
        f"Твой баланс: {new_balance} изюминок\n\n"
        f"Можешь запускать генерацию!",
        reply_markup=main_menu_kb(user.id),
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
        title="Покупка изюминок 🍇",
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
                    reply_markup=promo_try_kb(promo_id, target_user_id),
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
                        reply_markup=promo_try_kb(promo_id, target_user_id),
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
                library_kb = broadcast_library_kb(target_user_id)
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


async def set_avatar_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команда: установить готовое фото как свой аватар.
    Использование: ответить этой командой на сообщение с фото —
    /set_avatar [female|male|child]. Только для админов (юзерам недоступно,
    публичной загрузки аватара нет — монетизация не затрагивается).
    """
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    target = update.message.reply_to_message
    if not target or not target.photo:
        await update.message.reply_text(
            "Ответь этой командой на сообщение с фото.\n"
            "Пример: пришли фото, затем ответь на него «/set_avatar female»."
        )
        return

    kind = (context.args[0].strip().lower() if context.args else "female")
    if kind not in ("female", "male", "child"):
        kind = "female"

    try:
        photo = target.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        bio = io.BytesIO()
        await file.download_to_memory(out=bio)
        bio.seek(0)
        direct_url = _cache_image(bio.read())
        persistent_url = await _persist_image_ref(direct_url)
    except Exception:
        logger.exception("set_avatar_admin: failed to fetch/persist photo for user=%s", user.id)
        await update.message.reply_text("Не удалось обработать фото. Попробуй ещё раз.")
        return

    if not persistent_url:
        await update.message.reply_text("Не удалось залить фото на хостинг — попробуй ещё раз чуть позже.")
        return

    set_avatar_url(user.id, persistent_url, kind)
    set_active_avatar_kind(user.id, kind)
    await update.message.reply_text(
        f"Готово — аватар ({avatar_kind_label(kind)}) установлен и сделан активным ✅"
    )


# ----------------------------
# Input collection
# ----------------------------

# ══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ СООБЩЕНИЙ: текст, фото, видео, webapp
# ══════════════════════════════════════════════════════════════

async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Постоянная reply-клавиатура шлёт обычный текст. Перехватываем ярлыки
    разделов и открываем то же, что инлайн-кнопки. True — если это была
    кнопка меню (как промпт обрабатывать уже не нужно)."""
    if text not in PERSISTENT_MENU_BUTTONS:
        return False
    user = update.effective_user

    if text == MENU_BTN_LIBRARY:
        if PROMPT_WEBAPP_URL:
            await update.message.reply_text(
                "Открывай библиотеку по кнопке ниже:",
                reply_markup=webapp_open_kb(user.id),
            )
        else:
            await update.message.reply_text(
                "Выбери категорию. Покажу лучшие стили с примерами 👇",
                reply_markup=prompt_library_menu_kb(),
            )
        return True

    if text == MENU_BTN_VIDEO:
        if not SEEDANCE_ENABLED:
            await update.message.reply_text(video_unavailable_text(), reply_markup=main_menu_kb())
            return True
        # Хаб генерации в вебаппе (docs/specs/2026-08-13_webapp_generation_hub.md) —
        # вместо пикера модели/панели сразу открываем экран «Конструктор»,
        # если фича включена и есть URL вебаппа. Kill-switch выключен по
        # умолчанию — ничего не меняется, пока Аня не включит флаг.
        if VIDEO_CONSTRUCTOR_ENABLED and PROMPT_WEBAPP_URL:
            await update.message.reply_text(
                "🎬 Видео для Reels\n\n"
                "Настрой модель, формат, качество, фото и описание в конструкторе — "
                "и возвращайся сюда за запуском.",
                reply_markup=video_constructor_kb(user.id),
            )
            return True
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_prompt = False
        state.waiting_for_video_image = True
        state.waiting_for_motion_video = False
        # Сначала только выбор модели — см. комментарий у video_cb == "video"
        # в button_handler (тот же флоу, инлайн-путь). Модель уже выбрана в
        # этой сессии — сразу полная панель (ТЗ video_panel_declutter).
        if state.video_model_picked:
            await update.message.reply_text(
                video_status_text(state),
                reply_markup=video_kb(state),
            )
            return True
        await update.message.reply_text(
            "🎬 Видео для Reels\n\n"
            "Можно сразу отправлять текст описания и фото — сохраню в черновик.\n"
            "Выбери модель:",
            reply_markup=video_model_picker_kb(),
        )
        return True

    if text == MENU_BTN_PHOTO:
        if PHOTO_CONSTRUCTOR_ENABLED and PROMPT_WEBAPP_URL:
            await update.message.reply_text(
                "✨ Сгенерировать фото\n\n"
                "Опиши, что хочешь получить, и добавь фото в конструкторе — "
                "и возвращайся сюда за запуском.",
                reply_markup=photo_constructor_kb(user.id),
            )
            return True
        state = get_or_init_state(context)
        deactivate_video_session(state)
        await update.message.reply_text(
            "✍️ Напиши описание картинки одним сообщением — и я сгенерирую фото.\n\n"
            "Например: «девушка на фоне заката», «кот в космосе», «портрет в стиле кино».\n"
            "Можно приложить своё фото как референс.",
        )
        return True

    if text == MENU_BTN_AVATAR:
        await update.message.reply_text(
            "🪄 AI-аватар — это ты в любом образе\n\n"
            "Пришли 3–8 своих фото, и нейросеть сгенерирует аватар и запомнит твою внешность.\n"
            "После этого в каждой генерации будешь появляться именно ты.\n\n"
            "Если загружено несколько аватаров (👩/👨/🧒) — кнопками ниже "
            "выбери, каким генерировать (● текущий).",
            reply_markup=avatar_actions_kb(user.id),
        )
        return True

    if text == MENU_BTN_ENHANCE:
        state = get_or_init_state(context)
        deactivate_video_session(state)
        state.prompt = ENHANCE_PHOTO_PROMPT
        state.image_prompt = ""
        state.style_extract = False
        state.references = []  # старое фото не подмешиваем — нужно новое, для улучшения
        state.image_model = "gemini"  # nano banana, фикс по требованию функции
        await update.message.reply_text(
            "Пришли фото, которое нужно улучшить 🖼️\n"
            "Бот повысит качество и сделает его похожим на кадр от профессионального "
            "фотографа — черты лица останутся прежними.",
            reply_markup=ENHANCE_WAITING_KB,
        )
        return True

    if text == MENU_BTN_BALANCE:
        await balance(update, context)
        return True

    if text == MENU_BTN_HELP:
        await help_command(update, context)
        return True

    return False


async def _submit_report(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    state: "UserState",
    kind: str,
    report_text: str,
    photo_file_id: Optional[str] = None,
) -> None:
    """Общая отправка репорта админам — единая точка для «🚨 Проблема» и
    «🐞 Баг-баунти», текстом (handle_text) или текст+фото одним сообщением
    (handle_photo, caption). kind: "problem" | "bug".

    Живой баг 2026-07-19 (второй за день): handle_photo вообще не проверял
    waiting_for_problem_report/waiting_for_bug_report при caption — текст
    всегда становился обычным state.prompt, фото — обычным reference,
    репорт с фото в одном сообщении не уходил вовсе. Раньше это же поле
    дублировалось в handle_text для двух почти одинаковых блоков
    (проблема/баг) — вынесено сюда, чтобы такой баг не повторился в
    третьем месте."""
    username = f"@{user.username}" if user.username else "нет"
    full_name = (user.full_name or "").strip() or "нет"
    label = "🐞 Баг-баунти" if kind == "bug" else "🚨 Сообщение о проблеме"
    admin_kb = bug_bounty_admin_kb(user.id) if kind == "bug" else support_report_admin_kb(user.id)
    admin_message = (
        f"{label}\n\n"
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
                reply_markup=admin_kb,
            )
            if photo_file_id:
                await context.bot.send_photo(chat_id=admin_id, photo=photo_file_id)
            delivered += 1
        except Exception:
            logger.exception(f"Failed to forward {kind} report to admin_id={admin_id}")

    reply_target = update.message or update.effective_message
    if delivered > 0:
        if not photo_file_id:
            # Фото уже приложено этим же сообщением — новый скриншот вторым
            # сообщением не ждём (см. pending_report_kind в handle_photo).
            state.pending_report_kind = kind
            state.pending_report_kind_at = time.time()
        if kind == "bug":
            confirm = (
                f"Спасибо! Если это реальный баг — начислю {BUG_BOUNTY_REWARD} 🍇 "
                "и пришлю уведомление.\n"
            )
        else:
            confirm = "Спасибо, отправила в поддержку ✅\n"
        if not photo_file_id:
            confirm += "Можешь добавить скриншот следующим сообщением."
        await reply_target.reply_text(confirm.rstrip(), reply_markup=main_menu_kb(user.id))
    else:
        await reply_target.reply_text(
            "Не получилось передать репорт прямо сейчас.\nПопробуй еще раз через минуту.",
            reply_markup=main_menu_kb(user.id),
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    # Telegram доставляет боту копию его же answerWebAppQuery-сообщения как
    # обычный message-update в личном чате (via_bot = сам бот) — например,
    # заглушку "📚 Стиль подобран — жми ниже 👇" из инлайн-1-тапа библиотеки
    # (docs/specs/2026-07-17_via_bot_message_leak.md). Без этого фильтра
    # текст заглушки доходил до state.prompt = text ниже и затирал реально
    # выбранный стиль раньше, чем успевал сработать pl_use_ по кнопке под ней.
    _via_bot = getattr(update.message, "via_bot", None)
    if _via_bot and _via_bot.id == context.bot.id:
        return

    text = update.message.text.strip()
    if not text:
        return

    # Постоянное нижнее меню — обрабатываем до всего остального, чтобы тап
    # по кнопке всегда открывал раздел, а не уходил в генерацию.
    if await handle_menu_button(update, context, text):
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
                reply_markup=main_menu_kb(user.id),
            )
            return

        state.waiting_for_problem_report = False
        await _submit_report(update, context, user, state, "problem", text.strip())
        return

    if state.waiting_for_bug_report:
        if text.lower() in {"отмена", "cancel", "/cancel"}:
            state.waiting_for_bug_report = False
            await update.message.reply_text(
                "Ок, отмена. Если что — кнопку «🐞 Баг-баунти» можно нажать снова.",
                reply_markup=main_menu_kb(user.id),
            )
            return

        state.waiting_for_bug_report = False
        await _submit_report(update, context, user, state, "bug", text.strip())
        return

    if state.waiting_for_mj_prompt:
        state.mj_prompt = text
        state.waiting_for_mj_prompt = False
        state.waiting_for_mj_image = True
        await update.message.reply_text(
            "Промт сохранён ✅\n"
            "Можешь прислать фото-референс (необязательно) или сразу жми «🚀 Сгенерировать».",
            reply_markup=mj_draft_kb(state),
        )
        return

    if state.waiting_for_board_style_correction:
        # Доски — Full: юзер нажал «✏️ Поправить» под сообщением-анализом и
        # прислал свой текст стиля доски следующим сообщением (docs/specs/2026-08-09_mood_boards_full.md).
        state.waiting_for_board_style_correction = False
        corrected = text.strip()
        if not corrected:
            await update.message.reply_text(
                "Пустой текст не сохранила — пришли описание стиля доски ещё раз."
            )
            return
        state.board_style_note = corrected
        state.board_style_board_id = state.board_style_pending_board_id
        state.board_style_short_id = state.board_style_pending_short_id or _board_short_id(f"custom-{int(time.time())}")
        state.board_style_pending_note = None
        state.board_style_pending_board_id = None
        state.board_style_pending_title = ""
        state.board_style_pending_short_id = ""
        await update.message.reply_text(
            "✅ Стиль доски подключён — активен для следующих генераций.",
            reply_markup=board_style_disable_kb(state.board_style_short_id),
        )
        return

    if state.waiting_for_video_duration:
        state.waiting_for_video_duration = False
        model_code = get_video_model(state)
        dur_min, dur_max = get_seedance_duration_bounds(model_code)
        digits = "".join(ch for ch in text if ch.isdigit())
        try:
            picked = int(digits) if digits else int(text.strip())
        except ValueError:
            picked = None
        if picked is None or not (dur_min <= picked <= dur_max):
            await update.message.reply_text(
                f"Не поняла число секунд. Напиши целое от {dur_min} до {dur_max}.",
                reply_markup=video_kb(state),
            )
            return
        state.video_duration = normalize_seedance_duration(picked, model_code)
        state.video_session_active = True
        await update.message.reply_text(
            f"Длительность: {state.video_duration} сек ✅",
            reply_markup=video_kb(state),
        )
        return

    if state.waiting_for_video_prompt or state.video_session_active:
        state.video_prompt = text
        state.image_prompt = ""
        state.waiting_for_video_prompt = False
        state.video_session_active = True
        await update.message.reply_text(
            "Описание для видео сохранено ✅\n"
            "Теперь можешь отправить фото, выбрать длительность/качество и нажать запуск.",
            reply_markup=video_kb(state),
        )
        return

    if state.prompt == ENHANCE_PHOTO_PROMPT:
        # Режим «Улучшить фото» ждёт ФОТО, а не описание — раньше текст молча
        # перезаписывал служебный промт и юзер тихо оказывался в обычной
        # генерации, не заметив (макет утверждён Аней 2026-07-15).
        context.user_data["enhance_pending_text"] = text
        await update.message.reply_text(
            "Я жду фото для улучшения 🖼️\n"
            "Пришли фото — или преврати этот текст в описание для обычной генерации:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✍️ Генерить по этому тексту", callback_data="enhance_use_pending_text")],
                [InlineKeyboardButton("✖️ Отмена", callback_data="reset")],
            ]),
        )
        return

    deactivate_video_session(state)
    state.prompt = text
    state.style_extract = False
    state.pending_report_kind = ""

    # Единый экран фото: статусы черновика + только осмысленные кнопки.
    await update.message.reply_text(photo_draft_text(state, user.id), reply_markup=photo_draft_kb(state, user.id))


def _append_reference_url(state: "UserState", direct_url: str) -> bool:
    """Добавляет уже захостенный URL в state.references с тем же потолком,
    что и ручная загрузка фото юзером (2 при активном style_extract, иначе
    8 — максимум, реально используемый в одной генерации). Общий код для
    handle_photo (фото из чата) и apply_webapp_board_refs_payload (фото из
    доски мудборда, docs/specs/2026-08-09_mood_boards.md) — правь оба
    вызывающих места, если меняешь потолок здесь. Возвращает True, если URL
    реально добавлен (потолок не превышен)."""
    _refs_cap = 2 if state.style_extract else 8
    if len(state.references) < _refs_cap:
        state.references.append(direct_url)
        state.references_updated_at = time.time()
        return True
    return False


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    state = get_or_init_state(context)
    cache_media_group_message(update.effective_message)

    if state.waiting_for_problem_report or state.waiting_for_bug_report:
        # Текст + фото ОДНИМ сообщением (caption) — раньше сюда вообще не
        # заглядывали: caption всегда становился обычным state.prompt, фото —
        # обычным reference'ом для генерации, репорт не уходил (живой баг
        # 2026-07-19, второй за день). Пустой caption — тоже валидный репорт,
        # юзер мог решить, что один скриншот всё объясняет.
        kind = "bug" if state.waiting_for_bug_report else "problem"
        state.waiting_for_problem_report = False
        state.waiting_for_bug_report = False
        caption = (update.message.caption or "").strip()
        report_text = caption or "(без текста — только скриншот)"
        photo = update.message.photo[-1]
        await _submit_report(update, context, user, state, kind, report_text, photo_file_id=photo.file_id)
        return

    if state.pending_report_kind and (time.time() - state.pending_report_kind_at) <= PENDING_REPORT_SCREENSHOT_TTL_SECONDS:
        # Скриншот "вторым сообщением" к репорту — раньше тихо утекал в
        # обычные references генерации, потому что флаг ожидания ТЕКСТА
        # сбрасывается сразу после текста репорта, а фото никто не ждал
        # (живой баг 2026-07-19). Пересылаем админам с той же меткой, не
        # трогая state.prompt/state.references генерации.
        kind_label = "🐞 Баг-баунти" if state.pending_report_kind == "bug" else "🚨 Проблема"
        state.pending_report_kind = ""
        photo = update.message.photo[-1]
        delivered = 0
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo.file_id,
                    caption=f"{kind_label} — скриншот от user_id {user.id}",
                )
                delivered += 1
            except Exception:
                logger.exception(f"Failed to forward report screenshot to admin_id={admin_id}")
        if delivered > 0:
            await update.message.reply_text("Скриншот добавлен к репорту ✅")
        else:
            await update.message.reply_text("Не получилось переслать скриншот. Попробуй ещё раз.")
        return

    state.pending_report_kind = ""

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
                        f"Максимум {MAX_AVATAR_PHOTOS} фото для аватара. Нажми «🚀 Сгенерировать аватар» или начни заново."
                    )
                    return
                state.avatar_photos.append(direct_url)
            count = len(state.avatar_photos)
            # 🚀 — единый эмодзи запуска (UI_STYLE): кнопка честно говорит, что
            # запустится генерация, а не просто «Готово».
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"🚀 Сгенерировать аватар ({count} фото)", callback_data="avatar_gen_start")
            ]])
            status_text = (
                f"Получено фото: {count} ✅\n"
                "Можешь отправить ещё с других ракурсов или нажать «🚀 Сгенерировать аватар»."
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

        caption = (update.message.caption or "").strip()

        if state.waiting_for_mj_image:
            # Midjourney: фото-референс необязателен, генерация запускается
            # отдельной кнопкой (не автосразу, как у Kling Motion Control) —
            # юзер может прислать текст промта и фото в любом порядке.
            state.mj_reference = direct_url
            if caption and not (state.mj_prompt or "").strip():
                state.mj_prompt = caption
            await update.message.reply_text(
                "Фото-референс добавлено ✅\nЖми «🚀 Сгенерировать», когда готов(а).",
                reply_markup=mj_draft_kb(state),
            )
            return

        if state.waiting_for_motion_image:
            # Kling Motion Control мини-флоу: ровно 1 фото, затем сразу запуск —
            # не копим буфер, как в Seedance (waiting_for_video_image ниже).
            user_m = update.effective_user
            if user_m.id in queued_user_ids or user_m.id in processing_user_ids:
                await update.message.reply_text("Уже выполняется другая задача. Подожди.")
                return
            state.motion_image_url = direct_url
            state.waiting_for_motion_image = False
            processing_user_ids.add(user_m.id)
            try:
                context.application.create_task(run_kling_motion_control(update, context))
            except Exception:
                processing_user_ids.discard(user_m.id)
                logger.exception("create_task(run_kling_motion_control) failed for user=%s", user_m.id)
                await update.message.reply_text("Не удалось запустить генерацию. Попробуй ещё раз.")
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
            if caption:
                state.video_prompt = caption
            logger.info(
                "handle_photo: added video image for user=%s, total=%s, animation_source_urls=%s",
                user.id, total_refs, state.animation_source_urls,
            )
            caption_line = f"Описание сохранено: «{caption}»\n" if caption else ""
            await update.message.reply_text(
                f"Фото для видео добавлено ✅\n"
                f"Сейчас загружено: {total_refs}/{MAX_SEEDANCE_IMAGE_REFERENCES}\n"
                f"{caption_line}"
                "Бот запомнит внешность с фото.\n"
                "Можешь отправить ещё фото или запускать генерацию.",
                reply_markup=video_kb(state),
            )
            return

        state.animation_source_url = direct_url
        # style_extract ждёт РОВНО 2 фото (своё лицо + референс стиля) — 3-е и
        # дальше игнорируем, а не добавляем в буфер, иначе пайплайн снова может
        # схватить не то фото (см. _set_style_extract, P0 2026-07-17).
        _append_reference_url(state, direct_url)  # cap to max used in generation

        # Фото и промт одним сообщением (caption) — та же логика, что и для
        # отдельного текстового сообщения: описание сохраняется сразу, не
        # нужно присылать его вторым сообщением. В режиме «Улучшить фото»
        # state.prompt — служебный фиксированный промт, caption его не трогает.
        if caption and state.prompt != ENHANCE_PHOTO_PROMPT:
            deactivate_video_session(state)
            state.prompt = caption
            state.style_extract = False

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

    if state.motion_control_active:
        # Kling Motion Control мини-флоу (не Seedance) — следующий шаг ждёт фото,
        # video_kb() здесь неуместен (это UI для Seedance/Kling3/Veo/Wan).
        state.waiting_for_motion_image = True
        await update.message.reply_text(
            "Видео с движением добавлено ✅\n\n"
            "Теперь пришли своё фото — перенесу это движение на него."
        )
        return

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
    state.style_extract = False

    await update.message.reply_text(
        f"Готово ✨\nСтиль «{title}» применён.",
        reply_markup=photo_draft_kb(state, user.id),
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

    item_kind = "video" if action == "set_video_prompt" else "image"
    raw_title = str(payload.get("title") or "").strip()
    if raw_title and update.effective_user:
        _log_template_usage_safe(update.effective_user.id, raw_title, item_kind)

    state = get_or_init_state(context)
    state.image_prompt = ""
    if action == "set_video_prompt":
        state.video_prompt = prompt
        state.video_session_active = True
        state.waiting_for_video_image = True
        # Правило AGENT_NOTES [2026-07-16]: любая прямая запись промта без
        # резолва item обязана сбрасывать style_extract — иначе следующая
        # ФОТО-генерация требует ровно 2 фото под чужой двух-референсный стиль.
        # Image-ветка ниже это делает, видео-ветка была неучтённым путём.
        state.style_extract = False
    else:
        deactivate_video_session(state)
        state.prompt = prompt
        state.style_extract = False

    if update.effective_message:
        if action == "set_video_prompt":
            await update.effective_message.reply_text(
                f"Готово ✨\nСтиль «{title}» применён для видео.\n"
                "Теперь отправь фото и запускай видео.",
                reply_markup=video_kb(state),
            )
        else:
            _uid = update.effective_user.id if update.effective_user else None
            await update.effective_message.reply_text(
                f"Готово ✨\nСтиль «{title}» применён.",
                reply_markup=photo_draft_kb(state, _uid),
            )
    return True


def _board_short_id(board_id: str) -> str:
    """Укорачивает UUID доски вебаппа (36 символов) до префикса, который
    влезает в callback_data (лимит Telegram — 64 байта) вместе с префиксом
    вида `bsc_`/`bse_`/`bsoff_` — см. docs/specs/2026-08-09_mood_boards_full.md,
    п.2. Первых 16 символов UUID достаточно уникально в пределах одного юзера
    (максимум ~5 досок), не нужен отдельный ttl — переписывается при каждом
    новом анализе."""
    return (board_id or "")[:16]


def apply_board_style_note(prompt: str, board_style_note: str) -> str:
    """Накладывает подтверждённое AI-описание стиля активной доски (Доски —
    Full, docs/specs/2026-08-09_mood_boards_full.md) как БАЗОВЫЙ слой ПЕРЕД
    промтом конкретного выбранного стиля — доска задаёт общее
    настроение/палитру/композицию, промт стиля рисует поверх конкретный
    образ. Вызывается КАЖДУЮ генерацию, пока доска подключена (в отличие от
    one-shot state.references/style_extract), ДО apply_user_note_override —
    «свои пожелания» юзера к конкретному стилю остаются финальным словом.
    """
    if not board_style_note:
        return prompt
    return (
        f"Overall visual style/mood baseline from the user's mood board "
        f"(apply as a background aesthetic layer under everything else — "
        f"palette, atmosphere, composition): {board_style_note}\n\n"
        f"{prompt}"
    )


async def apply_webapp_board_refs_payload(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    """MVP «Доска = коллекция референсов» (docs/specs/2026-08-09_mood_boards.md).

    Вебапп хранит доски целиком на своей стороне (localStorage) — бот НЕ
    хранит доски, только принимает уже захостенные на imgbb URL фото доски
    (`board_refs`/`br`) и кладёт их в state.references ТЕМ ЖЕ кодом, что и
    ручная загрузка фото (`_append_reference_url`). Никакого AI-анализа
    стиля здесь нет — это Full-версия, отдельная будущая задача. Поле имени
    доски — переиспользует уже существующее `title`/`t` (действие
    "board_refs" делает семантику однозначной, конфликта с
    set_prompt/set_video_prompt нет, там то же поле означает название стиля).
    Намеренно НЕ трогает `note`/`n` — это другая сущность («свои пожелания»
    юзера к стилю, docs/specs/2026-07-17_note_override_weak.md), доски её не
    касаются вообще на MVP-этапе."""
    board_name = str(payload.get("title") or payload.get("t") or "").strip() or "Без названия"
    urls_raw = payload.get("board_refs")
    if urls_raw is None:
        urls_raw = payload.get("br")
    if not isinstance(urls_raw, list):
        urls_raw = []

    state = get_or_init_state(context)
    deactivate_video_session(state)
    # Свежий старт персонализации через доску — не мешаем со случайно
    # залежавшимся style_extract/references с прошлой, не связанной сессии
    # (тот же принцип, что и _set_style_extract при резолве item, AGENT_NOTES
    # 2026-07-16 «персистентный буфер references путал лицо»).
    _set_style_extract(state, False)
    state.references = []
    state.references_updated_at = 0.0
    # Доски — Full (docs/specs/2026-08-09_mood_boards_full.md): активация
    # доски через board_refs — тоже «переключение на другую доску», снимает
    # ранее подключённое (через board_style_analyze) AI-описание стиля,
    # чтобы не подмешивать чужой доски настроение в новые референсы.
    state.board_style_note = None
    state.board_style_board_id = None
    state.board_style_short_id = ""

    added = 0
    for raw_url in urls_raw:
        url = str(raw_url or "").strip()
        if not url:
            continue
        if _append_reference_url(state, url):
            added += 1
        else:
            # Потолок (8) достигнут — остальные фото доски молча не идут в
            # референс одной генерации (ожидаемо по спеке, не баг).
            break

    if update.effective_message and update.effective_user:
        library_btn = InlineKeyboardButton(
            MENU_BTN_LIBRARY,
            web_app=WebAppInfo(url=get_prompt_webapp_url(update.effective_user.id)),
        ) if PROMPT_WEBAPP_URL else InlineKeyboardButton(MENU_BTN_LIBRARY, callback_data="pl_open")
        await update.effective_message.reply_text(
            f"🖼️ Доска «{board_name}» подключена — фото из неё будут использоваться\n"
            f"как референс (загружено {added}/8).\n"
            "Теперь выбери стиль в библиотеке 👇",
            reply_markup=InlineKeyboardMarkup([[library_btn]]),
        )
    return True


def board_style_disable_kb(short_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🖼️ Отключить стиль доски", callback_data=f"bsoff_{short_id}"),
    ]])


async def apply_webapp_board_style_analyze_payload(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    """Доски — Full, AI-анализ стиля доски (docs/specs/2026-08-09_mood_boards_full.md).

    Симметрично apply_webapp_board_refs_payload (MVP), но вместо тупого
    накопления фото в state.references — vision-описание общего стиля
    ПОДБОРКИ (extract_board_style_description), которое сохраняется в
    ПЕРСИСТЕНТНОЕ поле state.board_style_note (не references/style_extract,
    те one-shot) после подтверждения юзером («✅ Всё верно» / «✏️ Поправить»,
    см. callback-ветки bsc_/bse_ в button_handler и waiting_for_board_style_correction
    в handle_text). Ошибка vision-вызова — честное сообщение, НИКАКИХ полей
    state не трогаем (ни pending, ни уже активную доску) — доска не
    остаётся «наполовину подключённой», а ранее подключённая доска не
    гаснет молча из-за неудачной попытки анализировать ДРУГУЮ доску. Успешный
    анализ, наоборот, СРАЗУ снимает ранее подключённый стиль доски (спека:
    «активация другой доски автоматически снимает предыдущий
    board_style_note» — «одна активная доска одновременно») — до подтверждения
    новый текст лежит только в pending, но старый уже не подмешивается.
    """
    board_id = str(payload.get("board_id") or "").strip()
    board_name = str(payload.get("title") or payload.get("t") or "").strip() or "Без названия"
    urls_raw = payload.get("board_refs")
    if urls_raw is None:
        urls_raw = payload.get("br")
    if not isinstance(urls_raw, list):
        urls_raw = []
    urls = [str(u).strip() for u in urls_raw if str(u or "").strip()]

    if not update.effective_message or not update.effective_user:
        return True

    if len(urls) < 2:
        await update.effective_message.reply_text(
            "В доске должно быть хотя бы 2 фото, чтобы понять её стиль — добавь ещё и попробуй снова."
        )
        return True

    description = await extract_board_style_description(urls)
    if not description:
        # Честный отказ — доска НЕ помечается стилизованной, ранее
        # подключённая (если была — другая доска) остаётся как есть.
        await update.effective_message.reply_text(
            "Не получилось разобрать стиль доски — попробуй ещё раз чуть позже."
        )
        return True

    state = get_or_init_state(context)
    short_id = _board_short_id(board_id) or _board_short_id(f"{board_name}-{int(time.time())}")
    # Успешный анализ = «активация другой доски» — снимаем ранее подключённый
    # стиль сразу (не ждём подтверждения нового), см. докстринг выше.
    state.board_style_note = None
    state.board_style_board_id = None
    state.board_style_short_id = ""
    state.board_style_pending_note = description
    state.board_style_pending_board_id = board_id
    state.board_style_pending_title = board_name
    state.board_style_pending_short_id = short_id
    state.waiting_for_board_style_correction = False

    await update.effective_message.reply_text(
        f"🖼️ Доска «{board_name}» — вот что подметил ИИ:\n\n"
        f"«{description}»\n\n"
        "Это описание будет подмешиваться в промт КАЖДОЙ генерации, пока доска активна.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Всё верно", callback_data=f"bsc_{short_id}"),
            InlineKeyboardButton("✏️ Поправить", callback_data=f"bse_{short_id}"),
        ]]),
    )
    return True


def _video_quality_label_from_mode(mode: str) -> str:
    """Обратная операция к резолву качества в _apply_webapp_generation_video
    (quality:"fast" -> mode="480p", если модель его поддерживает, иначе
    "pro" -> 720p) — нужна для префилла «✏️ Изменить», чтобы конструктор
    открылся с уже выбранным тумблером, а не всегда с дефолтным Pro."""
    return "fast" if mode == "480p" else "pro"


def build_generation_prefill(product: str, state: "UserState") -> dict:
    """Хаб генерации в вебаппе — Full, раздел 6 спеки
    (docs/specs/2026-08-13_webapp_generation_hub_navigation_full.md):
    «✏️ Изменить» с сохранением черновика. Сериализует текущий UserState в
    ТУ ЖЕ форму полей, что вебапп сам присылает в start_generation/sg —
    симметрично, чтобы конструктор мог просто заполнить свои инпуты этими
    значениями, без отдельного формата "только для чтения"."""
    if product == "video":
        model = get_video_model(state)
        return {
            "product": "video",
            "video_model": model,
            "aspect": getattr(state, "video_aspect_ratio", "16:9"),
            "quality": _video_quality_label_from_mode(get_selected_seedance_mode(state)),
            "duration": get_selected_seedance_duration(state),
            "face_grid": get_face_grid(state) if video_model_uses_face_grid(model) else False,
            "description": (state.video_prompt or "").strip(),
            "refs": get_video_image_urls(state),
        }
    if product == "midjourney":
        return {
            "product": "midjourney",
            "description": (state.mj_prompt or "").strip(),
            "refs": [state.mj_reference] if state.mj_reference else [],
        }
    if product == "avatar":
        return {
            "product": "avatar",
            "avatar_type": state.pending_avatar_kind or "female",
            "refs": list(state.avatar_photos),
        }
    if product == "photo":
        return {
            "product": "photo",
            "description": (state.prompt or "").strip(),
            "refs": list(state.references),
            "image_model": state.image_model,
        }
    return {}


def constructor_prefill_url(user_id: int, tab: str, product: str, state: "UserState") -> str:
    base = get_prompt_webapp_url(user_id)
    if not base:
        return ""
    try:
        prefill_raw = json.dumps(build_generation_prefill(product, state), ensure_ascii=False, separators=(",", ":"))
        return base + f"&tab={tab}&prefill=" + base64.urlsafe_b64encode(prefill_raw.encode()).decode()
    except Exception as e:
        logger.warning("Failed to encode generation prefill for webapp URL: %s", e)
        return base + f"&tab={tab}"


def video_constructor_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🎬 Открыть конструктор",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id) + "&tab=video_constructor"),
        ),
    ]])


def midjourney_constructor_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🎨 Открыть конструктор",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id) + "&tab=midjourney_constructor"),
        ),
    ]])


def avatar_constructor_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🪄 Открыть конструктор",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id) + "&tab=avatar_constructor"),
        ),
    ]])


def photo_constructor_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✨ Открыть конструктор",
            web_app=WebAppInfo(url=get_prompt_webapp_url(user_id) + "&tab=photo_constructor"),
        ),
    ]])


# ----------------------------------------------------------------------------
# Живой прогресс генерации в вебаппе (docs/specs/2026-08-13_webapp_generation_hub_full.md)
# НЕ очередь (в отличие от studio_worker.py) — тонкое write-only зеркало:
# бот сам инициирует и выполняет генерацию как сегодня, ДОПОЛНИТЕЛЬНО пишет
# статус в Cloudflare D1 (таблица generation_progress, отдельная от studio_*),
# пока юзер может смотреть его в вебаппе. Fire-and-forget по тому же паттерну,
# что _studio_api/_studio_complete в studio_worker.py — недоставленная запись
# НЕ блокирует и НЕ проваливает саму генерацию.
# ----------------------------------------------------------------------------

async def _gen_progress_api(path: str, payload: dict, timeout: int = 15) -> Optional[dict]:
    if not GEN_PROGRESS_ENABLED:
        return None
    url = f"{GEN_PROGRESS_API_BASE}/{path.lstrip('/')}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={"X-Gen-Progress-Secret": GEN_PROGRESS_SECRET, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if not (200 <= resp.status < 300):
                    body = await resp.text()
                    logger.warning("gen_progress api %s: status=%s body=%s", path, resp.status, body[:200])
                    return None
                return await resp.json()
    except Exception as e:
        logger.warning("gen_progress api %s exception: %s", path, e)
        return None


async def gen_progress_create(progress_id: str, user_id: int, product: str, meta: dict) -> bool:
    """True — Cloudflare подтвердил создание строки, можно безопасно
    показать юзеру кнопку «Смотреть прогресс» (спека, «Явный fallback:
    провал записи в D1» — не показываем нерабочую кнопку)."""
    return await _gen_progress_api("progress.create", {
        "id": progress_id, "user_id": user_id, "product": product, "meta": meta,
    }) is not None


async def gen_progress_update(progress_id: str, status: str, stage: str) -> None:
    # progress_pct сознательно не считаем — ни EvoLink, ни Zveno не отдают
    # реальный процент готовности, а выдуманное число врёт юзеру о точности,
    # которой нет (спека, риск №2 — "не делать красивый липовый %").
    await _gen_progress_api("progress.update", {"id": progress_id, "status": status, "stage": stage, "progress_pct": 0})


async def gen_progress_complete(progress_id: str, status: str, stage: str) -> None:
    await _gen_progress_api("progress.complete", {"id": progress_id, "status": status, "stage": stage})


def gen_progress_kb(user_id: int, progress_id: str, product: str) -> InlineKeyboardMarkup:
    """Обязательно инлайн (не reply) — initData нужен progress.get для
    проверки, что юзер смотрит свой, а не чужой прогресс (спека,
    «Архитектурное решение №2», по образцу фикса находки №1 прод-аудита
    Студии)."""
    url = get_prompt_webapp_url(user_id) + f"&tab=progress&job_id={progress_id}&product={product}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👀 Смотреть прогресс", web_app=WebAppInfo(url=url)),
    ]])


async def apply_webapp_generation_payload(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    """Хаб генерации в вебаппе (docs/specs/2026-08-13_webapp_generation_hub.md).

    Вебапп собирает ВСЕ настройки одним экраном («Конструктор») и шлёт ОДИН
    payload `start_generation`/`sg` с полем `product`. Диспетчер по продукту —
    каждый со своим kill-switch'ем (можно включать по одному продукту, не
    всё сразу)."""
    if not update.effective_message or not update.effective_user:
        return True

    product = str(payload.get("product") or payload.get("pr") or "").strip().lower()
    if product == "video":
        return await _apply_webapp_generation_video(update, context, payload)
    if product == "midjourney":
        return await _apply_webapp_generation_midjourney(update, context, payload)
    if product == "avatar":
        return await _apply_webapp_generation_avatar(update, context, payload)
    if product == "photo":
        return await _apply_webapp_generation_photo(update, context, payload)
    await update.effective_message.reply_text(
        "Этот раздел конструктора пока не поддержан ботом — используй чат для этого продукта."
    )
    return True


def _resolve_webapp_video_description(payload: dict) -> str:
    """Резолвит текст видео-описания для Конструктора (`description`/`p`).
    Если пришли `cat_idx`/`item_idx` (Full: библиотечный стиль подставлен в
    Конструктор) — описание берётся ИЗ БИБЛИОТЕКИ по индексам, присланный
    текст игнорируется (тот же принцип, что apply_webapp_prompt_payload_v2:
    «резолвить по индексам, а не по присланной строке», устойчиво к
    рассинхрону версий каталога). MVP-вебапп индексы пока не шлёт вообще —
    ветка на будущее, но обязана быть по контракту (docs/BOT_CONTRACT.md)."""
    try:
        raw_cat_idx = payload.get("cat_idx") if payload.get("cat_idx") is not None else payload.get("ci")
        raw_item_idx = payload.get("item_idx") if payload.get("item_idx") is not None else payload.get("ii")
        cat_idx = int(raw_cat_idx)
        item_idx = int(raw_item_idx)
        if 0 <= cat_idx < len(PROMPT_LIBRARY):
            cat_items = PROMPT_LIBRARY[cat_idx].get("items") or []
            if 0 <= item_idx < len(cat_items):
                library_prompt = str(cat_items[item_idx].get("prompt") or "").strip()
                if library_prompt:
                    return library_prompt
    except Exception:
        pass
    return str(payload.get("description") or payload.get("p") or "").strip()


def _webapp_bool(value, default: bool) -> bool:
    """Толерантный парсинг булева поля из webapp-payload — JSON.stringify шлёт
    настоящий boolean, но loose-парсер/ручной curl-тест может прислать строку."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


async def _apply_webapp_generation_video(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    """product=video — см. докстринг apply_webapp_generation_payload. Резолвим
    payload в UserState теми же полями, что заполняет сегодняшняя чат-панель
    (video_kb/video_status_text), и показываем карточку подтверждения с
    кнопкой `video_start`. Сам запуск/списание/очередь/доставка результата
    НЕ меняются — это тот же `_cb_video_start`/`run_seedance`, что и всегда
    (принцип спеки: «подбор — в вебаппе, факт траты денег и результат — в
    чате»).

    Серверная валидация фичефлагов модели — ОБЯЗАТЕЛЬНА (не только скрытие
    опций в вебаппе): устаревший кэш вебаппа у юзера может прислать модель,
    которую владелец уже выключила — тут молча не игнорируем и не падаем, а
    откатываем на дефолт и предупреждаем."""
    if not update.effective_message or not update.effective_user:
        return True
    if not VIDEO_CONSTRUCTOR_ENABLED:
        # Устаревший кэш вебаппа у юзера прислал payload уже выключенной
        # фичи (спека, «Что нужно от бэкенда» п.2) — честный отказ, а не
        # тихое игнорирование или падение на резолве несуществующих полей.
        await update.effective_message.reply_text(
            "Эта функция сейчас недоступна. Попробуй через обычное меню «🎬 Видео для Reels»."
        )
        return True
    if not SEEDANCE_ENABLED:
        await update.effective_message.reply_text(video_unavailable_text(), reply_markup=main_menu_kb())
        return True

    user_id = update.effective_user.id
    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.generating_avatar = False
    state.mj_active = False
    state.waiting_for_mj_prompt = False
    state.waiting_for_mj_image = False
    state.style_extract = False

    model_flags = {
        "seedance2": True,
        "seedance2_fast": SEEDANCE_FAST_ENABLED,
        "kling3": KLING3_ENABLED,
        "veo31": VEO31_ENABLED,
        "wan27": WAN27_ENABLED,
        "gemini_omni": GEMINI_OMNI_ENABLED,
        "seedance25": SEEDANCE25_ENABLED,
    }
    requested_model_raw = str(payload.get("video_model") or payload.get("vm") or "").strip().lower()
    requested_model = requested_model_raw or "seedance2"
    model_downgraded = requested_model not in model_flags or not model_flags.get(requested_model)
    resolved_model = "seedance2" if model_downgraded else requested_model
    state.video_model = resolved_model
    state.video_model_picked = True

    # ── Формат ──
    aspect_options = get_video_aspect_options(resolved_model)
    requested_aspect = str(payload.get("aspect") or payload.get("ar") or "").strip()
    if requested_aspect in aspect_options:
        resolved_aspect = requested_aspect
    elif "9:16" in aspect_options:
        resolved_aspect = "9:16"
    else:
        resolved_aspect = aspect_options[0] if aspect_options else "16:9"
    state.video_aspect_ratio = resolved_aspect

    # ── Длительность (normalize_seedance_duration клампит в границы модели,
    # включая свободный диапазон Wan 2.7 — тот же хелпер, что и video_kb). ──
    duration_options = get_seedance_duration_options(resolved_model)
    default_duration = duration_options[0] if duration_options else int(SEEDANCE_DURATION)
    raw_duration = payload.get("duration") if payload.get("duration") is not None else payload.get("d")
    try:
        requested_duration = int(raw_duration) if raw_duration is not None else default_duration
    except (TypeError, ValueError):
        requested_duration = default_duration
    state.video_duration = normalize_seedance_duration(requested_duration, resolved_model)

    # ── Качество — только для моделей с бинарным Pro/Fast (VIDEO_QUALITY_TOGGLE_MODELS). ──
    if resolved_model in VIDEO_QUALITY_TOGGLE_MODELS:
        requested_quality = str(payload.get("quality") or payload.get("q") or "").strip().lower()
        state.video_mode = resolve_webapp_video_quality(resolved_model, requested_quality)
    else:
        state.video_mode = None

    # ── Детектор лиц — только Seedance 2 / 2 Fast. ──
    if video_model_uses_face_grid(resolved_model):
        raw_face_grid = payload.get("face_grid") if payload.get("face_grid") is not None else payload.get("fg")
        state.video_face_grid = _webapp_bool(raw_face_grid, SEEDANCE_FACE_GRID)

    # ── Описание — резолв по индексам библиотеки, не доверяем присланному тексту. ──
    state.video_prompt = _resolve_webapp_video_description(payload)

    # ── Фото — те же потолки, что у ручной загрузки (MAX_SEEDANCE_IMAGE_REFERENCES). ──
    refs_raw = payload.get("refs")
    if refs_raw is None:
        refs_raw = payload.get("r")
    if not isinstance(refs_raw, list):
        refs_raw = []
    clean_refs = [str(u).strip() for u in refs_raw if str(u or "").strip()]
    set_video_image_urls(state, clean_refs)

    if not state.video_prompt.strip() and not get_video_image_urls(state):
        await update.effective_message.reply_text(
            "Нужно описание или хотя бы одно фото — вернись в конструктор и добавь что-нибудь одно.",
            reply_markup=video_constructor_kb(user_id),
        )
        return True

    state.video_session_active = True
    state.waiting_for_video_image = False
    state.waiting_for_video_prompt = False

    model_fallback_note = ""
    if model_downgraded and requested_model_raw:
        downgraded_label = (
            get_video_model_label(requested_model) if requested_model in model_flags else requested_model_raw
        )
        model_fallback_note = (
            f"⚠️ Модель «{downgraded_label}» сейчас недоступна — показываю с моделью по умолчанию.\n\n"
        )

    # build_video_generation_confirm_text — та же карточка «Экран V2», что
    # уже используют reply-кнопки/callback-путь конструктора (общий текст
    # с webapp_video_quality_label вместо самодельного числового режима).
    confirmation_text = model_fallback_note + build_video_generation_confirm_text(state)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Запустить видео", callback_data="video_start")],
        [InlineKeyboardButton(
            "✏️ Изменить",
            web_app=WebAppInfo(url=constructor_prefill_url(user_id, "video_constructor", "video", state)),
        )],
    ])
    await update.effective_message.reply_text(confirmation_text, reply_markup=kb)
    return True


async def _apply_webapp_generation_midjourney(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    """product=midjourney — тот же принцип, что и video: вебапп собирает
    текст + опциональный референс, бот резолвит в те же поля, что заполняет
    сегодняшний текстовый мини-флоу (_cb_menu_midjourney/_cb_mj_generate:
    state.mj_prompt/state.mj_reference), и показывает карточку подтверждения
    с кнопкой `mj_generate` — сам запуск/списание/сетка/апскейл НЕ меняются."""
    if not update.effective_message or not update.effective_user:
        return True
    if not MIDJOURNEY_CONSTRUCTOR_ENABLED:
        await update.effective_message.reply_text(
            "Эта функция сейчас недоступна. Попробуй через обычное меню «🎨 Midjourney»."
        )
        return True
    if not MIDJOURNEY_ENABLED:
        await update.effective_message.reply_text("Midjourney пока недоступен.", reply_markup=main_menu_kb())
        return True

    user_id = update.effective_user.id
    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.generating_avatar = False
    state.mj_active = True
    state.waiting_for_mj_prompt = False
    state.waiting_for_mj_image = False

    description = str(payload.get("description") or payload.get("p") or "").strip()
    state.mj_prompt = description

    refs_raw = payload.get("refs")
    if refs_raw is None:
        refs_raw = payload.get("r")
    refs = [str(u).strip() for u in refs_raw if str(u or "").strip()] if isinstance(refs_raw, list) else []
    # Midjourney (EvoLink) принимает ровно один референс — URL подставляется
    # в НАЧАЛО строки prompt (start_midjourney_task_evolink), не отдельное
    # поле. Если юзер добавил несколько фото в конструкторе — берём первое.
    state.mj_reference = refs[0] if refs else None

    if not description:
        await update.effective_message.reply_text(
            "Нужно описание — вернись в конструктор и напиши, что сгенерировать.",
        )
        return True

    ref_line = "Фото-референс: приложен ✅\n" if state.mj_reference else ""
    confirmation_text = (
        "🎨 Готово к запуску\n\n"
        f"Описание: {description}\n"
        f"{ref_line}"
        f"Стоимость: {MIDJOURNEY_GRID_COST} изюминок за сетку из 4 вариантов\n"
        f"(увеличение понравившегося — отдельно, {MIDJOURNEY_UPSCALE_COST} изюминок)"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Сгенерировать", callback_data="mj_generate")],
        [InlineKeyboardButton(
            "✏️ Изменить",
            web_app=WebAppInfo(url=constructor_prefill_url(user_id, "midjourney_constructor", "midjourney", state)),
        )],
    ])
    await update.effective_message.reply_text(confirmation_text, reply_markup=kb)
    return True


async def _apply_webapp_generation_avatar(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    """product=avatar — вебапп собирает тип аватара + фото одним экраном,
    бот резолвит в те же поля, что заполняет сегодняшний мини-флоу
    (_cb_avatar_gen_kind/фото-приём: state.pending_avatar_kind/avatar_photos),
    и показывает карточку подтверждения с кнопкой `avatar_gen_start` — сам
    запуск/списание/генерация НЕ меняются."""
    if not update.effective_message or not update.effective_user:
        return True
    if not AVATAR_CONSTRUCTOR_ENABLED:
        await update.effective_message.reply_text(
            "Эта функция сейчас недоступна. Попробуй через обычное меню «🪄 Аватар»."
        )
        return True

    user_id = update.effective_user.id
    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.prompt = AVATAR_REFSHEET_PROMPT
    state.style_extract = False
    state.references = []
    state.avatar_status_msg_id = None
    state.generating_avatar = True

    avatar_kind = str(payload.get("avatar_type") or payload.get("at") or "").strip().lower()
    if avatar_kind not in ("female", "male", "child"):
        avatar_kind = "female"
    state.pending_avatar_kind = avatar_kind

    refs_raw = payload.get("refs")
    if refs_raw is None:
        refs_raw = payload.get("r")
    refs = [str(u).strip() for u in refs_raw if str(u or "").strip()] if isinstance(refs_raw, list) else []
    state.avatar_photos = refs[:MAX_AVATAR_PHOTOS]

    if not state.avatar_photos:
        await update.effective_message.reply_text(
            "Нужно хотя бы одно фото — вернись в конструктор и добавь фото для аватара.",
        )
        return True

    confirmation_text = (
        "🪄 Готово к запуску\n\n"
        f"Тип: {avatar_kind_label(avatar_kind)}\n"
        f"Фото: {len(state.avatar_photos)} шт."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🚀 Сгенерировать аватар ({len(state.avatar_photos)} фото)",
            callback_data="avatar_gen_start",
        )],
        [InlineKeyboardButton(
            "✏️ Изменить",
            web_app=WebAppInfo(url=constructor_prefill_url(user_id, "avatar_constructor", "avatar", state)),
        )],
    ])
    await update.effective_message.reply_text(confirmation_text, reply_markup=kb)
    return True


async def _apply_webapp_generation_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    """product=photo — обычная фото-генерация (не Midjourney, не аватар,
    не библиотечный стиль). Вебапп собирает описание + референсы + модель
    (Gemini/GPT-5) одним экраном, бот резолвит в те же поля, что заполняет
    сегодняшний текстовый флоу (MENU_BTN_PHOTO/photo_draft_kb: state.prompt/
    state.references/state.image_model), и показывает карточку
    подтверждения с кнопкой `generate` (существующий коллбэк
    `_cb_generate`/`run_generation`) — сам запуск/списание/доставка
    результата НЕ меняются."""
    if not update.effective_message or not update.effective_user:
        return True
    if not PHOTO_CONSTRUCTOR_ENABLED:
        await update.effective_message.reply_text(
            "Эта функция сейчас недоступна. Попробуй через обычное меню «✨ Сгенерировать фото»."
        )
        return True

    user_id = update.effective_user.id
    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.generating_avatar = False
    state.style_extract = False

    description = str(payload.get("description") or payload.get("p") or "").strip()
    state.prompt = description
    state.image_prompt = ""

    image_model = str(payload.get("image_model") or payload.get("im") or "").strip().lower()
    if image_model == "gpt5" and GPT5_IMAGE_ENABLED:
        state.image_model = "gpt5"
    else:
        state.image_model = "gemini"

    refs_raw = payload.get("refs")
    if refs_raw is None:
        refs_raw = payload.get("r")
    refs = [str(u).strip() for u in refs_raw if str(u or "").strip()] if isinstance(refs_raw, list) else []
    state.references = refs[:8]
    state.references_updated_at = time.time() if state.references else 0.0

    if not description:
        await update.effective_message.reply_text(
            "Нужно описание — вернись в конструктор и напиши, что сгенерировать.",
            reply_markup=photo_constructor_kb(user_id),
        )
        return True

    photo_line = f"Фото: {len(state.references)} шт." if state.references else "Фото: своё не добавлено (возьму аватар, если есть)"
    model_line = f"Модель: {get_image_model_label(state.image_model)}\n" if GPT5_IMAGE_ENABLED else ""
    confirmation_text = (
        "✨ Готово к запуску\n\n"
        f"Описание: {description}\n"
        f"{model_line}"
        f"{photo_line}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Запустить генерацию", callback_data="generate")],
        [InlineKeyboardButton(
            "✏️ Изменить",
            web_app=WebAppInfo(url=constructor_prefill_url(user_id, "photo_constructor", "photo", state)),
        )],
    ])
    await update.effective_message.reply_text(confirmation_text, reply_markup=kb)
    return True


async def apply_webapp_prompt_payload_v2(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    action = str(payload.get("action") or payload.get("a") or "").strip().lower()
    if action in {"apply_prompt", "use_prompt", "set_template", "apply_template"}:
        action = "set_prompt"
    if action in {"apply_video_prompt", "use_video_prompt", "set_video_template", "apply_video_template"}:
        action = "set_video_prompt"
    if action in {"board_refs", "connect_board", "br"}:
        return await apply_webapp_board_refs_payload(update, context, payload)
    if action in {"board_style_analyze", "bsa"}:
        return await apply_webapp_board_style_analyze_payload(update, context, payload)
    if action in {"start_generation", "sg"}:
        return await apply_webapp_generation_payload(update, context, payload)
    if action == "topup":
        if update.effective_message:
            user_id_for_kb = update.effective_user.id if update.effective_user else None
            await update.effective_message.reply_text(
                "Открываю меню пополнения 💰",
                reply_markup=persistent_menu_kb(user_id_for_kb),
            )
            await buy(update, context)
        return True
    if action and action not in {"set_prompt", "set_video_prompt", "set_prompt_ref", "set_video_prompt_ref"}:
        return False

    raw_title = str(payload.get("title") or payload.get("t") or "").strip()
    title = raw_title or "шаблон"
    prompt = str(payload.get("prompt") or payload.get("p") or "").strip()

    image_prompt = str(payload.get("image_prompt") or "").strip()

    # (category,item) indices let us resolve title/upload_hint from PROMPT_LIBRARY
    # even when WebApp already sent the prompt inline — не только при переполнении
    # payload. Многие фото-стили не имеют "title" (только description), так что без
    # этого резолва title/upload_hint остаются пустыми в обычном (не fallback) пути.
    resolved_cat_idx = None
    resolved_item_idx = None
    item = None
    try:
        cat_idx = int(payload.get("cat_idx") if payload.get("cat_idx") is not None else payload.get("ci"))
        item_idx = int(payload.get("item_idx") if payload.get("item_idx") is not None else payload.get("ii"))
        if 0 <= cat_idx < len(PROMPT_LIBRARY):
            cat_items = PROMPT_LIBRARY[cat_idx].get("items") or []
            if 0 <= item_idx < len(cat_items):
                item = cat_items[item_idx]
                resolved_cat_idx = cat_idx
                resolved_item_idx = item_idx
    except Exception:
        item = None

    # Индексам можно верить только если они указывают на тот же стиль, что и
    # присланный prompt. Вебапп при активном поиске/фильтре может прислать
    # индексы относительно отфильтрованного списка — тогда item по этим индексам
    # это ДРУГОЙ стиль, и его title/upload_hint вводят в заблуждение (живой аудит
    # 2026-07-07: выбран «Полароид: детское фото», а бот ответил «Портреты» с
    # подсказкой «фото партнёра»).
    if item is not None and prompt:
        item_prompt = str(item.get("prompt") or "").strip()
        # Сравниваем по префиксу, а не целиком: WebApp может прислать промт
        # ОБРЕЗАННЫМ из-за лимита размера payload (см. parse_webapp_payload_loose
        # чуть ниже) — тогда усечённый текст не совпадёт с полным побайтово,
        # хотя это тот же самый стиль. Точное сравнение тут раньше гасило
        # upload_hint именно у длинных промтов — там, где подсказка нужнее
        # всего. 80 символов достаточно, чтобы отличить реально ДРУГОЙ стиль
        # (несовпадение по индексам при активном поиске в вебаппе).
        _prefix_len = min(len(item_prompt), len(prompt), 80)
        if item_prompt and _prefix_len > 0 and item_prompt[:_prefix_len] != prompt[:_prefix_len]:
            logger.warning(
                "webapp payload index mismatch: prompt differs from PROMPT_LIBRARY[%s][%s] — ignoring indices",
                payload.get("cat_idx", payload.get("ci")), payload.get("item_idx", payload.get("ii")),
            )
            item = None
            resolved_cat_idx = None
            resolved_item_idx = None

    # Индексы не подошли (например, «Новинки» шлёт позицию в отфильтрованном
    # списке, а не в реальной категории — живой аудит 2026-07-31), но сам
    # prompt у нас есть — ищем стиль по содержимому промта по всей библиотеке.
    # В отличие от резолва по индексам это НЕ угадывание: совпадение самого
    # промта — надёжное доказательство, что это тот самый стиль, а не чужой.
    # Раньше в этом случае title откатывался к литералу «шаблон» (находка
    # «Шаблон «шаблон»» из аудитов 07-02/07-07/07-31).
    if item is None and prompt:
        # Два прохода: сначала сравнение по ВСЕЙ доступной длине промта
        # (обрезанный payload — всё равно точный префикс полного промта),
        # и только если не нашли — старый 80-символьный кэп как страховка
        # от артефактов loose-парсера. Причина: в реальном prompt_library.json
        # есть пары стилей с одинаковыми первыми 80 символами, но разным
        # upload_hint — кэп в 80 отдавал юзеру подсказку и статистику ЧУЖОГО
        # (соседнего) стиля (баг-ресерч 2026-08-02).
        def _scan_library_by_prompt(prefix_cap):
            for cat_i, category in enumerate(PROMPT_LIBRARY):
                for item_i, cand in enumerate(category.get("items") or []):
                    cand_prompt = str(cand.get("prompt") or "").strip()
                    if not cand_prompt:
                        continue
                    _plen = min(len(cand_prompt), len(prompt))
                    if prefix_cap:
                        _plen = min(_plen, prefix_cap)
                    if _plen > 0 and cand_prompt[:_plen] == prompt[:_plen]:
                        return cand, cat_i, item_i
            return None, None, None

        item, resolved_cat_idx, resolved_item_idx = _scan_library_by_prompt(None)
        if item is None:
            item, resolved_cat_idx, resolved_item_idx = _scan_library_by_prompt(80)

    if item is not None:
        resolved_title = str(item.get("title") or "").strip()
        # Лейбл для аналитики и для сообщения пользователю: у фото-стилей часто
        # нет "title" (только description) — берём тот же fallback, что и в UI
        # (_showcase_item_label), иначе выходит «Шаблон «шаблон»».
        if not raw_title:
            fallback_label = resolved_title or _showcase_item_label(item)
            if fallback_label:
                raw_title = fallback_label
                title = fallback_label
        if not prompt:
            resolved_prompt = str(item.get("prompt") or "").strip()
            prompt = resolved_prompt or resolved_title
            if not image_prompt:
                image_prompt = str(item.get("image_prompt") or "").strip()

    if not prompt:
        # Ни индексы, ни полный скан библиотеки по содержимому не дали
        # реального промта — раньше здесь был молчаливый откат на литерал
        # title (по умолчанию "шаблон"), и он уходил В САМУ ГЕНЕРАЦИЮ как
        # промт, а не только как текст в чате (живой прод 2026-08-02:
        # video_prompt='шаблон' — юзер тратил изюминки на генерацию по
        # бессмысленному промту). Честный отказ вместо мусорной генерации.
        logger.warning(
            "apply_webapp_prompt_payload_v2: пустой prompt после всех резолвов (action=%s, cat_idx/item_idx=%s/%s)",
            action, payload.get("cat_idx", payload.get("ci")), payload.get("item_idx", payload.get("ii")),
        )
        if update.effective_message and update.effective_user:
            if PROMPT_WEBAPP_URL:
                retry_btn = InlineKeyboardButton(
                    "📚 Библиотека стилей",
                    web_app=WebAppInfo(url=get_prompt_webapp_url(update.effective_user.id)),
                )
            else:
                retry_btn = InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open")
            await update.effective_message.reply_text(
                "Не удалось применить именно эту карточку (возможно, устарела).\n"
                "Открой библиотеку и выбери стиль из категории заново:",
                reply_markup=InlineKeyboardMarkup([[retry_btn]]),
            )
        return True

    # Свободный текст пользователя («свои пожелания к причёске/макияжу») —
    # вебапп присылает его отдельным полем note/n для шаблонов с input_hint,
    # чтобы не переписывать сам prompt на клиенте. Пусто — шаблон уходит как есть.
    user_note = str(payload.get("note") or payload.get("n") or "").strip()

    state = get_or_init_state(context)
    # Доски — Full, AI-анализ стиля (docs/specs/2026-08-09_mood_boards_full.md):
    # если активна доска с подключённым описанием стиля — накладываем его
    # ПЕРЕД промтом стиля, каждую генерацию (не one-shot), а «свои пожелания»
    # юзера всё равно побеждают/дополняют — apply_user_note_override ниже.
    if state.board_style_note:
        prompt = apply_board_style_note(prompt, state.board_style_note)
    if user_note:
        prompt = apply_user_note_override(prompt, user_note)

    item_kind = "video" if action in {"set_video_prompt", "set_video_prompt_ref"} else "image"
    if raw_title and update.effective_user:
        _log_template_usage_safe(update.effective_user.id, raw_title, item_kind, cat_idx=resolved_cat_idx, item_idx=resolved_item_idx)

    state.image_prompt = image_prompt
    if action in {"set_video_prompt", "set_video_prompt_ref"}:
        state.video_prompt = prompt
        state.video_session_active = True
        state.waiting_for_video_image = True
    else:
        deactivate_video_session(state)
        state.prompt = prompt
        _set_style_extract(state, bool(item.get("style_extract")) if item is not None else False)

    if update.effective_message:
        if action in {"set_video_prompt", "set_video_prompt_ref"}:
            user_id_for_kb = update.effective_user.id if update.effective_user else None
            # Хаб генерации, раздел 4.1 (docs/specs/2026-08-13_webapp_generation_hub_navigation_full.md):
            # «Использовать» на видео-стиле открывает Конструктор с уже
            # подставленным описанием, а не сегодняшнюю чат-панель — GPT
            # Image-стилизация (image_prompt) не переносим в эту версию
            # Конструктора (там нет полей для неё), поэтому в этом одном
            # случае оставляем старый чат-путь без изменений.
            if VIDEO_CONSTRUCTOR_ENABLED and PROMPT_WEBAPP_URL and not image_prompt and user_id_for_kb is not None:
                await update.effective_message.reply_text(
                    style_applied_message(title, item, "video", user_note=user_note) + "\n"
                    "Донастрой в конструкторе и запускай видео.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                        "🎬 Открыть конструктор",
                        web_app=WebAppInfo(url=constructor_prefill_url(user_id_for_kb, "video_constructor", "video", state)),
                    )]]),
                )
                return True
            hint = "Теперь отправь фото и запускай видео."
            if image_prompt:
                hint = (
                    "Теперь отправь фото и запускай видео.\n"
                    "💡 Бот сначала стилизует фото через GPT Image, затем сгенерит видео."
                )
            await update.effective_message.reply_text(
                style_applied_message(title, item, "video", user_note=user_note) + "\n" + hint,
                reply_markup=persistent_menu_kb(user_id_for_kb),
            )
            await update.effective_message.reply_text(
                "Параметры видео:",
                reply_markup=video_kb(state),
            )
        else:
            user_id_for_kb = update.effective_user.id if update.effective_user else None
            await update.effective_message.reply_text(
                style_applied_message(title, item, "image", user_note=user_note),
                reply_markup=persistent_menu_kb(user_id_for_kb),
            )
            await update.effective_message.reply_text(
                photo_draft_text(state, user_id_for_kb),
                reply_markup=photo_draft_kb(state, user_id_for_kb),
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
    # cat_idx/item_idx — короткие числовые поля, обычно идут ДО длинного prompt
    # в JSON и потому выживают при обрезке payload по лимиту размера. Без них
    # upload_hint/title-фолбэк резолвиться не могут вообще (см. apply_webapp_
    # prompt_payload_v2) — раньше loose-парсер их просто не искал.
    cat_idx_match = re.search(r'"(?:cat_idx|ci)"\s*:\s*(\d+)', text, flags=re.IGNORECASE)
    item_idx_match = re.search(r'"(?:item_idx|ii)"\s*:\s*(\d+)', text, flags=re.IGNORECASE)

    action = action_match.group(1).strip().lower() if action_match else "set_prompt"
    # НЕ подставлять литерал «шаблон»: truthy-заглушка блокирует фолбэк-резолв
    # честного лейбла через _showcase_item_label (гейт `if not raw_title:` в
    # apply_webapp_prompt_payload_v2) — та же регрессия «Стиль „шаблон"» из
    # аудитов 07-02/07-07/07-31, но через код-путь обрезанных payload.
    title = title_match.group(1) if title_match else ""
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
        "title": title,
        "prompt": prompt_raw.strip(),
    }
    if cat_idx_match:
        payload["cat_idx"] = int(cat_idx_match.group(1))
    if item_idx_match:
        payload["item_idx"] = int(item_idx_match.group(1))
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


async def extract_style_description_from_reference(image_url: str) -> Optional[str]:
    """Text-only vision описание причёски/макияжа со второго фото.

    Используется для стилей с флагом `style_extract` (сейчас — «Образ с
    референса», 💄 Бьюти): раньше оба фото уходили в image-модель одним
    запросом, и она периодически путала, чьё лицо использовать (~50/50,
    см. docs/briefs/backend.md). Текстовое описание вместо второго фото
    убирает лицо со второго фото из запроса физически — им неоткуда взяться
    в результате. Возвращает None при любой ошибке (вызывающий код должен
    штатно откатиться на старое поведение с двумя фото).
    """
    if not ZVENO_API_KEY:
        return None
    resolved = _ref_to_data_url(image_url) if _is_img_ref(image_url) else image_url
    if not resolved or not (resolved.startswith("http") or resolved.startswith("data:")):
        return None

    prompt = (
        "Describe ONLY the hairstyle and makeup visible in this photo, as a short "
        "style reference for recreating the SAME look on a DIFFERENT person. "
        "Hairstyle: shape, length, color, texture. Makeup: eye look, lips, tone/finish. "
        "Do NOT describe the face shape, identity, age, ethnicity, skin tone or any "
        "other facial/appearance feature of the person in the photo — only the "
        "hairstyle and makeup style itself. 2-4 sentences, plain text, no preamble."
    )
    payload = {
        "model": ZVENO_CHAT_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": resolved}},
            ],
        }],
        "temperature": 0.2,
        "max_completion_tokens": 300,
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
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if not (200 <= resp.status < 300):
                    body = await resp.text()
                    logger.warning("style_extract vision call failed: status=%s body=%s", resp.status, body[:300])
                    return None
                rd = await resp.json()
    except Exception as e:
        logger.warning("style_extract vision call exception: %s", e)
        return None

    choices = rd.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    text = str(content or "").strip()
    return text or None


async def extract_board_style_description(image_urls: List[str]) -> Optional[str]:
    """Text-only vision-описание общего визуального стиля ПОДБОРКИ фото —
    доска (mood-борд) в Full-режиме (docs/specs/2026-08-09_mood_boards_full.md).

    По образцу extract_style_description_from_reference (тот же Zveno
    text-only vision-вызов, тот же endpoint), но:
    - принимает СПИСОК URL (до 6 — латентность/стоимость vision-вызова
      растут с числом картинок, 6 достаточно для «палитра/настроение/
      композиция»), не один;
    - другой промт: не «причёска и макияж ОДНОГО человека», а «палитра/
      настроение/композиция ПОДБОРКИ», без упоминания лиц/личности людей на
      фото — описание уходит в промт генерации КАЖДОЙ следующей картинки,
      упоминание внешности конкретного человека там не нужно и вредно (та
      же причина, что и в оригинальной функции).
    Возвращает None при любой ошибке — вызывающий код обязан ответить юзеру
    честным текстом об ошибке и НЕ активировать доску без AI-описания
    (см. критерий приёмки в спеке).
    """
    if not ZVENO_API_KEY:
        return None

    resolved_urls: List[str] = []
    for raw_url in (image_urls or [])[:6]:
        resolved = _ref_to_data_url(raw_url) if _is_img_ref(raw_url) else raw_url
        if resolved and (resolved.startswith("http") or resolved.startswith("data:")):
            resolved_urls.append(resolved)
    if not resolved_urls:
        return None

    prompt = (
        "These photos are a MOOD BOARD/COLLECTION — describe their SHARED overall "
        "visual style: color palette, mood/atmosphere, composition and lighting "
        "style. Do NOT describe or mention any specific person's face, identity, "
        "age, ethnicity, gender or other facial/appearance feature — focus ONLY "
        "on the shared aesthetic across the photos. 2-4 sentences, plain text, "
        "no preamble."
    )
    content = [{"type": "text", "text": prompt}]
    for url in resolved_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    payload = {
        "model": ZVENO_CHAT_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "max_completion_tokens": 300,
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
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if not (200 <= resp.status < 300):
                    body = await resp.text()
                    logger.warning("board_style_analyze vision call failed: status=%s body=%s", resp.status, body[:300])
                    return None
                rd = await resp.json()
    except Exception as e:
        logger.warning("board_style_analyze vision call exception: %s", e)
        return None

    choices = rd.get("choices") or []
    if not choices:
        return None
    content_out = (choices[0].get("message") or {}).get("content")
    if isinstance(content_out, list):
        content_out = " ".join(p.get("text", "") for p in content_out if isinstance(p, dict))
    text = str(content_out or "").strip()
    return text or None


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
    rows: int = 8,
    cols: int = 8,
    line_color: tuple = (255, 255, 255),
    line_width: int = 12,
) -> bytes:
    """SOLID grid overlay — fallback when AI-portrait refify is unavailable.

    Per community testing of Seedance's face detector, the grid must be SOLID
    (100% opacity) and thick to reliably break face detection — semi-transparent
    or thin lines re-engage the detector. The 6×6 setting stopped passing, so the
    grid is denser: 8×8 white lines at 12px. The grid breaks the pixel patterns
    the detector relies on while Seedance still reads the character/pose from the
    cells between lines.
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


async def _process_single_grid_ref(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """None — сетку наложить не удалось. Оригинал наружу не отдаём: без сетки
    реальное фото почти гарантированно режется модерацией Seedance, и со
    стороны это выглядит как «у одних работает, у других нет» (реф протух
    после рестарта бота / не скачался — и в Seedance молча уходило голое фото)."""
    try:
        if _is_img_ref(url) or url.startswith("data:"):
            image_bytes = _resolve_image_bytes(url)
            if image_bytes is None:
                logger.warning("Grid overlay: image ref not found in cache: %s", url)
                return None
        else:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60), allow_redirects=True) as resp:
                if resp.status != 200:
                    logger.warning("Grid overlay: download failed status=%s url=%s", resp.status, url[:80])
                    return None
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
        logger.exception("Ref processing failed for url=%s", url[:60])
        return None


async def apply_grid_overlay_to_refs(image_urls: List[str]) -> List[Optional[str]]:
    """Поэлементно: обработанный реф или None, если сетка не наложилась."""
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
        # Пустой черновик: вместо выговора — экран фото со статусом и только
        # осмысленными кнопками (кнопки запуска тут нет — запускать нечего).
        queued_user_ids.discard(user.id)
        await reply_target.reply_text(photo_draft_text(state, user.id), reply_markup=photo_draft_kb(state, user.id))
        return

    references = list(state.references)

    if state.style_extract and len(references) != 2:
        # Жёсткий гейт (P0 2026-07-17): этому стилю нужны РОВНО 2 фото
        # (лицо + референс причёски/макияжа), аватар как автозамена сюда не
        # годится — не подставляем и не запускаем генерацию, пока их не 2.
        queued_user_ids.discard(user.id)
        if not references:
            gate_msg = (
                "Для этого стиля нужны 2 фото по порядку: сначала своё (лицо), "
                "потом фото-референс причёски/макияжа. Пришли оба и запускай снова."
            )
        elif len(references) == 1:
            gate_msg = (
                "Есть только 1 фото. Пришли ещё фото-референс причёски/макияжа "
                "(второе фото) и запускай снова."
            )
        else:
            gate_msg = (
                f"Для этого стиля нужно ровно 2 фото, а загружено {len(references)}. "
                "Выбери стиль заново из библиотеки — буфер фото очистится, и пришли "
                "только 2 нужных фото по порядку."
            )
        await reply_target.reply_text(gate_msg, reply_markup=photo_draft_kb(state, user.id))
        return

    # Берём выбранный активный аватар; если не выбран или его слот пуст —
    # откатываемся на первый доступный (female → male → child).
    _all_avatars = get_avatar_urls(user.id)
    _active_kind = get_active_avatar_kind(user.id)
    _avatar_order = ([_active_kind] if _active_kind else []) + ["female", "male", "child"]
    avatar_url = next(
        (_all_avatars.get(k) for k in _avatar_order if _all_avatars.get(k)),
        None,
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

    if state.style_extract:
        state.style_extract = False  # one-shot — не переносить на «Повторить»/следующую генерацию
        if len(references) >= 2:
            style_desc = await extract_style_description_from_reference(references[1])
            if style_desc:
                state.prompt = (
                    f"{state.prompt}\n\nStyle reference (hairstyle & makeup only — "
                    f"apply this look to the person in the first reference photo, "
                    f"do not use any facial features from this description): {style_desc}"
                )
                references = references[:1] + references[2:]
            else:
                await reply_target.reply_text(
                    "Не удалось разобрать референс стиля отдельно — сгенерирую по обоим фото как раньше."
                )

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

        # Чистим временные данные (фото-референсы и т.п.), но сохраняем
        # выбранную модель картинок и текущий промт — иначе после генерации
        # (особенно из библиотеки стилей) промт стирался, и следующее фото,
        # присланное без нового текста, оставалось без описания вообще.
        # Просьба Ани 2026-08-03: промт из библиотеки не должен сбрасываться
        # после генерации — юзер шлёт новое фото и получает тот же стиль
        # без повторного похода в библиотеку.
        new_state = UserState()
        new_state.image_model = state.image_model
        new_state.prompt = state.prompt
        # Доски — Full: подключённый стиль доски — персистентная настройка,
        # переживает генерацию (в отличие от references/style_extract),
        # иначе следующая же генерация после первой теряла бы AI-описание
        # доски вопреки требованию спеки «каждую генерацию, а не одну».
        new_state.board_style_note = state.board_style_note
        new_state.board_style_board_id = state.board_style_board_id
        new_state.board_style_short_id = state.board_style_short_id
        context.user_data["state"] = new_state

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



def _set_style_extract(state: "UserState", enabled: bool) -> None:
    """Переключает `state.style_extract` и, если включаем — чистит буфер фото.

    P0 2026-07-17 (docs/briefs/backend.md): `state.references` копится между
    генерациями (handle_photo только append'ит), поэтому без явной очистки
    `references[0]` при входе в style_extract-стиль мог оказаться старым
    фото с прошлого теста, а не тем, что юзер прислал сейчас — пайплайн
    принимал его за «лицо». Юзер обязан собрать пару фото заново под
    конкретно этот стиль (см. также run_generation — жёсткий гейт на
    len(references) == 2 и photo_draft_text — статус по слотам)."""
    state.style_extract = enabled
    if enabled:
        state.references = []
        state.references_updated_at = 0.0


def apply_user_note_override(base_prompt: str, user_note: str) -> str:
    """Дописывает свободный текст юзера («свои пожелания») к промту стиля так,
    чтобы image-модель реально его учитывала, а не игнорировала.

    Живой баг 2026-07-17 (docs/specs/2026-07-17_note_override_weak.md):
    слабая формулировка-приписка в конце промта («follow this instead of the
    generic description above: {note}») проигрывала плотному визуально
    конкретному дефолтному описанию образа впереди — модель держалась за
    «warm bronze eyeshadow... nude-pink lips» даже когда юзер явно просил
    «красная помада, стрелки». Не транспортный баг — note доезжал верно,
    просто формулировка отмены была недостаточно категоричной. Фикс — явный
    override-маркер вместо мягкой приписки (вариант 3 из ТЗ, без изменения
    структуры prompt_library.json).
    """
    if not user_note:
        return base_prompt
    return (
        f"{base_prompt}\n\n"
        f"MOST IMPORTANT OVERRIDE — ignore every makeup/hairstyle/color detail "
        f"mentioned above completely, they do not apply. Render ONLY this look "
        f"instead: {user_note}"
    )


async def _reply_after_callback(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    text: str,
    reply_markup=None,
) -> None:
    """query.message.reply_text(), но с фолбэком на send_message по chat_id.

    Кнопка на сообщении от answerWebAppQuery (инлайн-1-тап библиотеки,
    docs/specs/2026-07-15_webapp_inline_1tap.md) — это inline-сообщение
    Telegram: у такого callback'а `query.message` всегда None (только
    `inline_message_id`, Bot API гарантирует ровно одно из двух полей).
    `query.message.reply_text(...)` в этом случае падает AttributeError
    молча (state уже успевает выставиться до этой строки, а подтверждение
    юзер не видит вообще — живой баг 2026-07-17). В личном чате chat_id
    юзера всегда равен его user_id, так что send_message работает как
    полноценная замена."""
    if query.message is not None:
        await query.message.reply_text(text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)


# ══════════════════════════════════════════════════════════════
# ОБРАБОТЧИК КНОПОК: button_handler и вся логика callback
# ══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ CALLBACK-ВЕТОК (dispatch table): каждая функция —
# 1:1 копия тела бывшей if-ветки button_handler, без изменений логики
# (фаза 4 разбора монолита). Порядок функций не важен — порядок
# ВЫЗОВА сохранён в button_handler (см. ниже: точные совпадения —
# через словари QDATA_EXACT_HANDLERS/VIDEO_EXACT_HANDLERS, префиксные
# (.startswith) — оставлены inline if-цепочкой, порядок как в
# оригинале).
# ══════════════════════════════════════════════════════════════

async def _cb_pladm_open(update, context, query, user):
    await query.message.reply_text(
        "Кнопочный админ-редактор библиотеки открыт.",
        reply_markup=prompt_library_admin_kb(),
    )
    return


async def _cb_pladm_list(update, context, query, user):
    await prompt_library_list(update, context)
    return


async def _cb_pladm_export(update, context, query, user):
    await prompt_library_export(update, context)
    return


async def _cb_pladm_new(update, context, query, user):
    context.user_data["pl_admin_mode"] = "new"
    await query.message.reply_text("Отправь название новой категории одним сообщением.")
    return


async def _cb_pladm_rename(update, context, query, user):
    context.user_data["pl_admin_mode"] = "rename_old"
    await query.message.reply_text("Отправь текущее название категории.")
    return


async def _cb_pladm_delete(update, context, query, user):
    context.user_data["pl_admin_mode"] = "delete"
    await query.message.reply_text("Отправь название категории для удаления.")
    return


async def _cb_pladm_cancel(update, context, query, user):
    context.user_data.pop("pl_admin_mode", None)
    context.user_data.pop("pl_admin_rename_old", None)
    await query.message.reply_text("Админ-режим закрыт.")
    return


async def _cb_noop(update, context, query, user):
    await query.answer()
    return


async def _cb_pl_open_webapp(update, context, query, user):
    logger.info(
        "Prompt WebApp open requested: user_id=%s chat_id=%s",
        update.effective_user.id if update.effective_user else "unknown",
        update.effective_chat.id if update.effective_chat else "unknown",
    )
    if not PROMPT_WEBAPP_URL:
        await query.message.reply_text(
            "Выбери стиль из библиотеки 👇",
            reply_markup=prompt_library_menu_kb(),
        )
        return
    uid = update.effective_user.id if update.effective_user else None
    await query.message.reply_text(
        "Открывай библиотеку по кнопке ниже:",
        reply_markup=webapp_open_kb(uid),
    )
    return


async def _cb_pl_open(update, context, query, user):
    await query.message.reply_text(
        "Выбери категорию. Покажу лучшие стили с примерами 👇",
        reply_markup=prompt_library_menu_kb(),
    )
    return


async def _cb_plsave_cancel(update, context, query, user):
    context.user_data.pop("pending_pl_save", None)
    await query.message.reply_text("Сохранение в библиотеку отменено.", reply_markup=main_menu_kb())
    return


async def _cb_generate(update, context, query, user):
    state = get_or_init_state(context)
    was_in_video = state.video_session_active
    deactivate_video_session(state)
    if was_in_video and not state.prompt:
        await query.message.reply_text(
            "Режим видео закрыт. Напиши описание и нажми «✨ Сгенерировать фото»."
        )
        return
    await run_generation(update, context)
    return


async def _cb_enhance_photo(update, context, query, user):
    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.prompt = ENHANCE_PHOTO_PROMPT
    state.image_prompt = ""
    state.style_extract = False
    state.references = []  # старое фото не подмешиваем — нужно новое, для улучшения
    state.image_model = "gemini"  # nano banana, фикс по требованию функции
    await query.message.reply_text(
        "Пришли фото, которое нужно улучшить 🖼️\n"
        "Бот повысит качество и сделает его похожим на кадр от профессионального "
        "фотографа — черты лица останутся прежними.",
        reply_markup=ENHANCE_WAITING_KB,
    )
    return


async def _cb_enhance_use_pending_text(update, context, query, user):
    state = get_or_init_state(context)
    pending_text = str(context.user_data.pop("enhance_pending_text", "") or "").strip()
    if not pending_text:
        await query.answer("Текст уже неактуален, напиши заново.", show_alert=True)
        return
    deactivate_video_session(state)
    state.prompt = pending_text
    state.style_extract = False
    await query.message.reply_text(photo_draft_text(state, user.id), reply_markup=photo_draft_kb(state, user.id))
    return


async def _cb_menu_photo(update, context, query, user):
    await query.message.reply_text(
        "📸 Фото — выбери, что сделать:",
        reply_markup=photo_menu_kb(user.id),
    )
    return


async def _cb_menu_video(update, context, query, user):
    await query.message.reply_text(
        "🎬 Видео — выбери, что сделать:",
        reply_markup=video_menu_kb(user.id),
    )
    return


async def _cb_image_model_menu(update, context, query, user):
    state = get_or_init_state(context)
    await query.message.reply_text(
        image_model_menu_text(state),
        reply_markup=image_model_menu_kb(state),
    )
    return


async def _cb_image_model_set(update, context, query, user):
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


async def _cb_generate_again(update, context, query, user):
    state = get_or_init_state(context)
    deactivate_video_session(state)
    user_id = update.effective_user.id
    saved_prompt = (last_generated_prompt.get(user_id) or "").strip()
    if not saved_prompt:
        await query.message.reply_text(
            "Не нашла прошлое описание. Напиши новый текст и нажми «✨ Сгенерировать фото»."
        )
        return

    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.prompt = saved_prompt
    state.style_extract = False
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


async def _cb_animate_last(update, context, query, user):
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
        "или сразу жми «🚀 Запустить видео»."
    )
    await query.message.reply_text(
        video_status_text(state),
        reply_markup=video_kb(state),
    )
    return


async def _cb_motion_start(update, context, query, user):
    if not MOTION_CONTROL_ENABLED:
        await query.message.reply_text(video_unavailable_text(), reply_markup=main_menu_kb())
        return
    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.motion_control_active = True
    state.waiting_for_motion_video = True
    await query.message.reply_text(
        "🕺 Видео с движением\n\n"
        "1. Пришли короткое референс-видео с движением, которое нужно повторить "
        "(танец, жест, поворот и т.п.) — обычным видеофайлом.\n"
        "2. Затем пришли своё фото — перенесу движение на него."
    )
    return


async def _cb_seedance_retry(update, context, query, user):
    user_r = update.effective_user
    if user_r.id in queued_user_ids or user_r.id in processing_user_ids:
        await query.answer("Уже выполняется другая задача. Подожди.", show_alert=False)
        return
    state = get_or_init_state(context)
    # video_session_active гасит run_seedance после валидаций — см. video_start.
    processing_user_ids.add(user_r.id)
    try:
        context.application.create_task(run_seedance(update, context))
    except Exception:
        processing_user_ids.discard(user_r.id)
        logger.exception("create_task(run_seedance retry) failed for user=%s", user_r.id)
        await query.answer("Не удалось запустить генерацию. Попробуй ещё раз.", show_alert=True)
    return


async def _cb_avatar_actions(update, context, query, user):
    await query.message.reply_text(
        "🪄 AI-аватар — это ты в любом образе\n\n"
        "Пришли 3–8 своих фото, и нейросеть сгенерирует аватар и запомнит твою внешность.\n"
        "После этого в каждой генерации будешь появляться именно ты — "
        "хоть в образе киберпанк-воина, хоть на обложке журнала.\n\n"
        "Если загружено несколько аватаров (👩/👨/🧒) — кнопками ниже "
        "выбери, каким генерировать (● текущий).\n\n"
        "Это то, чего нет у большинства конкурентов 💪",
        reply_markup=avatar_actions_kb(user.id),
    )
    return


async def _cb_avatar_use(update, context, query, user):
    chosen = query.data.rsplit("_", 1)[-1]
    if not get_avatar_urls(user.id).get(chosen):
        await query.answer("Такой аватар ещё не загружен.", show_alert=True)
        return
    set_active_avatar_kind(user.id, chosen)
    await query.answer(f"Генерирую как: {avatar_kind_label(chosen)} ✅")
    try:
        await query.message.edit_reply_markup(reply_markup=avatar_actions_kb(user.id))
    except BadRequest:
        pass
    return


async def _cb_avatar_gen_refsheet(update, context, query, user):
    # Хаб генерации в вебаппе (docs/specs/2026-08-13_webapp_generation_hub.md) —
    # тот же kill-switch-паттерн, что у видео: выключен по умолчанию, ничего
    # не меняется, пока Аня не включит флаг.
    if AVATAR_CONSTRUCTOR_ENABLED and PROMPT_WEBAPP_URL:
        await query.message.reply_text(
            "Создаём аватар 🪄\n\n"
            "Выбери тип и загрузи фото в конструкторе — и возвращайся сюда за запуском.",
            reply_markup=avatar_constructor_kb(user.id),
        )
        return
    # Фото принимаются сразу, до выбора типа — порядок действий (сначала
    # фото или сначала тип) юзеру не важен, и фото больше не улетают в
    # обычный фото-черновик, если тип ещё не выбран (макет утверждён
    # Аней 2026-07-15).
    state = get_or_init_state(context)
    deactivate_video_session(state)
    state.prompt = AVATAR_REFSHEET_PROMPT
    state.style_extract = False
    state.references = []
    state.avatar_photos = []
    state.avatar_status_msg_id = None
    state.pending_avatar_kind = ""
    state.generating_avatar = True
    await query.message.reply_text(
        "Создаём аватар 🪄\n\n"
        "Пришли 3–6 фото, где хорошо видно лицо, и выбери, для кого аватар 👇\n"
        "Фото можно слать прямо сейчас — не потеряются.",
        reply_markup=avatar_gen_kind_kb(),
    )
    return


async def _cb_avatar_gen_kind(update, context, query, user):
    state = get_or_init_state(context)
    avatar_kind = query.data.rsplit("_", 1)[-1]
    # Тип можно тапнуть, даже если приём фото ещё не был включён явно
    # (например, повторный тап из старого сообщения) — не теряем то,
    # что юзер уже успел прислать.
    if not state.generating_avatar:
        deactivate_video_session(state)
        state.prompt = AVATAR_REFSHEET_PROMPT
        state.style_extract = False
        state.references = []
        state.avatar_photos = []
        state.avatar_status_msg_id = None
        state.generating_avatar = True
    state.pending_avatar_kind = avatar_kind
    await query.answer(f"Тип: {avatar_kind_label(avatar_kind)} ✅")
    return


async def _cb_avatar_gen_start(update, context, query, user):
    state = get_or_init_state(context)
    photos = list(state.avatar_photos)
    if not photos:
        await query.answer("Сначала отправь хотя бы одно фото.", show_alert=True)
        return
    if not state.pending_avatar_kind:
        await query.answer("Сначала выбери тип аватара 👆", show_alert=True)
        return

    if user.id in queued_user_ids or user.id in processing_user_ids:
        await query.answer("Сырник уже занят другой задачей. Подожди.", show_alert=True)
        return

    # Валидация ДО списания (как в run_generation, SirNike.py ~4720): __img__-рефы
    # живут в in-memory кэше и умирают при рестарте/деплое. Без этой проверки
    # protухшие рефы молча выпадали уже в generate_image_zveno — запрос уходил
    # БЕЗ фото юзера, «успех» без рефанда, и случайное лицо сохранялось активным
    # аватаром. Для аватара частичный набор фото тоже не годится (identity),
    # поэтому при любой потере просим прислать всё заново.
    stale_count = sum(
        1 for p in photos if _is_img_ref(p) and _resolve_image_bytes(p) is None
    )
    if stale_count:
        state.avatar_photos = []
        state.avatar_status_msg_id = None
        await query.answer()
        await query.message.reply_text(
            "Фото для аватара устарели — похоже, бот перезапускался и не сохранил их 😔\n"
            "Пришли фото ещё раз и жми «Сгенерировать аватар». Изюминки не списаны."
        )
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
    # Сохраняем выбранную модель картинок при сбросе временного состояния.
    new_state = UserState()
    new_state.image_model = state.image_model
    # Доски — Full: та же персистентность стиля доски, что и после обычной
    # фото-генерации выше — аватар не должен гасить подключённую доску.
    new_state.board_style_note = state.board_style_note
    new_state.board_style_board_id = state.board_style_board_id
    new_state.board_style_short_id = state.board_style_short_id
    context.user_data["state"] = new_state
    await query.message.reply_text(
        f"Запускаю генерацию аватара по {len(photos)} фото… ✨",
    )
    return


async def _cb_avatar_help(update, context, query, user):
    await query.answer()
    await query.message.reply_text(
        "🪄 AI-аватар — это твоя внешность в боте.\n\n"
        "Пришли 3–8 своих фото лица с разных ракурсов → "
        "бот сгенерирует аватар и запомнит, как ты выглядишь → "
        "дальше ты будешь появляться в любом образе на каждой картинке.\n\n"
        "Аватар необязателен — без него тоже можно генерировать."
    )
    return


async def _cb_avatar_back_menu(update, context, query, user):
    await query.message.reply_text(
        "Главное меню:",
        reply_markup=main_menu_kb(user.id),
    )
    return


async def _cb_menu_from_video(update, context, query, user):
    state = get_or_init_state(context)
    deactivate_video_session(state)
    await query.message.reply_text(
        "Главное меню:",
        reply_markup=main_menu_kb(user.id),
    )
    return


async def _cb_show_help(update, context, query, user):
    # Единый источник справки — та же, что и команда /help.
    await help_command(update, context)
    return


async def _cb_report_problem(update, context, query, user):
    # Единая реализация с командой /report — один текст и один способ отмены.
    await report_problem_command(update, context)
    return


async def _cb_bug_bounty(update, context, query, user):
    await bug_bounty_command(update, context)
    return


async def _cb_report_cancel(update, context, query, user):
    # Отмена репорта («🚨 Проблема» / «🐞 Баг-баунти») — снимает ТОЛЬКО
    # режим ожидания репорта. Раньше кнопка висела на общем "reset" и
    # передумавший жаловаться юзер молча терял черновик фото/стиля.
    state = get_or_init_state(context)
    state.waiting_for_problem_report = False
    state.waiting_for_bug_report = False
    state.pending_report_kind = ""
    await query.message.reply_text(
        "Ок, отменила. Твой черновик не тронут 👌",
        reply_markup=main_menu_kb(user.id),
    )
    return


async def _cb_reset(update, context, query, user):
    # Сбрасываем только временные данные (описание/фото/видео-сессию).
    # Липкие настройки-предпочтения переносим в новое состояние, иначе
    # выбор модели картинок терялся при возврате в меню кнопкой «◀️ В меню».
    prev_state = context.user_data.get("state")
    new_state = UserState()
    if isinstance(prev_state, UserState):
        new_state.image_model = prev_state.image_model
        # Выбор видео-модели — тоже липкая настройка: иначе каждый
        # «◀️ В меню» снова гонит юзера через пикер моделей.
        new_state.video_model = prev_state.video_model
        new_state.video_model_picked = prev_state.video_model_picked
        # Доски — Full: стиль доски — та же липкая настройка-предпочтение,
        # что и модель картинок/видео (персистентна по спеке, не one-shot) —
        # «◀️ В меню» не должно гасить подключённую доску.
        new_state.board_style_note = prev_state.board_style_note
        new_state.board_style_board_id = prev_state.board_style_board_id
        new_state.board_style_short_id = prev_state.board_style_short_id
    context.user_data["state"] = new_state
    await query.message.reply_text(
        "Готово — текущее описание и фото очищены.\n"
        "Баланс и аватары на месте. Можно начинать заново!",
        reply_markup=main_menu_kb(user.id),
    )
    return


async def _cb_show_buy(update, context, query, user):
    await buy(update, context)
    return


async def _cb_open_ref(update, context, query, user):
    await referral(update, context)
    return


async def _cb_show_avatar(update, context, query, user):
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


async def _cb_video_open(update, context, query, user):
    state = get_or_init_state(context)
    # Симметрия с аватарным входом (тот зовёт deactivate_video_session):
    # вход в видео-флоу гасит незавершённый аватарный — иначе handle_photo
    # проверяет generating_avatar ПЕРВЫМ и все фото молча уходят в
    # avatar_photos вместо видео-референсов (баг-ресерч 2026-08-02).
    state.generating_avatar = False
    state.mj_active = False  # см. комментарий про generating_avatar выше
    state.waiting_for_mj_prompt = False
    state.waiting_for_mj_image = False
    state.video_session_active = True
    state.waiting_for_video_prompt = False
    state.waiting_for_video_image = True
    state.waiting_for_motion_video = False

    # Хаб генерации в вебаппе (docs/specs/2026-08-13_webapp_generation_hub.md) —
    # тот же выключенный по умолчанию kill-switch, что и в reply-входе
    # (handle_menu_button, MENU_BTN_VIDEO).
    if VIDEO_CONSTRUCTOR_ENABLED and PROMPT_WEBAPP_URL:
        await query.message.reply_text(
            "🎬 Видео для Reels\n\n"
            "Настрой модель, формат, качество, фото и описание в конструкторе — "
            "и возвращайся сюда за запуском.",
            reply_markup=video_constructor_kb(user.id),
        )
        return

    # Сначала только выбор модели — полная панель настроек открывается
    # (редактированием этого же сообщения) уже после выбора, см.
    # video_model_picker_kb и ветку video_cb.startswith("video_model_")
    # ниже (решение Ани 2026-07-31, было 2 сообщения сразу со всеми
    # настройками). Уже выбирал модель в этой сессии — пикер не повторяем,
    # сразу полная панель (ТЗ video_panel_declutter).
    if state.video_model_picked:
        await query.message.reply_text(
            video_status_text(state),
            reply_markup=video_kb(state),
        )
        return
    await query.message.reply_text(
        "🎬 Видео для Reels\n\n"
        "Можно сразу отправлять текст описания и фото — сохраню в черновик.\n"
        "Выбери модель:",
        reply_markup=video_model_picker_kb(),
    )
    return


async def _cb_video_set_prompt(update, context, query, user):
    state = get_or_init_state(context)
    state.generating_avatar = False  # см. комментарий в _cb_video_open
    state.mj_active = False
    state.waiting_for_mj_prompt = False
    state.waiting_for_mj_image = False
    state.video_session_active = True
    state.waiting_for_video_prompt = True
    await query.message.reply_text("Напиши описание для видео одним сообщением.")
    return


async def _cb_video_set_image(update, context, query, user):
    state = get_or_init_state(context)
    state.generating_avatar = False  # см. комментарий в _cb_video_open
    state.mj_active = False
    state.waiting_for_mj_prompt = False
    state.waiting_for_mj_image = False
    state.video_session_active = True
    state.waiting_for_video_image = True
    await query.message.reply_text(
        "Отправляй фото для видео (можно несколько подряд).\n"
        f"Лимит: до {MAX_SEEDANCE_IMAGE_REFERENCES} фото.\n"
        "Бот запомнит внешность с фото и перенесёт в видео.\n"
        "Когда всё загрузишь, нажми «🚀 Запустить видео»."
    )
    return


async def _cb_video_clear_images(update, context, query, user):
    state = get_or_init_state(context)
    set_video_image_urls(state, [])
    state.waiting_for_video_image = True
    state.video_session_active = True
    await update_video_panel(
        query,
        "Фото очищены ✅\n\n" + video_status_text(state),
        video_kb(state),
    )
    return


async def _cb_video_facegrid_toggle(update, context, query, user):
    state = get_or_init_state(context)
    state.video_session_active = True
    state.video_face_grid = not get_face_grid(state)
    await update_video_panel(query, video_status_text(state), video_kb(state))
    return


async def _cb_video_set_video(update, context, query, user):
    await query.message.reply_text("Для этой модели этот шаг не нужен.")
    return


async def _cb_video_set_duration(update, context, query, user):
    state = get_or_init_state(context)
    state.video_session_active = True
    state.waiting_for_video_duration = True
    dur_min, dur_max = get_seedance_duration_bounds(get_video_model(state))
    await query.message.reply_text(
        f"Напиши число секунд от {dur_min} до {dur_max} одним сообщением."
    )
    return


async def _cb_video_change_model(update, context, query, user):
    state = get_or_init_state(context)
    state.video_session_active = True
    await update_video_panel(query, "🎬 Видео для Reels\n\nВыбери модель:", video_model_picker_kb())
    return


async def _cb_video_start(update, context, query, user):
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
                "Открой «🎬 Видео для Reels», добавь фото и описание — и запускай.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎬 Видео для Reels", callback_data="video")],
                ]),
            )
            return
    # НЕ гасим video_session_active/waiting_for_video_image здесь: run_seedance
    # деактивирует видео-режим сам, ПОСЛЕ валидаций и списания. Если погасить
    # до запуска, early-return («нужно описание или фото») оставляет флаги
    # выключенными — следующее сообщение молча уходит в фото-флоу, хотя
    # видео-панель на экране (регресс из audits/2026-07-02_qa_live_retest №2).
    # Add to processing_user_ids BEFORE create_task to close the race window
    processing_user_ids.add(user_vs.id)
    try:
        context.application.create_task(run_seedance(update, context))
    except Exception:
        processing_user_ids.discard(user_vs.id)
        logger.exception("create_task(run_seedance) failed for user=%s", user_vs.id)
        await query.answer("Не удалось запустить генерацию. Попробуй ещё раз.", show_alert=True)
    return


# ----------------------------------------------------------------------------
# Midjourney (EvoLink) — отдельный мини-флоу: сетка 4 варианта -> апскейл
# выбранного. Не переиспользует run_generation/GenerationJob (тот контракт —
# "один клик, один результат"), структурно ближе к run_kling_motion_control
# (свой gate через queued_user_ids/processing_user_ids, свой биллинг).
# ----------------------------------------------------------------------------

def mj_draft_kb(state: UserState) -> InlineKeyboardMarkup:
    rows = []
    if (state.mj_prompt or "").strip():
        rows.append([InlineKeyboardButton("🚀 Сгенерировать", callback_data="mj_generate")])
    rows.append([InlineKeyboardButton("◀️ В меню", callback_data="avatar_back_menu")])
    return InlineKeyboardMarkup(rows)


async def _cb_menu_midjourney(update, context, query, user):
    if not MIDJOURNEY_ENABLED:
        await query.message.reply_text("Midjourney пока недоступен.", reply_markup=main_menu_kb())
        return
    # Хаб генерации в вебаппе — тот же kill-switch-паттерн, что у видео/
    # аватара: выключен по умолчанию, ничего не меняется, пока флаг не включён.
    if MIDJOURNEY_CONSTRUCTOR_ENABLED and PROMPT_WEBAPP_URL:
        await query.message.reply_text(
            "🎨 Midjourney\n\n"
            "Опиши, что хочешь сгенерировать, в конструкторе — и возвращайся сюда за запуском.",
            reply_markup=midjourney_constructor_kb(user.id),
        )
        return
    state = get_or_init_state(context)
    # deactivate_video_session гасит video/motion/mj — вызываем ДО того, как
    # включим свой mj_active, иначе она же погасит и его (см. её докстринг).
    deactivate_video_session(state)
    state.generating_avatar = False
    state.mj_active = True
    state.waiting_for_mj_prompt = True
    state.waiting_for_mj_image = False
    state.mj_prompt = ""
    state.mj_reference = None
    await query.message.reply_text(
        "🎨 Midjourney\n\n"
        "Опиши, что хочешь сгенерировать, одним текстовым сообщением.\n"
        f"Стоимость: {MIDJOURNEY_GRID_COST} изюминок за сетку из 4 вариантов, "
        f"{MIDJOURNEY_UPSCALE_COST} изюминок — за увеличение понравившегося."
    )
    return


async def _cb_mj_generate(update, context, query, user):
    state = get_or_init_state(context)
    if not (state.mj_prompt or "").strip():
        await query.answer("Сначала пришли текстовое описание.", show_alert=True)
        return
    if user.id in queued_user_ids or user.id in processing_user_ids:
        await query.answer("Сырник уже занят другой задачей. Подожди.", show_alert=True)
        return
    # Reserve slot BEFORE any await — closes the race window (тот же паттерн,
    # что в run_generation/_cb_video_start).
    processing_user_ids.add(user.id)
    try:
        context.application.create_task(run_midjourney_grid(update, context))
    except Exception:
        processing_user_ids.discard(user.id)
        logger.exception("create_task(run_midjourney_grid) failed for user=%s", user.id)
        await query.answer("Не удалось запустить генерацию. Попробуй ещё раз.", show_alert=True)
    return


async def _cb_mj_pick(update, context, query, user):
    try:
        image_number = int(query.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Некорректный выбор.", show_alert=True)
        return
    if user.id in queued_user_ids or user.id in processing_user_ids:
        await query.answer("Сырник уже занят другой задачей. Подожди.", show_alert=True)
        return
    grid = _get_valid_mj_grid(user.id)
    if not grid:
        await query.answer()
        await query.message.reply_text(
            "Эта сетка устарела (прошло больше 23 часов) — сгенерируй заново.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎨 Midjourney", callback_data="menu_midjourney")
            ]]),
        )
        return
    if image_number >= len(grid.get("grid_urls") or []):
        await query.answer("Этого варианта уже нет в сетке.", show_alert=True)
        return
    processing_user_ids.add(user.id)
    try:
        context.application.create_task(
            run_midjourney_upscale(update, context, grid=grid, image_number=image_number)
        )
    except Exception:
        processing_user_ids.discard(user.id)
        logger.exception("create_task(run_midjourney_upscale) failed for user=%s", user.id)
        await query.answer("Не удалось запустить увеличение. Попробуй ещё раз.", show_alert=True)
    return


async def _cb_mj_pick_resend(update, context, query, user):
    """Кнопка-страховка: если сообщение с кнопками выбора не отправилось
    после генерации сетки (Telegram-таймаут), юзер может запросить его
    заново — картинки уже доставлены, повторной генерации/списания не будет."""
    await query.answer()
    grid = _get_valid_mj_grid(user.id)
    if not grid:
        await query.message.reply_text(
            "Эта сетка устарела (прошло больше 23 часов) — сгенерируй заново.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎨 Midjourney", callback_data="menu_midjourney")
            ]]),
        )
        return
    grid_urls = grid.get("grid_urls") or []
    await query.message.reply_text(_mj_picker_text(grid_urls), reply_markup=_mj_picker_kb(grid_urls))
    return


async def _cb_mj_grid_resend(update, context, query, user):
    """Кнопка-страховка на случай, когда даже сама сетка картинок не
    подтвердила доставку (Telegram-таймаут на send_media_group) — пробуем
    показать её ещё раз по уже сохранённым URL, без повторной генерации/
    списания (EvoLink свою работу уже сделал)."""
    await query.answer()
    grid = _get_valid_mj_grid(user.id)
    if not grid:
        await query.message.reply_text(
            "Эта сетка устарела (прошло больше 23 часов) — сгенерируй заново.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎨 Midjourney", callback_data="menu_midjourney")
            ]]),
        )
        return
    grid_urls = grid.get("grid_urls") or []
    await _deliver_mj_grid_and_picker(context, grid.get("chat_id") or update.effective_chat.id, user.id, grid_urls)
    return


QDATA_EXACT_HANDLERS = {
    "pladm_open": _cb_pladm_open,
    "pladm_list": _cb_pladm_list,
    "pladm_export": _cb_pladm_export,
    "pladm_new": _cb_pladm_new,
    "pladm_rename": _cb_pladm_rename,
    "pladm_delete": _cb_pladm_delete,
    "pladm_cancel": _cb_pladm_cancel,
    "noop": _cb_noop,
    "pl_open_webapp": _cb_pl_open_webapp,
    "pl_open": _cb_pl_open,
    "plsave_cancel": _cb_plsave_cancel,
    "generate": _cb_generate,
    "enhance_photo": _cb_enhance_photo,
    "enhance_use_pending_text": _cb_enhance_use_pending_text,
    "menu_photo": _cb_menu_photo,
    "menu_video": _cb_menu_video,
    "image_model_menu": _cb_image_model_menu,
    "image_model_set_gemini": _cb_image_model_set,
    "image_model_set_gpt5": _cb_image_model_set,
    "generate_again": _cb_generate_again,
    "animate_last": _cb_animate_last,
    "motion_start": _cb_motion_start,
    "seedance_retry": _cb_seedance_retry,
    "avatar_actions": _cb_avatar_actions,
    "avatar_use_female": _cb_avatar_use,
    "avatar_use_male": _cb_avatar_use,
    "avatar_use_child": _cb_avatar_use,
    "avatar_gen_refsheet": _cb_avatar_gen_refsheet,
    "avatar_gen_kind_female": _cb_avatar_gen_kind,
    "avatar_gen_kind_male": _cb_avatar_gen_kind,
    "avatar_gen_kind_child": _cb_avatar_gen_kind,
    "avatar_gen_start": _cb_avatar_gen_start,
    "avatar_help": _cb_avatar_help,
    "avatar_back_menu": _cb_avatar_back_menu,
    "menu_from_video": _cb_menu_from_video,
    "show_help": _cb_show_help,
    "report_problem": _cb_report_problem,
    "bug_bounty": _cb_bug_bounty,
    "report_cancel": _cb_report_cancel,
    "reset": _cb_reset,
    "show_buy": _cb_show_buy,
    "open_ref": _cb_open_ref,
    "show_avatar": _cb_show_avatar,
    "menu_midjourney": _cb_menu_midjourney,
    "mj_generate": _cb_mj_generate,
    "mj_pick_0": _cb_mj_pick,
    "mj_pick_1": _cb_mj_pick,
    "mj_pick_2": _cb_mj_pick,
    "mj_pick_3": _cb_mj_pick,
    "mj_pick_resend": _cb_mj_pick_resend,
    "mj_grid_resend": _cb_mj_grid_resend,
}

VIDEO_EXACT_HANDLERS = {
    "video": _cb_video_open,
    "video_set_prompt": _cb_video_set_prompt,
    "video_set_image": _cb_video_set_image,
    "video_clear_images": _cb_video_clear_images,
    "video_facegrid_toggle": _cb_video_facegrid_toggle,
    "video_set_video": _cb_video_set_video,
    "video_set_duration": _cb_video_set_duration,
    "video_change_model": _cb_video_change_model,
    "video_start": _cb_video_start,
}


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

    if query.data in QDATA_EXACT_HANDLERS:
        return await QDATA_EXACT_HANDLERS[query.data](update, context, query, user)

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
            if PROMPT_WEBAPP_URL:
                retry_btn = InlineKeyboardButton(
                    "📚 Библиотека стилей",
                    web_app=WebAppInfo(url=get_prompt_webapp_url(user.id)),
                )
            else:
                retry_btn = InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open")
            await query.message.reply_text(
                "Этот стиль обновился — открой «📚 Библиотека стилей» и выбери оттуда.",
                reply_markup=InlineKeyboardMarkup([[retry_btn]]),
            )
            return
        title = _showcase_item_label(item)
        _shc_kind = _showcase_item_kind(item)
        # Витрина /start — первый экран каждого нового юзера, но её клики
        # не попадали в template_usage_events вообще: топ-стили и статистика
        # систематически недооценивали самый массовый вход (баг-ресерч 2026-08-02).
        _log_template_usage_safe(user.id, title, _shc_kind, cat_idx=cat_idx, item_idx=item_idx)
        state = get_or_init_state(context)
        state.image_prompt = str(item.get("image_prompt") or "").strip()
        if _shc_kind == "video":
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
            _set_style_extract(state, bool(item.get("style_extract")))
            _hint_sc = str(item.get("upload_hint") or "").strip()
            _upload_note_sc = f"\n📎 Что загрузить: {_hint_sc}" if _hint_sc else ""
            await query.message.reply_text(
                f"Стиль «{title}» применён ✨{_upload_note_sc}\n"
                "Хочешь себя на этом фото? Сначала пришли своё фото обычным сообщением.",
                reply_markup=photo_draft_kb(state, user.id),
            )
        return

    if query.data.startswith("reward_bug_"):
        if not is_admin(update.effective_user.id):
            await query.answer("Нет доступа.", show_alert=True)
            return

        try:
            target_user_id = int(query.data.replace("reward_bug_", "", 1))
        except ValueError:
            await query.answer("Не удалось начислить: неверный user_id.", show_alert=True)
            return

        add_izyminki(target_user_id, BUG_BOUNTY_REWARD)
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎉 Подтвердили баг, который ты нашёл(а) — держи {BUG_BOUNTY_REWARD} 🍇 в подарок!\n"
                    "Спасибо, что помогаешь делать Сырник лучше 🧀"
                ),
            )
        except Exception:
            logger.warning("Failed to notify bug bounty reward to user_id=%s", target_user_id)

        # Правим клавиатуру на "Награждено" — защита от повторного клика тем же
        # админом на тот же репорт (если админов несколько, это best-effort:
        # окно гонки при одновременном клике не закрыто, но это низкий риск
        # для текущего масштаба — ADMIN_IDS короткий).
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ Награждено {BUG_BOUNTY_REWARD} 🍇", callback_data="noop")
            ]]))
        except Exception:
            pass
        await query.answer(f"Начислено {BUG_BOUNTY_REWARD} 🍇 пользователю {target_user_id} ✅")
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

    if query.data.startswith("pl_use_") or query.data.startswith("pl_usen_"):
        # pl_usen_ несёт ещё и "свои пожелания" (поле input_hint в вебаппе),
        # закодированные base64url — свободный текст не влезает как есть в
        # callback_data (лимит Telegram — 64 байта), см.
        # docs/specs/2026-07-17_inline_note_passthrough.md.
        has_note = query.data.startswith("pl_usen_")
        user_note = ""
        try:
            if has_note:
                rest = query.data[len("pl_usen_"):]
                cat_raw, item_raw, enc_note = rest.split("_", 2)
                pad = "=" * (-len(enc_note) % 4)
                user_note = base64.urlsafe_b64decode(enc_note + pad).decode("utf-8", errors="ignore").strip()
            else:
                _, _, cat_raw, item_raw = query.data.split("_", 3)
            cat_idx = int(cat_raw)
            item_idx = int(item_raw)
            item = PROMPT_LIBRARY[cat_idx]["items"][item_idx]
            item_kind = get_prompt_item_kind(item)
        except Exception:
            # callback_data несёт только cat_idx/item_idx (лимит Telegram — 64 байта
            # на callback_data, промт сюда не влезает) — если индексы не совпадают
            # с реальным PROMPT_LIBRARY (например, вебапп прислал их для карточки
            # из синтетической подборки «Новинки», а не по позиции в категории),
            # восстановить стиль тут нечем. «Попробуй ещё раз» вводит в
            # заблуждение — с теми же индексами повторный тап даст тот же отказ.
            if PROMPT_WEBAPP_URL:
                retry_btn = InlineKeyboardButton(
                    "📚 Библиотека стилей",
                    web_app=WebAppInfo(url=get_prompt_webapp_url(user.id)),
                )
            else:
                retry_btn = InlineKeyboardButton("📚 Библиотека стилей", callback_data="pl_open")
            await _reply_after_callback(
                query, context, user.id,
                "Не удалось применить именно эту карточку (возможно, устарела).\n"
                "Открой библиотеку и выбери стиль из категории заново:",
                reply_markup=InlineKeyboardMarkup([[retry_btn]]),
            )
            return

        if update.effective_user:
            _log_template_usage_safe(update.effective_user.id, _showcase_item_label(item), item_kind, cat_idx=cat_idx, item_idx=item_idx)

        state = get_or_init_state(context)
        state.image_prompt = str(item.get("image_prompt") or "").strip()
        base_prompt = str(item.get("prompt") or item.get("title") or "").strip()
        # Доски — Full (docs/specs/2026-08-09_mood_boards_full.md): описание
        # стиля активной доски — базовый слой перед промтом стиля, «свои
        # пожелания» юзера — поверх (apply_user_note_override), как и в
        # apply_webapp_prompt_payload_v2 выше.
        if state.board_style_note:
            base_prompt = apply_board_style_note(base_prompt, state.board_style_note)
        final_prompt = apply_user_note_override(base_prompt, user_note) if user_note else base_prompt
        if item_kind == "video":
            state.video_prompt = final_prompt
            state.video_session_active = True
            state.waiting_for_video_image = True
            hint = "Теперь отправь фото и запускай видео."
            if state.image_prompt:
                hint = (
                    "Теперь отправь фото и запускай видео.\n"
                    "💡 Бот сначала стилизует фото через GPT Image, затем сгенерит видео."
                )
            await _reply_after_callback(
                query, context, user.id,
                style_applied_message(_showcase_item_label(item), item, "video", user_note=user_note) + "\n" + hint,
                reply_markup=video_kb(state),
            )
            return
        deactivate_video_session(state)
        state.prompt = final_prompt
        _set_style_extract(state, bool(item.get("style_extract")))
        await _reply_after_callback(
            query, context, user.id,
            style_applied_message(_showcase_item_label(item), item, "image", user_note=user_note) + "\n"
            "Пришли своё фото — или запускай сразу.",
            reply_markup=photo_draft_kb(state, user.id),
        )
        return

    if query.data.startswith("bsc_"):
        # Доски — Full: «✅ Всё верно» под сообщением-подтверждением из
        # apply_webapp_board_style_analyze_payload (docs/specs/2026-08-09_mood_boards_full.md).
        state = get_or_init_state(context)
        short_id = query.data[len("bsc_"):]
        if not state.board_style_pending_note or state.board_style_pending_short_id != short_id:
            await query.message.reply_text(
                "Эта карточка устарела — открой доску в вебаппе и запроси анализ стиля заново."
            )
            return
        state.board_style_note = state.board_style_pending_note
        state.board_style_board_id = state.board_style_pending_board_id
        state.board_style_short_id = state.board_style_pending_short_id
        state.board_style_pending_note = None
        state.board_style_pending_board_id = None
        state.board_style_pending_title = ""
        state.board_style_pending_short_id = ""
        state.waiting_for_board_style_correction = False
        await query.message.reply_text(
            "✅ Стиль доски подключён — активен для следующих генераций.",
            reply_markup=board_style_disable_kb(state.board_style_short_id),
        )
        return

    if query.data.startswith("bse_"):
        # «✏️ Поправить» — просит юзера прислать свой текст описания стиля
        # следующим сообщением (свободный текст обрабатывается в handle_text,
        # waiting_for_board_style_correction).
        state = get_or_init_state(context)
        short_id = query.data[len("bse_"):]
        if not state.board_style_pending_note or state.board_style_pending_short_id != short_id:
            await query.message.reply_text(
                "Эта карточка устарела — открой доску в вебаппе и запроси анализ стиля заново."
            )
            return
        state.waiting_for_board_style_correction = True
        await query.message.reply_text(
            "Пришли своё описание стиля доски следующим сообщением (2-4 предложения — палитра, настроение, композиция)."
        )
        return

    if query.data.startswith("bsoff_"):
        # Чат-нативное отключение персистентного стиля доски — единственный
        # способ выключить его (вебапп для частого действия не должен
        # закрываться, см. docs/specs/2026-08-09_mood_boards_full.md, п.4).
        # Кнопка живёт под сообщением-подтверждением НАВСЕГДА (Telegram это
        # разрешает) — работает и по клику с более старого сообщения.
        state = get_or_init_state(context)
        state.board_style_note = None
        state.board_style_board_id = None
        state.board_style_short_id = ""
        await query.message.reply_text(
            "✅ Стиль доски отключён — дальше генерации идут без него."
        )
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
        "video_facegrid_toggle",
        "video_change_model",
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


    if video_cb in VIDEO_EXACT_HANDLERS:
        return await VIDEO_EXACT_HANDLERS[video_cb](update, context, query, user)

    if video_cb.startswith("video_longer_") or video_cb == "video_upgrade_seedance2":
        user_u = update.effective_user
        if user_u.id in queued_user_ids or user_u.id in processing_user_ids:
            await query.answer("Уже выполняется другая задача. Подожди.", show_alert=False)
            return
        params = last_video_params.get(user_u.id)
        video_retry_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Видео для Reels", callback_data="video")],
        ])
        if not isinstance(params, dict) or not params.get("model"):
            await query.message.reply_text(
                "Не нашла параметры прошлого видео — возможно, бот перезапускался.\n"
                "Открой «🎬 Видео для Reels» и запусти заново.",
                reply_markup=video_retry_kb,
            )
            return
        refs = [r for r in (params.get("refs") or []) if isinstance(r, str) and r.strip()]
        if any(_is_img_ref(r) and _resolve_image_bytes(r) is None for r in refs):
            await query.message.reply_text(
                "Исходное фото устарело (бот перезапускался).\n"
                "Открой «🎬 Видео для Reels», загрузи фото и запусти заново.",
                reply_markup=video_retry_kb,
            )
            return
        state = get_or_init_state(context)
        state.video_model = params["model"]
        state.video_mode = params.get("mode")
        state.video_aspect_ratio = params.get("aspect") or "16:9"
        state.video_prompt = params.get("prompt") or ""
        state.image_prompt = params.get("image_prompt") or ""
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
        # video_session_active гасит run_seedance после валидаций — см. video_start.
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

    if video_cb.startswith("video_aspect_"):
        state = get_or_init_state(context)
        state.video_session_active = True
        picked_ar = video_cb.replace("video_aspect_", "", 1).replace("x", ":")
        if picked_ar in {"16:9", "9:16", "1:1", "4:3"}:
            state.video_aspect_ratio = picked_ar
        await update_video_panel(query, video_status_text(state), video_kb(state))
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
            await update_video_panel(query, "Не нашла этот референс в буфере.", video_kb(state))
            return

        removed_url = video_images.pop(idx - 1)
        set_video_image_urls(state, video_images)
        removed_text = str(removed_url or "").strip()
        if len(removed_text) > 96:
            removed_text = f"{removed_text[:60]}...{removed_text[-28:]}"
        await update_video_panel(
            query,
            f"Удалён референс #{idx} ✅\n{removed_text}\n\n{video_status_text(state)}",
            video_kb(state),
        )
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
            # Veo 3.1 умеет только 16:9/9:16 — «1:1»/«4:3» с прошлой модели
            # иначе остаются в сводке невыбранными и провайдер их не примет.
            if state.video_aspect_ratio not in ("16:9", "9:16"):
                state.video_aspect_ratio = "16:9"
        elif picked_model == "wan27" and WAN27_ENABLED:
            state.video_model = "wan27"
            if not state.video_mode:
                state.video_mode = normalize_seedance_mode(SEEDANCE_MODE)
            # Wan 2.7 умеет только 16:9/9:16 — см. комментарий у veo31 выше.
            if state.video_aspect_ratio not in ("16:9", "9:16"):
                state.video_aspect_ratio = "16:9"
        elif picked_model == "gemini_omni" and GEMINI_OMNI_ENABLED:
            state.video_model = "gemini_omni"
            # Gemini Omni не берёт отдельный quality-параметр — mode не показывается
            # в video_kb (нет в списке моделей с mode_buttons), значение не важно.
            if state.video_aspect_ratio not in ("16:9", "9:16"):
                state.video_aspect_ratio = "16:9"
        elif picked_model == "seedance25" and SEEDANCE25_ENABLED:
            state.video_model = "seedance25"
            # Дефолт 480p (дешевле) — юзер сам переключает на 720p кнопкой
            # качества, обе цены видны сразу в video_kb.
            state.video_mode = normalize_seedance_mode(SEEDANCE25_MODE)
            if state.video_aspect_ratio not in ("16:9", "9:16"):
                state.video_aspect_ratio = "16:9"
        else:
            state.video_model = "seedance2"
            if not state.video_mode:
                state.video_mode = normalize_seedance_mode(SEEDANCE_MODE)
        state.video_model_picked = True
        await update_video_panel(query, video_status_text(state), video_kb(state))
        return

    if video_cb.startswith("video_mode_"):
        state = get_or_init_state(context)
        state.video_session_active = True
        state.waiting_for_video_image = True
        selected_model = get_video_model(state)
        if selected_model not in ("seedance2", "seedance2_fast", "kling3", "seedance25"):
            await update_video_panel(query, video_status_text(state), video_kb(state))
            return
        picked_mode = normalize_seedance_mode(video_cb.replace("video_mode_", "", 1))
        if picked_mode not in get_seedance_mode_options(selected_model):
            picked_mode = get_selected_seedance_mode(state)
        state.video_mode = picked_mode
        await update_video_panel(query, video_status_text(state), video_kb(state))
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
        await update_video_panel(query, video_status_text(state), video_kb(state))
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
        state.style_extract = False

        register_promo_click(promo_id, update.effective_user.id)

        await query.message.reply_text(
            "Готово ✨\nСтиль применён ✅",
            reply_markup=photo_draft_kb(state, update.effective_user.id),
        )
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


async def test_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команда: удалить тестовый аккаунт из базы, чтобы его следующий
    /start прошёл как новичок (проверка онбординга глазами нового юзера)."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    if not context.args:
        await update.message.reply_text(
            "Использование: /test_reset <user_id>\n"
            "Удаляет тестовый аккаунт из базы — его следующий /start пройдёт "
            "как у нового пользователя (подарок, витрина, онбординг).\n"
            "Аккаунты с платежами не удаляются."
        )
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом. Использование: /test_reset <user_id>")
        return

    result = delete_user_for_test(target_id)
    if result == "deleted":
        last_generated_image_url.pop(target_id, None)
        last_video_params.pop(target_id, None)
        await update.message.reply_text(
            f"Готово: {target_id} удалён из базы.\n"
            f"Его следующий /start пройдёт как у нового пользователя."
        )
    elif result == "has_payments":
        await update.message.reply_text(
            f"Отказ: у {target_id} есть платежи — это реальный клиент, не удаляю."
        )
    else:
        await update.message.reply_text(f"Пользователь {target_id} не найден в базе.")


async def video_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Причины отказов генераций за период. Использование: /video_errors [days=7] [image|video]"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    days = 7
    kind = None
    for arg in (context.args or []):
        a = arg.strip().lower()
        if a in ("image", "video"):
            kind = a
            continue
        try:
            days = max(1, min(int(a), 365))
        except ValueError:
            await update.message.reply_text("Использование: /video_errors [дней=7] [image|video]")
            return

    rows = get_error_breakdown(days=days, kind=kind)
    if not rows:
        await update.message.reply_text(f"Отказов за {days} дн. не найдено (kind={kind or 'все'}).")
        return

    lines = [f"Отказы генераций за {days} дн. (kind={kind or 'все'}):\n"]
    for r in rows:
        lines.append(f"• {r['error_type']}: {r['count']}")
        if r["last_message"]:
            model_info = f" [{r['model'] or r['provider'] or '?'}]"
            msg = r["last_message"][:200]
            lines.append(f"   последний:{model_info} {msg}")
    await send_long_text(update.message, "\n".join(lines))


async def provider_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сравнение провайдеров (Zveno/EvoLink/...) — success rate и реальная цена в ₽.
    Использование: /provider_stats [days=7] [image|video]"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    days = 7
    kind = None
    for arg in (context.args or []):
        a = arg.strip().lower()
        if a in ("image", "video"):
            kind = a
            continue
        try:
            days = max(1, min(int(a), 365))
        except ValueError:
            await update.message.reply_text("Использование: /provider_stats [дней=7] [image|video]")
            return

    rows = get_provider_comparison(days=days, kind=kind)
    if not rows:
        await update.message.reply_text(f"Данных за {days} дн. не найдено (kind={kind or 'все'}).")
        return

    lines = [f"Провайдеры за {days} дн. (kind={kind or 'все'}):\n"]
    current_provider = None
    for r in rows:
        if r["provider"] != current_provider:
            current_provider = r["provider"]
            lines.append(f"\n📡 {current_provider}")
        total = r["success"] + r["failed"]
        cost = f" · ₽{r['api_cost_rub']}" if r["api_cost_rub"] else ""
        per_success = f" (₽{r['cost_per_success_rub']}/успех)" if r["cost_per_success_rub"] else ""
        lines.append(
            f"• {r['model']}: ✅{r['success']} ❌{r['failed']} из {total} "
            f"(SR {r['success_rate']}%){cost}{per_success}"
        )
    await send_long_text(update.message, "\n".join(lines))


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


async def pnl_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """P&L-сводка за период. Использование: /pnl [days=7] [csv]"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    days = 7
    want_csv = False
    for arg in (context.args or []):
        a = arg.strip().lower()
        if a in ("csv", "-csv", "--csv"):
            want_csv = True
            continue
        try:
            days = max(1, min(int(a), 365))
        except ValueError:
            await update.message.reply_text("Использование: /pnl [дней=7] [csv]")
            return

    r = get_pnl_report(days=days, exclude_user_ids=list(ADMIN_IDS))

    def _money(v):
        return f"{v:,}".replace(",", " ")

    lines = [
        f"📊 P&L за {r['days']} дн. (тесты админов исключены)",
        "",
        "💰 Выручка",
        f"• Выручка, ₽: {_money(r['revenue_rub'])}" + (" (оценка)" if r["revenue_estimated"] else ""),
        f"• Изюминок продано: {_money(r['izyminki_sold'])}",
        f"• Платежей: {r['payments_count']} · платящих: {r['payers']}",
        "",
        "👥 Пользователи",
        f"• Новые: {r['new_users']} · активные: {r['active_users']}",
        f"• CR в оплату (платящие/новые): {r['cr_payment']}%",
        "",
        "🎬 Генерации по продуктам и моделям",
    ]
    if r["products"]:
        for p in r["products"]:
            net = p["charged"] - p["refunded"]
            api = f" · API ₽{p['api_cost_rub']}" if p["api_cost_rub"] else ""
            lines.append(
                f"• {p['kind']}/{p['model']}: ✅{p['success']} ❌{p['failed']} "
                f"(SR {p['success_rate']}%) · списано {p['charged']} / возврат {p['refunded']} "
                f"= {net}{api}"
            )
    else:
        lines.append("• нет данных за период")

    if r["video_models"]:
        lines.append("")
        lines.append("🎞 Success rate по видео-моделям")
        for v in r["video_models"]:
            lines.append(f"• {v['model']}: {v['success_rate']}% (✅{v['success']} / ❌{v['failed']})")

    lines += [
        "",
        "🎁 Бесплатные генерации",
        f"• Всего: {r['free_total']} · успешных: {r['free_success']}",
        "",
        "📈 Источники — новые юзеры",
    ]
    if r["source_new"]:
        for s in r["source_new"]:
            lines.append(f"• {s['source']}: {s['new_users']}")
    else:
        lines.append("• нет данных")

    lines.append("")
    lines.append("💳 Источники — оплаты")
    if r["source_pay"]:
        for s in r["source_pay"]:
            lines.append(
                f"• {s['source']}: {s['payments']} платежей / {s['payers']} платящих · {_money(s['revenue_rub'])} ₽"
            )
    else:
        lines.append("• нет оплат за период")

    await send_long_text(update.message, "\n".join(lines))

    if want_csv:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["section", "key", "value", "extra1", "extra2", "extra3"])
        w.writerow(["summary", "days", r["days"], "", "", ""])
        w.writerow(["summary", "revenue_rub", r["revenue_rub"], "estimated" if r["revenue_estimated"] else "exact", "", ""])
        w.writerow(["summary", "revenue_rub_exact", r["revenue_rub_exact"], "", "", ""])
        w.writerow(["summary", "izyminki_sold", r["izyminki_sold"], "", "", ""])
        w.writerow(["summary", "payments_count", r["payments_count"], "", "", ""])
        w.writerow(["summary", "payers", r["payers"], "", "", ""])
        w.writerow(["summary", "new_users", r["new_users"], "", "", ""])
        w.writerow(["summary", "active_users", r["active_users"], "", "", ""])
        w.writerow(["summary", "cr_payment_pct", r["cr_payment"], "", "", ""])
        w.writerow(["summary", "free_total", r["free_total"], r["free_success"], "", ""])
        for p in r["products"]:
            w.writerow([
                "product", f"{p['kind']}/{p['model']}",
                p["success"], p["failed"], p["charged"] - p["refunded"], p["api_cost_rub"],
            ])
        for s in r["source_new"]:
            w.writerow(["source_new", s["source"], s["new_users"], "", "", ""])
        for s in r["source_pay"]:
            w.writerow(["source_pay", s["source"], s["payments"], s["payers"], s["revenue_rub"], "rub"])

        data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        data.name = f"pnl_{r['days']}d.csv"
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=data,
            filename=data.name,
            caption=f"P&L CSV за {r['days']} дн.",
        )


async def template_stats_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Топ и наименее используемые шаблоны из «Библиотеки стилей».
    Использование: /template_stats [дней] (по умолчанию — за всё время)."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    days = None
    if context.args:
        try:
            days = max(1, min(int(context.args[0]), 3650))
        except ValueError:
            await update.message.reply_text("Использование: /template_stats [дней]")
            return

    counts = get_template_usage_counts(days=days)

    # Полный список шаблонов из библиотеки — чтобы никогда не использованные
    # тоже попали в отчёт (счёт 0), а не просто выпали из выборки.
    # Ключ — тот же лейбл, что в UI (_showcase_item_label): у фото-стилей часто
    # нет "title", только description, иначе большинство шаблонов выпало бы из отчёта.
    rows = []
    for cat in PROMPT_LIBRARY:
        cat_title = str(cat.get("title") or "—").strip() or "—"
        for item in cat.get("items") or []:
            item_label = _showcase_item_label(item)
            if not item_label:
                continue
            kind = get_prompt_item_kind(item)
            cnt = counts.get((cat_title, item_label), 0)
            rows.append({"category": cat_title, "title": item_label, "kind": kind, "count": cnt})

    if not rows:
        await update.message.reply_text("Библиотека стилей пуста.")
        return

    period_label = f"за {days} дн." if days else "за всё время"
    top = sorted(rows, key=lambda r: (-r["count"], r["title"]))[:10]
    bottom = sorted(rows, key=lambda r: (r["count"], r["title"]))[:10]

    def _fmt(r):
        kind_icon = "🎬" if r["kind"] == "video" else "🖼"
        return f"• {kind_icon} {r['category']} / {r['title']} — {r['count']}"

    lines = [
        f"📈 Использование шаблонов ({period_label})",
        f"Всего шаблонов в библиотеке: {len(rows)}",
        "",
        "🔥 Топ-10 самых используемых",
        *(_fmt(r) for r in top),
        "",
        "🧊 Топ-10 наименее используемых (включая никогда не использованные)",
        *(_fmt(r) for r in bottom),
    ]

    await send_long_text(update.message, "\n".join(lines))


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

# Плашка «Что умеет этот бот?» (Telegram description, лимит 512 символов).
BOT_DESCRIPTION = (
    "🧀 Сырник — бот для AI-фото и видео.\n"
    "\n"
    "🎨 Генерация изображений по тексту и фото — Nano Banana, GPT Image\n"
    "🎬 Оживление фото в видео — Seedance 2, Kling, Veo, Wan\n"
    "🪄 AI-портреты и аватары из ваших фото\n"
    "📚 Библиотека готовых стилей в один тап\n"
    "\n"
    "🎁 Бонус новичку на старте. Жми «Старт» 🚀"
)

# Краткое описание профиля (Telegram short description, лимит 120 символов).
BOT_SHORT_DESCRIPTION = (
    "🧀 AI-фото и видео: генерация картинок, оживление фото, AI-портреты. "
    "Бонус новичку на старте 🎁"
)

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


def _push_top_styles_to_webapp_repo(days: int = 30, limit: int = 10) -> None:
    """Публикует top_styles.json в репо вебаппа (docs/specs/2026-07-16_top_styles_stats_feed.md).
    Формат для фронтенда: [{"cat_idx": int, "item_idx": int, "uses_30d": int}, ...].
    Аналитика не должна ронять бот — все ошибки логируются и глотаются."""
    if not GITHUB_TOKEN or not WEBAPP_GITHUB_REPO:
        return
    import urllib.request as _req
    import base64 as _b64

    def _gh(method, path, body=None):
        import urllib.error as _err
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
        except _err.HTTPError as e:
            # Логируем код и тело ответа GitHub — иначе "403 недостаточно прав
            # у GITHUB_TOKEN на WEBAPP_GITHUB_REPO" (задокументированный
            # риск в config.py, ни разу не подтверждённый вручную) неотличим
            # в логах от "404 репо не существует" или "401 токен протух" —
            # публикация тихо не работает месяцами без единой зацепки, почему.
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                err_body = ""
            logger.warning("GitHub top_styles push HTTP %s %s %s: %s", e.code, method, path, err_body)
            return None
        except Exception as e:
            logger.warning("GitHub top_styles push error %s %s: %s", method, path, e)
            return None

    try:
        rows = get_top_styles_by_index(days=days, limit=limit)
    except Exception:
        logger.exception("get_top_styles_by_index failed")
        return

    payload_list = [
        {"cat_idx": r["cat_idx"], "item_idx": r["item_idx"], "uses_30d": r["uses"]}
        for r in rows
    ]
    content = json.dumps(payload_list, ensure_ascii=False, indent=2)

    filepath = f"/repos/{WEBAPP_GITHUB_REPO}/contents/top_styles.json"
    existing = _gh("GET", filepath)
    sha = existing.get("sha") if isinstance(existing, dict) else None

    body = {
        "message": f"stats: top_styles.json ({datetime.utcnow().strftime('%Y-%m-%d')})",
        "content": _b64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        body["sha"] = sha
    result = _gh("PUT", filepath, body)
    if result is not None:
        logger.info("top_styles.json pushed to %s (%d styles)", WEBAPP_GITHUB_REPO, len(payload_list))


async def _daily_top_styles_push_loop():
    """Раз в сутки публикует top_styles.json (спека требует «не реже раза в сутки»)."""
    while True:
        try:
            await asyncio.get_event_loop().run_in_executor(None, _push_top_styles_to_webapp_repo)
        except Exception:
            logger.exception("Daily top_styles push failed")
        await asyncio.sleep(86400)  # 24 часа


# ══════════════════════════════════════════════════════════════
# СТУДИЯ НЕЙРОМУЛЬТИКОВ — воркер очереди D1 (фаза 3 разбора монолита,
# см. docs/briefs/backend.md). Весь воркер (биллинг, генерация, поллинг,
# доставка результата в чат) вынесен в studio_worker.py — импортируем
# нужные имена, чтобы S._studio_* продолжали резолвиться (см. импорт
# `from studio_worker import (...)` в начале файла и
# `studio_worker.configure(...)` ниже, после того как здесь определены
# нужные хелперы).
# ══════════════════════════════════════════════════════════════


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
    # Описание бота (плашка «Что умеет этот бот?» над кнопкой «Старт») и краткое
    # описание профиля — задаём из кода, чтобы не править вручную в BotFather.
    try:
        await app.bot.set_my_description(description=BOT_DESCRIPTION)
        await app.bot.set_my_short_description(short_description=BOT_SHORT_DESCRIPTION)
    except Exception:
        logger.exception("Failed to set bot description")
    # Seed prompt library from remote in a thread so we don't block the event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync_prompt_library_from_remote)
    refresh_prompt_library()
    queue_worker_task = asyncio.create_task(_queue_worker_supervised(app))
    _cleanup_old_outputs(max_age_days=3)
    asyncio.create_task(_daily_log_push_loop())
    asyncio.create_task(_daily_top_styles_push_loop())
    if STUDIO_ENABLED:
        asyncio.create_task(_studio_poll_loop(app))
    else:
        logger.info("studio disabled (STUDIO_POLL_SECRET/STUDIO_API_BASE not set)")


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

# start_kling_motion_control/poll_kling_animation_custom (MashaGPT HTTP-клиент) —
# вынесены в video_providers.py (фаза 1 разбора монолита), импортированы выше.


async def run_kling_motion_control(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kling Motion Control — отдельный мини-флоу, НЕ переиспользует run_seedance
    (разные провайдер/эндпоинт/параметры, ровно 1 фото + 1 референс-видео, без
    длительности/режима/aspect ratio на выбор юзера). Гейт MOTION_CONTROL_ENABLED
    уже проверен раньше (кнопка скрыта), сюда попадаем только если флаг включён
    и юзер прошёл оба шага флоу (video_start -> motion_video_url, handle_photo ->
    motion_image_url). См. docs/specs/2026-07-31_evolink_video_provider.md."""
    user = None
    try:
        user = update.effective_user
        reply_target = update.callback_query.message if update.callback_query else update.message
        state = get_or_init_state(context)

        image_url = state.motion_image_url
        motion_video_url = state.motion_video_url
        prompt_text = (state.video_prompt or "").strip()

        if not image_url or not motion_video_url:
            await reply_target.reply_text(
                "Не хватает данных для запуска (фото или референс-видео). "
                "Открой «🕺 Видео с движением» заново."
            )
            return

        # EvoLink Kling Motion Control требует настоящий публичный HTTP(S) URL
        # для image_urls — data:/__img__ реф не принимает (в отличие от
        # Seedance/Gemini Omni, которым data: URL достаточно). Живой прод-баг
        # 2026-08-03: сырой __img__-реф улетал в EvoLink как есть и всегда
        # отбивался invalid_media_url. Хостим ДО списания — как с фото аватара.
        persistent_image_url = await _persist_image_ref(image_url)
        if not persistent_image_url:
            await reply_target.reply_text(
                "Не удалось подготовить фото для генерации (хостинг временно "
                "недоступен). Попробуй ещё раз через минуту — изюминки не списаны."
            )
            return
        image_url = persistent_image_url

        cost = KLING_MOTION_COST
        bal = get_balance(user.id)
        if bal < cost:
            await reply_target.reply_text(
                f"Не хватает изюминок.\nНужно: {cost}\nУ тебя: {bal}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Купить изюминки", callback_data="show_buy")
                ]])
            )
            return

        if not spend_izyminki(user.id, cost):
            await reply_target.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
            return

        state.motion_control_active = False
        state.waiting_for_motion_video = False
        state.waiting_for_motion_image = False

        await reply_target.reply_text("Запускаю Kling Motion Control 🕺\nОбычно занимает пару минут.")
        status_msg = await reply_target.reply_text("⏳ Генерирую видео…")

        async def _edit_status(text: str) -> None:
            try:
                await status_msg.edit_text(text)
            except Exception:
                pass

        use_evolink_motion = MOTION_CONTROL_PROVIDER == "evolink"
        motion_provider_label = "EVOLINK" if use_evolink_motion else "MASHAGPT"
        try:
            if use_evolink_motion:
                raw_task_id = await start_kling_motion_control_evolink(
                    image_url=image_url,
                    motion_video_url=motion_video_url,
                    prompt=prompt_text,
                    user_id=user.id,
                )
                # start_kling_motion_control_evolink возвращает task_id с
                # префиксом __EVOLINK__: (общий контракт _evolink_create_task) —
                # poll_evolink_task ждёт «голый» id.
                task_id = raw_task_id.split("__EVOLINK__:", 1)[1] if raw_task_id.startswith("__EVOLINK__:") else raw_task_id
                video_url = await poll_evolink_task(
                    task_id=task_id,
                    max_attempts=KLING_MOTION_MAX_POLL_ATTEMPTS,
                    poll_interval=KLING_MOTION_POLL_INTERVAL,
                )
            else:
                task_id = await start_kling_motion_control(
                    image_url=image_url,
                    motion_video_url=motion_video_url,
                    prompt=prompt_text,
                    user_id=user.id,
                )
                video_url = await poll_kling_animation_custom(
                    animation_id=task_id,
                    max_attempts=KLING_MOTION_MAX_POLL_ATTEMPTS,
                    poll_interval=KLING_MOTION_POLL_INTERVAL,
                )
            video_bytes = await download_video_bytes_with_fallback(video_url)
            saved_path = save_video_debug_copy(video_bytes, user.id, "Kling Motion Control")
            if saved_path:
                logger.info(f"Video local copy saved: {saved_path}")

            video_buffer = io.BytesIO(video_bytes)
            video_buffer.name = "kling_motion_control.mp4"
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_buffer,
                supports_streaming=True,
                caption="Готово 🕺\nKling Motion Control завершён.",
            )
            log_generation_event(
                user_id=user.id,
                kind="video",
                status="success",
                provider=motion_provider_label,
                cost=cost,
                was_free=False,
                references_count=1,
                prompt=prompt_text[:500] if prompt_text else None,
                username=user.username,
                model="kling_motion_control",
                duration_sec=KLING_MOTION_DURATION,
                charged_izyminki=cost,
                refunded_izyminki=0,
                is_admin_test=1 if user.id in ADMIN_IDS else 0,
            )
            context.application.create_task(
                _post_to_results_channel(
                    context.application, "video", video_bytes,
                    f"🕺 Kling Motion Control\n👤 {'@' + user.username if user.username else 'id' + str(user.id)}",
                    full_prompt=prompt_text,
                )
            )
        except BaseException as e:
            logger.exception("Kling Motion Control generation failed")
            add_izyminki(user.id, cost)
            log_generation_event(
                user_id=user.id,
                kind="video",
                status="failed",
                provider=motion_provider_label,
                cost=cost,
                was_free=False,
                references_count=1,
                model="kling_motion_control",
                duration_sec=KLING_MOTION_DURATION,
                charged_izyminki=cost,
                refunded_izyminki=cost,
                error_type=classify_generation_error(e),
                error_message=str(e),
                is_admin_test=1 if user.id in ADMIN_IDS else 0,
            )
            await reply_target.reply_text(
                "Не удалось выполнить Kling Motion Control.\n"
                "Временный технический сбой. Попробуй ещё раз позже.\n\n"
                "Списанные изюминки возвращены на баланс."
            )
            if isinstance(e, asyncio.CancelledError):
                raise
    finally:
        if user is not None:
            processing_user_ids.discard(user.id)


def _mj_picker_kb(grid_urls: list) -> InlineKeyboardMarkup:
    number_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(number_emoji[i], callback_data=f"mj_pick_{i}")
        for i in range(len(grid_urls))
    ]])


def _mj_picker_text(grid_urls: list) -> str:
    n = len(grid_urls)
    return (
        f"Готово 🎨 ({n} вариант{'а' if 1 < n < 5 else 'ов' if n != 1 else ''})\n"
        "Выбери вариант, чтобы увеличить в хорошем качестве "
        f"(+{MIDJOURNEY_UPSCALE_COST} изюминок):"
    )


async def _deliver_mj_grid_and_picker(context, chat_id: int, user_id: int, grid_urls: list) -> None:
    """Доставляет сетку вариантов + сообщение с кнопками выбора. Best-effort
    с ретраями на КАЖДОМ шаге, никогда не бросает исключение дальше и никогда
    не рефандит сама — вызывающий код уже решил, что генерация состоялась
    (EvoLink реально сделал картинки), а Telegram-таймаут при отправке не
    значит, что доставка не удалась (частый паттерн: клиент не дождался
    ответа, хотя сообщение реально дошло — живой прод-баг 2026-08-09: та же
    проблема, что раньше ловили на send_photo обычной фото-генерации и
    Kling Motion Control, здесь она же на send_media_group)."""
    media_delivered = False
    for attempt in range(2):
        try:
            if len(grid_urls) > 1:
                await context.bot.send_media_group(
                    chat_id=chat_id, media=[InputMediaPhoto(media=u) for u in grid_urls],
                )
            else:
                await context.bot.send_photo(chat_id=chat_id, photo=grid_urls[0])
            media_delivered = True
            break
        except Exception:
            if attempt == 0:
                await asyncio.sleep(2)
    if not media_delivered:
        logger.exception("Midjourney grid media delivery failed after retry: chat_id=%s", chat_id)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Сетка Midjourney сгенерирована, но не получилось её показать "
                    "(сбой соединения) — изюминки не списаны зря."
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔁 Показать сетку", callback_data="mj_grid_resend")
                ]]),
            )
        except Exception:
            pass
        return

    picker_sent = False
    for attempt in range(2):
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=_mj_picker_text(grid_urls), reply_markup=_mj_picker_kb(grid_urls),
            )
            picker_sent = True
            break
        except Exception:
            if attempt == 0:
                await asyncio.sleep(2)
    if not picker_sent:
        logger.exception(
            "Midjourney picker message failed after retry (images already delivered): chat_id=%s", chat_id,
        )
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Сетка готова выше ⬆️ Не получилось показать кнопки выбора с первого раза.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔁 Показать кнопки выбора", callback_data="mj_pick_resend")
                ]]),
            )
        except Exception:
            pass  # изображения уже доставлены — это лучшее, что можем сделать


async def run_midjourney_grid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Midjourney (EvoLink), фаза 1: генерация сетки 4 вариантов. Отдельный
    мини-флоу — не GenerationJob/generation_queue (тот контракт «один клик,
    один результат», у Midjourney есть промежуточный выбор варианта)."""
    user = None
    _progress_id = None
    _progress_kb = None
    try:
        user = update.effective_user
        reply_target = update.callback_query.message if update.callback_query else update.message
        state = get_or_init_state(context)
        prompt_text = (state.mj_prompt or "").strip()
        reference = state.mj_reference

        # Если юзер не прислал свой референс явно — берём сохранённый аватар
        # (тот же фолбэк, что уже есть в run_generation, SirNike.py ~4887-4897)
        # так «персонализация» Midjourney реально узнаёт лицо юзера по
        # умолчанию, а не только когда он вручную прикладывает фото.
        if not reference:
            _all_avatars = get_avatar_urls(user.id)
            _active_kind = get_active_avatar_kind(user.id)
            _avatar_order = ([_active_kind] if _active_kind else []) + ["female", "male", "child"]
            reference = next(
                (_all_avatars.get(k) for k in _avatar_order if _all_avatars.get(k)),
                None,
            )

        if not prompt_text:
            await reply_target.reply_text("Промт потерян — открой «🎨 Midjourney» заново.")
            return

        cost = MIDJOURNEY_GRID_COST
        bal = get_balance(user.id)
        if bal < cost:
            await reply_target.reply_text(
                f"Не хватает изюминок.\nНужно: {cost}\nУ тебя: {bal}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Купить изюминки", callback_data="show_buy")
                ]])
            )
            return

        # Референс (если есть) — публичный URL ДО списания (EvoLink Midjourney
        # кладёт URL в начало prompt, ему тоже нужен настоящий http(s) URL —
        # тот же паттерн, что и в фиксе Kling Motion Control).
        persistent_reference_url = None
        if reference:
            persistent_reference_url = await _persist_image_ref(reference)
            if not persistent_reference_url:
                await reply_target.reply_text(
                    "Не удалось подготовить фото-референс (хостинг временно "
                    "недоступен). Попробуй ещё раз через минуту — изюминки не списаны."
                )
                return

        if not spend_izyminki(user.id, cost):
            await reply_target.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
            return

        state.mj_active = False
        state.waiting_for_mj_prompt = False
        state.waiting_for_mj_image = False
        state.mj_prompt = ""
        state.mj_reference = None

        await reply_target.reply_text("Запускаю Midjourney 🎨\nОбычно занимает пару минут.")
        status_msg = await reply_target.reply_text("⏳ Генерирую сетку вариантов…")

        if GEN_PROGRESS_ENABLED:
            _progress_id = str(uuid.uuid4())
            if await gen_progress_create(_progress_id, user.id, "midjourney", {"cost": cost}):
                _progress_kb = gen_progress_kb(user.id, _progress_id, "midjourney")
                try:
                    await status_msg.edit_text("⏳ Генерирую сетку вариантов…", reply_markup=_progress_kb)
                except Exception:
                    pass

        async def _edit_status(text: str) -> None:
            try:
                await status_msg.edit_text(text, reply_markup=_progress_kb)
            except Exception:
                pass

        try:
            raw_task_id = await start_midjourney_task_evolink(
                prompt=prompt_text, image_url=persistent_reference_url, user_id=user.id,
            )
            task_id = raw_task_id.split("__EVOLINK__:", 1)[1] if raw_task_id.startswith("__EVOLINK__:") else raw_task_id
            # return_all=True: EvoLink Midjourney отдаёт "4 images per
            # generation" ОТДЕЛЬНЫМИ URL в results, не один сборный файл-
            # коллаж — живой прод-баг 2026-08-09, старый код брал только
            # results[0] и молча терял остальные 3 варианта.
            grid_urls = await poll_evolink_task(
                task_id=task_id,
                max_attempts=MIDJOURNEY_MAX_POLL_ATTEMPTS,
                poll_interval=MIDJOURNEY_POLL_INTERVAL,
                status_callback=_edit_status,
                return_all=True,
            )
            grid_urls = grid_urls[:4]
            _bounded_set(last_mj_grid, user.id, {
                "task_id": task_id,
                "grid_urls": grid_urls,
                "prompt": prompt_text,
                "chat_id": update.effective_chat.id,
                "created_at": time.time(),
            })
            # EvoLink уже сгенерировал картинки (реальные деньги потрачены на
            # его стороне) — с этой точки Telegram-таймауты при отправке НЕ
            # должны ни рефандить, ни пугать «временным сбоем»: сама доставка
            # (send_media_group) и сообщение с кнопками — best-effort с
            # ретраями внутри _deliver_mj_grid_and_picker, см. её докстринг.
            await _deliver_mj_grid_and_picker(context, update.effective_chat.id, user.id, grid_urls)
            if GEN_PROGRESS_ENABLED and _progress_kb is not None:
                await gen_progress_complete(_progress_id, "done", "Готово!")
            log_generation_event(
                user_id=user.id, kind="image", status="success", provider="EVOLINK_MIDJOURNEY",
                cost=cost, was_free=False, references_count=1 if reference else 0,
                prompt=prompt_text[:500], username=user.username, model=MIDJOURNEY_MODEL,
                charged_izyminki=cost, refunded_izyminki=0,
                is_admin_test=1 if user.id in ADMIN_IDS else 0,
            )
        except BaseException as e:
            logger.exception("Midjourney grid generation failed")
            add_izyminki(user.id, cost)
            if GEN_PROGRESS_ENABLED and _progress_kb is not None:
                await gen_progress_complete(_progress_id, "error", "Не получилось")
            log_generation_event(
                user_id=user.id, kind="image", status="failed", provider="EVOLINK_MIDJOURNEY",
                cost=cost, was_free=False, references_count=1 if reference else 0,
                model=MIDJOURNEY_MODEL, charged_izyminki=cost, refunded_izyminki=cost,
                error_type=classify_generation_error(e), error_message=str(e),
                is_admin_test=1 if user.id in ADMIN_IDS else 0,
            )
            await reply_target.reply_text(
                "Не удалось сгенерировать сетку Midjourney.\n"
                "Временный технический сбой. Попробуй ещё раз позже.\n\n"
                "Списанные изюминки возвращены на баланс."
            )
            if isinstance(e, asyncio.CancelledError):
                raise
    finally:
        if user is not None:
            processing_user_ids.discard(user.id)


async def run_midjourney_upscale(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, grid: dict, image_number: int,
) -> None:
    """Midjourney (EvoLink), фаза 2: апскейл одного из 4 вариантов сетки.
    Отдельная операция биллинга (не «бесплатное продолжение» сетки) — списание
    происходит в момент клика по кнопке варианта."""
    user = update.effective_user
    query = update.callback_query
    reply_target = query.message if query else update.effective_message
    chat_id = grid.get("chat_id") or update.effective_chat.id
    try:
        cost = MIDJOURNEY_UPSCALE_COST
        bal = get_balance(user.id)
        if bal < cost:
            await reply_target.reply_text(
                f"Не хватает изюминок.\nНужно: {cost}\nУ тебя: {bal}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Купить изюминки", callback_data="show_buy")
                ]])
            )
            return
        if not spend_izyminki(user.id, cost):
            await reply_target.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
            return

        status_msg = await reply_target.reply_text("⏳ Увеличиваю выбранный вариант…")

        async def _edit_status(text: str) -> None:
            try:
                await status_msg.edit_text(text)
            except Exception:
                pass

        try:
            raw_task_id = await start_midjourney_upscale_evolink(
                task_id=grid["task_id"], image_number=image_number, user_id=user.id,
            )
            task_id = raw_task_id.split("__EVOLINK__:", 1)[1] if raw_task_id.startswith("__EVOLINK__:") else raw_task_id
            final_url = await poll_evolink_task(
                task_id=task_id,
                max_attempts=MIDJOURNEY_MAX_POLL_ATTEMPTS,
                poll_interval=MIDJOURNEY_POLL_INTERVAL,
                status_callback=_edit_status,
            )
            await send_generation_result_by_url(context.application, chat_id, user.id, final_url, job=None)
            log_generation_event(
                user_id=user.id, kind="image", status="success", provider="EVOLINK_MIDJOURNEY_UPSCALE",
                cost=cost, was_free=False, references_count=0,
                prompt=(grid.get("prompt") or "")[:500], username=user.username,
                model=MIDJOURNEY_UPSCALE_MODEL, charged_izyminki=cost, refunded_izyminki=0,
                is_admin_test=1 if user.id in ADMIN_IDS else 0,
            )
        except BaseException as e:
            logger.exception("Midjourney upscale failed")
            add_izyminki(user.id, cost)
            log_generation_event(
                user_id=user.id, kind="image", status="failed", provider="EVOLINK_MIDJOURNEY_UPSCALE",
                cost=cost, was_free=False, references_count=0,
                model=MIDJOURNEY_UPSCALE_MODEL, charged_izyminki=cost, refunded_izyminki=cost,
                error_type=classify_generation_error(e), error_message=str(e),
                is_admin_test=1 if user.id in ADMIN_IDS else 0,
            )
            await reply_target.reply_text(
                "Не удалось увеличить вариант.\n"
                "Временный технический сбой. Попробуй ещё раз позже.\n\n"
                "Списанные изюминки возвращены на баланс."
            )
            if isinstance(e, asyncio.CancelledError):
                raise
    finally:
        if user is not None:
            processing_user_ids.discard(user.id)


# extract_task_video_url/extract_task_reference_count/build_seedance_prompt_with_refs/
# _data_url_to_jpeg_rgb/is_seedance_privacy_moderation_error/EVOLINK_SEEDANCE_MODEL_MAP/
# EVOLINK_SEEDANCE_MAX_IMAGES/build_evolink_url/_resolve_evolink_image_urls/
# _evolink_create_task/poll_evolink_task/start_seedance_task_evolink/
# start_gemini_omni_task_evolink/start_kling_motion_control_evolink/
# start_seedance_task/_start_seedance_task_fal/_poll_seedance_fal/poll_seedance_task —
# видео-провайдер-клиенты (Zveno + EvoLink + fal.ai), вынесены в video_providers.py
# (фаза 1 разбора монолита, см. docs/briefs/backend.md), импортированы выше.

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


# Инъекция бот-уровневых хелперов в video_providers.py (см. комментарий у
# `import video_providers` выше) — вызываем один раз, сразу после того как
# все нужные функции здесь уже определены.
video_providers.configure(
    is_img_ref=_is_img_ref,
    ref_to_data_url=_ref_to_data_url,
    resolve_image_bytes=_resolve_image_bytes,
    build_reference_sheet_url=build_seedance_reference_sheet_url,
    upload_bytes_to_freeimage=_upload_bytes_to_freeimage,
    upload_bytes_to_catbox=_upload_bytes_to_catbox,
    # lambda резолвит EVOLINK_API_KEY/SEEDANCE_PROVIDER как globals() ЭТОГО
    # модуля в момент ВЫЗОВА — тесты патчат `S.EVOLINK_API_KEY = "..."` уже
    # после импорта, и это продолжает работать (см. комментарий в
    # video_providers.py у _get_evolink_api_key_hook).
    get_evolink_api_key=lambda: EVOLINK_API_KEY,
    get_seedance_provider=lambda: SEEDANCE_PROVIDER,
)

# Инъекция бот-уровневых хелперов в photo_providers.py (см. комментарий у
# `import photo_providers` выше) — тот же паттерн, что и video_providers.configure()
# чуть выше: get_mashagpt_api_key — lambda, резолвящая MASHAGPT_API_KEY как global
# ЭТОГО модуля в момент вызова, чтобы `S.MASHAGPT_API_KEY = "..."` в тестах
# продолжал работать (см. комментарий в photo_providers.py).
photo_providers.configure(
    is_img_ref=_is_img_ref,
    ref_to_data_url=_ref_to_data_url,
    cache_image=_cache_image,
    get_mashagpt_api_key=lambda: MASHAGPT_API_KEY,
)


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


# Инъекция бот-уровневых хелперов в studio_worker.py (см. докстринг модуля и
# `import studio_worker` выше) — вызываем здесь, а не сразу за
# video_providers.configure()/photo_providers.configure() выше, потому что
# download_video_bytes_with_fallback определена только что, прямо над этим
# местом. download_video_bytes_with_fallback передана lambda с ленивым
# резолвом имени в ЭТОМ модуле (тот же трюк, что у _get_evolink_api_key_hook
# в video_providers.py) — так `S.download_video_bytes_with_fallback = ...` в
# тестах продолжает работать даже после переноса.
studio_worker.configure(
    # lambda с ленивым резолвом флагов/тарифов моделей как globals() ЭТОГО
    # модуля в момент ВЫЗОВА — тесты патчат `S.GEMINI_OMNI_ENABLED = True` и
    # т.п. уже после импорта (тот же трюк, что у _get_evolink_api_key_hook в
    # video_providers.py), и это продолжает работать.
    get_studio_video_models_raw=lambda: {
        "seedance2_fast": {"enabled": SEEDANCE_FAST_ENABLED, "cost_per_second": SEEDANCE_FAST_COST_PER_SECOND},
        "seedance2": {"enabled": SEEDANCE_ENABLED, "cost_per_second": SEEDANCE_COST_PER_SECOND},
        "kling3": {"enabled": KLING3_ENABLED, "cost_per_second": KLING3_COST_PER_SECOND},
        "veo31": {"enabled": VEO31_ENABLED, "cost_per_second": VEO31_COST_PER_SECOND},
        "wan27": {"enabled": WAN27_ENABLED, "cost_per_second": WAN27_COST_PER_SECOND},
        "gemini_omni": {"enabled": GEMINI_OMNI_ENABLED, "cost_per_second": GEMINI_OMNI_COST_PER_SECOND},
    },
    get_video_model_label=get_video_model_label,
    calc_generation_cost=calc_generation_cost,
    calc_seedance_cost=calc_seedance_cost,
    classify_generation_error=classify_generation_error,
    is_admin=is_admin,
    extract_chat_completion_text=extract_chat_completion_text,
    extract_zveno_image_result=_extract_zveno_image_result,
    upload_image_bytes_to_imgbb=upload_image_bytes_to_imgbb,
    upload_image_url_to_imgbb=upload_image_url_to_imgbb,
    download_video_bytes_with_fallback=lambda url: download_video_bytes_with_fallback(url),
)


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
                "Для видео нужно хотя бы одно: описание или фото. Добавь и запусти снова."
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
        selected_mode = get_selected_seedance_mode(state)
        selected_cps = get_video_model_cost_per_second(selected_model, selected_mode)
        selected_cost = calc_seedance_cost(selected_duration, selected_cps)
        selected_endpoint = SEEDANCE_FAST_ENDPOINT if selected_model == "seedance2_fast" else SEEDANCE_ENDPOINT
        if selected_model == "kling3":
            selected_model_slug = KLING3_MODEL
        elif selected_model == "veo31":
            selected_model_slug = VEO31_MODEL
        elif selected_model == "wan27":
            selected_model_slug = WAN27_MODEL
        elif selected_model == "seedance2_fast":
            selected_model_slug = SEEDANCE_FAST_MODEL
        elif selected_model == "seedance25":
            selected_model_slug = SEEDANCE25_MODEL
        elif selected_model == "gemini_omni":
            selected_model_slug = GEMINI_OMNI_MODEL
        else:
            selected_model_slug = SEEDANCE_MODEL

        # Провайдер-флаг (docs/specs/2026-07-31_evolink_video_provider.md): только
        # Seedance 2.0/2.0-fast умеют переключаться на EvoLink, остальные модели
        # (Kling 3.0/Веo 3.1/Wan 2.7) всегда идут через Zveno — SEEDANCE_PROVIDER
        # их не касается. Дефолт "zveno" не меняет НИЧЕГО в поведении. Gemini
        # Omni — новый продукт, которого у Zveno нет вообще, поэтому всегда
        # через EvoLink независимо от SEEDANCE_PROVIDER.
        is_gemini_omni = selected_model == "gemini_omni"
        # Seedance 2.5 — ВСЕГДА EvoLink (у Zveno этой модели нет вообще, не
        # подключена к переключателю SEEDANCE_PROVIDER, как и Gemini Omni).
        is_seedance25 = selected_model == "seedance25"
        use_evolink = seedance_uses_evolink(selected_model)
        selected_provider_label = "EVOLINK" if (use_evolink or is_gemini_omni or is_seedance25) else "ZVENO"

        # Seedance, Seedance 2.5 и Gemini Omni работают только от фото
        # (image-to-video); Kling 3.0, Veo 3.1 и Wan 2.7 умеют text-to-video.
        if selected_model in {"seedance2", "seedance2_fast", "gemini_omni", "seedance25"} and len(video_images) < 1:
            await reply_target.reply_text(
                "Загрузи хотя бы 1 фото-ференс и запусти снова.",
                reply_markup=video_kb(state),
            )
            return

        # У Gemini Omni лимит провайдера ниже общего лимита загрузки (9):
        # _resolve_evolink_image_urls молча обрежет до GEMINI_OMNI_MAX_IMAGES —
        # честно предупреждаем, какие фото реально пойдут в работу
        # (баг-ресерч 2026-08-02: раньше только warning в лог).
        if is_gemini_omni and len(video_images) > GEMINI_OMNI_MAX_IMAGES:
            await reply_target.reply_text(
                f"Gemini Omni принимает максимум {GEMINI_OMNI_MAX_IMAGES} фото — "
                f"возьму первые {GEMINI_OMNI_MAX_IMAGES} из {len(video_images)} загруженных."
            )
        # Seedance 2.5 умеет до 50 референсов, но общий лимит ЗАГРУЗКИ в UI —
        # MAX_SEEDANCE_IMAGE_REFERENCES (9), так что на практике это предупреждение
        # почти никогда не сработает — оставлено на случай будущего повышения
        # общего лимита загрузки специально под эту модель.
        if is_seedance25 and len(video_images) > SEEDANCE25_MAX_IMAGES:
            await reply_target.reply_text(
                f"Seedance 2.5 принимает максимум {SEEDANCE25_MAX_IMAGES} фото — "
                f"возьму первые {SEEDANCE25_MAX_IMAGES} из {len(video_images)} загруженных."
            )

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

        # Обработка рефа (сетка «детектор лиц») нужна только Seedance (реф
        # внешности) и только когда включён per-user тумблер (get_face_grid,
        # дефолт из env SEEDANCE_FACE_GRID — по умолчанию ВЫКЛ). Тумблер живёт
        # в video_kb (video_facegrid_toggle). Kling/Veo/Wan/Gemini Omni берут
        # картинку как первый кадр/референс-стиль — обработка ломает кадр, да и
        # детектор реальных лиц у них не ByteDance-овский.
        if get_face_grid(state) and video_images and video_model_uses_face_grid(selected_model):
            processed_refs = await apply_grid_overlay_to_refs(video_images)
            failed_count = sum(1 for r in processed_refs if r is None)
            if failed_count:
                # Раньше тут молча уходил оригинал без сетки → модерация Seedance
                # резала реальное фото, и пользователь получал непонятный отказ.
                # Честнее остановиться до списания изюминок и попросить фото заново.
                logger.warning(
                    "run_seedance: %s/%s refs failed grid processing, user=%s — aborting before charge",
                    failed_count, len(processed_refs), user.id,
                )
                await reply_target.reply_text(
                    "Не получилось подготовить фото для видео 😔\n"
                    + (
                        "Скорее всего, бот перезапускался и загруженное фото устарело.\n"
                        if failed_count == len(processed_refs)
                        else f"Не обработалось {failed_count} из {len(processed_refs)} фото.\n"
                    )
                    + "Отправь фото ещё раз и запускай — изюминки не списаны.",
                    reply_markup=video_kb(state),
                )
                return
            video_images = processed_refs

        if not spend_izyminki(user.id, selected_cost):
            await reply_target.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
            return

        # Only now, once every validation passed and izyminki are spent, are we
        # actually committed to the generation — deactivate video mode so a later
        # text message isn't mistaken for a new video prompt. Earlier early-returns
        # (empty draft, missing ref, low balance) keep the user in video mode so
        # they can fix the issue and retry without losing context. Callers
        # (video_start / seedance_retry / upsell) must NOT clear these flags
        # themselves — this is the single deactivation point.
        state.video_session_active = False
        state.waiting_for_video_prompt = False
        state.waiting_for_video_image = False

        eta_min = max(2, int(selected_duration * 0.8))
        eta_max = max(eta_min + 1, int(selected_duration * 2.0))
        # Инициализируем ДО try — если reply_text ниже сам бросит исключение
        # раньше, чем дойдёт до создания progress-строки, except-блок должен
        # безопасно прочитать _progress_kb (None), а не упасть NameError'ом
        # и не замаскировать реальную ошибку/рефанд.
        _progress_id = None
        _progress_kb = None
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

            # Живой прогресс в вебаппе (docs/specs/2026-08-13_webapp_generation_hub_full.md) —
            # тонкое зеркало, не блокирует и не может провалить саму генерацию
            # (gen_progress_create просто вернёт False, если Cloudflare недоступен).
            _progress_id = str(uuid.uuid4())
            _progress_kb = None
            if GEN_PROGRESS_ENABLED:
                _progress_created = await gen_progress_create(_progress_id, user.id, "video", {
                    "model_label": selected_model_label,
                    "aspect": getattr(state, "video_aspect_ratio", "16:9"),
                    "duration": selected_duration,
                })
                if _progress_created:
                    _progress_kb = gen_progress_kb(user.id, _progress_id, "video")
                    try:
                        await status_msg.edit_text("⏳ Генерирую видео…", reply_markup=_progress_kb)
                    except Exception:
                        pass

            async def _edit_status(text: str) -> None:
                try:
                    await status_msg.edit_text(text, reply_markup=_progress_kb)
                except Exception:
                    pass
                if GEN_PROGRESS_ENABLED and _progress_kb is not None:
                    await gen_progress_update(_progress_id, "processing", "Генерируем…")

            video_url = None
            last_seedance_error: Optional[Exception] = None
            for seedance_attempt in range(1, max_seedance_attempts + 1):
                if is_gemini_omni:
                    _start_task_fn = start_gemini_omni_task_evolink
                elif is_seedance25:
                    _start_task_fn = start_seedance25_task_evolink
                elif use_evolink:
                    _start_task_fn = start_seedance_task_evolink
                else:
                    _start_task_fn = start_seedance_task
                task_id = await _start_task_fn(
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
                "image_prompt": _saved_image_prompt,
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
            if GEN_PROGRESS_ENABLED and _progress_kb is not None:
                await gen_progress_complete(_progress_id, "done", "Готово!")
            log_generation_event(
                user_id=user.id,
                kind="video",
                status="success",
                provider=selected_provider_label,
                cost=selected_cost,
                was_free=False,
                references_count=len(video_images),
                prompt=prompt_text[:500] if prompt_text else None,
                username=user.username,
                model=selected_model,
                duration_sec=selected_duration,
                aspect_ratio=getattr(state, "video_aspect_ratio", "16:9"),
                charged_izyminki=selected_cost,
                refunded_izyminki=0,
                is_admin_test=1 if user.id in ADMIN_IDS else 0,
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
            if GEN_PROGRESS_ENABLED and _progress_kb is not None:
                await gen_progress_complete(_progress_id, "error", "Не получилось")
            # Restore state so "Повторить" can reuse the same images/prompt
            state.animation_source_urls = _saved_animation_source_urls
            state.video_prompt = _saved_video_prompt
            state.image_prompt = _saved_image_prompt
            log_generation_event(
                user_id=user.id,
                kind="video",
                status="failed",
                provider=selected_provider_label,
                cost=selected_cost,
                was_free=False,
                references_count=len(video_images),
                model=selected_model,
                duration_sec=selected_duration,
                aspect_ratio=getattr(state, "video_aspect_ratio", "16:9"),
                charged_izyminki=selected_cost,
                refunded_izyminki=selected_cost,
                error_type=classify_generation_error(e),
                error_message=str(e),
                is_admin_test=1 if user.id in ADMIN_IDS else 0,
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
            if any(k in error_text for k in (
                "insufficient_funds", "insufficient funds",
                "insufficient_quota", "insufficient credits", "insufficient_credits",
            )):
                await reply_target.reply_text(
                    f"Не удалось выполнить {selected_model_label}.\n"
                    "У провайдера видео сейчас закончился баланс.\n"
                    "Списанные изюминки возвращены на баланс."
                )
                await reply_target.reply_text(
                    "Попробовать еще раз?",
                    reply_markup=seedance_retry_kb(),
                )
                return
            if "ни одного фото-референса" in error_text or "хотя бы одно фото" in error_text:
                # Эта модель требует хотя бы 1 фото, а до провайдера не дошло
                # ни одного. Либо юзер не прикладывал фото к этой генерации,
                # либо приложенные фото устарели: они хранятся только в
                # памяти процесса (_image_cache), рестарт бота (деплой) их
                # стирает, а __img__-ref в state остаётся "живым" на вид.
                # Живой прод 2026-08-02: юзер загрузил фото ДО деплоя, запустил
                # видео ПОСЛЕ — рефы стали cache miss, генерация ушла без фото.
                # "Попробуй через минуту" тут вводит в заблуждение — повтор
                # без пересылки фото провалится так же.
                await reply_target.reply_text(
                    f"Не удалось выполнить {selected_model_label}.\n"
                    "Для этой модели нужно хотя бы одно фото, а до провайдера оно не дошло.\n"
                    "Если ты его уже присылал(а) — пришли ещё раз (бот мог перезапуститься и забыть старое) — и запусти видео заново.\n\n"
                    "Списанные изюминки возвращены на баланс."
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
                "Открой «🪄 Аватар» и загрузи несколько своих фото — бот сгенерирует "
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
        if _cost:
            _caption_parts.append(f"💰 Потрачено: {_cost} изюминок")
    try:
        _bal = get_balance(user_id)
        _caption_parts.append(f"Баланс: {_bal} изюминок")
    except Exception:
        pass
    if GPT5_IMAGE_ENABLED:
        _caption_parts.append("🧠 Другая модель — кнопкой «Модель картинок» ниже")
    _caption_parts.append("📎 Файл в хорошем качестве — следующим сообщением")
    await app.bot.send_photo(
        chat_id=chat_id,
        photo=photo_buffer,
        reply_markup=result_actions_kb(user_id=user_id, bot_username=bot_username),
        caption="\n".join(_caption_parts),
    )

    # После успешного send_photo результат ДОСТАВЛЕН — сбой в необязательном
    # хвосте (файл-вложение, nudge) не должен превращать успех в «ошибку
    # генерации»: вызывающий код по исключению отсюда решает про рефанд.
    try:
        await app.bot.send_document(
            chat_id=chat_id,
            document=doc_buffer,
        )
        if not (job and getattr(job, "save_as_avatar", False)):
            await maybe_send_avatar_nudge(app, chat_id, user_id)
    except Exception:
        logger.exception(
            "Post-delivery tail failed (photo already delivered): user=%s", user_id
        )

# ══════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ (ВОРКЕР): MashaGPT, Zveno, Nano
# ══════════════════════════════════════════════════════════════

async def _handle_generation_failure(
    app: Application,
    *,
    chat_id: int,
    user_id: int,
    job: "GenerationJob",
    error: BaseException,
    provider_label: str,
    references: List[str],
    refunded: bool,
    generation_succeeded: bool = False,
    use_moderation_message: bool = False,
) -> bool:
    """Единая точка отказа фото-генерации: возврат изюминок, сообщение юзеру,
    log_generation_event. Была продублирована почти дословно в ZVENO/MASHAGPT/
    YESAPI-ветках generate_image_by_job — правка в одном месте (как сегодняшний
    фикс формулировки insufficient_quota) требовала находить и чинить N копий.
    use_moderation_message сохраняет старое поведение 1:1 (только ZVENO её
    показывал) — унификация текста для остальных провайдеров осознанно НЕ
    сделана в этом рефакторинге, отдельная задача.
    Возвращает актуальный refunded — вызывающий код обязан переприсвоить его."""
    last_error_text = str(error) or repr(error)
    logger.error(f"Generation debug | provider={provider_label} | user_id={user_id} | error={last_error_text}")

    # generation_succeeded=True значит фото УЖЕ доставлено юзеру (флаг ставится
    # только после успешной отправки), а упал лишь пост-доставочный хвост —
    # рефанд в таком случае был бы ошибочным двойным начислением.
    if not generation_succeeded:
        if getattr(job, "cost", 0) > 0 and not refunded:
            add_izyminki(job.user_id, job.cost)
            refunded = True
        if getattr(job, "was_free", False) and not refunded:
            restore_free_generation(job.user_id)
            refunded = True

    error_type = classify_generation_error(error)
    if use_moderation_message and error_type == "moderation":
        # Раньше юзер видел только общее "что-то пошло не так" — не понимал,
        # что дело в фото/промте, и просто жал "Повторить" на той же
        # комбинации (бессмысленно, отказ повторится). Явно называем причину.
        failure_text = (
            "Модель отклонила запрос фильтром безопасности 🚫\n"
            "Попробуй другое фото и/или измени описание." + (
                "\n\n✅ Изюминки не списаны (или возвращены) — баланс не пострадал."
                if refunded else ""
            )
        )
    else:
        failure_text = generation_failure_user_text(refunded)
    if not generation_succeeded:
        # При доставленном фото сообщение «что-то пошло не так» поверх
        # полученного результата только путает — молча логируем хвостовой сбой.
        try:
            await app.bot.send_message(chat_id=chat_id, text=failure_text, reply_markup=result_actions_kb())
        except Exception:
            logger.warning("Failed to send %s failure message to user %s", provider_label, user_id)
    log_generation_event(
        user_id=user_id,
        kind="image",
        status="failed",
        provider=provider_label,
        cost=getattr(job, "cost", 0),
        was_free=getattr(job, "was_free", False),
        references_count=len(references or []),
        model=getattr(job, "image_model", None),
        aspect_ratio=getattr(job, "aspect_ratio", None),
        charged_izyminki=getattr(job, "cost", 0),
        refunded_izyminki=getattr(job, "cost", 0) if refunded else 0,
        error_type=error_type,
        error_message=last_error_text,
        is_admin_test=1 if user_id in ADMIN_IDS else 0,
    )
    return refunded


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
            image_url = await generate_image_zveno(
                prompt=prompt,
                references=references,
                user_id=user_id,
                image_model=getattr(job, "image_model", "gemini"),
            )
            _bounded_set(last_generated_prompt, user_id, prompt)
            _hist_url = image_url
            if _is_img_ref(_hist_url):
                _hist_url = await _persist_image_ref(_hist_url) or _hist_url
            add_generation_history(user_id=user_id, prompt=prompt, image_url=_hist_url)
            await send_generation_result_by_url(app, chat_id, user_id, image_url, job=job)
            # Флаг ставим ТОЛЬКО после фактической доставки фото юзеру: URL от
            # провайдера — ещё не результат (он мог протухнуть/не скачаться/не
            # отправиться в Telegram), а флаг блокирует рефанд в
            # _handle_generation_failure.
            generation_succeeded = True
            if getattr(job, "save_as_avatar", False):
                persistent_avatar_url = await _persist_image_ref(image_url)
                if persistent_avatar_url:
                    _job_avatar_kind = getattr(job, "avatar_kind", "female")
                    set_avatar_url(user_id, persistent_avatar_url, _job_avatar_kind)
                    # Свежесгенерированный аватар сразу делаем активным.
                    set_active_avatar_kind(user_id, _job_avatar_kind)
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
                model=getattr(job, "image_model", None),
                aspect_ratio=getattr(job, "aspect_ratio", None),
                charged_izyminki=getattr(job, "cost", 0),
                refunded_izyminki=0,
                is_admin_test=1 if user_id in ADMIN_IDS else 0,
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
            logger.exception("Zveno generation failed")
            refunded = await _handle_generation_failure(
                app, chat_id=chat_id, user_id=user_id, job=job, error=e,
                provider_label="ZVENO", references=references, refunded=refunded,
                generation_succeeded=generation_succeeded, use_moderation_message=True,
            )
            return

    if AI_PROVIDER == "MASHAGPT":
        try:
            image_url = await generate_image_mashagpt(
                prompt=prompt,
                references=references,
                user_id=user_id,
            )
            _bounded_set(last_generated_prompt, user_id, prompt)
            _hist_url = image_url
            if _is_img_ref(_hist_url):
                _hist_url = await _persist_image_ref(_hist_url) or _hist_url
            add_generation_history(user_id=user_id, prompt=prompt, image_url=_hist_url)
            await send_generation_result_by_url(app, chat_id, user_id, image_url, job=job)
            # Как в ZVENO-ветке: флаг только после фактической доставки.
            generation_succeeded = True
            if getattr(job, "save_as_avatar", False):
                persistent_avatar_url = await _persist_image_ref(image_url)
                if persistent_avatar_url:
                    _job_avatar_kind = getattr(job, "avatar_kind", "female")
                    set_avatar_url(user_id, persistent_avatar_url, _job_avatar_kind)
                    # Свежесгенерированный аватар сразу делаем активным.
                    set_active_avatar_kind(user_id, _job_avatar_kind)
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
                model=getattr(job, "image_model", None),
                aspect_ratio=getattr(job, "aspect_ratio", None),
                charged_izyminki=getattr(job, "cost", 0),
                refunded_izyminki=0,
                is_admin_test=1 if user_id in ADMIN_IDS else 0,
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
        except Exception as e:
            logger.exception("MashaGPT generation failed")
            refunded = await _handle_generation_failure(
                app, chat_id=chat_id, user_id=user_id, job=job, error=e,
                provider_label="MASHAGPT", references=references, refunded=refunded,
                generation_succeeded=generation_succeeded,
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
                                # Фото доставлено. Раньше сбой в хвосте ниже
                                # (документ/nudge/лог) улетал во внешний except
                                # и на attempt=0 запускал ВСЮ генерацию заново:
                                # дубль фото юзеру, повторный расход RPOINTS, а
                                # при неудаче ретрая — ещё и рефанд за уже
                                # доставленный результат.
                                generation_succeeded = True

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
                                    model=getattr(job, "image_model", None),
                                    aspect_ratio=getattr(job, "aspect_ratio", None),
                                    charged_izyminki=getattr(job, "cost", 0),
                                    refunded_izyminki=0,
                                    is_admin_test=1 if user_id in ADMIN_IDS else 0,
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
            if generation_succeeded:
                # Фото уже у юзера — упал только пост-доставочный хвост.
                # Ретраить генерацию (дубль) или рефандить нельзя.
                logger.exception(
                    "YesAPI post-delivery tail failed (photo already delivered): user=%s", user_id
                )
                return
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

    # Если дошли сюда — обе попытки не удались. Вся хвостовая логика (не
    # только отправка сообщения) намеренно в try/except — у YesAPI-ветки
    # это единственная защита от падения на log_generation_event и т.п.
    try:
        refunded = await _handle_generation_failure(
            app, chat_id=chat_id, user_id=user_id, job=job,
            error=Exception(last_error_text), provider_label="YESAPI",
            references=references, refunded=refunded,
            generation_succeeded=generation_succeeded,
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
    toggle_state = "ВКЛ 🟢" if get_face_grid(state) else "ВЫКЛ ⚪️"
    env_default = "вкл" if SEEDANCE_FACE_GRID else "выкл"
    await update.message.reply_text(
        f"Обрабатываю {len(video_images)} реф(ов) — превью сетки «детектор лиц». "
        f"Твой тумблер сейчас: {toggle_state} (env-дефолт SEEDANCE_FACE_GRID: {env_default}). "
        "Превью всегда рисует сетку — в реальной генерации она накладывается только при включённом тумблере."
    )
    try:
        processed = await apply_grid_overlay_to_refs(video_images)
    except Exception:
        logger.exception("preview_refs: processing failed")
        await update.message.reply_text("Ошибка при обработке рефов.")
        return
    for i, (orig, url) in enumerate(zip(video_images, processed), start=1):
        if url is None:
            # Grid failed — real generation would now stop before charging
            # instead of silently sending the raw photo to Seedance.
            await update.message.reply_text(
                f"Реф {i}/{len(processed)} — ❌ сетка не наложилась "
                "(генерация с таким рефом остановится до списания изюминок)"
            )
            continue
        status = "✅ обработано"
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


def log_provider_config() -> None:
    """Громкая сводка провайдеров при старте — один прод-инцидент 2026-08-01
    (AI_PROVIDER тихо потерялся в BotHost при правке других env-переменных,
    фото неделю молча шли через YesAPI вместо Zveno, обнаружилось только по
    жалобе на NOT_ENOUGH_RPOINTS) показал, что такие расхождения нужно ловить
    в логах на старте, а не через юзерские тикеты."""
    photo_provider = AI_PROVIDER
    video_provider = "evolink" if SEEDANCE_PROVIDER == "evolink" else "zveno"
    motion_provider = MOTION_CONTROL_PROVIDER if MOTION_CONTROL_ENABLED else "off"
    logger.info(
        "providers: photo=%s video=%s motion=%s gemini_omni=%s seedance25=%s studio=%s",
        photo_provider, video_provider, motion_provider,
        "on" if GEMINI_OMNI_ENABLED else "off",
        "on" if SEEDANCE25_ENABLED else "off",
        "on" if STUDIO_ENABLED else "off",
    )
    provider_keys = {
        "ZVENO": ZVENO_API_KEY, "MASHAGPT": MASHAGPT_API_KEY,
        "YESAPI": NANO_API_KEY, "EVOLINK": EVOLINK_API_KEY,
    }
    if photo_provider not in provider_keys:
        logger.warning("AI_PROVIDER=%s не распознан ни одним клиентом фото-генерации", photo_provider)
    elif not provider_keys[photo_provider]:
        logger.warning("AI_PROVIDER=%s, но ключ для него пуст — фото-генерация будет падать", photo_provider)
    if video_provider == "evolink" and not EVOLINK_API_KEY:
        logger.warning("SEEDANCE_PROVIDER=evolink, но EVOLINK_API_KEY пуст — видео будет падать")
    if SEEDANCE25_ENABLED and not EVOLINK_API_KEY:
        logger.warning("SEEDANCE25_ENABLED=1, но EVOLINK_API_KEY пуст — Seedance 2.5 будет падать (ВСЕГДА EvoLink)")
    if not ZVENO_API_KEY:
        logger.warning("ZVENO_API_KEY пуст — видео (Seedance/Kling/Veo/Wan) недоступно вне зависимости от AI_PROVIDER")
    if not (GITHUB_TOKEN and WEBAPP_GITHUB_REPO):
        # Фид «Топ-стили» (docs/specs/2026-07-16_top_styles_stats_feed.md) —
        # без токена/репо _push_top_styles_to_webapp_repo() молча ничего не
        # делает каждый день, раздел в вебаппе никогда не появится, и раньше
        # это никак не было видно в логах (сама top_styles.json не появилась
        # в репо вебаппа ни разу за месяц — обнаружено при разборе брифа
        # фронта 2026-08-14). Не хватает токена — не паникуем (может, фича
        # ещё не нужна), но факт отсутствия канала теперь виден при старте.
        logger.warning(
            "GITHUB_TOKEN/WEBAPP_GITHUB_REPO не заданы — top_styles.json (раздел "
            "«Топ-стили» в вебаппе) никогда не публикуется"
        )


def main():
    init_db()
    purge_stale_avatar_refs()

    # Черновики (фото/видео в процессе, ещё не запущенные) жили только в
    # памяти процесса — каждый "Update from Git" стирал их всем юзерам
    # посреди флоу. PicklePersistence переживает рестарт; UserState — plain
    # dataclass без блокировок/сокетов, пиклится как есть.
    persistence = PicklePersistence(filepath=os.path.join(DATA_DIR, "bot_persistence.pickle"))
    app = (
        Application.builder()
        .token(TOKEN)
        .persistence(persistence)
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
    app.add_handler(CommandHandler("bugbounty", bug_bounty_command))
    app.add_handler(CommandHandler("ai", ai_chat))
    app.add_handler(CommandHandler("hide_keyboard", hide_keyboard))
    app.add_handler(CommandHandler("admin_add", admin_add))
    app.add_handler(CommandHandler("set_avatar", set_avatar_admin))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("broadcast_promo", broadcast_promo))
    app.add_handler(CommandHandler("broadcast", broadcast_text))
    app.add_handler(CommandHandler("broadcast_text", broadcast_text))
    app.add_handler(CommandHandler("broadcast_hide_keyboard", broadcast_hide_keyboard))
    app.add_handler(CommandHandler("audience_stats", audience_stats))
    app.add_handler(CommandHandler("test_reset", test_reset))
    app.add_handler(CommandHandler("video_errors", video_errors))
    app.add_handler(CommandHandler("provider_stats", provider_stats))
    app.add_handler(CommandHandler("pnl", pnl_report))
    app.add_handler(CommandHandler("template_stats", template_stats_report))
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
    log_provider_config()
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
