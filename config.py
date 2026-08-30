import os


def _load_env_file() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
        return
    except ImportError:
        pass

    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                # .env should win over stale shell/session variables for predictable local runs.
                os.environ[key] = value


_load_env_file()

BASE_DIR = os.path.dirname(__file__)
DEFAULT_DATA_DIR = "/app/data" if (os.name != "nt" and os.path.isdir("/app/data")) else BASE_DIR
DATA_DIR = os.getenv("DATA_DIR", DEFAULT_DATA_DIR).strip() or DEFAULT_DATA_DIR


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


TOKEN = _required_env("BOT_TOKEN")

AI_PROVIDER = os.getenv("AI_PROVIDER", "YESAPI").upper()

NANO_API_BASE = os.getenv("NANO_API_BASE", "https://api.yesai.su/v2/google/nanobanana")
NANO_API_KEY = os.getenv("NANO_API_KEY", "")
if AI_PROVIDER == "YESAPI" and not NANO_API_KEY:
    raise RuntimeError("Missing required environment variable for YESAPI: NANO_API_KEY")

MASHAGPT_API_BASE = os.getenv("MASHAGPT_API_BASE", "https://api.mashagpt.ru")
MASHAGPT_API_KEY = os.getenv("MASHAGPT_API_KEY", "")
MASHAGPT_IMAGE_MODEL = os.getenv("MASHAGPT_IMAGE_MODEL", "nano-banana-pro")
MASHAGPT_CHAT_MODEL = os.getenv("MASHAGPT_CHAT_MODEL", "gpt-4o-mini")
ZVENO_API_BASE = os.getenv("ZVENO_API_BASE", "https://api.zveno.ai/v1")
ZVENO_API_KEY = os.getenv("ZVENO_API_KEY", "")
# Nano Banana 2: качество уровня Pro при цене в ~8 раз ниже (0.055/0.27 руб за 1k vs 0.36/2.12 у Pro).
ZVENO_IMAGE_MODEL = os.getenv("ZVENO_IMAGE_MODEL", "google/gemini-3.1-flash-image-preview")
ZVENO_CHAT_MODEL = os.getenv("ZVENO_CHAT_MODEL", "google/gemini-2.5-flash")

# EvoLink — новый провайдер видео (см. docs/specs/2026-07-31_evolink_video_provider.md).
# Заблокировано ключом (Аня заводит аккаунт) — EVOLINK_API_KEY пуст до выдачи ключа,
# реальный HTTP-клиент ещё не написан (см. SirNike.py: start_seedance_task_evolink).
EVOLINK_API_BASE = os.getenv("EVOLINK_API_BASE", "https://api.evolink.ai/v1")
EVOLINK_API_KEY = os.getenv("EVOLINK_API_KEY", "")
# "zveno" | "evolink" — переключатель провайдера ТОЛЬКО для Seedance 2.0/2.0-fast.
# Дефолт "zveno" — путь отката без редеплоя логики, одна env-переменная.
SEEDANCE_PROVIDER = os.getenv("SEEDANCE_PROVIDER", "zveno").strip().lower()

# "mashagpt" | "evolink" — переключатель провайдера для Kling Motion Control,
# НЕЗАВИСИМЫЙ от SEEDANCE_PROVIDER (разные продукты, разные эндпоинты/модели).
# MOTION_CONTROL_ENABLED остаётся выключенным по умолчанию вне зависимости от
# этого флага — фича ещё не готова к продакшену в принципе (см. ТЗ EvoLink).
MOTION_CONTROL_PROVIDER = os.getenv("MOTION_CONTROL_PROVIDER", "mashagpt").strip().lower()

# «Детектор лиц» — сетка-оверлей поверх фото-рефов Seedance. Ломает детектор
# реальных лиц у ByteDance (Seedance режет фотографии живых людей как «real
# person»). Сетка заметно портит кадр, поэтому вынесена в вариант и по умолчанию
# ВЫКЛЮЧЕНА: фото уходит в Seedance как есть, без сетки. Включить обратно (если
# модерация снова начнёт резать реальные лица) — одной env-переменной без
# редеплоя логики: SEEDANCE_FACE_GRID=on|1|true|yes. Флаг не касается
# Kling/Veo/Wan/Gemini Omni — у них другой (не ByteDance) детектор.
SEEDANCE_FACE_GRID = os.getenv("SEEDANCE_FACE_GRID", "0").strip().lower() in ("1", "true", "yes", "on")

# Gemini Omni Flash (EvoLink) — новый продукт, которого нет у Zveno/MashaGPT.
# Выключен по умолчанию до ручного ревью качества генераций Аней/маркетологом
# (ТЗ EvoLink, п.2 порядка работ: «не продолжать без ок»).
GEMINI_OMNI_ENABLED = os.getenv("GEMINI_OMNI_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
# reference-to-video, НЕ image-to-video: у EvoLink это два разных API для
# Gemini Omni (как и для Seedance) — image-to-video берёт строго 1 фото,
# reference-to-video — до 6 (живой прод 2026-08-02: тот же класс бага, что
# уже чинили для Seedance, см. GEMINI_OMNI_MAX_IMAGES в video_providers.py).
GEMINI_OMNI_MODEL = os.getenv("GEMINI_OMNI_MODEL", "gemini-omni-flash-reference-to-video")
GEMINI_OMNI_DURATION = int(os.getenv("GEMINI_OMNI_DURATION", "10"))
GEMINI_OMNI_DURATION_OPTIONS = os.getenv("GEMINI_OMNI_DURATION_OPTIONS", "5,8,10")
# Ориентир ≈7.8 ₽/сек (курс ~90₽/$, публичная страница EvoLink на 2026-07-31,
# НЕ реальный биллинг) × маржа ~3.3 (как у остальных видео-моделей) / ~5 ₽ за
# изюминку ≈ 5.1 изюм/сек. TODO: сверить по первому реальному счёту EvoLink —
# calc_seedance_cost НЕ менять, это отдельная задача после счёта.
GEMINI_OMNI_COST_PER_SECOND = float(os.getenv("GEMINI_OMNI_COST_PER_SECOND", "5.1"))

PROMPT_WEBAPP_URL = os.getenv("PROMPT_WEBAPP_URL", "").strip()
# Только стабильный домен: адреса вида https://<hash>.sirnike.pages.dev — снимок
# одного деплоя, они никогда не обновляются
PROMPT_LIBRARY_REMOTE_URL = os.getenv("PROMPT_LIBRARY_REMOTE_URL", "https://sirnike.pages.dev/prompt_library.json").strip()

REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY", "").strip()
PHOTOROOM_API_KEY = os.getenv("PHOTOROOM_API_KEY", "").strip()
FAPIHUB_API_KEY = os.getenv("FAPIHUB_API_KEY", "").strip()
CLIPDROP_API_KEY = os.getenv("CLIPDROP_API_KEY", "").strip()
# Local rembg fallback: needs ~500MB RAM for U2Net model.
# Disabled — bg removal made faces detect more easily and failed Seedance
# moderation. Set REMBG_LOCAL_ENABLED=1 only if re-enabling bg removal.
REMBG_LOCAL_ENABLED = os.getenv("REMBG_LOCAL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")

FAL_API_KEY = os.getenv("FAL_API_KEY", "").strip()
FAL_API_BASE = os.getenv("FAL_API_BASE", "https://queue.fal.run").strip()

IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "").strip()
PROVIDER_TOKEN = _required_env("PROVIDER_TOKEN")

KLING_API_BASE = os.getenv("KLING_API_BASE", "https://api.yesai.su/v2/yesvideo")
KLING_VERSION = os.getenv("KLING_VERSION", "1.6")
KLING_DURATION = os.getenv("KLING_DURATION", "10")
KLING_DIMENSIONS = os.getenv("KLING_DIMENSIONS", "16:9")
KLING_VIDEO_COST = int(os.getenv("KLING_VIDEO_COST", "5"))
KLING_MAX_POLL_ATTEMPTS = int(os.getenv("KLING_MAX_POLL_ATTEMPTS", "80"))
KLING_POLL_INTERVAL = int(os.getenv("KLING_POLL_INTERVAL", "15"))
KLING_MOTION_ENDPOINT = os.getenv("KLING_MOTION_ENDPOINT", "/v1/tasks/kling-2-6-motion-control")
KLING_MOTION_VERSION = os.getenv("KLING_MOTION_VERSION", "2.6-pro")
KLING_MOTION_COST = int(os.getenv("KLING_MOTION_COST", str(KLING_VIDEO_COST)))
KLING_MOTION_MODE = os.getenv("KLING_MOTION_MODE", "720p")
KLING_MOTION_ORIENTATION = os.getenv("KLING_MOTION_ORIENTATION", "video")
KLING_MOTION_DURATION = int(os.getenv("KLING_MOTION_DURATION", "10"))
KLING_MOTION_MAX_POLL_ATTEMPTS = int(
    os.getenv("KLING_MOTION_MAX_POLL_ATTEMPTS", str(KLING_MAX_POLL_ATTEMPTS))
)
KLING_MOTION_POLL_INTERVAL = int(
    os.getenv("KLING_MOTION_POLL_INTERVAL", str(KLING_POLL_INTERVAL))
)
MOTION_CONTROL_ENABLED = os.getenv("MOTION_CONTROL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
SEEDANCE_ENDPOINT = os.getenv("SEEDANCE_ENDPOINT", "/v1/videos")
SEEDANCE_MODEL = os.getenv("SEEDANCE_MODEL", "bytedance/seedance-2.0")
SEEDANCE_COST = int(os.getenv("SEEDANCE_COST", str(KLING_VIDEO_COST)))
SEEDANCE_MODE = os.getenv("SEEDANCE_MODE", "720p")
SEEDANCE_DURATION = int(os.getenv("SEEDANCE_DURATION", "5"))
SEEDANCE_DURATION_OPTIONS = os.getenv("SEEDANCE_DURATION_OPTIONS", "5,10,15")
SEEDANCE_FAST_DURATION_OPTIONS = os.getenv("SEEDANCE_FAST_DURATION_OPTIONS", "5,10,15")
SEEDANCE_COST_PER_SECOND = float(
    os.getenv(
        "SEEDANCE_COST_PER_SECOND",
        "6.75",
    )
)
SEEDANCE_MAX_POLL_ATTEMPTS = int(
    os.getenv("SEEDANCE_MAX_POLL_ATTEMPTS", str(KLING_MAX_POLL_ATTEMPTS))
)
SEEDANCE_POLL_INTERVAL = int(
    os.getenv("SEEDANCE_POLL_INTERVAL", str(KLING_POLL_INTERVAL))
)
# Max seconds to spend polling per attempt before declaring timeout.
# Default: 25 min so 15-second videos (which can take 20+ min) don't time out prematurely.
SEEDANCE_ATTEMPT_TIMEOUT_SECONDS = int(
    os.getenv("SEEDANCE_ATTEMPT_TIMEOUT_SECONDS", str(25 * 60))
)
SEEDANCE_ENABLED = os.getenv("SEEDANCE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
SEEDANCE_FAST_ENABLED = os.getenv("SEEDANCE_FAST_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
SEEDANCE_FAST_ENDPOINT = os.getenv("SEEDANCE_FAST_ENDPOINT", "/v1/videos")
SEEDANCE_FAST_MODEL = os.getenv("SEEDANCE_FAST_MODEL", "bytedance/seedance-2.0-fast")
SEEDANCE_FAST_MODE = os.getenv("SEEDANCE_FAST_MODE", "720p")
SEEDANCE_FAST_COST_PER_SECOND = float(
    os.getenv("SEEDANCE_FAST_COST_PER_SECOND", "5.4")
)
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

# Kling 3.0 (kwaivgi) через Zveno Videos API — те же эндпоинты, что Seedance.
# Закупка Zveno: 12.10 руб/сек (zveno.ai/models, 2026-06-11) — тариф 8.0 изюм/сек даёт маржу ~x3.3 как у Seedance.
KLING3_ENABLED = os.getenv("KLING3_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
KLING3_MODEL = os.getenv("KLING3_MODEL", "kwaivgi/kling-v3.0-std")
KLING3_COST_PER_SECOND = float(os.getenv("KLING3_COST_PER_SECOND", "8.0"))
KLING3_DURATION_OPTIONS = os.getenv("KLING3_DURATION_OPTIONS", "3,5,10,15")

# Veo 3.1 Fast (Google) через Zveno Videos API. Только 4/6/8 секунд, 720p, 16:9 или 9:16.
# Закупка Zveno: 12.21 руб/сек (без аудио) — тариф 8.0 изюм/сек, маржа ~x3.3.
VEO31_ENABLED = os.getenv("VEO31_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
VEO31_MODEL = os.getenv("VEO31_MODEL", "google/veo-3.1-fast")
VEO31_COST_PER_SECOND = float(os.getenv("VEO31_COST_PER_SECOND", "8.0"))
VEO31_DURATION_OPTIONS = os.getenv("VEO31_DURATION_OPTIONS", "4,6,8")

# Wan 2.7 (Alibaba) через Zveno Videos API — text-to-video и image/reference-to-video,
# 2-10 секунд, 480p/720p, 16:9 или 9:16 (проверено GET /v1/videos/models, 2026-07-08).
# Закупка Zveno: 16.21 руб/сек — тариф 10.0 изюм/сек, маржа ~x3.3 как у Kling/Veo.
WAN27_ENABLED = os.getenv("WAN27_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
WAN27_MODEL = os.getenv("WAN27_MODEL", "alibaba/wan-2.7")
WAN27_COST_PER_SECOND = float(os.getenv("WAN27_COST_PER_SECOND", "10.0"))
WAN27_DURATION_OPTIONS = os.getenv("WAN27_DURATION_OPTIONS", "5,10")

# Seedance 2.5 (ByteDance) через EvoLink — ВСЕГДА EvoLink, у Zveno этой модели
# нет (в отличие от seedance2/2_fast, у тех есть Zveno↔EvoLink переключатель
# SEEDANCE_PROVIDER — не путать). Отдельный премиум-продукт, НЕ подмена
# дефолтной Seedance 2.0: запрос партнёра-креатора (докладка от аналитика
# рынка, docs/ai-market/2026-08-08-creator-candidates.md), похожесть лица
# идентична 2.0, детектор реального лица ByteDance не блокирует. Live-тест
# Ани (плейграунд evolink.ai, БЕЗ ключа): reference-to-video 720p, 5с = $1.47
# = $0.294/сек = 26.46 ₽/сек закупка (льготного reference-тарифа у EvoLink
# НЕТ — совпало со "standard"). 480p — по прайсу, экстраполяция, не
# live-тестирован в reference-режиме. Тариф при марже x3.3 / 5₽ за изюминку:
# 480p ≈ 8 изюм/сек (+19% к текущей seedance2 6.75), 720p ≈ 18 изюм/сек
# (+160%) — оба качества доступны юзеру, не одно на выбор. TODO: сверить
# по первому реальному счёту EvoLink (±20%) перед включением флага.
SEEDANCE25_ENABLED = os.getenv("SEEDANCE25_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
# Живой прод-баг 2026-08-30: дефолт был "bytedance/seedance-2.5-reference-to-video"
# (Zveno-стиль слага с префиксом провайдера) — но эта модель ВСЕГДА идёт
# через EvoLink (start_seedance25_task_evolink), а EvoLink отвечал 404
# model_not_found на каждый вызов ("did_you_mean: seedance-2.5-reference-to-video"),
# 100% отказ для всех юзеров этой функции. У EvoLink слаги без префикса
# провайдера — тот же принцип, что EVOLINK_SEEDANCE_MODEL_MAP для 2.0.
SEEDANCE25_MODEL = os.getenv("SEEDANCE25_MODEL", "seedance-2.5-reference-to-video")
SEEDANCE25_MODE = os.getenv("SEEDANCE25_MODE", "480p")
SEEDANCE25_DURATION = int(os.getenv("SEEDANCE25_DURATION", "5"))
# Нативно до 30 сек ОДНИМ вызовом (у 2.0 через Zveno потолок 15с у любого
# провайдера, см. AGENT_NOTES.md 2026-07-08) — частично перекрывает
# «склейку клипов для нейромультика» для роликов ≤30с.
SEEDANCE25_DURATION_OPTIONS = os.getenv("SEEDANCE25_DURATION_OPTIONS", "5,10,15,30")
SEEDANCE25_COST_PER_SECOND_480P = float(os.getenv("SEEDANCE25_COST_PER_SECOND_480P", "8.0"))
SEEDANCE25_COST_PER_SECOND_720P = float(os.getenv("SEEDANCE25_COST_PER_SECOND_720P", "18.0"))
# До 50 референсов на вход (у обычной Seedance — 9, MAX_SEEDANCE_IMAGE_REFERENCES).
SEEDANCE25_MAX_IMAGES = int(os.getenv("SEEDANCE25_MAX_IMAGES", "50"))

# Хаб генерации в вебаппе (docs/specs/2026-08-13_webapp_generation_hub.md) —
# MVP: экран «Конструктор» для видео вместо чат-пикера модели/панели.
# Kill-switch: выключено — вход «🎬 Видео для Reels» ведёт на старый
# video_model_picker_kb() без единого изменения поведения.
VIDEO_CONSTRUCTOR_ENABLED = os.getenv("VIDEO_CONSTRUCTOR_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
# Full: аналогичные конструкторы для Midjourney/Аватара/обычного фото —
# независимые kill-switch'и, чтобы включать по одному продукту, не всё сразу.
MIDJOURNEY_CONSTRUCTOR_ENABLED = os.getenv("MIDJOURNEY_CONSTRUCTOR_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
AVATAR_CONSTRUCTOR_ENABLED = os.getenv("AVATAR_CONSTRUCTOR_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
PHOTO_CONSTRUCTOR_ENABLED = os.getenv("PHOTO_CONSTRUCTOR_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
# «Улучшить фото» в вебапп-хабе (docs/specs/2026-08-14_menu_simplification_and_enhance_constructor.md) —
# простейший из конструкторов: одно фото, без текстовых полей, фиксированный
# промт/модель. Тот же kill-switch-принцип — выключено не крэшит, а честно отказывает.
ENHANCE_CONSTRUCTOR_ENABLED = os.getenv("ENHANCE_CONSTRUCTOR_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")

if AI_PROVIDER == "ZVENO" and not ZVENO_API_KEY:
    raise RuntimeError("Missing required environment variable for ZVENO: ZVENO_API_KEY")

START_BONUS = int(os.getenv("START_BONUS", "5"))
REFERRAL_BONUS_REFERRER = int(os.getenv("REFERRAL_BONUS_REFERRER", "10"))
REFERRAL_BONUS_NEW_USER = int(os.getenv("REFERRAL_BONUS_NEW_USER", "5"))
BUG_BOUNTY_REWARD = int(os.getenv("BUG_BOUNTY_REWARD", "5"))

FREE_GENERATIONS_PER_DAY = int(os.getenv("FREE_GENERATIONS_PER_DAY", "0"))
BASE_GENERATION_COST = int(os.getenv("BASE_GENERATION_COST", "5"))
REFERENCE_COST = int(os.getenv("REFERENCE_COST", "0"))

# GPT-5 Image (OpenAI) через Zveno — альтернатива Gemini для генерации картинок.
# Закупка Zveno: 1.79/7.03 руб за 1k токенов (in/out) ≈ 12-30 руб за картинку.
# При реализованной цене ~5 ₽/изюминку 10 изюминок (50 ₽) давали маржу около нуля
# на дорогих картинках. Дефолт 25 изюминок (~125 ₽) = премиум-фото с нормальной маржой.
GPT5_IMAGE_ENABLED = os.getenv("GPT5_IMAGE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
ZVENO_GPT5_IMAGE_MODEL = os.getenv("ZVENO_GPT5_IMAGE_MODEL", "openai/gpt-5-image")
GPT5_IMAGE_COST = int(os.getenv("GPT5_IMAGE_COST", "25"))

# Обе фото-модели (Nano Banana 2 и GPT Image) через EvoLink — полный отказ
# от Zveno как закупки для фото, решение Ани 2026-08-25/26 («Zveno больше
# не хочу оплачивать»). model id Nano Banana 2 на EvoLink совпадает с
# ZVENO_IMAGE_MODEL (та же апстрим-модель), но закупка ТАРИФИЦИРУЕТСЯ
# ИНАЧЕ: у Zveno — по токенам (копейки/картинку), у EvoLink — фиксированно
# за картинку по quality-тиру (~4.5₽/1K, ~6.9₽/2K, ~10.3₽/4K по курсу
# ~85 ₽/$, EvoLink-прайсинг 2026-08-25) — это НА ПОРЯДОК дороже нынешней
# закупки Zveno. У EvoLink НЕТ модели `gpt-5-image` — премиум-tier идёт на
# `gpt-image-2` (другая модель OpenAI-линейки, EvoLink billing токенный, как
# у самого OpenAI, ~$0.027/1k output-токенов картинки — по прикидке из
# доков сопоставимо или чуть выгоднее нынешней закупки Zveno на тире high,
# но НЕ проверено живым вызовом на промтах Сырника — качество/модерация под
# вопросом до первого реального теста). Дефолты BASE_GENERATION_COST=5 /
# GPT5_IMAGE_COST=25 изюминок НЕ пересчитаны под новую закупку — поднять
# отдельно через env (без редеплоя) по факту первых логов
# credits_reserved/usage. Выключено по умолчанию до ручного теста — тот же
# порядок раскатки, что у Midjourney/Kling/Seedance-EvoLink.
PHOTO_PROVIDER = os.getenv("PHOTO_PROVIDER", "zveno").strip().lower()
EVOLINK_IMAGE_MODEL = os.getenv("EVOLINK_IMAGE_MODEL", "gemini-3.1-flash-image-preview")
EVOLINK_IMAGE_QUALITY = os.getenv("EVOLINK_IMAGE_QUALITY", "1K")
# Премиум-tier (замена GPT-5 Image) — EvoLink называет её gpt-image-2, не
# gpt-5-image (той модели у них нет вообще). quality high по умолчанию —
# тот же принцип "премиум = максимальное качество", что был у Zveno-варианта.
EVOLINK_GPT_IMAGE_MODEL = os.getenv("EVOLINK_GPT_IMAGE_MODEL", "gpt-image-2")
EVOLINK_GPT_IMAGE_QUALITY = os.getenv("EVOLINK_GPT_IMAGE_QUALITY", "high")
EVOLINK_IMAGE_MAX_POLL_ATTEMPTS = int(os.getenv("EVOLINK_IMAGE_MAX_POLL_ATTEMPTS", "60"))
EVOLINK_IMAGE_POLL_INTERVAL = int(os.getenv("EVOLINK_IMAGE_POLL_INTERVAL", "3"))

# Midjourney через EvoLink (у Zveno этой модели нет — проверено по
# https://zveno.ai/models). Отдельный мини-флоу (не третий пункт обычного
# image_model-пикера): сетка 2×2 → юзер выбирает вариант → апскейл отдельным
# вызовом. Выключено по умолчанию до ручного теста качества Аней (тот же
# порядок раскатки, что был у EvoLink-видео). Цена — грубая прикидка по
# заявленному EvoLink биллингу (fast ≈ 1.8 кредита/вызов, апскейл — отдельный
# вызов) с той же целевой маржой x3.3, что у остальных моделей (см. комментарий
# BUY_PACKS выше) — ТРЕБУЕТ сверки по факту credits_reserved из первого
# реального лога перед включением флага, не полагаться на эту цифру вслепую.
MIDJOURNEY_ENABLED = os.getenv("MIDJOURNEY_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
MIDJOURNEY_MODEL = os.getenv("MIDJOURNEY_MODEL", "mj-v7")
MIDJOURNEY_UPSCALE_MODEL = os.getenv("MIDJOURNEY_UPSCALE_MODEL", "mj-v7-upscale")
MIDJOURNEY_SPEED = os.getenv("MIDJOURNEY_SPEED", "fast").strip().lower()
MIDJOURNEY_GRID_COST = int(os.getenv("MIDJOURNEY_GRID_COST", "15"))
MIDJOURNEY_UPSCALE_COST = int(os.getenv("MIDJOURNEY_UPSCALE_COST", "10"))
# Картинки генерируются быстрее видео — короче интервал/меньше попыток
# (60×5с = 5 мин максимум ожидания на фазу).
MIDJOURNEY_MAX_POLL_ATTEMPTS = int(os.getenv("MIDJOURNEY_MAX_POLL_ATTEMPTS", "60"))
MIDJOURNEY_POLL_INTERVAL = int(os.getenv("MIDJOURNEY_POLL_INTERVAL", "5"))

MAX_POLL_ATTEMPTS = int(os.getenv("MAX_POLL_ATTEMPTS", "30"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# Объёмная скидка: цена за изюминку падает 9→5 ₽ от мелкого пакета к крупному,
# чтобы был стимул брать больше (растит средний чек). Видео остаётся прибыльным
# на любом пакете: 8 изюм/сек × 5 ₽ = 40 ₽/сек выручки vs ~12 ₽/сек закупки = x3.3.
BUY_PACKS = [
    {"count": 10, "price": 90, "name": "Проба"},
    {"count": 30, "price": 240, "name": "Фотосессия"},
    {"count": 70, "price": 490, "name": "Контент-неделя"},
    {"count": 150, "price": 900, "name": "Про"},
    {"count": 350, "price": 1750, "name": "Студия"},
]

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "320423776").split(",") if x.strip()]
RESULTS_CHANNEL_ID = os.getenv("RESULTS_CHANNEL_ID", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "gorbdan/sirnike").strip()
# Репо вебаппа — публикация top_styles.json (docs/specs/2026-07-16_top_styles_stats_feed.md).
# ⚠️ Требует, чтобы GITHUB_TOKEN имел права записи и в этот репо (не только в GITHUB_REPO) —
# не проверено автоматически, подтвердить вручную перед первым релизом фичи.
WEBAPP_GITHUB_REPO = os.getenv("WEBAPP_GITHUB_REPO", "gorbdan/_webapp").strip()

# ── Студия нейромультиков (docs/specs/2026-07-20_cartoon_studio.md) ──
# Очередь заданий — в Cloudflare D1 при вебапе; бот поллит /api/studio/*.
# Пустой STUDIO_POLL_SECRET = студия выключена (поллер не стартует) — так фича
# безопасно деплоится до того, как Аня заведёт D1 и секреты в Cloudflare.
STUDIO_POLL_SECRET = os.getenv("STUDIO_POLL_SECRET", "").strip()
_default_studio_api = (PROMPT_WEBAPP_URL.rstrip("/") + "/api/studio") if PROMPT_WEBAPP_URL else ""
STUDIO_API_BASE = os.getenv("STUDIO_API_BASE", _default_studio_api).strip().rstrip("/")
STUDIO_ENABLED = bool(STUDIO_POLL_SECRET and STUDIO_API_BASE)
STUDIO_MAX_SCENES = int(os.getenv("STUDIO_MAX_SCENES", "5"))
STUDIO_POLL_INTERVAL = int(os.getenv("STUDIO_POLL_INTERVAL", "4"))
STUDIO_CONCURRENCY = int(os.getenv("STUDIO_CONCURRENCY", "3"))

# ── Живой прогресс генерации в вебаппе (docs/specs/2026-08-13_webapp_generation_hub_full.md) ──
# НЕ очередь (в отличие от Студии выше) — тонкое write-only зеркало статуса:
# бот сам инициирует и выполняет генерацию как сегодня (без D1 вообще), и
# ДОПОЛНИТЕЛЬНО пишет прогресс в отдельную таблицу generation_progress, пока
# юзер может смотреть его в вебаппе. Пустой секрет = фича выключена (тот же
# принцип безопасного деплоя до заведения Cloudflare-инфраструктуры, что и у
# Студии) — но, в отличие от Студии, есть ещё и отдельный явный kill-switch
# GEN_PROGRESS_ENABLED, потому что запись в D1 живёт ВНУТРИ уже работающего
# пути генерации (run_seedance), а не в отдельном поллере — на всякий случай
# должна быть возможность выключить её одним флагом, не трогая секрет.
GEN_PROGRESS_SECRET = os.getenv("GEN_PROGRESS_SECRET", "").strip()
_default_gen_progress_api = (PROMPT_WEBAPP_URL.rstrip("/") + "/api/progress") if PROMPT_WEBAPP_URL else ""
GEN_PROGRESS_API_BASE = os.getenv("GEN_PROGRESS_API_BASE", _default_gen_progress_api).strip().rstrip("/")
GEN_PROGRESS_ENABLED = (
    os.getenv("GEN_PROGRESS_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
    and bool(GEN_PROGRESS_SECRET and GEN_PROGRESS_API_BASE)
)

TEST_MODE = os.getenv("TEST_MODE", "0").strip().lower() in ("1", "true", "yes", "on")
