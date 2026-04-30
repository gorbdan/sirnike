import asyncio
import base64
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime
from urllib.parse import urlsplit
from PIL import Image
from dataclasses import dataclass, field
from typing import List, Optional
import aiohttp
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.ext import PreCheckoutQueryHandler
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.error import BadRequest, Forbidden

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
    IMGBB_API_KEY,
    START_BONUS,
    FREE_GENERATIONS_PER_DAY,
    BASE_GENERATION_COST,
    REFERENCE_COST,
    MAX_POLL_ATTEMPTS,
    POLL_INTERVAL,
    ADMIN_IDS,
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
    SEEDANCE_ENABLED,
    SEEDANCE_FAST_ENABLED,
    SEEDANCE_FAST_ENDPOINT,
    SEEDANCE_FAST_MODEL,
    SEEDANCE_FAST_MODE,
    SEEDANCE_FAST_COST_PER_SECOND,
)

from db import (
    init_db,
    create_user_if_not_exists,
    get_balance,
    spend_izyminki,
    add_izyminki,
    get_free_info,
    use_free_generation,
    has_referral_bonus,
    mark_referral_bonus,
    get_all_user_ids,
    create_promo_broadcast,
    get_promo_broadcast,
    register_promo_click,
    get_promo_stats,
    payment_exists,
    save_payment,
    set_avatar_url,
    get_avatar_url,
    clear_avatar_url,
    log_generation_event,
    get_audience_overview,
    add_generation_history,
    get_generation_history,
    get_generation_history_item,
)

BASE_DIR = os.path.dirname(__file__)
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

log_handlers = [logging.StreamHandler()]
try:
    file_handler = RotatingFileHandler(
        os.path.join(BASE_DIR, "bot.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    log_handlers.append(file_handler)
except Exception:
    # If file logging cannot be initialized, keep console logging alive.
    pass

logging.basicConfig(
    level=logging.INFO,
    handlers=log_handlers,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ----------------------------
# State
# ----------------------------

photo_tasks = {}
photo_counts = {}
last_generated_image_url = {}
last_generated_prompt = {}
last_generation_references = {}
MAX_SEEDANCE_IMAGE_REFERENCES = 2
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
    waiting_for_problem_report: bool = False
    motion_prompt: str = ""
    motion_video_url: Optional[str] = None
    motion_duration: Optional[int] = None
    motion_model: str = "seedance2"
    waiting_for_motion_prompt: bool = False
    waiting_for_motion_image: bool = False
    waiting_for_motion_video: bool = False

@dataclass
class GenerationJob:
    chat_id: int
    user_id: int
    prompt: str
    references: List[str]
    message_id: Optional[int] = None
    cost: int = 0
    was_free: bool = False

generation_queue = asyncio.Queue()
queued_user_ids = set()
processing_user_ids = set()
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

PROMPT_LIBRARY_PRIMARY_PATH = os.path.join(os.path.dirname(__file__), "webapp", "prompt_library.json")
PROMPT_LIBRARY_LEGACY_PATH = os.path.join(os.path.dirname(__file__), "prompt_library.json")


def load_prompt_library() -> list:
    candidates = []
    if os.path.exists(PROMPT_LIBRARY_PRIMARY_PATH):
        candidates.append(PROMPT_LIBRARY_PRIMARY_PATH)
    if os.path.exists(PROMPT_LIBRARY_LEGACY_PATH):
        candidates.append(PROMPT_LIBRARY_LEGACY_PATH)
    if not candidates:
        return DEFAULT_PROMPT_LIBRARY

    # If both files exist, pick the freshest one.
    source_path = max(candidates, key=lambda p: os.path.getmtime(p))

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list) or not data:
            logger.warning("prompt_library.json is empty or invalid list, using defaults")
            return DEFAULT_PROMPT_LIBRARY

        for cat in data:
            if not isinstance(cat, dict):
                raise ValueError("Category item must be object")
            if "title" not in cat or "items" not in cat:
                raise ValueError("Category must contain title and items")
            if not isinstance(cat["items"], list):
                raise ValueError("Category items must be list")

        return data
    except Exception as e:
        logger.exception(f"Failed to load prompt_library.json: {e}")
        return DEFAULT_PROMPT_LIBRARY


PROMPT_LIBRARY = load_prompt_library()


def save_prompt_library(data: list) -> None:
    os.makedirs(os.path.dirname(PROMPT_LIBRARY_PRIMARY_PATH), exist_ok=True)
    with open(PROMPT_LIBRARY_PRIMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Keep legacy root file in sync as a mirror source for local tooling/backups.
    with open(PROMPT_LIBRARY_LEGACY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def refresh_prompt_library() -> None:
    global PROMPT_LIBRARY
    PROMPT_LIBRARY = load_prompt_library()


# ----------------------------
# Helpers
# ----------------------------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def calc_generation_cost(references: Optional[List[str]] = None) -> int:
    cost = BASE_GENERATION_COST
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


def get_seedance_duration_options(model_code: Optional[str] = None) -> List[int]:
    raw_options = SEEDANCE_FAST_DURATION_OPTIONS if model_code == "seedance2_fast" else SEEDANCE_DURATION_OPTIONS
    parsed: List[int] = []
    for raw in str(raw_options).split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            sec = int(raw)
        except ValueError:
            continue
        sec = max(5, min(sec, 10))
        if sec not in parsed:
            parsed.append(sec)

    default_sec = max(5, min(int(SEEDANCE_DURATION), 10))
    if default_sec not in parsed:
        parsed.append(default_sec)
    parsed.sort()
    return parsed


def get_selected_seedance_duration(state: UserState) -> int:
    model_code = get_motion_model(state)
    options = get_seedance_duration_options(model_code)
    default_sec = options[0] if options else max(5, min(int(SEEDANCE_DURATION), 10))
    selected = state.motion_duration if isinstance(state.motion_duration, int) else default_sec
    if selected not in options:
        selected = default_sec
    return selected


def get_motion_image_urls(state: UserState) -> List[str]:
    urls: List[str] = []
    for item in state.animation_source_urls:
        if isinstance(item, str):
            candidate = item.strip()
            if candidate and candidate not in urls:
                urls.append(candidate)
    if isinstance(state.animation_source_url, str):
        candidate = state.animation_source_url.strip()
        if candidate and candidate not in urls:
            urls.append(candidate)
    return urls[:MAX_SEEDANCE_IMAGE_REFERENCES]


def set_motion_image_urls(state: UserState, image_urls: List[str]) -> None:
    clean_urls: List[str] = []
    for item in image_urls:
        if isinstance(item, str):
            candidate = item.strip()
            if candidate and candidate not in clean_urls:
                clean_urls.append(candidate)
    clean_urls = clean_urls[:MAX_SEEDANCE_IMAGE_REFERENCES]
    state.animation_source_urls = clean_urls
    state.animation_source_url = clean_urls[-1] if clean_urls else None


def add_motion_image_url(state: UserState, image_url: str) -> int:
    current = get_motion_image_urls(state)
    candidate = image_url.strip()
    if candidate and candidate not in current:
        if len(current) >= MAX_SEEDANCE_IMAGE_REFERENCES:
            current = current[-(MAX_SEEDANCE_IMAGE_REFERENCES - 1):]
        current.append(candidate)
    set_motion_image_urls(state, current)
    return len(state.animation_source_urls)


def get_motion_model(state: UserState) -> str:
    if state.motion_model == "seedance2_fast" and SEEDANCE_FAST_ENABLED:
        return "seedance2_fast"
    return "seedance2"


def get_motion_model_label(model_code: str) -> str:
    return "Seedance 2.0 Fast" if model_code == "seedance2_fast" else "Seedance 2"


def get_motion_model_cost_per_second(model_code: str) -> float:
    if model_code == "seedance2_fast":
        return max(SEEDANCE_FAST_COST_PER_SECOND, 0.01)
    return max(SEEDANCE_COST_PER_SECOND, 0.01)


def calc_seedance_cost(duration_sec: int, cost_per_second: Optional[float] = None) -> int:
    cps = max(
        cost_per_second if cost_per_second is not None else SEEDANCE_COST_PER_SECOND,
        0.01,
    )
    safe_duration = max(5, min(int(duration_sec), 10))
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
    refund_text = "\n\nСписанные изюминки возвращены на баланс." if refunded else ""
    return (
        "Наблюдаются сбои, мы работаем над этим❤️\n"
        "Попробуй, пожалуйста, еще раз через пару минут."
        f"{refund_text}"
    )


def motion_unavailable_text() -> str:
    return "Seedance в разработке 🚧\nСкоро включим эту функцию."

def schedule_photo_done_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    old_task = photo_tasks.get(chat_id)
    if old_task and not old_task.done():
        old_task.cancel()

    async def send_done_later():
        try:
            await asyncio.sleep(2.0)
            count = photo_counts.get(chat_id, 0)
            if count > 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Фото-референсы успешно загружены: {count} шт.",
                    reply_markup=main_menu_kb()
                )
                photo_counts[chat_id] = 0
        except asyncio.CancelledError:
            pass

    photo_tasks[chat_id] = asyncio.create_task(send_done_later())


def main_menu_kb() -> InlineKeyboardMarkup:
    if PROMPT_WEBAPP_URL:
        prompt_library_button = InlineKeyboardButton(
            "Библиотека промптов 📚",
            callback_data="pl_open_webapp",
        )
    else:
        prompt_library_button = InlineKeyboardButton(
            "Библиотека промптов 📚",
            callback_data="pl_open",
        )

    rows = [
        [InlineKeyboardButton("Запустить генерацию⚡", callback_data="generate")],
        [prompt_library_button],
    ]
    motion_label = "Seedance 2 🎞" if SEEDANCE_ENABLED else "Seedance 🚧 (в разработке)"
    rows.append([InlineKeyboardButton(motion_label, callback_data="seedance_control")])
    rows.extend([
        [InlineKeyboardButton("Действия с аватаром 👤", callback_data="avatar_actions")],
        [InlineKeyboardButton("Сообщить о проблеме 🚨", callback_data="report_problem")],
        [InlineKeyboardButton("Сбросить всё❌", callback_data="reset")],
    ])
    return InlineKeyboardMarkup(rows)

def promo_try_kb(promo_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Попробовать", callback_data=f"promo_try_{promo_id}")]
    ])


def support_report_admin_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Ответить пользователю 💬", callback_data=f"support_reply_{user_id}")]
    ])


def avatar_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Заменить аватар 🔁", callback_data="set_avatar")],
        [InlineKeyboardButton("Показать аватар 👀", callback_data="show_avatar")],
        [InlineKeyboardButton("Удалить аватар 🗑", callback_data="delete_avatar")],
        [InlineKeyboardButton("Назад в меню ↩️", callback_data="avatar_back_menu")],
    ])


def webapp_open_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Открыть библиотеку 📚", web_app=WebAppInfo(url=PROMPT_WEBAPP_URL))]],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
    )


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
        rows.append([InlineKeyboardButton(item["title"], callback_data=f"pl_view_{cat_idx}_{item_idx}")])
    rows.append([InlineKeyboardButton("← К категориям", callback_data="pl_open")])
    return InlineKeyboardMarkup(rows)


def prompt_library_item_kb(cat_idx: int, item_idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Использовать промпт ✅", callback_data=f"pl_use_{cat_idx}_{item_idx}")],
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
        label = f"{idx + offset}. {prompt_preview or 'Без промпта'}"
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


def motion_control_kb(state: UserState) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Промпт ✍️", callback_data="mc_set_prompt")],
        [InlineKeyboardButton("Изображение 🌄", callback_data="mc_set_image")],
        [InlineKeyboardButton("Запустить Seedance 1.5 Pro ⚡", callback_data="mc_start")],
    ])


def motion_control_status_text(state: UserState) -> str:
    prompt_state = "добавлен" if state.motion_prompt.strip() else "необязательно"
    motion_images = get_motion_image_urls(state)
    image_state = (
        f"{len(motion_images)} шт. (макс. {MAX_SEEDANCE_IMAGE_REFERENCES})"
        if motion_images
        else "не добавлено"
    )
    selected_duration = SEEDANCE_DURATION
    eta_min = max(2, int(selected_duration * 0.8))
    eta_max = max(eta_min + 1, int(selected_duration * 2.0))

    return (
        "Seedance 1.5 Pro (тест для админа)\n"
        "Генерация видео с помощью нейросети.\n"
        "Можно запустить только с промптом, но лучше добавить 1–2 фото персонажа.\n"
        "Фото используются как референсы внешности и стиля персонажа.\n\n"
        "1. Нажми «Промпт» (необязательно)\n"
        "2. Добавь «Изображение» (до 2 фото-референсов)\n"
        "3. Запусти генерацию\n\n"
        f"Промпт: {prompt_state}\n"
        f"Изображение: {image_state}\n"
        f"Качество: {SEEDANCE_MODE} (фиксировано)\n"
        f"Длительность: {SEEDANCE_DURATION} сек\n"
        f"Ожидание результата: обычно {eta_min}–{eta_max} мин"
    )

# Override legacy motion UI helpers with Seedance 2 + variable duration/cost.
def motion_control_kb(state: UserState) -> InlineKeyboardMarkup:
    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_motion_model(state)
    duration_buttons = []
    for sec in get_seedance_duration_options(selected_model):
        cost = calc_seedance_cost(sec)
        prefix = "● " if sec == selected_duration else ""
        duration_buttons.append(
            InlineKeyboardButton(
                f"{prefix}{sec}с · {cost} изюминок",
                callback_data=f"mc_duration_{sec}",
            )
        )

    rows = [
        [InlineKeyboardButton("Промпт ✍️", callback_data="mc_set_prompt")],
        [InlineKeyboardButton("Изображение 🌄", callback_data="mc_set_image")],
    ]
    if duration_buttons:
        rows.append(duration_buttons[:3])
    if len(duration_buttons) > 3:
        rows.append(duration_buttons[3:])
    rows.append([InlineKeyboardButton("Запустить Seedance 2 ⚡", callback_data="mc_start")])
    return InlineKeyboardMarkup(rows)


def motion_control_status_text(state: UserState) -> str:
    prompt_state = "добавлен" if state.motion_prompt.strip() else "необязательно"
    motion_images = get_motion_image_urls(state)
    image_state = (
        f"{len(motion_images)} шт. (макс. {MAX_SEEDANCE_IMAGE_REFERENCES})"
        if motion_images
        else "не добавлено"
    )
    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_motion_model(state)
    selected_model_label = get_motion_model_label(selected_model)
    selected_cps = get_motion_model_cost_per_second(selected_model)
    selected_cost = calc_seedance_cost(selected_duration, selected_cps)
    selected_endpoint = SEEDANCE_FAST_ENDPOINT if selected_model == "seedance2_fast" else SEEDANCE_ENDPOINT
    selected_mode = SEEDANCE_FAST_MODE if selected_model == "seedance2_fast" else SEEDANCE_MODE
    selected_model_slug = SEEDANCE_FAST_MODEL if selected_model == "seedance2_fast" else SEEDANCE_MODEL
    eta_min = max(2, int(selected_duration * 0.8))
    eta_max = max(eta_min + 1, int(selected_duration * 2.0))
    options_text = ", ".join([f"{sec}с" for sec in get_seedance_duration_options(selected_model)])

    return (
        "Seedance 2 (тест для админа)\n"
        "Генерация видео с помощью нейросети.\n"
        "Можно запустить только с промптом, но лучше добавить 1–2 фото персонажа.\n"
        "Фото используются как референсы внешности и стиля персонажа.\n\n"
        "1. Нажми «Промпт» (необязательно)\n"
        "2. Добавь «Изображение» (до 2 фото-референсов)\n"
        "3. Выбери длительность ролика\n"
        "4. Запусти генерацию\n\n"
        f"Промпт: {prompt_state}\n"
        f"Изображение: {image_state}\n"
        f"Качество: {SEEDANCE_MODE} (фиксировано)\n"
        f"Длительность: {selected_duration} сек (варианты: {options_text})\n"
        f"Стоимость: {selected_cost} изюминок\n"
        f"Ожидание результата: обычно {eta_min}–{eta_max} минут"
    )


# Final override: Seedance 2 + Seedance 2.0 Fast selector.
def motion_control_kb(state: UserState) -> InlineKeyboardMarkup:
    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_motion_model(state)
    cps = get_motion_model_cost_per_second(selected_model)

    duration_buttons = []
    for sec in get_seedance_duration_options(selected_model):
        cost = calc_seedance_cost(sec, cps)
        prefix = "● " if sec == selected_duration else ""
        duration_buttons.append(
            InlineKeyboardButton(
                f"{prefix}{sec}с · {cost} изюминок",
                callback_data=f"mc_duration_{sec}",
            )
        )

    model_buttons = [
        InlineKeyboardButton(
            ("● " if selected_model == "seedance2" else "") + "Seedance 2",
            callback_data="mc_model_seedance2",
        )
    ]
    if SEEDANCE_FAST_ENABLED:
        model_buttons.append(
            InlineKeyboardButton(
                ("● " if selected_model == "seedance2_fast" else "") + "Seedance 2.0 Fast",
                callback_data="mc_model_seedance2_fast",
            )
        )

    rows = [
        [InlineKeyboardButton("Промпт ✍️", callback_data="mc_set_prompt")],
        [InlineKeyboardButton("Изображение 🌄", callback_data="mc_set_image")],
        [InlineKeyboardButton("Очистить фото-референсы 🧹", callback_data="mc_clear_images")],
        model_buttons,
    ]
    if duration_buttons:
        rows.append(duration_buttons[:3])
    if len(duration_buttons) > 3:
        rows.append(duration_buttons[3:])
    rows.append([InlineKeyboardButton("Запустить ⚡", callback_data="mc_start")])
    return InlineKeyboardMarkup(rows)


def motion_control_status_text(state: UserState) -> str:
    prompt_state = "добавлен" if state.motion_prompt.strip() else "необязательно"
    motion_images = get_motion_image_urls(state)
    image_state = (
        f"{len(motion_images)} шт. (макс. {MAX_SEEDANCE_IMAGE_REFERENCES})"
        if motion_images
        else "не добавлено"
    )
    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_motion_model(state)
    model_label = get_motion_model_label(selected_model)
    selected_mode = SEEDANCE_FAST_MODE if selected_model == "seedance2_fast" else SEEDANCE_MODE
    cps = get_motion_model_cost_per_second(selected_model)
    selected_cost = calc_seedance_cost(selected_duration, cps)
    eta_min = max(2, int(selected_duration * 0.8))
    eta_max = max(eta_min + 1, int(selected_duration * 2.0))
    options_text = ", ".join([f"{sec}с" for sec in get_seedance_duration_options(selected_model)])
    fast_hint = " (для быстрого теста промптов)" if selected_model == "seedance2_fast" else ""
    fast_limit_hint = ""

    return (
        f"{model_label}{fast_hint}\n"
        "Генерация видео с помощью нейросети.\n"
        f"{fast_limit_hint}"
        "Можно запустить только с промптом, но лучше добавить 1–2 фото персонажа.\n"
        "Фото используются как референсы внешности и стиля персонажа.\n\n"
        "1. Нажми «Промпт» (необязательно)\n"
        "2. Добавь «Изображение» (до 2 фото-референсов)\n"
        "3. Выбери модель и длительность\n"
        "4. Запусти генерацию\n\n"
        f"Модель: {model_label}\n"
        f"Промпт: {prompt_state}\n"
        f"Изображение: {image_state}\n"
        f"Качество: {selected_mode} (фиксировано)\n"
        f"Длительность: {selected_duration} сек (варианты: {options_text})\n"
        f"Стоимость: {selected_cost} изюминок\n"
        f"Ожидание результата: обычно {eta_min}–{eta_max} минут"
    )


# ----------------------------
# Commands
# ----------------------------

def result_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Сделать еще вариант🔄", callback_data="generate_again")],
        [InlineKeyboardButton("В меню", callback_data="reset")],
    ])



def seedance_retry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Повторить 🔁", callback_data="seedance_retry")],
        [InlineKeyboardButton("В меню", callback_data="reset")],
    ])


# Override label to keep retry wording consistent after failed image generation.
def result_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Повторить 🔁", callback_data="generate_again")],
        [InlineKeyboardButton("В меню", callback_data="reset")],
    ])


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

    if referrer_id and not has_referral_bonus(user.id):
        add_izyminki(user.id, REFERRAL_BONUS_NEW_USER)
        add_izyminki(referrer_id, REFERRAL_BONUS_REFERRER)
        mark_referral_bonus(user.id)

    bal = get_balance(user.id)
    free_date, free_count = get_free_info(user.id)
    state = get_or_init_state(context)
    avatar_url = get_avatar_url(user.id)
    avatar_status = "есть" if avatar_url else "нет"

    text = (
        f"Привет от Сырника! 🧀\n\n"
        f"Отправь текст (промт) и/или референсные фото.\n"
        f"Можешь отправлять фото по одному.\n"
        f"Когда всё будет готово, нажми кнопку «Запустить генерацию⚡».\n\n"
        f"Баланс: {bal} изюминок\n"
        f"Бесплатных генераций сегодня: {free_count}/{FREE_GENERATIONS_PER_DAY}\n\n"
        f"Команды:\n"
        f"/balance — баланс\n"
        f"/buy — купить изюминки\n"
        f"/ref — реферальная ссылка\n"
        f"/ai — текстовый AI-помощник\n"
        f"/report — сообщить о проблеме\n\n"
        f"Совет: открой «Библиотека промптов 📚», если нужна готовая идея.\n\n"
        f"Сейчас в буфере:\n"
        f"• промт: {'есть' if state.prompt else 'нет'}\n"
        f"• фото: {len(state.references)}\n"
        f"• сохранённый аватар: {avatar_status}\n"
    )
    await update.message.reply_text(text, reply_markup=main_menu_kb())

    if is_new_user:
        onboarding_text = (
            "Быстрый старт:\n"
            "1) Отправь текст с идеей картинки.\n"
            "2) Либо выбери готовый шаблон в «Библиотека промптов 📚».\n"
            "3) По желанию добавь фото-референсы.\n"
            "4) Нажми «Запустить генерацию⚡».\n\n"
            "После результата используй кнопки под картинкой:\n"
            "• «Сделать еще вариант🔄»\n"
            "• «В меню»"
        )
        await update.message.reply_text(onboarding_text, reply_markup=main_menu_kb())

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    bal = get_balance(user.id)
    free_date, free_count = get_free_info(user.id)

    await update.message.reply_text(
        f"У тебя {bal} изюминок 🧀\n"
        f"Сегодня бесплатных генераций: {free_count}/{FREE_GENERATIONS_PER_DAY}"
    )

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    await update.message.reply_text(
        f"Твоя реферальная ссылка:\n{link}\n\n"
        f"Ты получишь {REFERRAL_BONUS_REFERRER} изюминок за приглашённого друга.\n"
        f"Друг получит {REFERRAL_BONUS_NEW_USER} изюминок."
    )    


async def report_problem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)
    state = get_or_init_state(context)
    state.waiting_for_problem_report = True
    await update.message.reply_text(
        "Опиши проблему одним сообщением.\n"
        "Я передам это в поддержку прямо сейчас.\n\n"
        "Если передумала, отправь: отмена"
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
        payload = payload[cut:].strip()


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
    keyboard = []
    for pack in BUY_PACKS:
        generations_count = max(1, pack["count"] // BASE_GENERATION_COST)
        generations_label = ru_plural(generations_count, "образ", "образа", "образов")
        keyboard.append([
            InlineKeyboardButton(
                text=f"{pack['count']} изюминок — {pack['price']} ₽ · ≈ {generations_count} {generations_label}",
                callback_data=f"buy_{pack['count']}_{pack['price']}"
            )
        ])

    await update.message.reply_text(
        f"Выбери пакет изюминок:\n1 обычный образ = {BASE_GENERATION_COST} изюминок.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment = update.message.successful_payment

    payment_id = payment.telegram_payment_charge_id
    payload = payment.invoice_payload

    # защита от дубля
    if payment_exists(payment_id):
        await update.message.reply_text("Платёж уже обработан.")
        return

    _, count_str, price_str = payload.split("_")
    count = int(count_str)

    # сохраняем платеж
    save_payment(user.id, payment_id, count)

    # начисляем
    add_izyminki(user.id, count)

    await update.message.reply_text(
        f"Оплата прошла успешно ✅\n"
        f"Начислено {count} изюминок 🧀"
    )


async def send_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int, price: int):
    query = update.callback_query

    generations_count = max(1, count // BASE_GENERATION_COST)
    generations_label = ru_plural(generations_count, "образ", "образа", "образов")
    prices = [LabeledPrice(label=f"{count} изюминок", amount=price * 100)]

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title="Покупка изюминок 🧀",
        description=f"{count} изюминок для генераций. Это примерно {generations_count} {generations_label}.",
        payload=f"buy_{count}_{price}",
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=prices,
        start_parameter="buy-izuminki"
    )

async def broadcast_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        except Exception:
            failed += 1
            logger.exception(f"Не удалось отправить рассылку пользователю {target_user_id}")

    await update.message.reply_text(
        f"Рассылка завершена.\n"
        f"Promo ID: {promo_id}\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}"
    )

async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    users = get_all_user_ids()
    sent = 0
    failed = 0

    for target_user_id in users:
        try:
            if source_message:
                try:
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
            else:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=text,
                )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
            logger.exception(f"Не удалось отправить рассылку пользователю {target_user_id}")

    await update.message.reply_text(
        "Рассылка завершена.\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}"
    )

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
                _, message = _create_prompt_library_category(text.strip())
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

    if state.waiting_for_motion_prompt:
        state.motion_prompt = text
        state.waiting_for_motion_prompt = False

        await update.message.reply_text(
            "Промпт для Seedance сохранён ✅\n"
            "Проверь параметры и нажми запуск.",
            reply_markup=motion_control_kb(state),
        )
        return

    state.prompt = text

    await update.message.reply_text(
        "Промт сохранён.\n"
        "Теперь можешь отправить фото-референсы или нажать «Запустить генерацию⚡».",
        reply_markup=main_menu_kb()
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    state = get_or_init_state(context)
    

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    bio = io.BytesIO()
    await file.download_to_memory(out=bio)
    bio.seek(0)

    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("image", bio.read(), filename="reference.jpg", content_type="image/jpeg")

            async with session.post(
                f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}",
                data=form,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.error(f"IMGBB upload failed: {resp.status}, body: {body}")
                    await update.message.reply_text("Не удалось загрузить фото в imgbb. Попробуй ещё раз.")
                    return

                data = json.loads(body)

                logger.info(f"IMGBB response: {json.dumps(data, ensure_ascii=False)}")

                imgbb_data = data.get("data", {})

                url = imgbb_data.get("url")
                display_url = imgbb_data.get("display_url")
                image_obj = imgbb_data.get("image", {})

                direct_url = url or image_obj.get("url") or display_url

                if not direct_url:
                    await update.message.reply_text("imgbb не вернул ссылку на фото.")
                    return

                state.animation_source_url = direct_url

                if state.waiting_for_avatar_upload:
                    set_avatar_url(user.id, direct_url)
                    state.animation_source_url = direct_url
                    state.waiting_for_avatar_upload = False

                    await update.message.reply_text(
                        "Аватар сохранён 👤\n"
                        "Теперь можешь просто отправлять промты без повторной загрузки фото.",
                        reply_markup=main_menu_kb()
                    )
                    return

                if state.waiting_for_motion_image:
                    current_refs = get_motion_image_urls(state)
                    if len(current_refs) >= MAX_SEEDANCE_IMAGE_REFERENCES and direct_url not in current_refs:
                        await update.message.reply_text(
                            "Уже загружено 2 фото для Seedance.\n"
                            "Очисти референсы или замени одно из фото, затем запускай генерацию.",
                            reply_markup=motion_control_kb(state),
                        )
                        return
                    total_refs = add_motion_image_url(state, direct_url)
                    await update.message.reply_text(
                        f"Фото для Seedance добавлено ✅\n"
                        f"Сейчас загружено: {total_refs}/{MAX_SEEDANCE_IMAGE_REFERENCES}\n"
                        "Использую фото как референсы персонажа.\n"
                        "Можешь отправить еще фото или запускать генерацию.",
                        reply_markup=motion_control_kb(state),
                    )
                    return

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

    if not state.waiting_for_motion_video:
        return

    video = update.message.video
    if not video:
        await update.message.reply_text("Пришли обычное видеофайл-сообщение для Seedance.")
        return

    tg_file = await context.bot.get_file(video.file_id)
    state.motion_video_url = f"https://api.telegram.org/file/bot{TOKEN}/{tg_file.file_path}"
    state.waiting_for_motion_video = False

    await update.message.reply_text(
        "Видео с движением добавлено ✅",
        reply_markup=motion_control_kb(state),
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
        await update.message.reply_text("В выбранном шаблоне нет промпта.")
        return

    state = get_or_init_state(context)
    state.prompt = prompt

    await update.message.reply_text(
        f"Готово ✨\nПромпт из шаблона «{title}» сохранён.\n"
        "Можешь сразу нажимать «Запустить генерацию⚡» или добавить фото-референс.",
        reply_markup=main_menu_kb(),
    )


async def apply_webapp_prompt_payload(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    action = str(payload.get("action") or "").strip().lower()
    if action and action != "set_prompt":
        return False

    prompt = str(payload.get("prompt") or "").strip()
    title = str(payload.get("title") or "шаблон").strip() or "шаблон"
    if not prompt:
        if update.effective_message:
            await update.effective_message.reply_text("В выбранном шаблоне нет промпта.")
        return False

    state = get_or_init_state(context)
    state.prompt = prompt

    if update.effective_message:
        await update.effective_message.reply_text(
            f"Готово ✨\nПромпт из шаблона «{title}» сохранён.\nТеперь можно запускать генерацию.",
            reply_markup=main_menu_kb(),
        )
    return True


async def apply_webapp_prompt_payload_v2(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    action = str(payload.get("action") or "").strip().lower()
    if action and action != "set_prompt":
        return False

    title = str(payload.get("title") or "шаблон").strip() or "шаблон"
    prompt = str(payload.get("prompt") or "").strip() or title

    state = get_or_init_state(context)
    state.prompt = prompt

    if update.effective_message:
        await update.effective_message.reply_text(
            f"Готово ✨\nШаблон «{title}» применен.\nТеперь можно запускать генерацию.",
            reply_markup=main_menu_kb(),
        )
    return True


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
        if message:
            await message.reply_text("Данные из WebApp не распознаны. Попробуй еще раз.")
        return

    applied = await apply_webapp_prompt_payload_v2(update, context, payload)
    if False:
        await message.reply_text("Кнопка WebApp скрыта.", reply_markup=ReplyKeyboardRemove())
    if not applied and message:
        await message.reply_text("Не удалось применить шаблон.")


async def upload_image_url_to_imgbb(image_url: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                image_url,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as src_resp:
                if src_resp.status != 200:
                    logger.warning(f"Failed to fetch source image for prompt library: {src_resp.status}")
                    return None
                image_bytes = await src_resp.read()

            form = aiohttp.FormData()
            form.add_field("image", image_bytes, filename="library_example.jpg", content_type="image/jpeg")

            async with session.post(
                f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}",
                data=form,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.warning(f"IMGBB upload for prompt library failed: {resp.status}, body: {body}")
                    return None
                data = json.loads(body)
                imgbb_data = data.get("data", {})
                return imgbb_data.get("url") or (imgbb_data.get("image", {}) or {}).get("url") or imgbb_data.get("display_url")
    except Exception:
        logger.exception("upload_image_url_to_imgbb failed")
        return None


async def upload_image_bytes_to_imgbb(image_bytes: bytes, filename: str = "import.jpg") -> Optional[str]:
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
                    logger.warning(f"IMGBB upload from bytes failed: {resp.status}, body: {body}")
                    return None
                data = json.loads(body)
                imgbb_data = data.get("data", {})
                return (
                    imgbb_data.get("url")
                    or (imgbb_data.get("image", {}) or {}).get("url")
                    or imgbb_data.get("display_url")
                )
    except Exception:
        logger.exception("upload_image_bytes_to_imgbb failed")
        return None
        
# ----------------------------
# Generation
# ----------------------------

async def run_generation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)

    if user.id in queued_user_ids or user.id in processing_user_ids:
        await update.callback_query.message.reply_text(
            "Сырник уже занят твоей предыдущей магией 🧀\n"
            "Дождись результата, а потом запустим следующую."
        )
        return

    state = get_or_init_state(context)

    if not state.prompt:
        await update.callback_query.message.reply_text("Сначала отправь текст промпта.")
        return

    references = list(state.references)

    avatar_url = get_avatar_url(user.id)
    if avatar_url and not references:
        
        references = [avatar_url]
    cost = calc_generation_cost(references)

    free_date, free_count = get_free_info(user.id)
    use_free = free_count < FREE_GENERATIONS_PER_DAY
    paid = False

    if not use_free:
        bal = get_balance(user.id)
        if bal < cost:
            await update.callback_query.message.reply_text(
                f"Не хватает изюминок.\n"
                f"Нужно: {cost}\n"
                f"У тебя: {bal}\n\n"
                f"Напиши /buy."
            )
            return

        if not spend_izyminki(user.id, cost):
            await update.callback_query.message.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
            return

        paid = True
    else:
        use_free_generation(user.id)

    try:
        last_generated_prompt[user.id] = state.prompt
        last_generation_references[user.id] = list(references)

        job = GenerationJob(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            prompt=state.prompt,
            references=references,
            cost=cost if paid else 0,
            was_free=use_free,
)
        

        queued_user_ids.add(user.id)
        await generation_queue.put(job)

        await update.callback_query.message.reply_text(
            "Сырник всё понял 🧀\n"
            "Скоро покажу, что получилось."
        )

        context.user_data["state"] = UserState()

    except Exception:
        logger.exception("Failed to enqueue generation job")
        queued_user_ids.discard(user.id)

        if paid:
            add_izyminki(user.id, cost)

        await update.callback_query.message.reply_text(
            "Не получилось взять задачу в работу. Попробуй ещё раз."
        )



# ----------------------------
# Buttons
# ----------------------------

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
            f"Промпт:\n{prompt_text or 'Без промпта'}\n\n"
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
        if not PROMPT_WEBAPP_URL:
            await query.message.reply_text(
                "WebApp пока не подключен. Используй встроенную библиотеку ниже.",
                reply_markup=prompt_library_menu_kb(),
            )
            return

        await query.message.reply_text(
            "Открой кнопку ниже, чтобы выбрать шаблон в мини-приложении:",
            reply_markup=webapp_open_kb(),
        )
        return

    if query.data == "pl_open":
        await query.message.reply_text(
            "Выбери категорию. Я покажу лучшие шаблоны промптов с примерами 👇",
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
        except Exception:
            await query.message.reply_text("Не удалось открыть шаблон. Попробуй еще раз.")
            return

        card_text = (
            f"Шаблон: {item['title']}\n\n"
            f"Промпт:\n{item['prompt']}\n\n"
            "Нажми «Использовать промпт», чтобы подставить его в буфер."
        )

        example_url = item.get("example_url")
        if example_url:
            try:
                await query.message.reply_photo(
                    photo=example_url,
                    caption=card_text,
                    reply_markup=prompt_library_item_kb(cat_idx, item_idx),
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
                                    reply_markup=prompt_library_item_kb(cat_idx, item_idx),
                                )
                                return
                except Exception:
                    logger.exception("Failed to send prompt example image with fallback")

        await query.message.reply_text(
            card_text,
            reply_markup=prompt_library_item_kb(cat_idx, item_idx),
        )
        return

    if query.data.startswith("pl_use_"):
        try:
            _, _, cat_raw, item_raw = query.data.split("_", 3)
            cat_idx = int(cat_raw)
            item_idx = int(item_raw)
            item = PROMPT_LIBRARY[cat_idx]["items"][item_idx]
        except Exception:
            await query.message.reply_text("Не удалось применить промпт. Попробуй еще раз.")
            return

        state = get_or_init_state(context)
        state.prompt = item["prompt"]
        await query.message.reply_text(
            f"Готово ✨\nПромпт «{item['title']}» сохранён.\n"
            "Можешь сразу нажимать «Запустить генерацию⚡» или добавить фото-референс.",
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

            image_url = pending["image_url"]
            stable_example_url = await upload_image_url_to_imgbb(image_url)
            if not stable_example_url:
                stable_example_url = image_url

            data[cat_idx].setdefault("items", [])
            data[cat_idx]["items"].append(
                {
                    "title": pending["title"],
                    "prompt": pending["prompt"],
                    "example_url": stable_example_url,
                }
            )

            save_prompt_library(data)
            refresh_prompt_library()
            context.user_data.pop("pending_pl_save", None)

            await query.message.reply_text(
                f"Готово ✅\nШаблон «{pending['title']}» добавлен в категорию «{data[cat_idx].get('title', 'Без названия')}».",
                reply_markup=main_menu_kb(),
            )
            return
        except Exception:
            logger.exception("Failed to save prompt library item via category picker")
            await query.message.reply_text("Не удалось сохранить шаблон. Попробуй ещё раз.")
            return

    motion_callbacks = {"seedance_control", "motion_control", "mc_set_prompt", "mc_set_image", "mc_clear_images", "mc_set_video", "mc_start", "seedance_retry"}
    is_motion_callback = (
        query.data in motion_callbacks
        or query.data.startswith("mc_duration_")
        or query.data.startswith("mc_model_")
    )

    if is_motion_callback and not is_admin(update.effective_user.id):
        await query.message.reply_text("Эта функция пока доступна только администратору.")
        return

    if is_motion_callback and not SEEDANCE_ENABLED:
        await query.message.reply_text(motion_unavailable_text(), reply_markup=main_menu_kb())
        return

    if query.data == "generate":
        await run_generation(update, context)
        return

    if query.data == "generate_again":
        user_id = update.effective_user.id
        saved_prompt = (last_generated_prompt.get(user_id) or "").strip()
        if not saved_prompt:
            await query.message.reply_text(
                "Не нашла прошлый промпт для повтора. Отправь новый текст и нажми «Запустить генерацию⚡»."
            )
            return

        state = get_or_init_state(context)
        state.prompt = saved_prompt
        state.references = list(last_generation_references.get(user_id) or [])
        await run_generation(update, context)
        return
    
    if query.data in {"seedance_control", "motion_control"}:
        state = get_or_init_state(context)
        if not get_motion_image_urls(state):
            last_image = last_generated_image_url.get(update.effective_user.id)
            if isinstance(last_image, str) and last_image.strip():
                add_motion_image_url(state, last_image)
        state.waiting_for_motion_prompt = False
        state.waiting_for_motion_image = False
        state.waiting_for_motion_video = False

        await query.message.reply_text(
            motion_control_status_text(state),
            reply_markup=motion_control_kb(state),
        )
        return

    if query.data == "mc_set_prompt":
        state = get_or_init_state(context)
        state.waiting_for_motion_prompt = True
        await query.message.reply_text(
            "Напиши промпт для итогового видео одним сообщением.\n"
            "Можно пропустить этот шаг: модель всё равно перенесёт движение с видео на фото."
        )
        return

    if query.data == "mc_set_image":
        state = get_or_init_state(context)
        state.waiting_for_motion_image = True
        await query.message.reply_text(
            "Отправляй фото для Seedance (можно несколько подряд).\n"
            "Лимит: до 2 фото.\n"
            "Фото используются как референсы персонажа.\n"
            "Когда всё загрузишь, нажми «Запустить ⚡»."
        )
        return

    if query.data == "mc_clear_images":
        state = get_or_init_state(context)
        set_motion_image_urls(state, [])
        state.waiting_for_motion_image = False
        await query.message.reply_text(
            "Фото-референсы очищены ✅\n\n" + motion_control_status_text(state),
            reply_markup=motion_control_kb(state),
        )
        return

    if query.data == "mc_set_video":
        await query.message.reply_text("Для Seedance 2 этот шаг не нужен.")
        return

    if query.data.startswith("mc_model_"):
        state = get_or_init_state(context)
        picked_model = query.data.replace("mc_model_", "", 1)
        if picked_model == "seedance2_fast" and SEEDANCE_FAST_ENABLED:
            state.motion_model = "seedance2_fast"
        else:
            state.motion_model = "seedance2"
        await query.message.reply_text(
            motion_control_status_text(state),
            reply_markup=motion_control_kb(state),
        )
        return

    if query.data.startswith("mc_duration_"):
        state = get_or_init_state(context)
        try:
            picked = int(query.data.replace("mc_duration_", "", 1))
        except ValueError:
            picked = get_selected_seedance_duration(state)

        selected_model = get_motion_model(state)
        if picked not in get_seedance_duration_options(selected_model):
            picked = get_selected_seedance_duration(state)

        state.motion_duration = picked
        await query.message.reply_text(
            motion_control_status_text(state),
            reply_markup=motion_control_kb(state),
        )
        return

    if query.data == "mc_start":
        state = get_or_init_state(context)
        state.waiting_for_motion_image = False
        await run_seedance(update, context)
        return

    if query.data == "seedance_retry":
        await run_seedance(update, context)
        return

    if query.data == "avatar_actions":
        await query.message.reply_text(
            "Выбери действие с аватаром:",
            reply_markup=avatar_actions_kb(),
        )
        return

    if query.data == "avatar_back_menu":
        await query.message.reply_text(
            "Главное меню:",
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
        await query.message.reply_text("Всё сброшено. Можно начать заново.")
        return
    
    if query.data.startswith("promo_try_"):
        promo_id = query.data.replace("promo_try_", "", 1)
        promo = get_promo_broadcast(promo_id)

        if not promo:
            await query.message.reply_text(
                "Этот промт больше недоступен."
            )
            return

        state = get_or_init_state(context)
        state.prompt = promo["promo_prompt"]

        register_promo_click(promo_id, update.effective_user.id)

        await query.message.reply_text(
            "Готово ✨\n"
            "Я уже сохранил промт.\n\n"
            "Теперь отправь свои фото-референсы для генерации "
            "или нажми «Запустить генерацию⚡».",
            reply_markup=main_menu_kb()
        )
        return

    if query.data.startswith("buy_"):
        _, count_str, price_str = query.data.split("_")
        count = int(count_str)
        price = int(price_str)

        await send_invoice(update, context, count, price)
        return
    
    if query.data == "set_avatar":
        state = get_or_init_state(context)
        state.waiting_for_avatar_upload = True

        await query.message.reply_text(
            "Отправь одно фото, которое нужно сохранить как аватар.\n"
            "После этого его можно будет использовать в генерациях без повторной загрузки."
        )
        return
    
    if query.data == "show_avatar":
        avatar_url = get_avatar_url(update.effective_user.id)

        if not avatar_url:
            await query.message.reply_text("У тебя пока нет сохранённого аватара.")
            return

        await query.message.reply_photo(
            photo=avatar_url,
            caption="Вот твой текущий сохранённый аватар 👤"
        )
        return
    
    if query.data == "delete_avatar":
        clear_avatar_url(update.effective_user.id)
        await query.message.reply_text("Аватар удалён.")
        return

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
        stable_example_url = await upload_image_bytes_to_imgbb(bio.read(), filename=filename)
        if not stable_example_url:
            await update.message.reply_text("Не удалось загрузить изображение для импорта. Попробуй ещё раз.")
            return
    except Exception:
        logger.exception("prompt_library_import_from_reply failed")
        await update.message.reply_text("Не удалось импортировать изображение из реплая.")
        return

    context.user_data["pending_pl_save"] = {
        "title": title,
        "prompt": prompt_text,
        "image_url": stable_example_url,
    }

    await update.message.reply_text(
        f"Импорт готов ✅\nШаблон «{title}» подготовлен (с промптом).\nТеперь выбери категорию:",
        reply_markup=prompt_library_save_category_kb(),
    )


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


def _create_prompt_library_category(raw_title: str) -> tuple[bool, str]:
    title, emoji = _parse_category_title_and_emoji(raw_title)
    if not title:
        return False, "Название категории пустое."

    data = load_prompt_library()
    if _find_category_index_by_title(data, title) >= 0:
        return False, f"Категория «{title}» уже существует."

    data.append({"title": title, "emoji": emoji, "items": []})
    save_prompt_library(data)
    refresh_prompt_library()
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
        _, message = _create_prompt_library_category(raw)
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
        save_prompt_library(data)
        refresh_prompt_library()
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
        save_prompt_library(data)
        refresh_prompt_library()
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
        save_prompt_library(data)
        refresh_prompt_library()

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


async def post_init(app: Application):
    global queue_worker_task
    queue_worker_task = asyncio.create_task(queue_worker(app))


async def post_shutdown(app: Application):
    global queue_worker_task

    if queue_worker_task and not queue_worker_task.done():
        queue_worker_task.cancel()
        try:
            await queue_worker_task
        except asyncio.CancelledError:
            pass


async def queue_worker(app: Application):
    try:
        while True:
            job = await generation_queue.get()

            queued_user_ids.discard(job.user_id)
            processing_user_ids.add(job.user_id)

            try:
                await generate_image_by_job(app, job)

            except Exception:
                logger.exception("Queue worker error")
                try:
                    await app.bot.send_message(
                        chat_id=job.chat_id,
                        text="Ой, Сырник споткнулся на пути к магии. Попробуй ещё раз чуть позже."
                    )
                except Exception:
                    pass
            finally:
                processing_user_ids.discard(job.user_id)
                generation_queue.task_done()
    except asyncio.CancelledError:
        logger.info("queue_worker stopped")
        raise

async def start_kling_motion_control(
    image_url: str,
    motion_video_url: str,
    prompt: str,
    user_id: int,
) -> str:
    if not KLING_MOTION_ENDPOINT:
        raise Exception("Эндпоинт Motion Control не настроен (KLING_MOTION_ENDPOINT).")

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
            logger.info(f"Motion Control endpoint: {request_url}")
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
                    logger.warning(f"Motion start failed for {request_url}: {last_error}")
                    continue

                data = json.loads(response_text)
                task_id = data.get("id")
                if not task_id:
                    last_error = f"Task id missing in response: {data}"
                    continue
                return str(task_id)

        raise Exception(f"Motion Control start error: {last_error}")


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
        logger.info(f"Motion poll endpoint: {url}")
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
                        f"Motion status check failed: {resp.status}, url={poll_url}, body: {response_text}"
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
                                logger.info(f"Motion running endpoint ok: {running_url}")
                                running_payload = json.loads(running_text)
                                task_obj = find_task_in_running(running_payload)
                                if task_obj:
                                    data = task_obj
                                    break
                            else:
                                logger.warning(
                                    f"Motion running check failed: {running_resp.status}, "
                                    f"url={running_url}, body: {running_text}"
                                )
                except Exception:
                    pass

            if data is not None:
                status = str(data.get("status", "")).upper()
                status_description = data.get("message") or ""

                logger.info(
                    f"Motion task {animation_id}: "
                    f"attempt={attempt + 1}/{max_attempts}, "
                    f"status={status}, "
                    f"status_description={status_description}"
                )

                if status == "COMPLETED":
                    result_url = extract_video_url(data)
                    if not result_url:
                        raise Exception(f"Motion task completed but video URL missing: {data}")
                    return result_url

                if status in ("FAILED", "CANCELLED", "ERROR"):
                    raise Exception(
                        data.get("message")
                        or data.get("error")
                        or data.get("details")
                        or f"Motion task failed with status {status}"
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

    mode_value = "1080p" if str(mode or SEEDANCE_MODE).lower() == "1080p" else "720p"
    duration = max(5, min(int(duration if duration is not None else SEEDANCE_DURATION), 10))
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
    if model_code == "seedance2":
        if "fast" in model_value_lower:
            model_value = "bytedance/seedance-2.0"
            model_value_lower = model_value.lower()
    elif model_code == "seedance2_fast":
        if "fast" not in model_value_lower:
            model_value = "bytedance/seedance-2.0-fast"
            model_value_lower = model_value.lower()
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

    model_value_lower = model_value.lower()

    prompt_text = (prompt or "").strip()
    if combined_image_urls:
        if not prompt_text:
            prompt_text = "Animate the provided photo naturally. Keep the same person, face, clothes, and background."
        if len(combined_image_urls) > 1 and SEEDANCE_VIDEO_REFERENCE_MODE == "timeline":
            prompt_text = (
                "Use the first uploaded image as the exact START frame and the second uploaded image as the exact END frame. "
                "Keep character identity consistent across the entire video: same face, body, hair, outfit, and style. "
                "Create smooth motion between these two frames without replacing characters. "
                + prompt_text
            )
        elif len(combined_image_urls) > 1:
            prompt_text = (
                "Use uploaded images as character references. Preserve identity exactly: same face, hair, body, outfit, and style. "
                "Do not swap or replace characters. Keep all key character traits consistent through the whole video. "
                + prompt_text
            )
    elif not prompt_text:
        prompt_text = "Create a natural cinematic video."

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
        }
    payload_variants = []
    if combined_image_urls:
        primary_image_url = combined_image_urls[0]
        if is_video_jobs_endpoint:
            refs_payload = [
                {
                    "type": "image_url",
                    "image_url": {"url": url},
                }
                for url in combined_image_urls
            ]

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
                payload_variants.append({**payload_base, "frame_images": frame_images, "aspect_ratio": "16:9"})
                payload_variants.append({**payload_base, "frame_images": frame_images})
            else:
                # Character-reference mode: use photo refs as identity anchors, not timeline endpoints.
                payload_variants.append({**payload_base, "input_references": refs_payload, "aspect_ratio": "16:9"})
                payload_variants.append({**payload_base, "input_references": refs_payload})
                payload_variants.append({**payload_base, "image_urls": combined_image_urls})

                # Compatibility fallback for gateways that prefer legacy nested format.
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
    async with aiohttp.ClientSession() as session:
        for create_url in create_urls:
            logger.info(f"Seedance create task endpoint: {create_url}")
            for payload in payload_variants:
                ref_keys = [k for k in ("frame_images", "input_references", "image_url", "image_urls", "reference_images") if k in payload]
                logger.info(
                    f"Seedance create payload: model={payload.get('model')}, model_code={model_code}, duration={payload.get('duration') or payload.get('seconds')}, refs={ref_keys}, refs_count={len(combined_image_urls)}"
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
                    logger.info(f"Seedance create response: status={resp.status}, endpoint={create_url}")
                    if not (200 <= resp.status < 300):
                        last_error = f"{resp.status}. {response_text}"
                        continue
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        last_error = f"Non-JSON response: {response_text}"
                        continue
                    task_id = data.get("id")
                    polling_url = data.get("polling_url")
                    if is_video_jobs_endpoint and isinstance(polling_url, str) and polling_url.strip():
                        logger.info(f"Seedance create accepted: polling_url={polling_url.strip()}")
                        return "__POLL_URL__:" + polling_url.strip()
                    if task_id:
                        logger.info(f"Seedance create accepted: task_id={task_id}")
                        return str(task_id)
                    last_error = f"Task id missing in response: {data}"

    raise Exception(f"Seedance create task error: {last_error}")


async def poll_seedance_task(task_id: str, max_attempts: int, poll_interval: int) -> str:
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
        f"Seedance polling started: task_ref={task_id}, max_attempts={max_attempts}, interval={poll_interval}s, urls={poll_urls}"
    )

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_attempts):
            logger.info(f"Seedance poll tick: attempt={attempt + 1}/{max_attempts}")
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
                                f"Seedance status check failed: {resp.status}, url={poll_url}, auth={'yes' if headers else 'no'}, body={response_text}"
                            )
                            continue
                        try:
                            data = json.loads(response_text)
                            break
                        except json.JSONDecodeError:
                            logger.warning(f"Seedance status non-JSON response: {response_text}")
                            continue
                if data:
                    break

            if not data:
                continue

            status_raw = str(data.get("status", ""))
            status = status_raw.upper()
            logger.info(f"Seedance task {task_id}: attempt={attempt + 1}/{max_attempts}, status={status}")

            if status in ("COMPLETED", "SUCCEEDED"):
                video_url = None
                unsigned_urls = data.get("unsigned_urls")
                if isinstance(unsigned_urls, list):
                    for item in unsigned_urls:
                        if isinstance(item, str) and item.startswith("http"):
                            video_url = item
                            break
                if not video_url:
                    video_url = extract_task_video_url(data)
                if not video_url:
                    raise Exception(f"Seedance task completed but video URL missing: {data}")
                return video_url

            if status in ("FAILED", "CANCELLED", "ERROR"):
                raise Exception(
                    data.get("error")
                    or data.get("message")
                    or data.get("error")
                    or data.get("details")
                    or f"Seedance task failed with status {status}"
                )

    raise Exception("Превышено время ожидания генерации видео Seedance")


async def validate_image_url(image_url: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                image_url,
                timeout=aiohttp.ClientTimeout(total=30),
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
    headers_variants = [None, auth_headers]

    last_error = "unknown"
    async with aiohttp.ClientSession() as session:
        for candidate_url in candidate_urls:
            for headers in headers_variants:
                try:
                    logger.info(
                        f"Seedance download attempt: url={candidate_url}, auth={'yes' if headers else 'no'}"
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
                            f"Seedance download failed: status={resp.status}, url={candidate_url}, auth={'yes' if headers else 'no'}"
                        )
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        f"Seedance download exception: url={candidate_url}, auth={'yes' if headers else 'no'}, error={e}"
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
    user = update.effective_user
    create_user_if_not_exists(user.id, user.username, START_BONUS)
    reply_target = update.callback_query.message if update.callback_query else update.message
    state = get_or_init_state(context)

    if not is_admin(user.id):
        await reply_target.reply_text("Эта функция пока доступна только администратору.")
        return

    if not SEEDANCE_ENABLED:
        await reply_target.reply_text(motion_unavailable_text(), reply_markup=main_menu_kb())
        return

    if user.id in queued_user_ids or user.id in processing_user_ids:
        await reply_target.reply_text(
            "Сейчас уже выполняется другая твоя задача. Дождись результата и запусти снова."
        )
        return

    motion_images = get_motion_image_urls(state)
    if not motion_images:
        last_image = last_generated_image_url.get(user.id)
        if isinstance(last_image, str) and last_image.strip():
            add_motion_image_url(state, last_image)
            motion_images = get_motion_image_urls(state)

    prompt_text = (state.motion_prompt or "").strip()
    if not motion_images and not prompt_text:
        await reply_target.reply_text(
            "Для Seedance добавь изображение и/или промпт, затем запусти снова."
        )
        return

    for idx, img_url in enumerate(motion_images, start=1):
        ok_img, reason_img = await validate_image_url(img_url)
        if not ok_img:
            await reply_target.reply_text(f"Фото-референс #{idx} недоступен: {reason_img}")
            return

    selected_duration = get_selected_seedance_duration(state)
    selected_model = get_motion_model(state)
    selected_model_label = get_motion_model_label(selected_model)
    selected_cps = get_motion_model_cost_per_second(selected_model)
    selected_cost = calc_seedance_cost(selected_duration, selected_cps)
    selected_endpoint = SEEDANCE_FAST_ENDPOINT if selected_model == "seedance2_fast" else SEEDANCE_ENDPOINT
    selected_mode = SEEDANCE_FAST_MODE if selected_model == "seedance2_fast" else SEEDANCE_MODE
    selected_model_slug = SEEDANCE_FAST_MODEL if selected_model == "seedance2_fast" else SEEDANCE_MODEL

    bal = get_balance(user.id)
    if bal < selected_cost:
        await reply_target.reply_text(
            f"Не хватает изюминок.\nНужно: {selected_cost}\nУ тебя: {bal}\n\nНапиши /buy."
        )
        return

    if not spend_izyminki(user.id, selected_cost):
        await reply_target.reply_text("Не удалось списать изюминки. Попробуй ещё раз.")
        return

    eta_min = max(2, int(selected_duration * 0.8))
    eta_max = max(eta_min + 1, int(selected_duration * 2.0))

    processing_user_ids.add(user.id)
    try:
        await reply_target.reply_text(
            f"Запускаю {selected_model_label} 🎬\n"
            f"Обычно это занимает {eta_min}–{eta_max} минут."
        )
        task_id = await start_seedance_task(
            prompt=prompt_text,
            image_url=motion_images[0] if motion_images else None,
            image_urls=motion_images,
            user_id=user.id,
            duration=selected_duration,
            endpoint=selected_endpoint,
            mode=selected_mode,
            model_slug=selected_model_slug,
            model_code=selected_model,
        )

        video_url = await poll_seedance_task(
            task_id=task_id,
            max_attempts=SEEDANCE_MAX_POLL_ATTEMPTS,
            poll_interval=SEEDANCE_POLL_INTERVAL,
        )
        video_bytes = await download_video_bytes_with_fallback(video_url)
        saved_path = save_video_debug_copy(video_bytes, user.id, selected_model_label)
        if saved_path:
            logger.info(f"Seedance local copy saved: {saved_path}")

        if False:
            async with aiohttp.ClientSession() as session: pass
            async with session.get(
                video_url,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Не удалось скачать видео: {resp.status}")
                video_bytes = await resp.read()

        video_buffer = io.BytesIO(video_bytes)
        video_buffer.name = "seedance.mp4"

        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_buffer,
            supports_streaming=True,
            caption=f"Готово 🎬\n{selected_model_label} завершён.",
        )
        log_generation_event(
            user_id=user.id,
            kind="motion",
            status="success",
            provider="ZVENO",
            cost=selected_cost,
            was_free=False,
            references_count=len(motion_images),
        )
    except Exception as e:
        logger.exception("Seedance generation failed")
        add_izyminki(user.id, selected_cost)
        log_generation_event(
            user_id=user.id,
            kind="motion",
            status="failed",
            provider="ZVENO",
            cost=selected_cost,
            was_free=False,
            references_count=len(motion_images),
        )
        await reply_target.reply_text(
            f"Не удалось выполнить {selected_model_label}.\n"
            "Временный технический сбой. Попробуй еще раз через минуту.\n\n"
            "Списанные изюминки возвращены на баланс."
        )
        await reply_target.reply_text(
            "Попробовать еще раз?",
            reply_markup=seedance_retry_kb(),
        )
    finally:
        processing_user_ids.discard(user.id)

async def send_generation_result_by_url(
    app: Application,
    chat_id: int,
    user_id: int,
    image_url: str,
) -> None:
    if image_url:
        last_generated_image_url[user_id] = image_url

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

    await app.bot.send_photo(
        chat_id=chat_id,
        photo=photo_buffer,
        reply_markup=result_actions_kb(),
        caption="Лови своё крутое изображение 🔥\nНажми /start чтобы начать сначала"
    )

    await app.bot.send_document(
        chat_id=chat_id,
        document=doc_buffer,
        caption="Файл изображения в хорошем качестве JPG."
    )

async def generate_image_by_job(app: Application, job: GenerationJob) -> None:
    chat_id = job.chat_id
    user_id = job.user_id
    prompt = job.prompt
    references = job.references

    refunded = False
    last_error_text = "Неизвестная ошибка"

    await app.bot.send_message(
        chat_id=chat_id,
        text="Сырник шаманит пиксели ✨"
    )

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
                                if isinstance(url, str) and url.strip():
                                    return url
                            elif isinstance(image_item, str) and image_item.strip():
                                return image_item

                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content
                    if isinstance(content, list):
                        for part in content:
                            if not isinstance(part, dict):
                                continue
                            image_url = part.get("image_url")
                            if isinstance(image_url, dict):
                                url = image_url.get("url")
                                if isinstance(url, str) and url.strip():
                                    return url
                            elif isinstance(image_url, str) and image_url.strip():
                                return image_url
                            url = part.get("url")
                            if isinstance(url, str) and url.strip():
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

            user_content = []
            if prompt and prompt.strip():
                user_content.append({"type": "text", "text": prompt})
            for ref_url in (references or [])[:8]:
                if isinstance(ref_url, str) and ref_url.startswith("http"):
                    user_content.append({"type": "image_url", "image_url": {"url": ref_url}})

            payload = {
                "model": ZVENO_IMAGE_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": user_content if user_content else prompt,
                    }
                ],
                "modalities": ["image", "text"],
                "image_config": {"aspect_ratio": "9:16"},
            }

            request_url = build_zveno_url(ZVENO_API_BASE, "/v1/chat/completions")
            logger.info(f"Zveno image endpoint: {request_url}")

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
                    response_text = await resp.text()
                    if not (200 <= resp.status < 300):
                        raise Exception(f"Zveno image error: {resp.status}. {response_text}")
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        raise Exception(f"Zveno non-JSON response: {response_text}")

            image_url = extract_zveno_image_url(response_data)
            if image_url and image_url.startswith("data:image"):
                comma_idx = image_url.find(",")
                if comma_idx != -1:
                    try:
                        raw_bytes = base64.b64decode(image_url[comma_idx + 1:])
                        uploaded_url = await upload_image_bytes_to_imgbb(raw_bytes, filename="zveno_result.jpg")
                        if uploaded_url:
                            image_url = uploaded_url
                        else:
                            image_url = None
                    except Exception:
                        image_url = None
            if not image_url:
                image_bytes = extract_zveno_image_bytes(response_data)
                if image_bytes:
                    image_url = await upload_image_bytes_to_imgbb(image_bytes, filename="zveno_result.jpg")
            if not image_url:
                raise Exception(extract_zveno_error_text(response_data))

            last_generated_prompt[user_id] = prompt
            add_generation_history(user_id=user_id, prompt=prompt, image_url=image_url)
            await send_generation_result_by_url(app, chat_id, user_id, image_url)
            log_generation_event(
                user_id=user_id,
                kind="image",
                status="success",
                provider="ZVENO",
                cost=getattr(job, "cost", 0),
                was_free=getattr(job, "was_free", False),
                references_count=len(references or []),
            )
            return
        except Exception as e:
            last_error_text = str(e) or repr(e)
            logger.exception("Zveno generation failed")
            logger.error(f"Generation debug | provider=ZVENO | user_id={user_id} | error={last_error_text}")

            if getattr(job, "cost", 0) > 0 and not refunded:
                add_izyminki(job.user_id, job.cost)
                refunded = True

            await app.bot.send_message(
                chat_id=chat_id,
                text=generation_failure_user_text(refunded),
                reply_markup=result_actions_kb(),
            )
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
                payload["imageUrls"] = references[:8]
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
                            last_generated_prompt[user_id] = prompt
                            add_generation_history(user_id=user_id, prompt=prompt, image_url=image_url)
                            await send_generation_result_by_url(app, chat_id, user_id, image_url)
                            log_generation_event(
                                user_id=user_id,
                                kind="image",
                                status="success",
                                provider="MASHAGPT",
                                cost=getattr(job, "cost", 0),
                                was_free=getattr(job, "was_free", False),
                                references_count=len(references or []),
                            )
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

            if getattr(job, "cost", 0) > 0 and not refunded:
                add_izyminki(job.user_id, job.cost)
                refunded = True

            await app.bot.send_message(
                chat_id=chat_id,
                text=generation_failure_user_text(refunded),
                reply_markup=result_actions_kb(),
            )
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
                    "references_urls": references,
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
                                    last_generated_image_url[user_id] = image_url
                                    last_generated_prompt[user_id] = prompt
                                    add_generation_history(user_id=user_id, prompt=prompt, image_url=image_url)
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

                                await app.bot.send_photo(
                                    chat_id=chat_id,
                                    photo=photo_buffer,
                                    reply_markup=result_actions_kb(),
                                    caption="Лови своё крутое изображение 🔥\nНажми /start чтобы начать сначала"
                                )

                                await app.bot.send_document(
                                    chat_id=chat_id,
                                    document=doc_buffer,
                                    caption="Файл изображения в хорошем качестве JPG."
                                )
                                log_generation_event(
                                    user_id=user_id,
                                    kind="image",
                                    status="success",
                                    provider="YESAPI",
                                    cost=getattr(job, "cost", 0),
                                    was_free=getattr(job, "was_free", False),
                                    references_count=len(references or []),
                                )
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

def main():
    init_db()

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("ref", referral))
    app.add_handler(CommandHandler("report", report_problem_command))
    app.add_handler(CommandHandler("ai", ai_chat))
    app.add_handler(CommandHandler("admin_add", admin_add))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("broadcast_promo", broadcast_promo))
    app.add_handler(CommandHandler("broadcast", broadcast_text))
    app.add_handler(CommandHandler("broadcast_text", broadcast_text))
    app.add_handler(CommandHandler("audience_stats", audience_stats))
    app.add_handler(CommandHandler("pl_save", prompt_library_save_last))
    app.add_handler(CommandHandler("pl_import", prompt_library_import_from_reply))
    app.add_handler(CommandHandler("pl_newcat", prompt_library_new_category))
    app.add_handler(CommandHandler("pl_renamecat", prompt_library_rename_category))
    app.add_handler(CommandHandler("pl_delcat", prompt_library_delete_category))
    app.add_handler(CommandHandler("pl_admin", prompt_library_admin_help))
    app.add_handler(CommandHandler("pl_list", prompt_library_list))
    app.add_handler(CommandHandler("pl_history", prompt_library_history_command))
    app.add_handler(CommandHandler("pl_export", prompt_library_export))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data_v2))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CommandHandler("promo_stats", promo_stats))
    app.add_error_handler(error_handler)

    logger.info("Бот запускается...")
    app.run_polling()


if __name__ == "__main__":
    main()
