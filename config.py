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
GEMINI_OMNI_MODEL = os.getenv("GEMINI_OMNI_MODEL", "gemini-omni-flash-image-to-video")
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

TEST_MODE = os.getenv("TEST_MODE", "0").strip().lower() in ("1", "true", "yes", "on")
