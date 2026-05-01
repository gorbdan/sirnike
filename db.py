import sqlite3
import os
import shutil
import logging
from datetime import datetime, date, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(__file__)
DEFAULT_DATA_DIR = "/app/data" if (os.name != "nt" and os.path.isdir("/app/data")) else BASE_DIR
DATA_DIR = os.getenv("DATA_DIR", DEFAULT_DATA_DIR).strip() or DEFAULT_DATA_DIR
SEED_DB_NAME = os.path.join(BASE_DIR, "syrochnik.db")
DB_NAME = os.path.join(DATA_DIR, "syrochnik.db")
ALLOW_DB_SEED_COPY = os.getenv("ALLOW_DB_SEED_COPY", "0").strip().lower() in ("1", "true", "yes", "on")

logger = logging.getLogger(__name__)


def _ensure_runtime_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DB_NAME):
        return

    should_copy_seed = (
        DB_NAME != SEED_DB_NAME
        and os.path.exists(SEED_DB_NAME)
        and (ALLOW_DB_SEED_COPY or DATA_DIR == BASE_DIR or os.name == "nt")
    )
    if should_copy_seed:
        shutil.copy2(SEED_DB_NAME, DB_NAME)
        logger.info("Database bootstrapped from seed: %s -> %s", SEED_DB_NAME, DB_NAME)
    elif DB_NAME != SEED_DB_NAME and os.path.exists(SEED_DB_NAME):
        logger.info(
            "Seed DB copy skipped for safety (ALLOW_DB_SEED_COPY=0). Using runtime DB at: %s",
            DB_NAME,
        )


def get_conn():
    _ensure_runtime_db()
    return sqlite3.connect(DB_NAME)


def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            referrer_id INTEGER DEFAULT NULL,
            referral_bonus_given INTEGER NOT NULL DEFAULT 0,
            free_used_date TEXT,
            free_used_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """)
        conn.commit()

        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}

        if "referrer_id" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT NULL")
        if "referral_bonus_given" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN referral_bonus_given INTEGER NOT NULL DEFAULT 0")
        if "avatar_url" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")

        conn.commit()

        conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            telegram_payment_id TEXT UNIQUE NOT NULL,
            amount INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_broadcasts (
            promo_id TEXT PRIMARY KEY,
            admin_user_id INTEGER NOT NULL,
            caption_text TEXT,
            promo_prompt TEXT NOT NULL,
            photo_file_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            clicked_at TEXT NOT NULL,
            UNIQUE(promo_id, user_id)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS generation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            provider TEXT NOT NULL,
            cost INTEGER NOT NULL DEFAULT 0,
            was_free INTEGER NOT NULL DEFAULT 0,
            references_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS generation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prompt TEXT NOT NULL,
            image_url TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        conn.commit()


def create_user_if_not_exists(
    user_id: int,
    username: Optional[str] = None,
    start_bonus: int = 5,
    referrer_id: int = None
):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()

        if row is None:
            cur.execute(
                """
                INSERT INTO users (
                    user_id, username, balance, referrer_id, referral_bonus_given, created_at
                ) VALUES (?, ?, ?, ?, 0, ?)
                """,
                (user_id, username, start_bonus, referrer_id, datetime.utcnow().isoformat())
            )
            conn.commit()
            return True

        return False


def user_exists(user_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return cur.fetchone() is not None


def get_balance(user_id: int) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else 0


def add_izyminki(user_id: int, amount: int):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        conn.commit()
        return cur.rowcount > 0


def spend_izyminki(user_id: int, amount: int) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET balance = balance - ?
            WHERE user_id = ? AND balance >= ?
            """,
            (amount, user_id, amount)
        )
        conn.commit()
        return cur.rowcount > 0


def get_free_info(user_id: int):
    today = date.today().isoformat()

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT free_used_date, free_used_count FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = cur.fetchone()

        if not row:
            return today, 0

        free_date, free_count = row
        if free_date != today:
            return today, 0

        return free_date, free_count


def use_free_generation(user_id: int):
    today = date.today().isoformat()

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT free_used_date, free_used_count FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = cur.fetchone()

        if not row:
            cur.execute(
                "UPDATE users SET free_used_date = ?, free_used_count = 1 WHERE user_id = ?",
                (today, user_id)
            )
        else:
            free_date, free_count = row
            if free_date != today:
                cur.execute(
                    "UPDATE users SET free_used_date = ?, free_used_count = 1 WHERE user_id = ?",
                    (today, user_id)
                )
            else:
                cur.execute(
                    "UPDATE users SET free_used_count = free_used_count + 1 WHERE user_id = ?",
                    (user_id,)
                )

        conn.commit()


def has_referral_bonus(user_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT referral_bonus_given FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return bool(row and row[0] == 1)


def mark_referral_bonus(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET referral_bonus_given = 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()


def set_avatar_url(user_id: int, avatar_url: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET avatar_url = ? WHERE user_id = ?",
            (avatar_url, user_id)
        )
        conn.commit()


def get_avatar_url(user_id: int) -> Optional[str]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT avatar_url FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row and row[0] else None


def clear_avatar_url(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET avatar_url = NULL WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()


def payment_exists(payment_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM payments WHERE telegram_payment_id = ?",
            (payment_id,)
        )
        return cur.fetchone() is not None


def save_payment(user_id: int, payment_id: str, amount: int):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO payments (user_id, telegram_payment_id, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, payment_id, amount, datetime.utcnow().isoformat())
        )
        conn.commit()


def save_payment_once(user_id: int, payment_id: str, amount: int) -> bool:
    with get_conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO payments (user_id, telegram_payment_id, amount, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, payment_id, amount, datetime.utcnow().isoformat())
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_all_user_ids():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        return [row[0] for row in cur.fetchall()]


def create_promo_broadcast(
    promo_id: str,
    admin_user_id: int,
    caption_text: str,
    promo_prompt: str,
    photo_file_id: str,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO promo_broadcasts (
                promo_id, admin_user_id, caption_text, promo_prompt, photo_file_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                promo_id,
                admin_user_id,
                caption_text,
                promo_prompt,
                photo_file_id,
                datetime.utcnow().isoformat(),
            )
        )
        conn.commit()


def get_promo_broadcast(promo_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT promo_id, admin_user_id, caption_text, promo_prompt, photo_file_id, created_at
            FROM promo_broadcasts
            WHERE promo_id = ?
            """,
            (promo_id,)
        )
        row = cur.fetchone()

        if not row:
            return None

        return {
            "promo_id": row[0],
            "admin_user_id": row[1],
            "caption_text": row[2],
            "promo_prompt": row[3],
            "photo_file_id": row[4],
            "created_at": row[5],
        }


def register_promo_click(promo_id: str, user_id: int) -> bool:
    with get_conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO promo_clicks (promo_id, user_id, clicked_at)
                VALUES (?, ?, ?)
                """,
                (promo_id, user_id, datetime.utcnow().isoformat())
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_promo_stats(promo_id: str):
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT COUNT(*) FROM promo_clicks WHERE promo_id = ?",
            (promo_id,)
        )
        clicks = cur.fetchone()[0]

        cur.execute(
            "SELECT created_at FROM promo_broadcasts WHERE promo_id = ?",
            (promo_id,)
        )
        row = cur.fetchone()

        return {
            "promo_id": promo_id,
            "clicks": clicks,
            "created_at": row[0] if row else None,
        }


def log_generation_event(
    user_id: int,
    kind: str,
    status: str,
    provider: str,
    cost: int = 0,
    was_free: bool = False,
    references_count: int = 0,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO generation_events (
                user_id, kind, status, provider, cost, was_free, references_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                kind,
                status,
                provider,
                int(cost or 0),
                1 if was_free else 0,
                int(references_count or 0),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_audience_overview(days: int = 30):
    now = datetime.utcnow()
    since_days = (now - timedelta(days=days)).isoformat()
    since_7d = (now - timedelta(days=7)).isoformat()
    since_24h = (now - timedelta(days=1)).isoformat()

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (since_7d,))
        new_users_7d = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (since_days,))
        new_users_period = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id IS NOT NULL")
        referred_users = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT COUNT(*) FROM generation_events WHERE kind = 'image' AND status = 'success' AND created_at >= ?",
            (since_days,),
        )
        image_success_period = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM generation_events WHERE kind = 'image' AND status = 'success' AND created_at >= ?",
            (since_days,),
        )
        generators_period = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM generation_events WHERE created_at >= ?",
            (since_24h,),
        )
        active_24h = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM generation_events WHERE created_at >= ?",
            (since_7d,),
        )
        active_7d = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT COUNT(DISTINCT user_id), COUNT(*), COALESCE(SUM(amount), 0) FROM payments WHERE created_at >= ?",
            (since_days,),
        )
        row = cur.fetchone() or (0, 0, 0)
        payers_period, payments_count_period, izyminki_sold_period = row

        cur.execute(
            """
            SELECT u.user_id, COALESCE(u.username, ''), COUNT(*) AS cnt
            FROM generation_events ge
            JOIN users u ON u.user_id = ge.user_id
            WHERE ge.kind = 'image' AND ge.status = 'success' AND ge.created_at >= ?
            GROUP BY u.user_id, u.username
            ORDER BY cnt DESC
            LIMIT 10
            """,
            (since_days,),
        )
        top_rows = cur.fetchall()

    avg_per_generator = round(image_success_period / generators_period, 2) if generators_period else 0
    referral_share = round((referred_users / total_users) * 100, 1) if total_users else 0

    return {
        "days": days,
        "total_users": total_users,
        "new_users_7d": new_users_7d,
        "new_users_period": new_users_period,
        "referred_users": referred_users,
        "referral_share": referral_share,
        "image_success_period": image_success_period,
        "generators_period": generators_period,
        "avg_per_generator": avg_per_generator,
        "active_24h": active_24h,
        "active_7d": active_7d,
        "payers_period": payers_period or 0,
        "payments_count_period": payments_count_period or 0,
        "izyminki_sold_period": izyminki_sold_period or 0,
        "top_generators": [
            {"user_id": r[0], "username": r[1], "count": r[2]}
            for r in top_rows
        ],
    }


def add_generation_history(user_id: int, prompt: str, image_url: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO generation_history (user_id, prompt, image_url, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, prompt or "", image_url, datetime.utcnow().isoformat()),
        )
        conn.commit()


def get_generation_history(user_id: int, limit: int = 10, offset: int = 0):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, prompt, image_url, created_at
            FROM generation_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, int(limit), int(offset)),
        )
        rows = cur.fetchall()
        return [
            {"id": r[0], "prompt": r[1], "image_url": r[2], "created_at": r[3]}
            for r in rows
        ]


def get_generation_history_item(user_id: int, item_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, prompt, image_url, created_at
            FROM generation_history
            WHERE user_id = ? AND id = ?
            """,
            (user_id, int(item_id)),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "prompt": row[1], "image_url": row[2], "created_at": row[3]}
