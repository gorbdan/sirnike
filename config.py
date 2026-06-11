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

PROMPT_WEBAPP_URL = os.getenv("PROMPT_WEBAPP_URL", "").strip()
# Только стабильный домен: адреса вида https://<hash>.sirnike.pages.dev — снимок
# одного деплоя, они никогда не обновляются
PROMPT_LIBRARY_REMOTE_URL = os.getenv("PROMPT_LIBRARY_REMOTE_URL", "https://sirnike.pages.dev/prompt_library.json").strip()

REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY", "").strip()
PHOTOROOM_API_KEY = os.getenv("PHOTOROOM_API_KEY", "").strip()
FAPIHUB_API_KEY = os.getenv("FAPIHUB_API_KEY", "").strip()
CLIPDROP_API_KEY = os.getenv("CLIPDROP_API_KEY", "").strip()
# Local rembg fallback: needs ~500MB RAM for U2Net model.
# Enabled by default after BotHost RAM upgrade. Set REMBG_LOCAL_ENABLED=0 to disable.
REMBG_LOCAL_ENABLED = os.getenv("REMBG_LOCAL_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")

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
KLING3_DURATION_OPTIONS = os.getenv("KLING3_DURATION_OPTIONS", "5,10,15")

# Veo 3.1 Fast (Google) через Zveno Videos API. Только 4/6/8 секунд, 720p, 16:9 или 9:16.
# Закупка Zveno: 12.21 руб/сек (без аудио) — тариф 8.0 изюм/сек, маржа ~x3.3.
VEO31_ENABLED = os.getenv("VEO31_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
VEO31_MODEL = os.getenv("VEO31_MODEL", "google/veo-3.1-fast")
VEO31_COST_PER_SECOND = float(os.getenv("VEO31_COST_PER_SECOND", "8.0"))
VEO31_DURATION_OPTIONS = os.getenv("VEO31_DURATION_OPTIONS", "4,6,8")

if AI_PROVIDER == "ZVENO" and not ZVENO_API_KEY:
    raise RuntimeError("Missing required environment variable for ZVENO: ZVENO_API_KEY")

START_BONUS = int(os.getenv("START_BONUS", "5"))
REFERRAL_BONUS_REFERRER = int(os.getenv("REFERRAL_BONUS_REFERRER", "10"))
REFERRAL_BONUS_NEW_USER = int(os.getenv("REFERRAL_BONUS_NEW_USER", "5"))

FREE_GENERATIONS_PER_DAY = int(os.getenv("FREE_GENERATIONS_PER_DAY", "1"))
BASE_GENERATION_COST = int(os.getenv("BASE_GENERATION_COST", "5"))
REFERENCE_COST = int(os.getenv("REFERENCE_COST", "0"))

# GPT-5 Image (OpenAI) через Zveno — альтернатива Gemini для генерации картинок.
# Закупка Zveno: 1.79/7.03 руб за 1k токенов (in/out) ≈ 12-30 руб за картинку —
# при 5 изюминках маржа около нуля, поэтому дефолт 2x от базовой цены.
GPT5_IMAGE_ENABLED = os.getenv("GPT5_IMAGE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
ZVENO_GPT5_IMAGE_MODEL = os.getenv("ZVENO_GPT5_IMAGE_MODEL", "openai/gpt-5-image")
GPT5_IMAGE_COST = int(os.getenv("GPT5_IMAGE_COST", str(BASE_GENERATION_COST * 2)))

MAX_POLL_ATTEMPTS = int(os.getenv("MAX_POLL_ATTEMPTS", "30"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

BUY_PACKS = [
    {"count": 10, "price": 60},
    {"count": 20, "price": 100},
    {"count": 50, "price": 250},
    {"count": 120, "price": 600},
    {"count": 300, "price": 1500},
]

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "320423776").split(",") if x.strip()]
RESULTS_CHANNEL_ID = os.getenv("RESULTS_CHANNEL_ID", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "gorbdan/sirnike").strip()

TEST_MODE = os.getenv("TEST_MODE", "0").strip().lower() in ("1", "true", "yes", "on")
