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
DATA_DIR = os.getenv("DATA_DIR", BASE_DIR).strip() or BASE_DIR


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
ZVENO_IMAGE_MODEL = os.getenv("ZVENO_IMAGE_MODEL", "google/gemini-3-pro-image-preview")
ZVENO_CHAT_MODEL = os.getenv("ZVENO_CHAT_MODEL", "google/gemini-2.5-flash")

PROMPT_WEBAPP_URL = os.getenv("PROMPT_WEBAPP_URL", "").strip()

IMGBB_API_KEY = _required_env("IMGBB_API_KEY")
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
SEEDANCE_FAST_DURATION_OPTIONS = os.getenv("SEEDANCE_FAST_DURATION_OPTIONS", "5,10")
SEEDANCE_COST_PER_SECOND = float(
    os.getenv(
        "SEEDANCE_COST_PER_SECOND",
        "2.45",
    )
)
SEEDANCE_MAX_POLL_ATTEMPTS = int(
    os.getenv("SEEDANCE_MAX_POLL_ATTEMPTS", str(KLING_MAX_POLL_ATTEMPTS))
)
SEEDANCE_POLL_INTERVAL = int(
    os.getenv("SEEDANCE_POLL_INTERVAL", str(KLING_POLL_INTERVAL))
)
SEEDANCE_ENABLED = os.getenv("SEEDANCE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
SEEDANCE_FAST_ENABLED = os.getenv("SEEDANCE_FAST_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
SEEDANCE_FAST_ENDPOINT = os.getenv("SEEDANCE_FAST_ENDPOINT", "/v1/videos")
SEEDANCE_FAST_MODEL = os.getenv("SEEDANCE_FAST_MODEL", "bytedance/seedance-2.0-fast")
SEEDANCE_FAST_MODE = os.getenv("SEEDANCE_FAST_MODE", "720p")
SEEDANCE_FAST_COST_PER_SECOND = float(
    os.getenv("SEEDANCE_FAST_COST_PER_SECOND", "1.95")
)

if AI_PROVIDER == "ZVENO" and not ZVENO_API_KEY:
    raise RuntimeError("Missing required environment variable for ZVENO: ZVENO_API_KEY")

START_BONUS = int(os.getenv("START_BONUS", "5"))
REFERRAL_BONUS_REFERRER = int(os.getenv("REFERRAL_BONUS_REFERRER", "10"))
REFERRAL_BONUS_NEW_USER = int(os.getenv("REFERRAL_BONUS_NEW_USER", "5"))

FREE_GENERATIONS_PER_DAY = int(os.getenv("FREE_GENERATIONS_PER_DAY", "1"))
BASE_GENERATION_COST = int(os.getenv("BASE_GENERATION_COST", "5"))
REFERENCE_COST = int(os.getenv("REFERENCE_COST", "0"))

MAX_POLL_ATTEMPTS = int(os.getenv("MAX_POLL_ATTEMPTS", "30"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

BUY_PACKS = [
    {"count": 10, "price": 50},
    {"count": 20, "price": 100},
    {"count": 50, "price": 250},
    {"count": 120, "price": 600},
    {"count": 300, "price": 1500},
]

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "320423776").split(",") if x.strip()]
